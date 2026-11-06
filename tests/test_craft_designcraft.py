"""DesignCraft 어댑터(info_card · thumbnail) — 계산은 앱 없이, 실제 조판은 앱이 설치됐을 때만."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import designcraft as dc  # noqa: E402
from craft.adapters import figcraft as fg  # noqa: E402

Image = pytest.importorskip("PIL.Image")
HAS_FIG = (ROOT / "tools" / "crafts" / "figcraft" / "installed.json").exists()
HAS_DC = (ROOT / "tools" / "crafts" / "designcraft" / "installed.json").exists()
fig_app = pytest.mark.skipif(not HAS_FIG, reason="FigCraft 가 설치되지 않음")
dc_app = pytest.mark.skipif(not HAS_DC, reason="DesignCraft 가 설치되지 않음")


# ---------------------------------------------------------------- 앱 없이
def test_plugins_register():
    ad, _ = materials.plugins()
    assert ad["ui_mock"] is fg.ui_mock and ad["info_card"] is dc.info_card and ad["thumbnail"] is dc.thumbnail
    reg = materials.registry()
    assert reg.get("ui_mock") == "figcraft" and reg.get("info_card") == "designcraft" and reg.get("thumbnail") == "designcraft"


def test_inputs_checked(tmp_path):
    with pytest.raises(RuntimeError, match="src"):
        fg.ui_mock({"id": "m1", "type": "ui_mock"}, tmp_path / "m1.png", tmp_path)
    with pytest.raises(RuntimeError, match="device"):
        fg.ui_mock({"id": "m1", "type": "ui_mock", "device": "watch", "screen": {"title": "a"}}, tmp_path / "m1.png", tmp_path)
    with pytest.raises(RuntimeError, match="title"):
        dc.info_card({"id": "c", "type": "info_card"}, tmp_path / "c.png", tmp_path)


def test_card_rows_and_csv(tmp_path):
    f = tmp_path / "t.csv"
    f.write_text("name,title,points\na,제목 하나,첫째|둘째\n", "utf-8")
    rows = dc._rows({"csv": str(f)})
    assert rows[0]["points"] == ["첫째", "둘째"] and rows[0]["name"] == "a"
    v = dc._card_values(dc._card_layout(rows)["rows"][0], ["title", "n1", "p1", "n3", "p3"])
    assert v["n1"] == "01" and v["p1"] == "첫째" and v["n3"] == "" and v["p3"] == ""


# ---------------------------------------------------------------- 앱으로
@dc_app
def test_info_card_merge_pages(tmp_path):
    out = tmp_path / "c.png"
    info = dc.info_card({"id": "c", "type": "info_card", "rows": [
        {"title": "한 줄 제목", "body": "본문", "source": "출처"},
        {"title": "조금 더 긴 제목을 두 줄로 나눠 보는 카드", "points": ["요점"]}]}, out, tmp_path)
    assert info["rows"] == 2 and len(info["pages"]) == 2
    with Image.open(out) as a, Image.open(tmp_path / "c.p02.png") as b:
        assert a.size == b.size                                          # 시리즈 카드는 크기가 같다
        assert a.getpixel((1, 1))[3] == 0                                # 카드 밖 투명


@dc_app
def test_thumbnail_two_sizes(tmp_path):
    out = tmp_path / "t.png"
    info = dc.thumbnail({"id": "t", "type": "thumbnail", "title": "컴퓨터 버그, 진짜 벌레였다", "hook": "1947년",
                         "emphasis": "진짜 벌레", "src": False}, out, tmp_path)
    with Image.open(out) as v:
        assert v.size == (1080, 1920)
    with Image.open(tmp_path / "t.16x9.png") as h:
        assert h.size == (1280, 720)
    assert info["title_lines"] == ["컴퓨터 버그,", "진짜 벌레였다"]
