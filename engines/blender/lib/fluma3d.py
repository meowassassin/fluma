"""fluma3d — 에이전트가 영상마다 직접 쓰는 Blender 스크립트용 도구 모음 (Blender 5.x · bpy).

스크립트 모양 (compositions/<id>/blender/<이름>.py):

    import fluma3d as F

    def build(ctx):                      # ctx: sec, fps, w, h, transparent, draft, colors{bg,accent,text,surface,muted}, text, fonts
        F.world_hdri("studio_small_09", strength=1.0)        # 실제 스튜디오 반사 (Poly Haven CC0, 처음 한 번 받음)
        F.studio_lights(rim=ctx.colors["accent"])
        body = F.rounded_box(1.6, 3.2, 0.18, radius=0.22, material=F.mat_metal("#C9CCD3", rough=0.18))
        F.pop_in(body, at=0.0, dur=0.6)
        F.turntable(body, deg=40)
        F.camera(lens=60, loc=(0, -9, 1.2), target=(0, 0, 0), fstop=2.8)
        F.glow(0.3)

실행: python3 scripts/blender_run.py <id> compositions/<id>/blender/<이름>.py --name <이름> [--sec 3] [--size 1080x1080] [--transparent] [--draft]
→ public/elements/<id>/<이름>/f0001.png … (+ meta.json) → scene.js 에서 K.seq 로 얹음.
장면 전체를 3D 로: 콘티 장면에 "engine": "blender", "template": "Studio3D", "blender": "compositions/<id>/blender/<이름>.py"
"""
import math
import os

import bpy
from mathutils import Vector

CACHE = os.environ.get("FL_CACHE", os.path.join(os.path.dirname(__file__), "..", "cache"))
FONTS = os.environ.get("FL_FONTS", "")
_FPS = [30]


# ---------- 색 ----------
def rgb(h, a=1.0):
    """#RRGGBB → 선형 RGBA (Blender 재질 · 조명용)"""
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (a,)


# ---------- 장면 ----------
def reset(w=1080, h=1080, fps=30, sec=3.0, transparent=True, draft=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.fps = fps
    _FPS[0] = fps
    sc.frame_start, sc.frame_end = 1, max(1, round(sec * fps))
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    ee = sc.eevee
    ee.taa_render_samples = 16 if draft else 32          # 움직이는 영상은 32 로 충분 (정지 화면 품질과 거의 같음)
    # 그림자 광선 1 · 단계 6, 빠른 간접광: 화질 차이는 작고 프레임당 시간은 크게 줄어듦 (내장 GPU 에서도 1080×1920 이 몇 초)
    for a, v in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 1), ("shadow_step_count", 6), ("use_fast_gi", True),
                 ("ray_tracing_method", "SCREEN"), ("use_volumetric_shadows", True)):
        if hasattr(ee, a):
            try:
                setattr(ee, a, v)
            except (TypeError, AttributeError):
                pass
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.render.use_motion_blur = not draft
    return sc


def use_cycles(samples=None):
    """Cycles(경로 추적)로 전환: 그림자 전용 바닥 · 진짜 굴절 유리 · 부드러운 간접광. EEVEE 보다 느리지만 더 사실적.
    GPU(OptiX · CUDA · HIP · Metal)가 있으면 쓰고, 없으면 CPU + 노이즈 제거"""
    sc = bpy.context.scene
    if sc.render.engine == "CYCLES":
        return
    draft = sc.eevee.taa_render_samples <= 16
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples or (24 if draft else 64)
    cy.use_denoising = True
    cy.use_adaptive_sampling = True
    cy.max_bounces, cy.transmission_bounces, cy.glossy_bounces = 8, 8, 4
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "METAL"):   # oneAPI 는 드라이버에 따라 실패가 잦아 제외 (CPU 로)
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == kind
                    cy.device = "GPU"
                    break
            except TypeError:
                continue
    except Exception:  # noqa: BLE001
        pass


def frame(sec):
    return max(1, round(sec * _FPS[0]) + 1)


