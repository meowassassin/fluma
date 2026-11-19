"""CADCraft 어댑터(engine/craft/adapters/cadcraft.py) — drawing.
명령 · 창 · 단색 변환은 앱 없이, 도면 렌더는 CADCraft(3D 는 SolidCraft 도)가 설치됐을 때만."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import materials  # noqa: E402
from craft.adapters import cadcraft as cc  # noqa: E402

HAS = lambda a: (ROOT / "tools" / "crafts" / a / "installed.json").exists()   # noqa: E731
app = pytest.mark.skipif(not HAS("cadcraft"), reason="CADCraft 가 설치되지 않음")
app3d = pytest.mark.skipif(not (HAS("cadcraft") and HAS("solidcraft")), reason="CADCraft · SolidCraft 가 설치되지 않음")

ROOM = ['rectang {"p1":[0,0],"p2":[3600,6400]}', 'rectang {"p1":[200,200],"p2":[3400,6200]}',
        {"id": "text", "params": {"at": [1800, 4700], "text": "거실 18㎡", "height": 250, "justify": "MC"}}]


# ---------------------------------------------------------------- 앱 없이
def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["drawing"] is cc.drawing
    assert materials.registry().get("drawing") == "cadcraft"


def test_cmd_forms():
    assert cc._cmd(' line {"points":[[0,0],[1,1]]} ') == 'line {"points":[[0,0],[1,1]]}'
    assert cc._cmd({"id": "text", "params": {"text": "거실"}}) == 'text {"text": "거실"}'
    with pytest.raises(RuntimeError):
        cc._cmd(3)


def test_window_is_9_16_and_centered():
    (x0, y0), (x1, y1) = cc._window([0, 0, 3600, 6400], 1080, 1920, 0.05)
    assert abs((x1 - x0) / (y1 - y0) - 9 / 16) < 1e-9
    assert abs((x0 + x1) / 2 - 1800) < 1e-9 and x0 < 0 and y1 > 6400
    (x0, y0), (x1, y1) = cc._window([0, 0, 1000, 10], 1080, 1920, 0)
    assert abs(x1 - x0 - 1000) < 1e-6                           # 넓은 도면은 폭에 맞춘다


def test_mm_and_mono():
    assert cc._mm(80.04) == "80" and cc._mm(12.35) in ("12.3", "12.4") and cc._mm(236.81) == "236.8"
    Image = pytest.importorskip("PIL.Image")
    im = Image.new("RGB", (3, 1), "white")
    im.putpixel((0, 0), (255, 255, 0))         # 노란 글자 → 검정
    im.putpixel((1, 0), (255, 59, 48))         # 빨간 표시 → 빨강 그대로
    out = cc._mono(im)
    assert out.getpixel((0, 0))[0] < 40 and out.getpixel((1, 0)) == (220, 38, 38) and out.getpixel((2, 0)) == (255, 255, 255)


def test_needs_a_source(tmp_path):
    if not HAS("cadcraft"):
        pytest.skip("CADCraft 가 설치되지 않음")
    with pytest.raises(RuntimeError, match="src"):
        cc.drawing({"id": "d0"}, tmp_path / "d0.png", tmp_path)


# ---------------------------------------------------------------- 앱으로
@app
def test_drawing_from_commands_dark_and_mark(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    m = {"id": "d1", "type": "drawing", "cmd": ROOM, "mark": [[2400, 3400, 3300, 4200]], "width": 270, "height": 480}
    info = cc.drawing(m, tmp_path / "d1.png", tmp_path)
    assert info["paper"] == "dark" and info["source"] == "cmd" and (tmp_path / "d1.dxf").exists()
    x, y, w, h = info["marks"][0]["box"]
    assert 0.5 < x < 0.75 and 0.2 < y < 0.45 and w > 0.1
    with Image.open(tmp_path / "d1.png") as im:
        assert im.size == (270, 480)
        assert sum(im.convert("RGB").getpixel((3, 3))) < 200      # 어두운 CAD 화면


@app
def test_drawing_white_paper_from_src(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "plan.dxf"
    materials._run([materials.cli("cadcraft"), "sample", "floorplan", src], tmp_path)
    work = tmp_path / "s01"
    work.mkdir()
    info = cc.drawing({"id": "d2", "src": str(src), "paper": "white", "width": 270, "height": 480}, work / "d2.png", work)
    assert info["paper"] == "white" and info["source"] == "src"
    with Image.open(work / "d2.png") as im:
        px = im.convert("RGB")
        assert px.getpixel((2, 2)) == (255, 255, 255)
        colors = {px.getpixel((x, y)) for x in range(0, 270, 3) for y in range(0, 480, 3)}
        assert not any(r > 200 and g > 200 and b < 100 for r, g, b in colors)   # 노란 글자가 남지 않는다


@app3d
def test_drawing_from_model_views(tmp_path):
    m = {"id": "d3", "type": "drawing", "model": {"shape": "case", "size": [80, 50, 32]}, "views": ["front", "top", "right"],
         "title": "외형도", "width": 270, "height": 480}
    info = cc.drawing(m, tmp_path / "d3.png", tmp_path)
    assert info["source"] == "model"
    text = (tmp_path / "d3.dxf").read_text("utf-8", "replace")
    for v in ("80", "50", "32", "정면도", "평면도", "우측면도"):
        assert v in text
