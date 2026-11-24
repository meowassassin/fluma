"""Numba SDF ray marcher -> geometric/lighting passes (style-agnostic G-buffer).

python render.py scene.json [--res 1080] [--ss 2]  -> out/<name>_passes.npz
Passes (float32, HxW): hit, depth, pos(3), nrm(3), mat, ndl(key), shadow(key), fill(ndl fill),
ndh(key half vector), ndv, ao, gshadow (ground shadow), gao (ground contact AO), gpos(xz).
"""
import time, math, json, os
import numpy as np
from numba import njit, prange
from . import sdf

_H = os.path.dirname(os.path.abspath(__file__))


def _numba_stamp():
    """numba 캐시는 파일마다 따로 본다 — sdf.py 의 커널만 고치면 render.py 커널이 옛 sdf 코드를 품은 채 캐시에서 나온다(2026-11-24).
    두 파일 내용이 바뀌었으면 두 파일의 numba 캐시를 지운다"""
    import hashlib
    pc = os.path.join(_H, "__pycache__")
    h = hashlib.sha1(b"".join(open(os.path.join(_H, f), "rb").read() for f in ("sdf.py", "render.py"))).hexdigest()
    st = os.path.join(pc, "kernels.stamp")
    try:
        if open(st).read() == h:
            return
    except OSError:
        pass
    try:
        for e in os.scandir(pc):
            if (e.name.startswith("render.") or e.name.startswith("sdf.")) and e.name.endswith((".nbi", ".nbc")):
                os.remove(e.path)
        os.makedirs(pc, exist_ok=True)
        open(st, "w").write(h)
    except OSError:
        pass


_numba_stamp()


def _norm(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)


def auto_camera(scene, codes, P, res):
    cam = scene.get("camera", {})
    if cam.get("focus") is not None:                       # 초점 · 반지름이 화면 범위를 이미 정했다 — 형태 전체를 격자로 잴 필요 없음(따라가기 · 줌 프레임마다 약 1초 절약)
        fc, rr = np.asarray(cam["focus"], float), float(cam.get("radius", 0.2))
        return _fit(cam, fc - rr, fc + rr)
    g = np.linspace(-3, 3, 72)
    vol = sdf._grid(codes, P, g)
    idx = np.argwhere(vol < 0)
    lo, hi = g[idx.min(0)] - 0.05, g[idx.max(0)] + 0.05
    # 두 번째로 촘촘하게 — 첫 격자(칸 0.08)는 부리 · 손가락 · 꼬리 끝처럼 얇은 부분을 놓쳐 화면 밖으로 잘렸다
    span = float(np.max(hi - lo)) + 0.3
    g2 = np.linspace(-span / 2, span / 2, 96)
    ctr = (lo + hi) / 2
    try:
        sh = P.copy()
        sh[:, 9:12] -= np.where((np.asarray(codes)[:, None] < 100) | (np.asarray(codes)[:, None] == 106) | (np.asarray(codes)[:, None] == 200), ctr[None, :], 0.0)   # 도형 위치를 가운데로 옮겨 같은 정육면체 격자로 잰다
        vol2 = sdf._grid(codes, sh, g2)
        idx2 = np.argwhere(vol2 < 0)
        if len(idx2):
            lo, hi = g2[idx2.min(0)] + ctr - 0.03, g2[idx2.max(0)] + ctr + 0.03
    except Exception:  # noqa: BLE001 - 다시 재기에 실패하면 첫 범위로
        pass
    lo[1] = max(lo[1], 0.0)
    return _fit(cam, lo, hi)


def _fit(cam, lo, hi):
    center = (lo + hi) / 2
    az, el = math.radians(cam.get("azimuth", 35)), math.radians(cam.get("elevation", 18))
    fov = math.radians(cam.get("fov", 30))
    fill = cam.get("fill", 0.86)
    asp = float(cam.get("aspect", 1.0))                    # 세로 / 가로(9:16 세로 화면이면 1.777…) — 한 장면 전체를 그릴 때
    dirv = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    target = center.copy()
    dist = 5.0
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    th = math.tan(fov / 2)
    for _ in range(4):
        eye = target + dirv * dist
        f = _norm(target - eye); r = _norm(np.cross(f, [0, 1, 0])); u = np.cross(r, f)
        rel = corners - eye
        z = rel @ f
        sx = (rel @ r) / z / th; sy = (rel @ u) / z / th / asp
        # recenter target on screen bbox center, then fit largest extent to `fill`
        cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
        target = target + (r * cx + u * cy * asp) * (float((target - eye) @ f) * th)
        ext = max(sx.max() - sx.min(), sy.max() - sy.min()) / 2
        dist *= ext / fill
    eye = target + dirv * dist
    f = _norm(target - eye); r = _norm(np.cross(f, [0, 1, 0])); u = np.cross(r, f)
    return eye, f, r, u, th, (lo, hi)


