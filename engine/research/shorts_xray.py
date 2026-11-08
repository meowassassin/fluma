#!/usr/bin/env python3
"""
쇼츠 엑스레이 — 트렌드 쇼츠 한 편을 편집 요소 단위로 분해한다 (사용자가 '분해 보기'를 누를 때만).

  python3 engine/research/shorts_xray.py <영상 id 또는 URL> [--whisper base] [--keep-video]

받는 것: 480p 이하 영상 + 소리(분석 · 앱 안 재생용, data/public/trends/xray/<id>/ 에만 · 화면의 '지우기'로 삭제).
뽑는 것 (모두 CPU, 1분 쇼츠 기준 1~2분):
  - 샷: 컷 시각 · 샷마다 대표 프레임
  - 레이어: 샷마다 피사체 누끼(rembg) · 피사체를 지운 배경판(인페인팅) · 피사체 면적 · 얼굴 수
  - 등장 요소: 누끼끼리 색 분포를 비교해 같은 캐릭터 · 사물을 묶음(A · B · C …)
  - 카메라: 광류로 샷마다 고정 · 팬 · 줌인 · 줌아웃 · 흔들림
  - 글자: 프레임마다 글자 같은 영역(상자) → 자막이 뜨는 시각 · 높이
  - 소리: 음량 곡선 · 대사(faster-whisper, 단어 시각) · 박자(BPM · 박 시각) · 음악 깔림(추정) · 효과음 후보(급한 소리 변화)
  - 편집 레시피: 컷과 박자가 맞는 비율, 훅 길이, 자막 · 대사 비중 등을 한국어 문장으로
결과: data/public/trends/xray/<id>/xray.json (+ shots/ · cut/ · bg/ 이미지). 진행 상황은 '@progress 0.42 단계' 줄로 출력.
베끼기 금지: 결과는 패턴 참고용. 누끼 · 배경판을 우리 영상에 쓰지 않는다(화면에도 표시).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
OUT = ROOT / "data" / "public" / "trends" / "xray"
MAX_SEC = 180


def say(p: float, stage: str):
    print(f"@progress {p:.2f} {stage}", flush=True)


def vid_of(s: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    v = m.group(1) if m else s
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
        raise SystemExit(f"영상 id 가 올바르지 않습니다: {s}")
    return v


# ---------------------------------------------------------------- 받기 · 정보
def download(vid: str, d: Path) -> Path:
    dst = d / "src.mp4"
    if dst.exists() and dst.stat().st_size > 10_000 and (probe(dst).get("h") or 0) >= 700:
        return dst
    dst.unlink(missing_ok=True)
    url = f"https://www.youtube.com/shorts/{vid}"
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "--no-playlist",
                        # 쇼츠는 세로라 '높이'가 긴 변 — 960 이하(540×960)로 받아야 누끼가 정확하다 (480 이하면 240×426)
                        "-f", "bv*[height<=960][ext=mp4]+ba[ext=m4a]/bv*[height<=960]+ba/b[height<=960]/b",
                        "--merge-output-format", "mp4", "-o", str(d / "dl.%(ext)s"), url],
                       capture_output=True, text=True, timeout=300)
    got = sorted(d.glob("dl.*"))
    if not got:
        raise SystemExit(f"영상을 받지 못했습니다: {r.stderr.strip()[-300:]}")
    # 브라우저에서 바로 재생되게 H.264 + AAC mp4 로 맞춘다(이미 그렇다면 복사만)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(got[0]), "-t", str(MAX_SEC), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], check=True)
    for g in got:
        g.unlink(missing_ok=True)
    return dst


def probe(src: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                        "-of", "json", str(src)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    return {"duration": round(float(j["format"]["duration"]), 2), "w": v.get("width"), "h": v.get("height"),
            "fps": round(float(num) / max(1, float(den)), 2), "audio": any(s["codec_type"] == "audio" for s in j["streams"])}


# ---------------------------------------------------------------- 샷
def detect_cuts(src: Path, dur: float) -> list[float]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-vf", "select='gt(scene,0.30)',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    cuts, last = [], 0.0
    for t in (float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)):
        if t - last >= 0.25 and dur - t >= 0.25:   # 너무 짧은 샷은 앞 샷에 붙임
            cuts.append(round(t, 2)); last = t
    return cuts


def grab(src: Path, t: float, dst: Path, width: int | None = None):
    vf = ["-vf", f"scale={width}:-2"] if width else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", *vf, "-q:v", "3", str(dst)], check=True)


def small_frames(src: Path, d: Path, fps: int = 4, width: int = 270) -> list[Path]:
    d.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", f"fps={fps},scale={width}:-2", "-t", str(MAX_SEC), str(d / "f%05d.jpg")], check=True)
    return sorted(d.glob("f*.jpg"))


def hist_cuts(frames: list[Path], fps: int) -> list[float]:
    """작은 프레임끼리 색 분포가 크게 달라지는 곳 — ffmpeg 장면 감지가 놓친 컷(밝기가 비슷한 그림 전환 등)을 보충"""
    import cv2
    out, prev = [], None
    for i, p in enumerate(frames):
        im = cv2.imread(str(p))
        if im is None:
            continue
        hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1, 2], None, [12, 6, 6], [0, 180, 0, 256, 0, 256])
        h = cv2.normalize(h, h).flatten()
        g = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (32, 56)).astype(np.float32)
        if prev is not None:
            corr = cv2.compareHist(prev[0], h, cv2.HISTCMP_CORREL)
            diff = float(np.abs(g - prev[1]).mean())   # 같은 색인데 그림이 바뀐 경우
            if corr < 0.55 or diff > 38:
                out.append(round(i / fps, 2))
        prev = (h, g)
    return out


def merge_cuts(a: list[float], b: list[float], dur: float) -> list[float]:
    out = []
    for t in sorted(a + b):
        if t < 0.25 or dur - t < 0.25 or (out and t - out[-1] < 0.4):
            continue
        out.append(round(t, 2))
    return out


# ---------------------------------------------------------------- 카메라 (광류)
def camera_moves(frames: list[Path], fps: int, shots: list[dict]) -> None:
    import cv2
    grays = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frames]
    if not grays or grays[0] is None:
        return
    h, w = grays[0].shape
    ys, xs = np.mgrid[0:h:6, 0:w:6]
    cx, cy = xs - w / 2, ys - h / 2
    per = []   # (t, dx, dy, zoom, resid)
    for i in range(1, len(grays)):
        a, b = grays[i - 1], grays[i]
        if a is None or b is None:
            continue
        fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)[::6, ::6]
        fx, fy = fl[..., 0], fl[..., 1]
        dx, dy = float(np.median(fx)), float(np.median(fy))
        # 바깥으로 퍼지는 정도 = 줌 (가운데 기준 위치와 흐름의 내적)
        rr = cx * cx + cy * cy + 1e-6
        zoom = float(np.median(((fx - dx) * cx + (fy - dy) * cy) / rr)) * 100
        resid = float(np.mean(np.hypot(fx - dx, fy - dy)))
        per.append((i / fps, dx, dy, zoom, resid))
    for s in shots:
        seg = [p for p in per if s["start"] < p[0] <= s["end"]]
        if len(seg) < 2:
            s["camera"] = {"kind": "고정", "pan": [0, 0], "zoom": 0, "motion": 0}
            continue
        arr = np.array(seg)
        dx, dy, zm, rs = arr[:, 1].mean(), arr[:, 2].mean(), arr[:, 3].mean(), arr[:, 4].mean()
        jitter = float(np.std(arr[:, 1]) + np.std(arr[:, 2]))
        kind = "고정"
        if jitter > 2.2 and abs(dx) < jitter and abs(dy) < jitter:
            kind = "흔들림"
        elif abs(zm) > 0.35:
            kind = "줌인" if zm > 0 else "줌아웃"
        elif max(abs(dx), abs(dy)) > 0.6:
            kind = ("팬 →" if dx < 0 else "팬 ←") if abs(dx) >= abs(dy) else ("틸트 ↓" if dy < 0 else "틸트 ↑")
        s["camera"] = {"kind": kind, "pan": [round(float(dx), 2), round(float(dy), 2)], "zoom": round(float(zm), 2),
                       "motion": round(float(rs), 2)}


# ---------------------------------------------------------------- 글자 영역
def text_boxes(img_path: Path) -> list[list[float]]:
    """글자처럼 보이는 가로 덩어리 상자(0~1 좌표). OCR 이 아니라 '어디에 글자가 있나'만."""
    import cv2
    im = cv2.imread(str(img_path))
    if im is None:
        return []
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    H, W = g.shape
    grad = cv2.morphologyEx(g, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, W // 30), 3)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw)
    out = []
    for x, y, w, h, area in stats[1:]:
        if h < H * 0.012 or h > H * 0.09 or w < W * 0.12 or w / max(h, 1) < 2.2:
            continue
        fill = area / float(w * h)
        if fill < 0.35:
            continue
        roi = grad[y:y + h, x:x + w]
        if roi.mean() < 28:   # 가장자리가 약하면 글자가 아님
            continue
        out.append([round(x / W, 3), round(y / H, 3), round(w / W, 3), round(h / H, 3)])
    return out[:8]


def text_track(frames: list[Path], fps: int) -> tuple[list[dict], list[list]]:
    per = [text_boxes(p) for p in frames]
    # 띠(높이)마다 연속으로 보이는 구간 → 자막 이벤트
    bands = ["위", "가운데 위", "가운데", "가운데 아래", "아래"]
    events, open_ = [], {}
    for i, boxes in enumerate(per + [[]]):
        t = i / fps
        here = {}
        for b in boxes:
            k = min(4, int((b[1] + b[3] / 2) * 5))
            here.setdefault(k, b)
        for k in list(open_):
            if k not in here:
                e = open_.pop(k)
                if t - e["start"] >= 0.5:
                    e["end"] = round(t, 2); events.append(e)
        for k, b in here.items():
            if k not in open_:
                open_[k] = {"start": round(t, 2), "band": bands[k], "box": b}
    events.sort(key=lambda e: e["start"])
    return events, per


# ---------------------------------------------------------------- 레이어 (누끼 · 배경판)
_session = None
MATTE = {"model": "isnet-general-use"}


def pick_matte(vid: str) -> str:
    """그림체(2D · 픽셀)면 애니 전용 모델이 경계가 훨씬 깨끗하다. 트렌드 목록의 화풍 판별을 쓴다"""
    if os.environ.get("XRAY_MATTE"):
        return os.environ["XRAY_MATTE"]
    try:
        idx = json.loads((ROOT / "data" / "public" / "trends" / "index.json").read_text(encoding="utf-8"))
        vis = next((x.get("visual") for x in idx.get("items", []) if x.get("id") == vid), None)
    except Exception:  # noqa: BLE001
        vis = None
    return "isnet-anime" if vis in ("2d", "pixel") else "isnet-general-use"


_msam = None


def refine(im: Image.Image, mask: np.ndarray) -> np.ndarray:
    """rembg(두드러진 것 찾기)의 대충 경계를 MobileSAM 으로 다듬는다: rembg 상자 · 안쪽 점을 주고, 후보 중
    확신도 × rembg 와 겹치는 정도가 가장 높은 것. 많이 다르면(다른 물체) rembg 그대로"""
    global _msam
    import cv2
    from xray_track import MobileSam, bbox, inner_point, iou
    if _msam is None:
        _msam = MobileSam()
    b, p = bbox(mask, 0.05), inner_point(mask)
    if not b or not p:
        return mask
    cs, cf = _msam.masks(_msam.embed(im), [list(p)], box=b)
    best = max(range(len(cs)), key=lambda i: float(cf[i]) * iou(cs[i], mask))
    m = cs[best]
    if iou(m, mask) < 0.5:
        return mask
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return m


def matte(im: Image.Image) -> np.ndarray:
    global _session
    from rembg import new_session, remove
    if _session is None:
        _session = new_session(MATTE["model"])
    return (np.array(remove(im, session=_session, only_mask=True)) > 128).astype(np.uint8)


def temporal_plate(frames: list[Image.Image]) -> tuple[np.ndarray, np.ndarray] | None:
    """같은 샷의 여러 프레임에서 피사체가 비켜난 순간의 진짜 배경을 모은다(카메라가 고정일 때만 쓸 것).
    픽셀마다 '피사체가 아닌 프레임들'의 중앙값. 한 번도 안 드러난 곳은 never 마스크로 돌려준다"""
    import cv2
    if len(frames) < 3:
        return None
    arr = np.stack([np.array(f).astype(np.float32) for f in frames])           # [n, H, W, 3]
    hide = np.stack([cv2.dilate(matte(f) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) > 0 for f in frames])
    arr[hide] = np.nan
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # 한 번도 안 드러난 픽셀은 nan — 아래에서 따로 메움
        plate = np.nanmedian(arr, axis=0)
    never = np.isnan(plate).any(axis=2)
    return np.nan_to_num(plate).astype(np.uint8), never.astype(np.uint8)


def cutout(src_img: Path, cut_dst: Path, bg_dst: Path, plate_frames: list[Image.Image] | None = None) -> dict:
    import cv2
    im = Image.open(src_img).convert("RGB")
    mask = matte(im)
    if mask.mean() > 0.005:
        try:
            mask = refine(im, mask)
        except Exception as e:  # noqa: BLE001
            print(f"[누끼 다듬기] 건너뜀: {e}", file=sys.stderr)
    rgba = Image.fromarray(np.dstack([np.array(im), mask * 255]).astype(np.uint8), "RGBA")
    area = float(mask.mean())
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    parts = int(sum(1 for s in stats[1:] if s[4] > mask.size * 0.02))
    info = {"area": round(area, 3), "parts": parts, "bbox": None}
    if area > 0.005:
        ys, xs = np.where(mask > 0)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        H, W = mask.shape
        info["bbox"] = [round(x0 / W, 3), round(y0 / H, 3), round((x1 - x0) / W, 3), round((y1 - y0) / H, 3)]
        rgba.crop((x0, y0, x1 + 1, y1 + 1)).save(cut_dst)
        # 배경판: 카메라가 고정이면 여러 프레임에서 진짜 배경을 모으고, 끝까지 가려진 곳만 주변으로 메움
        bgr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        big = cv2.dilate(mask * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
        tp = temporal_plate(plate_frames) if plate_frames else None
        if tp is not None and tp[0].shape[:2] == bgr.shape[:2]:
            plate = cv2.cvtColor(tp[0], cv2.COLOR_RGB2BGR)
            hole = (tp[1] * 255).astype(np.uint8)
            plate = cv2.inpaint(plate, hole, 9, cv2.INPAINT_TELEA) if hole.any() else plate
            info["plate"] = "frames"   # 여러 프레임에서 모음
            info["plate_hidden"] = round(float(tp[1].mean()), 3)
        else:
            plate = cv2.inpaint(bgr, big, 9, cv2.INPAINT_TELEA)
            info["plate"] = "inpaint"
        cv2.imwrite(str(bg_dst), plate, [cv2.IMWRITE_JPEG_QUALITY, 85])
        # 같은 요소 묶기용 색 분포 (누끼 안쪽 HSV)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], mask, [18, 8], [0, 180, 0, 256])
        info["_hist"] = cv2.normalize(hist, hist).flatten().tolist()
    # 얼굴(실사 사람 여부)
    try:
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        g = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
        info["faces"] = int(len(casc.detectMultiScale(g, 1.15, 5, minSize=(int(g.shape[1] * 0.08),) * 2)))
    except Exception:  # noqa: BLE001
        info["faces"] = 0
    return info


def group_subjects(shots: list[dict]) -> list[dict]:
    import cv2
    groups: list[dict] = []
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for s in shots:
        h = s["subject"].pop("_hist", None)
        if h is None:
            continue
        hv = np.array(h, dtype=np.float32)
        best, score = None, 0.0
        for g in groups:
            c = float(cv2.compareHist(hv, g["_h"], cv2.HISTCMP_CORREL))
            if c > score:
                best, score = g, c
        if best is not None and score > 0.72:
            best["shots"].append(s["i"]); best["_h"] = (best["_h"] + hv) / 2
            s["subject"]["group"] = best["id"]
        elif len(groups) < len(letters):
            g = {"id": letters[len(groups)], "shots": [s["i"]], "_h": hv, "cover": s["subject"].get("cut")}
            groups.append(g); s["subject"]["group"] = g["id"]
    for g in groups:
        g.pop("_h", None)
    return groups


def palette(img: Path, k: int = 5) -> list[dict]:
    q = Image.open(img).convert("RGB").resize((96, 170)).quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal, cols = q.getpalette(), sorted(q.getcolors(), reverse=True)
    tot = sum(c for c, _ in cols) or 1
    return [{"hex": "#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]), "w": round(c / tot, 3)} for c, i in cols]


# ---------------------------------------------------------------- 소리
def load_audio(src: Path, sr: int = 22050) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-t", str(MAX_SEC), "-ac", "2", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True, check=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return a.reshape(-1, 2) if a.size else np.zeros((0, 2), np.float32)


def stft_mag(x: np.ndarray, n: int = 2048, hop: int = 512) -> np.ndarray:
    if len(x) < n:
        x = np.pad(x, (0, n - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop]
    return np.abs(np.fft.rfft(frames * np.hanning(n), axis=1)).astype(np.float32)


def tempo_beats(onset: np.ndarray, fr: float) -> tuple[float | None, float, list[float]]:
    """onset 곡선의 자기상관으로 BPM, 그 박자 격자의 위상으로 박 시각"""
    if len(onset) < fr * 4:
        return None, 0.0, []
    o = onset - onset.mean()
    ac = np.correlate(o, o, "full")[len(o) - 1:]
    lo, hi = int(fr * 60 / 180), int(fr * 60 / 70)
    if hi >= len(ac):
        return None, 0.0, []
    seg = ac[lo:hi]
    lag = lo + int(np.argmax(seg))
    conf = float(seg.max() / (np.abs(ac[1:hi]).mean() + 1e-9))
    phase = max(range(lag), key=lambda p: onset[p::lag].sum())
    beats = [round(i / fr, 3) for i in range(phase, len(onset), lag)]
    bpm = 60.0 * fr / lag
    while bpm > 150:   # 두 배로 잡힌 박(8분음표)은 한 박씩 건너 사람이 세는 박으로
        bpm /= 2; beats = beats[::2]
    return round(bpm, 1), round(conf, 2), beats


# 받아쓰기 앞 문장: 문장부호가 있는 구어 예시를 주면 받아쓰기도 마침표 · 쉼표를 찍는다(없으면 문장 경계가 사라진다)
SPEECH_PROMPT = "오늘은 이걸 해 봤는데요, 생각보다 잘 되더라고요. 여러분들도 한번 해 보시고요."


def speech(src: Path, model_name: str, lang_from: Path | None = None, prompt: str | None = None) -> list[dict]:
    """lang_from: 언어는 이 소리(원본 섞인 소리)로 판정 — 목소리만 떼어 낸 트랙은 음색이 바뀌어 언어를 잘못 짐작하기도 한다
    prompt: 앞 문장(제목 · 화면 글자 같은 고유 낱말을 넣으면 '확장 프로그램'을 '확정 프로그램'으로 잘못 듣지 않는다)"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    m = WhisperModel(model_name, device="cpu", compute_type="int8")
    # 파일 경로 대신 16kHz 소리 배열을 넘긴다 (설치된 PyAV 버전과 faster-whisper 의 파일 열기가 안 맞는 문제 회피)
    pcm = load_audio(src, 16000).mean(axis=1)
    lang = None
    if lang_from is not None:
        try:   # 받아쓰기와 같은 방식(음성 구간만)으로 판정해야 짧은 말에서도 받아쓰기 때 판정과 같아진다
            _, info = m.transcribe(load_audio(lang_from, 16000).mean(axis=1), vad_filter=True, beam_size=1, without_timestamps=True)
            lang = info.language
        except Exception:  # noqa: BLE001
            lang = None
    segs, _info = m.transcribe(pcm, language=lang, word_timestamps=True, vad_filter=True, beam_size=5,
                               initial_prompt=prompt or (SPEECH_PROMPT if lang in (None, "ko") else None))
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in (s.words or [])]})
    return out


