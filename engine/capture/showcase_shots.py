"""쇼케이스 장면(shot) 렌더 — 레퍼런스(Linear Agent · Cursor 2.0 · Raycast MCP · Screen Studio 4.0, 2026-11-09 분석)의 문법:
  - 앱 전체가 아니라 '그 부분'만 오려 어두운 바탕 위에 띄운다(둥근 모서리 · 그림자). 크게(화면 폭의 70~84%) — 글씨가 읽히게
  - 3D 기울기(원근) + 피사계 심도(초점에서 멀수록 흐림) · 천천히 밀고 들어가기(push-in)
  - 장면 사이에는 큰 글자 카드(낱말마다 흐림 → 선명 · 떠오름). 장면은 흐림 섞기(blur dissolve)로 넘긴다
  - 바탕: 짙은 바탕 위 천천히 떠도는 빛, 가장자리 어둡게(vignette)
showcase.py render 가 계획에 card · shot 이 있으면 이것을 쓴다.

계획 step 의 shot(선택)
  {"fit": 0.8, "pad": 28, "push": [1.0, 1.07], "tilt": [rx0, ry0, rx1, ry1], "dof": 0.6, "speed": 1.0, "lead": 0.4, "tail": 0.6, "cursor": true}
  tilt 는 도(°) — x축(위아래로 눕힘) · y축(좌우로 돌림)이 장면 동안 처음 값 → 끝 값으로. 없으면 정면.
card step: {"do": "card", "text": "한 줄이면 됩니다", "sub": "작은 설명(선택)", "dur": 2.2}
"""
from __future__ import annotations

import bisect
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
FONT = ROOT / "engine" / "assets" / "fonts"
DISSOLVE = 0.35


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


_F: dict = {}


def font(size: int, weight: str = "Bold"):
    from PIL import ImageFont
    k = (size, weight)
    if k not in _F:
        f = FONT / f"Pretendard-{weight}.otf"
        _F[k] = ImageFont.truetype(str(f if f.exists() else FONT / "Pretendard-Bold.otf"), size)
    return _F[k]


# ---------------------------------------------------------------- 바탕
class Backdrop:
    def __init__(self, W, H):
        import cv2
        self.W, self.H, self.cv2 = W, H, cv2
        q = 8
        self.h, self.w = H // q, W // q
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.yy, self.xx = yy, xx
        r = np.hypot((xx - self.w / 2) / (self.w * 0.62), (yy - self.h / 2) / (self.h * 0.62))
        self.vig = (1 - np.clip(r - 0.35, 0, 1) * 0.85)[..., None]

    def at(self, t: float):
        w, h = self.w, self.h
        g1 = np.exp(-(((self.xx - w * (0.28 + 0.1 * math.sin(t * 0.3))) / (w * 0.42)) ** 2 + ((self.yy - h * (0.3 + 0.08 * math.cos(t * 0.23))) / (h * 0.5)) ** 2))
        g2 = np.exp(-(((self.xx - w * (0.76 + 0.08 * math.cos(t * 0.21))) / (w * 0.36)) ** 2 + ((self.yy - h * (0.78 + 0.06 * math.sin(t * 0.27))) / (h * 0.45)) ** 2))
        img = np.full((h, w, 3), [16, 10, 11], np.float32) + g1[..., None] * np.array([120, 46, 62]) * 0.5 + g2[..., None] * np.array([110, 70, 40]) * 0.28
        img *= self.vig
        return self.cv2.resize(img.clip(0, 255).astype(np.uint8), (self.W, self.H), interpolation=self.cv2.INTER_LINEAR)


