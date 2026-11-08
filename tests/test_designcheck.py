"""디자인 검사 · 아트 디렉션 · 최종본 관문"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "checks"))
import paths  # noqa: E402,F401
import designcheck as D  # noqa: E402
from craft import design, usage  # noqa: E402


def _video(tmp, vf, name="a.mp4", sec=3):
    f = tmp / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf, "-t", str(sec), "-pix_fmt", "yuv420p", str(f)], check=True)
    return f


def test_flat_still_video_is_flagged(tmp_path):
    v = _video(tmp_path, "color=c=#111111:s=540x960:r=24")
    codes = {x["code"] for x in D.findings(v, {"scenes": [{"sec": 3}]})}
    assert {"D10", "D11", "D12", "D15"} <= codes


def test_busy_moving_video_passes(tmp_path):
    v = _video(tmp_path, "testsrc2=s=540x960:r=24")
    codes = {x["code"] for x in D.findings(v, {"scenes": [{"sec": 3}]})}
    assert not codes & {"D10", "D11", "D12"}


def test_purple_default_is_flagged(tmp_path):
    v = _video(tmp_path, "color=c=#6c3ce7:s=540x960:r=24")
    assert "D14" in {x["code"] for x in D.findings(v, {"scenes": [{"sec": 3}]})}


def test_art_problems_and_apply():
    assert design.art_problems({}) == ["아트 디렉션이 없음"]
    sb = {"direction": {"subs": {"box": True}, "art": {"palette": {"bg": "#111111", "ink": "#eeeeee", "accent": "#ff5500"}, "rule": "r", "avoid": ["a"]}},
          "scenes": [{"materials": [{"type": "info_card"}, {"type": "chart", "accent": "#000000"}]}]}
    assert design.art_problems(sb) == []
    design.apply_art(sb)
    assert sb["direction"]["color_bg"] == "#111111" and sb["direction"]["subs"] == {"hot": "#ff5500", "box": True}
    assert sb["scenes"][0]["materials"][0]["accent"] == "#ff5500" and sb["scenes"][0]["materials"][1]["accent"] == "#000000"


def test_usage_record_counts_blender(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "ALL", {})
    usage.record("blender", {"loft", "render.eevee"})
    assert usage.ALL["blender"] == {"loft", "render.eevee"}


def test_blender_script_features_are_recorded(tmp_path, monkeypatch):
    from craft.adapters import blender
    monkeypatch.setattr(usage, "ALL", {})
    f = tmp_path / "x.py"
    f.write_text("import bpy\nimport fluma3d as F\ndef build(ctx):\n    F.loft([])\n    bpy.ops.mesh.primitive_plane_add()\n")
    blender._note_features(f, {"engine": "eevee"})
    assert {"render.eevee", "loft", "bpy.ops.mesh.primitive_plane_add"} <= usage.ALL["blender"]


def test_fonts_install_copies_repo_fonts(tmp_path):
    sys.path.insert(0, str(ROOT / "engine" / "core"))
    import fonts
    assert fonts.install(tmp_path) == len(fonts.FILES)
    assert fonts.install(tmp_path) == 0                  # 이미 있으면 건너뛴다


def test_intermediate_materials_stay_off_screen():
    from craft import motion
    mats = [{"id": "a", "file": "x/s01/a.png", "spec": {"steps": []}},
            {"id": "b", "file": "x/s01/b.png", "spec": {"steps": [{"params": {"path": "x/s01/a.png"}}]}},
            {"id": "c", "file": "x/s01/c.mp4", "spec": {"uses": {"n": "b"}}}]
    assert motion.input_materials(mats) == {"a", "b"}


def test_usage_reads_effect_names_in_scripts(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "ALL", {})
    f = tmp_path / "x.jsx"
    f.write_text('FX(a,"Directional Blur");', "utf-8")
    usage.note(["/x/effectcraft-cli", "script", str(f)], {})
    assert any("blur" in i.lower() for i in usage.ALL["effectcraft"])


def test_clause_subtitles_keep_sentences_and_no_orphan_word():
    from craft import motion
    ws = [{"text": w, "startMs": i * 400, "endMs": i * 400 + 380} for i, w in enumerate("전쟁이 끝나고 42킬로미터를 달려 승리를 외치고 숨진 병사.".split() + "마라톤의 기원입니다.".split())]
    r = motion.clause_chunks(ws, 22)
    assert all(len(c["text"].split()) >= 2 for c in r)
    assert r[-1]["text"] == "마라톤의 기원입니다."
    assert all(a["end"] == b["start"] for a, b in zip(r, r[1:]))



def test_retention_flags_monotony_and_passes_variety():
    import retention
    one = [{"sec": 5, "narration": "그냥 말", "materials": [{"type": "form", "form": "parchment"}]} for _ in range(5)]
    codes = {c for c, _, _ in retention.check({"scenes": one})}
    assert {"R01", "R02", "R05", "R06", "R07", "R09"} <= codes
    forms = ["parchment", "atlas", "gridchart", "comic", "sunset"]
    ok = [{"sec": 5, "narration": "왜 그럴까요?", "surprise": "x", "materials": [{"type": "form", "form": f}, {"type": "cast", "id": f"p{i}"}, {"type": "archive"}]} for i, f in enumerate(forms)]
    assert retention.check({"scenes": ok}) == []


def test_cast_makes_different_people_from_specs():
    from craft import cast
    a = cast.Fig({"beard": "full", "hat": "hoplite"}).pose("talk").steps()
    b = cast.Fig({"glasses": True, "garment": "suit"}).pose("talk").steps()
    assert a != b and len(cast.materials({"id": "k", "poses": ["run", "talk", "shock"]})) == 11


def test_geo_clips_real_coastline():
    from craft import geo
    polys, to = geo.land([20.5, 36.2, 24.6, 38.9], 1920, 1080)
    assert len(polys) >= 3 and sum(len(p) for p in polys) > 300
    x, y = to(23.73, 37.98)
    assert 0 < x < 1920 and 0 < y < 1080
