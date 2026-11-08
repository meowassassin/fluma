#!/usr/bin/env python3
"""레퍼런스 화면 문법 — 레퍼런스 쇼츠(X-ray)에서 잰 값을 말로(컷 길이 · 카메라 · 구도 · 색 · 빛 · 속도). 지어내지 않고 숫자에서 나온 말만.
direct.py(콘티 direction 채우기) · directions.py(시안) · design.py 가 쓴다.

  python3 engine/story/look.py data/storyboards/<id>.json
"""
from __future__ import annotations

import colorsys
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())

CAMERA_EN = {"고정": "locked-off static camera", "흔들림": "handheld camera with natural shake", "줌인": "slow push-in",
             "줌아웃": "slow pull-out", "팬 →": "slow pan right", "팬 ←": "slow pan left", "틸트 ↓": "tilt down", "틸트 ↑": "tilt up"}


# ---------------------------------------------------------------- 색 · 빛 말로
def color_word(hex_: str) -> str:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.12 or l < 0.06:
        base = "near-black" if l < 0.12 else "charcoal grey" if l < 0.35 else "grey" if l < 0.7 else "off-white"
        return base
    hue = h * 360
    names = [(15, "red"), (40, "orange"), (55, "amber"), (70, "yellow"), (100, "olive"), (150, "green"), (185, "teal"),
             (205, "cyan"), (245, "blue"), (275, "indigo"), (300, "purple"), (335, "magenta"), (360, "red")]
    name = next(n for lim, n in names if hue <= lim)
    if name == "blue" and l < 0.25:
        name = "navy"
    if name in ("orange", "amber") and s < 0.45:
        name = "warm beige" if l > 0.45 else "brown"
    tone = "deep " if l < 0.25 else "muted " if s < 0.35 else "light " if l > 0.75 else ""
    return (tone + name).strip()


def _warm(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return (r - b) / 255


def _light(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------- 레퍼런스에서 잰 값
def xrays(sb: dict) -> list[dict]:
    out = []
    for rid in sb.get("reference") or []:
        f = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "xray.json"
        if f.exists():
            try:
                out.append(json.loads(f.read_text("utf-8")))
            except (OSError, ValueError):
                pass
    return out


def framing_of(sub: dict) -> str:
    a, faces = float(sub.get("area") or 0), int(sub.get("faces") or 0)
    size = "extreme close-up" if a > 0.55 else "close-up" if a > 0.3 else "medium shot" if a > 0.12 else "wide shot"
    who = "" if not faces else " of one person" if faces == 1 else f" of {faces} people"
    return size + who


def lens_of(framing: str) -> str:
    return "85mm lens, shallow depth of field" if "close" in framing else "50mm lens" if "medium" in framing else "24mm wide lens"


def look(sb: dict) -> dict:
    """레퍼런스 쇼츠들에서 잰 시각 지시 — 숫자에서 나온 말만(지어내지 않음)"""
    xs = xrays(sb)
    shots = [s for x in xs for s in x.get("shots") or []]
    if not shots:
        return {}
    lens = [float(s["end"]) - float(s["start"]) for s in shots]
    cams = Counter((s.get("camera") or {}).get("kind", "고정") for s in shots)
    pal: Counter = Counter()
    for s in shots:
        for p in s.get("palette") or []:
            if _light(p["hex"]) < 0.025:      # 레터박스 검은 띠 · 완전 검정은 화면 색이 아니다
                continue
            pal[p["hex"]] += float(p.get("w") or 0)
    top = [h for h, _ in pal.most_common(6)]
    tot = sum(pal.values()) or 1
    light = sum(_light(h) * w for h, w in pal.items()) / tot
    warm = sum(_warm(h) * w for h, w in pal.items()) / tot
    words = []
    for h in top:
        w = color_word(h)
        if w not in words:
            words.append(w)
    faces = sum(1 for s in shots if (s.get("subject") or {}).get("faces"))
    bpm = next((x.get("sound", {}).get("bpm") for x in xs if (x.get("sound") or {}).get("bpm")), None)
    avg = sum(lens) / len(lens)
    return {
        "refs": [x.get("id") for x in xs],
        "shot_sec": round(avg, 2),
        "pace": "fast cuts, one clear action per shot" if avg < 2.2 else "steady pacing" if avg < 4 else "slow, lingering shots",
        "camera_mix": {CAMERA_EN.get(k, k): v for k, v in cams.most_common()},
        "palette": top[:5],
        "color": ", ".join(words[:4]),
        "key": "low-key, moody lighting with deep shadows" if light < 0.3 else "natural daylight exposure" if light < 0.55 else "bright, high-key lighting",
        "temperature": "warm color temperature" if warm > 0.06 else "cool color temperature" if warm < -0.04 else "neutral color temperature",
        "faces_share": round(faces / len(shots), 2),
        "bpm": bpm,
        "shots": [{"sec": round(float(s["end"]) - float(s["start"]), 2), "camera": CAMERA_EN.get((s.get("camera") or {}).get("kind", "고정")),
                   "framing": framing_of(s.get("subject") or {}), "color": ", ".join(list(dict.fromkeys(color_word(p["hex"]) for p in (s.get("palette") or []) if _light(p["hex"]) >= 0.025))[:3])}
                  for s in shots],
    }


if __name__ == "__main__":
    print(json.dumps(look(json.loads(Path(sys.argv[1]).read_text("utf-8"))), ensure_ascii=False, indent=1))
