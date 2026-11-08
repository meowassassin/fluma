"""다듬기(engine/craft/refine.py) · 작업 세션(engine/craft/session.py) — 기록 형식 · 자리표시자 · 장면 컴프 이름 · 검사 · 실제 적용"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import refine  # noqa: E402

Image = pytest.importorskip("PIL.Image")
HAS = {a: (ROOT / "tools" / "crafts" / a / "installed.json").exists() for a in ("photocraft", "effectcraft")}


def _sb(**kw):
    sb = {"id": "2026-11-06-refine-01", "title": "다듬기 시험", "format": "concept",
          "scenes": [{"role": "hook", "sec": 2.0, "narration": "하나"}, {"role": "reveal", "sec": 3.0, "narration": "둘",
                                                                          "refine": [{"target": "motion", "layer": "light", "why": "시험",
                                                                                      "steps": [{"id": "effect.apply", "params": {"effect": "Glow", "layers": ["Mat a"], "t": "$SEC"}}]},
                                                                                     {"target": "sound", "layer": "sound", "why": "시험",
                                                                                      "steps": [{"id": "edit.space_clips", "params": {"at": "$START_SMP"}}]}]}]}
    sb.update(kw)
    return sb


def test_placeholders_and_comp_names():
    sb = _sb()
    v = refine.vars_for(sb, 1)
    assert v["COMP"] == "S02 반전" and v["START"] == 2.0 and v["END"] == 5.0 and v["START_SMP"] == 96000
    assert refine.subst({"a": "$MID", "b": ["$END", "x$END"]}, v) == {"a": 3.5, "b": [5.0, "x$END"]}   # 문자열 전체만 바뀐다
    with pytest.raises(ValueError):
        refine.subst("$START", refine.vars_for(sb, None))                                           # 영상 전체 pass 에는 장면 시각 없음
    st = refine.motion_steps(sb)
    assert st[0] == {"command": "comp.open", "params": {"comp": "S02 반전"}} and st[1]["params"]["t"] == 3.0
    # 장면 일부만 렌더하면 콘티가 잘려 오지만 컴프 이름은 원래 번호(S02) — 아니면 없는 컴프를 연다
    cut = {**sb, "scenes": [sb["scenes"][1]]}
    assert refine.motion_steps(cut, [2])[0]["params"]["comp"] == "S02 반전"
    assert refine.sound_cmds(sb) == ['edit.space_clips={"at": 96000}']
    assert refine.edit_lines(sb) == []


def test_validate_catches_bad_passes(monkeypatch):
    monkeypatch.setattr(refine, "_ids", lambda app: {"effect.apply", "edit.space_clips"})
    assert refine.validate(_sb()) == []
    bad = _sb()
    bad["scenes"][0]["refine"] = [{"target": "motion", "layer": "sparkle", "steps": [{"id": "nope"}]}]
    bad["scenes"][0]["detail"] = {"vibe": "x"}
    bad["refine"] = [{"target": "paint", "layer": "color", "steps": [{"id": "a"}], "why": "w"}]
    errs = " / ".join(refine.validate(bad))
    assert "sparkle" in errs and "why" in errs and "'nope'" in errs and "vibe" in errs and "paint" in errs


def test_coverage_shows_missing_layers():
    sb = _sb()
    sb["scenes"][1]["detail"] = {"light": "결론에 빛 한 번", "typo": "핵심 숫자 굵게"}
    sb["scenes"][0]["materials"] = [{"id": "a", "type": "image", "refine": [{"app": "photocraft", "layer": "color", "why": "w", "steps": [{"id": "x"}, {"id": "y"}]}]}]
    cv = refine.coverage(sb)
    assert cv["grid"]["photocraft"]["color"] == [1, 2] and cv["grid"]["effectcraft"]["light"] == [1, 1]
    assert cv["missing"] == [(2, "typo")]


def test_session_plan_keep_drop(tmp_path):
    sp = tmp_path / "sb.json"
    sp.write_text(json.dumps(_sb(), ensure_ascii=False), "utf-8")
    py = [sys.executable, str(ROOT / "engine" / "craft" / "session.py")]
    r = subprocess.run(py + ["plan", str(sp), "1", "typo=제목 위계", "sparkle=x"], capture_output=True, text=True)
    assert r.returncode != 0 and "sparkle" in r.stdout + r.stderr
    subprocess.run(py + ["plan", str(sp), "1", "typo=제목 위계"], check=True, capture_output=True)
    p = json.dumps({"layer": "typo", "why": "위계", "steps": [{"command": "effect.apply", "params": {"effect": "Glow"}}]})
    r = subprocess.run(py + ["keep", str(sp), "1", "--target", "motion", "--pass", p], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    sc = json.loads(sp.read_text("utf-8"))["scenes"][0]
    assert sc["detail"] == {"typo": "제목 위계"} and sc["refine"][0]["target"] == "motion" and sc["refine"][0]["steps"][0]["id"] == "effect.apply"
    r = subprocess.run(py + ["keep", str(sp), "1", "--target", "motion", "--pass", json.dumps({"layer": "typo", "steps": [{"id": "effect.apply"}]})],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "why" in r.stdout          # 근거 없는 다듬기는 남기지 않는다
    subprocess.run(py + ["drop", str(sp), "1", "--target", "motion", "1"], check=True, capture_output=True)
    assert json.loads(sp.read_text("utf-8"))["scenes"][0]["refine"] == []


@pytest.mark.skipif(not HAS["photocraft"], reason="PhotoCraft 가 설치되지 않음")
def test_material_refine_chains_on_editable(tmp_path):
    """PhotoCraft 편집 파일을 이어서 다듬는다: 픽셀 레이어 고르기 → 필터 → 맨 위 조정 레이어(문서 전체 톤)"""
    from craft.adapters.craft_script import craft
    d = ROOT / "data" / "workspace" / "test-refine"
    d.mkdir(parents=True, exist_ok=True)
    src = d / "src.png"
    Image.new("RGB", (540, 960), (90, 120, 160)).save(src)
    base = craft({"type": "craft", "id": "base", "app": "photocraft", "open": str(src.relative_to(ROOT)),
                  "steps": [{"id": "layer.duplicate", "params": {}}]}, d / "base.png", d)
    rec = {"id": "m", "app": "photocraft", "file": str((d / "base.png").relative_to(ROOT)), "editable": base["editable"]}
    m = {"id": "m", "refine": [{"layer": "color", "app": "photocraft", "why": "시험",
                                "steps": [{"id": "layer.newAdjustmentLayer.colorLookup", "params": {"lut": "warm"}}]}]}
    out = refine.apply_material(rec, m, d)
    assert out["refined"][0]["steps"] == ["layer.newAdjustmentLayer.colorLookup"] and out["editable"] == base["editable"]
    a = Image.open(ROOT / rec["file"]).convert("RGB").getpixel((270, 480))
    b = Image.open(ROOT / out["file"]).convert("RGB").getpixel((270, 480))
    assert b[0] > a[0] and b != a                                  # 따뜻하게(빨강 쪽으로)


def test_script_failures_are_found_in_exit_zero_output():
    from craft import refine
    out = '{"comp": 1}\n{"error": {"file": "a", "line": 1, "message": "컴프 없음"}, "ok": false, "result": null}\n{"ok": true}'
    assert refine.script_failures(out) == ["a: 컴프 없음"]
    assert refine.script_failures('{"ok": true}') == []


def test_comp_placeholder_is_replaced_inside_script_code():
    from craft import refine
    assert refine.subst({"code": 'it.name=="$COMP";new File("$ROOT/x")'}, {"COMP": "S01", "ROOT": "/r"}) == {"code": 'it.name=="S01";new File("/r/x")'}

