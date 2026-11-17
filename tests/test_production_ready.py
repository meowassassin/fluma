"""production_ready 가 lint CLI 재귀를 부르지 않는다."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "story"))


def test_lint_cli_finishes_quickly(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    sb = {
        "id": "2026-11-16-test-pr-01",
        "version": 1,
        "format": "concept",
        "duration_sec": 6,
        "title": "t",
        "topic": "t",
        "cta": "c",
        "script": "a / b",
        "scenes": [
            {
                "role": "hook",
                "sec": 3,
                "caption": "h",
                "narration": "가나다라마바사",
                "visual": {"kind": "text"},
            },
            {
                "role": "outro",
                "sec": 3,
                "caption": "o",
                "narration": "아자차카타파하",
                "visual": {"kind": "text"},
            },
        ],
    }
    p = tmp_path / "sb.json"
    p.write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    t0 = time.perf_counter()
    r = subprocess.run(
        [sys.executable, str(ROOT / "engine" / "checks" / "lint.py"), str(p)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert time.perf_counter() - t0 < 5.0


def test_touch_uses_inprocess_lint(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    from production_ready import touch_production_ready

    sb = {
        "id": "2026-11-16-test-pr-02",
        "version": 1,
        "format": "concept",
        "duration_sec": 6,
        "title": "t",
        "topic": "t",
        "cta": "c",
        "script": "a / b",
        "scenes": [
            {
                "role": "hook",
                "sec": 3,
                "caption": "h",
                "narration": "가나다라마바사",
                "visual": {"kind": "text"},
            },
            {
                "role": "outro",
                "sec": 3,
                "caption": "o",
                "narration": "아자차카타파하",
                "visual": {"kind": "text"},
            },
        ],
    }
    p = tmp_path / "sb2.json"
    p.write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    t0 = time.perf_counter()
    touch_production_ready(p)
    assert time.perf_counter() - t0 < 2.0
    out = json.loads(p.read_text("utf-8"))
    assert "production_ready" not in out
    assert (out.get("meta") or {}).get("production_ready") is not None