import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_enrich_adds_art_and_full_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    sbp = tmp_path / "t1.json"
    sbp.write_text(
        json.dumps(
            {
                "id": "t1",
                "engine": "craft",
                "aspect": "9:16",
                "scenes": [
                    {"role": "hook", "sec": 3.0, "narration": "가나다라마바사", "caption": "가나다라마바사",
                     "materials": [{"type": "video", "src": "x.mp4"}]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan = {
        "topic": "테스트",
        "shots": [{"purpose": "hook", "on_screen_text": "훅", "background": "browser tabs"}],
        "trend": {"refs": ["ref1"]},
    }
    import sys
    sys.path.insert(0, str(ROOT / "engine"))
    from story.board_enrich import enrich

    changed = enrich(sbp, plan)
    sb = json.loads(sbp.read_text("utf-8"))
    assert "direction.art" in changed or sb["direction"].get("art")
    assert sb["direction"].get("layout") == "full"
    assert sb.get("reference") == ["ref1"]
    assert sb["scenes"][0]["caption"] == "훅"