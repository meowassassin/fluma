"""세로 확장 — 가로 사진을 9:16 으로, 원본은 가운데 그대로(가짜 그리기 모델)"""
import json
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import catalog  # noqa: E402
import extend  # noqa: E402
import openrouter as OR  # noqa: E402
from test_providers import RAW  # noqa: E402


@pytest.fixture
def world(tmp_path, monkeypatch):
    (tmp_path / "models.json").write_text(json.dumps({**RAW, "at": time.time()}))
    (tmp_path / "settings.json").write_text(json.dumps({"models": {"edit.image": "bytedance-seed/seedream-5-0-lite"}}))
    monkeypatch.setattr(catalog, "CACHE", tmp_path / "models.json")
    monkeypatch.setattr(catalog, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(catalog, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(catalog, "estimate_image", lambda m, n=1: 0.03)
    monkeypatch.setattr(extend, "CACHE", tmp_path / "ext")
    monkeypatch.setattr(OR, "key", lambda: "sk-or-test")
    calls = []

    def make_image(model, prompt, out, aspect="9:16", refs=None, **k):
        calls.append((prompt, refs))
        p = Path(out).with_suffix(".png")
        Image.new("RGB", (720, 1280), (0, 200, 0)).save(p)          # 모델이 가운데까지 다 초록으로 바꿔 버린 경우
        return {"file": p, "cost": 0.03}
    monkeypatch.setattr(OR, "make_image", make_image)
    return calls


def test_landscape_photo_becomes_vertical_with_original_kept(world, tmp_path):
    src = tmp_path / "wide.jpg"
    Image.new("RGB", (1600, 900), (200, 30, 30)).save(src)
    out = extend.vertical(src, tmp_path / "v.jpg", hint="a city street", sid="s1")
    im = Image.open(out)
    assert im.size == (1080, 1920)
    assert abs(im.getpixel((540, 960))[0] - 200) < 12                         # 가운데는 원본(빨강) 그대로
    assert im.getpixel((540, 40))[1] > 150                                     # 위는 이어 그린 부분
    prompt, refs = world[0]
    assert "keep it exactly" in prompt and "a city street" in prompt and refs
    assert catalog.spent("s1") == 0.03
    extend.vertical(src, tmp_path / "v2.jpg", hint="a city street", sid="s1")
    assert len(world) == 1                                                     # 같은 사진은 다시 그리지 않는다


def test_vertical_or_no_model_is_left_alone(world, tmp_path, monkeypatch):
    tall = tmp_path / "tall.jpg"
    Image.new("RGB", (900, 1600)).save(tall)
    assert extend.vertical(tall) is None
    monkeypatch.setattr(OR, "key", lambda: "")
    wide = tmp_path / "w.jpg"
    Image.new("RGB", (1600, 900)).save(wide)
    assert extend.vertical(wide) is None and not world                         # 키가 없으면 지금처럼(띠 + 흐린 배경)
