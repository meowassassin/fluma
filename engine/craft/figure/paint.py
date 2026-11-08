"""스타일이 낸 단계를 PhotoCraft 로 긋는다. 레이어(단계별) PSD · 투명 PNG · (reveal) 그려지는 과정 프레임."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from . import styles


def _chunks(cmds, limit=1_200_000, active=None):
    """명령줄 한도로 나눈다 — 묶음마다 그때 쓰던 레이어를 다시 고르도록 (시작 레이어, 인자)"""
    a, z, start = [], 0, active
    for c, p in cmds:
        q = json.dumps(p, ensure_ascii=False)
        if z + len(q) > limit and a:
            yield start, a
            a, z, start = [], 0, active
        a += ["--cmd", c, "--params", q]
        z += len(q) + 40
        if c == "layer.new.layer" or (c == "layer.setProps" and p.get("name")):
            active = p["name"]
    if a:
        yield start, a


APPS = threading.BoundedSemaphore(max(2, min(4, (os.cpu_count() or 4) // 2)))     # 동시에 띄우는 앱 수 — 메모리 한도


def _go(P, cur, args, W, H, out):
    nxt = Path(out).with_suffix(".next.psd")                 # --in-place 는 PSD 에 남지 않는다
    b = [P, "run", "--new", json.dumps({"width": W, "height": H, "background": "transparent"}), *args, "--out", str(nxt)] if cur is None else [P, "run", str(out), *args, "--out", str(nxt)]
    with APPS:
        r = subprocess.run(b, capture_output=True, text=True, timeout=400, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout)[-400:])
    nxt.replace(out)


def _png(P, psd, png):
    with APPS:
        subprocess.run([P, "convert", str(psd), str(png)], check=True, capture_output=True, stdin=subprocess.DEVNULL)


def paint(P, shade, normal, out: Path, style="engrave", params=None, reveal=0, seed=5):
    """reveal: 0 완성만 · N 그려지는 과정 N 장(<out>_r000.png …)"""
    (fills, stages), (H, W) = styles.build(shade, normal, style, params, seed)
    out = Path(out)
    cmds = []
    for name, mask, color in fills:
        f = out.with_name(f"{out.stem}.{name}.png")
        Image.fromarray(styles.mask_png(mask, color), "RGBA").save(f)
        cmds.append(("file.placeEmbedded", {"path": str(f.resolve())}))
        cmds.append(("layer.setProps", {"name": name}))
    total = sum(len(s[1]) for s in stages)
    frames = []
    if reveal:
        per = max(1, total // reveal)
    cur, made, act = None, 0, None

    def flush():
        nonlocal cur, act, cmds
        for start, a in _chunks(cmds, active=act):
            _go(P, cur, (["--cmd", "layer.select", "--params", json.dumps({"name": start})] if cur and start else []) + a, W, H, out)
            cur = out
        for c, q in cmds:
            if c == "layer.new.layer" or (c == "layer.setProps" and q.get("name")):
                act = q["name"]
        cmds = []
    for name, items in stages:
        cmds.append(("layer.new.layer", {"name": name}))
        for i in range(0, max(1, len(items)), per if reveal else 10 ** 9):
            cmds += [("paint.stroke", q) for q in items[i:i + (per if reveal else len(items))]]
            if reveal:
                flush()
                fr = out.with_name(f"{out.stem}_r{made:03d}.png")
                _png(P, out, fr)
                frames.append(fr)
                made += 1
    flush()
    png = out.with_suffix(".png")
    _png(P, out, png)
    return {"psd": str(out), "png": str(png), "frames": [str(f) for f in frames], "strokes": total, "size": [W, H]}


def on_paper(png, out, paper="#e8d9b8"):
    a = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", a.size, paper)
    bg.alpha_composite(a)
    bg.convert("RGB").save(out)
