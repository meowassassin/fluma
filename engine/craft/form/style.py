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
        if meta["scene"].get("ground") is False:         # 공중에 뜬 것(날아다니는 운반자 · 떠 있는 물건) — 땅 그림자 없음
            self.b = {**buf, "gshadow": np.ones_like(buf["gshadow"]), "gao": np.ones_like(buf["gao"])}
        self.band = np.zeros_like(self.hit)
        self.hair = np.zeros_like(self.hit)
        self._illustrate(meta, mats)

    def _illustrate(self, meta, mats):
        """그림의 명암 — 2026-11-21: 피부를 실제 입체 그림자(머리카락 그림자 · 굴곡)로 칠해 얼굴에 얼룩진 덩어리가 생겼고,
        머리카락은 반사광 얼룩 하나라 헬멧처럼 보였다. 일러스트처럼:
        · 피부(뼈대의 skin 재료): 부위 크기만큼 뭉갠 법선(단순화한 둥근 면)으로 명암, 남이 드리운 그림자는 받지 않는다
        · 머리카락(hair 재료): 반사 얼룩을 끄고, 머리 모양을 따라 도는 하이라이트 띠(천사 고리)"""
        roles = {"skin": set(), "hair": set()}

        def walk(n):
            if isinstance(n, dict):
                for k, v in (n.get("_roles") or {}).items():
                    roles.setdefault(k, set()).update(v)
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)
        walk(meta["scene"].get("root"))
        L = np.asarray(meta["L"], np.float32); u = np.asarray(meta["u"], np.float32)
        nrm = np.stack([self.b["nx"], self.b["ny"], self.b["nz"]], -1)
        for role in ("skin", "hair"):
            ids = [i for i, m in enumerate(mats) if m in roles[role]]
            if not ids:
                continue
            mask = self.hit & np.isin(self.mat, ids)
            if mask.sum() < 16:
                continue
            n_s = np.zeros_like(nrm)
            cnt, lab = cv2.connectedComponents(mask.astype(np.uint8))
            for k in range(1, cnt):                               # 부위마다 그 크기만큼 뭉갠다(얼굴은 크게 · 손가락은 작게)
                mk = lab == k
                sig = max(1.0, (0.18 if role == "skin" else 0.04) * float(np.sqrt(mk.sum())))   # 머리카락은 다발 굴곡이 남게 조금만
                w = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), sig)
                for a in range(3):
                    n_s[..., a] += np.where(mk, cv2.GaussianBlur(nrm[..., a] * mk, (0, 0), sig) / np.maximum(w, 1e-4), 0)
            n_s /= np.maximum(np.linalg.norm(n_s, axis=-1, keepdims=True), 1e-4)
            if role == "skin":
                lv = np.clip((n_s @ L) * 0.85 + 0.2, 0, 1)
                self.lv[mask] = lv[mask]
            else:
                self.gloss_t[ids] = 0.0
                self.hair = mask                                  # 하이라이트는 뼈대가 낸 띠 획으로(draw_strokes)

    def px(self, w: float) -> int:
        """선 굵기(1080 출력 기준 px) → 이 버퍼의 px — 해상도가 낮아도 선이 형태를 덮지 않게(2026-11-20: 400px 움직임 프레임에서 캐릭터가 검은 덩어리)"""
        return max(1, int(round(w * self.N / 1080)))

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
        if img.shape[0] != self.hit.shape[0]:
            return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
        hh, ww = self.hit.shape
        out = cv2.resize(np.clip(img, 0, 1).astype(np.float32), (ww // self.ss, hh // self.ss), interpolation=cv2.INTER_AREA)
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
    g = c.b["gshadow"] * c.b["gao"]                    # 발밑 그림자만(타원 바닥판을 칠하던 것은 원판 무대처럼 보였다)
    img[(~c.hit) & (g < 0.55)] = bgc * np.array([0.84, 0.83, 0.86], np.float32)
    base = c.base
    sh = mix(base, c.shadow_t[c.mi], 0.55)
    t = smoothstep(0.20, 0.23, c.lv * (0.6 + 0.4 * c.b["ao"]))
    col = mix(sh, base, t[..., None])
    # single highlight shape for glossy parts (catch-light)
    spec = np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 1.5)
    hl = (spec * c.per_mat(c.gloss_t) > 0.55) & (c.b["shadow"] > 0.5)
    col[hl] = mix(col[hl], np.float32(1.0), 0.85)
    col[c.band] = mix(col[c.band], np.float32(1.0), 0.35)
    img[c.hit] = col[c.hit]
    # thin coloured outline = material shadow colour on the silhouette
    sil, _ = c.edges()
    ring = cv2.dilate(sil, disk(c.px(1.5))).astype(bool) & c.hit
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
    col = np.where(((lv > 0.80) & ~c.hair)[..., None], hi, col)     # 머리카락은 밝은 면 얼룩 대신 띠(c.band)
    # rim band on the fill side, only where the key does not already light it
    rim = ((1 - c.b["ndv"]) > 0.72) & (c.b["fill"] > 0.35) & (lv < 0.3) & (c.b["ny"] > -0.2)
    col[rim] = mix(col[rim], np.array([1.0, 0.97, 0.85], np.float32), 0.55)
    spec = np.clip(c.b["ndh"], 0, 1) ** c.per_mat(c.pow_t * 2.0)
    dot = (spec * c.per_mat(c.gloss_t) > 0.4) & (c.b["shadow"] > 0.5)
    col[dot] = 1.0
    col[c.band] = mix(col[c.band], np.float32(1.0), 0.4)
    img[c.hit] = col[c.hit]
    sil, inner = c.edges()
    thick = cv2.dilate(sil, disk(c.px(3.2)))
    thin = cv2.dilate(inner, disk(c.px(1.2)))
    line = np.maximum(thick, thin).astype(np.float32)
    line = cv2.GaussianBlur(line, (0, 0), max(0.5, 0.6 * c.N / 1080))
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
    ed_full = np.maximum(cv2.dilate(sil, disk(c.px(1.6))), cv2.dilate(inner, disk(c.px(0.8))))
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


STYLES = dict(flat=flat, cel=cel, sketch=sketch, clay=clay)


# ------------------------------------------------------------------ 얼굴 획(이목구비)
def _catmull(pts, n=6, closed=False):
    P = np.asarray(pts, np.float64)
    if len(P) < 3:
        return P
    out = []
    m = len(P)
    rng = range(m) if closed else range(m - 1)
    for i in rng:
        p0, p1 = P[(i - 1) % m] if (closed or i > 0) else P[i], P[i]
        p2 = P[(i + 1) % m]
        p3 = P[(i + 2) % m] if (closed or i + 2 < m) else p2
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return np.array(out)


def project_strokes(c: Ctx):
    """획(세상 좌표) → 화면 픽셀 · 보이는지(깊이) · 굵기(px). 보이는 것만, 연속 구간으로 나눠 돌려준다"""
    m = c.m
    eye, f, r, u = (np.asarray(m[k], np.float64) for k in ("eye", "f", "r", "u")); th = float(m["th"])
    N = c.N
    depth = c.b["depth"]
    out = []
    for st in m.get("strokes") or []:
        P = np.asarray(st["pts"], np.float64)
        V = P - eye
        z = V @ f
        if np.any(z <= 1e-6):
            continue
        X = ((V @ r) / z / th + 1) / 2 * N - 0.5
        Y = (1 - (V @ u) / z / th) / 2 * N - 0.5
        dist = np.linalg.norm(V, axis=1)
        scale = N / 2 / th / z                             # 세상 길이 → px
        xi = np.clip(np.round(X).astype(int), 0, N - 1); yi = np.clip(np.round(Y).astype(int), 0, N - 1)
        tol = 0.03 * float(np.mean(dist)) * th + 0.004 * float(np.mean(dist))
        vis = (X >= 0) & (X < N) & (Y >= 0) & (Y < N) & c.hit[yi, xi] & (dist <= depth[yi, xi] + max(tol, float(st.get("w", st.get("r", 0.01))) * 2))
        out.append({**st, "xy": np.stack([X, Y], 1), "vis": vis, "px": scale})
    return out


def _proj_pts(c: Ctx, pts):
    m = c.m
    eye, f, r, u = (np.asarray(m[k], np.float64) for k in ("eye", "f", "r", "u")); th = float(m["th"])
    V = np.asarray(pts, np.float64) - eye
    z = V @ f
    return np.stack([((V @ r) / z / th + 1) / 2 * c.N - 0.5, (1 - (V @ u) / z / th) / 2 * c.N - 0.5], 1)


def _mat_rgb(c: Ctx, name):
    mats = list(c.m["mats"])
    return c.base_t[mats.index(name)] if name in mats else np.array([0.1, 0.08, 0.07], np.float32)


def _taper_poly(xy, w, taper):
    """중심선 · 굵기(px) → 끝이 가늘어지는 획 다각형"""
    n = len(xy)
    t = np.linspace(0, 1, n)
    a, b = (taper or [1.0, 1.0])[:2]
    prof = np.minimum(1.0, np.minimum(a + (1 - a) * np.clip(t / 0.35, 0, 1), b + (1 - b) * np.clip((1 - t) / 0.35, 0, 1)))
    d = np.gradient(xy, axis=0)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1) / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
    hw = (w * prof / 2)[:, None]
    return np.vstack([xy + nrm * hw, (xy - nrm * hw)[::-1]])


