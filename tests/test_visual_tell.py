import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine")); sys.path.insert(0, str(ROOT / "engine" / "checks"))
import visual_tell as vt  # noqa: E402


def _mk(tmp, monkeypatch, scenes):
    monkeypatch.setattr(vt, "ROOT", tmp)
    d = tmp / "data" / "compositions" / "x" / "scenes"; d.mkdir(parents=True)
    for i, code in enumerate(scenes, 1):
        (d / f"s{i:02d}.jsx").write_text(code, "utf-8")


def test_slop_video_is_blocked(tmp_path, monkeypatch):
    code = ("K.scene(3, ['#1d2a44', '#0b1120']); var a = K.shape('rect', 540, 400, 600, 120, {fill: '#fff', round: 30}); "
            "var b = K.shape('rect', 540, 600, 600, 120, {fill: '#fff', round: 30}); K.fx(a, 'ec.stylize.glow', {}); "
            "var me = K.image(F + 'run.anim/f000.png', 540, 1090, 170);")
    _mk(tmp_path, monkeypatch, [code] * 6)
    codes = {f["code"] for f in vt.find({"scenes": [{}] * 6}, "x") if f["block"]}
    assert {"V01", "V02", "V03", "V05", "V07", "V08"} <= codes


def test_varied_video_passes(tmp_path, monkeypatch):
    bgs = ["#f4d35e", "#7fd1ae", "#f7f1e3", "#e85d75", "#9ec5fe", "#ffb26b"]
    scenes = [f"K.scene(3, '{c}'); var me = K.image(F + 'a.anim/f000.png', {300 + 90 * i}, {700 + 120 * i}, {80 + 30 * i});" for i, c in enumerate(bgs)]
    _mk(tmp_path, monkeypatch, scenes)
    sb = {"scenes": [{"shot_fn": "충격"}] + [{}] * 5}
    assert [f for f in vt.find(sb, "x") if f["block"]] == []
