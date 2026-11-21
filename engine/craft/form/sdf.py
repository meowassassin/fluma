"""Tiny general SDF modeler.

A scene is data (JSON):
{
  "materials": {"body": {"color": "#ffd23a", "gloss": 0.3, ...}, ...},
  "root": <node>
}
node = primitive | operation
primitive = {"prim": "sphere|ellipsoid|capsule|roundbox|roundcone|torus|cylinder|halfspace",
             <shape params>, "mat": "body",
             "pos": [x,y,z], "rot": [rx,ry,rz] (deg, XYZ), "scale": s,
             "round": r (optional inflate), "shell": t (optional hollow/onion),
             "mirror_x": true (optional: also adds the mirrored copy)}
operation = {"op": "union|smooth_union|subtract|smooth_subtract|intersect|smooth_intersect",
             "k": radius, "children": [node, node, ...], "cut_mat": bool (subtract: cut faces use cutter material)}
   (n-ary: folded left, e.g. subtract = first minus all the rest)
   operations may also carry pos/rot/scale applied to the whole group.

compile_scene() turns the tree into a flat postfix program (numba friendly).
evaluate with sdf_eval(x,y,z, codes, P, stack_d, stack_m) -> (distance, material id).
"""
import json, math
import numpy as np
from numba import njit

PRIM = {"sphere": 0, "ellipsoid": 1, "capsule": 2, "roundbox": 3, "roundcone": 4,
        "torus": 5, "cylinder": 6, "halfspace": 7}
OPS = {"union": 100, "smooth_union": 101, "subtract": 102, "smooth_subtract": 103, "joint_union": 106,
       "intersect": 104, "smooth_intersect": 105}
NP = 24  # floats per instruction
# layout: 0-8 inverse rotation (row major), 9-11 translation, 12 scale,
#         13-18 shape params, 19 mat id, 20 round, 21 shell, 22 k


def _rot(rx, ry, rz):
    rx, ry, rz = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    X = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Y = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Z = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Z @ Y @ X


def _xf(node):
    R = np.array(node["rotm"], float) if "rotm" in node else _rot(*node.get("rot", [0, 0, 0]))   # rotm: 회전 행렬(뼈대가 계산해 넣는다)
    return np.eye(4) if False else (R, np.array(node.get("pos", [0, 0, 0]), float), float(node.get("scale", 1.0)))


def _compose(parent, child):
    # world = Rp*(s_p*(Rc*(s_c*x)+tc))+tp
    Rp, tp, sp = parent
    Rc, tc, sc = child
    return Rp @ Rc, Rp @ (sp * tc) + tp, sp * sc


def _shape_params(n):
    p = n["prim"]
    if p == "sphere": return [n["r"]]
    if p == "ellipsoid": return list(n["radii"])
    if p == "capsule": return [n["h"], n["r"]]            # vertical, half height h
    if p == "roundbox": return list(n["size"]) + [n.get("r", 0.0)]  # half extents
    if p == "roundcone": return [n["r1"], n["r2"], n["h"]]  # base r1 at y=0, top r2 at y=h
    if p == "torus": return [n["R"], n["r"]]              # in xz plane
    if p == "cylinder": return [n["h"], n["r"], n.get("r_edge", 0.0)]  # vertical, half height
    if p == "halfspace": return []                        # solid where local y < 0
    raise ValueError(p)


