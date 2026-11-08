#!/usr/bin/env python3
"""동판화 그리기 — Blender 렌더(빛 · 면 방향)를 받아 형태를 감아 도는 선을 PhotoCraft 브러시로 긋는다.
실제 판화(뒤러) 측정: 중간 톤 91% · 칸별 디테일 0.72 · 선 굵기 1.9px. 부피는 윤곽이 아니라 형태를 따라가는 수많은 선에서 나온다.

  python3 engine/craft/engrave.py <이름>_shade.png <이름>_normal.png <out.psd>
"""
from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.inkdraw import hand, strokes  # noqa: E402

PAPER, INK = "#e8d9b8", "#1b130d"


def load(f):
    a = cv2.imread(str(f), cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535
    return a[:, :, 2::-1], a[:, :, 3]


def flow(n, cross):
    nx, ny = n[:, :, 0] * 2 - 1, -(n[:, :, 1] * 2 - 1)      # 화면 좌표
    tx, ty = -ny, nx
    m = np.hypot(tx, ty) + 1e-4
    flat = m < .12                                          # 카메라를 정면으로 보는 면은 방향이 없다 — 비스듬히
    tx, ty = np.where(flat, .82, tx / m), np.where(flat, .57, ty / m)
    if cross:
        tx, ty = -ty, tx
    return cv2.GaussianBlur(tx, (0, 0), 3), cv2.GaussianBlur(ty, (0, 0), 3)


def hatch(tone, alpha, edge, tx, ty, rr, sp_min, sp_max, limit, seed_step=4):
    H, W = tone.shape
    grid = np.zeros((H, W), np.uint8)
    spacing = sp_min + (sp_max - sp_min) * np.clip((tone - .08) / max(.01, limit - .08), 0, 1)
    out = []
    seeds = [(x, y) for y in range(2, H - 2, seed_step) for x in range(2, W - 2, seed_step)]
    rr.shuffle(seeds)

    def walk(x, y, s):
        p = []
        fx, fy = None, None
        for _ in range(rr.randint(16, 40)):
            ix, iy = int(x), int(y)
            if not (2 <= ix < W - 2 and 2 <= iy < H - 2) or alpha[iy, ix] < .6 or edge[iy, ix] or tone[iy, ix] > limit or grid[iy, ix]:
                break
            dx, dy = tx[iy, ix], ty[iy, ix]
            if fx is not None and dx * fx + dy * fy < 0:
                dx, dy = -dx, -dy
            fx, fy = dx, dy
            p.append((float(x), float(y), float(.35 + .65 * (1 - tone[iy, ix]))))
            x += dx * s * 4
            y += dy * s * 4
        return p
    for x, y in seeds:
        if alpha[y, x] < .6 or tone[y, x] > limit or grid[y, x] or edge[y, x]:
            continue
        a, b = walk(x, y, 1), walk(x, y, -1)
        p = b[::-1] + a[1:]
        if len(p) < 5:
            continue
        out.append(p)
        r = float(spacing[y, x])
        for q in p:
            cv2.circle(grid, (int(q[0]), int(q[1])), int(max(1, r)), 1, -1)
    return out


def run(shade, normal, out):
    from PIL import Image
    from craft.materials import cli
    P = cli("photocraft")
    rgb, alpha = load(shade)
    n, _ = load(normal)
    tone = cv2.GaussianBlur(rgb.mean(2), (0, 0), 1.5)
    tone = np.clip((tone - np.quantile(tone[alpha > .5], .02)) / max(.01, np.quantile(tone[alpha > .5], .985) - np.quantile(tone[alpha > .5], .02)), 0, 1)
    tone = tone ** 1.35                                     # 대비: 밝은 곳은 비우고 어두운 곳은 빽빽하게
    H, W = tone.shape
    nm = cv2.GaussianBlur(n, (0, 0), 1)
    g = sum(np.abs(cv2.Sobel(nm[:, :, c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(nm[:, :, c], cv2.CV_32F, 0, 1)) for c in range(3)) + 3 * (np.abs(cv2.Sobel(alpha, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(alpha, cv2.CV_32F, 0, 1)))
    edge = (g > .38).astype(np.uint8)
    rr = random.Random(5)
    tx, ty = flow(n, False)
    ax, ay = flow(n, True)
    sets = [(hatch(tone, alpha, edge, tx, ty, rr, 2.6, 13, .80), 2.0), (hatch(tone, alpha, edge, ax, ay, rr, 3.0, 9, .34), 1.9), (hatch(tone, alpha, edge, tx * .7 + ax * .7, ty * .7 + ay * .7, rr, 3.0, 8, .16), 1.9)]
    ct = strokes((1 - edge).astype(np.float32), np.ones((H, W), np.float32), 14)[:900]
    cmds = []
    blk = cv2.GaussianBlur(((rgb.mean(2) < .045) & (alpha > .6)).astype(np.float32), (0, 0), 1.1)         # 가장 어두운 곳(눈구멍 · 깊은 그늘)은 먹으로 채운다
    if blk.max() > 0:
        from PIL import Image as _I
        ib = [int(INK[i:i + 2], 16) for i in (1, 3, 5)]
        bp = Path(out).with_suffix(".blacks.png")
        _I.fromarray(np.dstack([np.full_like(blk, c) for c in ib] + [np.clip((blk - .4) / .2, 0, 1) * 255]).astype(np.uint8), "RGBA").save(bp)
        cmds.append(("file.placeEmbedded", {"path": str(bp)}))
    cmds.append(("layer.new.layer", {"name": "ink"}))
    for lines, size in sets:
        for p in lines:
            cmds.append(("paint.stroke", {"points": hand(p, rr), "preset": "Hard Round Pressure Size", "size": size, "color": INK}))
    for p in ct:
        cmds.append(("paint.stroke", {"points": hand(p, rr), "preset": "Hard Round Pressure Size", "size": 3.4, "color": INK}))
    cs, _ = cv2.findContours((alpha > .5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)      # 바깥선은 밝은 쪽도 끊기지 않게, 그늘 쪽은 굵게
    for c in cs:
        if len(c) < 60:
            continue
        pts = [(float(q[0][0]), float(q[0][1])) for q in c[::3]]
        for i in range(0, len(pts), 60):
            seg = pts[i:i + 66]
            if len(seg) < 4:
                continue
            mx, my = seg[len(seg) // 2]
            t = float(tone[int(my), int(mx)])
            cmds.append(("paint.stroke", {"points": hand([(x, y, .5 + .5 * (1 - t)) for x, y in seg], rr), "preset": "Hard Round Pressure Size", "size": round(2.8 + 3.4 * (1 - t), 1), "color": INK}))
    print("획", len(cmds) - 1)
    n_, cur = 0, None
    while n_ < len(cmds):
        a, z = ([] if cur is None else ["--cmd", "layer.select", "--params", json.dumps({"name": "ink"})]), 0   # 다시 열면 대상 레이어를 다시 고른다
        while n_ < len(cmds) and z < 1_200_000:
            q = json.dumps(cmds[n_][1])
            a += ["--cmd", cmds[n_][0], "--params", q]
            z += len(q) + 40
            n_ += 1
        nxt = Path(out).with_suffix(".next.psd")               # --in-place 는 PSD 에 남지 않는다 — 새 파일로 쓰고 바꾼다
        b = [P, "run", "--new", json.dumps({"width": W, "height": H, "background": PAPER}), *a, "--out", str(nxt)] if cur is None else [P, "run", str(out), *a, "--out", str(nxt)]
        r = subprocess.run(b, capture_output=True, text=True, timeout=500, stdin=subprocess.DEVNULL)
        if r.returncode:
            raise SystemExit((r.stderr or r.stdout)[-400:])
        nxt.replace(out)
        cur = out
    subprocess.run([P, "convert", str(out), str(Path(out).with_suffix(".png"))], check=True, capture_output=True)
    return {"psd": str(out), "strokes": len(cmds) - 1}


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()), ensure_ascii=False))
