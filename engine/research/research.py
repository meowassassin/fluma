#!/usr/bin/env python3
"""
조사층: 주제 → 검증 가능한 사실 목록 (facts JSON). 생성층은 이 목록 안에서만 쓴다.

왜 필요한가: 정보형 쇼츠의 가치는 구체성(이름·숫자·조건·출처)이다.
조사 없이 생성하면 모델은 안전하게 뭉뚱그린 문장만 쓴다. 조사층이 재료를 공급해야 생성층이 빈약하지 않다.

구현: claude -p 가 웹 검색을 써서 사실을 모은다 (Claude Code 는 headless 에서도 WebSearch 도구를 쓸 수 있다).
      나중에 API 로 바꿀 때는 검색 API + 모델 호출로 교체. LLM 호출은 이 파일의 llm() 하나로만.

출력: data/research/<slug>.json
{
  "topic": "...",
  "facts": [
    {"claim": "ElevenLabs 무료 플랜은 월 1만 자", "value": "10,000자/월", "entity": "ElevenLabs",
     "source": "https://...", "checked": "2026-10-26", "confidence": "high|medium"}
  ],
  "entities": ["Typecast", "ElevenLabs", "edge-tts"],
  "angle_candidates": ["...이 주제에서 가장 의외인 사실 1~3개..."],
  "caveats": ["...바뀌기 쉬운 수치, 지역 제한 등..."]
}
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
OUT = ROOT / "data" / "research"
LLM_CMD = os.environ.get("RESEARCH_CMD", "claude -p --output-format text --model sonnet --allowedTools WebSearch,WebFetch")

PROMPT = """당신은 정보형 쇼츠를 위한 리서처다. 아래 주제에 대해 **웹을 검색해서** 영상에 쓸 수 있는 사실을 모은다.

주제: {topic}
대상 시청자: {audience}
오늘: {today}

## 반드시 지킬 것
- 사실마다 **출처 URL**을 붙인다. 출처를 못 찾은 사실은 넣지 않는다.
- 숫자·가격·한도·날짜처럼 **구체적인 값**을 우선한다. 형용사("좋다", "자연스럽다")만 있는 문장은 사실이 아니다.
- 비교 주제면 각 항목(제품·도구·방법)마다 같은 기준의 값을 최소 2개씩 모은다 (예: 무료 한도, 상업 이용 가능 여부, 한국어 지원).
- 바뀌기 쉬운 값(가격·한도)은 확인한 날짜를 적고 caveats 에 "변동 가능"을 남긴다.
- 특정 회사 비방, 미확인 루머, 개인정보는 넣지 않는다.
- 최소 8개, 최대 20개의 사실.

## 출력 (JSON만)
{{
  "topic": "{topic}",
  "facts": [
    {{"claim": "한 문장", "value": "핵심 값", "entity": "대상 이름", "source": "URL", "checked": "{today}", "confidence": "high|medium"}}
  ],
  "entities": ["..."],
  "angle_candidates": ["이 주제에서 시청자가 의외라고 느낄 사실 1~3개, 한 줄씩"],
  "caveats": ["..."]
}}"""


def slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "-", s).strip("-")[:60]


def llm(prompt: str) -> str:
    res = subprocess.run(LLM_CMD, shell=True, input=prompt, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[:800])
    return res.stdout


def research(topic: str, audience: str = "", force=False) -> dict:
    import datetime as dt
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{slug(topic)}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    raw = llm(PROMPT.format(topic=topic, audience=audience or "일반 시청자", today=today))
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        raise ValueError("조사 결과에 JSON 없음")
    data = json.loads(m.group(0))
    # 출처 없는 사실은 버린다 (규칙)
    data["facts"] = [f for f in data.get("facts", []) if str(f.get("source", "")).startswith("http")]
    if len(data["facts"]) < 5:
        raise ValueError(f"출처 있는 사실이 {len(data['facts'])}개뿐 — 주제를 좁히거나 바꿔야 함")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "무료 TTS 사이트 3개 비교"
    c = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else ""   # 대상 시청자
    d = research(t, c, force="--force" in sys.argv)
    print(f"사실 {len(d['facts'])}개, 대상 {d.get('entities')}")
    for f in d["facts"][:5]:
        print(" -", f["claim"], "|", f["value"], "|", f["source"])
