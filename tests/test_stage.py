"""자동 진행 단계 경계(engine/mcp/fluma_stage.py) — 같은 턴은 막고, 새 턴 · 사람 대화 · 작업 안에서는 막지 않는다.

  .venv/bin/python -m pytest -q tests/test_stage.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine" / "mcp"))
import fluma_stage as st  # noqa: E402

PID = "2099-01-03-stage-01"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("FLUMA_AUTOPILOT", "FLUMA_TURN", "FLUMA_JOB_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FLUMA_STAGE_SPLIT", "1")
    yield
    shutil.rmtree(ROOT / "data" / "workspace" / "tmp" / PID, ignore_errors=True)


def test_same_turn_blocked_new_turn_free(monkeypatch):
    monkeypatch.setenv("FLUMA_AUTOPILOT", "1"); monkeypatch.setenv("FLUMA_TURN", "a")
    assert "턴을 끝낸다" in st.mark(PID, "written")
    with pytest.raises(ValueError):
        st.check(PID, "prep_start")
    st.check(PID, "storyboard_patch")                     # 다음 단계 도구가 아니면 그대로
    monkeypatch.setenv("FLUMA_TURN", "b")
    st.check(PID, "prep_start")                           # 새 대화(새 턴)에서는 된다


def test_reviewed_blocks_render_only(monkeypatch):
    monkeypatch.setenv("FLUMA_AUTOPILOT", "1"); monkeypatch.setenv("FLUMA_TURN", "a")
    st.mark(PID, "reviewed")
    st.check(PID, "review_frames")
    with pytest.raises(ValueError):
        st.check(PID, "render_start")


def test_inactive_without_autopilot_or_in_job(monkeypatch):
    assert st.mark(PID, "written") is None                # 사람과 하는 대화는 막지 않는다
    monkeypatch.setenv("FLUMA_AUTOPILOT", "1"); monkeypatch.setenv("FLUMA_TURN", "a")
    st.mark(PID, "written")
    monkeypatch.setenv("FLUMA_JOB_ID", "x")               # 작업(렌더 등) 안의 produce 는 막지 않는다
    st.check(PID, "produce_start")


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("FLUMA_STAGE_SPLIT")
    monkeypatch.setenv("FLUMA_AUTOPILOT", "1"); monkeypatch.setenv("FLUMA_TURN", "a")
    assert st.mark(PID, "written") is None