# ---------- 환경 · 조명 ----------
def world_hdri(name="studio_small_09", strength=1.0, rotate=0.0, backdrop=None, res="1k"):
    """Poly Haven(CC0) HDRI 로 실제 같은 반사 · 조명. 실행기가 렌더 전에 받아 engines/blender/cache/hdri 에 둔다 (Blender 안에서는 네트워크 차단).
    backdrop: 카메라에 보이는 배경색 (#hex). None 이면 HDRI 가 그대로 보임. 투명 요소(--transparent)면 배경은 어차피 투명.
    추천: studio_small_09 · studio_small_03 · photo_studio_loft_hall · brown_photostudio_02 · kloofendal_48d_partly_cloudy_puresky · empty_warehouse_01"""
    path = os.path.join(CACHE, "hdri", f"{name}_{res}.hdr")
    if not os.path.exists(path):
        raise RuntimeError(f"HDRI 없음: {name}_{res} — 스크립트에 world_hdri(\"{name}\") 처럼 이름을 글자 그대로 쓰면 실행기가 미리 받습니다")
    w = bpy.data.worlds.new("hdri"); bpy.context.scene.world = w; w.use_nodes = True
    nt = w.node_tree; bg = nt.nodes["Background"]; out = nt.nodes["World Output"]
    env = nt.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(path, check_existing=True)
    mp, tc = nt.nodes.new("ShaderNodeMapping"), nt.nodes.new("ShaderNodeTexCoord")
    mp.inputs["Rotation"].default_value[2] = math.radians(rotate)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = strength
    if backdrop:   # 반사 · 조명은 HDRI, 카메라에 보이는 배경은 단색 (Light Path 의 카메라 광선)
        lp, mix, flat = nt.nodes.new("ShaderNodeLightPath"), nt.nodes.new("ShaderNodeMixShader"), nt.nodes.new("ShaderNodeBackground")
        flat.inputs["Color"].default_value = rgb(backdrop)
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"]); nt.links.new(bg.outputs[0], mix.inputs[1])
        nt.links.new(flat.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return w


def world_sky(sun_elevation=35, sun_rotation=40, strength=0.6):
    """Blender 물리 하늘 (네트워크 없이). 야외 · 자연광 느낌"""
    w = bpy.data.worlds.new("sky"); bpy.context.scene.world = w; w.use_nodes = True
    nt = w.node_tree; sky = nt.nodes.new("ShaderNodeTexSky")
    for a, v in (("sun_elevation", math.radians(sun_elevation)), ("sun_rotation", math.radians(sun_rotation))):
        if hasattr(sky, a):
            setattr(sky, a, v)
    nt.links.new(sky.outputs["Color"], nt.nodes["Background"].inputs["Color"])
    nt.nodes["Background"].inputs["Strength"].default_value = strength
    return w


def world_gradient(top="#2A2F45", bottom="#0B0D14", strength=1.0):
    w = bpy.data.worlds.new("grad"); bpy.context.scene.world = w; w.use_nodes = True
    nt = w.node_tree; tc, sep, ramp = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0]); nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = rgb(bottom), rgb(top)
    nt.links.new(ramp.outputs["Color"], nt.nodes["Background"].inputs["Color"]); nt.nodes["Background"].inputs["Strength"].default_value = strength
    return w


def area_light(loc, target=(0, 0, 0), energy=500, size=3.0, color="#FFFFFF", name="L", spread=180):
    """spread(도): 빛이 퍼지는 각도. 좁히면 바닥 · 벽에 번지지 않고 물체만 비춤"""
    L = bpy.data.lights.new(name, "AREA"); L.energy, L.size, L.color = energy, size, rgb(color)[:3]
    L.spread = math.radians(spread)
    o = bpy.data.objects.new(name, L); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def studio_lights(key="#FFF4E8", rim="#7AA2FF", fill="#DDE6FF", power=1.0, target=(0, 0, 0)):
    """키(위 왼쪽 큰 소프트박스) · 림(뒤 강조색, 윤곽) · 필(앞 오른쪽 약하게) — 제품 사진 조명.
    림은 물체 높이에서 좁게(28°) 비춰 바닥 · 벽에 색 얼룩이 생기지 않게. target = 주인공 물체의 가운데"""
    return [area_light((-4, -4.5, 5), target, 900 * power, 4, key, "key"),
            area_light((3.5, 4.5, target[2] + 0.6), target, 1100 * power, 2.5, rim, "rim", spread=28),
            area_light((6, -7, 3), target, 160 * power, 6, fill, "fill")]


