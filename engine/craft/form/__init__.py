"""형태(form) — 에이전트가 데이터로 빚은 형태(SDF: 기본 도형을 녹여 붙임)를 영상의 화풍으로 그린다.

형태와 화풍을 나눈다(2026-11-19 사용자: 3D 렌더가 화풍을 하나로 고정해 버린다 · 영상마다 원본이어야 한다):
  형태 = 콘티 재료 type "form" 의 scene(부품 목록 — engine/craft/form/README.md) — 영상마다 새로 빚는다
  화풍 = flat(평면 일러스트) · cel(셀 카툰) · sketch(연필 스케치) · clay(클레이 3D) — 아트 디렉션 direction.art.style
같은 형태의 렌더 정보(passes)는 캐시해서, 화풍 · 투명 배경만 바꿀 때는 다시 계산하지 않는다(장당 약 0.5~1초).
결과는 투명 배경 PNG — 장면 위에 다른 재료처럼 얹는다. 바닥 그림자는 반투명으로 남는다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

STYLES = ("flat", "cel", "sketch", "clay")
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
CACHE = ROOT / "data" / "workspace" / "cache" / "form"


def _scene_with_view(scene: dict, view: dict | None) -> dict:
    s = json.loads(json.dumps(scene))
    if view:
        s.setdefault("camera", {}).update({k: v for k, v in view.items() if k in ("azimuth", "elevation", "fov", "frame", "target")})
    return s


def passes(scene: dict, res: int = 1080, ss: int = 2):
    """렌더 정보(깊이 · 면 방향 · 부위 · 빛) — 형태 · 카메라 · 크기가 같으면 캐시에서"""
    from . import render
    key = hashlib.sha1(json.dumps([scene, res, ss], sort_keys=True).encode()).hexdigest()[:16]
    f = CACHE / f"{key}.npz"
    if f.exists():
        try:
            return render.load(str(f))
        except Exception:  # noqa: BLE001 - 깨진 캐시는 다시
            pass
    buf, meta, _ = render.render(scene, res, ss)
    CACHE.mkdir(parents=True, exist_ok=True)
    render.save(buf, meta, str(f))
    return buf, meta


def _style_on(ctx, style: str, bg: str):
    from . import style as st
    fn = st.STYLES[style]
    if style == "clay":
        return ctx.finish(fn(ctx, bg_top=bg, bg_bot=bg, bounce_col="#e8dfd3"))
    if style == "sketch":
        return ctx.finish(fn(ctx, paper=bg, texture=False))
    return ctx.finish(fn(ctx, bg=bg))


def draw(scene: dict, style: str = "cel", out: Path | str | None = None, res: int = 1080, view: dict | None = None,
         background: str | None = None):
    """형태 → 화풍 → PNG. background 가 없으면 투명(흰 · 검은 바탕으로 두 번 그려 차이로 투명도를 구한다)"""
    from PIL import Image
    from . import style as st
    if style not in STYLES:
        raise ValueError(f"화풍은 {', '.join(STYLES)} 중 하나: {style}")
    sc = _scene_with_view(scene, view)
    buf, meta = passes(sc, res)
    ctx = st.Ctx(buf, meta)
    if background:
        img = Image.fromarray(_style_on(ctx, style, background))
    else:
        w = _style_on(ctx, style, "#ffffff").astype(np.float32) / 255
        b = _style_on(ctx, style, "#000000").astype(np.float32) / 255
        a = np.clip(1 - (w - b).mean(axis=2), 0, 1)
        rgb = np.clip(b / np.maximum(a[..., None], 1e-3), 0, 1)
        if style == "sketch":                         # 연필 · 물감은 종이 위에 겹쳐 칠하는 매체 — 형태 안쪽은 종이째 오려 낸다(어두운 배경에서도 보이게)
            import cv2
            paper = _style_on(ctx, style, "#f7efdf").astype(np.float32) / 255
            R = paper.shape[0]
            m = cv2.resize(ctx.hit.astype(np.float32), (R, R), interpolation=cv2.INTER_AREA)
            m = cv2.GaussianBlur(cv2.dilate(m, np.ones((5, 5), np.uint8)), (0, 0), 1.2)
            rgb = rgb * (1 - m[..., None]) + paper * m[..., None]
            a = np.maximum(a, m)
        a[a < 0.02] = 0
        img = Image.fromarray(np.dstack([(rgb * 255 + 0.5).astype(np.uint8), (a * 255 + 0.5).astype(np.uint8)]), "RGBA")
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
    return img
