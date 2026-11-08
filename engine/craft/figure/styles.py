"""화풍 — 같은 3D 인물을 전혀 다른 손으로 그린다. 스타일은 칸(params)으로 얼마든지 변주된다. 표는 출발점이지 고정값이 아니다.
스타일 함수는 '단계(stage)' 목록을 낸다: 먼저 깔 그림(fills)과 순서 있는 획 — 순서가 곧 스케치가 그려지는 순서다."""
from __future__ import annotations

import math
import random

import cv2
import numpy as np

STYLES = {
    "engrave":     {"title": "동판화", "mood": ["고전", "역사", "진지", "서사", "기록"], "ink": "#1b130d", "fits": ["parchment", "document", "atlas"]},
    "sketch":      {"title": "연필 스케치", "mood": ["과정", "설명", "회상", "다큐", "노트", "역사"], "ink": "#35302b", "fits": ["parchment", "gridchart", "document"]},
    "woodcut":     {"title": "목판화", "mood": ["강렬", "전쟁", "분노", "민속", "신화"], "ink": "#14100c", "fits": ["sunset", "halftone", "comic"]},
    "wash":        {"title": "수묵 담채", "mood": ["서정", "슬픔", "고요", "감성", "동양"], "ink": "#26221e", "fits": ["sunset", "parchment"]},
    "blackfigure": {"title": "흑회식 도기", "mood": ["그리스", "고대", "장식", "신화"], "ink": "#17110d", "fits": ["comic", "halftone", "parchment"]},
    "inkline":     {"title": "잉크 선화(잡지 삽화)", "mood": ["현대", "경제", "직장", "기술", "과학", "뉴스", "사회", "설명", "칼럼"], "ink": "#15171a", "fits": ["document", "gridchart", "screen", "chart"]},
    "pop":         {"title": "망점 팝", "mood": ["유머", "밈", "트렌드", "충격", "현대", "광고", "게임"], "ink": "#111111", "fits": ["comic", "halftone", "meme"]},
}


