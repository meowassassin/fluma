"""물리 데모 — MuJoCo 가 계산한 도미노 · 공 움직임을 Blender 물체에 입혀 렌더한다(engine/craft/physics.py)"""
import fluma3d as F


def build(ctx):
    F.world_gradient("#1d1b33", "#0b0b12", 1.0)
    F.studio_lights(rim=ctx.colors.get("accent", "#8b80ff"))
    F.floor("#15151c", rough=0.5)
    objs = {}
    for i in range(13):
        objs[f"d{i}"] = F.rounded_box(0.06, 0.5, 0.24, radius=0.012, material=F.mat_plastic("#8B80FF" if i % 2 == 0 else "#B9B2FF", rough=0.3))
    objs["ball"] = F.sphere(0.1, material=F.mat_plastic("#FF9A3C", rough=0.25))
    F.physics(ctx.args["physics"], objs)
    cam = F.camera(lens=50, loc=(-1.9, -3.2, 1.25), target=(1.0, 0, 0.15), fstop=4.0)
    F.dolly(cam, (0.4, -3.0, 1.0), start=0.0, end=ctx.sec)
