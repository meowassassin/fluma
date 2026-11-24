"""기획 기록(plan.py) · Stage 0.5 자료조사 · 시각 레퍼런스(ref_image) — 영상 생성 경로 제거(2026-11-19) 뒤 남은 기획 단계"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "gen"))
sys.path.insert(0, str(ROOT / "engine" / "research"))

import plan  # noqa: E402
import ref_image  # noqa: E402


def _minimal_shotplan(pid: str = "test-stage05-01", topic: str = "지브리풍 크롬 탭 정리") -> dict:
    return {"id": pid, "topic": topic, "aspect": "9:16", "trend": {}, "logline": "탭 과부하를 끄는 이야기",
            "route": "material", "route_why": "실제 화면으로 충분"}


def test_ref_image_search_pick_and_style_ref_pipeline(tmp_path, monkeypatch):
    import io
    from PIL import Image

    monkeypatch.setattr(ref_image, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "PLANS", tmp_path / "data" / "shotplans")
    monkeypatch.setattr(plan, "RESEARCH", tmp_path / "data" / "research")

    pid = "test-stage05-01"
    (tmp_path / "data" / "shotplans").mkdir(parents=True)
    (tmp_path / "data" / "research").mkdir(parents=True)
    sb = _minimal_shotplan(pid)
    sp = tmp_path / "data" / "shotplans" / f"{pid}.json"
    sp.write_text(json.dumps(sb, ensure_ascii=False), "utf-8")

    # 1) Stage 0.5 누락 시 plan.problems 가 자료조사 · 시각 레퍼런스 모두 막는지 검증
    errs, _ = plan.problems(json.loads(sp.read_text("utf-8")))
    assert any("주제 자료조사 없음" in e for e in errs)
    assert any("실제 이미지/영상 레퍼런스 확인 필요" in e for e in errs)

    # 2) data/research/<pid>.json 연결 검증
    (tmp_path / "data" / "research" / f"{pid}.json").write_text(json.dumps({
        "facts": [{"claim": "Chrome limits idle tabs", "value": "Memory Saver", "source": "https://support.google.com/chrome/answer/12929150"}],
        "visual_entities": ["Chrome tab strip", "giant mouse cursor"],
    }, ensure_ascii=False), "utf-8")
    plan.sync_research(pid)

    # 3) Bing HTML 파싱 + mock 이미지 다운로드 + 밀착 시트 + pick & shotplan 동기화 검증
    sample_html = '<a class="iusc" m="{&quot;murl&quot;:&quot;https://example.com/ghibli1.png&quot;,&quot;turl&quot;:&quot;https://example.com/t1.jpg&quot;,&quot;t&quot;:&quot;Ghibli style frame&quot;}"></a>'
    parsed = ref_image.parse_bing_html(sample_html)
    assert len(parsed) == 1 and parsed[0]["url"] == "https://example.com/ghibli1.png"

    buf = io.BytesIO()
    Image.new("RGB", (320, 320), (80, 140, 200)).save(buf, format="PNG")
    img_bytes = buf.getvalue()

    class _Resp:
        def __init__(self, status_code=200, text="", content=b""):
            self.status_code = status_code
            self.text = text
            self.content = content

        def raise_for_status(self):
            return None

    def fake_get(url, headers=None, timeout=15):
        if "bing.com" in url:
            return _Resp(200, text=sample_html)
        return _Resp(200, content=img_bytes)

    monkeypatch.setattr(ref_image.requests, "get", fake_get)
    sres = ref_image.search_and_save(pid, "ghibli cel shading background", limit=3, source="bing")
    assert sres["count"] == 1
    assert (tmp_path / sres["sheet"]).exists()

    pres = ref_image.pick_candidates(pid, [1], role="style", note="Soft watercolor palette", sync=True)
    assert pres["synced"] is True
    assert (tmp_path / pres["sheet"]).exists()

    updated = json.loads(sp.read_text("utf-8"))
    errs2, _ = plan.problems(updated)
    assert not errs2


def test_stage05_skip_and_direct_fetch(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(ref_image, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "PLANS", tmp_path / "data" / "shotplans")
    monkeypatch.setattr(plan, "RESEARCH", tmp_path / "data" / "research")

    pid = "test-skip-01"
    (tmp_path / "data" / "shotplans").mkdir(parents=True)
    sp = tmp_path / "data" / "shotplans" / f"{pid}.json"
    sp.write_text(json.dumps(_minimal_shotplan(pid, "지브리풍 순수 창작 밈"), ensure_ascii=False), "utf-8")

    plan.sync_research(pid, skip_reason="순수 창작 밈", style_skip="직접 묘사만으로 충분")
    errs, _ = plan.problems(json.loads(sp.read_text("utf-8")))
    assert not errs

    local_img = tmp_path / "user_ref.png"
    Image.new("RGB", (256, 256), (220, 120, 60)).save(local_img, format="PNG")
    fres = ref_image.fetch_direct(pid, [str(local_img)], role="prop", note="User attached ref", sync=True)
    assert fres["synced"] is True
    sb = json.loads(sp.read_text("utf-8"))
    assert sb["style_refs"][0]["role"] == "prop"
    (tmp_path / sb["style_refs"][0]["path"]).unlink()
    errs_missing, _ = plan.problems(sb)
    assert any("시각 레퍼런스 파일 없음" in e for e in errs_missing)
