#!/usr/bin/env python3
"""생성 클립 샷 설계 — 범용 LLM 이 못 하는 것(레퍼런스를 실제로 보고 잰 값 · 편집 자리 · 인물 이어 붙이기 · 만든 뒤 확인)을 프롬프트에 넣는다.

  python3 scripts/shotplan.py look storyboards/<id>.json            # 레퍼런스 쇼츠(X-ray)에서 잰 시각 지시(카메라 · 구도 · 색 · 빛 · 속도)
  python3 scripts/shotplan.py spec storyboards/<id>.json            # 장면별 샷 설계(JSON) — genclip.py prompts 가 모델 문법으로 바꾼다
  python3 scripts/shotplan.py frames storyboards/<id>.json          # 올라온 클립의 마지막 프레임 → 다음 클립 첫 프레임(이어 붙이기)
  python3 scripts/shotplan.py check storyboards/<id>.json [--mid walk]   # 올라온 클립이 설계와 맞나 + 고쳐 쓸 프롬프트 지시

샷 설계 칸(genmodels/cards/SHOT.md): subject · action · beats · setting · camera · lens · framing · lighting · color · mood · style ·
dialogue · audio · duration · request_sec · aspect · safe_zone · no_text · first_frame · references
"""
from __future__ import annotations

import argparse
import colorsys
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
HEAD, TAIL = 0.5, 0.5          # 편집 여유: 앞뒤 0.5초(자를 자리)

CAMERA_EN = {"고정": "locked-off static camera", "흔들림": "handheld camera with natural shake", "줌인": "slow push-in",
             "줌아웃": "slow pull-out", "팬 →": "slow pan right", "팬 ←": "slow pan left", "틸트 ↓": "tilt down", "틸트 ↑": "tilt up"}
SAFE = "keep the lower third and the top 10% of the frame free of faces and key action (captions and app UI go there)"


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
        f = ROOT / "public" / "trends" / "xray" / str(rid) / "xray.json"
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


# ---------------------------------------------------------------- 장면별 샷 설계
def _cast(sb: dict) -> dict:
    return {c.get("name"): c for c in sb.get("cast") or [] if isinstance(c, dict) and c.get("name")}


def specs(sb: dict) -> list[dict]:
    import genclip
    from engines import aspect_of
    lk, cast = look(sb), _cast(sb)
    gm = genclip.gen_materials(sb)
    ref_shots = lk.get("shots") or []
    prev: dict | None = None
    out = []
    for n, (i, m) in enumerate(gm):
        sc = sb["scenes"][i]
        # 레퍼런스 샷을 순서대로 빌린다(장면 수와 샷 수가 다르면 비율로) — 리듬 · 구도를 레퍼런스에서
        rs = ref_shots[round(n * (len(ref_shots) - 1) / max(1, len(gm) - 1))] if ref_shots else {}
        need = float(m.get("gen_sec") or 0) or (float(m["out"]) - float(m.get("in") or 0) if m.get("out") is not None else float(sc.get("sec") or 4))
        who = [cast[c] for c in m.get("cast") or [] if c in cast]
        framing = m.get("framing") or rs.get("framing") or "medium shot"
        line = (sc.get("dialogue") or "").strip()
        speaker = (m.get("speaker") or (m.get("cast") or [None])[0] or "the character")
        beats = list(m.get("beats") or [])
        if not beats:
            beats = [{"t": f"0-{HEAD:g}s", "what": "hold on the opening pose (cut handle)"}]
            if line and m.get("dialogue"):
                beats.append({"t": f"{HEAD:g}-{HEAD + need:.1f}s", "what": f'{speaker} says: "{line}"'})
            else:
                beats.append({"t": f"{HEAD:g}-{HEAD + need:.1f}s", "what": m.get("prompt") or sc.get("beat") or ""})
            beats.append({"t": f"{HEAD + need:.1f}-{HEAD + need + TAIL:.1f}s", "what": "settle, no new action (cut handle)"})
        first = None
        cont = m.get("continue")
        if cont is None and prev and set(prev.get("cast") or []) & set(m.get("cast") or []) and prev["scene"] == i - 1:
            cont = prev["id"]                      # 바로 앞 장면에 같은 인물 → 그 클립 끝에서 이어 시작
        if cont:
            f = ROOT / "compositions" / sb["id"] / "gen" / f"{cont}.last.png"
            first = str(f.relative_to(ROOT)) if f.exists() else f"(클립 {cont} 을 올리면 shotplan.py frames 가 만든다)"
        out.append({
            "id": m["id"], "scene": i, "gen": m.get("gen"),
            "subject": [f"{c['name']}: {c.get('look', '')}" for c in who],
            "action": m.get("prompt") or sc.get("beat") or "",
            "beats": beats,
            "setting": m.get("setting") or "",
            "camera": m.get("camera") or rs.get("camera") or "locked-off static camera",
            "framing": framing,
            "lens": m.get("lens") or lens_of(framing),
            "lighting": m.get("lighting") or ", ".join(x for x in (lk.get("key"), lk.get("temperature")) if x),
            "color": m.get("color") or rs.get("color") or lk.get("color") or "",
            "mood": m.get("mood") or "",
            "style": m.get("style") or "photorealistic, cinematic, natural skin texture",
            "dialogue": {"speaker": speaker, "line": line} if (line and m.get("dialogue")) else None,
            "audio": m.get("audio") or ("natural street ambience, no music" if m.get("dialogue") else "no music"),
            "duration": round(need, 2),
            "request_sec": round(need + HEAD + TAIL, 2),
            "aspect": aspect_of(sb),
            "safe_zone": SAFE,
            "no_text": True,
            "first_frame": first,
            "references": [c["ref"] for c in who if c.get("ref")],
            "people": m.get("people"),
            "pace": lk.get("pace"),
            "from_reference": {"refs": lk.get("refs"), "shot": rs} if rs else None,
        })
        prev = {**m, "scene": i}
    return out


