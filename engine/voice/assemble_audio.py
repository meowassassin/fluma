#!/usr/bin/env python3
"""
증거층 2: 음성 트랙 조립 — **음성이 장면 길이를 정한다** (2026-10-28).

장면마다 나레이션을 합성(tts.synth, 단어 타이밍 포함)하고:
  - 기본(--fit): 실제 말소리 구간(첫 단어 시작 ~ 마지막 단어 끝)을 잘라 앞 LEAD·뒤 TAIL 여백을 붙이고,
    그 길이로 scene.sec 를 다시 쓴다. 합계는 정수 duration_sec(15~60)로 올림해 남는 시간을 장면들에 나눈다.
    더 이상 빨리 감거나 자르지 않는다 (12초를 넘는 장면만 예외적으로 빠르게).
  - --keep-sec: 예전 방식. 콘티의 sec 에 맞춰 최대 1.25배 빠르게, 그래도 길면 자름 (감성처럼 음악이 길이를 정할 때).
  - 장면 시작에 효과음(sfx) 을 섞는다.
산출:
  data/audio/<id>.wav, data/audio/<id>.timing.json, data/audio/<id>.captions.json (Caption[] {text,startMs,endMs,scene}, 영상 기준 ms)
  → data/public/audio/ 로 복사 (렌더 엔진·마무리 단계·웹 미리보기가 읽는다)

사용:
  python engine/voice/assemble_audio.py data/storyboards/<id>.json [--keep-sec]
  TTS_PROVIDER=silent python engine/voice/assemble_audio.py data/storyboards/<id>.json   # 네트워크 없이
"""
import hashlib
import json
import re
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from tts import synth, duration, write_silence, resolve, read_words, restore_punct, DEFAULT_VOICE, FFMPEG, SR  # noqa: E402
TOKENS = json.loads((ROOT / "engine" / "spec" / "tokens" / "default.json").read_text(encoding="utf-8"))
SFX_DIR = ROOT / "assets" / "sfx"
MAX_TEMPO = 1.25
LEAD = 0.15          # 장면 시작 → 첫 단어
TAIL = 0.30          # 마지막 단어 → 장면 끝
SEC_MIN, SEC_MAX = 2.0, 12.0
DUR_MIN, DUR_MAX = 15, 60
SFX_GAIN = float(TOKENS["audio"].get("sfx_volume", 0.5))

# 효과음 — 사인파(삑 소리)가 아니라 노이즈 기반으로 실제 효과음처럼 합성한다(예전 사인파는 '기계음'으로 들렸다).
# 모양을 바꾸면 SFX_VERSION 을 올린다 → 다음 실행 때 engine/voice/sfx/*.wav 를 다시 만든다
SFX_VERSION = "2"
SFX_NAMES = ("stamp", "pop", "tick", "swoosh")


def _onepole(x, a: float, high: bool = False):
    """한 극 필터(저역 · 고역) — numpy 만으로"""
    import numpy as np
    y = np.empty_like(x)
    acc = 0.0
    for k, v in enumerate(x):
        acc += a * (v - acc)
        y[k] = acc
    return x - y if high else y


