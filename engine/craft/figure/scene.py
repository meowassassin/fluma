"""Blender 쪽 — 사양(JSON)대로 인체에 뼈대 · 자세 · 복장을 입혀 빛(shade)과 면 방향(normal) 패스를 렌더한다. fluma 모듈을 쓰지 않는다.
blender -b --python scene.py -- spec.json"""
import json
import math
import random
import sys

import bmesh  # noqa: F401
import bpy
import numpy as np
from mathutils import Matrix, Vector

SP = json.loads(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8").read())
sc = None
rr = random.Random(SP.get("seed", 3))
TEMP = []


def mat(n, v=.75):
    m = bpy.data.materials.get(n)
    if m:
        return m
    m = bpy.data.materials.new(n); m.use_nodes = True; t = m.node_tree; t.nodes.clear()
    o = t.nodes.new("ShaderNodeOutputMaterial"); s = t.nodes.new("ShaderNodeBsdfDiffuse"); s.inputs[0].default_value = (v, v, v, 1); t.links.new(s.outputs[0], o.inputs[0])
    return m


def temp(o):
    TEMP.append(o)
    return o


def meshobj(n, vs, fs, m):
    me = bpy.data.meshes.new(n); me.from_pydata(vs, [], fs); me.polygons.foreach_set("use_smooth", [True] * len(fs)); me.update()
    o = bpy.data.objects.new(n, me); sc.collection.objects.link(o); me.materials.append(m)
    return temp(o)


def segment_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1), t


J = {"pelvis": ((0, 0, .92), (0, -.01, 1.10)), "spine": ((0, -.01, 1.10), (0, -.01, 1.30)), "chest": ((0, -.01, 1.30), (0, -.015, 1.45)), "neck": ((0, -.015, 1.45), (0, -.03, 1.53)), "head": ((0, -.03, 1.53), (0, -.03, 1.68)),
     "uaL": ((.165, -.02, 1.385), (.285, -.02, 1.13)), "faL": ((.285, -.02, 1.13), (.385, -.03, .91)), "hdL": ((.385, -.03, .91), (.435, -.05, .78)),
     "uaR": ((-.165, -.02, 1.385), (-.285, -.02, 1.13)), "faR": ((-.285, -.02, 1.13), (-.385, -.03, .91)), "hdR": ((-.385, -.03, .91), (-.435, -.05, .78)),
     "thL": ((.09, 0, .92), (.125, -.015, .50)), "shL": ((.125, -.015, .50), (.16, .03, .09)), "ftL": ((.16, .03, .09), (.175, -.12, .02)),
     "thR": ((-.09, 0, .92), (-.125, -.015, .50)), "shR": ((-.125, -.015, .50), (-.16, .03, .09)), "ftR": ((-.16, .03, .09), (-.175, -.12, .02))}
PAR = {"spine": "pelvis", "chest": "spine", "neck": "chest", "head": "neck", "uaL": "chest", "faL": "uaL", "hdL": "faL", "uaR": "chest", "faR": "uaR", "hdR": "faR", "thL": "pelvis", "shL": "thL", "ftL": "shL", "thR": "pelvis", "shR": "thR", "ftR": "shR"}


def pick_engine():
    """GPU 가 있으면 EEVEE(수 초), 소프트웨어 GL(도커 등)뿐이면 Cycles CPU"""
    want = SP.get("engine", "auto")
    if want != "auto":
        return want
    try:
        import gpu                          # GL 은 첫 렌더 때 켜진다 — 작은 그림 하나로 깨워서 묻는다
        s0 = bpy.context.scene; s0.render.engine = "BLENDER_EEVEE"; s0.render.resolution_x = s0.render.resolution_y = 8
        if not s0.camera:
            c0 = bpy.data.objects.new("c0", bpy.data.cameras.new("c0")); s0.collection.objects.link(c0); s0.camera = c0
        bpy.ops.render.render()
        r = (gpu.platform.renderer_get() or "").lower()
        if s0.camera.name == "c0":
            bpy.data.objects.remove(s0.camera)
        return "CYCLES" if any(k in r for k in ("llvmpipe", "softpipe", "swrast")) or not r else "BLENDER_EEVEE"
    except Exception:
        return "CYCLES"


ENGINE = "CYCLES"


