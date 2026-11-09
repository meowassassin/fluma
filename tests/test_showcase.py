"""쇼케이스(제품 소개 영상) — 기다림 빨리 감기 · 카메라 줌 인/아웃 계산(녹화 없이)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
import showcase as S  # noqa: E402


def test_idle_gaps_are_shortened():
    ev = [{"t": 1.0, "t_end": 1.5}, {"t": 8.0, "t_end": 8.5}]
    pts = S.time_map(ev, 10.0)
    assert pts[-1][0] < 7.5                                  # 10초 녹화 → 긴 기다림(6초)만 1초로 줄여 7.5초 안(2026-11-09: 너무 빨라 덜 줄임)
    assert abs(S.src_time(pts, S.out_time(pts, 8.0)) - 8.0) < 1e-6


def test_camera_zooms_in_and_out_between_far_targets():
    size = (2880, 1800)
    ev = [{"t": 1.0, "box": [100, 100, 400, 120], "do": "focus"}, {"t": 4.0, "box": [2300, 1500, 400, 120], "do": "focus"}]
    pts = S.time_map(ev, 6.0)
    keys = S.camera_keys(ev, size, pts, 1920, 1080, 1920 * 0.86)
    zs = [k[3] for k in keys]
    assert max(zs) > 1.2 and 1.0 in zs[2:]                  # 들어갔다가 · 멀어서 한 번 빠짐
    assert S.cam_at(keys, 0.0)[2] == 1.0


def test_goto_loading_is_cut_even_with_preroll():
    ev = [{"t": 1.0, "t_end": 1.4, "do": "focus"}, {"do": "goto", "t0": 2.0, "t": 3.5, "t_end": 3.8}, {"t": 3.9, "t_end": 4.5, "do": "focus"}]
    pts = S.time_map(ev, 5.0)
    assert all(not (2.05 < S.src_time(pts, x / 100) < 3.45) for x in range(0, int(pts[-1][0] * 100)))   # 로딩 화면이 한 프레임도 안 나옴