def stroke_layers(c: Ctx):
    """얼굴 획 → [(색 rgb, 마스크)] 층 — 벡터 마감(vector.py)이 영역을 베지어 경로로 다시 그린다(래스터와 같은 모양).
    획(눈은 흰자 · 홍채 · 동공 · 반사점 · 눈꺼풀 층)마다 검은 판에 흰색으로만 그려 마스크를 얻는다"""
    N = c.N
    m0 = c.m
    out = []
    try:
        for st in list(m0.get("strokes") or []):
            parts = ("sclera", "iris", "pupil", "hi", "lid") if st["kind"] == "eye" else (None,)
            for part in parts:
                c.m = {**m0, "strokes": [{**st, "_only": part, "_white": True}]}
                tmp = draw_strokes(c, np.zeros((N, N, 3), np.float32))
                mk = tmp[..., 0] > 0.5
                if not mk.any():
                    continue
                if st["kind"] == "eye":
                    base = _mat_rgb(c, st["mat"])
                    col = {"sclera": hexrgb(st["sclera"]), "iris": base, "pupil": base * 0.35, "hi": np.ones(3, np.float32), "lid": hexrgb(st["lidc"])}[part]
                else:
                    col = _mat_rgb(c, st["mat"])
                    if st.get("light"):
                        col = col * (1 - float(st["light"])) + float(st["light"])
                out.append((np.asarray(col, np.float32), mk))
    finally:
        c.m = m0
    return out


