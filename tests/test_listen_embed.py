"""듣기(받아쓰기) · 찾기(임베딩)를 기존 코드가 쓰는지 — 가짜 오픈라우터, 키 · 돈 없이"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import catalog  # noqa: E402
import embed  # noqa: E402
import listen  # noqa: E402
import openrouter as OR  # noqa: E402
from test_providers import RAW  # noqa: E402


@pytest.fixture
def world(tmp_path, monkeypatch):
    raw = {**RAW, "at": time.time(), "models?output_modalities=transcription": [{"id": "openai/whisper-large-v3", "pricing": {"prompt": "0.0001"}}]}
    (tmp_path / "models.json").write_text(json.dumps(raw))
    (tmp_path / "settings.json").write_text(json.dumps({"models": {"voice.stt": "openai/whisper-large-v3", "embed": "nvidia/nemotron-3.5-embed-1b:free"}}))
    monkeypatch.setattr(catalog, "CACHE", tmp_path / "models.json")
    monkeypatch.setattr(catalog, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(catalog, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(embed, "CACHE", tmp_path / "emb")
    embed._mem.clear()
    monkeypatch.setattr(OR, "key", lambda: "sk-or-test")
    calls = {"stt": 0, "emb": 0}

    def tr(model, audio, language=None):
        calls["stt"] += 1
        return {"text": "안녕하세요 반갑습니다", "segments": [{"start": 0.0, "end": 1.0, "text": "안녕하세요 반갑습니다"}], "cost": 0.0001}

    def em(model, texts):
        calls["emb"] += len(texts)
        def vec(t):                                    # 뜻이 같은 두 문장을 같은 벡터로(가짜)
            k = "구조" if ("이점" in t or "장점" in t) else t
            return [float(sum(map(ord, k)) % 7 + 1), float(len(k) % 5 + 1), 1.0]
        return {"vectors": [vec(t) for t in texts], "cost": 0}
    monkeypatch.setattr(OR, "transcribe", tr)
    monkeypatch.setattr(OR, "embed", em)
    wav = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1", str(wav)], check=True)
    return calls, wav


def test_listen_none_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(OR, "key", lambda: "")
    assert listen.remote(tmp_path / "x.wav") is None                                 # 키가 없으면 로컬 whisper 로 넘긴다


def test_listen_remote_and_word_split(world):
    calls, wav = world
    segs = listen.remote(wav)
    assert calls["stt"] == 1 and segs[0]["text"] == "안녕하세요 반갑습니다"
    w = segs[0]["words"]
    assert [x["w"] for x in w] == ["안녕하세요", "반갑습니다"] and w[0]["s"] == 0 and w[-1]["e"] == 1.0   # 단어 시각이 없으면 구간을 나눈다


def test_xray_speech_uses_provider(world):
    calls, wav = world
    import shorts_xray
    segs = shorts_xray.speech(wav, "base")
    assert calls["stt"] == 1 and segs[0]["words"]


def test_embed_cache_and_concepts_semantic_overlap(world):
    calls, _ = world
    a, b = "고민 다음 장점 나열 후 할인", "문제를 꺼내고 이점 소개하고 쿠폰"
    assert embed.similar(a, b) == pytest.approx(1.0)
    n = calls["emb"]
    embed.similar(a, b)
    assert calls["emb"] == n                                                          # 같은 문장은 다시 돈 쓰지 않는다
    import concepts
    assert concepts.sim(a, b) < concepts.SIM_FAIL and concepts.same(a, b)            # 글자는 달라도 뜻이 같으면 겹침


def test_catalog_search_adds_semantic_hits(world, monkeypatch):
    import craft_catalog
    rows = [{"app": "effectcraft", "kind": "command", "id": "fx.glow", "label": "Glow", "menu": "Effect", "params": "", "summary": "bright halo"},
            {"app": "effectcraft", "kind": "command", "id": "fx.blur", "label": "Blur", "menu": "Effect", "params": "", "summary": "soften"}]
    monkeypatch.setattr(craft_catalog, "load", lambda app=None: rows)
    monkeypatch.setattr(embed, "search", lambda q, docs, n=15: [(0.9, 0), (0.1, 1)])
    got = [r["id"] for _s, r in craft_catalog.search("번쩍이는 빛 효과")]
    assert got == ["fx.glow"]                                                         # 낱말이 하나도 안 겹쳐도 뜻으로 찾는다


def test_screen_kind_with_multimodal_embedding(world, monkeypatch, tmp_path):
    import vision_tags
    from PIL import Image
    img = tmp_path / "f.png"; Image.new("RGB", (32, 32), (10, 10, 10)).save(img)
    monkeypatch.setattr(embed, "multimodal", lambda: True)
    monkeypatch.setattr(embed, "image_vectors", lambda paths, sid="-": [[1.0, 0.0, 0.0]])
    def vecs(texts, sid="-"):
        return [[1.0, 0.0, 0.0] if "funny meme" in t else [0.0, 1.0, 0.0] for t in texts]
    monkeypatch.setattr(embed, "vectors", vecs)
    r = vision_tags.classify(str(img))
    assert r["kind"] == "짤" and r["top"][0][0] == "짤"                                  # 로컬 CLIP 대신 고른 임베딩 모델로
