"""대화로 고치기 — 값 바꾸기(knob.py) · 조정 값 표현식(motion.adjust_jsx) · 장면 일부 렌더의 이웃 장면"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
import knob  # noqa: E402
from craft.motion import adjust_jsx  # noqa: E402


def sb():
    return {"id": "t-knob", "scenes": [{"role": "hook", "sec": 3, "materials": [{"id": "a", "type": "illustration"}]},
                                      {"role": "step", "sec": 5, "materials": [{"id": "route", "type": "model3d", "args": {"gap": 2.0}}]}],
            "voice": {"speed": 1.0}}


def test_resolve_paths():
    d = sb()
    node, key = knob.resolve(d, "route.args.gap"); assert key == "gap" and node["gap"] == 2.0
    node, key = knob.resolve(d, "s2.sec"); assert node["sec"] == 5
    node, key = knob.resolve(d, "a.adjust.scale"); assert key == "scale" and isinstance(node, dict)   # 없는 adjust 는 만든다
    node, key = knob.resolve(d, "voice.speed"); assert node["speed"] == 1.0


def test_relative_values():
    assert knob.parse_value("*1.5", 2.0) == 3.0
    assert knob.parse_value("+0.5", 5) == 5.5
    assert knob.parse_value("-0.25", 1.0) == 0.75
    assert knob.parse_value("*1.2", None) == 1.2          # 처음 정하는 배수
    assert knob.parse_value("true", None) is True and knob.parse_value("파랑", None) == "파랑"


def test_set_writes_storyboard_and_log(tmp_path):
    p = tmp_path / "t-knob.json"
    p.write_text(json.dumps(sb(), ensure_ascii=False))
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "story" / "knob.py"), "set", str(p), "route.args.gap=*1.5", "a.adjust.dx=0.1", "s1.sec=+1"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(p.read_text())
    assert d["scenes"][1]["materials"][0]["args"]["gap"] == 3.0
    assert d["scenes"][0]["materials"][0]["adjust"] == {"dx": 0.1}
    assert d["scenes"][0]["sec"] == 4
    log = ROOT / "data" / "workspace" / "render" / "t-knob" / "knobs.jsonl"
    assert log.exists(); log.unlink(); log.parent.rmdir()


def test_adjust_jsx_layers_on_top():
    j = adjust_jsx("route", {"dx": 0.1, "scale": 1.2, "delay": 0.5, "opacity": 0.5}, 1000, 2000)
    assert "value + [100.0, 0.0]" in j and "1.2000" in j and "L.startTime + 0.500" in j and "value * 0.500" in j
    assert "L.parent" in j                                 # 부모가 있는 레이어(재료의 자식)에는 두 번 얹지 않는다
    assert adjust_jsx("x", {}, 100, 100) == ""


def test_sub_job_keeps_neighbors():
    from engines import Job, sub_job
    sc = [{"sec": 2, "transition": "zoom"}, {"sec": 3}, {"sec": 2}]
    job = Job(sb={"id": "t", "scenes": sc}, sb_path=Path("t.json"), engine="craft", template="Scenes", tokens={}, draft=True,
              work=ROOT / "data" / "workspace" / "tmp" / "t-sub" / "Scenes",
              scenes=[{"start": 0, "end": 2, "index": 0}, {"start": 2, "end": 5, "index": 1}, {"start": 5, "end": 7, "index": 2}])
    j2 = sub_job(job, [1])
    assert len(j2.sb["scenes"]) == 1 and len(j2.sb["_all_scenes"]) == 3
    import shutil
    shutil.rmtree(ROOT / "data" / "workspace" / "tmp" / "t-sub", ignore_errors=True)
