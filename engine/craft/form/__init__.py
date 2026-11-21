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

STYLES = ("flat", "cel", "sketch", "clay", "vector")      # vector: VectorCraft 벡터 마감(engine/craft/form/vector.py)
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
CACHE = ROOT / "data" / "workspace" / "cache" / "form"
RENDER_VERSION = 15          # 렌더러(카메라 맞춤 · 광선 추적)가 바뀌면 올린다 — 캐시가 예전 그림을 내지 않게(2026-11-20: 카메라 범위를 고쳐도 잘린 그림이 그대로 나왔다)


def _scene_with_view(scene: dict, view: dict | None) -> dict:
    s = json.loads(json.dumps(scene))
    if view:
        s.setdefault("camera", {}).update({k: v for k, v in view.items() if k in ("azimuth", "elevation", "fov", "frame", "target")})
    return s


def expand_rigs(n):
    """뼈대 노드(rig)를 도형 트리로 펼친 사본 — 캐시 열쇠가 펼친 결과로 정해지게(뼈대 코드가 바뀌면 다시 그린다)"""
    if isinstance(n, dict):
        if "rig" in n:
            from .skeleton import expand
            return expand_rigs(expand(n))
        return {k: expand_rigs(v) for k, v in n.items()}
    if isinstance(n, list):
        return [expand_rigs(x) for x in n]
    return n


def passes(scene: dict, res: int = 1080, ss: int = 2):
    """렌더 정보(깊이 · 면 방향 · 부위 · 빛) — 형태 · 카메라 · 크기가 같으면 캐시에서"""
    from . import render
    from .world import prepare
    scene = prepare(scene, float(scene.get("t", 0.0)))        # 뼈대 → 도형(지형 · 이동 · 소품 배치 포함), 시간 t
    key = hashlib.sha1(json.dumps([scene, res, ss, RENDER_VERSION], sort_keys=True).encode()).hexdigest()[:16]
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
        img = fn(ctx, bg_top=bg, bg_bot=bg, bounce_col="#e8dfd3")
    elif style == "sketch":
        img = fn(ctx, paper=bg, texture=False)
    else:
        img = fn(ctx, bg=bg)
    if img.shape[0] == ctx.N:                              # 얼굴 획(이목구비)은 화풍 위에 매끈한 곡선으로
        img = st.draw_strokes(ctx, np.ascontiguousarray(img, np.float32))
    return ctx.finish(img)


def parts_apart(scene: dict, view: dict | None = None, res: int = 360) -> int:
    """화면에서 몸과 이어지지 않은 덩어리 수(0 이면 모두 이어짐) — 발이 다리에서 떨어지는 등. 아주 작은 조각(0.3% 미만)은 센다지 않는다"""
    import cv2
    buf, _ = passes(_scene_with_view(scene, view), res)
    m = (buf["hit"] > 0.5).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    areas = st[1:, cv2.CC_STAT_AREA]
    if not len(areas):
        return 0
    return int((areas > 0.003 * areas.sum()).sum() - 1)


def draw(scene: dict, style: str = "cel", out: Path | str | None = None, res: int = 1080, view: dict | None = None,
         background: str | None = None):
    """형태 → 화풍 → PNG. background 가 없으면 투명(흰 · 검은 바탕으로 두 번 그려 차이로 투명도를 구한다)"""
    from . import style as st
    if style not in STYLES:
        raise ValueError(f"화풍은 {', '.join(STYLES)} 중 하나: {style}")
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


