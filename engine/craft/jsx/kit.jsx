// Fluma EffectCraft 기본 함수(K) — craft 재료 · refine 의 script.run 앞에 자동으로 붙는다(2026-11-17).
// 움직임 완성품이 아니라 도형 · 글자 · 키프레임을 다루는 저수준 도구다 — 장면마다 이걸 조합해 새로 짠다.
// 시각은 나레이션 낱말로: K.pop(L, $CUE:404) — 재료 단계가 $CUE 를 초로 바꾼다.
// 함정(시험됨): 같은 프레임 안 두 키는 하나로 합쳐진다 → K 는 나타나기 키를 두 프레임 이상 띄운다.
//              부모 투명도는 자식에 안 내려간다 → K.follow(child, parent).
var K = (function () {
  var C = app.project.activeItem || app.project.item(1);
  var GAP = 0.07;   // 두 프레임 넘게(30fps)
  function hx(h) { if (h instanceof Array) return h; h = String(h).replace('#', ''); if (h.length === 3) h = h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2); return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
  function T(l) { return l.property('Transform'); }
  function ease(prop, infl) { var e = new KeyframeEase(0, infl || 75); for (var k = 1; k <= prop.numKeys; k++) { var a = []; var n = (prop.value && prop.value.length) || 1; for (var d = 0; d < n; d++) a.push(e); try { prop.setTemporalEaseAtKey(k, a, a); } catch (x) {} } }
  var K = {
    C: C, hx: hx, ease: ease,
    P: function (l) { return T(l).property('Position'); }, S: function (l) { return T(l).property('Scale'); },
    O: function (l) { return T(l).property('Opacity'); }, R: function (l) { return T(l).property('Rotation'); },
    /** 장면 길이 · 바탕(단색 '#hex' 또는 [위색, 아래색] 그라데이션) */
    scene: function (sec, bg) {
      C.duration = sec;
      var s = C.layers.addSolid([0, 0, 0], 'BG', C.width, C.height, 1); s.moveToEnd();
      if (bg instanceof Array) { var g = s.property('Effects').addProperty('ADBE Ramp'); g.property('Start Color').setValue(hx(bg[0])); g.property('End Color').setValue(hx(bg[1])); g.property('Start of Ramp').setValue([C.width / 2, 0]); g.property('End of Ramp').setValue([C.width / 2, C.height]); }
      else s.property('Effects').addProperty('ADBE Fill').property('Color').setValue(hx(bg || '#101218'));
      return s;
    },
    /** 글자 — o: {font, style, align: 'left'|'center'|'right', stroke, strokeW, tracking, box:[w,h]} */
    text: function (s, x, y, size, col, o) {
      o = o || {};
      var t = o.box ? C.layers.addBoxText(o.box, s) : C.layers.addText(s);
      var d = t.property('Source Text').value;
      d.font = o.font || 'Pretendard'; if (o.style) d.fontStyle = o.style; d.fontSize = size; d.applyFill = true; d.fillColor = hx(col || '#ffffff');
      d.justification = o.align === 'left' ? ParagraphJustification.LEFT_JUSTIFY : o.align === 'right' ? ParagraphJustification.RIGHT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY;
      if (o.stroke) { d.applyStroke = true; d.strokeColor = hx(o.stroke); d.strokeWidth = o.strokeW || 8; d.strokeOverFill = false; }
      if (o.tracking) d.tracking = o.tracking;
      t.property('Source Text').setValue(d); K.P(t).setValue([x, y]); if (o.name) t.name = o.name;
      // 한 줄이 안전 폭(maxW, 기본 화면의 92%)보다 넓으면 글자 크기를 줄인다 — 좌표를 잘못 줘도 글자가 화면 밖으로 안 나가게(2026-11-17)
      if (!o.box && !o.noFit) { try { var r = t.sourceRectAtTime(0, false), mw = o.maxW || C.width * 0.92;
        if (r && r.width > mw) { d = t.property('Source Text').value; d.fontSize = Math.max(8, size * mw / r.width); t.property('Source Text').setValue(d); } } catch (x) {} }
      return t;
    },
    /** 도형 레이어 — kind: 'rect'|'ellipse', o: {fill, stroke, strokeW, round, name} */
    shape: function (kind, x, y, w, h, o) {
      o = o || {};
      var L = C.layers.addShape(); if (o.name) L.name = o.name;
      var g = L.property('Contents').addProperty('ADBE Vector Group');
      var sh = g.property('Contents').addProperty(kind === 'ellipse' ? 'ADBE Vector Shape - Ellipse' : 'ADBE Vector Shape - Rect');
      sh.property('Size').setValue([w, h]); if (kind !== 'ellipse' && o.round) sh.property('Roundness').setValue(o.round);
      if (o.fill !== false) g.property('Contents').addProperty('ADBE Vector Graphic - Fill').property('Color').setValue(hx(o.fill || '#ffffff'));
      if (o.stroke) { var st = g.property('Contents').addProperty('ADBE Vector Graphic - Stroke'); st.property('Color').setValue(hx(o.stroke)); st.property('Stroke Width').setValue(o.strokeW || 6); }
      K.P(L).setValue([x, y]);
      return L;
    },
    /** 이미지 파일(png · jpg — 다른 재료의 결과는 "$USE:이름") */
    image: function (path, x, y, scale) {
      var seq = /[\\\/]f000\.png$/.test(path);   // 움직이는 형태(form_cli anim → …/f000.png) — 프레임 묶음을 12fps 로 반복 재생
      var io = new ImportOptions(new File(path)); if (seq) io.sequence = true;
      var it = app.project.importFile(io); var L = C.layers.add(it);
      if (seq) { try { it.mainSource.conformFrameRate = 12; } catch (e) {} L.timeRemapEnabled = true; L.property('Time Remap').expression = 'time % thisLayer.source.duration'; L.outPoint = C.duration; }
      K.P(L).setValue([x, y]); if (scale) K.S(L).setValue([scale, scale]); return L;
    },
    /** 붙여 넣은 SVG(edit.pasteSvg) 레이어의 획 · 도형 그룹들 — 그린 순서대로 */
    leaves: function (L) {
      var out = [];
      function walk(g) { var c = g.property('Contents'), leaf = false, j;
        for (j = 1; j <= c.numProperties; j++) if (c.property(j).matchName.indexOf('ADBE Vector Shape') === 0) leaf = true;
        if (leaf) { out.push(g); return; }
        for (j = 1; j <= c.numProperties; j++) if (c.property(j).matchName === 'ADBE Vector Group') walk(c.property(j)); }
      var cs = L.property('Contents'); for (var k = 1; k <= cs.numProperties; k++) if (cs.property(k).matchName === 'ADBE Vector Group') walk(cs.property(k));
      return out.reverse();   // SVG 는 나중에 그린 것이 앞
    },
    layer: function (name) { for (var i = 1; i <= C.numLayers; i++) if (C.layer(i).name.indexOf(name) === 0) return C.layer(i); return null; },
    /** t 에 나타나기(안 보이다가) — d 초 동안 */
    appear: function (L, t, d) { var o = K.O(L); o.setValue(0); o.setValueAtTime(Math.max(0, t - GAP), 0); o.setValueAtTime(t + (d || 0), 100); return L; },
    fadeOut: function (L, t, d) { var o = K.O(L); o.setValueAtTime(t, 100); o.setValueAtTime(t + (d || 0.2), 0); return L; },
    dim: function (L, t, v) { var o = K.O(L); o.setValueAtTime(t, o.valueAtTime(t, false)); o.setValueAtTime(t + 0.2, v === undefined ? 35 : v); return L; },
    /** 튀어나오기(넘쳤다 돌아옴) — 나타나기 포함 */
    pop: function (L, t, to) { to = to || 100; K.appear(L, t); var s = K.S(L); s.setValue([0, 0]); s.setValueAtTime(t, [0, 0]); s.setValueAtTime(t + 0.16, [to * 1.12, to * 1.12]); s.setValueAtTime(t + 0.28, [to * 0.96, to * 0.96]); s.setValueAtTime(t + 0.38, [to, to]); return L; },
    /** [x0,y0] → [x1,y1] 이동(이징) */
    move: function (L, t, from, to, d, infl) { var p = K.P(L); if (from) p.setValueAtTime(t, from); p.setValueAtTime(t + (d || 0.5), to); ease(p, infl || 80); return L; },
    /** 좌우로 흔들기(회전) */
    shake: function (L, t, amp) { amp = amp || 5; var r = K.R(L); r.setValueAtTime(t, 0); r.setValueAtTime(t + 0.06, -amp); r.setValueAtTime(t + 0.14, amp); r.setValueAtTime(t + 0.22, -amp * 0.6); r.setValueAtTime(t + 0.3, 0); return L; },
    /** 획이 그려지기(Trim Paths) — 그룹(K.leaves 결과) 또는 도형 레이어 */
    draw: function (g, t, d) { var c = g.property('Contents'); var tr = c.addProperty('ADBE Vector Filter - Trim'); var e = tr.property('End'); e.setValue(0); e.setValueAtTime(t, 0); e.setValueAtTime(t + (d || 0.45), 100); return g; },
    /** 그룹을 제 가운데 기준으로 튀어나오게 — cx, cy: 그 도형의 가운데(그림 좌표) */
    popGroup: function (g, t, cx, cy) { var tg = g.property('Transform'); tg.property('Anchor Point').setValue([cx, cy]); tg.property('Position').setValue([cx, cy]); var s = tg.property('Scale'); s.setValue([0, 0]); s.setValueAtTime(t, [0, 0]); s.setValueAtTime(t + 0.16, [112, 112]); s.setValueAtTime(t + 0.28, [96, 96]); s.setValueAtTime(t + 0.38, [100, 100]); return g; },
    /** 글자를 왼쪽부터 써 내려가기(Linear Wipe) — 글자 수에 맞는 속도 */
    write: function (L, t, d) { var w = L.property('Effects').addProperty('ADBE Linear Wipe'); w.property('Wipe Angle').setValue(270); w.property('Feather').setValue(30); var c = w.property('Transition Completion'); var n = 0; try { n = String(L.property('Source Text').value.text).length; } catch (x) {} c.setValue(100); c.setValueAtTime(t, 100); c.setValueAtTime(t + (d || Math.min(1.4, 0.12 + 0.07 * n)), 0); return L; },
    /** 자식이 부모 투명도를 따라가게(부모로 묶을 때) */
    /** EffectCraft 효과 붙이기 — 이름은 카탈로그 id('ec.stylize.glow') · 화면 이름('Glow') · 내부 이름('ADBE Glo2') 모두 된다(craft_catalog.py search 로 찾음).
     *  v = {속성 이름: 값 | [[초, 값], …](키프레임)}. 없는 이름이면 조용히 무시되던 것을 오류로 낸다(2026-11-19 시험) */
    fx: function (L, name, v) {
      var E = L.property('Effects'), n0 = E.numProperties; E.addProperty(name);
      if (E.numProperties === n0) throw new Error('K.fx: 효과 없음 — ' + name + ' (craft_catalog.py search 로 id 확인)');
      var f = E.property(E.numProperties);
      for (var k in (v || {})) { var p = f.property(k); if (!p) throw new Error('K.fx: ' + name + ' 에 속성 없음 — ' + k);
        var x = v[k]; if (x instanceof Array && x.length && x[0] instanceof Array) { for (var i = 0; i < x.length; i++) p.setValueAtTime(x[i][0], x[i][1]); } else p.setValue(x); }
      return f;
    },
    follow: function (child, parent) { child.parent = parent; K.O(child).expression = 'parent.transform.opacity'; return child; },
    /** 안전 영역 맞춤 — 장면 스크립트가 끝난 뒤 자동으로 불린다(craft_script.with_kit).
     *  묶음(맨 위 부모 레이어와 그 자식들)마다 움직임을 마친 자리(마지막 위치 · 크기 키)를 재서, 화면 가장자리(가로 m, 세로 m/2)를
     *  넘은 만큼만 그 묶음의 위치를 안쪽으로 옮긴다(위치 키 전체를 같은 만큼 — 연출은 그대로). 크기는 건드리지 않고,
     *  묶음 자체가 안전 영역보다 클 때만 그 묶음을 줄인다. 화면 밖에서 들어오거나 밖으로 나가는 연출(멈춘 자리가 완전히 밖)은 그대로.
     *  배경(BG) · 화면을 덮는 판 · 이미지 · 영상은 재지 않는다.
     *  2026-11-17: 좌표를 직접 쓴 2D 장면에서 카드 · 큰 글자가 자리 때문에 화면 밖으로 잘렸다(장면 전체 축소는 '작아져서 별로'라 요소만 옮긴다) */
    fit: function (m) {
      m = (m === undefined) ? 0.04 : m;
      var W = C.width, H = C.height, i, L, eps = 1 / 30, groups = {}, out = [];
      function keys(l) { var ts = [], nm = ['Position', 'Scale'], a, k, p; for (a = 0; a < nm.length; a++) { p = T(l).property(nm[a]); for (k = 1; k <= p.numKeys; k++) ts.push(p.keyTime(k)); } return ts; }
      function rest(l) { var t = 0, c = l, ks, k; while (c) { ks = keys(c); for (k = 0; k < ks.length; k++) if (ks[k] > t) t = ks[k]; c = c.parent; } return Math.min(t, C.duration - eps); }
      function world(l, x, y, t) { var c = l, tr, p, a, s; while (c) { tr = T(c); p = tr.property('Position').valueAtTime(t, false); a = tr.property('Anchor Point').valueAtTime(t, false); s = tr.property('Scale').valueAtTime(t, false); x = p[0] + (x - a[0]) * s[0] / 100; y = p[1] + (y - a[1]) * s[1] / 100; c = c.parent; } return [x, y]; }
      function top(l) { while (l.parent) l = l.parent; return l; }
      function shift(prop, dx, dy) { var k, v; if (prop.numKeys) { for (k = 1; k <= prop.numKeys; k++) { v = prop.keyValue(k); v[0] += dx; v[1] += dy; prop.setValueAtKey(k, v); } } else { v = prop.value; v[0] += dx; v[1] += dy; prop.setValue(v); } }
      function scaleBy(prop, f) { var k, v; if (prop.numKeys) { for (k = 1; k <= prop.numKeys; k++) { v = prop.keyValue(k); v[0] *= f; v[1] *= f; prop.setValueAtKey(k, v); } } else { v = prop.value; v[0] *= f; v[1] *= f; prop.setValue(v); } }
      for (i = 1; i <= C.numLayers; i++) {
        L = C.layer(i); if (L.name === 'BG') continue;
        var kind = ''; try { if (L.property('Source Text')) kind = 'text'; } catch (x) {} try { if (!kind && L.property('Contents')) kind = 'shape'; } catch (x) {}
        if (!kind) continue;
        var t = rest(L), op = 100; try { op = T(L).property('Opacity').valueAtTime(t, false); } catch (x) {}
        if (op < 5) continue;
        var r; try { r = L.sourceRectAtTime(t, false); } catch (x) { continue; }
        if (!r || !(r.width > 0) || !(r.height > 0)) continue;
        var p1 = world(L, r.left, r.top, t), p2 = world(L, r.left + r.width, r.top + r.height, t);
        var x0 = Math.min(p1[0], p2[0]), x1 = Math.max(p1[0], p2[0]), y0 = Math.min(p1[1], p2[1]), y1 = Math.max(p1[1], p2[1]);
        if (x1 <= 0 || x0 >= W || y1 <= 0 || y0 >= H) continue;              // 멈춘 자리가 완전히 밖 — 나가는 연출
        if (x1 - x0 > W * 0.95 && y1 - y0 > H * 0.5) continue;               // 화면을 덮는 판
        var tp = top(L), g = groups[tp.index];
        groups[tp.index] = g ? { L: tp, t: Math.max(g.t, t), x0: Math.min(g.x0, x0), y0: Math.min(g.y0, y0), x1: Math.max(g.x1, x1), y1: Math.max(g.y1, y1) } : { L: tp, t: t, x0: x0, y0: y0, x1: x1, y1: y1 };
      }
      var l0 = W * m, r0 = W * (1 - m), t0 = H * m / 2, b0 = H * (1 - m / 2);
      for (var gi in groups) {
        var G = groups[gi], w = G.x1 - G.x0, h = G.y1 - G.y0, f = Math.min(1, (r0 - l0) / w, (b0 - t0) / h);
        if (f < 0.999) {                                                     // 묶음 자체가 안전 영역보다 큼 — 그 묶음만 줄인다(기준점 둘레로)
          var ap = T(G.L).property('Position').valueAtTime(G.t, false);
          scaleBy(T(G.L).property('Scale'), f);
          G.x0 = ap[0] + (G.x0 - ap[0]) * f; G.x1 = ap[0] + (G.x1 - ap[0]) * f; G.y0 = ap[1] + (G.y0 - ap[1]) * f; G.y1 = ap[1] + (G.y1 - ap[1]) * f;
        }
        var dx = G.x0 < l0 ? l0 - G.x0 : (G.x1 > r0 ? r0 - G.x1 : 0), dy = G.y0 < t0 ? t0 - G.y0 : (G.y1 > b0 ? b0 - G.y1 : 0);
        if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5 && f >= 0.999) continue;
        shift(T(G.L).property('Position'), dx, dy);
        out.push({ layer: G.L.name, dx: Math.round(dx), dy: Math.round(dy), scale: Math.round(f * 1000) / 1000 });
      }
      return out.length ? out : null;
    }
  };
  return K;
})();