def setup():
    global sc, ENGINE, body, ar, Rinv
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    ENGINE = pick_engine()
    fem = SP.get("body") == "female"
    with bpy.data.libraries.load(SP["lib"]) as (a, b):
        b.objects = ["GEO-body_female_realistic", "GEO-body_male_realistic"] if fem else ["GEO-body_male_realistic"]
    body = b.objects[0]; sc.collection.objects.link(body); body.location = (0, 0, 0); body.parent = None
    if fem:                                                         # 여성: 남성과 정점 순서가 같다 → 관절을 정점 대응으로 옮긴다
        k = 1.684 / 1.641; body.scale = (k, k, k)                   # 키만 맞춘다(옷 · 머리 높이 칸을 같이 쓴다) — 체형 비율은 그대로
        Mv = np.array([v.co for v in b.objects[1].data.vertices]); Fv = np.array([v.co for v in body.data.vertices]) * k
        for n_, (h_, t_) in list(J.items()):
            def mv(p):
                p = np.array(p); i = np.argsort(np.linalg.norm(Mv - p, axis=1))[:12]
                return tuple(Fv[i].mean(0) + (p - Mv[i].mean(0)))
            J[n_] = (mv(h_), mv(t_))
        bpy.data.objects.remove(b.objects[1])
    body.data.materials.clear(); body.data.materials.append(mat("skin", .78))
    lv = SP.get("subdiv", 3)
    for m in body.modifiers:
        if m.type == "MULTIRES":
            m.levels = m.render_levels = min(lv, m.total_levels)
    ad = bpy.data.armatures.new("rig"); ar = bpy.data.objects.new("rig", ad); sc.collection.objects.link(ar)
    bpy.context.view_layer.objects.active = ar; ar.select_set(True); bpy.ops.object.mode_set(mode="EDIT")
    for n, (h, t) in J.items():
        e = ad.edit_bones.new(n); e.head = h; e.tail = t
    for n, p in PAR.items():
        ad.edit_bones[n].parent = ad.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    body.select_set(True); ar.select_set(True); bpy.context.view_layer.objects.active = ar
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    ar.rotation_euler = (0, 0, math.radians(90)); bpy.context.view_layer.update()
    Rinv = ar.matrix_world.inverted()
    body.hide_render = True
    ar.hide_render = True
    # 카메라 · 빛
    c = SP.get("camera") or {}
    cam = bpy.data.cameras.new("c"); cam.lens = c.get("lens", 62); co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
    co.location = c.get("loc", (4.5, -2.5, 1.28))
    co.rotation_euler = (Vector(c.get("look", (.2, 0, 1.08))) - co.location).to_track_quat("-Z", "Y").to_euler()
    sun = bpy.data.lights.new("s", "SUN"); sun.energy = 2.9; sun.angle = math.radians(3); so = bpy.data.objects.new("s", sun); sc.collection.objects.link(so)
    so.rotation_euler = [math.radians(v) for v in SP.get("sun", (52, -8, 30))]
    w = bpy.data.worlds.new("w"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (.035, .035, .035, 1); sc.world = w
    sc.render.engine = ENGINE; sc.render.film_transparent = True
    if ENGINE == "CYCLES":
        sc.cycles.device = "CPU"
    else:
        sc.eevee.use_shadows = True; sc.eevee.shadow_ray_count = 2; sc.eevee.shadow_step_count = 8
    sc.render.resolution_x, sc.render.resolution_y = SP.get("size", (1800, 2200))
    sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"; sc.render.image_settings.color_depth = "16"


def aim(bn, target, up=None):
    """뼈를 target 쪽으로. up: 그 뼈의 '앞(쉴 때 몸 앞쪽, 엄지 쪽)'이 향할 방향 — 팔을 축으로 돌려 손이 뒤집히지 않게"""
    pb = ar.pose.bones[bn]; bpy.context.view_layer.update()
    h = pb.head.copy(); d0 = (pb.tail - h).normalized(); d1 = ((Rinv @ Vector(target)) - h).normalized()
    q = d0.rotation_difference(d1); pb.rotation_mode = "QUATERNION"
    pb.matrix = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()
    if up is not None:
        R = pb.matrix.to_3x3() @ pb.bone.matrix_local.to_3x3().inverted()
        ax = (pb.tail - pb.head).normalized()
        f = R @ (Rinv.to_3x3() @ Vector((1, 0, 0))); u = Rinv.to_3x3() @ Vector(up)
        f = (f - ax * f.dot(ax)).normalized(); u = (u - ax * u.dot(ax)).normalized()
        ang = math.atan2(ax.dot(f.cross(u)), f.dot(u))
        rq = Matrix.Rotation(ang, 4, ax)
        pb.matrix = Matrix.Translation(pb.head) @ rq @ Matrix.Translation(-pb.head) @ pb.matrix
        bpy.context.view_layer.update()


def ik(hip, ankle, l1=.42, l2=.415):
    h, a = np.array(hip), np.array(ankle); d = a - h; L = min(np.linalg.norm(d), l1 + l2 - .004); u = d / np.linalg.norm(d)
    x = (l1 * l1 - l2 * l2 + L * L) / (2 * L); y = math.sqrt(max(0, l1 * l1 - x * x))
    fw = np.array((1, 0, 0)) - u * u[0]; fw = fw / (np.linalg.norm(fw) or 1)
    return tuple(h + u * x + fw * y)


def run_pose(t, stride=.34):
    a = 2 * math.pi * t
    up = .025 * math.cos(2 * a)
    def leg(ph, y):
        p = 2 * math.pi * ph
        x = stride * math.cos(p); sw = math.sin(p)
        z = .085 + (.30 * sw + .10 * sw * sw if sw > 0 else .0)    # 앞으로 넘어올 때 든다 · 디딤발 발목은 땅 높이
        hip = (0, y, .92 - .04 + up); ank = (x + .02, y * 1.15, z)          # 골반이 살짝 내려앉아 디딤발 무릎이 굽는다
        k = ik(hip, ank)
        toe = (ank[0] + (.15 if sw <= 0 else .06), ank[1], ank[2] - (.075 if sw <= 0 else .13))
        return k, ank, toe
    kL, aL, tL = leg(t, .09); kR, aR, tR = leg(t + .5, -.09)
    sL, sR = math.cos(a + math.pi), math.cos(a)                  # 팔은 반대로
    def arm(y, s_):                                              # 팔꿈치 90도로 접고 어깨에서 앞뒤로 흔든다(손은 허리~가슴 높이)
        el = (.0 + .20 * s_ - .06, y * 1.12, 1.15 + up + .03 * max(0, s_))
        wr = (el[0] + .16 + .08 * s_, y * .95, el[2] - .02 + .09 * max(0, s_))
        return el, wr, (wr[0] + .07, wr[1] * .97, wr[2] + .01)
    eL, wL, hL = arm(.2, sL); eR, wR, hR = arm(-.2, sR)
    return {"lift": -.04 + up, "aims": [("spine", (.05, 0, 1.28)), ("chest", (.11, 0, 1.44)), ("neck", (.15, 0, 1.53)), ("head", (.19, 0, 1.70)),
                                       ("thL", kL), ("shL", aL), ("ftL", tL), ("thR", kR), ("shR", aR), ("ftR", tR),
                                       ("uaL", eL), ("faL", wL), ("hdL", hL), ("uaR", eR), ("faR", wR), ("hdR", hR)]}


POSES = {
    "thrust": {"lift": -.02, "aims": [("spine", (.05, 0, 1.28)), ("chest", (.09, 0, 1.44)), ("neck", (.12, -.01, 1.53)), ("head", (.13, -.02, 1.70)),
                                      ("thL", (.30, .13, .56)), ("shL", (.30, .15, .10)), ("ftL", (.47, .16, .02)), ("thR", (-.17, -.12, .50)), ("shR", (-.40, -.14, .12)), ("ftR", (-.34, -.14, 0)),
                                      ("uaL", (.20, .30, 1.24)), ("faL", (.42, .30, 1.30)), ("hdL", (.52, .30, 1.32)), ("uaR", (-.13, -.33, 1.20)), ("faR", (.10, -.38, 1.05)), ("hdR", (.20, -.39, 1.02))]},
    "stand": {"lift": 0, "aims": [("uaL", (.02, .26, 1.14)), ("faL", (.08, .29, .92)), ("hdL", (.10, .30, .80)), ("uaR", (.02, -.26, 1.14)), ("faR", (.08, -.29, .92)), ("hdR", (.10, -.30, .80))]},
    "point": {"lift": 0, "aims": [("chest", (.03, 0, 1.45)), ("uaR", (.26, -.26, 1.34), (0, -.3, 1)), ("faR", (.50, -.28, 1.42)), ("hdR", (.62, -.29, 1.46)), ("uaL", (-.02, .26, 1.14)), ("faL", (.05, .29, .92)), ("hdL", (.07, .30, .80))]},
    "collapse": {"lift": -.42, "aims": [("spine", (.15, 0, .57)), ("chest", (.33, 0, .61)), ("neck", (.41, 0, .61)), ("head", (.54, 0, .56)),     # 탈진: 무릎을 꿇고 두 손바닥으로 땅을 짚는다
                                        ("thL", (.08, .12, .07)), ("shL", (-.32, .13, .07)), ("ftL", (-.45, .13, .02)), ("thR", (.06, -.12, .07)), ("shR", (-.34, -.13, .07)), ("ftR", (-.47, -.13, .02)),
                                        ("uaL", (.36, .21, .34), (0, -1, 0)), ("faL", (.41, .21, .08)), ("hdL", (.56, .21, .05)), ("uaR", (.38, -.21, .34), (0, 1, 0)), ("faR", (.43, -.21, .08)), ("hdR", (.58, -.21, .05))]},
}


def eval_body(pose):
    for pb in ar.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    ar.pose.bones["pelvis"].location = (0, pose.get("lift", 0), 0)       # 뼈 자기 좌표: Y 가 뼈 방향(위) — 골반을 위아래로
    for bn, tg, *up in pose["aims"]:
        aim(bn, tg, up[0] if up else None)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); eb = body.evaluated_get(dg); me = bpy.data.meshes.new_from_object(eb)
    W = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", W); W = W.reshape(-1, 3)
    W = (np.array(eb.matrix_world.to_3x3()) @ W.T).T + np.array(eb.matrix_world.translation)
    segs = {n: (np.array(ar.matrix_world @ ar.pose.bones[n].head), np.array(ar.matrix_world @ ar.pose.bones[n].tail)) for n in J}
    names = list(segs)
    lab = np.argmin(np.array([segment_dist(W, *segs[n])[0] for n in names]), axis=0)
    return me, W, segs, names, lab


# 손 — 휴식 자세에서 잰 손바닥 방향 · 손가락 구역(이 인체 모델 기준). 손가락마다 세 마디(MCP · PIP · DIP)를 손바닥 쪽으로 굽힌다.
#   X: 손 너비(엄지 쪽이 -), H: 손바닥 쪽이 +, S: 손목에서 손끝
FINGERS = {"index": ((-1, -.094), (.117, .155, .178)), "middle": ((-.094, -.061), (.118, .160, .186)), "ring": ((-.061, -.031), (.118, .157, .182)), "little": ((-.031, 1), (.122, .151, .172))}
GRIPS = {   # 손가락별 (MCP, PIP, DIP) 각도(도) · 엄지 각도
    "open": ({}, (5, 5, 0), 0), "relax": ({"index": (8, 14, 8), "middle": (12, 20, 10), "ring": (16, 26, 12), "little": (22, 30, 14)}, None, 12),
    "loose": ({"index": (35, 45, 20), "middle": (42, 52, 24), "ring": (48, 58, 26), "little": (55, 62, 28)}, None, 25),
    "grip": ({}, (78, 96, 52), 48), "point": ({"index": (0, 4, 2), "middle": (82, 98, 55), "ring": (86, 100, 55), "little": (88, 100, 55)}, None, 38)}
POSE_HANDS = {"thrust": ("grip", "grip"), "stand": ("relax", "relax"), "point": ("relax", "point"), "collapse": ("open", "open"), "run": ("loose", "loose")}
REST = {}
ZR = [None]          # 정점마다 쉴 때 높이 — 옷 자르기는 자세와 무관하게 이것으로(기울어도 같은 자리)


def rest_hands(W, segs, names, lab):
    """휴식 자세(뼈대 그대로)에서 손 정점의 손 좌표를 한 번 잰다"""
    for bn, side in (("hdL", 1), ("hdR", -1)):
        a, b = segs[bn]; d = (b - a) / np.linalg.norm(b - a)
        n = np.array([0, -side, 0.]); n -= (n @ d) * d; n /= np.linalg.norm(n)       # 손바닥은 몸 쪽
        x = -np.array([1., 0, 0]); x -= (x @ d) * d + (x @ n) * n; x /= np.linalg.norm(x)   # 엄지(앞쪽)가 -
        idx = np.where(lab == names.index(bn))[0]; V = W[idx] - a
        S, H, X = V @ d, V @ n, V @ x
        thumb = np.clip((-.086 - X) / .012, 0, 1) * np.clip((.132 - S) / .014, 0, 1)     # 엄지 무게(경계는 섞는다)
        REST[bn] = (idx, S, H, X, thumb, (d, n, x))