# ---------------------------------------------------------------- 글자 카드
def card_frame(bg, text: str, sub: str, age: float, life: float, W: int, H: int):
    """큰 글자: 낱말마다 0.09초 차례로 흐림 8px → 선명, 아래 14px → 제자리. 끝 0.3초 흐려지며 사라짐"""
    import cv2
    from PIL import Image, ImageDraw
    size = int(W / 17) if W >= H else int(W / 10)
    f = font(size, "Bold")
    d0 = ImageDraw.Draw(Image.new("L", (4, 4)))
    words = text.split(" ")
    space = d0.textlength(" ", font=f)
    track = -size * 0.02                                     # 자간을 조금 좁힌다(큰 제목은 기본 자간이 헐겁다)

    def wlen(w_):
        return sum(d0.textlength(c, font=f) + track for c in w_) - track
    lines, cur = [], []
    for w_ in words:                                         # 화면 폭 80% 를 넘으면 줄바꿈
        if cur and sum(wlen(x) for x in cur + [w_]) + space * len(cur) > W * 0.8:
            lines.append(cur); cur = []
        cur.append(w_)
    lines.append(cur)
    lh = size * 1.28
    y0 = H / 2 - lh * len(lines) / 2 - (size * 0.35 if sub else 0)
    out = bg.astype(np.float32)
    fade = min(1.0, max(0.0, (life - age) / 0.3)) if life else 1.0
    k = 0
    for li, ln in enumerate(lines):
        tw = sum(wlen(x) for x in ln) + space * (len(ln) - 1)
        x = (W - tw) / 2
        for w_ in ln:
            a = ease_out((age - 0.12 - k * 0.09) / 0.42) * fade
            if a > 0:
                lw = int(wlen(w_) + size * 0.6)
                lay = Image.new("L", (lw, int(size * 1.6)), 0)
                dd = ImageDraw.Draw(lay)
                cx_ = size * 0.3
                for c in w_:
                    dd.text((cx_, size * 0.18), c, font=f, fill=255)
                    cx_ += d0.textlength(c, font=f) + track
                m = np.asarray(lay).astype(np.float32) / 255.0
                bl = (1 - a) * 9
                if bl > 0.3:
                    m = cv2.GaussianBlur(m, (0, 0), bl)
                yy = int(y0 + li * lh + (1 - a) * 16 - size * 0.18)
                xx = int(x - size * 0.3)
                paste(out, m * a, xx, yy, (250, 250, 252))
            x += wlen(w_) + space
            k += 1
    if sub:
        fs = font(int(size * 0.5), "Regular")
        sa = ease_out((age - 0.25 - k * 0.09) / 0.5) * fade
        if sa > 0:
            sw_ = d0.textlength(sub, font=fs)
            lay = Image.new("L", (int(sw_ + 20), int(size * 0.8)), 0)
            ImageDraw.Draw(lay).text((10, 0), sub, font=fs, fill=255)
            m = np.asarray(lay).astype(np.float32) / 255.0
            paste(out, m * sa * 0.72, int((W - sw_) / 2 - 10), int(y0 + len(lines) * lh + size * 0.25 + (1 - sa) * 10), (225, 220, 235))
    return out.clip(0, 255).astype(np.uint8)


def paste(dst, alpha, x, y, rgb):
    """alpha(0~1, h×w)로 단색 글자를 dst(float BGR)에"""
    H, W = dst.shape[:2]
    h, w = alpha.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    a = alpha[y0 - y:y1 - y, x0 - x:x1 - x][..., None]
    col = np.array(rgb[::-1], np.float32)
    dst[y0:y1, x0:x1] = dst[y0:y1, x0:x1] * (1 - a) + col * a


# ---------------------------------------------------------------- UI 장면
def rot(rx, ry):
    a, b = math.radians(rx), math.radians(ry)
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    return Ry @ Rx


def project(w, h, W, H, scale, rx, ry, cx, cy, fov=1800.0):
    """오린 그림(w×h)의 네 모서리를 원근으로 화면에 — 카메라는 z = -fov"""
    pts = np.array([[-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], [w / 2, h / 2, 0], [-w / 2, h / 2, 0]], np.float64) * scale
    R = rot(rx, ry)
    q = pts @ R.T
    z = q[:, 2] + fov
    out = np.stack([q[:, 0] * fov / z + cx, q[:, 1] * fov / z + cy], 1)
    return out.astype(np.float32), z


