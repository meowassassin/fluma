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
        sh[:, 9:12] -= np.where((np.asarray(codes)[:, None] < 100) | (np.asarray(codes)[:, None] == 106), ctr[None, :], 0.0)   # 도형 위치를 가운데로 옮겨 같은 정육면체 격자로 잰다
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
        sx = (rel @ r) / z / th; sy = (rel @ u) / z / th
        # recenter target on screen bbox center, then fit largest extent to `fill`
        cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
        target = target + (r * cx + u * cy) * (float((target - eye) @ f) * th)
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
    res = 1.0; t = 0.02
    for _ in range(64):
        h = sdf.sdf_eval(x + lx * t, y + ly * t, z + lz * t, codes, P, sd, sm)[0]
        res = min(res, k * h / t)
        if res < 0.002 or t > tmax:
            break
        t += min(max(h, 0.012), 0.25)
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
def march(codes, P, W, H, eye, f, r, u, th, L, Lf, bc, br, out):
    for j in prange(H):
        sd = np.empty(32); sm = np.empty(32)
        for i in range(W):
            px = ((i + 0.5) / W * 2 - 1) * th
            py = (1 - (j + 0.5) / H * 2) * th
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
                    sh = _softshadow(x + nx * 0.004, y + ny * 0.004, z + nz * 0.004, L[0], L[1], L[2], codes, P, sd, sm, 10.0, 3.0)
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
                if dy < -1e-6:
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
    out = np.zeros((len(NAMES), N, N), np.float32)
    t1 = time.time()
    march(codes, P, N, N, eye, f, r, u, th, L, Lf, bc, br, out)
    t_march = time.time() - t1
    buf = {k: out[i] for i, k in enumerate(NAMES)}
    hitm = buf["hit"] > 0
    foot = hitm & (buf["py"] < 0.05)
    meta = dict(mats=mats, mat_table=sdf.material_table(scene), L=L, Lf=Lf, eye=eye, f=f, r=r, u=u, th=th,
                res=res, ss=ss, lo=lo, hi=hi,
                foot_center=np.array([(lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2]),
                foot_size=np.array([(hi[0] - lo[0]) / 2, (hi[2] - lo[2]) / 2]),
                scene=scene)
    return buf, meta, dict(compile=t_compile, camera=time.time() - t1 - t_march + 0, march=t_march, total=time.time() - t0)


def save(buf, meta, path):
    np.savez(path, **buf, **{"meta_" + k: (json.dumps(v) if k == "scene" else v) for k, v in meta.items()})


def load(path):
    z = np.load(path, allow_pickle=True)
    buf = {k: z[k] for k in z.files if not k.startswith("meta_")}
    meta = {k[5:]: z[k] for k in z.files if k.startswith("meta_")}
    meta["mats"] = list(meta["mats"]); meta["scene"] = json.loads(str(meta["scene"]))
    return buf, meta
