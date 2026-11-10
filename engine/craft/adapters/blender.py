#!/usr/bin/env python3
"""Blender 어댑터 — 곡면 · 유기적 모양 · 캐릭터 3D. 에이전트가 영상마다 스크립트를 쓰고, 결과는 다른 재료처럼 움직임 · 소리 · 편집 단계로 이어진다.

  { "id": "bud", "type": "model3d", "method": "blender", "script": "data/compositions/<id>/src/bud.py",
    "bridge": "data/compositions/<id>/asm.json",                         # 선택: SolidCraft · TextureCraft 잇기(engine/craft/bridge3d.py) — 스크립트의 ctx.args["asm"] 폴더로 넘어간다
    "sec": 4, "fps": 24, "width": 1080, "height": 1920, "transparent": true, "args": {…},
    "quality": "fast" | "balanced" | "best",                             # 없으면 direction.render_quality, 그것도 없으면 fast (QUALITY 표)
    "ref": {"video": "<레퍼런스 id>", "at": [9.3], "me": [2.0]} }        # ref = 레퍼런스 대조(engine/checks/refmatch.py)

스크립트: def build(ctx): … (import fluma3d as F — engine/craft/blender/fluma3d.py). ctx = sec · fps · w · h · transparent · draft · args · work.
  sec 없음 또는 "still": true → 정지 PNG. 있으면 투명이면 .mov(ProRes 4444), 불투명이면 .mp4.
  스크립트는 실행 전에 검사되고(프로세스 · 네트워크 · 비밀 파일 금지, blender/host.py) Blender 안에서도 감사 훅이 막는다(guard.py).
  키 · 토큰이 없는 환경 변수로 띄운다. 스크립트는 그 영상 폴더(data/compositions/<id>/) 안만.

빠른 확인: python3 engine/craft/adapters/blender.py <스크립트> --still 0.5,2 [--width 540 --height 960] [--samples 32] [--out 폴더]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "craft" / "blender"))
import host  # noqa: E402

FONTS = ROOT / "engine" / "assets" / "fonts"
# 품질 단계 — 프레임당 시간은 8코어 CPU · 1080×1920 기준 실측(2026-11-06). 잡티 제거가 샘플을 메워 balanced 가 best 와 거의 같다
# scale: 렌더 해상도 배율(결과는 확대 · 선명화해 목표 크기로). 스크립트는 F.use_quality(ctx) 로 받는다
QUALITY = {"fast": {"engine": "eevee", "scale": 1.0, "samples": 8, "sec": 1.2,        # 기본: 영상 한 편 10분 이내. 8샘플은 32샘플과 거의 같고,
                    "eevee": {"motion_blur": True, "use_raytracing": False}},        # 레이 트레이싱을 끄면 빨라지고 표면 그림자 얼룩도 사라진다 · 모션 블러는 켬(움직임이 끊겨 보였다)
           "balanced": {"engine": "cycles", "scale": 0.5, "samples": 16, "sec": 9},  # 반사가 더 사실적 — 약 50분
           "best": {"engine": "cycles", "scale": 1.0, "samples": 32, "sec": 37}}     # 정지 컷 · 꼭 필요할 때


def _bin() -> str:
    from craft.materials import cli
    return cli("blender")


def check_script(script: Path) -> None:
    bad = []
    for f in sorted(script.parent.glob("*.py")):
        bad += [f"{f.name}:{m}" for m in host.lint(f) if f == script or "def build" not in m]
    if bad:
        raise RuntimeError("Blender 스크립트 검사에서 막힘:\n  " + "\n  ".join(bad))


def run(script: Path, out: Path, ctx: dict, stills: str = "", blend: Path | None = None, timeout: int = 7200) -> str:
    check_script(script)
    host.prefetch(script)
    e = host.env({"FL_SCRIPT": script, "FL_OUT": out, "FL_CTX": json.dumps(ctx, ensure_ascii=False), "FL_STILLS": stills, "FL_PAD": 4,
                  **({"FL_BLEND": blend} if blend else {})})
    r = subprocess.run([_bin(), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "1", "-P", str(host.LIB / "runner.py")],
                       env=e, capture_output=True, text=True, timeout=timeout, cwd=str(script.parent))
    log = r.stdout + r.stderr
    if r.returncode != 0:
        raise RuntimeError("Blender 스크립트 실패:\n" + (log[log.rfind("Traceback"):] if "Traceback" in log else log[-1500:])[-1800:])
    return log


def estimate(m: dict, sec: float) -> float:
    """예상 렌더 시간(초) — 이 컴퓨터 기준. 사용자에게 시작 전에 알린다"""
    q = QUALITY[m.get("quality") or "fast"]
    return round(sec * int(m.get("fps", 24)) * q["sec"])


def _ctx(m: dict, work: Path, sec: float) -> dict:
    q = QUALITY[m.get("quality") or "fast"]
    k = q["scale"]
    even = lambda v: int(v * k) // 2 * 2  # noqa: E731
    return {"sec": sec, "fps": int(m.get("fps", 24)), "w": even(int(m.get("width", 1080))), "h": even(int(m.get("height", 1920))), "transparent": m.get("transparent", True) is not False,
            "draft": bool(m.get("draft")), "samples": m.get("samples") or q["samples"], "engine": q["engine"], "eevee": m.get("eevee") or q.get("eevee"), "adaptive": m.get("adaptive") or q.get("adaptive"), "args": m.get("args") or {}, "work": str(work), "fonts": str(FONTS), "colors": m.get("colors") or {}, "text": m.get("text") or {}}


def ensure_bridge(spec_path: Path) -> Path:
    """SolidCraft → TextureCraft 결과를 만든다(설계 · 사양이 바뀌었을 때만) → 결과 폴더"""
    from craft import bridge3d
    if not spec_path.exists():
        raise RuntimeError(f"bridge 사양이 없습니다: {spec_path}")
    spec = json.loads(spec_path.read_text("utf-8"))
    out = ROOT / spec["out_dir"]
    glb, asm = out / "model.glb", out / "assembly.json"
    newest = max(spec_path.stat().st_mtime, (ROOT / spec["design"]).stat().st_mtime)
    if not glb.exists() or not asm.exists() or glb.stat().st_mtime < newest:
        bridge3d.build(spec)
    return out


def assemble_adaptive(fd: Path, fps: int, dst: Path) -> None:
    """적응 렌더 잇기: 전체 프레임 사이를 움직임 보간 → 물체가 움직인 영역은 실제 렌더로 덮는다(경계는 부드럽게) → f####.png"""
    from PIL import Image, ImageFilter
    a = json.loads((fd / "adaptive.json").read_text("utf-8"))
    keys, first, last = a["keys"], a["first"], a["last"]
    W, H = a["w"], a["h"]
    tmp = fd / "seq"
    tmp.mkdir(exist_ok=True)
    # 간격이 일정하게 k 프레임을 이어 보간(마지막 간격만 다를 수 있어 시각 목록으로 넘긴다)
    lst = fd / "keys.txt"
    lst.write_text("".join(f"file '{fd / f'k{k:04d}.png'}'\nduration {(b - k) / fps:.6f}\n" for k, b in zip(keys, keys[1:])) + f"file '{fd / f'k{keys[-1]:04d}.png'}'\n", "utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf",
                    f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1", "-start_number", str(first), str(tmp / "f%04d.png")], check=True)
    for f in range(first, last + 1):
        p = tmp / f"f{f:04d}.png"
        kp = fd / f"k{f:04d}.png"
        base = Image.open(kp if kp.exists() else p).convert("RGB")
        b = a["regions"].get(str(f))
        rp = fd / f"r{f:04d}.png"
        if b and rp.exists():
            x0, y1 = int(b[0] * W), H - int(b[1] * H)
            x1, y0 = int(b[2] * W), H - int(b[3] * H)
            r = Image.open(rp).convert("RGB").resize((x1 - x0, y1 - y0))
            mask = Image.new("L", r.size, 0)
            mask.paste(255, (8, 8, r.width - 8, r.height - 8))
            base.paste(r, (x0, y0), mask.filter(ImageFilter.GaussianBlur(4)))
        base.save(dst / f"f{f:04d}.png")


TEMPLATE = ROOT / "engine" / "craft" / "blender" / "templates" / "product.py"


def _pbr(spec, finish="plastic") -> dict:
    """TextureCraft 재질 칸(이름 · 색 · {color, roughness, metallic}) → PBR 값"""
    from .texturecraft import CLEAN, FINISH, _hex
    if isinstance(spec, dict):
        return {"color": spec.get("color", "#d8dade"), "roughness": spec.get("roughness", 0.35), "metallic": spec.get("metallic", 0.0)}
    h = _hex(spec) if isinstance(spec, str) else None
    if h:
        r, mt = FINISH.get(finish, FINISH["plastic"])
        return {"color": h, "roughness": r, "metallic": mt}
    c = CLEAN.get(str(spec).lower())
    if c:
        return {"color": c[0], "roughness": c[1], "metallic": c[2]}
    return {"color": "#d8dade", "roughness": 0.35, "metallic": 0.0}


def from_design(m: dict, out: Path, work: Path) -> dict:
    """스크립트가 없는 재료: SolidCraft 로 모양을 만들고 Blender 기본 제품 컷으로 렌더(분해도는 SolidCraft 동작이라 그대로)"""
    from . import solidcraft as sc
    from .texturecraft import _materials
    from ..materials import _hash, cli
    if m.get("exploded"):
        return sc.model3d(m, out, work)
    d = sc.design(m, work, out.stem, cli("solidcraft"))
    mats = _materials(m, d["bodies"], d["meta"])
    finish = mats.pop("finish", "plastic")
    logo = m.get("logo")
    args = {"obj": str(d["obj"]), "mats": {k: _pbr(v, finish) for k, v in mats.items()}, "yaw": m.get("yaw", 28), "pitch": m.get("pitch", 16), "fill": m.get("fill", 0.8),
            "turntable": bool(m.get("turntable")), "turns": m.get("turns", 0.25), "stage": m.get("stage", True) is not False,
            "logo": (logo.get("text") if isinstance(logo, dict) else logo) if not str(logo or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else None, **(m.get("args") or {})}
    info = _render(TEMPLATE, {**m, "args": args, "transparent": False, "sec": (m.get("sec") or 4) if m.get("turntable") else None, "fps": m.get("fps", 24)}, out, work)
    return {**info, "blend_editable": info.get("editable"), "editable": str(d["sc"].relative_to(ROOT)) if d["sc"].is_relative_to(ROOT) else str(d["sc"]),
            "editable_hash": _hash(d["sc"]), "parts": d["bodies"], "apps": ["solidcraft", "blender"]}


def model3d(m: dict, out: Path, work: Path) -> dict:
    if not m.get("script"):
        if not any(m.get(k) for k in ("shape", "commands", "src")):
            raise RuntimeError("model3d: script(Blender 스크립트) 또는 shape · commands · src 가 필요합니다")
        return from_design(m, out, work)
    script = (ROOT / m["script"]).resolve()
    if not script.exists() or (ROOT / "data" / "compositions") not in script.parents:
        raise RuntimeError(f"model3d(blender): 스크립트는 data/compositions/ 안의 .py 여야 합니다: {m['script']}")
    return _render(script, m, out, work)


def _note_features(script: Path, ctx: dict) -> None:
    """Blender 는 <앱>-cli 호출이 아니라 사용량에 안 잡힌다 — 스크립트가 쓴 F.* · bpy 기능과 렌더러를 적는다"""
    import ast
    from .. import usage
    ids = {f"render.{ctx['engine']}"}
    for f in script.parent.glob("*.py"):
        if f != script:
            continue
        for n in ast.walk(ast.parse(f.read_text("utf-8"))):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "F":
                ids.add(n.attr)
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute) and isinstance(n.value.value, ast.Attribute) and getattr(n.value.value.value, "id", "") == "bpy":
                ids.add(f"bpy.{n.value.value.attr}.{n.value.attr}.{n.attr}")
    usage.record("blender", ids)


def _render(script: Path, m: dict, out: Path, work: Path) -> dict:
    args = dict(m.get("args") or {})
    if m.get("_uses"):
        args["uses"] = m["_uses"]                              # 다른 앱이 만든 재료 파일(같은 장면) — 스크립트의 ctx.args["uses"][이름]
        m = {**m, "args": args}
    if m.get("bridge"):
        args["asm"] = str(ensure_bridge(ROOT / m["bridge"]))
        m = {**m, "args": args}
    if m.get("physics"):                                       # MuJoCo 로 움직임을 먼저 계산 → 스크립트가 fluma3d.physics 로 키를 넣는다
        from craft import physics
        scene = (ROOT / m["physics"]).resolve()
        if not scene.exists() or (ROOT / "data" / "compositions") not in scene.parents:
            raise RuntimeError(f"physics 장면은 data/compositions/ 안의 MJCF(.xml) 여야 합니다: {m['physics']}")
        traj = work / f"{out.stem}.traj.json"
        res = physics.simulate(scene, float(m.get("sec") or 4), int(m.get("fps", 24)), {k: v for k, v in args.items() if not isinstance(v, (dict, list))},
                               m.get("ctrl"), m.get("goals"), work / f"{out.stem}.visual.json" if m.get("visual") else None,
                               poses=m.get("poses"), expect=m.get("expect"))
        if m.get("retime"):                                    # 속도 연출(부딪히는 순간 느리게) — physics.retime
            res = physics.retime(res, m["retime"])
        traj.write_text(json.dumps(res), "utf-8")
        args["physics"] = str(traj)
        m = {**m, "args": args}
        print(f"[3D] {out.stem}: 물리 계산(MuJoCo) {len(res['bodies'])}개 물체 · {res['sec']}초", flush=True)
    blend = work / f"{out.stem}.blend"
    still = bool(m.get("still")) or not m.get("sec")
    sec = float(m.get("sec") or 1)
    fd = work / f"{out.stem}.frames"
    shutil.rmtree(fd, ignore_errors=True)
    ctx = _ctx(m, work, sec)
    tw, th = int(m.get("width", 1080)), int(m.get("height", 1920))
    print(f"[3D] {out.stem}: {m.get('quality') or 'fast'} · 예상 {estimate(m, sec) / 60:.0f}분", flush=True)
    t0 = time.time()
    _note_features(script, ctx)
    try:
        run(script, fd, ctx, stills=str(float(m.get("at", 0))) if still else "", blend=blend)
    except RuntimeError as e:
        if ctx["engine"] != "eevee" or not re.search(r"EGL|OpenGL|GPU|display|GHOST", str(e)):
            raise
        # EEVEE 는 그래픽 장치가 필요하다 — 없는 환경(GPU 없는 컨테이너 등)에서는 멈추지 말고 Cycles 로
        print(f"[3D] {out.stem}: 그래픽 장치가 없어 Cycles 로 바꿉니다 — 크게 느려집니다(프레임당 약 {QUALITY['balanced']['sec']}초). docker/docker-compose.gpu.yml 참고", flush=True)
        m = {**m, "quality": "balanced"}
        ctx = _ctx(m, work, sec)
        shutil.rmtree(fd, ignore_errors=True)
        run(script, fd, ctx, stills=str(float(m.get("at", 0))) if still else "", blend=blend)
    info = {"app": "blender", "editable": str(blend.relative_to(ROOT)) if blend.is_relative_to(ROOT) else str(blend), "size": [tw, th], "quality": m.get("quality") or "fast", "render_sec": round(time.time() - t0)}
    if still:
        shutil.move(str(fd / "s00.png"), str(out))
        shutil.rmtree(fd, ignore_errors=True)
        return {**info, "as": "image"}
    ev = fd / "events.json"
    if ev.exists():
        info["events"] = json.loads(ev.read_text("utf-8"))     # F.event 순간 — 소리 단계가 효과음을 맞춘다
    frames = sorted(fd.glob("f*.png"))
    if not frames:
        raise RuntimeError("Blender 가 프레임을 내지 않았습니다")
    alpha = ctx["transparent"]
    suffix = ".mov" if alpha else ".mp4"
    vid = out.with_suffix(suffix)
    codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"] if alpha else ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]
    vf = [f"scale={tw}:{th}:flags=lanczos,cas=0.45"] if (ctx["w"], ctx["h"]) != (tw, th) else []     # 낮춰 그린 것을 목표 크기로
    if not alpha:                                                                                  # 장면보다 짧아도 끝 프레임을 잡아 화면이 비지 않게
        vf.append("tpad=stop_mode=clone:stop_duration=20")
    up = ["-vf", ",".join(vf)] if vf else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(ctx["fps"]), "-i", str(fd / "f%04d.png"), *up, *codec, str(vid)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Blender 영상 잇기 실패: {r.stderr[-200:]}")
    out.write_bytes(frames[len(frames) // 2].read_bytes())
    shutil.rmtree(fd, ignore_errors=True)
    return {**info, "file_suffix": suffix, "as": "video", "frames": len(frames), "fps": ctx["fps"], "sec": round(len(frames) / ctx["fps"], 2), "poster": out.name}


ADAPTERS = {"model3d": model3d, "model3d@blender": model3d}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--still", default="1", help="초, 쉼표로 여러 개")
    ap.add_argument("--sec", type=float, default=4)
    ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--height", type=int, default=960)
    ap.add_argument("--samples", type=int)
    ap.add_argument("--opaque", action="store_true")
    ap.add_argument("--quality", default="best", choices=list(QUALITY))
    ap.add_argument("--out")
    ap.add_argument("--args", default="{}", help="JSON → ctx.args")
    ap.add_argument("--physics", help="MuJoCo 장면(MJCF) — 먼저 계산해 ctx.args['physics'] 로 넘긴다")
    ap.add_argument("--anim", action="store_true", help="정지 화면 대신 짧은 영상(mp4)으로 — 움직임 확인용")
    ap.add_argument("--ctrl", help="조종 값 시간표 JSON(physics.py 와 같음)")
    ap.add_argument("--goals", help="목표 JSON — 계획기가 조종 값을 찾는다(physics.py plan) · 손 동작은 --poses 가 맞다")
    ap.add_argument("--poses", help="자세 키 JSON(physics.py pose_ctrl) — 손 · 몸 동작")
    ap.add_argument("--expect", help="닿음 기대 JSON(physics.py check_contacts)")
    ap.add_argument("--retime", help='속도 연출 JSON [{"from": 1.0, "to": 1.4, "speed": 0.3}] — 그 구간 느리게(영상 길이가 늘어난다)')
    ap.add_argument("--traj", help="이미 계산한 결과(.traj.json — physics.py gym · run) 를 그대로 ctx.args['physics'] 로")
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    script = Path(a.script).resolve()
    out = Path(a.out).resolve() if a.out else ROOT / "data" / "workspace" / "blender" / script.stem
    out.mkdir(parents=True, exist_ok=True)
    args = json.loads(a.args)
    if a.traj:
        args["physics"] = str(Path(a.traj).resolve())
    if a.physics:
        from craft import physics
        res = physics.simulate(Path(a.physics).resolve(), a.sec, a.fps, {k: v for k, v in args.items() if not isinstance(v, (dict, list))},
                               json.loads(a.ctrl) if a.ctrl else None, json.loads(a.goals) if a.goals else None, out / "physics.visual.json",
                               poses=json.loads(a.poses) if a.poses else None, expect=json.loads(a.expect) if a.expect else None)
        if a.retime:
            res = physics.retime(res, json.loads(a.retime))
            a.sec = res["sec"]
        tp = out / "physics.traj.json"
        tp.write_text(json.dumps(res), "utf-8")
        args["physics"] = str(tp)
    m = {"width": a.width, "height": a.height, "samples": a.samples, "transparent": not a.opaque, "draft": True, "args": args, "quality": a.quality, "fps": a.fps}
    if a.anim:
        fd = out / "frames"
        shutil.rmtree(fd, ignore_errors=True)
        run(script, fd, _ctx(m, out, a.sec), stills="")
        frames = sorted(fd.glob("*.png"))
        mp4 = out / f"{script.stem}.mp4"
        lst = out / "frames.txt"
        lst.write_text("".join(f"file '{f}'\nduration {1 / a.fps:.6f}\n" for f in frames), "utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", f"fps={a.fps},format=yuv420p", "-c:v", "libx264", "-crf", "18", str(mp4)], check=True)
        print(str(mp4.relative_to(ROOT)) if mp4.is_relative_to(ROOT) else str(mp4))
        return 0
    run(script, out, _ctx(m, out, a.sec), stills=a.still)
    print("\n".join(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in sorted(out.glob("s*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