def hand(W, segs, names, bn, shape):
    """손 모양을 입힌다 → 쥔 손 안쪽 점(창 · 방패 손잡이 자리)"""
    idx, S, H, X, thumb, (d0, n0, x0) = REST[bn]
    pb = ar.pose.bones[bn]; Rw = ar.matrix_world.to_3x3()
    M = np.array(Rw @ pb.matrix.to_3x3() @ pb.bone.matrix_local.to_3x3().inverted() @ Rw.inverted())     # 쉼 → 지금 손 회전
    d, n, x = M @ d0, M @ n0, M @ x0
    a = segs[bn][0]
    per, every, th = GRIPS.get(shape, GRIPS["relax"])
    S2, H2, X2 = S.copy(), H.copy(), X.copy()
    fs = list(FINGERS)
    cen = np.array([(max(lo, -.12) + min(hi, 0)) / 2 for (lo, hi), _ in FINGERS.values()])
    wt = np.exp(-((X[:, None] - cen[None]) / .009) ** 2); wt /= wt.sum(1, keepdims=True) + 1e-9      # 손가락 경계(물갈퀴)는 섞는다
    J = np.array([FINGERS[f][1] for f in fs]); A = np.array([per.get(f, every or (0, 0, 0)) for f in fs], float)
    sj_v, ang_v = wt @ J, wt @ A                                          # 정점마다 마디 자리 · 각도
    hp = np.median(H[(thumb < .5) & (S > .12)]) + .009
    for j in (2, 1, 0):                                                   # 끝마디부터 — 앞 마디가 뒤 마디를 함께 돌린다
        sj = sj_v[:, j]
        k = np.clip((S - sj + .007) / .014, 0, 1); k = k * k * (3 - 2 * k)   # 마디 앞뒤 1.4cm 에서 부드럽게 꺾는다
        r = np.radians(ang_v[:, j]) * k * (1 - thumb)
        u, v = S2 - sj, H2 - hp
        S2, H2 = sj + u * np.cos(r) - v * np.sin(r), hp + u * np.sin(r) + v * np.cos(r)
    if th:                                                               # 엄지: 손바닥 쪽으로 감싼다(손목 쪽 축 기준)
        r = math.radians(th) * thumb * np.clip((S - .045) / .02, 0, 1); c = np.array([-.072, .012])
        u, v = X2 - c[0], H2 - c[1]                                       # 엄지는 - 쪽 → 음의 각으로 돌면 손바닥(+H)으로 온다
        X2, H2 = c[0] + u * np.cos(r) + v * np.sin(r), c[1] - u * np.sin(r) + v * np.cos(r)
    W[idx] += np.outer(S2 - S, d) + np.outer(H2 - H, n) + np.outer(X2 - X, x)
    return a + d * .145 + n * .045 + x * -.055


def part(name, me0, W, mask, m, push, smooth=12, thick=.006):
    polys = np.empty(len(me0.polygons) * 4, int); me0.polygons.foreach_get("vertices", polys) if False else None
    fs = [p.vertices[:] for p in me0.polygons if mask[list(p.vertices)].all()]
    if not fs:
        return None
    idx = np.unique(np.array(fs)); rem = np.full(len(W), -1); rem[idx] = np.arange(len(idx))
    ob = meshobj(name, [tuple(W[k]) for k in idx], [tuple(int(rem[k]) for k in f) for f in fs], m)
    d = ob.modifiers.new("d", "DISPLACE"); d.strength = push; d.mid_level = 0
    s = ob.modifiers.new("sm", "SMOOTH"); s.iterations = smooth; s.factor = .6
    ob.modifiers.new("s", "SOLIDIFY").thickness = thick
    return ob


def tube(name, pts, r, m):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"; s = cu.splines.new("NURBS"); s.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        s.points[i].co = (*p, 1)
    s.use_cyclic_u = True; s.order_u = 3; cu.bevel_depth = r; cu.bevel_resolution = 2
    o = bpy.data.objects.new(name, cu); sc.collection.objects.link(o); cu.materials.append(m)
    return temp(o)


DZ = [0.0]          # 골반이 내려간 만큼(꿇기 · 쓰러짐) — 허리 높이는 골반 기준으로 잰다


class Ring:
    """허리 고리 — 골반 뼈 방향에 맞춰 기운다(숙이거나 꿇어도 허리를 두른다). 천은 고리에서 중력 쪽으로 늘어진다"""
    def __init__(self, c, u, v, ax, rx, ry):
        self.c, self.u, self.v, self.ax, self.rx, self.ry = c, u, v, ax, rx, ry
        h = -ax + np.array((0, 0, -2.0)); self.hang = h / np.linalg.norm(h)     # 서 있으면 아래, 엎드리면 땅 쪽

    def pt(self, a, ru=None, rv=None, down=0.0, back=0.0):
        ru = self.rx if ru is None else ru; rv = self.ry if rv is None else rv
        return tuple(self.c + ru * math.cos(a) * self.u + rv * math.sin(a) * self.v + down * self.hang - back * self.u)


SEGS = [None]


def waist_ring(W, lab, names, z, grow):
    """z: 쉴 때 높이(정점마다 ZR 로 고른다 — 자세와 상관없이 같은 허리)"""
    sel = (np.abs(ZR[0] - z) < .012) & np.isin(lab, [names.index(n) for n in ("pelvis", "spine", "chest")])
    a, b = SEGS[0]["pelvis"]; ax = (b - a) / np.linalg.norm(b - a)
    c = W[sel].mean(0); f = np.array((1., 0, 0)) - ax[0] * ax                 # 앞(+X)을 고리 평면에
    if np.linalg.norm(f) < .2:
        f = np.array((0, 0, -1.)) - ax[2] * ax
    u = f / np.linalg.norm(f); v = np.cross(ax, u)
    R = W[sel] - c
    return Ring(c, u, v, ax, np.abs(R @ u).max() + grow, np.abs(R @ v).max() + grow)


def helmet(HC, yaw):
    M = mat("metal", .5); rings, seg = 150, 240; vs = []; fs = []; keep = {}
    def prof(u):
        z = .14 - .355 * u; k = math.sqrt(max(0.0, 1 - (1 - min(u / .42, 1)) ** 2.2))
        return (.122 * k if u < .42 else .122 - .012 * (u - .42)), (.112 * k if u < .42 else .112 - .05 * ((u - .42) / .58) ** 1.2), z
    for i in range(rings + 1):
        u = i / rings; rx, ry, z = prof(u)
        for j in range(seg):
            p = (j / seg - .5) * 6.283
            fx = 1 + .10 * math.exp(-(p / .5) ** 2) * (1 if u > .35 else u / .35); back = 1 + .22 * max(0, u - .62) / .38 * max(0, math.cos(p - math.pi)) ** 2
            vs.append((HC.x + rx * math.cos(p) * fx * back, HC.y + ry * math.sin(p) * back, HC.z + z))
            ab = abs(p)
            eye = ab > .20 and ab < .86 and abs((u - .50 - .06 * (ab - .2)) / .058) ** 2 + ((ab - .52) / .38) ** 2 < 1
            slit = ab < .06 + .10 * max(0, u - .68) / .32 and u > .68
            keep[(i, j)] = not (eye or slit)
    for i in range(rings):
        for j in range(seg):
            k = (j + 1) % seg
            if keep[(i, j)] and keep[(i + 1, j)] and keep[(i, k)] and keep[(i + 1, k)]:
                a = i * seg + j; b = i * seg + k; fs.append((a, b, b + seg, a + seg))
    hel = meshobj("helmet", vs, fs, M); hel.modifiers.new("s", "SOLIDIFY").thickness = -.004
    bpy.ops.mesh.primitive_uv_sphere_add(radius=.098, location=(HC.x + .004, HC.y, HC.z - .01)); dk = temp(bpy.context.object); dk.scale = (1.02, .88, 1.22); dk.data.materials.append(mat("void", .03))

    def crown(a):
        return Vector((HC.x + .126 * math.cos(a), HC.y, HC.z - .009 + .153 * math.sin(a)))
    cv = bpy.data.curves.new("stand", "CURVE"); cv.dimensions = "3D"; s = cv.splines.new("POLY"); K = 40; s.points.add(K - 1)
    for i in range(K):
        a = math.radians(12 + 156 * i / (K - 1)); p = crown(a) + Vector((math.cos(a), 0, math.sin(a))) * .006; s.points[i].co = (p.x, p.y, p.z, 1)
    cv.bevel_depth = .014; cv.bevel_resolution = 3; stand = temp(bpy.data.objects.new("stand", cv)); sc.collection.objects.link(stand); cv.materials.append(M)
    hv = bpy.data.curves.new("hair", "CURVE"); hv.dimensions = "3D"; hv.bevel_depth = .0052; hv.bevel_resolution = 1
    for n in range(950):
        q = n / 949; a = math.radians(14 + 152 * q) + rr.uniform(-.015, .015); rad = Vector((math.cos(a), 0, math.sin(a))); base = crown(a) + rad * .012; base.y += rr.uniform(-.008, .008)
        tall = .125 * (1 - .2 * q) + rr.uniform(-.006, .01); fall = .12 + .62 * max(0, q - .35) / .65 * (.75 + .25 * rr.random()); pts = []
        for k in range(10):
            t = k / 9
            p = base + rad * tall * math.sin(min(1, t * 1.5) * 1.57) + Vector((-1, 0, 0)) * (fall * .55 * t ** 1.6) + Vector((0, 0, -1)) * (fall * 1.1 * max(0, t - .35) ** 1.7 * q ** 1.3)
            p.y += (base.y - HC.y) * 2.2 * t + .006 * math.sin(t * 5 + n) * t; pts.append(p)
        sp = hv.splines.new("NURBS"); sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p.x, p.y, p.z, 1); sp.points[i].radius = 1 - .8 * i / 9
        sp.order_u = 3; sp.use_endpoint_u = True
    hair = temp(bpy.data.objects.new("hair", hv)); sc.collection.objects.link(hair); hv.materials.append(mat("horse", .3))
    HT = Matrix.Translation(HC) @ Matrix.Rotation(math.radians(yaw), 4, "Z") @ Matrix.Translation(-HC)
    for o in (hel, dk, stand, hair):
        o.matrix_world = HT @ o.matrix_world
    return HT


