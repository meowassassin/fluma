"""그리기 엔진 3단계 — 화풍 카드(style.json) · 명암 · 하이라이트 · 손맛을 계산으로.

설계: 볼트 02 Architecture/그리기 엔진 설계 — 구조로 그리기.md (4 · 5절)
그림자 · 하이라이트를 손으로 그리지 않는다. 빛 방향 하나로:
  그림자   = 덩어리 − (빛 쪽으로 민 같은 덩어리)       → 빛 반대쪽 초승달
  하이라이트 = 덩어리 − (빛 반대쪽으로 조금 민 같은 덩어리) → 빛 쪽 가장자리 얇은 띠
  바닥 그림자 = 바닥에 닿은 부품 아래 납작한 타원
색은 역할(role) 색에서 화풍의 '그림자 색 이동' 규칙으로 만든다(탁한 회색 그림자 금지).
손맛은 외곽선 점을 법선 방향으로 저주파 잡음만큼 밀어 완벽한 원 · 대칭을 없앤다(같은 대칭이라도 씨앗이 다름).
"""
from __future__ import annotations

import colorsys
import json
import math
from dataclasses import dataclass
from pathlib import Path

from . import geom

DEFAULT_STYLE = {
    "outline": {"on": False, "width": 0.025, "color": "dark"},      # width: 단위 높이 비율 · color: dark(같은 색 짙게) | #hex
    "shade": {"tones": 2, "light": 135, "depth": 0.12, "shift": {"h": 0.03, "s": 0.04, "l": -0.11}},
    "rim": {"on": False, "width": 0.025, "l": 0.12},
    "round": 0.08,                                                   # 합치기 부드러움(단위 높이 비율)
    "wobble": {"amp": 0.0, "freq": 3.0},                             # 손맛: 진폭(단위 높이 비율) · 둘레당 물결 수 — 깨끗한 평면 벡터는 0
    "ground_shadow": {"on": True, "opacity": 0.25},
    "gradient": {"on": True, "amount": 0.07},                      # 빛 쪽이 조금 밝은 같은 색 그라데이션
    "palette": {},
}

PRESETS = {
    # 레퍼런스 측정 전 출발점 — style_card 가 측정값을 덮어쓴다
    "flat-bright": {"outline": {"on": False}, "shade": {"tones": 2, "light": 135, "depth": 0.12, "shift": {"h": 0.03, "s": 0.04, "l": -0.11}},
                    "rim": {"on": False}, "round": 0.1, "wobble": {"amp": 0.0, "freq": 3.0}},
    "flat-minimal": {"outline": {"on": False}, "shade": {"tones": 1}, "rim": {"on": False}, "round": 0.04, "wobble": {"amp": 0.0, "freq": 0}, "gradient": {"on": False}},
    "doodle": {"outline": {"on": True, "width": 0.03, "color": "#1a1a1a"}, "shade": {"tones": 1}, "rim": {"on": False}, "round": 0.06,
               "wobble": {"amp": 0.012, "freq": 4.0}, "ground_shadow": {"on": False}},
}


def merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


STYLES = Path(__file__).resolve().parents[2] / "styles"


def resolve(style: dict | None) -> dict:
    """화풍 카드 → 완성된 값. {"system": 이름} 이면 styles/<이름>/style.json(레퍼런스에서 잰 계약)을 먼저 깐다"""
    s = dict(style or {})
    if s.get("system"):
        f = STYLES / s["system"] / "style.json"
        if f.exists():
            s = merge(json.loads(f.read_text("utf-8")), {k: v for k, v in s.items() if k != "system"})
    base = merge(DEFAULT_STYLE, PRESETS.get(s.get("preset", ""), {}))
    out = merge(base, {k: v for k, v in s.items() if k != "preset"})
    sh = out["shade"].get("shift") or {}
    if "l" in sh:   # 측정값이 지나치면 묶는다 — 그림자가 너무 검거나 안 보이지 않게
        sh["l"] = max(-0.25, min(-0.06, float(sh["l"])))
        sh["s"] = max(-0.1, min(0.15, float(sh.get("s", 0.04))))
        sh["h"] = max(0.0, min(0.08, float(sh.get("h", 0.03))))
    return out


