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
