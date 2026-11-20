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


def _style_on(ctx, style, bg: str):
    from . import style as st
    if isinstance(style, dict):                    # 화풍 값(look) — 이름 대신 축의 값으로
        return ctx.finish(st.look(ctx, style, bg=bg))
    fn = st.STYLES[style]
    if style == "clay":
        return ctx.finish(fn(ctx, bg_top=bg, bg_bot=bg, bounce_col="#e8dfd3"))
    if style == "sketch":
        return ctx.finish(fn(ctx, paper=bg, texture=False))
    return ctx.finish(fn(ctx, bg=bg))


def draw(scene: dict, style: str = "cel", out: Path | str | None = None, res: int = 1080, view: dict | None = None,
         background: str | None = None):
    """형태 → 화풍 → PNG. background 가 없으면 투명(흰 · 검은 바탕으로 두 번 그려 차이로 투명도를 구한다)"""
    from . import style as st
    if not isinstance(style, dict) and style not in STYLES:
        raise ValueError(f"화풍은 {', '.join(STYLES)} 중 하나 또는 값 묶음(look): {style}")
    sc = _scene_with_view(scene, view)
    buf, meta = passes(sc, res)
    return _image(st.Ctx(buf, meta), style, background, out)


# ---------------------------------------------------------------- 움직임(2026-11-20 사용자: 3D 로 빚어 놓고 정지 그림 한 장으로만 쓴다 — 움직임이 없다)
# 형태의 이름 붙은 부품(name)의 값(pos · rot · scale · radii · r · h …)을 시간에 따라 바꿔 프레임마다 다시 그린다 → PNG 묶음(반복 재생).
# 카메라는 쉬는 자세로 한 번 맞추고 모든 프레임에 같이 쓴다(자세가 바뀌어도 화면이 흔들리지 않게).

def _lerp(a, b, t):
    if isinstance(a, list):
        return [_lerp(x, y, t) for x, y in zip(a, b)]
    return a + (b - a) * t


def _track_at(keys: list, t: float, dur: float):
    """[[초, 값], …] — 사이는 부드럽게(cosine). 마지막 키 뒤는 첫 키로 돌아가며 반복"""
    ks = sorted(keys, key=lambda k: k[0])
    if len(ks) == 1:
        return ks[0][1]
    ks = ks + [[dur, ks[0][1]]] if ks[-1][0] < dur else ks
    for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
        if t0 <= t <= t1:
            u = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            import math
            return _lerp(v0, v1, (1 - math.cos(math.pi * u)) / 2)
    return ks[-1][1]


def pose(scene: dict, t: float) -> dict:
    """t 초의 자세 — anim.tracks 의 이름 붙은 부품 값을 바꾼 사본"""
    an = scene.get("anim") or {}
    tracks, dur = an.get("tracks") or {}, float(an.get("dur") or 1.0)
    s = json.loads(json.dumps(scene))

    def walk(n):
        tr = tracks.get(n.get("name")) if isinstance(n, dict) else None
        if tr:
            for k, keys in tr.items():
                n[k] = _track_at(keys, t % dur, dur)
        for c in (n.get("children") or []) if isinstance(n, dict) else []:
            walk(c)
    walk(s["root"])
    return s


