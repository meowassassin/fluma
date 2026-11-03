/* 템플릿 "Overlay" (HyperFrames) — 실제 장면 위 자막 한 줄 + 숫자 하나 + 감정 (분석 2026-10-26).
 * Remotion 판(2026-10-28 커밋 31566d8)을 그대로 옮겼다: 생성 배경·장면 전환·헤드라인·큰 숫자·브라우저 프레임·칩·파형·사진·단어 자막.
 * 화면은 draw(t) 하나가 시간 t 로만 정한다 (SFLib.mount 가 GSAP 타임라인에 묶음).
 */
(function () {
  const { clamp, lerp, prog, ease, noise3D, mix, rotateHue, el, esc, fit, captionPages, mount } = window.SFLib;
  const { sb, tokens: T, scenes, captions, duration } = window.SF;
  const root = document.getElementById("root");
  const W = 1080, H = 1920, TR = 0.4;               // 전환 길이(초): 다음 장면 시작부터 겹친다 → 음성과 화면 시작이 맞는다
  const accent = T.color.accent;
  const has = (p) => !!p && (window.SF.assets || []).includes(p);
  const TRANS = (T.transitions && T.transitions.length ? T.transitions : ["slide-up", "wipe", "slide-left", "iris", "fade"]);

  // ---------- 장면 만들기 ----------
  const S = scenes.map((sc, i) => {
    const s = sb.scenes[i], v = s.visual || {};
    const node = el("div", "scene", root); node.style.zIndex = String(10 + i);
    const asset = v.asset && has(v.asset) ? v.asset : null;
    const isPhoto = (v.kind === "still" || v.kind === "footage") && asset;
    const hasValue = (v.kind === "number" || v.kind === "price_tag") && v.primary;
    const isHero = !hasValue && !isPhoto && !["screenshot", "list", "compare", "audio_demo"].includes(v.kind);
    const o = { sc, s, v, node, isPhoto, hasValue, isHero, seed: `${sb.id}-${i}` };

    if (isPhoto) {
      o.photo = el("div", "photo", node);
      o.media = /\.(mp4|mov|webm)$/.test(asset)
        ? Object.assign(el("video", "clip", o.photo), { src: asset, muted: true })
        : Object.assign(el("img", "", o.photo), { src: asset });
      if (o.media.tagName === "VIDEO") { o.media.setAttribute("data-start", sc.start); o.media.setAttribute("data-duration", sc.sec + TR); }
      el("div", "scrim", o.photo);
    } else {
      o.mesh = el("div", "mesh", node);
      const blobs = el("div", "blobs", o.mesh);
      const pal = [mix(T.color.bg, accent, 0.55), accent, rotateHue(accent, 38), mix(T.color.bg, rotateHue(accent, -30), 0.3)];
      o.blobs = pal.map((c, k) => { const b = el("div", "blob", blobs); b.style.background = c; b.style.opacity = k === 1 ? 0.55 : 0.75; return b; });
      const beams = el("div", "beams", o.mesh);
      o.beams = [0, 1].map((k) => { const b = el("div", "beam", beams); b.style.width = 220 + k * 120 + "px"; return b; });
      o.dots = el("div", "dots", o.mesh);
      el("div", "vignette", o.mesh);
      const wm = (v.primary ?? sb.hook_number ?? "").toString();
      if (wm) { o.wm = el("div", "watermark", node); o.wm.textContent = `${wm}  ${wm}  ${wm}  ${wm}`; }
    }

    if (hasValue) {
      o.num = el("div", "bignum", node);
      o.numV = el("div", "v", o.num);
      o.numV.style.color = v.emphasis === "good" ? T.color.good : v.emphasis === "bad" ? T.color.bad : accent;
      if (v.secondary) { o.numSub = el("div", "sub", o.num); o.numSub.textContent = v.secondary; }
    }
    if (v.kind === "screenshot") {
      const b = o.browser = el("div", "browser", node);
      const bar = el("div", "bar", b);
      ["#FF5F57", "#FEBC2E", "#28C840"].forEach((c) => (el("span", "dot", bar).style.background = c));
      el("div", "url", bar, `🔒 ${esc((v.secondary || v.primary || "example.com").toLowerCase().replace(/\s+/g, ""))}`);
      const page = el("div", "page", b);
      if (asset) o.shot = Object.assign(el("img", "", page), { src: asset });
      else {
        const m = el("div", "mock", page); m.style.background = `linear-gradient(160deg, #fff, ${accent}18)`;
        el("div", "nm", m).textContent = v.primary || "";
        el("div", "ln", m).style.width = "520px"; el("div", "ln", m).style.width = "380px";
        el("div", "cta", m).textContent = "무료로 시작";
      }
    }
    if ((v.kind === "list" || v.kind === "compare") && (v.items || []).length) {
      o.chips = el("div", "chips", node);
      o.chipEls = v.items.slice(0, 5).map((it, k) => { const c = el("div", "chip" + (k === 0 ? " first" : ""), o.chips); c.textContent = it; return c; });
    }
    if (v.kind === "audio_demo") {
      const items = v.items && v.items.length ? v.items : [v.primary || "샘플"];
      o.wave = el("div", "wave", node);
      o.rows = items.map((label, k) => {
        const r = el("div", "row", o.wave);
        const hd = el("div", "hd", r, `<span>${esc(label)}</span><span></span>`);
        const bars = el("div", "bars", r);
        const bs = Array.from({ length: 36 }, (_, b) => el("i", "", bars));
        return { r, st: hd.lastChild, bs, k };
      });
    }

    // 헤드라인 (scene.caption). 작성자가 줄을 나눴으면 그 줄을 지킨다.
    o.head = el("div", "headline", node);
    const lines = (s.caption || "").split("\n").filter(Boolean).slice(0, isHero ? 3 : 2);
    o.lines = lines.map((ln, k) => {
      const wrap = el("div", "line", o.head);
      const txt = el("span", "txt", wrap); txt.textContent = ln;
      const under = k === lines.length - 1 ? el("span", "under", txt) : null;
      if (under) txt.insertBefore(under, txt.firstChild);
      return { txt, under };
    });
    if ((v.kind === "still" || v.kind === "footage") && !asset && v.asset) el("div", "missing", node).textContent = "에셋 필요 · " + v.asset;
    return o;
  });

  // 필름 그레인 (전체에 한 장) — 2프레임마다 시드를 바꾼다
  const grain = el("div", "grain", root);
  grain.style.zIndex = "90";
  grain.innerHTML = `<svg width="100%" height="100%"><filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="0" stitchTiles="stitch"/></filter><rect width="100%" height="100%" filter="url(#g)"/></svg>`;
  const turb = grain.querySelector("feTurbulence");

  // 단어 자막
  const C = T.captions || {};
  const capY = C.y ?? 1330, capSize = C.size ?? 76, capW = W * (C.widthRatio ?? 0.86);
  const capLayer = el("div", "caps", root); capLayer.style.top = capY + "px"; capLayer.style.zIndex = "80";
  const pages = captionPages(captions, C.combineMs ?? 900).map((p) => {
    const pg = el("span", "pg", capLayer);
    p.ws = p.tokens.map((w) => { const s = el("span", "w", pg); s.textContent = w.text; return s; });
    p.el = pg; pg.style.display = "none";
    return p;
  });

  // 고정 요소
  if (sb.badge) { const b = el("div", "badge", root); b.textContent = sb.badge; b.style.zIndex = "85"; }
  if (sb.brand) { const b = el("div", "brand", root, `<i></i>${esc(sb.brand)}`); b.style.zIndex = "85"; }
  let disc = null;
  if (sb.format === "ad") { disc = el("div", "disclaimer", root); disc.textContent = "※ 매출·수익은 상권·입지·매장 상황에 따라 다를 수 있습니다"; disc.style.zIndex = "85"; }
  const tb = T.signature && T.signature.time_bar !== false ? el("div", "timebar", root, "<i></i>") : null;
  if (tb) tb.style.zIndex = "95";

  // ---------- 그리기 ----------
  const countUp = (value, p) => {
    const m = value.match(/(\d[\d,]*(?:\.\d+)?)/); if (!m) return value;
    const raw = m[1], n = Number(raw.replace(/,/g, "")), dec = (raw.split(".")[1] || "").length;
    const cur = (n * p).toFixed(dec);
    return value.replace(raw, raw.includes(",") ? Number(cur).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : cur);
  };

  function enter(o, i, t) {
    // 장면 i 는 [start, end + TR) 동안 보인다. 들어올 때 TR 초 동안 전환.
    const { start, end } = o.sc; const last = i === S.length - 1;
    const visible = t >= start - 1e-6 && (last ? t <= end + 1e-6 : t < end + TR);
    o.node.style.display = visible ? "block" : "none";
    if (!visible) return false;
    const p = i === 0 ? 1 : ease.outCubic(prog(t, start, start + TR));
    const kind = TRANS[(i - 1 + TRANS.length) % TRANS.length];
    const st = o.node.style; st.transform = ""; st.clipPath = ""; st.opacity = "1";
    if (p < 1) {
      if (kind === "slide-up") st.transform = `translateY(${(1 - p) * 100}%)`;
      else if (kind === "slide-left") st.transform = `translateX(${(1 - p) * 100}%)`;
      else if (kind === "wipe") st.clipPath = `inset(${(1 - p) * 100}% ${(1 - p) * 100}% 0 0)`;
      else if (kind === "iris") st.clipPath = `circle(${p * 120}% at 50% 50%)`;
      else st.opacity = String(p);
    }
    return true;
  }

  function drawScene(o, t) {
    const lt = t - o.sc.start, dur = o.sc.sec;
    if (o.mesh) {
      const tt = (t * 0.1) + o.sc.index * 0.3;
      o.blobs.forEach((b, k) => {
        const nx = noise3D(`${o.seed}-x${k}`, k * 1.7, tt, 0), ny = noise3D(`${o.seed}-y${k}`, k * 2.3, 0, tt), ns = noise3D(`${o.seed}-s${k}`, tt, k, 0);
        const size = W * (0.6 + 0.2 * ns);
        Object.assign(b.style, { width: size + "px", height: size + "px", left: W * (0.5 + 0.5 * nx) - size / 2 + "px", top: H * (0.12 + k * 0.25 + 0.1 * ny) - size / 2 + "px" });
      });
      const f = t * 30;
      o.beams.forEach((b, k) => (b.style.left = ((f * (1.4 + k * 0.6) + k * 700) % (W * 2.2)) - W * 0.6 + "px"));
      o.dots.style.backgroundPosition = `0 ${-((f * 0.4) % 36)}px`;
      if (o.wm) o.wm.style.transform = `translate(${-((f * 1.2) % (W * 1.5))}px, -50%) rotate(-8deg)`;
    }
    if (o.photo) {
      const p = clamp(lt / (dur + TR)), m = o.v.motion || "kenburns_in";
      const sc = m === "kenburns_in" ? 1.02 + p * 0.1 : m === "kenburns_out" ? 1.12 - p * 0.1 : 1.06;
      const tx = m === "pan_left" ? -p * 60 : m === "pan_right" ? p * 60 : 0;
      o.media.style.transform = `scale(${sc}) translateX(${tx}px)`;
    }
    if (o.num) {
      const s = ease.outBack(clamp(lt / 0.45), 1.6);
      const size = fit(o.numV, W * 0.84, (T.font.number_px || 160) * 1.6, 80);
      o.numV.textContent = countUp(o.v.primary, ease.outCubic(clamp(lt / 0.6)));
      o.numV.style.fontSize = size + "px";
      o.numV.style.transform = `scale(${lerp(1.6, 1, clamp(s))}) rotate(${(1 - clamp(s)) * -6}deg)`;
      o.numV.style.opacity = String(clamp(lt / 0.15));
      o.numV.style.textShadow = `0 10px 0 rgba(0,0,0,.25), 0 0 60px ${o.numV.style.color}55`;
      if (o.numSub) o.numSub.style.opacity = String(prog(lt, 0.27, 0.53));
    }
    if (o.browser) {
      const s = ease.outCubic(clamp(lt / 0.6));
      o.browser.style.transform = `perspective(1600px) rotateX(${(1 - s) * 18}deg) translateY(${(1 - s) * 140}px) scale(${0.92 + s * 0.08})`;
      o.browser.style.opacity = String(s);
      if (o.shot) o.shot.style.transform = `translateY(${-260 * clamp(lt / (dur + TR))}px)`;
    }
    if (o.chipEls) o.chipEls.forEach((c, k) => {
      const s = ease.outBack(clamp((lt - 0.13 - k * 0.17) / 0.4), 1.2);
      c.style.transform = `translateX(${(1 - s) * (k % 2 ? 300 : -300)}px)`; c.style.opacity = String(clamp(s));
    });
    if (o.rows) {
      const per = dur / o.rows.length, active = Math.min(o.rows.length - 1, Math.floor(lt / per));
      o.rows.forEach((r) => {
        const on = r.k === active; r.r.classList.toggle("on", on); r.st.textContent = on ? "▶ 재생 중" : "· 들음";
        r.st.style.color = on ? accent : ""; const local = (lt - r.k * per) * 30;
        r.bs.forEach((b, i) => {
          const seed = Math.sin((i + 1) * 12.9898 + r.k * 78.233) * 43758.5453, base = 0.25 + (seed - Math.floor(seed)) * 0.75;
          const pulse = on ? 0.6 + 0.4 * Math.abs(Math.sin((local + i * 3) / 4)) : 0.35;
          b.style.height = Math.max(6, base * pulse * 64) + "px"; b.style.background = on ? accent : ""; b.style.opacity = on ? 1 : 0.5;
        });
      });
    }
    // 헤드라인
    const maxPx = o.isHero ? 150 : 96, boxW = W * (o.isHero ? 0.88 : 0.84);
    let size = maxPx;
    o.lines.forEach((l) => (size = Math.min(size, fit(l.txt, boxW, maxPx, 40))));
    o.lines.forEach((l, k) => {
      l.txt.style.fontSize = size + "px";
      const s = ease.outBack(clamp((lt - k * 0.13) / 0.5), 1.4);
      l.txt.style.transform = `translateY(${(1 - clamp(s, 0, 1.2)) * 110}%)`;
      if (l.under) {
        Object.assign(l.under.style, { bottom: size * 0.06 + "px", height: size * 0.3 + "px" });
        l.under.style.transform = `scaleX(${ease.outCubic(prog(lt, 0.27 + k * 0.13, 0.67 + k * 0.13))})`;
      }
    });
    const y = o.isHero ? 560 + (700 - o.lines.length * size * 1.15) / 2 : 250;
    o.head.style.top = y + "px";
  }

  function draw(t) {
    S.forEach((o, i) => { if (enter(o, i, t)) drawScene(o, t); });
    turb.setAttribute("seed", String(Math.floor(t * 15) % 8));
    // 단어 자막
    const ms = t * 1000;
    pages.forEach((p) => {
      const on = t >= p.start && t < p.end;
      p.el.style.display = on ? "inline-block" : "none";
      if (!on) return;
      const size = Math.min(capSize, fit(p.el, capW, capSize, 30));
      p.el.style.fontSize = size + "px";
      const e = clamp((t - p.start) / 0.17);
      p.el.style.transform = `translateY(${lerp(36, 0, e)}px) scale(${lerp(0.86, 1, e)})`;
      p.tokens.forEach((w, k) => {
        const active = w.startMs <= ms && w.endMs > ms;
        const pop = active ? ease.outBack(clamp((ms - w.startMs) / 200), 2) : 0;
        p.ws[k].style.color = active ? (C.highlight || accent) : "";
        p.ws[k].style.transform = `scale(${1 + clamp(pop, 0, 1.2) * 0.08})`;
      });
    });
    if (tb) tb.firstChild.style.width = (1 - clamp(t / duration)) * 100 + "%";
    if (disc) disc.style.display = t >= duration - 3 ? "block" : "none";
  }

  mount(draw);
})();
