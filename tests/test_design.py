"""디자인 결정(engine/craft/design.py) — 효과는 근거가 있을 때만 · 사용자 > 레퍼런스 > 효과 없음 · 시안 · 재료마다 앱 고르기"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import design  # noqa: E402
from craft.motion import build_jsx  # noqa: E402

WORDS = [{"text": " AI", "startMs": 30, "endMs": 700, "scene": 0}, {"text": " 추천", "startMs": 700, "endMs": 1098, "scene": 0},
         {"text": " 그런데", "startMs": 1300, "endMs": 1800, "scene": 0}]


def _sb(direction=None, fmt="concept"):
    return {"id": "2026-11-06-design-01", "format": fmt, "title": "디자인 시험", "direction": direction or {},
            "scenes": [{"role": "hook", "sec": 2.0, "narration": "AI 추천 그런데",
                        "elements": [{"name": "훅 제목", "what": "'AI 추천'", "cue": "AI"}]}]}


def _jsx(sb):
    return build_jsx(sb, WORDS, [{"index": 0, "start": 0.0, "end": 2.0, "sec": 2.0}], Path("/tmp/x.ecproj"))


def test_default_is_no_effects():
    z = design.resolve({})
    assert z["bg_preset"] is None and not z["bg_motion"] and z["enter"] is None and z["cam_push"] == 1.0
    assert not z["frame"]["shadow"] and not z["text_pop"] and z["title_preset"] is None
    jsx = _jsx(_sb())
    assert "bgPreset(c, bgL" not in jsx and "dressBg(c, bgL" not in jsx           # 배경 움직임 없음(형식이 concept 이어도)
    assert "popIn(tl" not in jsx and "sS.setValueAtTime" not in jsx                # 제목 · 자막 '톡' 없음
    assert "zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime(2.0, [107" not in jsx   # 장면 밀기 없음


def test_user_value_wins_and_partial_merge():
    z = design.resolve({"direction": {"frame": {"shadow": True}, "enter": {"screen": "wipeInFromRight"}, "bg_preset": None}})
    assert z["frame"] == {"shadow": True, "round": False, "push": 1.0}
    assert design.enter_for(z, "screen") == "wipeInFromRight" and design.enter_for(z, "image") is None


def test_motion_proposal_draws_effects():
    props = design.proposals(_sb(), {})
    names = [p["name"] for p in props]
    assert len(props) == 2 and names[0].startswith("담백")                     # 레퍼런스가 없으면 2개
    jsx = _jsx(_sb(props[1]["direction"]))
    assert "bgPreset(c, bgL, \"blueprintGrid\"" in jsx and "SubBox 01" in jsx and "popIn" in jsx
    plain = _jsx(_sb(props[0]["direction"]))
    assert "TitleBox 1" not in plain and "SubBox" not in plain                 # 담백: 상자 없음


def test_from_reference_only_what_was_measured():
    look = {"camera_mix": {"slow push-in": 5, "locked-off static camera": 10}, "shot_sec": 1.8}
    x = [{"video": {"duration": 10}, "speech": [{"start": 0, "end": 6}], "text": [1] * 2}]
    r = design.from_reference(look, x)
    assert r["cam_push"] > 1.0 and r["enter"] is None and r["sound"]["voice_chain"] == "clean"
    assert design.from_reference({}, []) == {}


def test_direct_merge_keeps_user_keys_and_lock():
    from story.direct import design_merge
    sb = {"id": "x", "scenes": [], "direction": {"cam_push": 1.0, "_auto": []}}
    design_merge(sb)                                   # 레퍼런스 없음 → 아무것도 넣지 않음, 사용자 값 그대로
    assert sb["direction"]["cam_push"] == 1.0 and sb["direction"]["design_from"] == "none"
    locked = {"id": "x", "scenes": [], "direction": {"locked": True}}
    assert design_merge(locked) == {} and "design_from" not in locked["direction"]


def test_methods_list_and_unknown_method(tmp_path):
    from craft import materials
    ms = materials.methods()
    assert ms["chart"][0] == "gridcraft" and "deckcraft" in ms["chart"]      # 기본이 앞, 다른 방법은 뒤(alt)
    sb = {"id": "2026-11-06-design-01", "scenes": [{"sec": 2, "materials": [{"id": "c1", "type": "chart", "method": "figcraft",
                                                                              "labels": ["a"], "values": [1]}]}]}
    with pytest.raises(RuntimeError, match="figcraft"):
        materials.build(sb)


def test_pick_locks_direction(tmp_path, monkeypatch):
    import story.directions as dr
    monkeypatch.setattr(dr, "STORE", tmp_path)
    sp = tmp_path / "s.json"
    sp.write_text(json.dumps(_sb({"cam_push": 1.05, "_auto": ["cam_push"]})), "utf-8")
    (tmp_path / "2026-11-06-design-01.json").write_text(json.dumps(design.proposals(_sb(), {})), "utf-8")
    with pytest.raises(SystemExit):                     # ok() 는 결과 블록을 찍고 끝낸다
        dr.cmd_pick(sp, "1")
    d = json.loads(sp.read_text("utf-8"))["direction"]
    assert d["locked"] and d["picked"].startswith("담백") and d["cam_push"] == 1.0 and d["_auto"] == []