def ui_frame(bg, crop, shot: dict, u: float, W: int, H: int, cursor_xy=None, press=0.0):
    """crop(BGR) 을 바탕 위에: 크기 fit · push-in · 기울기 · 그림자 · 피사계 심도"""
    import cv2
    h, w = crop.shape[:2]
    fit = float(shot.get("fit", 0.8))
    base = min(W * fit / w, H * 0.86 / h)
    p0, p1 = shot.get("push", [1.0, 1.07])
    sc = base * (p0 + (p1 - p0) * ease(u))
    tl = shot.get("tilt") or [0, 0, 0, 0]
    rx = tl[0] + (tl[2] - tl[0]) * ease(u)
    ry = tl[1] + (tl[3] - tl[1]) * ease(u)
    dx, dy = shot.get("drift", [0, 0])
    cx, cy = W / 2 + dx * W * (ease(u) - 0.5), H / 2 + dy * H * (ease(u) - 0.5)
    quad, z = project(w, h, W, H, sc, rx, ry, cx, cy)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    P = cv2.getPerspectiveTransform(src, quad)
    # 둥근 모서리 알파
    r = int(min(w, h) * 0.035 + 8)
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1); cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for c in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, c, r, 255, -1, lineType=cv2.LINE_AA)
    img = cv2.warpPerspective(crop, P, (W, H), flags=cv2.INTER_LINEAR)
    al = cv2.warpPerspective(m, P, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32) / 255.0
    # 그림자: 아래로 · 크게 흐림
    q = 4
    sh = cv2.resize(al, (W // q, H // q), interpolation=cv2.INTER_AREA)
    sh = cv2.warpAffine(sh, np.float32([[1, 0, 0], [0, 1, 34 / q]]), (W // q, H // q))
    sh = cv2.resize(cv2.GaussianBlur(sh, (0, 0), 50 / q), (W, H))
    out = bg.astype(np.float32) * (1 - sh[..., None] * 0.7)
    # 가는 밝은 테두리
    edge = (al - cv2.erode(al, np.ones((3, 3), np.uint8))).clip(0, 1) * 0.22
    out = out * (1 - al[..., None]) + img.astype(np.float32) * al[..., None]
    out = out * (1 - edge[..., None]) + 255 * edge[..., None]
    # 피사계 심도: 초점(가운데)에서 깊이가 멀수록 흐림 — 기울였을 때만
    dof = float(shot.get("dof", 0.6))
    if dof > 0 and (abs(rx) > 0.5 or abs(ry) > 0.5):
        zz = np.zeros((H, W), np.float32)
        # 깊이 지도: 네 모서리 z 를 화면 위에서 쌍선형으로 — 투영 사각형 안의 각 점을 근사(가로 · 세로 그라데이션)
        zmin, zmax = z.min(), z.max()
        if zmax - zmin > 1:
            gx = np.linspace(0, 1, W, dtype=np.float32)[None, :]; gy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
            # 모서리 순서: 좌상 · 우상 · 우하 · 좌하
            zz = (z[0] * (1 - gx) * (1 - gy) + z[1] * gx * (1 - gy) + z[2] * gx * gy + z[3] * (1 - gx) * gy).astype(np.float32)
            far = np.abs(zz - (zmin + zmax) / 2) / ((zmax - zmin) / 2 + 1e-6)
            far = (np.clip(far - 0.25, 0, 1) / 0.75) ** 1.4 * dof
            small = cv2.resize(out, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
            blur = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3.2), (W, H))
            out = out * (1 - far[..., None]) + blur * far[..., None]
    if cursor_xy is not None:
        px, py = cursor_xy
        pt = cv2.perspectiveTransform(np.float32([[[px, py]]]), P)[0, 0]
        draw_cursor(out, float(pt[0]), float(pt[1]), 30 * W / 1920 * (1 - 0.16 * press))
    return out.clip(0, 255).astype(np.uint8)


def draw_cursor(img, px, py, s):
    import cv2
    tri = np.float32([[0, 0], [0, 1.42], [0.36, 1.08], [0.6, 1.58], [0.8, 1.49], [0.57, 1.0], [1.02, 1.0]]) * s + [px, py]
    cv2.fillPoly(img, [np.int32(tri + [s * .08, s * .14])], (30, 30, 30), lineType=cv2.LINE_AA)
    cv2.fillPoly(img, [np.int32(tri)], (255, 255, 255), lineType=cv2.LINE_AA)
    cv2.polylines(img, [np.int32(tri)], True, (15, 15, 15), max(2, int(s * .07)), lineType=cv2.LINE_AA)


def dissolve(a, b, k):
    """흐림 섞기: 가운데에서 가장 흐리고, 앞 → 뒤로"""
    import cv2
    bl = math.sin(math.pi * k) * 10
    mix = cv2.addWeighted(a, 1 - k, b, k, 0)
    if bl > 0.5:
        sm = cv2.resize(mix, (mix.shape[1] // 3, mix.shape[0] // 3), interpolation=cv2.INTER_AREA)
        mix = cv2.resize(cv2.GaussianBlur(sm, (0, 0), bl / 3), (mix.shape[1], mix.shape[0]))
    return mix


# ---------------------------------------------------------------- 전체
def render_shots(out: Path, rec: dict, aspect: str, music, dst: Path | None, fps: int = 60) -> Path:
    import cv2
    plan, (sw, sh), events = rec["plan"], rec["size"], rec["events"]
    W, H = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    frames = [(t, out / "frames" / n) for t, n in rec["frames"]]
    times = [f[0] for f in frames]
    fw0 = cv2.imread(str(frames[len(frames) // 2][1])).shape[1]
    f_ = fw0 / sw
    cache: dict = {}

    def load(s):
        p = frames[max(0, bisect.bisect_right(times, s) - 1)][1]
        if p.name not in cache:
            if len(cache) > 10:
                cache.pop(next(iter(cache)))
            cache[p.name] = cv2.imread(str(p))
        return cache[p.name]

    # 장면 목록: card(정해진 길이) · ui(녹화 구간)
    shots = []
    if plan.get("title"):
        shots.append({"kind": "card", "text": plan["title"], "sub": plan.get("subtitle", ""), "dur": 2.6})
    for e in events:
        if e["do"] == "card":
            shots.append({"kind": "card", "text": e.get("text", ""), "sub": e.get("sub", ""), "dur": float(e.get("dur", 2.3))})
        elif e.get("box") and e["do"] != "goto":
            sp = e.get("shot") or {}
            lead, tail = float(sp.get("lead", 0.35)), float(sp.get("tail", 0.5))
            a, b = e["t"] - lead, e.get("t_end", e["t"]) + tail
            bx = [v * f_ for v in e["box"]]
            pad = float(sp.get("pad", 28)) * f_
            x0, y0 = max(0, int(bx[0] - pad)), max(0, int(bx[1] - pad))
            x1, y1 = min(int(sw * f_), int(bx[0] + bx[2] + pad)), min(int(sh * f_), int(bx[1] + bx[3] + pad))
            if sp.get("max_h") and (y1 - y0) > (x1 - x0) * float(sp["max_h"]):     # 세로로 긴 테두리는 가운데를 잘라 크게(대화 칸)
                hh = int((x1 - x0) * float(sp["max_h"])); cyc = (y0 + y1) // 2
                y0, y1 = max(0, cyc - hh // 2), max(0, cyc - hh // 2) + hh
            speed = float(sp.get("speed", 1.0))
            shots.append({"kind": "ui", "a": a, "b": b, "crop": (x0, y0, x1, y1), "shot": sp, "dur": (b - a) / speed, "speed": speed, "ev": e})
    if plan.get("end"):
        shots.append({"kind": "card", "text": plan["end"].get("title", ""), "sub": plan["end"].get("sub", ""), "dur": 3.2})
    t = 0.0
    for s_ in shots:
        s_["t0"] = t; t += s_["dur"]
    total = t
    bd = Backdrop(W, H)
    dst = dst or out / "showcase.mp4"
    silent = out / "showcase.silent.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)

    def draw(s_, tt, bg):
        age = tt - s_["t0"]
        if s_["kind"] == "card":
            return card_frame(bg, s_["text"], s_["sub"], age, s_["dur"], W, H)
        x0, y0, x1, y1 = s_["crop"]
        src_t = s_["a"] + age * s_["speed"]
        crop = load(src_t)[y0:y1, x0:x1]
        e, sp = s_["ev"], s_["shot"]
        cur, press = None, 0.0
        if e["do"] in ("click", "type") and sp.get("cursor", True):
            bx = [v * f_ for v in e["box"]]
            tx, ty = bx[0] + bx[2] * (0.5 if e["do"] == "click" else 0.1) - x0, bx[1] + bx[3] * 0.55 - y0
            k = ease((src_t - (e["t"] - 0.9)) / 0.9)
            cur = (tx + (1 - k) * (x1 - x0) * 0.25, ty + (1 - k) * (y1 - y0) * 0.35)
            press = max(0.0, 1 - abs(src_t - e["t"]) / 0.12) if e["do"] == "click" else 0.0
        return ui_frame(bg, crop, sp, age / max(1e-6, s_["dur"]), W, H, cur, press)

    import os
    stills = [float(x) for x in os.environ.get("FLUMA_SHOWCASE_STILLS", "").split(",") if x.strip()]   # 미리 보기: 이 시각만 그림으로
    order = [s_["t0"] for s_ in shots]

    def frame(tt):
        bg = bd.at(tt)
        i = max(0, bisect.bisect_right(order, tt) - 1)
        s_ = shots[i]
        img = draw(s_, tt, bg)
        if i + 1 < len(shots) and tt > s_["t0"] + s_["dur"] - DISSOLVE:
            k = (tt - (s_["t0"] + s_["dur"] - DISSOLVE)) / DISSOLVE
            nx = shots[i + 1]
            img = dissolve(img, draw(nx, nx["t0"], bg), ease(k))
        return img
    if stills:
        ff.stdin.close(); ff.wait(); silent.unlink(missing_ok=True)
        for tt in stills:
            cv2.imwrite(str(out / f"still_{tt:05.1f}.png"), frame(tt))
        print(f"[쇼케이스] 미리 보기 {len(stills)}장 · 전체 {total:.1f}초 · 장면 시작 {[round(x, 1) for x in order]}")
        return out
    for fi in range(int(total * fps)):
        tt = fi / fps
        bg = bd.at(tt)
        i = max(0, bisect.bisect_right([s_["t0"] for s_ in shots], tt) - 1)
        s_ = shots[i]
        img = draw(s_, tt, bg)
        # 다음 장면과 흐림 섞기(끝 DISSOLVE 초)
        if i + 1 < len(shots) and tt > s_["t0"] + s_["dur"] - DISSOLVE:
            k = (tt - (s_["t0"] + s_["dur"] - DISSOLVE)) / DISSOLVE
            nx = shots[i + 1]
            img = dissolve(img, draw(nx, nx["t0"], bg), ease(k))
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()
    # 소리: 음악 + 클릭만 아주 작게
    mp, mstart = None, 0.0
    if music == "auto":
        sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: F401
        from craft import music_pick as MP
        try:
            m = MP.pick({"id": "showcase", "format": "ad", "scenes": [{"sec": total, "narration": ""}]}, {}, plan.get("music_mood", "minimal tech product launch"), plan.get("bpm", 100))
            if m.get("use"):
                mp, mstart = ROOT / m["src"], m.get("start", 0)
                print(f"[쇼케이스] 음악: {m['title']} — {m.get('by')} · {m.get('license')}")
        except Exception as ex:  # noqa: BLE001
            print(f"[쇼케이스] 음악 고르기 실패: {ex}", file=sys.stderr)
    elif music and music != "none":
        mp = Path(music)
    tick = ROOT / "engine" / "assets" / "sfx" / "tick.wav"
    clicks = [s_["t0"] + (s_["ev"]["t"] - s_["a"]) / s_["speed"] for s_ in shots if s_["kind"] == "ui" and s_["ev"]["do"] == "click"]
    ins, filt, labels, n = ["-i", str(silent)], [], [], 1
    if mp and mp.exists():
        ins += ["-ss", f"{mstart:.2f}", "-i", str(mp)]
        filt.append(f"[{n}:a]afade=t=in:d=0.8,afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5,loudnorm=I=-15:TP=-2,aformat=channel_layouts=stereo[m]")
        labels.append("[m]"); n += 1
    if tick.exists() and plan.get("ui_sounds", True):
        for c in clicks:
            ins += ["-i", str(tick)]
            filt.append(f"[{n}:a]volume=-18dB,adelay={int(c * 1000)}|{int(c * 1000)},aformat=channel_layouts=stereo[u{n}]")
            labels.append(f"[u{n}]"); n += 1
    if labels:
        filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[a]" if len(labels) > 1 else f"{labels[0]}anull[a]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-t", f"{total:.2f}", str(dst)], check=True)
        silent.unlink()
    else:
        silent.replace(dst)
    print(f"[쇼케이스] 장면 {len(shots)}개 · {total:.1f}초 · {fps}fps ({aspect}) → {dst}")
    return dst
