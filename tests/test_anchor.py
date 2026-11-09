"""기준점 — 기준 광고 프레임에서 문법을 뽑아 콘티에 적고, 프롬프트 맨 앞에 넣고, 시안을 견준다(가짜 보기 모델)"""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
import anchor  # noqa: E402
import catalog  # noqa: E402
import see  # noqa: E402

RULES = {"summary": "제품 하나, 여백, 정밀한 빛", "background": "seamless white", "palette": ["#F5F5F7"], "light": "soft top light",
         "subject": "one hero object, 30% of frame", "avoid": ["카페 조명"], "avoid_en": ["warm cafe lighting", "busy crowd"],
         "prompt_en": "Seamless light-grey infinity background, one hero object centered with generous negative space, soft diffused top light.",
         "checklist": ["배경이 비어 있나"]}


@pytest.fixture
def world(tmp_path, monkeypatch):
    xr = tmp_path / "data" / "public" / "trends" / "xray" / "AAAAAAAAAAA"
    (xr / "shots").mkdir(parents=True)
    shots = []
    for i in range(6):
        Image.new("RGB", (90, 160), (240, 240, 240)).save(xr / "shots" / f"{i:03d}.jpg")
        shots.append({"i": i, "start": i, "end": i + 1 + (i % 2), "frame": f"trends/xray/AAAAAAAAAAA/shots/{i:03d}.jpg"})
    (xr / "xray.json").write_text(json.dumps({"shots": shots}))
    data = tmp_path / "data"
    (data / "storyboards").mkdir(parents=True, exist_ok=True)
    sb = {"id": "t-anchor", "scenes": [{"sec": 4, "beat": "cup", "materials": [{"id": "g1", "type": "video", "gen": "seedance", "prompt": "a paper cup on a table"}]}],
          "direction": {}}
    sbp = data / "storyboards" / "t-anchor.json"
    sbp.write_text(json.dumps(sb))
    monkeypatch.setattr(anchor, "XRAY", xr.parent)
    monkeypatch.setattr(anchor, "ROOT", tmp_path)
    monkeypatch.setattr(anchor, "_sb_path", lambda sid: sbp)
    calls = []

    def ask(items, q, **k):
        calls.append((list(items), q))
        if "시각 문법" in q and "채점" not in q:
            return {"text": "", "json": RULES, "model": "fake/vl"}
        return {"text": "", "json": {"items": [{"i": 1, "score": 3, "misses": ["따뜻한 카페 조명"], "fix_en": "seamless light-grey background"},
                                              {"i": 2, "score": 8, "misses": []}], "best": 2}, "model": "fake/vl"}
    monkeypatch.setattr(see, "ask", ask)
    monkeypatch.setattr(catalog, "chosen", lambda cap, sb=None: "fake/vl")
    return sbp, calls, tmp_path


def test_set_writes_rules_and_frames(world):
    sbp, calls, tmp = world
    a = anchor.set_anchor("t-anchor", ["AAAAAAAAAAA"], "애플 감성")
    sb = json.loads(sbp.read_text())
    assert sb["direction"]["anchor"]["rules"]["prompt_en"].startswith("Seamless")
    assert a["frames"] and all((tmp / f).exists() for f in a["frames"])          # 기준 프레임이 콘티 폴더에 복사됨(대화창에 띄울 수 있게)
    assert len(calls[0][0]) == len(a["frames"]) and "애플 감성" in calls[0][1]


def test_match_reports_low_scores(world):
    sbp, calls, tmp = world
    anchor.set_anchor("t-anchor", ["AAAAAAAAAAA"], "애플 감성")
    m = anchor.match("t-anchor", ["a.png", "b.png"])
    lines = anchor.report(m)
    assert lines[0].startswith("✓ b.png") and lines[1].startswith("✗ a.png") and "seamless" in lines[1]
    assert calls[-1][0][-2:] == ["a.png", "b.png"]                                # 기준 프레임 뒤에 시안
