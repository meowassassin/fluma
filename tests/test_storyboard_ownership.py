"""콘티 칸 주인 — 한 단계가 고친 칸을 다른 단계가 지우지 않는다(2026-11-18 감사)"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import sbio  # noqa: E402
import script  # noqa: E402
from craft.design import apply_art  # noqa: E402


def _sb():
    return {"id": "t", "script": "가 / 나 / 다", "title": "제목",
            "direction": {"layout": "full"},
            "scenes": [{"id": "s1", "narration": "가", "caption": "c1"}, {"id": "s2", "narration": "나"}, {"id": "s3", "narration": "다"}]}


def test_save_keeps_edits_made_while_stage_ran(tmp_path):
    p = tmp_path / "sb.json"
    base = _sb()
    p.write_text(json.dumps(base, ensure_ascii=False))
    mine = copy.deepcopy(base)
    mine["direction"]["font_title"] = "Pretendard"                 # 이 단계(디자이너)가 바꾼 칸
    other = copy.deepcopy(base)
    other["scenes"][1]["caption"] = "에이전트가 고침"                 # 그동안 에이전트가 고친 칸
    other["direction"]["anchors"] = ["오리"]
    p.write_text(json.dumps(other, ensure_ascii=False))
    out = sbio.save(p, base, mine)
    assert out["direction"] == {"layout": "full", "anchors": ["오리"], "font_title": "Pretendard"}
    assert out["scenes"][1]["caption"] == "에이전트가 고침"
    assert json.loads(p.read_text())["scenes"][1]["caption"] == "에이전트가 고침"


def test_save_deletes_only_what_stage_deleted(tmp_path):
    p = tmp_path / "sb.json"
    base = _sb()
    p.write_text(json.dumps(base, ensure_ascii=False))
    mine = copy.deepcopy(base)
    del mine["scenes"][0]["caption"]
    out = sbio.save(p, base, mine)
    assert "caption" not in out["scenes"][0]


def test_script_follows_narration_edit():
    sb = _sb()
    assert script.apply(sb)[0]                                     # 첫 맞춤 — 지문을 남긴다
    sb["scenes"][1]["narration"] = "나를 고침"                        # knob · 손 편집
    changed, _ = script.apply(sb)
    assert changed and sb["script"] == "가 / 나를 고침 / 다"
    assert sb["scenes"][1]["narration"] == "나를 고침"


def test_narration_follows_script_edit():
    sb = _sb()
    script.apply(sb)
    sb["script"] = "가 / 새 대본 / 다"
    script.apply(sb)
    assert sb["scenes"][1]["narration"] == "새 대본"


def test_locked_true_does_not_crash_and_locks_colors():
    sb = {"direction": {"locked": True, "color_bg": "#000000", "feel": {"palette": {"bg": "#ffffff"}}}, "scenes": []}
    apply_art(sb)
    assert sb["direction"]["color_bg"] == "#000000"


def test_writer_skips_silent_scenes_and_locked():
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import skill_pass as sp
    sb = _sb()
    sb["scenes"][1]["say"] = False
    sb["scenes"][1]["narration"] = ""
    sb["script"] = "가 / 다"
    ch = sp.writer_apply(sb, {"script": "가2 / 다2", "_locked": ["s3.narration"]})
    assert "script" in ch
    assert sb["script"] == "가2 / 다" and sb["scenes"][1]["narration"] == ""
    script.apply(sb)                                               # 말하는 장면 수와 칸 수가 맞아 오류가 나지 않는다
