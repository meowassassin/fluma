#!/usr/bin/env python3
"""실제 화면 기반 UI 애니메이션 — 녹화가 아니라, 실제 앱 화면(배치 · 색 · 구성 요소)을 재료로 움직임을 설계해 프레임마다 그린다.
제품 페이지 데모(Linear · Cursor 류)처럼: 글자는 흐려 형태만, 보여 줄 것(입력하는 말 · 결과 · 장면 카드)만 선명하게,
요소가 하나씩 등장하고 카메라가 앱 안에서 다가간다(브라우저가 확대된 채 다시 그려 글자가 깨지지 않음).

  python3 engine/capture/uianim.py <계획.json> <출력 폴더> [--fps 30] [--gif]

시간은 '장면(shot)'마다. 프레임마다 FX.seek(t) 로 그 시각의 모습을 정확히 맞춘 뒤 찍는다 — 앱이 느려도 결과는 매끈하다.
계획(JSON)
  { "base": "http://127.0.0.1:4311", "viewport": [1600, 900], "scale": 1.2, "lang": "ko", "fps": 30,
    "shots": [
      { "url": "/", "dur": 4.5,
        "setup": [ {"hide": ".dock-log > *"}, {"user": "보낼 말", "id": "u1", "into": ".dock-log"},
                   {"ai": ["문단", "문단"], "steps": 3, "media": ".dock-log > :nth-child(4) .md-media.multi", "id": "a1", "into": ".dock-log"} ],
        "keep": ["textarea", "#u1"],                   # 흐리지 않을 것(선택자)
        "acts": [ {"at": 0.4, "dur": 2.0, "do": "type", "sel": "textarea", "text": "…"},
                  {"at": 2.6, "dur": 0.4, "do": "pop", "sel": "#u1"},
                  {"at": 3.0, "dur": 1.6, "do": "stream", "sel": "#a1"},
                  {"at": 4.0, "dur": 0.8, "do": "cursor", "sel": "button.btn-primary", "click": true},
                  {"at": 5.0, "dur": 0.6, "do": "pulse", "sel": ".sb-scenes > li:nth-child(4)"} ],
        "camera": [ {"at": 0, "sel": "textarea", "zoom": 1.35}, {"at": 3.2, "dur": 1.0, "sel": ".dock-log", "zoom": 1.1} ],
        "focus":  [ {"at": 5.0, "dur": 0.6, "sel": ".sb-scenes > li:nth-child(4)", "amount": 1}, {"at": 7.0, "dur": 0.6, "amount": 0} ] } ] }
  물리 행동: {"at": 1.0, "do": "physics", "physics": "data/compositions/<id>/src/x.mjcf.xml", "bind": {"body 이름": "선택자"}, "sec": 3}
  — 페이지의 요소(알림 카드 · 버튼 · 글자)를 제자리에서 떨어뜨리고 부딪히게 한다(engine/craft/physics.py).
  등장 행동(pop · stream · fade)이 붙은 요소는 그 시각 전까지 보이지 않는다. 장면 사이는 0.45초 흐림 섞기.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

RUNTIME = r"""
(() => {
const ease = (x) => { x = Math.min(1, Math.max(0, x)); return x < .5 ? 4*x*x*x : 1 - Math.pow(-2*x + 2, 3) / 2; };
const eout = (x) => { x = Math.min(1, Math.max(0, x)); return 1 - Math.pow(1 - x, 3); };
const FX = window.FX = { acts: [], cam: [], foc: [], rects: {}, root: null, overlay: null, cursor: null, ring: null, typed: new Map() };
FX.q = (s) => document.querySelector(s);
FX.css = (txt) => { const st = document.createElement('style'); st.textContent = txt; document.head.appendChild(st); };
FX.setup = (spec) => {
  // 앱 자체 전환 · 애니메이션은 멈춘다(프레임은 우리가 정한 시각으로만 움직인다)
  FX.css(`*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; }
    .fx-abs :is(p, li, dd, dt, td, th, figcaption, h1, h2, h3, h4, .step-row, .ellipsis, .m-meta, .chip, small, label, code, pre, .sb-prod, a, span):not(.fx-keep):not(.fx-keep *) { filter: blur(5px); opacity: .78; }
    .fx-keep, .fx-keep * { filter: none !important; opacity: 1 !important; }
    textarea::placeholder { color: transparent !important; }`);
  if (spec.abstract !== false) document.body.classList.add('fx-abs');   // 디자인 화면(새로 그린 UI)은 흐리지 않는다
  for (const s of spec.setup || []) {
    if (s.hide) document.querySelectorAll(s.hide).forEach((e) => e.style.display = 'none');
    if (s.css) FX.css(s.css);
    if (s.user) {
      const tpl = document.querySelector('.m-user:not(.steer)'); const n = tpl.cloneNode(true);
      n.id = s.id; n.style.display = ''; n.querySelector('.m-bubble').textContent = s.user;
      FX.q(s.into).appendChild(n);
    }
    if (s.ai) {
      const tpl = document.querySelector('.m-ai:not(.live)'); const n = document.createElement('div'); n.className = tpl.className; n.id = s.id;
      if (s.steps) { const st = tpl.querySelector('.steps'); if (st) { const c = st.cloneNode(true); const rows = [...c.querySelectorAll('.step')];
          rows.slice(s.steps).forEach((r) => r.remove()); c.querySelector('.steps-more')?.remove(); n.appendChild(c); } }
      const md = document.createElement('div'); md.className = 'md';
      for (const t of s.ai) { const p = document.createElement('p'); p.textContent = t; md.appendChild(p); const g = document.createElement('div'); g.className = 'md-gap'; md.appendChild(g); }
      if (s.media) { const m = document.querySelector(s.media); if (m) md.appendChild(m.cloneNode(true)); }
      n.appendChild(md); FX.q(s.into).appendChild(n);
    }
    if (s.scroll) { const e = FX.q(s.scroll); if (e) e.scrollTop = typeof s.to === 'number' ? s.to : s.to === 'top' ? 0 : e.scrollHeight; }
  }
  for (const k of spec.keep || []) document.querySelectorAll(k).forEach((e) => e.classList.add('fx-keep'));
  FX.acts = spec.acts || []; FX.cam = spec.camera || []; FX.foc = spec.focus || [];
  FX.root = document.querySelector(spec.root || '.app') || document.body;
  FX.root.style.transformOrigin = '0 0';
  // 강조 구멍: 화면 전체를 흐리고 어둡게 덮되 대상 자리만 뚫는다
  FX.overlay = document.createElement('div');
  FX.overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483600;pointer-events:none;backdrop-filter:blur(7px) brightness(.5);-webkit-backdrop-filter:blur(7px) brightness(.5);opacity:0';
  document.body.appendChild(FX.overlay);
  FX.ring = document.createElement('div');
  FX.ring.style.cssText = 'position:fixed;z-index:2147483601;pointer-events:none;border-radius:14px;box-shadow:0 0 0 1.5px rgba(255,255,255,.55),0 18px 50px rgba(0,0,0,.45);opacity:0';
  document.body.appendChild(FX.ring);
  FX.cursor = document.createElement('div');
  FX.cursor.innerHTML = '<svg width="26" height="34" viewBox="0 0 26 34"><path d="M2 2 L2 27 L8.5 21 L13 31.5 L17.5 29.5 L13 19.5 L22 19.5 Z" fill="#fff" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>';
  FX.cursor.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483602;pointer-events:none;opacity:0;filter:drop-shadow(0 3px 6px rgba(0,0,0,.45));transform-origin:2px 2px';
  document.body.appendChild(FX.cursor);
  FX.ripple = document.createElement('div');
  FX.ripple.style.cssText = 'position:fixed;z-index:2147483601;pointer-events:none;border-radius:50%;border:2px solid rgba(255,255,255,.8);opacity:0';
  document.body.appendChild(FX.ripple);
  // 자리 재기(변환 없음 · 모두 보인 상태) — 등장 전에는 visibility/opacity 로만 숨겨 자리가 변하지 않는다
  const sels = new Set([...FX.acts.map((a) => a.sel), ...FX.cam.map((c) => c.sel), ...FX.foc.map((f) => f.sel)].filter(Boolean));
  for (const s of sels) { const e = FX.q(s); if (e) { const r = e.getBoundingClientRect(); FX.rects[s] = [r.left, r.top, r.width, r.height]; } }
  for (const a of FX.acts) if (a.do === 'type') { const e = FX.q(a.sel); if (e) FX.typed.set(a, e); }
  FX.scroll0 = new Map();
  for (const a of FX.acts) if (a.do === 'scroll') { const e = FX.q(a.sel); if (e && !FX.scroll0.has(e)) FX.scroll0.set(e, e.scrollTop); }
  return Object.keys(FX.rects).length;
};
const lerp = (a, b, u) => a + (b - a) * u;
function camAt(t) {
  const W = innerWidth, H = innerHeight;
  const key = (c) => { const z = c.zoom || 1; if (!c.sel) return [W / 2, H / 2, z]; const r = FX.rects[c.sel] || [0, 0, W, H];
    let cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2; const hw = W / (2 * z), hh = H / (2 * z);
    cx = Math.min(Math.max(cx, hw), W - hw); cy = Math.min(Math.max(cy, hh), H - hh); return [cx, cy, z]; };
  const C = FX.cam; if (!C.length) return [W / 2, H / 2, 1];
  let cur = key(C[0]);
  for (let i = 1; i < C.length; i++) { const c = C[i]; if (t < c.at) break; const nx = key(c); const u = ease((t - c.at) / (c.dur || .9)); const prev = cur;
    cur = [lerp(prev[0], nx[0], u), lerp(prev[1], nx[1], u), Math.exp(lerp(Math.log(prev[2]), Math.log(nx[2]), u))]; }
  return cur;
}
function focAt(t) {
  let amt = 0, sel = null, prevSel = null;
  for (const f of FX.foc) { if (t < f.at) break; const u = eout((t - f.at) / (f.dur || .5)); amt = lerp(amt, f.amount ?? 1, u); if (f.sel) { prevSel = sel; sel = f.sel; } }
  return [amt, sel];
}
FX.seek = (t) => {
  const W = innerWidth, H = innerHeight;
  // 등장 · 글자
  for (const a of FX.acts) {
    const e = a.sel ? FX.q(a.sel) : null; if (!e && a.do !== 'cursor' && a.do !== 'physics') continue;
    const u = (t - a.at) / (a.dur || .4);
    if (a.do === 'physics') { /* 물리(MuJoCo) — 요소마다 처음 자리에서 계산된 만큼 옮기고 돌린다. a.tracks: {선택자: [[dx, dy, 도], …]} */
      const fr = Math.max(0, Math.round((t - a.at) * (a.fps || 30)));
      for (const [sel, tr] of Object.entries(a.tracks || {})) { const el = FX.q(sel); if (!el || !tr.length) continue; const v = tr[Math.min(tr.length - 1, fr)];
        el.style.transform = `translate(${v[0]}px, ${v[1]}px) rotate(${v[2]}deg)`; el.style.willChange = 'transform'; }
      continue; }
    if (a.do === 'pop') { const k = eout(u); e.style.opacity = t < a.at ? '0' : String(k); e.style.transform = `translateY(${(1 - k) * 16}px) scale(${.97 + .03 * k})`; }
    else if (a.do === 'fade') { e.style.opacity = t < a.at ? '0' : String(eout(u)); }
    else if (a.do === 'stream') { const k = Math.min(1, Math.max(0, u)); e.style.opacity = t < a.at ? '0' : '1'; e.style.clipPath = `inset(0 0 ${(1 - eout(k)) * 100}% 0)`; }
    else if (a.do === 'type') { const n = Math.max(0, Math.min(a.text.length, Math.floor(a.text.length * Math.min(1, Math.max(0, u))))); const v = a.text.slice(0, n);
      const vv = a.clear_at != null && t >= a.clear_at ? '' : v;           // 보낸 뒤 입력창이 비워짐
      if ('value' in e) { e.value = vv; } else e.textContent = vv; }
    else if (a.do === 'grow') { const k = eout(u); e.style.transformOrigin = 'left center'; e.style.opacity = t < a.at ? '0' : String(Math.min(1, k * 3)); e.style.transform = `scaleX(${t < a.at ? 0 : k})`; }
    else if (a.do === 'swap') { const on = t >= a.at; if (e.dataset.fxA == null) { e.dataset.fxA = e.textContent; } e.textContent = on ? a.text : e.dataset.fxA; }
    else if (a.do === 'cls') { e.classList.toggle(a.cls || 'on', t >= a.at); }
    else if (a.do === 'wave') { const on = t >= a.at && t <= a.at + (a.dur || 2); [...e.children].forEach((b, i) => {
        const h = on ? .25 + .75 * Math.abs(Math.sin(t * 7.3 + i * .9) * Math.cos(t * 2.1 + i * .37)) : .22; b.style.transform = `scaleY(${h.toFixed(3)})`; }); }
    else if (a.do === 'flip') { const kids = [...e.children], n = kids.length, iv = a.every || .5; const x = t < a.at ? 0 : (t - a.at) / iv;
      const k = Math.floor(x) % n, f = Math.min(1, (x - Math.floor(x)) / .25);       // 장면이 넘어갈 때 0.25 만큼 겹쳐 넘김
      kids.forEach((c, i) => { c.style.opacity = i === k ? '1' : (i === (k - 1 + n) % n && t >= a.at && x >= 1 ? String(1 - f) : '0'); }); }
    else if (a.do === 'count') { const k = ease(u); const v = t < a.at ? a.from : a.from + (a.to - a.from) * Math.min(1, Math.max(0, k));
      e.textContent = (a.prefix || '') + (a.fixed ? v.toFixed(a.fixed) : Math.round(v)) + (a.suffix || ''); }
    else if (a.do === 'pulse') { const k = t < a.at ? 0 : Math.sin(Math.min(1, Math.max(0, u)) * Math.PI); e.style.boxShadow = k ? `0 0 0 ${2 + 2 * k}px rgba(124,108,255,${.85 * k})` : ''; e.style.borderRadius = '12px'; }
  }
  // 스크롤(시각으로만 정해진다 — 새 메시지가 아래에 생기면 목록이 따라 내려간다)
  for (const [e, y0] of FX.scroll0) e.scrollTop = y0;
  for (const a of FX.acts) { if (a.do !== 'scroll' || t < a.at) continue; const e = FX.q(a.sel); if (!e) continue;
    const px = (v) => v === 'bottom' ? e.scrollHeight - e.clientHeight : v === 'top' ? 0 : v === 'here' || v == null ? e.scrollTop
      : (typeof v === 'string' && v[0] === '#') ? Math.max(0, Math.min(e.scrollHeight - e.clientHeight, (FX.q(v)?.offsetTop ?? 0) - (a.pad ?? 28))) : Number(v);
    const from = px(a.from), to = px(a.to); e.scrollTop = from + (to - from) * ease((t - a.at) / (a.dur || .6)); }
  // 카메라(앱 안에서 확대 — 다시 그려서 선명)
  const [cx, cy, z] = camAt(t);
  FX.root.style.transform = `translate(${W / 2 - cx * z}px, ${H / 2 - cy * z}px) scale(${z})`;
  const toScreen = (r) => [W / 2 + (r[0] - cx) * z, H / 2 + (r[1] - cy) * z, r[2] * z, r[3] * z];
  // 강조 구멍
  const [amt, fs] = focAt(t);
  FX.overlay.style.opacity = String(amt); FX.ring.style.opacity = String(amt);
  if (fs && FX.rects[fs]) { const [x, y, w, h] = toScreen(FX.rects[fs]); const p = 10, r = 14;
    const X = x - p, Y = y - p, Wd = w + 2 * p, Hd = h + 2 * p;
    const hole = `M${X + r},${Y} H${X + Wd - r} A${r},${r} 0 0 1 ${X + Wd},${Y + r} V${Y + Hd - r} A${r},${r} 0 0 1 ${X + Wd - r},${Y + Hd} H${X + r} A${r},${r} 0 0 1 ${X},${Y + Hd - r} V${Y + r} A${r},${r} 0 0 1 ${X + r},${Y} Z`;
    FX.overlay.style.clipPath = `path(evenodd, "M0,0 H${W} V${H} H0 Z ${hole}")`;
    Object.assign(FX.ring.style, { left: X + 'px', top: Y + 'px', width: Wd + 'px', height: Hd + 'px' }); }
  // 커서: 대상까지 곡선으로, 누르면 작아졌다 물결
  let cur = null, press = 0, rip = -1;
  for (const a of FX.acts) { if (a.do !== 'cursor') continue; const r = FX.rects[a.sel]; if (!r) continue;
    const to = [r[0] + r[2] * (a.x ?? .5), r[1] + r[3] * (a.y ?? .55)]; const from = a.from ? [W * a.from[0], H * a.from[1]] : [to[0] + 160, to[1] + 120];
    if (t < a.at - .05) { if (!cur) cur = null; continue; }
    const u = eout((t - a.at) / (a.dur || .7)); const c = [(from[0] + to[0]) / 2 + 40, Math.min(from[1], to[1]) - 50];
    cur = [ (1-u)*(1-u)*from[0] + 2*(1-u)*u*c[0] + u*u*to[0], (1-u)*(1-u)*from[1] + 2*(1-u)*u*c[1] + u*u*to[1] ];
    const tc = a.at + (a.dur || .7); if (a.click && t >= tc) { press = Math.max(0, 1 - Math.abs(t - tc - .06) / .1); rip = t - tc; }
    if (a.hide_after != null && t > a.at + a.hide_after) cur = null; }
  if (cur) { const [sx, sy] = [W / 2 + (cur[0] - cx) * z, H / 2 + (cur[1] - cy) * z]; FX.cursor.style.opacity = '1';
    FX.cursor.style.transform = `translate(${sx}px, ${sy}px) scale(${1 - .14 * press})`;
    if (rip >= 0 && rip < .5) { const k = eout(rip / .5), R = 10 + 36 * k; Object.assign(FX.ripple.style, { left: sx - R + 'px', top: sy - R + 'px', width: 2 * R + 'px', height: 2 * R + 'px', opacity: String(.8 * (1 - k)) }); }
    else FX.ripple.style.opacity = '0'; }
  else { FX.cursor.style.opacity = '0'; FX.ripple.style.opacity = '0'; }
  return true;
};
})();
"""


def physics_tracks(shot: dict, vw: int, vh: int, fps: int) -> dict:
    """행동 {"do": "physics", "at": 초, "physics": "장면(.mjcf.xml | .py)", "bind": {"body": "선택자"}, "args": {…}, "sec": 3,
    "view": {"width": 세상 너비 m, "x": 0.5, "ground": 0.9}} → 요소마다 처음 자리 기준 이동 · 회전(픽셀 · 도). 페이지 배치가 출발점"""
    acts = []
    for a in shot.get("acts") or []:
        if a.get("do") == "physics" and a.get("physics") and "tracks" not in a:
            from craft import physics as _phys
            res = _phys.simulate(ROOT / a["physics"], float(a.get("sec", 3)), fps, {k: v for k, v in (a.get("args") or {}).items() if not isinstance(v, (dict, list))})
            v = a.get("view") or {}
            pr = _phys.project2d(res, vw, vh, float(v.get("width", 3.6)), float(v.get("x", 0.5)), float(v.get("ground", 0.9)))
            tracks = {}
            for body, sel in (a.get("bind") or {}).items():
                rows = pr["bodies"].get(body)
                if rows:
                    x0, y0, r0 = rows[0]
                    tracks[sel] = [[round(x - x0, 1), round(y - y0, 1), round(r - r0, 2)] for x, y, r in rows]
            a = {**a, "tracks": tracks, "fps": fps}
        acts.append(a)
    return {**shot, "acts": acts}


def render(plan: dict, out: Path, fps: int, gif: bool) -> Path:
    import cv2
    import numpy as np
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    vw, vh = plan.get("viewport", [1600, 900])
    sc = float(plan.get("scale", 1.2))
    W, H = int(vw * sc), int(vh * sc)
    dst = out / "demo.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    lang = plan.get("lang")
    shots_frames: list[list[np.ndarray]] = []
    DIS = int(0.45 * fps)
    prev_tail = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[f"--force-device-scale-factor={sc:g}"])
        ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=sc, color_scheme=plan.get("theme", "dark"),
                                  locale={"ko": "ko-KR", "en": "en-US"}.get(lang or "", "ko-KR"))
        if lang:
            ctx.add_init_script(f"try {{ localStorage.setItem('fluma.lang', JSON.stringify({{state: {{lang: '{lang}'}}, version: 0}})); }} catch (e) {{}}")
        page = ctx.new_page()
        for si, shot in enumerate(plan["shots"]):
            page.goto(plan["base"].rstrip("/") + shot["url"], wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(int(shot.get("settle_ms", 1200)))
            page.evaluate(RUNTIME)
            shot = physics_tracks(shot, vw, vh, fps)
            n = page.evaluate("(s) => FX.setup(s)", shot)
            page.wait_for_timeout(300)
            frames = int(float(shot["dur"]) * fps)
            print(f"[UI 애니메이션] 장면 {si + 1}: {shot['url']} · {shot['dur']}초 · 잰 요소 {n}개", flush=True)
            for fi in range(frames):
                page.evaluate("(t) => FX.seek(t)", fi / fps)
                buf = page.screenshot(type="jpeg", quality=93)
                img = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
                if img.shape[1] != W or img.shape[0] != H:
                    img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
                if prev_tail is not None and fi < DIS:          # 앞 장면 끝 → 이 장면: 흐림 섞기
                    k = (fi + 1) / DIS
                    kk = k * k * (3 - 2 * k)
                    mix = cv2.addWeighted(prev_tail, 1 - kk, img, kk, 0)
                    b = np.sin(np.pi * kk) * 9
                    if b > 0.5:
                        sm = cv2.resize(mix, (W // 3, H // 3), interpolation=cv2.INTER_AREA)
                        mix = cv2.resize(cv2.GaussianBlur(sm, (0, 0), b / 3), (W, H))
                    img = mix
                ff.stdin.write(img.tobytes())
                last = img
            prev_tail = last
        browser.close()
    ff.stdin.close(); ff.wait()
    print(f"[UI 애니메이션] → {dst.relative_to(ROOT) if dst.is_relative_to(ROOT) else dst}")
    if gif:
        from showcase import to_gif, to_web
        g = to_gif(dst, out / "demo.gif", int(plan.get("gif_width", 800)), int(plan.get("gif_fps", 12)), int(plan.get("gif_colors", 128)))
        w = to_web(dst, out / "demo.web.mp4")
        print(f"[UI 애니메이션] GIF {g.stat().st_size / 1e6:.1f}MB · 페이지용 mp4 {w.stat().st_size / 1e6:.1f}MB")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("out"); ap.add_argument("--fps", type=int, default=30); ap.add_argument("--gif", action="store_true")
    a = ap.parse_args()
    render(json.loads(Path(a.plan).read_text("utf-8")), Path(a.out), a.fps, a.gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