def _sfx(name: str):
    import numpy as np
    rng = np.random.default_rng({"stamp": 1, "pop": 2, "tick": 3, "swoosh": 4}[name])
    if name == "swoosh":     # 휙: 대역이 아래에서 위로 쓸려 올라가는 바람 소리
        n = int(SR * 0.38); t = np.arange(n) / SR
        noise = rng.standard_normal(n)
        cut = np.linspace(0.04, 0.45, n)                  # 저역 차단 주파수가 점점 올라감
        y = np.empty(n); lo = 0.0
        for k in range(n):
            lo += cut[k] * (noise[k] - lo); y[k] = lo
        y = _onepole(y, 0.02, high=True)
        env = np.sin(np.pi * np.clip(t / t[-1], 0, 1)) ** 1.6
        y *= env
    elif name == "pop":      # 톡: 아주 짧은 터짐 + 아래로 떨어지는 짧은 음
        n = int(SR * 0.09); t = np.arange(n) / SR
        f = 520 * np.exp(-t * 28) + 140
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 45)
        burst = _onepole(rng.standard_normal(n), 0.35) * np.exp(-t * 160)
        y = 0.7 * tone + 0.6 * burst
    elif name == "tick":     # 딸깍: 3~5ms 클릭
        n = int(SR * 0.03); t = np.arange(n) / SR
        y = _onepole(rng.standard_normal(n), 0.5, high=True) * np.exp(-t * 900)
        y += 0.3 * np.sin(2 * np.pi * 1600 * t) * np.exp(-t * 500)
    else:                    # stamp 쿵: 낮게 떨어지는 쿵 + 짧은 타격 노이즈
        n = int(SR * 0.28); t = np.arange(n) / SR
        f = 95 * np.exp(-t * 9) + 45
        thump = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
        hit = _onepole(rng.standard_normal(n), 0.15) * np.exp(-t * 70)
        y = thump + 0.5 * hit
    y = y / (np.abs(y).max() + 1e-9) * 0.85
    fade = min(len(y), int(SR * 0.004))
    y[-fade:] *= np.linspace(1, 0, fade)                  # 끝 클릭 방지
    return (y * 32767).astype("<i2").tobytes()


def ensure_sfx():
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    ver = SFX_DIR / ".version"
    fresh = not ver.exists() or ver.read_text().strip() != SFX_VERSION
    for name in SFX_NAMES:
        p = SFX_DIR / f"{name}.wav"
        if p.exists() and not fresh:
            continue
        tmp = p.with_suffix(".tmp.wav")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(_sfx(name))
        tmp.replace(p)
    ver.write_text(SFX_VERSION)


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, f"포맷 불일치: {path}"
        return w.readframes(w.getnframes())


def write_pcm(path: Path, pcm: bytes):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)


def speed_up(src: Path, factor: float, dst: Path):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-filter:a", f"atempo={factor:.3f}",
                    "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", str(dst)], check=True)


def text_hash(text: str) -> str:
    """lint.py L14 가 '지금 나레이션으로 만든 음성인가'를 확인하는 키."""
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:8]