def sound(src: Path, dur: float, segs: list[dict]) -> dict:
    sr, hop = 22050, 512
    st = load_audio(src, sr)
    if not len(st):
        return {"has_audio": False}
    mono = st.mean(axis=1)
    side = (st[:, 0] - st[:, 1]) / 2
    S = stft_mag(mono, 2048, hop)
    fr = sr / hop
    freqs = np.fft.rfftfreq(2048, 1 / sr)
    power = S ** 2
    rms = np.sqrt(power.mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    logS = np.log1p(S * 10)
    flux = np.maximum(0, np.diff(logS, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    bpm, conf, beats = tempo_beats(np.clip(flux, 0, None), fr)
    if conf < 1.6:
        bpm, beats = None, []
    # 음악 깔림(추정): 1초 창마다 — 말소리 대역(300~3400Hz) 밖 에너지 비중 · 스테레오 폭 · 꾸준함
    band_out = power[:, (freqs < 250) | (freqs > 4000)].sum(axis=1) / (power.sum(axis=1) + 1e-12)
    flat = np.exp(np.log(S + 1e-9).mean(axis=1)) / (S.mean(axis=1) + 1e-9)
    in_speech = np.zeros(len(S), bool)
    for s in segs:
        in_speech[int(s["start"] * fr):int(s["end"] * fr) + 1] = True
    music = []
    floor = np.percentile(db, 20)
    peak = np.percentile(db, 98)
    for k in range(int(np.ceil(len(S) / fr))):
        a, b = int(k * fr), int((k + 1) * fr)
        if a >= len(S):
            break
        loud = db[a:b].mean() > peak - 35
        side_r = float(np.sqrt((side[a * hop:b * hop] ** 2).mean() + 1e-12) / (np.sqrt((mono[a * hop:b * hop] ** 2).mean() + 1e-12)))
        sustained = float((db[a:b] > peak - 30).mean()) > 0.6
        tonal = float(flat[a:b].mean()) < 0.3
        # 말소리 대역 밖(저음 · 고음) 에너지 · 스테레오 폭 · 꾸준히 울림 · 음정 있는 소리 — 둘 이상이면 음악으로 봄
        score = int(band_out[a:b].mean() > 0.4) + int(side_r > 0.15) + int(sustained) + int(tonal)
        music.append(1 if loud and score >= 2 else 0)
    # 효과음 후보: 급한 변화(onset) 중 박에서 벗어나고 말소리 시작이 아닌 것
    word_starts = [w["s"] for s in segs for w in s.get("words", [])]
    peaks = [i for i in range(1, len(flux) - 1) if flux[i] > 3.0 and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    sfx = []
    for i in peaks:
        t = i / fr
        if beats and min(abs(t - b) for b in beats) < 0.06:
            continue
        if word_starts and min(abs(t - w) for w in word_starts) < 0.08:
            continue
        cen = float((freqs * S[i]).sum() / (S[i].sum() + 1e-9))
        kind = "고음 (휙 · 찰칵 · 띵)" if cen > 3500 else "저음 (쿵 · 붐)" if cen < 600 else "중음 (팝 · 탁)"
        if sfx and t - sfx[-1]["t"] < 0.2:
            continue
        sfx.append({"t": round(t, 2), "kind": kind, "strength": round(float(flux[i]), 1)})
    # 화면용 음량 곡선 (초당 20점)
    step = max(1, int(fr / 20))
    env = db[::step]
    env = np.clip((env - env.min()) / (np.ptp(env) + 1e-9), 0, 1)
    return {"has_audio": True, "bpm": bpm, "beat_conf": conf, "beats": beats[:600], "music": music,
            "sfx": sfx[:60], "envelope": [round(float(x), 3) for x in env], "envelope_hz": round(fr / step, 2)}


# ---------------------------------------------------------------- 레시피
def recipe(x: dict) -> list[str]:
    out, shots, dur = [], x["shots"], x["video"]["duration"]
    cuts = [s["start"] for s in shots[1:]]
    out.append(f"샷 {len(shots)}개 · 평균 {round(dur / max(1, len(shots)), 2)}초 — " +
               ("아주 빠른 편집" if dur / max(1, len(shots)) < 1.2 else "빠른 편집" if dur / max(1, len(shots)) < 2.5 else "느긋한 편집"))
    if cuts:
        out.append(f"첫 컷 {cuts[0]}초 — " + ("훅을 1초 안에 끊음" if cuts[0] < 1 else "첫 장면을 길게 보여 줌"))
    snd = x["sound"]
    if snd.get("bpm") and cuts:
        on = sum(1 for c in cuts if min(abs(c - b) for b in snd["beats"]) < 0.09)
        out.append(f"음악 {snd['bpm']} BPM · 컷 {len(cuts)}개 중 {on}개가 박에 맞음" + (" — 박자 편집" if on / len(cuts) > 0.5 else ""))
    if snd.get("music"):
        m = sum(snd["music"]) / max(1, len(snd["music"]))
        out.append(f"음악 깔림(추정) {round(m * 100)}%")
    if x["speech"]:
        spoken = sum(s["end"] - s["start"] for s in x["speech"])
        out.append(f"대사 {round(spoken / dur * 100)}% · {sum(len(s['text']) for s in x['speech'])}자 — " + ("말로 끌고 감" if spoken / dur > 0.6 else "말보다 화면 위주"))
    if x["text"]:
        bands = {}
        for e in x["text"]:
            bands[e["band"]] = bands.get(e["band"], 0) + e["end"] - e["start"]
        main = max(bands, key=bands.get)
        out.append(f"화면 글자 {len(x['text'])}번 · 주로 {main}" + (" · 첫 1초에 글자 등장" if x["text"][0]["start"] < 1 else ""))
    if snd.get("sfx"):
        out.append(f"효과음 후보 {len(snd['sfx'])}개 (예: {', '.join(str(s['t']) + '초' for s in snd['sfx'][:4])})")
    cams = {}
    for s in shots:
        k = s.get("camera", {}).get("kind", "고정"); cams[k] = cams.get(k, 0) + 1
    moving = {k: v for k, v in cams.items() if k != "고정"}
    if moving:
        out.append("카메라 " + " · ".join(f"{k} {v}" for k, v in sorted(moving.items(), key=lambda kv: -kv[1])))
    if x["subjects"]:
        main = max(x["subjects"], key=lambda g: len(g["shots"]))
        out.append(f"등장 요소 {len(x['subjects'])}개 · 요소 {main['id']} 가 {len(main['shots'])}개 샷에 나옴")
    faces = sum(1 for s in shots if s["subject"].get("faces"))
    out.append(f"실사 얼굴이 보이는 샷 {faces}개" if faces else "실사 얼굴 없음 (그림 · 화면 위주)")
    return out


# ---------------------------------------------------------------- 실행
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--whisper", default=os.environ.get("XRAY_WHISPER", "small"), help="음성 인식 모델(tiny · base · small · medium) · none — 한국어는 small 부터 고유 낱말을 덜 틀린다")
    a = ap.parse_args()
    vid = vid_of(a.video)
    d = OUT / vid
    d.mkdir(parents=True, exist_ok=True)
    for sub in ("shots", "cut", "bg"):
        (d / sub).mkdir(exist_ok=True)
    t0 = time.time()
    say(0.02, "영상 받는 중")
    src = download(vid, d)
    info = probe(src)
    MATTE["model"] = pick_matte(vid)
    dur = info["duration"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        say(0.12, "프레임 뽑는 중")
        fps = 4
        frames = small_frames(src, tmp / "f", fps)
        say(0.18, "샷 나누는 중")
        cuts = merge_cuts(detect_cuts(src, dur), hist_cuts(frames, fps), dur)
        bounds = [0.0, *cuts, dur]
        shots = [{"i": i, "start": round(bounds[i], 2), "end": round(bounds[i + 1], 2)} for i in range(len(bounds) - 1)]
        say(0.25, "카메라 움직임 재는 중")
        camera_moves(frames, fps, shots)
        say(0.32, "글자 자리 찾는 중")
        text_events, _per = text_track(frames, fps)
    for k, s in enumerate(shots):
        say(0.36 + 0.34 * k / max(1, len(shots)), f"레이어 분해 중 ({k + 1}/{len(shots)})")
        mid = (s["start"] + s["end"]) / 2
        key = d / "shots" / f"{k:03d}.jpg"
        grab(src, mid, key)
        s["frame"] = f"trends/xray/{vid}/shots/{key.name}"
        cut_p, bg_p = d / "cut" / f"{k:03d}.png", d / "bg" / f"{k:03d}.jpg"
        pf = None
        if s.get("camera", {}).get("kind") == "고정" and s["end"] - s["start"] >= 1.0:
            span = s["end"] - s["start"]
            pf = []
            for j in range(6):
                tj = s["start"] + span * (0.1 + 0.8 * j / 5)
                fp = d / "shots" / f"_p{k:03d}_{j}.jpg"
                grab(src, tj, fp); pf.append(Image.open(fp).convert("RGB")); fp.unlink(missing_ok=True)
        try:
            sub = cutout(key, cut_p, bg_p, pf)
        except Exception as e:  # noqa: BLE001
            sub = {"area": 0, "parts": 0, "bbox": None, "faces": 0, "error": str(e)[:200]}
        if cut_p.exists():
            sub["cut"] = f"trends/xray/{vid}/cut/{cut_p.name}"
        if bg_p.exists():
            sub["bg"] = f"trends/xray/{vid}/bg/{bg_p.name}"
        s["subject"] = sub
        s["palette"] = palette(key)
    subjects = group_subjects(shots)
    stems = None
    if info["audio"]:
        say(0.66, "목소리와 음악 나누는 중")
        try:
            import separate
            mix = separate.load(src)
            v = separate.vocals(mix, log=lambda q: say(0.66 + 0.08 * q, "목소리와 음악 나누는 중"))
            separate.save(v, d / "vocals.m4a"); separate.save(mix - v, d / "music.m4a")
            stems = {"vocals": f"trends/xray/{vid}/vocals.m4a", "music": f"trends/xray/{vid}/music.m4a"}
        except Exception as e:  # noqa: BLE001
            print(f"[음원 분리] 건너뜀: {e}", file=sys.stderr)
    segs = []
    if info["audio"] and a.whisper != "none":
        say(0.76, "대사 받아 적는 중")
        try:
            segs = speech(d / "vocals.m4a" if stems else src, a.whisper, lang_from=src)   # 음악을 뺀 목소리로 받아 적으면 더 정확
        except Exception as e:  # noqa: BLE001
            print(f"[대사] 실패: {e}", file=sys.stderr)
    say(0.88, "소리 분석 중 (박자 · 음악 · 효과음)")
    # 박자 · 음악 · 효과음은 목소리를 뺀 트랙으로(말소리가 박 · 효과음으로 잘못 잡히지 않게)
    snd = sound(d / "music.m4a" if stems else src, dur, segs) if info["audio"] else {"has_audio": False}
    x = {"id": vid, "url": f"https://www.youtube.com/shorts/{vid}", "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "video": {**info, "src": f"trends/xray/{vid}/src.mp4"}, "shots": shots, "subjects": subjects,
         "text": text_events, "speech": segs, "sound": snd, "stems": stems, "took_sec": None, "matte": MATTE["model"]}
    x["recipe"] = recipe(x)
    x["took_sec"] = round(time.time() - t0, 1)
    (d / "xray.json").write_text(json.dumps(x, ensure_ascii=False, indent=1), encoding="utf-8")
    say(1.0, "완료")
    print(json.dumps({"id": vid, "shots": len(shots), "subjects": len(subjects), "speech": len(segs), "took_sec": x["took_sec"]}, ensure_ascii=False))
    for line in x["recipe"]:
        print(" -", line)


if __name__ == "__main__":
    main()
