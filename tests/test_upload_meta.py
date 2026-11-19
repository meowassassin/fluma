"""유튜브 업로드 정보 — 길이 · 해시태그 · 태그 정리, 실제로 보내는 설명(출처 · 해시태그 포함), 업로드 본문이 그 값을 쓴다"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "publish"))
import metadata  # noqa: E402
import upload_youtube  # noqa: E402


def test_tidy_limits_and_shorts_tag():
    r = metadata.tidy({"titles": ["가" * 80 + " #쇼츠"], "best": "고무 오리 디버깅 #Shorts", "description": "첫 줄",
                       "hashtags": ["고무 오리", "#디버깅", "#디버깅"], "tags": ["a,b", "<x>"] + [f"태그{i}" for i in range(30)]}, {"title": "화면 제목"})
    assert r["title"] == "고무 오리 디버깅" and len(r["titles"][0]) <= metadata.TITLE_MAX
    assert r["hashtags"][:2] == ["#고무오리", "#디버깅"] and "#Shorts" in r["hashtags"]
    assert len(r["tags"]) <= 15 and all("," not in t and "<" not in t for t in r["tags"])


def test_full_description_has_sources_and_hashtags():
    sb = {"id": "zz", "sources": ["https://example.com/a"], "format": "concept"}
    up = {"description": "본문", "hashtags": ["#디버깅", "#Shorts"]}
    full = metadata.full_description(sb, up)
    assert full.startswith("본문") and "https://example.com/a" in full and full.rstrip().endswith("#디버깅 #Shorts")


def test_upload_uses_generated_info():
    sb = {"id": "zz", "title": "화면 제목", "sources": [], "upload": {"title": "검색용 제목", "description": "본문", "hashtags": ["#Shorts"], "tags": ["t1"]}}
    assert upload_youtube.build_description(sb).startswith("본문")
