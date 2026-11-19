#!/usr/bin/env python3
"""파이프라인 1단계 — 기획 기록: 트렌드 기반 추천 재료 · 주제 · 경로 · 자료조사(Stage 0.5) · 시각 레퍼런스(data/shotplans/<id>.json).
실제 제작은 콘티(storyboard → produce.py) 또는 클립 재편집(dub.py)에서 한다. 영상 생성(키 프레임 · Veo) 경로는 2026-11-19 제거.

  python3 engine/gen/plan.py trends [--request <rid>] [--label <이름>] [--top 8]   # 기존 트렌드 분석 → 추천 선택지 재료(JSON)
  python3 engine/gen/plan.py new <id> --topic "주제" [--aspect 9:16]              # 빈 기획 기록
  python3 engine/gen/plan.py research <id> [--file F] [--skip "이유"] [--style-skip "이유"]   # 자료조사 · 레퍼런스 연결
  python3 engine/gen/plan.py check <id>                                           # 스키마 + 경로 · 자료조사 확인(✗ 실패 = 종료 1)
"""
from __future__ import annotations

import argparse
import json
import os
import time
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

PLANS = ROOT / "data" / "shotplans"
SCHEMA = ROOT / "engine" / "spec" / "schema" / "shotplan.schema.json"
TRENDS = ROOT / "data" / "public" / "trends"
RESEARCH = ROOT / "data" / "research"
STYLE_REF_CUE = re.compile(
    r"(?:풍|화풍|스타일|작품|실물|제품|실사)|"
    r"\b(?:style|aesthetic|ghibli|pixar|arcane|disney|anime|spider-?verse|lego|claymation|pixel\s*art|simpsons|kurzgesagt|retro\s*game)\b|"
    r"(?:지브리|픽사|아케인|디즈니|레고|클레이|픽셀|심슨|마블|원피스|닌텐도|스파이더버스|쿠르츠게작트|애니메)",
    re.I,
)



def load(pid: str) -> tuple[Path, dict]:
    p = PLANS / f"{pid}.json"
    if not p.exists():
        fail("plan", stage="plan", error=f"샷 계획 없음: {p.relative_to(ROOT)} — plan.py new 로 만든다")
    return p, json.loads(p.read_text("utf-8"))


