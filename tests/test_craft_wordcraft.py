"""WordCraft 어댑터(scripts/craft/adapters/wordcraft.py) — 그림 재기는 앱 없이, 문서 렌더는 앱이 설치됐을 때만."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import wordcraft as wc  # noqa: E402

Image = pytest.importorskip("PIL.Image")
pytest.importorskip("numpy")
app = pytest.mark.skipif(not (ROOT / "tools" / "crafts" / "wordcraft" / "installed.json").exists(), reason="WordCraft 가 설치되지 않음")

TEXT = "① 회원은 구독 시작 후 7일 이내에 환불을 요청할 수 있습니다.\n② 단, 프로모션 요금제는 환불되지 않습니다.\n③ 3영업일 안에 처리합니다."


def test_plugin_registered():
    ad, _ = materials.plugins()
    assert ad["document"] is wc.document
    assert materials.registry().get("document") == "wordcraft"


def test_seams_and_boxes(tmp_path):
    f = tmp_path / "h.png"
    im = Image.new("RGB", (200, 100), "white")
    im.paste((255, 255, 0), (20, 30, 120, 50))
    for x in (50, 80):                                    # 글자 경계 이음선(밝은 섞임)
        im.paste((255, 255, 140), (x, 30, x + 1, 50))
    im.paste((0, 0, 0), (60, 35, 62, 45))                 # 글자 잉크는 그대로
    im.save(f)
    assert wc.seal_seams(f, (255, 255, 0)) == 40
    px = Image.open(f).convert("RGB")
    assert px.getpixel((50, 40)) == (255, 255, 0) and px.getpixel((61, 40)) == (0, 0, 0)
    assert wc.highlight_boxes(f, (255, 255, 0)) == [[20, 30, 100, 20]]
    assert 0.49 < wc.content_bottom(f) < 0.51


def test_bad_fields(tmp_path):
    with pytest.raises(RuntimeError, match="track"):
        wc._pairs([{"to": "x"}])
    with pytest.raises(RuntimeError, match="comments"):
        wc._comments([{"text": "x"}])


@app
def test_document_full(tmp_path):
    info = wc.document({"id": "m1", "type": "document", "title": "이용약관 제7조", "text": TEXT,
                        "highlight": ["프로모션 요금제는 환불되지 않습니다"], "track": {"from": "7일 이내", "to": "14일 이내"}},
                       tmp_path / "m1.png", tmp_path)
    assert info["size"] == [1080, 1920] and info["highlighted"] and info["changes"] >= 2
    assert info["highlight"] and info["font_scale"] > 0 and (tmp_path / "m1.docx").exists()
    info2 = wc.document({"id": "m2", "text": TEXT, "comments": [{"at": "3영업일", "text": "처리 기한"}]}, tmp_path / "m2.png", tmp_path)
    assert info2["size"] == [1080, 1920] and info2["comments"] == 1


@app
def test_document_errors(tmp_path):
    with pytest.raises(RuntimeError, match="찾지 못했습니다"):
        wc.document({"id": "m1", "text": TEXT, "highlight": ["없는 문장"]}, tmp_path / "m1.png", tmp_path)
    with pytest.raises(RuntimeError, match="없습니다"):
        wc.document({"id": "m1", "text": TEXT, "track": {"from": "30일", "to": "x"}}, tmp_path / "m1.png", tmp_path)
