#!/usr/bin/env python3
"""
트렌드 층 4단계: engine/spec/rules/trends/<week>.json 을 읽어
  - engine/spec/tokens/trend_overrides.json 의 가중치와 range 내 값을 조정한다 (한 주 ±0.1 까지만)
  - 큰 변경 제안은 engine/spec/rules/trends/proposals.md 에 붙인다 (사람 승인 대기)

기본 틀(engine/spec/tokens/default.json, rulebook.md 0절)은 절대 건드리지 않는다.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
OVR = ROOT / "engine" / "spec" / "tokens" / "trend_overrides.json"
PROPOSALS = ROOT / "engine" / "spec" / "rules" / "trends" / "proposals.md"
MAX_STEP = 0.10          # 가중치 한 주 최대 이동
MIN_SAMPLE = 30


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def move_weights(current: dict, target: dict) -> dict:
    """현재 가중치를 target 쪽으로 최대 MAX_STEP 만큼만 이동하고 합계 1로 정규화."""
    out = {}
    for k, cur in current.items():
        if k.startswith("$"):
            continue
        cur = float(cur)
        tgt = float(target.get(k, cur))
        delta = clamp(tgt - cur, -MAX_STEP, MAX_STEP)
        out[k] = max(0.0, cur + delta)
    s = sum(out.values()) or 1.0
    normalized = {k: round(v / s, 3) for k, v in out.items()}
    # $comment 같은 메타 키는 그대로 보존
    return {**{k: v for k, v in current.items() if k.startswith("$")}, **normalized}


def main():
    if len(sys.argv) < 2:
        files = sorted((ROOT / "engine" / "spec" / "rules" / "trends").glob("*-W*.json"))
        if not files:
            sys.exit("engine/spec/rules/trends/<week>.json 이 없습니다. 분석 프롬프트를 먼저 실행하세요.")
        trend_path = files[-1]
    else:
        trend_path = Path(sys.argv[1])

    trend = json.loads(trend_path.read_text(encoding="utf-8"))
    if trend.get("insufficient") or trend.get("sample_size", 0) < MIN_SAMPLE:
        sys.exit(f"표본 부족 ({trend.get('sample_size')}) — 갱신하지 않음.")

    ovr = json.loads(OVR.read_text(encoding="utf-8"))
    before = json.dumps(ovr["format_weights"]), json.dumps(ovr["hook_style_weights"])

    # 1) 가중치 이동 (급변 방지)
    if "formats" in trend:
        ovr["format_weights"] = move_weights(ovr["format_weights"], trend["formats"])
    if "hook_styles" in trend:
        ovr["hook_style_weights"] = move_weights(ovr["hook_style_weights"], trend["hook_styles"])

    # 2) range 내 값 조정 — 관찰값을 토큰으로 번역하는 보수적 규칙
    look = trend.get("look", {})
    o = ovr["overrides"]
    cuts = look.get("cuts_per_10s_median")
    if cuts:
        # 컷이 빠를수록 reveal 짧게. 10초당 3컷=300ms, 6컷=180ms 선형
        target = clamp(300 - (cuts - 3) * 40, *o["motion.reveal_ms"]["range"])
        o["motion.reveal_ms"]["value"] = int(target)
    cps = trend.get("chars_per_sec_median")
    if cps:
        # 말 속도: 초당 4.5자를 1.0으로 보고 ±
        target = clamp(1.0 + (cps - 4.5) * 0.08, *o["audio.speed"]["range"])
        o["audio.speed"]["value"] = round(target, 2)
    size = look.get("caption_size", {})
    if size:
        dominant = max(size, key=size.get)
        px = {"large": 72, "medium": 64, "small": 58}[dominant]
        o["font.caption_px"]["value"] = clamp(px, *o["font.caption_px"]["range"])

    ovr["updated"] = dt.date.today().isoformat()
    ovr["source_week"] = trend.get("week")
    ovr["approved"] = False      # 사람이 확인 후 true로
    OVR.write_text(json.dumps(ovr, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) 제안은 자동 반영하지 않고 기록만
    props = trend.get("proposals") or []
    topics = trend.get("trending_topics") or []
    with PROPOSALS.open("a", encoding="utf-8") as f:
        f.write(f"\n## {trend.get('week')} ({ovr['updated']})\n")
        f.write(f"- 가중치 변경: formats {before[0]} → {json.dumps(ovr['format_weights'])}\n")
        f.write(f"- 가중치 변경: hooks {before[1]} → {json.dumps(ovr['hook_style_weights'])}\n")
        if topics:
            f.write("- 이번 주 주제 후보: " + ", ".join(topics[:10]) + "\n")
        for p in props:
            f.write(f"- [ ] 제안: {p}\n")
        for obs in trend.get("top_vs_bottom", []):
            f.write(f"- 관찰: {obs}\n")

    print(f"갱신: {OVR} (approved=false, 확인 필요)")
    print(f"제안 기록: {PROPOSALS}")


if __name__ == "__main__":
    main()