@njit(cache=True, fastmath=True)
def _normal(x, y, z, codes, P, sd, sm):
    e = 0.0015
    a = sdf.sdf_eval(x + e, y - e, z - e, codes, P, sd, sm)[0]
    b = sdf.sdf_eval(x - e, y - e, z + e, codes, P, sd, sm)[0]
    c = sdf.sdf_eval(x - e, y + e, z - e, codes, P, sd, sm)[0]
    d = sdf.sdf_eval(x + e, y + e, z + e, codes, P, sd, sm)[0]
    nx = a - b - c + d; ny = -a - b + c + d; nz = -a + b - c + d
    l = math.sqrt(nx * nx + ny * ny + nz * nz) + 1e-12
    return nx / l, ny / l, nz / l


@njit(cache=True, fastmath=True)
def _softshadow(x, y, z, lx, ly, lz, codes, P, sd, sm, k, tmax):
    res = 1.0; t = 0.025
    for _ in range(128):                                   # 2026-11-23: 걸음이 커서(최소 0.012) 얇은 물체(숟가락 자루) 그림자에 물결 띠 — 최소 걸음을 줄이고 더 걷는다
        h = sdf.sdf_eval(x + lx * t, y + ly * t, z + lz * t, codes, P, sd, sm)[0]
        # 출발 근처(0.2 안)는 실제로 막힐 때만 — 빛이 비스듬한 매끈한 면(단지 · 라벨)에서 광선이 제 면을 스쳐 나뭇결 같은 띠가 생겼다
        if t < 0.2:
            if h < 0.0015:
                res = 0.0
        else:
            res = min(res, k * h / t)
        if res < 0.002 or t > tmax:
            break
        t += min(max(h, 0.004), 0.2)
    res = min(max(res, 0.0), 1.0)
    return res * res * (3 - 2 * res)


@njit(cache=True, fastmath=True)
def _ao(x, y, z, nx, ny, nz, codes, P, sd, sm):
    occ = 0.0; sca = 1.0
    for i in range(6):
        h = 0.02 + 0.06 * i
        d = sdf.sdf_eval(x + nx * h, y + ny * h, z + nz * h, codes, P, sd, sm)[0]
        occ += (h - d) * sca
        sca *= 0.8
    return min(max(1.0 - 2.2 * occ, 0.0), 1.0)


