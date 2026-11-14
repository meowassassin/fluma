#!/usr/bin/env python3
"""파이프라인 3단계 — 샷별 키 프레임(나노 바나나) · 사용자 승인 ②(화풍 · 캐릭터 · 배경).
승인된 키 프레임이 4단계의 **시작 프레임**이 된다. 캐릭터는 이 그림 안에 그려 넣는다 —
Veo · Flow 는 시작 프레임과 캐릭터 참조를 한 요청에 같이 받지 못해서, 4단계는 시작 프레임만 넘긴다(사용자 결정 2026-11-11).

참조(조사): 샷 각도에 가장 가까운 시트 그림 + 정면(정체 기준), 캐릭터마다. 나노 바나나 캐릭터 참조 상한 4장(Pro 5) 안에서.
끝 프레임(end_frame: true 인 샷만): 시작 프레임을 Image 1 로 붙여 '같은 장면 · 같은 카메라, 끝 상태만 다르게'.

  python3 engine/gen/keyframe.py make <plan id> [--shots 1,3] [--candidates 2] [--model flash]
  python3 engine/gen/keyframe.py pick <plan id> <샷> <후보 번호>
  python3 engine/gen/keyframe.py sheet <plan id>                     # 승인용 한 장(샷 번호 · 목적 · 길이)
  python3 engine/gen/keyframe.py approve <plan id> [--shots 1,2]      # 승인 ② — 사용자가 승인한 샷만
  python3 engine/gen/keyframe.py status <plan id>
파일: data/compositions/<plan id>/keyframes/s<NN>.png(시작) · s<NN>_end.png(끝) · keyframes.json(프롬프트 · 참조 · 승인)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402
import character as charmod  # noqa: E402
import image as imagegen  # noqa: E402
import plan as planmod  # noqa: E402

MAX_CHAR_REFS = 4


def live_shots(sb: dict) -> list[dict]:
    """키 프레임이 필요한 샷 — 모션그래픽(kind=motion)은 레퍼런스 그림으로 바로 생성하므로 뺀다"""
    return [s for s in sb["shots"] if s.get("kind") != "motion"]


def kdir(pid: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "keyframes"


def load_meta(pid: str) -> dict:
    p = kdir(pid) / "keyframes.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"shots": {}}


def save_meta(pid: str, m: dict) -> None:
    kdir(pid).mkdir(parents=True, exist_ok=True)
    (kdir(pid) / "keyframes.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), "utf-8")


def nearest_view(s: dict) -> str:
    """샷의 피사체 방향 → 가장 가까운 시트 그림(조사: 뒷모습이면 back)"""
    t = (s.get("subject_pos") or "") + " " + (s.get("start_state") or "")
    if re.search(r"(?i)facing away|from behind|back to (the )?camera|back view", t):
        return "back"
    if re.search(r"(?i)facing (screen|camera)[- ]left|profile.*left|looks? (screen|camera)[- ]left", t):
        return "left"
    if re.search(r"(?i)facing (screen|camera)[- ]right|profile.*right|looks? (screen|camera)[- ]right", t):
        return "right"
    return "front"


def refs_for(pid: str, sb: dict, s: dict) -> list[tuple[Path, str]]:
    out = []
    d_kf = kdir(pid)
    shot_n = s["n"]
    # 1) ArtCraft 식 2D 캔버스 합성 · 마스크 가이드 또는 3D Stage Previz 가 있으면 구도/인페인팅 참조로 먼저 넣는다
    mask_f = d_kf / f"s{shot_n:02d}_mask.png"
    base_f = d_kf / f"s{shot_n:02d}.png"
    comp_f = d_kf / f"s{shot_n:02d}_compose.png"
    stage_f = d_kf / f"s{shot_n:02d}_stage.png"
    if mask_f.exists() and base_f.exists():
        out.append((base_f, "current shot frame — keep everything in the black mask areas identical"))
        out.append((mask_f, "inpaint mask (white = region to modify or regenerate, black = region to keep untouched)"))
    elif comp_f.exists():
        out.append((comp_f, "2D canvas composite layout guide — follow this exact spatial arrangement, pose and framing"))
    if stage_f.exists():
        out.append((stage_f, "3D stage previz camera & blocking guide — match this camera angle, perspective, subject placement and depth"))
    for name in s.get("characters") or []:
        d = charmod.cdir(pid, name)
        v = nearest_view(s)
        for view in dict.fromkeys(["front", v]):
            f = d / f"{view}.png"
            if f.exists():
                out.append((f, f"{name}, {view} view from the approved character sheet — identity, hairstyle, wardrobe and colours to preserve"))
    return out[:MAX_CHAR_REFS]


def shot_hash(sb: dict, s: dict, files: list[Path], refs: list[tuple[Path, str]]) -> str:
    h = hashlib.sha256(planmod.keyframe_prompt(sb, s, [r for _, r in refs]).encode())
    for f in files + [p for p, _ in refs]:
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()[:16]


def end_prompt(sb: dict, s: dict) -> str:
    return ("Image 1 is the approved first frame of this shot. Generate the LAST frame of the same shot: the same scene, characters, wardrobe, "
            "lighting, colours and art style exactly as in Image 1, framed from the same camera position"
            + ("" if s["camera_move"] == "locked-off" else f" after a {s['camera_move']}") +
            f". Only this changes: {s['end_state'].rstrip('.')}. A single still frame. No text, letters, captions or logos anywhere in the image.")


def check_sheets(pid: str, sb: dict, shots: list[dict]) -> list[str]:
    bad = []
    st = {r["name"]: r["state"] for r in charmod.status(pid)} if sb.get("needs_character") else {}
    for n in sorted({c for s in shots for c in s.get("characters") or []}):
        if st.get(n) != "승인":
            bad.append(f"{n}: 캐릭터 시트 {st.get(n, '없음')} — 2단계 승인 ① 먼저")
    return bad


def make(pid: str, shots: list[int] | None, candidates: int, model: str, force: bool = False) -> dict:
    _, sb = planmod.load(pid)
    errs, _ = planmod.problems(sb)
    if errs:
        fail("keyframe", stage="keyframe", error="샷 계획 검사 실패 — plan.py check 부터: " + " / ".join(errs[:3]))
    all_live = live_shots(sb)
    d = kdir(pid); d.mkdir(parents=True, exist_ok=True)
    todo = [s for s in all_live if not shots or s["n"] in shots]
    # --shots 없이 호출했을 때 일부 샷만 이미 생성되어 있다면 누락된 샷만 이어서 생성(쿼터 낭비 방지)
    if not shots and not force and candidates == 1:
        missing = [s for s in todo if not (d / f"s{s['n']:02d}.png").exists()]
        if missing:
            todo = missing
    bad = check_sheets(pid, sb, todo)
    if bad:
        fail("keyframe", stage="keyframe", error=" / ".join(bad))
    m = load_meta(pid)
    jobs = []
    for s in todo:
        refs = refs_for(pid, sb, s)
        pr = planmod.keyframe_prompt(sb, s, [r for _, r in refs])
        outs = [d / (f"s{s['n']:02d}.png" if candidates == 1 else f"s{s['n']:02d}_c{i + 1}.png") for i in range(candidates)]
        jobs += [(s, o, pr, refs) for o in outs]
    made, errors = [], []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [(s, o, ex.submit(imagegen.generate, o, pr, refs, sb["aspect"], model)) for s, o, pr, refs in jobs]
        for s, o, f in futs:
            try:
                meta = f.result(); made.append(o.name)
                rec = m["shots"].setdefault(str(s["n"]), {})
                if candidates == 1:
                    rec["first"] = meta; rec.pop("end", None) if s.get("end_frame") else None
                else:
                    rec.setdefault("candidates", [])
                    rec["candidates"] = [x for x in rec["candidates"] if x["path"] != meta["path"]] + [meta]
                rec["approval"] = None
            except imagegen.ImageGenError as e:
                errors.append(f"s{s['n']:02d} {o.name}: {e}")
    if candidates == 1:                       # 끝 프레임 — 시작 프레임이 생긴 샷만
        ends = [s for s in todo if s.get("end_frame") and (d / f"s{s['n']:02d}.png").exists()]
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = [(s, ex.submit(imagegen.generate, d / f"s{s['n']:02d}_end.png", end_prompt(sb, s),
                                  [(d / f"s{s['n']:02d}.png", "approved first frame of this shot — keep everything identical except the end state")], sb["aspect"], model)) for s in ends]
            for s, f in futs:
                try:
                    m["shots"][str(s["n"])]["end"] = f.result(); made.append(f"s{s['n']:02d}_end.png")
                except imagegen.ImageGenError as e:
                    errors.append(f"s{s['n']:02d} 끝 프레임: {e}")
    m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_meta(pid, m)
    warns = [f"s{k}: {v['first']['warn']}" for k, v in m["shots"].items() if (v.get("first") or {}).get("warn")]
    return {"made": made, "errors": errors, "warns": warns}


def files_of(pid: str, s: dict) -> list[Path]:
    """승인 대상은 생성된 키 프레임(sNN.png)뿐 — 무대(_stage) · 캔버스(_compose)는 make 의 구도 참고(refs_for)로만 쓴다.
    가이드를 시작 프레임으로 쓰면 회색 격자 · 색 상자가 그대로 영상이 된다(2026-11-14 USB 포코 사례)."""
    d = kdir(pid)
    return [d / f"s{s['n']:02d}.png"] + ([d / f"s{s['n']:02d}_end.png"] if s.get("end_frame") else [])


def status(pid: str) -> list[dict]:
    _, sb = planmod.load(pid)
    m = load_meta(pid)
    d = kdir(pid)
    rows = []
    for s in live_shots(sb):
        n = s["n"]
        rec = m["shots"].get(str(n), {})
        fs = files_of(pid, s)
        have = all(f.exists() for f in fs)
        ap = rec.get("approval")
        cur = shot_hash(sb, s, fs, refs_for(pid, sb, s)) if have else None
        st = "없음" if not fs[0].exists() else ("승인" if ap and ap.get("hash") == cur else ("승인 무효(입력이 바뀜)" if ap else ("만듦 · 승인 대기" if have else "끝 프레임 없음")))
        rows.append({
            "shot": n,
            "purpose": s["purpose"],
            "state": st,
            "candidates": [Path(x["path"]).name for x in rec.get("candidates") or []],
            "has_mask": (d / f"s{n:02d}_mask.png").exists(),
            "has_compose": (d / f"s{n:02d}_compose.png").exists(),
            "has_stage": (d / f"s{n:02d}_stage.png").exists(),
        })
    return rows


MANNEQUIN_PRESETS: dict[str, dict[str, float]] = {
    "stand": {"bodyYaw": 0, "torsoLean": 0, "headYaw": 0, "headPitch": 0, "lShoulderPitch": 8, "lShoulderRoll": 12, "lElbowBend": 15, "rShoulderPitch": 8, "rShoulderRoll": 12, "rElbowBend": 15, "lHipPitch": 0, "lKneeBend": 4, "rHipPitch": 0, "rKneeBend": 4},
    "wave": {"bodyYaw": -10, "torsoLean": -4, "headYaw": 10, "headPitch": -6, "lShoulderPitch": 10, "lShoulderRoll": 14, "lElbowBend": 18, "rShoulderPitch": 135, "rShoulderRoll": 35, "rElbowBend": 55, "lHipPitch": -4, "lKneeBend": 6, "rHipPitch": 6, "rKneeBend": 4},
    "point": {"bodyYaw": 15, "torsoLean": 8, "headYaw": -12, "headPitch": 0, "lShoulderPitch": 15, "lShoulderRoll": 15, "lElbowBend": 25, "rShoulderPitch": 92, "rShoulderRoll": 5, "rElbowBend": 8, "lHipPitch": 12, "lKneeBend": 8, "rHipPitch": -12, "rKneeBend": 10},
    "run": {"bodyYaw": 0, "torsoLean": 24, "headYaw": 0, "headPitch": -10, "lShoulderPitch": 65, "lShoulderRoll": 15, "lElbowBend": 85, "rShoulderPitch": -45, "rShoulderRoll": 15, "rElbowBend": 75, "lHipPitch": -45, "lKneeBend": 65, "rHipPitch": 55, "rKneeBend": 25},
    "sit": {"bodyYaw": 0, "torsoLean": 10, "headYaw": 0, "headPitch": 5, "lShoulderPitch": 28, "lShoulderRoll": 12, "lElbowBend": 65, "rShoulderPitch": 28, "rShoulderRoll": 12, "rElbowBend": 65, "lHipPitch": 88, "lKneeBend": 88, "rHipPitch": 88, "rKneeBend": 88},
    "cheer": {"bodyYaw": 0, "torsoLean": -10, "headYaw": 0, "headPitch": -15, "lShoulderPitch": 155, "lShoulderRoll": 28, "lElbowBend": 25, "rShoulderPitch": 155, "rShoulderRoll": 28, "rElbowBend": 25, "lHipPitch": -8, "lKneeBend": 12, "rHipPitch": 8, "rKneeBend": 12},
    "phone": {"bodyYaw": -8, "torsoLean": 12, "headYaw": -5, "headPitch": 26, "lShoulderPitch": 12, "lShoulderRoll": 10, "lElbowBend": 20, "rShoulderPitch": 58, "rShoulderRoll": -15, "rElbowBend": 95, "lHipPitch": 0, "lKneeBend": 5, "rHipPitch": 0, "rKneeBend": 5},
}


def compute_mannequin_joints(obj: dict) -> dict[str, tuple[float, float, float]]:
    """오브젝트 위치(x,y,z) · 스케일(h) · 포즈 각도(pose)로부터 15개 인체 3D 관절 좌표를 계산한다."""
    import math
    ox, oy, oz = float(obj.get("x", 0.0)), float(obj.get("y", 0.0)), float(obj.get("z", 0.0))
    scale = float(obj.get("h", 1.75)) / 1.75
    preset_name = str(obj.get("posePreset") or "stand")
    pose = {**MANNEQUIN_PRESETS.get(preset_name, MANNEQUIN_PRESETS["stand"]), **(obj.get("pose") or {})}

    byaw = math.radians(float(pose.get("bodyYaw", 0.0)))
    lean = math.radians(float(pose.get("torsoLean", 0.0)))
    hyaw = math.radians(float(pose.get("headYaw", 0.0)))
    hpitch = math.radians(float(pose.get("headPitch", 0.0)))

    def rot_y(v: tuple[float, float, float], a: float) -> tuple[float, float, float]:
        c, s = math.cos(a), math.sin(a)
        return (v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c)

    def add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    # 골반 높이 (앉은 자세면 낮춤)
    hip_pitch_avg = 0.5 * (float(pose.get("lHipPitch", 0.0)) + float(pose.get("rHipPitch", 0.0)))
    pelvis_y = oy + (0.58 if hip_pitch_avg > 60 else 0.92) * scale
    pelvis = (ox, pelvis_y, oz)

    # 척추/가슴/목/머리
    torso_len = 0.48 * scale
    chest_local = rot_y((0.0, torso_len * math.cos(lean), torso_len * math.sin(lean)), byaw)
    chest = add(pelvis, chest_local)
    neck = add(chest, rot_y((0.0, 0.12 * scale, 0.02 * scale * math.sin(lean)), byaw))
    head_dir = rot_y((0.0, 0.16 * scale * math.cos(hpitch), 0.16 * scale * math.sin(hpitch)), byaw + hyaw)
    head = add(neck, head_dir)

    # 어깨 & 팔
    sh_w = 0.21 * scale
    u_arm, l_arm = 0.28 * scale, 0.26 * scale

    def arm_chain(side: int, sp_deg: float, sr_deg: float, eb_deg: float):
        sh = add(chest, rot_y((side * sh_w, 0.04 * scale, 0.0), byaw))
        sp, sr = math.radians(sp_deg), math.radians(sr_deg)
        # 기본 아래 방향(0, -1, 0)에서 앞(+z)으로 pitch, 바깥(side*x)으로 roll
        ux = side * math.sin(sr) * math.cos(sp * 0.3)
        uy = -math.cos(sp) * math.cos(sr)
        uz = math.sin(sp)
        ul = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
        ux, uy, uz = ux / ul, uy / ul, uz / ul
        elbow = add(sh, rot_y((ux * u_arm, uy * u_arm, uz * u_arm), byaw))
        tot_p = sp + math.radians(eb_deg)
        fx = side * math.sin(sr * 0.7) * 0.6
        fy = -math.cos(tot_p) * math.cos(sr * 0.5)
        fz = math.sin(tot_p)
        fl = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
        fx, fy, fz = fx / fl, fy / fl, fz / fl
        hand = add(elbow, rot_y((fx * l_arm, fy * l_arm, fz * l_arm), byaw))
        return sh, elbow, hand

    l_sh, l_el, l_ha = arm_chain(-1, float(pose.get("lShoulderPitch", 8)), float(pose.get("lShoulderRoll", 12)), float(pose.get("lElbowBend", 15)))
    r_sh, r_el, r_ha = arm_chain(1, float(pose.get("rShoulderPitch", 8)), float(pose.get("rShoulderRoll", 12)), float(pose.get("rElbowBend", 15)))

    # 엉덩이 & 다리
    hip_w = 0.11 * scale
    u_leg, l_leg = 0.44 * scale, 0.44 * scale

    def leg_chain(side: int, hp_deg: float, kb_deg: float):
        hip = add(pelvis, rot_y((side * hip_w, 0.0, 0.0), byaw))
        hp, kb = math.radians(hp_deg), math.radians(kb_deg)
        tx, ty, tz = side * 0.03, -math.cos(hp), math.sin(hp)
        knee = add(hip, rot_y((tx * u_leg, ty * u_leg, tz * u_leg), byaw))
        ank_p = hp - kb
        cx_, cy_, cz_ = side * 0.02, -math.cos(ank_p), math.sin(ank_p)
        ankle = add(knee, rot_y((cx_ * l_leg, cy_ * l_leg, cz_ * l_leg), byaw))
        return hip, knee, ankle

    l_hip, l_kn, l_ank = leg_chain(-1, float(pose.get("lHipPitch", 0)), float(pose.get("lKneeBend", 4)))
    r_hip, r_kn, r_ank = leg_chain(1, float(pose.get("rHipPitch", 0)), float(pose.get("rKneeBend", 4)))

    return {
        "pelvis": pelvis, "chest": chest, "neck": neck, "head": head,
        "lShoulder": l_sh, "lElbow": l_el, "lHand": l_ha,
        "rShoulder": r_sh, "rElbow": r_el, "rHand": r_ha,
        "lHip": l_hip, "lKnee": l_kn, "lAnkle": l_ank,
        "rHip": r_hip, "rKnee": r_kn, "rAnkle": r_ank,
    }


def render_stage3d(pid: str, shot: int, spec: dict) -> Path:
    """3D Stage Previz — 관절 마네킹(포즈) + 소품 + 카메라(yaw · pitch · dist · fov)를 고속 투영해 s<NN>_stage.png 로 저장한다."""
    import math
    from PIL import Image, ImageDraw, ImageFont
    _, sb = planmod.load(pid)
    W, H = (1080, 1920) if sb.get("aspect", "9:16") == "9:16" else ((1920, 1080) if sb.get("aspect") == "16:9" else (1080, 1080))
    d = kdir(pid); d.mkdir(parents=True, exist_ok=True)
    out = d / f"s{shot:02d}_stage.png"

    cam = spec.get("camera") or {}
    yaw = math.radians(float(cam.get("yaw", 25.0)))
    pitch = math.radians(float(cam.get("pitch", 18.0)))
    dist = max(2.0, float(cam.get("dist", 6.5)))
    fov = math.radians(max(20.0, min(110.0, float(cam.get("fov", 50.0)))))
    target = [float(x) for x in (cam.get("target") or [0.0, 0.85, 0.0])[:3]]

    # 카메라 위치 및 정규 직교 기저
    cx = target[0] + dist * math.cos(pitch) * math.sin(yaw)
    cy = target[1] + dist * math.sin(pitch)
    cz = target[2] + dist * math.cos(pitch) * math.cos(yaw)
    fx, fy, fz = target[0] - cx, target[1] - cy, target[2] - cz
    fl = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
    fx, fy, fz = fx / fl, fy / fl, fz / fl
    rx, ry, rz = -fz, 0.0, fx
    rl = math.sqrt(rx * rx + rz * rz) or 1.0
    rx, rz = rx / rl, rz / rl
    ux = ry * fz - rz * fy
    uy = rz * fx - rx * fz
    uz = rx * fy - ry * fx

    focal = (min(W, H) * 0.5) / math.tan(fov * 0.5)

    def project(pt: tuple[float, float, float]) -> tuple[float, float, float] | None:
        dx, dy, dz = pt[0] - cx, pt[1] - cy, pt[2] - cz
        z = dx * fx + dy * fy + dz * fz
        if z <= 0.15:
            return None
        x = dx * rx + dy * ry + dz * rz
        y = dx * ux + dy * uy + dz * uz
        return (W * 0.5 + (x / z) * focal, H * 0.5 - (y / z) * focal, z)

    im = Image.new("RGB", (W, H), (20, 22, 28))
    dr = ImageDraw.Draw(im, "RGBA")

    # 지평선 바닥 그리드
    for g in range(-4, 5):
        p1, p2 = project((g * 1.0, 0.0, -4.0)), project((g * 1.0, 0.0, 4.0))
        if p1 and p2:
            dr.line([(p1[0], p1[1]), (p2[0], p2[1])], fill=(70, 80, 100, 140), width=2)
        q1, q2 = project((-4.0, 0.0, g * 1.0)), project((4.0, 0.0, g * 1.0))
        if q1 and q2:
            dr.line([(q1[0], q1[1]), (q2[0], q2[1])], fill=(70, 80, 100, 140), width=2)

    objs = spec.get("objects") or [
        {"label": "Subject", "kind": "character", "x": 0.0, "y": 0.0, "z": 0.0, "w": 0.9, "h": 1.75, "d": 0.6, "color": "#6366f1"},
    ]
    draw_cmds = []  # (avg_z, fn)
    import numpy as np

    for obj in objs:
        col = str(obj.get("color") or "#6366f1").lstrip("#")
        rgb = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4)) if len(col) == 6 else (99, 102, 241)
        if obj.get("kind", "character") == "character":
            ox, oy, oz = float(obj.get("x", 0.0)), float(obj.get("y", 0.0)), float(obj.get("z", 0.0))
            oh = float(obj.get("h", 1.75))

            # 발밑 3D 스테이지 원형 받침대 (Stage ring / disc)
            pedestal_pts = []
            for deg in range(0, 360, 24):
                rad = math.radians(deg)
                pedestal_pts.append((ox + 0.45 * math.cos(rad), oy + 0.005, oz + 0.45 * math.sin(rad)))
            pj_ped = [project(p) for p in pedestal_pts]
            if all(p is not None for p in pj_ped):
                poly = [(p[0], p[1]) for p in pj_ped if p is not None]
                draw_cmds.append((oz + 0.01, lambda poly=poly: dr.polygon(poly, fill=(99, 102, 241, 65), outline=(129, 140, 248, 180))))

            # 2D 캐릭터 4방향 시트 -> 3D 빌보드 투영
            char_name = obj.get("character") or str(obj.get("label", "")).split()[0]
            cdir_char = ROOT / "data" / "compositions" / pid / "characters" / char_name
            if not cdir_char.exists():
                chars_dir = ROOT / "data" / "compositions" / pid / "characters"
                if chars_dir.exists():
                    subdirs = [d for d in chars_dir.iterdir() if d.is_dir()]
                    if subdirs:
                        cdir_char = subdirs[0]

            cam_yaw_deg = float(cam.get("yaw", 25.0))
            body_yaw = float((obj.get("pose") or {}).get("bodyYaw", 0.0))
            rel_yaw = ((cam_yaw_deg - body_yaw) % 360 + 360) % 360

            if 45 <= rel_yaw < 135:
                view_name = "left"
            elif 135 <= rel_yaw < 225:
                view_name = "back"
            elif 225 <= rel_yaw < 315:
                view_name = "right"
            else:
                view_name = "front"

            view_path = cdir_char / f"{view_name}.png"
            if not view_path.exists() and (cdir_char / "front.png").exists():
                view_path = cdir_char / "front.png"

            texture_drawn = False
            if view_path.exists():
                try:
                    cimg = Image.open(view_path).convert("RGB")
                    carr = np.array(cimg, dtype=np.float32)
                    bg = carr[5, 5]
                    dist_bg = np.linalg.norm(carr - bg, axis=2)
                    alpha = np.clip((dist_bg - 10.0) / 15.0 * 255.0, 0, 255).astype(np.uint8)
                    rgba = np.dstack([carr.astype(np.uint8), alpha])
                    cutout = Image.fromarray(rgba, "RGBA")

                    pt_btm = project((ox, oy, oz))
                    pt_top = project((ox, oy + oh, oz))
                    if pt_btm and pt_top:
                        h_px = int(abs(pt_btm[1] - pt_top[1]))
                        if h_px > 10:
                            aspect = cutout.width / cutout.height
                            w_px = max(6, int(h_px * aspect))
                            resized_cutout = cutout.resize((w_px, h_px), Image.Resampling.LANCZOS)
                            left_px = int(pt_btm[0] - w_px * 0.5)
                            top_px = int(pt_top[1])
                            avg_z = (pt_btm[2] + pt_top[2]) * 0.5

                            def draw_billboard(img=resized_cutout, x=left_px, y=top_px):
                                im.paste(img, (x, y), img)
                            draw_cmds.append((avg_z, draw_billboard))
                            texture_drawn = True
                except Exception:
                    pass

            if not texture_drawn:
                joints = compute_mannequin_joints(obj)
                pjoints = {k: project(v) for k, v in joints.items()}
                if not any(v is None for v in pjoints.values()):
                    pj = {k: v for k, v in pjoints.items() if v is not None}
                    limbs = [
                        ("pelvis", "chest", 0.12, 1.0),
                        ("chest", "neck", 0.06, 0.95),
                        ("lShoulder", "rShoulder", 0.065, 0.95),
                        ("lHip", "rHip", 0.065, 0.9),
                        ("lShoulder", "lElbow", 0.055, 0.92),
                        ("lElbow", "lHand", 0.046, 1.05),
                        ("rShoulder", "rElbow", 0.055, 0.92),
                        ("rElbow", "rHand", 0.046, 1.05),
                        ("lHip", "lKnee", 0.068, 0.85),
                        ("lKnee", "lAnkle", 0.054, 0.95),
                        ("rHip", "rKnee", 0.068, 0.85),
                        ("rKnee", "rAnkle", 0.054, 0.95),
                    ]
                    for a, b, rad_m, shade in limbs:
                        pa, pb = pj[a], pj[b]
                        avg_z = (pa[2] + pb[2]) * 0.5
                        w_px = max(4, int((rad_m * 2.0 / avg_z) * focal))
                        lcol = tuple(min(255, int(c * shade)) for c in rgb) + (240,)
                        draw_cmds.append((avg_z, lambda pa=pa, pb=pb, w_px=w_px, lcol=lcol: dr.line([(pa[0], pa[1]), (pb[0], pb[1])], fill=lcol, width=w_px)))
                    for k, pt in pj.items():
                        rad_m = 0.125 if k == "head" else (0.09 if k in ("chest", "pelvis") else 0.052)
                        r_px = max(3, int((rad_m / pt[2]) * focal))
                        jcol = (rgb + (255,)) if k in ("head", "chest", "pelvis") else (240, 244, 255, 255)
                        draw_cmds.append((pt[2] - 0.02, lambda pt=pt, r_px=r_px, jcol=jcol, rgb=rgb: dr.ellipse([pt[0] - r_px, pt[1] - r_px, pt[0] + r_px, pt[1] + r_px], fill=jcol, outline=rgb + (255,), width=2)))
        else:
            ox, oy, oz = float(obj.get("x", 0.0)), float(obj.get("y", 0.0)), float(obj.get("z", 0.0))
            ow, oh, od = float(obj.get("w", 0.9)) * 0.5, float(obj.get("h", 1.0)), float(obj.get("d", 0.6)) * 0.5
            verts = [
                (ox - ow, oy, oz - od), (ox + ow, oy, oz - od), (ox + ow, oy + oh, oz - od), (ox - ow, oy + oh, oz - od),
                (ox - ow, oy, oz + od), (ox + ow, oy, oz + od), (ox + ow, oy + oh, oz + od), (ox - ow, oy + oh, oz + od),
            ]
            pverts = [project(v) for v in verts]
            if any(v is None for v in pverts):
                continue
            quads = [([4, 5, 6, 7], 1.0), ([0, 1, 2, 3], 0.65), ([0, 4, 7, 3], 0.8), ([1, 5, 6, 2], 0.85), ([3, 2, 6, 7], 1.12)]
            for idxs, shade in quads:
                pts = [(pverts[i][0], pverts[i][1]) for i in idxs]  # type: ignore[index]
                avg_z = sum(pverts[i][2] for i in idxs) / 4.0       # type: ignore[index]
                fill = tuple(min(255, int(c * shade)) for c in rgb) + (215,)
                draw_cmds.append((avg_z, lambda pts=pts, fill=fill, rgb=rgb: dr.polygon(pts, fill=fill, outline=rgb + (255,))))

    draw_cmds.sort(key=lambda x: -x[0])
    for _, fn in draw_cmds:
        fn()

    if spec.get("hud"):
        try:
            font = ImageFont.truetype(str(ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf"), 28)
        except OSError:
            font = ImageFont.load_default()
        for obj in objs:
            ox, oy, oz = float(obj.get("x", 0.0)), float(obj.get("y", 0.0)), float(obj.get("z", 0.0))
            oh = float(obj.get("h", 1.75))
            top_pt = project((ox, oy + oh + 0.18, oz))
            if top_pt and obj.get("label"):
                dr.text((top_pt[0] - 36, top_pt[1] - 18), str(obj["label"]), font=font, fill=(255, 255, 255, 240))

    im.save(out)
    (d / f"s{shot:02d}_stage.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), "utf-8")
    return out


def auto_stage_spec(sb: dict, s: dict) -> dict:
    """샷 계획(shotplan)의 지시문(shot_size · angle · camera_move · subject_pos · start_state)을 분석하여
    3D 가상 무대의 카메라(yaw · pitch · dist · fov · target)와 배치 오브젝트(캐릭터 · 소품)를 자동 구성한다."""
    angle_str = str(s.get("angle") or "eye-level").lower()
    size_str = str(s.get("shot_size") or "medium close-up").lower()
    pos_str = str(s.get("subject_pos") or "").lower()
    start_str = str(s.get("start_state") or "").lower()

    # 카메라 피치 (각도) 및 타깃 Y
    if any(k in angle_str for k in ("low", "worm", "bottom-up", "upward")):
        pitch = -16.0
        target_y = 1.05
    elif any(k in angle_str for k in ("high", "bird", "top-down", "downward")):
        pitch = 30.0
        target_y = 0.70
    elif "overhead" in angle_str:
        pitch = 70.0
        target_y = 0.50
    else:  # eye-level
        pitch = 12.0
        target_y = 0.85

    # 카메라 거리 및 화각 (샷 크기)
    if any(k in size_str for k in ("extreme close", "macro", "ecu")):
        dist = 3.0
        fov = 38.0
    elif "close" in size_str:
        dist = 4.2
        fov = 42.0
    elif "medium close" in size_str:
        dist = 5.2
        fov = 46.0
    elif "medium" in size_str:
        dist = 6.4
        fov = 50.0
    elif any(k in size_str for k in ("wide", "long", "full")):
        dist = 8.5
        fov = 55.0
    else:
        dist = 5.5
        fov = 48.0

    # 카메라 요(yaw) — 피사체 위치에 따라
    if "left" in pos_str:
        yaw = 28.0
    elif "right" in pos_str:
        yaw = -28.0
    else:
        yaw = 18.0

    cam = {
        "yaw": yaw,
        "pitch": pitch,
        "dist": dist,
        "fov": fov,
        "target": [0.0, target_y, 0.0],
    }

    # 포즈 프리셋 추출
    pose_preset = "stand"
    if any(k in start_str for k in ("sit", "sitting")):
        pose_preset = "sit"
    elif any(k in start_str for k in ("run", "running", "chase")):
        pose_preset = "run"
    elif any(k in start_str for k in ("walk", "walking")):
        pose_preset = "stand"
    elif any(k in start_str for k in ("wave", "waving", "greet")):
        pose_preset = "wave"
    elif any(k in start_str for k in ("hold", "grip", "push", "reach", "pull")):
        pose_preset = "point"

    pose_dict = dict(MANNEQUIN_PRESETS.get(pose_preset, MANNEQUIN_PRESETS["stand"]))

    # 캐릭터 오브젝트 배치
    objs = []
    chars = s.get("characters") or []
    all_chars = sb.get("characters") or []

    for i, cname in enumerate(chars or ["Character"]):
        cinfo = next((c for c in all_chars if c.get("name") == cname), {})
        ident = (cinfo.get("identity") or "").lower()
        is_small = any(k in ident for k in ("tiny", "small", "hamster", "creature", "chibi", "little"))

        w = 0.85
        h = 1.35 if is_small else 1.75
        d_val = 0.55 if is_small else 0.60
        x_offset = (i - (len(chars) - 1) / 2.0) * 1.5 if len(chars) > 1 else 0.0

        objs.append({
            "id": f"obj-char-{i+1}",
            "kind": "character",
            "character": cname,
            "label": f"{cname} (주인공)",
            "x": x_offset,
            "y": 0.0,
            "z": 0.0,
            "w": w,
            "h": h,
            "d": d_val,
            "color": "#6366f1",
            "posePreset": pose_preset,
            "pose": pose_dict,
        })

    # 소품 (props) 추출
    if any(k in start_str for k in ("port", "usb", "block", "box", "desk", "table", "wrench", "device", "lever")):
        objs.append({
            "id": "obj-prop-1",
            "kind": "prop",
            "label": "소품/블록",
            "x": 0.65,
            "y": 0.35,
            "z": 0.15,
            "w": 0.70,
            "h": 0.50,
            "d": 0.60,
            "color": "#f59e0b",
        })

    return {
        "camera": cam,
        "objects": objs,
    }


def auto_stage(pid: str, sel: list[int] | None = None) -> dict:
    """무대 구도 가이드만 그린다 — 승인하지 않는다(승인 ②는 make 로 만든 키 프레임을 사용자가 보고)."""
    _, sb = planmod.load(pid)
    made = []
    shots = [s for s in live_shots(sb) if not sel or s["n"] in sel]
    if not shots:
        fail("keyframe", stage="auto-stage", error="3D 무대 구도를 생성할 샷이 없습니다")
    for s in shots:
        render_stage3d(pid, s["n"], auto_stage_spec(sb, s))
        made.append(s["n"])
    return {"made": made}


def sheet_png(pid: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    _, sb = planmod.load(pid)
    d = kdir(pid)
    tiles = []
    for s in live_shots(sb):
        for f, tag in zip(files_of(pid, s), ("", " 끝")):
            im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (540, 960), (60, 60, 60))
            tiles.append((f"#{s['n']}{tag} {s['purpose']} {s['final_sec']:g}s/{s['gen_sec']}s", im.resize((360, int(im.height * 360 / im.width)))))
    th = max(t.height for _, t in tiles) + 60
    cols = min(6, len(tiles)); rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 380 + 20, rows * th + 20), (30, 30, 30)); dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf"), 26)
    except OSError:
        font = ImageFont.load_default()
    for i, (lab, im) in enumerate(tiles):
        x, y = 20 + (i % cols) * 380, 20 + (i // cols) * th
        dr.text((x, y), lab, font=font, fill=(240, 240, 240)); sheet.paste(im, (x, y + 44))
    out = d / "sheet.png"; d.mkdir(parents=True, exist_ok=True); sheet.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    mk = sp.add_parser("make"); mk.add_argument("pid"); mk.add_argument("--shots"); mk.add_argument("--candidates", type=int, default=1); mk.add_argument("--model", default="flash"); mk.add_argument("--force", action="store_true")
    pk = sp.add_parser("pick"); pk.add_argument("pid"); pk.add_argument("shot", type=int); pk.add_argument("n", type=int)
    sh = sp.add_parser("sheet"); sh.add_argument("pid")
    apv = sp.add_parser("approve"); apv.add_argument("pid"); apv.add_argument("--shots")
    st = sp.add_parser("status"); st.add_argument("pid")
    s3d = sp.add_parser("stage3d"); s3d.add_argument("pid"); s3d.add_argument("shot", type=int); s3d.add_argument("--spec", default="{}")
    ast = sp.add_parser("auto-stage"); ast.add_argument("pid"); ast.add_argument("--shots")
    clr = sp.add_parser("clear-guide"); clr.add_argument("pid"); clr.add_argument("shot", type=int); clr.add_argument("--kind", default="all")
    a = ap.parse_args()
    sel = [int(x) for x in a.shots.split(",")] if getattr(a, "shots", None) else None
    if a.cmd == "auto-stage":
        res = auto_stage(a.pid, sel)
        shots_arg = ",".join(map(str, res["made"]))
        ok("keyframe", stage="auto-stage", made=shots_arg,
           next=f"무대 구도는 가이드일 뿐 — keyframe.py make {a.pid} --shots {shots_arg} 로 키 프레임을 만들고 사용자 승인 ② 뒤 4단계")
        return 0
    if a.cmd == "stage3d":
        spec = json.loads(Path(a.spec).read_text("utf-8")) if Path(a.spec).is_file() else json.loads(a.spec or "{}")
        out = render_stage3d(a.pid, a.shot, spec)
        ok("keyframe", stage3d=str(out.relative_to(ROOT)), next=f"keyframe.py make {a.pid} --shots {a.shot} 로 3D 구도 가이드를 반영해 생성")
        return 0
    if a.cmd == "clear-guide":
        d = kdir(a.pid)
        targets = ["mask", "compose", "stage"] if a.kind == "all" else [a.kind]
        removed = []
        for k in targets:
            for ext in (".png", ".json"):
                f = d / f"s{a.shot:02d}_{k}{ext}"
                if f.exists():
                    f.unlink(); removed.append(f.name)
        ok("keyframe", cleared=",".join(removed) or "없음")
        return 0
    if a.cmd == "make":
        r = make(a.pid, sel, a.candidates, a.model, getattr(a, "force", False))
        sheet = sheet_png(a.pid) if a.candidates == 1 else None
        for w in r["warns"]:
            print(f"△ {w}")
        if r["errors"]:
            fail("keyframe", stage="make", error=" / ".join(r["errors"]), made=",".join(r["made"]))
        ok("keyframe", made=",".join(r["made"]), sheet=str(sheet.relative_to(ROOT)) if sheet else "",
           next="승인용 그림을 보여 주고 샷별로 승인 ② 또는 그 샷만 재생성(--shots)")
        return 0
    if a.cmd == "pick":
        d = kdir(a.pid); src = d / f"s{a.shot:02d}_c{a.n}.png"
        if not src.exists():
            fail("keyframe", stage="keyframe", error=f"후보 없음: {src.name}")
        dst = d / f"s{a.shot:02d}.png"; dst.write_bytes(src.read_bytes())
        m = load_meta(a.pid); rec = m["shots"].setdefault(str(a.shot), {})
        meta = next((x for x in rec.get("candidates") or [] if Path(x["path"]).name == src.name), {})
        rec["first"] = {**meta, "path": str(dst), "picked_from": src.name}; rec["approval"] = None; rec.pop("end", None)
        save_meta(a.pid, m)
        ok("keyframe", first=str(dst.relative_to(ROOT)), next="끝 프레임이 필요한 샷이면 make --shots 로 다시(끝 프레임은 시작 프레임 기준)")
        return 0
    if a.cmd == "sheet":
        ok("keyframe", sheet=str(sheet_png(a.pid).relative_to(ROOT))); return 0
    if a.cmd == "approve":
        _, sb = planmod.load(a.pid); m = load_meta(a.pid); done = []
        for s in live_shots(sb):
            if sel and s["n"] not in sel:
                continue
            fs = files_of(a.pid, s)
            if not all(f.exists() for f in fs):
                fail("keyframe", stage="keyframe", error=f"샷 {s['n']}: 키 프레임이 아직 없다")
            m["shots"].setdefault(str(s["n"]), {})["approval"] = {"status": "approved", "hash": shot_hash(sb, s, fs, refs_for(a.pid, sb, s)), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            done.append(str(s["n"]))
        save_meta(a.pid, m)
        left = [r["shot"] for r in status(a.pid) if r["state"] != "승인"]
        ok("keyframe", approved=",".join(done), remaining=",".join(map(str, left)) or "없음",
           next="모든 샷 승인 — 4단계 영상 생성" if not left else "남은 샷 승인 또는 재생성")
        return 0
    print(json.dumps(status(a.pid), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
