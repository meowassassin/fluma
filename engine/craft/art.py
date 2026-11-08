"""Craft 파이프라인 — 그림 단계: 형태(form.json) + 화풍(style.json) → 부품별 레이어 SVG + 뼈대(rig.json).

설계: 볼트 02 Architecture/그리기 엔진 설계 — 구조로 그리기.md · Craft 파이프라인 설계 (5절 craft/art.py)
  data/compositions/<id>/forms/<이름>.form.json        에이전트가 쓰는 형태(좌표 없음)
  data/compositions/<id>/style.json                    화풍 카드(없으면 flat-bright)
→ data/compositions/<id>/craft/art/figures/<이름>/
     full.svg            전체(VectorCraft 에서 열어 사람이 고칠 수 있음, 그룹 = 부품)
     layers/<레이어>.svg   부품 하나씩 — 모두 같은 캔버스 · 같은 크기라 겹치면 원래 그림이 된다
     rig.json            레이어 순서(뒤→앞) · 관절(캔버스 픽셀) · 부모 · 역할(다리 · 팔 · 부속) — 움직임 단계가 인형으로 조립
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from drawlib import render as drender, style as dstyle  # noqa: E402
from drawlib.form import U, solve  # noqa: E402

SCALE = 4.0      # 그림 단위 → SVG 픽셀 배율(크게 내보내야 EffectCraft 에서 선명)


def _kind(p) -> str:
    """움직임에서 쓰는 부품 종류: leg · arm · tail(부속) · body"""
    sp = p.spec
    if sp.get("limb_kind"):
        return sp["limb_kind"]
    if sp.get("ground"):
        return "leg"
    if sp.get("shape") == "capsule" and p.parent:
        return "arm"
    if sp.get("shape") in ("sweep", "leaf") and p.parent:
        return "tail"
    return "body"


def build_figure(form: dict, style: dict | None, out_dir: Path) -> dict:
    placed, warns = solve(form)
    st = dstyle.resolve(style)
    pal = {**drender.DEFAULT_PALETTE, **st.get("palette", {}), **(form.get("palette") or {})}
    full = drender.svg(placed, palette=pal, style=st)
    vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', full).group(1).split()]
    W, H = vb[2] * SCALE, vb[3] * SCALE
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]:.1f} {vb[1]:.1f} {vb[2]:.1f} {vb[3]:.1f}" width="{W:.0f}" height="{H:.0f}">'
    (out_dir / "layers").mkdir(parents=True, exist_ok=True)
    (out_dir / "full.svg").write_text(full.replace(re.search(r"<svg[^>]*>", full).group(0), head), "utf-8")
    groups = re.findall(r'(<g id="([^"]+)"[^>]*>.*?</g>)', full, flags=re.S)
    layer_of = {p.id: p.layer for p in placed}
    byid = {p.id: p for p in placed}
    # origin = 그림 좌표 (0, 0) — 풀이기가 발을 y=0 · 몸 가운데를 x≈0 에 둔다 → 화면에 '서 있는 점'
    rig = {"name": form.get("name"), "canvas": [round(W), round(H)], "unit_px": U * SCALE, "facing": form.get("facing", "right"),
           "origin": [round(-vb[0] * SCALE, 1), round(-vb[1] * SCALE, 1)], "layers": []}
    for g, gid in groups:
        (out_dir / "layers" / f"{gid}.svg").write_text(head + g + "</svg>\n", "utf-8")
        if gid == "ground_shadow":
            rig["layers"].append({"id": gid, "file": f"layers/{gid}.svg", "pivot": [W / 2, H / 2], "parent": None, "kind": "shadow"})
            continue
        p = byid.get(gid)
        par = layer_of.get(p.parent) if p and p.parent else None
        px = ((p.pivot[0] - vb[0]) * SCALE, (p.pivot[1] - vb[1]) * SCALE) if p else (W / 2, H / 2)
        rig["layers"].append({"id": gid, "file": f"layers/{gid}.svg", "pivot": [round(px[0], 1), round(px[1], 1)],
                              "parent": par if par != gid else None, "kind": _kind(p) if p else "body",
                              "mirror_of": p.spec.get("_mirror_of") if p else None})
    (out_dir / "rig.json").write_text(json.dumps(rig, ensure_ascii=False, indent=1), "utf-8")
    return {"rig": rig, "warnings": warns}


def build_all(sid: str) -> list[str]:
    """영상의 모든 형태를 그린다 → 그린 이름들"""
    d = ROOT / "data" / "compositions" / sid
    st_p = d / "style.json"
    style = json.loads(st_p.read_text("utf-8")) if st_p.exists() else {"preset": "flat-bright"}
    done = []
    for f in sorted((d / "forms").glob("*.form.json")) if (d / "forms").exists() else []:
        name = f.name[: -len(".form.json")]
        build_figure(json.loads(f.read_text("utf-8")), style, d / "craft" / "art" / "figures" / name)
        done.append(name)
    return done


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("python3 engine/craft/art.py <영상 id>")
    print(build_all(sys.argv[1]))
