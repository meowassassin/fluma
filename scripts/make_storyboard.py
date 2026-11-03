#!/usr/bin/env python3
"""
콘티 생성기: 주제 → 결정층 → 생성층(claude -p) → 검사층 → (승급) → storyboards/<id>.json

호출 상한: 영상당 LLM 호출 최대 MAX_CALLS, 칸당 재시도 최대 2회, 승급 1회.
넘으면 포기하고 종료 코드 2 (대기열의 다음 주제로).

사용:
  python scripts/make_storyboard.py --topic "무료 TTS 사이트 3개 비교" [--audience "마케터"] [--duration 30]
  python scripts/make_storyboard.py --topic "..." --dry-run      # LLM 없이 결정층만
  LLM_CMD 환경변수로 호출 명령 교체 가능 (기본: claude -p). 나중에 API로 바꿀 때 여기 한 줄.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decide import decide, Decision          # noqa: E402
from lint import lint, recent_titles         # noqa: E402
from research import research               # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "tokens" / "default.json").read_text(encoding="utf-8"))
RULEBOOK = (ROOT / "rules" / "rulebook.md").read_text(encoding="utf-8")
EXPLAIN = (ROOT / "rules" / "explain_patterns.md")
EXPLAIN_TXT = EXPLAIN.read_text(encoding="utf-8") if EXPLAIN.exists() else ""

MAX_CALLS = 8
MAX_RETRY_PER_SCENE = 2
LLM_CMD = os.environ.get("LLM_CMD", "claude -p --output-format text --model sonnet")
ESCALATE_CMD = os.environ.get("ESCALATE_CMD", "claude -p --output-format text --model opus")

calls = 0


# ---------- 생성층: LLM 호출은 이 함수 하나로만 ----------
def llm(prompt: str, escalate=False) -> str:
    """모델 호출 어댑터. 나중에 API로 바꿀 때 이 함수만 수정."""
    global calls
    calls += 1
    if calls > MAX_CALLS:
        raise RuntimeError(f"호출 상한 {MAX_CALLS} 초과")
    cmd = ESCALATE_CMD if escalate else LLM_CMD
    res = subprocess.run(cmd, shell=True, input=prompt, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[:500])
    return res.stdout


def extract_json(text: str):
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("JSON 없음")
    return json.loads(m.group(0))


def section(md: str, header: str) -> str:
    m = re.search(rf"^## {re.escape(header)}.*?(?=^## |\Z)", md, flags=re.S | re.M)
    return m.group(0) if m else ""


def facts_block(facts: dict) -> str:
    lines = [f"- [{i}] {f['entity']}: {f['claim']} (값: {f['value']}) — {f['source']}" for i, f in enumerate(facts.get("facts", []))]
    angles = "\n".join(f"- {a}" for a in facts.get("angle_candidates", []))
    caveats = "\n".join(f"- {c}" for c in facts.get("caveats", []))
    return f"""## 조사된 사실 (이 목록 밖의 수치·이름·주장은 쓰지 않는다)
{chr(10).join(lines)}

## 의외의 각도 후보 (훅에 쓸 것)
{angles}

## 주의
{caveats}"""


def fill_prompt(d: Decision, facts: dict, audience: str = "", brand: str | None = None) -> str:
    rules3 = section(RULEBOOK, "3. 생성층 규칙")
    slots = "\n".join(
        f"- scene[{i}] role={s['role']}, sec={s['sec']}, visual.kind={s['visual_kind']}, "
        f"caption ≤ {s['caption_max']}자(줄바꿈 1회 허용), narration 공백 제외 {s['narration_range'][0]}~{s['narration_range'][1]}자"
        for i, s in enumerate(d.scenes)
    )
    concept_hint = EXPLAIN_TXT if d.format in ("concept", "series") and EXPLAIN_TXT else ""
    return f"""당신은 한국어 정보형 쇼츠 대본 작가다. 아래 **정해진 칸**만 채운다. 구조·길이·장면 수는 바꾸지 않는다.

대상 시청자: {audience or "일반 시청자"}{f"  /  브랜드: {brand}" if brand else ""}
주제: {d.topic}
형식: {d.format}  /  훅 유형: {d.hook_style} (question=질문, number=숫자 제시, contrarian=통념 반박, pain=불편 공감)
총 길이: {d.duration_sec}초