@njit(cache=True, fastmath=True, parallel=True)
def march(codes, P, W, H, eye, f, r, u, th, L, Lf, bc, br, out, asp=1.0, ground=True):
    for j in prange(H):
        sd = np.empty(32); sm = np.empty(32)
        for i in range(W):
            px = ((i + 0.5) / W * 2 - 1) * th
            py = (1 - (j + 0.5) / H * 2) * th * asp
            dx = f[0] + r[0] * px + u[0] * py
            dy = f[1] + r[1] * px + u[1] * py
            dz = f[2] + r[2] * px + u[2] * py
            dl = math.sqrt(dx * dx + dy * dy + dz * dz); dx /= dl; dy /= dl; dz /= dl
            ox, oy, oz = eye[0], eye[1], eye[2]
            # bounding sphere
            cx, cy, cz = ox - bc[0], oy - bc[1], oz - bc[2]
            b = cx * dx + cy * dy + cz * dz
            c = cx * cx + cy * cy + cz * cz - br * br
            disc = b * b - c
            hit = False; t = 0.0; m = -1
            if disc > 0:
                t = max(-b - math.sqrt(disc), 0.0)
                tend = -b + math.sqrt(disc)
                for _ in range(160):
                    d, mm = sdf.sdf_eval(ox + dx * t, oy + dy * t, oz + dz * t, codes, P, sd, sm)
                    if d < 0.0004 * t:
                        hit = True; m = mm; break
                    t += d * 0.9
                    if t > tend:
                        break
            if hit:
                x, y, z = ox + dx * t, oy + dy * t, oz + dz * t
                nx, ny, nz = _normal(x, y, z, codes, P, sd, sm)
                ndl = nx * L[0] + ny * L[1] + nz * L[2]
                sh = 1.0
                if ndl > 0:
                    sh = _softshadow(x + nx * 0.01, y + ny * 0.01, z + nz * 0.01, L[0], L[1], L[2], codes, P, sd, sm, 10.0, 3.0)
                hx, hy, hz = L[0] - dx, L[1] - dy, L[2] - dz
                hl = math.sqrt(hx * hx + hy * hy + hz * hz)
                out[0, j, i] = 1.0
                out[1, j, i] = t
                out[2, j, i] = x; out[3, j, i] = y; out[4, j, i] = z
                out[5, j, i] = nx; out[6, j, i] = ny; out[7, j, i] = nz
                out[8, j, i] = m
                out[9, j, i] = ndl
                out[10, j, i] = sh
                out[11, j, i] = nx * Lf[0] + ny * Lf[1] + nz * Lf[2]
                out[12, j, i] = (nx * hx + ny * hy + nz * hz) / hl
                out[13, j, i] = -(nx * dx + ny * dy + nz * dz)
                out[14, j, i] = _ao(x, y, z, nx, ny, nz, codes, P, sd, sm)
                out[15, j, i] = 1.0; out[16, j, i] = 1.0
                out[17, j, i] = x; out[18, j, i] = z
            else:
                out[0, j, i] = 0.0
                out[8, j, i] = -1
                out[15, j, i] = 1.0; out[16, j, i] = 1.0
                if dy < -1e-6 and not ground:              # 바닥 그림자를 버리는 층(shadow: false) — 바닥 패스를 건너뛴다(층 광선 추적의 약 45%)
                    out[1, j, i] = -oy / dy
                elif dy < -1e-6:
                    tg = -oy / dy
                    gx, gz = ox + dx * tg, oz + dz * tg
                    out[1, j, i] = tg
                    out[17, j, i] = gx; out[18, j, i] = gz
                    dd = sdf.sdf_eval(gx, 0.0, gz, codes, P, sd, sm)[0]
                    if dd < 1.5:
                        out[15, j, i] = _softshadow(gx, 0.001, gz, L[0], L[1], L[2], codes, P, sd, sm, 8.0, 3.0)
                        # contact AO: sample the field a bit above the ground
                        occ = 0.0
                        for s in range(5):
                            h = 0.03 + 0.07 * s
                            dd2 = sdf.sdf_eval(gx, h, gz, codes, P, sd, sm)[0]
                            occ += max(h - dd2, 0.0) / h * (0.75 ** s)
                        out[16, j, i] = max(1.0 - 0.45 * occ, 0.0)
                else:
                    out[1, j, i] = 1e3


NAMES = ["hit", "depth", "px", "py", "pz", "nx", "ny", "nz", "mat", "ndl", "shadow", "fill",
         "ndh", "ndv", "ao", "gshadow", "gao", "gx", "gz"]


