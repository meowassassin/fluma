"""Style passes over the cached G-buffer (render.py). Nothing here knows about ducks:
inputs are hit mask, material id + material table/hints, normals, depth, lighting terms.

python style.py out/duck_scene_passes.npz [flat cel sketch clay] [--tag duck]
"""
import os, colorsys
import numpy as np, cv2

_H = os.path.dirname(os.path.abspath(__file__))


def hexrgb(h):
    h = h.lstrip("#"); return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def auto_shadow(rgb, amount=1.0):
    """Painterly shadow colour: darker, more saturated, hue pushed toward warm red/violet."""
    h, l, s = colorsys.rgb_to_hls(*rgb)
    h2 = (h - 0.05 * amount) % 1.0 if 0.0 < h < 0.45 else (h + 0.04 * amount) % 1.0
    return np.array(colorsys.hls_to_rgb(h2, l * (1 - 0.35 * amount), min(1, s * 1.15 + 0.05)), np.float32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a + (b - a) * t


class Ctx:
    """Derived per-pixel data shared by all styles (built once from the cached passes)."""

    def __init__(self, buf, meta):
        self.b, self.m = buf, meta
        self.N = buf["hit"].shape[0]
        self.ss = int(meta["ss"])
        self.hit = buf["hit"] > 0.5
        self.mat = buf["mat"].astype(np.int32)
        mats = meta["mats"]; mt = meta["mat_table"]; sc = meta["scene"]["materials"]
        self.base_t = mt[:, :3].astype(np.float32)
        self.shadow_t = np.array([hexrgb(sc[n]["shadow"]) if "shadow" in sc[n] else auto_shadow(mt[i, :3])
                                  for i, n in enumerate(mats)], np.float32)
        self.gloss_t = mt[:, 3].astype(np.float32); self.pow_t = mt[:, 4].astype(np.float32)
        mi = np.maximum(self.mat, 0)
        self.mi = mi
        self.base = self.base_t[mi]
        self.lv = np.clip(buf["ndl"], 0, 1) * buf["shadow"]  # key light visibility * cosine
        self.lv[~self.hit] = 0

    def per_mat(self, table):
        return np.asarray(table, np.float32)[self.mi]

    def edges(self, normal_thr=0.75, depth_thr=0.03):
        key = (normal_thr, depth_thr)
        if not hasattr(self, "_edges"): self._edges = {}
        if key not in self._edges: self._edges[key] = self._edges_impl(normal_thr, depth_thr)
        return self._edges[key]

    def _edges_impl(self, normal_thr, depth_thr):
        """Silhouette and interior line masks (uint8 0/1) from id/depth/normal discontinuities."""
        h = self.hit; m = self.mat; d = self.b["depth"]
        n = np.stack([self.b["nx"], self.b["ny"], self.b["nz"]], -1)
        sil = np.zeros_like(h); inner = np.zeros_like(h)
        for ax in (0, 1):
            sl_a = (slice(None, -1), slice(None)) if ax == 0 else (slice(None), slice(None, -1))
            sl_b = (slice(1, None), slice(None)) if ax == 0 else (slice(None), slice(1, None))
            s = h[sl_a] != h[sl_b]
            both = h[sl_a] & h[sl_b]
            e = both & ((m[sl_a] != m[sl_b])
                        | ((n[sl_a] * n[sl_b]).sum(-1) < normal_thr)
                        | (np.abs(d[sl_a] - d[sl_b]) > depth_thr * d[sl_a]))
            sil[sl_a] |= s; sil[sl_b] |= s
            inner[sl_a] |= e
        return sil.astype(np.uint8), (inner & ~sil).astype(np.uint8)

    def ground_ellipse(self, scale=0.95, shift=0.25):
        c = self.m["foot_center"]; a = self.m["foot_size"] * scale
        L = self.m["L"]
        cx, cz = c[0] - L[0] * shift, c[1] - L[2] * shift
        gx, gz = self.b["gx"], self.b["gz"]
        r = ((gx - cx) / a[0]) ** 2 + ((gz - cz) / a[1]) ** 2
        return (~self.hit) & (r < 1.0) & (self.b["depth"] < 999)

    def finish(self, img):
        if img.shape[0] != self.N:
            return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
        out = cv2.resize(np.clip(img, 0, 1).astype(np.float32), (self.N // self.ss,) * 2, interpolation=cv2.INTER_AREA)
        return (out * 255 + 0.5).astype(np.uint8)


def disk(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def noise(N, cells, seed, octaves=1):
    rng = np.random.default_rng(seed)
    acc = np.zeros((N, N), np.float32); amp = 1.0; tot = 0
    for o in range(octaves):
        c = int(cells * 2 ** o)
        small = rng.random((c + 3, c + 3)).astype(np.float32)
        big = cv2.resize(small, (N + N * 3 // c, N + N * 3 // c), interpolation=cv2.INTER_CUBIC)[:N, :N]
        acc += amp * big; tot += amp; amp *= 0.5
    return acc / tot


# ------------------------------------------------------------------ FLAT
def flat(c: Ctx, bg="#f4efe6"):
    N = c.N; sc = c.ss
    bgc = hexrgb(bg)
    img = np.broadcast_to(bgc, (N, N, 3)).copy()
    img[c.ground_ellipse()] = bgc * np.array([0.90, 0.88, 0.88], np.float32)
    base = c.base
    sh = mix(base, c.shadow_t[c.mi], 0.55)
    t = smoothstep(0.20, 0.23, c.lv * (0.6 + 0.4 * c.b["ao"]))
    col = mix(sh, base, t[..., None])
    # single highlight shape for glossy parts (catch-light)
    spec = np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 1.5)
    hl = (spec * c.per_mat(c.gloss_t) > 0.55) & (c.b["shadow"] > 0.5)
    col[hl] = mix(col[hl], np.float32(1.0), 0.85)
    img[c.hit] = col[c.hit]
    # thin coloured outline = material shadow colour on the silhouette
    sil, _ = c.edges()
    ring = cv2.dilate(sil, disk(int(1.5 * sc))).astype(bool) & c.hit
    img[ring] = c.shadow_t[c.mi][ring] * 0.9
    return img


# ------------------------------------------------------------------ CEL
def cel(c: Ctx, bg="#eaf2f7", ink="#2a1c14"):
    N = c.N; sc = c.ss
    bgc = hexrgb(bg)
    img = np.broadcast_to(bgc, (N, N, 3)).copy()
    g = c.b["gshadow"] * c.b["gao"]
    gmask = (~c.hit) & (g < 0.55)
    img[gmask] = bgc * np.array([0.80, 0.82, 0.90], np.float32)
    base, shc = c.base, c.shadow_t[c.mi]
    hi = mix(base, np.array([1.0, 0.98, 0.9], np.float32), 0.45)
    lv = c.lv * (0.55 + 0.45 * c.b["ao"])
    col = np.where((lv < 0.16)[..., None], shc, base)
    col = np.where((lv > 0.80)[..., None], hi, col)
    # rim band on the fill side, only where the key does not already light it
    rim = ((1 - c.b["ndv"]) > 0.72) & (c.b["fill"] > 0.35) & (lv < 0.3) & (c.b["ny"] > -0.2)
    col[rim] = mix(col[rim], np.array([1.0, 0.97, 0.85], np.float32), 0.55)
    spec = np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 2.0)
    dot = (spec * c.per_mat(c.gloss_t) > 0.4) & (c.b["shadow"] > 0.5)
    col[dot] = 1.0
    img[c.hit] = col[c.hit]
    sil, inner = c.edges()
    thick = cv2.dilate(sil, disk(int(3.2 * sc)))
    thin = cv2.dilate(inner, disk(int(1.2 * sc)))
    line = np.maximum(thick, thin).astype(np.float32)
    line = cv2.GaussianBlur(line, (0, 0), 0.6 * sc)
    img = mix(img, hexrgb(ink), line[..., None])
    return img


# ------------------------------------------------------------------ SKETCH
def sketch(c: Ctx, seed=7, paper=None, texture=True):
    """Works at output resolution (R) for speed; edges come from the supersampled buffers."""
    N, sc = c.N, c.ss
    R = N // sc
    dn = lambda a: cv2.resize(np.ascontiguousarray(a, np.float32), (R, R), interpolation=cv2.INTER_AREA)
    cov = dn(c.hit)
    hit = cov > 0.5
    base = dn(c.base * c.hit[..., None]) / np.maximum(cov, 1e-3)[..., None]
    lum_base = base @ np.array([0.3, 0.59, 0.11], np.float32)
    lv = dn(c.lv * c.b["ao"]) / np.maximum(cov, 1e-3)
    g = dn(c.b["gshadow"] * c.b["gao"])

    paper = np.array(hexrgb(paper) if isinstance(paper, str) else (paper if paper is not None else [0.965, 0.935, 0.875]), np.float32)
    n1 = noise(R, 6, seed, 3)
    rng = np.random.default_rng(seed + 1)
    grain = cv2.GaussianBlur(rng.random((R, R), dtype=np.float32), (0, 0), 0.7)
    grain = (grain - grain.mean()) / (grain.std() + 1e-6)
    fib = cv2.GaussianBlur(rng.random((R, R), dtype=np.float32), (0, 0), sigmaX=6, sigmaY=0.6)
    fib = (fib - fib.mean()) / (fib.std() + 1e-6)
    tex = (0.035 * (n1[..., None] - 0.5) + 0.015 * grain[..., None] + 0.012 * fib[..., None]) if texture else 0.0
    img = paper[None, None, :] * (1 + tex)

    # light watercolour wash: offset, ragged, pigment pooling at its edge
    wn = noise(R, 10, seed + 2, 2)
    wmask = cv2.GaussianBlur(cov, (0, 0), 3)
    wmask = np.clip((wmask - 0.62 - 0.4 * (wn - 0.5)) * 5, 0, 1)
    M = np.float32([[1, 0, 2], [0, 1, -2]])
    wcol = cv2.warpAffine(base * cov[..., None], M, (R, R))
    wm = cv2.warpAffine(wmask, M, (R, R))
    edge_dark = np.clip(wm * (1 - wm) * 4, 0, 1)
    wash_a = (0.32 + 0.15 * edge_dark) * wm * (0.85 + 0.3 * (wn[..., None] - 0.5))[..., 0]
    img = img * mix(np.ones(3, np.float32), wcol, wash_a[..., None])

    # tone for hatching
    tone = np.where(hit, np.sqrt(np.clip(lum_base, 0, 1)) * (0.12 + 0.88 * np.power(np.clip(lv, 0, 1), 0.6)), np.minimum(1.0, 0.2 + 0.8 * g))
    tone = cv2.GaussianBlur(tone.astype(np.float32), (0, 0), 1.5)
    tone += 0.10 * (noise(R, 14, seed + 3) - 0.5)
    # hatching stops short of the outline (hand-drawn), ragged
    inset = cv2.GaussianBlur(cov, (0, 0), 4) + 0.6 * (noise(R, 20, seed + 5) - 0.5)
    hatch_ok = np.where(hit, smoothstep(0.55, 0.8, inset), 1.0)

    yy, xx = np.mgrid[0:R, 0:R].astype(np.float32)
    warp = 5 * (noise(R, 5, seed + 4) - 0.5)
    dark = np.zeros((R, R), np.float32)
    spacing = 5.5
    for k, (ang, thr, alpha) in enumerate([(58, 0.42, 0.6), (-32, 0.18, 0.5)]):
        a = np.deg2rad(ang)
        u = xx * np.cos(a) + yy * np.sin(a) + warp
        v = -xx * np.sin(a) + yy * np.cos(a)
        dist = np.abs((u / spacing) % 1.0 - 0.5) * spacing
        w = np.clip((thr - tone) / thr, 0, 1) * 0.9 + 0.25
        stroke = np.clip(w - dist + 0.5, 0, 1) * smoothstep(thr, thr - 0.06, tone)
        rowid = np.floor(u / spacing)
        brk = np.sin(v / (22 + 9 * k) + rowid * 2.3) * 0.5 + 0.5
        stroke *= smoothstep(0.08, 0.3, brk)
        dark = 1 - (1 - dark) * (1 - alpha * stroke * hatch_ok)

    # graphite outlines: a confident pass + two looser jittered passes
    sil, inner = c.edges(normal_thr=0.8)
    ed_full = np.maximum(cv2.dilate(sil, disk(int(1.6 * sc))), cv2.dilate(inner, disk(int(0.8 * sc))))
    ed = np.clip(dn(ed_full) * 1.6, 0, 1)
    for k in range(3):
        amp = 1.2 if k == 0 else 2.8
        dx = (noise(R, 5, seed + 20 + k) - 0.5) * 2 * amp
        dy = (noise(R, 5, seed + 30 + k) - 0.5) * 2 * amp
        e = cv2.remap(ed, xx + dx, yy + dy, cv2.INTER_LINEAR)
        press = (0.65 if k == 0 else 0.3) + (0.35 if k == 0 else 0.7) * noise(R, 9, seed + 40 + k)
        a = (1.0 if k == 0 else 0.45) * press
        dark = 1 - (1 - dark) * (1 - a * e)
    # very dark materials (eyes, tyres...) get a solid graphite fill, as an artist would
    solid = smoothstep(0.25, 0.12, lum_base) * cov
    dark = 1 - (1 - dark) * (1 - 0.85 * solid)
    dark *= np.clip(0.85 + 0.2 * grain, 0.5, 1.2)  # graphite skips the paper tooth
    # specular highlights stay as untouched paper (lifted with an eraser)
    spec = dn((np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 1.5)) * c.per_mat(c.gloss_t) * c.hit)
    dark *= 1 - smoothstep(0.35, 0.5, spec)
    graphite = np.array([0.20, 0.19, 0.21], np.float32)
    return mix(img, graphite, np.clip(dark, 0, 1)[..., None])


# ------------------------------------------------------------------ CLAY
def clay(c: Ctx, bg_top="#f6f1ea", bg_bot="#e8dfd3", bounce_col=None):
    """Soft toy/clay render. Shading is evaluated only on object pixels (1D) for speed."""
    N = c.N
    hit = c.hit
    b = {k: c.b[k][hit] for k in ("ndl", "shadow", "ao", "ny", "fill", "ndv", "ndh")}
    mi = c.mi[hit]
    alb = np.power(c.base_t, 2.2)[mi]
    ndl, sh = b["ndl"], b["shadow"][:, None]
    wrap = np.clip((ndl + 0.35) / 1.35, 0, 1)
    soft_sh = sh + (1 - sh) * np.array([0.10, 0.04, 0.02], np.float32)
    key = np.array([1.0, 0.95, 0.86], np.float32) * 2.0
    ao = b["ao"][:, None]; ny = b["ny"][:, None]
    sky = np.array([0.55, 0.62, 0.75], np.float32) * 0.55
    bounce = np.power(hexrgb(bounce_col or bg_bot), 2.2) * 0.55   # 투명 배경으로 뽑을 때도 반사광은 같게
    fill = np.array([0.75, 0.8, 0.95], np.float32) * 0.5 * np.clip(b["fill"], 0, 1)[:, None]
    diff = key * (wrap ** 1.4)[:, None] * soft_sh + fill * ao + (sky * (0.5 + 0.5 * ny) + bounce * (0.5 - 0.5 * ny)) * ao
    sss = np.exp(-((ndl - 0.05) / 0.22) ** 2)[:, None] * np.array([0.45, 0.12, 0.02], np.float32) * sh
    surf = noise(N, 60, 3, 1)[hit][:, None]
    col = alb * (diff + sss) * (0.97 + 0.06 * surf)
    fres = (0.04 + 0.96 * (1 - np.clip(b["ndv"], 0, 1)) ** 5)[:, None]
    gl = c.gloss_t[mi][:, None]
    spec = np.clip(b["ndh"], 0, 1)[:, None] ** c.pow_t[mi][:, None] * sh * gl * 1.6
    col = col + spec + fres * gl * 0.35 * ao
    # hue-preserving filmic: compress by luminance so bright yellow does not turn lime
    lum = col @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    col = col * (1 / (1 + 0.45 * lum))[:, None]
    col = np.power(np.clip(col, 0, 1), 1 / 2.2)
    yy = np.linspace(0, 1, N, dtype=np.float32)[:, None, None]
    img = mix(hexrgb(bg_top), hexrgb(bg_bot), yy) * np.ones((1, N, 1), np.float32)
    gs = (0.35 + 0.65 * c.b["gshadow"]) * c.b["gao"]
    img *= mix(np.array([0.62, 0.6, 0.66], np.float32), np.ones(3, np.float32), gs[..., None])
    img[hit] = col
    return img


# ------------------------------------------------------------------ LOOK (조절 값으로 그리는 화풍 — 2026-11-20)
# 화풍 이름마다 규칙을 두지 않는다: 그림체를 이루는 축(명암 단계 · 선 · 해칭 · 스크린톤 · 망점 · 색 수 · 채도 · 흑백 · 종이 · 번짐 · 픽셀)을
# 값으로 열고, 에이전트가 참고 그림을 보고 값을 정한다(engine/craft/form/README.md '화풍 값').
LOOK_KEYS = ("bands", "solid", "detail", "detail_scale", "detail_on", "fur", "fur_scale", "tufts", "hatch_follow", "brush", "seed", "shadow", "light", "highlight", "rim", "saturation", "tint", "mono", "ink", "line", "inner", "jitter", "weight",
             "hatch", "hatch_angle", "cross", "tone", "halftone", "paper", "wash", "ground", "pixel", "colors")


def _lum(img):
    return img @ np.array([0.299, 0.587, 0.114], np.float32)


def noise3(P, seed=1):
    """3D 값 노이즈(0~1) — 표면 위치(world)로 털 결 · 근육 굴곡을 만든다(형태를 다시 계산하지 않는다)"""
    fl = np.floor(P).astype(np.int64); f = P - fl
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        v = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        v = (v ^ (v >> 13)) * 1274126177
        return ((v ^ (v >> 16)) & 0xFFFF).astype(np.float32) / 65535.0
    x, y, z = fl[..., 0], fl[..., 1], fl[..., 2]
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    out = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (fx if dx else 1 - fx) * (fy if dy else 1 - fy) * (fz if dz else 1 - fz)
                out = out + w * h(x + dx, y + dy, z + dz)
    return out.astype(np.float32)


def _on_mats(c: Ctx, names):
    mats = list(c.m["mats"])
    if not names:
        return c.hit
    ids = [mats.index(n) for n in names if n in mats]
    return c.hit & np.isin(c.mat, ids)


def _brush(mask, lw, rng, shade=None, weight=0.0, wobble=1.0, taper=0.18):
    """윤곽을 붓 획으로 — 획마다 시작 · 끝이 가늘고, 그림자 쪽은 굵고, 조금 어긋나 겹친다"""
    out = np.zeros(mask.shape, np.float32)
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    H, W = mask.shape
    for cn in cnts:
        pts = cn[:, 0, :]
        n = len(pts)
        if n < 12:
            continue
        i = int(rng.integers(0, max(1, n // 8)))
        while i < n:
            L = int(rng.integers(max(20, n // 14), max(40, n // 5)))
            seg = pts[i:i + L:2]
            off = rng.normal(0, wobble, 2)
            for j, (x, y) in enumerate(seg):
                t = j / max(1, len(seg) - 1)
                w = lw * (taper + (1 - taper) * np.sin(np.pi * t) ** 0.7)
                if shade is not None and weight:
                    w *= 1 + weight * float(shade[min(H - 1, max(0, int(y))), min(W - 1, max(0, int(x)))])
                cv2.circle(out, (int(x + off[0]), int(y + off[1])), max(1, int(w)), 1.0, -1, lineType=cv2.LINE_AA)
            i += L - int(L * 0.3)
    return out


def look(c: Ctx, p: dict, bg="#ffffff"):
    N, sc = c.N, c.ss
    g = lambda k, d=None: p.get(k, d)  # noqa: E731
    bgc = hexrgb(bg)
    img = np.broadcast_to(bgc, (N, N, 3)).copy()
    ink = hexrgb(g("ink", "#1b1714"))
    if g("ground", True):
        gm = (~c.hit) & (c.b["gshadow"] * c.b["gao"] < 0.55)
        img[gm] = bgc * 0.84
    s = np.clip(c.lv * (0.55 + 0.45 * c.b["ao"]), 0, 1)                 # 0 그림자 … 1 빛
    det, fur = float(g("detail", 0.0)), float(g("fur", 0.0))              # 표면: 굴곡(근육 · 덩어리) · 털 결 — 표면 위치로 노이즈를 만들어 빛에 반영
    if det or fur:
        P = np.stack([c.b["px"], c.b["py"], c.b["pz"]], -1).astype(np.float32)
        hgt = np.zeros((N, N), np.float32)
        if det:
            sc_ = float(g("detail_scale", 9.0))
            hgt += det * (noise3(P * sc_, 3) + 0.5 * noise3(P * sc_ * 2.1, 4))
        if fur:
            fs_ = float(g("fur_scale", 70.0))
            hgt += fur * 0.6 * noise3(P * np.array([fs_, fs_ * 0.12, fs_], np.float32), 7)   # 위아래로 긴 결(털이 아래로 흐른다)
        hgt *= _on_mats(c, g("detail_on"))
        gy_, gx_ = np.gradient(hgt)
        L, r_, u_ = c.m["L"], c.m["r"], c.m["u"]
        lx, ly = float(np.dot(L, r_)), -float(np.dot(L, u_))
        bump = gx_ * lx + gy_ * ly
        sd = float(bump[c.hit].std()) or 1.0
        s = np.clip(s + 0.35 * bump / sd * c.hit, 0, 1)
    bands = int(g("bands", 3))
    if bands <= 0:
        t = smoothstep(0.0, 1.0, s)                                       # 부드러운 명암
    elif bands == 1:
        t = np.ones_like(s)                                               # 명암 없음(평면)
    else:
        t = np.floor(np.clip(s * 1.15, 0, 0.999) * bands) / (bands - 1)
    base = c.base
    dark = mix(base, c.shadow_t[c.mi], float(g("shadow", 0.85)))
    col = mix(dark, base, t[..., None])
    lt = float(g("light", 0.0))                                           # 밝은 면을 하양 쪽으로
    if lt:
        col = mix(col, np.ones(3, np.float32), (lt * (s > 0.8))[..., None])
    hl = g("highlight", "dot")
    if hl:
        spec = np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 2.0) * c.per_mat(c.gloss_t)
        m = (spec > (0.4 if hl == "dot" else 0.15)) & (c.b["shadow"] > 0.5)
        col[m] = mix(col[m], np.ones(3, np.float32), 1.0 if hl == "dot" else 0.5)
    rim = float(g("rim", 0.0))
    if rim:
        r = ((1 - c.b["ndv"]) > 0.7) & (c.b["fill"] > 0.3)
        col[r] = mix(col[r], np.ones(3, np.float32), rim)
    sat = float(g("saturation", 1.0))
    if sat != 1.0:
        L = _lum(col)[..., None]; col = np.clip(L + (col - L) * sat, 0, 1)
    if g("tint"):
        col = mix(col, hexrgb(g("tint")), 0.25)
    if g("mono"):                                                         # 흑백(먹 · 연필): 밝기만 남기고 종이색 위에
        col = np.repeat(_lum(col)[..., None], 3, -1)
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    shade = (1 - s) * c.hit
    hp = int(g("hatch", 0) * sc)                                          # 해칭: 그림자 쪽에 사선(간격 px), cross 면 더 어두운 곳에 교차
    if hp:
        a = np.radians(float(g("hatch_angle", 35)))
        w = max(1, int(hp * 0.28))
        if g("hatch_follow"):                                             # 형태를 따라 휘는 해칭(표면 위치의 등고선) — 둥근 면을 감싸며 돈다
            ext = float(np.max(c.m["hi"] - c.m["lo"])) or 1.0
            k_ = N / ext / hp
            P1 = c.b["py"] * np.cos(a) + (c.b["px"] * 0.8 + c.b["pz"] * 0.6) * np.sin(a)
            P2 = c.b["py"] * np.cos(a + 1.3) + (c.b["px"] * 0.6 - c.b["pz"] * 0.8) * np.sin(a + 1.3)
            wr = 0.28
            l1 = ((P1 * k_) % 1.0) < wr
            l2 = ((P2 * k_) % 1.0) < wr
        else:
            l1 = ((xx * np.cos(a) + yy * np.sin(a)) % hp) < w
            l2 = ((xx * np.cos(a + 1.4) + yy * np.sin(a + 1.4)) % hp) < w
        hm = l1 & (shade > 0.45) & c.hit
        if g("cross", True):
            hm |= l2 & (shade > 0.72) & c.hit
        col[hm] = mix(col[hm], ink, 0.85)
    tp = int(g("tone", 0) * sc)                                           # 스크린톤: 그림자 쪽에 같은 크기 점
    if tp:
        dx, dy = (xx % tp) - tp / 2, (yy % tp) - tp / 2
        tm = (dx * dx + dy * dy < (tp * 0.32) ** 2) & (shade > 0.4)
        col[tm] = mix(col[tm], ink, 0.8)
    hf = int(g("halftone", 0) * sc)                                       # 망점: 어두울수록 큰 점(밝은 면은 원래 색)
    if hf:
        dx, dy = (xx % hf) - hf / 2, (yy % hf) - hf / 2
        rad = shade * hf * 0.62
        hm = (dx * dx + dy * dy < rad * rad) & c.hit
        col = np.where(c.hit[..., None], mix(base, np.ones(3, np.float32), 0.15) if not g("mono") else np.ones_like(col), col)
        col[hm] = mix(c.shadow_t[c.mi][hm], ink, 0.5)
    so = float(g("solid", 0.0))                                           # 먹칠(베타): 이만큼 넘게 어두운 곳을 먹색으로 꽉
    if so:
        sm = (shade > so) & c.hit
        col[sm] = ink
    wash = float(g("wash", 0.0))                                          # 수채: 칠이 번지고 가장자리에 물감이 고인다
    if wash:
        blur = cv2.GaussianBlur(col, (0, 0), 3 * sc * wash)
        col = np.where(c.hit[..., None], blur, col)
        dist = cv2.distanceTransform(c.hit.astype(np.uint8), cv2.DIST_L2, 3)
        edge = np.exp(-dist / (6 * sc)) * c.hit
        col = col * (1 - 0.35 * wash * edge[..., None])
        col *= (0.92 + 0.16 * noise(N, 18, 5, 2))[..., None] ** wash
    img[c.hit] = col[c.hit]
    obj = c.hit
    tuft = float(g("tufts", fur))                                         # 털 뭉치: 털 재질 실루엣 밖으로 삐져나온 결
    if tuft:
        on = cv2.dilate(_on_mats(c, g("detail_on")).astype(np.uint8), disk(int(3 * sc))).astype(bool)
        dist, lab = cv2.distanceTransformWithLabels((~c.hit).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ang = np.arctan2(*np.gradient(dist.astype(np.float32))[::-1])
        strand = noise(N, 140, 31, 1)
        strand = 0.5 + 0.5 * np.sin(ang * 26 + strand * 9)                # 실루엣을 따라 도는 가는 결
        tm = (~c.hit) & on & (dist < tuft * 7 * sc * strand ** 3) & (dist > 0)
        zy, zx = np.nonzero(c.hit)
        idx = lab[tm] - 1
        ok_ = (idx >= 0) & (idx < len(zy))
        tys, txs = np.nonzero(tm)
        img[tys[ok_], txs[ok_]] = col[zy[idx[ok_]], zx[idx[ok_]]]
        obj = c.hit | tm
    lw = float(g("line", 2.5))                                            # 선: 바깥 굵기(px) · 안쪽 · 흔들림 · 그림자 쪽 굵게 · 붓
    if lw > 0:
        sil, inner = c.edges()
        if obj is not c.hit:
            sil = (obj & ~cv2.erode(obj.astype(np.uint8), disk(1)).astype(bool)).astype(np.uint8)
        br = float(g("brush", 0.0))
        if br:                                                            # 붓 획: 바깥선은 획으로(시작 · 끝 가늘게, 그림자 쪽 굵게, 어긋나 겹침)
            lm = _brush(obj, lw * sc, np.random.default_rng(int(g("seed", 3))), shade=cv2.dilate(shade.astype(np.float32), disk(int(5 * sc))),
                        weight=float(g("weight", 0.6)), wobble=br * 1.5 * sc, taper=0.18 + 0.45 * (1 - min(1.0, br)))   # brush 1 = 획 끝이 가장 가늘다
        else:
            lm = cv2.dilate(sil, disk(max(1, int(lw * sc)))).astype(np.float32)
        iw = float(g("inner", lw * 0.45))
        if iw > 0:
            lm = np.maximum(lm, cv2.dilate(inner, disk(max(1, int(iw * sc)))).astype(np.float32))
        wt = 0.0 if br else float(g("weight", 0.0))
        if wt:
            heavy = cv2.dilate(sil, disk(max(1, int(lw * (1 + wt) * sc)))).astype(np.float32)
            dark_side = cv2.dilate((shade > 0.5).astype(np.uint8), disk(int(4 * sc))).astype(np.float32)
            lm = np.maximum(lm, heavy * dark_side)
        jt = float(g("jitter", 0.0))
        if jt:
            nx_ = (noise(N, 24, 11, 2) - 0.5) * 2 * jt * sc; ny_ = (noise(N, 24, 12, 2) - 0.5) * 2 * jt * sc
            lm = cv2.remap(lm, (xx + nx_).astype(np.float32), (yy + ny_).astype(np.float32), cv2.INTER_LINEAR)
        lm = cv2.GaussianBlur(lm, (0, 0), 0.6 * sc)
        img = mix(img, ink, np.clip(lm, 0, 1)[..., None])
    pa = float(g("paper", 0.0))                                           # 종이 · 크레용 결
    if pa:
        img = img * (1 - pa * 0.25 * noise(N, 90, 21, 2))[..., None]
    return img


STYLES = dict(flat=flat, cel=cel, sketch=sketch, clay=clay)
