#!/usr/bin/env python3
"""API 키 읽기 — 설정 화면(설정 → 스톡 영상 · 음성)에서 넣은 키를 스크립트가 쓴다.

찾는 순서: 환경 변수 → ~/.shortsforge/api-keys.json(설정 화면이 0600 으로 저장, 에이전트는 못 읽음) → 저장소 루트 .env.local
값은 출력 · 기록하지 않는다. 키 이름:
TYPECAST_API_KEY · ELEVENLABS_API_KEY(음성) ·
PEXELS_API_KEY · PIXABAY_API_KEY(무료 스톡 영상) · YOUTUBE_API_KEY
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import sys
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
KEY_FILE = Path.home() / ".shortsforge" / "api-keys.json"


def get(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    try:
        v = (json.loads(KEY_FILE.read_text(encoding="utf-8")).get(name) or "").strip()
    except (OSError, ValueError):
        v = ""
    if v:
        return v
    try:
        from dotenv import dotenv_values
        return (dotenv_values(ROOT / ".env.local").get(name) or "").strip()
    except ImportError:
        return ""
