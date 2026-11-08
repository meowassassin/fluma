"""콘셉트 단계 — 안 검사(겹침 · 각도 · 닳은 말 · 한 방)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "story"))
import paths  # noqa: E402,F401
import concepts as C  # noqa: E402


def good():
    hooks = ["붕어빵 한 마리 뜯어 봤더니 팥이 제일 비쌉니다", "천 원으로 네 마리에서 한 마리까지 오년", "사장 장부를 그대로 켜 드립니다", "붕어빵과 타이야키가 맞붙으면", "이 골목 붕세권 지도를 다시 그렸습니다", "사실 주인공은 밀가루입니다"]
    angles = ["해부", "데이터", "역할극", "대결", "형식파괴", "반전"]
    return {"concepts": [{"name": f"안{i}", "angle": angles[i], "promise": "p", "one_shot": f"한 방 {i} {'가나다라마바사'[i]}{'아자차카타파하'[i]}", "hook": hooks[i], "evidence": "https://x", "trick": "t", "beats": [{"big": "a"}, {"big": "b"}]} for i in range(6)]}


def test_good_set_passes():
    assert C.check(good(), [])[0] == []


def test_too_few_angles_is_blocked():
    d = good()
    for c in d["concepts"]:
        c["angle"] = "데이터"
    bad, _ = C.check(d, [])
    assert any("가지뿐" in b for b in bad) and any("2개까지" in b for b in bad)


def test_tired_hook_and_missing_one_shot():
    d = good()
    d["concepts"][0]["hook"] = "이것만 알면 붕어빵 끝"
    d["concepts"][1]["one_shot"] = ""
    bad, _ = C.check(d, [])
    assert any("닳은 말" in b for b in bad) and any("one_shot" in b for b in bad)


def test_overlap_with_past_video():
    d = good()
    bad, _ = C.check(d, [("old", d["concepts"][2]["hook"])])
    assert any("겹침" in b for b in bad)


def test_unverified_evidence_is_a_note_not_a_block():
    d = good()
    d["concepts"][0]["evidence"] = "조사 필요"
    bad, note = C.check(d, [])
    assert bad == [] and note
