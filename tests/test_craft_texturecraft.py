"""TextureCraft 어댑터(scripts/craft/adapters/texturecraft.py) — OBJ 세우기 · 카메라 맞추기 · 재질 규칙은 앱 없이,
재질 · 렌더는 TextureCraft 가 설치됐을 때만."""
from __future__ import annotations

import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import texturecraft as tc  # noqa: E402

HAS_APP = (ROOT / "tools" / "crafts" / "texturecraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="TextureCraft 가 설치되지 않음")

CUBE = """mtllib x.mtl
o Body1
v 0 0 0
v 10 0 0
v 10 20 0
v 0 20 0
v 0 0 30
v 10 0 30
v 10 20 30
v 0 20 30
vn 0 -1 0
usemtl Body1
f 1 2 6 5
o Body2
v 0 0 30
v 1 1 31
v 0 1 30
f 9 10 11
"""


def test_to_y_up_axes_and_sets(tmp_path):
    src, dst = tmp_path / "a.obj", tmp_path / "b.obj"
    src.write_text(CUBE, "utf-8")
    box = tc.to_y_up(src, dst, stage=False)
    assert box["bodies"] == ["Body1", "Body2"]                  # usemtl 없는 몸체도 제 세트
    assert box["min"] == [0, 0, -20] and box["max"] == [10, 31, 0]   # 높이(Z 30)가 Y 로, 앞(-Y)이 +Z 로
    text = dst.read_text("utf-8")
    assert "mtllib" not in text and "usemtl Body2" in text
    assert "vn 0 0 1" in text                                   # 앞 법선(-Y) → +Z(카메라 쪽)
    tc.to_y_up(src, dst, stage=True)
    assert "o Stage" in dst.read_text("utf-8")


def test_fit_distance_fills_frame():
    lo, hi = [-40, 0, -25], [40, 32, 25]
    _, d1 = tc.fit_distance(lo, hi, [30], 18, 28, 9 / 16, 0.8)
    _, d2 = tc.fit_distance(lo, hi, [30], 18, 28, 9 / 16, 0.4)
    assert 1.8 < d2 / d1 < 2.2                                  # 반만 채우면 두 배 멀리
    _, dt = tc.fit_distance(lo, hi, [0, 30, 90, 135], 18, 28, 9 / 16, 0.8)
    assert dt >= d1 - 1e-6                                      # 턴테이블은 모든 각도를 담는다
    # 카메라 식 확인: 거리 d 에서 가운데 높이 fill 비율의 물체
    _, d = tc.fit_distance([-1, -50, -1], [1, 50, 1], [0], 0, 28, 9 / 16, 0.5)
    assert abs(50 / (d - 1) - 0.5 * math.tan(math.radians(14))) < 1e-3


def test_material_rules():
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "cap", "material": "#111827", "finish": "matte"},
            "Body3": {"role": "screen", "material": "#0b0f17", "fixed": True}}
    b = ["Body1", "Body2", "Body3"]
    r = tc._materials({"material": "wood"}, b, meta)
    assert r["Body1"] == "wood" and r["Body2"]["color"] == "#111827" and r["Body3"] == "#0b0f17"
    r = tc._materials({"material": {"cap": "#ff0000", "Body3": "gold"}}, b, meta)
    assert r["Body1"] == tc.DEFAULT and r["Body2"]["color"] == "#ff0000" and r["Body3"] == "gold"   # 이름으로 콕 집으면 고정 부품도
    r = tc._materials({"material": {"*": "wood"}}, b, meta)
    assert r["Body1"] == "wood" and r["Body3"] == "#0b0f17"                                        # "*" 는 고정 부품 빼고
    r = tc._materials({"material": "metal", "color": "#0f766e"}, b, meta)
    assert r["Body1"] == {"color": "#0f766e", "roughness": tc.CLEAN["metal"][1], "metallic": 1.0}
    assert tc._surface_steps("metal")[0]["id"] == "layer.add.fill"            # 쉬운 금속 이름: 무늬 없는 PBR
    assert tc._surface_steps("wood")[0]["params"]["material"] == "wood_oak"
    assert tc._surface_steps("iron_rusted")[0]["params"]["material"] == "iron_rusted"


def test_logo_ink_and_aspect():
    assert tc._ink("#ffffff") == "#1f2937" and tc._ink("#111827") == "#ffffff"
    assert tc._ink("wood_walnut") == "#ffffff" and tc._ink("metal") == "#1f2937"
    assert tc._aspect({"text": "FLUMA"}) > tc._aspect({"text": "플루"})


@app
def test_shot_on_builtin_mesh(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    obj = tmp_path / "box.obj"
    obj.write_text(CUBE.split("o Body2")[0] + "f 1 4 3 2\nf 5 6 7 8\nf 2 3 7 6\nf 3 4 8 7\nf 4 1 5 8\n", "utf-8")
    info = tc.shot(obj, tmp_path / "s.png", tmp_path, {"material": "#ef4444", "logo": "가", "width": 180, "height": 320, "samples": 0})
    assert info["as"] == "image" and info["texture_sets"] == ["Body1", "Stage"]
    with Image.open(tmp_path / "s.png") as im:
        assert im.size == (180, 320)
        px = im.convert("RGB").getpixel((90, 150))
        assert px[0] > px[1] + 40                                # 가운데에 빨간 상자
    with pytest.raises(RuntimeError, match="모르는 재질"):
        tc.shot(obj, tmp_path / "t.png", tmp_path, {"material": "no_such_material", "width": 90, "height": 160})


@app
def test_mcp_client_reports_errors(tmp_path):
    with tc.Mcp([materials.cli("texturecraft"), "mcp", "--read-root", tmp_path, "--write-root", tmp_path], tmp_path) as s:
        with pytest.raises(RuntimeError):
            s.call("project_open", {"path": "없는파일.tcraft"})
