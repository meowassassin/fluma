"""Blender 3D 요소 — 투명 배경 PNG 연속 이미지로 렌더해 다른 장면(HyperFrames 컴포지션의 K.seq)에 얹는다.

종류(SF_KIND): text(입체 글자 등장 · 천천히 회전) · number(3D 숫자가 세어짐) · badge(동전 · 배지에 글자) · orb(유리 구슬 + 금속 고리) · cube(둥근 큐브 탑) · svg(로고 · 아이콘 SVG 를 입체로)
환경변수: SF_OUT(폴더) SF_KIND SF_TEXT SF_COLOR(#hex) SF_SEC(길이) SF_FPS SF_SIZE(정사각 px) SF_SVG(경로) SF_SPIN(1/0) SF_QUALITY(draft|final)
"""
import math
import os
import re

import bpy
from mathutils import Vector

OUT = os.environ["SF_OUT"]
KIND = os.environ.get("SF_KIND", "text")
TEXT = os.environ.get("SF_TEXT", "3D")
COLOR = os.environ.get("SF_COLOR", "#FF5A78")
SEC = float(os.environ.get("SF_SEC", "3"))
FPS = int(os.environ.get("SF_FPS", "30"))
SIZE = int(os.environ.get("SF_SIZE", "720"))
SPIN = os.environ.get("SF_SPIN", "1") == "1"
FINAL = os.environ.get("SF_QUALITY", "final") == "final"
FONTS = os.environ.get("SF_FONTS", "")


def lin(h):
    h = h.lstrip("#")
    return tuple(((c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))) + (1,)