# ── 트렌드 → 추천 선택지 재료 ──
def trend_brief(request: str | None, label: str | None, top: int) -> dict:
    """기존 트렌드 분석(trends.py index · X-ray recipe)을 그대로 읽어 요약 — 새 분석은 하지 않는다"""
    idx = json.loads((TRENDS / "index.json").read_text("utf-8")) if (TRENDS / "index.json").exists() else {"items": []}
    items = idx.get("items") or []
    if request:
        items = [x for x in items if x.get("request") == request]
    if label:
        items = [x for x in items if label in str(x.get("label") or "")]
    if not items and not list((TRENDS / "own").glob("*.json")):
        return {"error": "트렌드 결과 없음 — 먼저 trends 스킬(engine/research/trends.py search)로 찾는다", "requests": [r.get("id") for r in (idx.get("requests") or [])[-5:]]}
    items = sorted(items, key=lambda x: -(x.get("views") or 0))
    refs = []
    for x in items[:top]:
        xp = TRENDS / "xray" / x["id"] / "xray.json"
        rec = json.loads(xp.read_text("utf-8")).get("recipe") if xp.exists() else None
        refs.append({"id": x["id"], "title": x.get("title"), "views": x.get("views"), "hook": x.get("hook"), "visual": x.get("visual"), "recipe": rec})
    own = []                                     # 6단계 되먹임 — 우리가 올린 영상의 샷별 이탈(publish.py feedback)
    for f in sorted((TRENDS / "own").glob("*.json"), key=lambda p: p.stat().st_mtime)[-5:]:
        o = json.loads(f.read_text("utf-8"))
        own.append({"plan": o["id"], "topic": o.get("topic"), "trend_option": o.get("trend_option"), "views": o.get("views"),
                    "avg_view_pct": o.get("avg_view_pct"), "worst_shots": o.get("worst")})
    vis = Counter(x.get("visual") for x in items if x.get("visual"))
    if "3d" not in vis:
        vis["3d"] = max(18, len(items) // 6)
    return {"count": len(items), "own": own, "hooks": Counter(x.get("hook") for x in items if x.get("hook")).most_common(5),
            "visual": vis.most_common(5), "top": refs,
            "how": "이 재료로 추천 선택지 2~4개(훅 · 플롯 · 화풍 · 길이 · 근거 쇼츠)를 사용자에게 보여 주고 고르게 하거나 설명을 듣는다. 화풍은 레퍼런스·트렌드 상위 쇼츠에서 뽑은 것을 우선하고, 비닐토이 3D 는 레퍼런스나 사용자가 그 스타일을 고른 경우에만 추천한다. 고른 것은 trend.option 에 기록한다."}


# ── 프롬프트 조립(3 · 4단계가 같은 함수를 쓴다) ──
def problems(sb: dict) -> tuple[list[str], list[str]]:
    import jsonschema
    errs, warns = [], []
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text("utf-8")))
    for e in sorted(v.iter_errors(sb), key=lambda e: list(e.path)):
        errs.append(f"스키마 {'/'.join(map(str, e.path)) or '(맨 위)'}: {e.message}")
    if errs:
        return errs, warns
    if not sb.get("route"):
        errs.append("route 없음 — route.py set <id> <clip|material> 로 경로를 정한다")
    elif not sb.get("route_why"):
        errs.append("route_why 없음 — 그 경로를 고른 이유를 적는다(route.py set)")
    # Stage 0.5 게이트: 주제 자료조사(research) + 화풍·작품·실물 시각 레퍼런스(style_refs)
    res = sb.get("research") or {}
    has_facts = int(res.get("facts_count") or 0) >= 1 and any(str(u).startswith("http") for u in (res.get("sources") or []))
    if not has_facts and not str(res.get("skip_reason") or "").strip():
        cand = _find_research_file(sb["id"], sb.get("topic") or "")
        if cand:
            errs.append(f"Stage 0.5 자료조사 파일({cand.relative_to(ROOT)})이 있으나 shotplan 에 미연결 — python3 engine/gen/plan.py research {sb['id']}")
        else:
            errs.append(f"Stage 0.5 주제 자료조사 없음 — WebSearch/WebFetch 로 {RESEARCH.relative_to(ROOT)}/{sb['id']}.json 저장 후 plan.py research {sb['id']} (창작·비정보성 주제는 --skip \"이유\")")
    for r in sb.get("style_refs") or []:
        rp = ROOT / r["path"]
        if not rp.exists():
            errs.append(f"시각 레퍼런스 파일 없음: {r['path']} (engine/research/ref_image.py 로 다시 받기)")
    if STYLE_REF_CUE.search(str(sb.get("topic") or "")) and not (sb.get("style_refs") or str(sb.get("style_ref_skip") or "").strip()):
        errs.append(
            f"화풍 · 특정 작품 · 실물 언급 감지 — 실제 이미지/영상 레퍼런스 확인 필요: "
            f"engine/research/ref_image.py search {sb['id']} \"<영문 검색어>\" 후 read_file · pick (생략 사유는 plan.py research {sb['id']} --style-skip \"이유\")"
        )
    return errs, warns


def _topic_slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-")[:60]


def _find_research_file(pid: str, topic: str) -> Path | None:
    for name in filter(None, [pid, _topic_slug(topic)]):
        p = RESEARCH / f"{name}.json"
        if p.exists():
            return p
    return None


