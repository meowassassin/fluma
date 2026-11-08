#!/usr/bin/env python3
"""실사 영상 개체의 주인공을 따라간다 — 가로 영상을 세로로 자동 재구성 · 이름표(글자 · 대역)를 주인공에 붙이기.

  python3 engine/capture/footage_track.py <id> <footage-node> --bx 0.5 --by 0.4 --lt 1.2 --mode reframe
  python3 engine/capture/footage_track.py <id> <footage-node> --bx 0.5 --by 0.4 --lt 1.2 --mode follow --target <node>

  --bx/--by : 주인공을 찍은 자리(영상 개체 상자 안 0~1) · --lt : 찍은 시각(장면 안 초)
  reframe   : 영상 개체를 원본 비율 그대로 화면 높이에 맞추고, 주인공이 늘 가운데 오도록 가로 이동 키를 단다(장면 칸이 바깥을 자름)
  follow    : 대상 개체(이름표 · 대역)가 주인공 머리 위를 따라다니도록 위치 키를 단다
방법: 영상 프레임(30fps 로 풀어 둔 것)을 초당 6장 — MobileSAM(점 · 상자 · 이전 마스크 힌트) + 광류 예측 (engine/research/xray_track.py 와 같은 부품)
고치기는 scene_graph.py patch --actor previs (자리 · 키 칸 — 사용자가 잠근 개체는 거절된다)
진행: '@progress 0.42 단계' 줄 · 마지막 줄 JSON
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from xray_track import MobileSam, bbox, clean, inner_point, iou, say, warp  # noqa: E402

W, H = 1080, 1920
TRACK_FPS = 6


def find(g, nid):
    for si, sc in enumerate(g["scenes"]):
        for ni, n in enumerate(sc.get("nodes", [])):
            if n.get("id") == nid:
                return si, ni, n
    sys.exit(f"노드 없음: {nid}")


def gray(im: Image.Image, w=320) -> np.ndarray:
    s = w / im.width
    return np.array(im.convert("L").resize((w, max(8, round(im.height * s)))))


def track(frames: list[Path], i0: int, seed: tuple[float, float], log) -> dict[int, tuple[float, float, float]]:
    """frames[i0] 의 seed(0~1)에서 시작해 앞뒤로 → {프레임 번호: (cx, cy, 높이)} (0~1)"""
    import cv2
    sam = MobileSam()
    im0 = Image.open(frames[i0]).convert("RGB"); Wf, Hf = im0.size
    p0 = [int(seed[0] * Wf), int(seed[1] * Hf)]
    cands, conf = sam.masks(sam.embed(im0), [p0])
    ok = [i for i in range(len(cands)) if cands[i][p0[1], p0[0]] and cands[i].mean() < 0.5] or list(range(len(cands)))
    top = max(float(conf[i]) for i in ok)
    m0 = clean(cands[max((i for i in ok if float(conf[i]) >= top - 0.03), key=lambda i: cands[i].sum())], tuple(p0))
    out = {}

    def put(i, m):
        b = bbox(m)
        if b: out[i] = ((b[0] + b[2]) / 2 / Wf, (b[1] + b[3]) / 2 / Hf, (b[3] - b[1]) / Hf)

    put(i0, m0)
    total = len(frames); done = 0
    for step in (1, -1):
        m, prev = m0, im0; lost = 0
        i = i0 + step
        while 0 <= i < len(frames):
            cur = Image.open(frames[i]).convert("RGB")
            g0, g1 = gray(prev), gray(cur)
            small = cv2.resize(m, (g0.shape[1], g0.shape[0]), interpolation=cv2.INTER_NEAREST)
            pred = cv2.resize(warp(small, g0, g1), (Wf, Hf), interpolation=cv2.INTER_NEAREST)
            b, pt = bbox(pred, 0.1), inner_point(pred)
            if not b or not pt:
                break
            cs, cf = sam.masks(sam.embed(cur), [list(pt)], box=b, hint=pred)
            j = max(range(len(cs)), key=lambda k: float(cf[k]) * (0.3 + iou(cs[k], pred)))
            nm = clean(cs[j], pt)
            if iou(nm, pred) < 0.15 or nm.sum() < Wf * Hf * 0.0005:
                lost += 1; nm = pred
                if lost >= 2:
                    break
            else:
                lost = 0
            put(i, nm); m, prev = nm, cur; i += step
            done += 1; say(0.1 + 0.8 * done / total, f"따라가는 중 {done}/{total}")
    return out


def smooth(vals: list[float], k: int = 5) -> list[float]:
    if len(vals) < 3:
        return vals
    a = np.array(vals, float); pad = np.pad(a, (k // 2, k // 2), mode="edge")
    return list(np.convolve(pad, np.ones(k) / k, mode="valid"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id"); ap.add_argument("node")
    ap.add_argument("--bx", type=float, required=True); ap.add_argument("--by", type=float, required=True)
    ap.add_argument("--lt", type=float, default=None)
    ap.add_argument("--mode", choices=["reframe", "follow"], default="reframe")
    ap.add_argument("--target")
    a = ap.parse_args()
    gp = ROOT / "data" / "scenes" / f"{a.id}.scene.json"
    g = json.loads(gp.read_text(encoding="utf-8"))
    si, ni, n = find(g, a.node)
    if n.get("kind") not in ("footage", "element"):
        sys.exit("실사 영상 개체(footage)만 따라갈 수 있습니다")
    src = n.get("src") or (g.get("assets") or {}).get(n.get("asset"), {}).get("src")
    sdir = ROOT / "data" / "public" / src
    meta = json.loads((sdir / "meta.json").read_text(encoding="utf-8"))
    fps, nfr = meta.get("fps", 30), meta["frames"]
    fw, fh = meta.get("width") or 1920, meta.get("height") or 1080
    sec = float(g["scenes"][si]["end"]) - float(g["scenes"][si]["start"])
    t_in, start, end = float(n.get("in") or 0), float(n.get("start") or 0), float(n.get("end") or sec)
    ft = lambda lt: t_in + (lt - start)   # 장면 안 시각 → 원본 시각
    lt0 = a.lt if a.lt is not None else start
    # 따라갈 프레임: 개체가 보이는 구간을 초당 6장
    lts = [round(start + k / TRACK_FPS, 3) for k in range(int((end - start) * TRACK_FPS) + 1)]
    idx = [min(nfr, max(1, round(ft(t) * fps) + 1)) for t in lts]
    frames = [sdir / f"f{i:0{meta.get('pad', 5)}d}.{meta.get('ext', 'jpg')}" for i in idx]
    i0 = min(range(len(lts)), key=lambda k: abs(lts[k] - lt0))
    # 찍은 자리(상자 안 0~1) → 원본 프레임 안 0~1 (cover · contain 맞춤 반영)
    b = n.get("box") or {"x": 0, "y": 0, "w": W, "h": H}
    bw, bh = b.get("w", W), b.get("h", H)
    sc = (max if (n.get("fit") or "cover") == "cover" else min)(bw / fw, bh / fh)
    dw, dh = fw * sc, fh * sc; ox, oy = (bw - dw) / 2, (bh - dh) / 2
    seed = ((a.bx * bw - ox) / dw, (a.by * bh - oy) / dh)
    if not (0 <= seed[0] <= 1 and 0 <= seed[1] <= 1):
        sys.exit("찍은 자리가 영상 밖입니다")
    say(0.05, "주인공 찾는 중")
    tr = track(frames, i0, seed, print)
    ks = sorted(tr)
    if len(ks) < 2:
        sys.exit("주인공을 따라가지 못했습니다 — 주인공 한가운데를 다시 찍어 보세요")
    cx = smooth([tr[k][0] for k in ks]); cy = smooth([tr[k][1] for k in ks]); hh = smooth([tr[k][2] for k in ks])
    times = [lts[k] for k in ks]
    P = f"/scenes/{si}/nodes/{ni}"
    if a.mode == "reframe":
        # 원본 비율 그대로 화면 높이에 맞춘 상자 → 주인공 가로 위치가 화면 가운데(540)에 오도록 x 키
        dw2 = H * fw / fh
        nb = {"x": round((W - dw2) / 2), "y": 0, "w": round(dw2), "h": H}
        # x 키(상자 기준 이동) = 화면 가운데 - 주인공 화면 위치. 영상 가장자리가 화면 안으로 들어오지 않게 제한
        lo, hi = W - (nb["x"] + dw2), -nb["x"]
        keys = [{"t": t, "x": round(max(lo, min(hi, W / 2 - (nb["x"] + x * dw2)))) if dw2 > W else 0, "y": 0, **({"ease": "linear"} if i else {})}
                for i, (t, x) in enumerate(zip(times, cx))]
        ops = [{"op": "replace" if "box" in n else "add", "path": f"{P}/box", "value": nb},
               {"op": "replace" if "keys" in n else "add", "path": f"{P}/keys", "value": keys}]
        note = f"세로 재구성: 키 {len(keys)}개 · {times[0]:.1f}~{times[-1]:.1f}초"
    else:
        if not a.target:
            sys.exit("--target 이 필요합니다")
        tsi, tni, tn = find(g, a.target)
        if tsi != si:
            sys.exit("같은 장면의 개체만 붙일 수 있습니다")
        # 주인공 화면 위치: 영상 개체 상자(키 무시 — 재구성 키가 있으면 그 이동도 더함)
        fkeys = n.get("keys") or []
        def fx_at(t):
            xs = [(k["t"], k.get("x", 0)) for k in fkeys if "x" in k]
            if not xs: return 0
            if t <= xs[0][0]: return xs[0][1]
            if t >= xs[-1][0]: return xs[-1][1]
            for (t1, x1), (t2, x2) in zip(xs, xs[1:]):
                if t1 <= t <= t2: return x1 + (x2 - x1) * (t - t1) / max(1e-3, t2 - t1)
            return 0
        tb = tn.get("box") or {}
        tw = tb.get("w", 600); base_cx = tb.get("x", 0) + tw / 2; base_y = tb.get("y", 0)
        keys = []
        for i, (t, x, y, h_) in enumerate(zip(times, cx, cy, hh)):
            sx = b.get("x", 0) + ox + x * dw + fx_at(t)
            top = b.get("y", 0) + oy + (y - h_ / 2) * dh
            keys.append({"t": t, "x": round(sx - base_cx), "y": round(top - 110 - base_y), **({"ease": "linear"} if i else {})})
        ops = [{"op": "replace" if "keys" in tn else "add", "path": f"/scenes/{tsi}/nodes/{tni}/keys", "value": keys}]
        note = f"따라붙이기: {tn.get('label') or tn['id']} 키 {len(keys)}개"
    tmp = ROOT / "data" / "workspace" / "tmp" / f"track-{a.id}-{a.node}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(ops), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "core" / "scene_graph.py"), "patch", a.id, str(tmp), "--actor", "previs"], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        sys.exit(f"설계도에 넣지 못했습니다: {r.stderr.strip() or r.stdout.strip()}")
    say(1.0, "끝")
    print(json.dumps({"ok": True, "mode": a.mode, "keys": len(keys), "tracked": len(ks), "of": len(lts), "note": note}, ensure_ascii=False))


if __name__ == "__main__":
    main()
