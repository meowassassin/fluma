"""대본 한 덩어리 → 장면 나레이션(engine/story/script.py) · 이어 말하기 기본"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
import script  # noqa: E402
import assemble_audio  # noqa: E402


def test_split_skips_silent_scenes():
    sb = {"script": "어제 배포한 코드가 / 오늘 아침 전부 롤백됐는데요 / 범인은 3년 전의 나였거든요.", "scenes": [{}, {"say": False}, {}, {}]}
    assert script.apply(sb)[0]
    assert [s.get("narration") for s in sb["scenes"]] == ["어제 배포한 코드가", None, "오늘 아침 전부 롤백됐는데요", "범인은 3년 전의 나였거든요."]
    assert script.apply(sb)[0] is False          # 두 번째는 바뀐 것 없음


def test_mismatch_stops():
    with pytest.raises(ValueError):
        script.apply({"script": "하나 / 둘", "scenes": [{}, {}, {}]})


def test_no_script_is_noop():
    assert script.apply({"scenes": [{"narration": "x"}]}) == (False, "")


def test_continuous_is_default():
    assert assemble_audio.continuous_mode({"scenes": []}) is True
    assert assemble_audio.continuous_mode({"voice": {"continuous": False}}) is False


def test_continuous_split_survives_punctuation_and_number_reading(monkeypatch, tmp_path):
    """음성 엔진이 문장부호를 빼고 숫자를 다르게 읽어도 장면 경계가 제자리(2026-11-10: 장면 5 음성 44.8초)"""
    scenes = [{"narration": "같은 쿼리가, 2,800배 빨라요."}, {"narration": "주문 100만 건에서 손님 하나를 찾아요."}, {"narration": "그래서 인덱스를 겁니다!"}]
    # 엔진이 낸 단어(숫자를 한글로 · 문장부호 없음) — 장면마다 3초씩 말함(장면 2초 하한보다 길게)
    said = [["같은", "쿼리가", "이천팔백배", "빨라요"], ["주문", "백만", "건에서", "손님", "하나를", "찾아요"], ["그래서", "인덱스를", "겁니다"]]
    words, t = [], 0.0
    for k, ws in enumerate(said):
        step = 3.0 / len(ws)
        for w in ws:
            words.append({"text": w, "startMs": int(t * 1000), "endMs": int((t + step * 0.9) * 1000)}); t += step
    total = t
    monkeypatch.setattr(assemble_audio, "synth", lambda *a, **k: None)
    monkeypatch.setattr(assemble_audio, "speech", lambda wav: (b"\x00\x00" * int(assemble_audio.SR * total), words, total))
    (tmp_path / "x").mkdir()
    parts = assemble_audio.continuous_parts(scenes, tmp_path / "x", "edge", None, 1.0, None)
    lens = [round(p["speech"], 1) for p in parts]
    assert all(2.4 <= x <= 3.6 for x in lens), lens          # 장면마다 약 3초
    assert [w["text"] for w in parts[1]["words"]][:2] == ["주문", "백만"]
