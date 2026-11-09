"""보기(VL) — 범용 묻기 · 레퍼런스 이해 · 뻔함 지도 초안 · 순간 찾기 · 초안 비평 (가짜 오픈라우터, 키 · 돈 없이)"""
import json
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import catalog  # noqa: E402
import openrouter as OR  # noqa: E402
import see  # noqa: E402
from test_providers import RAW  # noqa: E402

RID = "zzTestRef01"
SID = "2099-01-02-seetest-01"


@pytest.fixture
def world(tmp_path, monkeypatch):
    (tmp_path / "models.json").write_text(json.dumps({**RAW, "at": time.time()}))
    monkeypatch.setattr(catalog, "CACHE", tmp_path / "models.json")
    monkeypatch.setattr(catalog, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(catalog, "LEDGER", tmp_path / "spend.jsonl")
    monkeypatch.setattr(see, "XRAY", tmp_path / "xray")
    monkeypatch.setattr(OR, "key", lambda: "sk-or-test")
    sent = []

    def fake_see(model, prompt, images=None, videos=None, system=None, json_mode=False, max_tokens=None):
        sent.append({"model": model, "prompt": prompt, "images": images or [], "videos": videos or []})
        if "뻔한 것" in prompt:
            body = {"cliches": [{"kind": "구조", "what": "5위부터 1위로", "seen_in": [RID]}], "gaps": ["1위를 먼저 보여 주기"]}
        elif "순간을 모두 찾아라" in prompt:
            body = {"moments": [{"start": 4.0, "end": 6.0, "why": "고양이가 뛴다", "score": 0.9}]}
        elif "비평하라" in prompt:
            body = {"overall": "o", "issues": [{"t": [7, 9], "scene": 3, "what": "자막 늦음", "why": "w", "fix": "0.3초 앞당김", "severity": "high"}]}
        else:
            body = {"summary": "고양이 반응 모음", "hook": {"t": [0, 2], "device": "사슴과 대치"}}
        return {"text": "```json\n" + json.dumps(body, ensure_ascii=False) + "\n```", "cost": 0.004, "model": model}
    monkeypatch.setattr(OR, "see", fake_see)
    x = tmp_path / "xray" / RID
    x.mkdir(parents=True)
    (x / "xray.json").write_text(json.dumps({"id": RID, "video": {"duration": 20}, "shots": [{"start": 0}, {"start": 2.8}], "speech": [], "text": []}))
    yield sent
    (ROOT / "data" / "storyboards" / f"{SID}.json").unlink(missing_ok=True)
    (ROOT / "data" / "workspace" / "concepts" / f"{SID}.cliches-draft.json").unlink(missing_ok=True)
    shutil.rmtree(ROOT / "data" / "workspace" / "critique" / f"{SID}.json", ignore_errors=True)
    (ROOT / "data" / "workspace" / "critique" / f"{SID}.json").unlink(missing_ok=True)


def test_no_model_without_key(monkeypatch):
    monkeypatch.setattr(OR, "key", lambda: "")
    with pytest.raises(see.NoModel):
        see.model()


def test_ask_anything_youtube_link_for_google_models(world, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(b"\x89PNG")
    r = see.ask([RID, str(img)], "이 영상에서 넘기기 쉬운 순간은?", sid="s1")
    call = world[-1]
    assert call["model"] == "google/gemini-4-argon"                                  # 기본 켬(첫 후보)
    assert call["videos"] == [f"https://www.youtube.com/watch?v={RID}"] and call["images"] == [img]
    assert "넘기기 쉬운" in call["prompt"] and r["cost"] == 0.004
    assert catalog.spent("s1") == 0.004


def test_ref_understanding_is_saved_into_xray_and_reused(world):
    u = see.ref(RID)
    assert u["summary"] == "고양이 반응 모음" and u["_model"]
    assert "컷 시작" in world[-1]["prompt"]                                           # 측정값을 같이 준다
    saved = json.loads((see.XRAY / RID / "xray.json").read_text())
    assert saved["understanding"]["hook"]["device"] == "사슴과 대치"
    n = len(world)
    see.ref(RID)
    assert len(world) == n                                                            # 이미 본 것은 다시 돈 쓰지 않는다


def test_cliches_moments_critique(world):
    see.ref(RID)
    sbp = ROOT / "data" / "storyboards" / f"{SID}.json"
    sbp.parent.mkdir(parents=True, exist_ok=True)
    sbp.write_text(json.dumps({"id": SID, "reference": [RID], "scenes": [{"sec": 3, "beat": "b"}]}))
    d = see.cliches(SID)
    assert d["cliches"][0]["seen_in"] == [RID] and d["gaps"]
    assert see.moments(RID, "고양이가 뛰는 순간", 3.5)[0]["start"] == 4.0
    vid = ROOT / "data" / "out" / f"{SID}-craft-Scenes.mp4"
    vid.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=90x160:d=1", str(vid)], check=True)
    try:
        c = see.critique(SID)
        assert c["issues"][0]["severity"] == "high" and c["_video"].endswith(f"{SID}-craft-Scenes.mp4")
        assert "의도" in world[-1]["prompt"] or "intent" in world[-1]["prompt"]
    finally:
        vid.unlink(missing_ok=True)


def test_budget_gate_applies(world, monkeypatch):
    monkeypatch.setattr(catalog, "cap_usd", lambda: 0.0)
    with pytest.raises(catalog.NeedApproval):
        see.ask([RID], "q", sid="s2")
    see.ask([RID], "q", sid="s2", approve=True)