def compile_scene(scene):
    mats = list(scene["materials"].keys())
    mid = {m: i for i, m in enumerate(mats)}
    rows, codes = [], []

    def emit(code, xf=None, params=(), mat=0, rnd=0.0, shell=0.0, k=0.0):
        row = np.zeros(NP)
        if xf is not None:
            R, t, s = xf
            row[0:9] = R.T.reshape(-1)  # inverse rotation
            row[9:12] = t
            row[12] = s
        row[13:13 + len(params)] = params
        row[19], row[20], row[21], row[22] = mat, rnd, shell, k
        rows.append(row); codes.append(code)

    def visit(n, parent):
        if "rig" in n:                                  # 뼈대 캐릭터(engine/craft/form/skeleton.py) → 도형 트리로 펼친다
            from .skeleton import expand
            n = expand(n)
        xf = _compose(parent, _xf(n))
        if "prim" in n:
            emit(PRIM[n["prim"]], xf, _shape_params(n), mid[n["mat"]], n.get("round", 0.0), n.get("shell", 0.0))
            if n.get("mirror_x"):
                m = dict(n); m.pop("mirror_x")
                pos = list(m.get("pos", [0, 0, 0])); pos[0] = -pos[0]; m["pos"] = pos
                rot = list(m.get("rot", [0, 0, 0])); m["rot"] = [rot[0], -rot[1], -rot[2]]
                if "rotm" in m:
                    M = np.diag([-1.0, 1.0, 1.0]); m["rotm"] = (M @ np.array(m["rotm"]) @ M).tolist()
                emit(PRIM[m["prim"]], _compose(parent, _xf(m)), _shape_params(m), mid[m["mat"]], m.get("round", 0.0), m.get("shell", 0.0))
                emit(OPS["union"])
        else:
            kids = n["children"]
            visit(kids[0], xf)
            for c in kids[1:]:
                visit(c, xf)
                if n["op"] == "joint_union":              # 관절 이음: 관절(at) 둘레 reach 안에서만 k 만큼 녹아 붙는다 — 멀리 있는 부위(두 허벅지 · 팔과 옆구리)는 그대로
                    _, cw, scw = _compose(xf, (np.eye(3), np.array(n["at"], float), 1.0))
                    emit(OPS["joint_union"], (np.eye(3), cw, 1.0), params=[float(n["reach"]) * scw], k=float(n.get("k", 0.0)) * scw)
                else:
                    emit(OPS[n["op"]], k=n.get("k", 0.0), mat=1 if n.get("cut_mat") else 0)

    visit(scene["root"], (np.eye(3), np.zeros(3), 1.0))
    return np.array(codes, np.int32), np.array(rows, np.float64), mats


def material_table(scene):
    """Per-material float table: rgb(0-1) + gloss, spec_power, plus style hints."""
    out = []
    for name, m in scene["materials"].items():
        c = m["color"].lstrip("#")
        rgb = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        out.append(rgb + [m.get("gloss", 0.2), m.get("spec_power", 30.0)])
    return np.array(out, np.float64)


def load(path):
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------- numba kernels
@njit(cache=True, fastmath=True, inline="always")
def _len3(x, y, z):
    return math.sqrt(x * x + y * y + z * z)


@njit(cache=True, fastmath=True)
def _prim(code, x, y, z, P, i):
    a, b, c, d = P[i, 13], P[i, 14], P[i, 15], P[i, 16]
    if code == 0:
        return _len3(x, y, z) - a
    if code == 1:  # ellipsoid (iq bound)
        k0 = _len3(x / a, y / b, z / c)
        k1 = _len3(x / (a * a), y / (b * b), z / (c * c))
        if k1 < 1e-9:
            return -min(a, min(b, c))
        return k0 * (k0 - 1.0) / k1
    if code == 2:  # capsule vertical
        yy = min(max(y, -a), a)
        return _len3(x, y - yy, z) - b
    if code == 3:  # rounded box
        qx = abs(x) - a + d; qy = abs(y) - b + d; qz = abs(z) - c + d
        o = _len3(max(qx, 0.0), max(qy, 0.0), max(qz, 0.0))
        return o + min(max(qx, max(qy, qz)), 0.0) - d
    if code == 4:  # round cone r1 at y=0, r2 at y=h
        r1, r2, h = a, b, c
        qx = math.sqrt(x * x + z * z); qy = y
        bb = (r1 - r2) / h
        aa = math.sqrt(max(1.0 - bb * bb, 0.0))
        kk = -qx * bb + qy * aa  # dot(q, (-b, a))
        if kk < 0.0:
            return math.sqrt(qx * qx + qy * qy) - r1
        if kk > aa * h:
            return math.sqrt(qx * qx + (qy - h) ** 2) - r2
        return qx * aa + qy * bb - r1
    if code == 5:  # torus
        qx = math.sqrt(x * x + z * z) - a
        return math.sqrt(qx * qx + y * y) - b
    if code == 6:  # capped cylinder, rounded edge c
        dx = math.sqrt(x * x + z * z) - b + c
        dy = abs(y) - a + c
        return min(max(dx, dy), 0.0) + math.sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) - c
    if code == 7:
        return y
    return 1e9


