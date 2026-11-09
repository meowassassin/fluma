#!/usr/bin/env python3
"""실사 생성 샷 설계 — 그림 · 영상 모델마다 문법에 맞춘 프롬프트를 쓴다(genclip.py 가 오픈라우터로 직접 부르거나, 사용자가 자기 도구에 붙여 넣는다).
범용 LLM 이 못 하는 것(레퍼런스를 실제로 보고 잰 값 · 고른 느낌 · 편집 자리 · 인물 이어 붙이기 · 만든 뒤 확인)을 프롬프트에 넣는다.

흐름(이미지 먼저 → 영상): 샷마다
  1. 키프레임 그림 프롬프트(이미지 모델 문법) → 사용자가 그림을 만들어 올림(<재료 id>.png)
  2. 그림 확인(check) — 9:16 · 글자 · 얼굴 수, 그리고 에이전트가 직접 보고 설계와 맞는지
  3. 그 그림을 첫 프레임으로 영상 프롬프트(영상 모델 문법, 움직임 · 카메라 위주) → 사용자가 클립을 만들어 올림(<재료 id>.mp4)
  4. 클립 확인(check) — 길이 · 비율 · 카메라 · 글자 · 얼굴 · 대사 → 고쳐 쓸 문구

  python3 engine/gen/shotplan.py spec data/storyboards/<id>.json      # 장면별 샷 설계(JSON)
  python3 engine/gen/shotplan.py frames data/storyboards/<id>.json    # 올라온 클립의 마지막 프레임 → 다음 샷 첫 프레임(이어 붙이기)
  python3 engine/gen/shotplan.py check data/storyboards/<id>.json [--mid walk]   # 올라온 그림 · 클립 확인 + 고쳐 쓸 말
프롬프트 묶음(사용자에게 주는 문서)은 genclip.py prompts.

샷 설계 칸: subject · action · beats · setting · camera · lens · framing · lighting · color · mood · style · dialogue · audio ·
duration · request_sec · aspect · safe_zone · no_text · keyframe · first_frame · references
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from look import CAMERA_EN, lens_of, look  # noqa: E402

HEAD, TAIL = 0.5, 0.5          # 편집 여유: 앞뒤 0.5초(자를 자리)
SAFE = "keep the lower third and the top 10% of the frame free of faces and key action (captions and app UI go there)"
CARDS = ROOT / "engine" / "gen" / "models" / "cards"
IMAGE_CARDS = ROOT / "engine" / "gen" / "models" / "image"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_STYLE = "photorealistic, cinematic, natural skin texture"


def gen_dir(sid: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "gen"


def keyframe_file(sid: str, mid: str) -> Path | None:
    """사용자가 올린 키프레임 그림 — data/public/uploads/<id>/ 에서 이름에 재료 id 가 든 최신 그림"""
    up = ROOT / "data" / "public" / "uploads" / sid
    if not up.exists() or not mid:
        return None
    hits = [f for f in up.iterdir() if f.is_file() and f.suffix.lower() in IMG_EXT and mid.lower() in f.stem.lower()]
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def feel_of(sb: dict) -> dict:
    """고른 느낌(engine/story/feel.py pick) — 그림 · 영상 프롬프트의 style · mood · color · lighting 이 된다"""
    f = (sb.get("direction") or {}).get("feel")
    return f if isinstance(f, dict) else {}


# ---------------------------------------------------------------- 장면별 샷 설계
def _cast(sb: dict) -> dict:
    return {c.get("name"): c for c in sb.get("cast") or [] if isinstance(c, dict) and c.get("name")}


def specs(sb: dict) -> list[dict]:
    import genclip
    from engines import aspect_of
    lk, cast, fe = look(sb), _cast(sb), feel_of(sb)
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
        line = str(m.get("line") or "").strip()            # 클립 속 대사(있으면 원음으로 살린다)
        speaker = (m.get("speaker") or (m.get("cast") or [None])[0] or "the character")
        beats = list(m.get("beats") or [])
        if not beats:
            beats = [{"t": f"0-{HEAD:g}s", "what": "hold on the opening pose (cut handle)"},
                     {"t": f"{HEAD:g}-{HEAD + need:.1f}s", "what": f'{speaker} says: "{line}"' if line else (m.get("prompt") or sc.get("beat") or "")},
                     {"t": f"{HEAD + need:.1f}-{HEAD + need + TAIL:.1f}s", "what": "settle, no new action (cut handle)"}]
        key = keyframe_file(sb["id"], m["id"])
        first = key.relative_to(ROOT).as_posix() if key else None
        cont = m.get("continue")
        if cont is None and prev and set(prev.get("cast") or []) & set(m.get("cast") or []) and prev["scene"] == i - 1:
            cont = prev["id"]                      # 바로 앞 장면에 같은 인물 → 그 클립 끝에서 이어 시작
        if cont and not key:
            f = gen_dir(sb["id"]) / f"{cont}.last.png"
            first = f.relative_to(ROOT).as_posix() if f.exists() else f"(클립 {cont} 을 올리면 shotplan.py frames 가 만든다)"
        out.append({
            "id": m["id"], "scene": i, "gen": m.get("gen"), "image_model": m.get("image_model"),
            "subject": [f"{c['name']}: {c.get('look', '')}" for c in who],
            "action": m.get("prompt") or sc.get("beat") or "",
            "beats": beats,
            "setting": m.get("setting") or "",
            "camera": m.get("camera") or rs.get("camera") or "locked-off static camera",
            "framing": framing,
            "lens": m.get("lens") or lens_of(framing),
            "lighting": m.get("lighting") or fe.get("lighting_en") or ", ".join(x for x in (lk.get("key"), lk.get("temperature")) if x),
            "color": m.get("color") or fe.get("color_en") or rs.get("color") or lk.get("color") or "",
            "mood": m.get("mood") or fe.get("mood_en") or "",
            "style": m.get("style") or fe.get("style_en") or DEFAULT_STYLE,
            "dialogue": {"speaker": speaker, "line": line} if line else None,
            "audio": m.get("audio") or ("natural ambience, no music" if line else "no music"),
            "duration": round(need, 2),
            "request_sec": round(need + HEAD + TAIL, 2),
            "aspect": aspect_of(sb),
            "safe_zone": SAFE,
            "no_text": True,
            "keyframe": first if key else None,
            "first_frame": first,
            "references": [c["ref"] for c in who if c.get("ref")],
            "people": m.get("people"),
            "pace": lk.get("pace"),
            "feel": fe.get("name"),
            "from_reference": {"refs": lk.get("refs"), "shot": rs} if rs else None,
        })
        prev = {**m, "scene": i}
    return out


# ---------------------------------------------------------------- 이어 붙이기
def frames(sb: dict) -> list[str]:
    import genclip
    from craft import vclip
    d = gen_dir(sb["id"])
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for _i, m in genclip.gen_materials(sb):
        f = genclip.clip_file(sb["id"], m)
        if not f:
            continue
        a, b = vclip.span(m, vclip.probe(f)["dur"])
        out = d / f"{m['id']}.last.png"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(a, b - 0.05):.3f}", "-i", str(f), "-frames:v", "1", str(out)], capture_output=True)
        if r.returncode == 0 and out.exists():
            made.append(out.relative_to(ROOT).as_posix())
    return made


# ---------------------------------------------------------------- 만든 뒤 확인
def _faces(img: Path) -> int:
    try:
        import cv2
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        g = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
        return int(len(casc.detectMultiScale(g, 1.15, 5, minSize=(int(g.shape[1] * 0.08),) * 2))) if g is not None else 0
    except Exception:  # noqa: BLE001
        return -1


def _text_count(imgs: list[Path]) -> int:
    from shorts_xray import text_boxes
    n = 0
    for q in imgs:
        try:
            n += len(text_boxes(q))
        except Exception:  # noqa: BLE001
            pass
    return n


def check_key(sb: dict, spec: dict) -> dict:
    """올라온 키프레임 그림 vs 설계 — 비율 · 글자 · 얼굴 수(설계와 맞는지는 에이전트가 그림을 직접 보고도 판단한다)"""
    f = keyframe_file(sb["id"], spec["id"])
    if not f:
        return {"id": spec["id"], "missing": True}
    from PIL import Image
    with Image.open(f) as im:
        w, h = im.size
    issues, fixes = [], []
    if spec["aspect"] == "9:16" and abs(w / h - 9 / 16) > 0.04:
        issues.append(f"그림 비율 {w}×{h} — 9:16 이 아님(영상 모델이 다른 비율로 만들거나 양옆이 잘림)")
        fixes.append("generate the image in vertical 9:16")
    if _text_count([f]) >= 2:
        issues.append("그림에 글자처럼 보이는 영역")
        fixes.append("no text, no signs, no captions, no logos in the image")
    faces = _faces(f)
    want = spec.get("people")
    if want == 1 and faces >= 2:
        issues.append(f"얼굴 {faces}개 — 한 명이어야 함")
        fixes.append("only one person, no bystanders facing the camera")
    elif isinstance(want, int) and want >= 2 and 0 <= faces < want - 1:
        issues.append(f"얼굴 {faces}개 — {want}명이 보여야 함")
        fixes.append(f"exactly {want} people visible, faces toward camera")
    return {"id": spec["id"], "kind": "keyframe", "file": f.relative_to(ROOT).as_posix(), "size": [w, h], "issues": issues, "fixes": fixes}


def check_clip(sb: dict, spec: dict) -> dict:
    """올라온 클립 vs 설계 → 문제와 프롬프트 고칠 말"""
    import tempfile

    import genclip
    from craft import vclip
    from shorts_xray import camera_moves, small_frames
    m = next(m for _i, m in genclip.gen_materials(sb) if m["id"] == spec["id"])
    f = genclip.clip_file(sb["id"], m)
    if not f:
        return {"id": spec["id"], "missing": True}
    p = vclip.probe(f)
    issues, fixes = [], []
    if p["dur"] + 0.05 < spec["duration"]:
        issues.append(f"길이 {p['dur']:.1f}초 < 필요 {spec['duration']:.1f}초")
        fixes.append(f"request {spec['request_sec']:g}s or longer; keep the action slow enough to fill {spec['duration']:g}s")
    if spec["aspect"] == "9:16" and p["w"] > p["h"]:
        issues.append(f"가로 영상({p['w']}×{p['h']}) — 세로로 자르면 양옆이 잘림")
        fixes.append("generate in 9:16 vertical; keep the subject centered")
    a, b = vclip.span(m, p["dur"])
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
        if fr and _text_count([fr[0], fr[len(fr) // 2], fr[-1]]) >= 2:          # 생성 모델이 망가뜨리는 글자
            issues.append("화면에 글자처럼 보이는 영역")
            fixes.append("no text, no signs, no captions, no logos in frame")
        faces = _faces(fr[len(fr) // 2]) if fr else -1
        want_faces = spec.get("people")
        if want_faces == 1 and faces >= 2:
            issues.append(f"얼굴 {faces}개 — 한 명이어야 함")
            fixes.append("only one person in frame, no bystanders facing the camera")
        elif isinstance(want_faces, int) and want_faces >= 2 and 0 <= faces < want_faces - 1:
            issues.append(f"얼굴 {faces}개 — {want_faces}명이 보여야 함")
            fixes.append(f"exactly {want_faces} people visible, faces toward camera")
    if spec.get("dialogue"):
        if not p["audio"]:
            issues.append("소리 없음 — 대사 장면")
            fixes.append("enable native audio / lip-sync; put the line in quotes after the speaker")
        else:
            ws = genclip.words(f, a, b, ROOT / "data" / "audio" / sb["id"] / "gen")
            said = " ".join(w["text"] for w in ws).lower()
            want = [w for w in spec["dialogue"]["line"].lower().replace(".", "").replace(",", "").split() if len(w) > 3]
            miss = [w for w in want if w not in said]
            if want and len(miss) > len(want) / 2:
                issues.append(f"대사가 다름(들린 말: '{said[:60]}')")
                fixes.append(f'quote the exact line once: {spec["dialogue"]["speaker"]} says: "{spec["dialogue"]["line"]}"; no other speech')
    return {"id": spec["id"], "kind": "clip", "file": f.relative_to(ROOT).as_posix(), "dur": round(p["dur"], 2), "size": [p["w"], p["h"]],
            "issues": issues, "fixes": fixes}


# ---------------------------------------------------------------- 모델별 프롬프트로 바꾸기(카드의 compile 규칙)
ALIAS = {"dreamina": "seedance", "seedance": "seedance", "kling": "kling", "veo": "veo", "omni": "omni", "gemini": "omni",
         "hailuo": "hailuo", "minimax": "hailuo", "runway": "runway", "wan": "wan", "sora": "sora"}
IMAGE_ALIAS = {"seedream": "seedream", "dreamina": "seedream", "nanobanana": "nanobanana", "nano-banana": "nanobanana", "gemini": "nanobanana",
               "gptimage": "gptimage", "gpt-image": "gptimage", "openai": "gptimage", "midjourney": "midjourney", "mj": "midjourney"}
PAIR = {"seedance": "seedream", "veo": "nanobanana", "omni": "nanobanana", "kling": "midjourney", "runway": "midjourney",
        "hailuo": "midjourney", "wan": "midjourney"}
CLOSER = {"wide shot": "medium shot", "medium shot": "medium close-up", "medium close-up": "close-up", "close-up": "extreme close-up"}


def card(model: str) -> dict:
    f = CARDS / f"{ALIAS.get((model or '').lower(), (model or '').lower())}.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def image_card(model: str) -> dict:
    f = IMAGE_CARDS / f"{IMAGE_ALIAS.get((model or '').lower(), (model or '').lower())}.json"
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


def _beats(spec: dict) -> list[tuple[float, float, str]]:
    out = []
    for b in spec.get("beats") or []:
        t = str(b.get("t", "")).rstrip("s")
        try:
            a, z = (float(x) for x in t.split("-"))
        except ValueError:
            continue
        out.append((a, z, b.get("what") or ""))
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


def compile_image(spec: dict, model: str | None = None, k: int = 0, lk: dict | None = None) -> dict:
    """샷 설계 → 키프레임 그림 프롬프트(이미지 모델 문법). 영상의 첫 프레임이 되므로 '시작 순간'의 정지 장면을 그린다"""
    mdl = IMAGE_ALIAS.get((model or spec.get("image_model") or PAIR.get(ALIAS.get(str(spec.get("gen") or "").lower(), ""), "nanobanana")).lower(), "nanobanana")
    c = image_card(mdl)
    cp = c.get("compile") or {}
    v = variant(spec, 2, lk) if k == 1 else dict(spec)          # 그림 안: 0 설계대로 · 1 한 단계 가까이 · 2 다른 각도(정지 그림이라 카메라 움직임은 의미 없음)
    if k == 2:
        v["framing"] = f"low-angle {v['framing']}" if "close" not in (v.get("framing") or "") else f"three-quarter view {v['framing']}"
    who = _subject(v)
    action = (v.get("action") or "").rstrip(".")
    parts = {
        "subject": who, "action": f"{action}, frozen at the opening moment of the motion" if action else "",
        "setting": v.get("setting") or "", "framing": f"{v['framing']}, {v['lens']}",
        "lighting": v.get("lighting") or "", "color": f"color palette: {v['color']}" if v.get("color") else "",
        "mood": f"mood: {v['mood']}" if v.get("mood") else "", "style": v.get("style") or DEFAULT_STYLE,
    }
    order = [parts[x] for x in cp.get("order") or parts if parts.get(x)]
    notes = [c["note"]] if c.get("note") else []
    style = cp.get("style")
    no_text = "No text, no captions, no logos, no watermark."
    space = "Leave the lower third calm (captions go there)."
    if style == "phrases":
        prompt = _dedupe(", ".join(order)) + f" {cp.get('aspect', '--ar 9:16')} --no text, watermark, logo"
    elif style == "labeled":
        prompt = "\n".join(f"{x.capitalize()}: {parts[x]}" for x in (cp.get("order") or parts) if parts.get(x)) + f"\nComposition: vertical 9:16. {space}\n{no_text}"
    elif style == "narrative":
        prompt = f"A {parts['style']} image. {parts['framing'].capitalize()} of {who or 'the subject'}{', ' + parts['action'] if action else ''}" \
                 f"{'. ' + parts['setting'] if parts['setting'] else ''}. {parts['lighting']}. {parts['color']}. {parts['mood']}. " \
                 f"Vertical 9:16 aspect ratio. {space} {no_text}"
    else:                                                  # sentences(Seedream 등)
        prompt = _dedupe(", ".join(order)) + f". Vertical 9:16. {space} {no_text}"
    prompt = " ".join(prompt.replace(" . ", " ").split(" ")).replace("..", ".")
    return {"model": mdl, "title": c.get("title") or mdl, "variant": ["설계대로", "더 가까운 구도", "다른 각도"][k], "prompt": prompt.strip(),
            "settings": {"aspect": v["aspect"], "how": cp.get("aspect")}, "references": list(v.get("references") or []), "notes": notes}


def compile_prompt(spec: dict, model: str, k: int = 0, lk: dict | None = None) -> dict:
    """샷 설계 → 그 모델 문법의 영상 프롬프트 + 설정. 카드의 compile 규칙만 쓴다(지어내지 않음).
    키프레임 그림이 올라와 있으면 이미지→영상: 겉모습은 그림이 정하니 움직임 · 카메라 위주로 쓴다"""
    c = card(model)
    cp = c.get("compile") or {}
    if cp.get("available") is False:
        return {"model": model, "error": f"{c.get('title')}: {cp.get('reason')}"}
    v = variant(spec, k, lk)
    m = ALIAS.get((model or "").lower(), model)
    dur, warn = pick_duration(v["request_sec"], cp.get("durations") or c.get("durations"))
    dlg = v.get("dialogue")
    tone = v.get("tone") or "natural"
    i2v = bool(v.get("keyframe"))
    who = "" if i2v else _subject(v)
    look_ = "" if i2v else ", ".join(x for x in (v.get("lighting"), v.get("color")) if x)
    style = "" if i2v else v["style"]
    shot = f"{v['framing']}, {v['lens']}, {v['camera']}" if not i2v else v["camera"]
    beats = [(a, z, w) for a, z, w in _beats(v) if "cut handle" not in w]
    hold = "Hold still for the first and last half second (edit handles)."
    keep = "Keep the composition, lighting, colors and appearance of the input image." if i2v else ""
    neg_items = ["on-screen text", "subtitles", "captions", "watermark", "logos"] + (["background music"] if "no music" in (v.get("audio") or "") else [])
    refs = list(v.get("references") or []) + ([v["first_frame"]] if v.get("first_frame") and not str(v["first_frame"]).startswith("(") else [])
    lines, negative, notes = [], None, []
    if i2v:
        notes.append(f"이미지→영상: 올린 키프레임 `{v['keyframe']}` 을 첫 프레임(시작 이미지)으로 넣는다")

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

    act = v["action"]
    set_ = "" if i2v else (v.get("setting") or "")
    if m == "seedance":
        lines.append(", ".join(x for x in (who, act, set_, style, shot) if x) + ".")
        for n, _ref in enumerate(v.get("references") or [], 1):
            lines.append(f"The character in [Image {n}]: keep the appearance strictly from [Image {n}], no face changes.")
        if v.get("first_frame") and not str(v["first_frame"]).startswith("("):
            lines.append(f"Start from [Image {len(v.get('references') or []) + 1}] as the first frame.")
        for n, (a, z, w) in enumerate(beats, 1):
            say = line_of(dlg) if dlg and dlg["line"] in w else w
            lines.append(f"Shot {n} | {int(a)}-{max(int(a) + 1, round(z))}s: {say}")
        lines.append(keep or f"Keep the same {v.get('setting') or 'setting'}, {look_ or 'lighting'}" + (" and outfits" if who else "") + " throughout.")
        lines.append(hold + " No subtitles." + (" No BGM." if "no music" in (v.get("audio") or "") else ""))
        notes.append("실사 얼굴 그림은 직접 올릴 수 없다 — 인물 기준 그림은 Seedream(같은 계정)으로 만든 원본을 쓴다")
        notes.append("2.0 모델이면 타임스탬프를 지우고 Shot N 만 남긴다")
    elif m == "kling":
        lines.append(f"{who + '. ' if who else ''}{act}.")
        if set_:
            lines.append(set_ + ".")
        lines.append(f"{shot}. {look_}. {v.get('mood') or ''}".strip(" ."))
        if dlg:
            lines.append(line_of(dlg))
        lines.append(cp.get("single_shot") or "")
        lines.append(f"{(style + '. ') if style else ''}{keep} {hold} Keep the frame free of text.".strip())
    elif m == "veo":
        lines.append(f"A {shot} shot. {who + '. ' if who else ''}{act}{'. ' + set_ if set_ else ''}.")
        lines.append(" ".join(x for x in (f"{look_}." if look_ else "", f"{style}." if style else "", keep, cp.get("single_shot") or "") if x))
        if dlg:
            lines.append(line_of(dlg).rstrip(".!?") + ".")
        lines.append(f"Audio: {v.get('audio')}.")
        negative = ", ".join(["text", "subtitles", "captions", "watermark", "logo"] + (["music"] if "no music" in (v.get("audio") or "") else []))
    elif m == "omni":
        lines.append(cp.get("single_shot") or "")
        lines.append(" ".join(x for x in (f"{who}." if who else "", f"{act}.", f"{set_}." if set_ else "", f"{shot}.", f"{look_}." if look_ else "", f"{style}." if style else "", keep) if x))
        for a, z, w in beats:
            lines.append(f"[{a:g}-{z:g}s] {line_of(dlg) if dlg and dlg['line'] in w else w}")
        lines.append(f"Sound design: {v.get('audio')}. " + " ".join(f"No {x}." for x in neg_items[:3]))
    elif m == "wan":
        lines.append(cp.get("single_shot") or "")
        lines.append(" ".join(x for x in (f"{style}, {look_}." if style else "", f"{who}." if who else "", f"{act}.", f"{set_}." if set_ else "", f"{dur:g} seconds.", keep) if x))
        for n, (a, z, w) in enumerate(beats, 1):
            lines.append(f"Shot {n} [{a:g}-{z:g}s] {shot}. {line_of(dlg) if dlg and dlg['line'] in w else w}")
        if not dlg:
            lines.append("No dialogue.")
        lines.append("Negative prompt list: " + ", ".join(["no subtitles or watermarks", "no complex text", "no extra characters", "avoid facial distortion"]))
    elif m == "runway":
        lines.append(f"{v['camera'].capitalize()}, {v['framing']}: {who + ', ' if who else ''}{act}{', ' + set_ if set_ else ''}. "
                     f"{(look_ + ', ' + style + '. ') if style else ''}{keep} {cp.get('single_shot') or ''} Clean frame with plain surfaces.")
        notes.append("Runway API 는 소리가 없다 — 대사 장면은 다른 모델(Kling · Seedance · Veo · Hailuo)")
    elif m == "hailuo":
        first = f"[Shot 1] Live-action, cinematic, a {shot} frames {who or 'the subject'}. {act}{'. ' + set_ if set_ else ''}. {look_}. {keep}"
        if dlg:
            first += " " + line_of(dlg)
        lines.append(cp.get("header", "") + first)
        lines.append(f"overall_soundscape: {v.get('audio')}.")
    else:
        lines.append(f"{shot}. {who + '. ' if who else ''}{act}. {look_}. {style}. {keep} {hold}")
        if dlg:
            lines.append(line_of(dlg))
    prompt = "\n".join(_dedupe(" ".join(x.split())) for x in lines if x and x.strip())
    if cp.get("max_chars") and len(prompt) > cp["max_chars"]:
        notes.append(f"프롬프트 {len(prompt)}자 > 한도 {cp['max_chars']}자 — 줄일 것")
    if warn:
        notes.append(warn)
    aspect_ok = cp.get("aspect_9_16")
    if v["aspect"] == "9:16" and aspect_ok is False:
        notes.append("이 모델은 9:16 을 지원하지 않는다 — 가로로 만들면 Fluma 가 가운데를 자른다(인물을 가운데에)")
    elif v["aspect"] == "9:16" and aspect_ok is None:
        notes.append("9:16 지원이 문서로 확인되지 않음 — 화면 비율 선택지를 확인")
    return {"model": m, "title": c.get("title"), "variant": ["설계대로", "다른 카메라", "더 가까운 구도"][k], "i2v": i2v, "prompt": prompt,
            "negative": negative, "settings": {"duration": dur, "aspect": v["aspect"], "audio": bool((c.get("audio") or {}).get("native")) and bool(dlg)},
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
        print("\n".join(frames(sb)) or "올라온 클립이 없습니다")
        return 0
    bad = 0
    for s in specs(sb):
        if a.mid and s["id"] != a.mid:
            continue
        rs = [r for r in (check_key(sb, s), check_clip(sb, s)) if not r.get("missing")]
        if not rs:
            print(f"· {s['id']}: 아직 아무것도 올라오지 않음 — genclip.py prompts 의 1단계(그림)부터")
        for r in rs:
            what = "그림" if r["kind"] == "keyframe" else "클립"
            print(f"{'✓' if not r['issues'] else '✗'} {s['id']} {what}: {r['file']} · {r['size'][0]}×{r['size'][1]}" + (f" · {r['dur']}초" if r.get("dur") else ""))
            for i, fx in zip(r["issues"], r["fixes"]):
                bad += 1
                print(f"    - {i}\n      → 프롬프트에: {fx}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
