#!/usr/bin/env python3
"""끊어 넣을 순간 찾기 — 퍼온 클립의 원래 말(clip.py --subs 의 단어 시각)에서 '편집 장치'를 넣기 좋은 자리를 고른다.
실제 에셋 밈 쇼츠(예: 욕 · 말이 막히는 순간마다 평화로운 자연 컷으로 끊어 넣기)의 재료. 고르는 건 에이전트 · 사용자 — 여기는 후보만.

후보 종류
  pause    말 사이 0.8초 이상 빔(박수 · 웃음 · 머뭇거림) — 자연 컷 · 검은 화면 글자 · 반응 자막 자리
  repeat   같은 구가 다시 나옴 — 반복 강조 · 점점 커지는 자막
  question 물음 — 질문을 화면 글자로 크게, 답 전에 끊기
  bleep    욕 · 막말(목록) — 기호로 가리고(ㅆ@) 삐 소리 · 자연 컷
  stammer  같은 낱말 연속 · 말 끊김(wait · hold on · uh) — 자막으로 놀리기

  python3 engine/capture/cutaway.py <meta.json 경로 | 콘티 id/재료 이름> [--pause 0.8]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
BLEEP = re.compile(r"(?i)\b(fuck\w*|shit\w*|damn\w*|bitch\w*|ass(hole)?|hell|crap|bastard|dick|piss\w*)\b|씨[발빨]|시[발바]|개새|병신|좆|존나|ㅅㅂ")
STAMMER = re.compile(r"(?i)\b(uh+|um+|er+|wait|hold on|hang on|no no|what the)\b")


def load(arg: str) -> dict:
    p = Path(arg)
    if not p.exists():
        p = ROOT / "data" / "public" / "elements" / arg / "meta.json"
    return json.loads(p.read_text("utf-8"))


def find(meta: dict, pause: float = 0.8) -> list[dict]:
    subs = meta.get("subs") or []
    words = [w for s in subs for w in s.get("words") or []]
    out = []
    for a, b in zip(words, words[1:]):
        gap = round(float(b["s"]) - float(a["e"]), 2)
        if gap >= pause:
            out.append({"kind": "pause", "s": a["e"], "e": b["s"], "sec": gap, "after": a["w"], "before": b["w"]})
    for i, w in enumerate(words):
        if BLEEP.search(w["w"]):
            out.append({"kind": "bleep", "s": w["s"], "e": w["e"], "word": w["w"]})
        if STAMMER.search(w["w"]) or (i and re.sub(r"\W", "", w["w"].lower()) == re.sub(r"\W", "", words[i - 1]["w"].lower()) != ""):
            out.append({"kind": "stammer", "s": w["s"], "e": w["e"], "word": w["w"]})
    seen: dict[str, float] = {}
    for s in subs:
        key = re.sub(r"\W+", " ", s["text"].lower()).strip()
        if s["text"].strip().endswith("?"):
            out.append({"kind": "question", "s": s["s"], "e": s["e"], "text": s["text"]})
        if len(key) > 8 and key in seen:
            out.append({"kind": "repeat", "s": s["s"], "e": s["e"], "text": s["text"], "first_at": seen[key]})
        seen.setdefault(key, s["s"])
    return sorted(out, key=lambda x: (x["s"], x["kind"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meta"); ap.add_argument("--pause", type=float, default=0.8)
    a = ap.parse_args()
    print(json.dumps(find(load(a.meta), a.pause), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
