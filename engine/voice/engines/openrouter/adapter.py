"""오픈라우터 음성 — 설정 → 모델 의 '말하기 · 음성'(voice.tts)에서 고른 모델. 말투 지시(style)는 instructions 로(받는 모델만)"""
from pathlib import Path
import subprocess
import sys

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401


def available() -> bool:
    import catalog
    return bool(catalog.chosen("voice.tts"))


def synth(text, out_wav: Path, voice=None, speed=1.0, style=None):
    import catalog
    import openrouter as OR
    model = catalog.chosen("voice.tts")
    if not model:
        raise RuntimeError("오픈라우터 음성 모델을 고르지 않았습니다 — 설정 → 모델 → 말하기 · 음성")
    mp3 = Path(out_wav).with_suffix(".or.mp3")
    OR.speech(model, text, mp3, voice=voice or None, speed=speed, instructions=style)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(out_wav)], check=True)
    mp3.unlink(missing_ok=True)
    catalog.record("-", "voice.tts", model, None, f"음성 {len(text)}자", extra={"chars": len(text)})
