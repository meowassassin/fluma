"""대본 검토를 뒤에서(bundle.py script) — 기록 상태 · 고친 말 옮기기 · 막힘 알림. LLM 은 부르지 않는다.

  .venv/bin/python -m pytest -q tests/test_script_bg.py
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine" / "story"))
import bundle  # noqa: E402

SID = "2099-01-01-bgtest-01"


@pytest.fixture()
def proj():
    sp = ROOT / "data" / "storyboards" / f"{SID}.json"
    sb = {"id": SID, "title": "제목", "scenes": [{"role": "hook", "narration": "말 하나", "caption": "글자 하나"},
                                                 {"role": "outro", "narration": "말 둘", "caption": "글자 둘"}]}
    sp.write_text(json.dumps(sb, ensure_ascii=False), "utf-8")
    sub = bundle._words(sb)
    fin = copy.deepcopy(sub)
    fin["scenes"][0]["caption"] = "고친 글자"
    fin["scenes"][1]["narration"] = "고친 말"
    bundle._bg_write(SID, status="ok", submitted=sub, final=fin, secs=1.0)
    yield sp
    sp.unlink(missing_ok=True)
    shutil.rmtree(ROOT / "data" / "compositions" / SID, ignore_errors=True)


def test_adopts_only_untouched_fields_once(proj):
    sb = json.loads(proj.read_text("utf-8"))
    sb["scenes"][1]["narration"] = "에이전트가 손본 말"          # 그사이 에이전트가 고친 칸은 덮지 않는다
    proj.write_text(json.dumps(sb, ensure_ascii=False), "utf-8")
    g = bundle.script_gate(SID, wait=False)
    assert g["ok"] and g["adopted"] == ["장면1 화면 글자: 고친 글자"]
    now = json.loads(proj.read_text("utf-8"))
    assert now["scenes"][0]["caption"] == "고친 글자" and now["scenes"][1]["narration"] == "에이전트가 손본 말"
    now["scenes"][0]["caption"] = "글자 하나"                    # 옮긴 뒤 되돌려도 다시 덮지 않는다
    proj.write_text(json.dumps(now, ensure_ascii=False), "utf-8")
    assert bundle.script_gate(SID, wait=False)["adopted"] == []


def test_error_and_running(proj):
    bundle._bg_write(SID, status="error", error="시청자 점수 5")
    g = bundle.script_gate(SID, wait=False)
    assert not g["ok"] and g["error"].startswith("대본 검토 막힘: 시청자 점수 5") and "고친 말" in g["script"]
    import os
    bundle._bg_write(SID, status="running", pid=os.getpid(), started=__import__("time").time())
    assert bundle.script_gate(SID, wait=False) == {"ok": True, "status": "running", "secs": 0}


def test_no_record_is_noop():
    assert bundle.script_gate("2099-01-01-none-01", wait=False) == {"ok": True, "status": "none"}