def cyclorama(color="#14161D", rough=0.5, radius=4.0, back=9.0, width=60, height=30):
    """스튜디오 곡면 배경(호리존트): 바닥이 둥글게 벽으로 이어져 지평선이 없음. back = 카메라에서 본 뒤쪽 벽까지 거리(y)"""
    prof = [(-40.0, 0.0), (back - radius, 0.0)]
    for k in range(1, 17):
        a = k / 16 * math.pi / 2
        prof.append((back - radius + radius * math.sin(a), radius - radius * math.cos(a)))
    prof.append((back, height))
    verts, faces = [], []
    for x in (-width / 2, width / 2):
        verts += [(x, y, z) for y, z in prof]
    n = len(prof)
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    me = bpy.data.meshes.new("cyc"); me.from_pydata(verts, [], faces); me.update()
    o = bpy.data.objects.new("cyclorama", me); bpy.context.collection.objects.link(o); o["fl_stage"] = True
    for p in me.polygons:
        p.use_smooth = True
    o.data.materials.append(mat_plastic(color, rough=rough, coat=0))
    return o


def floor(color="#111318", rough=0.45, shadow_only=False, size=40):
    """바닥. shadow_only=True 면 그림자만 받는 투명 바닥 (투명 배경 위 요소에 접지감)"""
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0)); f = bpy.context.object; f["fl_stage"] = True
    if shadow_only:   # 그림자 받는 투명 바닥은 Cycles 만 지원 → 자동 전환
        use_cycles()
        f.is_shadow_catcher = True
    else:
        f.data.materials.append(mat_plastic(color, rough=rough, coat=0))
    return f


