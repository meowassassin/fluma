#!/usr/bin/env python3
"""제품 소개 영상(쇼케이스) — 실제 앱을 대본대로 움직여 녹화하고, 카메라가 짚을 곳으로 줌 인 · 아웃하며 나머지는 흐리게, 글자는 한 자씩.
에이전트 · MCP 도구 소개 페이지의 데모처럼: 화면을 그대로 보여 주지 않고 '지금 볼 한 곳'을 강조해 가며 보여 준다.

  python3 engine/capture/showcase.py record <계획.json> <출력 폴더>        # 1) 실제 녹화(프레임 + 동작마다 대상 위치)
  python3 engine/capture/showcase.py render <출력 폴더> [--aspect 16:9|9:16|1:1] [--music auto|<파일>|none] [--out x.mp4]
  python3 engine/capture/showcase.py make   <계획.json> <출력 폴더> [...]  # 둘 다

계획(JSON)
  { "url": "http://127.0.0.1:4311/", "viewport": [1440, 900], "scale": 2, "lang": "en", "theme": "light",
    "title": "Fluma",                                   # 첫 화면 큰 글자(없으면 생략)
    "end": {"title": "Fluma", "sub": "github.com/…"},    # 끝 화면
    "steps": [
      {"do": "wait", "ms": 600, "caption": "Talk to it like a producer"},
      {"do": "focus", "target": ".home-chat", "ms": 1600, "caption": "…"},          # 움직이지 않고 그곳만 짚기
      {"do": "type", "target": "textarea", "text": "Make a 30s short about …", "delay": 45},   # 실제로 한 자씩 입력(실시간)
      {"do": "click", "target": "text=Trends", "caption": "…"},
      {"do": "press", "key": "Enter"}, {"do": "hover", "target": "…"}, {"do": "scroll", "by": 500},
      {"do": "goto", "url": "/settings/media"}
    ] }
  target 은 Playwright 선택자. 동작마다 'zoom'(1~3, 없으면 대상 크기로 자동) · 'hold'(ms, 동작 뒤 머묾) · 'overview': true(전체로 빠짐).
연출(render)
  - 카메라: 동작 대상 상자로 줌 인(상자가 화면 폭의 ~55%), 다음 대상이 멀면 중간에 줌 아웃했다가 다시 들어간다(가감속)
  - 강조: 줌 인 중에는 대상 상자만 선명 · 둥근 모서리 · 그림자, 나머지는 흐리게 · 어둡게
  - 커서: 대상까지 곡선으로 이동 · 누르면 물결. 입력은 실제 녹화(한 자씩 · 실시간)
  - 글자: 동작마다 caption 이 한 자씩 생긴다. 기다리기만 하는 긴 구간은 빨리 감는다
  - 화면 이동: 로딩은 잘라 내고 앞 화면을 새 화면으로 겹쳐 넘김(그 전에 전체로 빠짐) · 짚는 곳은 살짝 떠오름(크기 · 그림자 · 테두리)
  - 음악: --music auto 면 music_pick 으로 맞는 무료 곡(박자 · 힘 있는 구간 · 페이드) + 아주 작은 클릭 · 넘김 소리(ui_sounds: false 면 끔) · 60fps
결과: <출력>/frames/*.jpg · events.json(녹화) → <출력>/showcase.mp4
비밀(이메일 · 키 · 계정 번호)은 webrec 과 같은 규칙으로 늘 가린다.
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
FPS = 30
FONT = ROOT / "engine" / "assets" / "fonts"


# ---------------------------------------------------------------- 녹화
def record(plan: dict, out: Path) -> None:
    from playwright.sync_api import sync_playwright
    from webrec import MASK_JS, MASK_TEXT
    out.mkdir(parents=True, exist_ok=True)
    fdir = out / "frames"
    if fdir.exists():
        for f in fdir.glob("*.jpg"):
            f.unlink()
    fdir.mkdir(exist_ok=True)
    vw, vh = plan.get("viewport", [1440, 900])
    scale = float(plan.get("scale", 2))
    base = plan["url"].rstrip("/")
    frames: list[tuple[float, str]] = []
    events: list[dict] = []
    lang = plan.get("lang")
    with sync_playwright() as p:
        # 화면 녹화(screencast)는 device_scale_factor 를 무시하고 1배로 온다 — 브라우저 배율을 강제해야 2배(줌 인해도 선명)
        browser = p.chromium.launch(headless=True, args=[f"--force-device-scale-factor={scale:g}"])
        ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=scale, color_scheme=plan.get("theme", "light"),
                                  locale={"en": "en-US", "ko": "ko-KR", "zh": "zh-CN"}.get(lang or "", "ko-KR"))
        ctx.add_init_script(MASK_JS)
        if lang:   # 화면 말(Fluma: zustand persist 'fluma.lang') — 설정 파일은 건드리지 않는다
            ctx.add_init_script(f"try {{ localStorage.setItem('fluma.lang', JSON.stringify({{state: {{lang: '{lang}'}}, version: 0}})); }} catch (e) {{}}")
        page = ctx.new_page()
        page.goto(plan["url"], wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(int(plan.get("settle_ms", 1200)))
        cdp = ctx.new_cdp_session(page)
        t0 = time.time()

        def on_frame(prm):
            ts = float(prm["metadata"]["timestamp"]) - t0
            f = fdir / f"{len(frames):05d}.jpg"
            f.write_bytes(base64.b64decode(prm["data"]))
            frames.append((ts, f.name))
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]})
            except Exception:
                pass

        cdp.on("Page.screencastFrame", on_frame)
        page.evaluate("([p]) => { window.__flumaMaskTimer = setInterval(() => window.__flumaMask && window.__flumaMask(p, []), 150); }", [MASK_TEXT])
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "everyNthFrame": 1, "maxWidth": int(vw * scale), "maxHeight": int(vh * scale)})

        def measure(loc):
            b = loc.bounding_box()
            return [round(b["x"] * scale), round(b["y"] * scale), round(b["width"] * scale), round(b["height"] * scale)] if b else None

        def box(sel):
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="attached", timeout=8000)
                # 화면 밖이면 부드럽게 굴려 가운데로(굴러가는 모습도 영상에 담긴다) — 순간 이동하면 어색했다
                off = loc.evaluate("e => { const r = e.getBoundingClientRect(); return r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth; }")
                if off:
                    loc.evaluate("e => e.scrollIntoView({behavior: 'smooth', block: 'center'})")
                    page.wait_for_timeout(1100)
                loc.wait_for(state="visible", timeout=8000)
                b = loc.bounding_box()
                return loc, ([round(b["x"] * scale), round(b["y"] * scale), round(b["width"] * scale), round(b["height"] * scale)] if b else None)
            except Exception as e:  # noqa: BLE001
                print(f"[쇼케이스] 대상을 못 찾음: {sel} ({str(e).splitlines()[0][:80]})", file=sys.stderr)
                return None, None

        try:
            page.wait_for_timeout(500)
            for i, s in enumerate(plan.get("steps") or []):
                do = s.get("do")
                ev = {k: s[k] for k in ("caption", "zoom", "overview", "shot", "text", "sub", "dur") if k in s}
                ev.update({"i": i, "do": do})
                if do == "card":                                 # 글자 카드 — 녹화하지 않는다(렌더가 장면 사이에 넣음)
                    events.append(ev); continue
                loc, b = box(s["target"]) if s.get("target") else (None, None)
                ev["box"] = b
                ev["t"] = round(time.time() - t0, 3)
                if do == "click" and loc:
                    page.wait_for_timeout(650)              # 카메라 · 커서가 먼저 도착할 시간(렌더에서 이 사이를 쓴다)
                    ev["t"] = round(time.time() - t0, 3)
                    loc.click(timeout=8000)
                elif do == "type" and loc:
                    loc.click(timeout=8000)
                    page.wait_for_timeout(350)
                    ev["t"] = round(time.time() - t0, 3)
                    loc.press_sequentially(s["text"], delay=int(s.get("delay", 75)))
                    ev["t_end"] = round(time.time() - t0, 3)
                elif do == "press":
                    page.keyboard.press(s["key"])
                elif do == "hover" and loc:
                    loc.hover(timeout=8000)
                elif do == "scroll":
                    page.mouse.wheel(0, float(s.get("by", 500)))
                elif do == "scrollthrough" and loc:            # 대화 · 목록을 천천히 훑는다(실제로 굴러가는 모습이 영상에 담김)
                    ms_ = int(s.get("scroll_ms", 4000))
                    loc.evaluate("""(e, a) => new Promise(res => { let el = e; while (el && el !== document.body && !(el.scrollHeight > el.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(el).overflowY))) el = el.parentElement;
                        if (!el || el === document.body) el = document.scrollingElement; const y0 = a.from === 'top' ? 0 : el.scrollTop, y1 = a.to === 'bottom' ? el.scrollHeight - el.clientHeight : y0 + a.by;
                        if (a.from === 'top') el.scrollTop = 0; const t0 = performance.now(); const f = (n) => { const u = Math.min(1, (n - t0) / a.ms); const k = u < .5 ? 4*u*u*u : 1 - Math.pow(-2*u + 2, 3) / 2;
                        el.scrollTop = y0 + (y1 - y0) * k; u < 1 ? requestAnimationFrame(f) : res(); }; setTimeout(() => requestAnimationFrame(f), 300); })""",
                                 {"ms": ms_, "from": s.get("from", "here"), "to": s.get("to", "by"), "by": float(s.get("by", 2400))})
                    ev["t"] = round(time.time() - t0 - ms_ / 1000 - 0.1, 3)
                elif do == "goto":
                    u = s["url"] if s["url"].startswith("http") else base + s["url"]
                    ev["t0"] = round(time.time() - t0, 3)          # 이동 직전 — 렌더는 t0~t(로딩)를 잘라 내고 앞뒤 화면을 겹쳐 넘긴다
                    page.goto(u, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(250)
                    ev["t"] = round(time.time() - t0, 3)
                page.wait_for_timeout(int(s.get("ms", s.get("hold", 900))))
                ev.setdefault("t_end", round(time.time() - t0, 3))
                if s.get("union"):                              # 여러 요소를 한 장면으로(예: 마지막 사용자 말 ~ 에이전트 진행 상황)
                    bs = []
                    for sel in s["union"]:
                        try:
                            bb = measure(page.locator(sel).first)
                            if bb and bb[2] > 4:
                                bs.append(bb)
                        except Exception:
                            pass
                    if bs:
                        ux0, uy0 = min(b_[0] for b_ in bs), min(b_[1] for b_ in bs)
                        ev["box"] = [ux0, uy0, max(b_[0] + b_[2] for b_ in bs) - ux0, max(b_[1] + b_[3] for b_ in bs) - uy0]
                elif s.get("frame"):                            # 장면으로 오릴 테두리(누르는 대상과 다를 때 — 예: 영상을 누르고 편집기 전체를 보여 줌)
                    try:
                        fb = measure(page.locator(s["frame"]).first)
                        if fb and fb[2] > 4:
                            ev["box"] = fb
                    except Exception:
                        pass
                elif loc and do in ("focus", "hover"):          # 머무는 동안 자리가 바뀌었을 수 있다(그림 로딩 · 펼침) — 끝 자리를 강조 상자로
                    try:
                        be = measure(loc)
                        if be and be[2] > 4:
                            ev["box"] = be
                    except Exception:
                        pass
                events.append(ev)
            page.wait_for_timeout(600)
        finally:
            try:
                last = page.screenshot(type="jpeg", quality=90)
                f = fdir / f"{len(frames):05d}.jpg"; f.write_bytes(last); frames.append((time.time() - t0, f.name))
            except Exception:
                pass
            dur = time.time() - t0
            try:
                cdp.send("Page.stopScreencast")
            except Exception:
                pass
            browser.close()
    frames.sort()
    (out / "events.json").write_text(json.dumps({"plan": plan, "size": [int(vw * scale), int(vh * scale)], "dur": round(dur, 3),
                                                 "frames": frames, "events": events}, ensure_ascii=False, indent=1), "utf-8")
    print(f"[쇼케이스] 녹화 {dur:.1f}초 · 프레임 {len(frames)} · 동작 {len(events)} → {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


# ---------------------------------------------------------------- 시간 (기다림 빨리 감기 · 화면 이동은 로딩을 잘라 냄)
def time_map(events: list[dict], dur: float, ff: bool = False) -> list[tuple[float, float]]:
    """[(출력 초, 녹화 초)] 조각 — 동작 사이 1.6초를 넘는 '아무 일 없는' 구간은 0.6초로, 화면 이동(goto)의 로딩(t0~t)은 0초로"""
    keep = []
    for e in events:
        a = e["t"] if e.get("do") == "goto" else max(0.0, e["t"] - 1.3)
        b = max(e.get("t_end", e["t"]), e["t"]) + 0.8
        keep.append((a, b))
    gotos = [(e["t0"], e["t"]) for e in events if e.get("do") == "goto" and "t0" in e]
    for g0, g1 in gotos:                                   # 로딩(g0~g1)은 어느 구간도 먹지 않게 — 앞 구간은 g0 에서 끊고, 뒤 구간의 앞당김은 g1 부터
        keep = [(max(a, g1) if g0 <= a < g1 else a, min(b, g0) if a < g0 < b else b) for a, b in keep]
        keep = [(a, b) for a, b in keep if b > a + 0.01]
    keep.sort()
    pts, src, outt = [(0.0, 0.0)], 0.0, 0.0
    for a, b in keep + [(dur, dur)]:
        if a > src:
            gap = a - src
            cut = any(src - 0.05 <= g0 and g1 <= a + 0.05 for g0, g1 in gotos)
            # 기다림: 소개 영상은 1초로 자르고, 데모(ff)는 빨리 감기(최대 12배 · 1~4초) — 에이전트가 일하는 모습이 빠르게 보이게
            g = 0.0 if cut else ((min(4.0, max(1.0, gap / 12)) if ff else 1.0) if gap > 2.5 else gap)
            outt += g; src = a
            pts.append((outt, src))
        if b > src:
            outt += b - src; src = b
            pts.append((outt, src))
    return pts


def src_time(pts, t):
    for (o0, s0), (o1, s1) in zip(pts, pts[1:]):
        if t <= o1:
            return s0 + (s1 - s0) * ((t - o0) / (o1 - o0) if o1 > o0 else 0)
    return pts[-1][1]


def out_time(pts, s):
    for (o0, s0), (o1, s1) in zip(pts, pts[1:]):
        if s <= s1:
            return o0 + (o1 - o0) * ((s - s0) / (s1 - s0) if s1 > s0 else 0)
    return pts[-1][0]


def cuts(events, pts) -> list[tuple[float, float]]:
    """[(출력 초, 이동 직전 녹화 초)] — 이 시각부터 앞 화면을 새 화면으로 겹쳐 넘긴다"""
    return [(out_time(pts, e["t"]), e["t0"] - 0.03) for e in events if e.get("do") == "goto" and "t0" in e]


# ---------------------------------------------------------------- 카메라
def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def camera_keys(events, size, pts, W, H, frame_w, zmax: float = 2.6) -> list[tuple[float, float, float, float, float]]:
    """[(출력 초, cx, cy, zoom, 강조 0~1)] — zoom 1 = 창 전체. 상자 폭이 화면의 ~55% 가 되게(최대 2.6배).
    화면 이동 전에는 전체로 빠져 있고(새 화면이 줌 인 상태로 툭 나오지 않게), 멀리 떨어진 다음 대상은 빠졌다가 들어간다"""
    sw, sh = size
    full = (sw / 2, sh / 2, 1.0, 0.0)
    keys = [(0.0, *full)]
    prev = full
    for e in events:
        b = e.get("box")
        t = out_time(pts, e["t"])
        te = out_time(pts, e.get("t_end", e["t"]))
        if e.get("do") == "goto" or e.get("overview") or not b:
            if e.get("do") == "goto" or e.get("overview"):
                keys += [(max(keys[-1][0] + 0.05, t - 0.9), *keys[-1][1:]), (max(keys[-1][0] + 0.1, t - 0.02), *full), (t + 0.5, *full)]
                prev = full
            continue
        x, y, w, h = b
        z = e.get("zoom") or min(zmax, max(1.25, (W * 0.55) / (w * frame_w / sw)))
        z = min(z, (H * 0.68) / max(1, h * frame_w / sw))
        z = max(1.15, z)
        tgt = (x + w / 2, y + h / 2, float(z), 1.0)
        arrive = max(keys[-1][0] + 0.9, t - 0.6)
        far = math.hypot(tgt[0] - prev[0], tgt[1] - prev[1]) > sw * 0.35 and prev[2] > 1.1
        if far:
            mid = ((prev[0] + tgt[0]) / 2, (prev[1] + tgt[1]) / 2, 1.0, 0.0)
            keys.append((max(keys[-1][0] + 0.05, arrive - 1.6), *prev))
            keys.append((arrive - 0.8, *mid))
        else:
            keys.append((max(keys[-1][0] + 0.05, arrive - 1.2), *keys[-1][1:]))
        keys.append((arrive, *tgt))
        keys.append((max(arrive + 0.05, te + 0.15), *tgt))
        prev = tgt
    return keys


def cam_at(keys, t):
    if t <= keys[0][0]:
        return keys[0][1:]
    for k0, k1 in zip(keys, keys[1:]):
        if t <= k1[0]:
            u = ease((t - k0[0]) / max(1e-6, k1[0] - k0[0]))
            return tuple(a + (b - a) * u for a, b in zip(k0[1:], k1[1:]))
    return keys[-1][1:]


# ---------------------------------------------------------------- 그리기
_FONTS: dict = {}


def font(size: int, bold=True):
    from PIL import ImageFont
    k = (size, bold)
    if k not in _FONTS:
        for n in (("Pretendard-Bold.otf", "Pretendard-SemiBold.otf") if bold else ("Pretendard-Medium.otf", "Pretendard-Regular.otf")) + ("Geist.ttf",):
            f = FONT / n
            if f.exists():
                _FONTS[k] = ImageFont.truetype(str(f), size); break
        else:
            _FONTS[k] = ImageFont.load_default()
    return _FONTS[k]


def kinetic(img, txt: str, age: float, life: float, size: int, cy: float, sub: str = "", glass=True, rate=0.045):
    """글자가 한 자씩: 자마다 0.16초에 걸쳐 투명 → 불투명 · 아래에서 10px 떠오름. 뒤 상자(유리)는 나온 글자만큼 자란다. 끝 0.25초에 사라짐"""
    import cv2
    from PIL import Image, ImageDraw
    H, W = img.shape[:2]
    out_a = min(1.0, max(0.0, (life - age) / 0.25)) if life else 1.0
    if out_a <= 0 or age < 0:
        return img
    f = font(size)
    d0 = ImageDraw.Draw(Image.new("L", (8, 8)))
    widths = [d0.textlength(txt[:k], font=f) for k in range(len(txt) + 1)]
    tw = widths[-1]
    x0 = (W - tw) / 2
    shown = min(len(txt), int(age / rate) + 1)
    pad_x, pad_y = size * 0.62, size * 0.42
    if glass:                                             # 유리 상자: 뒤를 흐리고 어둡게 · 가는 밝은 테두리 — 나온 글자 폭까지만
        # 상자는 글자 왼쪽 끝에 붙어, 나온 글자(+ 지금 떠오르는 한 자)만큼 오른쪽으로 자란다 — 빈 상자가 먼저 보이지 않게 불투명도도 함께
        grow = widths[min(len(txt), shown)] + (widths[min(len(txt), shown + 1)] - widths[min(len(txt), shown)]) * min(1.0, (age % rate) / rate if shown < len(txt) else 1)
        bx0, bx1 = int(x0 - pad_x), int(x0 + max(size * 0.6, grow) + pad_x)
        out_a = out_a * min(1.0, age / 0.14)
        by0, by1 = int(cy - pad_y), int(cy + size * 1.18 + pad_y * 0.6)
        bx0, by0 = max(0, bx0), max(0, by0); bx1, by1 = min(W, bx1), min(H, by1)
        if bx1 - bx0 > 8 and by1 - by0 > 8:
            reg = img[by0:by1, bx0:bx1]
            sm = cv2.resize(reg, (max(1, reg.shape[1] // 6), max(1, reg.shape[0] // 6)), interpolation=cv2.INTER_AREA)
            gl = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 3), (reg.shape[1], reg.shape[0]))
            gl = (gl * 0.42 + np.array([28, 16, 18]) * 0.3).astype(np.uint8)
            m = rounded_mask(bx1 - bx0, by1 - by0, 0, 0, bx1 - bx0 - 1, by1 - by0 - 1, (by1 - by0) / 2).astype(np.float32)[..., None] / 255.0 * out_a
            img[by0:by1, bx0:bx1] = (reg * (1 - m) + gl * m).astype(np.uint8)
            ring = np.zeros((by1 - by0, bx1 - bx0), np.uint8)
            r_ = int((by1 - by0) / 2)
            cv2.rectangle(ring, (r_, 0), (bx1 - bx0 - r_, by1 - by0 - 1), 255, 1, lineType=cv2.LINE_AA)
            sub_img = img[by0:by1, bx0:bx1].astype(np.float32)
            edge = rounded_mask(bx1 - bx0, by1 - by0, 0, 0, bx1 - bx0 - 1, by1 - by0 - 1, r_) - rounded_mask(bx1 - bx0, by1 - by0, 1.5, 1.5, bx1 - bx0 - 2.5, by1 - by0 - 2.5, r_ - 1.5)
            e_ = (edge.astype(np.float32) / 255.0 * 0.22 * out_a)[..., None]
            img[by0:by1, bx0:bx1] = (sub_img * (1 - e_) + 255 * e_).astype(np.uint8)
    lay = Image.new("RGBA", (W, int(size * 2.6)), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    base_y = size * 0.5
    for k, ch in enumerate(txt[:shown]):
        a = min(1.0, (age - k * rate) / 0.16) * out_a
        if a <= 0:
            continue
        dy = (1 - ease(a)) * 10
        d.text((x0 + widths[k], base_y + dy), ch, font=f, fill=(255, 255, 255, int(255 * a)))
    if sub and age > 0.5:
        fs = font(int(size * 0.46), bold=False)
        sa = min(1.0, (age - 0.5) / 0.4) * out_a
        sw_ = d.textlength(sub, font=fs)
        lay2 = Image.new("RGBA", (W, int(size * 1.2)), (0, 0, 0, 0))
        ImageDraw.Draw(lay2).text(((W - sw_) / 2, (1 - ease(sa)) * 8), sub, font=fs, fill=(214, 216, 230, int(230 * sa)))
        over_at(img, np.asarray(lay2), int(cy + size * 1.55))
    over_at(img, np.asarray(lay), int(cy - base_y))
    return img


def over_at(dst, rgba, y0):
    H = dst.shape[0]
    y1 = min(H, y0 + rgba.shape[0])
    if y1 <= max(0, y0):
        return dst
    src = rgba[max(0, -y0): y1 - y0]
    a = src[..., 3:4].astype(np.float32) / 255.0
    reg = dst[max(0, y0):y1]
    dst[max(0, y0):y1] = (reg * (1 - a) + src[..., :3][..., ::-1] * a).astype(np.uint8)
    return dst


def rounded_mask(W, H, x0, y0, x1, y1, r):
    import cv2
    m = np.zeros((int(H), int(W)), np.uint8)
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    if x1 <= x0 or y1 <= y0:
        return m
    r = int(max(2, min(r, (x1 - x0) / 2, (y1 - y0) / 2)))
    cv2.rectangle(m, (x0 + r, y0), (x1 - r, y1), 255, -1)
    cv2.rectangle(m, (x0, y0 + r), (x1, y1 - r), 255, -1)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, lineType=cv2.LINE_AA)
    return m


def soft_shadow(W, H, x0, y0, x1, y1, r, off, sigma):
    """둥근 상자 그림자 — 4분의 1 크기에서 흐려 키운다(빠름)"""
    import cv2
    q = 4
    m = rounded_mask(W // q, H // q, x0 / q, (y0 + off) / q, x1 / q, (y1 + off) / q, r / q).astype(np.float32) / 255.0
    m = cv2.GaussianBlur(m, (0, 0), sigma / q)
    return cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)


def cursor(img, px, py, s, press=0.0):
    """macOS 비슷한 화살표 — 흰 몸 · 검은 테두리 · 부드러운 그림자, 누르면 살짝 작아짐"""
    import cv2
    s = s * (1 - 0.16 * press)
    tri = np.float32([[0, 0], [0, 1.42], [0.36, 1.08], [0.6, 1.58], [0.8, 1.49], [0.57, 1.0], [1.02, 1.0]]) * s + [px, py]
    sh = np.zeros(img.shape[:2], np.float32)
    cv2.fillPoly(sh, [np.int32(tri + [s * 0.08, s * 0.14])], 1.0, lineType=cv2.LINE_AA)
    x0, y0 = int(px - s), int(py - s)
    x1, y1 = int(px + s * 2.5), int(py + s * 2.5)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.shape[1], x1), min(img.shape[0], y1)
    if x1 > x0 + 2 and y1 > y0 + 2:
        sh[y0:y1, x0:x1] = cv2.GaussianBlur(sh[y0:y1, x0:x1], (0, 0), s * 0.12)
        img[y0:y1, x0:x1] = (img[y0:y1, x0:x1] * (1 - sh[y0:y1, x0:x1, None] * 0.45)).astype(np.uint8)
    cv2.fillPoly(img, [np.int32(tri)], (255, 255, 255), lineType=cv2.LINE_AA)
    cv2.polylines(img, [np.int32(tri)], True, (15, 15, 15), max(2, int(s * 0.07)), lineType=cv2.LINE_AA)


def badge(img, txt: str, W: int):
    from PIL import Image, ImageDraw
    f = font(max(20, W // 64))
    d0 = ImageDraw.Draw(Image.new("L", (4, 4)))
    tw = d0.textlength(txt, font=f)
    w_, h_ = int(tw + f.size * 1.2), int(f.size * 1.8)
    lay = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w_ - 1, h_ - 1), radius=h_ // 2, fill=(20, 18, 30, 210))
    d.text((f.size * 0.6, f.size * 0.36), txt, font=f, fill=(255, 255, 255, 240))
    a = np.asarray(lay)
    x0, y0 = W - w_ - int(W * 0.035), int(W * 0.03)
    reg = img[y0:y0 + h_, x0:x0 + w_]
    al = a[..., 3:4].astype(np.float32) / 255.0
    img[y0:y0 + h_, x0:x0 + w_] = (reg * (1 - al) + a[..., :3][..., ::-1] * al).astype(np.uint8)
    return img


def to_gif(mp4: Path, gif: Path, width: int = 1280, fps: int = 20) -> Path:
    """발표 자료 · 페이지용 GIF — 두 번 거쳐 색 표(palette)를 영상에 맞춰 만들고, 바뀐 곳만 다시 그려 크기를 줄인다"""
    # bayer 떨림(규칙 무늬)이 오차 확산보다 프레임 사이 변화가 적어 훨씬 작다(같은 31초: 60MB → 21MB)
    vf = f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", vf, "-loop", "0", str(gif)], check=True)
    return gif


def render(out: Path, aspect: str, music: str | None, dst: Path | None, fps: int = 60) -> Path:
    import cv2
    rec = json.loads((out / "events.json").read_text("utf-8"))
    if any(e.get("do") == "card" or e.get("shot") for e in rec["events"]):   # 장면(shot) 문법 — 레퍼런스처럼 오려 띄우기 · 기울기 · 글자 카드
        from showcase_shots import render_shots
        return render_shots(out, rec, aspect, music, dst, fps)
    plan, (sw, sh), events = rec["plan"], rec["size"], rec["events"]
    W, H = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    frames = [(t, out / "frames" / n) for t, n in rec["frames"]]
    fw0 = cv2.imread(str(frames[len(frames) // 2][1])).shape[1]          # 실제 프레임 폭 — 상자(2배 좌표)를 거기에 맞춘다
    if abs(fw0 - sw) > 4:
        f_ = fw0 / sw
        sw, sh = fw0, int(round(sh * f_))
        for e in events:
            if e.get("box"):
                e["box"] = [v * f_ for v in e["box"]]
    demo = plan.get("style") == "demo"          # 데모(GIF · 페이지): 실제 화면 그대로 · 자동 줌만 · 흐림 없음 · 빨리 감기 · 제목 카드 없음
    pts = time_map(events, rec["dur"], ff=demo)
    cut_list = cuts(events, pts)
    body = pts[-1][0]
    intro = 2.8 if plan.get("title") and not demo else 0.0
    outro = 3.4 if plan.get("end") and not demo else (0.6 if demo else 0.8)
    total = intro + body + outro
    frame_w = W * (0.94 if demo else 0.86 if W >= H else 0.94)
    keys = camera_keys(events, (sw, sh), pts, W, H, frame_w, zmax=1.7 if demo else 2.6)
    boxed = [(out_time(pts, e["t"]), out_time(pts, e.get("t_end", e["t"])), e["box"]) for e in events if e.get("box")]
    cache: dict[str, tuple] = {}

    def load(p: Path):
        k = p.name
        if k not in cache:
            if len(cache) > 8:
                cache.pop(next(iter(cache)))
            im = cv2.imread(str(p))
            small = cv2.resize(im, (im.shape[1] // 6, im.shape[0] // 6), interpolation=cv2.INTER_AREA)
            bl = cv2.resize(cv2.GaussianBlur(small, (0, 0), 4.5), (im.shape[1], im.shape[0]), interpolation=cv2.INTER_LINEAR)
            cache[k] = (im, (bl * 0.42).astype(np.uint8))
        return cache[k]

    times = [f[0] for f in frames]
    import bisect

    def frame_at(s):
        return frames[max(0, bisect.bisect_right(times, s) - 1)][1]

    def background(t):
        """짙은 보라 그라데이션 + 천천히 떠도는 빛(바탕이 멈춰 보이지 않게)"""
        q = 8
        h, w = H // q, W // q
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        gx, gy = w * (0.3 + 0.12 * math.sin(t * 0.35)), h * (0.25 + 0.1 * math.cos(t * 0.27))
        glow = np.exp(-(((xx - gx) / (w * 0.45)) ** 2 + ((yy - gy) / (h * 0.55)) ** 2))[..., None]
        base = (1 - yy[..., None] / h) * np.array([70, 30, 40]) + (yy[..., None] / h) * np.array([20, 10, 12])
        img = base + glow * np.array([120, 50, 70]) * 0.55
        return cv2.resize(img.clip(0, 255).astype(np.uint8), (W, H), interpolation=cv2.INTER_LINEAR)

    caps = [(out_time(pts, e["t"]) - (0.0 if e.get("do") == "goto" else 0.6), out_time(pts, e.get("t_end", e["t"])) + 1.2, e["caption"])
            for e in events if e.get("caption")]
    caps = [(a, min(b, caps[i + 1][0] - 0.05) if i + 1 < len(caps) else b, c) for i, (a, b, c) in enumerate(caps)]
    clicks = [out_time(pts, e["t"]) for e in events if e.get("do") == "click" and e.get("box")]
    cur_pts = [(out_time(pts, e["t"]), (e["box"][0] + e["box"][2] / 2, e["box"][1] + e["box"][3] * 0.62)) for e in events
               if e.get("box") and e.get("do") in ("click", "type", "hover")]
    dst = dst or out / "showcase.mp4"
    silent = out / "showcase.silent.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    csize = max(34, W // 34) if W >= H else max(40, W // 22)
    for fi in range(int(total * fps)):
        t = fi / fps
        tb = min(max(0.0, t - intro), body)
        img = background(0.0 if demo else t)          # 데모는 바탕을 멈춘다 — 움직이는 빛은 GIF 의 모든 프레임을 바꿔 크기가 몇 배로 커졌다
        s = src_time(pts, tb)
        sharp, blur = load(frame_at(s))
        # 화면 이동: 앞 화면 → 새 화면을 0.4초 동안 겹쳐 넘긴다(로딩 화면은 잘림)
        for tc, s_prev in cut_list:
            if tc <= tb < tc + 0.4:
                a_ = ease((tb - tc) / 0.4)
                ps_, pb_ = load(frame_at(s_prev))
                sharp = cv2.addWeighted(ps_, 1 - a_, sharp, a_, 0); blur = cv2.addWeighted(pb_, 1 - a_, blur, a_, 0)
                break
        cx, cy, z, foc = cam_at(keys, tb)
        frect = None
        if t < intro:
            z, foc = 0.9 + 0.1 * ease(t / max(intro, 1e-6)), 0.0
        k = frame_w / sw * z
        M = np.float32([[k, 0, W / 2 - cx * k], [0, k, H * 0.5 - cy * k]])
        x0, y0 = M[0, 2], M[1, 2]
        x1, y1 = x0 + sw * k, y0 + sh * k
        rad = 22 * z
        shd = soft_shadow(W, H, x0, y0, x1, y1, rad, 30, 44)
        img = (img * (1 - shd[..., None] * 0.6)).astype(np.uint8)
        view = cv2.warpAffine(sharp, M, (W, H), flags=cv2.INTER_LINEAR)
        if foc > 0.01:
            vblur = cv2.warpAffine(blur, M, (W, H), flags=cv2.INTER_LINEAR)
            cur = min(boxed, key=lambda b_: 0 if b_[0] - 0.6 <= tb <= b_[1] + 0.6 else min(abs(b_[0] - tb), abs(b_[1] - tb)))[2]
            bx, by, bw_, bh_ = cur
            pad = 12 / k * 2
            fx0, fy0 = k * (bx - pad) + M[0, 2], k * (by - pad) + M[1, 2]
            fx1, fy1 = k * (bx + bw_ + pad) + M[0, 2], k * (by + bh_ + pad) + M[1, 2]
            lift = 1.0                                       # 키우지 않는다 — 키우면 선명한 상자 속 내용이 흐린 주변과 어긋났다(2026-11-09). 그림자 · 테두리로만 띄움
            fcx, fcy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
            L = np.float32([[lift, 0, fcx * (1 - lift)], [0, lift, fcy * (1 - lift)]])
            M2 = np.vstack([L, [0, 0, 1]]) @ np.vstack([M, [0, 0, 1]])
            lifted = cv2.warpAffine(sharp, M2[:2], (W, H), flags=cv2.INTER_LINEAR)
            gx0, gy0 = fcx + (fx0 - fcx) * lift, fcy + (fy0 - fcy) * lift
            gx1, gy1 = fcx + (fx1 - fcx) * lift, fcy + (fy1 - fcy) * lift
            frect = (gx0, gy0, gx1, gy1)
            fm = rounded_mask(W, H, gx0, gy0, gx1, gy1, 16).astype(np.float32) / 255.0
            base_v = view * (1 - 0.2 * foc) if demo else view * (1 - foc) + vblur * foc      # 데모는 흐리지 않고 살짝만 어둡게
            fsh = soft_shadow(W, H, gx0, gy0, gx1, gy1, 16, 18, 26) * foc
            base_v = base_v * (1 - fsh[..., None] * 0.7)
            ring = (rounded_mask(W, H, gx0 - 1.5, gy0 - 1.5, gx1 + 1.5, gy1 + 1.5, 17).astype(np.float32) / 255.0 - fm).clip(0, 1) * 0.35 * foc
            mix = base_v * (1 - fm[..., None]) + lifted * fm[..., None]
            view = (mix * (1 - ring[..., None]) + 255 * ring[..., None]).astype(np.uint8)
        win = rounded_mask(W, H, x0, y0, x1, y1, rad).astype(np.float32) / 255.0
        img = (img * (1 - win[..., None]) + view * win[..., None]).astype(np.uint8)
        # 창 테두리: 가는 밝은 선(어두운 바탕에서 창이 떠 보이게)
        edge = (win - rounded_mask(W, H, x0 + 1.2, y0 + 1.2, x1 - 1.2, y1 - 1.2, rad - 1.2).astype(np.float32) / 255.0).clip(0, 1) * 0.18
        img = (img * (1 - edge[..., None]) + 255 * edge[..., None]).astype(np.uint8)
        # 커서
        # 커서는 누르기 · 입력 앞뒤에만(짚기만 하는 장면에 구석에 멈춰 있으면 어색했다)
        near = [ti for ti, _ in cur_pts if tb - 1.6 <= ti <= tb + 1.3]
        if cur_pts and intro <= t < intro + body and near:
            prev_p, nxt = (sw * 0.6, sh * 0.7), None
            for ti, pnt in cur_pts:
                if ti <= tb:
                    prev_p = pnt
                else:
                    nxt = (ti, pnt); break
            p_ = prev_p
            if nxt and nxt[0] - tb < 0.75:
                u = ease(1 - (nxt[0] - tb) / 0.75)
                ctrl = ((prev_p[0] + nxt[1][0]) / 2 + sw * 0.04, min(prev_p[1], nxt[1][1]) - sh * 0.08)
                p_ = tuple((1 - u) ** 2 * a0 + 2 * (1 - u) * u * c0 + u ** 2 * b0 for a0, c0, b0 in zip(prev_p, ctrl, nxt[1]))
            px, py = k * p_[0] + M[0, 2], k * p_[1] + M[1, 2]
            press = max([max(0.0, 1 - abs(tb - tc) / 0.12) for tc in clicks] + [0.0])
            for tc in clicks:                                  # 누른 곳에서 퍼지는 물결
                dt = tb - tc
                if 0 <= dt < 0.5:
                    r = int(8 + 46 * ease(dt / 0.5))
                    ov = img.copy(); cv2.circle(ov, (int(px), int(py)), r, (255, 255, 255), -1, lineType=cv2.LINE_AA)
                    img = cv2.addWeighted(ov, 0.28 * (1 - dt / 0.5), img, 1 - 0.28 * (1 - dt / 0.5), 0)
            cursor(img, px, py, max(22, 24 * min(z, 1.5)) * (W / 1920), press)
        # 빨리 감기 표시(데모): 녹화 시간이 출력보다 빨리 흐르는 동안 오른쪽 위 작은 알약
        if demo:
            ds = src_time(pts, min(body, tb + 0.05)) - src_time(pts, max(0.0, tb - 0.05))
            spd = ds / 0.1 if tb > 0.05 else 1.0
            if spd > 1.8:
                img = badge(img, f"▶▶ ×{int(round(spd))}", W)
        # 글자
        if t < intro:
            img = (img * (1 - 0.55 * min(1.0, (intro - t) / 0.3))).astype(np.uint8)
            img = kinetic(img, plan["title"], t - 0.2, intro - 0.2, int(W / 11 if W >= H else W / 7), H * 0.38, plan.get("subtitle", ""), glass=False, rate=0.07)
        elif t >= intro + body and plan.get("end"):
            te = t - intro - body
            img = (img * (1 - min(1.0, te / 0.4) * 0.8)).astype(np.uint8)          # 끝 화면: 뒤 화면을 충분히 눌러 제목만 남게
            img = kinetic(img, plan["end"].get("title", ""), te - 0.15, 0, int(W / 11 if W >= H else W / 7), H * 0.38, plan["end"].get("sub", ""), glass=False, rate=0.07)
        else:
            for a_, b_, c_ in caps:
                if a_ <= tb <= b_:
                    up = bool(frect) and foc > 0.3 and frect[3] > H * 0.8      # 짚는 곳이 글자 띠(아래)까지 내려오면 글자는 위로
                    img = kinetic(img, c_, tb - a_, b_ - a_, csize, H * (0.07 if up else 0.84))
                    break
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()
    # 소리: 음악 + 아주 작은 UI 소리(클릭 · 화면 넘김) — 음악 밑에 깔릴 만큼만
    mp, mstart = None, 0.0
    if music == "auto":
        from craft import music_pick as MP
        sb = {"id": "showcase", "format": "ad", "scenes": [{"sec": total, "narration": ""}], "topic": plan.get("topic", "")}
        try:
            m = MP.pick(sb, {}, plan.get("music_mood", "minimal tech product launch"), plan.get("bpm", 110))
            if m.get("use"):
                mp, mstart = ROOT / m["src"], m.get("start", 0)
                print(f"[쇼케이스] 음악: {m['title']} — {m.get('by')} · {m.get('license')}")
        except Exception as e:  # noqa: BLE001
            print(f"[쇼케이스] 음악 고르기 실패: {e}", file=sys.stderr)
    elif music and music != "none":
        mp = Path(music)
    sfx_dir = ROOT / "engine" / "assets" / "sfx"
    ui = [(intro + tc, "tick") for tc in clicks] + [(intro + tc - 0.05, "swoosh") for tc, _ in cut_list]
    ui = [(a, sfx_dir / f"{n}.wav") for a, n in ui if (sfx_dir / f"{n}.wav").exists()] if plan.get("ui_sounds", True) else []
    ins, filt, labels = ["-i", str(silent)], [], []
    n_in = 1
    if mp and mp.exists():
        ins += ["-ss", f"{mstart:.2f}", "-i", str(mp)]
        filt.append(f"[{n_in}:a]afade=t=in:d=0.6,afade=t=out:st={max(0, total - 2.0):.2f}:d=2.0,loudnorm=I=-15:TP=-2,aformat=channel_layouts=stereo[m]")
        labels.append("[m]"); n_in += 1
    for a, f in ui:
        ins += ["-i", str(f)]
        filt.append(f"[{n_in}:a]volume={'-20dB' if 'tick' in f.name else '-24dB'},adelay={int(a * 1000)}|{int(a * 1000)},aformat=channel_layouts=stereo[u{n_in}]")
        labels.append(f"[u{n_in}]"); n_in += 1
    if labels:
        filt.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest[a]" if len(labels) > 1 else f"{labels[0]}anull[a]")
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-t", f"{total:.2f}", str(dst)], check=True)
        silent.unlink()
    else:
        silent.replace(dst)
    print(f"[쇼케이스] {total:.1f}초 · {fps}fps ({aspect}) → {dst.relative_to(ROOT) if dst.is_relative_to(ROOT) else dst}")
    if demo:                                     # 데모는 GIF 도 함께(발표 자료 · README) — mp4 는 소리 없이(페이지 자동 재생용)
        gif = to_gif(dst, dst.with_suffix(".gif"), int(plan.get("gif_width", 1280)), int(plan.get("gif_fps", 20)))
        print(f"[쇼케이스] GIF {gif.stat().st_size / 1e6:.1f}MB → {gif.relative_to(ROOT) if gif.is_relative_to(ROOT) else gif}")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["record", "render", "make"])
    ap.add_argument("a"); ap.add_argument("b", nargs="?")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1"]); ap.add_argument("--music", default="auto"); ap.add_argument("--out"); ap.add_argument("--fps", type=int, default=60)
    a = ap.parse_args()
    if a.cmd in ("record", "make"):
        plan = json.loads(Path(a.a).read_text("utf-8"))
        out = Path(a.b or ROOT / "data" / "public" / "showcase" / Path(a.a).stem)
        record(plan, out)
    else:
        out = Path(a.a)
    if a.cmd in ("render", "make"):
        render(out, a.aspect, a.music, Path(a.out) if a.out else None, a.fps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
