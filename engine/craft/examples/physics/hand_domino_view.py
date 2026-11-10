"""손이 첫 도미노를 민다 — 손 · 도미노 모양은 모델 그대로(F.mjcf_build), 손은 무광 흰색, 도미노는 보라 두 톤
확인(2026-11-10, 애니메이션 원칙 판): 처음 닿는 것 = 검지 끝 · 시작 겹침 없음 · 파고듦 1mm 안 · 다가감 경로가 호(직선에서 14mm)
  python3 engine/craft/adapters/blender.py engine/craft/examples/physics/hand_domino_view.py --physics engine/craft/examples/physics/hand_domino.py \
    --args '{"x0":0.52,"hand_z":0.16}' --expect '[{"touch":"d0","by":"rh_ffdistal"}]' --retime '[{"from":1.18,"to":1.55,"speed":0.35}]' \
    --anim --sec 3.0 --fps 30 --poses '[{"t": 0}, {"t": 0.4, "ease": "out", "overlap": 0.08, "joints": {"*MFJ[123]": 1.45, "*RFJ[123]": 1.45, "*LFJ[123]": 1.45, "*THJ4": 1.1, "*THJ1": 0.6, "*FFJ*": 0}}, {"t": 1.0, "ease": "inout", "arc": [0, 0, 0.04], "ik": [{"body": "right_shadow_hand/rh_ffdistal", "to": [0.47, 0.033, 0.12]}]}, {"t": 1.32, "ease": "snap", "anticipate": 0.15, "ik": [{"body": "right_shadow_hand/rh_ffdistal", "to": [0.565, 0.033, 0.085]}]}, {"t": 1.65, "ease": "out", "overshoot": 0.08, "ik": [{"body": "right_shadow_hand/rh_ffdistal", "to": [0.565, 0.033, 0.16]}]}, {"t": 2.15, "ease": "inout", "arc": [0, 0, 0.03], "ik": [{"body": "right_shadow_hand/rh_ffdistal", "to": [0.44, 0.033, 0.15]}]}, {"t": 2.7, "ease": "soft", "back": 1}]'
"""
import fluma3d as F


def build(ctx):
    F.world_gradient("#1d1b33", "#0b0b12", 1.0)
    F.studio_lights(rim=ctx.colors.get("accent", "#8b80ff"))
    F.floor("#15151c", rough=0.5)
    objs = F.mjcf_build(ctx.args["physics"], colors={"right_shadow_hand/*": "#E9E6F2", "d*": "#8B80FF"})
    F.physics(ctx.args["physics"], objs)
    cam = F.camera(lens=40, loc=(0.2, -0.85, 0.42), target=(0.55, 0.03, 0.08), fstop=4.0)
    F.spring_camera(cam, [(0.0, (0.2, -0.85, 0.42)), (1.3, (0.55, -0.9, 0.36))], sec=ctx.sec, stiffness=6, damping=0.95,
                    look=[(0.0, (0.5, 0.03, 0.09)), (1.3, (0.75, 0.03, 0.05))])