def mix_in(base: bytes, overlay: bytes, gain: float, at: float = 0.0) -> bytes:
    """overlay 를 base 의 at 초 위치에 더한다 (클리핑 방지)."""
    off = max(0, int(at * SR))
    n = max(0, min(len(base) // 2 - off, len(overlay) // 2))
    out = bytearray(base)
    for i in range(n):
        a = struct.unpack_from("<h", base, (off + i) * 2)[0]
        b = struct.unpack_from("<h", overlay, i * 2)[0]
        struct.pack_into("<h", out, (off + i) * 2, int(max(-32768, min(32767, a + b * gain))))
    return bytes(out)


def sfx_list(v) -> list[tuple[str, float]]:
    """콘티 sfx: "swoosh" (장면 시작) 또는 [{"name": "swoosh", "at": 0.4}, …] (장면 안 초 — 화면의 부딪힘 · 도장 순간에 맞춘다)"""
    if not v or v == "none":
        return []
    if isinstance(v, str):
        return [(v, 0.0)]
    return [(x.get("name", "none"), float(x.get("at", 0))) for x in v if isinstance(x, dict) and x.get("name") not in (None, "none")]


def fit(scene_wav: Path, sec: float, work: Path) -> tuple[bytes, float, float]:
    """장면 길이에 맞춘 PCM, 원래 나레이션 길이, 적용 배속을 돌려준다."""
    nar = duration(scene_wav) if scene_wav.exists() else 0.0
    target = int(SR * sec)
    sped = 1.0
    src = scene_wav
    if nar > sec and nar > 0:
        sped = min(MAX_TEMPO, nar / sec)
        fast = work / (scene_wav.stem + f".x{sped:.2f}.wav")
        speed_up(scene_wav, sped, fast)
        src = fast
    pcm = read_pcm(src) if src.exists() else b""
    pcm = pcm[: target * 2]                               # 그래도 길면 자름
    pcm += b"\x00\x00" * (target - len(pcm) // 2)          # 짧으면 무음 채움
    return pcm, nar, sped


def ceil1(x: float) -> float:
    return math.ceil(x * 10 - 1e-9) / 10


def speech(wav: Path) -> tuple[bytes, list, float]:
    """말소리 구간 PCM, 그 구간 기준 단어 타이밍(ms), 길이(s). 앞뒤 무음은 잘라 낸다."""
    pcm = read_pcm(wav)
    words = read_words(wav)
    total = len(pcm) / 2 / SR
    if words:
        a = max(0.0, words[0]["startMs"] / 1000 - 0.03)
        b = min(total, words[-1]["endMs"] / 1000 + 0.10)
    else:
        a, b = 0.0, total
    clip = pcm[int(a * SR) * 2: int(b * SR) * 2]
    shifted = [{**w, "startMs": w["startMs"] - a * 1000, "endMs": w["endMs"] - a * 1000} for w in words]
    return clip, shifted, len(clip) / 2 / SR


def opts_key(opts: dict | None) -> str:
    return "" if not opts else "|o" + json.dumps(opts, ensure_ascii=False, sort_keys=True)


def voice_opts(sb: dict) -> dict:
    """콘티 voice 의 조절 값(받는 엔진만 쓴다): ending(말끝 처리) · intensity(감정 강도) · pitch(반음)"""
    v = sb.get("voice") or {}
    return {k: v[k] for k in ("ending", "intensity", "pitch") if v.get(k) not in (None, "", "keep")}


def scene_wav(sc: dict, i: int, work: Path, prov: str, vid: str | None = None, speed: float = 1.0, style: str | None = None,
              opts: dict | None = None) -> tuple[Path, str]:
    nar_text = (sc.get("narration") or "").strip()
    # 캐시 키: 음성 엔진 · 목소리 · 문장 · 조절 값. 나레이션을 고치거나 엔진 · 목소리 · 조절 값을 바꾸면 다시 합성한다.
    key = hashlib.sha1(f"{prov}|{vid or DEFAULT_VOICE.get(prov, '')}|{nar_text}{'' if speed == 1.0 else f'|x{speed:g}'}{f'|s{style}' if style else ''}{opts_key(opts)}".encode("utf-8")).hexdigest()[:8]
    wav = work / f"scene-{i}-{key}.wav"
    # 단어 타이밍(.words.json)이 없는 예전 캐시는 다시 합성한다
    if nar_text and (not wav.exists() or not Path(str(wav) + ".words.json").exists()):
        synth(nar_text, wav, vid, prov, speed=speed, style=style, opts=opts)
    elif not nar_text and not wav.exists():
        write_silence(wav, 0.1)
    if nar_text:
        restore_punct(wav, nar_text)   # 캐시된 예전 합성에도(문장부호 없이 저장된 것)
    return wav, nar_text


def continuous_mode(sb: dict) -> bool:
    """이어 말하기: 콘티 voice.continuous, 없으면 레퍼런스 스타일 카드의 voice.continuous(참고 영상이 컷이 바뀌어도 말을 이어 가면)"""
    v = (sb.get("voice") or {}).get("continuous")
    if v is not None:
        return bool(v)
    for rid in sb.get("reference") or []:
        p = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            return bool(json.loads(p.read_text(encoding="utf-8")).get("voice", {}).get("continuous"))
    return False


def continuous_parts(scenes: list, work: Path, prov: str, vid, speed: float, style, opts: dict | None = None) -> list:
    """대본 전체를 한 번에 합성(문장이 장면을 넘어 자연스럽게 이어짐) → 단어를 글자 수로 장면에 나눠 담고,
    장면 사이는 앞 장면 마지막 단어 끝과 다음 장면 첫 단어 시작의 가운데에서 자른다(프레임 단위)."""
    texts = [(sc.get("narration") or "").strip() for sc in scenes]
    full = " ".join(texts)
    key = hashlib.sha1(f"{prov}|{vid or DEFAULT_VOICE.get(prov, '')}|{full}|x{speed:g}|s{style or ''}{opts_key({k: v for k, v in (opts or {}).items() if k in ('ending', 'intensity', 'pitch')})}|cont".encode("utf-8")).hexdigest()[:8]
    wav = work / f"all-{key}.wav"
    if not wav.exists() or not Path(str(wav) + ".words.json").exists():
        synth(full, wav, vid, prov, speed=speed, style=style, opts=opts)
    clip, words, total = speech(wav)
    cum, acc = [], 0
    for t in texts:
        acc += len(re.sub(r"\s", "", t)); cum.append(acc)
    owner, c = [], 0
    for w in words:
        c += len(re.sub(r"\s", "", w["text"]))
        owner.append(next((i for i, x in enumerate(cum) if c <= x + 1), len(texts) - 1))
    cuts = [0.0]
    for i in range(len(texts) - 1):
        a = [w for w, o in zip(words, owner) if o == i]; b = [w for w, o in zip(words, owner) if o == i + 1]
        if a and b:
            ms = (a[-1]["endMs"] + b[0]["startMs"]) / 2
        else:
            ms = total * 1000 * cum[i] / max(1, cum[-1])
        cuts.append(round(ms / 1000 * 30) / 30)
    cuts.append(total)
    for i in range(1, len(cuts) - 1):   # 장면은 2초 이상(스키마) — 짧으면 자르는 자리를 뒤로 민다(말은 이어지므로 티가 안 난다)
        cuts[i] = max(cuts[i], round((cuts[i - 1] + 2.0) * 30) / 30)
    parts = []
    for i, t in enumerate(texts):
        a0, a1 = cuts[i], max(cuts[i] + 1 / 30, cuts[i + 1])
        seg = clip[int(a0 * SR) * 2: int(a1 * SR) * 2]
        ws = [{**w, "startMs": w["startMs"] - a0 * 1000, "endMs": w["endMs"] - a0 * 1000} for w, o in zip(words, owner) if o == i]
        parts.append({"clip": seg, "words": ws, "speech": len(seg) / 2 / SR, "need": len(seg) / 2 / SR, "tempo": 1.0, "text": t, "wav": wav})
    return parts


def plan_secs(needs: list, fixed: list) -> list:
    """장면별 필요 길이 → 최종 sec. 합계를 정수 duration(15~60)으로 맞추고 남는 시간은 나레이션 장면부터 고르게."""
    secs = [min(SEC_MAX, max(SEC_MIN, ceil1(n))) for n in needs]
    total = sum(secs)
    target = min(DUR_MAX, max(DUR_MIN, math.ceil(total - 1e-9)))
    extra = round(target - total, 3)
    while extra > 1e-6:
        room = [i for i, s in enumerate(secs) if s < SEC_MAX and not fixed[i]] or [i for i, s in enumerate(secs) if s < SEC_MAX]
        if not room:
            break
        share = max(0.1, ceil1(extra / len(room)))
        for i in room:
            add = min(share, SEC_MAX - secs[i], extra)
            secs[i] = round(secs[i] + add, 3); extra = round(extra - add, 3)
            if extra <= 1e-6:
                break
    return [round(s, 2) for s in secs]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep = "--keep-sec" in sys.argv
    if not args:
        sys.exit("사용: python engine/voice/assemble_audio.py data/storyboards/<id>.json [--keep-sec]")
    sb_path = Path(args[0])
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    sid = sb["id"]
    work = ROOT / "data" / "audio" / sid
    work.mkdir(parents=True, exist_ok=True)
    ensure_sfx()
    prov, vid = resolve(sb)
    # 말 속도(콘티 voice.speed, 0.8~1.6): 엔진이 직접 빠르게 말한다(합성 뒤 빨리 감기보다 자연스럽다)
    speed = max(0.8, min(1.6, float((sb.get("voice") or {}).get("speed") or 1.0)))
    style = ((sb.get("voice") or {}).get("style") or "").strip() or None   # 말투 지시(글로 연기를 받는 엔진 — openrouter 의 일부 모델)
    vopts = voice_opts(sb)
    print(f"[음성] 엔진 {prov} · 목소리 {vid or '기본'}{' · ' + json.dumps(vopts, ensure_ascii=False) if vopts else ''}")
    scenes = sb["scenes"]

    # 1) 합성 + 필요한 길이
    parts = []
    cont = continuous_mode(sb) and not keep and all((sc.get("narration") or "").strip() for sc in scenes)
    if cont:
        parts = continuous_parts(scenes, work, prov, vid, speed, style, vopts)
        print("[음성] 이어 말하기: 대본 전체를 한 번에 합성하고 단어 사이 쉼에서 장면을 자릅니다")
    for i, sc in enumerate(scenes if not cont else []):
        # 장면마다 합성할 때는 앞뒤 장면 글을 문맥으로 넘긴다(문맥으로 감정을 고르는 엔진 — typecast smart)
        ctx = {"prev_text": (scenes[i - 1].get("narration") or "").strip() if i else None,
               "next_text": (scenes[i + 1].get("narration") or "").strip() if i + 1 < len(scenes) else None} if prov == "typecast" and not (sb.get("voice") or {}).get("style") else {}
        wav, nar_text = scene_wav(sc, i, work, prov, vid, speed, style, {**vopts, **{k: v for k, v in ctx.items() if v}})
        if nar_text:
            clip, words, speech_s = speech(wav)
        else:
            clip, words, speech_s = b"", [], 0.0
        tempo = 1.0
        if not keep and speech_s > SEC_MAX - LEAD - TAIL:      # 12초를 넘는 한 장면만 예외적으로 빠르게
            tempo = speech_s / (SEC_MAX - LEAD - TAIL)
            fast = work / f"{wav.stem}.fit.wav"
            write_pcm(fast, clip); speed_up(fast, tempo, fast.with_suffix(".x.wav"))
            clip = read_pcm(fast.with_suffix(".x.wav")); speech_s = len(clip) / 2 / SR
            words = [{**w, "startMs": w["startMs"] / tempo, "endMs": w["endMs"] / tempo} for w in words]
        need = (LEAD + speech_s + TAIL) if nar_text else float(sc["sec"])
        parts.append({"clip": clip, "words": words, "speech": speech_s, "need": need, "tempo": tempo, "text": nar_text, "wav": wav})

    # 2) 장면 길이 결정 — 말이 없는 영상(음악 · 화면 주도)은 콘티 길이 그대로. 최소 길이로 늘리면 재료가 끝난 뒤 화면이 빈다
    if keep or not any(p["text"] for p in parts):
        secs = [float(sc["sec"]) for sc in scenes]
    elif cont:   # 자른 길이 그대로(프레임 단위), 마지막 장면에 끝 여유
        secs = [round(round(p["need"] * 30) / 30, 3) for p in parts]
        secs[-1] = round(secs[-1] + (math.ceil(sum(secs) + TAIL) - sum(secs)), 3)   # 끝 여유를 두고 합계를 정수 초로
    else:
        secs = plan_secs([p["need"] for p in parts], [not p["text"] for p in parts])

    # 3) 조립
    pcm_all = bytearray()
    timing, captions = [], []
    t = 0.0
    print(f"제공자: {prov}  모드: {'keep-sec' if keep else 'fit (음성이 길이를 정함)'}")
    voice_all, sfx_all, sfx_marks = bytearray(), bytearray(), []
    print(f"{'장면':>4} {'역할':<8} {'전':>5} {'후':>5} {'말소리':>6} {'배속':>5}  sfx")
    for i, (sc, p, sec) in enumerate(zip(scenes, parts, secs)):
        target = int(SR * sec)
        if keep and p["text"]:
            pcm, nar, sped = fit(p["wav"], sec, work)
            words = [{**w, "startMs": w["startMs"] / sped, "endMs": w["endMs"] / sped} for w in read_words(p["wav"])]
            lead = 0.0
        else:
            lead = (LEAD if p["text"] else 0.0) if not cont else 0.0
            pcm = b"\x00\x00" * int(SR * lead) + p["clip"]
            pcm = pcm[: target * 2] + b"\x00\x00" * max(0, target - len(pcm) // 2)
            nar, sped, words = p["speech"], p["tempo"], p["words"]
        # 효과음은 장면당 하나 · '딸깍(tick)'은 빼기 — 많으면 거슬린다(2026-11-03 사용자 평가). 콘티 direction.sfx_dense 면 그대로
        fx = sfx_list(sc.get("sfx"))
        if not (sb.get("direction") or {}).get("sfx_dense"):
            fx = [x for x in fx if x[0] != "tick"][:1]
        voice_all += pcm                                   # 나레이션만(효과음 전) — SoundCraft Voice 트랙
        fxpcm = b"\x00\x00" * (len(pcm) // 2)               # 효과음만 — SoundCraft SFX 트랙
        for name, at in fx:
            f = SFX_DIR / f"{name}.wav"
            if f.exists():
                pcm = mix_in(pcm, read_pcm(f), SFX_GAIN, at)
                fxpcm = mix_in(fxpcm, read_pcm(f), SFX_GAIN, at)
                sfx_marks.append({"scene": i, "name": name, "at": round(t + at, 3)})
        sfx_all += fxpcm
        sfx = ",".join(f"{n}@{a:g}" if a else n for n, a in fx) or "none"
        pcm_all += pcm
        for w in words:
            s0 = (t + lead) * 1000 + w["startMs"]; e0 = (t + lead) * 1000 + w["endMs"]
            if s0 >= (t + sec) * 1000:
                continue
            captions.append({"text": " " + w["text"], "startMs": round(s0), "endMs": round(min(e0, (t + sec) * 1000)),
                             "timestampMs": round((s0 + e0) / 2), "confidence": None, "scene": i})
        timing.append({"scene": i, "role": sc["role"], "start": round(t, 3), "end": round(t + sec, 3), **({"dialogue": p["dialogue"]} if p.get("dialogue") else {}),
                       "narration_ms": int(nar * 1000), "sped": round(sped, 3), "sfx": sfx,
                       "text_hash": text_hash(p["text"])})
        print(f"{i:>4} {sc['role']:<8} {float(sc['sec']):>5.1f} {sec:>5.1f} {nar:>5.2f}s {sped:>5.2f}  {sfx}")
        t += sec

    # 4) 콘티에 실측 길이 반영
    if not keep:
        changed = any(abs(float(sc["sec"]) - s) > 1e-6 for sc, s in zip(scenes, secs))
        new_dur = int(round(sum(secs)))
        if changed or sb.get("duration_sec") != new_dur:
            for sc, s in zip(scenes, secs):
                sc["sec"] = int(s) if float(s).is_integer() else s
            sb["duration_sec"] = new_dur
            sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[콘티] 장면 길이를 실측 음성으로 갱신 → 합계 {new_dur}s ({sb_path})")

    out_wav = ROOT / "data" / "audio" / f"{sid}.wav"
    write_pcm(out_wav, bytes(pcm_all))                     # 나레이션 + 효과음(마무리 단계 finish.py 용)
    write_pcm(ROOT / "data" / "audio" / f"{sid}.voice.wav", bytes(voice_all))
    write_pcm(ROOT / "data" / "audio" / f"{sid}.sfx.wav", bytes(sfx_all))
    (ROOT / "data" / "audio" / f"{sid}.sfx.json").write_text(json.dumps(sfx_marks, ensure_ascii=False, indent=1), encoding="utf-8")
    a = ROOT / "data" / "audio"
    (a / f"{sid}.timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    (a / f"{sid}.captions.json").write_text(json.dumps(captions, ensure_ascii=False), encoding="utf-8")
    pub = ROOT / "data" / "public" / "audio"
    pub.mkdir(parents=True, exist_ok=True)
    for ext in (".wav", ".voice.wav", ".sfx.wav", ".sfx.json", ".timing.json", ".captions.json"):
        shutil.copy2(a / f"{sid}{ext}", pub / f"{sid}{ext}")
    print(f"\n→ {out_wav} ({duration(out_wav):.2f}s)  단어 {len(captions)}개  복사 → {pub}")


if __name__ == "__main__":
    main()
