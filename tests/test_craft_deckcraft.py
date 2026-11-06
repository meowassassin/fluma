"""DeckCraft 어댑터(scripts/craft/adapters/deckcraft.py) — 항목 나누기는 앱 없이, 렌더는 앱이 설치됐을 때만."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import deckcraft as dc  # noqa: E402

Image = pytest.importorskip("PIL.Image")
app = pytest.mark.skipif(not (ROOT / "tools" / "crafts" / "deckcraft" / "installed.json").exists(), reason="DeckCraft 가 설치되지 않음")


def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["diagram"] is dc.diagram
    assert materials.registry().get("diagram") == "deckcraft"


def test_norm_items():
    assert dc.norm_items([["무료", "광고"], ["유료", "무제한"]], "compare") == ["무료", "\t광고", "유료", "\t무제한"]
    with pytest.raises(RuntimeError):
        dc.norm_items([], "steps")
    with pytest.raises(RuntimeError, match="compare"):
        dc.norm_items(["a", "b", "c"], "compare")


def test_units_arrows_go_with_next_item():
    ch = [{"id": 1, "text": "A", "box": [0, 0, 100, 50]}, {"id": 2, "preset": "rightArrow", "box": [40, 52, 20, 20]},
          {"id": 3, "text": "B", "box": [0, 74, 100, 50]}]
    units, frame = dc.units_of(ch, ["A", "B"], "steps")
    assert [u["ids"] for u in units] == [[1], [3, 2]] and frame == []


def test_units_hierarchy_lines_go_with_child():
    ch = [{"id": 1, "text": "대표", "box": [100, 0, 60, 40]}, {"id": 2, "text": "개발", "box": [20, 80, 60, 40]},
          {"id": 3, "text": "디자인", "box": [180, 80, 60, 40]},
          {"id": 4, "preset": "line", "box": [50, 40, 80, 40]}, {"id": 5, "preset": "line", "box": [130, 40, 80, 40]}]
    units, _ = dc.units_of(ch, ["대표", "\t개발", "\t디자인"], "hierarchy")
    assert [u["ids"] for u in units] == [[1], [2, 4], [3, 5]]


def test_font_for():
    assert dc.font_for([0, 0, 260, 120], "URL 입력") == 30
    assert dc.font_for([0, 0, 40, 40], "아주 긴 항목 이름입니다") == 14


@app
def test_diagram_steps(tmp_path):
    info = dc.diagram({"id": "m1", "type": "diagram", "kind": "steps", "title": "세 단계", "items": ["입력", "분석", "확인"],
                       "cues": ["입력", None, "확인"]}, tmp_path / "m1.png", tmp_path)
    assert info["size"] == [1080, 1920] and len(info["layers"]) == 3
    assert [l["cue"] for l in info["layers"]] == ["입력", None, "확인"]
    ys = [l["box"][1] for l in info["layers"]]
    assert ys == sorted(ys)                               # 위에서 아래로
    for l in info["layers"]:
        assert Path(l["file"]).exists() or (ROOT / l["file"]).exists()
    assert (tmp_path / "m1.deckcraft").exists()