def shield(loc, rot):
    prof = [(0, .06), (.10, .055), (.25, .04), (.38, .02), (.445, .003), (.455, -.012), (.495, -.014), (.50, 0), (.495, .014), (.455, .016), (.44, .02), (.38, .042), (.25, .062), (.10, .078), (0, .082)]
    vs = []; fs = []; N = 160; L = len(prof)
    for i in range(N):
        a = i / N * 6.283
        vs += [(r * math.cos(a), r * math.sin(a), z) for r, z in prof]
    for i in range(N):
        for j in range(L - 1):
            a = i * L + j; b = ((i + 1) % N) * L + j; fs.append((a, b, b + 1, a + 1))
    s = meshobj("shield", vs, fs, mat("shieldface", .3)); s.location = loc; s.rotation_euler = rot
    bpy.context.view_layer.update()

    def dome(r):
        t = [(0, .082), (.10, .078), (.25, .062), (.38, .042), (.44, .02)]
        for (r0, z0), (r1, z1) in zip(t, t[1:]):
            if r <= r1:
                return z0 + (z1 - z0) * (r - r0) / (r1 - r0)
        return .02

    def bar(a, b, w, nm):
        a, b = Vector(a), Vector(b); d = b - a; ln = d.length; d = d / ln; nn = Vector((-d.y, d.x)); v = []; f = []; NN = 40
        for i in range(NN):
            t = i / (NN - 1) * ln
            for k, o in enumerate((-w, -w * .9, w * .9, w)):
                p = a + d * t + nn * o; v.append((p.x, p.y, dome(p.length) + (0 if k in (0, 3) else .006) + .001))
        for i in range(NN - 1):
            for k in range(3):
                q = i * 4 + k; f.append((q, q + 1, q + 5, q + 4))
        o = meshobj(nm, v, f, mat("device", .95)); o.parent = s
    up = s.matrix_world.to_3x3().inverted() @ Vector((0, 0, 1)); u2 = Vector((up.x, up.y)).normalized(); rt = Vector((u2.y, -u2.x)); ap = u2 * .31
    bar(tuple(ap), tuple(-u2 * .28 + rt * .21), .042, "l1"); bar(tuple(ap), tuple(-u2 * .28 - rt * .21), .042, "l2")
    for i in range(30):
        a = i / 30 * 6.283
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=.0085, location=(.475 * math.cos(a), .475 * math.sin(a), .022)); q = temp(bpy.context.object); q.data.materials.append(mat("device", .95)); q.parent = s


def spear(mid):
    A = mid + Vector((-1.2, 0, -.115)); B = mid + Vector((1.8, 0, .175)); c = (A + B) / 2; d = B - A
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=.0125, depth=d.length, location=c); o = temp(bpy.context.object); o.rotation_mode = "QUATERNION"; o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized()); o.data.materials.append(mat("skin"))
    L = [(0, 0), (.02, .03), (.09, .042), (.2, .018), (.3, 0)]; v = []; f = []
    for i in range(32):
        a = i / 32 * 6.283
        v += [(r * math.cos(a) * .45, r * math.sin(a), z) for z, r in L]
    for i in range(32):
        for j in range(4):
            a = i * 5 + j; b = ((i + 1) % 32) * 5 + j; f.append((a, b, b + 1, a + 1))
    t = meshobj("tip", v, f, mat("metal")); t.location = B; t.rotation_mode = "QUATERNION"; t.rotation_quaternion = o.rotation_quaternion


def cloak():
    gw, gh = 60, 90; v = []; f = []
    for j in range(gh):
        t = j / (gh - 1)
        for i in range(gw):
            u = i / (gw - 1) - .5; fold = (.055 * math.sin(u * 19 + t * 2.2) + .028 * math.sin(u * 41 + t * 5)) * t ** .7
            v.append((-.075 - .62 * t * t - .10 * t + fold * .9 - .12 * (1 - t) * (u * 2) ** 2, u * (.34 + .72 * t ** .8) + .09 * t * math.sin(t * 3.2), 1.455 - .98 * t + .05 * math.sin(u * 9) * t + fold * .25 - .05 * (1 - t) * (u * 2) ** 2))
    for j in range(gh - 1):
        for i in range(gw - 1):
            a = j * gw + i; f.append((a, a + 1, a + gw + 1, a + gw))
    meshobj("cloak", v, f, mat("cloth", .5)).modifiers.new("s", "SOLIDIFY").thickness = .006


def tunic(W, segs, names, lab, swing=0.0):
    """천: 허리에서 나와 다리를 피해 늘어지고, 뛰는 방향 반대로 날린다"""
    C = mat("cloth", .62)
    torso = np.isin(lab, [names.index(n) for n in ("pelvis", "spine", "chest")]); d, t = segment_dist(W, segs["uaL"][0], segs["uaL"][1]); d2, t2 = segment_dist(W, segs["uaR"][0], segs["uaR"][1])
    sleeve = ((lab == names.index("uaL")) & (t < .5)) | ((lab == names.index("uaR")) & (t2 < .5))
    part("shirt", ME[0], W, (torso | sleeve) & (ZR[0] > 1.0) & (ZR[0] < 1.47), C, .013, 10)
    rg = waist_ring(W, lab, names, 1.06, .012)
    gw, gh = 180, 40; P = np.zeros((gw * gh, 3))
    for j in range(gh):
        s = j / (gh - 1)
        for i in range(gw):
            a = i / gw * 6.283; r = 1 + (.09 * math.sin(a * 13 + 1) + .05 * math.sin(a * 27)) * s ** .7
            P[j * gw + i] = rg.pt(a, (rg.rx + .11 * s ** 1.3) * r, (rg.ry + .09 * s ** 1.3) * r, .36 * s - .05 * swing * s * s - .02 * math.sin(a * 5) * s, .16 * swing * s * s)
    for th, sh in (("thL", "L"), ("thR", "R")):                                  # 허벅지를 뚫지 않게 밀어낸다
        a, b = segs[th]; dist, tt = segment_dist(P, a, b); cl = a + tt[:, None] * (b - a); inside = dist < .115
        P[inside] = cl[inside] + (P[inside] - cl[inside]) / np.maximum(dist[inside, None], 1e-4) * .115
    f = [(j * gw + i, j * gw + (i + 1) % gw, (j + 1) * gw + (i + 1) % gw, (j + 1) * gw + i) for j in range(gh - 1) for i in range(gw)]
    meshobj("skirt", [tuple(p) for p in P], f, C)
    tube("belt", [rg.pt(a, rg.rx + .012, rg.ry + .012, -.004) for a in np.linspace(0, 6.283, 24, endpoint=False)], .011, mat("metal"))


def blobs(name, pts, m):
    """메타볼 덩어리(털 · 수염) → 메시"""
    mb = bpy.data.metaballs.new(name); mb.resolution = mb.render_resolution = .006; mb.threshold = .5; o = bpy.data.objects.new(name, mb); sc.collection.objects.link(o)
    for p, r in pts:
        e = mb.elements.new(); e.co = tuple(p); e.radius = r
    dg = bpy.context.evaluated_depsgraph_get(); me = bpy.data.meshes.new_from_object(o.evaluated_get(dg)); me.polygons.foreach_set("use_smooth", [True] * len(me.polygons)); me.update()
    bpy.data.objects.remove(o); ob = temp(bpy.data.objects.new(name + "m", me)); sc.collection.objects.link(ob); me.materials.clear(); me.materials.append(m)
    return ob


