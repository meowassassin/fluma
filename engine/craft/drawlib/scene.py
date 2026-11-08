"""그리기 엔진 6단계 — 장면 배경 세계: 하늘 · 빛 번짐 · 먼 층 · 지면 · 잔무늬. 좌표는 규칙이 정한다.

설계: 볼트 02 Architecture/그리기 엔진 설계 — 구조로 그리기.md (7절)
world = {
  "sky":    "gradient" | "flat"                 위는 어둡게 · 아래(지평선)는 밝게, 화풍 bg 색에서
  "glow":   { "at": "center" | "left" | "right", "size": 0.55 }   주인공 뒤 은은한 원형 빛
  "far":    [ { "archetype": "building", "count": 4, "palette": {…} }, … ]   지평선을 따라 고른 간격 · 공기 원근
  "ground": { "y": 0.8, "role": "main_dark" }  살짝 휜 지면 띠
  "motif":  "stars" | "dots" | "grass" | "none"  잔무늬, 겹치지 않게 고른 간격(포아송 원반)
}
결과: 층마다 SVG(1080×1920) — sky · glow · far · ground · motif. EffectCraft 에서 층별 속도 차(패럴랙스)로 움직인다.
"""
from __future__ import annotations

import math
import random
import re

from . import geom, render as drender, style as stylemod
from .form import U, solve

W, H = 1080, 1920
POS = {"left": 0.3, "center": 0.5, "right": 0.7}


def _blend(a: str, b: str, t: float) -> str:
    ra, rb = stylemod._hex(a), stylemod._hex(b)
    return stylemod._to_hex(*[x + (y - x) * t for x, y in zip(ra, rb)])


def _svg(body: str, defs: str = "") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">' + (f"<defs>{defs}</defs>" if defs else "") + body + "</svg>\n"


def poisson(n: int, x0: float, x1: float, y0: float, y1: float, rmin: float, seed: int) -> list[tuple[float, float]]:
    """겹치지 않게 고른 간격으로 n 개(던지고 거르기 — 작은 수라 충분)"""
    rnd = random.Random(seed)
    pts: list[tuple[float, float]] = []
    tries = 0
    while len(pts) < n and tries < n * 60:
        tries += 1
        p = (rnd.uniform(x0, x1), rnd.uniform(y0, y1))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= rmin * rmin for q in pts):
            pts.append(p)
    return pts


