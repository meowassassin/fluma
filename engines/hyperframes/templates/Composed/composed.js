/* Composed: 장면마다 두 층을 그린다.
 *  1) code 노드 — compositions/<id>/scene.js 가 정의한 window.FLUMA_SCENE.scenes[i] (에이전트가 짠 코드 연출)
 *  2) 데이터 노드 — compositions/<id>/graph.js 의 window.FLUMA_GRAPH (장면 설계도 scenes/<id>.scene.json 을 컴파일한 것)
 *     글자 · 도형 · 사진 · 올린 영상 · 레이어 요소 · 대역 상자를 키프레임(위치 · 크기 · 회전 · 투명도 · 이징)으로 움직인다.
 * 둘 다 없으면(기획 · 콘티 단계) '콘티 미리보기'. scene.js · graph.js 는 어댑터가 이 파일 앞에 붙인다. */
(function () {
  const spec = window.FLUMA_SCENE;
  const G = window.FLUMA_GRAPH;
  const ROLE = { hook: "훅", step: "단계", reveal: "공개", payoff: "결론", verdict: "결론", outro: "맺음", cta: "행동", problem: "고민", benefit: "이점", proof: "증거", compare: "비교", context: "맥락" };
  const preview = (c) => {   // 화면 구성 전: 콘티 글자 (파일 경로 같은 내부 사정은 화면에 쓰지 않는다)
    const sc = SF.sb.scenes[c.i] || {};
    const b = K.bg(c.root, { type: "grid" });
    const tag = K.text(c.root, `장면 ${c.i + 1} · ${ROLE[sc.role] || sc.role || ""} · 콘티 미리보기`, { y: 520, size: 34, color: "rgba(255,255,255,.55)" });
    const t = K.text(c.root, sc.caption || "", { y: 760, size: 72 });
    c.auto(b, tag, t); return null;
  };

  // ---------- 이징 (GSAP 이름과 같게 — 설계도 · 움직임 레시피와 통일) ----------
  const EASE = {
    linear: (p) => p,
    "sine.inOut": (p) => -(Math.cos(Math.PI * p) - 1) / 2,
    "power2.in": (p) => p * p,
    "power2.out": (p) => 1 - (1 - p) * (1 - p),
    "power2.inOut": (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2),
    "power3.out": (p) => 1 - Math.pow(1 - p, 3),
    "expo.out": (p) => (p === 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    "back.out": (p) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); },
  };
  /** cubic(x1,y1,x2,y2) — CSS cubic-bezier 와 같은 곡선. x 로 t 를 찾고(뉴턴 + 이분) y 를 돌려준다 */
  const CUBIC = {};
  const cubic = (str) => {
    if (CUBIC[str]) return CUBIC[str];
    const m = /^cubic\((-?[\d.]+),(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)\)$/.exec(str); if (!m) return null;
    const [x1, y1, x2, y2] = m.slice(1).map(Number);
    const B = (a, b, t) => 3 * a * t * (1 - t) * (1 - t) + 3 * b * t * t * (1 - t) + t * t * t;
    const dB = (a, b, t) => 3 * a * (1 - t) * (1 - t) + 6 * (b - a) * t * (1 - t) + 3 * (1 - b) * t * t;
    const f = (p) => {
      if (p <= 0) return 0; if (p >= 1) return 1;
      let t = p;
      for (let i = 0; i < 6; i++) { const d = dB(x1, x2, t); if (Math.abs(d) < 1e-6) break; t -= (B(x1, x2, t) - p) / d; }
      if (t < 0 || t > 1 || Math.abs(B(x1, x2, t) - p) > 1e-4) { let lo = 0, hi = 1; t = p; for (let i = 0; i < 30; i++) { const x = B(x1, x2, t); if (Math.abs(x - p) < 1e-5) break; if (x < p) lo = t; else hi = t; t = (lo + hi) / 2; } }
      return B(y1, y2, t);
    };
    return (CUBIC[str] = f);
  };
  const easeOf = (name) => EASE[name] || (name && cubic(name)) || EASE["power2.inOut"];
  const FIELDS = ["x", "y", "scale", "rot", "opacity"];
  const DEF = { x: 0, y: 0, scale: 1, rot: 0, opacity: 1 };
  /** 키프레임 보간: 칸마다 그 칸을 가진 키들 사이에서, 뒤쪽 키의 ease 로 */
  function at(keys, t) {
    const out = { ...DEF };
    if (!keys || !keys.length) return out;
    for (const f of FIELDS) {
      const ks = keys.filter((k) => k[f] != null).sort((a, b) => a.t - b.t);
      if (!ks.length) continue;
      if (t <= ks[0].t) { out[f] = ks[0][f]; continue; }
      if (t >= ks[ks.length - 1].t) { out[f] = ks[ks.length - 1][f]; continue; }
      for (let j = 0; j < ks.length - 1; j++) {
        const a = ks[j], b = ks[j + 1];
        if (t >= a.t && t <= b.t) { const p = easeOf(b.ease)((t - a.t) / Math.max(1e-3, b.t - a.t)); out[f] = a[f] + (b[f] - a[f]) * p; break; }
      }
    }
    return out;
  }

  /** 쌓는 순서: 설계도 개체는 기본으로 코드 연출(scene.js — 패널 · 띠가 z 20~30 을 쓰기도 함) 위에 둔다.
   *  layer 0 이상 = 100 + layer (코드 연출 위), 음수 = 0 (배경 바로 위, z 를 준 코드 요소 뒤) */
  // 음수(배경 바로 위)는 z -1 로 코드 요소(z 없음 · 양수) 뒤에 두고, 그 장면의 배경(.k-bg)은 z -2 로 한 칸 더 뒤로 보낸다
  const zOf = (n, d) => { const l = n.layer ?? d; return l < 0 ? -1 : 100 + l; };
  const sinkBg = (root) => { for (const b of root.children) if (b.classList && b.classList.contains("k-bg")) b.style.zIndex = "-2"; };
  const DEFBOX = { text: [80, 400, 920, null], rect: [340, 760, 400, 400], ellipse: [340, 760, 400, 400] };
  /** 글자 · 도형의 상자 · 모양 (편집기가 고친 값을 다시 빌드하지 않고 바로 반영할 때도 쓴다) */
  function paint(e, n, z) {
    const b = n.box || {}, st = n.style || {}, d = DEFBOX[n.kind] || [0, 0, 1080, 1920];
    Object.assign(e.style, { left: (b.x ?? d[0]) + "px", top: (b.y ?? d[1]) + "px", width: (b.w ?? d[2]) + "px",
      height: (b.h ?? d[3]) != null ? (b.h ?? d[3]) + "px" : "auto", zIndex: String(zOf(n, z)) });
    if (n.kind === "text") {
      Object.assign(e.style, { color: st.color || K.T.text, fontFamily: st.font || "Pretendard, sans-serif", fontWeight: String(st.weight ?? 800),
        fontSize: (st.size ?? 72) + "px", lineHeight: "1.2", textAlign: st.align || "center", whiteSpace: "pre-wrap", wordBreak: "keep-all",
        background: st.bg || "transparent", borderRadius: (st.radius ?? 0) + "px" });
      if (e.textContent !== (n.text || "")) e.textContent = n.text || "";
      fitText(e, n);
    } else {
      Object.assign(e.style, { background: st.bg || K.T.accent, border: st.border || "none", borderRadius: n.kind === "ellipse" ? "50%" : (st.radius ?? 0) + "px" });
    }
  }
  /** 글자가 상자를 넘치면 글자 크기를 줄여 상자 안에 맞춘다(style.fit: false 면 끔). 가로가 영상 밖으로 나가 잘리는 일을 막는다 */
  function fitText(e, n) {
    const st = n.style || {}; if (st.fit === false) return;
    let size = st.size ?? 72; const min = Math.min(size, 22);
    e.style.fontSize = size + "px";
    const over = () => e.scrollWidth > e.clientWidth + 1 || (n.box && n.box.h != null && e.scrollHeight > e.clientHeight + 1);
    for (let k = 0; k < 40 && size > min && over(); k++) { size = Math.max(min, Math.floor(size * 0.94)); e.style.fontSize = size + "px"; }
  }
  const FITS = [];
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => FITS.forEach(([e, n]) => fitText(e, n)));   // 글꼴이 늦게 오면 다시 잼

  // 편집기 실시간 반영: "장면번호:노드id" → 노드. 끌기 · 키 · 글자처럼 노드 수가 그대로인 고치기는 다시 빌드하지 않는다
  const LIVE = (window.__flumaGraph = window.__flumaGraph || { nodes: {}, cams: {} });

  /** 데이터 노드 하나 → DOM. { el, update(lt) } */
  function makeNode(c, n, sketch) {
    const b = n.box || {};
    const st = n.style || {};
    const zd = n.kind === "text" ? 10 : 4, z = zOf(n, zd);
    let e, inner = null;
    // 스케치에서도 글자 · 도형 · 사진 · 실사는 그대로 그린다(화면 전체 연필 필터가 밑그림으로 바꿈). 대역 상자는 아직 채울 것이 없는 자리만
    const kfImg = n.gen && n.gen.keyframe;   // 대역 · 생성 자리의 참고 그림(구도) — 스케치에서는 연필 선으로 바뀐다
    const cands = (n.gen && n.gen.candidates) || [];
    const clip = n.kind === "gen-clip" && n.gen && n.gen.chosen != null ? cands[n.gen.chosen] : null;   // 생성된 영상(고른 후보)
    if (clip) {
      inner = K.seq(c.root, clip.src, { x: b.x ?? 0, y: b.y ?? 0, w: b.w ?? 1080, h: b.h ?? 1920, fit: n.fit || "cover", from: n.in, to: n.out, at: n.start ?? 0, z, loop: false });
      e = inner.el;
    } else if ((n.kind === "proxy" || n.kind === "gen-clip" || n.kind === "3d") && !kfImg) {
      // 대역 상자: 스케치 단계 · 아직 생성 전 · 3D 대역. 이름표로 무엇이 들어갈지 보여 준다
      e = K.box(c.root, { x: b.x ?? 140, y: b.y ?? 640, w: b.w ?? 800, h: b.h ?? 400, style: {
        zIndex: z, border: "3px dashed rgba(169,155,255,.9)", background: "rgba(104,92,255,.14)", borderRadius: "18px",
        display: "grid", placeItems: "center", color: "#d6d1ff", font: "700 34px Pretendard, sans-serif", textAlign: "center", padding: "12px", boxSizing: "border-box" } });
      e.textContent = n.label || n.text || `${n.kind} · ${n.id}`;
    } else if (n.kind === "text" || n.kind === "rect" || n.kind === "ellipse") {
      e = K.box(c.root, {});
      paint(e, n, zd);
      if (n.kind === "text") FITS.push([e, n]);
    } else if (n.kind === "image" || n.kind === "gen-clip" || n.kind === "3d" || n.kind === "proxy") {
      // gen-clip · 3d 는 아직 영상이 없을 때 키프레임 그림(구도 확인용)을 대신 보여 준다
      e = K.box(c.root, { x: b.x ?? 0, y: b.y ?? 0, w: b.w ?? 1080, h: b.h ?? 1920, style: { zIndex: z, overflow: "hidden", borderRadius: (st.radius ?? 0) + "px" } });
      const img = document.createElement("img"); img.src = n.kind === "image" ? n.src : kfImg; e.appendChild(img);
      Object.assign(img.style, { width: "100%", height: "100%", objectFit: n.fit || "cover", display: "block" });
    } else if (n.kind === "footage" || n.kind === "element") {
      // 올린 영상 프레임(uploads/…) · 레이어 요소(elements/…) — K.seq 가 시각으로 프레임을 골라 렌더에서도 정확
      inner = K.seq(c.root, n.src, { x: b.x ?? 0, y: b.y ?? 0, w: b.w ?? 1080, h: b.h ?? 1920, fit: n.fit || "cover", from: n.in, to: n.out, at: n.start ?? 0, z, loop: false });
      e = inner.el;
    } else {
      return null;
    }
    // 필름 질감(style.grain 0~1): 실사 · 생성 · 사진의 '너무 깨끗한' 느낌을 덜어 준다 — 고운 입자(프레임마다 자리 바뀜) + 살짝 차분한 색
    const grainOf = (m) => Number((m.style || {}).grain ?? (m.kind === "gen-clip" ? 0.35 : 0));
    let grain = null;
    if (["image", "footage", "element", "gen-clip"].includes(n.kind)) {
      grain = document.createElement("div");
      Object.assign(grain.style, { position: "absolute", inset: "0", pointerEvents: "none", mixBlendMode: "overlay", backgroundSize: "256px 256px",
        backgroundImage: "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='256' height='256' filter='url(%23n)'/></svg>\")" });
      e.appendChild(grain);
    }
    const setGrain = (m) => { if (!grain) return; const g = grainOf(m); grain.style.opacity = String(g * 0.55); grain.style.display = g > 0 ? "block" : "none"; e.style.filter = g > 0 ? `saturate(${1 - g * 0.12}) contrast(${1 + g * 0.04})` : ""; };
    setGrain(n);
    e.dataset.name = n.label || n.text || n.id;
    e.dataset.gnode = n.id;   // 편집기에서 설계도 노드와 이어 줄 열쇠
    let cur = n;
    LIVE.nodes[`${c.i}:${n.id}`] = { set(n2) { cur = n2; if ((n2.kind === "text" || n2.kind === "rect" || n2.kind === "ellipse")) paint(e, n2, zd); else if (n2.box) Object.assign(e.style, { left: (n2.box.x ?? 0) + "px", top: (n2.box.y ?? 0) + "px", ...(n2.box.w != null ? { width: n2.box.w + "px" } : {}), ...(n2.box.h != null ? { height: n2.box.h + "px" } : {}) }); e.style.zIndex = String(zOf(n2, zd)); if ((n2.layer ?? 0) < 0) sinkBg(c.root); setGrain(n2); } };
    return { el: e, update(lt) {
      const on = lt >= (cur.start ?? 0) && lt <= (cur.end ?? Infinity);
      e.style.visibility = on ? "visible" : "hidden";
      if (!on) return;
      if (inner) inner.update(lt);
      if (grain && grain.style.display !== "none") { const f = Math.floor(lt * 24); grain.style.backgroundPosition = `${(f * 97) % 256}px ${(f * 61) % 256}px`; }
      const k = at(cur.keys, lt);
      e.style.translate = `${k.x}px ${k.y}px`;
      e.style.scale = String(k.scale);
      e.style.rotate = `${k.rot}deg`;
      e.style.opacity = String(k.opacity);
    } };
  }

  function drawGraph(c) {
    const gs = G && G.scenes && G.scenes[c.i];
    if (!gs) return null;
    const sketch = G.fidelity === "sketch";
    const items = (gs.nodes || []).map((n) => makeNode(c, n, sketch)).filter(Boolean);
    if ((gs.nodes || []).some((n) => n.kind !== "code" && (n.layer ?? 0) < 0)) sinkBg(c.root);
    // 카메라: 장면 칸 전체(코드 연출 + 데이터 노드)를 움직인다. x · y = 카메라 위치(화면은 반대로), scale = 확대, rot = 기울기
    let cam = gs.camera && gs.camera.keys && gs.camera.keys.length ? gs.camera : null;
    LIVE.cams[c.i] = { set(cm) { cam = cm && cm.keys && cm.keys.length ? cm : null; if (!cam) { c.root.style.translate = ""; c.root.style.scale = ""; c.root.style.rotate = ""; } } };
    if (!items.length && !cam) return null;
    return (lt) => {
      items.forEach((it) => it.update(lt));
      if (cam) {
        const k = at(cam.keys, lt);
        c.root.style.transformOrigin = "50% 50%";
        c.root.style.translate = `${-k.x * k.scale}px ${-k.y * k.scale}px`;
        c.root.style.scale = String(k.scale);
        c.root.style.rotate = `${-k.rot}deg`;
      }
    };
  }

  if (!spec && !G) { K.compose({ captions: { style: "highlight" }, scenes: [preview] }); return; }

  // 장면마다: code(scene.js) → 데이터 노드 순서로 그리고, 매 프레임 둘 다 갱신
  const codeOf = (i) => (spec && spec.scenes) ? (spec.scenes[i] || spec.scenes[spec.scenes.length - 1]) : null;
  const scene = (c) => {
    const boil = (lt) => { if (window.__flumaBoil) window.__flumaBoil(c.sc.start + lt); };
    const fn = codeOf(c.i);
    const gsc = G && G.scenes && G.scenes[c.i];
    const hasData = !!(gsc && ((gsc.nodes && gsc.nodes.length) || (gsc.camera && gsc.camera.keys && gsc.camera.keys.length)));
    const code = fn ? fn(c) : (hasData ? null : preview(c));
    const data = drawGraph(c);
    if (!data && !(G && G.fidelity === "sketch")) return code;
    return (lt, p) => { if (typeof code === "function") code(lt, p); if (data) data(lt); boil(lt); };
  };
  K.compose({ ...(spec || { captions: { style: "highlight" } }), scenes: [scene] });
  if (G && G.fidelity === "sketch") sketchLook();

  /** 스케치(애니메틱): 화면 전체(코드 연출 · 사진 · 실사 · 대역)를 연필 밑그림으로. 자막은 그대로 둬 말 타이밍을 본다.
   *  윤곽선(가장자리 검출) × 옅은 명암 + 종이색, 선은 1/8초마다 살짝 흔들린다(손그림 애니메틱의 '끓는 선') */
  function sketchLook() {
    const cam = document.querySelector("#root > .k-cam"); if (!cam) return;
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg"); svg.setAttribute("width", "0"); svg.setAttribute("height", "0"); svg.style.position = "absolute";
    svg.innerHTML = `<filter id="fluma-sketch" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">
      <feColorMatrix type="saturate" values="0" result="g"/>
      <feComponentTransfer in="g" result="tone"><feFuncR type="linear" slope=".32" intercept=".68"/><feFuncG type="linear" slope=".32" intercept=".68"/><feFuncB type="linear" slope=".3" intercept=".66"/></feComponentTransfer>
      <feConvolveMatrix in="g" order="3" kernelMatrix="-1 -1 -1 -1 8 -1 -1 -1 -1" preserveAlpha="true" result="edge"/>
      <feColorMatrix in="edge" type="matrix" values="-2.6 0 0 0 1  -2.6 0 0 0 1  -2.6 0 0 0 1  0 0 0 0 1" result="ink"/>
      <feTurbulence id="fluma-boil" type="fractalNoise" baseFrequency=".035" numOctaves="2" seed="1" result="n"/>
      <feDisplacementMap in="ink" in2="n" scale="3.5" xChannelSelector="R" yChannelSelector="G" result="wob"/>
      <feBlend in="wob" in2="tone" mode="multiply"/>
    </filter>`;
    document.body.appendChild(svg);
    cam.style.filter = "url(#fluma-sketch)";
    const root = document.getElementById("root"); if (root) root.style.background = "#f1ede4";
    const boil = svg.querySelector("#fluma-boil");
    // 시각에 묶어 흔든다(렌더에서도 같은 결과) — 재생 루프가 부르는 장면 그리기에서 갱신
    window.__flumaBoil = (t) => { const k = Math.floor(t * 8) % 4 + 1; if (boil.getAttribute("seed") !== String(k)) boil.setAttribute("seed", String(k)); };
  }
})();
