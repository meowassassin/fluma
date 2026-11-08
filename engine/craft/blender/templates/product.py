"""기본 제품 컷 — 스크립트가 없는 model3d 재료(내장 형태 · SolidCraft 명령 · STEP/OBJ). 부품 재질 · 스튜디오 조명 · 받침 · 자동 구도 · 돌려 보기 · 로고.
args: obj(SolidCraft OBJ 경로, mm) · mats({몸체: {color, roughness, metallic}}) · yaw · pitch · fill · turntable · turns · stage(받침) · bg · logo"""
import math

import bpy
from mathutils import Vector

import fluma3d as F


def build(ctx):
    a = ctx.args
    F.use_quality(ctx)
    F.world_hdri("studio_small_09", strength=0.7, rotate=30)
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=a["obj"], forward_axis="Y", up_axis="Z")
    parts = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    root = bpy.data.objects.new("product", None)
    bpy.context.collection.objects.link(root)
    mats = a.get("mats") or {}
    for o in parts:
        n = o.name.split(".")[0]
        m = mats.get(n) or mats.get("*") or {"color": "#d8dade", "roughness": 0.35, "metallic": 0.0}
        mt = F.mat_metal(m["color"], rough=m.get("roughness", 0.3), name=n) if m.get("metallic", 0) > 0.5 else F.mat_plastic(m["color"], rough=m.get("roughness", 0.35), coat=0.2, name=n)
        o.data.materials.clear()
        o.data.materials.append(mt)
        for pg in o.data.polygons:
            pg.use_smooth = True
        o.parent = root
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in parts for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    k = 5.0 / max(hi - lo)                                    # 가장 긴 변을 5 단위로
    mid = (lo + hi) / 2
    root.scale = (k, k, k)
    root.location = (-mid.x * k, -mid.y * k, -lo.z * k)
    size = (hi - lo) * k
    if a.get("logo"):
        ink = F.mat_plastic(a.get("logo_color", "#f4f4f4"), rough=0.4, name="logo")
        t = F.text3d(str(a["logo"]), size=min(size.x, size.z) * 0.12, depth=0.012, bevel=0.0, material=ink, loc=(0, -size.y / 2 - 0.008, size.z * 0.45))
        t.rotation_euler = (math.radians(90), 0, 0)
        t.parent = root.parent
    if a.get("stage", True):
        F.floor(a.get("floor", "#2b2d33"), rough=0.4, size=80)
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 12, 20), rotation=(math.radians(90), 0, 0))
    bpy.context.object.data.materials.append(F.mat_plastic(a.get("bg", "#16181e"), rough=0.8, coat=0.0, name="wall"))
    c = Vector((0, 0, size.z / 2))
    F.area_light((-7, -7, 11), target=tuple(c), energy=900, size=1.6, color="#fff5ea", name="key")
    F.area_light((7, 3, 6), target=tuple(c), energy=380, size=1.2, color="#d9e4ff", name="rim")
    s = F.area_light((-10, -8, 5), target=tuple(c), energy=180, size=1.0, name="strip")
    s.data.shape, s.data.size, s.data.size_y = "RECTANGLE", 1.0, 14
    yaw, pitch = math.radians(a.get("yaw", 28)), math.radians(a.get("pitch", 16))
    lens = 62.0
    aspect = ctx.w / ctx.h
    reach = max(size.x, size.y) / max(aspect, 1e-3) * 0.62 / max(a.get("fill", 0.8), 0.1)
    d = max(reach, size.z * 0.62 / max(a.get("fill", 0.8), 0.1)) * lens / 36 * 1.6 + 2
    F.camera(lens=lens, loc=tuple(c + Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))) * d), target=tuple(c))
    if a.get("turntable"):
        root.rotation_mode = "XYZ"
        # 회전축이 제품 가운데를 지나게: 받침 빈 객체로 돌린다
        pivot = bpy.data.objects.new("pivot", None)
        bpy.context.collection.objects.link(pivot)
        root.parent = pivot
        turns = float(a.get("turns", 0.25))
        fc = F.key(pivot, "rotation_euler", 0.0, (0, 0, 0), "LINEAR")
        F.key(pivot, "rotation_euler", ctx.sec, (0, 0, 2 * math.pi * turns), "LINEAR")