{rules3}

{facts_block(facts)}

{concept_hint}

## 구체성 규칙 (빈약한 장면 금지)
- hook·outro 를 뺀 모든 장면에는 **고유명사(제품·도구·기능 이름) 또는 숫자**가 자막이나 visual 에 최소 하나 들어간다.
- "좋다/자연스럽다/편하다" 같은 평가어는 반드시 값과 같이 쓴다 (예: "한국어 4/5", "월 1만 자").
- compare 의 item 은 같은 기준 2개를 값으로 보여준다 (예: items: ["월 1만 자 무료", "상업 이용 ○ 출처표기"]).
- verdict 는 "누구에게 무엇"으로 행동 가능하게 (예: "정보 영상 → 타입캐스트 / 대량 → ElevenLabs").
- 사용한 사실의 번호를 sources 에 URL 로 넣는다.

## 채울 칸 (순서대로, 개수 정확히 {len(d.scenes)}개)
{slots}

## visual 작성법
- kind=number: primary에 숫자+단위 (예 "37%"), secondary에 짧은 설명
- kind=compare: primary에 항목명, items에 "특징 ○/△" 2개
- kind=list: items에 2~3개
- kind=diff: before/after 한 줄씩
- kind=text: primary에 자막과 다른 짧은 한 줄
- 출처가 필요한 수치는 sources에 URL 또는 "내부 실험"으로 명시. 모르는 수치는 만들지 말고 수치 없는 문장으로.

## 출력 (JSON만, 설명 없이)
{{
  "title": "유튜브 제목 40자 이내",
  "hook_number": "핵심 숫자 또는 null",
  "scenes": [ {{"role": "...", "sec": 0, "caption": "...", "narration": "...", "visual": {{"kind": "...", ...}}, "sfx": "stamp|pop|tick|swoosh|none"}} ],
  "cta": "20자 이내",
  "caption": "게시글 본문 300자 이내",
  "hashtags": ["#..."],
  "sources": []
}}"""


def fix_prompt(sb: dict, fails: list) -> str:
    """실패한 칸만 다시. 나머지는 그대로 돌려받는다."""
    by_scene = {}
    for code, idx, msg in fails:
        by_scene.setdefault(idx, []).append(f"{code}: {msg}")
    lines = []
    for idx, msgs in by_scene.items():
        where = f"scene[{idx}]" if idx is not None else "전체"
        lines.append(f"- {where}: " + " / ".join(msgs))
    return f"""아래 콘티에서 **지적된 칸만** 고친다. 다른 장면의 글자는 한 글자도 바꾸지 않는다. 장면 수·sec·role 유지.

## 지적
{chr(10).join(lines)}

## 규칙 요약
- caption ≤ {TOKENS['limits']['caption_max_chars']}자, 줄바꿈 1회
- narration은 공백 제외 sec × {TOKENS['limits']['narration_chars_per_sec'][0]}~{TOKENS['limits']['narration_chars_per_sec'][1]}자
- outro는 hook의 핵심어를 하나 포함해 처음으로 이어지게
- hook·outro 외 모든 장면에 고유명사 또는 숫자 하나 이상 (L11)
- 금칙어 금지: 충격, 경악, 미쳤다, 역대급, 꼭 보세요

## 콘티
{json.dumps(sb, ensure_ascii=False, indent=2)}

## 출력: 수정된 콘티 전체 JSON만"""


