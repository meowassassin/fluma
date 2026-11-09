"""콘셉트 단계 — 안 검사(뻔함 지도 · 깨는 것 · 겹침 · 각도 · 한 방)"""
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
    cliches = [{"kind": "구조", "what": "고민 제시 다음 장점 나열 후 할인 안내", "seen_in": ["r1"]},
               {"kind": "제목", "what": "숫자 넣은 리스트 제목", "seen_in": ["r2"]},
               {"kind": "첫장면", "what": "가게 간판 정면샷으로 시작", "seen_in": ["r3"]}]
    return {"cliches": cliches, "concepts": [{"name": f"안{i}", "angle": angles[i], "promise": "p", "one_shot": f"한 방 {i} {'가나다라마바사'[i]}{'아자차카타파하'[i]}", "hook": hooks[i],
            "breaks": str(i % 3 + 1), "why_fresh": "w", "structure": f"흐름 {i}", "evidence": "https://x", "trick": "t", "beats": [{"big": "a"}, {"big": "b"}]} for i in range(6)]}


SEEN = lambda r: r in ("r1", "r2", "r3")  # noqa: E731


def test_good_set_passes():
    assert C.check(good(), [], SEEN)[0] == []


def test_too_few_angles_is_blocked():
    d = good()
    for c in d["concepts"]:
        c["angle"] = "데이터"
    bad, _ = C.check(d, [], SEEN)
    assert any("가지뿐" in b for b in bad) and any("2개까지" in b for b in bad)


def test_cliche_map_must_come_from_analyzed_refs():
    d = good()
    d["cliches"][0]["seen_in"] = ["안본영상"]
    bad, _ = C.check(d, [], SEEN)
    assert any("X-ray 한 레퍼런스가 없음" in b for b in bad)
    d = good(); d["cliches"] = d["cliches"][:2]
    assert any("뻔함 지도" in b for b in C.check(d, [], SEEN)[0])


def test_each_concept_must_break_a_mapped_cliche():
    d = good()
    d["concepts"][0]["breaks"] = "지도에 없는 말"
    d["concepts"][1]["one_shot"] = ""
    for c in d["concepts"]:
        c["breaks"] = "1" if c is not d["concepts"][0] else c["breaks"]
    bad, _ = C.check(d, [], SEEN)
    assert any("지도에 없음" in b for b in bad) and any("one_shot" in b for b in bad) and any("가지뿐 — 서로 다른" in b for b in bad)


def test_concept_that_copies_the_cliche_is_blocked():
    d = good()
    d["concepts"][0]["structure"] = "고민 제시 다음 장점 나열 후 할인 안내"
    assert any("그대로 닮음" in b for b in C.check(d, [], SEEN)[0])


def test_overlap_with_past_video():
    d = good()
    bad, _ = C.check(d, [("old", d["concepts"][2]["hook"])], SEEN)
    assert any("겹침" in b for b in bad)


def test_unverified_evidence_is_a_note_not_a_block():
    d = good()
    d["concepts"][0]["evidence"] = "조사 필요"
    bad, note = C.check(d, [], SEEN)
    assert bad == [] and note
