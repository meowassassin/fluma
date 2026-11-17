"""생성 파이프라인 무결성 가드레일(중복 시트 · 참조 누락 · 유령 자막/음성 차단 · 동시 락) 테스트."""
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "gen"))
sys.path.insert(0, str(ROOT / "engine" / "research"))

import assemble  # noqa: E402
import character  # noqa: E402
import editor_bridge  # noqa: E402
import image as imagegen  # noqa: E402
import keyframe  # noqa: E402
import plan  # noqa: E402
import ref_image  # noqa: E402


def test_character_duplicate_views_and_meta(tmp_path):
    d = tmp_path / "Hero"
    d.mkdir()
    (d / "front.png").write_bytes(b"same-front-bytes")
    (d / "back.png").write_bytes(b"same-front-bytes")
    (d / "left.png").write_bytes(b"left-bytes")
    (d / "right.png").write_bytes(b"right-bytes")
    dups = character.duplicate_views(d)
    assert ("front", "back") in dups

    bad_meta = {
        "views": {
            "front": {"prompt": f"... {character.VIEW_TEXT['front']} ...", "refs": []},
            "left": {"prompt": f"... {character.VIEW_TEXT['front']} ...", "refs": []},
            "right": {"prompt": f"... {character.VIEW_TEXT['right']} ...", "refs": [{"path": "front.png"}]},
        }
    }
    errs = character.view_integrity_errors(d, bad_meta)
    assert any("front 와 back" in e for e in errs)
    assert any("left: 프롬프트가 정면" in e for e in errs)
    assert any("left: 정면 참조" in e for e in errs)

    (d / "back.png").write_bytes(b"real-back-bytes")
    good_meta = {
        "views": {
            "front": {"prompt": f"... {character.VIEW_TEXT['front']} ...", "refs": []},
            "back": {"prompt": f"... {character.VIEW_TEXT['back']} ...", "refs": [{"path": "front.png"}]},
            "left": {"prompt": f"... {character.VIEW_TEXT['left']} ...", "refs": [{"path": "front.png"}]},
            "right": {"prompt": f"... {character.VIEW_TEXT['right']} ...", "refs": [{"path": "front.png"}]},
        }
    }
    assert character.view_integrity_errors(d, good_meta) == []


def test_keyframe_ref_missing_error():
    sb = {"shots": [{"n": 1, "characters": ["Hero"]}, {"n": 2, "characters": []}]}
    assert keyframe._ref_missing_error(sb, sb["shots"][0], {"first": {"via": "gflow:t2i", "refs": []}})
    assert keyframe._ref_missing_error(sb, sb["shots"][0], {"first": {"via": "gflow:image", "mode": "t2i", "refs": []}})
    assert keyframe._ref_missing_error(sb, sb["shots"][0], {"first": {"via": "gflow:image", "mode": "i2i", "refs": [{"path": "a.png"}]}}) is None
    assert keyframe._ref_missing_error(sb, sb["shots"][1], {"first": {"via": "gflow:t2i", "refs": []}}) is None


def test_stale_ghost_audio_rejected_and_draft_ass(tmp_path, monkeypatch):
    audio_dir = tmp_path / "data" / "public" / "audio"
    audio_dir.mkdir(parents=True)
    pid = "test-pid-ghost"
    (audio_dir / f"{pid}.captions.json").write_text(json.dumps([
        {"text": "옛날 대사", "startMs": 100, "endMs": 800, "scene": 0}
    ]), "utf-8")
    old_hash = hashlib.sha1("옛날 대사".encode("utf-8")).hexdigest()[:8]
    (audio_dir / f"{pid}.timing.json").write_text(json.dumps([
        {"scene": 0, "text_hash": old_hash, "start": 0.0, "end": 3.0}
    ]), "utf-8")
    monkeypatch.setattr(assemble, "ROOT", tmp_path)
    monkeypatch.setattr(editor_bridge, "ROOT", tmp_path)

    silent_story = {"id": pid, "title": "무언극 테스트", "scenes": [{"sec": 3.0, "narration": "", "caption": ""}]}
    assert assemble.audio_matches_story(pid, silent_story) is False
    assert editor_bridge._story_audio_matches(pid, silent_story, False) is False

    ass_p = tmp_path / "draft.ass"
    assert assemble._write_draft_ass(ass_p, pid, silent_story, 1080, 1920, 3.0) is True
    ass_txt = ass_p.read_text("utf-8")
    assert "옛날 대사" not in ass_txt
    assert "무언극 테스트" in ass_txt

    changed_story = {"id": pid, "title": "새 대사", "script": "바뀐 대사", "scenes": [{"sec": 3.0, "narration": "바뀐 대사"}]}
    assert assemble.audio_matches_story(pid, changed_story) is False
    assert editor_bridge._story_audio_matches(pid, changed_story, False) is False

    matching_story = {"id": pid, "title": "맞는 대사", "script": "옛날 대사", "scenes": [{"sec": 3.0, "narration": "옛날 대사"}]}
    assert assemble.audio_matches_story(pid, matching_story) is True
    assert editor_bridge._story_audio_matches(pid, matching_story, False) is True