def draw_strokes(c: Ctx, img):
    """얼굴 획을 그림 위에 — 매끈한 곡선(Catmull-Rom), 끝이 가늘어지는 선 · 채움 · 점. 가려진 곳은 그리지 않는다"""
    SH = 4
    for st in project_strokes(c):
        rgb = _mat_rgb(c, st["mat"])
        if st.get("light"):
            rgb = rgb * (1 - float(st["light"])) + float(st["light"])
        col = tuple(float(x) for x in rgb)
        only, white = st.get("_only"), st.get("_white")
        if white:
            col = (1.0, 1.0, 1.0)
        xy, vis = st["xy"], st["vis"]
        if st["kind"] == "eye":                                   # 눈: 흰자 안에 잘려 들어간 홍채 · 동공 → 반사점 → 위 눈꺼풀
            if vis.mean() < 0.6:
                continue
            N = img.shape[0]
            shape = _catmull(xy, 4, closed=True)
            mask = np.zeros((N, N), np.float32)
            cv2.fillPoly(mask, [np.round(shape * (1 << SH)).astype(np.int32)], 1.0, cv2.LINE_AA, SH)
            ys, xs = np.nonzero(mask > 0)
            if not len(xs):
                continue
            y0, y1, x0, x1 = max(0, ys.min() - 2), min(N, ys.max() + 3), max(0, xs.min() - 2), min(N, xs.max() + 3)
            W1, K0 = (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
            pick = lambda part, colr: (W1 if only == part else K0) if white else tuple(float(v) for v in colr)  # noqa: E731
            box = np.zeros((y1 - y0, x1 - x0, 3), np.float32) + np.asarray(pick("sclera", hexrgb(st["sclera"])), np.float32)
            off = np.array([x0, y0], np.float64)
            for key, colr in (("iris", rgb), ("pupil", rgb * 0.35)):
                P2 = _proj_pts(c, st[key]) - off
                cv2.fillPoly(box, [np.round(_catmull(P2, 3, closed=True) * (1 << SH)).astype(np.int32)], pick(key, colr), cv2.LINE_AA, SH)
            hp = _proj_pts(c, [st["hi"]])[0] - off
            V = np.asarray(st["hi"]) - np.asarray(c.m["eye"]); zz = float(V @ np.asarray(c.m["f"]))
            cv2.circle(box, tuple(int(v) for v in np.round(hp * (1 << SH))), max(1, int(float(st["hi_r"]) * c.N / 2 / float(c.m["th"]) / zz * (1 << SH))), pick("hi", (1, 1, 1)), -1, cv2.LINE_AA, SH)
            mk = mask[y0:y1, x0:x1, None]
            img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - mk) + box * mk
            L2 = _proj_pts(c, st["lid"])
            w = float(st["lid_w"]) * N / 2 / float(c.m["th"]) / zz
            cv2.fillPoly(img, [np.round(_taper_poly(_catmull(L2, 5), max(w, 1.2), [0.3, 0.9]) * (1 << SH)).astype(np.int32)], pick("lid", hexrgb(st["lidc"])), cv2.LINE_AA, SH)
            continue
        if st["kind"] == "fill":
            if vis.mean() < 0.6:
                continue
            pts = _catmull(xy, 5, closed=True)
            cv2.fillPoly(img, [np.round(pts * (1 << SH)).astype(np.int32)], col, cv2.LINE_AA, SH)
        elif st["kind"] == "dot":
            if vis[0]:
                rr = float(st["r"]) * float(st["px"][0])
                cv2.circle(img, tuple(int(v) for v in np.round(xy[0] * (1 << SH))), max(1, int(rr * (1 << SH))), col, -1, cv2.LINE_AA, SH)
        else:
            if not vis.any():
                continue
            w = float(st["w"]) * float(np.mean(st["px"]))
            dense = _catmull(xy, 6)                              # 곡선을 촘촘히 → 보이는 구간마다 따로(가려진 곳에서 끊긴다)
            dv = np.interp(np.linspace(0, len(vis) - 1, len(dense)), np.arange(len(vis)), vis.astype(float)) > 0.5
            runs, k = [], None
            for i, ok in enumerate(list(dv) + [False]):
                if ok and k is None:
                    k = i
                elif not ok and k is not None:
                    runs.append((k, i)); k = None
            full = len(runs) == 1 and runs[0] == (0, len(dense))
            for a, b in runs:
                if b - a < 3:
                    continue
                tp = st.get("taper") if full else [0.2, 0.2]
                cv2.fillPoly(img, [np.round(_taper_poly(dense[a:b], max(w, 1.2), tp) * (1 << SH)).astype(np.int32)], col, cv2.LINE_AA, SH)
    return img


