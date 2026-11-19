#!/usr/bin/env python3
"""장면 코드 파일 — 콘티 재료 칸에 "$FILE:data/compositions/<id>/scenes/s01.jsx" 를 쓰면 그 파일 내용으로 펼친다.

2026-11-19: 장면 코드(EffectCraft JSX)가 콘티 JSON 문자열 안에 있어 에이전트가 Edit 로 한 칸씩 고쳤다(영상 3편에 Edit 234번).
파일로 빼면 장면 하나를 Write 한 번으로 고치고, 재료 처리 맨 앞에서 펼치므로 $CUE · 재료 캐시 · 검사(lint)가 그대로 동작한다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
PREFIX = "$FILE:"


def _read(ref: str) -> str:
    f = Path(ref[len(PREFIX):].strip())
    f = f if f.is_absolute() else ROOT / f
    f = f.resolve()
    if ROOT.resolve() not in f.parents:
        raise RuntimeError(f"$FILE: 저장소 밖 파일은 쓸 수 없습니다: {f}")
    if not f.is_file():
        raise RuntimeError(f"$FILE: 파일이 없습니다: {f.relative_to(ROOT.resolve())}")
    return f.read_text("utf-8")


def inline(x):
    """dict · list · str 안의 "$FILE:경로" 값을 파일 내용으로 바꾼 사본"""
    if isinstance(x, str):
        return _read(x) if x.startswith(PREFIX) else x
    if isinstance(x, dict):
        return {k: inline(v) for k, v in x.items()}
    if isinstance(x, list):
        return [inline(v) for v in x]
    return x


def inline_safe(x):
    """검사용 — 파일이 없어도 멈추지 않는다(없는 파일은 lint 가 따로 알린다)"""
    try:
        return inline(x)
    except (OSError, RuntimeError):
        return x
