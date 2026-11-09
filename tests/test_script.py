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
