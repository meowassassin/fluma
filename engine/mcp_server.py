#!/usr/bin/env python3
"""Fluma MCP 서버(stdio) — 레퍼런스 쇼츠 · 채널 분석을 다른 에이전트(Claude Code · Codex · Cursor …)에서 도구로 쓴다.

  python3 engine/mcp_server.py          # MCP 클라이언트 설정: {"command": "<repo>/.venv/bin/python", "args": ["<repo>/engine/mcp_server.py"]}

도구
  analyze_reference(url, videos=5)  쇼츠 분해 → 스타일 카드 → 채널 카드(같은 채널 여러 편). 수 분~십여 분 걸린다
  channel_card(channel_id)          만들어 둔 채널 카드(형식 · 구성 뼈대 · 화면 비율 · 리듬 · 말투 · 목소리)
  style_card(video_id)              만들어 둔 한 편의 스타일 카드
  voice_profile(audio_path)         소리 파일의 목소리 특징(높이 · 억양 폭 · 말끝 · 세기 변화 · 속도)
외부 SDK 없이 JSON-RPC 2.0(MCP 2025-06-18 의 initialize · tools/list · tools/call)만 구현한다. 레퍼런스의 영상 · 대사는
분석 재료일 뿐 결과물에 옮기지 않는다(카드의 '옮기는 법' 참고).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
PY = sys.executable
XR = ROOT / "data" / "public" / "trends" / "xray"
CH = ROOT / "data" / "public" / "trends" / "channels"
VID = re.compile(r"(?:shorts/|v=|youtu\.be/)?([A-Za-z0-9_-]{11})")

TOOLS = [
    {"name": "analyze_reference", "description": "Analyze a reference YouTube Short and several other Shorts from its channel. Returns the channel card (format, structure skeletons, screen-kind ratios, cut rhythm/BPM, tone, voice profile) as Markdown. Slow: minutes.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "YouTube Shorts URL or 11-char id"},
                                                      "videos": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}}, "required": ["url"]}},
    {"name": "channel_card", "description": "Return a previously built channel card (Markdown).",
     "inputSchema": {"type": "object", "properties": {"channel_id": {"type": "string"}}, "required": ["channel_id"]}},
    {"name": "style_card", "description": "Return a previously built single-video style card (Markdown).",
     "inputSchema": {"type": "object", "properties": {"video_id": {"type": "string"}}, "required": ["video_id"]}},
    {"name": "voice_profile", "description": "Measure a voice recording: median pitch, intonation range, phrase-ending drop, loudness variation. JSON.",
     "inputSchema": {"type": "object", "properties": {"audio_path": {"type": "string"}}, "required": ["audio_path"]}},
]


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _card(md: Path, cut: str | None = None) -> str:
    if not md.exists():
        raise ValueError(f"카드가 없습니다: {md.relative_to(ROOT)}")
    t = md.read_text(encoding="utf-8")
    return t.split(cut)[0] if cut and cut in t else t


def call(name: str, a: dict) -> str:
    if name == "analyze_reference":
        m = VID.search(str(a.get("url", "")))
        if not m:
            raise ValueError("YouTube Shorts URL 또는 11자 id 가 필요합니다")
        vid, n = m.group(1), max(1, min(10, int(a.get("videos") or 5)))
        for step in (["engine/research/shorts_xray.py", vid], ["engine/research/ref_style.py", vid], ["engine/research/ref_channel.py", vid, "--n", str(n)]):
            r = _run(step, 3600)
            if r.returncode != 0:
                raise RuntimeError(f"{step[0]} 실패: {(r.stderr or r.stdout).strip()[-400:]}")
        last = json.loads(r.stdout.strip().splitlines()[-1])
        return _card(CH / last["channel"] / "channel.md")
    if name == "channel_card":
        cid = str(a.get("channel_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", cid):
            raise ValueError("channel_id 형식이 올바르지 않습니다")
        return _card(CH / cid / "channel.md")
    if name == "style_card":
        m = VID.search(str(a.get("video_id", "")))
        if not m:
            raise ValueError("video_id 가 필요합니다")
        return _card(XR / m.group(1) / "style" / "style.md")
    if name == "voice_profile":
        p = Path(str(a.get("audio_path", ""))).expanduser()
        if not p.is_file():
            raise ValueError("소리 파일이 없습니다")
        r = _run(["engine/voice/voice_profile.py", str(p)], 300)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-300:])
        return r.stdout.strip()
    raise ValueError(f"모르는 도구: {name}")


def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    msg.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            reply(None, error={"code": -32700, "message": "parse error"}); continue
        mid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if mid is None:          # 알림(notifications/initialized 등)은 답하지 않는다
            continue
        if method == "initialize":
            reply(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                        "serverInfo": {"name": "fluma", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            try:
                text = call(params.get("name", ""), params.get("arguments") or {})
                reply(mid, {"content": [{"type": "text", "text": text}], "isError": False})
            except Exception as e:  # noqa: BLE001 — 도구 오류는 MCP 결과로 돌려준다
                reply(mid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        elif method == "ping":
            reply(mid, {})
        else:
            reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
