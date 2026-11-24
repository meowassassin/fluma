#!/usr/bin/env python3
"""콘티 저장 — 각 단계는 '내가 바꾼 칸만' 최신 파일 위에 얹는다(3방향 병합).

2026-11-18 감사: 단계마다 콘티를 처음에 읽고 LLM · 합성(수십 초~분)을 기다린 뒤 통째로 써서,
그 사이 에이전트 · 다른 단계가 고친 칸이 사라졌다(skill_pass.run_pass · assemble_audio · voice_match · direct 등).

  base = sbio.load(path)          # 시작할 때 읽은 것
  sb = copy.deepcopy(base); ...   # 고친다
  sbio.save(path, base, sb)       # base → sb 로 바뀐 칸만 지금 파일에 반영(원자적 쓰기 · 파일 잠금)
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

_MISSING = object()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def merge(base, mine, theirs):
    """base → mine 으로 바뀐 것만 theirs 에 얹는다. 같은 칸을 양쪽이 바꿨으면 mine(지금 쓰는 단계)이 이긴다."""
    if mine == base:
        return theirs
    if isinstance(mine, dict) and isinstance(base, dict) and isinstance(theirs, dict):
        out = dict(theirs)
        for k in set(base) | set(mine):
            b, m = base.get(k, _MISSING), mine.get(k, _MISSING)
            if b == m:
                continue
            if m is _MISSING:
                out.pop(k, None)
            elif b is _MISSING or k not in theirs:
                out[k] = m
            else:
                out[k] = merge(b, m, theirs[k])
        return out
    if isinstance(mine, list) and isinstance(base, list) and isinstance(theirs, list) and len(mine) == len(base) == len(theirs) \
            and all(isinstance(x, dict) for x in mine + base + theirs) and _same_ids(base, theirs):
        return [merge(b, m, t) for b, m, t in zip(base, mine, theirs)]
    return mine


def _same_ids(a: list, b: list) -> bool:
    """장면 · 재료 목록이 같은 순서인가(id 가 있으면 id 로) — 순서가 바뀐 목록은 칸 단위로 섞지 않는다"""
    ia, ib = [x.get("id") for x in a], [x.get("id") for x in b]
    return ia == ib


def save(path: Path, base: dict, mine: dict, indent: int = 2) -> dict:
    """base → mine 의 변경만 지금 파일에 얹어 쓴다. 쓴 결과를 돌려준다."""
    path = Path(path)
    from platform_util import file_lock
    with file_lock(str(path) + ".lock"):
        try:
            theirs = load(path)
        except (OSError, ValueError):
            theirs = copy.deepcopy(base)
        out = merge(base, mine, theirs)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=indent) + "\n", "utf-8")
        os.replace(tmp, path)
    return out