def build(world: dict, style: dict | None, seed: int = 0) -> dict[str, str]:
    st = stylemod.resolve(style)
    pal = {**drender.DEFAULT_PALETTE, **st.get("palette", {})}
    bg = st.get("bg") or pal.get("dark", "#1f2755")
    horizon = float((world.get("ground") or {}).get("y", 0.8)) * H
    layers: dict[str, str] = {}

    # 하늘: 위는 어둡고 차갑게, 지평선은 밝게
    top, low = stylemod.shift(bg, h=0.03, s=0.02, l=-0.12), stylemod.shift(bg, h=0, s=-0.04, l=0.12)
    if world.get("sky", "gradient") == "gradient":
        layers["sky"] = _svg('<rect width="100%" height="100%" fill="url(#sky)"/>',
                             f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{low}"/></linearGradient>')
    else:
        layers["sky"] = _svg(f'<rect width="100%" height="100%" fill="{bg}"/>')

    # 빛 번짐: 주인공 뒤 원형 빛(같은 계열 밝은 색, 낮은 불투명도)
    g = world.get("glow")
    if g:
        cx = POS.get(g.get("at", "center"), 0.5) * W
        r = float(g.get("size", 0.55)) * W
        col = stylemod.shift(low, h=0, s=0.05, l=0.15)
        layers["glow"] = _svg(f'<circle cx="{cx:.0f}" cy="{horizon - r * 0.55:.0f}" r="{r:.0f}" fill="url(#glow)"/>',
                              f'<radialGradient id="glow"><stop offset="0" stop-color="{col}" stop-opacity="0.55"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>')

    # 먼 층: 몸 설계도 인스턴스를 지평선을 따라, 하늘색에 섞어(공기 원근) 흐리게
    rnd = random.Random(seed)
    items = []
    for spec in world.get("far") or []:
        for _ in range(int(spec.get("count", 3))):
            items.append(spec)
    if items:
        xs = poisson(len(items), 0.04 * W, 0.96 * W, 0, 1, W / (len(items) + 2), seed + 1)
        xs = sorted(x for x, _ in xs)
        body = []
        for spec, x in zip(items, xs):
            placed, _ = solve({"archetype": spec["archetype"], "view": "front"})
            fpal = {k: _blend(v, low, 0.55) for k, v in {**pal, **(spec.get("palette") or {})}.items() if isinstance(v, str) and v.startswith("#")}
            svg = drender.svg(placed, palette=fpal, style={**st, "shade": {"tones": 1}, "rim": {"on": False}, "ground_shadow": {"on": False}, "gradient": {"on": False}}, res=1.6)
            vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
            k = rnd.uniform(0.75, 1.15) * 0.16 * H / vb[3]
            inner = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())
            body.append(f'<g transform="translate({x:.0f},{horizon + 6:.0f}) scale({k:.3f}) translate({-(vb[0] + vb[2] / 2):.1f},{-(vb[1] + vb[3]):.1f})">{inner}</g>')
        layers["far"] = _svg("".join(body))

    # 지면: 살짝 휜 띠(큰 타원 윗부분)
    gr = world.get("ground") or {}
    gcol = pal.get(gr.get("role", "main_dark"), gr.get("role", "#203040"))
    layers["ground"] = _svg(f'<ellipse cx="{W / 2}" cy="{horizon + W * 1.6:.0f}" rx="{W * 1.4:.0f}" ry="{W * 1.6:.0f}" fill="{gcol}"/>'
                            f'<ellipse cx="{W / 2}" cy="{horizon + W * 1.6 + 26:.0f}" rx="{W * 1.4:.0f}" ry="{W * 1.6:.0f}" fill="{stylemod.shift(gcol, h=0.03, s=0.03, l=-0.08)}"/>')

    # 잔무늬
    m = world.get("motif", "stars")
    if m and m != "none":
        if m == "grass":
            pts = poisson(26, 0.02 * W, 0.98 * W, horizon + 60, H - 40, 70, seed + 2)
            c = stylemod.shift(gcol, h=0, s=0.05, l=0.08)
            body = "".join(f'<path d="M{x - 8:.0f} {y:.0f} Q{x:.0f} {y - 26:.0f} {x + 3:.0f} {y - 34:.0f} Q{x + 2:.0f} {y - 14:.0f} {x + 8:.0f} {y:.0f}Z" fill="{c}"/>' for x, y in pts)
        else:
            n = 46 if m == "stars" else 30
            pts = poisson(n, 0.02 * W, 0.98 * W, 0.03 * H, horizon - 0.18 * H, 60, seed + 2)
            c = stylemod.shift(low, h=0, s=-0.1, l=0.3)
            rr = random.Random(seed + 3)
            if m == "stars":
                body = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr.uniform(1.5, 4.2):.1f}" fill="{c}" opacity="{rr.uniform(0.45, 0.95):.2f}"/>' for x, y in pts)
            else:
                body = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr.uniform(4, 9):.1f}" fill="{c}" opacity="0.35"/>' for x, y in pts)
        layers["motif"] = _svg(body)
    return layers


def composite(layers: dict[str, str], figures: list[tuple[str, float, float]]) -> str:
    """미리 보기용 한 장: 층들 + 인물(SVG, 화면 x 비율, 높이 비율). 바닥은 지평선"""
    order = ["sky", "glow", "far", "motif", "ground"]
    parts = [re.sub(r"^<svg[^>]*>|</svg>\s*$", "", layers[k].strip()) for k in order if k in layers]
    for svg, x, size in figures:
        vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
        k = size * H / vb[3]
        inner = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())
        gy = 0.8 * H + 40
        parts.append(f'<g transform="translate({x * W:.0f},{gy:.0f}) scale({k:.3f}) translate({-(vb[0] + vb[2] / 2):.1f},{-(vb[1] + vb[3]):.1f})">{inner}</g>')
    return _svg("".join(parts))
