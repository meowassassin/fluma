#!/usr/bin/env python3
"""생성 경로용 콘티 보강 — assemble 이 만든 얇은 storyboard 에 연출 · 디자인 · 레퍼런스 칸을 채운다.

  python3 engine/story/board_enrich.py <콘티.json> [--plan <shotplan id>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401

SHOT_FN = {"hook": "충격", "build": "힘", "turn": "변화", "payoff": "여운", "cta": "끝"}


def _shotplan(pid: str) -> dict | None:
    p = ROOT / "data" / "shotplans" / f"{pid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def enrich(sbp: Path, plan: dict | None = None) -> list[str]:
    """콘티 파일을 읽고 보강해 저장한다 → 바뀐 칸 요약 목록"""
    sb = json.loads(sbp.read_text("utf-8"))
    pid = sb.get("id") or sbp.stem
    plan = plan or _shotplan(pid) or {}
    changed: list[str] = []
    sb.setdefault("meta", {})
    sb["meta"]["compose_mode"] = sb["meta"].get("compose_mode") or "overlay"
    sb["meta"]["quality_tier"] = sb["meta"].get("quality_tier") or "delivery"

    trend = plan.get("trend") or {}
    refs = list(sb.get("reference") or [])
    for key in ("refs", "reference_ids"):
        for rid in trend.get(key) or []:
            if rid and rid not in refs:
                refs.append(str(rid))
    if refs and refs != sb.get("reference"):
        sb["reference"] = refs[:5]
        changed.append("reference")

    if plan.get("topic") and not sb.get("topic"):
        sb["topic"] = plan["topic"]
        changed.append("topic")
    logline = (plan.get("logline") or plan.get("title") or "").strip()
    if logline and not (sb.get("intent") or {}).get("one_line"):
        sb["intent"] = {**(sb.get("intent") or {}), "one_line": logline[:200]}
        changed.append("intent")

    style = plan.get("style") or {}
    d = sb.setdefault("direction", {})
    if not isinstance(d.get("art"), dict):
        accent = style.get("accent") or "#FFD60A"
        d["art"] = {
            "palette": {"bg": "#08080c", "ink": "#f2f2f4", "accent": accent},
            "rule": (style.get("en") or plan.get("style_en") or "풀프레임 생성 클립, 샷마다 시선 한 곳, 레터박스 띠 금지")[:160],
            "avoid": "가운데 작은 카드, 추상 구슬, caption=나레이션 전부 복붙",
        }
        changed.append("direction.art")
    if d.get("layout") in (None, "", "card"):
        d["layout"] = "full"
        changed.append("direction.layout")
    if not d.get("anchors"):
        shots = plan.get("shots") or []
        bg0 = (shots[0].get("background") or shots[0].get("action") or "")[:80] if shots else ""
        d["anchors"] = {
            "emotion": (plan.get("topic") or sb.get("title") or "주제")[:48],
            "motif": style.get("motif") or "샷마다 카메라·앵글 변화",
            "object": bg0 or "첫 샷 핵심 소품",
            "break": "turn 샷",
            "final_image": "payoff 샷",
        }
        changed.append("direction.anchors")

    shots = plan.get("shots") or []
    scenes = sb.get("scenes") or []
    for sc, sh in zip(scenes, shots):
        pur = sh.get("purpose") or sc.get("role") or ""
        if not sc.get("shot_fn") and pur in SHOT_FN:
            sc["shot_fn"] = SHOT_FN[pur]
        if not sc.get("beat") and sh.get("beat"):
            sc["beat"] = sh["beat"]
        narr = (sc.get("narration") or "").strip()
        cap = (sc.get("caption") or "").strip()
        ost = (sh.get("on_screen_text") or "").strip()
        if narr and cap == narr:
            if ost:
                sc["caption"] = ost[:32]
            elif pur == "hook" and len(narr) > 18:
                sc["caption"] = narr[:16].rstrip() + "…"
            elif len(narr) > 24:
                sc["caption"] = narr[:22].rstrip() + "…"
        if pur in ("hook", "turn", "payoff") and not sc.get("beats"):
            sc["beats"] = [{"do": "확대", "t": 0.35}]
        sc.setdefault("visual", {"kind": "footage", "motion": "kenburns_in" if pur == "hook" else "none"})

    sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    subprocess.run(
        [sys.executable, str(ROOT / "engine" / "story" / "direct.py"), str(sbp), "--write"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    sb = json.loads(sbp.read_text("utf-8"))
    d = sb.setdefault("direction", {})
    if sb.get("meta", {}).get("compose_mode") == "overlay" and d.get("layout") in (None, "", "card", "band"):
        d["layout"] = "full"
        locked = d.get("locked") if isinstance(d.get("locked"), list) else []
        if d.get("locked") is not True and "layout" not in locked:
            locked.append("layout")
            d["locked"] = locked
        changed.append("direction.layout(lock)")
        sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    from material_evidence import apply_file  # noqa: E402

    me = apply_file(sbp, write=True)
    if me:
        changed.extend(me)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("storyboard")
    ap.add_argument("--plan", help="shotplan id (기본: 콘티 id)")
    a = ap.parse_args()
    sbp = Path(a.storyboard)
    if not sbp.is_absolute():
        sbp = ROOT / sbp
    if not sbp.exists():
        print(f"콘티 없음: {sbp}", file=sys.stderr)
        return 1
    pid = a.plan or json.loads(sbp.read_text("utf-8")).get("id") or sbp.stem
    ch = enrich(sbp, _shotplan(pid))
    print(json.dumps({"changed": ch}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())