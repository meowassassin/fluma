"""VectorCraft 어댑터(engine/craft/adapters/vectorcraft.py) — 계산은 앱 없이, 실제 그리기는 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import materials  # noqa: E402
from craft.adapters import vectorcraft as vc  # noqa: E402

Image = pytest.importorskip("PIL.Image")
HAS_APP = (ROOT / "tools" / "crafts" / "vectorcraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="VectorCraft 가 설치되지 않음")


# ---------------------------------------------------------------- 앱 없이
def test_plugin_registers_new_materials():
    ad, _ = materials.plugins()
    assert ad["overlay"] is vc.overlay and ad["template_card"] is vc.template_card
    reg = materials.registry()
    assert reg.get("overlay") == "vectorcraft" and reg.get("template_card") == "vectorcraft"


def test_box_ratio_or_pixels():
    assert vc._px_box([0.5, 0.25, 0.5, 0.5], 200, 100) == [100, 25, 100, 50]
    assert vc._px_box([10, 20, 30, 40], 200, 100) == [10, 20, 30, 40]
    assert vc._px_box(None, 200, 100) is None
    assert vc._px_pt([0.5, 0.5], 200, 100) == [100, 50]


def test_hand_loop_overlaps_and_arrow_ends_on_points():
    lp = vc._loop_path([100, 100, 200, 80], 10, 0)["anchors"]
    assert len(lp) == 10 and "in" not in lp[0] and "out" not in lp[-1]
    ar = vc._arrow_path([0, 0], [100, 0], 0.2)["anchors"]
    assert (ar[0]["x"], ar[0]["y"], ar[1]["x"], ar[1]["y"]) == (0, 0, 100, 0)
    assert ar[0]["out"][1] != 0            # 옆으로 휜다


def test_overlay_needs_target(tmp_path):
    with pytest.raises(RuntimeError, match="target"):
        vc.overlay({"id": "m2", "type": "overlay", "marks": []}, tmp_path / "m2.png", tmp_path)
    with pytest.raises(RuntimeError, match="아직 없습니다"):
        vc.overlay({"id": "m2", "type": "overlay", "target": "m1", "marks": []}, tmp_path / "m2.png", tmp_path)


# ---------------------------------------------------------------- 앱으로
def _target(tmp_path: Path, w=540, h=960) -> None:
    im = Image.new("RGB", (w, h), "white")
    im.paste((30, 30, 30), (300, 40, 500, 100))
    f = tmp_path / "shot.png"
    im.save(f)
    (tmp_path / "m1.json").write_text(json.dumps({"file": str(f)}), "utf-8")


@app
@pytest.mark.parametrize("style", ["clean", "hand"])
def test_overlay_layers_match_marks(tmp_path, style):
    _target(tmp_path)
    m = {"id": "m2", "type": "overlay", "target": "m1", "style": style, "marks": [
        {"kind": "box", "box": [300, 40, 200, 60], "text": "여기", "cue": "버튼"},
        {"kind": "arrow", "box": [0.55, 0.04, 0.37, 0.06], "text": "누르기"},
        {"kind": "label", "box": [0.1, 0.5, 0.8, 0.05], "text": "설명 한 줄"}]}
    info = vc.overlay(m, tmp_path / "m2.png", tmp_path)
    assert info["app"] == "vectorcraft" and (info["width"], info["height"]) == (540, 960)
    assert [L["cue"] for L in info["layers"]] == ["버튼", None, None]
    for L in info["layers"]:
        x, y, w, h = L["box"]
        assert 0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1
        with Image.open(L["file"]) as im:
            assert im.mode == "RGBA" and im.getchannel("A").getbbox()
            assert abs(im.width - w * 540) <= 1 and abs(im.height - h * 960) <= 1
    # 박스 레이어는 대상 상자를 감싼다
    bx = info["layers"][0]["box"]
    assert bx[0] * 540 < 300 and (bx[0] + bx[2]) * 540 > 500
    assert (tmp_path / "m2.png").exists() and Path(info["editable"]).exists()


@app
def test_template_card_default_and_named_row(tmp_path):
    csvf = tmp_path / "ds.csv"
    csvf.write_text('name,품목,가격,반응\nday1,배추 1포기,"4,980원",평소 가격\nday2,무 1개,"1,290원",이러다 다 죽어요\n', "utf-8")
    info = vc.template_card({"id": "m1", "type": "template_card", "csv": str(csvf), "row": "day2"}, tmp_path / "m1.png", tmp_path)
    assert info["default_template"] and info["row"] == "day2" and info["values"]["가격"] == "1,290원"
    assert (info["width"], info["height"]) == (960, 720)
    assert sorted(p.name for p in (tmp_path / "m1.cards").glob("*.png")) == ["day1.png", "day2.png"]
    # 만든 틀을 다시 쓰고, 한 줄(values)만 넣기
    tpl = Path(info["editable"])
    info2 = vc.template_card({"id": "m3", "type": "template_card", "template": str(tpl),
                              "values": {"품목": "대파", "가격": "2,000원", "반응": "평소 가격"}}, tmp_path / "m3.png", tmp_path)
    assert "default_template" not in info2 and (tmp_path / "m3.png").exists()
    with pytest.raises(RuntimeError, match="범위"):
        vc.template_card({"id": "m4", "type": "template_card", "template": str(tpl), "csv": str(csvf), "row": 5}, tmp_path / "m4.png", tmp_path)
