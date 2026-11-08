"""범용 Craft 재료(engine/craft/adapters/craft_script.py) — type: craft.
검사(명령 id · 경로 · 참조)는 앱 없이, 실제 실행은 그 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import materials  # noqa: E402
from craft.adapters import craft_script as cs  # noqa: E402

HAS = lambda a: (ROOT / "tools" / "crafts" / a / "installed.json").exists()   # noqa: E731
CATALOG = (ROOT / ".claude" / "skills" / "crafts" / "catalog" / "vectorcraft.jsonl").exists()
need_catalog = pytest.mark.skipif(not CATALOG, reason="Craft 명령 목록(catalog)이 없음")
PNG = "data/workspace/tmp/test-craft-script/capture.png"   # 저장소 안 시험용 캡처(사용자 영상 파일에 기대지 않는다)


@pytest.fixture(autouse=True, scope="module")
def _capture_png():
    f = ROOT / PNG
    if not f.exists():
        from PIL import Image, ImageDraw
        f.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (900, 600), (24, 28, 36))
        d = ImageDraw.Draw(im)
        for i in range(12):
            d.rectangle([40, 40 + i * 44, 40 + 60 * (i % 7 + 4), 68 + i * 44], fill=(90 + i * 10, 140, 210))
        im.save(f)
    yield


def app(name):
    return pytest.mark.skipif(not HAS(name), reason=f"{name} 가 설치되지 않음")


@pytest.fixture
def work(tmp_path):
    return tmp_path


def ctx(work, app_="vectorcraft"):
    c = cs.Ctx({"id": "m1", "app": app_, "steps": []}, work / "m1.png", work)
    c.dir.mkdir(parents=True, exist_ok=True)
    return c


# ---------------------------------------------------------------- 앱 없이
def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["craft"] is cs.craft


def test_unknown_app():
    with pytest.raises(RuntimeError, match="모르는 앱"):
        cs.validate({"app": "nocraft", "steps": []})


@need_catalog
def test_unknown_id_suggests():
    with pytest.raises(RuntimeError) as e:
        cs.validate({"app": "vectorcraft", "steps": [{"id": "shape.rectangle"}, {"id": "shape.rect", "params": {}}]})
    assert "2번째" in str(e.value) and "shape.rectangle" in str(e.value)


@need_catalog
def test_validate_forms():
    s = cs.validate({"app": "pdfcraft", "steps": [{"tool": "doc_save", "args": {"doc": 1}}, "doc_list"]})
    assert s == [{"id": "doc_save", "params": {"doc": 1}}, {"id": "doc_list", "params": {}}]
    with pytest.raises(RuntimeError, match="params"):
        cs.validate({"app": "pdfcraft", "steps": [{"id": "doc_list", "params": [1]}]})


def test_paths_read_inside_root(work):
    c = ctx(work)
    p = cs.fix_paths({"path": PNG, "text": "a/b 그대로"}, c, "file.place")
    assert p["path"] == str((ROOT / PNG).resolve()) and p["text"] == "a/b 그대로"
    for bad in ("/etc/passwd", "../../../etc/hosts", "~/.ssh/id_rsa"):
        with pytest.raises(RuntimeError, match="밖"):
            cs.fix_paths({"path": bad}, c, "file.place")
    with pytest.raises(RuntimeError, match="밖"):                 # 키 이름이 낯설어도 절대 경로는 검사
        cs.fix_paths({"whatever": "/etc/passwd"}, c, "x.y")


def test_paths_write_inside_work(work):
    c = ctx(work)
    p = cs.fix_paths({"path": "data/out/a.png"}, c, "file.export")
    assert Path(p["path"]).is_relative_to(work.resolve())
    p = cs.fix_paths({"path": "$FRAMES"}, c, "motion.export_animation")
    assert p["path"] == str(c.frames.resolve())
    with pytest.raises(RuntimeError, match="작업 폴더 밖"):
        cs.fix_paths({"path": "../../x.png"}, c, "file.export")
    with pytest.raises(RuntimeError, match="작업 폴더 밖"):
        cs.fix_paths({"path": str(ROOT / "README.md")}, c, "file.save")


def test_refs_shift_and_resolve(work):
    assert cs.shift_refs({"id": "$0.id", "ids": ["$2.ids", "$$1"], "t": "x $1"}, 1) == {"id": "$1.id", "ids": ["$3.ids", "$$1"], "t": "x $1"}
    c = ctx(work, "filmcraft")
    res = [{"sequence": 7}, {"items": [8]}, {"clips": [12, 13]}]
    assert cs.resolve_refs({"item": "$0.items.0", "clips": "$1.clips", "c": "$last.clips.1"}, res, 1, c, 2) == {"item": 8, "clips": [12, 13], "c": 13}
    with pytest.raises(RuntimeError, match="없습니다"):
        cs.resolve_refs("$0.nope", res, 1, c, 2)


def test_failed_step_messages(work):
    c = ctx(work)
    c.m["steps"] = [{"id": "shape.rectangle"}, {"id": "paint.setFill"}]
    c.offset = 1                                                   # 앞에 file.new 하나
    assert "2번째 명령 paint.setFill" in c.fail("", "error: step 2 (paint.setFill): bad", "run")      # 0부터 세는 앱
    c.offset = 0
    assert "2번째 명령 paint.setFill" in c.fail("", "error: step 2 (paint.setFill): bad", "run")      # 1부터 세는 앱
    so = '{"command":"a","ok":true}\n{"command":"b","ok":false,"error":"x"}\n'
    assert "2번째" in c.fail(so, "", "run")


# ---------------------------------------------------------------- 앱으로 실제 실행
def run(m, work):
    out = work / f"{m['id']}.png"
    info = cs.craft(m, out, work)
    assert info["app"] == m["app"] and info["steps_run"] == [s["id"] for s in m["steps"]]
    assert (ROOT / info["editable"]).exists()
    return out, info


def size(p):
    from PIL import Image
    with Image.open(p) as im:
        return im.size


@app("vectorcraft")
def test_vectorcraft(work):
    m = {"type": "craft", "id": "m1", "app": "vectorcraft", "steps": [
        {"id": "shape.rectangle", "params": {"x": 0, "y": 0, "width": 1080, "height": 1920}},
        {"id": "paint.setFill", "params": {"id": "$0.id", "color": "#223355"}},
        {"id": "text.create", "params": {"x": 540, "y": 900, "text": "시험", "size": 120, "font": "Noto Sans CJK KR", "color": "#ffffff", "justify": "center"}}]}
    out, info = run(m, work)
    assert size(out) == (1080, 1920) and info["editable"].endswith(".vectorcraft")


@app("vectorcraft")
def test_failure_names_step(work):
    m = {"type": "craft", "id": "m1", "app": "vectorcraft", "steps": [
        {"id": "shape.rectangle", "params": {"x": 0, "y": 0, "width": 10, "height": 10}},
        {"id": "paint.setFill", "params": {"id": "$0.nope", "color": "#fff"}}]}
    with pytest.raises(RuntimeError, match="2번째 명령 paint.setFill"):
        cs.craft(m, work / "m1.png", work)


@app("vectorcraft")
def test_still_to_video(work):
    m = {"type": "craft", "id": "m2", "app": "vectorcraft", "as": "video", "export": {"duration": 1, "fps": 10},
         "steps": [{"id": "shape.ellipse", "params": {"x": 100, "y": 100, "width": 300, "height": 300}}]}
    out, info = run(m, work)
    assert info["file_suffix"] == ".mp4" and out.with_suffix(".mp4").stat().st_size > 0


@app("effectcraft")
def test_effectcraft_video(work):
    m = {"type": "craft", "id": "m1", "app": "effectcraft", "new": {"duration": 1}, "export": {"format": "mp4", "end": 0.5, "time": 0.2},
         "steps": [{"id": "layer.newSolid", "params": {"name": "BG", "color": "#101018"}},
                   {"id": "anim.applyBuiltinPreset", "params": {"preset": "pulseRings", "layers": ["BG"]}}]}
    out, info = run(m, work)
    assert info["file_suffix"] == ".mp4" and out.with_suffix(".mp4").exists() and size(out) == (1080, 1920)


@app("filmcraft")
def test_filmcraft_refs(work):
    m = {"type": "craft", "id": "m1", "app": "filmcraft", "export": {"time": 0.5}, "steps": [
        {"id": "file.import", "params": {"paths": [PNG]}},
        {"id": "timeline.place", "params": {"item": "$0.items.0", "track": "V1", "seconds": 0, "insert": False, "audio": False}},
        {"id": "clip.fitToFrame", "params": {"clips": "$1.clips"}}]}
    out, _ = run(m, work)
    assert size(out) == (1080, 1920)


@app("photocraft")
def test_photocraft(work):
    m = {"type": "craft", "id": "m1", "app": "photocraft", "new": {"background": "#111418"}, "steps": [
        {"id": "file.placeEmbedded", "params": {"path": PNG, "scale": 90, "center": [540, 960]}},
        {"id": "type.create", "params": {"x": 540, "y": 300, "text": "시험", "align": "center", "font": "Noto Sans CJK KR", "size": 96, "color": "#ffffff"}}]}
    out, _ = run(m, work)
    assert size(out) == (1080, 1920)


@app("deckcraft")
def test_deckcraft(work):
    m = {"type": "craft", "id": "m1", "app": "deckcraft", "steps": [
        {"id": "insert.smartArt", "params": {"kind": "process", "items": ["하나", "둘", "셋"]}},
        {"id": "smartArt.layout", "params": {"kind": "verticalProcess"}}]}
    out, _ = run(m, work)
    assert size(out) == (1080, 1920)


@app("pdfcraft")
def test_pdfcraft(work):
    m = {"type": "craft", "id": "m1", "app": "pdfcraft", "new": {"from": "images", "paths": [PNG], "dpi": 72}, "export": {"dpi": 72},
         "steps": [{"id": "comment_add", "params": {"doc": 1, "page": 1, "type": "rectangle", "rect": [25, 120, 880, 240], "color": "red", "width": 5}}]}
    out, _ = run(m, work)
    assert size(out)[0] > 500


@app("wordcraft")
def test_wordcraft(work):
    m = {"type": "craft", "id": "m1", "app": "wordcraft", "steps": [
        {"id": "text.insert", "params": {"text": "환불 규정"}}, {"id": "select.text", "params": {"text": "환불"}},
        {"id": "format.highlight", "params": {"color": "yellow"}}]}
    out, _ = run(m, work)
    assert size(out) == (1080, 1920)


@app("soundcraft")
def test_soundcraft_is_audio_only(work):
    m = {"type": "craft", "id": "m1", "app": "soundcraft", "export": {"end": 1}, "steps": [
        {"id": "track.new", "params": {"kind": "audio", "format": "stereo", "name": "SFX"}},
        {"id": "file.import_audio", "params": {"path": "engine/voice/sfx/pop.wav", "track": "SFX", "at": 0, "new_tracks": False}}]}
    out, info = run(m, work)
    assert not out.exists() and info["media"] == "audio" and (ROOT / info["audio"]).exists()
    assert "file_suffix" not in info

