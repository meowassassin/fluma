"""PdfCraft 어댑터(scripts/craft/adapters/pdfcraft.py) — 계산은 앱 없이, 실제 형광펜 · 자르기는 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import pdfcraft as pc  # noqa: E402

HAS_APP = (ROOT / "tools" / "crafts" / "pdfcraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="PdfCraft 가 설치되지 않음")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


# ---------------------------------------------------------------- 앱 없이
def test_plugin_overrides_builtin_doc_quote():
    ad, _ = materials.plugins()
    assert ad["doc_quote"] is pc.doc_quote


def test_sentence_split_across_lines_is_found_per_line():
    lines = [{"text": "그러나 이", "rect": [0, 0, 100, 10]}, {"text": "용자의 43.7%는 검증하지 않았다.", "rect": [0, 12, 200, 22]}]
    assert pc._span_lines(lines, "이용자의 43.7%는") == [(0, 4, 5), (1, 0, 10)]
    # 영어: 진짜 하이픈은 그대로, 낱말 나눔 하이픈은 지우고 잇는다
    en = [{"text": "the WMT 2014 English-", "rect": [0, 0, 1, 1]}, {"text": "to-German task", "rect": [0, 2, 1, 3]}]
    assert pc._span_lines(en, "English-to-German") == [(0, 13, 21), (1, 0, 9)]
    hy = [{"text": "the trans-", "rect": [0, 0, 1, 1]}, {"text": "former model", "rect": [0, 2, 1, 3]}]
    assert pc._span_lines(hy, "transformer model") == [(0, 4, 9), (1, 0, 12)]
    assert pc._span_lines(lines, "없는 문장") is None


def test_slice_rect_uses_char_widths():
    r = pc._slice_rect({"text": "가나다라", "rect": [0, 0, 400, 10]}, 1, 3)
    assert r == [100, 0, 300, 10]


def test_crop_keeps_context_lines_whole():
    rows = [{"text": f"줄{k}", "rect": [50, 100 + 20 * k, 500, 112 + 20 * k]} for k in range(10)]
    c = pc._crop([[200, 180, 300, 192]], rows, (600, 800), 1)     # 4번째 줄 + 위아래 한 줄
    assert c[1] > 152 and c[1] < 160          # 3번째 줄 위(160)와 2번째 줄 아래(152) 사이
    assert c[3] > 212 and c[3] < 220
    assert c[0] < 50 and c[2] > 500


def test_outline_and_box_padding():
    assert pc._outline([[0, 0, 10, 10]], 2, 1) == []
    # 첫 줄 시작이 끝 줄 끝보다 오른쪽이면 하나로 못 감싼다
    assert pc._outline([[90, 0, 100, 10], [0, 12, 20, 22]], 2, 1) == []
    pts = pc._outline([[40, 0, 100, 10], [0, 12, 60, 22]], 2, 1)
    assert len(pts) == 8 and pts[0] == [38, -1]
    lines = [{"text": "위", "rect": [0, -6, 100, -2]}, {"text": "글", "rect": [0, 0, 100, 10]}]
    assert pc._vpad([[0, 0, 100, 10]], lines, 4, 1) == 0.6             # 틈 2pt → 최소 여백


def test_redact_regex_and_names():
    names, words = pc._redact_words(["문의 kim@ex.go.kr · 010-1234-5678 · 2026년"], ["email", "phone", "credit-card", "김\\w+"])
    assert names == ["credit-card"]
    assert "kim@ex.go.kr" in words and "010-1234-5678" in words and "2026" not in " ".join(words)
    with pytest.raises(RuntimeError):
        pc._redact_words(["x"], ["("])


# ---------------------------------------------------------------- 앱으로
def _en_pdf(d: Path) -> Path:
    txt = d / "en.txt"
    txt.write_text("Results\n\nThe model reaches 28.4 BLEU on the test set while\ntraining in only three days on eight GPUs.\n"
                   "Contact: jane.doe@example.com\n", "utf-8")
    steps = [{"tool": "doc_create", "args": {"from": "text", "path": txt.name}}, {"tool": "doc_save", "args": {"doc": 1, "path": "en.pdf"}}]
    (d / "mk.json").write_text(json.dumps(steps), "utf-8")
    materials._run([materials.cli("pdfcraft"), "run", "--script", d / "mk.json", "--root", d], d)
    return d / "en.pdf"


@app
def test_doc_quote_english_highlight_crop_redact(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    pdf = _en_pdf(tmp_path)
    before = pdf.read_bytes()
    work = tmp_path / "s01"
    work.mkdir()
    m = {"id": "m1", "type": "doc_quote", "pdf": str(pdf), "find": "while training in only three days", "mark": "both", "redact": ["email"]}
    info = pc.doc_quote(m, work / "m1.png", work)
    assert info["highlighted"] is True and info["app"] == "pdfcraft" and info["page"] == 1
    assert len(info["highlight"]) == 2                       # 두 줄에 걸친 문장
    assert info["redacted"] >= 1
    assert pdf.read_bytes() == before                         # 원본은 그대로
    with Image.open(work / "m1.png") as im:
        assert abs(im.size[0] - 1080) <= 2
        x, y, w, h = info["highlight"][0]
        px = im.convert("RGB").getpixel((int(x + w / 2), int(y + 1)))
        assert px[2] < 120 and px[0] > 180                    # 노란 형광펜
    assert (work / "m1.marked.pdf").exists() and info["editable"].endswith("m1.marked.pdf")
    text = materials._run([materials.cli("pdfcraft"), "text", work / "m1.marked.pdf", "--page", "1"], work)
    assert "jane.doe" not in text and "28.4 BLEU" in text


@app
@pytest.mark.skipif(not CHROME, reason="한국어 PDF 를 만들 크롬이 없음")
def test_doc_quote_korean_line_break(tmp_path):
    html = tmp_path / "ko.html"
    html.write_text("<!doctype html><meta charset=utf-8><body style='font-family:Noto Sans CJK KR;font-size:11pt;width:300pt'>"
                    "<p>응답자의 58.4%가 최근 한 달 안에 생성형 AI를 사용했다고 답했다. 그러나 이용자의 43.7%는 AI가 제시한 정보를 "
                    "별도로 검증하지 않고 그대로 사용한 경험이 있다고 응답했다.</p></body>", "utf-8")
    pdf = tmp_path / "ko.pdf"
    subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", html.as_uri()], capture_output=True, timeout=120)
    if not pdf.exists():
        pytest.skip("크롬이 PDF 를 만들지 못함")
    work = tmp_path / "s01"
    work.mkdir()
    info = pc.doc_quote({"id": "m1", "pdf": str(pdf), "find": "이용자의 43.7%는 AI가 제시한 정보를 별도로 검증하지 않고"}, work / "m1.png", work)
    assert info["highlighted"] and info["highlight"] and (work / "m1.png").exists()
    for x, y, w, h in info["highlight"]:
        assert w < info["size"][0] * 0.99 and h < 80           # 줄 하나 크기(프레임 전체가 아님)