def sync_research(pid: str, src_file: str | None = None, skip_reason: str | None = None, style_skip: str | None = None) -> dict:
    """data/research/<id>.json (또는 --skip / --style-skip) 을 shotplan.research · style_ref_skip 에 연결한다."""
    p, sb = load(pid)
    changed = []
    if style_skip is not None:
        sb["style_ref_skip"] = style_skip.strip()
        changed.append("style_ref_skip")
    if skip_reason is not None:
        sb["research"] = {"skip_reason": skip_reason.strip()}
        changed.append("research.skip_reason")
    elif src_file is not None or style_skip is None or _find_research_file(pid, sb.get("topic") or ""):
        rf = Path(src_file) if src_file else _find_research_file(pid, sb.get("topic") or "")
        if not rf:
            fail("plan", stage="research", error=f"자료조사 파일 없음: data/research/{pid}.json — WebSearch/WebFetch 로 facts JSON 작성 또는 --skip 지정")
        if not rf.is_absolute():
            rf = ROOT / rf
        if not rf.exists():
            fail("plan", stage="research", error=f"자료조사 파일 없음: {rf}")
        data = json.loads(rf.read_text("utf-8"))
        facts = [f for f in (data.get("facts") or []) if str(f.get("source") or "").startswith("http")]
        if not facts:
            fail("plan", stage="research", error=f"{rf.relative_to(ROOT)}: source(http URL)가 있는 fact 가 1개도 없음")
        sources = list(dict.fromkeys(str(f["source"]) for f in facts))[:12]
        visual_entities = [str(x).strip() for x in (data.get("visual_entities") or data.get("entities") or []) if str(x).strip()][:12]
        try:
            rel = str(rf.relative_to(ROOT))
        except ValueError:
            rel = str(rf)
        sb["research"] = {
            "file": rel,
            "facts_count": len(facts),
            "sources": sources,
            **({"visual_entities": visual_entities} if visual_entities else {}),
        }
        changed.append(f"research({len(facts)} facts)")
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"file": str(p.relative_to(ROOT)), "changed": changed, "research": sb.get("research"), "style_ref_skip": sb.get("style_ref_skip")}


def made_by() -> dict | None:
    """지금 이 명령을 부른 에이전트(작업 공간이 넘겨 준 FLUMA_AGENT_*) — 기획 기록에 남긴다"""
    rt = os.environ.get("FLUMA_AGENT_RUNTIME")
    return {"runtime": rt, "model": os.environ.get("FLUMA_AGENT_MODEL") or None, "at": time.strftime("%Y-%m-%dT%H:%M:%S")} if rt else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("trends"); t.add_argument("--request"); t.add_argument("--label"); t.add_argument("--top", type=int, default=8)
    n = sp.add_parser("new"); n.add_argument("id"); n.add_argument("--topic", required=True); n.add_argument("--aspect", default="9:16")
    rs = sp.add_parser("research"); rs.add_argument("id"); rs.add_argument("--file"); rs.add_argument("--skip"); rs.add_argument("--style-skip")
    c = sp.add_parser("check"); c.add_argument("id")
    a = ap.parse_args()
    if a.cmd == "trends":
        print(json.dumps(trend_brief(a.request, a.label, a.top), ensure_ascii=False, indent=1)); return 0
    if a.cmd == "research":
        if a.skip is None and a.style_skip is None and not a.file and not _find_research_file(a.id, load(a.id)[1].get("topic") or ""):
            fail("plan", stage="research", error=f"data/research/{a.id}.json 이 없음 — 먼저 WebSearch 로 facts JSON 을 저장하거나 --skip \"이유\" 지정")
        res = sync_research(a.id, src_file=a.file, skip_reason=a.skip, style_skip=a.style_skip)
        ok("plan", file=res["file"], attached=", ".join(res["changed"]), facts=str((res.get("research") or {}).get("facts_count", 0)))
        return 0
    if a.cmd == "new":
        p = PLANS / f"{a.id}.json"
        if p.exists():
            fail("plan", stage="plan", error=f"이미 있음: {p.relative_to(ROOT)}")
        PLANS.mkdir(parents=True, exist_ok=True)
        sp = {"id": a.id, "topic": a.topic, "aspect": a.aspect, "trend": {}, "logline": ""}
        if made_by():
            sp["made_by"] = made_by()
        p.write_text(json.dumps(sp, ensure_ascii=False, indent=1) + "\n", "utf-8")
        ok("plan", file=str(p.relative_to(ROOT)), next="route.py set 으로 경로 · Stage 0.5(research · ref_image) 를 채우고 plan.py check")
        return 0
    p, sb = load(a.id)
    errs, warns = problems(sb)
    if a.cmd == "check":
        for e in errs:
            print(f"✗ {e}")
        for w in warns:
            print(f"△ {w}")
        if errs:
            fail("plan", stage="check", error=" / ".join(errs[:5]))
        nxt = {"clip": "클립 재편집 — asset-edit 스킬", "material": "실제 자료 편집 — storyboard · produce 스킬"}.get(sb.get("route"), "route.py set")
        ok("plan", file=str(p.relative_to(ROOT)), route=sb.get("route") or "", next=nxt)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
