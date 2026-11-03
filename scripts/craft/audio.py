"""Craft 파이프라인 — 소리 단계: 나레이션(+효과음) · 배경음악 → SoundCraft 세션(.scraft) + 믹스 WAV.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (2 · 5절)
  트랙 Voice   public/audio/<id>.wav (assemble_audio 가 나레이션에 효과음을 이미 섞은 파일)
  트랙 Music   콘티 music.src(사용자가 준 파일만) · gain_db(기본 −14) · 말하는 동안 duck_db(기본 −5) 만큼 자동으로 내림
               — 말하는 구간은 단어 타이밍에서 구하고, 그 앞뒤에 음량 자동화 점을 찍는다(사람이 SoundCraft 에서 점을 고칠 수 있음)
  마스터       리미터(maximizer)
결과: compositions/<id>/craft/audio/<id>.scraft · <id>.mix.wav
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
RATE = 48000   # SoundCraft 새 세션의 샘플레이트


def cli(app: str) -> Path | None:
    f = ROOT / "tools" / "crafts" / app / "installed.json"
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


def commands(sb: dict, voice: Path, words: list[dict], dur: float) -> list[str]:
    """SoundCraft run 에 넘길 --cmd 목록 — 트랙: Voice(나레이션) · SFX(효과음, 있으면) · Music(있으면) · Master"""
    sid = sb["id"]
    v_only, fx = PUBLIC / "audio" / f"{sid}.voice.wav", PUBLIC / "audio" / f"{sid}.sfx.wav"
    split = v_only.exists() and fx.exists()               # 음성 단계가 나레이션 · 효과음을 따로 남겼으면 트랙도 따로
    c = [f"track.new={json.dumps({'kind': 'audio', 'format': 'stereo', 'name': 'Voice'})}",
         f"file.import_audio={json.dumps({'path': str(v_only if split else voice), 'track': 'Voice', 'at': 0, 'new_tracks': False})}"]
    marks = PUBLIC / "audio" / f"{sid}.sfx.json"
    if split and marks.exists() and json.loads(marks.read_text("utf-8")):
        c += [f"track.new={json.dumps({'kind': 'audio', 'format': 'stereo', 'name': 'SFX'})}",
              f"file.import_audio={json.dumps({'path': str(fx), 'track': 'SFX', 'at': 0, 'new_tracks': False})}"]
    m = sb.get("music") or {}
    src = m.get("src")
    music = (ROOT / src) if src and not Path(src).is_absolute() else (Path(src) if src else None)
    if music and music.exists():
        base = float(m.get("gain_db", -14))
        duck = base + float(m.get("duck_db", -5))
        start = float(m.get("start", 0.0))
        c += [f"track.new={json.dumps({'kind': 'audio', 'format': 'stereo', 'name': 'Music'})}",
              f"file.import_audio={json.dumps({'path': str(music), 'track': 'Music', 'at': 0, 'new_tracks': False})}",
              f"mix.volume={json.dumps({'tracks': ['Music'], 'db': base})}"]
        pts = [(0.0, base)]
        for a, b in speech_spans(words):
            pts += [(max(0.0, a - 0.15), base), (a + 0.05, duck), (b, duck), (b + 0.35, base)]
        fade = float(m.get("fade_out", 1.5))
        pts += [(max(0.0, dur - fade), base), (dur, -60.0)]
        # 자동화 점의 at 은 초가 아니라 샘플 단위(세션 48 kHz) — 초로 넣으면 모든 점이 맨 앞에 몰린다
        for at, val in pts:
            c.append(f"automation.set_point={json.dumps({'track': 'Music', 'param': 'volume', 'at': int(round(at * RATE)), 'value': round(val, 2)})}")
    # 새 세션에는 마스터 트랙이 없다 → 만들고 리미터(maximizer)를 건다
    c += [f"track.new={json.dumps({'kind': 'master', 'format': 'stereo', 'name': 'Master'})}",
          f"mix.insert={json.dumps({'track': 'Master 1', 'plugin': 'maximizer'})}"]   # 마스터는 이름을 받지 않고 'Master 1' 로 생김
    return c


def mix(sb: dict, dur: float, out_dir: Path | None = None) -> tuple[Path, Path] | None:
    """세션 + 믹스 WAV 를 만든다. SoundCraft 가 없거나 실패하면 None(마무리 단계가 ffmpeg 로 대신 섞음)"""
    sc = cli("soundcraft")
    sid = sb["id"]
    voice = PUBLIC / "audio" / f"{sid}.wav"
    if not sc or not voice.exists():
        return None
    caps_p = PUBLIC / "audio" / f"{sid}.captions.json"
    words = json.loads(caps_p.read_text("utf-8")) if caps_p.exists() else []
    d = out_dir or (ROOT / "compositions" / sid / "craft" / "audio")
    d.mkdir(parents=True, exist_ok=True)
    session, wav = d / f"{sid}.scraft", d / f"{sid}.mix.wav"
    man_p = d.parent / "craft.json"
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    au = man.get("audio") or {}
    if session.exists() and au.get("hash") and _sha(session) != au["hash"]:
        # 사람이 세션을 고쳤다 → 다시 만들지 않고 그 세션으로 바운스만
        args = [str(sc), "run", "--in", str(session), "--bounce", str(wav), "--end", f"{dur:.3f}"]
        au["edited"] = True
    else:
        cmds = commands(sb, voice, words, dur)
        args = [str(sc), "run"] + [x for c in cmds for x in ("--cmd", c)] + ["--bounce", str(wav), "--end", f"{dur:.3f}", "--save", str(session)]
    r = subprocess.run(args, cwd=str(d), text=True, capture_output=True, timeout=600, env={**os.environ, "SOUNDCRAFT_NO_PREFS": "1"})
    if r.returncode != 0 or not wav.exists():
        print(f"[소리] SoundCraft 실패 — ffmpeg 로 대신 섞습니다\n{(r.stdout + r.stderr)[-800:]}")
        return None
    if not au.get("edited"):
        au = {"file": os.path.relpath(session, ROOT), "hash": _sha(session), "app": "soundcraft"}
    man["audio"] = au
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return session, wav


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""
