"""그림 시안 → 사용자가 고름 → 그 그림으로 영상 — 가짜 오픈라우터로 처음부터 끝까지(키 · 돈 없이)"""
import json
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import catalog  # noqa: E402
import feel  # noqa: E402
import genclip  # noqa: E402
import openrouter as OR  # noqa: E402
from test_providers import RAW  # noqa: E402

SID = "2099-01-01-gentest-01"
SB = {"id": SID, "title": "t", "scenes": [{"sec": 4, "beat": "b", "materials": [{"id": "walk", "type": "video", "gen": "seedance", "prompt": "a cat walks on a ledge", "gen_sec": 3}]}]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    raw = {**RAW, "at": time.time()}
    (tmp_path / "models.json").write_text(json.dumps(raw))
    (tmp_path / "settings.json").write_text(json.dumps({"models": {"make.image": "bytedance-seed/seedream-5-0-lite", "make.video": "google/veo-3.1-lite"}}))
    monkeypatch.setattr(catalog, "CACHE", tmp_path / "models.json")
    monkeypatch.setattr(catalog, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(catalog, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(catalog, "estimate_image", lambda m, n=1: 0.03 * n)
    monkeypatch.setattr(feel, "STORE", tmp_path / "feel")
    monkeypatch.setattr(OR, "key", lambda: "sk-or-test")
    calls = []

    def make_image(model, prompt, out, aspect="9:16", refs=None, **k):
        p = Path(out).with_suffix(".png"); p.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (90, 160), (200, 100, 50)).save(p)
        calls.append(("image", prompt))
        return {"file": p, "cost": 0.03}
    monkeypatch.setattr(OR, "make_image", make_image)
    monkeypatch.setattr(OR, "video_submit", lambda *a, **k: calls.append(("video", k)) or {"id": "job9", "status": "pending"})
    monkeypatch.setattr(OR, "video_wait", lambda job, **k: {"status": "completed", "usage": {"cost": 0.18}})
    monkeypatch.setattr(OR, "video_download", lambda job, out, index=0: (out.parent.mkdir(parents=True, exist_ok=True), out.write_bytes(b"mp4"), out)[2])
    yield calls
    for d in (ROOT / "data" / "compositions" / SID, ROOT / "data" / "public" / "uploads" / SID):
        shutil.rmtree(d, ignore_errors=True)
    (ROOT / "data" / "storyboards" / f"{SID}.json").unlink(missing_ok=True)


def test_keyframes_then_pick_then_video(world):
    keys = genclip.make_keys(SB, n=3)
    assert len(keys) == 3 and len({p for k, p in world if k == "image"}) == 3          # 시안 3장은 서로 다른 프롬프트
    with pytest.raises(SystemExit):
        genclip.run(SB)                                                              # 고르기 전엔 영상을 만들지 않는다
    genclip.pick_key(SB, "walk", 2)
    out = genclip.run(SB)
    v = next(k for kind, k in world if kind == "video")
    assert v["first_frame"].name.startswith("walk") and v["duration"] == 4 and v["aspect"] == "9:16"
    assert out == [f"data/public/uploads/{SID}/walk.mp4"]
    assert catalog.spent(SID) == pytest.approx(0.09 + 0.18)                          # 실제 비용이 장부에
    jobs = json.loads((ROOT / "data" / "compositions" / SID / "gen" / "jobs.json").read_text())
    assert jobs["walk"]["status"] == "downloaded"


def test_feel_drawn_preview_becomes_keyframe(world):
    d = {"route": "mixed", "route_why": "w", "gen_scenes": [1], "scene_en": "a cat on a ledge", "for_mid": "walk", "options": [
        {"name": "현실", "why": "w", "style_en": "documentary", "mood_en": "calm", "color_en": "natural", "lighting_en": "day", "grade": {"temp": 0.1}},
        {"name": "몽환", "why": "w", "style_en": "dreamy", "mood_en": "soft", "color_en": "pastel", "lighting_en": "glow", "grade": {"bloom": 0.6}}]}
    made = feel.generate(SID, d)
    assert len(made) == 2 and all(made)
    assert feel.generate(SID, d) == made and sum(1 for k, _ in world if k == "image") == 2   # 같은 시안은 다시 그리지 않는다
    feel.STORE.mkdir(parents=True, exist_ok=True)
    (feel.STORE / f"{SID}.json").write_text(json.dumps(d))
    sbp = ROOT / "data" / "storyboards" / f"{SID}.json"
    sbp.parent.mkdir(parents=True, exist_ok=True)
    sbp.write_text(json.dumps(SB))
    import subprocess
    r = subprocess.run([sys.executable, "-c", f"""
import sys; sys.path.insert(0, 'engine'); import paths, feel, json
from pathlib import Path
feel.STORE = Path({str(feel.STORE)!r})
sys.argv = ['feel', 'pick', '{SID}', '2', {str(sbp)!r}]
feel.main()"""], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (ROOT / "data" / "public" / "uploads" / SID / "walk.png").exists()          # 고른 그린 시안 = 영상의 첫 프레임
    assert json.loads(sbp.read_text())["direction"]["feel"]["name"] == "몽환"
