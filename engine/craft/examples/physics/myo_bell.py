"""사람 손(MyoSuite · myo_sim MyoHand, Apache-2.0)이 검지로 벽 버튼을 누른다 — 근육 대신 관절 위치 구동(position_drive) +
팔 전체를 움직이는 받침(미끄럼 관절) + 중력 보정. 동작은 자세 키(poses · IK), 물리는 버튼이 눌리는 반응만.
버튼: 손가락 방향(-y)으로 0~8mm 들어가는 스프링(감쇠 있어 튀어나오지 않음), 벽과는 서로 닿지 않게(exclude), 접촉은 단단하게(solref 0.005)."""
import warnings

import mujoco


def scene(args):
    warnings.filterwarnings("ignore")
    import myo_sim
    from craft import physics as P
    spec = myo_sim.load_spec("myohand_r")
    P.position_drive(spec, kp=6.0, kv=0.3)
    root = spec.body("myoarm_r_root")
    for ax, nm in (([1, 0, 0], "arm_x"), ([0, 1, 0], "arm_y"), ([0, 0, 1], "arm_z")):
        root.add_joint(name=nm, type=mujoco.mjtJoint.mjJNT_SLIDE, axis=ax, range=[-0.2, 0.2], damping=30, armature=0.2)
        a = spec.add_actuator(name=nm, target=nm, trntype=mujoco.mjtTrn.mjTRN_JOINT)
        a.set_to_position(kp=1500, kv=120)
    for b in spec.bodies:
        b.gravcomp = 1                                       # 손 · 팔이 처지지 않게(사람은 근육이 받친다)
    bx, by, bz = float(args.get("bx", -0.217)), float(args.get("by", -0.66)), float(args.get("bz", 1.52))
    wall = spec.worldbody.add_body(name="wall", pos=[bx, by - 0.025, bz])
    wall.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.06, 0.01, 0.06], rgba=[0.92, 0.92, 0.95, 1], solref=[0.005, 1])
    btn = spec.worldbody.add_body(name="button", pos=[bx, by - 0.007, bz])
    btn.add_joint(name="press", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0, -1, 0], stiffness=30, damping=2.0,
                  range=[0.0, 0.008], limited=mujoco.mjtLimited.mjLIMITED_TRUE, solref_limit=[0.004, 1.0])
    btn.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.016, 0.008, 0], quat=[0.7071, 0.7071, 0, 0], rgba=[1, 0.35, 0.3, 1], mass=0.01, solref=[0.005, 1])
    spec.add_exclude(bodyname1="button", bodyname2="wall")
    return spec