def modern(me, W, segs, names, lab, has):
    """현대 옷 — 몸에서 잘라 부풀린다(셔츠 · 반팔 · 바지 · 신발 · 재킷 · 실험복) + 짧은 머리 · 안경"""
    L = lambda *ns: np.isin(lab, [names.index(n) for n in ns])  # noqa: E731
    def along(bn, lo, hi):
        t = segment_dist(W, *segs[bn])[1]; return (lab == names.index(bn)) & (t >= lo) & (t <= hi)
    torso = L("pelvis", "spine", "chest") & (ZR[0] > .89) & (ZR[0] < 1.47)
    tone = SP.get("cloth_tone", .7)

    def loose(bones, ease=.012, keep=.35, fold=0.0):
        """천은 근육을 따라가지 않는다 — 팔 · 다리를 한 줄기로 보고 위에서 아래로 고르게 가늘어지는 통으로(살 굴곡은 keep 만큼만)"""
        V = W.copy(); bones = list(bones)
        chains = [c for c in (("thL", "shL"), ("thR", "shR"), ("uaL", "faL"), ("uaR", "faR")) if c[0] in bones or c[1] in bones] + [(b_,) for b_ in bones if b_ in ("ftL", "ftR")]
        for ch in chains:
            Rs = []
            for bn in ch:
                m = lab == names.index(bn); Rs.append(np.percentile(segment_dist(V[m], *segs[bn])[0], 80) + ease)
            for k, bn in enumerate(ch):
                if bn not in bones:
                    continue
                m = lab == names.index(bn); a_, b_ = segs[bn]; dist, tt = segment_dist(V[m], a_, b_)
                T = (k + tt) / len(ch); R = Rs[0] * (1 - T) + Rs[-1] * T if len(ch) > 1 else np.full_like(tt, Rs[0])
                c_ = a_ + tt[:, None] * (b_ - a_)
                rad = keep * dist + (1 - keep) * R
                if fold and len(ch) > 1:                              # 주름: 관절 안쪽 · 단 위에서 천이 접혀 고리 모양으로 몰린다
                    ax_ = (b_ - a_) / np.linalg.norm(b_ - a_); u_ = np.cross(ax_, (0, 0, 1.)); u_ = u_ / (np.linalg.norm(u_) or 1); w_ = np.cross(ax_, u_)
                    th = np.arctan2((V[m] - c_) @ w_, (V[m] - c_) @ u_)
                    env = .35 + np.exp(-((T - .5) / .1) ** 2) + 1.3 * np.exp(-((T - .97) / .05) ** 2)
                    rad = rad + fold * env * np.sin(T * 6.283 * 9 + 1.6 * np.sin(th * 2 + T * 11)) * (.6 + .4 * np.cos(th * 3 + k))
                V[m] = c_ + (V[m] - c_) / np.maximum(dist[:, None], 1e-4) * rad[:, None]
        return V
    if "shirt" in has or "tshirt" in has:
        sl = (L("uaL", "uaR") | along("faL", 0, .92) | along("faR", 0, .92)) if "shirt" in has else (along("uaL", 0, .55) | along("uaR", 0, .55))
        part("shirt", me, loose(("uaL", "uaR", "faL", "faR"), .006, .5, .004), (torso | sl) & ~L("neck", "head"), mat("shirt", tone), .009, 14)
    if "jacket" in has or "coat" in has:
        jt = SP.get("jacket_tone", .3 if "jacket" in has else .9)
        part("jacket", me, loose(("uaL", "uaR", "faL", "faR"), .016, .3, .006), (torso | L("uaL", "uaR") | along("faL", 0, .85) | along("faR", 0, .85)) & ~L("neck", "head"), mat("jacket", jt), .022, 40, .008)
        if "coat" in has:                                                   # 실험복 · 외투: 허리 아래로 무릎까지 늘어진 자락(앞은 벌어진다)
            rg = waist_ring(W, lab, names, .98, .03); gw, gh = 120, 30; P = np.zeros((gw * gh, 3))
            for j in range(gh):
                t_ = j / (gh - 1)
                for i in range(gw):
                    a = .35 + i / (gw - 1) * (6.283 - .7)                    # 앞(+X)은 열어 둔다
                    P[j * gw + i] = rg.pt(a, rg.rx + .05 * t_, rg.ry + .06 * t_, .48 * t_)
            for th in ("thL", "thR"):
                a_, b_ = segs[th]; dist, tt = segment_dist(P, a_, b_); cl = a_ + tt[:, None] * (b_ - a_); inside = dist < .1
                P[inside] = cl[inside] + (P[inside] - cl[inside]) / np.maximum(dist[inside, None], 1e-4) * .1
            f = [(j * gw + i, j * gw + i + 1, (j + 1) * gw + i + 1, (j + 1) * gw + i) for j in range(gh - 1) for i in range(gw - 1)]
            meshobj("coatskirt", [tuple(p) for p in P], f, mat("jacket", jt)).modifiers.new("s", "SOLIDIFY").thickness = .006
    if "trousers" in has:
        ankle = min(segs["shL"][1][2], segs["shR"][1][2]) + .03
        part("trousers", me, loose(("thL", "thR", "shL", "shR"), .02, .25, .006), ((L("thL", "thR", "shL", "shR") & (ZR[0] > .12)) | (L("pelvis") & (ZR[0] < 1.02))), mat("trousers", SP.get("trouser_tone", .35)), .012, 30)
    if "shoes" in has:
        for ft, sh in (("ftL", "shL"), ("ftR", "shR")):
            part("shoe" + ft, me, loose((ft,), .01, .45), (lab == names.index(ft)) | ((lab == names.index(sh)) & (ZR[0] < .13)), mat("shoe", .12), .016, 45, .006)
    if has & {"shirt", "jacket", "coat"}:                                      # 깃: 목둘레 고리(셔츠는 얇게, 재킷 · 실험복은 접힌 칼라처럼 두껍게)
        nk = L("neck", "chest") & (np.abs(ZR[0] - 1.455) < .012)
        if nk.sum() > 20:
            P_ = W[nk]; c_ = P_.mean(0); A_ = np.arctan2(P_[:, 1] - c_[1], P_[:, 0] - c_[0]); o_ = np.argsort(A_)
            ring = [tuple(P_[o_[i]] + (P_[o_[i]] - c_) * .25 + np.array((0, 0, .008))) for i in range(0, len(o_), max(1, len(o_) // 28))]
            tube("collar", ring, .016 if has & {"jacket", "coat"} else .009, mat("jacket" if has & {"jacket", "coat"} else "shirt", SP.get("jacket_tone", .3 if "jacket" in has else .9) if has & {"jacket", "coat"} else tone))
    bpb = ar.pose.bones["head"]; RM = ar.matrix_world @ bpb.matrix @ bpb.bone.matrix_local.inverted(); RI = np.array(RM.inverted())
    hd = lab == names.index("head"); Hr = (RI[:3, :3] @ W.T).T + RI[:3, 3]
    up_ = hd & (Hr[:, 2] > 1.5); zn = Hr[up_][np.argmin(Hr[up_][:, 1]), 2]
    if "shorthair" in has:                                                  # 짧은 머리: 이마선 위 · 귀 위 · 뒤통수를 덮는다
        face_y = Hr[hd][:, 1].min()
        m = hd & ((Hr[:, 2] > zn + .075) | ((Hr[:, 1] > face_y + .07) & (Hr[:, 2] > zn - .045))) & ~((np.abs(Hr[:, 0]) > .068) & (Hr[:, 2] < zn + .03) & (Hr[:, 1] < face_y + .12))
        hair = part("shorthair", me, W, m, mat("hairmass" + str(SP.get("hair_tone", .16)), SP.get("hair_tone", .16)), .014, 6, .01)
        if hair:
            tx = bpy.data.textures.new("hn", "CLOUDS"); tx.noise_scale = .012
            dm = hair.modifiers.new("t", "DISPLACE"); dm.texture = tx; dm.strength = .008; dm.texture_coords = "GLOBAL"
    if "longhair" in has:                                                   # 긴 머리: 정수리에서 뒤 · 옆으로 흘러 어깨 아래까지, 세로 결
        face_y = Hr[hd][:, 1].min(); HM = mat("hairmass" + str(SP.get("hair_tone", .16)), SP.get("hair_tone", .16))
        cap = hd & ((Hr[:, 2] > zn + .055) | ((Hr[:, 1] > face_y + .07) & (Hr[:, 2] > zn - .05)))
        parts_ = [part("longcap", me, W, cap, HM, .009, 10, .008)]
        pts = []
        for _ in range(420):                                                  # 뒤로 늘어진 머리 — 촘촘하게 겹쳐 한 덩어리로
            t = rr.random() ** .8; ang = rr.uniform(-1.25, 1.25)
            r_ = .088 + .015 * t; q = Vector((math.sin(ang) * r_ * (1 - .15 * t), -.03 + math.cos(ang) * r_ * .95 + .01, zn + .06 - .31 * t))
            pts.append((np.array(RM @ q), .028 * (1 - .3 * t)))
        parts_.append(blobs("longhair", pts, HM))
        tx = bpy.data.textures.new("strand", "WOOD"); tx.wood_type = "BANDNOISE"; tx.noise_basis_2 = "SIN"; tx.noise_scale = .02; tx.turbulence = 3
        for o_ in parts_:
            if o_ is None:
                continue
            sm = o_.modifiers.new("sm", "SMOOTH"); sm.iterations = 6
            dm = o_.modifiers.new("strand", "DISPLACE"); dm.texture = tx; dm.strength = .006; dm.texture_coords = "GLOBAL"
    if "glasses" in has:
        fy = Hr[hd][:, 1].min(); ez = zn + .032
        for sx in (1, -1):
            loc = RM @ Vector((sx * .033, fy + .012, ez)); bpy.ops.mesh.primitive_torus_add(major_radius=.021, minor_radius=.0028, location=tuple(loc))
            g = temp(bpy.context.object); g.data.materials.append(mat("void", .05)); g.rotation_euler = (RM.to_3x3() @ Matrix.Rotation(math.radians(90), 3, "X")).to_euler()
        bpy.ops.mesh.primitive_cylinder_add(radius=.0022, depth=.026, location=tuple(RM @ Vector((0, fy + .01, ez + .004))))
        g = temp(bpy.context.object); g.data.materials.append(mat("void", .05)); g.rotation_euler = (RM.to_3x3() @ Matrix.Rotation(math.radians(90), 3, "Y")).to_euler()


def curly_hair():
    bpb = ar.pose.bones["head"]; RM = ar.matrix_world @ bpb.matrix @ bpb.bone.matrix_local.inverted()
    mb = bpy.data.metaballs.new("hm"); mb.resolution = mb.render_resolution = .005; mb.threshold = .5; o = bpy.data.objects.new("hm", mb); sc.collection.objects.link(o); C0 = Vector((0, -.012, 1.585))
    for _ in range(280):
        v = Vector((rr.gauss(0, 1), rr.gauss(0, 1), rr.gauss(0, 1))).normalized()
        if (v.y < -.30 and v.z < .42) or (v.z < -.25 and v.y < .3) or (abs(v.x) > .75 and v.z < 0 and v.y < .25):
            continue
        e = mb.elements.new(); e.co = tuple(RM @ (C0 + Vector((v.x * .098, v.y * .112, v.z * .108)))); e.radius = .030
    dg = bpy.context.evaluated_depsgraph_get(); me = bpy.data.meshes.new_from_object(o.evaluated_get(dg)); me.polygons.foreach_set("use_smooth", [True] * len(me.polygons)); me.update()
    bpy.data.objects.remove(o); m = bpy.data.objects.new("hairm", me); sc.collection.objects.link(m); me.materials.clear(); me.materials.append(mat("hairmass" + str(SP.get("hair_tone", .16)), SP.get("hair_tone", .16))); temp(m)
    for x in (.033, -.033):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=.0125, location=tuple(RM @ Vector((x, -.104, 1.566)))); q = temp(bpy.context.object); q.data.materials.append(mat("void", .03))


ME = [None]
HANDS = ["relax", "relax"]


def dress(me, W, segs, names, lab, cos, swing):
    has = set(cos)
    DZ[0] = float(segs["pelvis"][0][2]) - .92; SEGS[0] = segs
    hs = SP.get("hands") or {}
    GR = hand(W, segs, names, "hdR", hs.get("R") or HANDS[1]); GL = hand(W, segs, names, "hdL", hs.get("L") or HANDS[0])
    me.vertices.foreach_set("co", W.astype(np.float64).ravel()); me.update(); me.polygons.foreach_set("use_smooth", [True] * len(me.polygons)); me.update()
    me.materials.clear(); me.materials.append(mat("skin")); sk = temp(bpy.data.objects.new("skinm", me)); sc.collection.objects.link(sk); ME[0] = me
    HP = W[lab == names.index("head")].mean(0); HC = Vector((HP[0] + .012, HP[1], HP[2] + .02))
    if "cuirass" in has:
        a, b = segs["pelvis"][0], segs["chest"][1]; dc = np.linalg.norm((W - (a + segment_dist(W, a, b)[1][:, None] * (b - a))) * np.array([1, .8, 1]), axis=1)
        torso = np.isin(lab, [names.index(n) for n in ("pelvis", "spine", "chest")])
        part("cuirass", me, W, (torso | (dc < .205)) & (ZR[0] > 1.02) & (ZR[0] < 1.455) & (~np.isin(lab, [names.index("neck"), names.index("head")])), mat("armor", .42), .02)
        rg = waist_ring(W, lab, names, 1.04, .03)
        tube("cbelt", [rg.pt(q) for q in np.linspace(0, 6.283, 24, endpoint=False)], .016, mat("device", .95))
    if "greaves" in has:
        for sh in ("shL", "shR"):
            a, b = segs[sh]; t = segment_dist(W, a, b)[1]
            part("g" + sh, me, W, (lab == names.index(sh)) & (t > .1) & (t < .93), mat("armor", .42), .012)
    if "pteruges" in has:
        rg = waist_ring(W, lab, names, 1.0, .03); N = 22
        for i in range(N):
            a = i / N * 6.283; rx, ry = rg.rx, rg.ry
            v = [rg.pt(a, rx, ry, -.04), rg.pt(a + .2, rx, ry, -.04), rg.pt(a + .2, rx + .07, ry + .065, .23), rg.pt(a, rx + .07, ry + .065, .23)]
            meshobj("p%d" % i, v, [(0, 1, 2, 3)], mat("cloth")).modifiers.new("s", "SOLIDIFY").thickness = .008
    if "tunic" in has:
        tunic(W, segs, names, lab, swing)
    if "beard" in has or "horns" in has:
        bpb = ar.pose.bones["head"]; RM = ar.matrix_world @ bpb.matrix @ bpb.bone.matrix_local.inverted()
        HC_np = lambda: np.array(RM @ Vector((0, -.03, 1.6)))  # noqa: E731  머리 가운데
    if "beard" in has:                                                     # 수염: 쉴 때 얼굴 좌표에서 턱선 · 입가를 골라 그 자리에 자라고 턱 아래로 늘어진다
        RI = np.array(RM.inverted()); hd = np.isin(lab, [names.index("head"), names.index("neck")])
        Hp = W[hd]; Hr = (RI[:3, :3] @ Hp.T).T + RI[:3, 3]
        up_ = Hr[:, 2] > 1.5; zn = Hr[up_][np.argmin(Hr[up_][:, 1]), 2]           # 코끝 높이 — 입 · 턱은 여기서 잰다
        front = Hr[:, 1] < Hr[:, 1].min() + .085
        jaw = front & (Hr[:, 2] > zn - .125) & (Hr[:, 2] < zn - .052) & (np.abs(Hr[:, 0]) < .066)
        lip = front & (np.abs(Hr[:, 2] - (zn - .03)) < .005) & (np.abs(Hr[:, 0]) < .028) & (Hr[:, 1] < Hr[:, 1].min() + .03)
        pts = []
        for src, n_, r_ in ((jaw, 240, (.013, .019)), (lip, 60, (.005, .0075))):
            ids = np.where(src)[0]
            for k in rr.sample(list(ids), min(n_, len(ids))):
                pts.append((Hp[k] + (Hp[k] - HC_np()) * .06, rr.uniform(*r_)))
        cz = Hr[jaw][:, 2].min() if jaw.any() else 1.47; cy = Hr[jaw][:, 1].min() if jaw.any() else -.1
        L = SP.get("beard_len", .09)
        for _ in range(110):                                                # 턱 아래로 늘어진 부분(끝으로 갈수록 가늘게)
            t = rr.random(); q = Vector((rr.gauss(0, .03 * (1 - .6 * t)), cy + .02 + .015 * t, cz - L * t))
            pts.append((np.array(RM @ q), .022 * (1 - .55 * t)))
        blobs("bd", pts, mat("hairmass" + str(SP.get("hair_tone", .16)), SP.get("hair_tone", .16)))
    if "horns" in has:                                                     # 염소 뿔: 이마에서 뒤로 넘어가며 휘고 끝이 바깥으로
        for sx in (1, -1):
            pts = []
            for t in np.linspace(0, 1, 10):
                pts.append(RM @ Vector((sx * (.04 + .05 * t + .03 * t ** 3), -.05 + .20 * t - .02 * math.sin(t * 3.0), 1.66 + .17 * math.sin(t * 2.2) - .02 * t)))
            cv = bpy.data.curves.new("hn", "CURVE"); cv.dimensions = "3D"; sp = cv.splines.new("NURBS"); sp.points.add(len(pts) - 1)
            for i, q in enumerate(pts):
                sp.points[i].co = (q.x, q.y, q.z, 1); sp.points[i].radius = 1 - .9 * i / (len(pts) - 1)
            sp.use_endpoint_u = True; sp.order_u = 4; cv.bevel_depth = .03; cv.bevel_resolution = 4
            h = temp(bpy.data.objects.new("hn", cv)); sc.collection.objects.link(h); cv.materials.append(mat("horn", .55))
            for k in range(9):                                                 # 뿔 마디(고리)
                t = .08 + k * .09; q = pts[int(t * 9)]
                bpy.ops.mesh.primitive_torus_add(major_radius=.027 * (1 - .85 * t), minor_radius=.004, location=tuple(q)); r_ = temp(bpy.context.object); r_.data.materials.append(mat("horn", .55))
                nx = pts[min(9, int(t * 9) + 1)] - q; r_.rotation_euler = nx.to_track_quat("Z", "Y").to_euler()
    if "goatlegs" in has:                                                  # 판 · 사티로스: 엉덩이부터 텁수룩한 털 다리, 발은 발굽
        for ft, sh in (("ftL", "shL"), ("ftR", "shR")):
            ank = segs[sh][1]; m = (lab == names.index(ft)) | ((lab == names.index(sh)) & (ZR[0] < .12))
            W[m] = ank + (W[m] - ank) * np.array([.25, .25, .4])                  # 사람 발은 발굽 안으로 접는다
            bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=.048, radius2=.03, depth=ank[2] + .02, location=(ank[0] + .025, ank[1], (ank[2] + .02) / 2))
            hv = temp(bpy.context.object); hv.rotation_euler = (0, math.radians(-14), 0); hv.data.materials.append(mat("void", .08))
        me.vertices.foreach_set("co", W.astype(np.float64).ravel()); me.update()
        legs = np.isin(lab, [names.index(n) for n in ("thL", "thR", "shL", "shR")]) | ((lab == names.index("pelvis")) & (ZR[0] < 1.0))
        fur = part("fur", me, W, legs & (ZR[0] > .11), mat("hairmass", .22), .02, smooth=4, thick=.004)
        tx = bpy.data.textures.new("furn", "CLOUDS"); tx.noise_scale = .018; tx.noise_depth = 2
        dm = fur.modifiers.new("shag", "DISPLACE"); dm.texture = tx; dm.strength = .032; dm.mid_level = .3; dm.texture_coords = "GLOBAL"
        bpy.ops.object.select_all(action="DESELECT")
        fur.modifiers.move(len(fur.modifiers) - 1, 1)
    if has & {"shirt", "tshirt", "jacket", "coat", "trousers", "shoes", "shorthair", "glasses", "longhair"}:
        modern(me, W, segs, names, lab, has)
    if "helmet" in has:
        helmet(HC, SP.get("head_yaw", 18))
    if "hair" in has:
        curly_hair()
    if "shield" in has:
        shield((GL[0] + .22, GL[1] + .1, 1.22), (0, math.radians(76), math.radians(SP.get("shield_yaw", -4))))
    if "spear" in has:
        spear(Vector(GR))
    if "cloak" in has:
        cloak()


def normal_material():
    n = bpy.data.materials.new("n"); n.use_nodes = True; t = n.node_tree; t.nodes.clear()
    o = t.nodes.new("ShaderNodeOutputMaterial"); e = t.nodes.new("ShaderNodeEmission"); g = t.nodes.new("ShaderNodeNewGeometry"); v = t.nodes.new("ShaderNodeVectorTransform"); v.vector_type = "NORMAL"; v.convert_from = "WORLD"; v.convert_to = "CAMERA"
    a = t.nodes.new("ShaderNodeVectorMath"); a.operation = "MULTIPLY"; a.inputs[1].default_value = (.5, .5, .5); b = t.nodes.new("ShaderNodeVectorMath"); b.operation = "ADD"; b.inputs[1].default_value = (.5, .5, .5)
    t.links.new(g.outputs["Normal"], v.inputs[0]); t.links.new(v.outputs[0], a.inputs[0]); t.links.new(a.outputs[0], b.inputs[0]); t.links.new(b.outputs[0], e.inputs[0]); t.links.new(e.outputs[0], o.inputs[0])
    return n


def id_pass(path):
    """재질마다 다른 색(옷 · 살 · 갑옷 경계) — 화풍이 면 방향 변화로 못 찾는 옷 경계선을 여기서 찾는다"""
    keep = {}; made = {}
    for o in sc.objects:
        if o.hide_render or not hasattr(o.data, "materials"):
            continue
        keep[o.name] = [s_.material for s_ in o.material_slots]
        for s_ in o.material_slots:
            m = s_.material
            if m is None:
                continue
            if m.name not in made:
                h = (len(made) * .618034) % 1
                e = bpy.data.materials.new("id_" + m.name); e.use_nodes = True; t = e.node_tree; t.nodes.clear()
                out = t.nodes.new("ShaderNodeOutputMaterial"); em = t.nodes.new("ShaderNodeEmission")
                import colorsys
                em.inputs[0].default_value = (*colorsys.hsv_to_rgb(h, .9, .9), 1); t.links.new(em.outputs[0], out.inputs[0]); made[m.name] = e
            s_.material = made[m.name]
    set_samples(1); sc.render.filepath = path; bpy.ops.render.render(write_still=True)
    for o in sc.objects:
        for s_, m in zip(o.material_slots, keep.get(o.name, [])):
            s_.material = m


def set_samples(n):
    if ENGINE == "CYCLES":
        sc.cycles.samples = n
    else:
        sc.eevee.taa_render_samples = max(8, n)


def render_set():
    """배경 세트 — 사람 대신 땅 · 산 · 달을 3D 로 만들어 같은 화풍의 손이 긋게 한다(평면 도형 배경은 그림과 따로 논다)"""
    global sc, ENGINE
    bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene; ENGINE = pick_engine()
    st = SP["set"]; W_, H_ = SP.get("size", (1920, 1080)); seed = SP.get("seed", 3)
    sc.render.engine = ENGINE; sc.render.film_transparent = True; sc.render.resolution_x, sc.render.resolution_y = W_, H_
    sc.view_settings.view_transform = "Standard"; sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"; sc.render.image_settings.color_depth = "16"
    if ENGINE != "CYCLES":
        sc.eevee.use_shadows = True
    cam = bpy.data.cameras.new("c"); cam.lens = SP.get("lens", 30); co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
    co.location = (0, -12, SP.get("eye", 1.6)); co.rotation_euler = (math.radians(88), 0, 0)
    sun = bpy.data.lights.new("s", "SUN"); sun.energy = SP.get("light", 3); so = bpy.data.objects.new("s", sun); sc.collection.objects.link(so); so.rotation_euler = [math.radians(v) for v in SP.get("sun", (62, 0, -35))]
    w = bpy.data.worlds.new("w"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (.03, .03, .03, 1); sc.world = w
    G = mat("ground", .7)
    for k, (y0, sx, sy, amp, ns) in enumerate(((70, 120, 175, .7, 9), (75, 320, 50, 8, 26), (150, 520, 80, 30, 70))):   # 앞 들판 · 중간 언덕 · 먼 산맥(완만하게)
        if k and st not in ("hills", "mountains"):
            continue
        if k == 2 and st != "mountains" and not SP.get("far", True):
            continue
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=300, y_subdivisions=90, size=1, location=(0, y0, -.3 if not k else 0))
        g = bpy.context.object; g.scale = (sx, sy, 1); bpy.ops.object.transform_apply(scale=True)
        tx = bpy.data.textures.new("t%d" % k, "CLOUDS"); tx.noise_scale = ns; tx.noise_depth = 1
        dm = g.modifiers.new("d", "DISPLACE"); dm.texture = tx; dm.strength = amp; dm.mid_level = .35; dm.texture_coords = "GLOBAL"
        g.data.materials.append(G); bpy.ops.object.shade_smooth()
    if SP.get("moon"):
        mx, mz, mr = SP["moon"]                                               # 화면 비율 위치(0~1) · 반지름(화면 높이 비율)
        D = 300; hfov = 2 * math.atan(18 / cam.lens)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=48, radius=D * math.tan(hfov / 2) * mr * 2 * H_ / W_, location=((mx - .5) * 2 * D * math.tan(hfov / 2), D - 12, 1.6 + (.5 - mz) * 2 * D * math.tan(hfov / 2) * H_ / W_))
        mo = bpy.context.object; bpy.ops.object.shade_smooth()
        tx = bpy.data.textures.new("cr", "VORONOI"); tx.noise_scale = .25
        dm = mo.modifiers.new("d", "DISPLACE"); dm.texture = tx; dm.strength = mo.dimensions[0] * .02
        em = bpy.data.materials.new("moon"); em.use_nodes = True; t_ = em.node_tree; t_.nodes.clear()          # 달은 스스로 빛난다
        o_ = t_.nodes.new("ShaderNodeOutputMaterial"); e_ = t_.nodes.new("ShaderNodeEmission"); e_.inputs[0].default_value = (1, 1, 1, 1); e_.inputs[1].default_value = 1.0
        t_.links.new(e_.outputs[0], o_.inputs[0]); mo.data.materials.append(em)
    nm = normal_material(); vl = sc.view_layers[0]; tag = SP["out"] + "_000"
    vl.material_override = None; set_samples(SP.get("samples", 24)); sc.render.filepath = tag + "_shade.png"; bpy.ops.render.render(write_still=True)
    vl.material_override = nm; set_samples(8); sc.render.filepath = tag + "_normal.png"; bpy.ops.render.render(write_still=True)
    vl.material_override = None; id_pass(tag + "_id.png")


