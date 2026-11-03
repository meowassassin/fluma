#!/usr/bin/env python3
"""
결정층: 주제 문장 → 타입 값 (형식, 길이, 장면 구성, 칸 제약). LLM을 쓰지 않는다.

규칙은 rules/rulebook.md 1·2절과 같다. 아무 규칙도 안 맞으면 trend_overrides.format_weights 로 가중 선택.
"""
import json
import random
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "tokens" / "default.json").read_text(encoding="utf-8"))
OVR = json.loads((ROOT / "tokens" / "trend_overrides.json").read_text(encoding="utf-8"))


def weights(d: dict) -> dict:
    """$comment 같은 메타 키를 뺀 가중치만."""
    return {k: float(v) for k, v in d.items() if not k.startswith("$")}

HOOK_SEC = 3
OUTRO_SEC = 3

# 형식별 장면 골격. N은 항목 수(주제에서 추출, 기본 3)
SKELETON = {
    "compare":   lambda n: ["hook"] + ["item"] * n + ["verdict", "outro"],
    "countdown": lambda n: ["hook"] + ["item"] * n + ["verdict", "outro"],
    "mythbust":  lambda n: ["hook", "contrast", "reveal", "verdict", "outro"],
    "fix":       lambda n: ["hook", "setup"] + ["step"] * min(max(n, 2), 3) + ["verdict", "outro"],
    "concept":   lambda n: ["hook", "setup", "reveal", "reveal", "verdict", "outro"],
    "series":    lambda n: ["hook", "setup", "reveal", "reveal", "verdict", "outro"],
    # 분석(2026-10-26)에서 추가된 세 형식 — 현장 영상 + 자막 한 줄 + 숫자 하나
    "ad":        lambda n: ["hook"] + ["benefit"] * min(max(n, 2), 4) + ["proof", "cta"],
    "emotional": lambda n: ["hook"] + ["mood"] * min(max(n, 3), 5) + ["cta"],
    "daily":     lambda n: ["hook"] + ["price"] * min(max(n, 1), 3) + ["mood", "cta"],
}

# 장면 역할 → 화면 종류 기본값
# 분석 결과: 툴·현장 주제는 still/footage 가 1순위. 패널(compare/list)은 데이터·원리 주제에만.
VISUAL_FOR = {
    "hook": "number", "setup": "text", "item": "compare", "contrast": "diff",
    "step": "list", "reveal": "text", "verdict": "list", "outro": "text",
    "benefit": "footage", "proof": "footage", "mood": "still", "price": "price_tag", "cta": "text",
}

# 시안(브리프)에서 오는 형식 지정. 주제 문장 규칙보다 우선.
BRIEF_FORMATS = {"광고": "ad", "ad": "ad", "감성": "emotional", "emotional": "emotional",
                 "시세": "daily", "당일": "daily", "daily": "daily"}

RULES = [
    # (정규식, 형식)  — rulebook 1절 순서
    (r"\bvs\b|비교|차이|대결|뭐가 (더|제일)", "compare"),
    (r"TOP\s*\d|순위|(\d+)\s*(가지|개|곳|선)", "countdown"),
    (r"사실은|오해|착각|진짜|아닌|거짓|틀린", "mythbust"),
    (r"방법|하는 ?법|해결|줄이는|고치는|막는|없애는|피하는", "fix"),
    (r"원리|어떻게 동작|구조|왜 |이유|작동", "concept"),
]


@dataclass
class Decision:
    topic: str
    format: str
    duration_sec: int
    n_items: int
    scenes: list = field(default_factory=list)   # [{"role","sec","visual_kind","caption_max","narration_range"}]
    hook_style: str = "question"
    rule_hit: str = ""
    weights_used: bool = False

    def to_json(self):
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def pick_format(topic: str, brief_format: str = ""):
    if brief_format:
        f = BRIEF_FORMATS.get(brief_format.strip().lower(), brief_format.strip().lower())
        if f in SKELETON:
            return f, "brief", False
    for pat, fmt in RULES:
        if re.search(pat, topic, flags=re.I):
            return fmt, pat, False
    w = weights(OVR["format_weights"])
    fmt = random.choices(list(w.keys()), weights=list(w.values()), k=1)[0]
    return fmt, "weights", True


def count_items(topic: str, fmt: str) -> int:
    m = re.search(r"(\d+)\s*(가지|개|곳|선|종)", topic)
    if m:
        return min(max(int(m.group(1)), 2), 5)
    if fmt in ("compare",):
        # "A vs B" 류는 2, 그 외 3
        return 2 if re.search(r"\bvs\b", topic, re.I) else 3
    return 3


def pick_duration(fmt: str, n: int, target: int | None = None) -> int:
    """길이는 형식으로 정한다 (채널 개념 없음, 2026-10-28). 사용자가 target 을 주면 그 값(15~60)."""
    if target:
        return max(15, min(60, int(target)))
    base = 30
    if fmt == "series":
        base = 30
    if fmt in ("ad", "daily"):
        base = 15          # 분석: 광고·시세는 15~20초가 승자 (실제 광고 사례 15~16초)
    if fmt == "emotional":
        base = 20
    # 항목이 많으면 조금 늘림 (최대 60)
    return min(base + max(0, n - 3) * 4, 60)


def allocate(roles: list, duration: int):
    """hook/outro 고정, 나머지를 균등 배분. 합계 == duration 보장."""
    body = [r for r in roles if r not in ("hook", "outro", "cta")]
    remain = duration - HOOK_SEC - OUTRO_SEC
    per = remain // len(body)
    extra = remain - per * len(body)
    secs = []
    for r in roles:
        if r == "hook":
            secs.append(HOOK_SEC)
        elif r in ("outro", "cta"):
            secs.append(OUTRO_SEC)
        else:
            s = per + (1 if extra > 0 else 0)
            extra -= 1 if extra > 0 else 0
            secs.append(s)
    return secs


def decide(topic: str, brief_format: str = "", target: int | None = None) -> Decision:
    fmt, hit, used_w = pick_format(topic, brief_format)
    n = count_items(topic, fmt)
    dur = pick_duration(fmt, n, target)
    roles = SKELETON[fmt](n)
    secs = allocate(roles, dur)
    lim = TOKENS["limits"]
    cps_lo, cps_hi = lim["narration_chars_per_sec"]
    # 형식별 훅 화면: 현장형(ad/emotional)은 사진·영상, 시세는 가격표. 숫자 도장은 데이터·원리 주제용.
    hook_kind = {"ad": "still", "emotional": "still", "daily": "price_tag"}.get(fmt, "number")
    scenes = []
    for role, sec in zip(roles, secs):
        scenes.append({
            "role": role,
            "sec": sec,
            "visual_kind": hook_kind if role == "hook" else VISUAL_FOR[role],
            "caption_max": lim["caption_max_chars"],
            "narration_range": [int(sec * cps_lo), int(sec * cps_hi)],
        })
    hw = weights(OVR["hook_style_weights"])
    hook_style = random.choices(list(hw.keys()), weights=list(hw.values()), k=1)[0]
    return Decision(topic, fmt, dur, n, scenes, hook_style, hit, used_w)


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "무료 TTS 사이트 3개 비교"
    bf = sys.argv[2] if len(sys.argv) > 2 else ""          # 형식 지정: 광고|감성|시세|compare …
    tg = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None   # 목표 길이(초)
    print(decide(t, bf, tg).to_json())