# ------------------------------------------------------------------ RENDER (2026-11-23 사용자: 3D 렌더 느낌 — 다시 그린 2D 도 '클립아트' 수준)
# 재질마다 빛이 다르게 맺힌다: 금속은 주변을 비추고(반사), 꿀 · 젤리는 빛이 속을 지나 두꺼운 곳이 짙고(투과),
# 털은 가장자리가 빛나고(sheen), 나무 · 돌은 결(무늬)이 있다. 주변(env)은 하늘 · 지평선 · 바닥 색과 큰 조명판(softbox) —
# 반사 · 은은한 빛이 같은 주변에서 온다. 장면 전체(camera.aspect · backdrop)면 바닥 · 배경까지 그리고 초점 흐림 · 번짐 · 입자로 마감.
# 재질 칸: kind(plastic · metal · liquid · fuzz · wood · matte) · rough(0~1, 없으면 1-gloss) · bump(굴곡 세기) · bump_scale(굴곡 촘촘함)
# 장면 칸: env {sky, horizon, ground, key, key_power, rim} · floor {color, color2, texture: "wood"|"plain", scale} · camera {dof, focus}

def _h3(ix, iy, iz):
    n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
    n = (n ^ (n >> 13)) * 1274126177
    return ((n ^ (n >> 16)) & 0xFFFF).astype(np.float32) / 65535.0