PAL = {"skin": ((.62, .40, .30), .55, 0), "cloth": ((.55, .14, .08), .85, 0), "armor": ((.55, .38, .16), .38, .9), "metal": ((.6, .42, .18), .35, .9),
       "device": ((.25, .14, .07), .7, 0), "hairmass": ((.06, .04, .03), .6, 0), "horn": ((.45, .40, .32), .5, 0), "void": ((.02, .02, .02), .5, 0),
       "shirt": ((.8, .78, .72), .8, 0), "jacket": ((.15, .17, .22), .7, 0), "trousers": ((.2, .2, .24), .8, 0), "shoe": ((.08, .06, .05), .5, 0)}


def pbr(name, col, rough, metal, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; t = m.node_tree; b = t.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if sss and "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = sss
    return m


def colorize(objs, colors):
    """무대용 색 재질 — 회색 재질 이름(skin · cloth · armor …)을 배우마다 색으로"""
    made = {}
    for o in objs:
        if not hasattr(o.data, "materials"):
            continue
        for sl in o.material_slots:
            if sl.material is None:
                continue
            key = sl.material.name.rstrip("0123456789.")
            key = "hairmass" if key.startswith("hairmass") else key
            if key not in made:
                col, rough, metal = PAL.get(key, ((.5, .5, .5), .7, 0))
                col = tuple(colors.get(key, col))
                made[key] = pbr("stage_" + key, col, rough, metal, .15 if key == "skin" else 0)
            sl.material = made[key]


def stage():
    """영화 같은 장면 — 하늘 · 안개 · 낮은 해 · 지형 · 여러 배우(색 재질)를 한 컷으로 렌더한다. 결과: <out>_000_color.png"""
    global sc
    st = SP["stage"]
    setup(); sc.render.film_transparent = False
    r0 = eval_body({"lift": 0, "aims": []}); rest_hands(*r0[1:]); ZR[0] = r0[1][:, 2].copy()
    for o in list(sc.objects):                                    # 인물 렌더용 해 · 카메라는 무대 것으로 바꾼다
        if o.type in ("LIGHT", "CAMERA"):
            bpy.data.objects.remove(o)
    base = dict(SP)
    for a in st.get("actors", []):
        SP.clear(); SP.update(base); SP.update(a)
        if a.get("cycle_t") is not None:
            pose = run_pose(a["cycle_t"], a.get("stride", .36)); HANDS[:] = POSE_HANDS["run"]
        else:
            pose = a["pose"] if isinstance(a["pose"], dict) else POSES[a["pose"]]; HANDS[:] = POSE_HANDS.get(a["pose"] if isinstance(a["pose"], str) else "stand", ("relax", "relax"))
        me, W, segs, names, lab = eval_body(pose)
        dress(me, W, segs, names, lab, a.get("costume", []), a.get("swing", 1.0 if a.get("cycle_t") is not None else 0))
        objs = list(TEMP); TEMP.clear()
        colorize(objs, a.get("colors", {}))
        e = bpy.data.objects.new("actor", None); sc.collection.objects.link(e)
        for o in objs:
            o.parent = e
        e.location = (*a.get("at", (0, 0))[:2], a.get("z", 0)); e.rotation_euler = (0, 0, math.radians(a.get("yaw", 0)))
        e.scale = (a.get("scale", 1),) * 3
    SP.clear(); SP.update(base)
    # 지형
    G = pbr("ground", tuple(st.get("ground", (.42, .33, .2))), .95, 0)
    nt = G.node_tree; b = nt.nodes.get("Principled BSDF"); n_ = nt.nodes.new("ShaderNodeTexNoise"); n_.inputs["Scale"].default_value = 3; cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (*[c * .6 for c in st.get("ground", (.42, .33, .2))], 1); cr.color_ramp.elements[1].color = (*[min(1, c * 1.25) for c in st.get("ground", (.42, .33, .2))], 1)
    nt.links.new(n_.outputs[0], cr.inputs[0]); nt.links.new(cr.outputs[0], b.inputs["Base Color"])
    for k, (y0, sx, sy, amp, ns, z0) in enumerate(((0, 160, 160, .5, 9, -.05), (110, 600, 120, 14, 40, -2), (260, 1200, 200, 55, 110, -6))):
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=260, y_subdivisions=160 if not k else 80, size=1, location=(0, y0, z0))
        g = bpy.context.object; g.scale = (sx, sy, 1); bpy.ops.object.transform_apply(scale=True)
        tx = bpy.data.textures.new("tg%d" % k, "CLOUDS"); tx.noise_scale = ns; tx.noise_depth = 2
        dm = g.modifiers.new("d", "DISPLACE"); dm.texture = tx; dm.strength = amp; dm.mid_level = .5 if k else .5; dm.texture_coords = "GLOBAL"
        if not k:                                                     # 배우 자리는 평평하게
            vg = g.vertex_groups.new(name="far"); vs = [v.index for v in g.data.vertices if (v.co.x ** 2 + v.co.y ** 2) ** .5 > 6]
            vg.add(vs, 1.0, "REPLACE"); dm.vertex_group = "far"
        g.data.materials.append(G); bpy.ops.object.shade_smooth()
    # 하늘 · 해 · 안개
    w = bpy.data.worlds.new("w"); w.use_nodes = True; sc.world = w; t = w.node_tree; bg = t.nodes["Background"]
    el, rot = st.get("sun_elev", 8), st.get("sun_rot", 200)
    sk = t.nodes.new("ShaderNodeTexSky")
    try:
        sk.sky_type = "NISHITA"
    except Exception:  # noqa: BLE001
        pass
    for attr, v in (("sun_elevation", math.radians(el)), ("sun_rotation", math.radians(rot)), ("altitude", 200), ("air_density", st.get("air", 2.0)), ("dust_density", st.get("dust", 3.0))):
        if hasattr(sk, attr):
            setattr(sk, attr, v)
    t.links.new(sk.outputs[0], bg.inputs[0]); bg.inputs[1].default_value = st.get("sky_strength", .35)
    if st.get("fog", .004):
        sc.eevee.volumetric_end = 600; sc.eevee.volumetric_tile_size = "8"
        vs_ = t.nodes.new("ShaderNodeVolumePrincipled"); vs_.inputs["Density"].default_value = st.get("fog", .004); vs_.inputs["Color"].default_value = (*st.get("fog_color", (.8, .7, .6)), 1)
        t.links.new(vs_.outputs[0], t.nodes["World Output"].inputs["Volume"])
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = st.get("sun_energy", 4); sun.color = st.get("sun_color", (1, .78, .55)); sun.angle = math.radians(2)
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(90 - el), 0, math.radians(rot + 90))
    if st.get("moon"):
        mx, my, mz, mr = st["moon"]; bpy.ops.mesh.primitive_uv_sphere_add(radius=mr, location=(mx, my, mz)); mo = bpy.context.object
        em = bpy.data.materials.new("moonE"); em.use_nodes = True; tt = em.node_tree; tt.nodes.clear(); oo = tt.nodes.new("ShaderNodeOutputMaterial"); ee = tt.nodes.new("ShaderNodeEmission")
        ee.inputs[0].default_value = (1, .95, .82, 1); ee.inputs[1].default_value = st.get("moon_strength", 6); tt.links.new(ee.outputs[0], oo.inputs[0]); mo.data.materials.append(em)
    c = st.get("camera", {}); cam = bpy.data.cameras.new("c"); cam.lens = c.get("lens", 35); co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
    co.location = c.get("loc", (0, -9, 1.4)); co.rotation_euler = (Vector(c.get("look", (0, 0, 1.2))) - co.location).to_track_quat("-Z", "Y").to_euler()
    if c.get("focus"):
        cam.dof.use_dof = True; cam.dof.focus_distance = c["focus"]; cam.dof.aperture_fstop = c.get("fstop", 2.8)
    sc.render.resolution_x, sc.render.resolution_y = st.get("size", (1920, 1080))
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    sc.view_settings.look = "None"; sc.render.image_settings.color_depth = "8"; sc.render.image_settings.color_mode = "RGB"
    set_samples(st.get("samples", 64)); sc.render.filepath = SP["out"] + "_000_color.png"; bpy.ops.render.render(write_still=True)


