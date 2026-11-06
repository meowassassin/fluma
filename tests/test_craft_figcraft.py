"""FigCraft 어댑터(ui_mock) — 글자 재기 · 줄바꿈은 앱 없이, 실제 그리기는 앱이 설치됐을 때만."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from craft import materials  # noqa: E402
from craft.adapters import designcraft as dc  # noqa: E402
from craft.adapters import figcraft as fg  # noqa: E402

Image = pytest.importorskip("PIL.Image")
HAS_FIG = (ROOT / "tools" / "crafts" / "figcraft" / "installed.json").exists()
HAS_DC = (ROOT / "tools" / "crafts" / "designcraft" / "installed.json").exists()
fig_app = pytest.mark.skipif(not HAS_FIG, reason="FigCraft 가 설치되지 않음")
dc_app = pytest.mark.skipif(not HAS_DC, reason="DesignCraft 가 설치되지 않음")


# ---------------------------------------------------------------- 앱 없이
def test_plugins_register():
    ad, _ = materials.plugins()
    assert ad["ui_mock"] is fg.ui_mock and ad["info_card"] is dc.info_card and ad["thumbnail"] is dc.thumbnail
    reg = materials.registry()
    assert reg.get("ui_mock") == "figcraft" and reg.get("info_card") == "designcraft" and reg.get("thumbnail") == "designcraft"


def test_wrap_breaks_at_words_not_letters():
    t = "한글 줄바꿈이 낱말 단위로 되는지 시험하는 문장입니다"
    lines = fg.wrap(t, 400, 40, 700)
    assert len(lines) > 1
    assert " ".join(lines) == t                       # 낱말이 잘리지 않았다
    assert all(fg.text_width(ln, 40, 700) <= 400 for ln in lines)


def test_wrap_keeps_newlines_and_clips():
    assert fg.wrap("첫 줄\n둘째 줄", 2000, 40) == ["첫 줄", "둘째 줄"]
    lines = fg.wrap("가나다 " * 40, 300, 40, max_lines=2)
    assert len(lines) == 2 and lines[-1].endswith("…")
    assert fg.ellipsize("아주 긴 항목 이름입니다", 120, 17).endswith("…")


def test_balanced_title_avoids_dangling_modifier():
    lines = fg.wrap("전환이 안 나올 때 광고비보다 먼저 볼 것", 792, 76, 700, -0.025, balance=True)
    assert not any(ln.endswith(("안", "나올")) for ln in lines[:-1])
    assert fg.break_penalty(["전환이 안 나올", "때 광고비보다"]) > 0


def test_inputs_checked(tmp_path):
    with pytest.raises(RuntimeError, match="src"):
        fg.ui_mock({"id": "m1", "type": "ui_mock"}, tmp_path / "m1.png", tmp_path)
    with pytest.raises(RuntimeError, match="device"):
        fg.ui_mock({"id": "m1", "type": "ui_mock", "device": "watch", "screen": {"title": "a"}}, tmp_path / "m1.png", tmp_path)
    with pytest.raises(RuntimeError, match="title"):
        dc.info_card({"id": "c", "type": "info_card"}, tmp_path / "c.png", tmp_path)


# ---------------------------------------------------------------- 앱으로
@fig_app
def test_ui_mock_capture_phone(tmp_path):
    im = Image.new("RGB", (360, 900), "white")
    im.paste((20, 120, 240), (0, 0, 360, 80))
    src = tmp_path / "shot.png"
    im.save(src)
    out = tmp_path / "m1.png"
    info = fg.ui_mock({"id": "m1", "type": "ui_mock", "src": str(src)}, out, tmp_path)
    assert info["device"] == "phone" and info["app"] == "figcraft" and info["as"] == "image"
    with Image.open(out) as o:
        assert o.mode == "RGBA" and o.getpixel((2, 2))[3] == 0          # 둘레는 투명
        x, y, w, h = info["screen_box"]
        cx, cy = int((x + w / 2) * o.width), int((y + h * 0.5) * o.height)
        assert o.getpixel((cx, cy))[3] == 255
    assert (tmp_path / "m1.figcraft").exists()


@fig_app
def test_ui_mock_generated_screen_marks_mock(tmp_path):
    out = tmp_path / "m2.png"
    info = fg.ui_mock({"id": "m2", "type": "ui_mock", "device": "phone", "mock": True, "screen": {
        "title": "알림 설정", "items": ["방해 금지", {"title": "야간 요약", "toggle": True}], "tabs": ["홈", "설정"]}},
        out, tmp_path)
    assert info["mock"] is True and len(info["item_boxes"]) == 2 and out.exists()
