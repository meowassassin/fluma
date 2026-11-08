#!/usr/bin/env python3
"""3D 앱 잇기 — SolidCraft(모양 · 관절 동작) → TextureCraft(재질 · 로고) → Blender(곡면 추가 · 조명 · 최종 렌더).
정밀한 부품과 기계 동작은 CAD 로, 표면은 TextureCraft 로, 영화 품질 화면은 Blender 로 — 앱마다 잘하는 일을 한 컷에서 쓴다.

  python3 engine/craft/bridge3d.py <사양.json>

사양
  { "design": "data/compositions/<id>/src/x.sc",               # 관절 · 모션 스터디가 든 SolidCraft 설계
    "out_dir": "data/compositions/<id>/src/asm",
    "study": "Open", "samples": 121,                            # 모션 스터디 → 단계별 부품 위치(없으면 멈춘 모형)
    "materials": {"Shell": {"color": "#efece6", "roughness": 0.2, "metallic": 0}, "Tip": "rubber", "*": …},   # texturecraft 재질 칸과 같다
    "logo": {"text": "MOA", "on": "Shell", "size": 8},          # 선택
    "resolution": 1024, "bake": false }                         # bake: 스마트 재질을 쓸 때만(GPU 를 많이 쓴다)
결과(out_dir): model.glb(재질이 구워진 메시) · assembly.json({scale_mm, parts: {부품: {bodies, poses: [[원점, x, y, z] …]}}})
Blender 스크립트에서:
    asm = F.import_assembly(ctx.args["asm"], scale=0.1)         # mm → 씬 단위(0.1 = cm)
    F.play_assembly(asm, frm=0, to=1, start=0.4, end=3.0)       # 동작의 0~1 구간을 그 시간에 재생
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.adapters.texturecraft import build_project, to_y_up  # noqa: E402
from craft.materials import cli  # noqa: E402


def _sc(sc: str, cmds: list, design: Path, work: Path, *extra) -> None:
    f = work / "bridge.script.json"
    f.write_text(json.dumps({"commands": cmds}, ensure_ascii=False), "utf-8")
    r = subprocess.run([sc, "run", str(f), "--in", str(design), "--quiet", *map(str, extra)], capture_output=True, text=True, timeout=600, cwd=str(work))
    if r.returncode != 0:
        raise RuntimeError(f"SolidCraft 내보내기 실패: {(r.stderr or r.stdout)[-400:]}")


def occurrences(sc: str, design: Path, work: Path) -> dict[str, list[str]]:
    """부품(occurrence) → 몸체 이름들"""
    out = work / "bridge.mass.json"
    f = work / "bridge.script.json"
    f.write_text(json.dumps({"commands": [{"command": "assembly.mass_properties", "params": {}}]}), "utf-8")
    r = subprocess.run([sc, "run", str(f), "--in", str(design), "--results", "--quiet", "--json-out", str(out)], capture_output=True, text=True, timeout=300, cwd=str(work))
    if r.returncode != 0:
        raise RuntimeError(f"SolidCraft 부품 목록 실패: {(r.stderr or r.stdout)[-300:]}")
    j = json.loads(out.read_text("utf-8"))
    res = j[-1] if isinstance(j, list) else (j.get("results") or [j])[-1]         # 명령마다 결과 하나
    res = res.get("result", res) if isinstance(res, dict) else res
    parts: dict[str, list[str]] = {}
    for o in res.get("occurrences") or []:
        names = [b["name"] for b in o.get("bodies") or []]
        if names:
            parts[str(o.get("name"))] = names                 # 'Case:1' — motion.export 의 occurrence 와 같은 이름
    return parts


def build(spec: dict) -> dict:
    sc, tc = cli("solidcraft"), cli("texturecraft")
    design = ROOT / spec["design"]
    out = ROOT / spec["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    # 1) SolidCraft: 기본 자세 메시 · 부품 · 동작
    obj = out / "base.obj"
    _sc(sc, [], design, out, "--out", obj)
    parts = occurrences(sc, design, out)
    poses: dict[str, list] = {}
    if spec.get("study"):
        mf = out / "motion.json"
        _sc(sc, [{"command": "motion.export", "params": {"study": spec["study"], "samples": int(spec.get("samples", 121)), "path": str(mf)}}], design, out)
        for s in json.loads(mf.read_text("utf-8"))["samples"]:
            for p in s["positions"]:
                q = p["pose"]
                poses.setdefault(str(p["occurrence"]).split(":")[0], []).append([q["origin"], q["x"], q["y"], q["z"]])
    # 2) TextureCraft: 굽기 · 재질 · 로고 → GLB
    yobj = out / "base.y.obj"
    box = to_y_up(obj, yobj, stage=False)
    proj = out / "model.tcraft"
    logo = dict(spec["logo"]) if spec.get("logo") else None
    if logo:
        logo.setdefault("side", "front")
    build_project(tc, yobj, proj, out, box["bodies"], spec.get("materials") or {}, box, logo, resolution=int(spec.get("resolution", 1024)), bake=bool(spec.get("bake")))
    glb = out / "model.glb"
    r = subprocess.run([tc, "run", str(proj), "file.exportMesh", json.dumps({"path": str(glb)})], capture_output=True, text=True, timeout=600, cwd=str(out))
    if r.returncode != 0 or not glb.exists():
        raise RuntimeError(f"TextureCraft GLB 내보내기 실패: {(r.stderr or r.stdout)[-400:]}")
    res = {"parts": {k.split(":")[0]: {"bodies": v, "poses": poses.get(k.split(":")[0], [])} for k, v in parts.items()}, "bodies": box["bodies"]}
    (out / "assembly.json").write_text(json.dumps(res, ensure_ascii=False), "utf-8")
    for f in (out / "bridge.script.json", out / "bridge.mass.json", out / "base.y.obj"):
        f.unlink(missing_ok=True)
    return {"glb": str(glb.relative_to(ROOT)), "parts": {k: len(v["poses"]) for k, v in res["parts"].items()}, "bodies": len(box["bodies"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    a = ap.parse_args()
    print(json.dumps(build(json.loads(Path(a.spec).read_text("utf-8"))), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