def vnoise3(x, y, z):
    """3D 값 노이즈(0~1) — 표면 위치에 붙는 무늬라 카메라 · 자세가 바뀌어도 무늬가 미끄러지지 않는다"""
    ix, iy, iz = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    ix, iy, iz = ix.astype(np.int64), iy.astype(np.int64), iz.astype(np.int64)
    acc = 0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (ux if dx else 1 - ux) * (uy if dy else 1 - uy) * (uz if dz else 1 - uz)
                acc = acc + w * _h3(ix + dx, iy + dy, iz + dz)
    return acc


def fbm3(x, y, z, oct=3):
    a, t, f, out = 1.0, 0.0, 1.0, 0
    for _ in range(oct):
        out = out + a * vnoise3(x * f, y * f, z * f); t += a; a *= 0.5; f *= 2.03
    return out / t


def _lin(h):
    return np.power(hexrgb(h), 2.2).astype(np.float32)


def _env(d, rough, E):
    """주변 빛(선형 RGB) — d: 방향(n,3), rough: (n,) 0~1(거칠수록 조명판 가장자리가 퍼지고 약해진다)"""
    y = d[:, 1:2]
    up = E["horizon"] + (E["sky"] - E["horizon"]) * np.clip(y / 0.7, 0, 1) ** 0.8
    dn = E["horizon"] * 0.7 + (E["ground"] - E["horizon"] * 0.7) * np.clip(-y / 0.35, 0, 1)
    col = np.where(y >= 0, up, dn)
    r = rough[:, None]
    for L, colr, size in E["boxes"]:
        c = d @ L
        edge = np.cos(np.radians(size))
        w = 0.015 + 0.35 * r[:, 0] ** 1.5
        box = np.clip((c - edge + w) / (2 * w), 0, 1)
        box = box * box * (3 - 2 * box)
        col = col + colr * (box * (1 - 0.75 * r[:, 0]))[:, None] * (1 + 3 * (1 - r[:, 0]))[:, None] * 0.25
    return col


