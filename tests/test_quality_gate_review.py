"""검토 상한 뒤: 그림이 그대로인 장면의 문제는 계속 막고, 바뀐 장면의 옛 문제만 권고로."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
import quality_gate as qg  # noqa: E402


def _rec(tmp_path, rec):
    f = tmp_path / "data" / "compositions" / "v" / "skill_pass" / "review.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(rec, ensure_ascii=False), "utf-8")


def test_per_scene_stale_only_softens_changed_scenes(tmp_path, monkeypatch):
    monkeypatch.setattr(qg, "ROOT", tmp_path)
    _rec(tmp_path, {"problems": [{"scene": 1, "kind": "겹침", "what": "a", "stale": False}, {"scene": 2, "kind": "잘림", "what": "b", "stale": True}]})
    out = {x["scene"]: x for x in qg.from_review("v")}
    assert out[1]["block"] and not out[2]["block"]


def test_whole_record_stale_softens_all(tmp_path, monkeypatch):
    monkeypatch.setattr(qg, "ROOT", tmp_path)
    _rec(tmp_path, {"stale": True, "problems": [{"scene": 1, "kind": "겹침", "what": "a"}]})
    assert not qg.from_review("v")[0]["block"]
