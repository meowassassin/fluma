#!/usr/bin/env python3
"""보기(VL) — 영상 · 그림을 직접 보고 말로. Claude Code 는 그림은 보지만 영상은 못 본다 → 그 눈이 VL 이다.
설정 → 보기 · 만들기 · 말하기 의 '보기 · 영상 이해(VL)' 모델(키가 있으면 기본 켬). 판단은 늘 에이전트가 한다 — VL 은 본 것을 근거(시각)와 함께 말한다.

**범용(무엇이든)** — 기능을 정해 두지 않는다. 에이전트가 영상 · 그림 · 유튜브 링크에 대해 궁금한 것은 무엇이든 묻는다:
  python3 engine/providers/see.py ask <영상|그림|유튜브 id·주소 ...> --q "질문" [--json] [--sid <콘티 id>] [--approve]
    예) "이 쇼츠에서 시청자가 넘기기 쉬운 순간은?" · "두 영상의 편집 리듬 차이" · "이 캡처에서 강조할 숫자 위치(비율 좌표)" ·
        "이 클립에서 고양이가 놀라는 순간 시각" · "이 그림이 '몽환 필름' 느낌과 맞나, 무엇을 고치면 되나" · "이 장면에 어울리는 효과음 세 가지"

**자주 쓰는 일(위 ask 를 구조화한 것)**:
  ref <쇼츠 id ...>                 레퍼런스 이해 → xray.json 의 understanding(장면 · 훅 · 반전 · 편집 문법 · 자막 말투 · 소리 · 붙잡는 장치 · 뻔한 것 · 빌릴 것)
  cliches <콘티 id>                 레퍼런스 이해들을 모아 뻔함 지도 초안 → data/workspace/concepts/<id>.cliches-draft.json (에이전트가 고쳐 concepts 에)
  moments <영상|유튜브> --want "…" [--sec 3.5]   원하는 순간 찾기 → [{start, end, why}] (클립 구간 · 짤 · 반응 자막 시각)
  critique <콘티 id> [--video 경로]  초안 영상 비평 — 의도 · 콘셉트 · 레퍼런스 이해와 대조, 몇 초에 무엇이 왜 어색한지 · 고칠 방법 → data/workspace/critique/<id>.json
  clip <콘티> <재료 id>              생성 · 퍼온 클립이 설계(재료 칸)와 맞나 — 동작 · 카메라 · 인물 · 글자 · 어색함
  image <그림> --want "…"           그림이 원하는 것과 맞나(키프레임 · 시안 · 재료)

영상 보내기: 모델이 google/* 이고 유튜브 링크가 있으면 링크 그대로(Gemini AI Studio 는 유튜브만 받는다), 아니면 파일을 base64(크면 480p 로 줄여서).
돈: 모델 가격 × 영상 길이로 어림 → 비용 관문(영상 한 편 상한 안이면 그대로, 넘으면 사용자 승인 뒤 --approve) → 장부.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

XRAY = ROOT / "data" / "public" / "trends" / "xray"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MAX_INLINE = 18 * 1024 * 1024                  # base64 로 보낼 영상 크기 — 넘으면 줄인다
TOKENS_PER_SEC = 300                            # 영상 1초 ≈ 300 입력 토큰(Gemini 기본 해상도 기준 어림) — 예상 비용에만 쓴다
SYSTEM = ("You are the eyes of a short-form video editor. Watch carefully and report what is actually on screen and in the audio, "
          "with timestamps in seconds. Do not invent things you cannot see or hear; say 'unclear' instead. Answer in Korean unless asked otherwise.")


class NoModel(RuntimeError):
    pass


def model(sb: dict | None = None) -> str:
    import catalog
    m = catalog.chosen("see.video", sb)
    if not m:
        raise NoModel("보기(VL) 모델이 없습니다 — 오픈라우터 키를 넣고 설정 → 보기 · 만들기 · 말하기 에서 고르세요(없으면 측정 X-ray + 프레임 시트로)")
    return m


def _yt(x: str) -> str | None:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", x)
    if m:
        return m.group(1)
    return x if re.fullmatch(r"[A-Za-z0-9_-]{11}", x) else None


def _dur(p: Path) -> float:
    try:
        from craft import vclip
        return float(vclip.probe(p)["dur"] or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _shrink(p: Path, td: Path) -> Path:
    """보기 모델에 보낼 영상은 늘 작게(360p · 초당 8장 · 소리 모노) — 모델은 어차피 초당 1~2장만 본다.
    2026-11-09: 8.8MB 원본을 통째로 올려 무료 모델에서 한 편에 4분 넘게 걸림"""
    if p.stat().st_size <= 1_500_000:
        return p
    out = td / f"{p.stem}.vl.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vf", "scale=-2:360,fps=8", "-c:v", "libx264", "-crf", "32", "-preset", "veryfast",
                    "-c:a", "aac", "-ac", "1", "-b:a", "40k", str(out)], check=True)
    return out


def resolve_media(items: list[str], mdl: str, td: Path) -> tuple[list, list, float]:
    """(그림들, 영상들, 영상 길이 합) — 유튜브 id/주소는 google 모델이면 링크, 아니면 X-ray 원본(src.mp4) 또는 받아서"""
    imgs, vids, secs = [], [], 0.0
    for it in items:
        p = Path(it) if Path(it).is_absolute() else ROOT / it
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            imgs.append(p)
            continue
        if p.is_file() and p.suffix.lower() in VIDEO_EXT:
            secs += _dur(p)
            vids.append(_shrink(p, td))
            continue
        y = _yt(it)
        if not y:
            raise SystemExit(f"볼 수 없는 것: {it} (영상 · 그림 파일 또는 유튜브 id · 주소)")
        local = XRAY / y / "src.mp4"
        if local.exists():
            secs += _dur(local)
        if mdl.startswith("google/"):
            vids.append(f"https://www.youtube.com/watch?v={y}")
            secs += 0 if local.exists() else 60
        elif local.exists():
            vids.append(_shrink(local, td))
        else:
            dl = td / f"{y}.mp4"
            from platform_util import venv_tool
            subprocess.run([venv_tool("yt-dlp"), "-q", "-f",
                            "b[height<=480][ext=mp4]/b[height<=480]/b", "-o", str(dl), f"https://www.youtube.com/watch?v={y}"], check=True, timeout=600)
            secs += _dur(dl)
            vids.append(_shrink(dl, td))
    return imgs, vids, secs


def estimate(mdl: str, secs: float, n_images: int, out_tokens: int = 3000) -> float | None:
    import catalog
    row = next((m for m in catalog.raw().get("models") or [] if m["id"] == mdl), None)
    if not row:
        return None
    pr = row.get("pricing") or {}
    pin, pout = catalog._f(pr.get("prompt")) or 0.0, catalog._f(pr.get("completion")) or 0.0
    return round((secs * TOKENS_PER_SEC + n_images * 1300 + 1500) * pin + out_tokens * pout, 4)


def _json(text: str):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1)
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def ask(items: list[str], question: str, sid: str = "-", json_mode: bool = False, approve: bool = False, sb: dict | None = None,
        what: str = "보기") -> dict:
    """무엇이든 묻기 → {"text", "json"?, "cost", "model"}"""
    import catalog
    import openrouter as OR
    mdl = model(sb)
    with tempfile.TemporaryDirectory() as td:
        imgs, vids, secs = resolve_media(items, mdl, Path(td))
        est = estimate(mdl, secs, len(imgs))
        catalog.guard(sid, "see.video", mdl, est, f"{what} — 영상 {secs:.0f}초 · 그림 {len(imgs)}장", approve)
        q = question + ("\n\nReturn only valid JSON." if json_mode else "")
        r = OR.see(mdl, q, images=imgs, videos=vids, system=SYSTEM, json_mode=json_mode)
    catalog.record(sid, "see.video", mdl, r.get("cost"), what, est=est)
    out = {"text": r["text"], "cost": r.get("cost"), "model": mdl}
    if json_mode:
        try:
            out["json"] = _json(r["text"])
        except ValueError:
            out["json"] = None
    return out


# ---------------------------------------------------------------- 레퍼런스 이해
REF_Q = """이 쇼츠를 편집자 눈으로 처음부터 끝까지 보고 아래 JSON 으로 답하라. 측정값(아래)과 다르게 보이면 본 것을 우선하고 notes 에 적어라.
측정값: {measured}
{{
 "summary": "한 문장 — 무엇을 어떻게 보여 주는 영상인가",
 "format": "형식(순위 모음 · 정보 · 광고 · 브이로그 · 반응 · 시연 · 스토리 …)과 근거",
 "hook": {{"t": [시작, 끝], "device": "첫 3초에 붙잡는 장치", "why": "왜 넘기지 않게 되나"}},
 "beats": [{{"t": [시작, 끝], "what": "화면에서 일어나는 일", "camera": "구도 · 움직임", "text_on_screen": "화면 글자 그대로", "sound": "말 · 음악 · 효과음", "emotion": "시청자 감정"}}],
 "turns": [{{"t": 초, "kind": "반전 · 웃음 · 정보 · 감정", "how": "어떻게 터지나(타이밍 · 대비 · 자막 · 소리)"}}],
 "editing": {{"pace": "컷 리듬", "cuts": "컷 · 전환 방식", "zoom_motion": "확대 · 흔들림 · 속도 변화", "captions": {{"position": "위치", "style": "모양 · 색 · 크기", "tone": "말투(예: 동물 속마음 · ㅋㅋ · 반말)", "timing": "말 · 동작과 언제 맞물리나"}}}},
 "audio": {{"music": "곡 느낌 · 박자 · 컷과 맞물림", "sfx": "효과음과 쓰인 순간", "voice": "나레이션 · 원음 · 말투"}},
 "retention": ["끝까지 보게 하는 장치들(시각 포함)"],
 "loop_or_end": "끝 처리(루프 · 질문 · 반전 · CTA)",
 "cliches": ["이 분야에서 흔히 보이는 것 중 이 영상이 한 것"],
 "fresh": ["이 영상만의 다른 점"],
 "borrow": ["우리 영상에 빌릴 문법(내용 말고 리듬 · 장치)"],
 "do_not_copy": ["베끼면 안 되는 것(내용 · 대사 · 고유 캐릭터)"],
 "notes": "그 밖에 편집자가 알아야 할 것"
}}"""


def _measured(x: dict) -> str:
    shots = x.get("shots") or []
    cuts = [round(float(s.get("start", 0)), 2) for s in shots]
    sp = " / ".join(s.get("text", "") for s in (x.get("speech") or [])[:20])[:600]
    tx = " / ".join(sorted({str(t.get("text", "")) for t in (x.get("text") or [])[:40]}))[:400]
    return json.dumps({"길이초": (x.get("video") or {}).get("duration"), "컷 시작": cuts[:40], "말": sp, "화면 글자": tx,
                       "BPM": (x.get("sound") or {}).get("bpm")}, ensure_ascii=False)


def ref(rid: str, approve: bool = False, force: bool = False) -> dict:
    f = XRAY / rid / "xray.json"
    x = json.loads(f.read_text("utf-8")) if f.exists() else {}
    if x.get("understanding") and not force:
        return x["understanding"]
    r = ask([rid], REF_Q.format(measured=_measured(x) if x else "(측정 없음)"), sid=f"ref:{rid}", json_mode=True, approve=approve, what=f"레퍼런스 이해 {rid}")
    u = {**(r.get("json") or {"raw": r["text"]}), "_model": r["model"], "_at": dt.datetime.now().isoformat(timespec="seconds")}
    if f.exists():
        x["understanding"] = u
        f.write_text(json.dumps(x, ensure_ascii=False, indent=1), "utf-8")
    else:
        (XRAY / rid).mkdir(parents=True, exist_ok=True)
        (XRAY / rid / "understanding.json").write_text(json.dumps(u, ensure_ascii=False, indent=1), "utf-8")
    return u


def understanding(rid: str) -> dict | None:
    f = XRAY / rid / "xray.json"
    if f.exists():
        u = json.loads(f.read_text("utf-8")).get("understanding")
        if u:
            return u
    g = XRAY / rid / "understanding.json"
    return json.loads(g.read_text("utf-8")) if g.exists() else None


def cliches(sid: str, approve: bool = False) -> dict:
    """레퍼런스 이해들 → 뻔함 지도 초안(코드가 판정하지 않는다 — VL 이 본 것을 묶고, 에이전트가 고친다)"""
    import catalog
    import openrouter as OR
    sb = _sb(sid)
    us = {r: understanding(r) for r in sb.get("reference") or []}
    us = {k: v for k, v in us.items() if v}
    if not us:
        raise SystemExit("레퍼런스 이해가 없습니다 — 먼저 see.py ref <쇼츠 id>")
    mdl = model(sb)
    q = ("아래는 같은 분야 쇼츠들을 본 기록이다. '이 분야에서 다들 하는 것(뻔한 것)'을 묶어라 — 구조 · 첫장면 · 제목 · 화면 · 말투 · 소리 종류마다. "
         "각각 실제로 한 영상 id 를 seen_in 에. 그리고 아무도 안 한 빈자리(기회)도 적어라.\n"
         'JSON: {"cliches": [{"kind": "구조|첫장면|제목|화면|말투|소리", "what": "…", "seen_in": ["id"]}], "gaps": ["…"]}\n\n'
         + json.dumps(us, ensure_ascii=False)[:60000])
    est = estimate(mdl, 0, 0)
    catalog.guard(sid, "see.video", mdl, est, "뻔함 지도 초안", approve)
    r = OR.see(mdl, q + "\n\nReturn only valid JSON.", system=SYSTEM, json_mode=True)
    catalog.record(sid, "see.video", mdl, r.get("cost"), "뻔함 지도 초안", est=est)
    d = _json(r["text"])
    out = ROOT / "data" / "workspace" / "concepts" / f"{sid}.cliches-draft.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    return d


def moments(src: str, want: str, sec: float | None = None, approve: bool = False, sid: str = "-") -> list[dict]:
    q = (f"이 영상에서 다음에 맞는 순간을 모두 찾아라: {want}\n"
         + (f"각 구간은 {sec:g}초 안팎으로. " if sec else "")
         + 'JSON: {"moments": [{"start": 초, "end": 초, "why": "무엇이 보이고 들리나", "score": 0~1}]} — score 높은 순.')
    r = ask([src], q, sid=sid, json_mode=True, approve=approve, what=f"순간 찾기: {want[:30]}")
    return ((r.get("json") or {}).get("moments")) or []


def _sb(sid_or_path: str) -> dict:
    p = Path(sid_or_path)
    if not p.suffix:
        p = ROOT / "data" / "storyboards" / f"{sid_or_path}.json"
    elif not p.is_absolute():
        p = ROOT / p
    return json.loads(p.read_text("utf-8"))


def critique(sid: str, video: str | None = None, approve: bool = False) -> dict:
    sb = _sb(sid)
    sid = sb["id"]
    outs = [ROOT / "data" / "out" / n for n in (f"{sid}-craft-Scenes.mp4", f"{sid}-craft-Scenes-draft.mp4", f"{sid}.mp4", f"{sid}-draft.mp4")]
    v = Path(video) if video else max((o for o in outs if o.exists()), key=lambda o: o.stat().st_mtime, default=None)   # 가장 최근 렌더(초안 포함)
    if not v or not Path(v).exists():
        raise SystemExit("초안 영상이 없습니다 — 먼저 render.py --draft (또는 --video 경로)")
    refs = {r: understanding(r) for r in sb.get("reference") or []}
    dr = sb.get("direction") or {}
    ctx = {"intent": sb.get("intent"), "concept": sb.get("concept"), "feel": (dr.get("feel") or {}).get("name"),
           "planned_direction": {k: dr.get(k) for k in ("note", "transition", "motion", "font_title", "color_bg", "color_text") if dr.get(k)},
           "scenes": [{"i": i + 1, "sec": s.get("sec"), "beat": s.get("beat"), "narration": s.get("narration"), "caption": s.get("caption"),
                       "screen": s.get("screen"), "on_screen_text": s.get("hook_text") or s.get("text") or s.get("title"),
                       "materials": [{k: m.get(k) for k in ("type", "id", "role", "prompt", "note", "text") if m.get(k)} for m in s.get("materials") or [] if isinstance(m, dict)]}
                      for i, s in enumerate(sb.get("scenes") or [])],
           "reference_understanding": {k: {kk: (u or {}).get(kk) for kk in ("hook", "editing", "turns", "retention", "borrow")} for k, u in refs.items()}}
    q = ("이 초안 쇼츠를 깐깐한 편집자로 보고 비평하라. 의도 · 콘셉트 · 레퍼런스에서 빌리기로 한 문법과 대조한다. "
         "먼저 계획(planned_direction.note · 장면 materials · 화면 글자)이 화면에 실제로 나왔는지 장면마다 확인하고, 빠진 것(예: 계획한 전환 · 글자 · 연출이 없음)은 severity high 로 적는다. "
         "가공 없이 붙인 웹 화면(브라우저 머리띠 · 주소 · 사업자 정보 · 흰 바닥글 · 빈 여백), 톤이 안 맞는 컷, 정지된 로고도 짚는다. "
         "넘기게 되는 순간, 어색한 타이밍(자막 · 말 · 컷 · 소리), 안 보이거나 읽기 어려운 글자, 화면이 멈춘 곳, 뻔한 곳, 느낌이 섞인 곳을 시각과 함께.\n"
         'JSON: {"overall": "한 문단", "watch_through": "끝까지 볼 확률과 이유", "issues": [{"t": [시작, 끝], "scene": 장면 번호, "what": "무엇이", '
         '"why": "왜 문제", "fix": "어떻게 고치나(구체적으로)", "severity": "high|mid|low"}], "keep": ["좋아서 남길 것"]}\n\n'
         + json.dumps(ctx, ensure_ascii=False)[:20000])
    an = (sb.get("direction") or {}).get("anchor") or {}
    frames = [f for f in an.get("frames") or [] if (ROOT / f).exists()][:4]
    if frames:                                                   # 기준점: 사용자가 고른 기준 광고의 실제 프레임과 같은 세계인지도 본다
        q += ("\n\n영상 뒤에 붙은 그림들은 사용자가 '" + str(an.get("words") or "") + "' 의 기준으로 고른 실제 광고 프레임이다. "
              "초안이 그 시각 문법(" + json.dumps({k: (an.get("rules") or {}).get(k) for k in ("background", "light", "palette", "subject", "typography")}, ensure_ascii=False)
              + ")과 얼마나 같은 세계인지 JSON 에 \"anchor\": {\"score\": 0~10, \"misses\": [\"기준과 다른 것\"]} 로 더하라. 6 미만이면 그 차이를 issues 에 high 로.")
    r = ask([str(v), *frames], q, sid=sid, json_mode=True, approve=approve, sb=sb, what="초안 비평")
    d = {**(r.get("json") or {"raw": r["text"]}), "_model": r["model"], "_video": Path(v).relative_to(ROOT).as_posix() if Path(v).is_relative_to(ROOT) else str(v),
         "_at": dt.datetime.now().isoformat(timespec="seconds")}
    out = ROOT / "data" / "workspace" / "critique" / f"{sb['id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    return d


def check_clip(sb: dict, mid: str, approve: bool = False) -> dict:
    m = next((dict(m) for sc in sb.get("scenes") or [] for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("id") == mid), None)
    if not m:
        raise SystemExit(f"재료 {mid} 가 콘티에 없습니다")
    from craft.materials import find_upload
    f = find_upload(sb["id"], {**m, "type": "video"}) or (ROOT / m["src"] if m.get("src") else None)
    if not f or not Path(f).exists():
        raise SystemExit(f"{mid}: 클립이 아직 없습니다")
    spec = {k: m.get(k) for k in ("what", "want", "in", "out", "query") if m.get(k)}
    q = ("이 클립(퍼온 클립 · 스톡 · 녹화)이 장면 의도와 맞는지 보라. 의도: " + json.dumps(spec, ensure_ascii=False)
         + '\nJSON: {"match": 0~1, "issues": [{"t": 초, "what": "다른 점 · 어색함 · 잘림 · 글자", "fix": "어느 구간을 쓰거나 무엇으로 바꿀지"}], "usable": [시작, 끝]}')
    return ask([str(f)], q, sid=sb["id"], json_mode=True, approve=approve, sb=sb, what=f"클립 확인 {mid}").get("json") or {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("ask"); a_.add_argument("items", nargs="+"); a_.add_argument("--q", required=True); a_.add_argument("--json", action="store_true"); a_.add_argument("--sid", default="-")
    r_ = sub.add_parser("ref"); r_.add_argument("ids", nargs="+"); r_.add_argument("--force", action="store_true")
    c_ = sub.add_parser("cliches"); c_.add_argument("sid")
    m_ = sub.add_parser("moments"); m_.add_argument("src"); m_.add_argument("--want", required=True); m_.add_argument("--sec", type=float); m_.add_argument("--sid", default="-")
    k_ = sub.add_parser("critique"); k_.add_argument("sid"); k_.add_argument("--video")
    l_ = sub.add_parser("clip"); l_.add_argument("storyboard"); l_.add_argument("mid")
    i_ = sub.add_parser("image"); i_.add_argument("image"); i_.add_argument("--want", required=True); i_.add_argument("--sid", default="-")
    for p in (a_, r_, c_, m_, k_, l_, i_):
        p.add_argument("--approve", action="store_true", help="사용자가 금액을 보고 승인했을 때만")
    a = ap.parse_args()
    import catalog
    try:
        if a.cmd == "ask":
            r = ask(a.items, a.q, a.sid, a.json, a.approve)
            print(json.dumps(r["json"], ensure_ascii=False, indent=1) if a.json and r.get("json") is not None else r["text"])
        elif a.cmd == "ref":
            for rid in a.ids:
                u = ref(_yt(rid) or rid, a.approve, a.force)
                print(f"[보기] {rid}: {u.get('summary') or '(요약 없음)'}")
        elif a.cmd == "cliches":
            d = cliches(a.sid, a.approve)
            print(json.dumps(d, ensure_ascii=False, indent=1))
        elif a.cmd == "moments":
            print(json.dumps(moments(a.src, a.want, a.sec, a.approve, a.sid), ensure_ascii=False, indent=1))
        elif a.cmd == "critique":
            d = critique(a.sid, a.video, a.approve)
            print(json.dumps({k: d.get(k) for k in ("overall", "watch_through", "issues")}, ensure_ascii=False, indent=1))
        elif a.cmd == "clip":
            print(json.dumps(check_clip(_sb(a.storyboard), a.mid, a.approve), ensure_ascii=False, indent=1))
        else:
            q = (f"이 그림이 다음과 맞는지 보라: {a.want}\n"
                 'JSON: {"match": 0~1, "seen": "보이는 것", "issues": ["다른 점 · 어색함"], "fix": "다시 만들 때 영어 프롬프트 문구"}')
            r = ask([a.image], q, a.sid, True, a.approve, what="그림 확인")
            print(json.dumps(r.get("json") or r["text"], ensure_ascii=False, indent=1))
    except NoModel as e:
        print(f"[보기 없음] {e}")
        return 10
    except catalog.NeedApproval as e:
        print(f"[승인 필요] {e}")
        return 20
    return 0


if __name__ == "__main__":
    sys.exit(main())
