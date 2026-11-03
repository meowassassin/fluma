/* ShortsForge × HyperFrames 공용 라이브러리.
 * 원칙: 화면은 시간 t(초)만으로 결정된다 (HyperFrames 는 GSAP 타임라인을 seek 해서 프레임을 찍는다).
 * 무작위·Date·네트워크 금지. 노이즈는 시드 고정.
 * window.SF = { sb, tokens, scenes:[{index,start,end,sec}], captions:[{text,startMs,endMs,scene}], duration, fps } 를 어댑터가 넣는다.
 */
(function () {
  const SF = window.SF;

  // ---------- 수학 ----------
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, p) => a + (b - a) * p;
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const ease = {
    linear: (p) => p,
    outCubic: (p) => 1 - Math.pow(1 - p, 3),
    outQuart: (p) => 1 - Math.pow(1 - p, 4),
    inOutCubic: (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2),
    outBack: (p, s = 1.7) => 1 + (s + 1) * Math.pow(p - 1, 3) + s * Math.pow(p - 1, 2),
    // 감쇠 스프링 근사 (Remotion spring 대용): 0→1, 살짝 넘쳤다 돌아옴
    spring: (p, damping = 12) => (p <= 0 ? 0 : p >= 1 ? 1 : 1 - Math.exp(-damping * p * 0.5) * Math.cos(p * Math.PI * 2.2 * (12 / damping))),
  };

  // ---------- 시드 노이즈 (3D simplex, 결정적) ----------
  function hashSeed(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function mulberry(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  const grad3 = [[1,1,0],[-1,1,0],[1,-1,0],[-1,-1,0],[1,0,1],[-1,0,1],[1,0,-1],[-1,0,-1],[0,1,1],[0,-1,1],[0,1,-1],[0,-1,-1]];
  const permCache = {};
  function perm(seed) {
    if (permCache[seed]) return permCache[seed];
    const r = mulberry(hashSeed(seed)); const p = Array.from({ length: 256 }, (_, i) => i);
    for (let i = 255; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [p[i], p[j]] = [p[j], p[i]]; }
    return (permCache[seed] = p.concat(p));
  }
  function noise3D(seed, x, y, z) {
    const P = perm(seed); const F3 = 1 / 3, G3 = 1 / 6;
    const s = (x + y + z) * F3; const i = Math.floor(x + s), j = Math.floor(y + s), k = Math.floor(z + s);
    const t = (i + j + k) * G3; const x0 = x - i + t, y0 = y - j + t, z0 = z - k + t;
    let i1, j1, k1, i2, j2, k2;
    if (x0 >= y0) { if (y0 >= z0) { i1=1;j1=0;k1=0;i2=1;j2=1;k2=0; } else if (x0 >= z0) { i1=1;j1=0;k1=0;i2=1;j2=0;k2=1; } else { i1=0;j1=0;k1=1;i2=1;j2=0;k2=1; } }
    else { if (y0 < z0) { i1=0;j1=0;k1=1;i2=0;j2=1;k2=1; } else if (x0 < z0) { i1=0;j1=1;k1=0;i2=0;j2=1;k2=1; } else { i1=0;j1=1;k1=0;i2=1;j2=1;k2=0; } }
    const pts = [[x0, y0, z0, 0, 0, 0], [x0 - i1 + G3, y0 - j1 + G3, z0 - k1 + G3, i1, j1, k1], [x0 - i2 + 2 * G3, y0 - j2 + 2 * G3, z0 - k2 + 2 * G3, i2, j2, k2], [x0 - 1 + 0.5, y0 - 1 + 0.5, z0 - 1 + 0.5, 1, 1, 1]];
    let n = 0; const ii = i & 255, jj = j & 255, kk = k & 255;
    for (const [px, py, pz, a, b, c] of pts) {
      let tt = 0.6 - px * px - py * py - pz * pz;
      if (tt > 0) { const g = grad3[P[ii + a + P[jj + b + P[kk + c]]] % 12]; tt *= tt; n += tt * tt * (g[0] * px + g[1] * py + g[2] * pz); }
    }
    return 32 * n;   // 대략 -1..1
  }

  // ---------- 색 ----------
  const hex2rgb = (h) => { const m = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16)); };
  const rgb2hex = (r, g, b) => "#" + [r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, p) => { const A = hex2rgb(a), B = hex2rgb(b); return rgb2hex(lerp(A[0], B[0], p), lerp(A[1], B[1], p), lerp(A[2], B[2], p)); };
  function rotateHue(hex, deg) {
    let [r, g, b] = hex2rgb(hex).map((v) => v / 255);
    const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
    let h = 0; const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
    if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h = (h * 60 + deg + 720) % 360;
    const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
    const [a, bb, cc] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return rgb2hex((a + m) * 255, (bb + m) * 255, (cc + m) * 255);
  }

  // ---------- DOM ----------
  const el = (tag, cls, parent, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; if (parent) parent.appendChild(e); return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /** 글자 크기를 폭에 맞춘다 (한 번 측정해 캐시). maxPx 이하에서 줄이 넘치지 않는 최대 크기. */
  function fit(node, maxWidth, maxPx, minPx = 24) {
    if (node.__fit && node.__fitW === maxWidth) return node.__fit;
    node.style.whiteSpace = "nowrap"; node.style.fontSize = maxPx + "px";
    const w = node.scrollWidth || 1;
    const size = Math.max(minPx, Math.min(maxPx, Math.floor((maxPx * maxWidth) / w)));
    node.style.fontSize = size + "px";
    if (document.fonts && document.fonts.status === "loaded") { node.__fit = size; node.__fitW = maxWidth; }
    return size;
  }

  // ---------- 단어 자막 페이지 (createTikTokStyleCaptions 와 같은 규칙) ----------
  function captionPages(captions, combineMs) {
    const out = []; let cur = [];
    for (const c of captions) {
      if (cur.length && (c.scene !== cur[0].scene || c.startMs - cur[0].startMs >= combineMs)) { out.push(cur); cur = []; }
      cur.push(c);
    }
    if (cur.length) out.push(cur);
    return out.map((p, i) => {
      const next = out[i + 1];
      const end = next ? Math.min(next[0].startMs, p[p.length - 1].endMs + 400) : p[p.length - 1].endMs + 400;
      return { tokens: p, start: p[0].startMs / 1000, end: end / 1000 };
    });
  }

  /** 템플릿 등록: draw(t) 를 GSAP 타임라인 하나에 묶는다. HyperFrames 는 이 타임라인을 seek 한다. */
  function mount(draw) {
    window.__timelines = window.__timelines || {};
    const tl = gsap.timeline({ paused: true });
    const clock = { t: 0 };
    tl.to(clock, { t: SF.duration, duration: SF.duration, ease: "none", onUpdate: () => draw(clock.t) }, 0);
    window.__timelines["main"] = tl;
    tl.seek(0); draw(0);
    // 미리보기 하네스(웹)가 직접 시간을 넘길 수 있게
    window.__sfSeek = (t) => { tl.seek(t); draw(clamp(t, 0, SF.duration)); };
    if (document.fonts) document.fonts.ready.then(() => draw(clock.t));
    return tl;
  }

  window.SFLib = { clamp, lerp, prog, ease, noise3D, mix, rotateHue, el, esc, fit, captionPages, mount };
})();
