#!/usr/bin/env python3
"""오픈라우터 — 보기 · 만들기 · 말하기를 키 하나로(2026-11-09 공식 문서 기준).

  보기     chat completions 의 image_url · video_url(유튜브 링크 또는 base64 mp4)
  그리기   POST /images (input_references = 참조 · 편집할 그림) → base64
  찍기     POST /videos → 작업 id → GET /videos/{id} 조회 → GET /videos/{id}/content 받기(frame_images = 시작 · 끝 프레임)
  말하기   POST /audio/speech (OpenAI 호환) → 소리 바이트
  듣기     POST /audio/transcriptions (verbose_json = 구간 시각)
  찾기     POST /embeddings

키는 engine/core/apikeys.py(OPENROUTER_API_KEY — 설정 화면이 ~/.shortsforge/ 에 저장). 값은 출력 · 기록하지 않는다.
돈이 드는 호출은 여기서 바로 부르지 않는다 — catalog.py 의 비용 관문(guard 예상 · 승인 → record 장부)을 거친다.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

BASE = "https://openrouter.ai/api/v1"
HEAD = {"HTTP-Referer": "https://github.com/meowassassin/fluma", "X-Title": "Fluma"}


class ProviderError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def key() -> str:
    import apikeys
    return apikeys.get("OPENROUTER_API_KEY")


def has_key() -> bool:
    return bool(key())


def _session():
    import requests
    return requests


def _auth() -> dict:
    k = key()
    if not k:
        raise ProviderError("오픈라우터 키가 없습니다 — 설정 → 모델 에서 넣어 주세요", 401)
    return {"Authorization": f"Bearer {k}", **HEAD}


def _check(r) -> None:
    if r.ok:
        return
    try:
        msg = (r.json().get("error") or {}).get("message") or r.text[:300]
    except ValueError:
        msg = r.text[:300]
    hint = {401: "키가 맞지 않음", 402: "크레딧 부족 — openrouter.ai/credits", 413: "보낸 파일이 너무 큼", 429: "요청이 많음 — 잠시 뒤"}.get(r.status_code, "")
    raise ProviderError(f"오픈라우터 {r.status_code}{' · ' + hint if hint else ''}: {msg}", r.status_code)


def public(path: str, params: dict | None = None, timeout: int = 60) -> dict:
    """키 없이 읽는 공개 목록(/models · /images/models · /videos/models · /embeddings/models)"""
    r = _session().get(f"{BASE}/{path.lstrip('/')}", params=params, headers=HEAD, timeout=timeout)
    _check(r)
    return r.json()


def post(path: str, body: dict, timeout: int = 300):
    r = _session().post(f"{BASE}/{path.lstrip('/')}", headers={**_auth(), "Content-Type": "application/json"}, json=body, timeout=timeout)
    _check(r)
    return r


def get(path: str, timeout: int = 120, stream: bool = False):
    r = _session().get(f"{BASE}/{path.lstrip('/')}", headers=_auth(), timeout=timeout, stream=stream)
    _check(r)
    return r


def data_url(path: Path) -> str:
    mt = mimetypes.guess_type(str(path))[0] or ("video/mp4" if path.suffix.lower() in (".mp4", ".mov") else "image/png")
    return f"data:{mt};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _media(x: str | Path) -> str:
    """주소면 그대로(유튜브 · https), 파일이면 base64 data URL"""
    s = str(x)
    return s if s.startswith(("http://", "https://", "data:")) else data_url(Path(x))


def _cost(js: dict) -> float | None:
    u = js.get("usage") or {}
    c = u.get("cost")
    return float(c) if c is not None else None


# ---------------------------------------------------------------- 보기
def see(model: str, prompt: str, images: list | None = None, videos: list | None = None, system: str | None = None,
        json_mode: bool = False, max_tokens: int | None = None, timeout: int | None = None) -> dict:
    """그림 · 영상을 보고 답하기 → {"text", "cost"}. videos: 유튜브 링크(Gemini AI Studio 는 유튜브만) 또는 mp4 경로"""
    parts = [{"type": "text", "text": prompt}]
    parts += [{"type": "image_url", "image_url": {"url": _media(i)}} for i in images or []]
    parts += [{"type": "video_url", "video_url": {"url": _media(v)}} for v in videos or []]
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": parts}]
    body = {"model": model, "messages": msgs, "usage": {"include": True}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if max_tokens:
        body["max_tokens"] = max_tokens
    # 기다림 상한(FLUMA_SEE_TIMEOUT, 기본 180초) — 무료 모델 대기열에서 몇 분씩 묶이지 않게. 넘으면 오류로 알리고 부르는 쪽이 건너뛴다
    js = post("chat/completions", body, timeout=timeout or int(os.environ.get("FLUMA_SEE_TIMEOUT", "180"))).json()
    ch = (js.get("choices") or [{}])[0]
    txt = (ch.get("message") or {}).get("content") or ""
    if isinstance(txt, list):
        txt = "".join(p.get("text", "") for p in txt if isinstance(p, dict))
    return {"text": txt, "cost": _cost(js), "model": js.get("model") or model}


# ---------------------------------------------------------------- 그리기
def speech(model: str, text: str, out: Path, voice: str | None = None, speed: float | None = None, instructions: str | None = None) -> dict:
    body = {"model": model, "input": text, "response_format": "mp3"}
    if voice:
        body["voice"] = voice
    if speed and abs(speed - 1) > 0.01:
        body["speed"] = speed
    if instructions:
        body["instructions"] = instructions
    r = post("audio/speech", body, timeout=300)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return {"file": out, "cost": None}


def transcribe(model: str, audio: Path, language: str | None = None) -> dict:
    """→ {"text", "segments"[{start,end,text}], "words"?, "cost"}"""
    body = {"model": model, "input_audio": {"data": base64.b64encode(audio.read_bytes()).decode(), "format": audio.suffix.lstrip(".") or "wav"},
            "response_format": "verbose_json", "timestamp_granularities": ["word", "segment"]}
    if language:
        body["language"] = language
    try:
        js = post("audio/transcriptions", body, timeout=600).json()
    except ProviderError as e:                 # 단어 시각을 못 주는 모델 — 구간 시각만 다시
        if e.status != 400:
            raise
        body.pop("timestamp_granularities", None)
        js = post("audio/transcriptions", body, timeout=600).json()
    return {**js, "cost": _cost(js)}


def embed(model: str, texts: list[str]) -> dict:
    js = post("embeddings", {"model": model, "input": texts}, timeout=120).json()
    return {"vectors": [d.get("embedding") for d in js.get("data") or []], "cost": _cost(js)}
