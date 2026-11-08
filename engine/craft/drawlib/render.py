"""그리기 엔진 — 배치된 덩어리를 레이어 SVG 로. 화풍 카드(style.json)대로 밑색 · 그림자 · 하이라이트 · 외곽선 · 바닥 그림자.

레이어 = 한 실루엣(merge 로 묶인 부품들). 그룹 id = 부품 id 라 VectorCraft 에서 열면 부품별로 고칠 수 있고,
5단계 뼈대(rig.json)가 같은 id 로 움직인다. 그룹마다 data-pivot(관절) · data-parent 를 적는다.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from . import geom, style as stylemod
from .form import U, Placed

DEFAULT_PALETTE = {"main": "#ff9f1c", "main_dark": "#d9780a", "accent": "#f72585", "accent2": "#4cc9f0",
                   "light": "#fff3d6", "dark": "#2b2d42", "white": "#ffffff", "black": "#14141f"}


@dataclass
class Layer:
    id: str
    parts: list[Placed]
    z: float
    role: str

    @property
    def decal(self) -> bool:
        return bool(self.parts[0].spec.get("decal"))


def layers(placed: list[Placed]) -> list[Layer]:
    out: dict[str, Layer] = {}
    for p in placed:
        L = out.get(p.layer)
        if L is None:
            out[p.layer] = Layer(p.layer, [p], p.z, p.role)
        else:
            L.parts.append(p)
            L.z = min(L.z, p.z)
    return sorted(out.values(), key=lambda q: q.z)


def _seed(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


def layer_svg(L: Layer, st: dict, pal: dict, res: float) -> tuple[str, tuple[float, float, float, float]] | None:
    """레이어 하나 → <g> 와 범위"""
    # 2관절 팔다리는 관절을 거의 그대로(덜 부드럽게) 합친다 — 크게 합치면 관절이 불룩해져 국수처럼 휜다
    limb = all(p.spec.get("limb_kind") for p in L.parts)
    shape = L.parts[0].shape if len(L.parts) == 1 else geom.Union([p.shape for p in L.parts], k=(0.015 if limb else st["round"]) * U)
    sharp = any(p.spec.get("shape") in ("box", "cylinder", "leaf") for p in L.parts)
    ca = 50.0 if sharp else 80.0
    wob = st["wobble"]["amp"] * U if not L.decal else st["wobble"]["amp"] * U * 0.4
    seed = _seed(L.id)
    o = geom.outline(shape, res=res, corner_angle=ca, wobble_amp=wob, wobble_freq=st["wobble"]["freq"], seed=seed)
    if not o.d:
        return None
    base = pal.get(L.role, L.role)
    cav = L.parts[0].spec.get("cavity_of")
    if cav:   # 구멍 안: 부모 색을 어둡고 차갑게
        base = stylemod.shift(pal.get(cav, cav), h=0.04, s=0.02, l=-0.16)
    fill = base
    gr = st.get("gradient") or {}
    defs = ""
    if gr.get("on") and not L.decal and not cav:
        # 빛 쪽이 조금 밝은 은은한 그라데이션(무지개 금지 — 같은 색의 밝기만)
        lx, ly = stylemod.light_vec(st["shade"]["light"])
        gid = f"g-{L.id}"
        hi = stylemod.shift(base, h=0, s=0, l=float(gr.get("amount", 0.08)))
        defs = (f'<defs><linearGradient id="{gid}" x1="{0.5 + 0.5 * lx:.2f}" y1="{0.5 + 0.5 * ly:.2f}" x2="{0.5 - 0.5 * lx:.2f}" y2="{0.5 - 0.5 * ly:.2f}">'
                f'<stop offset="0" stop-color="{hi}"/><stop offset="1" stop-color="{base}"/></linearGradient></defs>')
        fill = f"url(#{gid})"
    out = [defs + f'<path class="fill" d="{o.d}" fill="{fill}" fill-rule="evenodd"/>']
    big = (o.bounds[2] - o.bounds[0]) > 0.12 * U and (o.bounds[3] - o.bounds[1]) > 0.12 * U
    if st["shade"].get("tones", 1) >= 2 and big and not L.decal and not cav:
        # 그림자 끝은 외곽선과 뾰족하게 만난다 — 모서리로 맞춰야 곡선이 끝을 넘쳐 가시가 생기지 않는다
        sh = geom.outline(stylemod.shadow_shape(shape, U, st), res=res, corner_angle=40.0, wobble_amp=wob * 0.6, wobble_freq=st["wobble"]["freq"], seed=seed + 1)
        if sh.d:
            out.append(f'<path class="shade" d="{sh.d}" fill="{stylemod.shift(base, **st["shade"]["shift"])}" fill-rule="evenodd"/>')
    if st["rim"].get("on") and big and not L.decal and not cav:
        rm = geom.outline(stylemod.rim_shape(shape, U, st), res=res * 0.7, corner_angle=ca, seed=seed + 2)
        if rm.d:
            out.append(f'<path class="rim" d="{rm.d}" fill="{stylemod.shift(base, h=0, s=-0.02, l=st["rim"]["l"])}" fill-rule="evenodd"/>')
    if st["outline"].get("on"):
        oc = st["outline"].get("color", "dark")
        col = stylemod.shift(base, h=0.02, s=0.05, l=-0.38) if oc == "dark" else oc
        out.append(f'<path class="line" d="{o.d}" fill="none" stroke="{col}" stroke-width="{st["outline"]["width"] * U:.2f}" stroke-linejoin="round"/>')
    p0 = L.parts[0]
    attrs = f' data-pivot="{p0.pivot[0]:.2f},{p0.pivot[1]:.2f}"' + (f' data-parent="{p0.parent}"' if p0.parent else "")
    return f'<g id="{L.id}"{attrs}>' + "".join(out) + "</g>", o.bounds


def svg(placed: list[Placed], palette: dict | None = None, style: dict | None = None, res: float = 0.8, pad: float = 0.15) -> str:
    st = stylemod.resolve(style)
    pal = {**DEFAULT_PALETTE, **st.get("palette", {}), **(palette or {})}
    groups, bx = [], []
    feet = [p for p in placed if p.spec.get("ground")]
    for L in layers(placed):
        r = layer_svg(L, st, pal, res)
        if r:
            groups.append(r[0])
            bx.append(r[1])
    if not bx:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>'
    if feet and st["ground_shadow"].get("on"):
        fb = [p.shape.bounds() for p in feet]
        x0, x1 = min(b[0] for b in fb), max(b[2] for b in fb)
        cx, rx = (x0 + x1) / 2, (x1 - x0) / 2 + 0.12 * U
        groups.insert(0, f'<g id="ground_shadow"><ellipse cx="{cx:.1f}" cy="0" rx="{rx:.1f}" ry="{0.06 * U:.1f}" fill="#000" opacity="{st["ground_shadow"]["opacity"]}"/></g>')
        bx.append((cx - rx, -0.06 * U, cx + rx, 0.06 * U))
    x0, y0 = min(b[0] for b in bx), min(b[1] for b in bx)
    x1, y1 = max(b[2] for b in bx), max(b[3] for b in bx)
    m = pad * U
    vb = f"{x0 - m:.1f} {y0 - m:.1f} {x1 - x0 + 2 * m:.1f} {y1 - y0 + 2 * m:.1f}"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">\n' + "\n".join(groups) + "\n</svg>\n"
