"""오픈라우터 공급자 층 — 능력별 모델 목록 · 고른 모델 · 비용 관문 · 그림 시안 → 고르기 → 영상(가짜 오픈라우터, 키 · 돈 없이)"""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import catalog  # noqa: E402
import openrouter as OR  # noqa: E402

RAW = {
    "at": 0,
    "models": [
        {"id": "google/gemini-4-argon", "name": "Argon", "architecture": {"input_modalities": ["text", "image", "video"]}, "pricing": {"prompt": "0.000002"}, "context_length": 1048576},
        {"id": "x/text-only", "name": "T", "architecture": {"input_modalities": ["text"]}, "pricing": {"prompt": "0.000001"}},
    ],
    "images/models": [
        {"id": "bytedance-seed/seedream-5-0-lite", "architecture": {"input_modalities": ["text", "image"]},
         "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1", "9:16"]}, "input_references": {"type": "range", "min": 0, "max": 10}}},
        {"id": "x/square-only", "architecture": {"input_modalities": ["text"]}, "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["1:1"]}}},
    ],
    "videos/models": [
        {"id": "google/veo-3.1-lite", "supported_aspect_ratios": ["16:9", "9:16"], "supported_durations": [4, 6, 8], "supported_resolutions": ["720p", "1080p"],
         "supported_frame_images": ["first_frame", "last_frame"], "generate_audio": True,
         "pricing_skus": {"duration_seconds_with_audio": "0.08", "duration_seconds_without_audio": "0.05", "duration_seconds_with_audio_720p": "0.05", "duration_seconds_without_audio_720p": "0.03"}},
        {"id": "runway/gen-4.5", "supported_aspect_ratios": ["9:16"], "supported_durations": [2, 5, 10], "supported_frame_images": ["first_frame"], "pricing_skus": {"cents_per_second_output": "12"}},
        {"id": "bytedance/seedance-2.5", "supported_aspect_ratios": ["9:16"], "supported_durations": [4, 5, 6], "supported_frame_images": ["first_frame"], "pricing_skus": {"video_tokens": "0.0000107"}},
        {"id": "minimax/hailuo-2.3", "supported_aspect_ratios": ["16:9"], "supported_durations": [6], "pricing_skus": {"duration_seconds": "0.08"}},
    ],
    "models?output_modalities=speech": [{"id": "hexgrad/kokoro-82m", "pricing": {"prompt": "0.00000062", "completion": "0"}}],
    "models?output_modalities=transcription": [],
    "models?output_modalities=audio": [],
    "embeddings/models": [{"id": "nvidia/nemotron-3.5-embed-1b:free", "pricing": {"prompt": "0", "completion": "0"}}],
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    raw = {**RAW, "at": time.time()}
    (tmp_path / "models.json").write_text(json.dumps(raw))
    monkeypatch.setattr(catalog, "CACHE", tmp_path / "models.json")
    monkeypatch.setattr(catalog, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(catalog, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(OR, "key", lambda: "sk-or-test")
    return tmp_path


def test_lists_only_usable_models_per_capability(env):
    assert [r["id"] for r in catalog.models("see.video")] == ["google/gemini-4-argon"]           # 영상 입력 되는 것만
    assert catalog.models("embed")[0]["free"]
    assert "make.video" not in catalog.CAPS and "make.image" not in catalog.CAPS and "edit.image" not in catalog.CAPS   # 생성은 없앴다 — 완전 로컬


def test_chosen_model_order_and_local_and_no_key(env, monkeypatch):
    assert catalog.chosen("see.video") == "google/gemini-4-argon"                                # VL 은 기본 켬
    (env / "settings.json").write_text(json.dumps({"models": {"make.video": "runway/gen-4.5", "see.video": "local"}}))
    assert catalog.chosen("make.video") is None and catalog.chosen("see.video") is None         # 예전 설정이 남아도 생성은 없다
    sb = {"direction": {"models": {"see.video": "google/gemini-4-argon"}}}
    assert catalog.chosen("see.video", sb) == "google/gemini-4-argon"                             # 영상마다 바꾸기
    monkeypatch.setattr(OR, "key", lambda: "")
    assert catalog.chosen("see.video", sb) is None                                                # 키가 없으면 전부 로컬


def test_budget_gate(env):
    catalog.guard("v1", "see.video", "m", 2.0, "x")                                              # 상한 $3 안
    catalog.record("v1", "see.video", "m", 2.5, "x")
    with pytest.raises(catalog.NeedApproval):
        catalog.guard("v1", "see.video", "m", 1.0, "x")                                          # 2.5 + 1.0 > 3
    with pytest.raises(catalog.NeedApproval):
        catalog.guard("v2", "see.video", "m", None, "x")                                         # 예상 불가는 늘 승인
    catalog.guard("v1", "see.video", "m", 1.0, "x", approve=True)
    assert catalog.spent("v1") == 2.5 and catalog.spent("v2") == 0


def test_request_shapes_follow_official_docs(env, monkeypatch, tmp_path):
    sent = []

    class R:
        ok, status_code, content = True, 200, b"ID3"
        def __init__(self, js): self._js = js
        def json(self): return self._js

    def fake_post(path, body, timeout=0):
        sent.append((path, body))
        return R({"choices": [{"message": {"content": "{}"}}], "usage": {"cost": 0.001}})
    monkeypatch.setattr(OR, "post", fake_post)
    OR.see("m/vl", "what happens?", videos=["https://www.youtube.com/watch?v=abc"])
    assert sent[-1][1]["messages"][0]["content"][1] == {"type": "video_url", "video_url": {"url": "https://www.youtube.com/watch?v=abc"}}


def test_no_key_never_calls_paid_api(monkeypatch):
    monkeypatch.setattr(OR, "key", lambda: "")
    with pytest.raises(OR.ProviderError):
        OR.post("chat/completions", {})