def mat(name, color, metal=0.1, rough=0.25, coat=0.6, transmission=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Coat Weight", coat), ("Transmission Weight", transmission)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    return m


def font():
    for n in ("Pretendard-Black.otf", "Pretendard-Bold.otf"):
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return bpy.data.fonts.load(p, check_existing=True)
    return None


def text_obj(body, size=1.0, depth=0.3, material=None):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body, cu.size, cu.extrude, cu.bevel_depth, cu.bevel_resolution = body, size, depth, depth * 0.2, 4
    cu.align_x, cu.align_y, cu.space_character = "CENTER", "CENTER", 1.05
    f = font()
    if f:
        cu.font = f
    o = bpy.data.objects.new("t", cu)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = (math.radians(90), 0, 0)
    if material:
        o.data.materials.append(material)
    return o


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = SIZE
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, max(1, round(SEC * FPS))
sc.eevee.taa_render_samples = 64 if FINAL else 16
for a, v in (("use_raytracing", True), ("use_shadows", True)):
    if hasattr(sc.eevee, a):
        setattr(sc.eevee, a, v)
sc.view_settings.view_transform = "AgX"
sc.render.use_motion_blur = FINAL

# 조명: 키 · 림 · 필 + 반사용 약한 하늘
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.8, 0.82, 0.86, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
for name, loc, e, col in (("key", (-4, -5, 6), 900, (1, .97, .93)), ("rim", (4, 5, 4), 700, lin(COLOR)[:3]), ("fill", (5, -6, 0), 200, (.9, .95, 1))):
    L = bpy.data.lights.new(name, "AREA"); L.energy, L.size, L.color = e, 4, col
    o = bpy.data.objects.new(name, L); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()

cam_d = bpy.data.cameras.new("c"); cam_d.lens = 70
cam = bpy.data.objects.new("c", cam_d); bpy.context.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -12, 1.2)
cam.rotation_euler = (Vector((0, 0, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()

root = bpy.data.objects.new("root", None); bpy.context.collection.objects.link(root)
acc = mat("acc", lin(COLOR))
n = sc.frame_end

if KIND in ("text", "number"):
    raw = TEXT
    m = re.search(r"\d[\d,]*(?:\.\d+)?", raw) if KIND == "number" else None
    final = raw
    if m:
        d0 = len(m.group(0).split(".")[1]) if "." in m.group(0) else 0
        final = f"{raw[:m.start()]}{float(m.group(0).replace(',', '')):,.{d0}f}{raw[m.end():]}"
    t = text_obj(final, size=1.6, depth=0.4, material=acc); t.parent = root
    bpy.context.view_layer.update()
    s = min(1.0, 4.2 / max(0.01, t.dimensions.x)); t.scale = (s, s, s)
    if m:
        num, pre, post = float(m.group(0).replace(",", "")), raw[:m.start()], raw[m.end():]
        end = max(2, round(min(1.2, SEC * .5) * FPS))

        def upd(scene, *_):
            p = 1 - (1 - min(1, (scene.frame_current - 1) / end)) ** 3
            t.data.body = f"{pre}{num * p:,.{d0}f}{post}"
        bpy.app.handlers.frame_change_pre.append(upd)
elif KIND == "badge":
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=1.8, depth=0.35, rotation=(math.radians(90), 0, 0))
    coin = bpy.context.object; coin.parent = root
    bpy.ops.object.modifier_add(type="BEVEL"); coin.modifiers["Bevel"].width = 0.08; coin.modifiers["Bevel"].segments = 5
    bpy.ops.object.shade_smooth()
    coin.data.materials.append(mat("gold", lin(COLOR), metal=1.0, rough=0.2, coat=0.3))
    t = text_obj(TEXT, size=0.9, depth=0.08, material=mat("ink", (0.95, 0.95, 0.95, 1), rough=0.3)); t.parent = root
    t.location = (0, -0.25, 0)
    bpy.context.view_layer.update(); s = min(1.4, 2.9 / max(0.01, t.dimensions.x)); t.scale = (s, s, s)
elif KIND == "orb":
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1.4); g = bpy.context.object; g.parent = root
    bpy.ops.object.shade_smooth(); g.data.materials.append(mat("glass", (1, 1, 1, 1), metal=0, rough=0.03, coat=0, transmission=1.0))
    bpy.ops.mesh.primitive_torus_add(major_radius=2.0, minor_radius=0.1); r = bpy.context.object; r.parent = root
    r.data.materials.append(mat("ring", lin(COLOR), metal=1.0, rough=0.15)); r.rotation_euler = (math.radians(70), 0, 0)
elif KIND == "cube":
    for k in range(3):
        bpy.ops.mesh.primitive_cube_add(size=1.3 - k * 0.3, location=(0, 0, -1.0 + k * 1.15)); c = bpy.context.object; c.parent = root
        bpy.ops.object.modifier_add(type="BEVEL"); c.modifiers["Bevel"].width = 0.12; c.modifiers["Bevel"].segments = 6
        bpy.ops.object.shade_smooth(); c.data.materials.append(acc if k % 2 == 0 else mat(f"w{k}", (0.92, 0.92, 0.94, 1)))
        c.rotation_euler = (0, 0, math.radians(k * 18))
elif KIND == "svg":
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=os.environ["SF_SVG"])
    objs = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    for o in objs:
        o.data.extrude = 0.004; o.data.bevel_depth = 0.0008
        o.data.materials.clear(); o.data.materials.append(acc); o.parent = root
    bpy.context.view_layer.update()
    xs = [v for o in objs for v in (o.matrix_world @ Vector(c) for c in o.bound_box)]
    if xs:
        mn = Vector((min(v.x for v in xs), min(v.y for v in xs), min(v.z for v in xs))); mx = Vector((max(v.x for v in xs), max(v.y for v in xs), max(v.z for v in xs)))
        span = max(mx.x - mn.x, mx.y - mn.y) or 1
        k = 4.0 / span
        for o in objs:
            o.location = (o.location - (mn + mx) / 2) * k; o.scale = tuple(x * k for x in o.scale)
        root.rotation_euler = (math.radians(90), 0, 0)

# 등장(아래에서 솟으며 커짐) + 천천히 회전
base_rot = tuple(root.rotation_euler)
root.scale = (0.2, 0.2, 0.2); root.location = (0, 0, -1.5); root.keyframe_insert("scale", frame=1); root.keyframe_insert("location", frame=1)
root.scale = (1, 1, 1); root.location = (0, 0, 0)
f_in = max(2, round(0.55 * FPS))
root.keyframe_insert("scale", frame=f_in); root.keyframe_insert("location", frame=f_in)
if SPIN:
    root.rotation_euler = (base_rot[0], base_rot[1], base_rot[2] - math.radians(25)); root.keyframe_insert("rotation_euler", frame=1)
    root.rotation_euler = (base_rot[0], base_rot[1], base_rot[2] + math.radians(25)); root.keyframe_insert("rotation_euler", frame=n)

os.makedirs(OUT, exist_ok=True)
for f in range(1, n + 1):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(OUT, f"f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
print(f"[element] {KIND} {n} frames → {OUT}")
