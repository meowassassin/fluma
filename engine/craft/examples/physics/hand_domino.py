"""손(menagerie Shadow Hand, Apache-2.0)이 손끝으로 첫 도미노를 민다 — 손은 '팔'(움직이는 받침: 앞뒤 · 좌우 · 위아래 미끄럼 + 위치 작동기)에 달려
자세 키(poses · IK)대로 움직이고, 물리는 닿은 뒤의 반응만 계산한다. 중력 보정(gravcomp)으로 손가락이 처지지 않는다.
도미노 접촉은 손 모델과 같은 단단함(solref 0.005), 질량은 나무 도미노(약 60g)."""
from pathlib import Path

from dm_control import mjcf

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
HAND = ROOT / "data" / "assets" / "mujoco" / "menagerie" / "shadow_hand" / "right_hand.xml"   # python3 engine/craft/physics.py fetch menagerie/shadow_hand


def scene(args):
    if not HAND.exists():
        raise RuntimeError("손 모델이 없습니다 — python3 engine/craft/physics.py fetch menagerie/shadow_hand")
    r = mjcf.RootElement(model="hand_domino")
    r.option.timestep = 0.002
    r.option.cone, r.option.impratio = "elliptic", 10                       # 손 모델이 권하는 접촉 설정
    r.worldbody.add("geom", name="floor", type="plane", size=[3, 3, 0.1], friction=[0.6, 0.01, 0.001], solref=[0.005, 1])
    arm = r.worldbody.add("body", name="arm", pos=[0, 0, float(args.get("hand_z", 0.16))], gravcomp=1)
    for ax, nm in (([1, 0, 0], "arm_x"), ([0, 1, 0], "arm_y"), ([0, 0, 1], "arm_z")):
        arm.add("joint", name=nm, type="slide", axis=ax, range=[-0.3, 0.3], damping=40, armature=0.5)
        r.actuator.add("position", name=nm, joint=nm, kp=3000, kv=200, ctrlrange=[-0.3, 0.3])
    arm.add("geom", type="sphere", size=[0.01], mass=0.5, contype=0, conaffinity=0, rgba=[0, 0, 0, 0])
    h = mjcf.from_path(str(HAND))
    for b in h.find_all("body"):
        b.gravcomp = 1                                                       # 손가락이 중력에 처지지 않게(사람 손은 근육이 받친다)
    mount = arm.add("site", name="mount", quat=[0, 1, 0, 0])                # 손바닥이 아래를 본다
    mount.attach(h)
    n, gap, x0 = int(args.get("count", 10)), float(args.get("gap", 0.06)), float(args.get("x0", 0.52))
    for i in range(n):
        b = r.worldbody.add("body", name=f"d{i}", pos=[x0 + i * gap, 0.033, 0.05])
        b.add("freejoint")
        b.add("geom", type="box", size=[0.008, 0.035, 0.05], mass=0.06, rgba=[0.55, 0.5, 1, 1], friction=[0.4, 0.01, 0.001], solref=[0.005, 1])
    return r
