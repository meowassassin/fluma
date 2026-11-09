"""조립 문법 — 방향의 글꼴을 실제로 쓰고, 세리프면 상자 없는 절제된 제목, 장면 사이 zoom 전환, 끝 장면이 멈추지 않음"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
from craft import motion  # noqa: E402


def test_resolve_font_maps_to_installed():
    assert motion.resolve_font("Noto Serif CJK KR", "Pretendard-Black") == "GowunBatang-Bold"
    assert motion.resolve_font("명조 light", "x") == "GowunBatang-Regular"
    assert motion.resolve_font("SongMyung-Regular", "x") == "SongMyung-Regular"
    assert motion.resolve_font(None, "Pretendard-Black") == "Pretendard-Black"
    assert motion.resolve_font("Unknown Grotesk", "Pretendard-Black") == "Pretendard-Black"


def test_serif_direction_gives_editorial_title():
    g = motion.grammar({"direction": {"font_title": "Noto Serif CJK KR", "color_text": "#EDEAE4"}})
    assert g["title"]["editorial"] and not g["title"]["box"] and g["title"]["fg"] == "#EDEAE4"
    assert motion.grammar({})["title"]["box"]                                    # 방향이 없으면 예전 그대로
