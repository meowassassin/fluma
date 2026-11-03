#!/usr/bin/env python3
"""
증류층: 검사 실패 기록에서 규칙 후보를 뽑아 제안한다. rulebook.md 는 직접 고치지 않는다 (사람 승인).

입력: storyboards/*.json 의 meta.lint_failures (형식 "r1 L03 s=2 자막 ...") 와 storyboards/_failed/*.json
집계: 최근 30편에서 (검사 코드, 장면 역할) 쌍의 횟수. 3회 이상이면 제안.
출력: rules/trends/proposals.md 에 "## 증류 제안 <날짜>" 절 추가, rules/trends/distill-<날짜>.json 에 집계.

사용: python scripts/distill.py [--min 3] [--last 30]
"""
import argparse
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROPOSALS = ROOT / "rules" / "trends" / "proposals.md"

SUGGEST = {
    "L03": "해당 역할의 caption_max 를 줄이거나(예: 24자) 생성 프롬프트에 '한 줄 12자 이내 × 2줄' 명시",
    "L04": "해당 역할의 narration 칸 범위를 sec×4~6자로 좁히고, 생성 프롬프트에 '공백 제외 N자 이내' 숫자를 직접 적기",
    "L08": "outro/cta 프롬프트에 'hook 의 핵심어 <단어>를 그대로 포함' 지시 추가 (결정층이 hook 키워드를 cta 칸에 전달)",
    "L11": "해당 역할의 visual.kind 기본값을 still/screenshot 으로 바꾸거나, 생성 프롬프트에 '숫자 또는 고유명사 필수' 강조",
    "L12": "이 형식은 조사·증거층이 에셋을 먼저 확보한 뒤 생성하도록 순서 변경 (에셋 없으면 주제 보류)",
    "L06": "금칙어 목록을 생성 프롬프트 맨 위로 올리고, 대체 표현 예시 추가",
    "L02": "결정층 allocate() 반올림 확인 — 생성층이 sec 를 바꾸지 못하게 assemble 에서 고정",
}


def parse_failures(sb: dict):
    """meta.lint_failures 의 문자열 또는 (code, idx, msg) 를 (code, role) 로."""
    out = []
    roles = [s.get("role") for s in sb.get("scenes", [])]
    fmt = sb.get("format", "?")
    for item in (sb.get("meta", {}) or {}).get("lint_failures", []):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            code, idx = item[0], item[1]
        else:
            m = re.search(r"\b(L\d\d|T\d\d)\b.*?s=(\d+|None)", str(item))
            if not m:
                continue
            code, idx = m.group(1), (None if m.group(2) == "None" else int(m.group(2)))
        role = roles[idx] if isinstance(idx, int) and idx < len(roles) else "전체"
        out.append((code, role, fmt))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=3)
    ap.add_argument("--last", type=int, default=30)
    args = ap.parse_args()

    files = sorted((ROOT / "storyboards").glob("*.json"), key=lambda p: p.stat().st_mtime)[-args.last:]
    files += sorted((ROOT / "storyboards" / "_failed").glob("*.json")) if (ROOT / "storyboards" / "_failed").exists() else []
    pair = Counter(); by_fmt = Counter(); n = 0
    for f in files:
        try:
            sb = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        n += 1
        for code, role, fmt in parse_failures(sb):
            pair[(code, role)] += 1
            by_fmt[(code, fmt)] += 1

    today = dt.date.today().isoformat()
    report = {"date": today, "storyboards_scanned": n,
              "by_code_role": [{"code": c, "role": r, "count": k} for (c, r), k in pair.most_common()],
              "by_code_format": [{"code": c, "format": f, "count": k} for (c, f), k in by_fmt.most_common()]}
    (ROOT / "rules" / "trends").mkdir(parents=True, exist_ok=True)
    (ROOT / "rules" / "trends" / f"distill-{today}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    hits = [((c, r), k) for (c, r), k in pair.most_common() if k >= args.min]
    with PROPOSALS.open("a", encoding="utf-8") as f:
        f.write(f"\n## 증류 제안 {today} (콘티 {n}편, 기준 {args.min}회)\n")
        if not hits:
            f.write("- 반복 실패 없음\n")
        for (code, role), k in hits:
            f.write(f"- [ ] {code}가 {role}에서 {k}회 — 규칙 후보: {SUGGEST.get(code, '해당 규칙의 칸 제약을 결정층에서 더 좁히기')}\n")
    print(f"콘티 {n}편 스캔, 실패 쌍 {len(pair)}종, 제안 {len(hits)}건 → {PROPOSALS}")
    for (code, role), k in pair.most_common(10):
        print(f"  {code} @ {role}: {k}")


if __name__ == "__main__":
    main()