def assemble(d: Decision, gen: dict, audience: str = "") -> dict:
    today = dt.date.today().isoformat()
    n = len(list((ROOT / "storyboards").glob(f"{today}-video-*.json"))) + 1
    scenes = []
    for i, slot in enumerate(d.scenes):
        g = gen["scenes"][i] if i < len(gen.get("scenes", [])) else {}
        vis = g.get("visual", {}) or {}
        vis.setdefault("kind", slot["visual_kind"])
        scenes.append({
            "role": slot["role"],
            "sec": slot["sec"],                      # 길이는 결정층 값 고정
            "caption": g.get("caption", ""),
            "narration": g.get("narration", ""),
            "visual": vis,
            "sfx": g.get("sfx", "none"),
        })
    return {
        "id": f"{today}-video-{n:02d}",
        "version": 1,
        "audience": audience or None,
        "brand": None,
        "badge": None,
        "constraints": [],
        "format": d.format,
        "duration_sec": d.duration_sec,
        "title": gen.get("title", d.topic)[:40],
        "topic": d.topic,
        "hook_number": gen.get("hook_number"),
        "scenes": scenes,
        "cta": gen.get("cta", "")[:20],
        "caption": gen.get("caption", "")[:300],
        "hashtags": gen.get("hashtags", [])[:10],
        "sources": gen.get("sources", []),
        "series": None,
        "meta": {"created_at": dt.datetime.now().isoformat(timespec="seconds"), "model": LLM_CMD,
                 "llm_calls": 0, "escalated": False, "lint_failures": []},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--audience", default="", help="대상 시청자 (자유 문장, 예: 개발자, 자영업자)")
    ap.add_argument("--duration", type=int, default=None, help="목표 길이(초, 15~60). 없으면 형식으로 정함")
    ap.add_argument("--brief-format", default="", help="시안 형식 지정 (광고|감성|시세|ad|emotional|daily)")
    ap.add_argument("--brand", default=None, help="화면 하단에 표시할 브랜드명 (선택)")
    ap.add_argument("--dry-run", action="store_true", help="결정층 결과만 출력")
    args = ap.parse_args()

    brief_format = args.brief_format or os.environ.get("BRIEF_FORMAT", "")  # 웹 API 는 env 로 넘긴다
    d = decide(args.topic, brief_format, args.duration)
    print(f"[결정] format={d.format} ({d.rule_hit}) duration={d.duration_sec}s scenes={[s['role'] for s in d.scenes]}")
    if args.dry_run:
        print(d.to_json())
        return

    # 조사 (캐시됨: research/<slug>.json 이 있으면 재사용)
    facts = research(args.topic, args.audience)
    print(f"[조사] 사실 {len(facts['facts'])}개, 대상 {facts.get('entities')}")

    # 생성
    gen = extract_json(llm(fill_prompt(d, facts, args.audience, args.brand)))
    sb = assemble(d, gen, args.audience)
    if args.brand:
        sb["brand"] = args.brand
    if d.format == "ad":
        sb.setdefault("badge", "창업 15초" if "창업" in args.topic else "15초")
    if d.format == "daily":
        sb.setdefault("badge", "오늘 시세")
    history = []
    titles = recent_titles()

    # 검사 → 실패 칸만 수정 (칸당 2회) → 승급 1회
    tries = {}
    escalated = False
    for round_ in range(1, 6):
        fails = lint(sb, titles)
        if not fails:
            break
        history += [f"r{round_} {c} s={i} {m}" for c, i, m in fails]
        print(f"[검사 {round_}] 실패 {len(fails)}건: " + "; ".join(f"{c}@{i}" for c, i, _ in fails))
        key = tuple(sorted((c, i) for c, i, _ in fails))
        tries[key] = tries.get(key, 0) + 1
        if tries[key] > MAX_RETRY_PER_SCENE and not escalated:
            print("[승급] 같은 실패 반복 → 상위 모델 1회")
            escalated = True
            fixed = extract_json(llm(fix_prompt(sb, fails), escalate=True))
        elif tries[key] > MAX_RETRY_PER_SCENE and escalated:
            print("[포기] 승급 후에도 실패. 다음 주제로.")
            sb["meta"]["lint_failures"] = history
            (ROOT / "storyboards" / "_failed").mkdir(exist_ok=True)
            (ROOT / "storyboards" / "_failed" / f"{sb['id']}.json").write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
            sys.exit(2)
        else:
            fixed = extract_json(llm(fix_prompt(sb, fails)))
        # sec·role은 결정층 값 유지
        for i, s in enumerate(fixed.get("scenes", [])):
            if i < len(sb["scenes"]):
                s["sec"] = sb["scenes"][i]["sec"]
                s["role"] = sb["scenes"][i]["role"]
        sb.update({k: fixed[k] for k in ("title", "scenes", "cta", "caption", "hashtags", "sources", "hook_number") if k in fixed})

    sb["meta"]["llm_calls"] = calls
    sb["meta"]["escalated"] = escalated
    sb["meta"]["lint_failures"] = history
    out = ROOT / "storyboards" / f"{sb['id']}.json"
    out.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[저장] {out}  호출 {calls}회, 승급 {escalated}")


if __name__ == "__main__":
    main()