def render_style(c: Ctx, bg="#f6f1ea"):
    m = c.m; sc = m["scene"]; mats = m["mats"]; smats = sc["materials"]
    H, W = c.hit.shape
    eye = np.asarray(m["eye"], np.float32); f = np.asarray(m["f"], np.float32)
    r = np.asarray(m["r"], np.float32); u = np.asarray(m["u"], np.float32)
    th = float(m["th"]); asp = float(m.get("aspect", 1.0)) if "aspect" in m else 1.0
    L = np.asarray(m["L"], np.float32)
    e = sc.get("env") or {}
    E = {"sky": _lin(e.get("sky", "#cfd9e6")), "horizon": _lin(e.get("horizon", "#f3e6d2")), "ground": _lin(e.get("ground", "#6b5a4a"))}
    key = _lin(e.get("key", "#fff1dc")) * float(e.get("key_power", 2.6))
    rimc = _lin(e.get("rim", "#cfe2ff"))
    fh = np.array([f[0], 0, f[2]], np.float32); fh /= max(np.linalg.norm(fh), 1e-4)
    back = fh + np.array([0, 0.55, 0], np.float32); back /= np.linalg.norm(back)      # 형태 뒤 위쪽의 큰 창 — 액체 · 금속 · 바닥에 비치고 윤곽을 밝힌다
    side = r * 0.9 + np.array([0, 0.25, 0], np.float32) - f * 0.2; side /= np.linalg.norm(side)
    E["boxes"] = [(L, key * 0.9, 14), (side, _lin(e.get("fill", "#e9eef7")) * 0.9, 22), (back, rimc * 2.2, 24)]
    # 화소마다 보는 방향
    jj, ii = np.mgrid[0:H, 0:W].astype(np.float32)
    pxx = ((ii + 0.5) / W * 2 - 1) * th
    pyy = (1 - (jj + 0.5) / H * 2) * th * asp
    V = f[None, None] + r[None, None] * pxx[..., None] + u[None, None] * pyy[..., None]
    V /= np.linalg.norm(V, axis=-1, keepdims=True)
    full = bool(sc.get("backdrop") or sc.get("camera", {}).get("aspect"))
    img = np.zeros((H, W, 3), np.float32)
    # ── 배경: 주변 그대로(초점 밖) ───────────────────────────────
    if full:
        sky = ~c.hit & (c.b["depth"] >= 999)
        img[sky] = _env(V[sky], np.full(int(sky.sum()), 0.9, np.float32), E)
        nb = int(e.get("bokeh", 0))                        # 먼 배경의 빛 망울(초점 흐림이 둥글게 퍼뜨린다)
        if nb:
            rng = np.random.default_rng(int(e.get("seed", 3)))
            lay = np.zeros((H, W, 3), np.float32)
            cols = [_lin(x) for x in (e.get("bokeh_colors") or [e.get("horizon", "#f3e6d2"), e.get("sky", "#cfd9e6")])]
            for _ in range(nb):
                cx_, cy_ = rng.uniform(0, W), rng.uniform(0, H * 0.55)
                rad = rng.uniform(0.008, 0.03) * W
                cv2.circle(lay, (int(cx_), int(cy_)), int(rad), tuple(float(v) for v in cols[rng.integers(len(cols))] * rng.uniform(0.6, 1.6)), -1, cv2.LINE_AA)
            img[sky] = img[sky] + lay[sky] * 0.45
        # 바닥
        fl = sc.get("floor") or {}
        gm = ~c.hit & (c.b["depth"] < 999)
        gx, gz = c.b["gx"][gm], c.b["gz"][gm]
        fc1, fc2 = _lin(fl.get("color", "#8a5a34")), _lin(fl.get("color2", fl.get("color", "#6a4026")))
        if fl.get("texture", "wood") == "wood":
            s_ = float(fl.get("scale", 1.0))
            plank = np.floor(gz * 2.2 / s_)
            pv = _h3(plank.astype(np.int64), np.zeros_like(plank, np.int64), np.ones_like(plank, np.int64))
            grain = fbm3(gx * 0.8 / s_ + pv * 7, gz * 26 / s_, pv * 3, 4)
            ring = 0.5 + 0.5 * np.sin((gz * 30 / s_ + grain * 9 + pv * 5))
            t = np.clip(0.25 + 0.5 * ring * grain + 0.25 * pv, 0, 1)[:, None]
            alb = fc1 * (1 - t) + fc2 * t
            seam = np.abs(((gz * 2.2 / s_) % 1.0) - 0.5) > 0.493
            alb = np.where(seam[:, None], alb * 0.45, alb)
        else:
            alb = fc1 * np.ones((int(gm.sum()), 1), np.float32)
        # 바닥 그림자 · 접촉 그늘은 화면에서 한 번 뭉갠다 — 깎고 녹인 형태의 거리장은 정확하지 않아 링 · 줄무늬가 생긴다(2026-11-23 숟가락)
        gsh_s = cv2.GaussianBlur(c.b["gshadow"].astype(np.float32), (0, 0), 0.006 * W)
        gao_s = 0.45 + 0.55 * cv2.GaussianBlur(c.b["gao"].astype(np.float32), (0, 0), 0.015 * W)
        gs = (0.25 + 0.75 * gsh_s[gm]) * gao_s[gm]
        amb = _env(np.tile(np.array([[0, 1, 0]], np.float32), (int(gm.sum()), 1)), np.ones(int(gm.sum()), np.float32), E) * 0.55
        lit = alb * (key * max(float(L[1]), 0.1) * gs[:, None] * 0.75 + amb * gao_s[gm][:, None])
        Vg = V[gm]; Rg = Vg * np.array([1, -1, 1], np.float32)
        fr = (0.04 + 0.96 * (1 - np.clip(-Vg[:, 1], 0, 1)) ** 5)[:, None]
        lit = lit + fr * _env(Rg, np.full(len(Rg), 0.55, np.float32), E) * float(fl.get("reflect", 0.5)) * gs[:, None]
        img[gm] = lit
    else:
        img[:] = _lin(bg)
        gs = (0.35 + 0.65 * c.b["gshadow"]) * c.b["gao"]
        img *= (0.55 + 0.45 * gs)[..., None]
    # ── 형태 ───────────────────────────────────────────────
    h = c.hit
    if h.any():
        P = np.stack([c.b["px"][h], c.b["py"][h], c.b["pz"][h]], -1)
        N = np.stack([c.b["nx"][h], c.b["ny"][h], c.b["nz"][h]], -1)
        mi = c.mi[h]
        kind = np.array([{"plastic": 0, "metal": 1, "liquid": 2, "fuzz": 3, "wood": 4, "matte": 5, "glass": 6}.get(smats[n].get("kind", "plastic"), 0) for n in mats])[mi]
        rough = np.array([float(smats[n].get("rough", max(0.04, 1 - float(smats[n].get("gloss", 0.3))))) for n in mats], np.float32)[mi]
        bump = np.array([float(smats[n].get("bump", {"fuzz": 0.6, "wood": 0.15, "matte": 0.12}.get(smats[n].get("kind", ""), 0.04))) for n in mats], np.float32)[mi]
        bsc = np.array([float(smats[n].get("bump_scale", {"fuzz": 90, "wood": 30}.get(smats[n].get("kind", ""), 40))) for n in mats], np.float32)[mi]
        alb = np.power(c.base_t, 2.2)[mi]
        # 굴곡: 노이즈 기울기로 면 방향을 흔든다
        if (bump > 0).any():
            q = P * bsc[:, None]; eps = 0.35
            n0 = fbm3(q[:, 0], q[:, 1], q[:, 2], 2)
            g = np.stack([(fbm3(q[:, 0] + eps, q[:, 1], q[:, 2], 2) - n0), (fbm3(q[:, 0], q[:, 1] + eps, q[:, 2], 2) - n0),
                          (fbm3(q[:, 0], q[:, 1], q[:, 2] + eps, 2) - n0)], -1) / eps
            g = g - N * (g * N).sum(-1, keepdims=True)
            N = N - g * bump[:, None]
            N /= np.linalg.norm(N, axis=-1, keepdims=True)
        else:
            n0 = np.zeros(len(P), np.float32)
        Vh = V[h]
        ndv = np.clip(-(N * Vh).sum(-1), 1e-3, 1)
        ndl = (N @ L)
        sh = c.b["shadow"][h]; ao = c.b["ao"][h]
        R = Vh - 2 * (N * Vh).sum(-1, keepdims=True) * N
        Hh = L[None] - Vh; Hh /= np.linalg.norm(Hh, axis=-1, keepdims=True)
        ndh = np.clip((N * Hh).sum(-1), 0, 1)
        a2 = np.maximum(rough ** 2, 0.002) ** 2
        D = a2 / (np.pi * (ndh * ndh * (a2 - 1) + 1) ** 2)
        F0 = np.where((kind == 1)[:, None], alb, 0.04)
        Fr = F0 + (1 - F0) * ((1 - ndv) ** 5)[:, None]
        spec = (D * np.clip(ndl, 0, 1) * sh / (4 * np.maximum(ndv, 0.15)))[:, None] * Fr * key * 0.5
        envR = _env(R, rough, E)
        irr = _env(N, np.ones(len(N), np.float32), E) * 0.9
        wrap = np.clip((ndl + 0.25) / 1.25, 0, 1)
        diff = key * (wrap * np.minimum(sh + 0.08, 1))[:, None] * 0.55 + irr * ao[:, None]
        col = alb * diff * (1 - Fr) + spec + envR * Fr * ao[:, None]
        # 금속: 주변을 그대로 비춘다(자기 색을 입혀)
        k1 = kind == 1
        if k1.any():
            col[k1] = envR[k1] * Fr[k1] * (0.35 + 0.65 * ao[k1, None]) + spec[k1] * 1.5 + alb[k1] * diff[k1] * 0.04
        # 액체 · 젤리: 두꺼운 가운데는 짙고 얇은 가장자리는 밝게, 빛이 속에서 번진다
        k2 = kind == 2
        if k2.any():
            thick = ndv[k2] ** 0.6
            body = np.power(np.maximum(alb[k2], 1e-4), 0.55 + 1.6 * thick[:, None])
            glow = (np.clip(-ndl[k2], 0, 1) * 0.6 + 0.6)[:, None] * key * 0.35
            col[k2] = body * (diff[k2] * 0.9 + glow) * (1 - Fr[k2]) + envR[k2] * np.minimum(Fr[k2], 0.35) * 0.8 + spec[k2] * 2.0
        # 유리 · 얇은 막(날개): 몸은 거의 비치고 주변 반사와 가장자리만 보인다
        k6 = kind == 6
        if k6.any():
            edge = ((1 - ndv[k6]) ** 1.5)[:, None]
            col[k6] = alb[k6] * irr[k6] * 0.35 + envR[k6] * (0.12 + 0.88 * edge) * 0.9 + spec[k6] * 1.5
        # 털: 가장자리가 빛나고(sheen) 결이 거칠다
        k3 = kind == 3
        if k3.any():
            sheen = ((1 - ndv[k3]) ** 2.2)[:, None] * (alb[k3] * 0.6 + 0.4) * (irr[k3] + key * 0.25 * np.clip(ndl[k3], 0, 1)[:, None])
            col[k3] = alb[k3] * diff[k3] * (0.75 + 0.5 * n0[k3, None]) + sheen * 0.9 + spec[k3] * 0.2
        # 나무 결
        k4 = kind == 4
        if k4.any():
            Pk = P[k4] * bsc[k4, None] * 0.1
            grain = fbm3(Pk[:, 0] * 0.5, Pk[:, 1] * 8, Pk[:, 2] * 8, 3)
            ring = 0.5 + 0.5 * np.sin(Pk[:, 0] * 2 + grain * 10)
            col[k4] = col[k4] * (0.7 + 0.45 * ring)[:, None]
        # 가장자리 빛(뒤에서 오는 빛)
        rim = ((1 - ndv) ** 2.5 * np.clip(N @ back + 0.15, 0, 1))[:, None] * rimc * 0.9 * (kind != 1)[:, None]
        img[h] = col + rim
    # ── 마감: 초점 흐림 · 번짐 · 톤 · 비네트 · 입자 ────────────────────
    cam = sc.get("camera", {})
    dep = np.where(c.b["depth"] < 999, c.b["depth"], np.nan)
    fd = float(cam.get("focus_depth") or np.nanmedian(np.where(h, dep, np.nan)) if h.any() else np.nanmedian(dep))
    dof = float(cam.get("dof", 0.6 if full else 0.0))
    if dof > 0:
        dd = np.nan_to_num(np.abs(1 / np.maximum(np.nan_to_num(dep, nan=1e3), 1e-3) - 1 / fd) * fd, nan=1.0)
        coc = np.clip(dd * dof * 2.2, 0, 1)
        levels = [0, 2.5, 6, 12]
        bl = [img] + [cv2.GaussianBlur(img, (0, 0), s * W / 1080) for s in levels[1:]]
        x = coc * (len(levels) - 1)
        out = np.zeros_like(img)
        for k in range(len(levels)):
            wk = np.clip(1 - np.abs(x - k), 0, 1)[..., None]
            out += bl[k] * wk
        img = out
    bright = np.clip(img - 0.9, 0, None)
    img = img + cv2.GaussianBlur(bright, (0, 0), 18 * W / 1080) * 0.5
    a, b_, c2, d, e2 = 2.51, 0.03, 2.43, 0.59, 0.14            # ACES 근사
    img = np.clip((img * (a * img + b_)) / (img * (c2 * img + d) + e2), 0, 1)
    img = np.power(img, 1 / 2.2)
    if not full:                                           # 투명 배경으로 뽑을 때: 형태 밖은 받은 바탕 그대로(바닥 그림자만) — 톤 매핑이 바탕색을 바꾸면 투명도가 틀어진다
        gsh = ((0.35 + 0.65 * c.b["gshadow"]) * c.b["gao"])[..., None]
        img[~h] = (hexrgb(bg) * (0.55 + 0.45 * gsh))[~h]
    if full:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        vg = ((xx / W - 0.5) ** 2 * 1.2 + (yy / H - 0.48) ** 2) ** 0.5
        img *= np.clip(1.15 - 0.75 * vg, 0, 1)[..., None]
        img += (np.random.default_rng(1).standard_normal((H, W, 1)).astype(np.float32)) * 0.012
    return np.clip(img, 0, 1)


STYLES["render"] = render_style
