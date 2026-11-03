"""그리기 엔진 — 그림 lint: '초딩 티 · AI 티' 를 재서 막는다(open-design 의 lint-artifact 를 그림에 옮김).

규칙의 근거와 숫자는 rules/illustration/*.md. 여기는 기계로 잴 수 있는 것만:
  P0(그리기 거절)  기본 팔레트 · 회색 그림자 · 실루엣이 감자 · 크기 위계 없음
  P1(경고)         색 비율 · 명도 대비 · 굳은 자세 · 표정 없음 · 접선
결과는 의미로 된 문장 — 좌표가 아니라 형태 · 화풍을 어떻게 고칠지 말한다.
"""
from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

import numpy as np

from . import geom, style as stylemod
from .form import U, Placed


@dataclass
class Finding:
    code: str
    level: str          # P0 | P1
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "level": self.level, "message": self.message}


def _area(shape: geom.Shape, res: float) -> tuple[float, np.ndarray, tuple[float, float]]:
    F, x0, y0 = geom.sample(shape, res)
    inside = F < 0
    return float(inside.sum()) * res * res, inside, (x0, y0)


def _lum(hexs: str) -> float:
    r, g, b = stylemod._hex(hexs)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sat(hexs: str) -> float:
    r, g, b = stylemod._hex(hexs)
    return colorsys.rgb_to_hls(r, g, b)[2]


def silhouette_solidity(placed: list[Placed], res: float) -> float:
    """실루엣 넓이 / 볼록 껍질 넓이. 1 에 가까울수록 특징 없는 감자 모양"""
    shape = geom.Union([p.shape for p in placed if not p.spec.get("decal")])
    F, x0, y0 = geom.sample(shape, res)
    ys, xs = np.nonzero(F < 0)
    if len(xs) < 10:
        return 1.0
    pts = np.stack([xs, ys], 1).astype(float)
    hull = _hull(pts)
    hx, hy = hull[:, 0], hull[:, 1]
    hull_area = 0.5 * abs(np.dot(hx, np.roll(hy, -1)) - np.dot(hy, np.roll(hx, -1)))
    return float(len(xs) / max(hull_area, 1.0))


def _hull(P: np.ndarray) -> np.ndarray:
    P = np.unique(P, axis=0)
    P = P[np.lexsort((P[:, 1], P[:, 0]))]
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in P[::-1]:
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return np.array(lo[:-1] + up[:-1])


