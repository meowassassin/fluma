"""FilmCraft — 조립(engine/craft/edit.py) 과 화면 녹화 다듬기(engine/craft/adapters/filmcraft.py).
계산(마커 · 썸네일 시각 · 내보내기 설정 · 줌 키프레임 · 속도 시각 바꾸기)은 앱 없이, 실제 내보내기는 앱이 설치됐을 때만."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from craft import edit  # noqa: E402
from craft.adapters import filmcraft as fca  # noqa: E402

HAS_APP = (ROOT / "tools" / "crafts" / "filmcraft" / "installed.json").exists()
app = pytest.mark.skipif(not HAS_APP, reason="FilmCraft 가 설치되지 않음")

SB = {"id": "t-fc", "title": "시험", "scenes": [
    {"role": "hook", "sec": 4, "narration": "findAll 한 번 불렀는데 쿼리가 백한 번 나갑니다. 왜 그럴까요?", "visual": {"primary": "백한"}},
    {"role": "step", "sec": 3, "narration": "", "caption": "fetch join 으로 한 번에"},
    {"role": "outro", "sec": 3, "narration": "저장해 두세요"}]}


# ---------------------------------------------------------------- 앱 없이
def test_markers_at_scene_boundaries_with_line_lead():
    ms = edit.markers(SB)
    assert [m["params"]["time"] for m in ms] == [0, 4 * edit.TICKS, 7 * edit.TICKS]
    assert [m["params"]["name"] for m in ms] == ["1. 훅", "2. 단계", "3. 마무리"]
    assert ms[0]["params"]["comment"].endswith("…") and len(ms[0]["params"]["comment"]) <= 29
    assert ms[1]["params"]["comment"] == "fetch join 으로 한 번에"          # 대사가 없으면 자막
    assert ms[0]["params"]["color"] == "rose" and ms[-1]["params"]["color"] == "green"


def test_thumb_time_hook_middle_or_key_word():
    assert edit.thumb_time(SB) == 2.0
    words = [{"text": " 쿼리가", "startMs": 1500}, {"text": " 백한", "startMs": 1900}, {"text": " 백한", "startMs": 5000}]
    assert edit.thumb_time(SB, words) == 2.6
    assert edit.thumb_time({"scenes": []}) == 0.0


def test_export_settings_skip_loudness_only_when_already_near_minus14():
    assert edit.export_settings(1080, 1920, None) == {}
    assert edit.export_settings(1080, 1920, -14.3) == {"effects": {"loudness": {"enabled": False}}}
    assert edit.export_settings(1080, 1920, -19.0) == {}
    # SoundCraft 가 일부러 키우지 않은 소리(효과음만 · 사람이 고친 세션: target_lufs null)는 정규화하지 않는다
    assert edit.export_settings(1080, 1920, -35.7, keep_level=True) == {"effects": {"loudness": {"enabled": False}}}
    st = edit.export_settings(1080, 1080, None)
    assert st["frameSize"] == [1080, 1080] and st["bitrateKbps"] < 12000


def test_zoom_keys_center_box_and_stay_inside_frame():
    keys = fca.zoom_keys([{"t": 2, "box": [0.5, 0.5, 0.5, 0.25], "dur": 1}], 1000, 2000)
    assert [round(k[0], 2) for k in keys] == [2, 2.3, 3.3, 3.6]
    assert keys[0][1] == 100.0 and keys[-1][1] == 100.0
    t, s, (px, py) = keys[1]
    k = s / 100
    assert abs(k - 1.76) < 0.01
    # 화면 밖이 보이지 않는다: 클립 가장자리가 화면 안쪽으로 들어오지 않음
    assert px - k * 500 <= 0 and px + k * 500 >= 1000 and py - k * 1000 <= 0 and py + k * 1000 >= 2000
    # 이어지는 줌은 100% 로 돌아가지 않고 바로 옮긴다
    two = fca.zoom_keys([{"t": 1, "box": [0, 0, 0.5, 0.5], "dur": 1}, {"t": 2.5, "box": [0.5, 0.5, 0.5, 0.5], "dur": 1}], 1000, 1000)
    assert [round(k[0], 2) for k in two] == [1, 1.3, 2.3, 2.5, 2.8, 3.8, 4.1]
    assert all(a[0] < b[0] for a, b in zip(two, two[1:]))


def test_speed_ranges_and_remap():
    rs = fca.speed_ranges([{"from": 6, "to": 8, "x": 2}, {"from": 2, "to": 4, "x": 4}, {"from": 3, "to": 5, "x": 2}, {"from": 9, "to": 9, "x": 3}])
    assert rs == [(2.0, 4.0, 4.0), (6.0, 8.0, 2.0)]
    assert fca.remap(1.0, rs) == 1.0
    assert fca.remap(3.0, rs) == 2.25
    assert fca.remap(5.0, rs) == 3.5
    assert fca.remap(8.0, rs) == 5.5


def test_blur_boxes_relative_or_pixels():
    ls = fca.blur_lines(9, [[0.1, 0.1, 0.5, 0.1], {"box": [100, 200, 300, 50], "amount": 80}], 1000, 2000)
    assert [x["id"] for x in ls] == ["effects.apply", "effects.setParam", "masks.add"] * 2
    assert ls[2]["params"]["effect"] == 3 and ls[5]["params"]["effect"] == 4
    assert ls[2]["params"]["center"] == [350.0, 300.0] and ls[4]["params"]["value"] == 80
    assert ls[5]["params"]["center"] == [250.0, 225.0]


def test_trim_without_fields_does_nothing(tmp_path):
    assert fca.trim({"id": "m1", "type": "screen"}, tmp_path / "m1.mp4", tmp_path) is None


# ---------------------------------------------------------------- 앱으로
def _clip(p: Path, sec: float = 4.0):
    """프레임마다 시각이 찍힌 540×960 녹화(위에 '비밀' 줄, 가운데 초록 버튼)"""
    font = next((f for f in ("/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Bold.ttc",
                             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc") if Path(f).exists()), None)
    ff = f"fontfile={font}:" if font else ""
    vf = (f"drawbox=x=30:y=150:w=330:h=40:color=black:t=fill,drawbox=x=30:y=450:w=480:h=80:color=0x2da44e:t=fill,"
          f"drawtext={ff}text='%{{pts\\:flt}}':x=30:y=800:fontsize=60:fontcolor=black")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=white:s=540x960:r=30:d={sec}", "-vf", vf,
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"ffmpeg 시험 영상 실패: {r.stderr[-200:]}")


def _dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout.strip())


def _frame(p: Path, t: float, out: Path):
    from PIL import Image
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(p), "-frames:v", "1", str(out)], check=True)
    return Image.open(out).convert("RGB")


@app
def test_trim_zoom_blur_speed(tmp_path):
    src = tmp_path / "m5.mp4"
    _clip(src)
    m = {"id": "m5", "type": "screen", "zoom": [{"t": 0.5, "box": [0.05, 0.46, 0.9, 0.1], "dur": 0.8}],
         "blur": [[0.05, 0.15, 0.62, 0.05]], "speed": [{"from": 2.0, "to": 4.0, "x": 4}]}
    r = fca.trim(m, src, tmp_path, info={"steps": [{"t": 1.0, "t_end": 3.0, "label": "버튼"}]})
    assert r and Path(r["file"]).exists() and r["app"] == "filmcraft" and r["as"] == "video"
    assert (tmp_path / "m5.fcproj").exists() and r["editable_hash"]
    assert abs(_dur(Path(r["file"])) - 2.5) < 0.15                       # 2초 + 2초/4
    assert r["steps"][0]["t"] == 1.0 and r["steps"][0]["t_end"] == 2.25
    plain, zoomed = _frame(Path(r["file"]), 0.2, tmp_path / "a.png"), _frame(Path(r["file"]), 1.2, tmp_path / "b.png")
    # 줌: 초록 버튼 높이가 커진다
    green = lambda im: sum(1 for y in range(0, 960, 2) if (lambda p: p[1] > 140 and p[0] < 90)(im.getpixel((270, y))))  # noqa: E731
    assert green(zoomed) > green(plain) * 1.1
    # 흐림: 검은 줄 가장자리가 번진다(회색 픽셀이 생김)
    row = [plain.getpixel((x, 170))[0] for x in range(0, 540)]
    assert any(40 < v < 215 for v in row[340:400])


@app
def test_assemble_markers_thumb_and_loudness_skip(tmp_path, monkeypatch):
    monkeypatch.setattr(edit, "ROOT", tmp_path)
    v = tmp_path / "v.mp4"
    _clip(v, 10.0)
    a = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10:sample_rate=48000",
                    "-af", "volume=-20dB", "-ac", "2", str(a)], check=True)
    cj = tmp_path / "data" / "compositions" / "t-fc" / "craft" / "craft.json"
    cj.parent.mkdir(parents=True)
    cj.write_text(json.dumps({"audio": {"lufs": -14.1}}))
    out = edit.assemble(SB, v, a, tmp_path / "out.mp4", width=540, height=960)
    assert out and out.exists()
    ed = json.loads(cj.read_text())["edit"]
    assert ed["export"]["loudness"] == "skip"
    csv = (tmp_path / ed["markers"]).read_text("utf-8")
    assert "1. 훅" in csv and "2. 단계" in csv and "3. 마무리" in csv
    from PIL import Image
    assert Image.open(tmp_path / ed["thumb"]["file"]).size == (540, 960)
    w = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True).stdout.strip()
    assert w == "540,960"
