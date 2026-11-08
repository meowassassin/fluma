"""그리기 엔진(engine/craft/drawlib) — 설계가 약속한 성질만 고정한다: 닫힌 곡선 · 정확한 넓이 · 날카로운 모서리 · 적은 핸들."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from drawlib.geom import Box, Capsule, Circle, Ellipse, Leaf, Polygon, Subtract, Union, bezier_points, outline  # noqa: E402


def _area(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# 몸 설계도(library/archetypes)는 실험 데이터 — 순정 상태(라이브러리 비움)에서는 그걸 쓰는 시험을 건너뛴다
needs_archetypes = pytest.mark.skipif(not (ROOT / "data" / "library" / "archetypes").exists() or not any((ROOT / "data" / "library" / "archetypes").glob("*.form.json")),
                                      reason="library/archetypes 가 비어 있음(실험 데이터)")

def test_circle_is_smooth_and_accurate():
    o = outline(Circle((0, 0), 50), res=1)
    assert len(o.rings) == 1 and o.handles <= 6
    assert abs(_area(bezier_points(o.rings, 64)[0]) / (math.pi * 50 ** 2) - 1) < 0.005
    assert o.d.startswith("M") and o.d.endswith("Z")


def test_box_keeps_exact_corners_even_off_grid_and_rotated():
    for sh in (Box((0, 0), 100, 60), Box((0.3, 0.7), 100, 60), Box((0, 0), 100, 60, rot=20)):
        o = outline(sh, res=1)
        assert o.handles == 4
    starts = sorted(tuple(np.round(c[0]).tolist()) for c in outline(Box((0, 0), 100, 60), res=1).rings[0])
    assert starts == sorted([(-50.0, -30.0), (-50.0, 30.0), (50.0, 30.0), (50.0, -30.0)])


def test_triangle_and_leaf_tips_stay_sharp():
    assert outline(Polygon([(0, -50), (45, 40), (-45, 40)]), res=1).handles == 3
    assert outline(Leaf((0, 0), (0, -120), 50), res=0.8).handles == 2


def test_smooth_union_and_subtract_make_one_body_with_a_hole():
    body = Union([Capsule((0, 40), (0, -40), 55, 38), Capsule((-22, 80), (-26, 135), 12, 10), Capsule((22, 80), (30, 135), 12, 10)], k=14)
    o = outline(Subtract(body, Ellipse((18, -20), 14, 6)), res=0.8)
    assert len(o.rings) == 2          # 몸 하나 + 입 구멍
    assert o.handles < 60             # 사람이 고칠 만한 핸들 수


# ---------------------------------------------------------------- 2단계: 형태 풀이(좌표 없음)
import pytest  # noqa: E402

from drawlib.form import SolveError, solve  # noqa: E402

BEAN = {
    "view": "3/4", "facing": "right",
    "parts": [
        {"id": "body", "shape": "blob", "size": {"h": 1.5, "w": 1.05}},
        {"id": "eye_l", "shape": "ellipsoid", "size": {"h": 0.3, "w": 0.24}, "attach": {"to": "body", "v": 0.28, "az": -22, "inset": 0.2}, "role": "white", "decal": True},
        {"id": "eye_r", "mirror": "eye_l"},
        {"id": "arm_l", "shape": "capsule", "len": 0.6, "r": [0.09, 0.07], "attach": {"to": "body", "v": 0.5, "az": -80, "inset": 0.1}, "splay": 25},
        {"id": "arm_r", "mirror": "arm_l"},
        {"id": "leg_l", "shape": "capsule", "len": 0.45, "r": [0.11, 0.09], "attach": {"to": "body", "v": 0.9, "az": -40, "inset": 0.12}, "splay": 6, "ground": True},
        {"id": "leg_r", "mirror": "leg_l"},
    ],
}


def _by(placed):
    return {p.id: p for p in placed}


def test_coordinates_are_refused_with_a_relation_hint():
    bad = {"parts": [{"id": "body", "shape": "blob", "size": {"h": 1}, "x": 120, "y": 340}]}
    with pytest.raises(SolveError) as e:
        solve(bad)
    assert any("좌표" in p and "attach" in p for p in e.value.problems)


def test_three_quarter_view_puts_far_side_behind_and_hides_far_side_decals_in_profile():
    placed, _ = _by(solve(BEAN)[0]), None
    assert placed["arm_r"].z < placed["body"].z < placed["arm_l"].z        # 먼 팔은 몸 뒤, 가까운 팔은 앞
    side = _by(solve({**BEAN, "view": "side"})[0])
    assert "eye_l" in side and "eye_r" not in side                           # 옆에서는 먼 쪽 눈이 안 보인다


def test_feet_touch_the_ground_and_facing_left_mirrors():
    right = _by(solve(BEAN)[0])
    assert abs(max(right[k].shape.bounds()[3] for k in ("leg_l", "leg_r"))) < 1e-6
    left = _by(solve({**BEAN, "facing": "left"})[0])
    assert left["arm_l"].pivot[0] == pytest.approx(-right["arm_l"].pivot[0])


def test_floating_part_is_reported_in_words():
    f = {"parts": [{"id": "body", "shape": "ellipsoid", "size": {"h": 1}},
                   {"id": "hat", "shape": "box", "size": {"h": 0.3, "w": 0.4}, "attach": {"to": "body", "at": "top", "inset": -0.15}}]}
    with pytest.raises(SolveError) as e:
        solve(f)
    assert any("떠 있습니다" in p for p in e.value.problems)


def test_cycles_and_unknown_parents_are_named():
    f = {"parts": [{"id": "a", "shape": "ellipsoid", "size": {"h": 1}, "attach": {"to": "b"}},
                   {"id": "b", "shape": "ellipsoid", "size": {"h": 1}, "attach": {"to": "a"}}]}
    with pytest.raises(SolveError) as e:
        solve(f)
    assert e.value.problems


@needs_archetypes
def test_every_archetype_solves_and_renders():
    """몸 설계도마다 한 장(설계 문서 9절의 연기 시험)"""
    from drawlib import render
    from drawlib.form import ARCHETYPES
    names = sorted(p.name[: -len(".form.json")] for p in ARCHETYPES.glob("*.form.json"))
    assert len(names) >= 9
    for n in names:
        placed, _ = solve({"archetype": n})
        assert "<path" in render.svg(placed, style={"preset": "flat-bright"}, res=1.5), n


@needs_archetypes
def test_archetype_override_add_remove():
    placed, _ = solve({"archetype": "blob_creature", "remove": ["antenna"],
                       "parts": [{"id": "body", "role": "accent"}, {"id": "hat", "shape": "box", "size": {"h": 0.2, "w": 0.5}, "attach": {"to": "body", "at": "top", "inset": 0.05}}]})
    ids = {p.id for p in placed}
    assert "antenna" not in ids and "hat" in ids
    assert next(p for p in placed if p.id == "body").role == "accent"


# ---------------------------------------------------------------- 그림 lint · 화풍 시스템
@needs_archetypes
def test_lint_refuses_default_palette_and_flags_missing_expression():
    from drawlib.lint import lint
    placed, _ = solve({"archetype": "blob_creature"})
    codes = {f.code: f.level for f in lint(placed, {"archetype": "blob_creature"}, {"preset": "flat-bright"})}
    assert codes.get("I01") == "P0" and codes.get("I08") == "P1"
    styled = {f.code for f in lint(placed, {}, {"preset": "flat-bright", "palette": {"main": "#ff6b6b", "main_dark": "#c94c4c"}})}
    assert "I01" not in styled


def test_lint_catches_parts_buried_in_same_value():
    from drawlib.lint import lint
    f = {"view": "front", "parts": [
        {"id": "body", "shape": "blob", "size": {"h": 1.2, "w": 1.0}, "role": "dark"},
        {"id": "arm", "shape": "capsule", "len": 0.5, "r": [0.08, 0.06], "attach": {"to": "body", "v": 0.4, "az": -20, "inset": 0.1}, "dir": 90, "role": "dark"}]}
    placed, _ = solve(f)
    assert any(x.code == "I10" for x in lint(placed, f, {"preset": "flat-bright", "palette": {"dark": "#1f2755"}}))


def test_dark_colors_keep_saturation_in_shadow():
    from drawlib import style
    sh = style.shift("#0b0326", h=0.03, s=0.04, l=-0.25)
    assert style._hex(sh) != (0.0, 0.0, 0.0)


def test_style_system_is_loaded_and_measured_shift_is_clamped(tmp_path, monkeypatch):
    import json as _j
    from drawlib import style
    d = tmp_path / "demo"; d.mkdir()
    (d / "style.json").write_text(_j.dumps({"palette": {"main": "#123456"}, "shade": {"tones": 2, "shift": {"h": 0.3, "s": 0.5, "l": -0.6}}}))
    monkeypatch.setattr(style, "STYLES", tmp_path)
    st = style.resolve({"system": "demo"})
    assert st["palette"]["main"] == "#123456"
    assert st["shade"]["shift"]["l"] == -0.25 and st["shade"]["shift"]["h"] == 0.08


def test_limb_expands_to_two_joints_and_cut_makes_an_opening():
    f = {"view": "front", "parts": [
        {"id": "body", "shape": "blob", "size": {"h": 1.2, "w": 1.0}, "role": "dark"},
        {"id": "hole", "shape": "ellipsoid", "size": {"h": 0.4, "w": 0.4}, "attach": {"to": "body", "v": 0.3, "az": 0, "inset": 0.3}, "cut": True, "role": "dark"},
        {"id": "leg", "shape": "limb", "kind": "leg", "len": 0.6, "r": [0.1, 0.07, 0.05], "bend": -40, "attach": {"to": "body", "v": 0.9, "az": -30, "inset": 0.1}, "ground": True}]}
    placed, _ = solve(f)
    by = {p.id: p for p in placed}
    assert "leg_lo" in by and by["leg_lo"].parent == "leg" and by["leg_lo"].spec.get("ground")
    assert by["hole"].spec.get("cavity_of") == "dark"
    import numpy as np
    cx, cy = (by["hole"].shape.bounds()[0] + by["hole"].shape.bounds()[2]) / 2, (by["hole"].shape.bounds()[1] + by["hole"].shape.bounds()[3]) / 2
    assert by["body"].shape.sdf(np.array([cx]), np.array([cy]))[0] > 0      # 몸이 그 자리에서 파였다


@needs_archetypes
def test_world_layers_are_built_without_coordinates():
    from drawlib import scene
    L = scene.build({"glow": {"at": "center"}, "far": [{"archetype": "building", "count": 3}], "motif": "stars"}, {"preset": "flat-bright", "palette": {"main": "#ff6b6b"}}, seed=1)
    assert {"sky", "glow", "far", "ground", "motif"} <= set(L)
    assert all(v.startswith("<svg") for v in L.values())


def test_shadows_never_spill_outside_their_shape_and_have_no_needles():
    """엉성한 벡터의 대표 증상: 그림자 끝이 실루엣 밖으로 튀는 바늘 · 가는 찌꺼기"""
    import numpy as np
    from drawlib import geom, style
    from drawlib.form import U
    st = style.resolve({"preset": "flat-bright"})
    f = {"view": "3/4", "parts": [
        {"id": "body", "shape": "blob", "size": {"h": 1.2, "w": 0.95}, "tilt": 12},
        {"id": "arm", "shape": "limb", "kind": "arm", "len": 0.6, "r": [0.075, 0.06, 0.05], "bend": 40, "attach": {"to": "body", "v": 0.5, "az": 80, "inset": 0.06}, "dir": 75},
        {"id": "leg", "shape": "limb", "kind": "leg", "len": 0.5, "r": [0.1, 0.07, 0.045], "bend": -45, "attach": {"to": "body", "v": 0.9, "az": -35, "inset": 0.12}, "dir": 10, "ground": True}]}
    placed, _ = solve(f)
    layers = {}
    for p in placed:
        layers.setdefault(p.layer, []).append(p.shape)
    for lid, shapes in layers.items():
        shape = shapes[0] if len(shapes) == 1 else geom.Union(shapes, k=st["round"] * U)
        sh = geom.outline(style.shadow_shape(shape, U, st), res=0.8, corner_angle=40.0)
        for P in geom.bezier_points(sh.rings, 24):
            d = shape.sdf(P[:, 0], P[:, 1])
            assert d.max() < 0.8, f"{lid}: 그림자가 면 밖으로 {d.max():.1f} 튀어나옴"
