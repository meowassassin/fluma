#!/usr/bin/env python3
"""릴리즈 기준 측정 — 스튜디오에서 만든 영상 한 편(세션)이 기준을 넘었나.

기준(2026-11-18 사용자와 정함 · 볼트 07 Planning/릴리즈 기준):
  agent_min      에이전트 작업 시간(주제 확정 → 완성) ≤ 15분
  produce_full   전체 제작(렌더까지) 횟수 ≤ 3
  block          품질 관문 막음 0(면제 없이)
  fix_turns      제작이 시작된 뒤 사용자가 바로잡은 턴 ≤ 2
  user_cmds      사용자가 직접 실행한 명령 0 (크레딧 쓰는 생성은 제외 — 세션 밖이라 여기선 안 셈)
같은 경로로 서로 다른 주제 3편이 연속 통과하면 릴리즈 후보.

  python3 engine/checks/release_report.py <id> [<id> ...]     # 표 + 기준 통과 여부
  python3 engine/checks/release_report.py --json <id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
WS = ROOT / "data" / "workspace"
LIMITS = {"agent_min": 15.0, "produce_full": 3, "block": 0, "fix_turns": 2}


def _jsonl(p: Path, sid: str) -> list[dict]:
    try:
        return [d for d in (json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()) if d.get("id") == sid]
    except OSError:
        return []


def measure(sid: str) -> dict:
    s = json.loads((WS / "sessions" / f"{sid}.json").read_text("utf-8"))
    msgs = s.get("messages") or []
    asst = [m for m in msgs if m.get("role") == "assistant"]
    users = [m for m in msgs if m.get("role") == "user"]

    def runs_produce(m: dict) -> bool:
        return any("engine/produce.py" in json.dumps(t.get("input"), ensure_ascii=False) for t in m.get("tools") or [])

    first_prod = next((m["ts"] for m in asst if runs_produce(m)), None)
    # 제작 시작 턴의 요청 이후에 온 사용자 말 = 바로잡은 턴(결과를 보고 한 요청 포함)
    start_req = max((u["ts"] for u in users if first_prod and u["ts"] < first_prod), default=None)
    fix_turns = sum(1 for u in users if start_req and u["ts"] > start_req)
    prod = _jsonl(WS / "results" / "produce-timings.jsonl", sid)
    skill = _jsonl(WS / "results" / "skill-pass-timings.jsonl", sid)
    try:
        q = json.loads((WS / "tmp" / sid / "quality.json").read_text("utf-8"))
    except (OSError, ValueError):
        q = {}
    out = {
        "id": sid,
        "wall_min": round((msgs[-1]["ts"] - msgs[0]["ts"]) / 60000, 1) if msgs else 0,
        "agent_min": round(sum((m.get("durationMs") or 0) for m in asst) / 60000, 1),
        "agent_min_after_start": round(sum((m.get("durationMs") or 0) for m in asst if start_req and m["ts"] > start_req) / 60000, 1),
        "turns": len(users),
        "fix_turns": fix_turns,
        "tool_calls": sum(len(m.get("tools") or []) for m in asst),
        "produce_runs": len(prod),
        "produce_full": sum(1 for p in prod if "render" in p),
        "render_sec": round(sum(p.get("render", 0) for p in prod), 1),
        "llm_pass_sec": round(sum(x["sec"] for x in skill if x["phase"].endswith("_agent")), 1),
        "llm_calls": sum(1 for x in skill if x["phase"].endswith("_agent") and x["sec"] > 1),
        "cost_usd": round(sum((m.get("cost") or 0) for m in asst), 2),
        "block": len(q.get("block") or []),
        "advise": len(q.get("advise") or []),
        "waived": len(q.get("waived") or []),
        "finished": bool(q) and not q.get("block"),
    }
    try:                                          # 다양성 · 앱 깊이(2026-11-19) — 장면 흐름 · K 키트만 쓴 장면 비율
        sys.path.insert(0, str(ROOT / "engine" / "checks"))
        import lint as _lint
        sbj = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
        scn = [s for s in sbj.get("scenes") or [] if s.get("materials")]
        out["flow"] = _lint.flow_sig(sbj)
        out["kit_only"] = f"{len(_lint.kit_only_scenes(sbj))}/{len(scn)}"
        out["accent"] = ((sbj.get("direction") or {}).get("color_accent"))
    except (OSError, ValueError, ImportError):
        out.update(flow=None, kit_only=None, accent=None)
    out["pass"] = {k: (out[k] <= v) for k, v in LIMITS.items()} | {"finished": out["finished"], "no_waiver": out["waived"] == 0}
    out["ok"] = all(out["pass"].values())
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    rows = [measure(a) for a in args]
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    for r in rows:
        print(f"\n## {r['id']}  {'통과' if r['ok'] else '미달'}")
        print(f"  전체 {r['wall_min']}분 · 에이전트 {r['agent_min']}분(제작 시작 뒤 {r['agent_min_after_start']}분) · 비용 ${r['cost_usd']}")
        print(f"  사용자 턴 {r['turns']}(제작 시작 뒤 {r['fix_turns']}) · 도구 호출 {r['tool_calls']}")
        print(f"  produce {r['produce_runs']}회(렌더까지 {r['produce_full']}회 · 렌더 {r['render_sec']}초) · LLM 단계 {r['llm_calls']}회 {r['llm_pass_sec']}초")
        print(f"  품질 관문: 막음 {r['block']} · 권고 {r['advise']} · 면제 {r['waived']}")
        print(f"  다양성: 흐름 {r.get('flow')} · K 키트만 쓴 장면 {r.get('kit_only')} · 강조색 {r.get('accent')}")
        print("  기준: " + " · ".join(f"{k} {'✓' if v else '✗'}" for k, v in r["pass"].items()))
    streak = 0
    for r in rows:
        streak = streak + 1 if r["ok"] else 0
    print(f"\n연속 통과 {streak}편 / 3편 필요")
    return 0 if streak >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
