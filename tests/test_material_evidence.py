"""material 증거 정책 — 카드만 막기 · 브랜드 아이콘 보강."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "story"))
sys.path.insert(0, str(ROOT / "engine" / "checks"))


def _sb(*scene_list):
    return {
        "id": "2026-11-16-evidence-test",
        "version": 1,
        "format": "compare",
        "duration_sec": 12,
        "title": "t",
        "topic": "t",
        "cta": "c",
        "scenes": list(scene_list),
    }


def test_l59_blocks_card_only_body():
    from material_evidence import material_evidence_checks

    sb = _sb(
        {
            "role": "hook",
            "sec": 3,
            "narration": "훅",
            "materials": [{"id": "m1", "type": "info_card", "title": "x", "body": "y"}],
        },
        {
            "role": "build",
            "sec": 5,
            "narration": "Claude 쓰면 이렇게",
            "materials": [{"id": "m2", "type": "diagram", "kind": "steps", "items": ["a", "b"]}],
        },
        {"role": "outro", "sec": 4, "narration": "끝", "materials": []},
    )
    codes = {c for c, _, _ in material_evidence_checks(sb)}
    assert "L59" in codes


def test_dedupe_and_icon(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    from material_evidence import apply_storyboard, material_evidence_checks

    sb = _sb(
        {
            "role": "build",
            "sec": 5,
            "narration": "Docker 이미지 빌드",
            "screen": "실제 화면",
            "visual": {"kind": "screenshot"},
            "materials": [
                {"id": "m1", "type": "info_card", "title": "a", "body": "b"},
                {"id": "m2", "type": "diagram", "kind": "list", "items": ["x", "y"]},
            ],
        },
    )
    changed = apply_storyboard(sb)
    mats = sb["scenes"][0]["materials"]
    assert len([m for m in mats if m.get("type") in ("info_card", "diagram")]) == 1
    assert any(m.get("type") == "icon" for m in mats) or changed
    assert sb["scenes"][0].get("screen") != "실제 화면" or any(
        m.get("type") == "icon" for m in mats
    )


def test_daily_exempt():
    from material_evidence import material_evidence_checks

    sb = _sb(
        {
            "role": "build",
            "sec": 5,
            "narration": "오늘 시세",
            "materials": [{"id": "m1", "type": "template_card", "csv": "data/x.csv"}],
        },
    )
    sb["format"] = "daily"
    assert not material_evidence_checks(sb)