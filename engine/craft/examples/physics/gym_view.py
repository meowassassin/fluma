"""Gymnasium 환경(Ant 등)을 굴린 결과를 렌더 — 모양은 모델 그대로(F.mjcf_build), 카메라는 몸통을 스프링으로 따라간다.
  python3 engine/craft/physics.py gym Ant-v5 --policy plan --goals '[{"t":0,"body":"torso","move":[1,0,0],"w":3}]' --visual --out x.traj.json
  python3 engine/craft/adapters/blender.py engine/craft/examples/physics/gym_view.py --traj x.traj.json --anim --sec 4"""
import fluma3d as F


def build(ctx):
    F.world_gradient("#1d1b33", "#0b0b12", 1.0)
    F.studio_lights(rim=ctx.colors.get("accent", "#8b80ff"))
    F.floor("#15151c", rough=0.6, size=200)
    body = ctx.args.get("follow", "torso")
    objs = F.mjcf_build(ctx.args["physics"], colors={"*": ctx.args.get("color", "#8B80FF")})
    F.physics(ctx.args["physics"], objs)
    cam = F.camera(lens=40, loc=(-1.5, -4.5, 2.2), target=(0, 0, 0.4), fstop=0)
    F.spring_camera(cam, [(0.0, body)], sec=ctx.sec, stiffness=float(ctx.args.get("cam_k", 60)), damping=1.0, look=[(0.0, body)], physics=ctx.args["physics"], offset=(-1.5, -4.5, 1.8))
