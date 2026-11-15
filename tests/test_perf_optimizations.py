"""최적화 패치 회귀 · 동시성 · 세션 재사용 검증 테스트."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401

from craft import edit, materials, music_pick as M, usage  # noqa: E402
from gen import video  # noqa: E402


def test_usage_thread_isolation():
    results = {}

    def worker(name: str, app: str, feat: str, delay: float):
        usage.begin()
        time.sleep(delay)
        usage.record(app, [feat])
        time.sleep(0.02)
        results[name] = usage.take()

    usage.ALL.clear()
    t1 = threading.Thread(target=worker, args=("t1", "vectorcraft", "v1", 0.01))
    t2 = threading.Thread(target=worker, args=("t2", "photocraft", "p1", 0.02))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["t1"] == [{"app": "vectorcraft", "id": "v1"}]
    assert results["t2"] == [{"app": "photocraft", "id": "p1"}]
    assert "v1" in usage.ALL.get("vectorcraft", set())
    assert "p1" in usage.ALL.get("photocraft", set())


def test_materials_build_parallel_and_dependency_order(tmp_path, monkeypatch):
    monkeypatch.setattr(materials, "ROOT", tmp_path)
    monkeypatch.setattr(usage, "ROOT", tmp_path)

    order = []
    guard = threading.Lock()

    def slow_base(m, out, work):
        time.sleep(0.08)
        out.write_bytes(m["id"].encode("utf-8"))
        with guard:
            order.append(m["id"])
        return {"app": "mock_base"}

    def dep_consumer(m, out, work):
        uses = m.get("_uses") or {}
        assert "base" in uses and Path(uses["base"]).exists()
        out.write_bytes(b"dep_ok")
        with guard:
            order.append(m["id"])
        return {"app": "mock_dep"}

    monkeypatch.setattr(materials, "plugins", lambda: ({"mock_base": slow_base, "mock_dep": dep_consumer}, {}))
    monkeypatch.setattr(materials, "registry", lambda: {})

    sb = {
        "id": "p-par",
        "scenes": [
            {
                "sec": 4,
                "materials": [
                    {"id": "m1", "type": "mock_base"},
                    {"id": "m2", "type": "mock_dep", "uses": {"base": "m1"}},
                    {"id": "m3", "type": "mock_base"},
                ],
            },
            {
                "sec": 4,
                "materials": [
                    {"id": "m4", "type": "mock_base"},
                    {"id": "m5", "type": "mock_base"},
                ],
            },
        ],
    }

    t0 = time.monotonic()
    made = materials.build(sb)
    elapsed = time.monotonic() - t0

    assert [r["id"] for r in made] == ["m1", "m2", "m3", "m4", "m5"]
    assert order.index("m1") < order.index("m2")
    assert elapsed < 0.25   # 4×0.08s 직렬(0.32s+)보다 확실히 빨라야 함


def test_music_pick_parallel_fetch_and_score(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "ROOT", tmp_path)
    monkeypatch.setattr(M, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(M, "XRAY", tmp_path / "xray")

    monkeypatch.setattr(M, "trending_sounds", lambda sb, n=8: [{"sound": "TrendHit", "shorts": 3, "views": 5000}])
    monkeypatch.setattr(M, "free_version", lambda song: {"id": "fv1", "title": "TrendHit (No Copyright Music)", "by": "Audio Library", "sec": 90, "views": 10000})
    monkeypatch.setattr(M, "chart", lambda n=20: [])
    monkeypatch.setattr(M, "search", lambda q, n=8, recent=False: [{"id": "s1", "title": "Other (No Copyright Music)", "by": "Audio Library", "sec": 90, "views": 2000}])

    fetched = []

    def fake_fetch(vid: str) -> Path:
        time.sleep(0.05)
        fetched.append(vid)
        p = tmp_path / "cache" / f"{vid}.m4a"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"audio")
        return p

    monkeypatch.setattr(M, "fetch", fake_fetch)
    monkeypatch.setattr(M, "measure", lambda p, need: {"bpm": 92 if p.stem == "fv1" else 140, "beat_conf": 0.9, "sec": 90.0, "start": 5.0})

    sb = {"id": "t-mus", "topic": "테스트", "scenes": [{"sec": 30, "narration": ""}]}
    res = M.pick(sb, {}, None, 92)
    assert res["use"] is True
    assert set(fetched) == {"fv1", "s1"}
    assert "TrendHit" in res["title"]


def test_edit_assemble_batches_import_and_place(tmp_path, monkeypatch):
    monkeypatch.setattr(edit, "ROOT", tmp_path)
    fc = tmp_path / "filmcraft-cli"
    fc.write_text("#!/bin/sh\n", "utf-8")
    monkeypatch.setattr(edit, "cli", lambda name: fc)

    v = tmp_path / "v.mp4"; v.write_bytes(b"v")
    a = tmp_path / "a.wav"; a.write_bytes(b"a")
    out = tmp_path / "out.mp4"

    calls = []

    def fake_fc(cli_p, *args, cwd=None):
        calls.append(args)
        if "import" in args:
            return {"items": [10, 11]}
        if "export" in args:
            out.write_bytes(b"mp4")
        return {}

    scripts = []

    def fake_run_script(cli_p, proj, lines, cwd=None):
        scripts.append(lines)
        return []

    monkeypatch.setattr(edit, "_fc", fake_fc)
    monkeypatch.setattr(edit, "_run_script", fake_run_script)

    sb = {"id": "t-ed", "title": "배치", "scenes": [{"role": "hook", "sec": 3, "narration": "테스트"}]}
    res = edit.assemble(sb, v, a, out)
    assert res == out
    imp_calls = [c for c in calls if "import" in c]
    assert len(imp_calls) == 1
    assert str(v.resolve()) in imp_calls[0] and str(a.resolve()) in imp_calls[0]
    assert len(scripts) == 1
    ids = [ln["id"] for ln in scripts[0]]
    assert ids[:2] == ["timeline.place", "timeline.place"]
    assert "markers.add" in ids


def test_video_run_reuses_route_flow_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(video, "ROOT", tmp_path)
    monkeypatch.setattr(video, "approved_shots", lambda pid: {1, 2})
    monkeypatch.setattr(video, "used", lambda pid, sb, s: 0)
    monkeypatch.setattr(video, "attempts", lambda pid, n: [])
    monkeypatch.setattr(video, "write_attempt", lambda *a, **kw: None)
    monkeypatch.setattr(video, "plan_project_id", lambda pid: "proj-1")
    monkeypatch.setattr(video.kfmod, "kdir", lambda pid: tmp_path / "kf")
    monkeypatch.setattr(video.planmod, "load", lambda pid: (
        tmp_path / "plan.json",
        {"shots": [
            {"n": 1, "gen_sec": 4, "kind": "motion"},
            {"n": 2, "gen_sec": 4, "kind": "motion"},
        ], "aspect": "9:16"},
    ))
    monkeypatch.setattr(video.planmod, "video_prompt", lambda sb, s: {"prompt": f"shot {s['n']}", "negative": ""})
    monkeypatch.setattr(video, "style_refs", lambda *a, **kw: [])
    monkeypatch.setattr(video, "settings", lambda: {
        "backend": "gflow", "model": "veo_3_1_lite",
        "credits": {"veo_3_1_lite": 10}, "max_attempts": 3, "timeout_sec": 60,
    })

    created = []

    class FakeFlow:
        name = "flow"
        agent_only = False

        def __init__(self):
            self.closed = 0
            self.credits_calls = 0
            self.gen_calls = 0
            created.append(self)

        def available(self):
            return True, ""

        def credits(self):
            self.credits_calls += 1
            return 100

        def generate(self, req, timeout):
            assert self.closed == 0
            self.gen_calls += 1
            req.out.parent.mkdir(parents=True, exist_ok=True)
            req.out.write_bytes(b"mp4")
            return video.GenResult(True, req.out, req.model, "flow", raw={"flow_project_id": "proj-1"})

        def close(self):
            self.closed += 1

    monkeypatch.setattr(video, "make_backend", lambda name, pid: FakeFlow())
    res = video.run("p-reuse", None, None)

    assert res["done"] == [1, 2]
    assert res["stopped"] is None
    assert len(created) == 1
    assert created[0].credits_calls == 1
    assert created[0].gen_calls == 2
    assert created[0].closed == 1


def test_flow_mcp_reuses_persistent_agent_worker(tmp_path, monkeypatch):
    fm = video.FlowMCP(tmp_path / "out")
    starts = 0
    closed = 0
    reqs = []

    class FakeStdin:
        def write(self, data: str):
            reqs.append(json.loads(data))
            out = Path(reqs[-1]["out"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"video-bytes")

        def flush(self):
            pass

        def close(self):
            pass

    class FakeStdout:
        def __init__(self):
            self.idx = 0

        def fileno(self):
            return 0

        def readline(self):
            self.idx += 1
            p = reqs[self.idx - 1]["out"]
            return "FLUMA_AGENT_I2V " + json.dumps({"ok": True, "stage": "done", "path": p, "media_id": f"m{self.idx}"}) + "\n"

    class FakeAgentProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout()

        def poll(self):
            return None

        def wait(self, timeout=None):
            nonlocal closed
            closed += 1
            return 0

    def fake_start():
        nonlocal starts
        if fm.agent_p is None:
            starts += 1
            fm.agent_p = FakeAgentProc()

    monkeypatch.setattr(fm, "_start_agent", fake_start)
    monkeypatch.setattr(video.select, "select", lambda r, w, x, t=None: (r, [], []))

    img = tmp_path / "s01.png"; img.write_bytes(b"png")
    r1 = fm._agent_i2v(video.GenRequest(1, "p1", img, None, 8, "9:16", "veo_3_1_lite", tmp_path / "1.mp4", project="pj"), 60)
    r2 = fm._agent_i2v(video.GenRequest(2, "p2", img, None, 8, "9:16", "veo_3_1_lite", tmp_path / "2.mp4", project="pj"), 60)
    assert r1.ok and r2.ok
    assert starts == 1
    assert len(reqs) == 2
    fm.close()
    assert closed == 1
