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
                self.hair = mask
                up = n_s @ u
                self.band |= mask & (np.abs(up - 0.62) < 0.04) & (self.b["ndv"] > 0.25)

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
