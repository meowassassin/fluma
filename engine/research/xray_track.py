#!/usr/bin/env python3
"""
개체 추적 누끼 — 분해한 쇼츠에서 사용자가 찍은 개체 하나를 시간에 따라 계속 오려 낸다.

  python3 engine/research/xray_track.py <영상 id> --t 3.2 --x 0.52 --y 0.40 [--from 2.0 --to 6.5] [--fps 12] [--key 1.0]

  --t/--x/--y : 개체를 찍은 시각(초)과 화면 위치(0~1)
  --from/--to : 따라갈 구간. 없으면 그 시각이 든 샷 전체(최대 8초)
방법 (CPU · GPU 없음, MobileSAM — 프레임당 약 2초):
  1) 찍은 프레임에서 점 하나로 개체 마스크
  2) 앞뒤 프레임마다: 광류(Farneback)로 이번 위치를 예측 → 예측 상자 · 안쪽 점 · 이전 마스크를 힌트로
     MobileSAM 이 후보 4개를 내고, 모델 확신도 × 예측과 겹치는 정도가 가장 높은 것을 고름
     → 움직임이 커도 매 프레임 경계를 새로 잡는다(광류만 쓰면 밀림)
  3) 컷 · 전환이거나 두 프레임 연속 놓치면 그 방향은 멈춤
결과: data/public/trends/xray/<id>/track/<tid>/ — f0001.png …(투명 배경, 원본 크기) · preview.webm(투명 미리보기) · cover.png · meta.json(궤적 · 상자)
참고용: 다른 사람 영상의 개체를 우리 영상에 쓰지 않는다. 움직임(궤적 · 크기 변화)을 읽는 데 쓴다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
XR = ROOT / "data" / "public" / "trends" / "xray"
MAX_SPAN = 8.0


def say(p: float, stage: str):
    print(f"@progress {p:.2f} {stage}", flush=True)


MSAM = Path.home() / ".rembg" / "models" / "mobilesam"
MSAM_URL = "https://huggingface.co/Acly/MobileSAM/resolve/main/"


class MobileSam:
    """MobileSAM ONNX (인코더 28MB · 디코더 16MB). 이전 마스크를 힌트(mask_input)로 넣을 수 있다"""

    def __init__(self):
        import urllib.request
        import onnxruntime as ort
        MSAM.mkdir(parents=True, exist_ok=True)
        for f in ("mobile_sam_image_encoder.onnx", "sam_mask_decoder_multi.onnx"):
            if not (MSAM / f).exists():
                urllib.request.urlretrieve(MSAM_URL + f, MSAM / f)
        o = ort.SessionOptions(); o.enable_cpu_mem_arena = False
        self.enc = ort.InferenceSession(str(MSAM / "mobile_sam_image_encoder.onnx"), o, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(MSAM / "sam_mask_decoder_multi.onnx"), o, providers=["CPUExecutionProvider"])

    def embed(self, img: Image.Image):
        W, H = img.size; s = 1024 / max(W, H)
        x = np.array(img.resize((round(W * s), round(H * s)), Image.BILINEAR)).astype(np.float32)
        return self.enc.run(None, {"input_image": x})[0], s, (H, W)

    def masks(self, emb, pos: list, neg: list = (), box: list | None = None, hint: np.ndarray | None = None):
        e, s, (H, W) = emb
        pts, lab = [], []
        for p in pos: pts.append(p); lab.append(1)
        for p in neg: pts.append(p); lab.append(0)
        if box: pts += [[box[0], box[1]], [box[2], box[3]]]; lab += [2, 3]
        if not box: pts.append([0, 0]); lab.append(-1)
        coords = (np.array(pts, np.float32) * s)[None]
        mi, has = np.zeros((1, 1, 256, 256), np.float32), np.zeros(1, np.float32)
        if hint is not None and hint.sum():
            import cv2
            hh, ww = round(H * s), round(W * s)
            pad = np.zeros((1024, 1024), np.float32); pad[:hh, :ww] = cv2.resize(hint.astype(np.float32), (ww, hh))
            mi[0, 0] = np.where(cv2.resize(pad, (256, 256)) > 0.5, 8.0, -8.0); has[0] = 1
        m, iou, _ = self.dec.run(None, {"image_embeddings": e, "point_coords": coords, "point_labels": np.array([lab], np.float32),
                                        "mask_input": mi, "has_mask_input": has, "orig_im_size": np.array([H, W], np.float32)})
        return [(m[0][i] > 0).astype(np.uint8) for i in range(m.shape[1])], iou[0]


def clean(mask: np.ndarray, seed: tuple[int, int] | None = None) -> np.ndarray:
    """잔 조각 · 구멍 정리. 찍은 점(seed)이 든 덩어리와 그만큼 큰 덩어리만 남김"""
    import cv2
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return m
    areas = st[1:, 4]
    keep = {i + 1 for i, a in enumerate(areas) if a >= areas.max() * 0.25}
    if seed is not None and 0 <= seed[1] < lab.shape[0] and 0 <= seed[0] < lab.shape[1] and lab[seed[1], seed[0]] > 0:
        keep.add(int(lab[seed[1], seed[0]]))
    return np.isin(lab, list(keep)).astype(np.uint8)


def inner_point(mask: np.ndarray) -> tuple[int, int] | None:
    """마스크 안쪽 깊은 점(거리 변환 최대) — 오목한 모양에서도 개체 안에 찍힌다"""
    import cv2
    if mask.sum() == 0:
        return None
    d = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(d)), d.shape)
    return int(x), int(y)


def bbox(mask: np.ndarray, pad: float = 0.0) -> list[int] | None:
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    px, py = int((x1 - x0) * pad), int((y1 - y0) * pad)
    H, W = mask.shape
    return [max(0, int(x0 - px)), max(0, int(y0 - py)), min(W - 1, int(x1 + px)), min(H - 1, int(y1 + py))]


def warp(mask: np.ndarray, prev_g: np.ndarray, cur_g: np.ndarray, with_flow: bool = False):
    """cur 의 각 화소가 prev 의 어디서 왔는지(역방향 광류)로 마스크를 옮긴다. with_flow 면 광류도 돌려준다"""
    import cv2
    flow = cv2.calcOpticalFlowFarneback(cur_g, prev_g, None, 0.5, 4, 21, 3, 5, 1.2, 0)
    H, W = mask.shape
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    out = (cv2.remap(mask.astype(np.float32), gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_LINEAR) > 0.5).astype(np.uint8)
    return (out, flow) if with_flow else out


def pts_arg(v: str | None) -> list[tuple[float, float]]:
    """"0.4,0.5;0.6,0.7" → [(0.4, 0.5), (0.6, 0.7)] (화면 비율)"""
    out = []
    for part in (v or "").split(";"):
        if "," in part:
            x, y = part.split(",", 1); out.append((min(1.0, max(0.0, float(x))), min(1.0, max(0.0, float(y)))))
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def seed_mask(sam: "MobileSam", im: Image.Image, pos: list[tuple[float, float]], neg: list[tuple[float, float]]) -> np.ndarray | None:
    """찍은 점(들)로 첫 마스크. 점 하나는 모호하다(부분 · 전체) — 첫 점을 품고 확신도가 최고와 비슷한(0.03 이내) 후보 중
    가장 큰 것 = 개체 전체. 화면 절반을 넘는 건 배경일 가능성이 높아 뺀다"""
    W, H = im.size
    P = [[int(x * W), int(y * H)] for x, y in pos]; N = [[int(x * W), int(y * H)] for x, y in neg]
    cands, conf = sam.masks(sam.embed(im), P, neg=N)
    s0 = P[0]
    ok = [i for i in range(len(cands)) if cands[i][s0[1], s0[0]] and cands[i].mean() < 0.5] or list(range(len(cands)))
    top = max(float(conf[i]) for i in ok)
    m = clean(cands[max((i for i in ok if float(conf[i]) >= top - 0.03), key=lambda i: cands[i].sum())], (s0[0], s0[1]))
    for x, y in N:   # 빼기 점이 든 덩어리는 확실히 지운다
        if 0 <= y < H and 0 <= x < W and m[y, x]:
            import cv2
            _, lab = cv2.connectedComponents(m)
            if lab[y, x] != lab[s0[1], s0[0]]:
                m[lab == lab[y, x]] = 0
    return m if m.sum() >= W * H * 0.0005 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vid")
    ap.add_argument("--t", type=float, required=True)
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--from", dest="t0", type=float)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--pos", help="더 포함할 점들 'x,y;x,y' (화면 비율, --t 시각)")
    ap.add_argument("--neg", help="빼야 할 점들 'x,y;x,y' — 개체에 붙어 함께 잡히는 책상 · 모니터 등. 시간에 따라 광류로 같이 움직인다")
    ap.add_argument("--preview", help="따라가지 않고 --t 프레임 하나만 잘라 이 PNG 로 저장(미리보기)")
    a = ap.parse_args()
    import cv2

    d = XR / a.vid
    src = d / "src.mp4"
    if not src.exists():
        sys.exit("먼저 분해(shorts_xray.py)를 해야 합니다 — 받아 둔 영상이 없습니다")
    x = json.loads((d / "xray.json").read_text(encoding="utf-8"))
    dur = x["video"]["duration"]
    shot = next((s for s in x["shots"] if s["start"] <= a.t < s["end"]), x["shots"][-1])
    t0 = a.t0 if a.t0 is not None else shot["start"]
    t1 = a.t1 if a.t1 is not None else shot["end"]
    t0, t1 = max(0.0, max(t0, a.t - MAX_SPAN / 2)), min(dur, min(t1, a.t + MAX_SPAN / 2))
    if t1 - t0 < 0.2:
        sys.exit("따라갈 구간이 너무 짧습니다")
    if a.preview:   # 한 프레임 미리보기: 사용자가 점을 더 찍어 다듬은 뒤 추적을 시작한다
        import cv2
        fr = Path(tempfile.mkdtemp()) / "p.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a.t:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=540:-2", str(fr)], check=True)
        im = Image.open(fr).convert("RGB"); W, H = im.size
        m = seed_mask(MobileSam(), im, [(a.x, a.y), *pts_arg(a.pos)], pts_arg(a.neg))
        if m is None:
            sys.exit("찍은 곳에서 개체를 찾지 못했습니다")
        Image.fromarray(np.dstack([np.array(im), m * 255]).astype(np.uint8), "RGBA").save(a.preview)
        print(json.dumps({"area": round(float(m.mean()), 4)}))
        return
    tid = f"t{int(time.time())}"
    out = d / "track" / tid
    out.mkdir(parents=True, exist_ok=True)

    say(0.03, "프레임 뽑는 중")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(src),
                        "-vf", f"fps={a.fps},scale=540:-2", str(tmp / "f%04d.png")], check=True)
        files = sorted(tmp.glob("f*.png"))
        if not files:
            sys.exit("프레임을 뽑지 못했습니다")
        rgb = [Image.open(f).convert("RGB") for f in files]
        gray = [cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY) for im in rgb]
        H, W = gray[0].shape
        n = len(rgb)
        k0 = min(n - 1, max(0, round((a.t - t0) * a.fps)))

        say(0.08, "개체 잡는 중")
        sam = MobileSam()
        seed = (int(a.x * W), int(a.y * H))
        m0 = seed_mask(sam, rgb[k0], [(a.x, a.y), *pts_arg(a.pos)], pts_arg(a.neg))
        if m0 is None:
            sys.exit("찍은 곳에서 개체를 찾지 못했습니다 — 개체 한가운데를 다시 찍어 주세요")
        # 사용자가 찍은 '빼기' 점(픽셀) — 프레임마다 광류로 옮겨 계속 '여긴 아님'으로 쓴다
        user_neg = {k0: [[float(x * W), float(y * H)] for x, y in pts_arg(a.neg)]}
        masks: list[np.ndarray | None] = [None] * n
        masks[k0] = m0
        done = 0

        def hist(img: Image.Image, m: np.ndarray):
            hsv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2HSV)
            h = cv2.calcHist([hsv], [0, 1, 2], m, [12, 6, 6], [0, 180, 0, 256, 0, 256])
            return cv2.normalize(h, h).flatten()
        ref = hist(rgb[k0], m0)   # 개체의 색 분포 — 다른 물체 · 배경으로 번진 후보를 걸러 낸다

        def negatives(b: list[int], pred: np.ndarray) -> list[list[int]]:
            """예측 상자를 넉넉히 키운 테두리의 네 변 가운데 — 개체 밖이면 '여긴 아님' 점"""
            x0, y0, x1, y1 = b; px, py = (x1 - x0) * 0.25, (y1 - y0) * 0.25
            pts = [[(x0 + x1) / 2, y0 - py], [(x0 + x1) / 2, y1 + py], [x0 - px, (y0 + y1) / 2], [x1 + px, (y0 + y1) / 2]]
            # 상자 '안쪽'에 아님 점을 찍으면, 빠르게 움직인 개체가 예측 밖으로 나간 자리(=개체 위)에 찍혀 오히려 놓친다 → 바깥 테두리만
            return [[int(x), int(y)] for x, y in pts if 0 <= x < W and 0 <= y < H and not pred[int(y), int(x)]]

        def run(order: list[int]):
            nonlocal done, ref
            prev, miss, skipped = k0, 0, False
            unverified: list[int] = []   # 모델이 확인하지 않은 프레임(건너뛰기 · 대신 채움) — 놓치고 멈추면 함께 버림
            for k in order:
                # 장면이 확 바뀌면(컷 · 전환) 같은 개체가 아니다 → 이 방향은 여기까지
                if float(np.abs(gray[k].astype(np.int16) - gray[prev].astype(np.int16)).mean()) > 38:
                    break
                pred, flow = warp(masks[prev], gray[prev], gray[k], with_flow=True)   # 광류로 예측한 이번 위치
                if pred.sum() < W * H * 0.0003:   # 화면 밖으로 나감
                    break
                # 사용자 '빼기' 점도 광류로 옮긴다(역방향 광류의 근사 역: p - flow(p)). 개체 안으로 들어온 점은 버림
                moved = []
                for x_, y_ in user_neg.get(prev, []):
                    xi, yi = int(min(W - 1, max(0, x_))), int(min(H - 1, max(0, y_)))
                    nx, ny = x_ - float(flow[yi, xi, 0]), y_ - float(flow[yi, xi, 1])
                    if 0 <= nx < W and 0 <= ny < H and not pred[int(ny), int(nx)]:
                        moved.append([nx, ny])
                user_neg[k] = moved
                # 움직임이 작으면(개체 안 광류 중앙값 < 1px) 모델을 건너뛰고 예측을 쓴다 — 단, 연속으로는 안 건너뜀(밀림 방지)
                motion = float(np.median(np.hypot(flow[..., 0], flow[..., 1])[pred > 0])) if pred.any() else 0.0
                if motion < 1.0 and not skipped and k != order[-1]:
                    masks[k] = clean(pred); prev = k; skipped = True; done += 1; unverified.append(k)
                    say(0.1 + 0.78 * done / max(1, n - 1), f"따라가는 중 ({done}/{n - 1})")
                    continue
                skipped = False
                b, p = bbox(pred, 0.12), inner_point(pred)
                # 이전 마스크를 힌트(mask_input)로 넣으면 모델이 경계를 새로 보지 않고 힌트를 베껴 오차가 쌓인다 → 상자 · 점만
                cs, cf = sam.masks(sam.embed(rgb[k]), [list(p)] if p else [], neg=negatives(bbox(pred), pred) + [[int(x_), int(y_)] for x_, y_ in moved], box=b)
                pa = max(1, int(pred.sum()))

                def score(i: int) -> float:
                    c = cs[i]; a_ = max(1, int(c.sum()))
                    size = float(np.exp(-abs(np.log(a_ / pa)) * 1.5))   # 크기가 갑자기 변한 후보는 깎음
                    look = max(0.0, float(cv2.compareHist(ref, hist(rgb[k], c), cv2.HISTCMP_CORREL)))
                    return float(cf[i]) * (0.25 + iou(c, pred)) * (0.3 + size) * (0.3 + look)
                best = max(range(len(cs)), key=score); m = clean(cs[best], p)
                ratio = m.sum() / pa
                look = max(0.0, float(cv2.compareHist(ref, hist(rgb[k], m), cv2.HISTCMP_CORREL)))
                # 놓침 판정: 예측과도 안 겹치고, 모습(색 분포)이나 크기도 다를 때만. 큰 움직임에선 광류 예측이 틀리고 모델이 맞는 경우가 많다
                lost = iou(m, pred) < 0.3 and (look < 0.55 or not 0.5 <= ratio <= 2.0)
                if lost:   # 이번엔 예측을 쓰고, 두 번 연속이면 멈춤
                    miss += 1
                    if miss >= 2:
                        for u in unverified:
                            masks[u] = None   # 마지막 확인 뒤의 프레임은 모두 버림(깨진 모양이 남지 않게)
                        break
                    m = pred; unverified.append(k)
                else:
                    miss = 0; unverified.clear()
                    ref = ref * 0.85 + hist(rgb[k], m) * 0.15   # 개체 모습이 서서히 바뀌는 것은 따라감
                masks[k] = m
                prev = k
                done += 1
                say(0.1 + 0.78 * done / max(1, n - 1), f"따라가는 중 ({done}/{n - 1})")

        run(list(range(k0 + 1, n)))
        run(list(range(k0 - 1, -1, -1)))

        say(0.88, "투명 프레임 쓰는 중")
        path, boxes, i_out = [], [], 0
        first = next(i for i, m in enumerate(masks) if m is not None)
        last = max(i for i, m in enumerate(masks) if m is not None)
        feather = lambda m: cv2.GaussianBlur((m * 255).astype(np.uint8), (3, 3), 0)   # 경계를 살짝 부드럽게
        for k in range(first, last + 1):
            m = masks[k] if masks[k] is not None else np.zeros((H, W), np.uint8)
            i_out += 1
            rgba = np.dstack([np.array(rgb[k]), feather(m)])
            Image.fromarray(rgba, "RGBA").save(out / f"f{i_out:04d}.png", optimize=False, compress_level=3)
            b = bbox(m)
            ys, xs = np.where(m > 0)
            tt = round(t0 + k / a.fps, 3)
            if b:
                path.append([tt, round(float(xs.mean()) / W, 4), round(float(ys.mean()) / H, 4), round(float(m.mean()), 4)])
                boxes.append([tt, round(b[0] / W, 4), round(b[1] / H, 4), round((b[2] - b[0]) / W, 4), round((b[3] - b[1]) / H, 4)])
        b0 = bbox(masks[k0])
        if b0:
            Image.fromarray(np.dstack([np.array(rgb[k0]), feather(masks[k0])]), "RGBA").crop((b0[0], b0[1], b0[2] + 1, b0[3] + 1)).save(out / "cover.png")

    say(0.94, "미리보기 만드는 중")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(a.fps), "-i", str(out / "f%04d.png"),
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "34", "-row-mt", "1", str(out / "preview.webm")], check=True)
    start = round(t0 + first / a.fps, 3)
    meta = {"id": tid, "vid": a.vid, "seed": {"t": a.t, "x": a.x, "y": a.y}, "from": start, "to": round(t0 + (last + 1) / a.fps, 3),
            "fps": a.fps, "frames": i_out, "w": W, "h": H, "path": path, "boxes": boxes,
            "preview": f"trends/xray/{a.vid}/track/{tid}/preview.webm", "cover": f"trends/xray/{a.vid}/track/{tid}/cover.png",
            "seq": f"trends/xray/{a.vid}/track/{tid}", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    # 움직임 요약: 이동 거리 · 크기 변화
    if len(path) > 1:
        dist = sum(((path[i][1] - path[i - 1][1]) ** 2 + (path[i][2] - path[i - 1][2]) ** 2) ** 0.5 for i in range(1, len(path)))
        meta["motion"] = {"travel": round(dist, 3), "scale": round(path[-1][3] / max(path[0][3], 1e-4), 2),
                          "dx": round(path[-1][1] - path[0][1], 3), "dy": round(path[-1][2] - path[0][2], 3)}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    say(1.0, "완료")
    print(json.dumps({"id": tid, "frames": i_out, "from": meta["from"], "to": meta["to"], "motion": meta.get("motion")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
