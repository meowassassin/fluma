#!/usr/bin/env python3
"""대본 한 덩어리 → 장면 나레이션. 대본을 장면마다 따로 쓰면 문장이 장면에서 끊기고(매번 '~입니다.' 로 닫힘) 다음 장면과 이어지지 않는다 —
그래서 대본(sb.script)을 한 번에 이어서 쓰고, 장면이 바뀌는 곳에만 ' / ' 를 넣는다. 엔진이 나눠 장면 narration 에 넣는다.

  "script": "어제 배포한 코드가 / 오늘 아침 전부 롤백됐는데요, 이유가 좀 웃깁니다. / 범인은 3년 전의 나였거든요."
  → 나레이션이 있는 장면(narration 칸이 비어 있지 않거나 say != false)에 차례로. 문장이 장면을 넘어가도 된다(이어 말하기로 한 번에 합성).
나눈 조각 수가 말하는 장면 수와 다르면 멈추고 알린다. produce.py · assemble_audio.py 가 맨 앞에서 부른다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def pieces(script: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\s/\s|\n\s*/\s*\n?|\s*\|\s*", script.strip())]


def speaking(sb: dict) -> list[int]:
    """나레이션을 받을 장면: say: false(말 없는 장면)를 뺀 전부"""
    return [i for i, sc in enumerate(sb.get("scenes") or []) if sc.get("say") is not False]


def apply(sb: dict) -> tuple[bool, str]:
    s = sb.get("script")
    if not isinstance(s, str) or not s.strip():
        return False, ""
    ps, idx = pieces(s), speaking(sb)
    if len(ps) != len(idx):
        raise ValueError(f"대본 조각 {len(ps)}개 ≠ 말하는 장면 {len(idx)}개 — script 의 ' / ' 를 장면 수에 맞추거나, 말 없는 장면에 \"say\": false")
    changed = False
    for i, p in zip(idx, ps):
        if sb["scenes"][i].get("narration") != p:
            sb["scenes"][i]["narration"] = p; changed = True
    return changed, f"대본 → 장면 {len(idx)}개"


def main() -> int:
    sp = Path(sys.argv[1])
    sb = json.loads(sp.read_text("utf-8"))
    try:
        changed, msg = apply(sb)
    except ValueError as e:
        print(f"[대본] {e}", file=sys.stderr); return 1
    if changed:
        sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    if msg:
        print(f"[대본] {msg}{' (나레이션 갱신)' if changed else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