def test_gflow_profile_lock_serializes_threads(tmp_path, monkeypatch):
    monkeypatch.setattr(imagegen, "_GFLOW_LOCK_PATH", tmp_path / "gflow.lock")
    active = 0
    max_active = 0
    guard = threading.Lock()

    def worker():
        nonlocal active, max_active
        with imagegen._gflow_profile_lock():
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.03)
            with guard:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_active == 1


def _minimal_shotplan(pid: str = "test-stage05-01", topic: str = "지브리풍 크롬 탭 정리") -> dict:
    return {
        "id": pid,
        "topic": topic,
        "aspect": "9:16",
        "trend": {},
        "logline": "탭 과부하를 끄는 이야기",
        "style": "Warm watercolor cel shading, soft morning light.",
        "needs_character": True,
        "characters": [
            {"name": "Hero", "identity": "chubby white rabbit mascot with round cheeks", "wardrobe": "blue hoodie"}
        ],
        "narration": "탭을 너무 많이 열면 컴퓨터가 멈춰요",
        "shots": [
            {
                "n": 1,
                "purpose": "hook",
                "gen_sec": 4,
                "final_sec": 3.0,
                "shot_size": "medium shot",
                "angle": "eye-level",
                "camera_move": "locked-off",
                "camera_intent": "keep focus on hero",
                "subject_pos": "Hero centered in frame",
                "start_state": "Hero stands under floating translucent browser window panels with colored tab headers",
                "action": "Hero catches a falling browser window panel",
                "env_motion": "cool breeze moves leaves gently",
                "end_state": "Hero holds three browser panels awkwardly",
                "background": "pastel desk workshop",
                "lighting": "soft warm window daylight",
                "ambient": "quiet room hum",
                "sfx": "soft pop",
                "avoid": "blur, text",
                "characters": ["Hero"],
            }
        ],
    }


def test_ref_image_search_pick_and_style_ref_pipeline(tmp_path, monkeypatch):
    import io
    from PIL import Image

    monkeypatch.setattr(ref_image, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "ROOT", tmp_path)
    monkeypatch.setattr(plan, "PLANS", tmp_path / "data" / "shotplans")
    monkeypatch.setattr(plan, "RESEARCH", tmp_path / "data" / "research")
    monkeypatch.setattr(character, "ROOT", tmp_path)
    monkeypatch.setattr(keyframe, "ROOT", tmp_path)

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

    # 4) character.py & keyframe.py 로 실제 style_refs 전달 검증 + 해시 무효화 검증
    c_refs = character.style_refs_for(updated)
    assert len(c_refs) == 1
    pr_front = character.prompt_for(updated, updated["characters"][0], "front", False, c_refs)
    assert "visual art style" in pr_front

    char_dir = character.cdir(pid, "Hero")
    char_dir.mkdir(parents=True)
    (char_dir / "front.png").write_bytes(img_bytes)
    h1 = character.input_hash(updated, updated["characters"][0], char_dir)
    updated["style_refs"].append({"path": "data/compositions/other.png", "role": "prop"})
    h2 = character.input_hash(updated, updated["characters"][0], char_dir)
    assert h1 != h2

    kf_refs = keyframe.refs_for(pid, json.loads(sp.read_text("utf-8")), updated["shots"][0])
    assert len(kf_refs) == 2  # Hero front + style_ref
    kpr = plan.keyframe_prompt(updated, updated["shots"][0], [r for _, r in kf_refs])
    assert "Follow each Image label strictly" in kpr


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


