"""Fluma MCP 서버 · 작업 대기열 — 실제 stdio 로 말을 주고받고, 작업은 임시 폴더에서 짧은 명령으로 돌린다.

  .venv/bin/python -m pytest -q tests/test_mcp.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
SERVER = ROOT / "engine" / "mcp_server.py"


@pytest.fixture()
def jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("FLUMA_JOBS_DIR", str(tmp_path / "jobs"))
    sys.path.insert(0, str(ROOT / "engine" / "mcp"))
    import fluma_jobs
    monkeypatch.setattr(fluma_jobs, "JOBS", tmp_path / "jobs")
    return fluma_jobs


def rpc(lines: list[dict]) -> list[dict]:
    inp = "".join(json.dumps(x) + "\n" for x in lines)
    r = subprocess.run([sys.executable, str(SERVER)], input=inp, capture_output=True, text=True, timeout=60, cwd=ROOT)
    return [json.loads(ln) for ln in r.stdout.splitlines() if ln.strip()]


def test_initialize_and_list():
    out = rpc([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
               {"jsonrpc": "2.0", "method": "notifications/initialized"},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
               {"jsonrpc": "2.0", "id": 3, "method": "nope"}])
    assert [o["id"] for o in out] == [1, 2, 3]                     # 알림에는 답하지 않는다
    assert out[0]["result"]["serverInfo"]["name"] == "fluma" and out[0]["result"]["instructions"]
    names = {t["name"] for t in out[1]["result"]["tools"]}
    assert {"project_status", "produce_start", "job_wait", "job_cancel"} <= names
    assert all(t["inputSchema"]["type"] == "object" for t in out[1]["result"]["tools"])
    assert out[2]["error"]["code"] == -32601


def test_bad_project_id_is_tool_error():
    out = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "project_status", "arguments": {"project": "../../etc"}}}])
    assert out[0]["result"]["isError"] is True


def _cmd(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_job_progress_result_and_join(jobs):
    code = "import time\nfor i in range(1,4):\n print(f'프레임 {i}/3', flush=True); time.sleep(0.4)\nprint('\\nFLUMA_RESULT\\nstatus=ok\\nfile=data/out/x.mp4\\nresult_file=r')"
    a = jobs.submit("t", _cmd(code), project="p1", key="t:p1", heavy=False)
    b = jobs.submit("t", _cmd(code), project="p1", key="t:p1", heavy=False)
    assert b.get("joined") and b["id"] == a["id"]
    j = jobs.wait(a["id"], 20)
    assert j["status"] == "done" and j["result"]["file"] == "data/out/x.mp4" and j["progress"] == 1.0


def test_job_error_and_cancel(jobs):
    e = jobs.wait(jobs.submit("t", _cmd("import sys; print('boom'); sys.exit(3)"), heavy=False)["id"], 20)
    assert e["status"] == "error" and "boom" in e["error"]
    c = jobs.submit("t", _cmd("import time; time.sleep(60)"), heavy=False)
    for _ in range(50):
        if jobs.get(c["id"]).get("child_pid"):
            break
        time.sleep(0.1)
    jobs.cancel(c["id"])
    time.sleep(0.5)
    assert jobs.get(c["id"])["status"] == "canceled"


def test_heavy_jobs_run_one_at_a_time(jobs, monkeypatch):
    monkeypatch.setenv("FLUMA_HEAVY_SLOTS", "1")
    slow = _cmd("import time; time.sleep(1.5)")
    a = jobs.submit("t", slow, heavy=True, mem_gb=0)
    b = jobs.submit("t", slow, heavy=True, mem_gb=0)
    time.sleep(0.8)
    states = {jobs.get(a["id"])["status"], jobs.get(b["id"])["status"]}
    assert states == {"running", "waiting"}
    assert jobs.wait(b["id"], 20)["status"] == "done"


# ---------- 제작 도구(콘티 · 검토 · 면제) — 임시 data 폴더에 예시 콘티 ----------
@pytest.fixture()
def tools(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "engine" / "mcp"))
    sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: F401
    import fluma_tools
    data = tmp_path / "data"
    (data / "storyboards").mkdir(parents=True)
    ex = json.loads((ROOT / "engine/spec/examples/storyboard.example.json").read_text("utf-8"))
    ex["id"] = "2026-01-01-test-01"
    (data / "storyboards" / f"{ex['id']}.json").write_text(json.dumps(ex, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(fluma_tools, "DATA", data)
    return fluma_tools, ex["id"], data


def test_patch_protects_and_validates(tools):
    T, pid, data = tools
    with pytest.raises(ValueError, match="못 바꾸는"):
        T.storyboard_patch(pid, {"waivers": {"D10": {"why": "x", "user_said": "y"}}})
    with pytest.raises(ValueError, match="형식 검사"):
        T.storyboard_patch(pid, {"scenes": {"1": {"sec": "느림"}}})
    with pytest.raises(ValueError, match="없는 장면"):
        T.storyboard_patch(pid, {"scenes": {"99": {"caption": "x"}}})
    r = T.storyboard_patch(pid, {"title": "새 제목", "scenes": {"1": {"caption": "바뀐 자막"}}})
    sb = json.loads((data / "storyboards" / f"{pid}.json").read_text("utf-8"))
    assert sb["title"] == "새 제목" and sb["scenes"][0]["caption"] == "바뀐 자막" and "scenes.1.caption" in r["changed"]


def test_review_needs_build_and_every_scene_seen(tools):
    T, pid, data = tools
    with pytest.raises(ValueError, match="전체 빌드"):
        T.review_submit(pid, [])
    proj = data / "compositions" / pid / "craft" / "motion" / f"{pid}.ecproj"
    proj.parent.mkdir(parents=True)
    proj.write_text("{}")
    with pytest.raises(ValueError, match="보지 않았"):
        T.review_submit(pid, [])
    n = len(json.loads((data / "storyboards" / f"{pid}.json").read_text("utf-8"))["scenes"])
    T._seen_path(pid).write_text(json.dumps({"stamp": T.build_stamp(pid), "scenes": [1]}))
    if n > 1:
        with pytest.raises(ValueError, match="안 본 장면"):
            T.review_submit(pid, [])
    T._seen_path(pid).write_text(json.dumps({"stamp": T.build_stamp(pid), "scenes": list(range(1, n + 1))}))
    r = T.review_submit(pid, [{"scene": 1, "kind": "겹침", "what": "글자가 그림을 덮음"}])
    assert r["blocking"] == 1
    assert T.review_fresh(pid)[0] is True
    proj.write_text('{"changed": true}')                 # 장면이 바뀌면 검토는 낡음
    assert T.review_fresh(pid)[0] is False


def test_waive_requires_user_words(tools):
    T, pid, data = tools
    with pytest.raises(ValueError, match="user_said"):
        T.waive(pid, "D10", "빈 화면 의도", "")
    T.waive(pid, "D10", "빈 화면 의도", "이 장면은 비어도 돼", scene=2)
    sb = json.loads((data / "storyboards" / f"{pid}.json").read_text("utf-8"))
    assert sb["waivers"]["D10:2"]["user_said"] == "이 장면은 비어도 돼"