def _hermite(p0, p1, m0, m1, u):
    if isinstance(p0, list):
        return [_hermite(a, b, c, d, u) for a, b, c, d in zip(p0, p1, m0, m1)]
    u2, u3 = u * u, u * u * u
    return (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m1


def _scale(v, k):
    return [_scale(x, k) for x in v] if isinstance(v, list) else v * k


def _sub(a, b):
    return [_sub(x, y) for x, y in zip(a, b)] if isinstance(a, list) else a - b


def _track_at(keys: list, t: float, dur: float):
    """[[초, 값], …] — 키를 지나며 멈추지 않고 이어 흐른다(Catmull-Rom, 속도가 이어짐). 마지막 키 뒤는 첫 키로 돌아가며 반복.
    2026-11-20: 키마다 속도가 0 이 되는 cosine 보간이 모든 동작을 로봇처럼 멈칫거리게 했다. 멈춰야 할 곳은 같은 값의 키를 두 번 둔다(유지)"""
    ks = sorted(keys, key=lambda k: k[0])
    if len(ks) == 1:
        return ks[0][1]
    if any(isinstance(k[1], str) for k in ks):            # 글자 값(관절 이름 등)은 섞지 않고 그 시각의 값
        return next((k[1] for k in reversed(ks) if k[0] <= t), ks[0][1])
    loop = ks[-1][0] < dur
    pts = ks + [[dur, ks[0][1]]] if loop else ks
    n = len(pts)
    for i in range(n - 1):
        (t0, v0), (t1, v1) = pts[i], pts[i + 1]
        if t0 <= t <= t1:
            h = (t1 - t0) or 1e-6
            u = (t - t0) / h

            def slope(j):                                 # 이웃 키로 기울기(같은 값 두 키 사이는 0 — 유지)
                a = pts[j - 1] if j > 0 else ([pts[-2][0] - dur, pts[-2][1]] if loop and n > 2 else pts[j])
                b = pts[j + 1] if j < n - 1 else ([pts[1][0] + dur, pts[1][1]] if loop and n > 2 else pts[j])
                if b[0] == a[0]:
                    return _scale(pts[j][1], 0.0)
                if pts[j][1] == (pts[j - 1][1] if j > 0 else None) or pts[j][1] == (pts[j + 1][1] if j < n - 1 else None):
                    return _scale(pts[j][1], 0.0)
                return _scale(_sub(b[1], a[1]), h / (b[0] - a[0]))
            return _hermite(v0, v1, slope(i), slope(i + 1), u)
    return pts[-1][1]


def pose(scene: dict, t: float) -> dict:
    """t 초의 자세 — anim.tracks 의 이름 붙은 부품 값을 바꾼 사본"""
    an = scene.get("anim") or {}
    tracks, dur = an.get("tracks") or {}, float(an.get("dur") or 1.0)
    s = json.loads(json.dumps(scene))

    def walk(n):
        tr = tracks.get(n.get("name")) if isinstance(n, dict) else None
        if tr:
            for k, keys in tr.items():
                v = _track_at(keys, t % dur, dur)
                if "." in k:                              # 뼈대 안쪽 값 — "pose.r_elbow" · "pose.head" · "face.smile"
                    path = k.split(".")
                    d = n
                    for part in path[:-1]:
                        d = d.setdefault(part, {})
                    d[path[-1]] = v
                else:
                    n[k] = v
        for c in (n.get("children") or []) if isinstance(n, dict) else []:
            walk(c)
    walk(s["root"])
    for k, keys in (tracks.get("camera") or {}).items():   # 카메라도 움직인다(focus · azimuth · radius …)
        s.setdefault("camera", {})[k] = _track_at(keys, t % dur, dur)
    return s


def animate(scene: dict, style: str = "cel", out_dir: Path | str | None = None, res: int = 720, view: dict | None = None,
            background: str | None = None) -> dict:
    """움직임 프레임 묶음 → out_dir/f000.png … (투명 PNG). 같은 입력이면 다시 그리지 않는다.
    한 장 약 0.5~2초 — 이동 · 카메라가 있으면 24fps, 제자리 동작은 12fps"""
    from . import render
    from . import style as st
    if style not in STYLES:
        raise ValueError(f"화풍은 {', '.join(STYLES)} 중 하나: {style}")
    an = scene.get("anim") or {}
    dur = float(an.get("dur") or 1.0)
    # 2026-11-21: 12fps 고정이었다 — 손그림은 2프레임 한 장이어도 그림이 이어지지만 입체 렌더를 12장으로 끊으면 걷기 · 카메라가 뚝뚝 끊겼다.
    # 이동(move) · 카메라 트랙 · 따라가기가 있으면 24fps, 제자리 동작(숨쉬기 · 표정)은 12fps. anim.fps 로 직접 정할 수 있다
    moving = '"move"' in json.dumps(scene.get("root")) or bool((an.get("tracks") or {}).get("camera")) or an.get("camera") == "follow"
    fps = int(an.get("fps") or (24 if moving else 12))
    n = max(1, round(fps * dur))
    sc = _scene_with_view(scene, view)
    key = hashlib.sha1(json.dumps([sc, style, res, background, fps, RENDER_VERSION], sort_keys=True).encode()).hexdigest()[:12]
    d = Path(out_dir) if out_dir else CACHE / f"anim-{key}"
    stamp = d / "anim.json"
    if stamp.exists() and json.loads(stamp.read_text("utf-8")).get("key") == key and (d / f"f{n - 1:03d}.png").exists():
        return json.loads(stamp.read_text("utf-8"))
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("f*.png"):
        old.unlink()
    from .world import prepare
    from . import sdf as _sdf
    lag = float(an.get("overlap", 0.07))
    frame = lambda t: prepare(_overlap(pose(sc, t), pose(sc, t - lag)) if lag > 0 else pose(sc, t), t)  # noqa: E731 — 시간 t 의 장면
    follow = "camera" in (an.get("tracks") or {}) or an.get("camera") == "follow"   # 카메라 칸을 움직이거나 follow 면 프레임마다 다시 맞춘다
    if an.get("camera") == "follow":                       # 따라가기: 움직이는 뼈대(move)의 골반을 가운데에, 키의 0.75 배 반지름
        from .world import Ground, locomotion
        mover = _find_mover(sc["root"])
        if mover is not None:
            g0 = Ground(sc)
            base = frame
            def frame(t, _b=base, _m=mover, _g=g0):  # noqa: E731
                f_ = _b(t)
                lo = locomotion(_m, t, _g)
                H = float((_m.get("size") or {}).get("height", 1.7))
                f_["camera"] = {**(f_.get("camera") or {}), "focus": [float(lo["origin"][0]), float(lo["pelvis_y"]), float(lo["origin"][2])],
                                "radius": float(an.get("radius", 0.75)) * H}
                return f_
    cam = None
    if not follow:                                         # 고정 카메라: 처음 · 가운데 · 끝 자세를 모두 담게 맞춘다(걸어가도 화면 밖으로 안 나감)
        fr = [frame(t) for t in (0.0, dur / 2, max(0.0, dur - 1 / fps))]
        uni = {**fr[0], "root": {"op": "union", "children": [x["root"] for x in fr]}}
        codes, P, _ = _sdf.compile_scene(uni)
        eye, f, r, u, th, (lo, hi) = render.auto_camera(uni, codes, P, res)
        pad = float(an.get("pad", 0.12))
        eye = (eye - (lo + hi) / 2) * (1 + pad) + (lo + hi) / 2
        cam = (eye, f, r, u, th, (lo, hi))
    for i in range(n):
        buf, meta, _ = render.render(frame(i / fps), res, 1, cam=cam)
        _image(st.Ctx(buf, meta), style, background, d / f"f{i:03d}.png")
    info = {"key": key, "dir": str(d), "first": str(d / "f000.png"), "frames": n, "fps": fps, "dur": dur}
    stamp.write_text(json.dumps(info, ensure_ascii=False), "utf-8")
    return info


DISTAL = ("head", "l_elbow", "r_elbow", "l_grip", "r_grip", "l_spread", "r_spread")


def _overlap(cur, lagged):
    """겹침 · 따라오기 — 끝 관절(고개 · 팔꿈치 · 손)은 조금 늦은 시각의 값을 쓴다. 몸통이 먼저 움직이고 끝이 따라온다"""
    if isinstance(cur, dict) and isinstance(lagged, dict):
        if "rig" in cur and isinstance(cur.get("pose"), dict) and isinstance(lagged.get("pose"), dict):
            cur = {**cur, "pose": {**cur["pose"], **{k: lagged["pose"][k] for k in DISTAL if k in lagged["pose"]}}}
        return {k: (_overlap(v, lagged.get(k)) if k != "pose" else v) for k, v in cur.items()}
    if isinstance(cur, list) and isinstance(lagged, list) and len(cur) == len(lagged):
        return [_overlap(a, b) for a, b in zip(cur, lagged)]
    return cur


def _find_mover(n):
    if isinstance(n, dict):
        if "rig" in n and n.get("move"):
            return n
        for v in n.values():
            r = _find_mover(v)
            if r is not None:
                return r
    elif isinstance(n, list):
        for v in n:
            r = _find_mover(v)
            if r is not None:
                return r
    return None


def edge_cut(img, thr: float = 0.004) -> list[str]:
    """그림이 화면 가장자리에서 잘린 쪽(투명 PNG 기준, 그림자처럼 옅은 것은 빼고) — 받침판 · 소품이 테두리에서 직선으로 끊기는 것"""
    a = np.asarray(img.convert("RGBA"))[..., 3] > 200
    sides = {"위": a[0], "아래": a[-1], "왼쪽": a[:, 0], "오른쪽": a[:, -1]}
    return [k for k, v in sides.items() if v.mean() > thr]


def _image(ctx, style: str, background: str | None, out):
    from PIL import Image
    if style == "vector":                                 # 부위 영역 → 베지어 경로 → VectorCraft(투명 PNG 그대로)
        import tempfile
        from . import vector
        dst = Path(out) if out else Path(tempfile.mkstemp(suffix=".png")[1])
        dst.parent.mkdir(parents=True, exist_ok=True)
        vector.draw(ctx, dst, bg=background)
        return Image.open(dst).convert("RGBA")
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
