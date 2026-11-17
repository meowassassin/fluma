"""에이전트 런타임 통합(agent_cli · skill_pass · research · fluma_agent)과 리서치/레퍼런스 최적화 회귀 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401


def test_agent_cli_runtime_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import agent_cli

    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"agent": {"cli": "antigravity", "agyModel": "gemini-flash"}}), "utf-8")
    monkeypatch.setattr(agent_cli, "SETTINGS", cfg)
    monkeypatch.delenv("FLUMA_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("FLUMA_SKILL_RUNTIME", raising=False)
    monkeypatch.delenv("FLUMA_AGENT_MODEL", raising=False)

    assert agent_cli.runtime("FLUMA_SKILL_RUNTIME") == ("antigravity", "gemini-flash")

    monkeypatch.setenv("FLUMA_AGENT_RUNTIME", "codex")
    assert agent_cli.runtime("FLUMA_SKILL_RUNTIME") == ("codex", "")

    monkeypatch.setenv("FLUMA_SKILL_RUNTIME", "claude")
    assert agent_cli.runtime("FLUMA_SKILL_RUNTIME") == ("claude", "")


def test_agent_cli_clean_env_and_extract_json(monkeypatch: pytest.MonkeyPatch):
    import agent_cli

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-keep")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("FLUMA_AGENT_RUNTIME", "claude")

    c_env = agent_cli.clean_env("claude")
    assert "ANTHROPIC_API_KEY" not in c_env
    assert c_env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-keep"
    assert "FLUMA_AGENT_RUNTIME" not in c_env

    x_env = agent_cli.clean_env("codex")
    assert "OPENAI_API_KEY" not in x_env

    assert agent_cli.extract_json('설명...\n```json\n{"a": [1, 2]}\n```\n끝') == {"a": [1, 2]}


def test_skill_pass_and_research_respect_configured_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import agent_cli
    import research
    import skill_pass

    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"agent": {"cli": "antigravity"}}), "utf-8")
    monkeypatch.setattr(agent_cli, "SETTINGS", cfg)
    monkeypatch.delenv("FLUMA_AGENT_RUNTIME", raising=False)
    monkeypatch.delenv("FLUMA_SKILL_RUNTIME", raising=False)
    monkeypatch.delenv("FLUMA_RESEARCH_RUNTIME", raising=False)
    monkeypatch.setattr(research, "LLM_CMD", "")

    ok_agy = MagicMock(returncode=0, stdout=json.dumps({"response": '{"changed": ["ok"]}'}), stderr="")
    with patch("subprocess.run", return_value=ok_agy) as sp:
        res, cost = skill_pass.claude("SYS", "PRM", tools="Read", dirs=[str(ROOT)])
        assert res == {"changed": ["ok"]}
        assert cost == 0.0
        cmd = sp.call_args[0][0]
        assert Path(cmd[0]).name.startswith("agy")
        assert "--sandbox" in cmd

    with patch("subprocess.run", return_value=ok_agy) as sp2:
        txt = research.llm("Docker multi-stage build facts")
        assert json.loads(txt) == {"changed": ["ok"]}
        cmd2 = sp2.call_args[0][0]
        assert Path(cmd2[0]).name.startswith("agy")
        assert "search_web(*)" in cmd2[cmd2.index("--settings") + 1]


def test_fluma_agent_logged_in_detects_antigravity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import fluma_agent

    fake_home = tmp_path / "home"
    (fake_home / ".gemini" / "antigravity-cli").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(fluma_agent.shutil, "which", lambda _name: None)
    assert fluma_agent.logged_in() is True


def test_shorts_xray_download_fast_remux_when_h264_aac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import shorts_xray as sx

    dl_file = tmp_path / "dl.mp4"
    dl_file.write_bytes(b"0" * 20_000)

    monkeypatch.setattr(sx, "probe", lambda _p: {"duration": 35.0, "w": 540, "h": 960, "fps": 30.0, "audio": True, "vcodec": "h264", "acodec": "aac"})
    calls = []

    def fake_run(cmd, **_kw):
        calls.append(cmd)
        if cmd and Path(cmd[0]).name.startswith("yt-dlp"):
            return MagicMock(returncode=0, stdout="", stderr="")
        if cmd and cmd[0] == "ffmpeg":
            (tmp_path / "src.mp4").write_bytes(b"1" * 20_000)
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        dst = sx.download("abcdefghijk", tmp_path)

    assert dst.exists()
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    assert "-c" in ffmpeg_cmd and "copy" in ffmpeg_cmd
    assert "libx264" not in ffmpeg_cmd


def test_shorts_xray_speech_slices_lang_detect_and_avoids_duplicate_audio_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import shorts_xray as sx

    src = tmp_path / "src.mp4"
    src.write_bytes(b"x")
    pcm = np.zeros((16000 * 60, 2), dtype=np.float32)

    load_calls = []
    transcribe_calls = []

    class FakeModel:
        def __init__(self, *_a, **_kw):
            pass

        def transcribe(self, arr, **kw):
            transcribe_calls.append((len(arr), kw))
            if kw.get("without_timestamps"):
                return [], type("Info", (), {"language": "ko"})()
            return [type("Seg", (), {"start": 0.0, "end": 1.0, "text": "안녕", "words": []})()], type("Info", (), {"language": "ko"})()

    monkeypatch.setattr(sx, "load_audio", lambda p, sr=16000: (load_calls.append(p), pcm)[1])
    fake_fw = type("FakeFW", (), {"WhisperModel": FakeModel})()
    with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
        segs = sx.speech(src, "small", lang_from=src)

    assert len(load_calls) == 1  # same_src 일 때는 오디오 디코드를 한 번만 수행
    assert transcribe_calls[0][0] == 16000 * 25  # 언어 판정은 앞 25초만
    assert transcribe_calls[1][0] == 16000 * 60  # 전체 받아쓰기는 1회만
    assert segs and segs[0]["text"] == "안녕"


def test_ref_channel_reuses_cached_xray_and_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ref_channel as rc

    xr = tmp_path / "xray"
    vid_dir = xr / "testvid0001"
    (vid_dir / "style").mkdir(parents=True)
    (vid_dir / "src.mp4").write_bytes(b"mp4")
    (vid_dir / "xray.json").write_text(json.dumps({
        "video": {"duration": 10.0},
        "shots": [{"start": 0.0, "end": 5.0}, {"start": 5.0, "end": 10.0}],
        "speech": [{"start": 0.5, "end": 2.5, "text": "테스트 문장.", "words": [{"w": "테스트", "s": 0.5, "e": 1.5}, {"w": "문장.", "s": 1.5, "e": 2.5}]}],
        "sound": {"bpm": 120.0, "beats": [0.0, 5.0]},
    }), "utf-8")
    (vid_dir / "style" / "scan.json").write_text(json.dumps({
        "words": ["Docker"],
        "kinds": [[0.5, "실제 화면"], [5.5, "도표"]],
        "frames": [{"t": 0.5, "lines": [], "band": [0.0, 1.0, "#000000"]}],
    }), "utf-8")

    monkeypatch.setattr(rc, "XR", xr)
    import voice_profile as vp
    monkeypatch.setattr(vp, "profile", lambda *_a, **_kw: {"f0_median": 140.0})

    out = rc.analyze_video("testvid0001", "테스트", tmp_path / "work", "small", ["korean", "en"], 1.0)
    assert out["id"] == "testvid0001"
    assert out["cuts"] == 1
    assert out["bpm"] == 120.0
    assert len(out["sentences"]) == 1


def test_trends_search_parallel_sources_and_thumbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import trends

    monkeypatch.setattr(trends, "PUBLIC", tmp_path)
    monkeypatch.setattr(trends, "save", lambda _d: None)
    monkeypatch.setattr(trends, "classify", lambda _paths: {})
    monkeypatch.setattr(trends, "search", lambda q, _n: [{"id": f"{q}000000000"[:11], "title": f"{q} title", "views": 1000, "short": True}])
    monkeypatch.setattr(trends, "hashtag", lambda t, _n: [{"id": f"{t}111111111"[:11], "title": f"#{t} title", "views": 2000, "short": True}])
    monkeypatch.setattr(trends, "thumb", lambda vid: f"trends/thumbs/{vid}.jpg")

    a = type("Args", (), {"want": "any", "label": "it", "request": "", "category": "tech", "limit": 5, "channel": ""})()
    d = {"items": [], "requests": []}
    req = {"id": "r1", "label": "it", "category": "tech", "tags": ["t1"], "queries": ["q1"], "count": 0}
    trends._search_into(a, d, req, ["q1"], ["t1"])
    assert req["count"] == 2
    assert len(d["items"]) == 2
