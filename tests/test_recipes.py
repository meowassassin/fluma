"""검증된 레시피(engine/craft/recipes.py) — 펼치기(자리 채움 · JSX 도우미) · 모든 레시피 파일 형식"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import recipes, refine  # noqa: E402


def test_every_recipe_is_well_formed():
    rs = recipes.load()
    assert len(rs) >= 15
    for r in rs:
        assert r["layer"] in refine.LAYERS and r["target"] in ("motion", "material") and r["when"] and r["avoid"]
        v = {k: "X" for k in r.get("vars") or {}} | {"COMP": "S01 훅", "SEC": 3}
        p = recipes.expand(r, v)
        assert p["layer"] == r["layer"] and p["steps"]
        for s in p["steps"]:
            assert not recipes._TOK.search(json.dumps(s["params"], ensure_ascii=False))   # 자리가 다 채워졌다


def test_expand_fills_names_numbers_and_prelude():
    r = recipes.load("light-sweep-once")[0]
    p = recipes.expand(r, {"COMP": "S06 반전", "MAT": "Mat card", "T0": 0.5})
    code = p["steps"][0]["params"]["code"]
    assert p["steps"][0]["id"] == "script.run" and 'it.name=="S06 반전"' in code and 'L("Mat card")' in code
    assert "[[0.5,[-0.3,0.5]],[0.5+0.9" in code and "function EASE" in code and p["recipe"] == "light-sweep-once"
    with pytest.raises(SystemExit, match="MAT"):
        recipes.expand(r, {"COMP": "S06 반전"})
    m = recipes.expand(recipes.load("material-warm-grain")[0], {"PIXEL": "Backdrop"})
    assert m["app"] == "photocraft" and m["steps"][0]["params"] == {"name": "Backdrop"} and m["steps"][2]["params"] == {"name": "Title"}
