"""생성 클립(Dreamina 등) 흐름 — 구간 · 화면 비율 채우기 · 끝 처리 · 대사 소리 · 프롬프트 목록 · AI 표시 판정"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import genclip  # noqa: E402

ff = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")


def _clip(p: Path, sec: float = 4.0, w: int = 640, h: int = 360) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration={sec}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(p)], check=True)
    return p


def _sb(**kw) -> dict:
    sb = {"id": "2026-11-06-gentest-99", "title": "t", "aspect": "9:16",
          "cast": [{"name": "mina", "look": "short bob, blue tee", "ref": "public/uploads/x/mina.png"}],
          "scenes": [{"role": "hook", "sec": 4, "narration": "", "dialogue": "Hi there.",
                      "materials": [{"id": "walk", "type": "video", "gen": "dreamina", "prompt": "a woman walks", "cast": ["mina"], "dialogue": True}]},
                     {"role": "body", "sec": 3, "narration": "말", "materials": [{"id": "m1", "type": "text"}]}]}
    sb.update(kw)
    return sb


def test_span():
    assert genclip.span({"in": 1, "out": 3}, 10) == (1.0, 3.0)
    assert genclip.span({}, 5) == (0.0, 5)
    assert genclip.span({"out": 99}, 5) == (0.0, 5)
    with pytest.raises(RuntimeError):
        genclip.span({"in": 3, "out": 2}, 10)


def test_detect_and_dialogue():
    sb = _sb()
    assert genclip.has_generated(sb)
    assert [m["id"] for _, m in genclip.gen_materials(sb)] == ["walk"]
    assert genclip.dialogue_scene(sb, 0)["id"] == "walk"
    assert genclip.dialogue_scene(sb, 1) is None
    assert not genclip.has_generated({"scenes": [{"materials": [{"type": "video", "src": "a.mp4"}]}]})


def test_prompts_carry_cast_and_line():
    md = genclip.prompts(_sb())
    assert "9:16" in md and "short bob, blue tee" in md and "mina.png" in md and "Hi there." in md


@ff
def test_audio_pcm_length(tmp_path):
    f = _clip(tmp_path / "c.mp4")
    pcm = genclip.audio_pcm(f, 0.5, 2.5, 24000)
    assert len(pcm) == 2 * 24000 * 2


@ff
@pytest.mark.parametrize("end", ["slow", "freeze", "loop"])
def test_gen_clip_cover_and_end(tmp_path, end):
    from craft.materials import gen_clip
    f = _clip(tmp_path / "c.mp4", sec=3.0)
    out = tmp_path / "m.png"
    info = gen_clip({"id": "m", "gen": "dreamina", "in": 0.5, "out": 2.5, "end": end, "_W": 540, "_H": 960, "_sec": 4.0}, f, out)
    mp4 = out.with_suffix(".mp4")
    p = genclip.probe(mp4)
    assert (p["w"], p["h"]) == (540, 960)            # 세로 화면으로 가운데 잘라 채움
    assert not p["audio"]                             # 소리는 음성 단계가 넣는다
    assert 4.0 <= p["dur"] <= 6.5                      # 장면 길이 + 짧은 여유(예전 20초 아님)
    assert info["generated"] == "dreamina" and info["clip"]["fit"] == "cover"


# ---------------------------------------------------------------- 샷 설계(shotplan)
import shotplan  # noqa: E402


def test_color_words():
    assert shotplan.color_word("#0b1927") in ("navy", "deep navy", "deep blue")
    assert "grey" in shotplan.color_word("#333333") or "charcoal" in shotplan.color_word("#333333")
    assert "teal" in shotplan.color_word("#14c6d0") or "cyan" in shotplan.color_word("#14c6d0")


def test_spec_fields_and_handles():
    sb = _sb(aspect="9:16")
    s = shotplan.specs(sb)[0]
    assert s["request_sec"] == round(s["duration"] + shotplan.HEAD + shotplan.TAIL, 2)
    assert s["no_text"] and "lower third" in s["safe_zone"] and s["aspect"] == "9:16"
    assert s["dialogue"] == {"speaker": "mina", "line": "Hi there."}
    assert any("Hi there." in b["what"] for b in s["beats"])
    assert s["subject"] and "short bob" in s["subject"][0]


def test_continue_from_previous_same_cast():
    sb = _sb()
    sb["scenes"][1]["materials"] = [{"id": "walk2", "type": "video", "gen": "dreamina", "prompt": "she turns", "cast": ["mina"]}]
    s = shotplan.specs(sb)
    assert s[1]["first_frame"] and "walk" in s[1]["first_frame"]


@pytest.mark.parametrize("model,must", [
    ("seedance", ["Shot 1 |", "'s line (", "{Hi there.}", "No subtitles."]),
    ("kling", ['says: "Hi there."', "single unbroken shot"]),
    ("veo", ["says: Hi there.", "Audio:"]),
    ("omni", ["single continuous shot", "[0.5-", "Sound design:"]),
    ("wan", ["One continuous shot.", "Shot 1 [", "Negative prompt list:"]),
    ("hailuo", ["integrated_multimodal_description:", "<d>[English] Hi there.</d>"]),
])
def test_compile_model_syntax(model, must):
    s = shotplan.specs(_sb(aspect="9:16"))[0]
    r = shotplan.compile_prompt(s, model)
    for x in must:
        assert x in r["prompt"], (model, x, r["prompt"])
    assert r["settings"]["duration"] >= s["request_sec"] - 0.05 or r["notes"]


def test_compile_veo_negative_param_and_sora_closed():
    s = shotplan.specs(_sb())[0]
    assert "subtitles" in shotplan.compile_prompt(s, "veo")["negative"]
    assert "error" in shotplan.compile_prompt(s, "sora")
    assert shotplan.compile_prompt(s, "dreamina")["model"] == "seedance"


def test_variants_change_camera_and_framing():
    s = shotplan.specs(_sb())[0]
    a, b, c = (shotplan.compile_prompt(s, "kling", k)["prompt"] for k in range(3))
    assert a != b and a != c
