#!/usr/bin/env python3
"""기획 준비 한 번에 — 경로 기록 · 트렌드 검색 · 레퍼런스 고르기 · 분석 · 이미 보여 준 선택지를 명령 하나로(2026-11-19 속도: 한 편 15분).

에이전트가 이 단계들을 하나씩 부르면 도구 왕복만 20~40번이었다. 판단이 필요 없는 일은 여기서 하고, 짧은 요약만 돌려준다.
에이전트가 할 일은 이 요약을 보고: 사실 조사(WebSearch → data/research/<id>.json) · 선택지(각도) · 콘티.

  python3 engine/story/prepare.py <id> "<주제>" [--queries "검색어1,검색어2"] [--refs a b c] [--route material|clip]
결과: data/compositions/<id>/prepare.json (+ 출력 요약). 레퍼런스 분석은 서버 작업이라 동시에 돈다(편당 1분 안팎).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

PY = sys.executable
XRAY = ROOT / "data" / "public" / "trends" / "xray"


def _run(args: list[str], timeout: int = 600) -> tuple[int, str]:
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _arg(a: list[str], k: str, d=None):
    return a[a.index(k) + 1] if k in a else d


def _refs_from_trends(topic: str, queries: str | None, n: int = 3) -> tuple[list[dict], str]:
    """주제와 맞는 쇼츠 — 이미 찾아 둔 목록에서, 모자라면 새로 검색"""
    sys.path.insert(0, str(ROOT / "engine" / "gen"))
    import plan
    br = plan.trend_brief(None, None, 12, queries or topic)
    how = "기존 목록"
    if not br.get("topic_matched"):
        _run(["engine/research/trends.py", "search", "--queries", queries or topic, "--label", topic[:40], "--limit", "8"], timeout=300)
        br = plan.trend_brief(None, None, 12, queries or topic)
        how = "새로 검색"
    top = [x for x in br.get("top") or [] if x.get("id")]
    return top[:n], how


def _understanding(vid: str) -> dict:
    try:
        x = json.loads((XRAY / vid / "xray.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    u = x.get("understanding") or {}
    cut = lambda v, n=160: str(v or "")[:n]  # noqa: E731
    return {"summary": cut(u.get("summary"), 200), "hook": cut(u.get("hook")), "editing": cut(u.get("editing")), "borrow": cut(u.get("borrow")),
            "do_not_copy": cut(u.get("do_not_copy"), 120), "cliches": cut(u.get("cliches"), 160), "recipe": (x.get("recipe") or [])[:5]}


def main() -> int:
    a = sys.argv[1:]
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or not a[i - 1].startswith("--"))]
    if len(pos) < 2:
        print(__doc__); return 2
    pid, topic = pos[0], pos[1]
    t0 = time.time()
    route = _arg(a, "--route", "material")
    sp = ROOT / "data" / "shotplans" / f"{pid}.json"
    if not sp.exists() or not json.loads(sp.read_text("utf-8")).get("route"):
        _run(["engine/gen/route.py", "set", pid, route, "--why", "기본 경로(실제 자료 · Craft 2D) — prepare.py", "--topic", topic, "--by", "default"])
    refs = [{"id": r} for r in a[a.index("--refs") + 1:] if not r.startswith("--")] if "--refs" in a else None
    how = "지정"
    if not refs:
        refs, how = _refs_from_trends(topic, _arg(a, "--queries"))
    ids = [r["id"] for r in refs]
    if ids:
        _run(["engine/research/analyze_ref.py", *ids, "--wait", "420"], timeout=480)
    sys.path.insert(0, str(ROOT / "engine" / "gen"))
    import plan
    out = {"id": pid, "topic": topic, "route": route,
           "references": [{"id": r["id"], "title": r.get("title"), "views": r.get("views"), **_understanding(r["id"])} for r in refs],
           "references_from": how, "angles": list(plan.ANGLES), "already_offered": plan.offered()[:15],
           "research_file": f"data/research/{pid}.json", "research_exists": (ROOT / "data" / "research" / f"{pid}.json").exists(),
           "sec": round(time.time() - t0, 1)}
    f = ROOT / "data" / "compositions" / pid / "prepare.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    for r in out["references"]:
        print(f"- 레퍼런스 {r['id']} · 조회 {r.get('views')} · {r.get('title') or ''}\n  요약: {r.get('summary')}\n  빌릴 것: {r.get('borrow')}\n  베끼지 말 것: {r.get('do_not_copy')}")
    print(f"- 각도: {' · '.join(out['angles'])}\n- 이미 보여 준 선택지(겹치지 않게): {' / '.join(out['already_offered'][:8])}")
    if not out["references"]:
        fail("prepare", stage="trends", error="맞는 레퍼런스 쇼츠를 못 찾음 — --queries 로 검색어를 바꾸거나 --refs 로 직접", file=str(f.relative_to(ROOT)))
    ok("prepare", file=str(f.relative_to(ROOT)), refs=" ".join(ids), sec=str(out["sec"]),
       next=f"사실 조사(WebSearch → {out['research_file']}, facts[] + source) → 선택지(각도가 다르게, plan.py vet) → 콘티는 bundle.py 로 한 번에")
    return 0


if __name__ == "__main__":
    sys.exit(main())
