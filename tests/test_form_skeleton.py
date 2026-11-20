"""뼈대 캐릭터(engine/craft/form/skeleton.py) — 부품이 떨어지지 않음 · 발이 바닥 · 얼굴이 고개를 따라 돎"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
from craft import form as F  # noqa: E402
from craft.form import skeleton as K  # noqa: E402

MATS = {k: {"color": "#888888"} for k in ("skin", "hair", "top", "bottom", "shoe", "eye", "mouth", "fur", "nose", "body", "beak")}
POSES = [{}, {"spine": [6, -5, 10], "head": [8, 25, -10], "l_arm": [30, 20, 0], "l_elbow": 100, "r_arm": [-10, 150, 0], "r_elbow": 30,
              "l_leg": [25, 5], "l_knee": 40, "r_leg": [-10, 3], "r_knee": 10, "lean": [3, 2]}]


def scene(root, az=25):
    return {"materials": MATS, "camera": {"azimuth": az, "elevation": 5, "fov": 30, "frame": 1.3}, "root": root}


def test_humanoid_parts_connected_in_poses():
    for pose in POSES:
        for az in (0, 35, 90):
            assert F.parts_apart(scene({"rig": "humanoid", "pose": pose}, az), res=240) == 0


def test_quadruped_parts_connected_in_poses():
    for pose in ({}, {"spine": [-6, 0], "neck": [15, 25], "head": [-10, 10, 12], "tail": [60, 15, 80], "fl": [35, 0], "fl_knee": 40, "br": [-20, 0], "br_knee": 30}):
        for az in (0, 60, 90):
            assert F.parts_apart(scene({"rig": "quadruped", "pose": pose}, az), res=240) == 0


def test_feet_stay_on_ground_when_knees_bend():
    J0 = K.joints({}, {})
    J1 = K.joints({}, {"l_knee": 50, "r_knee": 50, "l_leg": [30, 0], "r_leg": [30, 0]})
    foot = J0["S"]["foot_h"] * J0["H"]
    assert abs(min(J1["l_ankle"][1], J1["r_ankle"][1]) - foot) < 1e-9 and abs(J0["l_ankle"][1] - foot) < 1e-9
    assert J1["head"][1] < J0["head"][1]                          # 무릎을 굽히면 몸이 내려온다


def test_face_follows_head_turn():
    J0 = K.joints({}, {}); J1 = K.joints({}, {"head": [0, 40, 0]})
    e0 = K._on_head(J0, 0.1, 0) - J0["head"]; e1 = K._on_head(J1, 0.1, 0) - J1["head"]
    ang = np.degrees(np.arctan2(e1[0], e1[2]) - np.arctan2(e0[0], e0[2]))
    assert abs(ang - 40) < 1e-6


def test_bird_parts_connected_in_poses():
    for pose in ({}, {"tilt": -10, "neck": [25, 20], "head": [-15, 10, 10], "wings": [70, 20], "tail": [30, 1], "l_leg": [20], "l_knee": 30}):
        for az in (0, 70, 90):
            assert F.parts_apart(scene({"rig": "bird", "pose": pose}, az), res=240) == 0


def test_expressions_and_hair_stay_attached():
    root = {"rig": "humanoid", "hands": "fingers", "face": {"smile": -1, "brow": 1, "eyelid": 0.5, "open": 0.6},
            "hair": {"bangs": 1, "side": 1, "back": 0.8, "tail": 1, "bun": 1, "spikes": 5}, "pose": {"r_grip": 1, "l_spread": 20}}
    for az in (0, 45, 150):
        assert F.parts_apart(scene(root, az), res=240) == 0


def test_anim_tracks_reach_inside_rig():
    sc = scene({"rig": "humanoid", "name": "hero"})
    sc["anim"] = {"dur": 1.0, "tracks": {"hero": {"pose.r_elbow": [[0, 10], [0.5, 90]], "face.smile": [[0, -1], [0.5, 1]]}}}
    p = F.pose(sc, 0.5)
    assert abs(p["root"]["pose"]["r_elbow"] - 90) < 1e-9 and abs(p["root"]["face"]["smile"] - 1) < 1e-9
    assert abs(F.pose(sc, 0.0)["root"]["pose"]["r_elbow"] - 10) < 1e-9


def test_joint_limits_clamp_pose():
    P = K.clamp_pose({"l_knee": -40, "r_elbow": 200, "head": [0, 120, 0], "l_arm": [0, -40, 0]})
    assert P["l_knee"] == 0 and P["r_elbow"] == 150 and P["head"][1] == 80 and P["l_arm"][1] == -15


def test_ik_reaches_target_and_bends_forward():
    J = K.joints({}, {}, {"l_foot": [0.08, 0.35, 0.25], "pelvis_y": 0.93}, ground=False)
    assert np.linalg.norm(J["l_ankle"] - np.array([0.08, 0.35, 0.25])) < 1e-6
    assert J["l_knee"][2] > (J["l_hip"][2] + J["l_ankle"][2]) / 2          # 무릎은 앞으로


def test_walk_on_stairs_feet_on_treads_and_drag_prop_on_ground():
    from craft.form import world as W
    steps = [{"prim": "roundbox", "size": [0.6, 0.09 * (i + 1), 0.15], "r": 0.01, "pos": [0, 0.09 * (i + 1), 1.2 + 0.3 * i], "mat": "body"} for i in range(4)]
    case = {"prim": "roundbox", "size": [0.15, 0.25, 0.08], "r": 0.02, "pos": [0, 0.25, 0], "mat": "beak"}
    hero = {"rig": "humanoid", "move": {"path": [[0, 0], [0, 2.6]], "speed": 1.0}, "hold": {"r": {"prop": case, "grip": [0, 0.5, 0], "mode": "drag", "ground": [0, 0, 0]}}}
    sc = {"materials": MATS, "root": {"op": "union", "children": steps + [hero]}}
    g = W.Ground(sc)
    assert abs(g(0, 1.2) - 0.18) < 0.01 and abs(g(0, 0.5)) < 1e-6
    for t in (0.2, 1.1, 1.7, 2.3):
        lo = W.locomotion(hero, t, g)
        for side in ("l", "r"):
            f = lo["feet"][side]
            assert f[1] >= g(f[0], f[2]) + 0.06 - 1e-6            # 발은 늘 디딘 면 위(발 높이 이상)
        parts = W.place(hero, t, g)
        assert len(parts) == 2
    assert F.parts_apart({**scene({"op": "union", "children": steps + [hero]}, 80), "t": 1.5}, res=200) <= 1
