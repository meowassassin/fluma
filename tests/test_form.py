"""형태(form) — 데이터로 빚은 형태를 화풍으로: 투명 배경 · 화풍 네 가지 · 재료 연결 · 검사"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
from craft import form  # noqa: E402

MUG = json.loads((ROOT / "engine" / "craft" / "form" / "examples" / "mug.json").read_text("utf-8"))


def test_draw_all_styles_transparent(tmp_path):
    for s in form.STYLES:
        im = form.draw(MUG, s, tmp_path / f"{s}.png", res=270)
        a = np.asarray(im)[..., 3]
        assert im.mode == "RGBA" and a[0, 0] == 0 and a.max() == 255, s     # 모서리는 투명, 형태는 불투명


def test_form_material_adapter_and_lint(tmp_path):
    from craft import materials
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import lint
    out = tmp_path / "m.png"
    info = materials.form({"id": "m", "type": "form", "scene": json.dumps(MUG), "style": "flat", "res": 270}, out, tmp_path)
    assert out.exists() and info["style"] == "flat" and info["as"] == "image"
    assert "form" in materials.BUILTIN
    sb = {"id": "zz", "format": "concept", "scenes": [{"role": "hook", "sec": 3, "narration": "가", "materials": [{"id": "f", "type": "form", "style": "oil"}]}]}
    msgs = [m for c, _, m in lint.lint(sb) if c == "L39"]
    assert any("형태 데이터" in m for m in msgs) and any("flat" in m for m in msgs)