def test_gflow_i2i_agent_only_routes_and_skips_agy(tmp_path, monkeypatch):
    import subprocess
    from PIL import Image

    monkeypatch.setattr(imagegen, "_GFLOW_LOCK_PATH", tmp_path / "gflow.lock")
    monkeypatch.setattr(imagegen, "_AGENT_ONLY_IMAGE", False)
    monkeypatch.setattr(imagegen, "_AGENT_WORKER", None)
    monkeypatch.setattr(imagegen, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(imagegen, "default_flow_project", lambda: "proj-agent-1")

    fake_gflow = tmp_path / "gflow"
    fake_gflow.write_text("#!/bin/sh\n", "utf-8")
    monkeypatch.setattr(imagegen, "_find_gflow", lambda: fake_gflow)
    monkeypatch.setattr(imagegen.shutil, "which", lambda name: None if name == "xvfb-run" else f"/usr/bin/{name}")

    ref1 = tmp_path / "style.png"
    ref2 = tmp_path / "front.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(ref1, format="PNG")
    Image.new("RGB", (64, 64), (40, 50, 60)).save(ref2, format="PNG")

    cli_calls = []

    def fake_run(cmd, env=None, capture_output=True, text=True, timeout=600, cwd=None):
        cli_calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            36,
            stdout="",
            stderr="flow-host-migrated: this account is served Flow's agent-only composer (#799)",
        )

    monkeypatch.setattr(imagegen.subprocess, "run", fake_run)
    monkeypatch.setattr(
        imagegen,
        "_generate_agy",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("agy 폴백이 호출되면 안 됨")),
    )

    jobs_sent = []
    worker_starts = 0

    class FakeWorker:
        def __init__(self):
            self._lines: list[str] = []
            self.stdin = self
            self.stdout = self

        def poll(self):
            return None

        def write(self, payload: str):
            job = json.loads(payload)
            jobs_sent.append(job)
            Image.new("RGB", (90, 160), (200, 100, 50)).save(job["out"], format="PNG")
            reply = {
                "ok": True,
                "stage": "done",
                "kind": "image",
                "path": job["out"],
                "media_id": f"media-{len(jobs_sent)}",
                "project_id": job["project"] or "proj-agent-1",
                "uploaded": [Path(r["path"]).name for r in job["refs"]],
            }
            self._lines.append("FLUMA_AGENT_I2V " + json.dumps(reply, ensure_ascii=False) + "\n")

        def flush(self):
            pass

        def readline(self):
            return self._lines.pop(0) if self._lines else ""

        def close(self):
            pass

        def wait(self, timeout=5):
            return 0

    fake_worker = FakeWorker()

    def fake_ensure_worker():
        nonlocal worker_starts
        if imagegen._AGENT_WORKER is None:
            worker_starts += 1
            imagegen._AGENT_WORKER = fake_worker
        return imagegen._AGENT_WORKER

    monkeypatch.setattr(imagegen, "_ensure_agent_worker", fake_ensure_worker)
    monkeypatch.setattr(imagegen.select, "select", lambda rlist, *_: (rlist, [], []))

    out1 = tmp_path / "shot1.png"
    meta1 = imagegen.generate(
        out1,
        "hero wearing blue hoodie",
        refs=[(ref1, "style ref"), (ref2, "front view")],
        aspect="9:16",
        model="nano-pro",
        backend="gflow",
    )
    assert out1.exists()
    assert meta1["via"] == "gflow:agent-i2i"
    assert meta1["agent_only"] is True
    assert meta1["flow_project_id"] == "proj-agent-1"
    assert meta1["flow_media_id"] == "media-1"
    assert len(cli_calls) == 1
    assert len(jobs_sent) == 1 and len(jobs_sent[0]["refs"]) == 2

    # 두 번째 i2i 호출은 _AGENT_ONLY_IMAGE 캐시로 gflow CLI 를 건너뛰고 상주 워커를 재사용한다
    out2 = tmp_path / "shot2.png"
    meta2 = imagegen.generate(
        out2,
        "hero back view",
        refs=[(ref2, "front view")],
        aspect="9:16",
        model="flash",
        backend="gflow",
    )
    assert out2.exists()
    assert meta2["flow_media_id"] == "media-2"
    assert len(cli_calls) == 1
    assert worker_starts == 1
    assert len(jobs_sent) == 2
    assert jobs_sent[1]["model"] == "nano2"


def test_gflow_failure_and_agy_fallback_reports_both_errors(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(imagegen, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(imagegen.shutil, "which", lambda name: "/usr/bin/agy" if name == "agy" else None)
    monkeypatch.setattr(imagegen, "_generate_gflow", lambda *a, **kw: (_ for _ in ()).throw(imagegen.ImageGenError("gflow broken")))
    monkeypatch.setattr(imagegen, "_generate_agy", lambda *a, **kw: (_ for _ in ()).throw(imagegen.ImageGenError("429 QUOTA_EXHAUSTED")))

    with pytest.raises(imagegen.ImageGenError) as exc:
        imagegen.generate(tmp_path / "o.png", "prompt", backend="gflow")
    msg = str(exc.value)
    assert "gflow broken" in msg and "429 QUOTA_EXHAUSTED" in msg
