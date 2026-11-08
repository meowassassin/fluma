"""Craft 파이프라인 1단계 — 앱 없이 확인할 수 있는 약속만: 자막 덩어리 · 단어 큐 · 말하는 구간 · 덕킹 점(샘플 단위) · SRT · 프로젝트 구조."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft.audio import RATE, commands, finish_commands, speech_spans  # noqa: E402
from craft.edit import srt  # noqa: E402
from craft.motion import build_jsx, chunks, cue_time, quoted  # noqa: E402

WORDS = [{"text": " AI", "startMs": 30, "endMs": 700, "scene": 0}, {"text": " 추천", "startMs": 700, "endMs": 1098, "scene": 0},
         {"text": " 5개", "startMs": 1098, "endMs": 1519, "scene": 0}, {"text": " 중", "startMs": 1519, "endMs": 1800, "scene": 0},
         {"text": " 그런데", "startMs": 3200, "endMs": 3600, "scene": 1}]


def test_captions_follow_one_or_two_words():
    cs = chunks(WORDS)
    assert [c["text"] for c in cs] == ["AI 추천", "5개 중", "그런데"]
    assert cs[0]["start"] == 0.03 and cs[0]["end"] == 1.098


def test_cue_word_maps_to_scene_local_time():
    assert cue_time("5개 중", WORDS, 0.0, 2.8) == 1.098
    assert cue_time("그런데", WORDS, 2.8, 6.0) == 0.4
    assert cue_time("없는 낱말", WORDS, 0.0, 2.8) is None
    assert quoted("노란 상자 'AI가 / 지어낸 / 패키지' 쌓임") == ["AI가", "지어낸", "패키지"]


def test_music_ducks_under_speech_with_points_in_samples():
    assert speech_spans(WORDS) == [(0.03, 1.8), (3.2, 3.6)]
    sb = {"id": "x", "music": {"src": __file__, "gain_db": -14, "duck_db": -6}}
    pts = [json.loads(c.split("=", 1)[1]) for c in commands(sb, Path(__file__), WORDS, 10.0) if c.startswith("automation.set_point")]
    assert all(isinstance(p["at"], int) for p in pts)                      # 초가 아니라 샘플
    assert any(p["at"] == int(round(0.08 * RATE)) and p["value"] == -20 for p in pts)
    # 끝 페이드아웃은 자동화 점이 아니라 음악 클립의 s-curve 페이드(두 번째 실행) — 영상보다 긴 음악은 영상 길이로 자른다
    fin = finish_commands(sb, {"clip": 11, "frames": 20 * RATE}, 10.0)
    assert any(c.startswith("edit.trim_clip=") and json.loads(c.split("=", 1)[1])["end"] == 10 * RATE for c in fin)
    outs = [json.loads(c.split("=", 1)[1]) for c in fin if c.startswith("edit.fades_create=")]
    assert any(f["side"] == "out" and f.get("shape") == "s-curve" for f in outs)


def test_srt_is_well_formed():
    s = srt(WORDS)
    assert s.startswith("1\n00:00:00,030 --> 00:00:01,098\nAI 추천\n")


def test_project_has_one_comp_per_scene_and_a_persistent_pill():
    sb = {"id": "t", "direction": {"color_bg": "#0f4b7d"}, "scenes": [
        {"role": "hook", "sec": 2.8, "elements": [{"name": "훅 제목", "what": "'AI가 / 지어낸'", "cue": "AI"},
                                                  {"name": "숫자 알약", "what": "분홍 '19.7% 가짜'", "cue": "5개"}]},
        {"role": "reveal", "sec": 1.0, "elements": [{"name": "숫자 알약", "what": "보라 '43% 반복'", "cue": "그런데"}]}]}
    scenes = [{"index": 0, "start": 0.0, "end": 2.8, "sec": 2.8}, {"index": 1, "start": 2.8, "end": 3.8, "sec": 1.0}]
    jsx = build_jsx(sb, WORDS, scenes, Path("/tmp/x.ecproj"))
    assert "addComp(\"S01 훅\"" in jsx and "addComp(\"S02 반전\"" in jsx
    assert jsx.count("txt(main, 'PillText'") == 1 and "txt(c, 'PillText'" not in jsx   # 알약은 영상 전체에 하나
    assert "KeyframeInterpolationType.HOLD" in jsx
    assert "Title 2" in jsx and "fitBox(c, 'TitleBox 1', 'Title 1'" in jsx  # 상자는 글자를 따라감


def test_materials_registry_and_match():
    """재료 종류 → 앱(능력 목록), PdfCraft 일치 결과 → [x, y, w, h]"""
    from craft import materials
    reg = materials.registry()
    for t, app in {"chart": "gridcraft", "doc_quote": "pdfcraft", "illustration": "vectorcraft", "photo": "photocraft"}.items():
        if (materials.ROOT / "tools" / "crafts" / app / "installed.json").exists():
            assert reg[t] == app
    rep = {"steps": [{"result": [{"doc": 1}]}, {"result": [{"matches": [{"page": 2, "rects": [[10, 20, 110, 32]]}]}]}]}
    assert materials._first_match(rep) == (2, [[10, 20, 100, 12]])
    assert materials._first_match({"steps": []}) is None
