"""실사 합성 — 카메라 · 바닥 수학과 재료 등록(앱 없이 시험)"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401

from checks import lint  # noqa: E402
from craft import live, materials  # noqa: E402


def _cam():
    return {"pos": [10.0, -5.0, -100.0], "ori": [8.0, -14.0, 3.0]}


def test_ae_camera_projects_like_blender_matrix():
    """After Effects 카메라 → Blender 행렬로 바꿔도 같은 픽셀에 찍힌다"""
    c = _cam()
    B, O, k = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0], 1.0
    m = live.cam_matrix(c["pos"], c["ori"], B, O, k)
    for p in ([0, 0, 0], [15, 22, 30], [-20, 5, 12]):
        a = live.project(p, c["pos"], c["ori"], 900, 720, 1280)
        b = live.to_pixel(m, p, 900, 720, 1280)
        assert math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6


def test_ground_hit_inverts_projection():
    m = [[1, 0, 0, 1], [0, 0, -1, -10], [0, 1, 0, 5], [0, 0, 0, 1]]   # +y 를 보는 카메라, 높이 5
    p = [2.0, 4.0, 0.0]
    uv = live.to_pixel(m, p, 800, 720, 1280)
    q = live.ground_hit(m, uv[0], uv[1], 800, 720, 1280)
    assert q and math.dist(p, q) < 1e-6


def test_fit_plane_finds_floor_among_outliers():
    pts = [[x * 1.0, y * 1.0, 0.002 * ((x + y) % 2)] for x in range(10) for y in range(10)] + [[i, 0, 3 + i] for i in range(8)]
    c, n, ratio = live.fit_plane(pts)
    assert abs(abs(n[2]) - 1) < 1e-3 and ratio > 0.85 and abs(c[2]) < 0.01


def test_cut_path_hides_when_object_leaves():
    import numpy as np
    on = np.zeros((40, 40), np.uint8)
    on[10:30, 12:22] = 255
    off = np.zeros((40, 40), np.uint8)
    path, seen = live.cut_path([off, on, off], "center")
    assert seen == [False, True, False]
    assert path[0] == path[1] == path[2] and abs(path[1][0] - 16.5 * 4) < 0.01


def test_contour_is_scaled_to_full_frame():
    import numpy as np
    a = np.zeros((40, 40), np.uint8)
    a[10:20, 10:20] = 255
    xs = [p[0] for p in live.contour(a, grow=1)]
    assert min(xs) <= 36 and max(xs) >= 80


def test_live_is_a_registered_material():
    ad, _ = materials.plugins()
    assert "live" in ad
    assert materials.registry().get("live") == "effectcraft"


def test_lint_requires_cut_for_behind(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    sb = {"scenes": [{"sec": 3, "materials": [{"id": "m", "type": "live", "src": str(f), "items": [{"id": "t", "kind": "text", "text": "x", "follow": {"cut": "p"}, "behind": "p"}]}]}]}
    msgs = [x[2] for x in lint.material_spec_checks(sb)]
    assert any("cuts" in m for m in msgs)
