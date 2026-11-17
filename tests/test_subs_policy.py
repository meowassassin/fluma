"""말 자막 정책 — 구절형 기본 · 본문 화면글 띠 제한."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from craft import design, subs_policy  # noqa: E402
from craft import motion  # noqa: E402


def _words(text: str, ms: int = 200) -> list[dict]:
    out, t = [], 0
    for w in text.split():
        out.append({"text": w, "startMs": t, "endMs": t + ms})
        t += ms
    return out


def test_ko_speech_preset_defaults_clause():
    sb = {"language": "ko", "format": "concept", "preset": {"lead": "말", "layout": {"captions": {"chars": 9, "box": 0.6}}}}
    assert subs_policy.subs_mode(sb) == "clause"
    assert 18 <= subs_policy.subs_max_chars(sb) <= 34
    subs_policy.apply_preset_direction_subs(sb)
    assert sb["direction"]["subs"]["mode"] == "clause"


def test_clip_format_word_mode():
    sb = {"format": "clip", "language": "ko"}
    assert subs_policy.subs_mode(sb) == "word"


def test_screen_caption_hidden_on_body_with_speech():
    sc = {"role": "step", "caption": "스테이징 확인"}
    assert not subs_policy.show_screen_caption_band(sc, has_speech=True, screen_text=True)
    sc_hook = {"role": "hook", "caption": "3체크"}
    assert subs_policy.show_screen_caption_band(sc_hook, has_speech=True, screen_text=True)


def test_clause_chunks_longer_than_word_chunks():
    text = "배포 전에 스테이징에서 롤백 경로와 모니터 알림을 꼭 확인하세요"
    ws = _words(text)
    clauses = motion.clause_chunks(ws, 28)
    words = motion.chunks(ws, max_chars=13, max_words=4)
    assert len(clauses) <= len(words)          # 단어 자막도 꾸미는 말에서 끊지 않아(2026-11-16) 덩어리가 커졌다 — 구절 자막이 더 잘게 쪼개지지만 않으면 된다
    assert all(len(c["text"]) >= 10 for c in clauses)


def test_design_delivery_skips_text_pop_for_clause():
    sb = {
        "language": "ko",
        "format": "concept",
        "preset": {"lead": "말"},
        "meta": {"quality_tier": "delivery"},
        "direction": {"layout": "full", "art": {"palette": {"bg": "#111", "ink": "#fff", "accent": "#f00"}, "rule": "x", "avoid": "y"},
                   "subs": {"mode": "clause"}},
    }
    r = design.resolve(sb)
    assert r["text_pop"] is False


def test_speech_led_no_slow_voice():
    from craft import pace_policy

    sb = {"format": "concept", "preset": {"lead": "말", "speech_ratio": 0.87, "voice": {"cps": 7.7}}, "voice": {"speed": 0.86}}
    assert pace_policy.speech_led(sb)
    assert pace_policy.voice_speed(sb) >= 1.0
    pace_policy.apply_voice_pace(sb)
    assert sb["voice"]["speed"] >= 1.15


def test_grammar_infers_clause_subs():
    sb = {"language": "ko", "format": "fix", "preset": {"lead": "말"}, "direction": {}}
    g = motion.grammar(sb)
    assert g["subs"]["mode"] == "clause"
    assert g["subs"]["max_chars"] >= 18