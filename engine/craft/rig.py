"""그린 SVG(이름 붙은 그룹) → 부품 레이어 + 뼈대(rig.json). 움직임 단계(motion.puppet)가 이걸로 관절을 돌린다.

디자이너(에이전트 · 사람)는 부품마다 <g id="body"> · "arm" · "leg_front" · "leg_back" · "sack" … 로 묶기만 하면 된다.
id 가 없는 최상위 요소(배경 · 별)는 버린다 — 캐릭터만 남는다.
관절은 자동 추정: 부품 픽셀 중 몸에 가장 가까운 점(팔 · 다리 · 꼬리가 붙은 자리), 몸은 발밑 가운데.
더 정확히 하려면 그룹에 data-pivot="x y" · data-kind="arm|leg|tail|body|part" · data-parent="body" 를 적는다(SVG 좌표).
"""
from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
KINDS = [("leg", "leg"), ("foot", "leg"), ("arm", "arm"), ("hand", "arm"), ("wing", "arm"),
         ("tail", "tail"), ("sack", "tail"), ("scarf", "tail"), ("hair", "tail"), ("antenna", "tail"), ("body", "body")]


def kind_of(gid: str) -> str:
    for key, k in KINDS:
        if key in gid.lower():
            return k
    return "part"


def _viewbox(root) -> tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        x, y, w, h = [float(v) for v in re.split(r"[ ,]+", vb.strip())]
        return x, y, w, h
    return 0.0, 0.0, float(root.get("width", 1000)), float(root.get("height", 1000))


def split(svg: Path, out_dir: Path, render) -> dict:
    """render(svg_path, png_path) 는 VectorCraft 렌더(scale 1). → rig dict (rig.json 도 쓴다)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(svg)
    root = tree.getroot()
    vx, vy, vw, vh = _viewbox(root)
    defs = [e for e in root if e.tag.endswith("defs")]
    groups = [e for e in root if e.tag.endswith("}g") and e.get("id")]
    # 편집 툴의 레이어(VectorCraft 는 전체를 Layer_1 로 감싼다) 안에 부품 그룹이 있으면 그 안을 본다
    while len(groups) == 1 and any(c.tag.endswith("}g") and c.get("id") for c in groups[0]):
        groups = [c for c in groups[0] if c.tag.endswith("}g") and c.get("id")]
    if not groups:
        return {}
    layers, masks = [], {}
    for g in groups:
        gid = g.get("id")
        one = ET.Element(root.tag, {k: v for k, v in root.attrib.items()})
        for d in defs:
            one.append(copy.deepcopy(d))
        one.append(copy.deepcopy(g))
        f = out_dir / f"{gid}.svg"
        ET.ElementTree(one).write(f, encoding="unicode")
        png = out_dir / f"{gid}.png"
        render(f, png)
        a = np.asarray(Image.open(png).convert("RGBA"))[:, :, 3] > 24
        sx, sy = vw / a.shape[1], vh / a.shape[0]           # 픽셀 → SVG 좌표
        masks[gid] = (a, sx, sy)
        layers.append({"id": gid, "file": f.name, "kind": g.get("data-kind") or kind_of(gid),
                       "parent": g.get("data-parent"), "pivot_hint": g.get("data-pivot")})
    body = next((l for l in layers if l["kind"] == "body"), layers[0])
    body["kind"] = "body"
    ba, sx, sy = masks[body["id"]]
    ys, xs = np.nonzero(ba)
    bcx, bcy = xs.mean(), ys.mean()
    allmask = np.any([m[0] for m in masks.values()], axis=0)
    gy = np.nonzero(allmask)[0].max()                        # 발밑(바닥선)
    for l in layers:
        if l["pivot_hint"]:
            px, py = [float(v) for v in re.split(r"[ ,]+", l["pivot_hint"].strip())]
        elif l is body:
            px, py = vx + bcx * sx, vy + gy * sy
        else:
            m, _, _ = masks[l["id"]]
            yy, xx = np.nonzero(m)
            if not len(xx):
                px, py = vx + bcx * sx, vy + bcy * sy
            elif l["kind"] == "leg":           # 다리: 맨 위(엉덩이) 가운데
                top = yy.min()
                qx, qy = xx[yy <= top + 6].mean(), top + 4
            else:                                # 팔 · 꼬리 · 기타: 몸 중심에 가장 가까운 점(붙은 자리)
                i = np.argmin((xx - bcx) ** 2 + (yy - bcy) ** 2)
                qx, qy = xx[i], yy[i]
            if len(xx):
                px, py = vx + qx * sx, vy + qy * sy
        l["pivot"] = [round(float(px), 1), round(float(py), 1)]
        if l is not body and not l["parent"]:
            l["parent"] = body["id"]
        l.pop("pivot_hint")
        (out_dir / f"{l['id']}.png").unlink(missing_ok=True)
    rig = {"canvas": [vw, vh], "origin": [round(vx + bcx * sx, 1), round(vy + gy * sy, 1)], "layers": layers, "source": svg.name}
    (out_dir / "rig.json").write_text(json.dumps(rig, ensure_ascii=False, indent=1), "utf-8")
    return rig
