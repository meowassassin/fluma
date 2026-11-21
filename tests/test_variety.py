"""영상마다 다르게 — 선택지 겹침(plan.py vet) · 장면 흐름 · 콘셉트 · 앱 효과 깊이(lint L66 · L67 · L69) · 강조색(direct.ref_accent)"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
for d in ("engine", "engine/checks", "engine/gen", "engine/story"):
    sys.path.insert(0, str(ROOT / d))
import lint  # noqa: E402
import plan  # noqa: E402


def test_option_similarity_catches_rewordings():
    assert plan._sim("금요일 배포가 위험한 이유", '"금요일 오후 배포가 왜 위험한가"를 장애 사례 도식으로') >= plan.SIM_SAME
    assert plan._sim("엘리베이터 닫힘 버튼은 작동 안 한다", "DNS 바꿨는데 왜 바로 안 바뀌나") < plan.SIM_SAME


def test_flow_signature_collapses_repeats():
    sb = {"scenes": [{"role": "hook"}, {"role": "item"}, {"role": "item"}, {"role": "outro"}]}
    assert lint.flow_sig(sb) == "hook→item→outro"


def test_concept_required():
    sb = {"id": "zz-variety", "format": "concept", "scenes": [{"role": "hook"}]}
    codes = {c for c, _, _ in lint.variety(sb)}
    assert "L67" in codes and "L68" in codes
    sb["concept"] = {"angle": "오해 깨기", "breaks": "정의부터 읽는 시작", "structure": "오해→실험→진실"}
    assert "L67" not in {c for c, _, _ in lint.variety(sb)}


def _craft(code):
    return {"materials": [{"type": "craft", "app": "effectcraft", "steps": [{"id": "script.run", "params": {"code": code}}]}]}


def test_kit_only_scenes_flagged():
    flat = {"format": "concept", "scenes": [_craft("K.shape('rect',1,2,3,4)") for _ in range(4)]}
    assert lint.craft_depth(flat)
    rich = {"format": "concept", "scenes": [_craft("var t=K.text('a',1,1,9,'#fff'); K.fx(t,'ec.stylize.glow',{})") for _ in range(3)] + [_craft("K.shape()")]}
    assert not lint.craft_depth(rich)


def test_accent_not_fixed_red():
    import direct
    picks = {direct.ref_accent("no-such-ref", f"vid-{i}") for i in range(8)}
    assert "#ff2d2d" not in picks and len(picks) > 1


def test_feature_plan_requires_and_uses():
    sc = _craft("K.shape()")
    assert lint.feature_plan({"scenes": [sc]})                      # 고른 기능 없음
    sc2 = {**_craft("var t=K.text('a',1,1,9,'#fff'); K.fx(t,'ec.blur.gaussian',{})"), "features": ["ec.blur.gaussian"]}
    assert not lint.feature_plan({"scenes": [sc2]})
    sc3 = {**_craft("K.shape()"), "features": ["ec.blur.gaussian"]}
    assert "안 씀" in lint.feature_plan({"scenes": [sc3]})[0][2]
    sc4 = {**_craft("K.shape()"), "features": ["ec.stylize.glow"]}      # AI 티 효과만 고른 경우는 쓰라고 하지 않는다(V03 과 충돌)
    assert not lint.feature_plan({"scenes": [sc4]})


def test_release_report_counts_chosen_features():
    import release_report as rr
    sb = {"scenes": [{**_craft("K.fx(t, 'ec.stylize.glow', {})"), "features": ["ec.blur.gaussian"]}]}
    r = rr.craft_features("zz-none", sb)
    assert r["chosen"] == 2


def test_craft_search_korean_benchmark():
    """한국어로 찾았을 때 맞는 효과가 상위 5개 안에(2026-11-19 기준선 3/24 → 고친 뒤 24/24)"""
    import json as _j
    from craft import craft_catalog as cc
    b = _j.loads((ROOT / "tests" / "craft_search_bench.json").read_text("utf-8"))
    top5 = sum(any(r["id"] in ans for _, r in cc.search(q, n=5)) for q, ans in b.items())
    assert top5 >= len(b) - 2, f"top5 {top5}/{len(b)}"


def test_scene_file_inlined(tmp_path):
    from craft import scenefile
    d = ROOT / "data" / "workspace" / "tmp" / "zz-scenefile"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "s01.jsx"
    f.write_text("var t=K.text('a',1,1,9,'#fff'); K.fx(t,'ec.stylize.glow',{});", "utf-8")
    ref = f"$FILE:{f.relative_to(ROOT)}"
    sc = {"features": ["ec.stylize.glow"], "materials": [{"type": "craft", "app": "effectcraft", "steps": [{"id": "script.run", "params": {"code": ref}}]}]}
    assert "K.fx" in scenefile.inline(sc["materials"][0])["steps"][0]["params"]["code"]
    sb = {"format": "concept", "scenes": [sc] * 3}
    assert not lint.craft_depth(sb) and not lint.feature_plan(sb) and not lint.file_refs(sb)
    f.unlink()
    assert lint.file_refs(sb)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_font_catalog_names_resolve():
    """글꼴 목록 — 이름 · 한국어 이름으로 찾고, 묶음 글꼴은 받지 않고 바로 쓴다"""
    import fonts
    cat = fonts.catalog()
    assert len(cat) >= 30 and all(f.get("license") == "OFL" for f in cat)
    assert all(fonts.path_of(f["ps"]) for f in cat if f.get("bundled"))
    from craft import motion
    assert motion._catalog_font("도현") == "DoHyeon-Regular"
    assert motion._catalog_font("Gowun Batang") == "GowunBatang-Bold"
    assert motion._catalog_font("없는 글꼴") is None


def test_direction_modes_fill_defaults_but_keep_explicit():
    from craft import design
    sb = {"direction": {"mode": "cinematic", "layout": "card", "subs": {"y": 0.7}}}
    d = design.with_mode(sb)["direction"]
    assert d["letterbox"] and d["pin_title"] is False and d["layout"] == "full"      # 레퍼런스가 채운 layout 은 모드가 이긴다
    assert d["subs"]["y"] == 0.7 and d["subs"]["box"] is False                       # 직접 적은 자막 칸은 그대로, 나머지는 모드
    sb["direction"]["layout_user"] = True
    assert design.with_mode(sb)["direction"]["layout"] == "card"
    assert design.with_mode({"direction": {"mode": "comic"}})["direction"]["subs"]["bubble"] is True
    assert design.with_mode({"direction": {}}) == {"direction": {}}


def test_bundle_writes_files_inside_composition_and_checks(tmp_path, monkeypatch):
    import json, sys
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import bundle
    sid = "2026-11-19-ztestbd-01"
    sb = json.loads((ROOT / "engine" / "spec" / "examples" / "storyboard.example.json").read_text("utf-8"))
    sb["id"] = sid
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"storyboard": sb, "files": {"scenes/s01.jsx": "K.scene(3);"}}), "utf-8")
    try:
        assert bundle.apply(f) == sid
        assert (ROOT / "data" / "compositions" / sid / "scenes" / "s01.jsx").read_text() == "K.scene(3);"
        hard, soft = bundle.check(sid)
        assert isinstance(hard, list) and isinstance(soft, list)
        f.write_text(json.dumps({"storyboard": sb, "files": {"../../escape.txt": "x"}}), "utf-8")
        import pytest
        with pytest.raises(SystemExit):
            bundle.apply(f)
    finally:
        import shutil
        shutil.rmtree(ROOT / "data" / "compositions" / sid, ignore_errors=True)
        for x in (ROOT / "data" / "storyboards").glob(f"{sid}.json*"):
            x.unlink()


def test_converge_blocks_only_unresolved_baseline(tmp_path):
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import shutil
    import skill_pass as sp
    sid = "ztest-converge-unit"
    blk = lambda x: x.get("kind") in sp.BLOCKING  # noqa: E731
    try:
        sp.converge(sid, "viewer", {"issues": [{"scene": 1, "kind": "흐름 끊김", "what": "A"}, {"scene": 4, "kind": "넘김", "what": "C"}], "score": 6}, "issues", blk)
        r = sp.converge(sid, "viewer", {"verify": [{"id": 1, "resolved": True}], "new": [{"scene": 6, "kind": "흐름 끊김", "what": "NEW"}], "score": 5}, "issues", blk)
        assert [x["what"] for x in r["issues"]] == ["C"] and [x["what"] for x in r["advice"]] == ["NEW"] and r["score"] < 7
        r = sp.converge(sid, "viewer", {"verify": [{"id": 1, "resolved": True}, {"id": 2, "resolved": True}], "new": [{"scene": 2, "kind": "넘김", "what": "N2"}], "score": 6}, "issues", blk)
        assert r["issues"] == [] and r["score"] == 8
    finally:
        shutil.rmtree(ROOT / "data" / "compositions" / sid, ignore_errors=True)


def test_parse_scenes_accepts_lists_and_ranges():
    sys.path.insert(0, str(ROOT / "engine"))
    import render
    assert render.parse_scenes("3,5,6,7", 8) == [2, 3, 4, 5, 6]
    assert render.parse_scenes("2-3,6", 8) == [1, 2, 3, 4, 5]
    assert render.parse_scenes("4", 8) == [3]


def test_cue_word_must_be_in_narration():
    sb = {"id": "x", "scenes": [{"narration": "고양이는 상자에 들어가요", "materials": [{"type": "craft", "id": "a", "steps": "K.pop(a, $CUE:상자)"}]},
                                {"narration": "전혀 다른 말", "materials": [{"type": "craft", "id": "b", "steps": "K.pop(b, $CUE:우주선)"}]}]}
    codes = [(c, i) for c, i, _ in lint.cue_check(sb)]
    assert codes == [("L73", 1)]


def test_carry_transition_jsx_has_carrier_and_monotonic_wake(tmp_path):
    import json as _j
    from PIL import Image
    from craft import motion
    d = tmp_path / "bee.anim"; d.mkdir()
    Image.new("RGBA", (64, 64), (250, 200, 60, 255)).save(d / "f000.png")
    (d / "anim.json").write_text(_j.dumps({"fps": 24}))
    js = motion.carry_jsx("x", {"by": str(d / "f000.png"), "path": [[-0.2, 0.7], [0.5, 0.5], [1.2, 0.3]], "dur": 1.0}, 1, 2.0, 540, 960)
    assert "conformFrameRate = 24" in js and "Carry 01" in js and "setTrackMatte" in js
    assert js.count("tp.setValueAtTime") >= 8                         # 지나간 자리가 시간에 따라 자란다


def test_osc_track():
    from craft import form as F
    assert abs(F._track_at({"osc": [10, 5, 2]}, 0.125, 1.0) - 15) < 1e-6
    assert F._track_at({"osc": [[0, 1], [2, 0], 1]}, 0.25, 1.0) == [2.0, 1.0]
