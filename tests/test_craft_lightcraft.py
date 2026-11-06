"""LightCraft 어댑터(scripts/craft/adapters/lightcraft.py) — 계산은 앱 없이, 현상은 앱이 설치됐을 때만."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import lightcraft as lc  # noqa: E402

Image = pytest.importorskip("PIL.Image")
app = pytest.mark.skipif(not (ROOT / "tools" / "crafts" / "lightcraft" / "installed.json").exists(), reason="LightCraft 가 설치되지 않음")


def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["photo_grade"] is lc.photo_grade
    assert materials.registry().get("photo_grade") == "lightcraft"


def test_crop_rect_916():
    r = lc.crop_rect((2560, 1600), "9:16")
    assert r[1] == 0 and r[3] == 1 and abs((r[2] - r[0]) - 1600 * 9 / 16 / 2560) < 1e-4
    assert abs((r[0] + r[2]) / 2 - 0.5) < 1e-4
    left = lc.crop_rect((2560, 1600), "9:16", [0.0, 0.5])
    assert left[0] == 0.0                                  # 가장자리에서 멈춘다
    tall = lc.crop_rect((1000, 3000), "9:16")              # 더 길쭉 → 위아래를 자른다
    assert tall[0] == 0 and tall[2] == 1 and tall[1] > 0
    assert lc.crop_rect((1080, 1920), "9:16") is None and lc.crop_rect((100, 100), False) is None
    with pytest.raises(RuntimeError):
        lc.crop_rect((100, 100), "7:3")


def test_auto_values_are_damped():
    v = lc.auto_values({"exposure": -0.74, "contrast": 68, "highlights": -66, "shadows": 52, "vibrance": 30, "whites": 0})
    assert v["light.contrast"] == 15 and v["light.highlights"] == -26.4 and abs(v["light.exposure"] + 0.296) < 1e-6
    assert "light.whites" not in v


def test_look_of():
    assert lc.look_of("film")[0] == "lc.warm-film"
    assert lc.look_of("lc.teal-orange") == ("lc.teal-orange", {})
    assert lc.look_of("none") == (None, {})
    with pytest.raises(RuntimeError, match="look"):
        lc.look_of("sepia-dream")


@app
def test_grade_photo(tmp_path):
    src = tmp_path / "land.jpg"
    im = Image.new("RGB", (800, 500))
    for x in range(800):
        for y in range(0, 500, 50):
            im.putpixel((x, y), (x % 255, 120, 200))
    im.save(src)
    info = lc.photo_grade({"id": "m1", "type": "photo_grade", "src": str(src), "look": "warm", "credit": "사진: 시험"},
                          tmp_path / "m1.png", tmp_path)
    assert info["app"] == "lightcraft" and info["size"] == [1080, 1920] and info["preset"] == "lc.warm-glow"
    assert (tmp_path / "m1.png").exists() and (tmp_path / "m1.lightcraft.json").exists()
    with pytest.raises(RuntimeError, match="없습니다"):
        lc.photo_grade({"id": "m2", "src": str(tmp_path / "x.jpg")}, tmp_path / "m2.png", tmp_path)
