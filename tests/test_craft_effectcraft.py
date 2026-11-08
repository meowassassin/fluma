"""EffectCraft 움직임 단계(engine/craft/motion.py) — 내장 프리셋 · 실제 화면 다듬기 · 플러그인 계약(모르는 종류 · as · overlay · highlighted).
JSX 생성은 앱 없이, 실제 실행 · 렌더는 EffectCraft 가 설치됐을 때만."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import motion  # noqa: E402

INST = ROOT / "tools" / "crafts" / "effectcraft" / "installed.json"
HAS_APP = INST.exists()
app = pytest.mark.skipif(not HAS_APP, reason="EffectCraft 가 설치되지 않음")
Image = pytest.importorskip("PIL.Image")


def W_(text, s, e, sc=0):
    return {"text": text, "startMs": int(s * 1000), "endMs": int(e * 1000), "scene": sc}


def _png(p: Path, size, color=(30, 34, 44, 255)) -> str:
    Image.new("RGBA", size, color).save(p)
    return str(p)


def _jsx(monkeypatch, tmp_path, recs: dict, fmt="concept", direction=None, words=None, sec=4.0, n_scenes=1, elements=None):
    monkeypatch.setattr(motion, "scene_materials", lambda sid, n, sc=None: [dict(r, scene=n) for r in recs.get(n, [])])
    monkeypatch.setattr(motion, "palette_list", lambda sid: [[1, 0.84, 0.04], [1, 0.24, 0.42], [0.08, 0.78, 0.82]])
    scs = [{"role": "hook", "sec": sec, "beat": "b", "narration": "x", "materials": [{"id": r["id"]} for r in recs.get(i + 1, [])],
            "elements": elements or []} for i in range(n_scenes)]
    sb = {"id": "t-effectcraft", "format": fmt, "title": "", "direction": {"color_bg": "#101522", **(direction or {})}, "scenes": scs}
    tm = [{"index": i, "start": i * sec, "end": (i + 1) * sec, "sec": sec} for i in range(n_scenes)]
    return motion.build_jsx(sb, words or [], tm, tmp_path / "p.ecproj")


# ---------------------------------------------------------------- 앱 없이
def test_unknown_material_kind_by_hint_or_extension():
    assert motion.mat_kind({"type": "diagram", "file": "a/b.png"}) == "image"
    assert motion.mat_kind({"type": "model3d", "file": "a/b.mp4"}) == "video"
    assert motion.mat_kind({"type": "model3d", "file": "a/b.png", "as": "video"}) == "video"
    # 기본 종류는 as 힌트가 있어도 그대로(PdfCraft doc_quote 는 as=image 를 붙인다 — 확대 · 형광펜 경로를 지킨다)
    assert motion.mat_kind({"type": "doc_quote", "as": "image"}) == "doc_quote"
    assert motion.mat_kind({"type": "screen", "as": "video"}) == "screen"


def test_enter_preset_defaults_and_overrides():
    motion.DZ = motion._design.resolve({})
    assert motion.enter_preset({"type": "web"}) is None                           # 근거 없으면 전환 없이 바로 보임(craft/design.py)
    assert motion.enter_preset({"type": "web", "spec": {"enter": False}}) is None  # 콘티에서 끄기
    assert motion.enter_preset({"type": "image", "spec": {"enter": "cardFlipIn"}}) == "cardFlipIn"
    assert motion.enter_preset({"type": "web"}, {"enter": "fadeIn"}) == "fadeIn"
    assert motion.enter_preset({"type": "web"}, {"enter": {"web": "wipeInFromRight"}}) == "wipeInFromRight"
    assert motion.enter_preset({"type": "image"}, {"enter": {"web": "wipeInFromRight"}}) is None


def test_background_preset_only_from_direction():
    assert motion.bg_preset({"format": "concept"}) is None                        # 형식만으로는 배경 효과를 넣지 않는다
    assert motion.bg_preset({"format": "emotional"}) is None
    assert motion.bg_preset({"format": "concept", "direction": {"bg_preset": "blueprintGrid"}}) == "blueprintGrid"
    assert motion.bg_preset({"format": "concept", "direction": {"bg_preset": None}}) is None
    t, ef, et = motion.bg_tunes("blueprintGrid", [0.95, 0.94, 0.93], [])
    assert ["effects/#1/color", [0.95, 0.94, 0.93]] in t and ef is None           # 판 = 콘티 바탕색
    _, ef, et = motion.bg_tunes("pulseRings", [0, 0, 0], [[1, 0, 0]])
    assert (ef, et) == ("100*Math.pow", "26*Math.pow")                           # 고리 세기 절제


def test_screen_aspect_covers_frame(tmp_path):
    full = {"type": "model3d", "as": "image", "file": _png(tmp_path / "a.png", (540, 960))}
    wide = {"type": "drawing", "file": _png(tmp_path / "b.png", (1800, 640))}
    shot = {"type": "screen", "file": _png(tmp_path / "c.png", (540, 960))}
    assert motion.placement(full) == "full"           # 9:16 렌더는 화면을 덮는다
    assert motion.placement(wide) == "center"         # 가로 도면은 가운데 칸
    assert motion.placement(shot) == "full" and not motion.covers_frame(shot, 1080, 1920)   # 실제 화면은 액자(둥근 모서리)


def test_overlay_parents_layers_on_target(monkeypatch, tmp_path):
    scr = _png(tmp_path / "s.png", (1000, 1400))
    box = _png(tmp_path / "box.png", (300, 100), (255, 0, 0, 255))
    recs = {1: [{"id": "m1", "type": "screen", "key": "k", "file": scr, "spec": {}},
                {"id": "o1", "type": "overlay", "key": "k", "target": "m1",
                 "layers": [{"file": box, "box": [0.1, 0.1, 0.3, 0.1], "cue": None}, {"file": box, "box": [0.1, 0.5, 0.3, 0.1], "cue": "여기"}]}]}
    js = _jsx(monkeypatch, tmp_path, recs, words=[W_("여기", 2.5, 3.0)])
    assert "Overlay o1 1" in js and "Overlay o1 2" in js
    assert "ol.parent = tg" in js and '"Mat m1"' in js
    assert "os_.setValueAtTime(0.60" in js        # 첫 층: 대상 등장(0초) + 0.6초
    assert "os_.setValueAtTime(2.50" in js        # 둘째 층: cue 낱말 시각
    assert "roundShadow(ml" not in js              # 근거 없으면 액자 없음
    js = _jsx(monkeypatch, tmp_path, recs, words=[W_("여기", 2.5, 3.0)], direction={"frame": {"shadow": True, "round": True}})
    assert "roundShadow(ml, true, true)" in js       # 방향이 정하면 둥근 모서리 + 그림자


def test_doc_quote_highlighted_skips_fake_marker(monkeypatch, tmp_path):
    pg = _png(tmp_path / "pg.png", (1200, 1600), (255, 255, 255, 255))
    rec = {"id": "q1", "type": "doc_quote", "key": "k", "file": pg, "highlight": [[100, 200, 600, 40]], "spec": {}}
    js = _jsx(monkeypatch, tmp_path, {1: [dict(rec, highlighted=True)]})
    assert "Highlight q1" not in js and "var zk" in js       # 확대는 그대로
    js = _jsx(monkeypatch, tmp_path, {1: [rec]})
    assert "Highlight q1 0" in js


def test_next_full_screen_wipes_over_and_previous_holds(monkeypatch, tmp_path):
    a = _png(tmp_path / "a.png", (1000, 1400))
    b = _png(tmp_path / "b.png", (1000, 1400))
    recs = {1: [{"id": "a", "type": "screen", "key": "k", "file": a, "spec": {"start": 0}},
                {"id": "b", "type": "screen", "key": "k", "file": b, "spec": {"start": 2.0}}]}
    js = _jsx(monkeypatch, tmp_path, recs, direction={"enter": {"screen": "wipeInFromRight"}})
    assert 'pre(c, ml, "wipeInFromRight", 2.00, 0.6)' in js
    assert "ml.outPoint = 2.63" in js                       # 앞 화면은 닦기가 끝날 때까지 그대로(바탕색 번쩍임 없음)


def test_text_presets_title_and_emotional_subs(monkeypatch, tmp_path):
    words = [W_("짧은", 0.2, 0.6), W_("자막", 0.6, 1.0)]
    el = [{"name": "훅 제목", "what": "'첫 줄'"}]
    js = _jsx(monkeypatch, tmp_path, {}, fmt="emotional", words=words, elements=el)
    assert "textPreset(" not in js.split("function textPreset")[0] and "popIn(tl" not in js and "bgPreset(c, bgL" not in js   # 형식만으로는 효과 없음
    js = _jsx(monkeypatch, tmp_path, {}, fmt="emotional", words=words, elements=el,
              direction={"title_preset": "bounceInWords", "sub_preset": "fadeUpCharacters", "bg_preset": "bokehDrift"})
    assert 'textPreset(c, tl, "bounceInWords"' in js and 'textPreset(c, s, "fadeUpCharacters", 0.200, 0.450)' in js
    assert 'bgPreset(c, bgL, "bokehDrift"' in js
    js = _jsx(monkeypatch, tmp_path, {}, fmt="concept", words=words, elements=el, direction={"title_preset": None, "text_pop": True})
    assert "textPreset(c, s," not in js and "textPreset(c, tl" not in js and "popIn(tl" in js


# ---------------------------------------------------------------- 앱으로 실제 실행 · 렌더
def _cli() -> Path:
    return ROOT / json.loads(INST.read_text("utf-8"))["cli"]


@app
def test_presets_run_and_render(monkeypatch, tmp_path):
    """JSX 가 엔진에서 돌고(프리셋 · 마스크 · 오버레이), 렌더에 빨간 주석 상자가 대상 화면 위 제자리에 보인다"""
    scr = _png(tmp_path / "s.png", (1000, 1400), (40, 44, 56, 255))
    box = _png(tmp_path / "box.png", (300, 100), (255, 0, 0, 255))
    recs = {1: [{"id": "m1", "type": "screen", "key": "k", "file": scr, "spec": {}},
                {"id": "o1", "type": "overlay", "key": "k", "target": "m1", "layers": [{"file": box, "box": [0.0, 0.0, 0.3, 0.1], "cue": None}]}]}
    js = _jsx(monkeypatch, tmp_path, recs, fmt="concept", sec=2.0)
    jf = tmp_path / "m.jsx"
    jf.write_text(js, "utf-8")
    env = {**os.environ, "DO_NOT_TRACK": "1", "EFFECTCRAFT_FONT_DIRS": str(ROOT / "engine" / "assets" / "fonts")}
    r = subprocess.run([str(_cli()), "script", str(jf)], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0 and "실패" not in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    out = tmp_path / "f.png"
    subprocess.run([str(_cli()), "render-frame", "--project", str(tmp_path / "p.ecproj"), "--comp", "Main", "--time", "1.5", "--out", str(out)],
                   check=True, capture_output=True, env=env, timeout=120)
    im = Image.open(out).convert("RGB")
    px = im.load()
    reds = [(x, y) for x in range(0, im.width, 6) for y in range(0, im.height, 6) if px[x, y][0] > 200 and px[x, y][1] < 60]
    assert reds, "주석 상자가 보이지 않음"
    xs = [p[0] for p in reds]
    ys = [p[1] for p in reds]
    assert max(xs) < im.width * 0.5 and max(ys) < im.height * 0.5     # 대상 화면의 왼쪽 위 모서리 쪽
