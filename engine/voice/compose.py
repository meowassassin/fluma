#!/usr/bin/env python3
"""배경 음악 작곡 — SoundCraft 의 MIDI 클립 · 내장 악기(subtractive_synth · drum_synth) · 이펙트로 영상 길이에 맞춘 곡을 만든다.
음악 라이브러리 없이, 영상마다 템포 · 화음 · 구성을 화면 박자에 맞춰 새로 짓는다(참고 쇼츠 X-ray 의 BPM · 구간을 따른다).

  python3 engine/voice/compose.py <곡 사양.json> [--out data/public/audio/<id>.music.wav]

곡 사양
  { "bpm": 96, "bars": 6, "beats_per_bar": 4,
    "chords": [["A2","C3","E3","G3"], ["F2","A2","C3","E3"], …],      # 마디마다(모자라면 되풀이)
    "parts": [
      {"name": "Pad", "instrument": "subtractive_synth", "params": {"amp_attack": 900, "cutoff": 1800, …},
       "pattern": "chord", "bars": [1, 6], "velocity": 70, "octave": 0,
       "inserts": [{"plugin": "plate_reverb", "params": {"mix": 35, "decay": 4}}], "volume_db": -8, "pan": 0},
      {"name": "Arp", "pattern": "arp", "rate": 8, …},                  # rate = 한 마디에 몇 음(8 = 8분음표)
      {"name": "Drums", "instrument": "drum_synth", "pattern": "beat", "kick": [1,3], "hat": 8, "snare": [], "bars": [4, 5]},
      {"name": "Sub", "pattern": "root", "octave": -1, …} ],
    "end_hold_sec": 1.5 }                                                # 마지막 화음 뒤 꼬리
패턴: chord(마디 내내 화음) · arp(화음 음을 오르내림) · root(근음 한 마디) · beat(드럼 — kick/snare 는 박 번호, hat 은 마디당 수)
결과: <out>.wav · <out>.scraft(편집 가능한 세션 — 사람이 SoundCraft 로 열어 고칠 수 있음) · 콘티 music.src 로 쓴다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.materials import cli  # noqa: E402

TPQ = 960                                            # 4분음표 틱(SoundCraft — 480 으로 계산하면 곡이 두 배 빨라진다)
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
DRUM = {"kick": 36, "snare": 38, "hat": 42, "open_hat": 46}


def midi(n: str) -> int:
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", n)
    if not m:
        raise ValueError(f"음 이름: {n} (예: A2 · C#3 · Bb1)")
    return 12 * (int(m.group(3)) + 1) + NOTE[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]


def notes(spec: dict, part: dict) -> list[tuple[int, int, int, int]]:
    """(pitch, start_tick, length_tick, velocity)"""
    bpb = int(spec.get("beats_per_bar", 4))
    bar = TPQ * bpb
    chords = [[midi(x) for x in c] for c in spec["chords"]]
    a, b = part.get("bars", [1, spec["bars"]])
    vel = int(part.get("velocity", 80))
    oc = 12 * int(part.get("octave", 0))
    out = []
    for k in range(a - 1, b):
        ch = [p + oc for p in chords[k % len(chords)]]
        t0 = k * bar
        pat = part.get("pattern", "chord")
        if pat == "chord":
            ln = bar if k < b - 1 or not spec.get("end_hold_sec") else bar + int(spec["end_hold_sec"] * spec["bpm"] / 60 * TPQ)
            out += [(p, t0, ln - 10, vel) for p in ch]
        elif pat == "root":
            out.append((ch[0], t0, bar - 10, vel))
        elif pat == "arp":
            rate = int(part.get("rate", 8))
            step = bar // rate
            seq = ch + ch[-2:0:-1]                      # 오르내림
            for i in range(rate):
                out.append((seq[i % len(seq)] + (12 if part.get("up") and i % len(seq) == len(ch) - 1 else 0), t0 + i * step, int(step * 0.9), vel - (8 if i % 2 else 0)))
        elif pat == "beat":
            for beat in part.get("kick", [1, 3]):
                out.append((DRUM["kick"], t0 + (beat - 1) * TPQ, TPQ // 2, vel))
            for beat in part.get("snare", []):
                out.append((DRUM["snare"], t0 + (beat - 1) * TPQ, TPQ // 2, vel - 10))
            h = int(part.get("hat", 0))
            for i in range(h):
                out.append((DRUM["hat"], t0 + i * (bar // h), bar // h // 2, vel - 25 - (10 if i % 2 else 0)))
        else:
            raise ValueError(f"모르는 패턴: {pat}")
    return out


def _run(sc: str, args: list[str], cwd: Path) -> str:
    r = subprocess.run([sc, "run", *args], cwd=str(cwd), text=True, capture_output=True, timeout=600, env={**os.environ, "SOUNDCRAFT_NO_PREFS": "1"})
    if r.returncode != 0:
        raise SystemExit(f"SoundCraft 실패: {(r.stderr or r.stdout)[-600:]}")
    return r.stdout


def _x(cmds: list[tuple[str, dict]]) -> list[str]:
    return [x for c, p in cmds for x in ("--cmd", f"{c}={json.dumps(p, ensure_ascii=False)}")]


def compose(spec: dict, out: Path) -> dict:
    sc = str(cli("soundcraft"))
    out.parent.mkdir(parents=True, exist_ok=True)
    sess = out.with_suffix(".scraft")
    bar = TPQ * int(spec.get("beats_per_bar", 4))
    total_ticks = bar * int(spec["bars"])
    # 1) 템포 · 트랙 · 클립(클립 id 를 읽는다)
    c1: list[tuple[str, dict]] = [("event.tempo", {"bpm": spec["bpm"]})]
    for p in spec["parts"]:
        c1.append(("track.new", {"kind": "instrument", "name": p["name"], "instrument": p.get("instrument", "subtractive_synth"),
                                 "format": "stereo", "timebase": "ticks"}))
        a, b = p.get("bars", [1, spec["bars"]])
        tail = int((spec.get("end_hold_sec") or 0) * spec["bpm"] / 60 * TPQ) if b == spec["bars"] else 0
        smp = 48000 * 60 / spec["bpm"] / TPQ           # 클립 위치는 숫자면 샘플(48 kHz) — 틱으로 넣으면 클립이 0.2초로 짧아져 첫 음만 울린다
        c1.append(("midi.new_clip", {"track": p["name"], "start": int((a - 1) * bar * smp), "end": int((b * bar + tail) * smp)}))
    so = _run(sc, _x(c1) + ["--save", str(sess)], out.parent)
    clips = [json.loads(m.group(1))["clip"] for m in re.finditer(r"^midi\.new_clip: (\{.*\})$", so, re.M)]
    if len(clips) != len(spec["parts"]):
        raise SystemExit(f"클립 id 를 다 못 읽었습니다: {clips}")
    # 2) 음표 · 악기 소리 · 이펙트 · 볼륨 → 바운스
    c2: list[tuple[str, dict]] = []
    n_notes = 0
    for p, clip in zip(spec["parts"], clips):
        if p.get("params"):
            c2.append(("mix.instrument", {"track": p["name"], "plugin": p.get("instrument", "subtractive_synth"), "params": p["params"]}))
        for pitch, st, ln, vel in notes(spec, p):
            c2.append(("midi.note_add", {"clip": clip, "pitch": pitch, "start_ticks": st - (p.get("bars", [1])[0] - 1) * bar, "length_ticks": ln,
                                         "velocity": max(1, min(127, vel))}))
            n_notes += 1
        for k, ins in enumerate(p.get("inserts") or []):
            c2.append(("mix.insert", {"track": p["name"], "slot": k, "plugin": ins["plugin"], "params": ins.get("params") or {}}))
        if p.get("volume_db") is not None:
            c2.append(("mix.volume", {"track": p["name"], "db": p["volume_db"]}))
        if p.get("pan"):
            c2.append(("mix.pan", {"track": p["name"], "pan": p["pan"]}))
    sec = total_ticks / TPQ * 60 / spec["bpm"] + float(spec.get("end_hold_sec") or 0)
    f = out.parent / f".{out.stem}.cmds"
    f.write_text("\n".join(f"{c}={json.dumps(p, ensure_ascii=False)}" for c, p in c2), "utf-8")
    args = ["--in", str(sess), "--in-place", "--save", str(sess)]
    # 명령이 많으면 --cmd 줄이 길어진다 → 묶음으로 나눠 같은 세션에 이어 적용
    for i in range(0, len(c2), 300):
        _run(sc, args + _x(c2[i:i + 300]), out.parent)
    so = _run(sc, args + ["--bounce", str(out), "--end", f"{sec:.3f}"], out.parent)
    f.unlink(missing_ok=True)
    m = re.search(r"\{[^{}]*lufs[^{}]*\}", so, re.I)
    return {"wav": str(out.relative_to(ROOT)), "session": str(sess.relative_to(ROOT)), "sec": round(sec, 3), "notes": n_notes,
            "parts": [p["name"] for p in spec["parts"]], "loudness": json.loads(m.group(0)) if m else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out")
    a = ap.parse_args()
    sp = Path(a.spec)
    spec = json.loads(sp.read_text("utf-8"))
    out = Path(a.out) if a.out else ROOT / "data" / "public" / "audio" / f"{sp.stem}.music.wav"
    out = out if out.is_absolute() else ROOT / out
    print(json.dumps(compose(spec, out), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