# ---------- 재질 (PBR) ----------
def _bsdf(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, m.node_tree.nodes["Principled BSDF"]


def _set(b, **kw):
    names = {"base": "Base Color", "metal": "Metallic", "rough": "Roughness", "coat": "Coat Weight", "coat_rough": "Coat Roughness",
             "trans": "Transmission Weight", "ior": "IOR", "emit_col": "Emission Color", "emit": "Emission Strength",
             "sheen": "Sheen Weight", "aniso": "Anisotropic", "sss": "Subsurface Weight", "spec": "Specular IOR Level"}
    for k, v in kw.items():
        n = names[k]
        if n in b.inputs:
            b.inputs[n].default_value = v


def mat_plastic(color, rough=0.28, coat=0.8, name="plastic"):
    m, b = _bsdf(name); _set(b, base=rgb(color), rough=rough, coat=coat, coat_rough=0.08); return m


def mat_metal(color="#C9CCD3", rough=0.2, brushed=False, name="metal"):
    m, b = _bsdf(name); _set(b, base=rgb(color), metal=1.0, rough=rough, aniso=0.6 if brushed else 0.0); return m


def mat_glass(tint="#FFFFFF", rough=0.02, ior=1.45, name="glass", solid=True):
    """투명 유리. EEVEE 는 재질마다 레이트레이싱 굴절을 켜야 뒤(안쪽 물체 · 배경)가 비쳐 보인다 — 안 켜면 흰 덩어리.
    solid=True: 속이 찬 물체(구 · 상자), False: 얇은 판(화면 덮개 · 창)"""
    m, b = _bsdf(name); _set(b, base=rgb(tint), trans=1.0, rough=rough, ior=ior)
    for a, v in (("use_raytrace_refraction", True), ("use_screen_refraction", True), ("thickness_mode", "SPHERE" if solid else "SLAB"),
                 ("surface_render_method", "DITHERED")):
        if hasattr(m, a):
            try:
                setattr(m, a, v)
            except (TypeError, ValueError):
                pass
    return m


def mat_shell(tint="#FFFFFF", alpha=0.16, rough=0.04, name="shell"):
    """투명 외피 — 안에 든 물체(빛나는 심 · 부품)가 비쳐 보여야 할 때. 반사 · 코팅은 유리처럼, 속은 반투명 블렌딩.
    (EEVEE 의 mat_glass 굴절은 같은 유리 안에 든 물체를 못 본다 → 흰 덩어리. 이럴 땐 이것)"""
    m, b = _bsdf(name); _set(b, base=rgb(tint), rough=rough, coat=1.0, coat_rough=0.03, spec=0.8)
    if "Alpha" in b.inputs:
        b.inputs["Alpha"].default_value = alpha
    for a, v in (("surface_render_method", "BLENDED"), ("use_transparency_overlap", True), ("use_backface_culling", False)):
        if hasattr(m, a):
            try:
                setattr(m, a, v)
            except (TypeError, ValueError):
                pass
    return m


def mat_frosted(tint="#FFFFFF", name="frosted"):
    return mat_glass(tint, rough=0.35, name=name)


def mat_clay(color="#E8E2D6", name="clay"):
    m, b = _bsdf(name); _set(b, base=rgb(color), rough=0.75, sss=0.05); return m


def mat_emissive(color, strength=6.0, name="emit"):
    m, b = _bsdf(name); _set(b, base=rgb(color), emit_col=rgb(color), emit=strength); return m


def mat_gradient(c1, c2, axis="Z", name="grad", rough=0.3):
    """두 색 그라데이션 플라스틱 (아래 c1 → 위 c2). 축은 물체 자신의 축: 보통 Z, text3d · svg3d 는 세워 놓았으므로 axis="Y" """
    m, b = _bsdf(name); nt = m.node_tree
    tc, sep, ramp = nt.nodes.new("ShaderNodeTexCoord"), nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0]); nt.links.new(sep.outputs[axis], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = rgb(c1), rgb(c2)
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"]); _set(b, rough=rough, coat=0.6)
    return m


def mat_image(path, emit=0.9, rough=0.25, name="img"):
    """이미지(앱 화면 캡처 · 사진 · 로고)를 붙인 재질. emit>0 이면 화면처럼 스스로 빛남. 상자 앞면에 쓰려면 image_plane 이 더 정확"""
    m, b = _bsdf(name); nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(path, check_existing=True)
    nt.links.new(tex.outputs["Color"], b.inputs["Base Color"]); _set(b, rough=rough, coat=0.5)
    if emit:
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"]); _set(b, emit=emit)
    return m


# ---------- 모양 ----------
def _finish(o, material=None, smooth=True, bevel=0.0, segments=5, subdiv=0):
    bpy.context.view_layer.objects.active = o
    if bevel:
        md = o.modifiers.new("bevel", "BEVEL"); md.width, md.segments, md.limit_method = bevel, segments, "ANGLE"
    if subdiv:
        md = o.modifiers.new("sub", "SUBSURF"); md.levels = md.render_levels = subdiv
    if smooth and o.type == "MESH":
        for p in o.data.polygons:
            p.use_smooth = True
    if material:
        o.data.materials.append(material)
    return o


def rounded_box(w, h, d, radius=0.15, material=None, loc=(0, 0, 0)):
    """둥근 모서리 상자 (폰 · 카드 · 버튼 · 블록). w=가로 h=세로(z) d=두께(y)"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object
    o.scale = (w, d, h); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return _finish(o, material, bevel=min(radius, w / 2.01, h / 2.01, d / 2.01), segments=8)


def sphere(r=1.0, material=None, loc=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=64, ring_count=32, location=loc)
    return _finish(bpy.context.object, material)


def torus(major=1.0, minor=0.15, material=None, loc=(0, 0, 0), rot=(90, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=96, minor_segments=24, location=loc,
                                     rotation=tuple(math.radians(a) for a in rot))
    return _finish(bpy.context.object, material)


def stage(*objs):
    """무대 표시: 받침 · 바닥 · 배경판처럼 '물체가 아닌 것'. 림 라이트(강조색 윤곽)가 비추지 않아 색 얼룩이 생기지 않음"""
    for o in objs:
        o["fl_stage"] = True
    return objs[0] if len(objs) == 1 else objs


def cylinder(r=0.5, depth=1.0, material=None, loc=(0, 0, 0), rot=(0, 0, 0), bevel=0.04):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, vertices=96, location=loc, rotation=tuple(math.radians(a) for a in rot))
    return _finish(bpy.context.object, material, bevel=bevel, segments=4)


def image_plane(path, width=1.5, loc=(0, 0, 0), emit=0.9, radius=0.0):
    """이미지를 비율 그대로 판에 붙임 (정면 = 카메라 -Y). 폰 화면이면 rounded_box 몸체 앞에 loc 를 살짝 앞으로"""
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=(math.radians(90), 0, 0)); o = bpy.context.object
    o.scale = (width, width * h / max(w, 1), 1); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat_image(path, emit=emit))
    o["fl_img"] = (width, width * h / max(w, 1), w, h)      # 판 크기 · 이미지 픽셀 → anchor_on_image 가 씀
    if radius:   # 모서리 둥글게 (꼭짓점 베벨)
        md = o.modifiers.new("round", "BEVEL"); md.affect, md.width, md.segments = "VERTICES", radius, 8
    return o


def font(weight="Black"):
    for n in (f"Pretendard-{weight}.otf", "Pretendard-Bold.otf", "Pretendard-Regular.otf"):
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return bpy.data.fonts.load(p, check_existing=True)
    return None


def text3d(body, size=1.0, depth=0.25, bevel=0.03, material=None, weight="Black", loc=(0, 0, 0), align="CENTER", spacing=1.04, max_width=None):
    """입체 글자 (한글 Pretendard). 정면(카메라 -Y)을 보게 세움. max_width 를 주면 그 폭 안으로 줄임"""
    cu = bpy.data.curves.new("t", "FONT"); cu.body = body; cu.size = size; cu.extrude = depth
    cu.bevel_depth, cu.bevel_resolution = bevel, 4
    cu.align_x, cu.align_y, cu.space_character = align, "CENTER", spacing
    f = font(weight)
    if f:
        cu.font = f
    o = bpy.data.objects.new("t", cu); bpy.context.collection.objects.link(o)
    o.location = loc; o.rotation_euler = (math.radians(90), 0, 0)
    if material:
        o.data.materials.append(material)
    if max_width:
        bpy.context.view_layer.update()
        if o.dimensions.x > max_width:
            s = max_width / o.dimensions.x; o.scale = (s, s, s)
    return o


def svg3d(path, depth=0.12, size=3.0, material=None):
    """SVG(로고 · 아이콘)를 입체로. size = 가장 긴 변 길이"""
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=path)
    objs = [o for o in bpy.data.objects if o not in before and o.type == "CURVE"]
    root = bpy.data.objects.new("svg", None); bpy.context.collection.objects.link(root)
    for o in objs:
        o.data.extrude = depth / 100; o.data.bevel_depth = depth / 400; o.parent = root
        if material:
            o.data.materials.clear(); o.data.materials.append(material)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if pts:
        mn = Vector((min(p.x for p in pts), min(p.y for p in pts), 0)); mx = Vector((max(p.x for p in pts), max(p.y for p in pts), 0))
        k = size / max(mx.x - mn.x, mx.y - mn.y, 1e-6)
        for o in objs:
            o.location = (o.location - (mn + mx) / 2) * k; o.scale = tuple(x * k for x in o.scale)
    root.rotation_euler = (math.radians(90), 0, 0)
    return root


def group(*objs, name="g"):
    """여러 오브젝트를 한 덩어리로 (함께 움직이게)"""
    e = bpy.data.objects.new(name, None); bpy.context.collection.objects.link(e)
    for o in objs:
        o.parent = e
    return e


def import_model(path, size=None, loc=(0, 0, 0), ground=False):
    """glTF(.glb/.gltf) · OBJ · FBX 모델 불러오기 (compositions/<id>/blender/assets/ 에 둔 모델 — scripts/asset3d.py fetch).
    size = 가장 긴 변 길이로 맞춤. ground=True 면 발(가장 아래)이 loc 의 z(바닥)에 닿게 — 동물 · 사람 · 서 있는 사물"""
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    try:
        from guard import trusted   # Blender 내장 가져오기가 환경 변수를 만지는 동안만 허용
    except ImportError:
        import contextlib
        trusted = contextlib.nullcontext
    with trusted():
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=path)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=path)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        else:
            raise ValueError(f"모델 형식 미지원: {ext}")
    objs = [o for o in bpy.data.objects if o not in before]
    root = group(*[o for o in objs if o.parent is None], name="model")
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    if pts and size:
        span = max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3))
        k = size / max(span, 1e-6); root.scale = (k, k, k)
        mid = Vector([(max(p[i] for p in pts) + min(p[i] for p in pts)) / 2 for i in range(3)]) * k
        if ground:
            mid.z = min(p[2] for p in pts) * k
        root.location = Vector(loc) - mid
    else:
        root.location = loc
    return root


def actions():
    """불러온 모델들이 가진 동작 이름 (예: Fox → Survey · Walk · Run)"""
    return [a.name for a in bpy.data.actions]


def play(model, action=None, speed=1.0, start=0.0, end=None):
    """import_model 로 불러온 리깅 모델(동물 · 사람 · 기계)의 동작을 [start, end] 초 동안 반복 재생.
    action = 동작 이름 일부(대소문자 무시, 예 "walk"). 없으면 첫 동작. speed = 재생 속도(2.0 = 두 배 빠르게).
    걷는 방향으로 실제로 이동시키려면 F.key(model, "location", …) 를 함께 쓴다(발이 미끄러지지 않게 speed 로 보폭을 맞춘다)."""
    arms = [o for o in [model, *model.children_recursive] if o.type == "ARMATURE"]
    if not arms:
        raise ValueError("뼈대(armature)가 없는 모델이라 동작을 재생할 수 없습니다")
    acts = list(bpy.data.actions)
    if not acts:
        raise ValueError("이 모델에는 동작이 없습니다")
    pick = next((a for a in acts if action and action.lower() in a.name.lower()), None) if action else acts[0]
    if pick is None:
        raise ValueError(f"동작 '{action}' 없음 — 있는 동작: {', '.join(a.name for a in acts)}")
    sc = bpy.context.scene
    f0 = frame(start)
    f1 = frame(end) if end is not None else sc.frame_end
    a0, a1 = pick.frame_range
    length = max(1.0, (a1 - a0) / max(0.05, speed))
    for arm in arms:
        ad = arm.animation_data_create()
        for t in list(ad.nla_tracks):
            ad.nla_tracks.remove(t)
        ad.action = None
        tr = ad.nla_tracks.new()
        tr.name = "play"
        strip = tr.strips.new(pick.name, int(f0), pick)
        try:   # Blender 4.4+ 슬롯 동작: 뼈대 슬롯을 맞춰야 재생된다
            if getattr(pick, "slots", None) and len(pick.slots):
                strip.action_slot = next((s for s in pick.slots if s.target_id_type == "OBJECT"), pick.slots[0])
        except (AttributeError, TypeError):
            pass
        strip.extrapolation = "HOLD"
        strip.scale = 1.0 / max(0.05, speed)
        strip.repeat = max(1.0, (f1 - f0 + 1) / length)
    return pick.name


# ---------- 움직임 ----------
def key(obj, path, sec, value, ease="BEZIER"):
    """sec 초에 값 고정. ease: BEZIER(부드럽게) · BACK(살짝 넘었다 돌아옴) · EXPO(빠르게 와서 천천히) · ELASTIC · BOUNCE · LINEAR"""
    setattr(obj, path, value)
    obj.keyframe_insert(path, frame=frame(sec))
    ad = obj.animation_data
    act = ad.action if ad else None
    curves = []
    if act is not None:
        if hasattr(act, "fcurves"):
            curves = list(act.fcurves)
        elif hasattr(act, "layers"):   # Blender 5 레이어 액션
            for ly in act.layers:
                for st in ly.strips:
                    for cb in getattr(st, "channelbags", []):
                        curves += list(cb.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            if abs(kp.co[0] - frame(sec)) < 0.5:
                kp.interpolation = ease if ease in ("BACK", "EXPO", "ELASTIC", "BOUNCE", "LINEAR", "BEZIER", "SINE", "CUBIC", "QUART") else "BEZIER"
                kp.easing = "EASE_OUT"


def appear(obj, at):
    """at 초 전에는 렌더에서 숨김 (자식까지). 등장 효과(pop_in · drop_in · rise_in)가 at>0 이면 자동으로 부른다 —
    그러지 않으면 시작 전에도 처음 자세(작게 · 아래)로 이미 보인다"""
    if at <= 0:
        return
    for o in [obj, *obj.children_recursive]:
        o.hide_render = True
        o.keyframe_insert("hide_render", frame=max(1, frame(at) - 1))
        o.hide_render = False
        o.keyframe_insert("hide_render", frame=frame(at))
        if o.animation_data and o.animation_data.action:
            for fc in _fcurves(o.animation_data.action):
                if fc.data_path == "hide_render":
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"


def _fcurves(act):
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []
    for ly in getattr(act, "layers", []):
        for st in ly.strips:
            for cb in getattr(st, "channelbags", []):
                out += list(cb.fcurves)
    return out


def pop_in(obj, at=0.0, dur=0.55, from_scale=0.0):
    appear(obj, at)
    s = tuple(obj.scale)
    key(obj, "scale", at, tuple(x * from_scale + 1e-3 for x in s), "BACK")
    key(obj, "scale", at + dur, s, "BACK")


def drop_in(obj, at=0.0, dur=0.6, height=3.0):
    appear(obj, at)
    p = tuple(obj.location)
    key(obj, "location", at, (p[0], p[1], p[2] + height), "BOUNCE")
    key(obj, "location", at + dur, p, "BOUNCE")


def rise_in(obj, at=0.0, dur=0.7, depth=1.5):
    appear(obj, at)
    p = tuple(obj.location)
    key(obj, "location", at, (p[0], p[1], p[2] - depth), "EXPO")
    key(obj, "location", at + dur, p, "EXPO")


def turntable(obj, deg=30, start=0.0, end=None, axis=2):
    end = end if end is not None else (bpy.context.scene.frame_end - 1) / _FPS[0]
    r = list(obj.rotation_euler); r0 = list(r); r0[axis] -= math.radians(deg / 2); r1 = list(r); r1[axis] += math.radians(deg / 2)
    key(obj, "rotation_euler", start, tuple(r0), "LINEAR"); key(obj, "rotation_euler", end, tuple(r1), "LINEAR")


def float_idle(obj, amp=0.08, period=2.4):
    """둥둥 떠 있음 (드라이버, 렌더에서도 결정적)"""
    for i, c in enumerate("xyz"):
        if c == "z":
            d = obj.driver_add("location", i).driver
            d.expression = f"{obj.location[i]:.4f} + {amp} * sin(frame / {_FPS[0] * period / math.tau:.4f})"


# ---------- 카메라 · 마무리 ----------
def camera(lens=55, loc=(0, -9, 1.5), target=(0, 0, 0), fstop=0.0, ortho=False, ortho_scale=6.0):
    cd = bpy.data.cameras.new("cam"); cd.lens = lens
    if ortho:
        cd.type, cd.ortho_scale = "ORTHO", ortho_scale
    cam = bpy.data.objects.new("cam", cd); bpy.context.collection.objects.link(cam); bpy.context.scene.camera = cam
    cam.location = loc
    t = bpy.data.objects.new("cam_target", None); bpy.context.collection.objects.link(t); t.location = target
    c = cam.constraints.new("TRACK_TO"); c.target, c.track_axis, c.up_axis = t, "TRACK_NEGATIVE_Z", "UP_Y"
    if fstop:
        cd.dof.use_dof, cd.dof.aperture_fstop, cd.dof.focus_object = True, fstop, t
    return cam


def dolly(cam, to, start=0.0, end=None):
    end = end if end is not None else (bpy.context.scene.frame_end - 1) / _FPS[0]
    key(cam, "location", start, tuple(cam.location), "SINE"); key(cam, "location", end, tuple(to), "SINE")


def glow(strength=0.35, threshold=0.9):
    """컴포지터 글로우 (Blender 5 노드 그룹 방식). 실패하면 조용히 생략"""
    sc = bpy.context.scene
    try:
        ng = bpy.data.node_groups.new("fl_comp", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl, out, g = ng.nodes.new("CompositorNodeRLayers"), ng.nodes.new("NodeGroupOutput"), ng.nodes.new("CompositorNodeGlare")
        for n, v in (("Type", "Fog Glow"), ("Quality", "High"), ("Threshold", threshold), ("Size", 0.5), ("Strength", strength)):
            if n in g.inputs:
                try:
                    g.inputs[n].default_value = v
                except (TypeError, ValueError):
                    pass
        ng.links.new(rl.outputs["Image"], g.inputs["Image"]); ng.links.new(g.outputs["Image"], out.inputs[0])
        if "Alpha" in rl.outputs and len(out.inputs) > 1:
            pass
        sc.compositing_node_group = ng
    except Exception as e:  # noqa: BLE001
        print("[fluma3d] 글로우 생략:", e)


def finalize():
    """렌더 직전 (실행기가 부름): 림 라이트(이름 rim*)는 무대(바닥 · 곡면 배경)를 비추지 않게 — 라이트 링킹.
    강조색 윤곽은 물체에만 생기고 바닥에 색 얼룩이 번지지 않는다."""
    stage = [o for o in bpy.data.objects if o.get("fl_stage")]
    rims = [o for o in bpy.data.objects if o.type == "LIGHT" and o.name.startswith("rim")]
    if not stage or not rims:
        return
    col = bpy.data.collections.new("fl_rim_receivers")
    for o in bpy.data.objects:
        if o.type in ("MESH", "CURVE", "FONT") and not o.get("fl_stage"):
            col.objects.link(o)
    for r in rims:
        try:
            r.light_linking.receiver_collection = col
        except AttributeError:   # 라이트 링킹이 없는 버전: 무대 근처로 빛이 덜 가게 세기만 낮춤
            r.data.energy *= 0.6


_ANCHORS = {}


def anchor(obj, name, offset=(0, 0, 0)):
    """3D 물체의 한 점을 2D 고정점으로 내보낸다 → 프레임마다 화면 위치가 meta.json anchors 에 기록되고,
    scene.js 에서 K.seq(..., { pins: [{ name, el, dx, dy }] }) 로 2D 라벨이 이 점을 정확히 따라다닌다.
    offset: 물체 기준 위치 (예: 기둥 꼭대기 (0, 0, 높이)). 같은 이름이면 덮어씀"""
    _ANCHORS[name] = (obj, Vector(offset))
    return obj


def anchor_on_image(plane, name, px, py):
    """image_plane 위의 이미지 픽셀 (px, py) 를 고정점으로 (예: 캡처 속 버튼 · 가격). 2D 강조가 화면 속 그 자리에 붙는다"""
    pw, ph, iw, ih = plane["fl_img"]
    return anchor(plane, name, offset=((px / iw - 0.5) * pw, (0.5 - py / ih) * ph, 0.005))


def _anchor_positions():
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    out = {}
    for name, (obj, off) in _ANCHORS.items():
        co = world_to_camera_view(sc, sc.camera, obj.matrix_world @ off)
        out[name] = [round(co.x * sc.render.resolution_x, 1), round((1 - co.y) * sc.render.resolution_y, 1), 1 if co.z > 0 else 0]
    return out


def render_sequence(out_dir, pad=4):
    sc = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    track = {n: [] for n in _ANCHORS}
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f); sc.render.filepath = os.path.join(out_dir, f"f{f:0{pad}d}.png")
        bpy.ops.render.render(write_still=True)
        for n, v in _anchor_positions().items():
            track[n].append(v)
    if track:
        import json
        with open(os.path.join(out_dir, "anchors.json"), "w", encoding="utf-8") as fp:
            json.dump(track, fp)


def render_still(path, sec):
    sc = bpy.context.scene
    sc.frame_set(min(sc.frame_end, frame(sec))); sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