def render(scene, res=1080, ss=2, cam=None):
    """cam: 앞서 맞춘 카메라(eye, f, r, u, th, (lo, hi)) — 움직임 프레임마다 자세가 바뀌어도 화면이 흔들리지 않게 같은 카메라로"""
    t0 = time.time()
    codes, P, mats = sdf.compile_scene(scene)
    t_compile = time.time() - t0
    eye, f, r, u, th, (lo, hi) = cam if cam is not None else auto_camera(scene, codes, P, res)
    # lights in camera-relative terms: key from top-left-front, fill from right
    L = _norm(-0.55 * r + 0.95 * np.array([0, 1, 0]) - 0.45 * f)
    Lf = _norm(0.8 * r + 0.2 * np.array([0, 1, 0]) - 0.6 * f)
    bc = (lo + hi) / 2; br = float(np.linalg.norm(hi - lo) / 2 + 0.05)
    N = res * ss
    asp = float(scene.get("camera", {}).get("aspect", 1.0))
    NH = int(round(N * asp))
    out = np.zeros((len(NAMES), NH, N), np.float32)
    t1 = time.time()
    if (scene.get("camera", {}).get("aspect") or scene.get("backdrop")) and not scene.get("layer"):
        br = 1e3                                           # 장면 전체(바닥 · 배경까지) — 형태 둘레 구 밖의 광선도 바닥까지 따라간다
    ground = not (scene.get("layer") and scene.get("shadow") is False) and scene.get("ground") is not False
    import numba
    try:                                                   # 형태가 몇 줄에 몰려도 스레드가 고르게 나눠 갖게(정적 분할은 8스레드에서 1.6배뿐)
        with numba.parallel_chunksize(4):
            march(codes, P, N, NH, eye, f, r, u, th, L, Lf, bc, br, out, asp, ground)
    except AttributeError:
        march(codes, P, N, NH, eye, f, r, u, th, L, Lf, bc, br, out, asp, ground)
    t_march = time.time() - t1
    buf = {k: out[i] for i, k in enumerate(NAMES)}
    meta = dict(mats=mats, mat_table=sdf.material_table(scene), L=L, Lf=Lf, eye=eye, f=f, r=r, u=u, th=th,
                res=res, ss=ss, lo=lo, hi=hi, aspect=asp,
                foot_center=np.array([(lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2]),
                foot_size=np.array([(hi[0] - lo[0]) / 2, (hi[2] - lo[2]) / 2]),
                scene=scene, strokes=sdf.collect_strokes(scene))
    return buf, meta, dict(compile=t_compile, camera=time.time() - t1 - t_march + 0, march=t_march, total=time.time() - t0)


KEEP32 = {"depth", "px", "py", "pz", "gx", "gz"}      # 위치 · 깊이는 무늬 · 초점 흐림에 정밀도가 필요 — 나머지(면 방향 · 빛 · 그늘 0~1)는 반 정밀도로


def save(buf, meta, path):
    """2026-11-24: 무압축 float32 로 장당 630MB, 캐시 폴더가 95GB 까지 커졌다 → 빛 · 면 칸은 float16, 압축, 폴더 상한(가장 오래 안 쓴 것부터 지움)"""
    np.savez_compressed(path, **{k: (v if k in KEEP32 or v.dtype != np.float32 else v.astype(np.float16)) for k, v in buf.items()},
                        **{"meta_" + k: (json.dumps(v) if k in ("scene", "strokes") else v) for k, v in meta.items()})
    trim_cache(os.path.dirname(str(path)))


def trim_cache(folder, cap_gb=None):
    cap = float(cap_gb if cap_gb is not None else os.environ.get("FLUMA_FORM_CACHE_GB", "12")) * (1 << 30)
    try:
        fs = [(e.stat().st_atime, e.stat().st_size, e.path) for e in os.scandir(folder) if e.name.endswith(".npz")]
    except OSError:
        return
    total = sum(x[1] for x in fs)
    for _, size, pth in sorted(fs):
        if total <= cap:
            break
        try:
            os.remove(pth); total -= size
        except OSError:
            pass


def load(path):
    z = np.load(path, allow_pickle=True)
    buf = {k: (z[k].astype(np.float32) if z[k].dtype == np.float16 else z[k]) for k in z.files if not k.startswith("meta_")}
    meta = {k[5:]: z[k] for k in z.files if k.startswith("meta_")}
    meta["mats"] = list(meta["mats"]); meta["scene"] = json.loads(str(meta["scene"]))
    meta["strokes"] = json.loads(str(meta["strokes"])) if "strokes" in meta else []
    return buf, meta


def project(scene, pts, res=1080):
    """3D 점 → 화면 px(같은 카메라로 그린 판 위에 글자 · 2D 층을 맞춰 놓을 때). camera.focus 가 있어야 형태를 재지 않는다"""
    codes, P, _ = sdf.compile_scene(scene)
    eye, f, r, u, th, _ = auto_camera(scene, codes, P, res)
    asp = float(scene.get("camera", {}).get("aspect", 1.0))
    W, H = res, int(round(res * asp))
    out = []
    for p in pts:
        rel = np.asarray(p, float) - eye
        z = rel @ f
        sx, sy = (rel @ r) / z / th, (rel @ u) / z / th / asp
        out.append([float((sx + 1) / 2 * W), float((1 - sy) / 2 * H), float(z)])
    return out