@njit(cache=True, fastmath=True)
def sdf_eval(px, py, pz, codes, P, sd, sm):
    sp = 0
    for i in range(codes.shape[0]):
        c = codes[i]
        if c < 100:
            dx = px - P[i, 9]; dy = py - P[i, 10]; dz = pz - P[i, 11]
            s = P[i, 12]
            lx = (P[i, 0] * dx + P[i, 1] * dy + P[i, 2] * dz) / s
            ly = (P[i, 3] * dx + P[i, 4] * dy + P[i, 5] * dz) / s
            lz = (P[i, 6] * dx + P[i, 7] * dy + P[i, 8] * dz) / s
            d = _prim(c, lx, ly, lz, P, i) * s - P[i, 20]
            if P[i, 21] > 0.0:
                d = abs(d) - P[i, 21]
            sd[sp] = d; sm[sp] = P[i, 19]; sp += 1
        else:
            sp -= 1
            d2 = sd[sp]; m2 = sm[sp]
            d1 = sd[sp - 1]; m1 = sm[sp - 1]
            k = P[i, 22]
            if c == 100:
                if d2 < d1:
                    d1 = d2; m1 = m2
            elif c == 101:
                h = min(max(0.5 + 0.5 * (d2 - d1) / k, 0.0), 1.0)
                nd = d2 * (1.0 - h) + d1 * h - k * h * (1.0 - h)
                if d2 < d1:
                    m1 = m2
                d1 = nd
            elif c == 102:
                if -d2 > d1:
                    d1 = -d2
                    if P[i, 19] > 0.0:
                        m1 = m2  # "cut_mat": cut surface takes the cutter's material
            elif c == 103:
                if P[i, 19] > 0.0 and -d2 > d1:
                    m1 = m2
                a = -d1; b = d2  # smooth max(d1, -d2) = -smin(-d1, d2)
                h = min(max(0.5 + 0.5 * (b - a) / k, 0.0), 1.0)
                d1 = -(b * (1.0 - h) + a * h - k * h * (1.0 - h))
            elif c == 106:
                ddx = px - P[i, 9]; ddy = py - P[i, 10]; ddz = pz - P[i, 11]
                w = 1.0 - math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz) / P[i, 13]
                if w > 0.0:
                    w = w * w * (3.0 - 2.0 * w)
                    kk = k * w
                    h = min(max(0.5 + 0.5 * (d2 - d1) / kk, 0.0), 1.0)
                    nd = d2 * (1.0 - h) + d1 * h - kk * h * (1.0 - h)
                    if d2 < d1:
                        m1 = m2
                    d1 = nd
                elif d2 < d1:
                    d1 = d2; m1 = m2
            elif c == 104:
                if d2 > d1:
                    d1 = d2; m1 = m2
            elif c == 105:
                a = -d1; b = -d2
                h = min(max(0.5 + 0.5 * (b - a) / k, 0.0), 1.0)
                nd = -(b * (1.0 - h) + a * h - k * h * (1.0 - h))
                if d2 > d1:
                    m1 = m2
                d1 = nd
            sd[sp - 1] = d1; sm[sp - 1] = m1
    return sd[0], int(sm[0])


def export_obj(scene, path, res=160, bounds=(-1.2, 1.2)):
    """Marching cubes mesh export (for path tracers)."""
    from skimage import measure
    codes, P, _ = compile_scene(scene)
    g = np.linspace(bounds[0], bounds[1], res)
    vol = _grid(codes, P, g)
    v, f, n, _ = measure.marching_cubes(vol, 0.0, spacing=(g[1] - g[0],) * 3)
    v += bounds[0]
    with open(path, "w") as fh:
        for a in v: fh.write(f"v {a[0]:.5f} {a[1]:.5f} {a[2]:.5f}\n")
        for a in f + 1: fh.write(f"f {a[0]} {a[1]} {a[2]}\n")
    return len(v), len(f)


@njit(cache=True)
def _grid(codes, P, g):
    n = g.shape[0]
    out = np.empty((n, n, n), np.float32)
    sd = np.empty(32); sm = np.empty(32)
    for i in range(n):
        for j in range(n):
            for k in range(n):
                out[i, j, k] = sdf_eval(g[i], g[j], g[k], codes, P, sd, sm)[0]
    return out
