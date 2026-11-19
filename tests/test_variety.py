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
    sc2 = {**_craft("var t=K.text('a',1,1,9,'#fff'); K.fx(t,'ec.stylize.glow',{})"), "features": ["ec.stylize.glow"]}
    assert not lint.feature_plan({"scenes": [sc2]})
    sc3 = {**_craft("K.shape()"), "features": ["ec.stylize.glow"]}
    assert "안 씀" in lint.feature_plan({"scenes": [sc3]})[0][2]


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
