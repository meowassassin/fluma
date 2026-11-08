"""인물 엔진 — 화풍 고르기 · 획 생성(앱 없이)"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
from craft.figure import choose, styles  # noqa: E402


def _ball(d):
    S = 200
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    nx, ny = (x - 100) / 70, (y - 100) / 70
    r2 = nx ** 2 + ny ** 2
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    a = (r2 < 1).astype(np.float32)
    g = np.clip(.2 + .8 * (nx * -.5 + ny * -.5 + nz * .7), 0, 1) * a
    sh = np.dstack([g, g, g, a]); nm = np.dstack([(nz + 1) / 2, (-ny + 1) / 2, (nx + 1) / 2, a])
    cv2.imwrite(str(d / "s.png"), (sh * 65535).astype(np.uint16))
    cv2.imwrite(str(d / "n.png"), (nm * 65535).astype(np.uint16))
    return d / "s.png", d / "n.png"


def test_every_style_builds_ordered_strokes(tmp_path):
    s, n = _ball(tmp_path)
    for st in styles.FN:
        (fills, stages), _ = styles.build(s, n, st, {})
        assert fills or sum(len(i) for _, i in stages) > 0, st
    (_, st), _ = styles.build(s, n, "sketch", {})
    assert [x[0] for x in st][:2] == ["block", "outline"]        # 큰 덩어리 → 윤곽 순서로 그려진다


def test_params_change_density(tmp_path):
    s, n = _ball(tmp_path)
    c = lambda d: sum(len(i) for _, i in styles.build(s, n, "engrave", {"density": d})[0][1])
    assert c(1.6) > c(.6)


def test_choice_follows_topic_and_can_be_overridden():
    war = {"id": "a", "title": "전쟁과 분노의 신화", "scenes": []}
    calm = {"id": "b", "title": "고요한 슬픔", "scenes": []}
    assert choose.rank(war)[0][0] != choose.rank(calm)[0][0]
    assert choose.pick(war, {"style": "wash"})["style"] == "wash"
    assert choose.pick({"id": "c", "direction": {"art": {"figure": "sketch"}}})["style"] == "sketch"
    assert choose.vary("x", "sketch") != choose.vary("y", "sketch")


def test_small_figure_gets_fat_style_and_lines():
    sb = {"id": "z", "title": "고요한 슬픔", "scenes": []}
    c = choose.pick(sb, {"on_screen": 180})
    assert c["style"] in choose.FAT and c["params"]["line"] > 2
