"""스킬이 가리키는 예시 콘티가 있고 스키마를 통과한다(2026-11-16: 가리키는 파일이 없어 에이전트가 스키마 · 엔진 코드를 뒤지며 3분을 썼다)"""
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def test_example_storyboard_valid():
    ex = json.loads((ROOT / "engine/spec/examples/storyboard.example.json").read_text("utf-8"))
    sch = json.loads((ROOT / "engine/spec/schema/storyboard.schema.json").read_text("utf-8"))
    errs = list(jsonschema.Draft202012Validator(sch).iter_errors(ex))
    assert not errs, [e.message for e in errs][:5]


def test_skills_point_to_existing_example():
    for f in (ROOT / ".claude/skills").rglob("*.md"):
        assert "data/storyboards/example.json" not in f.read_text("utf-8"), f
