"""SoundCraft 소리 단계(scripts/craft/audio.py) — 명령 만들기는 앱 없이, 실제 믹스 · 라우드니스는 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import audio  # noqa: E402

HAS_APP = (ROOT / "tools" / "crafts" / "soundcraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="SoundCraft 가 설치되지 않음")

WORDS = [{"text": " 안녕", "startMs": 200, "endMs": 900}, {"text": " 하세요", "startMs": 950, "endMs": 1600},
         {"text": " 다음", "startMs": 3000, "endMs": 3600}]


def _wav(p: Path, sec: float, bursts: list[tuple[float, float]] = (), amp: float = 0.25, rate: int = 24000, freq: float = 300.0):
    """말처럼 끊기는 사인 묶음(배음 몇 개) — 들리는 구간만 bursts"""
    n = int(sec * rate)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        fr = bytearray()
        for i in range(n):
            t = i / rate
            on = any(a <= t < b for a, b in bursts)
            v = amp * sum(math.sin(2 * math.pi * freq * k * t) / k for k in (1, 2, 3, 5)) * 0.5 if on else 0.0
            fr += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
        w.writeframes(bytes(fr))


@pytest.fixture
def pub(tmp_path, monkeypatch):
    """가짜 public/audio · assets/sfx — 저장소 파일은 건드리지 않는다"""
    pa = tmp_path / "public" / "audio"
    pa.mkdir(parents=True)
    sfx = tmp_path / "sfx"
    sfx.mkdir()
    _wav(sfx / "pop.wav", 0.1, [(0, 0.1)], amp=0.6, freq=900)
    monkeypatch.setattr(audio, "PUBLIC", tmp_path / "public")
    monkeypatch.setattr(audio, "SFX_DIR", sfx)
    return pa


def _params(cmds, cid):
    return [json.loads(c.split("=", 1)[1]) for c in cmds if c.startswith(cid + "=")]


# ---------------------------------------------------------------- 앱 없이
def test_voice_chain_sfx_clips_and_master(pub):
    _wav(pub / "x.wav", 4, [(0.2, 1.6)])
    _wav(pub / "x.voice.wav", 4, [(0.2, 1.6)])
    _wav(pub / "x.sfx.wav", 4)
    (pub / "x.sfx.json").write_text(json.dumps([{"scene": 0, "name": "pop", "at": 0.2}, {"scene": 1, "name": "pop", "at": 2.75}]))
    cmds = audio.commands({"id": "x"}, pub / "x.wav", WORDS, 4.0)
    ins = _params(cmds, "mix.insert")
    assert [i["plugin"] for i in ins if i["track"] == "Voice"] == ["eq_7band", "compressor", "de_esser"]
    eq = ins[0]["params"]
    assert eq["hpf_on"] == 1 and eq["hpf_freq"] == 90 and eq["high_mid_freq"] == 3500 and 0 < eq["high_mid_gain"] <= 3
    imp = [p for p in _params(cmds, "file.import_audio") if p["track"] == "SFX"]
    assert [p["at"] for p in imp] == [{"seconds": 0.2}, {"seconds": 2.75}]          # 효과음마다 클립 하나, 그 시각에
    assert all(p["path"].endswith("pop.wav") for p in imp)
    assert _params(cmds, "mix.volume")[0] == {"tracks": ["SFX"], "db": audio.sfx_gain_db()}
    mx = [i for i in ins if i["track"] == "Master 1"][0]
    assert mx["plugin"] == "maximizer" and mx["params"]["ceiling"] == audio.CEILING_DB


def test_missing_sfx_file_falls_back_to_mixed_track(pub):
    _wav(pub / "x.wav", 2, [(0.2, 1.0)])
    _wav(pub / "x.voice.wav", 2, [(0.2, 1.0)])
    _wav(pub / "x.sfx.wav", 2, [(0.5, 0.6)])
    (pub / "x.sfx.json").write_text(json.dumps([{"name": "없는소리", "at": 0.5}]))
    imp = [p for p in _params(audio.commands({"id": "x"}, pub / "x.wav", [], 2.0), "file.import_audio") if p["track"] == "SFX"]
    assert len(imp) == 1 and imp[0]["path"].endswith("x.sfx.wav")


def test_music_ducking_uses_write_range_with_ramps_in_samples(pub):
    pts = audio.duck_points(WORDS, -14.0, -19.0, 5.0)
    wr = _params(pts, "automation.write_range")
    assert wr[0] == {"track": "Music", "param": "volume", "start": 0, "end": 5 * audio.RATE, "value": -14.0}
    assert len(wr) == 3 and all(w["value"] == -19.0 for w in wr[1:])            # 말 구간 2개(0.2~1.6 · 3.0~3.6)
    sp = _params(pts, "automation.set_point")
    assert all(isinstance(p["at"], int) for p in sp)                            # 초가 아니라 샘플
    assert {"track": "Music", "param": "volume", "at": int(0.25 * audio.RATE), "value": -19.0} in sp
    assert {"track": "Music", "param": "volume", "at": int(round(1.95 * audio.RATE)), "value": -14.0} in sp


def test_music_end_is_trimmed_and_s_curve_faded():
    c = audio.finish_commands({"music": {"fade_out": 2}}, {"clip": 11, "frames": 40 * audio.RATE}, 30.0)
    assert _params(c, "edit.trim_clip") == [{"clip": 11, "end": 30 * audio.RATE}]
    out = [f for f in _params(c, "edit.fades_create") if f["side"] == "out"][0]
    assert out == {"clip": 11, "side": "out", "length": 2 * audio.RATE, "shape": "s-curve"}
    assert c[-1].startswith("session.audio_health=")                            # 바운스 전에 자체 검사
    assert not _params(audio.finish_commands({}, {"clip": 3, "frames": 10 * audio.RATE}, 30.0), "edit.trim_clip")


def test_master_gain_goes_to_threshold_or_fader():
    up = _params(audio.master_commands(5.0), "mix.insert_params")[0]["params"]
    assert up == {"threshold": -5.0, "ceiling": audio.CEILING_DB}
    down = audio.master_commands(-3.0)
    assert _params(down, "mix.insert_params")[0]["params"]["threshold"] == 0.0
    assert _params(down, "mix.volume")[0] == {"tracks": ["Master 1"], "db": -3.0}
    assert _params(audio.master_commands(99), "mix.insert_params")[0]["params"]["threshold"] == -audio.MAX_GAIN


def test_parse_run_output():
    out = ('track.new: {"tracks":[1]}\n'
           'file.import_audio: {"imported":[{"channels":2,"clip":11,"frames":1920000,"source":10,"track":9}]}\n'
           'session.audio_health: {"healthy":false,"issue_count":1,"issues":[{"clip":11,"problem":"missing"}]}\n'
           '{"bytes":8,"lufs":-12.5,"path":"m.wav","peak_db":-1.5,"seconds":30.0,"true_peak_db":-1.2}\n'
           '{"audio_files_written":3,"path":"s.scraft"}\n')
    res, b = audio.parse_run(out)
    assert [r[0] for r in res] == ["track.new", "file.import_audio", "session.audio_health"]
    assert b["lufs"] == -12.5 and b["true_peak_db"] == -1.2
    cmds = ['track.new={"name":"Music"}', 'file.import_audio={"track":"Music","path":"/m.wav"}', "session.audio_health={}"]
    assert audio.find_music_clip(cmds, res)["clip"] == 11
    assert audio.health_report(res) == ['{"clip": 11, "problem": "missing"}']


# ---------------------------------------------------------------- 앱으로
def _ebur(wav: Path) -> float | None:
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return None
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(wav), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    lines = [l for l in r.stderr.splitlines() if l.strip().startswith("I:")]
    return float(lines[-1].split()[1]) if lines else None


@app
def test_mix_hits_target_loudness_and_records_it(pub, tmp_path):
    bursts = [(0.2 + i * 0.9, 0.2 + i * 0.9 + 0.7) for i in range(9)]
    _wav(pub / "q.wav", 9, bursts, amp=0.05)                                    # 조용한 녹음(약 −30 LUFS)
    _wav(pub / "q.voice.wav", 9, bursts, amp=0.05)
    _wav(pub / "q.sfx.wav", 9)
    (pub / "q.sfx.json").write_text(json.dumps([{"name": "pop", "at": 1.0}]))
    words = [{"text": " 말", "startMs": int(a * 1000), "endMs": int(b * 1000)} for a, b in bursts]
    (pub / "q.captions.json").write_text(json.dumps(words))
    music = tmp_path / "music.wav"
    _wav(music, 12, [(0, 12)], amp=0.08, rate=48000, freq=110)
    sb = {"id": "q", "music": {"src": str(music), "gain_db": -18, "duck_db": -6}}
    out = tmp_path / "craft" / "audio"
    session, wav = audio.mix(sb, 9.0, out_dir=out)
    rec = json.loads((tmp_path / "craft" / "craft.json").read_text())["audio"]
    assert abs(rec["lufs"] - audio.TARGET_LUFS) <= 1.0 and rec["true_peak_db"] <= -1.0
    measured = _ebur(wav)
    if measured is not None:
        assert abs(measured - rec["lufs"]) <= 0.5                               # 기록값 = 실제 파일
    # 사람이 세션을 고치면(해시 다름) 다시 짓지 않고 바운스만
    import os
    import subprocess
    subprocess.run([str(audio.cli("soundcraft")), "run", "--in", str(session), "--in-place", "--save", str(session),
                    "--cmd", 'mix.volume={"tracks":["Music"],"db":-30}'], check=True, capture_output=True, cwd=str(out),
                   env={**os.environ, "SOUNDCRAFT_NO_PREFS": "1"})
    assert audio.mix(sb, 9.0, out_dir=out)
    rec2 = json.loads((tmp_path / "craft" / "craft.json").read_text())["audio"]
    assert rec2.get("edited") is True and "lufs" in rec2 and rec2["hash"] == rec["hash"]
