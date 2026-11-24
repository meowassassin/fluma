"""제작 품질 — 사용자에게 '모드'를 묻지 않는 단일 프로필.

  한 번에 납품 해상도로 렌더(초안 half 생략) · 콘티 보강 · direct 기록.
  produce: writer·director·designer skill_pass + 렌더 전 화면 검토(review) 기본 ON, refine 은 FLUMA_DEEP_REFINE=1 일 때만.
  끄기: FLUMA_PRODUCE_SKILLS=0 · FLUMA_SKIP_SKILLS=1 · FLUMA_DEEP_REVIEW=0 · produce --fast/--no-skills

개발용만: FLUMA_MODE=draft(초안만)
"""
from __future__ import annotations

import os


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    return v if v is not None and str(v).strip() != "" else None


def use_draft_render() -> bool:
    return _env("FLUMA_MODE") == "draft"


def hard_skills() -> bool:
    e = _env("FLUMA_HARD_SKILLS")
    return e == "1" if e is not None else False


def skip_skill_pass() -> bool:
    return _env("FLUMA_SKIP_SKILLS") == "1"


def deep_review() -> bool:
    """skill_pass 화면 검토(review, 렌더 전 정지 화면) — 기본 켬(refine 은 FLUMA_DEEP_REFINE=1 일 때만)."""
    if _env("FLUMA_DEEP_REVIEW") == "0":
        return False
    return True


def run_skill_pass_in_produce(*, skills_ok: bool = False) -> bool:
    """produce/assemble 안 skill_pass writer·director·designer — 기본 켬. FLUMA_PRODUCE_SKILLS=0 만 끔."""
    if skip_skill_pass():
        return False
    if _env("FLUMA_PRODUCE_SKILLS") == "0":
        return False
    return True


def skip_viewer_pass() -> bool:
    """시청자 시뮬(viewer) — 기본 켬. FLUMA_SKIP_VIEWER=1 로만 생략."""
    return _env("FLUMA_SKIP_VIEWER") == "1"
