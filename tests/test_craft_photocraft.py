"""PhotoCraft 어댑터(engine/craft/adapters/photocraft.py) — 계산은 앱 없이, 실제 그리기는 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import materials  # noqa: E402
from craft.adapters import photocraft as pc  # noqa: E402

Image = pytest.importorskip("PIL.Image")
HAS_APP = (ROOT / "tools" / "crafts" / "photocraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="PhotoCraft 가 설치되지 않음")


# ---------------------------------------------------------------- 앱 없이
def test_plugin_overrides_builtin_photo():
    ad, _ = materials.plugins()
    assert ad["photo"] is pc.photo


def test_box_accepts_ratio_or_pixels():
    assert pc._box([0.5, 0.25, 0.5, 0.5], 200, 100) == (100, 25, 100, 50)
    assert pc._box([10, 20, 30, 40], 200, 100) == (10, 20, 30, 40)
    with pytest.raises(RuntimeError):
        pc._box([1, 2, 3], 10, 10)


def test_title_wraps_evenly():
    assert pc._wrap("기자회견에서 고개 숙인 교육위원회 관계자들", 11.2) == ["기자회견에서 고개 숙인", "교육위원회 관계자들"]
    assert pc._wrap("짧은 제목", 11.2) == ["짧은 제목"]
    assert pc._wrap("첫 줄\n둘째 줄", 3) == ["첫 줄", "둘째 줄"]


def test_round_rect_path_is_closed_with_8_knots():
    p = pc._round_rect(0, 0, 100, 50, 10)["subpaths"][0]
    assert p["closed"] and len(p["knots"]) == 8
    xs = [k["anchor"][0] for k in p["knots"]]
    assert min(xs) == 0 and max(xs) == 100


# ---------------------------------------------------------------- 앱으로
def _capture(f: Path) -> Path:
    """흰 배경 캡처 흉내: 위에 빨간 로고, 가운데 검은 글자 줄, 아래 회색 사진 칸"""
    from PIL import ImageDraw
    im = Image.new("RGB", (400, 600), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 120, 60), fill=(220, 30, 40))
    for y in (250, 290):
        d.rectangle((30, y, 370, y + 20), fill=(20, 20, 20))
    d.rectangle((0, 380, 400, 600), fill=(120, 140, 160))
    im.save(f)
    return f


@app
def test_plain_photo_runs_with_positional_input(tmp_path):
    src = _capture(tmp_path / "cap.jpg")
    out = tmp_path / "m1.png"
    info = pc.photo({"id": "m1", "type": "photo", "src": str(src)}, out, tmp_path)
    assert info["app"] == "photocraft" and info["size"] == [400, 600]
    assert Image.open(out).size == (400, 600)


@app
def test_clean_removes_logo(tmp_path):
    src = _capture(tmp_path / "cap.png")
    out = tmp_path / "m2.png"
    pc.photo({"id": "m2", "type": "photo", "src": str(src), "clean": [[15, 15, 110, 50]]}, out, tmp_path)
    r, g, b = Image.open(out).convert("RGB").getpixel((70, 40))
    assert r > 180 and g > 180 and b > 180          # 빨간 로고 자리가 흰 배경으로


@app
def test_alpha_text_makes_white_transparent_and_trims(tmp_path):
    from PIL import ImageDraw
    src = tmp_path / "t.png"
    im = Image.new("RGB", (300, 80), "white")
    ImageDraw.Draw(im).rectangle((40, 30, 260, 50), fill="black")
    im.save(src)
    out = tmp_path / "m3.png"
    info = pc.photo({"id": "m3", "type": "photo", "src": str(src), "alpha_text": True}, out, tmp_path)
    a = Image.open(out).convert("RGBA")
    assert info["alpha_text"] and a.size[0] < 300 and a.size[1] < 80     # 빈 곳이 잘렸다
    assert a.getpixel((a.width // 2, a.height // 2))[3] > 200


@app
def test_card_has_size_psd_and_highlight(tmp_path, monkeypatch):
    monkeypatch.delenv("FLUMA_ASPECT", raising=False)
    src = _capture(tmp_path / "cap.png")
    out = tmp_path / "m4.png"
    m = {"id": "m4", "type": "photo", "src": str(src), "frame": "card", "title": "로고를 지운 캡처 카드", "highlight": [0.05, 0.4, 0.9, 0.12]}
    info = pc.photo(m, out, tmp_path)
    assert Image.open(out).size == (1080, 1920) and info["size"] == [1080, 1920]
    assert (tmp_path / "m4.psd").exists() and info["editable_hash"]
    x, y, w, h = info["highlight_box"]
    px = Image.open(out).convert("RGB").getpixel((int((x + w / 2) * 1080), int(y * 1920)))
    assert px[0] > 200 and px[1] > 170 and px[2] < 90          # 노란 강조 상자 윗변
    bx, by, bw, bh = info["photo_box"]
    assert 0 < bx and bx + bw < 1 and by > 0.1 and by + bh < 0.81
    # 16:9 도 같은 칸으로
    info2 = pc.photo({**m, "id": "m5", "aspect": "16:9"}, tmp_path / "m5.png", tmp_path)
    assert Image.open(tmp_path / "m5.png").size == (1920, 1080) and info2["size"] == [1920, 1080]


@app
def test_card_keeps_hand_edited_psd(tmp_path):
    src = _capture(tmp_path / "cap.png")
    out = tmp_path / "m6.png"
    m = {"id": "m6", "type": "photo", "src": str(src), "frame": "card"}
    info = pc.photo(m, out, tmp_path)
    out.with_suffix(".json").write_text(json.dumps(info), "utf-8")
    # 사람이 PSD 를 고친 것처럼(다른 문서로 덮어씀) → 다시 짜지 않고 그 PSD 를 쓴다
    P = materials.cli("photocraft")
    materials._run([P, "run", "--new", json.dumps({"width": 1080, "height": 1920, "background": "#ff0000"}), "--out", tmp_path / "m6.psd"], tmp_path)
    info2 = pc.photo(m, out, tmp_path)
    assert info2.get("edited_by_hand") and Image.open(out).convert("RGB").getpixel((5, 5)) == (255, 0, 0)


@app
def test_build_uses_plugin_photo(tmp_path, monkeypatch):
    """materials.build 가 어댑터를 거쳐 기록(info)을 남기는지 — 저장소 대신 임시 폴더에서"""
    P = materials.cli("photocraft")              # 앱 경로는 진짜 저장소에서
    monkeypatch.setattr(materials, "ROOT", tmp_path)
    monkeypatch.setattr(materials, "cli", lambda app: P)
    monkeypatch.setattr(materials, "read_text_boxes", lambda f: [])
    src = _capture(tmp_path / "cap.png")
    sb = {"id": "pc_test", "scenes": [{"materials": [{"id": "m1", "type": "photo", "src": str(src), "frame": "card", "title": "카드"}]}]}
    (tmp_path / "data" / "storyboards").mkdir(parents=True)
    (tmp_path / "data" / "storyboards" / "pc_test.json").write_text(json.dumps(sb), "utf-8")
    recs = materials.build(sb)
    assert recs[0]["app"] == "photocraft" and recs[0]["frame"] == "card"
    assert (tmp_path / recs[0]["file"]).exists()
