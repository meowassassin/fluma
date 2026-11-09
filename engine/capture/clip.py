#!/usr/bin/env python3
"""
클립 — 유튜브 · 쇼츠 · 틱톡 · 인스타 릴스 · 레딧 영상 주소에서 필요한 구간만 받아 영상 재료로 쓴다(모음 · 반응 쇼츠).

  python3 engine/capture/clip.py search "고양이 vs 동물" [--n 20] [--max-sec 90]        # 받기 전 후보 목록만(주소 · 길이 · 조회수 · 채널)
  python3 engine/capture/clip.py fetch <영상 id> <이름> <주소> [--in 3.5] [--out 9] [--subs] [--best 3.5] [--vertical]
      --best 초: in/out 을 안 줬으면 유튜브 '가장 많이 다시 본 구간'(heatmap)에서 그 길이의 가장 센 구간을 고른다(첫 1.5초 제외)
      --moment "설명": 보기(VL) 모델이 영상을 보고 그 설명에 맞는 순간을 찾는다(예: "고양이가 놀라 뛰어오르는 순간") — --best 와 같이 주면 길이는 --best
      --vertical: 받은 뒤 세로 9:16 으로 리프레이밍(engine/capture/reframe.py — 주인공 따라가기 · 둘이 안 들어가면 띠 배치) → clip.mp4 가 세로판
  python3 engine/capture/clip.py credits <영상 id>                                       # 설명란 '출처' 목록(meme.py credits 와 같은 형식)

받은 클립: data/public/elements/<영상 id>/<이름>/clip.mp4 + meta.json(채널 · 제목 · 주소 · 구간 · 받은 날)
재료:      {"type": "video", "src": "data/public/elements/<영상 id>/<이름>/clip.mp4"}
--subs:    클립 속 말을 받아써 meta.json 의 subs(단어 시각)에 남긴다 — 원본 말 자막(반응 쇼츠)에 쓴다.

운영 원칙(기본값으로 강제)
- 구간은 짧게: 한 클립 기본 상한 15초(--max 로 바꿈). 긴 원본을 통째로 옮기지 않는다.
- 출처를 남긴다: 채널 · 제목 · 주소가 meta.json 에 들어가고 credits 로 설명란에 붙는다.
- 우리 편집을 얹는다: 순위 · 제목 · 반응 자막 · 효과음 — 재사용 콘텐츠 수익화 정책은 '거의 그대로 옮긴 영상'을 막는다.
권리는 원작자에게 있다. 신고 · Content ID 위험은 채널 운영자가 판단한다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
PUBLIC = ROOT / "data" / "public"
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
AI_TITLE = re.compile(r"\b(ai|a\.i\.|sora|veo|kling|generated)\b|인공지능|AI\s*영상", re.I)
YTDLP = str(ROOT / ".venv" / "bin" / "yt-dlp") if (ROOT / ".venv" / "bin" / "yt-dlp").exists() else "yt-dlp"


def _run(args: list[str], timeout: int = 300) -> str:
    r = subprocess.run([YTDLP, "--no-warnings", "--no-playlist", *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise SystemExit(f"[clip] 실패: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout


def cmd_search(a):
    q = f"ytsearch{a.n}:{a.query}" + (" #shorts" if a.shorts else "")
    out = subprocess.run([YTDLP, "--no-warnings", "--flat-playlist", "-J", q], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise SystemExit(f"[clip] 검색 실패: {out.stderr.strip()[-300:]}")
    rows = []
    for e in json.loads(out.stdout).get("entries") or []:
        d = e.get("duration") or 0
        if a.max_sec and d and d > a.max_sec:
            continue
        if (e.get("view_count") or 0) < a.min_views or AI_TITLE.search(e.get("title") or ""):   # 안 퍼진 영상 · AI 생성 영상은 모음 재료로 약하다
            continue
        rows.append({"url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}", "id": e.get("id"), "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
                     "sec": d, "views": e.get("view_count")})
    rows.sort(key=lambda r: -(r["views"] or 0))
    d = PUBLIC / "clips"; d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", a.query).strip("-")[:40] or "q"
    (d / f"search-{slug}.json").write_text(json.dumps({"query": a.query, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": rows}, ensure_ascii=False, indent=1), "utf-8")
    for i, r in enumerate(rows, 1):
        v = f"{r['views']:,}" if r["views"] else "?"
        print(f"{i:2d}. {r['sec'] or '?':>5}s  조회 {v:>12}  {r['channel'] or '?'} — {r['title']}\n    {r['url']}")
    print(f"[clip] 목록: {(d / f'search-{slug}.json').relative_to(ROOT)} — 받을 것만 fetch")


def cmd_fetch(a):
    if not ID_RE.match(a.id) or not ID_RE.match(a.name):
        raise SystemExit("[clip] 잘못된 영상 id · 이름")
    info = json.loads(_run(["-J", "--skip-download", a.url], 120))
    dur = float(info.get("duration") or 0)
    if a.moment and a.in_ is None and a.out is None:             # VL 이 본 '원하는 순간'
        try:
            import see
            ms = see.moments(a.url, a.moment, a.best, sid=a.id)
            if ms:
                m0 = ms[0]
                st, en = float(m0["start"]), float(m0["end"])
                if a.best:
                    mid = (st + en) / 2
                    st, en = max(0.0, mid - a.best / 2), mid + a.best / 2
                a.in_, a.out = st, en
                print(f"[clip] VL 이 고른 순간 {st:.1f}~{en:.1f}초 — {m0.get('why', '')}")
        except Exception as e:  # noqa: BLE001 — VL 이 없거나(키 · 모델) 승인이 필요하면 다시 본 구간으로
            print(f"[clip] VL 순간 찾기 건너뜀: {e}")
    if a.best and a.in_ is None and a.out is None:               # 가장 많이 다시 본 구간
        h = info.get("heatmap") or []
        W = float(a.best)
        if h and dur > W:
            cand = [x / 10 for x in range(15, int((dur - W) * 10) + 1)]
            a.in_ = max(cand, key=lambda st: sum(t["value"] * max(0, min(t["end_time"], st + W) - max(t["start_time"], st)) for t in h))
            a.out = a.in_ + W
            print(f"[clip] 다시 본 구간 {a.in_:.1f}~{a.out:.1f}초(heatmap)")
    t0 = max(0.0, float(a.in_ or 0))
    t1 = float(a.out) if a.out else (min(dur, t0 + a.max) if dur else t0 + a.max)
    if t1 - t0 > a.max:
        raise SystemExit(f"[clip] 구간 {t1 - t0:.1f}초 — 상한 {a.max}초. 필요한 부분만(--in · --out) 또는 --max 로 명시")
    out = PUBLIC / "elements" / a.id / a.name
    out.mkdir(parents=True, exist_ok=True)
    dst = out / "clip.mp4"
    _run(["-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b", "--merge-output-format", "mp4", "--download-sections", f"*{t0}-{t1}",
          "--force-keyframes-at-cuts", "-o", str(out / "raw.%(ext)s"), a.url], 600)
    raw = next(iter(sorted(out.glob("raw.*"))), None)
    if not raw:
        raise SystemExit("[clip] 받은 파일이 없습니다")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-movflags", "+faststart", str(dst)], check=True)
    raw.unlink()
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(dst)], capture_output=True, text=True)
    st = (json.loads(pr.stdout or "{}").get("streams") or [{}])[0]
    meta = {"kind": "clip", "role": "clip", "file": "clip.mp4", "in": t0, "out": t1, "sec": round(t1 - t0, 2), "w": st.get("width"), "h": st.get("height"),
            "source": {"site": info.get("extractor_key"), "title": info.get("title"), "url": info.get("webpage_url") or a.url, "author": info.get("channel") or info.get("uploader"),
                       "author_url": info.get("channel_url") or info.get("uploader_url"), "date": info.get("upload_date")},
            "fetched": time.strftime("%Y-%m-%d"), "license": f"원작자 권리 — 출처: {info.get('webpage_url') or a.url}", "commercial": "불명확(출처 표기 · 짧은 구간 · 우리 편집 얹기)"}
    if a.subs:
        meta["subs"] = transcribe(dst)
    if a.vertical:                                              # 세로 9:16 — 원본 가로판은 clip_h.mp4 로 남긴다
        import shutil as _sh
        hor = out / "clip_h.mp4"; _sh.move(str(dst), hor)
        sys.path.insert(0, str(ROOT / "engine" / "capture"))
        import reframe as RF
        P = RF.plan(hor)
        RF.render(hor, P, dst)
        meta.update(w=1080, h=1920, reframe={"layout": P["layout"], "aspect": P["aspect"], "found_ratio": P["found_ratio"], "zoom_in": P["zoom_in"], "from": "clip_h.mp4"})
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    print(f"[clip] {dst.relative_to(ROOT)} · {meta['sec']}초 · {st.get('width')}×{st.get('height')} · {meta['source']['author']} — {meta['source']['title']}")
    print(f'[clip] 재료: {{"type": "video", "src": "{dst.relative_to(ROOT)}"}}')


def transcribe(f: Path) -> list[dict]:
    """클립 속 말 → 단어 시각. 원본 말 자막에 쓴다 — '듣기' 모델을 골랐으면 오픈라우터, 아니면 faster-whisper(CPU)"""
    try:
        import listen
        r = listen.remote(f)
        if r is not None:
            return [{"text": s["text"], "s": s["start"], "e": s["end"], "words": s["words"]} for s in r]
    except Exception as e:  # noqa: BLE001
        print(f"[clip] 오픈라우터 받아쓰기 실패 — 로컬로: {e}")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    m = WhisperModel("base", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(f), word_timestamps=True, vad_filter=True)
    return [{"text": s.text.strip(), "s": round(s.start, 2), "e": round(s.end, 2), "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in (s.words or [])]} for s in segs]


def cmd_credits(a):
    base = PUBLIC / "elements" / a.id
    for mp in sorted(base.glob("*/meta.json")) if base.exists() else []:
        m = json.loads(mp.read_text("utf-8"))
        if m.get("kind") == "clip":
            s = m["source"]
            print(f"{s.get('author') or '?'} · {s.get('title') or ''} — {s['url']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search"); s.add_argument("query"); s.add_argument("--n", type=int, default=20); s.add_argument("--max-sec", type=float, default=0); s.add_argument("--shorts", action="store_true"); s.add_argument("--min-views", type=int, default=10000)
    f = sp.add_parser("fetch"); f.add_argument("id"); f.add_argument("name"); f.add_argument("url")
    f.add_argument("--in", dest="in_", type=float, default=None); f.add_argument("--out", type=float); f.add_argument("--max", type=float, default=15); f.add_argument("--subs", action="store_true"); f.add_argument("--best", type=float); f.add_argument("--vertical", action="store_true"); f.add_argument("--moment")
    c = sp.add_parser("credits"); c.add_argument("id")
    a = ap.parse_args()
    {"search": cmd_search, "fetch": cmd_fetch, "credits": cmd_credits}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
