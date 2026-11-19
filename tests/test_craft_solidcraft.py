"""SolidCraft 어댑터(engine/craft/adapters/solidcraft.py) — model3d.
계산(형태 명령 · 상자 · 재질 규칙)은 앱 없이, 렌더는 SolidCraft · TextureCraft 가 설치됐을 때만."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import materials  # noqa: E402
from craft.adapters import solidcraft as sc  # noqa: E402

HAS = lambda a: (ROOT / "tools" / "crafts" / a / "installed.json").exists()   # noqa: E731
app = pytest.mark.skipif(not HAS("solidcraft"), reason="SolidCraft 가 설치되지 않음")
app_tc = pytest.mark.skipif(not (HAS("solidcraft") and HAS("texturecraft")), reason="SolidCraft · TextureCraft 가 설치되지 않음")


# ---------------------------------------------------------------- 앱 없이
def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["model3d@solidcraft"] is sc.model3d
    assert ad["model3d"] is sc.model3d                               # 기본도 SolidCraft(Blender 는 2026-11-11 제거)


def test_builtin_shapes_and_aliases():
    for name in sc.SHAPES:
        cmds, meta, moves = sc.shape_commands({"shape": name})
        assert cmds and all("command" in c for c in cmds)
        assert moves and all(mv["occurrence"] in meta for mv in moves)      # 분해 이동은 있는 몸체만
    cmds, meta, _ = sc.shape_commands({"shape": "텀블러", "size": [70, 120]})
    assert meta["Body2"]["role"] == "lid"
    with pytest.raises(RuntimeError, match="내장 형태"):
        sc.shape_commands({"shape": "우주선"})


def test_size_reaches_commands():
    cmds, _, _ = sc.shape_commands({"shape": "case", "size": [100, 60, 40]})
    rect = next(c for c in cmds if c["command"] == "sketch.rectangle.rounded")
    assert rect["params"]["p0"] == [-50, -30] and rect["params"]["p1"] == [50, 30]


def test_src_and_commands(tmp_path):
    step = tmp_path / "a.step"
    step.write_text("ISO-10303-21;", "utf-8")
    assert sc.shape_commands({"src": str(step)})[0][0]["command"] == "file.insert_step"
    glb = tmp_path / "a.glb"
    glb.write_bytes(b"glTF")
    c = sc.shape_commands({"src": str(glb)})[0][0]
    assert c["command"] == "file.insert_mesh" and c["params"]["up"] == "y"
    with pytest.raises(RuntimeError, match="없습니다"):
        sc.shape_commands({"src": str(tmp_path / "none.stl")})
    own = [{"id": "sketch.create", "params": {"plane": "XY"}}]
    assert sc.shape_commands({"commands": own})[0] == [{"command": "sketch.create", "params": {"plane": "XY"}}]


def test_looks_rules():
    _, meta, _ = sc.shape_commands({"shape": "bottle"})
    looks = {c["params"]["bodies"][0]: c["params"] for c in sc._looks({"material": "#16a34a"}, meta)}
    assert looks["Body1"]["color"] == "#16a34a" and looks["Body2"]["color"] == "#111827"   # 재질 하나는 본체에만
    looks = {c["params"]["bodies"][0]: c["params"] for c in sc._looks({"material": "metal", "color": "#0f766e"}, meta)}
    assert looks["Body1"]["color"] == "#0f766e" and looks["Body1"]["pbr"]["metallic"] == 1.0  # 색 + 금속 = 아노다이징
    assert set(looks["Body1"]["pbr"]) == {"metallic", "roughness", "dielectric_ior"}


def test_exploded_box(tmp_path):
    obj = tmp_path / "a.obj"
    obj.write_text("o Body1\nv 0 0 0\nv 10 10 10\no Body2\nv 0 0 10\nv 10 10 12\n", "utf-8")
    assert sc._boxes(obj)["Body2"] == ([0, 0, 10], [10, 10, 12])
    lo, hi = sc._exploded_box(obj, [{"occurrence": "Body2", "translate": [0, 0, 20]}], 0)
    assert lo == [0, 0, 0] and hi == [10, 10, 32]


# ---------------------------------------------------------------- 앱으로
@app_tc
def test_model3d_still_with_logo(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    m = {"id": "m1", "type": "model3d", "shape": "case", "material": "metal", "color": "#1e3a8a", "logo": "FLUMA",
         "width": 270, "height": 480, "samples": 8}
    info = sc.model3d(m, tmp_path / "m1.png", tmp_path)
    assert info["as"] == "image" and info["apps"] == ["solidcraft", "texturecraft"]
    assert (tmp_path / "m1.sc").exists() and (tmp_path / "m1.tcraft").exists()
    assert set(info["texture_sets"]) == {"Body1", "Body2", "Stage"}
    with Image.open(tmp_path / "m1.png") as im:
        assert im.size == (270, 480)
        px = im.convert("RGB").getpixel((135, 260))
        assert px[2] > px[0] + 20                       # 가운데에 파란 케이스


@app_tc
def test_model3d_turntable_mp4(tmp_path):
    m = {"id": "m2", "type": "model3d", "shape": "puck", "turntable": True, "sec": 1, "fps": 12, "width": 180, "height": 320}
    info = sc.model3d(m, tmp_path / "m2.png", tmp_path)
    assert info["file_suffix"] == ".mp4" and info["as"] == "video" and info["frames"] == 12
    assert (tmp_path / "m2.mp4").stat().st_size > 1000 and (tmp_path / "m2.png").exists()


@app
def test_model3d_exploded_mp4(tmp_path):
    m = {"id": "m3", "type": "model3d", "shape": "phone", "exploded": True, "sec": 0.5, "fps": 20, "width": 180, "height": 320}
    info = sc.model3d(m, tmp_path / "m3.png", tmp_path)
    assert info["file_suffix"] == ".mp4" and info["parts"] == ["Body1", "Body2", "Body3"]
    assert info["frames"] % 2 == 1 and (tmp_path / "m3.mp4").exists()


@app
def test_model3d_exploded_needs_parts(tmp_path):
    cmds = [{"command": "sketch.create", "params": {"plane": "XY"}},
            {"command": "sketch.circle.center", "params": {"center": [0, 0], "radius": 10}},
            {"command": "solid.extrude", "params": {"distance": 5}}]
    with pytest.raises(RuntimeError, match="둘 이상"):
        sc.model3d({"id": "m4", "commands": cmds, "exploded": True}, tmp_path / "m4.png", tmp_path)
    d = json.loads((tmp_path / "m4.solid.json").read_text("utf-8"))
    assert d["commands"][0]["command"] == "sketch.create"
