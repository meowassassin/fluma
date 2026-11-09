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
    vids = {r["id"]: r for r in catalog.models("make.video")}
    assert vids["google/veo-3.1-lite"]["ok"] and not vids["minimax/hailuo-2.3"]["ok"]          # 9:16 못 하는 모델은 고를 수 없게
    assert vids["runway/gen-4.5"]["price_label"].startswith("초당 $0.120")                      # 센트 단위 → 달러
    assert "영상 토큰" in vids["bytedance/seedance-2.5"]["price_label"]
    assert [r["id"] for r in catalog.models("see.video")] == ["google/gemini-4-argon"]           # 영상 입력 되는 것만
    imgs = {r["id"]: r for r in catalog.models("edit.image")}
    assert imgs["bytedance-seed/seedream-5-0-lite"]["ok"] and not imgs["x/square-only"]["ok"]
    assert catalog.models("embed")[0]["free"]


def test_chosen_model_order_and_local_and_no_key(env, monkeypatch):
    assert catalog.chosen("see.video") == "google/gemini-4-argon"                                # VL 은 기본 켬
    assert catalog.chosen("make.video") is None                                                  # 생성은 고르기 전엔 로컬(프롬프트만)
    (env / "settings.json").write_text(json.dumps({"models": {"make.video": "runway/gen-4.5", "see.video": "local"}}))
    assert catalog.chosen("make.video") == "runway/gen-4.5" and catalog.chosen("see.video") is None
    sb = {"direction": {"models": {"make.video": "google/veo-3.1-lite"}}}
    assert catalog.chosen("make.video", sb) == "google/veo-3.1-lite"                             # 영상마다 바꾸기
    monkeypatch.setattr(OR, "key", lambda: "")
    assert catalog.chosen("make.video", sb) is None                                              # 키가 없으면 전부 로컬


def test_video_estimate_and_budget_gate(env):
    assert catalog.estimate_video("google/veo-3.1-lite", 6, "720p", audio=True) == 0.3
    assert catalog.estimate_video("google/veo-3.1-lite", 6, "720p", audio=False) == 0.18
    assert catalog.estimate_video("bytedance/seedance-2.5", 5) is None                           # 토큰 단위 = 예상 불가
    catalog.guard("v1", "make.video", "m", 2.0, "x")                                             # 상한 $3 안
    catalog.record("v1", "make.video", "m", 2.5, "x")
    with pytest.raises(catalog.NeedApproval):
        catalog.guard("v1", "make.video", "m", 1.0, "x")                                         # 2.5 + 1.0 > 3
    with pytest.raises(catalog.NeedApproval):
        catalog.guard("v2", "make.video", "m", None, "x")                                        # 예상 불가는 늘 승인
    catalog.guard("v1", "make.video", "m", 1.0, "x", approve=True)
    assert catalog.spent("v1") == 2.5 and catalog.spent("v2") == 0


def test_request_shapes_follow_official_docs(env, monkeypatch, tmp_path):
    sent = []

    class R:
        ok, status_code, content = True, 200, b"ID3"
        def __init__(self, js): self._js = js
        def json(self): return self._js

    def fake_post(path, body, timeout=0):
        sent.append((path, body))
        if path == "images":
            return R({"data": [{"b64_json": "iVBORw0KGgo=", "media_type": "image/png"}], "usage": {"cost": 0.03}})
        if path == "videos":
            return R({"id": "job1", "status": "pending"})
        return R({"choices": [{"message": {"content": "{}"}}], "usage": {"cost": 0.001}})
    monkeypatch.setattr(OR, "post", fake_post)
    img = tmp_path / "k.png"; img.write_bytes(b"\x89PNG")
    r = OR.make_image("m/img", "a cat", tmp_path / "out", refs=[img])
    assert r["file"].suffix == ".png" and r["cost"] == 0.03
    assert sent[-1][1]["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    OR.video_submit("m/vid", "walk", duration=6, resolution="720p", first_frame=img, audio=False)
    b = sent[-1][1]
    assert b["aspect_ratio"] == "9:16" and b["frame_images"][0]["frame_type"] == "first_frame" and b["generate_audio"] is False
    OR.see("m/vl", "what happens?", videos=["https://www.youtube.com/watch?v=abc"])
    assert sent[-1][1]["messages"][0]["content"][1] == {"type": "video_url", "video_url": {"url": "https://www.youtube.com/watch?v=abc"}}


def test_no_key_never_calls_paid_api(monkeypatch):
    monkeypatch.setattr(OR, "key", lambda: "")
    with pytest.raises(OR.ProviderError):
        OR.post("videos", {})
