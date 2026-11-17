"""앱을 넘나드는 연결($USE · $READ)과 말에 맞추기($CUE) — 2026-11-16"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
from craft import cues  # noqa: E402
from craft.adapters.craft_script import expand_uses  # noqa: E402


def test_use_and_read(tmp_path):
    work = ROOT / "data" / "workspace" / "tmp" / "test-craft-links"
    work.mkdir(parents=True, exist_ok=True)
    (work / "art.svg").write_text("<svg/>", "utf-8")
    m = {"_uses": {"art": str(work / "art.png"), "art/": str(work)}}
    out = expand_uses({"a": "$USE:art", "b": "$USE:art/art.svg", "c": "$READ:$USE:art/art.svg"}, m)
    assert out == {"a": str(work / "art.png"), "b": str(work / "art.svg"), "c": "<svg/>"}
    with pytest.raises(RuntimeError, match="uses"):
        expand_uses("$USE:nope", m)
    with pytest.raises(RuntimeError, match="없습니다"):
        expand_uses("$USE:art/missing.svg", m)


def test_cue_resolve(monkeypatch):
    words = [{"text": "주소", "start": 0.1, "end": 0.4}, {"text": "404가", "start": 1.3, "end": 1.8}]
    monkeypatch.setattr(cues, "scene_words", lambda sb, i: (words, 6.0))
    sb = {"id": "x"}
    assert cues.resolve({"t": "$CUE:404", "u": "$CUE:404+0.3", "e": "$CUE:404@end"}, sb, 0) == {"t": 1.3, "u": 1.6, "e": 1.8}
    assert cues.resolve("k.setValueAtTime($CUE:주소-0.05, 1)", sb, 0) == "k.setValueAtTime(0.05, 1)"
    assert cues.resolve("$CUE:404", sb, 0, absolute=True) == 7.3
    with pytest.raises(RuntimeError, match="낱말이 없습니다"):
        cues.resolve("$CUE:500", sb, 0)
    assert cues.resolve({"plain": 1}, sb, 0) == {"plain": 1}
