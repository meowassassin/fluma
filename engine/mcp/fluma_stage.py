"""자동 진행의 단계 경계 — 단계를 마친 대화는 다음 단계 도구를 부르지 못하게 하고, 다음 단계는 새 대화에서(2026-11-25).

2026-11-24 실측: 자동 진행 지시('단계마다 턴을 끝내고 새 대화로')를 에이전트가 따르지 않고 한 대화로 끝까지 가
대화가 27.7만 토큰까지 쌓였고, 도구를 부를 때마다 그걸 다시 읽은 것이 비용의 약 70%였다.
글로 된 지시 대신 도구가 막는다. 스튜디오(studio/agent.mjs)는 턴마다 FLUMA_TURN 을 새로 주고, 자동 진행의 다음 턴은 새 대화로 연다.
자동 진행(FLUMA_AUTOPILOT=1)이 아니면 아무것도 막지 않는다 — 사람과 하는 대화 · 다른 도구에서 부를 때는 그대로.

  단계 written  : 대본 · 화면 쓰기가 끝남(bundle.py apply 통과)   → 음성 · 빌드 · 검토 · 렌더 도구를 막는다
  단계 reviewed : 화면 검토 제출(막는 문제 0)                   → 완성 렌더 도구를 막는다
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
BLOCKS = {"written": {"prep_start", "scene_build_start", "review_frames", "scene_still", "render_start", "produce_start"},
          "reviewed": {"render_start", "produce_start"}}
NEXT = {"written": "새 대화에서 음성(prep_start) → 화면 검토(review_frames · review_submit)",
        "reviewed": "새 대화에서 완성 렌더(render_start mode=final) → 품질 관문"}


def _p(pid: str) -> Path:
    return ROOT / "data" / "workspace" / "tmp" / pid / "stage.json"


def active() -> bool:
    # 기본 꺼짐(2026-11-25 실측): Fable 5.2 는 캐시 쓰기 $16/M · 다시 읽기 $0.20/M 이라, 새 대화마다 기본 맥락(약 3.4만)을 다시 쌓는 값이
    # 아끼는 다시 읽기보다 크다. 다시 읽기가 비싼 런타임 · 모델에서만 FLUMA_STAGE_SPLIT=1 로 켠다
    return os.environ.get("FLUMA_STAGE_SPLIT") == "1" and os.environ.get("FLUMA_AUTOPILOT") == "1" and bool(os.environ.get("FLUMA_TURN")) and not os.environ.get("FLUMA_JOB_ID")


def mark(pid: str, stage: str) -> str | None:
    """단계를 마쳤다고 적는다 — 자동 진행일 때만. 에이전트에게 보일 한 줄(턴을 끝내라)을 돌려준다"""
    if not active():
        return None
    p = _p(pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"stage": stage, "turn": os.environ["FLUMA_TURN"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), "utf-8")
    return end_line(stage)


def end_line(stage: str) -> str:
    return (f"자동 진행: 이 대화의 단계({stage})가 끝났다 — 더 부르지 말고 한 줄 보고로 지금 턴을 끝낸다. "
            f"서버가 {NEXT[stage]} 을 이어 간다(앞 대화의 도구 출력을 다시 읽지 않게)")


def check(pid: str, tool: str) -> None:
    """이 대화가 이미 단계를 마쳤는데 다음 단계 도구를 부르면 막는다"""
    if not active():
        return
    try:
        rec = json.loads(_p(pid).read_text("utf-8"))
    except (OSError, ValueError):
        return
    if rec.get("turn") == os.environ.get("FLUMA_TURN") and tool in BLOCKS.get(rec.get("stage"), ()):
        raise ValueError(end_line(rec["stage"]))
