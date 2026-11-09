"""배경 음악 넣을지 · 효과음 규칙 · 자동 목소리 우선순위(네트워크 없이)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import music_pick as M  # noqa: E402
import tts  # noqa: E402


def sb(**kw):
    return {"id": "t", "scenes": [{"narration": kw.pop("nar", "말이 있다"), "sec": 5}], **kw}


def test_decide_without_reference():
    assert M.decide(sb(format="clip"))[0] is False                 # 퍼온 클립 원음이 주인공
    assert M.decide(sb(nar=""))[0] is True                         # 나레이션 없으면 음악이 리듬
    assert M.decide(sb(format="emotional"))[0] is True
    use, why, _ = M.decide(sb())
    assert use and "작게" in why                                   # 설명형은 말 뒤에 작게


def test_user_choice_wins():
    assert M.decide(sb(music={"use": False}))[0] is False
    assert M.decide(sb(format="clip", music={"use": True}))[0] is True


def test_sfx_dropped_under_music():
    s = sb(music={"use": True, "src": "x.m4a"})
    assert not M.sfx_allowed(s, {"name": "pop"})
    assert M.sfx_allowed(s, {"name": "stamp", "keep": True})
    assert M.sfx_allowed(sb(), {"name": "pop"})
    s["direction"] = {"sfx_with_music": True}
    assert M.sfx_allowed(s, {"name": "pop"})


def test_free_detection():
    assert M.is_free({"title": "Good For You – THBD (No Copyright Music)", "by": "x"})
    assert M.is_free({"title": "Joyful", "by": "Audio Library"})
    assert not M.is_free({"title": "APT.", "by": "ROSÉ"})
    assert not M.is_free({"title": "[Free Music No Copyright] Undertale Lofi Mega Mix", "by": "x"})   # 남의 곡 고친 것
    assert not M.is_free({"title": "Calm (No Copyright Music)", "by": "x", "sec": 3600})             # 긴 모음
    assert M._core("Good For You – THBD (No Copyright Music)") == "good for you"


def test_bpm_fit_half_double():
    assert M.bpm_fit(120, 120) == 1.0 and M.bpm_fit(60, 120) == 1.0 and M.bpm_fit(80, 120) < 0.5


def test_voice_auto_uses_storyboard_voice(monkeypatch):
    monkeypatch.setattr(tts, "engine_available", lambda n: True)
    monkeypatch.setattr(tts, "_settings", lambda: {"voice_engine": "edge", "voice_id": ""})
    assert tts.resolve({"voice": {"engine": "supertonic", "id": "F2", "source": "auto"}}) == ("supertonic", "F2")
    monkeypatch.setattr(tts, "_settings", lambda: {"voice_engine": "edge", "voice_id": "", "voice_auto": False})
    assert tts.resolve({"voice": {"engine": "supertonic", "id": "F2", "source": "auto"}})[0] == "edge"