def animate(scene: dict, style: str = "cel", out_dir: Path | str | None = None, res: int = 720, view: dict | None = None,
            background: str | None = None) -> dict:
    """움직임 프레임 묶음 → out_dir/f000.png … (투명 PNG). 같은 입력이면 다시 그리지 않는다.
    한 장 약 2초(720 · 화풍 포함) — 12fps · 1~2초 반복이면 12~24장. 만화 · 애니메이션은 원래 12fps(2프레임 한 장)라 어색하지 않다"""
    from . import render
    from . import style as st
    if not isinstance(style, dict) and style not in STYLES:
        raise ValueError(f"화풍은 {', '.join(STYLES)} 중 하나 또는 값 묶음(look): {style}")
    an = scene.get("anim") or {}
    fps, dur = 12, float(an.get("dur") or 1.0)          # 12fps 고정 — 장면(kit · motion)이 12fps 로 들여와 반복한다
    n = max(1, round(fps * dur))
    sc = _scene_with_view(scene, view)
    key = hashlib.sha1(json.dumps([sc, style, res, background], sort_keys=True).encode()).hexdigest()[:12]
    d = Path(out_dir) if out_dir else CACHE / f"anim-{key}"
    stamp = d / "anim.json"
    if stamp.exists() and json.loads(stamp.read_text("utf-8")).get("key") == key and (d / f"f{n - 1:03d}.png").exists():
        return json.loads(stamp.read_text("utf-8"))
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("f*.png"):
        old.unlink()
    rest = pose(sc, 0.0)
    codes, P, _ = __import__("craft.form.sdf", fromlist=["x"]).compile_scene(rest)
    cam = render.auto_camera(rest, codes, P, res)
    eye, f, r, u, th, (lo, hi) = cam
    pad = float(an.get("pad", 0.18))                # 움직이며 쉬는 자세 밖으로 나가는 만큼 여유(화면 맞춤을 넓힌다)
    eye = (eye - (lo + hi) / 2) * (1 + pad) + (lo + hi) / 2
    cam = (eye, f, r, u, th, (lo, hi))
    for i in range(n):
        buf, meta, _ = render.render(pose(sc, i / fps), res, 1, cam=cam)
        _image(st.Ctx(buf, meta), style, background, d / f"f{i:03d}.png")
    info = {"key": key, "dir": str(d), "first": str(d / "f000.png"), "frames": n, "fps": fps, "dur": dur}
    stamp.write_text(json.dumps(info, ensure_ascii=False), "utf-8")
    return info


def _image(ctx, style: str, background: str | None, out):
    from PIL import Image
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
    px = int(style.get("pixel", 0)) if isinstance(style, dict) else 0
    if px > 1:                                     # 픽셀: 크게 깎아 줄이고(가장 가까운 색) 다시 키운다 · 색 수 제한 · 투명도는 켜짐/꺼짐
        from PIL import Image as _I
        w, h = img.size
        small = img.convert("RGBA").resize((max(1, w // px), max(1, h // px)), _I.NEAREST)
        al = small.getchannel("A").point(lambda v: 255 if v > 110 else 0)
        rgb = small.convert("RGB").quantize(colors=int(style.get("colors", 16)), method=_I.Quantize.MEDIANCUT).convert("RGB")
        if style.get("line", 2.5):                 # 픽셀 외곽선: 한 칸 두께(끊긴 선 대신) — 배경을 깔았을 때도 형태 윤곽 기준
            import numpy as _np
            import cv2 as _cv
            a_ = _cv.resize(ctx.hit.astype(_np.uint8), small.size, interpolation=_cv.INTER_AREA) > 0
            er = _np.zeros_like(a_); er[1:-1, 1:-1] = a_[1:-1, 1:-1] & a_[:-2, 1:-1] & a_[2:, 1:-1] & a_[1:-1, :-2] & a_[1:-1, 2:]
            arr = _np.asarray(rgb).copy(); ink = style.get("ink", "#1b1714").lstrip("#")
            arr[a_ & ~er] = [int(ink[i:i + 2], 16) for i in (0, 2, 4)]
            rgb = _I.fromarray(arr)
        small = rgb.convert("RGBA"); small.putalpha(al)
        img = small.resize((w, h), _I.NEAREST)
    elif isinstance(style, dict) and style.get("colors"):
        from PIL import Image as _I
        al = img.convert("RGBA").getchannel("A")
        img = img.convert("RGB").quantize(colors=int(style["colors"]), method=_I.Quantize.MEDIANCUT).convert("RGBA"); img.putalpha(al)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
    return img
