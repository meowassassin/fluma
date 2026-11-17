"""말 주도 숏폼 박자 — 음성 길이만 장면을 정하고, 느린 TTS·정수 초 패딩을 막는다."""
from __future__ import annotations

from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())


def speech_led(sb: dict) -> bool:
    pr = sb.get("preset") or {}
    if pr.get("lead") == "말" and float(pr.get("speech_ratio") or 0) >= 0.55:
        return True
    if (sb.get("direction") or {}).get("lead") == "말":
        return True
    fmt = sb.get("format") or ""
    return fmt in ("concept", "fix", "compare", "mythbust", "daily", "ad", "series", "science")


def target_cps(sb: dict) -> float:
    pr = sb.get("preset") or {}
    if (pr.get("voice") or {}).get("cps"):
        return float(pr["voice"]["cps"])
    for rid in sb.get("reference") or []:
        p = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            import json

            v = (json.loads(p.read_text(encoding="utf-8")).get("voice") or {}).get("chars_per_sec")
            if v:
                return float(v)
    return 7.2


def voice_speed(sb: dict) -> float:
    """엔진 기본 6.6자/초 대비 합성 배속 — 말 주도는 최소 1.0(느린 0.8x 금지)."""
    cps = target_cps(sb)
    sp = round(max(1.0, min(1.55, cps / 6.6)), 2) if speech_led(sb) else round(max(0.9, min(1.5, cps / 6.6)), 2)
    locked = set((sb.get("voice") or {}).get("locked") or [])
    if "speed" in locked:
        return float((sb.get("voice") or {}).get("speed") or sp)
    return sp


def apply_voice_pace(sb: dict) -> bool:
    v = sb.setdefault("voice", {})
    if v.get("source") == "user" and v.get("speed") is not None:
        return False
    want = voice_speed(sb)
    old = float(v.get("speed") or 0)
    if abs(old - want) < 0.02 and old >= (1.0 if speech_led(sb) else 0.9):
        return False
    v["speed"] = want
    return True