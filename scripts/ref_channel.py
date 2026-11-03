#!/usr/bin/env python3
"""채널 카드(범용) — 레퍼런스 쇼츠 한 편이 아니라 '그 채널'의 구성 · 화면 · 리듬 · 말투 · 목소리를 여러 편에서 뽑는다.
형식을 가정하지 않는다: 화면 종류는 CLIP 제로샷(vision_tags.py), 말이 없으면 컷 · 음악 박자로 뼈대를 만들고, 말투 · 농담은 한국어일 때만.

  python3 scripts/ref_channel.py <레퍼런스 쇼츠 id 또는 URL> [--n 6] [--whisper base]
  python3 scripts/ref_channel.py note <채널 id> --jokes <json 파일>     # 에이전트가 대사 시트를 보고 고른 농담 줄을 카드에 적는다

하는 일(영상마다)
  1) 같은 채널의 최근 쇼츠 n 편을 받는다(레퍼런스 자신은 분해도 결과를 다시 쓴다)
  2) 목소리만 떼어(separate.py) 받아 적는다(faster-whisper small · 탐색 폭 5). 제목과 화면 글자(2초마다 ocr.py)를
     앞 문장으로 넣어 고유 낱말(확장 프로그램 · 개발자 모드 · Tenor …)을 덜 틀리게 하고 문장부호도 찍게 한다
  3) 문장마다 역할(소식 · 설명 · 방법 안내 · 반전 · 농담 후보 · 맺음) · 그때 화면 종류(실제 화면 · 기사 · 짤 · 사진) · 컷 수
  4) 문장 끝 · 이음말 · 첫 문장 · 끝 문장 · 목소리 특징(voice_profile.py)
채널 전체: 문장 끝 비율(문장 수 기준) · 이음말 · 말 속도 · 이어 말하기 · 목소리 특징 중앙값 · 농담 비율
결과: public/trends/channels/<채널 id>/channel.json · channel.md · lines-<영상>.jpg(대사마다 그 순간 화면, 번호는 channel.md 와 같다)
레퍼런스의 스타일 카드(style.json)에 channel 칸을 달아, direct.py · voice_match.py · lint.py 가 채널 카드를 따른다.
원본 대사는 말투 예시로만 쓴다 — 콘티는 사용자의 주제로 새로 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
XR = ROOT / "public" / "trends" / "xray"
CH = ROOT / "public" / "trends" / "channels"

ENDINGS = ["더라고요", "거든요", "잖아요", "습니다", "입니다", "합니다", "됩니다", "는데요", "는데", "고요", "대요", "네요", "어요", "아요",
           "예요", "에요", "세요", "까요", "죠", "요", "다"]
LINKS = ["근데", "그래서", "그리고", "아무튼", "심지어", "그러니까", "일단", "이제", "그냥", "진짜", "약간", "막", "되게", "사실", "참고로", "여러분들", "여러분"]
# 농담 후보(자동): 화면 · 앞말을 살짝 비트는 말 · 시청자에게 던지는 말 · 끝 한마디. 확정은 에이전트가 대사 시트를 보고 note 로 한다
JOKE_PAT = re.compile(r"아니고요|아닙니다|아니라|그렇다고|농담|ㅋ|할 수도 있|되는 거예요|되겠습니다|마세요|하시고요|하시면|인생|망|큰일|굳이|사실상|좋겠네요|바쁘")


def say(p, stage):
    print(f"@progress {p:.2f} {stage}", flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def vid_of(s: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    v = m.group(1) if m else s
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
        sys.exit(f"영상 id 가 올바르지 않습니다: {s}")
    return v


def channel_of(vid: str) -> dict:
    r = run(["yt-dlp", "-J", "--no-playlist", "--skip-download", "--no-warnings", f"https://www.youtube.com/shorts/{vid}"], timeout=120)
    if r.returncode != 0:
        sys.exit(f"영상 정보를 받지 못했습니다: {r.stderr.strip()[-300:]}")
    j = json.loads(r.stdout)
    return {"id": j.get("channel_id"), "title": j.get("channel") or j.get("uploader"), "url": j.get("channel_url"), "ref_title": j.get("title")}


def channel_shorts(cid: str, limit: int) -> list[dict]:
    r = run(["yt-dlp", "--flat-playlist", "-J", "--no-warnings", "--playlist-end", str(limit), f"https://www.youtube.com/channel/{cid}/shorts"], timeout=180)
    if r.returncode != 0:
        return []
    return [{"id": e["id"], "title": e.get("title") or ""} for e in (json.loads(r.stdout).get("entries") or []) if e.get("id")]


def norm(s: str) -> str:
    return re.sub(r"[^\w가-힣]", "", s).lower()


# 기사 표지: 기자 이름 · 입력 시각 · 언론사 · 날짜(영어 일반 낱말 press · news 는 앱 화면에도 흔해 넣지 않는다)
NEWS = re.compile(r"기자\b|[가-힣]{2,4} 기자|입력\s?20\d\d|승인\s?20\d\d|뉴스|일보|신문|특파원|보도|Reuters|Bloomberg|Forbes|CoinDesk|The Verge|TechCrunch|20\d\d[.-]\s?\d{1,2}[.-]\s?\d{1,2}")


def screen_kind(frame, lines: list[dict]) -> str:
    """한 프레임의 화면 종류(범용) — vision_tags.py(CLIP 제로샷) + OCR 기사 표지"""
    import vision_tags
    return vision_tags.classify(str(frame), lines)["kind"]


def screen_scan(src: Path, dur: float, langs, step: float = 1.0) -> tuple[list[str], list[tuple[float, str]], list[dict]]:
    """1초마다 화면을 읽어 → (화면 낱말 자주 나온 순 — 받아쓰기 힌트, [(시각, 화면 종류)], 프레임별 글줄 · 띠)
    이 채널은 나레이션 자막이 없을 수도 있어 화면 글자를 '정답 자막'으로 쓰지 않는다 — 자막인지는 layout_metrics 가 말과 견줘 가린다"""
    import ocr
    from ref_style import band_of
    cnt: dict[str, int] = {}
    kinds, frames = [], []
    with tempfile.TemporaryDirectory() as tmp:
        t = 0.5
        while t < dur:
            f = Path(tmp) / f"c{int(t * 10):04d}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(f)])
            if f.exists():
                lines = ocr.read(str(f), langs, min_score=0.8)
                kinds.append((t, screen_kind(f, lines)))
                from PIL import Image as _I
                top, bot, bgc = band_of(np.array(_I.open(f).convert("RGB")))
                frames.append({"t": t, "lines": [{k: o[k] for k in ("text", "box", "bg", "fg")} for o in lines], "band": [top, bot, bgc]})
                for o in lines:
                    for tok in o["text"].split():
                        if 2 <= len(norm(tok)) <= 20 and not re.match(r"^[@#\d]|\d+(분|초|시간)전", tok):
                            cnt[tok] = cnt.get(tok, 0) + 1
            t += step
    return [w for w, _ in sorted(cnt.items(), key=lambda x: -x[1])], kinds, frames


def _lum(h: str) -> float:
    return sum(int(h[i:i + 2], 16) for i in (1, 3, 5)) / 3


def layout_metrics(frames: list[dict], segs: list[dict]) -> dict:
    """사람이 편집한 화면의 배치 수치 — 자막(말과 겹치는 글줄) · 고정 제목(같은 자리에 오래 남는 글) · 화면 채움.
    위치 · 크기는 화면 높이 기준 0~1. 자막이 없으면 captions.share 가 0 에 가깝다"""
    words = [(w["s"], w["e"], norm(w["w"])) for sg in segs for w in sg.get("words") or [] if norm(w["w"])]
    cap, by_text = [], {}
    for fr in frames:
        t = fr["t"]
        spoken = "".join(w for s0, e0, w in words if s0 - 1.0 <= t <= e0 + 1.0)
        here = []
        for o in fr["lines"]:
            n = norm(o["text"])
            if len(n) < 2:
                continue
            key = (n[:12], round(o["box"][1], 2))
            by_text[key] = by_text.get(key, 0) + 1
            # 자막: 글줄의 2글자 조각 중 절반 이상이 지금 말하는 말에 들어 있다
            grams = [n[i:i + 2] for i in range(len(n) - 1)]
            if spoken and grams and sum(1 for g in grams if g in spoken) / len(grams) >= 0.5:
                here.append(o)
        if here:
            cap.append(here)
    n = max(1, len(frames))
    capf = [o for fr in cap for o in fr]
    med = lambda xs: round(float(np.median(xs)), 3) if xs else None
    captions = {"share": round(len(cap) / n, 2)}
    if capf:
        light = lambda h: _lum(h) > 150
        boxed = sum(1 for o in capf if abs(_lum(o["bg"]) - _lum(o["fg"])) > 120 and o["bg"] not in ("#000000",)) / len(capf)
        captions.update({"y": med([o["box"][1] + o["box"][3] / 2 for o in capf]), "height": med([o["box"][3] for o in capf]),
                         "chars": int(np.median([len(o["text"].replace(" ", "")) for o in capf])), "lines": int(np.median([len(fr) for fr in cap])),
                         "width": med([o["box"][2] for o in capf]), "fg_light": round(sum(1 for o in capf if light(o["fg"])) / len(capf), 2),
                         "box": round(boxed, 2), "fg": max(set(o["fg"] for o in capf), key=[o["fg"] for o in capf].count)})
    # 고정 제목: 말과 상관없이 프레임의 40% 이상에 같은 자리 · 같은 글로 남는 글줄(자막 제외)
    titles = [(k, c) for k, c in by_text.items() if c >= max(3, 0.4 * n)]
    title = {"present": bool(titles)}
    if titles:
        ys = [k[1] for k, _ in titles]
        hs = [o["box"][3] for fr in frames for o in fr["lines"] if (norm(o["text"])[:12], round(o["box"][1], 2)) in dict(titles)]
        title.update({"y": med(ys), "height": med(hs)})
    tops = [fr["band"][0] for fr in frames if fr["band"][1] - fr["band"][0] < 0.95]
    bots = [fr["band"][1] for fr in frames if fr["band"][1] - fr["band"][0] < 0.95]
    fill = {"letterbox": round(len(tops) / n, 2), "band_top": med(tops), "band_bottom": med(bots)}
    return {"captions": captions, "title": title, "fill": fill}


def is_korean(text: str) -> bool:
    h = len(re.findall(r"[가-힣]", text)); a = len(re.findall(r"[A-Za-z]", text))
    return h >= a


def role_of(i: int, n: int, text: str, ko: bool = True) -> str:
    """문장 역할(자동 추정 — 에이전트가 대사 시트를 보고 note 로 고칠 수 있다). 한국어가 아니면 자리 · 물음표만 본다"""
    if i == 0:
        return "소식 · 훅"
    if i == n - 1:
        return "맺음"
    if not ko:
        return "질문" if text.rstrip().endswith("?") else "설명 · 사실"
    if JOKE_PAT.search(text):
        return "농담 후보"
    if re.match(r"(근데|하지만|다만|그런데)", text):
        return "반전 · 한계"
    if re.search(r"(시고요|하시면|세요|되겠습니다|보시고)", text):
        return "방법 안내(시청자에게)"
    return "설명 · 사실"


def hint_prompt(title: str, words: list[str]) -> str:
    """받아쓰기 앞 문장: 제목 + 화면 낱말 + 문장부호가 있는 구어 예시(마침표가 찍히게)"""
    import shorts_xray as sx
    w = ", ".join(words[:25])
    return (f"{title}. " if title else "") + (f"화면: {w}. " if w else "") + sx.SPEECH_PROMPT


def sentences(segs: list[dict]) -> list[dict]:
    """받아쓰기 구간을 문장으로: 마침표 · 물음표에서, 없으면 구간 끝에서 끊는다"""
    out, cur, t0 = [], [], None
    for s in segs:
        for w in s["words"]:
            t0 = w["s"] if t0 is None else t0
            cur.append(w["w"])
            if re.search(r"[.?!]$", w["w"]):
                out.append({"t": round(t0, 2), "end": round(w["e"], 2), "text": " ".join(cur)}); cur, t0 = [], None
        if cur and s is segs[-1]:
            out.append({"t": round(t0, 2), "end": round(s["end"], 2), "text": " ".join(cur)}); cur, t0 = [], None
    return out


def ending_of(sent: str) -> str:
    last = re.sub(r"[.?!,…\s]+$", "", sent).split()[-1:] or [""]
    w = last[0]
    return next((e for e in ENDINGS if w.endswith(e)), w[-2:] if len(w) >= 2 else w)


def line_sheet(src: Path, sents: list[dict], dst: Path, offset: int):
    """대사마다 그 순간 화면(번호 = channel.md 의 줄 번호) — 화면을 비트는 농담인지 에이전트가 눈으로 확인"""
    if not sents:
        return
    ths = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, s in enumerate(sents):
            f = Path(tmp) / f"l{i:03d}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(s['t'] + s['end']) / 2:.2f}", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(f)])
            if not f.exists():
                continue
            im = Image.open(f).convert("RGB"); im.thumbnail((180, 320))
            dr = ImageDraw.Draw(im); dr.rectangle([0, 0, 40, 18], fill=(0, 0, 0)); dr.text((4, 3), f"#{offset + i}", fill=(255, 255, 0))
            ths.append(im)
    if not ths:
        return
    w, h = ths[0].size
    sh = Image.new("RGB", (w * min(8, len(ths)), h * ((len(ths) + 7) // 8)), (40, 40, 40))
    for i, im in enumerate(ths):
        sh.paste(im, ((i % 8) * w, (i // 8) * h))
    sh.save(dst, quality=85)


def analyze_video(vid: str, title: str, d: Path, whisper: str, langs) -> dict | None:
    import separate
    import shorts_xray as sx
    import voice_profile as vp
    xd = XR / vid
    d.mkdir(parents=True, exist_ok=True)
    if (xd / "src.mp4").exists() and (xd / "vocals.m4a").exists():          # 레퍼런스(이미 분해함) — 소리는 다시 쓰고 받아쓰기만 새로
        src, vocals = xd / "src.mp4", xd / "vocals.m4a"
    else:
        src = sx.download(vid, d)
        vocals = d / "vocals.m4a"
        if not vocals.exists():
            try:
                mix = separate.load(src); v = separate.vocals(mix); separate.save(v, vocals)
            except Exception as e:  # noqa: BLE001
                print(f"[음원 분리] {vid} 건너뜀: {e}", file=sys.stderr); vocals = src
    dur = float(sx.probe(src)["duration"])
    words, kinds, frames = screen_scan(src, dur, langs)
    cuts = sx.detect_cuts(src, dur)
    segs = sx.speech(vocals, whisper, lang_from=src, prompt=hint_prompt(title, words)) if whisper != "none" else []
    for sg in segs:
        sg["words"] = sg.get("words") or [{"w": t, "s": sg["start"], "e": sg["end"]} for t in sg["text"].split()]
    # 음악: 박자 · 컷이 박에 맞는 비율(말 없는 영상의 리듬)
    try:
        snd = sx.sound(src, dur, segs)
    except Exception:  # noqa: BLE001
        snd = {}
    beats = snd.get("beats") or []
    on_beat = round(sum(1 for c in cuts if beats and min(abs(c - b) for b in beats) <= 0.08) / len(cuts), 2) if cuts and beats else None
    # 컷마다 화면 종류(말이 없을 때의 뼈대)
    bounds = [0.0, *cuts, dur]
    shots = [{"t": round(a, 2), "sec": round(b - a, 2), "screen": min(kinds, key=lambda k: abs(k[0] - (a + b) / 2))[1] if kinds else None} for a, b in zip(bounds, bounds[1:])]
    sents = sentences(segs) if segs else []
    talk = sum(s["end"] - s["start"] for s in segs)
    ko = is_korean(" ".join(s["text"] for s in segs)) if segs else True
    gaps = [b["start"] - a["end"] for a, b in zip(segs, segs[1:])]
    pr = vp.profile(vocals if vocals.exists() else src, [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segs]) if segs else {}
    return {"id": vid, "title": title, "duration": round(dur, 1), "src": src, "hints": words[:25], "lang": "ko" if ko else "other",
            "speech_ratio": round(talk / dur, 2) if dur else 0, "bpm": snd.get("bpm"), "cut_on_beat": on_beat, "shots": shots,
            "layout": layout_metrics(frames, segs),
            "cps": round(sum(len(re.sub(r"\s", "", s["text"])) for s in segs) / talk, 2) if talk > 1 else 0,
            "median_gap": round(float(np.median(gaps)), 2) if gaps else 0.0, "prosody": pr,
            "cuts": len(cuts),
            "sentences": [{**s, "ending": ending_of(s["text"]) if ko else None, "joke_candidate": bool(ko and JOKE_PAT.search(s["text"])),
                           "role": role_of(i, len(sents), s["text"], ko),
                           "screen": min(kinds, key=lambda k: abs(k[0] - (s["t"] + s["end"]) / 2))[1] if kinds else None,
                           "cuts_in": sum(1 for c in cuts if s["t"] < c < s["end"])} for i, s in enumerate(sents)]}


def render_md(card: dict) -> str:
    v, t, st = card["voice"], card["tone"], card["structure"]
    talky = st.get("lead") != "음악 · 화면"
    ko = card.get("lang", "ko") == "ko"
    md = [f"# 채널 카드 — {card['title']}", f"{card.get('url') or ''} · 쇼츠 {len(card['videos'])}편 · 문장 {len([s for vd in card['videos'] for s in vd['sentences']])}개", "",
          f"**형식**: {st.get('lead', '말')} 주도 · " + " + ".join(list(st["screens"])[:2]) + f" 위주 · 컷 중앙값 {st.get('shot_sec')}초"
          + (f" · 음악 {st['bpm']} BPM · 컷이 박에 맞음 {int((st.get('cut_on_beat') or 0) * 100)}%" if st.get("bpm") else ""), "",
          "## 옮기는 법",
          "- 내용은 **사용자의 주제**로 새로 쓴다. 아래 대사 · 화면은 형식 · 박자 예시일 뿐 그대로 쓰지 않는다.",
          "- 장면 순서 · 화면 종류는 아래 뼈대처럼, 컷 길이 · 음악 박자도 이 채널 값에 맞춘다."]
    if talky and ko:
        md += ["- 문장 끝은 **아래 비율대로 섞는다**(한 가지로 몰지 않는다). 이음말도 비슷한 빈도로.",
               "- 농담은 이 채널 방식대로: 확정 농담 줄(아래)처럼. 콘티에서 그 장면은 beat 를 \"joke\" 로.",
               f"- 농담 빈도: 10초에 약 {card['joke_rate_per_10s']}번 ({'확정' if card.get('jokes') else '자동 후보 기준 — 대사 시트를 보고 note 로 확정'})"]
    elif not talky:
        md += ["- 말이 거의 없는 채널이다 — 나레이션 없이(또는 아주 짧게) 음악 · 화면 · 자막으로 끌고 간다. 화면 전환을 음악 박에 맞춘다."]
    md += ["", "## 구성 · 구조 (내 영상의 장면 순서 · 화면을 이렇게)",
           "- 화면에 나온 것(시간 비율): " + ", ".join(f"{k} {int(p * 100)}%" for k, p in st["screens"].items()),
           f"- 말 비율 {int(st.get('speech_ratio', 0) * 100)}% · 컷 길이 중앙값 {st.get('shot_sec')}초"
           + (f" · 영상당 {st['sentences_per_video']}문장 · 문장 길이 {st['sentence_sec']}초 · 문장당 컷 {st['cuts_per_sentence']}번" if talky and st.get("sentence_sec") else ""),
           "- 영상별 뼈대" + ("(역할[화면]):" if talky else "(컷 순서의 화면 종류):"), *[f"  {i + 1}) {sk}" for i, sk in enumerate(st["skeletons"])],
           "- 화면은 이야기하는 **대상 자체**를 보여 준다. '기사' 비율이 낮으면 기사 캡처는 근거 한두 곳만.", ""]
    lay = card.get("layout") or {}
    if lay:
        c, ti, fi = lay.get("captions", {}), lay.get("title", {}), lay.get("fill", {})
        pct = lambda v: f"{int((v or 0) * 100)}%"
        md += ["## 배치 (화면 높이 기준 — 자막 · 제목 · 채움을 이 숫자로)",
               f"- 자막: 시간의 {pct(c.get('share'))}에 있음" + (f" · 위치 y {c['y']} · 글자 높이 {c.get('height')} · 한 줄 {c.get('chars')}자 · {c.get('lines')}줄 · 상자 {pct(c.get('box'))} · 밝은 글씨 {pct(c.get('fg_light'))}" if c.get("y") is not None else " — 나레이션 자막을 거의 안 씀"),
               f"- 고정 제목: 영상의 {pct(ti.get('share'))}" + (f" · y {ti['y']} · 높이 {ti.get('height')}" if ti.get("y") is not None else ""),
               f"- 화면 채움: 위아래 띠 {pct(fi.get('letterbox'))}" + (f" · 띠 {fi.get('band_top')}~{fi.get('band_bottom')}" if fi.get("band_top") is not None else " · 화면 가득"), ""]
    if talky:
        md += ["## 말", f"- 초당 {v['cps']}{'자' if ko else ' 글자'} · 구간 사이 쉼 {v['median_gap']}초 → {'이어 말함' if v['continuous'] else '끊어 말함'}",
               "- 목소리(여러 편 중앙값): " + (" · ".join(f"{k} {val}" for k, val in (v.get("prosody") or {}).items() if val is not None) or "-")]
        if ko:
            md += ["- 문장 끝(문장 수 비율): " + (", ".join(f"~{k} {int(p * 100)}%" for k, p in list(t["endings"].items())[:10]) or "-"),
                   "- 이음말(1분당): " + (", ".join(f"{k} {val}" for k, val in list(t["connectives_per_min"].items())[:10]) or "-")]
        md += ["", "## 첫 문장 예시", *[f"- {x}" for x in t["openings"]], "", "## 끝 문장 예시", *[f"- {x}" for x in t["closings"]], ""]
    if card.get("jokes"):
        md += ["## 확정 농담 줄(에이전트가 화면과 함께 보고 고름)", *[f"- {j.get('line')} — {j.get('why', '')}" for j in card["jokes"]], ""]
    md += ["## 영상별 대사 · 컷 (#번호 = lines-<영상>.jpg 의 번호 · ★ 농담 후보)"]
    for vd in card["videos"]:
        md += ["", f"### {vd['title'] or vd['id']} ({vd['id']} · {vd['duration']}초 · 말 {int(vd.get('speech_ratio', 0) * 100)}%"
               + (f" · {vd['bpm']} BPM" if vd.get("bpm") else "") + ")", f"대사 시트: {vd.get('sheet') or '-'}"]
        md += [f"{s['n']}. {'★ ' if s['joke_candidate'] else ''}{s['t']:.1f}초 · [{s.get('role')} · {s.get('screen')} · 컷 {s.get('cuts_in', 0)}] {s['text']}" for s in vd["sentences"]]
        if not vd["sentences"]:
            md += ["- 컷: " + " → ".join(f"{sh['screen']}({sh['sec']}초)" for sh in (vd.get("shots") or [])[:30])]
    return "\n".join(md) + "\n"


def aggregate(meta: dict, vids: list[dict], jokes: list | None) -> dict:
    sents = [s for v in vids for s in v["sentences"]]
    n = max(1, len(sents))
    ko_sents = [s for s in sents if s.get("ending")]
    ends = {}
    for s in ko_sents:
        ends[s["ending"]] = ends.get(s["ending"], 0) + 1
    total = sum(v["duration"] for v in vids) or 1
    total_min = total / 60
    joined = " ".join(s["text"] for s in ko_sents)
    links = {w: round(len(re.findall(rf"(?<![가-힣]){w}", joined)) / total_min, 1) for w in LINKS} if ko_sents else {}
    pros = [v["prosody"] for v in vids if (v.get("prosody") or {}).get("f0_median")]
    med = {k: round(float(np.median([p[k] for p in pros if p.get(k) is not None])), 2) for k in ("f0_median", "range_st", "end_drop_st", "end_fall", "energy_sd_db") if any(p.get(k) is not None for p in pros)}
    talky = [v for v in vids if v.get("speech_ratio", 1) >= 0.2]
    cps = round(float(np.median([v["cps"] for v in talky])), 2) if talky else 0
    if med:
        med["cps"] = cps
    gap = round(float(np.median([v["median_gap"] for v in talky])), 2) if talky else 0
    njoke = len(jokes) if jokes else sum(1 for s in sents if s["joke_candidate"])
    # 화면 종류 비율: 시간 기준(컷마다 길이) — 말이 없는 영상도 같은 잣대
    scr = {}
    for v in vids:
        for sh in v.get("shots") or []:
            if sh.get("screen"):
                scr[sh["screen"]] = scr.get(sh["screen"], 0) + sh["sec"]
    st = sum(scr.values()) or 1
    speech = round(float(np.median([v.get("speech_ratio", 0) for v in vids])), 2)
    lead = "말" if speech >= 0.5 else "음악 · 화면" if speech < 0.2 else "말 + 음악"
    shot_sec = [sh["sec"] for v in vids for sh in v.get("shots") or []]
    ob = [v["cut_on_beat"] for v in vids if v.get("cut_on_beat") is not None]
    def skeleton(v):
        if v["sentences"] and v.get("speech_ratio", 1) >= 0.2:
            return " → ".join(x["role"] + f"[{x.get('screen') or '?'}]" for x in v["sentences"])
        seq = []   # 말이 없으면 컷 순서의 화면 종류(같은 종류가 이어지면 묶음)
        for sh in v.get("shots") or []:
            if seq and seq[-1][0] == sh["screen"]:
                seq[-1][1] += sh["sec"]
            else:
                seq.append([sh["screen"], sh["sec"]])
        return " → ".join(f"{k}({s:.1f}초)" for k, s in seq)
    structure = {"screens": {k: round(c / st, 2) for k, c in sorted(scr.items(), key=lambda x: -x[1])},
                 "lead": lead, "speech_ratio": speech,
                 "shot_sec": round(float(np.median(shot_sec)), 2) if shot_sec else None,
                 "bpm": round(float(np.median([v["bpm"] for v in vids if v.get("bpm")])), 1) if any(v.get("bpm") for v in vids) else None,
                 "cut_on_beat": round(float(np.median(ob)), 2) if ob else None,
                 "sentences_per_video": round(len(sents) / max(1, len(vids)), 1),
                 "sentence_sec": round(float(np.median([x["end"] - x["t"] for x in sents])), 1) if sents else None,
                 "cuts_per_sentence": round(sum(x.get("cuts_in", 0) for x in sents) / n, 2) if sents else None,
                 "skeletons": [skeleton(v) for v in vids]}
    lang = "ko" if sum(1 for v in vids if v.get("lang") == "ko") >= len(vids) / 2 else "other"
    # 배치(사람이 편집한 화면의 수치): 영상들의 중앙값 — 형식 프리셋(presets/formats)의 재료
    L = [v.get("layout") or {} for v in vids]
    md = lambda xs: round(float(np.median(xs)), 3) if xs else None
    capv = [l["captions"] for l in L if (l.get("captions") or {}).get("share", 0) >= 0.2 and "y" in l["captions"]]
    layout = {"captions": {"share": md([(l.get("captions") or {}).get("share", 0) for l in L]),
                           **({k: md([c[k] for c in capv if c.get(k) is not None]) for k in ("y", "height", "width", "chars", "lines", "box", "fg_light")} if capv else {})},
              "title": {"share": round(sum(1 for l in L if (l.get("title") or {}).get("present")) / max(1, len(L)), 2),
                        "y": md([l["title"]["y"] for l in L if (l.get("title") or {}).get("y") is not None]),
                        "height": md([l["title"]["height"] for l in L if (l.get("title") or {}).get("height") is not None])},
              "fill": {"letterbox": md([(l.get("fill") or {}).get("letterbox", 0) for l in L]),
                       "band_top": md([l["fill"]["band_top"] for l in L if (l.get("fill") or {}).get("band_top") is not None]),
                       "band_bottom": md([l["fill"]["band_bottom"] for l in L if (l.get("fill") or {}).get("band_bottom") is not None])}}
    return {"channel": meta["id"], "title": meta["title"], "url": meta["url"], "ref": meta["ref"], "lang": lang, "structure": structure, "layout": layout,
            "voice": {"cps": cps, "median_gap": gap, "continuous": bool(talky) and gap < 0.35, "prosody": med},
            "tone": {"sentences": len(ko_sents), "endings": {k: round(c / max(1, len(ko_sents)), 2) for k, c in sorted(ends.items(), key=lambda x: -x[1])},
                     "connectives_per_min": {k: v for k, v in sorted(links.items(), key=lambda x: -x[1]) if v},
                     "openings": [v["sentences"][0]["text"] for v in vids if v["sentences"]],
                     "closings": [v["sentences"][-1]["text"] for v in vids if v["sentences"]]},
            "joke_rate_per_10s": round(njoke / total * 10, 2), "jokes": jokes or [],
            "videos": [{k: v[k] for k in ("id", "title", "duration", "lang", "speech_ratio", "bpm", "cut_on_beat", "cps", "median_gap", "hints", "cuts", "shots", "layout", "prosody", "sentences", "sheet") if k in v} for v in vids]}


def link_style_card(ref: str, cid: str):
    sp = XR / ref / "style" / "style.json"
    if sp.exists():
        c = json.loads(sp.read_text(encoding="utf-8")); c["channel"] = cid
        sp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_note(cid: str, jokes_file: str):
    cp = CH / cid / "channel.json"
    card = json.loads(cp.read_text(encoding="utf-8"))
    jokes = json.loads(Path(jokes_file).read_text(encoding="utf-8"))
    if not isinstance(jokes, list) or not all(isinstance(j, dict) and j.get("line") for j in jokes):
        sys.exit('농담 목록 형식: [{"video": "<id>", "n": 12, "line": "그 컨테이너 아니고요", "why": "컨테이너선 사진을 말로 비틂"}]')
    card["jokes"] = jokes
    total = sum(v["duration"] for v in card["videos"]) or 1
    card["joke_rate_per_10s"] = round(len(jokes) / total * 10, 2)
    cp.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    (CH / cid / "channel.md").write_text(render_md(card), encoding="utf-8")
    print(json.dumps({"ok": True, "jokes": len(jokes), "joke_rate_per_10s": card["joke_rate_per_10s"]}, ensure_ascii=False))


def main():
    if sys.argv[1:2] == ["note"]:
        ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("channel"); ap.add_argument("--jokes", required=True)
        a = ap.parse_args(); return cmd_note(a.channel, a.jokes)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=6, help="레퍼런스 말고 더 볼 쇼츠 수")
    ap.add_argument("--whisper", default="small")
    ap.add_argument("--langs", default="korean,en")
    ap.add_argument("--keep-video", action="store_true", help="받은 영상을 지우지 않는다(기본: 대사 시트를 만든 뒤 지움)")
    a = ap.parse_args()
    ref = vid_of(a.video)
    say(0.02, "채널 찾는 중")
    meta = channel_of(ref)
    if not meta["id"]:
        sys.exit("채널을 찾지 못했습니다")
    meta["ref"] = ref
    out = CH / meta["id"]; out.mkdir(parents=True, exist_ok=True)
    listed = [e for e in channel_shorts(meta["id"], a.n + 6) if e["id"] != ref][: a.n]
    todo = [{"id": ref, "title": meta.get("ref_title") or ""}] + listed
    langs = a.langs.split(",")
    vids, line_no = [], 1
    for k, e in enumerate(todo):
        say(0.05 + 0.9 * k / len(todo), f"쇼츠 {k + 1}/{len(todo)} 받아 적는 중")
        try:
            v = analyze_video(e["id"], e["title"], out / "v" / e["id"], a.whisper, langs)
        except SystemExit as ex:
            print(f"[건너뜀] {e['id']}: {ex}", file=sys.stderr); continue
        except Exception as ex:  # noqa: BLE001
            print(f"[건너뜀] {e['id']}: {ex}", file=sys.stderr); continue
        if not v:
            continue
        for s in v["sentences"]:
            s["n"] = line_no; line_no += 1
        sheet = out / f"lines-{e['id']}.jpg"
        marks = v["sentences"] or [{"t": sh["t"], "end": sh["t"] + sh["sec"]} for sh in v.get("shots") or []]
        line_sheet(v.pop("src"), marks, sheet, v["sentences"][0]["n"] if v["sentences"] else 1)
        v["sheet"] = str(sheet.relative_to(ROOT)) if sheet.exists() else None
        vids.append(v)
        if not a.keep_video:
            shutil.rmtree(out / "v" / e["id"], ignore_errors=True)
    if not vids:
        sys.exit("받아 적은 쇼츠가 없습니다")
    old = out / "channel.json"
    jokes = json.loads(old.read_text(encoding="utf-8")).get("jokes") if old.exists() else None
    card = aggregate(meta, vids, jokes)
    old.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "channel.md").write_text(render_md(card), encoding="utf-8")
    link_style_card(ref, meta["id"])
    say(1.0, "끝")
    print(json.dumps({"ok": True, "channel": meta["id"], "title": meta["title"], "videos": len(vids), "sentences": card["tone"]["sentences"],
                      "card": str((out / "channel.md").relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
