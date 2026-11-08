"""영상 재료 자르기 — 길이 재기(probe) · 쓸 구간(span: in · out · end). materials 가 영상 재료를 장면 길이에 맞출 때 쓴다."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe(f: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(f)],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        d = {}
    v = next((s for s in d.get("streams") or [] if s.get("codec_type") == "video"), {})
    return {"dur": float((d.get("format") or {}).get("duration") or 0), "w": v.get("width") or 0, "h": v.get("height") or 0,
            "audio": any(s.get("codec_type") == "audio" for s in d.get("streams") or [])}


def span(m: dict, dur: float) -> tuple[float, float]:
    a = max(0.0, float(m.get("in") or 0))
    b = float(m["out"]) if m.get("out") is not None else dur
    b = min(b, dur) if dur else b
    if b <= a:
        raise RuntimeError(f"{m.get('id')}: in({a}) 이 out({b}) 보다 뒤입니다")
    return a, b
