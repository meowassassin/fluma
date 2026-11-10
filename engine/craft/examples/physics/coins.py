"""동전이 병에 쏟아져 차오른다 — 2D(평면) 장면. dm_control.mjcf 로 동전 count 개를 흩뿌려 조립"""
from dm_control import mjcf


def planar(body):
    """평면 안에서만: 가로 · 세로로 미끄러지고 화면 축으로만 돈다"""
    body.add("joint", type="slide", axis=[1, 0, 0]); body.add("joint", type="slide", axis=[0, 0, 1]); body.add("joint", type="hinge", axis=[0, 1, 0])


def scene(args):
    n, bounce = int(args.get("count", 36)), float(args.get("bounce", 0.3))
    r = mjcf.RootElement(model="coins")
    r.option.timestep = 0.002
    r.default.geom.friction = [0.5, 0.01, 0.001]
    r.default.geom.solref = [0.006, max(0.05, 1 - bounce)]
    r.worldbody.add("geom", name="floor", type="plane", size=[10, 1, 0.1])
    for nm, x, z, sx, sz in (("jar_l", -0.62, 0.55, 0.04, 0.55), ("jar_r", 0.62, 0.55, 0.04, 0.55), ("jar_b", 0, 0.03, 0.66, 0.03)):
        b = r.worldbody.add("body", name=nm, pos=[x, 0, z])
        b.add("geom", type="box", size=[sx, 0.3, sz], rgba=[0.85, 0.9, 1, 0.9])
    for i in range(n):
        b = r.worldbody.add("body", name=f"coin{i:02d}", pos=[-0.4 + (i * 0.137) % 0.8, 0, 1.6 + i * 0.09])
        planar(b)
        b.add("geom", type="sphere", size=[0.075], mass=0.02, rgba=[1, 0.78, 0.15, 1])
    return r