def load(shade, normal):
    def rd(f):
        a = cv2.imread(str(f), cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535
        return a[:, :, 2::-1], a[:, :, 3]
    rgb, alpha = rd(shade)
    n, _ = rd(normal)
    return rgb.mean(2), n, alpha


def id_edges(shade, alpha):
    """재질 경계(옷 · 살 · 갑옷)를 선으로 — id 패스가 없으면(옛 캐시) 0"""
    from pathlib import Path
    f = Path(str(shade).replace("_shade.png", "_id.png"))
    if not f.exists():
        return None
    a = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
    c = (a[:, :, :3].astype(np.int32) >> 4) if a.dtype == np.uint8 else (a[:, :, :3].astype(np.int32) >> 12)
    k = c[:, :, 0] * 256 + c[:, :, 1] * 16 + c[:, :, 2]
    e = (k != np.roll(k, 1, 0)) | (k != np.roll(k, 1, 1))
    return (e & (cv2.erode((alpha > .5).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)).astype(np.uint8)


def tone_of(g, alpha, gamma):
    t = cv2.GaussianBlur(g, (0, 0), 1.5)
    if getattr(_T, "abs", False):                                # 배경 세트: 밝기를 늘리지 않는다(밤은 어둡게, 달은 밝게 그대로)
        return np.clip(t, 0, 1) ** gamma
    lo, hi = np.quantile(t[alpha > .5], .02), np.quantile(t[alpha > .5], .985)
    return np.clip((t - lo) / max(.01, hi - lo), 0, 1) ** gamma


import threading
_T = threading.local()   # 지금 그리는 인물의 재질 경계(build 가 채운다) — 인물을 동시에 그리므로 스레드마다 따로


def edges(n, alpha, th=.38):
    nm = cv2.GaussianBlur(n, (0, 0), 1)
    g = sum(np.abs(cv2.Sobel(nm[:, :, c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(nm[:, :, c], cv2.CV_32F, 0, 1)) for c in range(3)) + 3 * (np.abs(cv2.Sobel(alpha, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(alpha, cv2.CV_32F, 0, 1)))
    e = (g > th).astype(np.uint8)
    ide = getattr(_T, "ide", None)
    return e | ide if ide is not None and ide.shape == e.shape else e


def flow(n, cross=False, fixed=None):
    if fixed is not None:
        a = math.radians(fixed + (90 if cross else 0))
        return np.full(n.shape[:2], math.cos(a), np.float32), np.full(n.shape[:2], math.sin(a), np.float32)
    nx, ny = n[:, :, 0] * 2 - 1, -(n[:, :, 1] * 2 - 1)
    tx, ty = -ny, nx
    m = np.hypot(tx, ty) + 1e-4
    flat = m < .12
    tx, ty = np.where(flat, .82, tx / m), np.where(flat, .57, ty / m)
    if cross:
        tx, ty = -ty, tx
    return cv2.GaussianBlur(tx, (0, 0), 3), cv2.GaussianBlur(ty, (0, 0), 3)


def hatch(tone, alpha, edge, tx, ty, rr, sp_min, sp_max, limit, length=(16, 40), step=4):
    H, W = tone.shape
    grid = np.zeros((H, W), np.uint8)
    spacing = sp_min + (sp_max - sp_min) * np.clip((tone - .08) / max(.01, limit - .08), 0, 1)
    out = []
    seeds = [(x, y) for y in range(2, H - 2, step) for x in range(2, W - 2, step)]
    rr.shuffle(seeds)

    def walk(x, y, s):
        p = []
        fx = fy = None
        for _ in range(rr.randint(*length)):
            ix, iy = int(x), int(y)
            if not (2 <= ix < W - 2 and 2 <= iy < H - 2) or alpha[iy, ix] < .6 or edge[iy, ix] or tone[iy, ix] > limit or grid[iy, ix]:
                break
            dx, dy = float(tx[iy, ix]), float(ty[iy, ix])
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
        r = int(max(1, spacing[y, x]))
        for q in p:
            cv2.circle(grid, (int(q[0]), int(q[1])), r, 1, -1)
    return out


def contour_paths(alpha, every=3, chunk=60):
    cs, _ = cv2.findContours((alpha > .5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        if len(c) < 60:
            continue
        H, W = alpha.shape
        pts = [(float(q[0][0]), float(q[0][1])) for q in c[::every]]
        runs, cur = [], []                                      # 그림 가장자리(배경 세트가 화면 끝까지 갈 때)에는 선을 긋지 않는다
        for x, y in pts:
            if 2 < x < W - 3 and 2 < y < H - 3:
                cur.append((x, y))
            elif cur:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        for r_ in runs:
            out += [r_[i:i + chunk + 6] for i in range(0, len(r_), chunk) if len(r_[i:i + chunk + 6]) > 3]
    return out


def _thin(img):
    """Zhang-Suen 세선화(numpy) — scikit-image 가 없는 가벼운 설치(lite)에서도 같은 뼈대를 얻는다"""
    im = np.pad(img.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P = [np.roll(np.roll(im, -dy, 0), -dx, 1) for dy, dx in ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))]
            B = sum(P)
            A = sum(((P[i] == 0) & (P[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8))
            c = (P[0] * P[2] * P[4] == 0) & (P[2] * P[4] * P[6] == 0) if step == 0 else (P[0] * P[2] * P[6] == 0) & (P[0] * P[4] * P[6] == 0)
            m = (im == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if m.any():
                im[m] = 0; changed = True
        if not changed:
            return im[1:-1, 1:-1].astype(bool)


def inner_paths(edge, limit=900, min_len=14):
    try:
        from skimage.morphology import skeletonize
        sk = skeletonize(edge > 0)
    except ImportError:
        sk = _thin(edge > 0)
    pts = {(int(y), int(x)) for y, x in zip(*np.nonzero(sk))}
    N = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    def nb(p):
        return [(p[0] + a, p[1] + b) for a, b in N if (p[0] + a, p[1] + b) in pts]
    out = []
    for start in [p for p in pts if len(nb(p)) == 1] + sorted(pts):
        if start not in pts:
            continue
        cur, path = start, []
        while cur:
            path.append(cur); pts.discard(cur)
            o = nb(cur)
            cur = o[0] if o else None
        if len(path) >= min_len:
            out.append([(float(x), float(y)) for y, x in path[::3]])
    return sorted(out, key=len, reverse=True)[:limit]


def hand(path, rr, jitter=1.0, pressure=True):
    n = len(path)
    ph, amp, fq = rr.uniform(0, 6.28), rr.uniform(.4, 1.4) * jitter, rr.uniform(5, 5.2)
    o = []
    for i, q in enumerate(path):
        x, y = q[0], q[1]
        w = q[2] if len(q) > 2 else .8
        t = i / max(1, n - 1)
        pr = (math.sin(math.pi * min(1, t * 1.05)) ** .55 if pressure else 1) * (.45 + .55 * w)
        wb = amp * math.sin(ph + t * fq)
        o.append([round(x + wb, 1), round(y - wb * .6, 1), round(max(.08, pr), 3)])
    return o


def stroke(path, rr, size, color, preset="Hard Round Pressure Size", opacity=None, jitter=1.0):
    p = {"points": hand(path, rr, jitter), "preset": preset, "size": round(float(size), 1), "color": color}
    if opacity is not None:
        p["opacity"] = opacity
    return p


def mask_png(mask, color):
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return np.dstack([np.full_like(mask, c) for c in rgb] + [np.clip(mask, 0, 1) * 255]).astype(np.uint8)


def engrave(P, a, rr):
    ink = a.get("ink", "#1b130d"); d = a.get("density", 1.0); L = a.get("line", 1.0)
    tone = tone_of(P["g"], P["alpha"], a.get("contrast", 1.35)); edge = edges(P["n"], P["alpha"])
    fx = a.get("fixed")                                          # 빗금 방향 고정(풍경: 거의 가로)
    tx, ty = flow(P["n"], fixed=fx); ax, ay = flow(P["n"], True, None if fx is None else fx + 70)
    S = lambda lines, s: [stroke(p, rr, s * L, ink) for p in lines]
    fills = [("blacks", cv2.GaussianBlur(((P["g"] < .045) & (P["alpha"] > .6)).astype(np.float32), (0, 0), 1.1), ink)]
    outer = []
    for seg in contour_paths(P["alpha"]):
        t = float(tone[int(seg[len(seg) // 2][1]), int(seg[len(seg) // 2][0])])
        outer.append(stroke([(x, y, .5 + .5 * (1 - t)) for x, y in seg], rr, (2.8 + 3.4 * (1 - t)) * L, ink))
    lay = a.get("layers") or ("outline", "tone", "cross", "deep")    # 쓸 빗금 층(풍경은 윤곽 · 한 겹)
    st = [("outline", lambda: outer + S(inner_paths(edge), 3.2)),
          ("tone", lambda: S(hatch(tone, P["alpha"], edge, tx, ty, rr, 2.6 / d, 13 / d, a.get("limit", .80)), 2.0)),
          ("cross", lambda: S(hatch(tone, P["alpha"], edge, ax, ay, rr, 3.0 / d, 9 / d, .34), 1.9)),
          ("deep", lambda: S(hatch(tone, P["alpha"], edge, tx * .7 + ax * .7, ty * .7 + ay * .7, rr, 3.0 / d, 8 / d, .16), 1.9))]
    return fills, [(n_, f()) for n_, f in st if n_ in lay]


def sketch(P, a, rr):
    """연필: 큰 덩어리를 먼저 잡고(겹치는 선), 윤곽을 두 번 긋고, 한 방향 빗금으로 그늘을 얹는다"""
    ink = a.get("ink", "#35302b"); d = a.get("density", 1.0); L = a.get("line", 1.0); preset = a.get("brush", "Hard Round Pressure Size"); jit = a.get("jitter", 2.2)
    tone = tone_of(P["g"], P["alpha"], a.get("contrast", 1.1)); edge = edges(P["n"], P["alpha"], .55)
    cs, _ = cv2.findContours((P["alpha"] > .5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    block = []
    for c in cs:
        if len(c) < 200:
            continue
        ap = cv2.approxPolyDP(c, 26, True)[:, 0].astype(float)
        for i in range(len(ap)):
            p, q = ap[i], ap[(i + 1) % len(ap)]
            o = (q - p) * rr.uniform(.06, .16)
            block.append(stroke([tuple(p - o + (p - q) * .0 + (q - p) * k / 8 * 1.2 + np.array((rr.uniform(-2, 2), rr.uniform(-2, 2)))) for k in range(9)], rr, 2.4 * L, ink, preset, .34, 1.0))
    first = [stroke(s, rr, 3.6 * L, ink, preset, .95, jit) for s in contour_paths(P["alpha"], 3, 44)]
    again = [stroke([(x + rr.uniform(-1, 1), y + rr.uniform(-1, 1)) for x, y in s], rr, 2.6 * L, ink, preset, .7, jit * 1.6) for s in contour_paths(P["alpha"], 4, 30) if rr.random() < .55]
    inner = [stroke(s, rr, 3 * L, ink, preset, .9, jit) for s in inner_paths(edge, 500, 18)]
    ang = a.get("angle", -56); tx, ty = flow(P["n"], fixed=ang); ax, ay = flow(P["n"], True, ang + 14)
    h1 = hatch(tone, P["alpha"], edge * 0, tx, ty, rr, 5 / d, 16 / d, .72, (10, 30)); h2 = hatch(tone, P["alpha"], edge * 0, ax, ay, rr, 5 / d, 11 / d, .30, (8, 24))
    return [], [("block", block), ("outline", first + inner), ("shade", [stroke(p, rr, 2.8 * L, ink, preset, .75, jit) for p in h1] + again), ("dark", [stroke(p, rr, 2.8 * L, ink, preset, .8, jit) for p in h2])]


def woodcut(P, a, rr):
    ink = a.get("ink", "#14100c"); d = a.get("density", 1.0); L = a.get("line", 1.0); paper = a.get("paper", "#e8d9b8")
    tone = tone_of(P["g"], P["alpha"], a.get("contrast", 1.0)); edge = edges(P["n"], P["alpha"], .5)
    blk = cv2.GaussianBlur((tone < a.get("black", .36)).astype(np.float32) * (P["alpha"] > .5), (0, 0), 2)
    blk = np.clip((blk - .42) / .16, 0, 1)
    tx, ty = flow(P["n"])
    carve = hatch(1 - np.clip(tone, 0, 1) * (blk < .5) * 0 - tone * 0 - (blk < .5) * 1, P["alpha"], edge * 0, tx, ty, rr, 9 / d, 11 / d, .5, (6, 16))    # 먹 안에 칼자국
    mid = hatch(tone * (blk < .5) + (blk >= .5), P["alpha"], edge, tx, ty, rr, 7 / d, 14 / d, .72, (6, 18))
    return [("blacks", blk, ink)], [("outline", [stroke(s, rr, 7.5 * L, ink) for s in contour_paths(P["alpha"], 3, 30)]), ("cut", [stroke(p, rr, 6 * L, ink) for p in mid] + [stroke(p, rr, 5 * L, paper) for p in carve])]


def wash(P, a, rr):
    ink = a.get("ink", "#26221e"); L = a.get("line", 1.0); tint = a.get("tint", "#7d7366")
    tone = tone_of(P["g"], P["alpha"], 1.1); edge = edges(P["n"], P["alpha"], .7)
    soft = cv2.GaussianBlur(tone, (0, 0), 5)
    m1 = cv2.GaussianBlur(((soft < .72) & (P["alpha"] > .5)).astype(np.float32), (0, 0), 4) * .38
    m2 = cv2.GaussianBlur(((soft < .38) & (P["alpha"] > .5)).astype(np.float32), (0, 0), 3) * .75
    return [("wash1", m1, tint), ("wash2", m2, ink)], [("brush", [stroke(s, rr, 8 * L, ink, jitter=1.8) for s in contour_paths(P["alpha"], 4, 26)] + [stroke(s, rr, 5 * L, ink, jitter=1.8) for s in inner_paths(edge, 160, 26)])]


def blackfigure(P, a, rr):
    ink = a.get("ink", "#17110d"); paper = a.get("paper", "#e0a15e"); L = a.get("line", 1.0)
    edge = edges(P["n"], P["alpha"], .42)
    inside = cv2.erode((P["alpha"] > .5).astype(np.uint8), np.ones((9, 9), np.uint8))
    return [("body", cv2.GaussianBlur((P["alpha"] > .5).astype(np.float32), (0, 0), .8), ink)], [("incise", [stroke(s, rr, 3.6 * L, paper) for s in inner_paths(edge * inside, 700, 16)])]


def inkline(P, a, rr):
    """잡지 삽화: 굵기가 변하는 깔끔한 윤곽 + 평면 두 톤(밝은 바탕 · 그림자 한 색) + 가장 어두운 곳에만 짧은 빗금"""
    ink = a.get("ink", "#15171a"); L = a.get("line", 1.0); fill = a.get("fill", "#f4f1ea"); tint = a.get("tint", "#9fb0c2")
    tone = tone_of(P["g"], P["alpha"], a.get("contrast", 1.2)); edge = edges(P["n"], P["alpha"], .5)
    body = cv2.GaussianBlur((P["alpha"] > .5).astype(np.float32), (0, 0), .8)
    shade = cv2.GaussianBlur(((cv2.GaussianBlur(tone, (0, 0), 3) < a.get("cut", .45)) & (P["alpha"] > .5)).astype(np.float32), (0, 0), 1.2)
    outer = []
    for seg in contour_paths(P["alpha"], 3, 50):
        t = float(tone[int(seg[len(seg) // 2][1]), int(seg[len(seg) // 2][0])])
        outer.append(stroke([(x, y, .45 + .55 * (1 - t)) for x, y in seg], rr, (3.2 + 4.2 * (1 - t)) * L, ink, jitter=.6))
    tx, ty = flow(P["n"], fixed=a.get("angle", -50))
    acc = hatch(tone, P["alpha"], edge, tx, ty, rr, 6, 9, .16, (8, 18))
    return [("base", body, fill), ("shadow", shade, tint)], [("outline", outer), ("inner", [stroke(s_, rr, 2.6 * L, ink, jitter=.6) for s_ in inner_paths(edge, 420, 20)]), ("accent", [stroke(p, rr, 2.0 * L, ink, jitter=.6) for p in acc])]


def pop(P, a, rr):
    """망점 팝: 밝은 단색 바탕 + 어두울수록 커지는 망점 그늘 + 굵은 윤곽"""
    ink = a.get("ink", "#111111"); L = a.get("line", 1.0); fill = a.get("fill", "#ffd84a"); dot = a.get("dot", 9)
    tone = cv2.GaussianBlur(tone_of(P["g"], P["alpha"], a.get("contrast", 1.0)), (0, 0), 2); edge = edges(P["n"], P["alpha"], .5)
    H, W = tone.shape; yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    c = math.cos(math.radians(45)); s_ = math.sin(math.radians(45))
    u, v = (xx * c + yy * s_) % dot - dot / 2, (-xx * s_ + yy * c) % dot - dot / 2
    r = np.clip(.62 - tone, 0, .62) / .62 * dot * .62
    dots = ((u * u + v * v) < r * r) & (P["alpha"] > .5)
    body = cv2.GaussianBlur((P["alpha"] > .5).astype(np.float32), (0, 0), .8)
    return [("base", body, fill), ("dots", dots.astype(np.float32), ink)], [("outline", [stroke(s0, rr, 7 * L, ink, jitter=.5) for s0 in contour_paths(P["alpha"], 3, 40)] + [stroke(s0, rr, 3.4 * L, ink, jitter=.5) for s0 in inner_paths(edge, 300, 22)])]


FN = {"inkline": inkline, "pop": pop, "engrave": engrave, "sketch": sketch, "woodcut": woodcut, "wash": wash, "blackfigure": blackfigure}


def ground(P, a, rr, style):
    """발이 닿는 땅 — 판화 · 도기 그림처럼 같은 잉크로 땅선과 발밑 그림자를 긋는다(인물이 떠 보이지 않게)"""
    al = P["alpha"] > .5
    rows = np.where(al.any(1))[0]
    if not len(rows):
        return []
    yb = int(rows[-1]); xs = np.where(al[max(0, yb - 8):yb + 1].any(0))[0]
    cols = np.where(al.any(0))[0]; wf = cols[-1] - cols[0]
    x0, x1 = int(xs.min()), int(xs.max())
    ink = a.get("ink") or STYLES[style]["ink"]; L = a.get("line", 1.0); H, W = al.shape
    out = []
    if style == "blackfigure":                                  # 도기: 띠 하나
        y = min(H - 3, yb + 6)
        return [stroke([(max(2, x0 - .45 * wf) + k * (x1 - x0 + .9 * wf) / 20, y + rr.uniform(-.6, .6)) for k in range(21)], rr, 7 * L, ink, jitter=.3)]
    reach = .55 * wf + 40
    occ = cv2.dilate(al.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0       # 인물 뒤로 지나가는 땅은 가려진다
    n_ = int(a.get("ground_lines", 8))
    for k in range(n_):                                          # 발 뒤(위)에서 앞(아래)으로 — 발이 놓인 줄이 가장 진하고 길다
        off = (k - n_ * .55) * 4.4; y = int(round(yb + 2 + off))
        if not 1 < y < H - 2:
            continue
        near = 1 - abs(off) / (n_ * 2.6)
        half = (x1 - x0) / 2 + reach * near * rr.uniform(.6, 1.0); c = (x0 + x1) / 2 + rr.uniform(-14, 14)
        xa, xb = int(max(2, c - half)), int(min(W - 3, c + half))
        row = ~occ[y, xa:xb]
        runs, st_ = [], None
        for i, v in enumerate(row):
            if v and st_ is None:
                st_ = i
            if (not v or i == len(row) - 1) and st_ is not None:
                if i - st_ > 10:
                    runs.append((xa + st_, xa + i))
                st_ = None
        for ra, rb in runs:
            m_ = max(3, int((rb - ra) / 14))
            out.append(stroke([(ra + (rb - ra) * i / m_, y + rr.uniform(-.7, .7), .35 + .6 * math.sin(math.pi * i / m_)) for i in range(m_ + 1)], rr, (1.6 + 1.6 * near) * L, ink, jitter=.6))
    return out


def build(shade, normal, style="engrave", params=None, seed=5):
    g, n, alpha = load(shade, normal)
    _T.ide = id_edges(shade, alpha)
    a = params or {}
    _T.abs = bool(a.get("abs_tone"))
    ink = a.get("ink") or STYLES[style]["ink"]
    if style not in ("blackfigure", "pop") and sum(int(ink[i:i + 2], 16) for i in (1, 3, 5)) / 765 > .6:
        g = 1 - g                                                # 밝은 잉크(분필 · 밤): 빛나는 곳에 선을 긋는다 — 어두운 바탕 위의 판화
    P = {"g": g, "n": n, "alpha": alpha}
    if a.get("ground"):                                          # 땅 그릴 자리를 아래에 남긴다
        pad = 70
        P = {"g": np.pad(g, ((0, pad), (0, 0))), "n": np.pad(n, ((0, pad), (0, 0), (0, 0))), "alpha": np.pad(alpha, ((0, pad), (0, 0)))}
        if getattr(_T, "ide", None) is not None:
            _T.ide = np.pad(_T.ide, ((0, pad), (0, 0)))
    rr = random.Random(seed)
    fills, stages = FN[style](P, a, rr)
    if a.get("ground"):
        stages = stages + [("ground", ground(P, a, rr, style))]
    return (fills, stages), P["alpha"].shape
