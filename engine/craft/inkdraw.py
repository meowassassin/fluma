#!/usr/bin/env python3
"""먹선 드로잉 — 실제 대상의 명암 구조에서 획을 찾아 PhotoCraft 브러시로 한 획씩 긋는다(필압 · 굵기 변화 · 붓 끝).
곡선을 상상해 쓰면 기계적이어서 슬롭이 된다. 이 도구는 '어디에 선이 있는가'를 대상에서 읽고, '어떻게 긋는가'를 붓으로 실행한다. 레이어 PSD 가 남는다.

  python3 engine/craft/inkdraw.py <투명 PNG> <out.psd> [--detail 0.6] [--paper "#e6d6b4"] [--ink "#1b130d"] [--wash "#8a5a33"] [--size 1400]
결과: <out>.psd(paper · wash · ink 레이어) · <out>.png(종이 위) · <out>_cut.png(종이 없이, 인물만)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401


def xdog(g: np.ndarray, s: float = 1.6, k: float = 1.6, tau: float = 0.985, eps: float = -0.02, phi: float = 90) -> np.ndarray:
    """XDoG — 사진의 형태 경계를 선화처럼 뽑는다(Winnemöller 2012)"""
    import cv2
    a, b = cv2.GaussianBlur(g, (0, 0), s), cv2.GaussianBlur(g, (0, 0), s * k)
    d = a - tau * b
    return np.where(d >= eps, 1.0, 1.0 + np.tanh(phi * (d - eps)))


def strokes(line: np.ndarray, weight: np.ndarray, min_len: int) -> list[list[tuple[float, float, float]]]:
    """선 영역 → 뼈대 → 끝점에서 걸어가며 획으로"""
    from skimage.morphology import remove_small_objects, skeletonize
    sk = skeletonize(remove_small_objects(line < 0.5, 24))
    H, W = sk.shape
    pts = {(int(y), int(x)) for y, x in zip(*np.nonzero(sk))}
    N = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def nb(p):
        return [(p[0] + a, p[1] + b) for a, b in N if (p[0] + a, p[1] + b) in pts]
    ends = [p for p in pts if len(nb(p)) == 1]
    out = []
    for start in ends + sorted(pts):
        if start not in pts:
            continue
        cur, path, pd = start, [], (0.0, 0.0)
        while cur:
            path.append(cur)
            pts.discard(cur)
            opts = nb(cur)
            if not opts:
                break
            cur = max(opts, key=lambda q: (q[0] - path[-1][0]) * pd[0] + (q[1] - path[-1][1]) * pd[1])     # 방향을 유지
            pd = (0.7 * pd[0] + 0.3 * (cur[0] - path[-1][0]), 0.7 * pd[1] + 0.3 * (cur[1] - path[-1][1]))
        if len(path) >= min_len:
            out.append([(x, y, float(weight[y, x])) for y, x in path[::3]])
    return sorted(out, key=len, reverse=True)


def hand(path, rr: random.Random):
    """필압: 들어가며 눌렀다 빠진다. 손떨림은 길게 흔들리는 저주파만 — 지글지글한 고주파는 가짜 티가 난다"""
    n = len(path)
    ph, amp = rr.uniform(0, 6.28), rr.uniform(.4, 1.4)
    o = []
    for i, (x, y, w) in enumerate(path):
        t = i / max(1, n - 1)
        pr = math.sin(math.pi * min(1, t * 1.05)) ** 0.55 * (.45 + .55 * w)
        wob = amp * math.sin(ph + t * rr.uniform(5, 5.2))
        o.append([round(x + wob, 1), round(y - wob * .6, 1), round(max(.08, pr), 3)])
    return o


def run(src: Path, out: Path, detail=.6, paper="#e6d6b4", ink="#1b130d", wash="#a8835a", size=1400, shade=.45, accents=None, wash_a=0, contour=True, blacks=0.0) -> dict:
    import cv2
    from PIL import Image
    from craft.materials import cli
    P = cli("photocraft")
    work = out.parent
    im = Image.open(src).convert("RGBA")
    s = size / max(im.size)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    W, H = im.size
    n = np.asarray(im).astype(np.float32) / 255
    a = n[:, :, 3]
    bg = np.ones_like(a) * .75
    g = (n[:, :, :3].mean(2) * a + bg * (1 - a)).astype(np.float32)
    g = cv2.createCLAHE(2.5, (8, 8)).apply((g * 255).astype(np.uint8)).astype(np.float32) / 255
    sig = (1.2 + 1.8 * (1 - detail)) * size / 1400
    want = .10 + .08 * detail                        # 원본 대비가 달라도 선 밀도는 같게 — 낮은 대비의 대리석도 잡힌다
    lo, hi = -.12, .03
    for _ in range(9):
        eps = (lo + hi) / 2
        line = xdog(g, s=sig, eps=eps)
        cover = float(((line < .5) & (a > .5)).sum()) / max(1, int((a > .5).sum()))
        lo, hi = (eps, hi) if cover < want else (lo, eps)
    dark = 1 - cv2.GaussianBlur(g, (0, 0), 6)
    ss = strokes(line * (a > .3) + (a <= .3), np.clip(dark * 1.5, 0, 1), int(10 + 22 * (1 - detail)))[:int(500 + 900 * detail)]
    # 윤곽: 몸 바깥선은 굵게 한 번 더
    cs, _ = cv2.findContours((a > .5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    outer = [[(float(p[0][0]), float(p[0][1]), .8) for p in c[::4]] for c in cs if len(c) > 80]
    if not contour:                                   # 회화처럼 대상 경계가 그림 안에 있으면 외곽선을 두르지 않는다
        outer = []
    rr = random.Random(7)
    fg = work / f"{out.stem}.in.png"
    Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8)).convert("RGB").save(fg)
    mask = work / f"{out.stem}.mask.png"
    Image.fromarray((a * 255).astype(np.uint8)).save(mask)
    wimg = work / f"{out.stem}.wash.png"
    # 음영: 큰 형태의 그늘 한 겹(붓으로 한 번 칠한 듯)만. 세부 명암은 아래 해칭이 맡는다
    w0 = cv2.GaussianBlur(g, (0, 0), 24 * size / 1400)
    t0 = float(np.quantile(w0[a > .5], shade)) if (a > .5).any() else .4
    lv = np.clip((t0 - w0) / .012, 0, 1).astype(np.float32)
    lv = cv2.GaussianBlur(lv, (0, 0), 1.6) * cv2.GaussianBlur(a, (0, 0), 1.5)
    rgb = tuple(int(wash[i:i + 2], 16) for i in (1, 3, 5))
    wa = np.dstack([np.full_like(lv, c) for c in rgb] + [lv * wash_a]).astype(np.uint8)
    Image.fromarray(wa, "RGBA").save(wimg)
    cmds = [{"command": "layer.setProps", "params": {"name": "paper"}},
            {"command": "edit.fill", "params": {"contents": "color", "color": paper}},
            {"command": "layer.new.layer", "params": {"name": "tooth"}},
            {"command": "edit.fill", "params": {"contents": "color", "color": "#808080"}},
            {"command": "filter.noise.addNoise", "params": {"amount": 9, "distribution": "gaussian", "monochromatic": True}},
            {"command": "filter.blur.gaussianBlur", "params": {"radius": .7}},
            {"command": "layer.setProps", "params": {"blend": "Overlay", "opacity": .45}},
            {"command": "file.placeEmbedded", "params": {"path": str(wimg)}},
            {"command": "layer.setProps", "params": {"name": "wash", "blend": "Multiply", "opacity": .85}},
            {"command": "layer.new.layer", "params": {"name": "ink"}}]
    if blacks:                                        # 가장 어두운 곳을 먹으로 채운다 — 판화 · 잉킹의 무게
        b0 = cv2.GaussianBlur(g, (0, 0), 2.2 * size / 1400)
        tb = float(np.quantile(b0[a > .5], blacks))
        bm = cv2.GaussianBlur(((b0 < tb) & (a > .5)).astype(np.float32), (0, 0), 1.2)
        bm = np.clip((bm - .42) / .16, 0, 1)
        ib = tuple(int(ink[i:i + 2], 16) for i in (1, 3, 5))
        bimg = work / f"{out.stem}.blacks.png"
        Image.fromarray(np.dstack([np.full_like(bm, c) for c in ib] + [bm * 255]).astype(np.uint8), "RGBA").save(bimg)
        cmds.insert(-1, {"command": "file.placeEmbedded", "params": {"path": str(bimg)}})
        cmds.insert(-1, {"command": "layer.setProps", "params": {"name": "blacks"}})
    base = W / 1400
    hatch_cmds = []
    for layer_q, ang, step in ((.34, -38, 13), (.16, 28, 15)):            # 어두운 곳은 한 겹 더 — 펜 드로잉의 교차 해칭
        tq = float(np.quantile(cv2.GaussianBlur(g, (0, 0), 5)[a > .5], layer_q))
        dk = cv2.GaussianBlur(g, (0, 0), 5) < tq
        c_, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        for off in np.arange(-max(W, H) * 1.3, max(W, H) * 1.3, step * base):
            run_, t = [], -max(W, H) * 1.3
            while t < max(W, H) * 1.3:
                x = W / 2 + c_ * t - s_ * off
                y = H / 2 + s_ * t + c_ * off
                on = 0 <= int(x) < W and 0 <= int(y) < H and dk[int(y), int(x)] and a[int(y), int(x)] > .6
                if on:
                    run_.append((x, y, .55))
                if run_ and (not on or len(run_) * 6 * base > rr.uniform(70, 150) * base):
                    if len(run_) >= 3:
                        hatch_cmds.append({"command": "paint.stroke", "params": {"points": hand(run_, rr), "preset": "Hard Round Pressure Size", "size": round(2.1 * base, 1), "color": ink}})
                    run_ = []
                    t += rr.uniform(4, 16) * base
                t += 6 * base
    cmds += hatch_cmds
    for c in outer:
        cmds.append({"command": "paint.stroke", "params": {"points": hand(c, rr), "preset": "Hard Round Pressure Size", "size": round(7 * base, 1), "color": ink}})
    for st in ss:
        L = len(st) * 3
        sz = (2.2 + min(5, L / 90) * 1.0) * base
        cmds.append({"command": "paint.stroke", "params": {"points": hand(st, rr), "preset": "Hard Round Pressure Size", "size": round(sz, 1), "color": ink}})
    for st in accents or []:                          # 눈 · 콧구멍처럼 대상에서 안 잡힌 곳은 에이전트가 직접 몇 획만
        pts = st["points"]
        hp = [(x, y, 1.0) for x, y in pts]
        dense = [(hp[i][0] + (hp[i + 1][0] - hp[i][0]) * k / 6, hp[i][1] + (hp[i + 1][1] - hp[i][1]) * k / 6, 1.0) for i in range(len(hp) - 1) for k in range(6)] + [hp[-1]]
        cmds.append({"command": "paint.stroke", "params": {"points": hand(dense, rr), "preset": "Hard Round Pressure Size", "size": st.get("size", 6) * base, "color": ink}})
    blank = work / f"{out.stem}.blank.png"
    Image.new("RGB", (W, H), paper).save(blank)
    cur, n = blank, 0
    while n < len(cmds):                              # 명령줄 길이 한도 — 나눠서 이어 그린다
        args, size_ = ([] if cur == blank else ["--cmd", "layer.select", "--params", json.dumps({"name": "ink"})]), 0
        while n < len(cmds) and size_ < 1_200_000:
            q = json.dumps(cmds[n]["params"], ensure_ascii=False)
            args += ["--cmd", cmds[n]["command"], "--params", q]
            size_ += len(q) + 40
            n += 1
        nxt = out.with_suffix(".next.psd")            # --in-place 는 PSD 에 남지 않는다 — 새 파일로 쓰고 바꾼다
        r = subprocess.run([P, "run", str(cur), *args, "--out", str(nxt)], capture_output=True, text=True, timeout=500, cwd=work)
        if r.returncode:
            raise RuntimeError((r.stderr or r.stdout)[-400:])
        nxt.replace(out)
        cur = out
    png = out.with_suffix(".png")
    subprocess.run([P, "convert", str(out), str(png)], check=True, capture_output=True, cwd=work)
    return {"psd": str(out), "png": str(png), "strokes": len(ss) + len(outer), "size": [W, H]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--detail", type=float, default=.6)
    ap.add_argument("--paper", default="#e6d6b4"); ap.add_argument("--ink", default="#1b130d"); ap.add_argument("--wash", default="#a8835a"); ap.add_argument("--shade", type=float, default=.45); ap.add_argument("--accents", help="직접 그을 획 JSON 파일: [{points:[[x,y]…], size}]")
    ap.add_argument("--size", type=int, default=1400)
    a = ap.parse_args()
    print(json.dumps(run(Path(a.src).resolve(), Path(a.out).resolve(), a.detail, a.paper, a.ink, a.wash, a.size, a.shade, json.loads(Path(a.accents).read_text("utf-8")) if a.accents else None), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
