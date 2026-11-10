#!/usr/bin/env python3
"""각본 · 연출 검토 꾸러미 — 콘티를 렌더하기 전에 '각본가 · 감독 자리'에서 다시 보도록, 필요한 것만 한 장에 모은다.
2026-11-10: writer · director 스킬이 시스템 프롬프트(약 75KB) 안에 묻혀 지켜지지 않았다(장면 5~10초 · 한 문장 40~60자 · 접속어 강의체).
제작 절차와 섞지 않고 이 꾸러미만 보고 대사 · 화면 리듬을 고친 뒤 produce 로 간다.

  python3 engine/story/review.py data/storyboards/<id>.json

보여 주는 것: ① 레퍼런스 기준 위반(L50~L52 · T50 — engine/checks/refnorm.py) ② 레퍼런스의 말 리듬(구절 길이 · 쉼 — 베끼지 않고 박자만)
③ 내 대본을 구절로 쪼갠 표(장면 · 글자 수 · 초) ④ 고칠 때 볼 점 8가지(writer · director 스킬의 핵심)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "checks"))
import refnorm  # noqa: E402

CHECK = [
    "화면은 레퍼런스 샷 중앙값 안팎으로 바뀐다 — 한 장면에 문장이 둘이면 재료도 둘(cue 로 그 낱말에)",
    "한 구절은 한숨에(레퍼런스 중앙값의 2배 안). 길면 끊거나, 화면이 보여 주는 것은 말에서 뺀다",
    "접속어(그래서 · 근데 · 그러니까)로 문장을 잇지 않는다 — 화면 전환이 잇는다",
    "훅 첫 문장 = 화면 · 말 · 화면 글자 세 칸이 같은 한 방(writer 훅 세 칸)",
    "숫자 · 이름은 말과 화면 중 한 곳에만 크게 — 둘 다 읽게 하지 않는다",
    "장면마다 시선은 한 곳(director) — 재료 여러 개를 동시에 펼치지 않는다",
    "꺾임(반전) 직전엔 반 박자 멈춤 · 끝 그림은 첫 장면의 기준 물건으로 돌아온다(다섯 기둥)",
    "AI 티: '~인데요, ~거든요' 반복 · '바로' '정말' 남발 · 요약 문장으로 끝내기 금지(writer · humanizer-ko)",
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    sb = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    refs = [r for r in (sb.get("reference") or []) if isinstance(r, str)]
    t = refnorm.targets(refs)
    print(f"# 각본 · 연출 검토 — {sb.get('title')}\n")
    print(f"레퍼런스 기준({', '.join(t['refs'][:5]) or '기본값'}): 샷 중앙값 {t['shot_med']}초 · 말 덩어리 중앙값 {t['phrase_med']}자 · {t['cps']}자/초\n")
    rows = refnorm.check(sb, t)
    print("## ① 위반" + (" — 없음" if not rows else ""))
    for c, sc, m in rows:
        print(f"- {c} {('장면 ' + str(sc)) if sc else '전체'}: {m}")
    for r in refs:
        f = refnorm.XRAY / r / "xray.json"
        if f.exists():
            x = json.loads(f.read_text("utf-8"))
            words = [w for seg in x.get("speech") or [] for w in seg.get("words") or []]
            allp = refnorm.phrases_from_words(words)
            ps = allp[:12] if len(allp) >= len(words) / 7 else []     # 구절을 못 자른 인식 결과는 박자를 보여 주지 않는다
            if ps:
                print(f"\n## ② 레퍼런스 {r} 의 말 리듬(박자만 — 문장은 베끼지 않는다)")
                print(" / ".join(f"{refnorm._chars(p)}자" for p in ps))
                shots = [round(float(s['end']) - float(s['start']), 1) for s in x.get("shots") or []][:16]
                print("샷 길이(초): " + " · ".join(str(s) for s in shots))
            break
    print("\n## ③ 내 대본(구절 · 글자 수)")
    script = sb.get("script") or " / ".join(str(s.get("narration") or "") for s in sb.get("scenes") or [])
    for i, (part, sc) in enumerate(zip(script.split(" / "), sb.get("scenes") or []), 1):
        ph = refnorm.phrases_from_text(part)
        print(f"- 장면 {i} · {sc.get('sec')}초 · 화면 단위 {refnorm.visual_units(sc)}: " + " | ".join(f"{p}({refnorm._chars(p)})" for p in ph))
    print("\n## ④ 고칠 때 볼 점")
    for k, c in enumerate(CHECK, 1):
        print(f"{k}. {c}")
    print("\n고친 뒤: python3 engine/checks/lint.py <콘티> 로 L50~L52 가 없는지 → produce")
    return 1 if any(c.startswith("L") for c, *_ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
