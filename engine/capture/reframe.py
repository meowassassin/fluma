#!/usr/bin/env python3
"""리프레이밍 — 가로 영상을 세로(9:16) 쇼츠 화면으로. 주인공(동물 · 사람)을 프레임마다 찾아 카메라가 부드럽게 따라가고,
멀리 작게 찍힌 장면은 당겨서 크게 보여 준다. 가운데만 자르면 주인공이 화면 밖으로 나가고, 위아래를 비우면 슬라이드 같다.

  python3 engine/capture/reframe.py <클립.mp4> [--out 세로.mp4] [--size 1080x1920] [--zoom 2.4] [--check 확인.png]

- 찾기: YOLOX-L(COCO, data/cache/perception/dwpose_yolox_l.onnx) — 사람 · 새 · 고양이 · 개 · 말 · 양 · 소 · 코끼리 · 곰 · 얼룩말 · 기린
- 화면 상자: 주인공들을 다 담는 상자 × zoom 배(여유) — 최소는 원본 높이의 45%(너무 당기면 화질이 깨진다), 최대는 원본 높이
- 카메라 길: 프레임별 목표를 가우시안으로 부드럽게 + 초당 이동 · 확대 속도 제한(사람 카메라처럼)
- 주인공을 못 찾은 구간은 앞뒤 값을 이어 쓰고, 끝까지 못 찾으면 움직임이 많은 곳을 따른다
- 확인 시트(--check): 원본 위에 카메라 상자를 그린 프레임 줄 — 붙인 언어 모델이 보고 판단한다
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
MODEL = ROOT / "data" / "cache" / "perception" / "dwpose_yolox_l.onnx"      # YOLOX-L(COCO, Apache-2.0) — 처음 쓸 때 받는다
MODEL_URL = "https://huggingface.co/yzd-v/DWPose/resolve/main/yolox_l.onnx"
_S: dict = {}


def _sess():
    if "s" not in _S:
        import onnxruntime as ort
        if not MODEL.exists():
            MODEL.parent.mkdir(parents=True, exist_ok=True)
            print(f"[reframe] 사물 찾기 모델 받는 중(217MB, Apache-2.0): {MODEL_URL}")
            subprocess.run(["curl", "-sfL", "-o", str(MODEL), MODEL_URL], check=True)
        _S["s"] = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _S["s"]
ANIMALS = {0: "사람", 14: "새", 15: "고양이", 16: "개", 17: "말", 18: "양", 19: "소", 20: "코끼리", 21: "곰", 22: "얼룩말", 23: "기린"}


def detect(frame: np.ndarray, thr: float = .25) -> list[tuple]:
    h, w = frame.shape[:2]; r = min(640 / h, 640 / w)
    pad = np.full((640, 640, 3), 114, np.uint8)
    pad[:int(h * r), :int(w * r)] = cv2.resize(frame, (int(w * r), int(h * r)))
    out = _sess().run(None, {"images": pad.transpose(2, 0, 1)[None].astype(np.float32)})[0][0]
    grids, strides = [], []
    for s in (8, 16, 32):
        n = 640 // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2)); strides.append(np.full((n * n, 1), s))
    g = np.concatenate(grids); st = np.concatenate(strides)
    xy = (out[:, :2] + g) * st; wh = np.exp(out[:, 2:4]) * st
    cls = out[:, 5:].argmax(1); sc = out[:, 4] * out[:, 5:].max(1)
    keep = (sc > thr) & np.isin(cls, list(ANIMALS))
    b = (np.concatenate([xy - wh / 2, xy + wh / 2], 1) / r)[keep]
    if not len(b):
        return []
    idx = cv2.dnn.NMSBoxes([[float(x0), float(y0), float(x1 - x0), float(y1 - y0)] for x0, y0, x1, y1 in b], sc[keep].tolist(), thr, .45)
    return [(*b[i], float(sc[keep][i]), ANIMALS[int(cls[keep][i])]) for i in np.array(idx).ravel()]


def plan(src: Path, zoom: float = 2.4, aspect: float = 9 / 16, step: int = 2) -> dict:
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30; n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); W = int(cap.get(3)); H = int(cap.get(4))
    cx, cy, hh, found, labels = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan), np.zeros(n, bool), []
    need = np.full(n, np.nan)
    prev = None; motion = np.zeros((n, 2))
    for i in range(n):
        ok, f = cap.read()
        if not ok:
            n = i; break
        gray = cv2.cvtColor(cv2.resize(f, (160, 90)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:                                             # 움직임 중심(못 찾을 때 대신)
            d = np.abs(gray - prev); s = d.sum()
            if s > 1e-3:
                ys, xs = np.mgrid[0:90, 0:160]; motion[i] = [(d * xs).sum() / s * W / 160, (d * ys).sum() / s * H / 90]
        prev = gray
        if i % step:
            continue
        bs = detect(f)
        ani = [b for b in bs if b[5] != "사람"]
        bs = ani or bs                                                   # 동물이 보이면 사람은 빼고(고양이 · 상대 동물이 주인공)
        if bs:
            B = np.array([b[:4] for b in bs])
            x0, y0 = B[:, :2].min(0); x1, y1 = B[:, 2:].max(0)
            cx[i], cy[i] = (x0 + x1) / 2, (y0 + y1) / 2
            hh[i] = (y1 - y0) * zoom                                           # 주인공 높이 기준(세로 화면이면 폭도 아래에서 맞춘다)
            need[i] = (x1 - x0) * 1.25                                         # 주인공들을 다 담는 데 필요한 폭
            found[i] = True; labels += [b[5] for b in bs]
    cx, cy, hh, motion, found, need = cx[:n], cy[:n], hh[:n], motion[:n], found[:n], need[:n]
    # 배치 고르기: 주인공들이 세로 화면(원본 높이 기준 폭 = H × 9/16)에 안 들어가는 프레임이 많으면 '띠' — 가로 화면을 가운데 띠로 크게, 뒤는 흐리게
    nd = need[~np.isnan(need)]
    full_w = H * aspect
    band = bool(len(nd) and (nd > full_w).mean() > .25)
    if band:
        aspect = float(np.clip(np.percentile(nd, 90) / max(1, np.nanmedian(np.where(np.isnan(hh), H, hh))), 1.0, W / H))   # 띠 비율: 필요한 폭만큼(최대 원본 비율)
    t = np.arange(n)
    for a, fb in ((cx, motion[:, 0]), (cy, motion[:, 1]), (hh, np.full(n, H))):
        good = ~np.isnan(a)
        if good.sum() >= 2:
            a[:] = np.interp(t, t[good], a[good])
        elif good.sum() == 1:
            a[:] = a[good][0]
        else:
            a[:] = np.where(fb > 0, fb, (W / 2 if a is cx else H / 2)) if a is not hh else H
    if not band:
        hh = np.maximum(hh, np.where(np.isnan(need), 0, need) / aspect)       # 세로 화면: 주인공 폭도 담기게
    hh = np.clip(hh, H * .45, min(H, W / aspect))
    sig = fps * .35                                                     # 0.35초 부드럽게(손떨림 없는 카메라)
    k = cv2.getGaussianKernel(int(sig * 6) | 1, sig).ravel()
    sm = lambda a: np.convolve(np.pad(a, len(k) // 2, mode="edge"), k, "valid")  # noqa: E731
    cx, cy, hh = sm(cx), sm(cy), sm(hh)
    vmax = W * .35 / fps                                                # 초당 화면 폭 35% 이상은 안 움직인다
    for a, lim in ((cx, vmax), (cy, vmax), (hh, H * .4 / fps)):
        for i in range(1, n):
            a[i] = a[i - 1] + np.clip(a[i] - a[i - 1], -lim, lim)
    cw = hh * aspect
    cx = np.clip(cx, cw / 2, W - cw / 2); cy = np.clip(cy, hh / 2, H - hh / 2)
    return {"fps": fps, "n": n, "W": W, "H": H, "layout": "band" if band else "fill", "aspect": round(aspect, 3), "cx": cx.tolist(), "cy": cy.tolist(), "h": hh.tolist(), "found_ratio": round(float(found[::step].mean()), 2),
            "labels": sorted(set(labels)), "zoom_in": round(float(H / np.median(hh)), 2)}


def render(src: Path, P: dict, out: Path, size=(1080, 1920)) -> Path:
    cap = cv2.VideoCapture(str(src))
    tmp = out.with_suffix(".v.mp4")
    pr = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{size[0]}x{size[1]}", "-r", str(P["fps"]), "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for i in range(P["n"]):
        ok, f = cap.read()
        if not ok:
            break
        h = P["h"][i]
        if P.get("layout") == "band":                                    # 띠: 화면 폭에 맞춘 가로 띠를 가운데(약간 위) + 뒤는 같은 영상을 크게 흐리고 어둡게
            w = h * P["aspect"]
            x0, y0 = P["cx"][i] - w / 2, P["cy"][i] - h / 2
            bh = int(size[0] / P["aspect"])
            M = np.float32([[size[0] / w, 0, -x0 * size[0] / w], [0, bh / h, -y0 * bh / h]])
            strip = cv2.warpAffine(f, M, (size[0], bh), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
            k = size[1] / P["H"]
            bg = cv2.resize(f, (int(P["W"] * k), size[1]))
            ox = (bg.shape[1] - size[0]) // 2
            bg = cv2.GaussianBlur(bg[:, ox:ox + size[0]], (0, 0), 28) * .45
            y = int(size[1] * .47 - bh / 2)
            bg[y:y + bh] = strip
            pr.stdin.write(np.clip(bg, 0, 255).astype(np.uint8).tobytes())
            continue
        w = h * size[0] / size[1]
        x0, y0 = P["cx"][i] - w / 2, P["cy"][i] - h / 2
        M = np.float32([[size[0] / w, 0, -x0 * size[0] / w], [0, size[1] / h, -y0 * size[1] / h]])
        pr.stdin.write(cv2.warpAffine(f, M, size, flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT).tobytes())
    pr.stdin.close(); pr.wait()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp), "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)], check=True)
    tmp.unlink()
    return out


def check_sheet(src: Path, P: dict, out: Path, k: int = 6) -> Path:
    cap = cv2.VideoCapture(str(src)); tiles = []
    for j in range(k):
        i = int(P["n"] * (j + .5) / k); cap.set(1, i); ok, f = cap.read()
        if not ok:
            continue
        h = P["h"][i]; w = h * P.get("aspect", 9 / 16)
        cv2.rectangle(f, (int(P["cx"][i] - w / 2), int(P["cy"][i] - h / 2)), (int(P["cx"][i] + w / 2), int(P["cy"][i] + h / 2)), (0, 255, 255), max(2, P["W"] // 300))
        tiles.append(cv2.resize(f, (384, int(384 * P["H"] / P["W"]))))
    cv2.imwrite(str(out), np.hstack(tiles))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("--out"); ap.add_argument("--size", default="1080x1920"); ap.add_argument("--zoom", type=float, default=2.4); ap.add_argument("--check")
    a = ap.parse_args()
    src = Path(a.src); out = Path(a.out) if a.out else src.with_name(src.stem + "_v.mp4")
    P = plan(src, a.zoom)
    size = tuple(int(v) for v in a.size.split("x"))
    render(src, P, out, size)
    if a.check:
        check_sheet(src, P, Path(a.check))
    print(json.dumps({"out": str(out), "layout": P["layout"], "aspect": P["aspect"], "found_ratio": P["found_ratio"], "labels": P["labels"], "zoom_in": P["zoom_in"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