# ---------------------------------------------------------------- 이어 붙이기
def frames(sb: dict) -> list[str]:
    import genclip
    d = ROOT / "compositions" / sb["id"] / "gen"
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for _i, m in genclip.gen_materials(sb):
        f = genclip.clip_file(sb["id"], m)
        if not f:
            continue
        a, b = genclip.span(m, genclip.probe(f)["dur"])
        out = d / f"{m['id']}.last.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(a, b - 0.05):.3f}", "-i", str(f), "-frames:v", "1", str(out)], capture_output=True)
        if r.returncode == 0 and out.exists():
            made.append(str(out.relative_to(ROOT)))
    return made


# ---------------------------------------------------------------- 만든 뒤 확인
def check_clip(sb: dict, spec: dict) -> dict:
    """올라온 클립 vs 설계 → 문제와 프롬프트 고칠 말"""
    import genclip
    m = next(m for _i, m in genclip.gen_materials(sb) if m["id"] == spec["id"])
    f = genclip.clip_file(sb["id"], m)
    if not f:
        return {"id": spec["id"], "missing": True}
    p = genclip.probe(f)
    issues, fixes = [], []
    if p["dur"] + 0.05 < spec["duration"]:
        issues.append(f"길이 {p['dur']:.1f}초 < 필요 {spec['duration']:.1f}초")
        fixes.append(f"request {spec['request_sec']:g}s or longer; keep the action slow enough to fill {spec['duration']:g}s")
    want_portrait = spec["aspect"] == "9:16"
    if want_portrait and p["w"] > p["h"]:
        issues.append(f"가로 영상({p['w']}×{p['h']}) — 세로로 자르면 양옆이 잘림")
        fixes.append("generate in 9:16 vertical; keep the subject centered")
    import tempfile
    from shorts_xray import camera_moves, small_frames, text_boxes
    a, b = genclip.span(m, p["dur"])
    with tempfile.TemporaryDirectory() as td:
        seg = Path(td) / "seg.mp4"            # 쓸 구간(in ~ out)만 본다
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(f), "-an", "-c:v", "libx264", "-preset", "ultrafast", str(seg)], check=True)
        fr = small_frames(seg, Path(td), fps=4, width=270)
        shot = [{"start": 0.0, "end": b - a}]
        camera_moves(fr, 4, shot)
        kind = shot[0]["camera"]["kind"]
        cam_en = CAMERA_EN.get(kind, kind)
        want_cam = (spec.get("camera") or "").lower()
        if want_cam and not any(w in want_cam for w in cam_en.split()[:2]) and not (kind == "고정" and "static" in want_cam):
            issues.append(f"카메라: 원한 것 '{spec['camera']}' / 실제 '{cam_en}'")
            fixes.append(f"state the camera move first and explicitly: '{spec['camera']}'" + ("; avoid 'static', 'tripod'" if "static" not in want_cam else ""))
        # 화면 속 글자(생성 모델이 망가뜨리는 것) — 앞 · 가운데 · 끝 프레임
        txt = 0
        for q in (fr[0], fr[len(fr) // 2], fr[-1]) if fr else []:
            try:
                txt += len(text_boxes(q))
            except Exception:  # noqa: BLE001
                pass
        if txt >= 2:
            issues.append(f"화면에 글자처럼 보이는 영역 {txt}곳")
            fixes.append("no text, no signs, no captions, no logos in frame")
        # 얼굴 수
        try:
            import cv2
            casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            g = cv2.imread(str(fr[len(fr) // 2]), cv2.IMREAD_GRAYSCALE) if fr else None
            faces = int(len(casc.detectMultiScale(g, 1.15, 5, minSize=(int(g.shape[1] * 0.08),) * 2))) if g is not None else 0
        except Exception:  # noqa: BLE001
            faces = -1
        want_faces = spec.get("people")            # 재료에 people(화면 인원)을 적었을 때만 확인
        if want_faces == 1 and faces >= 2:
            issues.append(f"얼굴 {faces}개 — 한 명이어야 함")
            fixes.append("only one person in frame, no bystanders facing the camera")
        elif isinstance(want_faces, int) and want_faces >= 2 and 0 <= faces < want_faces - 1:
            issues.append(f"얼굴 {faces}개 — {want_faces}명이 보여야 함")
            fixes.append(f"exactly {want_faces} people visible, faces toward camera")
    if spec.get("dialogue"):
        ws = genclip.words(f, a, b, ROOT / "audio" / sb["id"] / "gen") if p["audio"] else []
        if not p["audio"]:
            issues.append("소리 없음 — 대사 장면")
            fixes.append("enable native audio / lip-sync; put the line in quotes after the speaker")
        else:
            said = " ".join(w["text"] for w in ws).lower()
            want = [w for w in spec["dialogue"]["line"].lower().replace(".", "").replace(",", "").split() if len(w) > 3]
            miss = [w for w in want if w not in said]
            if want and len(miss) > len(want) / 2:
                issues.append(f"대사가 다름(들린 말: '{said[:60]}')")
                fixes.append(f'quote the exact line once: {spec["dialogue"]["speaker"]} says: "{spec["dialogue"]["line"]}"; no other speech')
    return {"id": spec["id"], "file": str(f.relative_to(ROOT)), "dur": round(p["dur"], 2), "size": [p["w"], p["h"]],
            "issues": issues, "fixes": fixes}


# ---------------------------------------------------------------- 모델별 프롬프트로 바꾸기(genmodels/cards/<모델>.json 의 compile)
CARDS = ROOT / "genmodels" / "cards"
ALIAS = {"dreamina": "seedance", "seedance": "seedance", "kling": "kling", "veo": "veo", "omni": "omni", "gemini": "omni",
         "hailuo": "hailuo", "minimax": "hailuo", "runway": "runway", "wan": "wan", "sora": "sora"}
CLOSER = {"wide shot": "medium shot", "medium shot": "medium close-up", "medium close-up": "close-up", "close-up": "extreme close-up"}


def card(model: str) -> dict:
    f = CARDS / f"{ALIAS.get((model or '').lower(), (model or '').lower())}.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def pick_duration(req: float, durs) -> tuple[float, str | None]:
    if isinstance(durs, list) and durs:
        ok = [d for d in durs if d >= req - 0.05]
        if ok:
            return min(ok), None
        return max(durs), f"필요 {req:g}초가 이 모델 최대 {max(durs)}초보다 길다 — 장면을 나누거나 연장 기능으로"
    return float(max(3, round(req + 0.49))), None


def variant(spec: dict, k: int, lk: dict | None = None) -> dict:
    """0 = 설계대로 · 1 = 다른 카메라(레퍼런스에서 두 번째로 많은 움직임) · 2 = 한 단계 가까운 구도"""
    v = dict(spec)
    if k == 1:
        mix = list(((lk or {}).get("camera_mix") or {}).keys())
        alt = next((c for c in mix if c.split()[0] not in (spec.get("camera") or "")), None) or \
            ("slow push-in" if "static" in (spec.get("camera") or "") else "locked-off static camera")
        v["camera"] = alt
    elif k == 2:
        base = next((f for f in CLOSER if (spec.get("framing") or "").startswith(f)), None)
        if base:
            v["framing"] = (spec.get("framing") or "").replace(base, CLOSER[base], 1)
            v["lens"] = lens_of(v["framing"])
    return v


def _subject(spec: dict) -> str:
    return "; ".join(spec.get("subject") or [])


def _beats(spec: dict, start_at: float = 0.0) -> list[tuple[float, float, str]]:
    out = []
    for b in spec.get("beats") or []:
        t = str(b.get("t", "")).rstrip("s")
        try:
            a, z = (float(x) for x in t.split("-"))
        except ValueError:
            continue
        out.append((a + start_at, z + start_at, b.get("what") or ""))
    return out


def _dedupe(line: str) -> str:
    """한 줄 안에서 쉼표로 나뉜 같은 말 반복 지우기(설계 칸끼리 겹친 'cinematic' 등)"""
    seen, out = set(), []
    for part in line.split(", "):
        key = part.strip().lower().rstrip(".")
        if key and key in seen:
            continue
        seen.add(key)
        out.append(part)
    return ", ".join(out)


def compile_prompt(spec: dict, model: str, k: int = 0, lk: dict | None = None) -> dict:
    """샷 설계 → 그 모델 문법의 프롬프트 + 설정. 카드의 compile 규칙만 쓴다(지어내지 않음)"""
    c = card(model)
    cp = c.get("compile") or {}
    if cp.get("available") is False:
        return {"model": model, "error": f"{c.get('title')}: {cp.get('reason')}"}
    v = variant(spec, k, lk)
    m = ALIAS.get((model or "").lower(), model)
    dur, warn = pick_duration(v["request_sec"], cp.get("durations") or c.get("durations"))
    dlg = v.get("dialogue")
    tone = v.get("tone") or "natural"
    who = _subject(v)
    look_ = ", ".join(x for x in (v.get("lighting"), v.get("color")) if x)
    shot = f"{v['framing']}, {v['lens']}, {v['camera']}"
    beats = [(a, z, w) for a, z, w in _beats(v) if "cut handle" not in w]
    hold = "Hold still for the first and last half second (edit handles)."
    neg_items = ["on-screen text", "subtitles", "captions", "watermark", "logos"] + (["background music"] if "no music" in (v.get("audio") or "") else [])
    refs = list(v.get("references") or []) + ([v["first_frame"]] if v.get("first_frame") and not str(v["first_frame"]).startswith("(") else [])
    lines, negative, notes = [], None, []

    def line_of(d):
        if not d:
            return ""
        if m == "seedance":
            return f"{d['speaker']}'s line ({tone}): {{{d['line']}}}"
        if m == "veo":
            return f"{d['speaker']} says: {d['line']}"
        if m == "hailuo":
            return f"{d['speaker']} (S1) says: <d>[{v.get('lang') or 'English'}] {d['line']}</d>"
        if m == "kling" and v.get("tone"):
            return f"{d['speaker']} ({tone}): {d['line']}"
        return f"{d['speaker']} says: \"{d['line']}\""

    if m == "seedance":
        lines.append(f"{who + ', ' if who else ''}{v['action']}{', ' + v['setting'] if v.get('setting') else ''}, {v['style']}, {shot}.")
        for n, ref in enumerate(v.get("references") or [], 1):
            lines.append(f"The character in [Image {n}]: keep the appearance strictly from [Image {n}], no face changes.")
        if v.get("first_frame") and not str(v["first_frame"]).startswith("("):
            lines.append(f"Start from [Image {len(v.get('references') or []) + 1}] as the first frame.")
        for n, (a, z, w) in enumerate(beats, 1):
            say = line_of(dlg) if dlg and dlg["line"] in w else w
            lines.append(f"Shot {n} | {int(a)}-{max(int(a) + 1, round(z))}s: {say}")
        lines.append(f"Keep the same {v.get('setting') or 'location'}, {look_ or 'lighting'} and outfits throughout. {hold}")
        lines.append("No subtitles." + (" No BGM." if "no music" in (v.get("audio") or "") else ""))
        notes.append("실사 얼굴 그림은 직접 올릴 수 없다 — 인물 기준 그림은 Seedream(같은 계정)으로 만든 원본을 쓴다")
        notes.append("2.0 모델이면 타임스탬프를 지우고 Shot N 만 남긴다")
    elif m == "kling":
        lines.append(f"{who + '. ' if who else ''}{v['action']}.")
        if v.get("setting"):
            lines.append(v["setting"] + ".")
        lines.append(f"{shot}. {look_}. {v.get('mood') or ''}".strip())
        if dlg:
            lines.append(line_of(dlg))
        lines.append(cp.get("single_shot") or "")
        lines.append(f"{v['style']}. {hold} Keep the frame free of text.")
    elif m == "veo":
        lines.append(f"A {shot} shot. {who + '. ' if who else ''}{v['action']}{'. ' + v['setting'] if v.get('setting') else ''}.")
        lines.append(f"{look_}. {v['style']}. {cp.get('single_shot')}")
        if dlg:
            lines.append(line_of(dlg).rstrip(".!?") + ".")
        lines.append(f"Audio: {v.get('audio')}.")
        negative = ", ".join(["text", "subtitles", "captions", "watermark", "logo"] + (["music"] if "no music" in (v.get("audio") or "") else []))
    elif m == "omni":
        lines.append(cp.get("single_shot"))
        lines.append(f"{who + '. ' if who else ''}{v['action']}{'. ' + v['setting'] if v.get('setting') else ''}. {shot}. {look_}. {v['style']}.")
        for a, z, w in beats:
            lines.append(f"[{a:g}-{z:g}s] {line_of(dlg) if dlg and dlg['line'] in w else w}")
        lines.append(f"Sound design: {v.get('audio')}. " + " ".join(f"No {x}." for x in neg_items[:3]))
    elif m == "wan":
        lines.append(cp.get("single_shot"))
        lines.append(f"{v['style']}, {look_}. {who + '. ' if who else ''}{v['action']}{'. ' + v['setting'] if v.get('setting') else ''}. {dur:g} seconds.")
        for n, (a, z, w) in enumerate(beats, 1):
            lines.append(f"Shot {n} [{a:g}-{z:g}s] {shot}. {line_of(dlg) if dlg and dlg['line'] in w else w}")
        if not dlg:
            lines.append("No dialogue.")
        lines.append("Negative prompt list: " + ", ".join(["no subtitles or watermarks", "no complex text", "no extra characters", "avoid facial distortion"]))
    elif m == "runway":
        lines.append(f"{v['camera'].capitalize()}, {v['framing']}: {who + ', ' if who else ''}{v['action']}{', ' + v['setting'] if v.get('setting') else ''}. {look_}, {v['style']}. {cp.get('single_shot')} Clean frame with plain surfaces.")
        notes.append("Runway API 는 소리가 없다 — 대사 장면은 다른 모델(Kling · Seedance · Veo · Hailuo)")
    elif m == "hailuo":
        first = f"[Shot 1] Live-action, cinematic, a {shot} frames {who or 'the subject'}. {v['action']}{'. ' + v['setting'] if v.get('setting') else ''}. {look_}."
        if dlg:
            first += " " + line_of(dlg)
        lines.append(cp.get("header", "") + first)
        lines.append(f"overall_soundscape: {v.get('audio')}.")
    else:
        lines.append(f"{shot}. {who + '. ' if who else ''}{v['action']}. {look_}. {v['style']}. {hold}")
        if dlg:
            lines.append(line_of(dlg))
    prompt = "\n".join(_dedupe(x) for x in lines if x and x.strip())
    if cp.get("max_chars") and len(prompt) > cp["max_chars"]:
        notes.append(f"프롬프트 {len(prompt)}자 > 한도 {cp['max_chars']}자 — 줄일 것")
    if warn:
        notes.append(warn)
    aspect_ok = cp.get("aspect_9_16")
    if v["aspect"] == "9:16" and aspect_ok is False:
        notes.append("이 모델은 9:16 을 지원하지 않는다 — 가로로 만들면 Fluma 가 가운데를 자른다(인물을 가운데에)")
    elif v["aspect"] == "9:16" and aspect_ok is None:
        notes.append("9:16 지원이 문서로 확인되지 않음 — 화면 비율 선택지를 확인")
    return {"model": m, "title": c.get("title"), "variant": ["설계대로", "다른 카메라", "더 가까운 구도"][k], "prompt": prompt,
            "negative": negative, "settings": {"duration": dur, "aspect": v["aspect"], "audio": bool((c.get("audio") or {}).get("native"))},
            "references": refs, "notes": notes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("look", "spec", "frames", "check"):
        s = sub.add_parser(n); s.add_argument("storyboard")
        if n == "check":
            s.add_argument("--mid")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads((sp if sp.is_absolute() else ROOT / sp).read_text("utf-8"))
    if a.cmd == "look":
        lk = look(sb)
        print(json.dumps({k: v for k, v in lk.items() if k != "shots"}, ensure_ascii=False, indent=1) if lk else "레퍼런스 분석 없음(콘티 reference 에 X-ray 한 쇼츠 id)")
        return 0
    if a.cmd == "spec":
        print(json.dumps(specs(sb), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "frames":
        made = frames(sb)
        print("\n".join(made) or "올라온 클립이 없습니다")
        return 0
    bad = 0
    for s in specs(sb):
        if a.mid and s["id"] != a.mid:
            continue
        r = check_clip(sb, s)
        if r.get("missing"):
            print(f"· {s['id']}: 아직 없음")
            continue
        print(f"{'✓' if not r['issues'] else '✗'} {s['id']}: {r['file']} · {r['dur']}초 · {r['size'][0]}×{r['size'][1]}")
        for i, fx in zip(r["issues"], r["fixes"]):
            bad += 1
            print(f"    - {i}\n      → 프롬프트에: {fx}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