def lint(placed: list[Placed], form: dict, style: dict | None, bg: str | None = None, res: float = 2.0) -> list[Finding]:
    st = stylemod.resolve(style)
    out: list[Finding] = []
    is_char = any("eye" in p.id for p in placed)
    vols = [p for p in placed if not p.spec.get("decal")]

    # --- 기본 팔레트(P0): 화풍 카드 · 형태에 팔레트가 없으면 기본 주황을 쓴다
    if not (st.get("palette") or form.get("palette")):
        out.append(Finding("I01", "P0", "팔레트가 없어 기본 색을 씁니다 — 화풍 카드(style.json)의 palette 를 레퍼런스 대표색으로 채우세요"))
    pal = {**__import__("drawlib.render", fromlist=["DEFAULT_PALETTE"]).DEFAULT_PALETTE, **st.get("palette", {}), **(form.get("palette") or {})}

    # --- 회색 그림자(P0)
    if st["shade"].get("tones", 1) >= 2:
        for role in {p.role for p in vols}:
            base = pal.get(role, role)
            if base.startswith("#") and _sat(base) > 0.15:
                sh = stylemod.shift(base, **st["shade"]["shift"])
                if _sat(sh) < 0.12:
                    out.append(Finding("I02", "P0", f"{role} 의 그림자 색이 탁한 회색입니다 — shade.shift 의 s(채도)를 올리고 h 로 색온도를 바꾸세요"))

    # --- 크기 위계(P0): 큰 · 중간 · 작은 덩어리
    areas = sorted((_area(p.shape, res)[0] for p in vols), reverse=True)
    if len(areas) >= 3:
        big, mid = areas[0], areas[len(areas) // 2]
        if big / max(mid, 1e-6) < 2.0:
            out.append(Finding("I03", "P0", f"덩어리 크기가 비슷합니다(가장 큰 것 / 중간 = {big / max(mid, 1e-6):.1f}) — 주인공 덩어리를 키우고 부속을 줄여 큰 · 중간 · 작은 위계를 만드세요(목표 ≥ 2.5)"))

    # --- 실루엣(P0): 감자 모양
    creature = is_char or form.get("archetype") in ("biped", "quadruped", "bird", "blob_creature")
    sol = silhouette_solidity(placed, res) if creature else 0.0   # 건물 · 상자 · 아이콘은 원래 꽉 찬 실루엣
    if sol > 0.93:
        out.append(Finding("I04", "P0", f"실루엣이 밋밋한 덩어리입니다(채움 {sol:.2f}) — 까맣게 칠해도 무엇인지 보이게 튀어나온 특징(귀 · 뿔 · 꼬리 · 벌린 팔 · 소품)을 더하세요(목표 ≤ 0.88)"))

    # --- 색 비율(P1): 60 · 30 · 10
    by_role: dict[str, float] = {}
    for p in placed:
        by_role[p.role] = by_role.get(p.role, 0) + _area(p.shape, res)[0]
    tot = sum(by_role.values()) or 1
    shares = sorted((v / tot for v in by_role.values()), reverse=True)
    if shares and not (0.45 <= shares[0] <= 0.75):
        out.append(Finding("I05", "P1", f"주조색 비율이 {shares[0]:.0%} 입니다 — 60% 안팎(45~75%)이 되게 역할 색을 나누세요"))
    if len(shares) >= 3 and shares[-1] > 0.2:
        out.append(Finding("I05", "P1", "강조색이 너무 넓습니다 — 강조(accent)는 10% 안팎의 작은 부품에만"))

    # --- 명도 대비(P1): 주인공 vs 배경
    if bg:
        main = pal.get("main", "#888888")
        if abs(_lum(main) - _lum(bg)) < 0.22:
            out.append(Finding("I06", "P1", f"주인공 색({main})과 배경({bg})의 밝기가 비슷해 묻힙니다 — 명도 차 0.25 이상으로"))

    # --- 굳은 자세(P1): 동세선 없음
    if is_char:
        root = next((p for p in placed if not p.parent), None)
        tilts = abs(float((root.spec if root else {}).get("tilt", 0)))
        limbs = [p for p in placed if p.spec.get("shape") in ("capsule", "sweep") and p.parent]
        asym = len({round(float(p.spec.get("dir", 0))) for p in limbs}) > 1 if limbs else False
        if tilts < 4 and not asym:
            out.append(Finding("I07", "P1", "자세가 굳어 있습니다 — 몸을 6~15도 기울이거나(tilt) 팔다리를 서로 다르게(dir) 둬서 동세선을 만드세요"))

    # --- 표정(P1)
    if is_char and not any(("brow" in p.id) or ("mouth" in p.id) for p in placed):
        out.append(Finding("I08", "P1", "눈만 있고 표정이 없습니다 — 눈썹(brow) · 입(mouth) 부품을 더하세요"))

    # --- 묻힘(P1): 몸 앞에 겹친 팔다리 · 부속이 몸과 밝기가 거의 같아 안 보임
    byid0 = {p.id: p for p in placed}
    for p in placed:
        par = byid0.get(p.parent) if p.parent else None
        if not par or p.spec.get("decal") or p.spec.get("merge") or p.z <= par.z:
            continue
        if p.spec.get("limb_kind") and par.spec.get("limb_kind"):   # 같은 팔다리의 아랫마디 — 원래 이어진 한 덩어리
            continue
        a_in = _area(geom.Intersect(p.shape, par.shape), res)[0] if True else 0
        a_p = _area(p.shape, res)[0]
        if a_p > 0 and a_in / a_p > 0.4:
            c1, c2 = pal.get(p.role, p.role), pal.get(par.role, par.role)
            if c1.startswith("#") and c2.startswith("#") and abs(_lum(c1) - _lum(c2)) < 0.08:
                out.append(Finding("I10", "P1", f"{p.id} 가 {par.id} 앞에 겹쳐 있는데 밝기가 같아 묻힙니다 — 다른 역할 색을 주거나(장갑 · 소매 · 밝은 테두리) 실루엣 밖으로 빼세요"))

    # --- 알록달록(P1): 한 캐릭터에 쨍한 색이 여러 개 흩어지면 장난감처럼 보인다(전문가는 강조 1~2곳)
    if is_char:
        hues = []
        for p in placed:
            c = pal.get(p.role, p.role)
            if not c.startswith("#") or p.role in ("white", "black"):
                continue
            r_, g_, b_ = stylemod._hex(c)
            h_, l_, s_ = colorsys.rgb_to_hls(r_, g_, b_)
            if s_ > 0.55 and 0.3 < l_ < 0.8 and all(min(abs(h_ - x), 1 - abs(h_ - x)) > 0.06 for x in hues):
                hues.append(h_)
        if len(hues) > 2:
            out.append(Finding("I12", "P1", f"쨍한 색이 {len(hues)}가지로 흩어져 장난감처럼 보입니다 — 강조색은 1~2곳에만, 나머지(장갑 · 신발 등)는 주조색 계열로"))
        # 머리 비율: 머리(head · face · opening 중 가장 큰 것)가 키의 1/3 을 넘으면 아기 비율
        heads = [p for p in placed if p.id in ("head", "face", "opening", "hood")]
        if heads:
            hb = max((p.shape.bounds() for p in heads), key=lambda b: b[3] - b[1])
            allb = [p.shape.bounds() for p in placed]
            tall = max(b[3] for b in allb) - min(b[1] for b in allb)
            if (hb[3] - hb[1]) / max(tall, 1e-6) > 0.34 and form.get("proportion") != "chibi":
                out.append(Finding("I13", "P1", "머리(얼굴)가 키의 1/3 을 넘어 아기 · 인형 비율입니다 — 귀여운 마스코트가 의도면 proportion: \"chibi\", 아니면 머리를 키의 1/5~1/4 로"))

    # --- 구멍이 실루엣을 뚫음(P1): cut 이 부모 밖으로 나가면 구멍이 아니라 찢긴 홈이 된다
    for p in placed:
        if p.spec.get("cut") and p.parent in byid0:
            whole = byid0[p.parent].spec.get("_uncut", byid0[p.parent].shape)
            outside = _area(geom.Subtract(p.shape, whole), res)[0]
            if outside > 0.02 * _area(p.shape, res)[0] + 1:
                out.append(Finding("I11", "P1", f"{p.id}(구멍)이 {p.parent} 가장자리를 뚫고 나가 찢긴 홈이 됩니다 — inset 을 키우거나 구멍을 작게"))

    # --- 접선(P1): 붙은 부품이 가장자리만 겨우 닿음
    byid = {p.id: p for p in placed}
    for p in placed:
        if p.parent and p.parent in byid and not p.spec.get("decal") and not p.spec.get("merge"):
            inset = float((p.spec.get("attach") or {}).get("inset", 0.05))
            if 0 <= inset < 0.03:
                out.append(Finding("I09", "P1", f"{p.id} 가 {p.parent} 에 가장자리만 닿습니다(접선) — inset 0.05 이상으로 겹치거나 확실히 떼세요"))
    return out


def blocking(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.level == "P0"]
