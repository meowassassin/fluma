#!/usr/bin/env python3
"""듣기(받아쓰기) — 설정에서 '듣기 · 받아쓰기' 모델을 골랐으면 오픈라우터로, 아니면 None(부르는 쪽이 로컬 faster-whisper 로).
결과 모양은 shorts_xray.speech 와 같다: [{start, end, text, words: [{w, s, e}]}] — 단어 시각이 안 오면 구간 안에서 글자 수로 나눈다.
쓰는 곳: 레퍼런스 받아쓰기(shorts_xray · ref_channel) · 클립 원본 말 자막(clip.py --subs) · 생성 클립 대사 확인 · 오픈라우터 음성의 단어 시각.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401


def _dur(p: Path) -> float:
    try:
        from craft import vclip
        return float(vclip.probe(p)["dur"] or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _split_words(seg: dict) -> list[dict]:
    toks = seg.get("text", "").split()
    if not toks:
        return []
    a, b = float(seg.get("start", 0)), float(seg.get("end", 0))
    n = sum(max(1, len(re.sub(r"\W", "", t))) for t in toks)
    out, t = [], a
    for tok in toks:
        d = (b - a) * max(1, len(re.sub(r"\W", "", tok))) / n
        out.append({"w": tok, "s": round(t, 2), "e": round(t + d, 2)})
        t += d
    return out


def remote(src: Path, language: str | None = None, sid: str = "-", approve: bool = True) -> list[dict] | None:
    """오픈라우터 받아쓰기. 모델을 안 골랐거나 키가 없으면 None. approve 기본 True — 받아쓰기는 몇 센트 이하라 상한 안에서 장부만 남긴다"""
    import catalog
    import openrouter as OR
    mdl = catalog.chosen("voice.stt")
    if not mdl:
        return None
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(wav)], check=True)
        secs = _dur(wav)
        row = next((m for m in catalog.raw().get("models?output_modalities=transcription") or [] if m["id"] == mdl), {})
        est = round(secs * (catalog._f((row.get("pricing") or {}).get("prompt")) or 0), 4) if row else None
        catalog.guard(sid, "voice.stt", mdl, est, f"받아쓰기 {secs:.0f}초", approve)
        js = OR.transcribe(mdl, wav, language)
    catalog.record(sid, "voice.stt", mdl, js.get("cost"), f"받아쓰기 {secs:.0f}초", est=est)
    segs = js.get("segments") or ([{"start": 0, "end": secs, "text": js.get("text", "")}] if js.get("text") else [])
    words = js.get("words") or []
    out = []
    for s in segs:
        a, b = float(s.get("start", 0)), float(s.get("end", 0))
        ws = [{"w": (w.get("word") or w.get("text") or "").strip(), "s": round(float(w.get("start", 0)), 2), "e": round(float(w.get("end", 0)), 2)}
              for w in words if a - 0.05 <= float(w.get("start", 0)) < b + 0.05]
        seg = {"start": round(a, 2), "end": round(b, 2), "text": str(s.get("text", "")).strip()}
        seg["words"] = ws or _split_words(seg)
        out.append(seg)
    return out
