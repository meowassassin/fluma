"""사람 손(뼈 · 근육 모델)이 벽 버튼을 누른다 — 모양은 모델 그대로(F.mjcf_build). 모델은 1.5m 높이라 offset 으로 원점 근처로 옮겨 조명 · 카메라를 맞춘다
확인(2026-11-10): 처음 닿는 것 = 기대한 손끝 · 시작 겹침 없음 · 파고듦 2mm 안
  python3 engine/craft/adapters/blender.py engine/craft/examples/physics/myo_bell_view.py --physics engine/craft/examples/physics/myo_bell.py --args '{"bx":-0.217,"by":-0.66,"bz":1.526}' \
    --expect '[{"touch":"button","by":"distph2_r"}]' --anim --sec 2.2 --poses '[{"t": 0}, {"t": 0.35, "joints": {"mcp[345]_flexion_r": 1.45, "pm[345]_flexion_r": 1.5, "md[345]_flexion_r": 1.1, "cmc_flexion_r": 0.5, "mp_flexion_r": 0.6, "ip_flexion_r": -0.3}}, {"t": 0.9, "ik": [{"site": "IFtip_r", "to": [-0.217, -0.652, 1.526]}]}, {"t": 1.15, "ik": [{"site": "IFtip_r", "to": [-0.217, -0.667, 1.526]}]}, {"t": 1.45, "ik": [{"site": "IFtip_r", "to": [-0.217, -0.645, 1.526]}]}, {"t": 1.9, "back": 1}]'
"""
import fluma3d as F

OFF = (0.217, 0.667, -1.45)      # 버튼이 원점 근처(0, 0, 0.076)에 오도록


def build(ctx):
    F.world_gradient("#26233f", "#0d0d16", 1.0)
    F.studio_lights(rim=ctx.colors.get("accent", "#8b80ff"))
    objs = F.mjcf_build(ctx.args["physics"], colors={"*_r": "#F1ECE4", "button": "#FF5A4F", "wall": "#3A3B4E"})
    F.physics(ctx.args["physics"], objs, offset=OFF)
    cam = F.camera(lens=50, loc=(-0.32, 0.12, 0.16), target=(0.0, 0.03, 0.07), fstop=4.0)
    F.spring_camera(cam, [(0.0, (-0.32, 0.12, 0.16)), (0.8, (-0.26, 0.06, 0.12))], sec=ctx.sec, stiffness=6, damping=0.95,
                    look=[(0.0, (0.0, 0.05, 0.07)), (0.8, (0.0, 0.01, 0.075))])
