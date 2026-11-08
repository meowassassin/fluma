"""Fluma 핵심 규칙 테스트 — 네트워크 · 모델 없이 도는 순수 로직만(말투 잠금 · 말끝 처리 · 목소리 거리 · 관문 · 검사 · 키 순서).

  .venv/bin/python -m pytest -q tests
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
def test_tone_edit_allows_ending_change():
    import tone_edit
    ok, bad = tone_edit.check("이번엔 노트북 하나가 뚫렸고, 서버까지 들어갔고요.", "이번엔 노트북 하나가 뚫렸고요, 서버까지 들어간 거예요.")
    assert ok and not bad


def test_tone_edit_refuses_content_rewrite():
    import tone_edit
    ok, bad = tone_edit.check("범인은 또 북한이고요, FBI가 공식으로 확인까지 해 줬습니다.",
                              "범인은 북한 해킹 조직이라고 FBI가 확인해 줬는데, 박수 칠 일은 아니고요.")
    assert not ok and any("박수" in b for b in bad)


# ---------- 말끝 처리: 합성할 때만 쉼표 → 마침표, 단어 글자는 원문으로 ----------
def test_tts_text_period_mode():
    import tts
    assert tts.tts_text("확인해 줬는데, 박수 칠 일은 아니고요.", "period") == "확인해 줬는데. 박수 칠 일은 아니고요."
    assert tts.tts_text("그대로, 둡니다.", "keep") == "그대로, 둡니다."
    assert tts.tts_text("그대로, 둡니다.", None) == "그대로, 둡니다."


# ---------- 목소리 특징: 구절 나누기 · 거리 ----------
def test_segs_from_words_uses_text_punctuation_when_engine_drops_it():
    import voice_profile as vp
    words = [{"text": "안녕", "startMs": 0, "endMs": 400}, {"text": "하세요", "startMs": 400, "endMs": 900},
             {"text": "반가워요", "startMs": 1100, "endMs": 1800}]
    segs = vp.segs_from_words(words, "안녕 하세요, 반가워요.")
    assert len(segs) == 2 and segs[0]["end"] == pytest.approx(0.9)


def test_voice_distance_zero_for_identical_and_grows():
    import voice_profile as vp
    ref = {"f0_median": 150.0, "range_st": 10.0, "end_drop_st": -1.0, "energy_sd_db": 6.0}
    assert vp.distance(ref, dict(ref)) == 0
    higher = {**ref, "f0_median": 150.0 * 2 ** (2 / 12)}   # 2반음 높음
    assert vp.distance(ref, higher) == pytest.approx(2.0, abs=0.05)


def test_f0_track_finds_pitch_of_a_tone(tmp_path):
    import voice_profile as vp
    sr = vp.SR
    t = np.arange(int(sr * 1.5)) / sr
    x = (0.4 * np.sin(2 * np.pi * 140 * t)).astype(np.float32)
    f0, _db = vp.f0_track(x)
    v = f0[f0 > 0]
    assert len(v) > 50 and abs(np.median(v) - 140) < 6


# ---------- 채널 카드: 문장 끝 · 문장 나누기 · 언어 ----------
def test_channel_ending_and_language():
    import ref_channel as rc
    assert rc.ending_of("서버까지 들어간 거예요.") == "예요"
    assert rc.ending_of("공짜로 풀고 있습니다.") == "습니다"
    assert rc.is_korean("근데 이게 끝이 아니었다고 하더라고요")
    assert not rc.is_korean("this is a cooking video with no talking")


def test_channel_sentences_split_on_punctuation():
    import ref_channel as rc
    segs = [{"start": 0, "end": 3, "text": "", "words": [{"w": "첫", "s": 0, "e": 0.5}, {"w": "문장입니다.", "s": 0.5, "e": 1.2},
                                                         {"w": "둘째", "s": 1.4, "e": 2}, {"w": "문장이고요.", "s": 2, "e": 3}]}]
    out = rc.sentences(segs)
    assert [s["text"] for s in out] == ["첫 문장입니다.", "둘째 문장이고요."]


# ---------- 관문: 의도 · 시안 해시 ----------
def test_gate_draft_hash_ignores_narration_but_not_screen():
    import gate
    sb = {"scenes": [{"narration": "가", "visual": {"kind": "x"}, "screen": "짤"}, {"narration": "나"}, {"narration": "다"}]}
    h0 = gate.draft_hash(sb)
    sb["scenes"][0]["narration"] = "어미만 바꿈"
    assert gate.draft_hash(sb) == h0
    sb["scenes"][0]["screen"] = "실제 화면"
    assert gate.draft_hash(sb) != h0


def test_gate_intent_hash_needs_summary():
    import gate
    assert gate.intent_hash({}) is None
    assert gate.intent_hash({"intent": {"summary": "누구에게 무엇을"}})


# ---------- 검사: 채널과 화면 구성 비교 ----------
def test_structure_tells_flags_article_heavy_script(monkeypatch):
    import lint
    ch = {"channel": "C", "lang": "ko", "structure": {"screens": {"실제 화면": 0.8, "짤": 0.2}, "lead": "말"}, "jokes": [{"line": "x"}], "joke_rate_per_10s": 0}
    monkeypatch.setattr(lint, "channel_card_of", lambda sb: ch)
    sb = {"scenes": [{"screen": "기사", "sec": 5}, {"screen": "기사", "sec": 5}, {"screen": "짤", "sec": 5}]}
    codes = [c for c, _ in lint.structure_tells(sb)]
    assert "L21" in codes and "T21" in codes


def test_structure_tells_music_led_channel_warns_on_heavy_narration(monkeypatch):
    import lint
    ch = {"channel": "C", "lang": "other", "structure": {"screens": {"음식": 1.0}, "lead": "음악 · 화면"}, "jokes": []}
    monkeypatch.setattr(lint, "channel_card_of", lambda sb: ch)
    sb = {"scenes": [{"screen": "음식", "sec": 5, "narration": "가" * 60}]}
    assert "T24" in [c for c, _ in lint.structure_tells(sb)]


# ---------- 키: 환경 변수 → 설정 화면 파일 → .env.local ----------
def test_apikeys_order(tmp_path, monkeypatch):
    import apikeys
    kf = tmp_path / "api-keys.json"
    kf.write_text(json.dumps({"FLUMA_TEST_KEY": "from-file"}), encoding="utf-8")
    monkeypatch.setattr(apikeys, "KEY_FILE", kf)
    monkeypatch.setattr(apikeys, "ROOT", tmp_path)          # .env.local 없음
    monkeypatch.delenv("FLUMA_TEST_KEY", raising=False)
    assert apikeys.get("FLUMA_TEST_KEY") == "from-file"
    monkeypatch.setenv("FLUMA_TEST_KEY", "from-env")
    assert apikeys.get("FLUMA_TEST_KEY") == "from-env"
    monkeypatch.delenv("FLUMA_TEST_KEY")
    kf.unlink()
    assert apikeys.get("FLUMA_TEST_KEY") == ""


# ---------- 스키마: 저장소의 예시 콘티가 스키마를 통과 ----------
def test_storyboard_schema_accepts_intent_and_screen():
    import jsonschema
    schema = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    assert "intent" in props and "screen" in schema["$defs"]["scene"]["properties"]
    jsonschema.Draft202012Validator.check_schema(schema)
