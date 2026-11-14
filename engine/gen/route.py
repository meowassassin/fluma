#!/usr/bin/env python3
"""1단계 경로 고르기 — 이 영상에 영상 생성이 필요한가? 필요 없으면 실제 자료로 만든다(생성은 크레딧 · 시간 · 승인 단계가 든다).

경로
  generate  생성(engine/gen 1~6단계): 세상에 없는 장면 · 캐릭터 연기 · 상상 · 이야기 장면이 영상의 중심
  clip      클립 재편집(asset-edit 스킬 · engine/gen/dub.py): 원본 영상 하나를 다시 엮는 밈 · 반응 · 더빙 자막
  material  실제 자료 편집(storyboard · produce 스킬 · engine/produce.py): 화면 녹화 · 사진 · 스톡 · 퍼온 클립 여러 개 · 차트 · 문서로 충분한 설명 · 뉴스 · 비교 · 순위 · 사용법 · 광고

고르는 방식(2026-11-12 사용자 결정): 에이전트가 요청 · 링크 · 레퍼런스를 보고 추천 경로와 이유 한 줄을 정해 세 경로를 선택지로 보여 주고(추천이 첫째),
사용자가 고른다. 낱말 신호로 자동 추천하던 suggest 는 판단이 얕아 없앴다. 이 도구는 고른 경로를 샷 계획에 기록만 한다(작업 공간 화면이 보여 줌).
  python3 engine/gen/route.py set <plan id> <generate|clip|material> --why "<이유 한 줄>" [--topic "<주제>"] [--storyboard data/storyboards/<id>.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402

def set_route(pid: str, route: str, why: str, storyboard: str | None, topic: str | None = None, by: str = "user") -> Path:
    import plan as planmod
    p = planmod.PLANS / f"{pid}.json"
    planmod.PLANS.mkdir(parents=True, exist_ok=True)
    sb = json.loads(p.read_text("utf-8")) if p.exists() else {"id": pid, "topic": pid, "aspect": "9:16", "style": "", "needs_character": False, "shots": []}
    if topic:
        sb["topic"] = topic
    sb["route"] = route
    sb["route_why"] = why
    sb["route_by"] = by
    if planmod.made_by() and not sb.get("made_by"):      # 처음 기획한 에이전트만(나중 설정 변경과 무관하게)
        sb["made_by"] = planmod.made_by()
    if storyboard:
        sb["handoff"] = storyboard
    elif route == "clip":
        sb["handoff"] = f"data/compositions/{pid}/dub.json"
    elif route == "material":
        sb["handoff"] = f"data/storyboards/{pid}.json"
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    st = sp.add_parser("set"); st.add_argument("pid"); st.add_argument("route", choices=["generate", "clip", "material"]); st.add_argument("--why", required=True, help="추천 이유 · 사용자가 고른 것")
    st.add_argument("--by", choices=["user", "default"], default="user", help="user = 사용자가 골랐다 · default = 사용자가 '알아서'라고 해 추천대로"); st.add_argument("--storyboard"); st.add_argument("--topic", help="주제(작업 공간 제목)")
    a = ap.parse_args()
    p = set_route(a.pid, a.route, a.why, a.storyboard, a.topic, a.by)
    nxt = {"generate": "plan 스킬 — 8초 이하 샷 칸 → 2 · 3 · 4단계", "clip": "asset-edit 스킬 — clip.py fetch → cutaway → dub.json → dub.py build",
           "material": "storyboard · produce 스킬 — 조사 · 콘티(실제 자료 재료) → produce.py"}[a.route]
    ok("route", plan=str(p.relative_to(ROOT)), route=a.route, next=nxt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
