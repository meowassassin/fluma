#!/usr/bin/env python3
"""AI 티 문형 감지 — writer 스킬 3장(AI 티 나는 문장) · 0.5장(한국어 AI 문체, humanizer-ko 요약)을 코드로.
각본가 단계(engine/story/skill_pass.py writer)에 '찾은 문제'로 넘기고, 고친 뒤에도 남으면 lint L55 로 막는다.

  python3 engine/checks/aitell.py data/storyboards/<id>.json      # 찾은 것 표(JSON)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# (규칙, 무거움 high|mid, 정규식, 고칠 방향) — 무거움 high 는 lint 실패, mid 는 각본가 단계에만 넘긴다
RULES = [
    ("대비 공개", "high", r"[가-힣]+(이|가)\s*아니(라|고)\s*[,]?\s*[가-힣 ]+(입니다|이에요|예요|이다|다)\b", "무엇인지 한 문장으로 바로 말한다"),
    ("부정 나열", "high", r"(없이[ ,]+[^.]*없이)", "실제로 일어나는 일 하나로"),
    ("스스로 묻고 답하기", "high", r"[가-힣]+(은|는)\?\s*\S", "질문 없이 그냥 말한다"),
    ("콜론 공개", "high", r"[가-힣]\s*:\s*[가-힣]", "콜론 대신 문장으로"),
    ("상투 문구", "high", r"(바쁜 현대인|새로운 차원|의 힘을 경험|차세대|원활한|혁신적인|게임 체인저)", "그 말이 가리키는 사실(숫자 · 이름 · 방법)로"),
    ("지혜 문장 마무리", "high", r"(결국 중요한 건|라고 할 수 있습니다|앞으로가 기대됩니다|결론적으로)", "마지막 줄은 행동 · 사실로"),
    ("번역투", "mid", r"(에 대해|을 통해|를 통해|에 있어서|를 가지고 있|되어진|에 의해)", "한국어 동사로 바로"),
    ("AI 유행어", "mid", r"(핵심적|효과적|다양한|지속 가능한|최적화|활용(하|해|할))", "숫자 · 이름 · 행동으로"),
    ("~적 이어 붙이기", "mid", r"(체계적|효율적|전략적|혁신적)\s*(이고|이며|인)", "동사 · 형용사로 풀기"),
]


def texts(sb: dict) -> list[tuple[str, str]]:
    """(어디, 글) — 대본 · 장면 나레이션 · 화면 글자 · 제목"""
    out = []
    if sb.get("script"):
        for i, part in enumerate(str(sb["script"]).split("/"), 1):
            out.append((f"script#{i}", part.strip()))
    else:
        for i, sc in enumerate(sb.get("scenes") or [], 1):
            if sc.get("narration"):
                out.append((f"s{i}.narration", str(sc["narration"])))
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        if sc.get("caption"):
            out.append((f"s{i}.caption", str(sc["caption"])))
    if sb.get("title"):
        out.append(("title", str(sb["title"])))
    return out


def find(sb: dict) -> list[dict]:
    found = []
    for where, t in texts(sb):
        for name, sev, rx, fix in RULES:
            m = re.search(rx, t)
            if m:
                found.append({"where": where, "rule": name, "severity": sev, "match": m.group(0), "text": t, "fix": fix})
        sents = [s for s in re.split(r"(?<=[.?!요다죠])\s+", t) if s.strip()]
        for s in sents:
            if s.count(",") >= 2:
                found.append({"where": where, "rule": "쉼표 과다", "severity": "mid", "match": s, "text": t, "fix": "연결어미 뒤 쉼표를 지운다"})
    # 같은 문장 끝이 세 번 연달아(대본 전체)
    ends = [(w, re.sub(r"[^가-힣]", "", t)[-2:]) for w, t in texts(sb) if w.startswith(("script", "s")) and ".caption" not in w and t]
    for k in range(2, len(ends)):
        if ends[k][1] and ends[k][1] == ends[k - 1][1] == ends[k - 2][1]:
            found.append({"where": ends[k][0], "rule": "같은 문장 끝 3연속", "severity": "mid", "match": ends[k][1], "text": "", "fix": "문장 끝을 섞는다(~요 · ~거든요 · 명사 끊기 · 반말 한 줄)"})
    return found


def main() -> int:
    sb = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    print(json.dumps(find(sb), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
