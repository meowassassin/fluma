"""레퍼런스 기준 검사(engine/checks/refnorm.py · lint L50~L53)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "checks"))
import refnorm  # noqa: E402

T = {"shot_med": 1.8, "shot_p75": 2.6, "phrase_med": 11.5, "phrase_p90": 20, "cps": 7.0, "refs": [], "n_shots": 10}


def sb(scenes, script):
    return {"id": "x", "format": "concept", "scenes": scenes, "script": script}


def codes(rows):
    return [c for c, *_ in rows]


def test_long_static_scene_fails_and_cues_split_it():
    one = sb([{"sec": 7, "materials": [{"id": "a", "type": "video"}]}], "짧게 말해요")
    assert "L50" in codes(refnorm.check(one, T))
    split = sb([{"sec": 7, "materials": [{"id": "a", "type": "video", "cue": "하나"}, {"id": "b", "type": "image", "cue": "둘"}]}], "하나 둘")
    assert "L50" not in codes(refnorm.check(split, T))
    take = sb([{"sec": 7, "long_take": "한 번에 따라가는 원테이크", "materials": [{"id": "a", "type": "video"}]}], "짧게")
    assert codes(refnorm.check(take, T)).count("L50") == 0 and "T51" in codes(refnorm.check(take, T))


def test_long_phrase_and_lecture_connectives():
    long = sb([{"sec": 3, "materials": [{"id": "a", "type": "image"}]}], "주문 백만 건에서 사천이백사십이번 손님 주문을 찾는 데 이십이 밀리초가 걸렸어요")
    assert "L51" in codes(refnorm.check(long, T))
    lect = sb([{"sec": 2, "materials": [{"id": "a", "type": "image"}]}] * 1,
              "해시로 바꿔요. 그래서 못 풀어요. 근데 빨라요. 그러니까 느리게 해요. 그래서 안전해요.")
    assert "L52" in codes(refnorm.check(lect, T))


def test_lint_l53_mock_screen_needs_ui():
    from lint import lint
    s = {"id": "x", "format": "concept", "duration_sec": 2, "scenes": [{"role": "hook", "sec": 2, "beat": "b", "caption": "", "narration": "",
         "materials": [{"id": "m", "type": "ui_mock", "device": "phone", "mock": True, "screen": {"title": "t", "items": ["a"]}}]}]}
    assert any(c == "L53" for c, *_ in lint(s))
    s["scenes"][0]["materials"][0]["ui"] = "data/compositions/x/ui/a.tsx"
    assert not any(c == "L53" for c, *_ in lint(s))
