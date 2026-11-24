"""VectorCraft 마감 — 렌더가 아는 부위 영역(재질) · 명암 경계를 매끈한 베지어 경로로 바꿔 벡터 일러스트로 다시 그린다(2026-11-20).

래스터 렌더를 그대로 쓰면 가장자리가 3D 렌더 같고, 이미지 트레이스는 색이 틀어졌다. 여기서는 픽셀을 짐작해 따지 않는다 —
렌더 버퍼의 재질 번호 · 빛 값으로 영역이 정확하다. 영역 윤곽은 매끄럽게 다듬어(가우시안 · 단순화 · Catmull-Rom → 3차 베지어)
VectorCraft 경로(면 · 그림자 면 · 부위 경계 가는 선 · 실루엣 굵은 선)로 그리고 PNG(+ 편집 파일 .vectorcraft)로 낸다.
화풍 이름 "vector" 로 쓴다(form.draw · animate · 재료 style).
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np



def _hex(rgb) -> str:
    c = np.clip(np.asarray(rgb, float) * 255 + 0.5, 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c)


def _smooth(pts: np.ndarray, sigma: float) -> np.ndarray:
    n = len(pts)
    if n < 8 or sigma <= 0:
        return pts
    k = int(3 * sigma) | 1
    w = np.exp(-0.5 * (np.arange(-k, k + 1) / sigma) ** 2); w /= w.sum()
    ext = np.vstack([pts[-k:], pts, pts[:k]])
    return np.stack([np.convolve(ext[:, i], w, mode="same")[k:k + n] for i in (0, 1)], 1)


def _bezier(pts: np.ndarray) -> str:
    """닫힌 점 목록 → Catmull-Rom 을 3차 베지어로(매끈한 곡선)"""
    n = len(pts)
    out = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1, c2 = p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6
        out.append(f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(out) + " Z"


def region_d(mask: np.ndarray, scale: float, smooth_px: float, min_area: float) -> str | None:
    """마스크 → 구멍까지 포함한 SVG 경로(바깥 · 구멍 고리, even-odd 로 칠한다)"""
    cs, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    parts = []
    for c in cs:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        p = c[:, 0, :].astype(float) * scale
        p = _smooth(p, smooth_px)
        p = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), 0.35, True)[:, 0, :].astype(float)
        if len(p) >= 3:
            parts.append(_bezier(p))
    return " ".join(parts) or None


def draw(ctx, out: Path, bg: str | None = None, ink: str = "#2a1c14", line: float = 6.4, inner: float = 2.2, shade: bool = True) -> Path:
    """렌더 정보(style.Ctx) → VectorCraft 벡터 그림 PNG(배경 없으면 투명) + .vectorcraft.
    line · inner: 선 지름(1080 출력 기준 px) — cel 화풍의 외곽선(반지름 3.2 · 1.2)과 같은 굵기"""
    N, ss = ctx.N, ctx.ss
    R = N // ss
    sc = 1.0 / ss
    hit = ctx.hit
    lv = ctx.lv * (0.55 + 0.45 * ctx.b["ao"])
    smooth_px = max(0.8, 1.2 * R / 1080)
    min_area = (R * 0.0015) ** 2 * ss * ss
    steps = [{"command": "file.new", "params": {"width": R, "height": R, "units": "Pixels"}}]
    if bg:
        steps.extend([{"command": "shape.rectangle", "params": {"x": 0, "y": 0, "width": R, "height": R}},
                      {"command": "paint.setFill", "params": {"color": bg}}, {"command": "paint.setStroke", "params": {"none": True}}])
    mats = [m for m in np.unique(ctx.mat[hit]) if m >= 0]
    regions = sorted(((int((hit & (ctx.mat == m)).sum()), m) for m in mats), reverse=True)   # 큰 부위부터 — 작은 부위(눈 · 입)가 위에

    def add(d, fill=None, stroke=None, weight=None, rule="evenOdd"):
        steps.append({"command": "path.create", "params": {"d": d, "closed": True}})
        steps.append({"command": "path.setFillRule", "params": {"rule": rule}})
        steps.append({"command": "paint.setFill", "params": {"color": fill} if fill else {"none": True}})
        if stroke:
            steps.extend([{"command": "paint.setStroke", "params": {"color": stroke}},
                          {"command": "stroke.set", "params": {"weight": weight, "join": "round", "cap": "round"}}])
        else:
            steps.append({"command": "paint.setStroke", "params": {"none": True}})
    lw_in = max(0.6, inner * R / 1080)
    for _, m in regions:
        reg = hit & (ctx.mat == m)
        d = region_d(reg, sc, smooth_px, min_area)
        if not d:
            continue
        add(d, fill=_hex(ctx.base_t[m]), stroke=ink, weight=lw_in)
        if shade:
            sh = reg & (lv < 0.2)
            sh = cv2.morphologyEx(sh.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
            ds = region_d(sh, sc, smooth_px * 1.5, min_area * 4)
            if ds:
                add(ds, fill=_hex(ctx.shadow_t[m]))
    from .style import stroke_layers                       # 얼굴 이목구비(눈 · 눈썹 · 입) · 머리 하이라이트 띠 — 래스터와 같은 획을 경로로
    for col, mk in stroke_layers(ctx):
        d = region_d(mk, sc, smooth_px * 0.6, min_area * 0.05)
        if d:
            add(d, fill=_hex(col))
    dsil = region_d(hit, sc, smooth_px, min_area)
    if dsil:
        add(dsil, stroke=ink, weight=max(1.0, line * R / 1080))        # 실루엣 굵은 선(면 없음)
    out = Path(out)
    with tempfile.TemporaryDirectory() as td:
        sp = Path(td) / "steps.json"
        sp.write_text(json.dumps(steps), "utf-8")
        from craft.materials import cli as craft_cli                     # 설치 기록(installed.json)의 실행 파일 — 운영체제마다 경로가 다르다(macOS .app · Windows .exe)
        cli = craft_cli("vectorcraft")
        r = subprocess.run([str(cli), "run", "--commands", str(sp), "--export", str(out), "--export", str(out.with_suffix(".vectorcraft")), "--scale", "1"],
                           capture_output=True, text=True, timeout=300, env={**os.environ, "VECTORCRAFT_NO_PREFS": "1"})
        if r.returncode != 0 or not out.exists():
            raise RuntimeError("VectorCraft 마감 실패: " + (r.stderr or r.stdout)[-300:])
    return out
