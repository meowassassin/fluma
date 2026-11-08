"""Blender 연결 — 앱 등록 · 재료 방법 · 스크립트 검사 · 레퍼런스 대조(앱 없이 도는 부분)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "checks"))
sys.path.insert(0, str(ROOT / "engine" / "craft" / "blender"))
import host  # noqa: E402
import refmatch  # noqa: E402
from craft import materials  # noqa: E402


def test_blender_is_an_alt_method_of_model3d():
    ms = materials.methods()["model3d"]
    assert ms[0] == "blender" and "solidcraft" in ms                    # 기본은 Blender, 예전 방식은 method: solidcraft
    ad, _ = materials.plugins()
    assert "model3d" in ad and "model3d@solidcraft" in ad
    app = json.loads((ROOT / "engine" / "craft" / "apps" / "blender" / "craft.json").read_text("utf-8"))
    assert all(b["url"].startswith("https://download.blender.org/") for b in app["direct"]["builds"].values()) and app["direct"]["sha256_url"].endswith(".sha256")


def test_script_guard_blocks_processes_network_and_secrets(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('import subprocess\nimport socket\nimport os\nos.system("x")\nopen("/home/u/.ssh/id_rsa")\ndef build(ctx):\n    pass\n', "utf-8")
    msgs = " / ".join(host.lint(bad))
    assert "subprocess" in msgs and "socket" in msgs and "os.system" in msgs and ".ssh" in msgs
    good = tmp_path / "ok.py"
    good.write_text("import fluma3d as F\ndef build(ctx):\n    F.sphere()\n", "utf-8")
    assert host.lint(good) == []
    env = host.env({"FL_X": 1})
    assert "ANTHROPIC_API_KEY" not in env and env["FL_X"] == "1"


def _sb(m, reference=("abc",)):
    return {"id": "t-refmatch", "reference": list(reference), "scenes": [{"materials": [m]}]}


def test_refmatch_flags_missing_and_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(refmatch, "ROOT", tmp_path)
    d = tmp_path / "data" / "compositions" / "t-refmatch" / "craft"
    (d / "materials" / "s01").mkdir(parents=True)
    (d / "refmatch").mkdir()
    f = d / "materials" / "s01" / "m.png"
    f.write_bytes(b"one")
    (d / "materials" / "s01" / "m.json").write_text(json.dumps({"file": str(f.relative_to(tmp_path))}), "utf-8")
    assert "ref 없음" in refmatch.status(_sb({"id": "m", "type": "model3d"}))[0][2]          # 3D 주인공 재료인데 대조 정보가 없다
    assert refmatch.status(_sb({"id": "m", "type": "model3d"}, ())) == []                    # 레퍼런스 콘티가 아니면 묻지 않는다
    sb = _sb({"id": "m", "type": "model3d", "ref": {"video": "abc", "at": [1]}})
    assert "확인 안 함" in refmatch.status(sb)[0][2]
    (d / "refmatch" / "state.json").write_text(json.dumps({"m": {"sha": refmatch._sha(f), "diff": "x"}}), "utf-8")
    assert refmatch.status(sb) == []
    f.write_bytes(b"two")                                                                    # 재료가 바뀌면 다시 확인
    assert "재료가 바뀜" in refmatch.status(sb)[0][2]


def test_method_error_lists_blender_script_rule(tmp_path):
    from craft.adapters.blender import _pbr, model3d
    with pytest.raises(RuntimeError, match="script"):
        model3d({"id": "x"}, tmp_path / "x.png", tmp_path)
    assert _pbr("#112233")["color"] == "#112233" and _pbr({"color": "#000000", "metallic": 1})["metallic"] == 1


def test_bridge_is_rebuilt_only_when_inputs_change(tmp_path, monkeypatch):
    import os
    from craft import bridge3d
    from craft.adapters import blender as ad
    monkeypatch.setattr(ad, "ROOT", tmp_path)
    (tmp_path / "x.sc").write_text("d", "utf-8")
    sp = tmp_path / "asm.json"
    sp.write_text(json.dumps({"design": "x.sc", "out_dir": "o"}), "utf-8")
    calls = []

    def fake(spec):
        calls.append(1)
        o = tmp_path / "o"; o.mkdir(exist_ok=True)
        (o / "model.glb").write_text("g", "utf-8"); (o / "assembly.json").write_text("{}", "utf-8")
    monkeypatch.setattr(bridge3d, "build", fake)
    ad.ensure_bridge(sp); ad.ensure_bridge(sp)
    assert len(calls) == 1
    os.utime(tmp_path / "x.sc", (9e9, 9e9))                    # 설계가 바뀌면 다시
    ad.ensure_bridge(sp)
    assert len(calls) == 2


@pytest.mark.skipif(not (ROOT / "tools" / "crafts" / "blender" / "installed.json").exists(), reason="Blender 가 설치되지 않음")
def test_mirror_pair_is_exact_even_after_same_pose(tmp_path):
    """같은 값을 주면 메시까지 거울 대칭이다 — 한쪽만 돌아가는 일이 구조적으로 없다"""
    import subprocess
    from craft.materials import cli
    js = tmp_path / "t.py"
    js.write_text('''
import sys, os, math
sys.path.insert(0, os.environ["FL_LIB"])
import bpy
import fluma3d as F
F.reset()
o = F.loft([F.ring(cx=0.3, z=z, rx=1 + z * 0.2, ry=0.5) for z in (0, 1, 2)], subdiv=1)
a, b = F.mirror_pair(o, loc=(-2, 0.5, 1))
F.pair_set([a, b], "rotation_euler", (0, 0, math.radians(35)))
bpy.context.view_layer.update()
two = [x for x in bpy.data.objects if x.type == "MESH"]
assert len(two) == 2 and two[0].data is two[1].data
w = lambda ob: sorted((round(-(ob.matrix_world @ v.co).x if ob is two[1] else (ob.matrix_world @ v.co).x, 4), round((ob.matrix_world @ v.co).y, 4), round((ob.matrix_world @ v.co).z, 4)) for v in ob.data.vertices)
assert w(two[0]) == w(two[1])
print("MIRROR_OK")
''', "utf-8")
    env = {**host.env({})}
    r = subprocess.run([cli("blender"), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "1", "-P", str(js)], capture_output=True, text=True, env=env, timeout=120)
    assert "MIRROR_OK" in r.stdout, (r.stdout + r.stderr)[-600:]


def test_extract_keeps_inner_links_and_drops_escaping_ones(tmp_path):
    """공유 라이브러리 링크를 버리면 앱이 실행되지 않는다(libtbb.so.12) · 밖을 가리키는 링크는 여전히 막는다"""
    import tarfile
    from craft.crafts import safe_extract
    src = tmp_path / "s"; (src / "lib").mkdir(parents=True)
    (src / "lib" / "real.so.12.1").write_text("x", "utf-8")
    (src / "lib" / "real.so.12").symlink_to("real.so.12.1")
    (src / "lib" / "evil").symlink_to("../../../../etc/passwd")
    a = tmp_path / "a.tar.xz"
    with tarfile.open(a, "w:xz") as t:
        t.add(src, arcname="app")
    out = tmp_path / "o"; out.mkdir()
    safe_extract(a, out)
    assert (out / "app" / "lib" / "real.so.12").read_text("utf-8") == "x"
    assert not (out / "app" / "lib" / "evil").is_symlink()