def main():
    if SP.get("stage"):
        return stage()
    if SP.get("set"):
        return render_set()
    setup(); print("FIG_ENGINE", ENGINE); nm = normal_material(); vl = sc.view_layers[0]; out = SP["out"]; samples = SP.get("samples", 48)
    cy = SP.get("cycle"); N = cy.get("frames", 8) if cy else 1
    r0 = eval_body({"lift": 0, "aims": []}); rest_hands(*r0[1:]); ZR[0] = r0[1][:, 2].copy()
    pn = "run" if cy else (SP["pose"] if isinstance(SP["pose"], str) else SP["pose"].get("hands_of", "stand"))
    HANDS[:] = POSE_HANDS.get(pn, ("relax", "relax"))
    for k in range(N):
        pose = run_pose(k / N, cy.get("stride", .34)) if cy else (SP["pose"] if isinstance(SP["pose"], dict) else POSES[SP["pose"]])
        me, W, segs, names, lab = eval_body(pose)
        dress(me, W, segs, names, lab, SP.get("costume", []), 1.0 if cy else SP.get("swing", 0.0))
        tag = f"{out}_{k:03d}"
        vl.material_override = None; set_samples(samples); sc.render.filepath = tag + "_shade.png"; bpy.ops.render.render(write_still=True)
        vl.material_override = nm; set_samples(8); sc.render.filepath = tag + "_normal.png"; bpy.ops.render.render(write_still=True)
        vl.material_override = None; id_pass(tag + "_id.png")
        for o in TEMP:
            d = o.data
            bpy.data.objects.remove(o, do_unlink=True)
        TEMP.clear()


main()
