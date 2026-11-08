"""앱 전체 기능 시험(engine/craft/probe.py) · 검색 결과에 붙는 시험 기록(craft_catalog.probe_note)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import craft_catalog, probe  # noqa: E402


def test_json_docs_reads_each_step_result():
    out = '{\n "comp": 2\n}\n[\n 28\n]\nnoise\n[{"id": "a", "enabled": true}]'
    assert probe.json_docs(out) == [{"comp": 2}, [28], [{"id": "a", "enabled": True}]]


def test_classify_tells_context_from_params():
    assert probe.classify(0, "") == "ok"
    assert probe.classify(1, "command `x` is not available right now: filters need a pixel layer") == "needs_context"
    assert probe.classify(1, "invalid parameters for `layer.style.add`: missing `style`") == "needs_params"
    assert probe.classify(1, "segfault") == "error"


def test_probe_note_in_search(monkeypatch):
    craft_catalog._PROBE["x"] = {
        "f.grain": {"id": "f.grain", "states": {"none": "no active layer", "pixel": True}, "run": "ok", "visible": True, "thumb": "data/t.png"},
        "f.need": {"id": "f.need", "run": "needs_params", "msg": "missing index"}}
    n = craft_catalog.probe_note("x", "f.grain")
    assert "되는 상태: pixel" in n and "no active layer" in n and "data/t.png" in n
    assert craft_catalog.probe_note("x", "f.need") == "needs_params: missing index"
    assert craft_catalog.probe_note("x", "nope") == ""


def test_sample_records_are_valid_jsonl():
    for f in (ROOT / ".claude" / "skills" / "crafts" / "probe").glob("*.jsonl"):
        for ln in f.read_text("utf-8").splitlines():
            r = json.loads(ln)
            assert r["id"] and r["kind"] in ("command", "effect", "preset", "tool")
