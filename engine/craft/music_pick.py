#!/usr/bin/env python3
"""배경 음악 — 넣을지 정하고(decide), 넣는다면 요즘 쓰이는 곡 중 이 영상에 맞는 것을 골라 콘티 music 에 적는다(pick). auto = 둘 다.

  python3 engine/craft/music_pick.py decide data/storyboards/<id>.json          # 넣을지만(이유와 함께)
  python3 engine/craft/music_pick.py pick   data/storyboards/<id>.json [--mood "calm lofi"] [--bpm 90]
  python3 engine/craft/music_pick.py auto   data/storyboards/<id>.json          # produce.py 가 음성 전에 부른다

넣을지(decide) — 콘티 music.use 를 사용자 · 에이전트가 적었으면 그대로. 아니면
  레퍼런스에 음악이 깔렸나(X-ray sound.music 비율) · 레퍼런스가 붙인 곡이 있나(쇼츠 사운드 표시) → 깔렸으면 넣고, 말로만 끌고 가면 뺀다
  레퍼런스가 없으면: 나레이션 없음 · 감성 · 순위 · 광고 · 시세 형식은 넣고, 퍼온 클립 원음 위주(클립 형식)는 뺀다, 설명형은 말 뒤에 작게
고르기(pick) — 후보 세 줄기
  ① 레퍼런스가 붙인 곡  ② 비슷한 쇼츠들이 지금 붙이는 곡(trend_music — 쇼츠 화면의 사운드 표시)
  ③ 유튜브 인기 · 최신 곡(YOUTUBE_API_KEY 가 있으면 Data API: 음악 인기 차트(KR) · 최근 1년 조회수 순) / 키가 없으면 웹 검색
  → 상업 곡은 영상에 직접 넣지 않는다(Content ID — 수익이 권리자에게 · 소리 꺼짐). 같은 제목의 무료 라이브러리 판(오디오 라이브러리 ·
    No Copyright)이 있으면 그것을, 없으면 그 곡과 박자 · 분위기가 비슷한 무료 곡을 넣고, 상업 곡은 upload_sound(업로드 때 쇼츠 편집기에서
    '사운드 추가'로 붙일 곡)로 남긴다. 설정 music_any_license=true 면(사용자가 권리 위험을 알고 켬) 상업 곡도 직접 넣는다.
  상위 몇 곡만 앞부분(150초)을 받아 박자(BPM)를 재고, 목표 박자(레퍼런스 > 분위기)에 가까운 곡 · 가장 힘 있는 구간(start)을 고른다.
결과: 콘티 music = {use, src, title, by, url, license, free, bpm, start, why, upload_sound[], source: "auto"} · 받은 곡은 data/workspace/asset-cache/music/
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

CACHE = ROOT / "data" / "workspace" / "asset-cache" / "music"
XRAY = ROOT / "data" / "public" / "trends" / "xray"
FREE_RE = re.compile(r"no copyright|copyright[- ]free|royalty[- ]free|audio library|free (bgm|music)|무료 ?(음원|브금|bgm)|저작권 ?(없는|free)|ncs release", re.I)
FREE_CHANNELS = re.compile(r"^(audio library|nocopyrightsounds|no copyright music|vlog no copyright music|free music library|bensound|chillhop music|"
                           r"audio library — music for content creators|breaking copyright.*|royalty free music.*)$", re.I)
ORIGINAL = re.compile(r"오리지널 사운드|원본 사운드|original sound|original audio", re.I)
# 형식 · 분위기 → 무료 곡 검색어 · 목표 박자
MOOD = {
    "emotional": ("emotional piano ambient", 78), "ad": ("upbeat corporate positive", 116), "ranking": ("funny upbeat energetic", 124),
    "clip": ("funny upbeat", 120), "daily": ("light background news", 100), "compare": ("upbeat electronic tech", 112),
}
DEFAULT_MOOD = ("chill lofi beat", 92)


def _settings() -> dict:
    p = ROOT / "data" / "workspace" / "settings.json"
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def music_on(sb: dict) -> bool:
    """이 영상에 배경 음악이 들어가나(효과음 규칙이 이걸 본다)"""
    m = sb.get("music") or {}
    if m.get("use") is False:
        return False
    return bool(m.get("src")) or m.get("use") is True


def sfx_allowed(sb: dict, ev) -> bool:
    """음악이 깔리면 효과음은 빼는 게 기본 — 콘티가 그 소리에 keep: true(꼭 필요한 사건 소리)를 달았거나 direction.sfx_with_music 일 때만"""
    if "sfx" in ((sb.get("intent") or {}).get("ban") or []):                    # 콘티 intent.ban — 효과음 금지
        return False
    if not music_on(sb) or (sb.get("direction") or {}).get("sfx_with_music"):
        return True
    return isinstance(ev, dict) and bool(ev.get("keep"))


# ---------- 레퍼런스 ----------
def ref_sound(rid: str) -> str | None:
    """레퍼런스 쇼츠가 붙인 곡(쇼츠 화면의 사운드 표시) — 한 번 읽고 xray 폴더에 남긴다"""
    f = XRAY / rid / "sound.json"
    if f.exists():
        return json.loads(f.read_text("utf-8")).get("sound")
    import trend_music
    s = trend_music.sound_of(rid)
    if (XRAY / rid).exists():
        f.write_text(json.dumps({"sound": s}, ensure_ascii=False), "utf-8")
    return s


def ref_info(sb: dict) -> dict:
    out = {"music_ratio": None, "bpm": None, "song": None, "speech_ratio": None, "id": None}
    for rid in sb.get("reference") or []:
        xp = XRAY / str(rid) / "xray.json"
        if not xp.exists():
            continue
        x = json.loads(xp.read_text("utf-8"))
        snd = x.get("sound") or {}
        mus = snd.get("music") or []
        out.update(id=str(rid), music_ratio=round(sum(mus) / len(mus), 2) if mus else None, bpm=snd.get("bpm"))
        st = XRAY / str(rid) / "style" / "style.json"
        if st.exists():
            out["speech_ratio"] = (json.loads(st.read_text("utf-8")).get("voice") or {}).get("speech_ratio")
        try:
            s = ref_sound(str(rid))
        except Exception:  # noqa: BLE001  사운드 표시는 덤 — 못 읽어도 판단은 한다
            s = None
        out["song"] = s if s and not ORIGINAL.search(s) else None
        break
    return out


def fmt_of(sb: dict) -> str:
    return str(sb.get("format") or sb.get("type") or "").replace("format-", "").lower()


def decide(sb: dict) -> tuple[bool, str, dict]:
    m = sb.get("music") or {}
    ref = ref_info(sb)
    if m.get("src") and (ROOT / m["src"]).exists() and m.get("source") != "auto":
        return True, "콘티에 곡이 정해져 있음", ref
    if isinstance(m.get("use"), bool) and m.get("source") != "auto":
        return m["use"], m.get("why") or "콘티에 정해져 있음", ref
    nar = sum(len((sc.get("narration") or "").strip()) for sc in sb.get("scenes") or [])
    f = fmt_of(sb)
    if ref["id"]:
        if ref["song"]:
            return True, f"레퍼런스가 곡을 붙임('{ref['song'][:40]}')", ref
        r = ref["music_ratio"]
        if r is not None and r >= 0.4:
            return True, f"레퍼런스에 음악이 {int(r * 100)}% 깔림" + (f" · {ref['bpm']:.0f} BPM" if ref["bpm"] else ""), ref
        if r is not None and r < 0.15:
            return False, f"레퍼런스는 음악 없이 말 · 원음으로 끌고 감(음악 {int(r * 100)}%)", ref
    if f == "clip":
        return False, "퍼온 클립 원음이 주인공", ref
    if not nar:
        return True, "나레이션이 없어 음악이 리듬을 끈다", ref
    if f in ("emotional", "ranking", "ad", "daily"):
        return True, f"{f} 형식은 음악 주도", ref
    return True, "설명형 — 말 뒤에 작게 깐다(말할 때 더 내림)", ref


# ---------- 후보 찾기 ----------
def _yt_key() -> str:
    try:
        import apikeys
        return apikeys.get("YOUTUBE_API_KEY")
    except Exception:  # noqa: BLE001
        return ""


def _api(path: str, **q) -> dict:
    q["key"] = _yt_key()
    url = f"https://www.googleapis.com/youtube/v3/{path}?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _iso_sec(d: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return sum(int(v or 0) * k for v, k in zip(m.groups(), (3600, 60, 1))) if m else 0


def _api_rows(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    d = _api("videos", part="snippet,contentDetails,statistics", id=",".join(ids[:50]))
    return [{"id": v["id"], "title": v["snippet"]["title"], "by": v["snippet"].get("channelTitle", ""), "sec": _iso_sec(v["contentDetails"].get("duration")),
             "views": int((v.get("statistics") or {}).get("viewCount") or 0), "published": v["snippet"].get("publishedAt", "")[:10]} for v in d.get("items") or []]


def search(q: str, n: int = 8, recent: bool = False) -> list[dict]:
    """유튜브 영상 검색 — Data API 키가 있으면 API(최근 1년 · 조회수 순), 없으면 웹(yt-dlp 검색)"""
    if _yt_key():
        try:
            p = {"part": "snippet", "type": "video", "q": q, "maxResults": n, "order": "viewCount" if recent else "relevance"}
            if recent:
                p["publishedAfter"] = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(time.time() - 365 * 86400))
            return _api_rows([it["id"]["videoId"] for it in _api("search", **p).get("items") or []])
        except Exception as e:  # noqa: BLE001
            print(f"[음악] Data API 실패 → 웹 검색: {str(e)[:80]}", file=sys.stderr)
    from platform_util import venv_tool
    r = subprocess.run([venv_tool("yt-dlp"), "--flat-playlist", "--no-warnings", "--print", "%(id)s\t%(title)s\t%(duration)s\t%(channel)s\t%(view_count)s",
                        f"ytsearch{n}:{q}"], capture_output=True, text=True, timeout=90)
    out = []
    for ln in r.stdout.splitlines():
        p = ln.split("\t")
        if len(p) == 5:
            out.append({"id": p[0], "title": p[1], "sec": int(float(p[2])) if p[2] not in ("NA", "None", "") else 0, "by": p[3],
                        "views": int(p[4]) if p[4].isdigit() else 0})
    return out


def chart(n: int = 20) -> list[dict]:
    """지금 한국 유튜브 음악 인기 차트(Data API 키가 있을 때만) — 상업 곡이 대부분이라 '업로드 때 붙일 곡' 후보"""
    if not _yt_key():
        return []
    try:
        d = _api("videos", part="snippet,contentDetails,statistics", chart="mostPopular", videoCategoryId="10", regionCode="KR", maxResults=n)
        return [{"id": v["id"], "title": v["snippet"]["title"], "by": v["snippet"].get("channelTitle", ""), "sec": _iso_sec(v["contentDetails"].get("duration")),
                 "views": int((v.get("statistics") or {}).get("viewCount") or 0)} for v in d.get("items") or []]
    except Exception:  # noqa: BLE001
        return []


# '무료'라고 적었어도 남의 곡을 고친 것(리믹스 · 커버 · 게임 · 애니 곡 · 느리게 · 나이트코어)과 긴 모음은 믿지 않는다
# (2026-11-09: 'Free Music No Copyright' 라던 Undertale 로파이 모음이 골라졌다)
NOT_FREE_RE = re.compile(r"remix|cover|mega ?mix|\bmix\b|medley|\bost\b|soundtrack|undertale|minecraft|pokemon|zelda|anime|nightcore|slowed|reverb|sped ?up|bootleg|"
                         r"mashup|tribute|리믹스|커버|메들리|【", re.I)


def trusted(v: dict) -> bool:
    return bool(FREE_CHANNELS.match((v.get("by") or "").strip()))


def is_free(v: dict) -> bool:
    title = v.get("title") or ""
    if v.get("sec") and v["sec"] > 600:                    # 10분 넘는 모음은 곡 하나가 아니다
        return False
    if trusted(v):
        return True
    return bool(FREE_RE.search(title)) and not NOT_FREE_RE.search(title)


def _core(title: str) -> str:
    """'Good For You – THBD (No Copyright Music)' → 'good for you' — 같은 곡인지 견줄 때"""
    t = re.sub(r"[\(\[].*?[\)\]]", " ", title.lower())
    t = re.split(r"\s[–\-|·]\s", t)[0]
    return re.sub(r"[^0-9a-z가-힣 ]+", " ", t).strip()


def free_version(song: str) -> dict | None:
    """상업 · 라이브러리 여부를 모르는 곡 이름 → 같은 제목의 무료 라이브러리 판"""
    core = _core(song)
    if len(core) < 3:
        return None
    for v in search(f"{core} no copyright music", 6):
        if is_free(v) and (core in _core(v["title"]) or _core(v["title"]) in core):
            return v
    return None


def trending_sounds(sb: dict, n: int = 8) -> list[dict]:
    """비슷한 쇼츠들이 지금 붙이는 곡 — 최근(2주) 모아 둔 것이 있으면 그것, 없으면 주제로 짧게 훑는다"""
    md = ROOT / "data" / "public" / "trends" / "music"
    rows = []
    for f in sorted(md.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if md.exists() else []:
        if time.time() - f.stat().st_mtime < 14 * 86400:
            rows += json.loads(f.read_text("utf-8")).get("songs") or []
    if rows:
        return sorted(rows, key=lambda s: -s.get("views", 0))[:n]
    q = (sb.get("topic") or sb.get("title") or "").strip()
    if not q:
        return []
    import trend_music
    songs: dict[str, dict] = {}
    for v in trend_music.search(f"{q} #shorts", n)[:n]:
        s = trend_music.sound_of(v["id"])
        if s and not ORIGINAL.search(s):
            g = songs.setdefault(s, {"sound": s, "shorts": 0, "views": 0})
            g["shorts"] += 1; g["views"] += v.get("views") or 0
        time.sleep(0.5)
    return sorted(songs.values(), key=lambda s: -s["views"])


# ---------- 받기 · 재기 ----------
def fetch(vid: str) -> Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{vid}.m4a"
    if out.exists():
        return out
    from platform_util import venv_tool
    r = subprocess.run([venv_tool("yt-dlp"), "-q", "--no-warnings", "-f", "bestaudio", "-x", "--audio-format", "m4a", "--download-sections", "*0-150",
                        "-o", str(CACHE / f"{vid}.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=180)
    return out if out.exists() and r.returncode == 0 else None


def measure(f: Path, need: float) -> dict:
    """박자 · 가장 힘 있는 구간의 시작(박에 맞춤)"""
    import numpy as np
    from shorts_xray import load_audio, stft_mag, tempo_beats
    sr, hop = 22050, 512
    st = load_audio(f, sr)
    mono = st.mean(axis=1) if len(st) else np.zeros(1)
    S = stft_mag(mono, 2048, hop)
    fr = sr / hop
    logS = np.log1p(S * 10)
    flux = np.concatenate([[0], np.maximum(0, np.diff(logS, axis=0)).sum(axis=1)])
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    bpm, conf, beats = tempo_beats(np.clip(flux, 0, None), fr)
    total = len(mono) / sr
    rms = np.sqrt((S ** 2).mean(axis=1) + 1e-12)
    start = 0.0
    if total > need + 4:
        win = int(need * fr)
        c = np.concatenate([[0], np.cumsum(rms)])
        means = (c[win:] - c[:-win]) / win
        lo = int(2 * fr)                                   # 맨 앞 2초(조용한 도입)는 건너뛴다
        k = lo + int(np.argmax(means[lo:])) if len(means) > lo else 0
        start = k / fr
        if beats:
            start = min(beats, key=lambda b: abs(b - start))   # 박에서 시작해야 첫 컷이 박에 붙는다
    return {"bpm": bpm, "beat_conf": conf, "sec": round(total, 1), "start": round(max(0.0, start), 2)}


def bpm_fit(b: float | None, target: float) -> float:
    if not b:
        return 0.5
    d = min(abs(b - target), abs(b * 2 - target), abs(b / 2 - target)) / target
    return max(0.0, 1 - d * 4)


# ---------- 고르기 ----------
def pick(sb: dict, ref: dict, mood: str | None, bpm: float | None) -> dict:
    f = fmt_of(sb)
    feel = ((sb.get("direction") or {}).get("feel") or {}).get("mood_en") or ""
    words, base_bpm = MOOD.get(f, DEFAULT_MOOD)
    target = float(bpm or ref.get("bpm") or base_bpm)
    q = (mood or (sb.get("music") or {}).get("mood") or f"{feel} {words}").strip()
    need = sum(float(sc.get("sec") or 0) for sc in sb.get("scenes") or []) or 30.0
    any_license = bool(_settings().get("music_any_license") or (sb.get("music") or {}).get("allow_any"))
    cands, upload = [], []

    def add(v: dict | None, why: str, bonus: float):
        if v and v["id"] not in {c["id"] for c in cands} and (not v.get("sec") or v["sec"] >= min(need, 25)):
            cands.append({**v, "free": is_free(v), "why": why, "bonus": bonus})

    if ref.get("song"):                                   # ① 레퍼런스가 붙인 곡
        fv = free_version(ref["song"])
        if fv:
            add(fv, f"레퍼런스가 붙인 곡('{ref['song'][:30]}')의 무료 판", 3.0)
        else:
            upload.append(ref["song"])
            if any_license:
                add(next(iter(search(ref["song"], 3)), None), f"레퍼런스가 붙인 곡('{ref['song'][:30]}')", 3.0)
    for s in trending_sounds(sb)[:5]:                     # ② 비슷한 쇼츠들이 지금 붙이는 곡
        fv = free_version(s["sound"])
        if fv:
            add(fv, f"요즘 비슷한 쇼츠 {s.get('shorts', 1)}편이 붙인 곡", 2.0)
        else:
            upload.append(s["sound"])
            if any_license:
                add(next(iter(search(s["sound"], 3)), None), f"요즘 비슷한 쇼츠 {s.get('shorts', 1)}편이 붙인 곡", 2.0)
    for v in chart(15)[:5]:                                # ③ 음악 인기 차트(키가 있을 때) — 상업 곡은 업로드 때 붙일 곡으로
        if is_free(v) or any_license:
            add(v, "유튜브 음악 인기 차트(KR)", 1.5)
        else:
            upload.append(f"{v['title']}")
    for v in search(f"{q} no copyright music", 10, recent=True):   # ④ 분위기에 맞는 요즘 인기 무료 곡
        if is_free(v):
            add(v, f"'{q}' 분위기 · 최근 인기 무료 곡", 0.0)
    if not cands:
        for v in search(f"{words} no copyright music audio library", 10):
            if is_free(v):
                add(v, f"'{words}' 분위기 무료 곡", 0.0)
    for c in cands:
        c["pre"] = c["bonus"] + 0.3 * math.log10(max(10, c.get("views") or 10)) + (1.0 if trusted(c) else 0.0)   # 믿을 만한 무료 곡 채널 먼저
    cands.sort(key=lambda c: -c["pre"])
    best = None
    for c in cands[:4]:                                   # 상위 몇 곡만 받아서 잰다(곡당 몇 초)
        p = fetch(c["id"])
        if not p:
            continue
        mm = measure(p, need)
        if mm["sec"] < min(need, 20):
            continue
        c.update(mm, src=str(p.relative_to(ROOT)), score=round(c["pre"] + 3 * bpm_fit(mm["bpm"], target), 2))
        if not best or c["score"] > best["score"]:
            best = c
    seen, up = set(), []
    for u in upload:
        if u.lower() not in seen:
            seen.add(u.lower()); up.append(u)
    if not best:
        return {"use": False, "why": "맞는 무료 곡을 받지 못함", "upload_sound": up[:5], "source": "auto"}
    return {"use": True, "src": best["src"], "title": best["title"], "by": best.get("by"), "url": f"https://www.youtube.com/watch?v={best['id']}",
            "free": best["free"], "license": "무료 라이브러리 곡(설명란에 곡 · 만든 이 표기)" if best["free"] else "상업 곡 — 권리 확인 필요(Content ID)",
            "bpm": best.get("bpm"), "target_bpm": target, "start": best.get("start", 0.0), "why": best["why"],
            "upload_sound": up[:5], "source": "auto", "mood": q}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["decide", "pick", "auto"]); ap.add_argument("storyboard")
    ap.add_argument("--mood"); ap.add_argument("--bpm", type=float)
    a = ap.parse_args()
    sp = Path(a.storyboard); sp = sp if sp.is_absolute() else ROOT / sp
    sb = json.loads(sp.read_text("utf-8"))
    use, why, ref = decide(sb)
    old = sb.get("music") or {}
    print(f"[음악] {'넣음' if use else '안 넣음'} — {why}")
    if a.cmd == "decide":
        return 0
    if old.get("src") and old.get("source") != "auto" and a.cmd == "auto":
        return 0                                          # 사용자가 준 곡은 건드리지 않는다
    if not use:
        sb["music"] = {**{k: v for k, v in old.items() if k in ("allow_any",)}, "use": False, "why": why, "source": "auto"}
    else:
        if a.cmd == "auto" and old.get("source") == "auto" and old.get("src") and (ROOT / old["src"]).exists():
            print(f"[음악] 이미 고름: {old.get('title')}"); return 0
        m = pick(sb, ref, a.mood, a.bpm)
        m["decide"] = why
        if not m.get("free") and m.get("use"):
            print("[음악] 주의: 상업 곡을 직접 넣었습니다(설정 music_any_license) — Content ID 로 수익 · 소리가 막힐 수 있음")
        sb["music"] = {**{k: v for k, v in old.items() if k in ("gain_db", "duck_db", "allow_any")}, **m}
        if m.get("use"):
            print(f"[음악] {m['title']} — {m.get('by')} · {m.get('bpm') or '?'} BPM(목표 {m['target_bpm']:.0f}) · {m['start']}초부터 · {m['why']}")
        if m.get("upload_sound"):
            print("[음악] 업로드 때 쇼츠 편집기 '사운드 추가'로 붙일 수 있는 유행곡: " + " / ".join(m["upload_sound"][:3]))
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
