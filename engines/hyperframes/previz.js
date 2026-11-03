// 미리 보기(프리비즈) 화면 — 장면 코드(compositions/<id>/scene.js) 없이 콘티만으로 '대충 만든' 영상을 짠다(scripts/previz.py render).
// 녹화 · 생성에 시간과 돈을 쓰기 전에 구성 · 타이밍 · 웃음 포인트를 본다. 재료가 있으면 그것을, 없으면 회색 카드(무엇이 들어갈지)로.
// 글자 띠(고정 제목 · 펀치라인 · 상황 괄호 · 반응 자막 · 속마음)는 최종과 같은 부품(K.talk.gram)이 콘티 grammar 숫자로 그린다.
(function () {
  const k = K.talk, g = k.gram, sb = SF.sb || {};
  const BG = (g.G && g.G.background) || "#000";
  const KIND = { "실제 화면": "웹 녹화", "기사": "웹 녹화 · 기사", "짤": "짤", "카드(글자)": "글자 카드", "도표": "도표", "애니메이션 · 일러스트": "2D 그림 · 캐릭터" };

  // 재료 하나: 파일이 있으면 그것, 없으면 회색 자리표시 카드
  function material(c, screen, what, src, from = 0, to = 99) {
    const b = g.box();
    const e = K.box(c.root, { x: b.x, y: b.y, w: b.w, h: b.h, style: { overflow: "hidden", visibility: "hidden", zIndex: 5 } });
    if (src && /\.(png|jpe?g|webp)$/i.test(src)) {
      const im = K.el("img", "", e); im.src = src; K.css(im, { width: "100%", height: "100%", objectFit: "cover" });
    } else if (src) {
      const s = K.seq(e, src, { x: 0, y: 0, w: b.w, h: b.h, fit: "cover", at: from, loop: true });
      e._seq = s;
    } else {
      K.css(e, { background: "repeating-linear-gradient(135deg,#2a2a2e 0 26px,#24242a 26px 52px)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "18px", textAlign: "center", padding: "0 70px", boxSizing: "border-box" });
      const t = K.el("div", "", e); K.css(t, { font: "800 60px/1.2 Pretendard", color: "#cfcfd6" }); t.textContent = `[${KIND[screen] || screen || "재료"}]`;
      const w = K.el("div", "", e); K.css(w, { font: "700 48px/1.35 Pretendard", color: "#9a9aa3" }); w.textContent = what || "";
    }
    K.name(e, `재료 · ${what || screen || ""}`);
    return { el: e, update(lt) { const on = lt >= from && lt < to; e.style.visibility = on ? "visible" : "hidden"; if (on && e._seq) e._seq.update(lt); } };
  }

  window.FLUMA_SCENE = {
    captions: { style: "none" },
    transitions: (sb.scenes || []).slice(1).map(() => "cut"),
    trDur: 0.01,
    global({ root }) {
      K.css(root, { background: BG });
      const parts = [g.title(root, sb.title), g.punch(root, sb.punchline)];
      if (!g.G.subs) parts.push(k.subs(root));   // 문법에 반응 자막 자리가 없으면 나레이션 자막
      return (t) => parts.forEach((p) => p && p.update && p.update(t));
    },
    scenes: (sb.scenes || []).map((sc) => (c) => {
      K.css(c.root, { background: BG });
      const v = sc.visual || {};
      // 장면 재료 + beats 의 '재료'를 시간 순서로 — 각 재료는 다음 재료가 올 때까지
      const seq = [{ t: 0, screen: sc.screen, what: v.primary || sc.beat, src: v.src }];
      for (const b of sc.beats || []) if (b.do === "재료") seq.push({ t: c.cue(b.at), screen: b.screen, what: b.what, src: b.src, hold: b.hold });
      seq.sort((a, b) => a.t - b.t);
      const mats = seq.map((m, i) => {
        const nextT = i + 1 < seq.length ? seq[i + 1].t : 99;
        const end = m.hold ? Math.min(nextT, m.t + m.hold) : nextT;
        return material(c, m.screen, m.what, m.src, m.t, end);
      });
      // 짤 · 사진이 hold 로 끝나면 장면 재료로 돌아온다
      const base = mats[0];
      const parts = [
        g.tag(c, sc.situation),
        g.sub(c, sc.caption, sc.caption_at != null ? sc.caption_at : 0.3),
        g.thought(c, sc.thought, sc.thought_at != null ? sc.thought_at : 0.6),
      ];
      return (lt) => {
        let shown = false;
        mats.forEach((m, i) => { if (i > 0) { m.update(lt); if (m.el.style.visibility === "visible") shown = true; } });
        base.update(shown ? -1 : lt);
        parts.forEach((p) => p.update(lt));
      };
    }),
  };
})();
