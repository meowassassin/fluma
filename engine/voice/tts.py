#!/usr/bin/env python3
"""
음성 어댑터. synth(text, out_wav, voice=None) 하나로 제공자를 숨긴다.

제공자는 환경변수 TTS_PROVIDER 로 고른다 (없으면 edge):
  edge        edge-tts (무료, 시제품용). 음성은 engine/spec/tokens/default.json audio.voice_id 또는 ko-KR-SunHiNeural
  openrouter  오픈라우터 키 하나 — 설정 → 모델 → 말하기 · 음성 에서 고른 모델(유료). 말투 지시(style)를 받는 모델은 그대로 넘긴다
  로컬 엔진   supertonic · melotts · chatterbox · cosyvoice · xtts · espeak (engine/voice/engines/<이름>/adapter.py)
  silent      네트워크 없이 파이프라인을 돌리기 위한 무음 WAV (길이 = 공백 제외 글자수 / 5.5초, 최소 1초)
업체별 키(Typecast · ElevenLabs · Gemini)는 2026-11-09 에 없앴다 — 유료 음성은 오픈라우터 하나로

출력은 항상 24kHz 16-bit mono WAV 로 맞춘다 (다른 포맷은 ffmpeg 로 변환).
제공자 추가 = PROVIDERS 딕셔너리에 함수 하나.

CLI:  python engine/voice/tts.py "문장" out.wav
      TTS_PROVIDER=silent python engine/voice/tts.py "문장" out.wav
      python engine/voice/tts.py "문장" out.wav openrouter alloy   (엔진 · 목소리 지정)
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
TOKENS = json.loads((ROOT / "engine" / "spec" / "tokens" / "default.json").read_text(encoding="utf-8"))
SR = 24000
FFMPEG = shutil.which("ffmpeg") or next((str(p) for p in Path("/opt/pw-browsers").glob("ffmpeg-*/ffmpeg-linux")), "ffmpeg")

DEFAULT_VOICE = {
    "edge": TOKENS["audio"].get("voice_id") or "ko-KR-SunHiNeural",   # 남성: ko-KR-InJoonNeural
}


def syllables(text: str) -> int:
    return len(re.sub(r"[\s\.,!?~…·\-\(\)\[\]\"'/:;]", "", text))


def write_silence(out_wav: Path, seconds: float):
    n = int(SR * seconds)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"\x00\x00" * n)


def to_wav(src: Path, out_wav: Path):
    """mp3 등 → 24kHz mono 16-bit wav"""
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", str(out_wav)], check=True)


# ---------- 제공자 ----------

def _silent(text, out_wav, voice):
    write_silence(out_wav, max(1.0, syllables(text) / 5.5))


def _edge(text, out_wav, voice, speed=1.0):
    """edge-tts. 단어 경계(WordBoundary)도 받아 <wav>.words.json 에 남긴다 (단어 단위 자막용)."""
    import asyncio
    import edge_tts  # pip install edge-tts
    rate = TOKENS["audio"].get("speed", 1.0) * speed   # 콘티 voice.speed 를 곱한다
    pct = int(round((rate - 1.0) * 100))
    tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
    words = []

    async def run():
        com = edge_tts.Communicate(text, voice or DEFAULT_VOICE["edge"], rate=f"{pct:+d}%", boundary="WordBoundary")
        with open(tmp, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":   # offset·duration 단위는 100ns
                    words.append({"text": ch["text"], "startMs": round(ch["offset"] / 1e4), "endMs": round((ch["offset"] + ch["duration"]) / 1e4)})
    # Edge 온라인 서비스는 가끔 소리 없이 끝난다(NoAudioReceived, 2026-11-02 영어 나레이션에서 확인 — 다시 하면 됨). 사람이 다시 누르지 않게 두 번 더
    for k in range(3):
        try:
            words.clear(); asyncio.run(run()); break
        except edge_tts.exceptions.NoAudioReceived:
            if k == 2:
                raise
            import time
            time.sleep(1.5 * (k + 1))
    to_wav(tmp, out_wav); tmp.unlink(missing_ok=True)
    write_words(out_wav, words)


PROVIDERS = {"silent": _silent, "edge": _edge}

# ---------- 음성 엔진 레지스트리 (engine/voice/engines/<이름>/voice.json + adapter.py) — 렌더 엔진처럼 갈아 끼운다 ----------
VOICES = ROOT / "engine" / "voice" / "engines"


def voice_meta(name: str) -> dict:
    p = VOICES / name / "voice.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def list_voice_engines() -> list[str]:
    return sorted(d.name for d in VOICES.iterdir() if (d / "voice.json").exists()) if VOICES.exists() else []


def _adapter(name: str):
    import importlib.util
    path = VOICES / name / "adapter.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"voice_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine_available(name: str) -> bool:
    if name in ("edge", "silent"):
        return True
    a = _adapter(name)
    try:
        return bool(a and a.available())
    except Exception:
        return False


def _settings() -> dict:
    try:
        return json.loads((ROOT / "data" / "workspace" / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve(sb: dict | None = None) -> tuple[str, str | None]:
    """(엔진, 목소리). 우선순위: 사용자가 콘티에 직접 정한 목소리(voice.source == "user") > 설정(설정 → 미디어 → 음성:
    data/workspace/settings.json voice_engine · voice_id) > 도구가 자동으로 적은 콘티 목소리(direct.py · voice_match.py) > TTS_PROVIDER > edge.
    (예전엔 콘티 목소리가 늘 이겨서, 레퍼런스 카드가 적은 Edge 가 설정의 유료 엔진을 덮었다.) 말 속도 · 감정 같은 다른 voice 값은 그대로 쓴다.
    쓸 수 없는 엔진이면(미설치 · 키 없음) edge 로 바꾸고 알린다."""
    v = (sb or {}).get("voice") or {}
    st = _settings()
    if st.get("voice_engine") and v.get("source") != "user":
        eng, vid = str(st["voice_engine"]).lower(), st.get("voice_id")
    else:
        eng = (v.get("engine") or st.get("voice_engine") or os.environ.get("TTS_PROVIDER") or "edge").lower()
        vid = v.get("id") if v.get("engine") else (st.get("voice_id") if st.get("voice_engine") == eng else None)
    if not engine_available(eng):
        print(f"[tts] 음성 엔진 {eng} 을(를) 쓸 수 없음(미설치 · 키 없음) → edge 로 대체", file=sys.stderr)
        eng, vid = "edge", None
    return eng, vid or None


def provider_name() -> str:
    return resolve()[0]


def words_path(wav) -> Path:
    return Path(str(wav) + ".words.json")


def write_words(wav, words: list):
    words_path(wav).write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")


def estimate_words(text: str, seconds: float) -> list:
    """단어 경계를 주지 않는 제공자: 글자 수 비례로 나눈다 (공백 기준 단어)."""
    toks = text.split()
    total = sum(max(1, syllables(t)) for t in toks) or 1
    out, t = [], 0.0
    for tok in toks:
        d = seconds * max(1, syllables(tok)) / total
        out.append({"text": tok, "startMs": round(t * 1000), "endMs": round((t + d) * 1000)})
        t += d
    return out


ENDING_MODES = ("keep", "period")


def tts_text(text: str, ending: str | None) -> str:
    """말끝 처리: period = 문장 중간 쉼표를 마침표로(말끝이 올라가지 않고 떨어진다). 콘티 · 자막 글은 그대로 둔다"""
    if ending == "period":
        return re.sub(r",(\s|$)", r".\1", text)
    return text


def synth(text: str, out_wav, voice: str | None = None, engine: str | None = None, speed: float = 1.0, style: str | None = None,
          opts: dict | None = None) -> Path:
    """합성 + 단어 타이밍(<wav>.words.json). 경계를 안 주는 엔진은 글자 수로 추정.
    opts(콘티 voice 의 조절 값): ending(keep · period) — 말투 지시(style)는 받는 엔진(openrouter 의 일부 모델)만 쓴다"""
    out_wav = Path(out_wav); out_wav.parent.mkdir(parents=True, exist_ok=True)
    eng = engine or provider_name()
    o = opts or {}
    said = tts_text(text, o.get("ending"))
    words_path(out_wav).unlink(missing_ok=True)
    if eng == "edge":
        _edge(said, out_wav, voice, speed)
        restore_punct(out_wav, text)
    elif eng in PROVIDERS:
        PROVIDERS[eng](said, out_wav, voice)
    else:
        raw = out_wav.with_suffix(".raw.wav")
        ad = _adapter(eng)
        if eng == "openrouter":
            ad.synth(said, raw, voice, speed, style)
            try:                              # 단어 시각을 주지 않는 엔진 — '듣기' 모델이 있으면 실제로 받아써서 맞춘다(없으면 글자 수 추정)
                import listen
                segs = listen.remote(raw)
                if segs:
                    write_words(out_wav, [{"text": w["w"], "startMs": int(w["s"] * 1000), "endMs": int(w["e"] * 1000)} for s in segs for w in s["words"] if w["w"]])
            except Exception as e:  # noqa: BLE001
                print(f"[tts] 단어 시각 받아쓰기 건너뜀: {e}", file=sys.stderr)
        else:
            ad.synth(said, raw, voice, speed)
        to_wav(raw, out_wav); raw.unlink(missing_ok=True)
    if not words_path(out_wav).exists():
        write_words(out_wav, estimate_words(text, duration(out_wav)))
    elif said != text:                      # 단어 글자를 원문(쉼표)으로 되돌린다 — 자막은 콘티 글 그대로
        ws, orig = read_words(out_wav), text.split()
        if len(ws) == len(orig):
            write_words(out_wav, [{**w, "text": t} for w, t in zip(ws, orig)])
    return out_wav


def restore_punct(wav, text: str) -> None:
    """단어 타이밍의 글자에 나레이션 원문의 문장부호를 되붙인다(<wav>.words.json 고쳐 씀, 여러 번 불러도 같음).
    Edge 의 WordBoundary 는 '?' ',' '.' 를 떼고 보내서 영어 자막에 물음표 · 마침표가 모두 빠졌다(2026-11-02). 원문 단어와 차례로 맞춘다"""
    ws = read_words(wav)
    if not ws or not text:
        return
    norm = lambda x: re.sub(r"[^\w'’-]", "", x).lower()
    toks, j, changed = text.split(), 0, False
    for w in ws:
        k = j
        while k < len(toks) and norm(toks[k]) != norm(w["text"]):
            k += 1
        if k < len(toks):
            if toks[k] != w["text"] and norm(toks[k]) == norm(w["text"]):
                w["text"] = toks[k]; changed = True
            j = k + 1
    if changed:
        write_words(wav, ws)


def read_words(wav) -> list:
    p = words_path(wav)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def duration(wav_path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / w.getframerate()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('사용: python engine/voice/tts.py "문장" out.wav')
    eng = sys.argv[3] if len(sys.argv) > 3 else None
    vid = sys.argv[4] if len(sys.argv) > 4 else None
    p = synth(sys.argv[1], sys.argv[2], vid, eng)
    print(f"{eng or provider_name()} → {p} ({duration(p):.2f}s)")
