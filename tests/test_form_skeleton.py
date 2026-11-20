"""뼈대 캐릭터(engine/craft/form/skeleton.py) — 부품이 떨어지지 않음 · 발이 바닥 · 얼굴이 고개를 따라 돎"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
from craft import form as F  # noqa: E402
from craft.form import skeleton as K  # noqa: E402

MATS = {k: {"color": "#888888"} for k in ("skin", "hair", "top", "bottom", "shoe", "eye", "mouth", "fur", "nose")}
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
