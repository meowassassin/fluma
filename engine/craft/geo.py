"""실제 지도 — Natural Earth 1:10m 육지(공개 자료)를 영역으로 잘라 화면 좌표의 다각형으로 낸다. 좌표를 손으로 찍지 않는다.

  land(bbox, W, H) → (육지 다각형 목록, 좌표 변환 함수)
  bbox = [서경, 남위, 동경, 북위]. 위도에 맞춰 가로세로 비를 보정해 화면을 채운다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "assets" / "geo" / "ne_10m_land.geojson"
_cache: list | None = None


def _rings() -> list:
    global _cache
    if _cache is None:
        _cache = []
        for f in json.loads(SRC.read_text("utf-8"))["features"]:
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                _cache.append(poly[0])
    return _cache


def clip(ring: list, box) -> list:
    """Sutherland–Hodgman — 영역 사각형으로 자른다"""
    x0, y0, x1, y1 = box
    edges = [(lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))]
    out = ring
    for inside, cross in edges:
        cur, out = out, []
        for i, p in enumerate(cur):
            q = cur[i - 1]
            if inside(p):
                if not inside(q):
                    out.append(cross(q, p))
                out.append(p)
            elif inside(q):
                out.append(cross(q, p))
        if not out:
            return []
    return out


def land(bbox, W: int, H: int, margin: int = 0, tol: float = 0.9):
    x0, y0, x1, y1 = bbox
    k = math.cos(math.radians((y0 + y1) / 2))
    s = min((W - 2 * margin) / ((x1 - x0) * k), (H - 2 * margin) / (y1 - y0))
    # 영역을 화면 비율로 넓힌다 — 좁게 자르면 영역 경계가 세로선으로 그려진다
    dx = ((W - 2 * margin) / s / k - (x1 - x0)) / 2
    dy = ((H - 2 * margin) / s - (y1 - y0)) / 2
    x0, x1, y0, y1 = x0 - dx - .3, x1 + dx + .3, y0 - dy - .3, y1 + dy + .3
    bbox = (x0, y0, x1, y1)
    ox0, oy1 = x0 + .3, y1 - .3
    to = lambda lon, lat: (margin + (lon - ox0) * k * s, margin + (oy1 - lat) * s)  # noqa: E731
    out = []
    for r in _rings():
        xs = [p[0] for p in r]; ys = [p[1] for p in r]
        if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
            continue
        c = clip([tuple(p[:2]) for p in r], bbox)
        if len(c) < 3:
            continue
        pts = [to(*p) for p in c]
        thin = [pts[0]]
        for q in pts[1:]:
            if math.dist(q, thin[-1]) >= tol:
                thin.append(q)
        if len(thin) >= 3:
            a = abs(sum(thin[i][0] * thin[(i + 1) % len(thin)][1] - thin[(i + 1) % len(thin)][0] * thin[i][1] for i in range(len(thin)))) / 2
            if a > 40:
                out.append(thin)
    return out, to
