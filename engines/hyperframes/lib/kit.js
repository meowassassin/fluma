/* Fluma Kit — 영상마다 에이전트가 짜는 컴포지션용 모션 부품 (HyperFrames · 1080×1920).
 * 모든 부품은 시간만으로 화면이 정해진다(결정적). 무작위는 K.rand(seed) 만.
 *
 *   K.compose({ scenes: [ (c) => { ...부품 만들기...; return (lt, p) => {...} } , ... ],
 *               transitions: ["wipe", "zoom", ...], captions: { style: "highlight" | "box" | "top" | "pop" | "none", ... },
 *               camera: (t) => ({ x, y, scale, rot }) })
 *   c = { root, sc, sb, scene, i, T(토큰), W, H }   lt = 장면 안 시간(초), p = 0..1
 * 부품은 { el, update(lt) } 를 돌려주고, 장면 함수의 draw 에서 update 를 부르면 된다. c.auto(...parts) 로 등록하면 자동으로 불린다.
 */
(function () {
  const { clamp, lerp, ease, noise3D, mix, el, esc } = window.SFLib;
  const SF = window.SF;
  const W = 1080, H = 1920;
  const T = SF.tokens.color;

  // ---------- 기본 ----------
  const E = {
    linear: (p) => p, out: ease.outCubic, out4: ease.outQuart, inOut: ease.inOutCubic, back: (p) => ease.outBack(p, 1.6), spring: (p) => ease.spring(p, 10),
    elastic: (p) => (p <= 0 ? 0 : p >= 1 ? 1 : Math.pow(2, -10 * p) * Math.sin((p * 10 - 0.75) * (2 * Math.PI / 3)) + 1),
    in: (p) => p * p * p,
  };
  const win = (lt, at, dur, fn = E.out) => fn(clamp((lt - at) / Math.max(0.001, dur)));
  function rand(seed) { let a = 0; for (const ch of String(seed)) a = (Math.imul(a ^ ch.charCodeAt(0), 2654435761) >>> 0); return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  const css = (e, o) => { for (const k in o) e.style[k] = o[k]; return e; };
  const box = (parent, o = {}) => css(el("div", "k-box", parent), { position: "absolute", left: (o.x ?? 0) + "px", top: (o.y ?? 0) + "px", width: o.w != null ? o.w + "px" : "auto", height: o.h != null ? o.h + "px" : "auto", ...(o.style || {}) });

  // ---------- 배경 ----------
  /** type: solid | gradient | grid | dots | stripes | noise | rays | paper | stars | pixel
   *       | mesh(움직이는 색 그물) | blueprint(청사진) | halftone(망점) | topo(등고선) | split(사선 2분할) | sky(겹친 언덕 · 해)
   *       | waves(물결 띠) | bokeh(흐린 빛망울) | scan(브라운관 주사선) | floor(원근 격자 바닥) | ink(종이 + 먹 번짐) | field(큰 색면 + 거대 도형) */
  function bg(parent, o = {}) {
    const type = o.type || "solid";   // 기본은 단색 — 그라데이션 · 빛번짐 바탕은 type 으로 고를 때만(look_check.py 가 잰다)
    const a = o.a || T.bg, b = o.b || mix(T.bg, T.accent, 0.35), c = o.c || T.accent;
    const e = css(el("div", "k-bg", parent), { position: "absolute", inset: "0", overflow: "hidden", background: a });
    const layer = css(el("div", "", e), { position: "absolute", inset: "-20%" });
    const grain = o.grain !== false ? css(el("div", "", e), { position: "absolute", inset: "0", opacity: String(o.grain ?? 0.06), mixBlendMode: "overlay",
      backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' seed='3'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")" }) : null;
    const sz = o.size || 72;
    const patterns = {
      solid: () => ({ background: a }),
      gradient: () => ({ background: `linear-gradient(160deg, ${a}, ${b})` }),
      grid: () => ({ background: `linear-gradient(${mix(a, c, .18)} 2px, transparent 2px) 0 0/${sz}px ${sz}px, linear-gradient(90deg, ${mix(a, c, .18)} 2px, transparent 2px) 0 0/${sz}px ${sz}px, ${a}` }),
      dots: () => ({ background: `radial-gradient(${mix(a, c, .35)} 3px, transparent 3.5px) 0 0/${sz}px ${sz}px, ${a}` }),
      stripes: () => ({ background: `repeating-linear-gradient(-35deg, ${a} 0 ${sz}px, ${mix(a, c, .12)} ${sz}px ${sz * 2}px)` }),
      rays: () => ({ background: `repeating-conic-gradient(from 0deg at 50% 50%, ${a} 0 10deg, ${mix(a, c, .22)} 10deg 20deg)` }),
      paper: () => ({ background: `radial-gradient(120% 80% at 30% 20%, ${mix(a, "#ffffff", .12)}, ${a})` }),
      pixel: () => ({ background: `linear-gradient(45deg, ${mix(a, c, .1)} 25%, transparent 25%, transparent 75%, ${mix(a, c, .1)} 75%) 0 0/${sz}px ${sz}px, linear-gradient(45deg, ${mix(a, c, .1)} 25%, ${a} 25%, ${a} 75%, ${mix(a, c, .1)} 75%) ${sz / 2}px ${sz / 2}px/${sz}px ${sz}px`, imageRendering: "pixelated" }),
      noise: () => ({ background: a }),
      stars: () => ({ background: a }),
      mesh: () => ({ background: a }),
      blueprint: () => ({ background: `linear-gradient(${mix(a, "#ffffff", .14)} 1px, transparent 1px) 0 0/${sz / 4}px ${sz / 4}px, linear-gradient(90deg, ${mix(a, "#ffffff", .14)} 1px, transparent 1px) 0 0/${sz / 4}px ${sz / 4}px, linear-gradient(${mix(a, "#ffffff", .28)} 2px, transparent 2px) 0 0/${sz}px ${sz}px, linear-gradient(90deg, ${mix(a, "#ffffff", .28)} 2px, transparent 2px) 0 0/${sz}px ${sz}px, ${a}` }),
      halftone: () => ({ background: `radial-gradient(circle at 30% 30%, ${c} 0 22%, transparent 23%) 0 0/${sz / 3}px ${sz / 3}px`, maskImage: "linear-gradient(160deg, #000 0%, transparent 75%)", WebkitMaskImage: "linear-gradient(160deg, #000 0%, transparent 75%)" }),
      topo: () => ({ background: a }),
      split: () => ({ background: `linear-gradient(${o.angle ?? 118}deg, ${a} 0 ${o.at ?? 52}%, ${b} ${o.at ?? 52}% 100%)` }),
      sky: () => ({ background: `linear-gradient(180deg, ${a}, ${mix(a, c, .45)})` }),
      waves: () => ({ background: a }),
      bokeh: () => ({ background: `radial-gradient(120% 90% at 50% 30%, ${mix(a, b, .5)}, ${a})` }),
      scan: () => ({ background: `repeating-linear-gradient(0deg, rgba(0,0,0,.5) 0 3px, transparent 3px 7px), radial-gradient(90% 60% at 50% 45%, ${mix(a, c, .45)}, ${a} 80%)` }),
      floor: () => ({ background: a }),
      ink: () => ({ background: `radial-gradient(120% 80% at 30% 20%, ${mix(a, "#ffffff", .1)}, ${a})` }),
      field: () => ({ background: a }),
    };
    css(layer, patterns[type] ? patterns[type]() : patterns.solid());
    let blobs = [];
    if (type === "noise" || o.blobs) {
      blobs = [0, 1, 2].map((k) => css(el("div", "", e), { position: "absolute", width: "900px", height: "900px", borderRadius: "50%", filter: "blur(120px)", opacity: ".55", background: [b, c, mix(c, "#ffffff", .3)][k] }));
    }
    // 추가 장치 (결정적: seed)
    const R = rand("bg-" + type + (o.seed || 1));
    const extra = [];
    if (type === "mesh") for (let k = 0; k < 4; k++) extra.push(css(el("div", "", e), { position: "absolute", width: "1200px", height: "1200px", borderRadius: "50%", filter: "blur(140px)", opacity: ".8", background: [b, c, mix(c, "#ffffff", .35), mix(b, c, .5)][k], left: `${R() * 600 - 400}px`, top: `${R() * 1400 - 300}px` }));
    if (type === "topo" || type === "waves") {
      const svgNS = "http://www.w3.org/2000/svg", sv = document.createElementNS(svgNS, "svg");
      sv.setAttribute("width", W); sv.setAttribute("height", H); css(sv, { position: "absolute", left: "0", top: "0" });
      const n = type === "topo" ? 18 : 7;
      for (let k = 0; k < n; k++) {
        const pth = document.createElementNS(svgNS, "path"), y0 = type === "topo" ? 200 + k * 95 : 900 + k * 150, amp = type === "topo" ? 40 + R() * 70 : 60, f = 1 + R() * 2;
        let d = `M -40 ${y0}`; for (let x = -40; x <= W + 40; x += 40) d += ` L ${x} ${y0 + Math.sin(x / 180 * f + k) * amp + Math.sin(x / 70 + k * 2) * amp * .25}`;
        if (type === "waves") d += ` L ${W + 40} ${H + 40} L -40 ${H + 40} Z`;
        pth.setAttribute("d", d); pth.setAttribute("fill", type === "waves" ? mix(a, k % 2 ? b : c, .12 + k * .09) : "none");
        if (type === "topo") { pth.setAttribute("stroke", mix(a, c, .35)); pth.setAttribute("stroke-width", k % 5 === 0 ? "3" : "1.4"); }
        sv.appendChild(pth); pth.__k = k;
      }
      e.appendChild(sv); extra.push(sv);
    }
    if (type === "sky") for (let k = 0; k < 4; k++) {
      extra.push(css(el("div", "", e), { position: "absolute", left: "-20%", width: "140%", height: `${700 - k * 120}px`, bottom: `${-200 + k * -10}px`, borderRadius: "50% 50% 0 0", background: mix(b, "#000000", .08 + k * .12), transform: `translateX(${(R() - .5) * 300}px)` }));
      if (k === 0) extra.push(css(el("div", "", e), { position: "absolute", left: `${200 + R() * 500}px`, top: "520px", width: "260px", height: "260px", borderRadius: "50%", background: c, boxShadow: `0 0 160px ${c}` }));
    }
    if (type === "bokeh") for (let k = 0; k < 16; k++) { const r = 80 + R() * 220; const d = css(el("div", "", e), { position: "absolute", width: r + "px", height: r + "px", borderRadius: "50%", left: R() * W - r / 2 + "px", top: R() * H - r / 2 + "px", background: [b, c, "#ffffff"][k % 3], opacity: String(.08 + R() * .18), filter: `blur(${4 + R() * 16}px)` }); d.__p = R() * 6; extra.push(d); }
    if (type === "floor") { const g = css(el("div", "", e), { position: "absolute", left: "-50%", width: "200%", height: "1100px", bottom: "-200px", transform: "perspective(600px) rotateX(62deg)", transformOrigin: "50% 0", background: `linear-gradient(${c} 2px, transparent 2px) 0 0/${sz * 1.5}px ${sz * 1.5}px, linear-gradient(90deg, ${c} 2px, transparent 2px) 0 0/${sz * 1.5}px ${sz * 1.5}px`, opacity: ".55", maskImage: "linear-gradient(transparent, #000 40%)", WebkitMaskImage: "linear-gradient(transparent, #000 40%)" }); extra.push(g);
      extra.push(css(el("div", "", e), { position: "absolute", left: "0", right: "0", top: "760px", height: "4px", background: c, boxShadow: `0 0 60px 10px ${c}`, opacity: ".7" })); }
    if (type === "ink") for (let k = 0; k < 5; k++) extra.push(css(el("div", "", e), { position: "absolute", width: `${300 + R() * 500}px`, height: `${300 + R() * 500}px`, left: `${R() * W - 300}px`, top: `${R() * H - 300}px`, borderRadius: `${40 + R() * 20}% ${50 + R() * 20}% ${45 + R() * 20}% ${55 + R() * 20}%`, background: mix(a, c, .5), filter: "blur(14px)", opacity: ".7" }));
    if (type === "field") { const big = css(el("div", "", e), { position: "absolute", width: "1500px", height: "1500px", left: `${-200 + R() * 300}px`, top: `${700 + R() * 300}px`, borderRadius: o.shape === "square" ? "0" : "50%", background: b, transform: "rotate(12deg)" }); extra.push(big); }
    let stars = [];
    if (type === "stars") {
      const r = rand("stars" + (o.seed || 1));
      stars = Array.from({ length: 90 }, () => { const s = css(el("div", "", e), { position: "absolute", left: r() * W + "px", top: r() * H + "px", width: "4px", height: "4px", borderRadius: "50%", background: "#fff" }); s.__p = r() * 6; s.__z = 0.3 + r(); return s; });
    }
    return {
      el: e, update(lt) {
        const sp = o.speed ?? 1;
        if (type === "grid" || type === "dots" || type === "pixel" || type === "stripes") layer.style.transform = `translate(${(lt * 30 * sp) % sz}px, ${(lt * 45 * sp) % sz}px)`;
        if (type === "rays") layer.style.transform = `rotate(${lt * 8 * sp}deg) scale(1.4)`;
        if (type === "gradient" || type === "paper") layer.style.transform = `translate(${Math.sin(lt * .4) * 30}px, ${Math.cos(lt * .3) * 30}px)`;
        blobs.forEach((bl, k) => { const x = noise3D("bg" + k, lt * .12 * sp, k, 0), y = noise3D("bg" + k, 0, lt * .12 * sp, k); css(bl, { left: (W / 2 - 450 + x * 420) + "px", top: (H / 2 - 450 + y * 700 + (k - 1) * 380) + "px" }); });
        stars.forEach((s) => { s.style.opacity = String(0.25 + 0.75 * Math.abs(Math.sin(lt * 1.5 + s.__p))); s.style.transform = `translateY(${(lt * 20 * s.__z) % H}px)`; });
        if (type === "mesh") extra.forEach((m, k) => { m.style.transform = `translate(${noise3D("m" + k, lt * .1 * sp, k, 0) * 300}px, ${noise3D("m" + k, 0, lt * .1 * sp, k) * 400}px)`; });
        if (type === "topo" || type === "waves") extra[0].style.transform = `translateY(${Math.sin(lt * .3 * sp) * 14}px)`;
        if (type === "sky") extra.forEach((m, k) => { if (k > 0) m.style.translate = `${Math.sin(lt * .15 + k) * 12 * k}px 0`; });
        if (type === "bokeh") extra.forEach((m) => { m.style.translate = `0 ${Math.sin(lt * .4 + m.__p) * 24}px`; });
        if (type === "floor") extra[0].style.backgroundPosition = `0 ${(lt * 90 * sp) % (sz * 1.5)}px, 0 0`;
        if (type === "field") extra[0].style.rotate = `${lt * 3 * sp}deg`;
        if (type === "blueprint" || type === "halftone") layer.style.transform = `translate(${(lt * 12 * sp) % sz}px, ${(lt * 18 * sp) % sz}px)`;
        if (grain) grain.style.backgroundPosition = `${Math.floor(lt * 24) * 37 % 200}px ${Math.floor(lt * 24) * 53 % 200}px`;
      },
    };
  }

  // ---------- 글자 ----------
  /** anim: rise | type | pop | mask | wave | stamp | blur | slide | glitch | none · split: char | word | line
   *  o: x y w align size weight color font at dur stagger outAt highlight:[단어들] hlColor hlStyle(color|bg|underline|box) stroke shadow lh */
  function text(parent, str, o = {}) {
    const anim = o.anim || "rise", split = o.split || (anim === "type" || anim === "wave" || anim === "glitch" ? "char" : "word");
    const e = box(parent, { x: o.x ?? 80, y: o.y ?? 400, w: o.w ?? W - 160, style: { textAlign: o.align || "center", lineHeight: String(o.lh ?? 1.15), letterSpacing: (o.ls ?? -0.02) + "em" } });
    css(e, { fontFamily: o.font || "Pretendard, sans-serif", fontWeight: String(o.weight ?? 900), fontSize: (o.size ?? 96) + "px", color: o.color || T.text, wordBreak: "keep-all" });
    if (o.stroke) e.style.webkitTextStroke = o.stroke;
    if (o.shadow !== false) e.style.textShadow = o.shadow || "0 6px 24px rgba(0,0,0,.25)";
    const hl = new Set((o.highlight || []).map(String));
    const units = [];
    String(str).split("\n").forEach((line, li) => {
      const ln = el("div", "k-line", e); css(ln, { overflow: anim === "mask" ? "hidden" : "visible", paddingBottom: anim === "mask" ? ".08em" : "0" });
      const words = line.split(" ");
      words.forEach((w, wi) => {
        const isHl = hl.has(w) || hl.has(w.replace(/[.,!?]$/, ""));
        const wspan = el("span", "k-w", ln); css(wspan, { display: "inline-block", whiteSpace: "pre", position: "relative" });
        if (isHl) {
          const st = o.hlStyle || "color", c = o.hlColor || T.accent;
          if (st === "color") wspan.style.color = c;
          if (st === "bg") css(wspan, { background: c, color: o.hlText || T.bg, padding: "0 .12em", borderRadius: ".12em" });
          if (st === "underline") css(wspan, { backgroundImage: `linear-gradient(${c},${c})`, backgroundSize: "100% .14em", backgroundPosition: "0 92%", backgroundRepeat: "no-repeat" });
          if (st === "box") css(wspan, { outline: `.06em solid ${c}`, outlineOffset: ".04em", borderRadius: ".1em" });
          wspan.__hl = true;
        }
        if (split === "char") { for (const ch of w) { const s = el("span", "", wspan, esc(ch)); css(s, { display: "inline-block" }); units.push({ s, li, hl: isHl }); } }
        else units.push({ s: wspan, li, hl: isHl, txt: w });
        if (split !== "char") wspan.textContent = w; else if (!wspan.childNodes.length) wspan.textContent = w;
        if (wi < words.length - 1) { const sp = el("span", "", ln, " "); css(sp, { display: "inline-block", width: ".28em" }); }
      });
      if (split === "line") { /* 줄 단위는 줄을 하나의 단위로 */ }
    });
    const lines = [...e.querySelectorAll(".k-line")];
    const at = o.at ?? 0, dur = o.dur ?? 0.5, stg = o.stagger ?? (split === "char" ? 0.03 : 0.08);
    const outAt = o.outAt, outDur = o.outDur ?? 0.3;
    const r = rand("txt" + str);
    units.forEach((u) => { u.j = (r() - .5); });
    return {
      el: e, units,
      update(lt) {
        const out = outAt != null ? win(lt, outAt, outDur, E.in) : 0;
        e.style.opacity = String(1 - out);
        if (split === "line") lines.forEach((ln, k) => { const p = win(lt, at + k * stg, dur, E.back); css(ln, { opacity: String(clamp(p * 2)), transform: `translateY(${(1 - p) * 60}px)` }); });
        units.forEach((u, k) => {
          const d = at + k * stg; const p = win(lt, d, dur, anim === "stamp" || anim === "pop" ? E.back : E.out4); const s = u.s.style;
          if (anim === "none") return;
          if (anim === "rise") { s.opacity = String(clamp(p * 1.6)); s.transform = `translateY(${(1 - p) * 70}px)`; }
          if (anim === "mask") { s.transform = `translateY(${(1 - p) * 110}%)`; }
          if (anim === "pop") { s.opacity = String(clamp(p * 3)); s.transform = `scale(${lerp(.2, 1, p)}) rotate(${(1 - p) * u.j * 30}deg)`; }
          if (anim === "stamp") { s.opacity = String(clamp(p * 4)); s.transform = `scale(${lerp(2.4, 1, p)})`; }
          if (anim === "blur") { s.opacity = String(p); s.filter = `blur(${(1 - p) * 18}px)`; s.transform = `scale(${lerp(1.15, 1, p)})`; }
          if (anim === "slide") { s.opacity = String(clamp(p * 2)); s.transform = `translateX(${(1 - p) * -140}px)`; }
          if (anim === "type") { s.opacity = lt >= d ? "1" : "0"; }
          if (anim === "wave") { s.opacity = String(clamp(p * 2)); s.transform = `translateY(${Math.sin(lt * 6 + k * .45) * 10 + (1 - p) * 60}px)`; }
          if (anim === "glitch") { const g = lt < d + .25 && lt >= d; s.opacity = lt >= d ? "1" : "0"; s.transform = g ? `translate(${u.j * 24}px, ${-u.j * 10}px)` : "none"; s.color = g ? (k % 2 ? "#0ff" : "#f0f") : ""; }
        });
        if (anim === "type" && o.cursor !== false) { e.dataset.cursor = "1"; }
      },
    };
  }

  /** 숫자 카운트: from→to, 단위 · 소수 자리 · 쉼표 */
  function counter(parent, to, o = {}) {
    const t = text(parent, " ", { anim: "none", ...o });
    const from = o.from ?? 0, at = o.at ?? 0, dur = o.dur ?? 1.2, dec = o.decimals ?? 0;
    const node = t.el.querySelector(".k-w") || t.el;
    return { el: t.el, update(lt) {
      const p = win(lt, at, dur, E.out4); const v = lerp(from, to, p);
      node.textContent = (o.prefix || "") + v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (o.suffix || "");
      t.el.style.transform = `scale(${lerp(.85, 1, win(lt, at, .4, E.back))})`; t.el.style.opacity = String(clamp((lt - at) * 6));
    } };
  }

  // ---------- 도형 · 그림 ----------
  /** 둥근 상자 / 원 / 알약. o: x y w h r fill stroke at anim(pop|grow|draw|slide|none) rot */
  function shape(parent, o = {}) {
    const e = box(parent, { x: o.x, y: o.y, w: o.w ?? 200, h: o.h ?? 200, style: { borderRadius: (o.r ?? 24) + (typeof o.r === "string" ? "" : "px"), background: o.fill ?? T.accent, border: o.stroke || "none", boxShadow: o.shadow || "none", transformOrigin: o.origin || "50% 50%" } });
    if (o.html) e.innerHTML = o.html;
    const at = o.at ?? 0, dur = o.dur ?? .5, anim = o.anim || "pop";
    return { el: e, update(lt) {
      const p = win(lt, at, dur, anim === "grow" ? E.out4 : E.back);
      const out = o.outAt != null ? win(lt, o.outAt, .3, E.in) : 0;
      e.style.opacity = String(clamp(p * 3) * (1 - out));
      const rot = (o.rot ?? 0) + (o.spin ? lt * o.spin : 0);
      if (anim === "pop") e.style.transform = `scale(${p}) rotate(${rot}deg)`;
      if (anim === "grow") e.style.transform = `scaleX(${p}) rotate(${rot}deg)`;
      if (anim === "slide") e.style.transform = `translateY(${(1 - p) * 300}px) rotate(${rot}deg)`;
      if (anim === "none") e.style.transform = `rotate(${rot}deg)`;
      if (o.float) e.style.translate = `0 ${Math.sin(lt * 2 + (o.x || 0)) * o.float}px`;
    } };
  }

  /** 픽셀아트: rows = ["..XX..", ...], palette = { X: "#f00", o: "#fff" }. px = 한 칸 크기. frames 를 주면 fps 로 넘김 */
  function pixel(parent, rows, o = {}) {
    const frames = Array.isArray(rows[0]) ? rows : [rows];
    const px = o.px ?? 24, pal = o.palette || { X: T.text, A: T.accent };
    const cols = Math.max(...frames[0].map((r) => r.length));
    const cv = el("canvas", "", parent); cv.width = cols * px; cv.height = frames[0].length * px;
    css(cv, { position: "absolute", left: (o.x ?? (W - cols * px) / 2) + "px", top: (o.y ?? 600) + "px", imageRendering: "pixelated" });
    const g = cv.getContext("2d"); let last = -1;
    const paint = (f) => { if (f === last) return; last = f; g.clearRect(0, 0, cv.width, cv.height); frames[f].forEach((row, y) => [...row].forEach((ch, x) => { if (pal[ch]) { g.fillStyle = pal[ch]; g.fillRect(x * px, y * px, px, px); } })); };
    const at = o.at ?? 0;
    return { el: cv, update(lt) {
      paint(Math.floor(Math.max(0, lt) * (o.fps ?? 6)) % frames.length);
      const p = win(lt, at, .45, E.back); cv.style.opacity = String(clamp(p * 3));
      cv.style.transform = `translateY(${(1 - p) * 80 + (o.bob ? Math.round(Math.sin(lt * 4) * o.bob / px) * px : 0)}px) scale(${o.flip ? -1 : 1}, 1)`;
    } };
  }

  /** 선 그리기 (SVG path) — 화살표 · 밑줄 · 연결선 · 손글씨 동그라미. d = path, o: stroke width at dur arrow */
  function draw(parent, d, o = {}) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", W); svg.setAttribute("height", H); css(svg, { position: "absolute", left: "0", top: "0", overflow: "visible", pointerEvents: "none" });
    const p = document.createElementNS(svg.namespaceURI, "path"); p.setAttribute("d", d); p.setAttribute("fill", "none");
    p.setAttribute("stroke", o.stroke || T.accent); p.setAttribute("stroke-width", o.width ?? 10); p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
    svg.appendChild(p); parent.appendChild(svg);
    let len = 0; const at = o.at ?? 0, dur = o.dur ?? .6;
    return { el: svg, update(lt) { if (!len) { len = p.getTotalLength() || 1000; p.setAttribute("stroke-dasharray", String(len)); } p.setAttribute("stroke-dashoffset", String(len * (1 - win(lt, at, dur, E.inOut)))); } };
  }

  /** 막대 비교 차트. items: [{label, value, color}] · o: x y w h max at stagger unit horizontal */
  function bars(parent, items, o = {}) {
    const e = box(parent, { x: o.x ?? 90, y: o.y ?? 700, w: o.w ?? W - 180, h: o.h ?? 700 });
    const max = o.max ?? Math.max(...items.map((i) => i.value));
    const n = items.length, gap = 28, bw = ((o.w ?? W - 180) - gap * (n - 1)) / n, hh = (o.h ?? 700) - 120;
    const parts = items.map((it, k) => {
      const col = box(e, { x: k * (bw + gap), y: 0, w: bw, h: o.h ?? 700 });
      const bar = box(col, { x: 0, w: bw, h: 0, style: { bottom: "90px", top: "auto", background: it.color || (k === n - 1 ? T.accent : mix(T.bg, T.text, .25)), borderRadius: "18px 18px 6px 6px" } });
      const val = box(col, { x: 0, w: bw, style: { textAlign: "center", font: `900 ${o.vsize ?? 64}px Pretendard`, color: T.text } });
      const lab = box(col, { x: 0, w: bw, style: { bottom: "0", top: "auto", textAlign: "center", font: `700 ${o.lsize ?? 40}px Pretendard`, color: T.muted } }); lab.textContent = it.label;
      return { bar, val, it };
    });
    const at = o.at ?? 0, stg = o.stagger ?? .18;
    return { el: e, update(lt) {
      parts.forEach(({ bar, val, it }, k) => {
        const p = win(lt, at + k * stg, .9, E.out4); const h = hh * (it.value / max) * p;
        bar.style.height = h + "px"; val.style.top = ((o.h ?? 700) - 90 - h - (o.vsize ?? 64) * 1.3) + "px";
        val.textContent = (o.prefix || "") + Math.round(it.value * p).toLocaleString() + (o.unit || ""); val.style.opacity = String(clamp(p * 3));
      });
    } };
  }

  /** 앱 · 브라우저 · 폰 창 틀. kind: browser | phone | terminal | card · src 이미지 또는 html */
  function frame(parent, o = {}) {
    const kind = o.kind || "browser";
    const w = o.w ?? 880, h = o.h ?? 620;
    const e = box(parent, { x: o.x ?? (W - w) / 2, y: o.y ?? 640, w, h, style: { borderRadius: kind === "phone" ? "56px" : "24px", overflow: "hidden", background: kind === "terminal" ? "#0d1117" : "#fff", boxShadow: "0 40px 90px -30px rgba(0,0,0,.55), 0 0 0 2px rgba(255,255,255,.06)" } });
    if (kind === "browser" || kind === "terminal") {
      const bar = box(e, { x: 0, y: 0, w, h: 56, style: { background: kind === "terminal" ? "#161b22" : "#f1f2f4", display: "flex", alignItems: "center", gap: "12px", padding: "0 22px" } });
      ["#ff5f57", "#febc2e", "#28c840"].forEach((c) => css(el("i", "", bar), { width: "16px", height: "16px", borderRadius: "50%", background: c, display: "inline-block" }));
      if (o.title) css(el("span", "", bar, esc(o.title)), { font: "600 24px Pretendard", color: kind === "terminal" ? "#8b949e" : "#555", marginLeft: "18px" });
    }
    const body = box(e, { x: 0, y: kind === "browser" || kind === "terminal" ? 56 : 0, w, h: h - (kind === "browser" || kind === "terminal" ? 56 : 0), style: { overflow: "hidden" } });
    let img = null;
    if (o.src) { img = el("img", "", body); img.src = o.src; css(img, { width: "100%", display: "block" }); }
    if (o.html) body.innerHTML = o.html;
    const lines = o.lines ? o.lines.map((l, k) => { const d = box(body, { x: 30, y: 26 + k * 50, w: w - 60, style: { font: "500 30px 'JetBrains Mono', monospace", color: l.color || "#e6edf3", whiteSpace: "pre" } }); d.dataset.t = l.text ?? l; return d; }) : [];
    const at = o.at ?? 0;
    return { el: e, body, update(lt) {
      const p = win(lt, at, .6, E.back); e.style.opacity = String(clamp(p * 3)); e.style.transform = `translateY(${(1 - p) * 200}px) rotate(${(o.tilt ?? 0) * (1 - p * .5)}deg)`;
      if (img && o.scroll) img.style.transform = `translateY(${-Math.max(0, lt - at - .6) * o.scroll}px)`;
      let budget = Math.max(0, lt - at - .5) * (o.cps ?? 28);
      lines.forEach((d) => { const s = d.dataset.t; const n = Math.max(0, Math.min(s.length, Math.floor(budget))); d.textContent = s.slice(0, n) + (n < s.length && n > 0 ? "▌" : ""); budget -= s.length; });
    } };
  }

  /** 이미지(public/ 자산) 켄번스 */
  function image(parent, src, o = {}) {
    const e = box(parent, { x: o.x ?? 0, y: o.y ?? 0, w: o.w ?? W, h: o.h ?? H, style: { overflow: "hidden", borderRadius: (o.r ?? 0) + "px" } });
    const img = el("img", "", e); img.src = src; css(img, { width: "100%", height: "100%", objectFit: o.fit || "cover", transformOrigin: o.origin || "50% 40%" });
    const at = o.at ?? 0;
    return { el: e, update(lt) { const p = win(lt, at, .5); e.style.opacity = String(p); img.style.transform = `scale(${lerp(o.from ?? 1.0, o.to ?? 1.12, clamp(lt / (o.dur ?? 6)))})`; } };
  }

  /** 입자 (색종이 · 불꽃 · 먼지). kind: confetti | spark | dust | rain */
  function particles(parent, o = {}) {
    const n = o.n ?? 60, r = rand("pt" + (o.seed ?? 1)), kind = o.kind || "confetti";
    const cols = o.colors || [T.accent, T.text, mix(T.accent, "#ffffff", .4), T.good];
    const ps = Array.from({ length: n }, () => {
      const d = el("div", "", parent); const s = kind === "dust" ? 6 : kind === "spark" ? 10 : 18;
      css(d, { position: "absolute", width: s + "px", height: (kind === "confetti" ? s * .5 : kind === "rain" ? 40 : s) + "px", background: cols[Math.floor(r() * cols.length)], borderRadius: kind === "confetti" ? "3px" : "50%", opacity: kind === "dust" ? ".4" : "1" });
      return { d, x: r() * W, y: r() * H, vx: (r() - .5) * 600, vy: kind === "rain" ? 1400 + r() * 400 : -900 - r() * 700, rot: r() * 720, ph: r() * 6 };
    });
    const at = o.at ?? 0, cx = o.x ?? W / 2, cy = o.y ?? H / 2;
    return { el: parent, update(lt) {
      const t = lt - at;
      ps.forEach((p) => {
        if (kind === "dust") { p.d.style.transform = `translate(${p.x + Math.sin(lt * .5 + p.ph) * 40}px, ${(p.y - lt * 30) % H}px)`; return; }
        if (kind === "rain") { p.d.style.transform = `translate(${p.x}px, ${((p.y + lt * p.vy) % (H + 80)) - 80}px)`; return; }
        if (t < 0) { p.d.style.opacity = "0"; return; }
        const x = cx + p.vx * t, y = cy + p.vy * t + 1600 * t * t;
        p.d.style.opacity = String(clamp(1.6 - t * .6)); p.d.style.transform = `translate(${x}px, ${y}px) rotate(${p.rot * t}deg)`;
      });
    } };
  }

  /** 진행 링 / 퍼센트 */
  function ring(parent, value, o = {}) {
    const s = o.size ?? 520, sw = o.width ?? 44, rr = (s - sw) / 2, C = 2 * Math.PI * rr;
    const e = box(parent, { x: o.x ?? (W - s) / 2, y: o.y ?? 640, w: s, h: s });
    e.innerHTML = `<svg width="${s}" height="${s}"><circle cx="${s / 2}" cy="${s / 2}" r="${rr}" stroke="${mix(T.bg, T.text, .15)}" stroke-width="${sw}" fill="none"/><circle class="k-arc" cx="${s / 2}" cy="${s / 2}" r="${rr}" stroke="${o.color || T.accent}" stroke-width="${sw}" fill="none" stroke-linecap="round" transform="rotate(-90 ${s / 2} ${s / 2})" stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg>`;
    const lab = box(e, { x: 0, y: s / 2 - (o.fsize ?? 130) * .62, w: s, style: { textAlign: "center", font: `900 ${o.fsize ?? 130}px Pretendard`, color: T.text } });
    const arc = e.querySelector(".k-arc"); const at = o.at ?? 0;
    return { el: e, update(lt) { const p = win(lt, at, o.dur ?? 1.2, E.out4); arc.setAttribute("stroke-dashoffset", String(C * (1 - value / 100 * p))); lab.textContent = Math.round(value * p) + (o.suffix ?? "%"); e.style.opacity = String(clamp((lt - at) * 5)); } };
  }

  /** 좌우 대결 화면: left/right = { title, sub, color } · VS 도장 */
  function versus(parent, left, right, o = {}) {
    const e = box(parent, { x: 0, y: o.y ?? 560, w: W, h: o.h ?? 760 });
    const half = (side, d, k) => {
      const p = box(e, { x: side ? W / 2 : 0, y: 0, w: W / 2, h: o.h ?? 760, style: { background: d.color || (side ? T.accent : mix(T.bg, T.text, .12)), display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "18px", clipPath: side ? "polygon(8% 0,100% 0,100% 100%,0 100%)" : "polygon(0 0,100% 0,92% 100%,0 100%)" } });
      p.innerHTML = `<div style="font:900 ${o.tsize ?? 88}px Pretendard;color:${d.text || T.text};text-align:center;line-height:1.05">${esc(d.title)}</div>` + (d.sub ? `<div style="font:700 40px Pretendard;color:${d.text || T.text};opacity:.8;text-align:center">${esc(d.sub)}</div>` : "");
      return p;
    };
    const L = half(0, left), R = half(1, right);
    const vs = box(e, { x: W / 2 - 110, y: (o.h ?? 760) / 2 - 110, w: 220, h: 220, style: { borderRadius: "50%", background: T.text, color: T.bg, font: "900 96px Pretendard", display: "grid", placeItems: "center", boxShadow: "0 20px 50px rgba(0,0,0,.4)" } });
    vs.textContent = "VS"; const at = o.at ?? 0;
    return { el: e, update(lt) {
      const pl = win(lt, at, .5, E.out4), pr = win(lt, at + .12, .5, E.out4), pv = win(lt, at + .45, .4, E.back);
      L.style.transform = `translateX(${(1 - pl) * -W / 2}px)`; R.style.transform = `translateX(${(1 - pr) * W / 2}px)`;
      vs.style.transform = `scale(${pv}) rotate(${(1 - pv) * -90}deg)`;
    } };
  }

  /** 순서 목록: 하나씩 등장 · 체크/엑스 아이콘 */
  function list(parent, items, o = {}) {
    const e = box(parent, { x: o.x ?? 100, y: o.y ?? 700, w: o.w ?? W - 200 });
    const rows = items.map((it, k) => {
      const t = typeof it === "string" ? { text: it } : it;
      const r = box(e, { x: 0, y: k * (o.gap ?? 150), w: o.w ?? W - 200, h: (o.gap ?? 150) - 26, style: { display: "flex", alignItems: "center", gap: "28px", padding: "0 34px", borderRadius: "28px", background: o.card === false ? "none" : mix(T.bg, T.text, .08) } });
      const mark = t.mark ?? String(k + 1);
      r.innerHTML = `<span style="flex:none;width:76px;height:76px;border-radius:22px;display:grid;place-items:center;font:900 44px Pretendard;background:${t.color || (t.mark === "×" ? T.bad : t.mark === "○" || t.mark === "✓" ? T.good : T.accent)};color:${T.bg}">${esc(mark)}</span><span style="font:800 ${o.size ?? 52}px Pretendard;color:${T.text};line-height:1.2">${esc(t.text)}</span>`;
      return r;
    });
    const at = o.at ?? 0, stg = o.stagger ?? .35;
    return { el: e, update(lt) { rows.forEach((r, k) => { const p = win(lt, at + k * stg, .5, E.back); r.style.opacity = String(clamp(p * 3)); r.style.transform = `translateX(${(1 - p) * 120}px)`; }); } };
  }

  /** 캐릭터(characters/<이름>) 를 화면 안 배우로: 립싱크는 마무리 단계 캐릭터와 별개로, 여기서는 등장 · 흔들림 · 반응 */
  function actor(parent, src, o = {}) {
    const img = el("img", "", parent); img.src = src;
    const w = o.w ?? 360; css(img, { position: "absolute", left: (o.x ?? (W - w) / 2) + "px", top: (o.y ?? 1100) + "px", width: w + "px" });
    const at = o.at ?? 0;
    return { el: img, update(lt) {
      const p = win(lt, at, .5, E.back);
      const react = o.react != null ? Math.sin(clamp((lt - o.react) / .4) * Math.PI) : 0;
      img.style.opacity = String(clamp(p * 3));
      img.style.transform = `translateY(${(1 - p) * 300 + Math.sin(lt * 3) * 10 - react * 60}px) rotate(${Math.sin(lt * 2) * 3}deg) scale(${1 + react * .15})`;
    } };
  }

  // ---------- 자막 (단어 타이밍) ----------
  /** style: highlight(노란 단어 강조) | box(검정 상자) | top(위 한 줄) | pop(단어 하나씩 크게) | outline | none */
  function captions(root, o = {}) {
    if (o.style === "none") return { update() {} };
    const style = o.style || "highlight";
    const pages = window.SFLib.captionPages(SF.captions, o.combineMs ?? 900);
    const e = css(el("div", "k-cap", root), { position: "absolute", left: "70px", right: "70px", top: (o.y ?? (style === "top" ? 300 : 1330)) + "px", textAlign: "center", zIndex: "50", pointerEvents: "none" });
    const hl = o.color || (T.caption && T.caption.toUpperCase() !== "#FFFFFF" ? T.caption : "#FFE14D");
    const base = `font:900 ${o.size ?? (style === "pop" ? 110 : 78)}px Pretendard;line-height:1.2;letter-spacing:-.02em;`;
    let cur = -1;
    return { update(t) {
      const k = pages.findIndex((p) => t >= p.start && t < p.end);
      if (k !== cur) { cur = k; e.innerHTML = ""; if (k < 0) return;
        pages[k].tokens.forEach((w) => { const s = el("span", "", e, esc(w.text.trim())); s.style.cssText = base + `display:inline-block;margin:0 ${style === "box" ? .08 : style === "pop" ? .26 : .22}em;`; s.__w = w; }); }
      if (k < 0) return;
      const ms = t * 1000; const pg = pages[k];
      [...e.children].forEach((s, i) => {
        const w = s.__w, on = ms >= w.startMs && ms < w.endMs + 80, said = ms >= w.startMs;
        if (style === "highlight") { s.style.color = on ? hl : "#fff"; s.style.webkitTextStroke = "10px #000"; s.style.paintOrder = "stroke fill"; s.style.transform = on ? "scale(1.08)" : "none"; }
        if (style === "box") { s.style.color = "#fff"; s.style.background = on ? hl : "rgba(0,0,0,.78)"; s.style.color = on ? "#000" : "#fff"; s.style.padding = "0 .18em"; s.style.borderRadius = ".14em"; }
        if (style === "top" || style === "outline") { s.style.color = said ? "#fff" : "rgba(255,255,255,.35)"; s.style.webkitTextStroke = "8px #000"; s.style.paintOrder = "stroke fill"; }
        if (style === "pop") { s.style.display = on ? "inline-block" : "none"; const p = clamp((ms - w.startMs) / 140); s.style.transform = `scale(${lerp(.6, 1, ease.outBack(p))}) rotate(${(i % 2 ? 2 : -2)}deg)`; s.style.color = i % 3 === 1 ? hl : "#fff"; s.style.webkitTextStroke = "12px #000"; s.style.paintOrder = "stroke fill"; }
      });
      const p = clamp((t - pg.start) / .12); e.style.opacity = String(p); e.style.transform = `translateY(${(1 - p) * 20}px)`;
    } };
  }

  // ---------- 전환 ----------
  /** 장면 경계 전환. kind: cut | fade | wipe | slide | zoom | flash | glitch | circle | push */
  function transition(kind, inEl, outEl, p) {
    const s = inEl.style, o = outEl ? outEl.style : null;
    const q = ease.inOutCubic(p);
    s.opacity = "1"; s.clipPath = "none"; s.transform = "none"; s.filter = "none";
    if (kind === "fade") s.opacity = String(q);
    if (kind === "wipe") s.clipPath = `inset(0 ${(1 - q) * 100}% 0 0)`;
    if (kind === "circle") s.clipPath = `circle(${q * 120}% at 50% 50%)`;
    if (kind === "slide") { s.transform = `translateY(${(1 - q) * 100}%)`; if (o) o.transform = `translateY(${-q * 30}%)`; }
    if (kind === "push") { s.transform = `translateX(${(1 - q) * 100}%)`; if (o) o.transform = `translateX(${-q * 100}%)`; }
    if (kind === "zoom") { s.opacity = String(q); s.transform = `scale(${lerp(1.4, 1, q)})`; s.filter = `blur(${(1 - q) * 12}px)`; if (o) o.transform = `scale(${lerp(1, .8, q)})`; }
    if (kind === "flash") { s.opacity = String(q > .5 ? 1 : 0); s.filter = `brightness(${1 + (1 - Math.abs(q - .5) * 2) * 3})`; }
    if (kind === "glitch") { s.opacity = String(q > .3 ? 1 : 0); s.transform = q < .9 ? `translateX(${Math.sin(p * 80) * 30 * (1 - q)}px)` : "none"; s.filter = q < .9 ? `hue-rotate(${(1 - q) * 180}deg) saturate(3)` : "none"; }
  }

  // ---------- 구성 ----------
  /** 편집기에서 손으로 고친 값 (compositions/<id>/overrides.json): { "장면:요소번호": { dx, dy, scale, rot, opacity, color, fill, text, hidden } } */
  // 키프레임: o.kf = [{ t(장면 안 초), dx, dy, scale, rot, opacity }] — 사이는 부드럽게(inOut) 보간, 없는 값은 o 의 고정값
  const KF = ["dx", "dy", "scale", "rot", "opacity"];
  function kfAt(o, lt) {
    const kf = o.kf; if (!kf || !kf.length) return o;
    const r = { ...o };
    for (const f of KF) {
      const ks = kf.filter((k) => k[f] != null); if (!ks.length) continue;
      if (lt <= ks[0].t) { r[f] = ks[0][f]; continue; }
      if (lt >= ks[ks.length - 1].t) { r[f] = ks[ks.length - 1][f]; continue; }
      for (let j = 0; j < ks.length - 1; j++) { const a = ks[j], b = ks[j + 1]; if (lt >= a.t && lt <= b.t) { r[f] = lerp(a[f], b[f], E.inOut((lt - a.t) / Math.max(.001, b.t - a.t))); break; } }
    }
    return r;
  }
  function applyOverrides(i, host, lt = 0) {
    const O = window.FLUMA_OVR; if (!O) return;
    for (const key in O) {
      const [sPart, path] = key.split(":"); if (sPart !== String(i)) continue;   // i = 장면 번호, 또는 "g"(전체 판)
      let e = host; for (const n of path.split(".")) { e = e && e.children[Number(n)]; } if (!e) continue; const o = kfAt(O[key], lt);
      e.style.translate = `${o.dx || 0}px ${o.dy || 0}px`;
      if (o.scale != null) e.style.scale = String(o.scale);
      if (o.rot != null) e.style.rotate = o.rot + "deg";
      if (o.opacity != null) e.style.opacity = String(o.opacity * (parseFloat(e.style.opacity || "1") || 1));
      if (o.color) e.style.color = o.color;
      if (o.fill) e.style.background = o.fill;
      if (o.hidden) e.style.visibility = "hidden";
      if (o.text != null && e.__ovrText !== o.text) { e.__ovrText = o.text; e.textContent = o.text; }
    }
  }
  window.__flumaApplyOverrides = applyOverrides; window.__flumaKfAt = kfAt;

  /** c.cue("S3로", { nth: 0, end: false, offset: 0, or: 1.2 }) → 장면 안 시각(초). 단어 일부만 맞아도 됨(공백 · 문장부호 무시).
   *  못 찾으면 or(없으면 장면 중간)를 쓰고 window.__FLUMA_MISSING_CUES 에 남긴다 — scripts/layout_check.py 가 알려 준다 */
  function cueAt(c, text, o = {}) {
    const norm = (x) => String(x).toLowerCase().replace(/[\s.,!?·…"'“”‘’()\[\]~:;-]/g, "");
    const q = norm(text);
    const hits = q ? c.words.filter((w) => norm(w.text).includes(q) || (q.length > 2 && q.includes(norm(w.text)) && norm(w.text).length > 1)) : [];
    const w = hits[o.nth ?? 0];
    if (!w) {
      (window.__FLUMA_MISSING_CUES = window.__FLUMA_MISSING_CUES || []).push({ scene: c.i, text });
      return o.or ?? c.sc.sec * 0.5;
    }
    return Math.max(0, (o.end ? w.end : w.at) + (o.offset ?? 0));
  }

  function compose(spec) {
    const root = document.getElementById("root");
    css(root, { position: "relative", width: W + "px", height: H + "px", overflow: "hidden", background: T.bg });
    const cam = css(el("div", "k-cam", root), { position: "absolute", inset: "0", transformOrigin: "50% 45%" });
    const TR = spec.trDur ?? 0.35;
    // 일부 장면만 렌더(엔진 섞기 · --scenes)해도 컴포지션 · 손 수정 · 전환은 원래 장면 번호(gi)로 찾는다
    const scenes = SF.scenes.map((sc, i) => {
      const gi = sc.index ?? i;
      const host = css(el("div", "k-scene", cam), { position: "absolute", inset: "0", overflow: "hidden", visibility: "hidden" });
      const auto = [];
      const c = { root: host, sc, i: gi, sb: SF.sb, scene: SF.sb.scenes[i], T, W, H, auto: (...ps) => { auto.push(...ps); return ps[0]; }, asset: (a) => a };
      // 음성 단어 신호: 이 장면 나레이션의 단어와 장면 안 시각(초). 움직임을 숫자로 박지 말고 c.cue("S3") 로 —
      // 음성을 다시 만들어 길이가 바뀌어도 움직임이 말에 맞춰 따라간다
      c.words = (SF.captions || []).filter((w) => w.scene === gi).map((w) => ({ text: String(w.text).trim(), at: w.startMs / 1000 - sc.start, end: w.endMs / 1000 - sc.start }));
      c.cue = (text, o = {}) => cueAt(c, text, o);
      const fn = (spec.scenes && (spec.scenes[gi] || spec.scenes[spec.scenes.length - 1])) || (() => null);
      let drawFn = null;
      try { drawFn = fn(c); } catch (err) { host.innerHTML = `<pre style="color:#f66;font:28px monospace;padding:40px;white-space:pre-wrap">장면 ${gi + 1} 오류: ${esc(err.message)}</pre>`; }
      return { host, sc, gi, auto, drawFn };
    });
    const caps = captions(root, spec.captions || {});
    const trs = spec.transitions || [];
    const global = spec.global ? spec.global({ root, cam, T, W, H }) : null;
    function draw(t) {
      scenes.forEach((s, i) => {
        const { start, end } = s.sc; const last = i === scenes.length - 1;
        const vis = t >= start && (t < end + (last ? 1 : TR));
        // 안 보이는 장면은 display 로 통째로 뺀다 — visibility 만 숨기면 자식이 visibility: visible 을 직접 가진 경우(컷 · 짤 show)
        // 부모와 상관없이 보여서, 타임라인을 오가면 지나간 장면의 요소가 다른 장면 위에 남는다(2026-11-02)
        s.host.style.visibility = vis ? "visible" : "hidden";
        s.host.style.display = vis ? "" : "none";
        if (!vis) return;
        const lt = t - start, p = clamp(lt / s.sc.sec);
        s.auto.forEach((a) => a.update(lt));
        if (s.drawFn) try { s.drawFn(lt, p); } catch (err) { /* 그리기 오류는 무시 */ }
        applyOverrides(s.gi, s.host, lt);
        const kind = i === 0 ? "cut" : trs[s.gi - 1] || spec.transition || "fade";
        const tp = clamp(lt / TR);
        transition(kind, s.host, scenes[i - 1] ? scenes[i - 1].host : null, tp);
        s.host.style.zIndex = String(i + 1);
      });
      if (global) global(t);
      applyOverrides("g", root, t);   // 편집기에서 전체 판 요소를 손으로 옮긴 값 (키 g:<경로>, 시각은 영상 전체 기준)
      const camf = spec.camera ? spec.camera(t) : null;
      if (camf) cam.style.transform = `translate(${camf.x || 0}px, ${camf.y || 0}px) scale(${camf.scale || 1}) rotate(${camf.rot || 0}deg)`;
      caps.update(t);
    }
    return window.SFLib.mount(draw);
  }

  /** 카메라 도우미: 장면 시작마다 살짝 펀치 줌 + 흔들림 */
  const camera = {
    punch: (amount = .06, decay = 6) => (t) => { const i = SF.scenes.findIndex((s) => t >= s.start && t < s.end); const lt = i < 0 ? 9 : t - SF.scenes[i].start; return { scale: 1 + amount * Math.exp(-lt * decay) }; },
    drift: (amp = 14) => (t) => ({ x: noise3D("cx", t * .3, 0, 0) * amp, y: noise3D("cy", 0, t * .3, 0) * amp, scale: 1.02 }),
    shake: (at, dur = .3, amp = 18) => (t) => { const k = clamp((t - at) / dur); const a = k > 0 && k < 1 ? (1 - k) * amp : 0; return { x: Math.sin(t * 90) * a, y: Math.cos(t * 70) * a }; },
  };

  // ---------- 연속 이미지 (레이어 요소: 다른 엔진 · 생성 모델이 만든 PNG 연속 이미지 · 사용자가 올린 실사 영상을 프레임으로 푼 것) ----------
  /** K.seq(root, "elements/<id>/<이름>" | "uploads/<id>/<이름>", { x, y, w, h, frames, fps, at, loop, from, to, ext, fit, radius, under, z })
   *  under: true = 일부러 글자 뒤에 까는 배경판 (겹침 검사에서 오류로 안 침, 기본 z 1)
   *  z = 쌓는 순서(zIndex). 한 장면에 여러 엔진 요소를 겹칠 때: 배경판 1 · 덮개 2 · 요소 3~8 · 글자 10 · 자막은 그 위
   *  pins: [{ name, el, dx, dy, align:[0.5,1] }] = 요소 meta.anchors[name] 점(프레임별 좌표)을 라벨(el)이 프레임마다 따라감.
   *        라벨의 x · y 는 무시되고 transform 으로 옮겨진다. 직접 쓰려면 반환값 .at(name, lt) → { x, y, visible }
   *  시간(lt)으로 프레임을 고른다 → 렌더에서도 정확히 같은 장면. from/to(초)로 영상의 일부만(트림). meta.json 이 있으면 frames · fps · ext 를 거기서 */
  function seq(parent, base, o = {}) {
    const meta = (window.SF_SEQ && window.SF_SEQ[base]) || {};
    const frames = o.frames ?? meta.frames ?? 1, fps = o.fps ?? meta.fps ?? 30, ext = o.ext ?? meta.ext ?? "png";
    const pad = o.pad ?? meta.pad ?? (ext === "jpg" ? 5 : 4);   // 올린 영상 f00001.jpg · 레이어 요소 f0001.png
    const e = box(parent, { x: o.x ?? 0, y: o.y ?? 0, w: o.w ?? W, h: o.h ?? H, style: { overflow: "hidden", borderRadius: (o.radius ?? 0) + "px", ...(o.z != null ? { zIndex: o.z } : o.under ? { zIndex: 1 } : {}) } });
    e.dataset.seq = base;                      // 겹침 검사(scripts/overlap_check.py)가 meta.bbox 로 실제 보이는 영역을 계산
    if (o.under) e.dataset.under = "1";        // 일부러 글자 뒤 배경으로 깐 것 → 겹침을 오류가 아닌 참고로
    const f0 = Math.floor((o.from ?? 0) * fps), f1 = Math.min(frames, o.to != null ? Math.ceil(o.to * fps) : frames);
    const url = (i) => `${base}/f${String(i).padStart(pad, "0")}.${ext}`;
    // 쓰는 프레임을 전부 미리 불러 둔다 (숨긴 img). 렌더러는 처음에 페이지의 이미지가 다 불릴 때까지 기다리므로,
    // 프레임마다 src 를 바꿔 새로 불러오다 못 따라가 같은 그림이 반복되고 건너뛰는(끊기는) 일이 없다.
    const pool = el("div", "", e); css(pool, { display: "none" });
    const imgs = [];
    for (let i = f0 + 1; i <= f1; i++) { const im = el("img", "", pool); im.decoding = "sync"; im.src = url(i); imgs.push(im); }
    // 그리기는 캔버스에 즉시 (drawImage 는 동기) — 이미지 교체 대기가 없음
    const cv = el("canvas", "", e);
    cv.width = meta.w || meta.size || 1080; cv.height = meta.h || meta.size || 1080;
    css(cv, { width: "100%", height: "100%", objectFit: o.fit || "contain", display: "block" });
    const g = cv.getContext("2d");
    let last = -1;
    const draw = (k) => {
      const im = imgs[k];
      if (!im || !im.complete || !im.naturalWidth) return false;
      if (cv.width !== im.naturalWidth || cv.height !== im.naturalHeight) { cv.width = im.naturalWidth; cv.height = im.naturalHeight; }
      g.clearRect(0, 0, cv.width, cv.height); g.drawImage(im, 0, 0);
      return true;
    };
    // 요소 고정점 → 화면(1080×1920) 좌표: 요소 이미지 픽셀을 상자 · object-fit(contain/cover)에 맞춰 환산
    const anchors = meta.anchors || {};
    const toPage = (px, py) => {
      const bw = o.w ?? W, bh = o.h ?? H, iw = cv.width, ih = cv.height;
      const k = (o.fit === "cover" ? Math.max : Math.min)(bw / iw, bh / ih);
      return [(o.x ?? 0) + (bw - iw * k) / 2 + px * k, (o.y ?? 0) + (bh - ih * k) / 2 + py * k];
    };
    const at = (name, k) => { const tr = anchors[name]; if (!tr || !tr.length) return null; const v = tr[Math.max(0, Math.min(tr.length - 1, f0 + k))]; const [x, y] = toPage(v[0], v[1]); return { x, y, visible: !!v[2] }; };
    const pins = (o.pins || []).map((p) => ({ ...p, node: p.el && (p.el.el || p.el) }));
    for (const p of pins) if (p.node && p.node.style) { p.node.style.left = "0px"; p.node.style.top = "0px"; p.node.style.willChange = "transform"; p.node.dataset.pin = base; }   // 겹침 검사: 자기 요소에 붙인 라벨은 겹쳐도 정상
    return { el: e, at: (name, lt) => at(name, Math.max(0, Math.round((lt - (o.at ?? 0)) * fps))), update(lt) {
      const t = lt - (o.at ?? 0);
      e.style.visibility = t < 0 ? "hidden" : "visible";
      if (t < 0 || !imgs.length) return;
      const n = imgs.length;
      let k = Math.round(t * fps);                       // 가장 가까운 프레임 (요소 fps 와 영상 fps 가 달라도 고르게)
      k = o.loop ? k % n : Math.min(n - 1, k);
      if (k !== last && draw(k)) last = k;
      for (const p of pins) {                            // 라벨이 요소의 고정점을 따라감. align: 라벨의 어느 점을 고정점에 (기본 가운데 아래)
        const a = at(p.name, k); if (!a || !p.node) continue;
        const ax = p.align?.[0] ?? 0.5, ay = p.align?.[1] ?? 1;
        const w = p.node.offsetWidth, h = p.node.offsetHeight;
        p.node.style.transform = `translate(${a.x - w * ax + (p.dx ?? 0)}px, ${a.y - h * ay + (p.dy ?? 0)}px)`;
      }
    } };
  }

  /** K.web(root, "elements/<id>/<이름>", { x, y, w, h, at, times, zoom, labels, chrome, z, name })
   *  scripts/webrec.py 가 남긴 웹 녹화(단계 화면 + 실제 녹화 구간)를 브라우저 창 안에서 재생한다.
   *  times[k] = k번째 동작(meta.actions[k])이 일어나는 장면 안 시각. c.cue("생성") 처럼 나레이션 단어에 맞춘다.
   *  없으면 at + 0.8 부터 1.6초 간격. 커서는 동작 0.55초 전부터 대상으로 움직이고, 그 순간 클릭 물결 · 화면 전환이 일어난다.
   *  입력은 글자가 쳐지듯, 스크롤은 미끄러지듯, 실제 녹화 구간은 그대로 재생(커서는 녹화 중 동작 시각을 따라감).
   *  zoom: 확대 배율(기본 1.25, false 면 끔) — 가까운 동작은 한 구간으로 묶어 한 번만 들어가고, maxZooms(기본 2)번까지만. labels: true 면 동작의 label 을 단계 배지로 띄움.
   *  read: 글자를 읽히게(true = 사람 편집 기준 52px, 숫자 = 목표 px). 페이지 전체를 축소하지 않고 늘 확대한 채 지금 말하는 대상(동작 위치 · focus)을
   *        화면 가운데로 따라간다 — 2026-11-02 '슬라이드 같음'의 첫째 원인(페이지 통째 축소 → 글자 20px)을 막는 기본값. textPx: 페이지 본문 글자 크기(CSS px, 기본 14)
   *  focus: [{ t, text } | { t, box:[x,y,w,h] }] 동작이 없는 때 볼 곳 — text 는 화면 글자로 찾음(녹화가 저장한 states[].texts), box 는 뷰포트 좌표. t = c.cue("단어")
   *  scene: c 를 넘기면 그 장면 콘티 beats 의 do:"확대"(what = 화면 글자)를 focus 로 쓴다 — 콘티에 적은 대로, 좌표 없이 */
  function web(parent, base, o = {}) {
    const meta = (window.SF_SEQ && window.SF_SEQ[base]) || {};
    const states = meta.states || [], acts = meta.actions || [];
    const [vw, vh] = meta.viewport || [1280, 800];
    const bar = o.chrome === false ? 0 : 46;
    const w = o.w ?? 1000, ih = Math.round(w * vh / vw), h = o.h ?? ih + bar, k = w / vw;
    const e = box(parent, { x: o.x ?? (W - w) / 2, y: o.y ?? 560, w, h, style: { borderRadius: "18px", overflow: "hidden", background: "#fff",
      boxShadow: "0 40px 90px -30px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08)", ...(o.z != null ? { zIndex: o.z } : {}) } });
    let urlText = null;
    if (bar) {
      const b = box(e, { x: 0, y: 0, w, h: bar, style: { background: "#f1f2f4", display: "flex", alignItems: "center", gap: "10px", padding: "0 18px", boxSizing: "border-box" } });
      ["#ff5f57", "#febc2e", "#28c840"].forEach((c) => css(el("i", "", b), { width: "13px", height: "13px", borderRadius: "50%", background: c, display: "inline-block", flex: "none" }));
      urlText = css(el("span", "", b), { marginLeft: "14px", flex: "1", height: "28px", lineHeight: "28px", borderRadius: "8px", background: "#fff", padding: "0 14px",
        font: "500 17px Pretendard", color: "#555", overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" });
    }
    const view = box(e, { x: 0, y: bar, w, h: h - bar, style: { overflow: "hidden", background: "#fff" } });
    const cam = box(view, { x: 0, y: 0, w, h: ih, style: { transformOrigin: "0 0", willChange: "transform" } });
    const shots = states.map((s) => { const im = el("img", "", cam); im.decoding = "sync"; im.src = `${base}/${s.shot}`;
      css(im, { position: "absolute", left: "0", top: "0", width: w + "px", height: ih + "px", opacity: "0" }); return im; });
    // 입력: 다음 화면의 입력칸 부분만 왼쪽부터 드러냄
    const typeWin = box(cam, { x: 0, y: 0, w: 0, h: 0, style: { overflow: "hidden", display: "none" } });
    const typeImg = el("img", "", typeWin); css(typeImg, { position: "absolute", width: w + "px", height: ih + "px" });
    // 실제 녹화 구간: 프레임을 미리 불러 캔버스에 그림
    const clips = acts.map((a) => {
      if (!a.clip) return null;
      const c = a.clip, pool = el("div", "", cam); css(pool, { display: "none" });
      const imgs = Array.from({ length: c.frames }, (_, i) => { const im = el("img", "", pool); im.decoding = "sync"; im.src = `${base}/${c.dir}/f${String(i + 1).padStart(c.pad || 5, "0")}.${c.ext || "jpg"}`; return im; });
      const cv = el("canvas", "", cam); cv.width = Math.round(vw * (meta.scale || 2)); cv.height = Math.round(vh * (meta.scale || 2));
      css(cv, { position: "absolute", left: "0", top: "0", width: w + "px", height: ih + "px", display: "none" });
      return { c, imgs, cv, g: cv.getContext("2d"), last: -1 };
    });
    const redBoxes = () => boxes.map((r) => ({ ...r, e: box(cam, { x: (r.b[0] - 8) * k, y: (r.b[1] - 6) * k, w: (r.b[2] + 16) * k, h: (r.b[3] + 12) * k,
      style: { border: `${Math.max(4, Math.round(5 / Math.max(1, zRead * 0.5)))}px solid #ff2d2d`, borderRadius: "6px", pointerEvents: "none", visibility: "hidden" } }) }));
    let reds = null;
    const ripple = box(cam, { x: 0, y: 0, w: 60, h: 60, style: { borderRadius: "50%", border: `4px solid ${T.accent}`, opacity: "0", pointerEvents: "none" } });
    const cur = box(cam, { x: 0, y: 0, w: 30, h: 42, style: { pointerEvents: "none", filter: "drop-shadow(0 3px 4px rgba(0,0,0,.35))" } });
    cur.innerHTML = '<svg viewBox="0 0 20 28" width="30" height="42"><path d="M1 1 L1 22 L6.5 16.5 L10.5 26 L14 24.5 L10 15.5 L18 15.5 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const badge = box(e, { x: 22, y: bar + 18, style: { padding: "10px 20px", borderRadius: "999px", background: T.accent, color: "#fff",
      font: "800 26px Pretendard", opacity: "0", boxShadow: "0 10px 30px -10px rgba(0,0,0,.5)" } });

    const at = o.at ?? 0, MOVE = 0.55;
    const times = acts.map((a, i) => (o.times && o.times[i] != null ? o.times[i] : at + 0.8 + i * 1.6));
    const ctr = (b) => (b ? [b[0] + b[2] / 2, b[1] + b[3] / 2] : null);
    // 커서가 지나갈 점들: 동작 대상 + 녹화 구간 안 동작
    const marks = [];
    // 볼 곳을 글자로: focus 의 text, 장면 콘티 beats 의 do:"확대"(what) — 녹화 때 저장한 화면 글자(states[].texts)에서 찾는다.
    //  좌표를 손으로 고르지 않게(2026-11-02). 그 시각에 보이는 화면(state)에서, 맞는 것 중 가장 작은(구체적인) 덩어리
    const stateAt = (lt) => { let st = 0; acts.forEach((a, j) => { if (lt >= times[j]) st = a.to; }); return st; };
    const findText = (q, lt) => {
      const tx = (states[stateAt(lt)] || {}).texts || [], ql = String(q).toLowerCase().replace(/\s+/g, " ").trim();
      const hit = tx.filter((x) => x.t.toLowerCase().includes(ql)).sort((x, y) => x.b[2] * x.b[3] - y.b[2] * y.b[3]);
      if (!hit.length) { console.warn(`[K.web] ${base}: 화면에서 "${q}" 를 못 찾음`); return null; }
      return hit[0];
    };
    // 보기 방식(2026-11-02 사용자 지적: 논문은 전체를 보여 줘야 하는데 다른 장면처럼 당겼다):
    //  "전체" = 페이지 폭 그대로(확대 없음) — 기사 · 논문 · 문서처럼 '이런 글이 있다'가 증거인 화면. 중요한 곳은 확대 대신 빨간 상자(beats do:"표시")
    //  "확대" = 말하는 대상을 당겨 읽히게 — 버튼 · 숫자 · 메뉴 같은 조작 화면. 배율은 대상 글자의 실제 크기로(큰 제목은 조금, 작은 UI 는 많이)
    //  정하지 않으면 장면 콘티의 view, 없으면 screen 이 기사면 전체 · 나머지는 확대
    const scn = o.scene && o.scene.scene;
    const viewMode = o.view || (scn && scn.view) || (scn && scn.screen === "기사" ? "전체" : "확대");
    const focusList = [...(o.focus || [])], boxes = [];
    if (scn) for (const b of scn.beats || []) {
      if (b.do === "확대" && b.what) focusList.push({ t: o.scene.cue(b.at), text: b.what });
      if (b.do === "표시" && b.what) { const t0 = o.scene.cue(b.at), h = findText(b.what, t0); if (h) { boxes.push({ t: t0, end: t0 + (b.hold ?? 99), b: h.b }); focusList.push({ t: t0, box: h.b, fs: h.fs }); } }
    }
    for (const f of focusList) {
      const h = f && (f.box ? { b: f.box, fs: f.fs } : (f.text ? findText(f.text, f.t ?? 0) : null));
      if (h && h.b) marks.push({ t: f.t ?? 0, p: ctr(h.b), b: h.b, fs: h.fs, click: false, look: true });
    }
    acts.forEach((a, i) => {
      if (a.box) marks.push({ t: times[i], p: ctr(a.box), b: a.box, click: a.do === "click" || a.do === "type" });
      if (a.clip) for (const ev of a.clip.events || []) if (ev.box) marks.push({ t: times[i] + ev.t, p: ctr(ev.box), click: ev.do === "click" || ev.do === "type" });
    });
    marks.sort((p, q) => p.t - q.t);
    // 목표 글자 크기: 40px(사람 쇼츠 하단 34 ~ 중앙 57). 52px 로 잡으니 4배 가까이 당겨져 답답하고 보여 줄 것이 잘렸다(2026-11-02 사용자 지적)
    const readPx = o.read === true ? 40 : (typeof o.read === "number" ? o.read : 0);
    const zRead = readPx ? Math.max(1, Math.min(4, readPx / ((o.textPx ?? 14) * k))) : 1;
    // 읽히게 모드의 배율은 '무엇을 보여 주나'로: 대상 영역(box)이 창 폭을 채우게(주변 10% 여유). 작은 버튼 하나면 최소 폭 minView(기본 380px)만큼 —
    // 너무 당기면 맥락이 사라진다(2026-11-02 4배 고정 → 머리줄 · 잘린 제목 · 빈 화면). 글자 크기(zRead)는 상한으로만
    //  하한은 글자(zRead 의 0.8배 — 9:16 판에서 본문이 읽히려면 한 번에 페이지 폭 300~400px 만 보인다): 넓은 영역을 주면 그 가운데를 읽히는 크기로 보여 준다
    //  대상이 통째로 들어오게(여유 20%) 맞추되, 글자가 읽히는 하한(zRead 0.85배)과 지나친 확대 상한(zRead 1.1배) 사이. 작은 버튼 하나면 주변 맥락 minView(기본 460px)까지
    const zBox = (b) => (b ? Math.max(zRead * 0.85, Math.min(zRead * 1.1, 4, vw / (Math.max(b[2], o.minView ?? 460) * 1.2), vh / (Math.max(b[3], 100) * 1.25))) : zRead);
    //  대상 글자 크기를 알면: 그 글자가 목표 크기로 보이는 배율(제목 28px 이면 1.4배, 본문 14px 이면 2.9배) — 단 대상이 통째로 들어오는 배율보다 크지 않게
    const zMark = (m) => {
      if (!m) return zRead;
      if (viewMode === "전체") return 1;
      if (!m.fs) return zBox(m.b);
      const fit = m.b ? Math.min(vw / (m.b[2] * 1.15), vh / (m.b[3] * 1.3)) : 4;
      return Math.max(1, Math.min(4, readPx / (m.fs * k), Math.max(fit, 1.2)));
    };
    const markAt = (lt) => { let m = null; for (const x of marks) { if (x.t - MOVE <= lt) m = x; } return m || marks[0] || null; };
    const zReadAt = (lt) => { let z = 0; const N = 10; for (let j = 0; j < N; j++) { z += zMark(markAt(lt - (j / (N - 1)) * 0.6)); } return z / N; };
    // 읽히게 모드인데 볼 곳이 하나도 없으면: 첫 화면에서 가장 큰 글자(제목) 덩어리
    if (readPx && !marks.length) {
      const tx = ((states[0] || {}).texts || []).filter((x) => x.b[1] >= 0 && x.b[1] < vh).sort((x, y) => y.fs * (y.fw / 400) - x.fs * (x.fw / 400));
      if (tx[0]) marks.push({ t: 0, p: ctr(tx[0].b), b: tx[0].b, click: false, look: true });
    }
    const home = readPx && marks.length ? marks[0].p : [vw * 0.62, vh * 0.7];
    const cursorAt = (lt) => {
      let prev = home;
      for (const m of marks) {
        if (lt < m.t - MOVE) return prev;
        if (lt < m.t) { const p = E.inOut(clamp((lt - (m.t - MOVE)) / MOVE)); return [lerp(prev[0], m.p[0], p), lerp(prev[1], m.p[1], p)]; }
        prev = m.p;
      }
      return prev;
    };
    // 확대(사람이 편집한 화면 녹화처럼): 동작마다 들락날락하지 않는다.
    //  · 2.4초 안에 이어지는 동작은 한 '확대 구간'으로 묶어, 한 번 들어가서 머문 채 커서를 따라 옮겨 간다
    //  · 클릭 · 입력이 있는 구간만, 영상(이 창) 전체에서 많아야 maxZooms(기본 2)번 — 나머지는 확대 없이 커서만
    //  · 들어가기 0.8초 · 나오기 0.9초, 화면 이동은 커서보다 살짝 늦게 따라간다(지난 0.5초 커서 위치의 평균)
    const zoomMax = o.zoom === false ? 1 : (o.zoom ?? 1.25);
    const GAP = 2.4, IN = 0.8, OUT = 0.9, HOLD = 0.7;
    const sessions = [];
    for (const m of marks) { const s = sessions[sessions.length - 1]; if (s && m.t - s.b < GAP) { s.b = m.t; s.click = s.click || m.click; s.n++; } else sessions.push({ a: m.t, b: m.t, click: m.click, n: 1 }); }
    const zs = sessions.filter((s) => s.click).sort((p, q) => q.n - p.n).slice(0, o.maxZooms ?? 2).sort((p, q) => p.a - q.a);
    const zoomAt = (lt) => {
      let z = 0;
      for (const s of zs) {
        const a0 = s.a - MOVE - IN, b1 = s.b + HOLD;
        const v = lt < a0 || lt > b1 + OUT ? 0 : lt < s.a - MOVE ? E.inOut(clamp((lt - a0) / IN)) : lt <= b1 ? 1 : 1 - E.inOut(clamp((lt - b1) / OUT));
        z = Math.max(z, v);
      }
      return 1 + (zoomMax - 1) * z;
    };
    const focusAt = (lt) => {   // 시각만으로 정해지는 부드러운 따라가기(렌더 · 되감기에도 같은 값)
      let x = 0, y = 0; const N = 10;
      for (let j = 0; j < N; j++) { const [px, py] = cursorAt(lt - (j / (N - 1)) * 0.5); x += px; y += py; }
      return [x / N, y / N];
    };
    const show = (i, op = 1, ty = 0) => { const im = shots[i]; if (!im) return; im.style.opacity = String(op); im.style.transform = ty ? `translateY(${ty}px)` : ""; };

    return { el: e, update(lt) {
      // 등장: 읽히게 모드(컷 편집 화면)는 바로 — 장면마다 서서히 나타나면 컷 사이가 검게 빈다. o.enter 로 강제
      const p0 = (o.enter ?? !readPx) ? win(lt, at, 0.5, E.out4) : 1;
      e.style.opacity = String(p0); e.style.transform = p0 < 1 ? `translateY(${(1 - p0) * 60}px)` : "";
      shots.forEach((im) => { im.style.opacity = "0"; im.style.transform = ""; });
      clips.forEach((c) => c && (c.cv.style.display = "none"));
      typeWin.style.display = "none";
      // 지금 보여 줄 화면: 마지막으로 일어난 동작의 결과, 전환 중이면 섞어서
      let i = -1; for (let j = 0; j < acts.length; j++) if (lt >= times[j]) i = j;
      let state = i < 0 ? 0 : acts[i].from;
      if (i < 0) show(0);
      else {
        const a = acts[i], t = lt - times[i];
        if (a.do === "record" && clips[i]) {
          const c = clips[i], n = Math.min(c.imgs.length - 1, Math.floor(t * c.c.fps));
          if (t < c.c.sec) { show(a.from); c.cv.style.display = "block"; if (n !== c.last && c.imgs[n] && c.imgs[n].complete && c.imgs[n].naturalWidth) { c.g.drawImage(c.imgs[n], 0, 0, c.cv.width, c.cv.height); c.last = n; } }
          else { show(a.to); state = a.to; }
        } else if (a.do === "scroll" && a.to !== a.from) {
          const p = E.inOut(clamp(t / 0.75)), dy = (a.dy || 0) * k;
          if (Math.abs(dy) < ih * 0.95) { show(a.from, 1, -dy * p); show(a.to, 1, dy - dy * p); }
          else { show(a.from, 1 - p); show(a.to, p); }
          state = p >= 1 ? a.to : a.from;
        } else if (a.do === "type" && a.box && a.to !== a.from) {
          const dur = Math.max(0.4, (a.text || "").length * 0.07), p = clamp(t / dur);
          show(a.from);
          if (p < 1) {
            const [bx, by, bw, bh] = a.box.map((v) => v * k);
            typeWin.style.display = "block"; typeImg.src = shots[a.to].src;
            css(typeWin, { left: bx + "px", top: by + "px", width: bw * p + "px", height: bh + "px" });
            css(typeImg, { left: -bx + "px", top: -by + "px" });
          } else { show(a.from, 1 - clamp((t - dur) / 0.2)); show(a.to, clamp((t - dur) / 0.2)); }
          state = p >= 1 ? a.to : a.from;
        } else {
          const p = clamp((t - 0.12) / 0.2);
          show(a.from, 1 - p); show(a.to, p);
          state = p >= 1 ? a.to : a.from;
        }
      }
      if (urlText && states[state]) urlText.textContent = states[state].url.replace(/^https?:\/\//, "");
      // 빨간 상자(beats do:"표시"): 그 단어부터, 그 화면(state)이 보이는 동안
      if (!reds) reds = redBoxes();
      for (const r of reds) r.e.style.visibility = lt >= r.t && lt < r.end && stateAt(lt) === stateAt(r.t) ? "visible" : "hidden";
      // 커서 · 클릭 물결
      const [cx, cy] = cursorAt(lt);
      cur.style.transform = `translate(${cx * k - 3}px, ${cy * k - 2}px)`;
      let rp = 0; for (const m of marks) if (m.click) { const d = lt - m.t; if (d >= 0 && d < 0.5) { rp = d / 0.5; ripple.style.left = m.p[0] * k - 30 + "px"; ripple.style.top = m.p[1] * k - 30 + "px"; } }
      ripple.style.opacity = String(rp ? 1 - rp : 0); ripple.style.transform = `scale(${0.4 + rp * 1.4})`;
      // 확대: 커서를 중심으로 당겨 들어감 (1배 이상이라 가장자리가 비지 않음)
      const zs1 = zoomAt(lt), [fx, fy] = focusAt(lt);
      if (readPx) {
        // 읽히게: 늘 zRead 배로, 지금 대상을 창 가운데로(가장자리가 비지 않게 가둔다). 클릭 구간은 조금 더(zoom 비율만큼)
        const z = zReadAt(lt) * zs1, vh2 = h - bar;
        // 대상이 창보다 넓으면 왼쪽 끝에 맞춘다(글은 왼쪽부터 읽힌다 — 가운데 맞추면 줄 앞이 잘렸다)
        const mk = markAt(lt), bw = mk && mk.b ? mk.b[2] * k * z : 0;
        const tx0 = bw > w * 0.92 ? 28 - mk.b[0] * k * z : w / 2 - fx * k * z;
        // 화면이 판보다 작으면(전체 보기) 가운데, 크면 가장자리가 비지 않게 가둔다
        const tx = w * z <= w ? (w - w * z) / 2 : clamp(tx0, w - w * z, 0);
        const ty = ih * z <= vh2 ? (vh2 - ih * z) / 2 : clamp(vh2 / 2 - fy * k * z, vh2 - ih * z, 0);
        cam.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`;
        // 커서 · 물결은 확대돼도 원래 크기로
        cur.style.transform += ` scale(${1 / z})`; cur.style.transformOrigin = "0 0";
      } else {
        const z = zs1;
        cam.style.transform = `translate(${fx * k * (1 - z)}px, ${fy * k * (1 - z)}px) scale(${z})`;
      }
      // 단계 배지
      if (o.labels) {
        let lab = null, la = -9; acts.forEach((a, j) => { if (a.label && lt >= times[j] - MOVE) { lab = a.label; la = times[j] - MOVE; } });
        badge.textContent = lab || ""; const bp = lab ? win(lt, la, 0.35, E.back) : 0;
        badge.style.opacity = String(bp); badge.style.transform = `translateY(${(1 - bp) * -14}px)`;
      }
    } };
  }

  // 부품마다 data-part(종류) · data-name(o.name) 을 달아 에디터 레이어 이름으로 쓴다
  const named = (part, fn) => function (...a) {
    const r = fn.apply(this, a); const e = r && r.el;
    if (e && e.dataset && !e.dataset.part) { e.dataset.part = part; const o = a.find((x) => x && typeof x === "object" && !x.root && !x.nodeType && typeof x.name === "string"); if (o) e.dataset.name = o.name; }
    return r;
  };
  const nameIt = (r, n) => { const e = r && (r.el || r); if (e && e.dataset) e.dataset.name = n; return r; };
  const P = { bg, text, counter, shape, pixel, draw, bars, frame, image, particles, ring, versus, list, actor, seq, web };
  for (const k in P) P[k] = named(k, P[k]);
  window.K = { W, H, T, E, win, rand, css, box, el, mix, clamp, lerp, ...P, captions, transition, compose, camera, noise: noise3D, name: nameIt, named };

  // ---------- K.talk: '말로 끌고 가는' 정보 쇼츠 문법 (레퍼런스 스타일 카드의 layout: band · captions: bracket-box) ----------
  //  검정 바탕 · 쇼츠 안전 영역 안의 콘텐츠 판에 화면 · 짤 · 로고, 첫 장면에만 고정 제목, 흰 글씨 자막, 스포트라이트 강조, 장면 안 컷.
  //  효과(튀기 · 날아오기 · 줌)는 없다 — 웃음은 짤 타이밍과 말이 만든다. 색은 콘티 direction(color_caption_bg/fg)을 따른다.
  //  안전 영역(SAFE): 위 UI ~220 · 아래 채널명 · 설명 ~380 · 오른쪽 버튼 줄 x ≳ 940 을 피한다. 판 = x 72~936 · y 380~1300.
  K.talk = (function () {
    const D = (SF.sb && SF.sb.direction) || {};
    const CAP_BG = D.color_caption_bg || "#101010", CAP_FG = D.color_caption_fg || "#f0f0f0", ACC = D.color_accent || T.accent || "#FF2D2D";
    const F = "Pretendard, sans-serif";
    // 배치 숫자: 형식 프리셋(콘티 preset — 사람이 편집한 실제 쇼츠에서 잰 값)이 있으면 그것으로, 없을 때만 안전 영역 기본값.
    //  자막 y · 크기 · 한 줄 글자 수 · 상자, 고정 제목 y, 화면 채움(위아래 띠). 손으로 정한 고정값이 'AI 틀'이 되지 않게(2026-11-02)
    const PR = (SF.sb && SF.sb.preset && SF.sb.preset.layout) || {};
    const PC = PR.captions || {}, PT = PR.title || {}, PF = PR.fill || {};
    const clampY = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const banded = (PF.letterbox ?? 0) > 0.5 && PF.band_top != null;
    const SAFE = { x0: 72, x1: 936, top: 220, bottom: 1540,
      panelTop: banded ? clampY(Math.round(PF.band_top * H), 220, 900) : 380,
      panelBottom: banded ? clampY(Math.round(PF.band_bottom * H), 1000, 1540) : 1300,
      titleY: PT.y != null && (PT.share ?? 0) >= 0.5 ? clampY(Math.round(PT.y * H), 220, 1400) : 240,
      capY: PC.y != null ? clampY(Math.round(PC.y * H - (PC.height || 0.035) * H * 0.6), 240, 1500) : 1340,
      capSize: PC.height ? Math.round(Math.max(36, Math.min(96, PC.height * H * 0.95))) : 56,
      // 한 줄 글자 수는 한국어 쇼츠에서 잰 값 — 라틴 문자는 폭이 절반쯤이라 영어 나레이션이면 두 배(같은 줄 폭)
      capChars: (PC.chars || 14) * ((SF.sb && SF.sb.language === "en") ? 2.1 : 1), capBox: (PC.box ?? 0) >= 0.5, capDark: PC.fg_light != null && PC.fg_light < 0.4,
      captions: PC.share == null || PC.share >= 0.2, title: PT.share == null ? true : PT.share >= 0.5, preset: (SF.sb && SF.sb.preset && SF.sb.preset.name) || null };
    const PW = SAFE.x1 - SAFE.x0, PX = (SAFE.x0 + SAFE.x1) / 2, CY = (SAFE.panelTop + SAFE.panelBottom) / 2, PH = SAFE.panelBottom - SAFE.panelTop;
    const d = (p, x, y, w, h, st = {}, html) => { const e = box(p, { x, y, w, h, style: st }); if (html != null) e.innerHTML = html; return e; };
    const vis = (e, on) => { e.style.visibility = on ? "visible" : "hidden"; };
    const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    /** 웹 녹화 한 장(창 px 1280×800 의 [x0,y0,x1,y1])을 콘텐츠 판 폭에 맞춰. o.full = 화면 폭 가득(안전 영역 무시 — 바탕처럼 쓸 때만) */
    function shot(parent, src, region = [0, 0, 1280, 800], o = {}) {
      const [vx0, vy0, vx1, vy1] = region, X = o.full ? 0 : SAFE.x0, Wd = o.full ? W : PW, k = Wd / (vx1 - vx0);
      const Hh = Math.min(Math.round((vy1 - vy0) * k), o.full ? H : PH), Y = Math.round((o.cy ?? CY) - Hh / 2);
      const clip = d(parent, X, Y, Wd, Hh, { overflow: "hidden", background: "#fff", zIndex: 2 });
      const cam = d(clip, 0, 0, Wd, Hh, { transformOrigin: "0 0" });   // 그림 + 강조를 함께 당기는 판(스포트라이트 확대)
      const img = el("img", "", cam); img.src = src;
      css(img, { position: "absolute", left: `${-vx0 * k}px`, top: `${-vy0 * k}px`, width: `${1280 * k}px`, height: `${800 * k}px` });
      nameIt(clip, o.name || "웹 화면");
      return { el: clip, cam, top: Y, bottom: Y + Hh, left: X, k, at: (vx, vy) => [X + (vx - vx0) * k, Y + (vy - vy0) * k], show: (v) => vis(clip, v), update() {} };
    }
    /** 짤(프레임 요소)을 콘텐츠 판 안에 비율 그대로. ar = 높이/너비, from = 짤 안 시작 초, o.full = 화면 폭 가득 */
    function insert(parent, src, ar, o = {}) {
      const maxH = Math.min(o.maxH ?? PH, PH);
      let w = o.full ? W : PW, h = Math.round(w * ar);
      if (!o.full && h > maxH) { h = maxH; w = Math.round(h / ar); }
      const x = o.full ? 0 : Math.round(PX - w / 2), Y = Math.round((o.cy ?? CY) - h / 2);
      const s = seq(parent, src, { x, y: Y, w, h, fit: o.fit || "cover", at: o.at ?? 0, from: o.from, z: 3, loop: o.loop ?? true });
      nameIt(s.el, o.name || "짤");
      return { ...s, top: Y, bottom: Y + h, show: (v) => vis(s.el, v) };
    }
    /** 실제 로고 · 사진 한 장(판 가운데, 정사각 size) */
    function logo(parent, src, size = 420, o = {}) {
      const e = d(parent, Math.round(PX - size / 2), Math.round((o.cy ?? CY) - size / 2), size, size, { zIndex: 2 });
      const im = el("img", "", e); im.src = src; css(im, { width: "100%", height: "100%", objectFit: "contain" });
      nameIt(e, o.name || "로고");
      return { el: e, show: (v) => vis(e, v), update() {} };
    }
    /** 고정 제목: 기본은 첫 장면에서만(scope: "first") — "all" 이면 끝까지. html 은 강조 낱말을 <b> 로 */
    function title(root, html, o = {}) {
      if (!SAFE.title && !o.force) return { el: null, update() {} };   // 이 형식은 고정 제목을 거의 안 씀(프리셋 title.share)
      const e = d(root, SAFE.x0, SAFE.titleY, PW, null, { textAlign: "center", font: `900 ${o.size ?? 74}px/1.1 ${F}`, color: "#fff", letterSpacing: "-.04em", whiteSpace: "nowrap", zIndex: 60 },
        String(html).replace(/<b>/g, `<span style="color:${ACC}">`).replace(/<\/b>/g, "</span>"));
      nameIt(e, "고정 제목");
      const end = o.scope === "all" ? 1e9 : ((SF.scenes && SF.scenes[0] && SF.scenes[0].end) || 4);
      return { el: e, update: (t) => vis(e, t < end) };
    }
    /** 자막: 흰 글씨 · 상자 없음 · 효과 없음(안전 영역 안 capY). global 에서 update(t) */
    function subs(root, o = {}) {
      if (!SAFE.captions && !o.force) return { el: null, update() {} };   // 이 형식은 나레이션 자막을 거의 안 씀(프리셋 captions.share)
      // 페이지 나누기: 프리셋의 한 줄 글자 수에 맞춰 단어를 묶는다(시간으로 묶으면 길이가 들쭉날쭉)
      const ws = SF.captions || [], pages = [];
      let cur = [], n = 0;
      const lim = o.chars ?? SAFE.capChars;
      for (const w of ws) {
        const len = String(w.text).trim().length;
        if (cur.length && (n + len > lim || w.scene !== cur[0].scene)) { pages.push(cur); cur = []; n = 0; }
        cur.push(w); n += len + 1;
      }
      if (cur.length) pages.push(cur);
      const P = pages.map((p, i) => ({ tokens: p, start: p[0].startMs / 1000, end: (pages[i + 1] ? Math.min(pages[i + 1][0].startMs, p[p.length - 1].endMs + 300) : p[p.length - 1].endMs + 400) / 1000 }));
      const size = o.size ?? SAFE.capSize, box = o.box ?? SAFE.capBox, dark = o.dark ?? SAFE.capDark;
      const e = d(root, SAFE.x0, o.y ?? SAFE.capY, PW, null, { textAlign: "center", zIndex: 60 });
      const span = el("span", "", e);
      css(span, { font: `800 ${size}px/1.3 ${F}`, color: box ? (dark ? "#fff" : "#111") : (dark ? "#111" : "#fff"), padding: box ? "4px 14px" : "0",
        background: box ? (dark ? "#111" : "#fff") : "transparent", boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone", letterSpacing: "-.02em" });
      nameIt(e, "자막");
      let curI = -2;
      return { el: e, update: (t) => { const i = P.findIndex((p) => t >= p.start && t < p.end); if (i !== curI) { curI = i; span.textContent = i < 0 ? "" : P[i].tokens.map((w) => String(w.text).trim()).join(" "); span.style.visibility = i < 0 ? "hidden" : "visible"; } } };
    }
    /** 괄호 자막: 그림 위쪽 가장자리에 걸친다. [from, to) 동안 그냥 보임 */
    function cap(parent, top, text, from = 0, to = 99) {
      const e = d(parent, SAFE.x0, top - 44, PW, 88, { display: "flex", alignItems: "center", justifyContent: "center", zIndex: 7, visibility: "hidden" },
        `<span style="background:${CAP_BG};color:${CAP_FG};font:900 54px/76px ${F};padding:0 16px;letter-spacing:-.03em;white-space:nowrap">${esc(text)}</span>`);
      nameIt(e, `괄호 자막 · ${text}`);
      return { el: e, update: (lt) => vis(e, lt >= from && lt < to) };
    }
    /** 작은 흰 글씨(상자 없음) — 꼭 필요한 한두 곳만 */
    function label(parent, text, y, from = 0, to = 99, o = {}) {
      const e = d(parent, SAFE.x0, y, PW, null, { textAlign: "center", font: `700 ${o.size ?? 44}px/1.2 ${F}`, color: o.color || "#fff", zIndex: 7, visibility: "hidden" }, esc(text));
      nameIt(e, `글씨 · ${text}`);
      return { el: e, update: (lt) => vis(e, lt >= from && lt < to) };
    }
    /** 강조(기본): 스포트라이트 — 웹 화면 s 의 창 px 상자 [x, y, w, h] 밖을 어둡게 하고 그 자리로 살짝 당겨 확대(o.zoom, 기본 1.12).
     *  빨간 네모는 원래 그림에 있던 표시와 헷갈려서 기본에서 뺐다(2026-11-02 사용자 지적) */
    function spot(parent, s, [bx, by, bw, bh], from, to = 99, o = {}) {
      const pad = o.pad ?? 10, z = o.zoom ?? 1.12;
      const [ax, ay] = s.at(bx, by);
      const lx = ax - s.left, ly = ay - s.top;
      const e = d(s.cam || s.el, Math.round(lx - pad), Math.round(ly - pad), Math.round(bw * s.k + pad * 2), Math.round(bh * s.k + pad * 2),
        { boxShadow: "0 0 0 4000px rgba(0,0,0,.6)", borderRadius: "8px", zIndex: 5, visibility: "hidden", pointerEvents: "none" });
      nameIt(e, "스포트라이트");
      const ox = lx + bw * s.k / 2, oy = ly + bh * s.k / 2;   // 강조 자리 가운데(판 좌표)를 중심으로 확대
      return { el: e, update: (lt) => {
        const on = lt >= from && lt < to && s.el.style.visibility !== "hidden";
        vis(e, on);
        const p = on ? E.out(clamp((lt - from) / 0.35)) : 0, sc = 1 + (z - 1) * p;
        if (s.cam) s.cam.style.transform = `translate(${ox * (1 - sc)}px, ${oy * (1 - sc)}px) scale(${sc})`;
      } };
    }
    /** (예전 이름) 빨간 네모 → 스포트라이트로 그린다. 정말 빨간 테두리가 필요하면 o.red = true */
    function red(parent, s, rect, from, to = 99, pad = 6, o = {}) {
      if (!o.red) return spot(parent, s, rect, from, to, { pad });
      const [x, y] = s.at(rect[0], rect[1]);
      const e = d(parent, x - pad, y - pad, rect[2] * s.k + pad * 2, rect[3] * s.k + pad * 2, { border: `5px solid ${ACC}`, zIndex: 5, visibility: "hidden" });
      nameIt(e, "빨간 네모");
      return { el: e, update: (lt) => vis(e, lt >= from && lt < to && s.el.style.visibility !== "hidden") };
    }
    /** 화살표 주석: "← 인간용" 같은 상자 글씨 (x 는 판 안으로 맞춤) */
    function note(parent, x, y, text, from, to = 99) {
      const e = d(parent, clamp(x, SAFE.x0, SAFE.x1 - 200), y, null, 48, { background: CAP_BG, color: CAP_FG, font: `800 34px/48px ${F}`, padding: "0 10px", whiteSpace: "nowrap", zIndex: 6, visibility: "hidden" }, esc(text));
      nameIt(e, `주석 · ${text}`);
      return { el: e, update: (lt) => vis(e, lt >= from && lt < to) };
    }
    /** 장면 안 컷: [{ at, items:[{show(v), update?}] }, …] → 지금 구간의 것만 보이게(짤 프레임도 넘긴다) */
    function cuts(list) {
      return (lt) => { let cur = 0; list.forEach((c, i) => { if (lt >= c.at) cur = i; }); list.forEach((c, i) => c.items.forEach((it) => { it.show(i === cur); if (i === cur && it.update) it.update(lt); })); };
    }
    /** 콘티 beats 실행: k.beats(c, main) — 장면의 scenes[i].beats 를 들리는 단어에 맞춰 화면에 옮긴다(화면 코드에서 손으로 옮기지 않게).
     *  재료(src 있음) = 그 재료로 바꿔 hold 초(기본 1.4, 다음 재료 beat 이 먼저 오면 거기까지) 보여 준 뒤 main 으로 돌아옴.
     *    src 가 그림(.png .jpg .webp)이면 판을 가득 채우고, 폴더(프레임 요소 · 짤)면 K.seq. 같은 재료가 장면 끝까지 가려면 hold: 99
     *  글자 = what 을 판 가운데 크게 1.2초(사람 편집의 '핵심 단어 박기'). 확대 · 표시는 K.web(read · focus) · k.red 몫이라 여기선 시각만 돌려준다.
     *  반환: update(lt) 와 times(beat 마다 시각) — times 는 K.web focus 등에 넘긴다 */
    function beats(c, main, o = {}) {
      const list = ((c.scene && c.scene.beats) || []).map((b) => ({ ...b, t: c.cue(b.at) }));
      const mats = list.filter((b) => b.do === "재료" && b.src);
      const items = mats.map((b, j) => {
        const nextT = j + 1 < mats.length ? mats[j + 1].t : 99, end = Math.min(nextT, b.t + (b.hold ?? o.hold ?? 1.4));
        let part;
        if (/\.(png|jpe?g|webp|gif)$/i.test(b.src)) {
          const e = d(c.root, SAFE.x0, SAFE.panelTop, PW, PH, { overflow: "hidden", zIndex: 4, visibility: "hidden", background: "#000" });
          const im = el("img", "", e); im.src = b.src; css(im, { width: "100%", height: "100%", objectFit: b.fit || "cover" });
          nameIt(e, `재료 · ${b.what || b.screen || ""}`);
          part = { el: e, update() {} };
        } else {
          part = insert(c.root, b.src, b.ar ?? PH / PW, { at: b.t, name: `재료 · ${b.what || b.screen || ""}` });
          part.el.style.zIndex = "4";
        }
        return { b, part, end };
      });
      const words = list.filter((b) => b.do === "글자" && b.what).map((b) => {
        const e = d(c.root, SAFE.x0, Math.round(CY - 90), PW, 180, { display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", zIndex: 7, visibility: "hidden",
          font: `900 ${o.wordSize ?? 104}px/1.1 ${F}`, color: "#fff", WebkitTextStroke: "10px #000", paintOrder: "stroke fill", letterSpacing: "-.03em" }, esc(b.what));
        nameIt(e, `글자 · ${b.what}`);
        return { b, e };
      });
      return { times: list.map((b) => b.t), list, update(lt) {
        let on = null;
        for (const it of items) { const v = lt >= it.b.t && lt < it.end; vis(it.part.el, v); if (v) { on = it; if (it.part.update) it.part.update(lt); } }
        if (main && main.el) vis(main.el, !on);
        if (main && main.update && !on) main.update(lt);
        for (const w of words) vis(w.e, lt >= w.b.t && lt < w.b.t + (w.b.hold ?? 1.2));
      } };
    }
    /** 참고 쇼츠의 화면 문법(콘티 grammar — scripts/previz.py grammar 가 스타일 카드에서 잰 값)으로 글자 띠를 그린다.
     *  g = { y(가운데) · h(글자 높이, 화면 비율) · box(흰 상자) · bg · fg · align }. 위치 · 크기 · 색을 손으로 정하지 않는다(미리 보기와 최종이 같은 부품) */
    const G = (SF.sb && SF.sb.grammar) || {};
    function gtext(parent, g, text, from = 0, to = 99, o = {}) {
      if (!g || !text) return { el: null, update() {} };
      // 잰 높이(g.h)는 글자 줄 높이 — 0.82배로 그렸더니 참고 쇼츠보다 작고 가늘었다(2026-11-02 미리 보기 비교). 1배 · 아주 굵게
      const fs = Math.round(g.h * H * 1.0), y = Math.round(g.y * H - (g.h * H) / 2);
      const left = g.align === "left";
      const e = d(parent, left ? Math.round(W * 0.06) : 0, y, left ? null : W, Math.round(g.h * H), { textAlign: left ? "left" : "center", zIndex: o.z ?? 30, visibility: "hidden" });
      const sp = el("span", "", e);
      css(sp, { font: `900 ${fs}px/1.1 ${F}`, color: g.fg || "#f0f0f0", letterSpacing: "-.03em", whiteSpace: "pre",
        ...(g.box ? { background: g.bg || "#f0f0f0", padding: `${Math.round(fs * 0.08)}px ${Math.round(fs * 0.3)}px` } : { textShadow: "0 0 6px rgba(0,0,0,.85), 0 2px 3px rgba(0,0,0,.9)" }) });
      sp.textContent = text;
      nameIt(e, o.name || `글자 · ${text}`);
      return { el: e, update: (lt) => vis(e, lt >= from && lt < to) };
    }
    const gram = {
      G,
      /** 영상 칸(참고 쇼츠의 영상 비율 · 자리). 없으면 SAFE 판 */
      box: () => (G.content ? { x: 0, y: Math.round(G.content.y0 * H), w: W, h: Math.round((G.content.y1 - G.content.y0) * H) } : { x: SAFE.x0, y: SAFE.panelTop, w: PW, h: PH }),
      /** 고정 제목(여러 줄은 ' / ' 로 나눔) · 고정 펀치라인 — 영상 내내 */
      title: (root, text) => { if (!G.title || !text) return { update() {} }; const ls = String(text).split(/\s*\/\s*|\n/); const ps = ls.map((t, i) => gtext(root, { ...G.title, y: G.title.y + i * (G.title.gap || G.title.h * 1.05) }, t, 0, 9999, { name: "고정 제목" })); return { update: (t) => ps.forEach((p) => p.update(t)) }; },
      punch: (root, text) => gtext(root, G.punch, text, 0, 9999, { name: "고정 펀치라인", z: 40 }),
      /** 장면마다: 상황 괄호 · 반응 자막 · 속마음 괄호 */
      tag: (c, text) => gtext(c.root, G.tag, text && `(${text})`, 0, 99, { name: "상황" }),
      sub: (c, text, from = 0.25, to = 99) => gtext(c.root, G.subs, text, from, to, { name: "반응 자막" }),
      thought: (c, text, from = 0, to = 99) => gtext(c.root, G.thought, text && `(${text})`, from, to, { name: "속마음" }),
    };
    /** 검정 바탕 (장면마다 첫 줄) */
    const bg = (parent) => { const e = d(parent, 0, 0, W, H, { background: D.color_bg || "#000" }); nameIt(e, "바탕"); return e; };
    return { SAFE, shot, insert, logo, title, subs, cap, label, spot, red, note, cuts, beats, gram, bg, CY };
  })();

  // ---------- K.pro: 프로 모션그래픽 기본 부품 (에디토리얼 타이포 · 원근 카드 · 지수 감속). 기본은 이것부터 ----------
  K.pro = (function () {
    const ACC = "#4F8CFF", INK = "#F5F5F7", DIM = "#86868B", BG = "#050507";
    const ex = (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p));           // 지수 감속 (애플 키노트 계열)
    const io = (p) => (p < .5 ? 16 * p ** 5 : 1 - Math.pow(-2 * p + 2, 5) / 2);
    const w = (lt, a, d, f = ex) => f(K.clamp((lt - a) / d));
    const F = "Pretendard, sans-serif";

  // 'AI 티'가 나는 장식(빛번짐 무대 · 비네트 · 흐림 등장 · 원근 카드 · 반사광)은 기본에서 뺐다 — 2026-11-02 데모가 "AI 티가 확 난다"는 평가.
  //  기본은 담백하게: 단색 바탕 · 짧은 이동/컷 등장 · 평평한 카드. 레퍼런스가 그런 화면일 때만 o.glow · o.blur · o.tilt 로 켠다(look_check.py 가 잰다).
  // 무대: 기본 단색. o.glow = 위에서 떨어지는 빛 + 비네트(예전 키노트 룩)
    const stage = (c, hue = ACC, o = {}) => {
      K.css(c.root, { background: o.bg ?? BG });
      if (!o.glow) return { el: c.root, update() {} };
      K.css(c.root, { perspective: "1600px" });
      const light = K.box(c.root, { x: -300, y: -500, w: 1680, h: 1500, style: { background: `radial-gradient(closest-side, ${hue}26, transparent 70%)`, filter: "blur(30px)" } });
      K.box(c.root, { x: 0, y: 0, w: 1080, h: 1920, style: { background: "radial-gradient(120% 80% at 50% 40%, transparent 55%, rgba(0,0,0,.7))", pointerEvents: "none", zIndex: 30 } });
      return { el: light, update(lt) { light.style.transform = `translate(${Math.sin(lt * .4) * 40}px, ${lt * 12}px)`; } };
    };
  // 글자: 줄마다 아래에서 짧게 올라옴(0.35초). o.blur = 흐림이 걷히는 등장 · o.cut = 그냥 나타남
    const type = (c, str, o) => {
      const e = K.box(c.root, { x: o.x ?? 90, y: o.y, w: o.w ?? 900, style: { font: `${o.weight ?? 700} ${o.size}px/${o.lh ?? 1.04} ${F}`, letterSpacing: (o.ls ?? -0.035) + "em", color: o.color ?? INK, textAlign: o.align ?? "left", zIndex: 10 } });
      const lines = str.split("\n").map((t) => { const m = K.el("div", "", e); m.style.overflow = "hidden"; m.style.paddingBottom = ".06em"; const s = K.el("div", "", m); s.innerHTML = t; return s; });
      return { el: e, update(lt) {
        lines.forEach((s, k) => {
          const at = (o.at ?? 0) + k * .06;
          if (o.cut) { s.style.visibility = lt >= at ? "visible" : "hidden"; return; }
          const p = w(lt, at, o.dur ?? (o.blur ? .9 : .35));
          s.style.transform = `translateY(${(1 - p) * 105}%)`;
          if (o.blur) s.style.filter = `blur(${(1 - p) * 8}px)`;
        });
        if (o.out != null) e.style.opacity = String(1 - w(lt, o.out, .4, io));
      } };
    };
    const rule = (c, x, y, len, at) => { const r = K.box(c.root, { x, y, w: len, h: 2, style: { background: "rgba(255,255,255,.22)", transformOrigin: "0 50%", zIndex: 10 } }); return { el: r, update(lt) { r.style.transform = `scaleX(${w(lt, at, .5)})`; } }; };
    const label = (c, txt, x, y, at) => type(c, txt, { x, y, size: 30, weight: 600, color: DIM, ls: .02, at, dur: .3 });
  // 실제 화면 캡처 카드: 기본은 평평하게 · 짧게 올라옴 · 얇은 테두리. o.tilt = 원근 회전 + 반사광(예전 룩)
    const card = (c, src, o) => {
      const W0 = o.w ?? 780, H0 = o.h ?? 560;
      const box = K.box(c.root, { x: o.x ?? 150, y: o.y ?? 640, w: W0, h: H0, style: { zIndex: 5, ...(o.tilt ? { transformStyle: "preserve-3d" } : {}) } });
      const face = K.box(box, { x: 0, y: 0, w: W0, h: H0, style: { borderRadius: o.radius ?? "14px", overflow: "hidden", background: "#111",
        boxShadow: o.tilt ? "0 60px 120px -30px rgba(0,0,0,.9), 0 0 0 1px rgba(255,255,255,.08)" : "0 0 0 1px rgba(255,255,255,.14)" } });
      const img = K.el("img", "", face); img.src = src; K.css(img, { width: "100%", display: "block" });
      const shine = o.tilt ? K.box(face, { x: 0, y: 0, w: W0, h: H0, style: { background: "linear-gradient(115deg, transparent 35%, rgba(255,255,255,.14) 50%, transparent 65%)" } }) : null;
      return { el: box, face, img, update(lt) {
        const at = o.at ?? 0;
        if (o.tilt) {
          const p = w(lt, at, 1.2);
          box.style.opacity = String(K.clamp(p * 1.4));
          box.style.transform = `translateY(${(1 - p) * 180}px) rotateX(${12 - p * 6}deg) rotateY(${(o.ry ?? -16) * (1 - p * .4) + Math.sin(lt * .5) * 2}deg) scale(${.9 + p * .1})`;
          shine.style.transform = `translateX(${-800 + w(lt, at + .5, 1.6, io) * 1600}px)`;
        } else {
          const p = w(lt, at, .35);
          box.style.opacity = String(K.clamp(p * 2)); box.style.transform = `translateY(${(1 - p) * 40}px)`;
        }
        if (o.scroll) img.style.transform = `translateY(${-Math.max(0, lt - 1) * o.scroll}px)`;
      } };
    };
  // 아주 큰 숫자 · 단어: 기본은 짧게 올라옴. o.blur = 흐림이 걷히며 커짐(예전 룩)
    const big = (c, txt, o) => {
      const e = K.box(c.root, { x: o.x ?? 80, y: o.y, w: o.w ?? 920, style: { font: `800 ${o.size}px/.9 ${F}`, letterSpacing: "-.06em", color: o.color ?? INK, textAlign: o.align ?? "left", zIndex: 10 } });
      e.innerHTML = txt;
      return { el: e, update(lt) {
        const p = w(lt, o.at ?? 0, o.blur ? 1.1 : .35); e.style.opacity = String(o.blur ? p : K.clamp(p * 2));
        e.style.transform = `translateY(${(1 - p) * (o.blur ? 60 : 24)}px)${o.blur ? ` scale(${1.06 - .06 * p})` : ""}`;
        if (o.blur) e.style.filter = `blur(${(1 - p) * 14}px)`;
      } };
    };


    const N = K.named;
    return { ACC, INK, DIM, BG, ex, io, w, F, stage: N("stage", stage), type: N("type", type), rule: N("rule", rule), label: N("label", label), card: N("card", card), big: N("big", big) };
  })();
})();