# ---------------------------------------------------------------- 색
def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{max(0, min(255, round(x * 255))):02x}" for x in (r, g, b))


def shift(color: str, h: float = 0.0, s: float = 0.0, l: float = 0.0) -> str:
    """HLS 로 옮긴 색 — 그림자는 색상을 차갑게(보라 쪽) · 채도 조금 올리고 · 어둡게"""
    r, g, b = _hex(color)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    # 색상은 파랑 · 보라(0.7) 쪽으로 h 만큼 당긴다
    target = 0.7
    d = ((target - hh + 0.5) % 1.0) - 0.5
    hh = (hh + max(-abs(h), min(abs(h), d))) % 1.0
    # 어두운 색에서 더 빼면 검정(채도 0)이 된다 → 원래 밝기의 55% 아래로는 내리지 않는다
    nl = max(ll * 0.55, ll + l) if l < 0 else ll + l
    return _to_hex(*colorsys.hls_to_rgb(hh, max(0, min(1, nl)), max(0, min(1, ss + s))))


# ---------------------------------------------------------------- 명암 덩어리
@dataclass
class Shifted(geom.Shape):
    a: geom.Shape
    dx: float
    dy: float

    def sdf(self, X, Y):
        return self.a.sdf(X - self.dx, Y - self.dy)

    def bounds(self):
        b = self.a.bounds()
        return (b[0] + self.dx, b[1] + self.dy, b[2] + self.dx, b[3] + self.dy)


def light_vec(deg: float) -> tuple[float, float]:
    """빛이 오는 쪽 단위 벡터(화면 좌표, y 아래). 135 = 왼쪽 위"""
    a = math.radians(deg)
    return (math.cos(a), -math.sin(a))


def _minor(shape: geom.Shape) -> float:
    b = shape.bounds()
    return max(1e-6, min(b[2] - b[0], b[3] - b[1]))


def shadow_shape(shape: geom.Shape, unit: float, st: dict) -> geom.Shape:
    """빛 반대쪽 그림자: 덩어리 − (빛 쪽으로 민 · 조금 키운 덩어리), 그리고 '열기'(줄였다 키우기)로 가는 찌꺼기를 지운다.
    키워서 빼면 그림자 경계가 외곽선과 분명한 각도로 만나 바늘 같은 끝이 생기지 않는다. 깊이는 부품 굵기에 비례"""
    lx, ly = light_vec(st["shade"]["light"])
    m = _minor(shape)
    d = min(st["shade"]["depth"] * unit, 0.3 * m)
    grow = 0.15 * m                           # 빛과 나란한 가장자리까지 덮어 가는 띠가 남지 않게
    raw = geom.Intersect(shape, geom.Offset(geom.Subtract(shape, Shifted(geom.Offset(shape, grow), lx * d, ly * d)), 0.0))
    r = min(max(0.012 * unit, 0.1 * m), 0.35 * d)   # 가는 조각(바늘 · 찌꺼기)은 지우되, 그림자 깊이보다 크게 깎아 큰 부품 명암이 사라지지 않게
    # 다시 키울 때 모서리 근처에서 원래 모양보다 커질 수 있다 → 마지막에 덩어리 안으로 잘라 그림자가 실루엣 밖으로 삐져나오지 않게
    return geom.Intersect(shape, geom.Offset(geom.Offset(raw, -r), r))


def rim_shape(shape: geom.Shape, unit: float, st: dict) -> geom.Shape:  # 가장자리 하이라이트 — 기본은 끔(가는 띠는 엉성해 보인다)
    """빛 쪽 가장자리 띠: 덩어리 − (빛 반대쪽으로 조금 민 덩어리)"""
    lx, ly = light_vec(st["shade"]["light"])
    d = min(st["rim"]["width"] * unit, 0.12 * _minor(shape))
    return geom.Subtract(shape, Shifted(shape, -lx * d, -ly * d), k=d * 0.3)
