"""장면 설계 언어(engine/craft/design_lang.py) — 검증 · 배치(안전 영역) · K 코드 생성. EffectCraft 없이 돈다.

  .venv/bin/python -m pytest -q tests/test_design_lang.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
from craft import design_lang as dl  # noqa: E402

SB = {"id": "2099-01-04-dl-01", "direction": {"art": {"palette": {"bg": "#eeeeee", "ink": "#111111", "accent": "#cc3300"}}, "font_title": "T", "font_body": "B"}}


def test_validate_reports_each_field():
    errs = dl.validate({"els": [{"id": "a", "kind": "txt"}, {"id": "a", "kind": "text", "enter": "zoom", "fx": [{"id": "ec.stylize.glow"}]},
                                {"id": "b", "kind": "tag", "text": "x", "at": {"below": "nope"}}]})
    joined = " | ".join(errs)
    assert "kind: 'txt'" in joined and "겹침" in joined and "enter: 'zoom'" in joined and "금지" in joined and "없는 요소 'nope'" in joined
    assert dl.validate({"els": [{"id": "a", "kind": "text", "text": "hi", "size": {"w": 300}}]}) == []


def test_compile_keeps_inside_safe_area_and_uses_cues():
    d = {"bg": "bg", "els": [{"id": "h", "kind": "text", "text": "아주 긴 제목 글자가 화면을 넘을 수도 있다", "role": "hero"},
                             {"id": "t1", "kind": "tag", "text": "A", "at": {"slot": [1, 2], "of": "h"}, "on": "에이", "enter": "drop"},
                             {"id": "t2", "kind": "tag", "text": "B", "at": {"slot": [2, 2], "of": "h"}, "on": "비", "emph": [{"on": "비", "do": "circle"}]}]}
    code = dl.compile_scene(d, SB, 2)
    assert 'K.scene(K.C.duration, "#eeeeee")' in code
    assert "$CUE:에이" in code and "$CUE:비" in code
    for x, y in re.findall(r"K\.P\(e_\w+\)\.setValue\(\[(-?\d+), (-?\d+)\]\)", code):
        assert dl.SAFE[0] <= int(x) <= dl.SAFE[2] and dl.SAFE[1] <= int(y) <= dl.SAFE[3]


def test_camera_and_fx_keys():
    d = {"camera": {"move": "push", "amount": 0.05}, "els": [{"id": "a", "kind": "box", "fx": [{"id": "ec.blur.gaussian", "Blurriness": [10, 0]}]}]}
    code = dl.compile_scene(d, SB, 1)
    assert "CAM" in code and "[105.0,105.0]" in code
    assert 'f.property("Blurriness").setValueAtTime(0.05, 10)' in code


def test_compile_rejects_invalid():
    try:
        dl.compile_scene({"els": [{"id": "a", "kind": "nope"}]}, SB, 1)
    except ValueError as e:
        assert "kind" in str(e)
    else:
        raise AssertionError("설계 오류인데 컴파일됨")


def test_flow_checks_without_render():
    sys.path.insert(0, str(ROOT / "engine" / "mcp"))
    import fluma_flow as fl
    bad = fl._check_video({"concept": {"angle": "a"}, "art": {"palette": {"bg": "red"}}, "hashtags": ["x"], "zzz": 1})
    j = " | ".join(bad)
    assert "모르는 칸" in j and "concept.breaks" in j and "palette.bg" in j and "anchors.emotion" in j and "hashtags" in j and "cta" in j
    assert fl._scene_map({"2": {}}, 3) == {2: {}}
    try:
        fl._scene_map([{}], 3)
    except ValueError as e:
        assert "3개" in str(e)
    v = fl._visual_of({"els": [{"id": "c", "kind": "capture", "src": "capture:x"}, {"id": "a", "kind": "tag", "text": "Node.js"},
                               {"id": "b", "kind": "tag", "text": "Go"}]})
    assert v == {"kind": "screenshot", "primary": "Node.js", "items": ["Node.js", "Go"]}
    assert fl._cue_words({"camera": {"on": "x"}, "els": [{"id": "a", "on": "y", "emph": [{"on": "z", "do": "scale"}]}]}) == \
        [("camera.on", "x"), ("els[a].on", "y"), ("els[a].emph[0].on", "z")]


def test_flow_fixes_from_first_real_run():
    """2026-11-25 첫 실제 제작에서 걸린 것들 — 낱말 옮기기 · 스키마 길이 · 재료 형식 · 설계 안 증거"""
    sys.path.insert(0, str(ROOT / "engine" / "mcp"))
    import fluma_flow as fl
    words = [{"text": " 그래서"}, {"text": " 127이고"}, {"text": " 흔히"}, {"text": " 쓰는"}, {"text": " 게"}, {"text": " 127.0.0.1이에요."}]
    assert fl._retarget("localhost는", "그래서 127이고 localhost는 127.0.0.1입니다.", words) in ("흔히", "쓰는")
    assert fl._retarget("없는말", "그래서 127이고", words) is None
    d = {"els": [{"id": "a", "on": "낱말+0.3", "emph": [{"on": "x", "do": "scale"}]}], "camera": {"on": "y@end"}}
    fl._set_cue(d, "els[a].on", "새"); fl._set_cue(d, "els[a].emph[0].on", "둘"); fl._set_cue(d, "camera.on", "셋")
    assert d["els"][0]["on"] == "새+0.3" and d["els"][0]["emph"][0]["on"] == "둘" and d["camera"]["on"] == "셋@end"
    errs = fl._schema_errors({"cta": "터미널에 ping 127.42.42.42 를 직접 쳐 보세요 " * 3, "hashtags": ["#a"]})
    assert any(e.startswith("video.cta") for e in errs)
    try:
        fl.assets_start("2099-01-05-x-01", [{"kind": "web", "name": "a"}, {"kind": "nope"}])
    except ValueError as e:
        assert "plan: 필요함" in str(e) and "kind 'nope'" in str(e) and "형식" in str(e)
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import material_evidence as me
    p = ROOT / "data" / "compositions" / "2099-01-05-x-01" / "design"
    p.mkdir(parents=True, exist_ok=True)
    (p / "s01.json").write_text('{"els": [{"id": "c", "kind": "capture", "src": "capture:x"}]}', "utf-8")
    try:
        m = {"type": "craft", "steps": [{"id": "script.run", "params": {"code": "$DESIGN:data/compositions/2099-01-05-x-01/design/s01.json"}}]}
        assert me.is_evidence(m)
    finally:
        import shutil
        shutil.rmtree(ROOT / "data" / "compositions" / "2099-01-05-x-01", ignore_errors=True)
