"""물리로 움직임 계산(engine/craft/physics.py) — MuJoCo 가 있으면 떨어지는 상자 · args 채우기를 확인"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import physics  # noqa: E402

pytest.importorskip("mujoco")

SCENE = """<mujoco><option timestep="0.002"/><worldbody><geom type="plane" size="5 5 .1"/>
<body name="box" pos="0 0 {{height}}"><freejoint/><geom type="box" size=".1 .1 .1" mass="1"/></body></worldbody></mujoco>"""


def test_box_falls_and_rests(tmp_path):
    f = tmp_path / "s.xml"; f.write_text(SCENE)
    r = physics.simulate(f, sec=1.5, fps=30, args={"height": 1.0})
    z = [row[2] for row in r["bodies"]["box"]]
    assert len(z) == 46 and z[0] == pytest.approx(1.0, abs=1e-3)
    assert z[-1] == pytest.approx(0.1, abs=0.02)            # 바닥에 놓임(상자 반 높이)
    assert all(len(row) == 7 for row in r["bodies"]["box"])  # 위치 3 + 쿼터니언 4


def test_missing_arg_is_an_error(tmp_path):
    f = tmp_path / "s.xml"; f.write_text(SCENE)
    with pytest.raises(KeyError):
        physics.simulate(f, sec=0.2, fps=30, args={})


PLANAR = """<mujoco><option timestep="0.002"/><worldbody><geom type="plane" size="5 1 .1"/>
<body name="b" pos="0 0 1"><joint type="slide" axis="1 0 0"/><joint type="slide" axis="0 0 1"/><joint type="hinge" axis="0 1 0"/>
<geom type="box" size=".2 .1 .1" mass="1" rgba="1 0 0 1"/></body></worldbody></mujoco>"""


def test_project2d_ground_and_shape(tmp_path):
    f = tmp_path / "p.xml"; f.write_text(PLANAR)
    r = physics.simulate(f, sec=1.5, fps=30)
    assert r["shapes"]["b"]["type"] == "box" and r["shapes"]["b"]["size"][0] == pytest.approx(0.2)
    p = physics.project2d(r, 1080, 1920, width_m=3.6, x0=0.5, ground=0.75)
    x, y, deg = p["bodies"]["b"][-1]
    assert p["ppm"] == pytest.approx(300)
    assert x == pytest.approx(540, abs=2) and y == pytest.approx(1440 - 0.1 * 300, abs=4) and abs(deg) < 1   # 바닥에 놓임(반 높이 0.1m 위)


def test_spring_follow_settles_on_target():
    seq = physics.spring_follow([(0, 0, 0, 1), (0.2, 100, 50, 1.5)], fps=30, sec=3, stiffness=60, damping=0.8)
    assert seq[0] == [0, 0, 1]
    assert seq[-1][0] == pytest.approx(100, abs=0.5) and seq[-1][2] == pytest.approx(1.5, abs=0.01)
    assert seq[8][0] < 100                                       # 바로 붙지 않고 따라간다


ACT = """<mujoco><option timestep="0.005" gravity="0 0 0"/><worldbody>
<body name="cart" pos="0 0 0"><joint name="x" type="slide" axis="1 0 0" damping="2"/><geom type="box" size=".1 .1 .1" mass="1"/></body></worldbody>
<actuator><motor name="push" joint="x" ctrlrange="-5 5" ctrllimited="true"/></actuator></mujoco>"""


def test_ctrl_schedule_and_planner(tmp_path):
    f = tmp_path / "a.xml"; f.write_text(ACT)
    r = physics.simulate(f, sec=1.0, fps=20, ctrl=[[0, {"push": 5}], [1, {"push": 5}]])
    assert r["bodies"]["cart"][-1][0] > 0.3                       # 시간표대로 밀림
    r = physics.simulate(f, sec=2.0, fps=20, goals=[{"t": 0, "body": "cart", "to": [0.5, 0, 0]}], plan_opts={"samples": 12})
    assert r["bodies"]["cart"][-1][0] == pytest.approx(0.5, abs=0.12)   # 계획기가 목표 자리로


def test_export_visual(tmp_path):
    f = tmp_path / "p.xml"; f.write_text(PLANAR)
    r = physics.simulate(f, sec=0.1, fps=10, visual=tmp_path / "v.visual.json")
    v = json.loads(Path(r["visual"]).read_text())
    assert [g["body"] for g in v["geoms"]] == ["b"] and v["geoms"][0]["type"] == "box"


ARM = """<mujoco><option timestep="0.002" gravity="0 0 0" integrator="implicitfast"/><default><geom solref="0.005 1"/></default><worldbody>
<body name="tip" pos="0 0 0.1"><joint name="x" type="slide" axis="1 0 0" range="-1 1"/><geom type="sphere" size=".02" mass=".1"/></body>
<body name="box" pos="{{bx}} 0 0.1"><freejoint/><geom type="box" size=".03 .03 .03" mass=".05"/></body>
<body name="other" pos="0 0.3 0.1"><joint name="y" type="slide" axis="0 1 0" range="-1 1"/><geom type="sphere" size=".02" mass=".1"/></body></worldbody>
<actuator><position name="x" joint="x" kp="200" kv="10" ctrlrange="-1 1"/><position name="y" joint="y" kp="200" kv="10" ctrlrange="-1 1"/></actuator></mujoco>"""


def test_pose_keys_ik_and_touch_check(tmp_path):
    f = tmp_path / "arm.xml"; f.write_text(ARM)
    poses = [{"t": 0}, {"t": 0.5, "ik": [{"body": "tip", "to": [0.3, 0, 0.1]}]}]
    r = physics.simulate(f, sec=1.5, fps=30, args={"bx": 0.2}, poses=poses, expect=[{"touch": "box", "by": "tip"}])
    assert r["ik_err"][0] < 1e-3
    assert r["contacts"]["first_touch"]["box"][1] == "tip" and not r["contacts"]["warn"]
    assert r["bodies"]["box"][-1][0] > 0.25                       # 손끝(tip)이 상자를 밀었다
    assert abs(r["bodies"]["other"][-1][1] - 0.3) < 1e-3          # 목표와 상관없는 관절은 그대로


def test_start_overlap_and_wrong_toucher_warn(tmp_path):
    f = tmp_path / "arm.xml"; f.write_text(ARM)
    r = physics.simulate(f, sec=0.3, fps=30, args={"bx": 0.03}, poses=[{"t": 0}], expect=[{"touch": "box", "by": "other"}])
    w = " ".join(r["contacts"]["warn"])
    assert "시작부터 겹침" in w and "기대: other" in w


def test_divergence_is_an_error(tmp_path):
    f = tmp_path / "bad.xml"
    f.write_text("""<mujoco><option timestep="0.05"/><worldbody><body name="b"><joint name="j" type="slide" axis="1 0 0"/>
    <geom type="sphere" size=".01" mass="1e-6"/></body></worldbody><actuator><position joint="j" kp="1e9" kv="1e6"/></actuator></mujoco>""")
    with pytest.raises(RuntimeError, match="발산"):
        physics.simulate(f, sec=1, fps=10, poses=[{"t": 0, "joints": {"j": 0.5}}])


def test_animation_principles_shape_motion(tmp_path):
    f = tmp_path / "arm.xml"; f.write_text(ARM)
    plain = [{"t": 0}, {"t": 1.0, "joints": {"x": 0.4}}]
    styled = [{"t": 0}, {"t": 1.0, "joints": {"x": 0.4}, "anticipate": 0.2, "overshoot": 0.15}]
    a = physics.simulate(f, sec=1.6, fps=60, args={"bx": 0.9}, poses=plain)["bodies"]["tip"]
    b = physics.simulate(f, sec=1.6, fps=60, args={"bx": 0.9}, poses=styled)["bodies"]["tip"]
    assert min(r[0] for r in a[:30]) > -0.005                     # 원칙 없음: 뒤로 가지 않는다
    assert min(r[0] for r in b[:30]) < -0.01                      # 예비 동작: 먼저 반대로
    assert max(r[0] for r in b) > max(r[0] for r in a) + 0.02     # 지나쳤다가
    assert abs(b[-1][0] - 0.4) < 0.02                              # 제자리에 멈춘다


def test_retime_slows_a_window():
    res = {"fps": 10, "sec": 2.0, "bodies": {"o": [[i / 10, 0, 0, 1, 0, 0, 0] for i in range(21)]}}
    r = physics.retime(res, [{"from": 0.5, "to": 1.0, "speed": 0.25}])
    xs = [row[0] for row in r["bodies"]["o"]]
    assert r["sec"] > 3.0                                         # 0.5초가 약 2초로 늘어나 전체가 길어진다
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert min(steps) < 0.03 and max(steps) > 0.09                 # 느린 구간 · 보통 구간이 함께
    assert abs(xs[-1] - 2.0) < 0.11
