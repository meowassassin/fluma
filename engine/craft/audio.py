"""Craft 파이프라인 — 소리 단계: 나레이션 · 효과음 · 배경음악 → SoundCraft 세션(.scraft) + 믹스 WAV.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (2 · 5절), 참고 .claude/skills/crafts/reference/soundcraft.md
  트랙 Voice   data/public/audio/<id>.voice.wav(나레이션만, 없으면 효과음이 섞인 <id>.wav)
               보이스 체인: eq_7band(HPF 90 Hz · 3.5 kHz 살짝 올림) → compressor → de_esser — 폰 스피커에서 또렷하게
  트랙 SFX     <id>.sfx.json 의 효과음마다 클립 하나(engine/voice/sfx/<이름>.wav 를 그 시각에) — 사람이 SoundCraft 에서 하나씩 밀고 당길 수 있다
  트랙 Music   콘티 music.src(사용자가 준 파일만) · gain_db(기본 −14) · 말하는 동안 duck_db(기본 −5) 만큼 내림
               — 말하는 구간은 단어 타이밍에서 구해 automation.write_range 로 쓰고, 앞뒤는 점 두 개로 부드럽게 경사
               — 끝은 영상 길이에 맞춰 자르고 s-curve 페이드 아웃(edit.fades_create, 길이는 샘플)
  마스터       maximizer(ceiling −1.5 dB) — 바운스 결과 LUFS 를 읽어 threshold 를 다시 맞추고 한 번 더 바운스(−14 LUFS 근처)
결과: data/compositions/<id>/craft/audio/<id>.scraft · <id>.mix.wav, craft.json 의 audio 기록에 lufs · true_peak_db
      (FilmCraft 단계는 lufs 가 있으면 최종 정규화를 따로 하지 않는다)
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import os
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "data" / "public"
SFX_DIR = ROOT / "assets" / "sfx"
RATE = 48000   # SoundCraft 새 세션의 샘플레이트

TARGET_LUFS = -14.0     # 쇼츠 라우드니스 목표
SFX_ONLY_LUFS = -18.0   # 효과음 · 정적만 있는 영상 — 조금 낮게(그래도 들리게)
CEILING_DB = -1.5       # maximizer ceiling 은 샘플 peak 기준 → true peak 여유를 두고 −1.5
LUFS_TOL = 0.5          # 이만큼 안이면 다시 바운스하지 않음
START_THRESHOLD = -4.0  # 첫 바운스의 maximizer threshold(이후 측정값으로 고침)
MAX_GAIN = 24.0         # 마스터에서 올릴 수 있는 최대 dB(조용한 녹음을 억지로 키워 찌그러뜨리지 않게)

# 나레이션 체인 — 슬롯 0 · 1 · 2 순서. 어느 것을 쓸지는 콘티 direction.sound.voice_chain(craft/design.py):
#   clean = 아래 셋(말 위주 레퍼런스 · 설명형), light = 저역만 정리(기본 — 근거 없이 소리를 바꾸지 않는다), none = 그대로
VOICE_CHAIN = [
    ("eq_7band", {"hpf_on": 1, "hpf_freq": 90, "high_mid_freq": 3500, "high_mid_gain": 2.0, "high_mid_q": 0.8}),
    ("compressor", {"threshold": -22, "ratio": 3, "attack": 5, "release": 80, "knee": 6, "makeup": 3}),
    ("de_esser", {"freq": 6500, "threshold": -28, "range": 8}),
]


def cli(app: str) -> Path | None:
    f = ROOT / "tools" / "crafts" / app / "installed.json"
    if not f.exists():                                          # 없으면 그 자리에서 설치(못 하면 ffmpeg 로 대신)
        import importlib.util
        spec = importlib.util.spec_from_file_location("fluma_crafts", ROOT / "engine" / "craft" / "crafts.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.ensure(app)
    try:
        rel = json.loads(f.read_text("utf-8")).get("cli")
    except (OSError, json.JSONDecodeError):
        return None
    p = ROOT / rel if rel else None
    return p if p and p.exists() else None


def speech_spans(words: list[dict], gap: float = 0.35) -> list[tuple[float, float]]:
    """단어 타이밍 → 말하는 구간들(사이가 gap 초보다 짧으면 이어 붙임)"""
    spans: list[list[float]] = []
    for w in sorted(words, key=lambda x: x["startMs"]):
        a, b = w["startMs"] / 1000, w["endMs"] / 1000
        if spans and a - spans[-1][1] <= gap:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return [(a, b) for a, b in spans]


def _cmd(cid: str, params: dict) -> str:
    return f"{cid}={json.dumps(params, ensure_ascii=False)}"


def _smp(sec: float) -> int:
    """초 → 세션 샘플(자동화 · 페이드 · 자르기는 숫자면 샘플이다 — 초로 넣으면 모든 점이 맨 앞에 몰린다)"""
    return int(round(max(0.0, sec) * RATE))


def sfx_gain_db() -> float:
    """assemble_audio 가 효과음을 섞던 배율(tokens audio.sfx_volume) → SFX 트랙 페이더 dB"""
    try:
        g = float(json.loads((ROOT / "engine" / "spec" / "tokens" / "default.json").read_text("utf-8"))["audio"].get("sfx_volume", 0.5))
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        g = 0.5
    return round(20 * math.log10(g), 2) if g > 0 else -60.0


def sfx_clips(sid: str) -> list[tuple[Path, float]] | None:
    """효과음 표(<id>.sfx.json) → [(파일, 영상 시각 초)]. 표가 없거나 파일이 빠졌으면 None(덩어리 sfx.wav 로 대신)"""
    marks_p = PUBLIC / "audio" / f"{sid}.sfx.json"
    try:
        marks = json.loads(marks_p.read_text("utf-8")) if marks_p.exists() else None
    except (OSError, json.JSONDecodeError):
        return None
    if marks is None:
        return None
    out = []
    for mk in marks:
        f = SFX_DIR / f"{mk.get('name')}.wav"
        if not f.exists():
            return None
        out.append((f, float(mk.get("at", 0.0))))
    return out


def material_events(sb: dict) -> list[tuple[Path, float]]:
    """재료가 남긴 순간(Blender F.event) → [(효과음 파일, 영상 시각 초)] — 화면에서 일어난 일에 소리가 저절로 맞는다"""
    out, t = [], 0.0
    base = ROOT / "data" / "compositions" / sb["id"] / "craft" / "materials"
    for n, sc in enumerate(sb.get("scenes") or [], 1):
        for ev in sc.get("sfx") or []:          # 콘티에 장면 기준으로 적은 효과음 — {"name": "stamp", "at": 3.3}
            w = SFX_DIR / f"{ev.get('name')}.wav"
            if w.exists():
                out.append((w, t + float(ev.get("at", 0))))
        for m in sc.get("materials") or []:
            f = base / f"s{n:02d}" / f"{m.get('id')}.json"
            try:
                rec = json.loads(f.read_text("utf-8")) if f.exists() else {}
            except (OSError, ValueError):
                rec = {}
            for ev in rec.get("events") or []:
                w = SFX_DIR / f"{ev.get('name')}.wav"
                if w.exists():
                    out.append((w, t + float(ev.get("at", 0))))
        t += float(sc.get("sec") or 0)
    return out


def clip_audio(sb: dict, out_dir: Path) -> list[tuple[Path, float]]:
    """퍼온 클립의 원음(동물 소리 · 현장 소리 · 반응) → [(wav, 영상 시각 초)] — 모음 · 반응 쇼츠는 원음이 살아 있어야 한다.
    재료 칸 "audio": false 면 뺀다. 클립마다 크기를 고르게(loudnorm −20 LUFS) 맞추고 장면 길이만큼 자른다"""
    out, t = [], 0.0
    base = ROOT / "data" / "compositions" / sb["id"] / "craft" / "materials"
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, sc in enumerate(sb.get("scenes") or [], 1):
        sec = float(sc.get("sec") or 0)
        for m in sc.get("materials") or []:
            if m.get("type") not in ("video", "stock") or m.get("audio") is False:
                continue
            def has_audio(f: Path) -> bool:
                p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
                return "audio" in p.stdout
            src, ss = base / f"s{n:02d}" / f"{m.get('id')}.mp4", 0.0
            if not (src.exists() and has_audio(src)):                   # 재료 단계는 화면만 남긴다 → 원본 파일의 소리(잘라 쓴 시작점 in 을 따라)
                src, ss = ROOT / str(m.get("src") or ""), float(m.get("in") or 0)
            if not src.exists() or src.suffix.lower() not in (".mp4", ".mov", ".webm", ".mkv", ".m4v") or not has_audio(src):
                continue
            w = out_dir / f"s{n:02d}-{m.get('id')}.wav"
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.3f}", "-i", str(src), "-vn", "-t", f"{sec:.3f}", "-af", "loudnorm=I=-20:TP=-3:LRA=11,afade=t=out:st=%.3f:d=0.08" % max(0.0, sec - 0.08),
                                "-ar", str(RATE), "-ac", "2", str(w)], capture_output=True, text=True)
            if r.returncode == 0 and w.exists() and audible(w):
                out.append((w, t))
        t += sec
    return out


def music_path(sb: dict) -> Path | None:
    src = (sb.get("music") or {}).get("src")
    if not src:
        return None
    p = Path(src) if Path(src).is_absolute() else ROOT / src
    return p if p.exists() else None


def audible(path: Path, floor_db: float = -50.0) -> bool:
    """WAV 에 들리는 소리가 있나(16비트 PCM 만 직접 읽음 — 모르는 형식이면 있다고 본다)"""
    try:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                return True
            a = array.array("h", w.readframes(w.getnframes()))
    except (OSError, wave.Error, EOFError):
        return True
    peak = max((abs(x) for x in a), default=0)
    return peak > 0 and 20 * math.log10(peak / 32768) > floor_db


def duck_points(words: list[dict], base: float, duck: float, dur: float) -> list[str]:
    """Music 음량 자동화 — 전체를 base 로 쓰고, 말하는 구간마다 write_range(duck) + 앞뒤 경사 점(0.2초 내려가고 0.3초 올라옴)"""
    c = [_cmd("automation.write_range", {"track": "Music", "param": "volume", "start": 0, "end": _smp(dur), "value": base})]
    # 경사 구간(앞 0.15초 · 뒤 0.35초)이 이웃 구간과 겹치지 않게 0.6초보다 가까운 말은 한 구간으로
    for a, b in speech_spans(words, gap=0.6):
        a0, a1, b0, b1 = max(0.0, a - 0.15), a + 0.05, b, min(dur, b + 0.35)
        if a1 >= b0 or a0 >= dur:
            continue
        c += [_cmd("automation.write_range", {"track": "Music", "param": "volume", "start": _smp(a0), "end": _smp(b1), "value": duck}),
              _cmd("automation.set_point", {"track": "Music", "param": "volume", "at": _smp(a0), "value": base}),
              _cmd("automation.set_point", {"track": "Music", "param": "volume", "at": _smp(a1), "value": duck}),
              _cmd("automation.set_point", {"track": "Music", "param": "volume", "at": _smp(b0), "value": duck}),
              _cmd("automation.set_point", {"track": "Music", "param": "volume", "at": _smp(b1), "value": base})]
    return c


def commands(sb: dict, voice: Path, words: list[dict], dur: float, threshold: float = START_THRESHOLD) -> list[str]:
    """새 세션을 짓는 SoundCraft --cmd 목록 — 트랙: Voice(+체인) · SFX(효과음마다 클립) · Music(덕킹) · Master(maximizer).
    음악 끝 자르기 · 페이드는 클립 id 가 필요해 다음 실행(finish_commands)에서 한다"""
    sid = sb["id"]
    v_only, fx = PUBLIC / "audio" / f"{sid}.voice.wav", PUBLIC / "audio" / f"{sid}.sfx.wav"
    split = v_only.exists() and fx.exists()               # 음성 단계가 나레이션 · 효과음을 따로 남겼으면 트랙도 따로
    c = [_cmd("track.new", {"kind": "audio", "format": "stereo", "name": "Voice"}),
         _cmd("file.import_audio", {"path": str(v_only if split else voice), "track": "Voice", "at": 0, "new_tracks": False})]
    from .design import resolve as _resolve
    snd = _resolve(sb)["sound"]
    chain = {"clean": VOICE_CHAIN, "light": [("eq_7band", {"hpf_on": 1, "hpf_freq": 80})], "none": []}.get(snd.get("voice_chain"), VOICE_CHAIN[:1])
    c += [_cmd("mix.insert", {"track": "Voice", "plugin": p, "params": prm}) for p, prm in chain]
    if split:
        clips = sfx_clips(sid)
        if clips is None:                                   # 표가 없거나 효과음 파일이 빠짐 → 섞인 덩어리 그대로
            clips = [(fx, 0.0)] if audible(fx) else []
            gain = 0.0                                     # 덩어리에는 이미 배율이 들어가 있다
        else:
            gain = sfx_gain_db()
    else:
        clips, gain = [], sfx_gain_db()
    clips = list(clips) + material_events(sb)               # 재료가 남긴 순간(Blender F.event)
    if clips:
        c.append(_cmd("track.new", {"kind": "audio", "format": "stereo", "name": "SFX"}))
        c += [_cmd("file.import_audio", {"path": str(f), "track": "SFX", "at": {"seconds": round(at, 3)}, "new_tracks": False})
              for f, at in clips]
        if gain:
            c.append(_cmd("mix.volume", {"tracks": ["SFX"], "db": gain}))
    orig = clip_audio(sb, ROOT / "data" / "compositions" / sid / "craft" / "audio" / "clips")
    if orig:                                                # 퍼온 클립 원음 — 모음 · 반응 쇼츠는 원음이 살아 있어야 한다
        c.append(_cmd("track.new", {"kind": "audio", "format": "stereo", "name": "Clips"}))
        c += [_cmd("file.import_audio", {"path": str(f), "track": "Clips", "at": {"seconds": round(at, 3)}, "new_tracks": False}) for f, at in orig]
        cg = float((sb.get("direction") or {}).get("clip_audio_db", 0))
        if cg:
            c.append(_cmd("mix.volume", {"tracks": ["Clips"], "db": cg}))
    music = music_path(sb)
    if music:                                               # 곡마다 크기가 달라(작곡 결과는 −37 dB 처럼 작다) 먼저 −16 LUFS 로 맞춘다 — gain_db 는 그 위에서의 상대값
        mn = ROOT / "data" / "compositions" / sid / "craft" / "audio" / "music.norm.wav"
        mn.parent.mkdir(parents=True, exist_ok=True)
        if subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(music), "-af", "loudnorm=I=-16:TP=-2:LRA=11", "-ar", str(RATE), "-ac", "2", str(mn)], capture_output=True).returncode == 0:
            music = mn
    if music:
        m = sb.get("music") or {}
        base = float(m.get("gain_db", -14 if words else 0))     # 나레이션이 없으면 음악이 주인공
        duck = base + float(m.get("duck_db", snd.get("duck_db", -5)))
        c += [_cmd("track.new", {"kind": "audio", "format": "stereo", "name": "Music"}),
              _cmd("file.import_audio", {"path": str(music), "track": "Music", "at": 0, "new_tracks": False}),
              _cmd("mix.volume", {"tracks": ["Music"], "db": base})]
        c += duck_points(words, base, duck, dur)
    # 새 세션에는 마스터 트랙이 없다 → 만들고 리미터(maximizer)를 건다(마스터는 이름을 받지 않고 'Master 1' 로 생김)
    c += [_cmd("track.new", {"kind": "master", "format": "stereo", "name": "Master"}),
          _cmd("mix.insert", {"track": "Master 1", "plugin": "maximizer", "params": {"threshold": threshold, "ceiling": CEILING_DB, "release": 80}})]
    return c


def finish_commands(sb: dict, music_clip: dict | None, dur: float) -> list[str]:
    """두 번째 실행: 음악 클립을 영상 길이로 자르고 끝에 s-curve 페이드 아웃(+짧은 페이드 인), 바운스 전 자체 검사"""
    c = []
    if music_clip:
        m = sb.get("music") or {}
        cid, frames = int(music_clip["clip"]), int(music_clip.get("frames") or 0)
        end = min(frames, _smp(dur)) if frames else _smp(dur)
        if frames > _smp(dur):
            c.append(_cmd("edit.trim_clip", {"clip": cid, "end": end}))
        fin, fout = float(m.get("fade_in", 0.05)), float(m.get("fade_out", 1.5))
        if fin > 0:
            c.append(_cmd("edit.fades_create", {"clip": cid, "side": "in", "length": min(_smp(fin), end // 2)}))
        if fout > 0:
            c.append(_cmd("edit.fades_create", {"clip": cid, "side": "out", "length": min(_smp(fout), end // 2), "shape": "s-curve"}))
    c.append(_cmd("session.audio_health", {}))
    return c


def master_commands(gain: float) -> list[str]:
    """마스터에서 gain dB 만큼 — maximizer threshold 로 올리고(0~MAX_GAIN), 줄여야 하면 리미터 뒤 페이더로 내린다"""
    gain = max(-30.0, min(MAX_GAIN, gain))
    th = round(-max(0.0, gain), 2)
    fader = round(min(0.0, gain), 2)
    return [_cmd("mix.insert_params", {"track": "Master 1", "slot": 0, "params": {"threshold": th, "ceiling": CEILING_DB}}),
            _cmd("mix.volume", {"tracks": ["Master 1"], "db": fader})]


def parse_run(out: str) -> tuple[list[tuple[str, object]], dict | None]:
    """soundcraft-cli run 출력 → ([(명령 id, 결과)], 바운스 결과). 출력은 명령마다 `ID: JSON` 한 줄 → 바운스 JSON → 저장 JSON"""
    res, bounce = [], None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "lufs" in d:
                bounce = d
                if not isinstance(d.get("lufs"), (int, float)):   # 무음이면 측정값이 없을 수 있다
                    d["lufs"] = float("-inf")
            continue
        cid, sep, rest = line.partition(": ")
        if sep and "." in cid and " " not in cid:
            try:
                res.append((cid, json.loads(rest)))
            except json.JSONDecodeError:
                res.append((cid, rest))
    return res, bounce


def find_music_clip(cmds: list[str], res: list[tuple[str, object]]) -> dict | None:
    """명령 순서와 결과 순서는 같다 → Music 으로 가져온 클립의 {clip, frames}"""
    for c, (cid, r) in zip(cmds, res):
        if not c.startswith("file.import_audio=") or cid != "file.import_audio":
            continue
        if json.loads(c.split("=", 1)[1]).get("track") == "Music" and isinstance(r, dict) and r.get("imported"):
            return r["imported"][0]
    return None


def health_report(res: list[tuple[str, object]]) -> list[str]:
    """session.audio_health 결과 → 문제 줄들(없으면 빈 목록)"""
    out = []
    for cid, r in res:
        if cid == "session.audio_health" and isinstance(r, dict) and not r.get("healthy", True):
            for i in r.get("issues") or [{"issue": f"문제 {r.get('issue_count')}개"}]:
                out.append(json.dumps(i, ensure_ascii=False) if not isinstance(i, str) else i)
    return out


def _sc(sc: Path, args: list[str], d: Path) -> tuple[subprocess.CompletedProcess, list, dict | None]:
    r = subprocess.run([str(sc), "run"] + args, cwd=str(d), text=True, capture_output=True, timeout=300,
                       env={**os.environ, "SOUNDCRAFT_NO_PREFS": "1"})
    res, bounce = parse_run(r.stdout)
    return r, res, bounce


def _x(cmds: list[str]) -> list[str]:
    return [x for c in cmds for x in ("--cmd", c)]


def mix(sb: dict, dur: float, out_dir: Path | None = None) -> tuple[Path, Path] | None:
    """세션 + 믹스 WAV 를 만든다. SoundCraft 가 없거나 실패하면 None(마무리 단계가 ffmpeg 로 대신 섞음)"""
    sc = cli("soundcraft")
    sid = sb["id"]
    voice = PUBLIC / "audio" / f"{sid}.wav"
    if sc and not voice.exists() and music_path(sb):           # 나레이션 없는 음악 주도 영상: 무음 트랙으로 같은 세션을 짓는다
        voice = (out_dir or (ROOT / "data" / "compositions" / sid / "craft" / "audio")) / f"{sid}.silence.wav"
        voice.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{dur:.3f}", str(voice)], check=True)
    if not sc or not voice.exists():
        return None
    caps_p = PUBLIC / "audio" / f"{sid}.captions.json"
    words = json.loads(caps_p.read_text("utf-8")) if caps_p.exists() else []
    d = out_dir or (ROOT / "data" / "compositions" / sid / "craft" / "audio")
    d.mkdir(parents=True, exist_ok=True)
    session, wav = d / f"{sid}.scraft", d / f"{sid}.mix.wav"
    man_p = d.parent / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    au = man.get("audio") or {}
    end = ["--bounce", str(wav), "--end", f"{dur:.3f}"]
    fail = "[소리] SoundCraft 실패 — ffmpeg 로 대신 섞습니다"
    try:
        if session.exists() and au.get("hash") and _sha(session) != au["hash"]:
            # 사람이 세션을 고쳤다 → 다시 만들지 않고 그 세션으로 바운스만(마스터도 사람이 정한 그대로)
            r, res, bounce = _sc(sc, ["--in", str(session), "--cmd", _cmd("session.audio_health", {})] + end, d)
            if r.returncode != 0 or not wav.exists():
                print(f"{fail}\n{(r.stdout + r.stderr)[-800:]}")
                return None
            for p in health_report(res):
                print(f"[소리] 세션 검사: {p}")
            au["edited"] = True
            target = None
        else:
            # 라우드니스: 말소리 · 음악 · 퍼온 클립 원음이 있으면 −14 LUFS(쇼츠 기준). 효과음만 있으면 −18 LUFS 로 조금 낮게(리미터가 '딱' 소리 꼭대기를 누른다)
            # 2026-11-09: 효과음만 있는 영상을 아예 안 키워 −29 LUFS — 앱 · 폰에서 '소리가 안 들린다'
            v_only = PUBLIC / "audio" / f"{sid}.voice.wav"
            has_clip = any(isinstance(m, dict) and m.get("type") in ("video", "stock") and m.get("audio") is not False
                           for sc_ in sb.get("scenes") or [] for m in sc_.get("materials") or [])
            program = bool(words) or music_path(sb) is not None or audible(v_only if v_only.exists() else voice) or has_clip
            target = TARGET_LUFS if program else SFX_ONLY_LUFS
            gain = -START_THRESHOLD if program else 0.0
            # 1) 세션 짓기
            cmds = commands(sb, voice, words, dur, threshold=-gain)
            r, res, _ = _sc(sc, _x(cmds) + ["--save", str(session)], d)
            if r.returncode != 0 or not session.exists():
                print(f"{fail}\n{(r.stdout + r.stderr)[-800:]}")
                return None
            # 2) 음악 끝 자르기 · 페이드 + 자체 검사 + 첫 바운스(라우드니스 측정)
            more = finish_commands(sb, find_music_clip(cmds, res), dur)
            from .refine import sound_cmds
            more += sound_cmds(sb)                      # 다듬기(장면 · 영상 전체 SoundCraft 명령) — 라우드니스 측정 전에
            inplace = ["--in", str(session), "--in-place", "--save", str(session)]
            r, res, bounce = _sc(sc, inplace + _x(more) + end, d)
            if r.returncode != 0 or not wav.exists() or not bounce:
                print(f"{fail}\n{(r.stdout + r.stderr)[-800:]}")
                return None
            for p in health_report(res):
                print(f"[소리] 세션 검사: {p}")
            # 3) 측정값으로 마스터를 고쳐 다시 바운스
            first = bounce["lufs"]
            for _ in range(2):                              # 리미터가 비선형이라 많아야 두 번 고친다
                if target is None or not math.isfinite(bounce["lufs"]) or abs(bounce["lufs"] - target) <= LUFS_TOL:
                    break
                new = max(-30.0, min(MAX_GAIN, gain + (target - bounce["lufs"])))
                if abs(new - gain) < 0.05:                  # 더 올릴 수 없음(MAX_GAIN)
                    break
                gain = new
                r, res, b2 = _sc(sc, inplace + _x(master_commands(gain)) + end, d)
                if r.returncode != 0 or not b2:
                    print(f"[소리] 라우드니스 다시 맞추기 실패 — 첫 바운스를 씁니다\n{(r.stdout + r.stderr)[-400:]}")
                    break
                bounce = b2
            print(f"[소리] 라우드니스 {first:.1f} → {bounce['lufs']:.1f} LUFS · true peak {bounce.get('true_peak_db', 0):.1f} dBTP"
                  + ("" if target != SFX_ONLY_LUFS else " (효과음만 — 조금 낮은 목표)"))
            au = {"file": os.path.relpath(session, ROOT), "hash": _sha(session), "app": "soundcraft"}
    except subprocess.TimeoutExpired:
        print(f"{fail} (시간 초과)")
        return None
    if bounce:
        au["lufs"] = round(float(bounce["lufs"]), 2)
        au["true_peak_db"] = round(float(bounce.get("true_peak_db", bounce.get("peak_db", 0.0))), 2)
        au["target_lufs"] = target
    man["audio"] = au
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return session, wav


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""
