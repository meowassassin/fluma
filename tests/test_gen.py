"""실사 생성 프롬프트(이미지 먼저 → 영상) · 느낌 단계 — 생성 모델은 부르지 않는다"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import feel  # noqa: E402
import genclip  # noqa: E402
import shotplan  # noqa: E402

SPEC = {"id": "walk", "scene": 1, "gen": "seedance", "image_model": None, "subject": [], "action": "a ginger cat walks along a rainy window ledge",
        "beats": [{"t": "0-0.5s", "what": "hold (cut handle)"}, {"t": "0.5-3.5s", "what": "the cat walks"}, {"t": "3.5-4s", "what": "settle (cut handle)"}],
        "setting": "a quiet apartment at dusk", "camera": "slow push-in", "framing": "wide shot", "lens": "24mm wide lens",
        "lighting": "hazy backlight", "color": "pastel pink", "mood": "dreamy", "style": "dreamy photorealism", "dialogue": None,
        "audio": "no music", "duration": 3, "request_sec": 4, "aspect": "9:16", "keyframe": None, "first_frame": None, "references": []}

GOOD_FEEL = {"route": "mixed", "route_why": "창가 컷은 실제 자료가 없음", "gen_scenes": [2], "options": [
    {"name": "현실", "why": "w", "style_en": "documentary", "mood_en": "calm", "color_en": "natural", "lighting_en": "daylight", "grade": {"temp": 0.05}},
    {"name": "몽환", "why": "w", "style_en": "dreamy", "mood_en": "soft", "color_en": "pastel", "lighting_en": "glow", "grade": {"bloom": 0.7, "lift": 0.3}}]}


def test_gen_materials_only_video_with_gen():
    sb = {"scenes": [{"materials": [{"type": "video", "src": "a.mp4"}, {"id": "walk", "type": "video", "gen": "seedance"}]},
                     {"materials": [{"type": "photo", "gen": "x"}]}]}
    got = genclip.gen_materials(sb)
    assert [(i, m["id"]) for i, m in got] == [(0, "walk")] and genclip.has_generated(sb)
    assert not genclip.has_generated({"scenes": [{"materials": [{"type": "video"}]}]})


def test_image_prompt_is_a_still_with_three_different_variants():
    ps = [shotplan.compile_image(SPEC, "midjourney", k)["prompt"] for k in range(3)]
    assert len(set(ps)) == 3                                   # 설계대로 · 더 가까이 · 다른 각도
    assert all("--ar 9:16" in p and "--no text" in p for p in ps)
    nb = shotplan.compile_image(SPEC, None, 0)                  # seedance 의 짝 = seedream
    assert nb["model"] == "seedream" and "No text" in nb["prompt"] and "9:16" in nb["prompt"]


def test_video_prompt_switches_to_motion_after_keyframe_upload():
    t2v = shotplan.compile_prompt(SPEC, "kling", 0)
    i2v = shotplan.compile_prompt({**SPEC, "keyframe": "data/public/uploads/x/walk.png", "first_frame": "data/public/uploads/x/walk.png"}, "kling", 0)
    assert not t2v["i2v"] and i2v["i2v"]
    assert "pastel pink" in t2v["prompt"] and "pastel pink" not in i2v["prompt"]          # 겉모습은 그림이 정한다
    assert "input image" in i2v["prompt"] and "slow push-in" in i2v["prompt"]
    assert "data/public/uploads/x/walk.png" in i2v["references"]


def test_seedance_starts_from_uploaded_keyframe():
    r = shotplan.compile_prompt({**SPEC, "keyframe": "k.png", "first_frame": "k.png"}, "dreamina", 0)
    assert r["model"] == "seedance" and "Start from [Image 1] as the first frame." in r["prompt"]


def test_sora_is_marked_unavailable():
    assert "error" in shotplan.compile_prompt(SPEC, "sora", 0)


def test_feel_check_and_filters():
    assert feel.check(GOOD_FEEL) == ([], [])
    bad = json.loads(json.dumps(GOOD_FEEL))
    bad["options"][1]["grade"] = {"temp": 0.05}
    bad["options"][0]["mood_en"] = ""
    bad["route"] = "maybe"
    errs = feel.check(bad)[0]
    assert any("route" in e for e in errs) and any("mood_en" in e for e in errs) and any("같은 안" in e for e in errs)
    assert feel.vf({}) == "" and "gblur" in feel.vf({"bloom": 0.5}) and "noise" in feel.vf({"grain": 0.4}) and "hue=s=0" in feel.vf({"mono": True})


def test_feel_reaches_gen_prompts():
    sb = {"id": "t", "direction": {"feel": {"name": "몽환", "style_en": "dreamy photorealism", "mood_en": "soft", "color_en": "pastel haze", "lighting_en": "glow"}}}
    assert shotplan.feel_of(sb)["style_en"] == "dreamy photorealism"
