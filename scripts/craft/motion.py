"""Craft 파이프라인 — 움직임 단계: 콘티 + 단어 타이밍 → EffectCraft 프로젝트(.ecproj).

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (3 · 5절)
결정적 생성기: 같은 입력이면 같은 프로젝트. 에이전트는 좌표 · 키프레임 숫자를 쓰지 않는다 — 콘티(장면 · 요소 · beats)와
장면 계획(scenes/<n>.plan.json, 있으면)만 쓰고, 이 생성기가 키프레임으로 바꾼다.

프로젝트 구조(사람이 EffectCraft 에서 열면 이렇게 보인다)
  Main                       1080×1920 전체, 장면 컴포지션을 시간순으로
  S01 훅 · S02 반전 …         장면마다 컴포지션 하나
     BG                      바탕(콘티 디자인 방향 색)
     Camera (null)           그림 층의 부모 — 장면 내내 천천히 밀고, beats 의 '확대' 에서 당긴다
     Art …                   compositions/<id>/craft/art/s<NN>*.png|svg (뒤 → 앞), 없으면 무엇이 들어갈지 적힌 자리표시
     Title · TitleBox …      '훅 제목' 요소: 노란 상자에 한 줄씩 쌓임(상자는 글자 크기를 따라감 — 사람이 글자를 고쳐도 맞음)
     Pill · PillText         '숫자 알약' 요소: 위쪽 가운데, 숫자가 아래에서 굴러 올라옴
     Sub 01 …                단어 자막(1~2어절씩, 화면 문법 grammar.subs 의 위치 · 크기)

화면 문법은 콘티 grammar(previz.py grammar 가 참고 쇼츠에서 잰 값)를 쓴다. 없으면 direction 의 기본값.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLE_KO = {"hook": "훅", "reveal": "반전", "setup": "의문", "step": "과정", "proof": "증거", "outro": "맺음", "contrast": "대비",
           "verdict": "결론", "payoff": "결론", "cta": "행동", "item": "항목", "benefit": "이점", "problem": "고민", "context": "맥락"}
ART_EXT = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".mp4", ".mov")


def js(v) -> str:
    """파이썬 값 → JS 리터럴(문자열은 안전하게 이스케이프)"""
    return json.dumps(v, ensure_ascii=False)


def rgb(hexs: str, default=(0.06, 0.29, 0.49)) -> list[float]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (hexs or "").strip())
    if not m:
        return list(default)
    h = m.group(1)
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def chunks(words: list[dict], max_chars: int = 9, max_words: int = 2) -> list[dict]:
    """단어 자막 → 1~2어절 덩어리(레퍼런스: 말하는 1~3단어만 따라 바뀜)"""
    out, cur = [], []
    for w in words:
        t = (w.get("text") or "").strip()
        if not t:
            continue
        if cur and (len(cur) >= max_words or len("".join(x["text"].strip() for x in cur)) + len(t) > max_chars):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"text": " ".join(x["text"].strip() for x in c), "start": c[0]["startMs"] / 1000, "end": c[-1]["endMs"] / 1000} for c in out]


def cue_time(cue: str | None, words: list[dict], start: float, end: float) -> float | None:
    """beats · 요소의 cue 낱말이 나오는 시각(장면 안 기준 초). 못 찾으면 None"""
    if not cue:
        return None
    key = re.sub(r"\s+", "", cue)
    for w in words:
        t = re.sub(r"\s+", "", w.get("text") or "")
        if t and (key in t or t in key) and start - 0.05 <= w["startMs"] / 1000 <= end:
            return round(w["startMs"] / 1000 - start, 3)
    return None


def art_files(sid: str, n: int) -> list[Path]:
    d = ROOT / "compositions" / sid / "craft" / "art"
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() in ART_EXT and re.match(rf"s{n:02d}(\b|[-_.])", p.name))


def grammar(sb: dict) -> dict:
    g = dict(sb.get("grammar") or {})
    g.setdefault("subs", {"y": 0.76, "h": 0.024, "box": False, "fg": "#ffffff"})
    g.setdefault("pill", {"y": 0.09, "h": 0.03})
    g.setdefault("title", {"y": 0.24, "h": 0.04, "box": True, "bg": "#ffd60a", "fg": "#111111"})
    return g


def element(sc: dict, *names: str) -> dict | None:
    for e in sc.get("elements") or []:
        if any(n in (e.get("name") or "") for n in names):
            return e
    return None


def quoted(text: str) -> list[str]:
    """'AI가 / 지어낸 / 패키지' 처럼 따옴표 안을 / 로 나눈 줄들"""
    m = re.search(r"[‘'\"“]([^’'\"”]+)[’'\"”]", text or "")
    return [s.strip() for s in m.group(1).split("/") if s.strip()] if m else []


PILL_COLORS = {"분홍": [0.97, 0.15, 0.52], "보라": [0.55, 0.3, 0.95], "청록": [0.1, 0.72, 0.68], "주황": [1.0, 0.55, 0.1], "파랑": [0.2, 0.5, 1.0]}


def pill_color(what: str, k: int) -> list[float]:
    for name, c in PILL_COLORS.items():
        if name in what:
            return c
    return list(PILL_COLORS.values())[k % len(PILL_COLORS)]


POS_X = {"left": 0.26, "center": 0.5, "right": 0.74, "far_left": -0.2, "far_right": 1.2}


def figure_dir(sid: str, name: str) -> Path:
    return ROOT / "compositions" / sid / "craft" / "art" / "figures" / name


def puppet(J, sid: str, fig: dict, sec: float, words: list[dict], start: float, end: float, W: int, H: int, k: int,
           d: Path | None = None) -> bool:
    """그린 캐릭터(rig.json)를 부품 레이어 인형으로 조립하고 동작을 붙인다. 좌표는 장면 말(at · to · size)에서만 온다"""
    d = d or figure_dir(sid, fig.get("name", ""))
    rp = d / "rig.json"
    if not rp.exists():
        return False
    rig = json.loads(rp.read_text("utf-8"))
    cw, ch = rig["canvas"]
    size = float(fig.get("size", 0.3))
    s = size * H / ch * 100                                # 레이어 배율(%)
    gy = float(fig.get("ground", 0.8)) * H
    x0 = POS_X.get(fig.get("at", "center"), 0.5) * W
    x1 = POS_X.get(fig.get("to", fig.get("at", "center")), 0.5) * W
    ox, oy = rig["origin"]
    nm = f"Fig {fig.get('name')} {k}"
    J(f"var fg = c.layers.addNull(); fg.name = {js(nm)}; fg.property('Transform').property('Position').setValue([{x0:.1f}, {gy:.1f}]);")
    J("var L = {};")
    for ly in rig["layers"]:
        px, py = ly["pivot"]
        wx, wy = x0 + (px - ox) * s / 100, gy + (py - oy) * s / 100
        J(f"var f = app.project.importFile(new ImportOptions(new File({js(str(d / ly['file']))})));")
        J(f"var l = c.layers.add(f); l.name = {js(nm + ' · ' + ly['id'])};")
        J(f"l.property('Transform').property('Anchor Point').setValue([{px}, {py}]); l.property('Transform').property('Scale').setValue([{s:.3f}, {s:.3f}]); l.property('Transform').property('Position').setValue([{wx:.1f}, {wy:.1f}]);")
        J(f"L[{js(ly['id'])}] = l;")
    for ly in rig["layers"]:   # 부모는 모든 위치를 정한 뒤에(세계 좌표 유지)
        J(f"L[{js(ly['id'])}].parent = {('L[' + js(ly['parent']) + ']') if ly.get('parent') else 'fg'};")
    # 동작 — 원리를 표현식으로(사람이 EffectCraft 에서 숫자를 바꾸면 그대로 반영)
    act = fig.get("action", "idle")
    t0 = cue_time(fig.get("cue"), words, start, end) or 0.0
    roots = [ly for ly in rig["layers"] if not ly.get("parent") and ly.get("kind") == "body"]
    for ly in roots:   # 숨쉬기: 발 기준으로 늘었다 줄기(부피 보존)
        J(f"L[{js(ly['id'])}].property('Transform').property('Scale').expression = 'var a = Math.sin(time * Math.PI * 1.3); [value[0] * (1 - 0.018 * a), value[1] * (1 + 0.026 * a)]';")
    for ly in rig["layers"]:
        kind, lid = ly.get("kind"), js(ly["id"])
        ph = "Math.PI" if ly.get("mirror_of") else "0"
        if kind == "tail":   # 부속: 한 박자 늦게 따라 흔들림
            J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + 9 * Math.sin(time * 5.0 - 0.7)';")
        if act == "walk":
            if kind == "leg":
                J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + 24 * Math.sin(time * 9.0 + {ph})';")
            elif kind == "arm":
                J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value - 20 * Math.sin(time * 9.0 + {ph})';")
        if act == "wave" and kind == "arm" and not ly.get("mirror_of"):
            # 바깥쪽 위로 들어 올린다: 몸 왼쪽에 붙은 팔은 시계 방향(+), 오른쪽 팔은 반대
            body_x = roots[0]["pivot"][0] if roots else ly["pivot"][0]
            sign = 1 if ly["pivot"][0] < body_x else -1
            J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + {sign} * (14 + 16 * Math.sin(time * 10.0))';")   # 그린 자세에서 흔든다
    if act == "walk":
        for ly in roots:   # 걸음마다 몸이 위아래로
            J(f"L[{js(ly['id'])}].property('Transform').property('Position').expression = 'value - [0, {0.03 * size * H:.1f} * Math.abs(Math.sin(time * 9.0))]';")
        J(f"var fp = fg.property('Transform').property('Position'); fp.setValueAtTime({t0:.3f}, [{x0:.1f}, {gy:.1f}]); fp.setValueAtTime({sec:.3f}, [{x1:.1f}, {gy:.1f}]);")
    if act == "bounce":
        J(f"fg.property('Transform').property('Position').expression = 'value - [0, {0.08 * size * H:.1f} * Math.abs(Math.sin((time - {t0:.3f}) * 6.0))]';")
    return True


# ---------------------------------------------------------------- 재료(범용): 어떤 Craft 툴이 만든 재료든 같은 방식으로
PLACE = {"full": (0.5, 0.5, 1.0, 1.0), "center": (0.5, 0.47, 0.82, 0.5), "left": (0.3, 0.55, 0.5, 0.45),
         "right": (0.7, 0.55, 0.5, 0.45), "top": (0.5, 0.3, 0.86, 0.32), "bottom": (0.5, 0.66, 0.86, 0.32)}


def scene_materials(sid: str, n: int, sc: dict | None = None) -> list[dict]:
    """이 장면의 재료 기록 — 콘티에 지금 있는 재료만(지운 재료의 기록이 남아 있어도 그리지 않는다), 콘티 순서대로"""
    d = ROOT / "compositions" / sid / "craft" / "materials" / f"s{n:02d}"
    recs = [json.loads(f.read_text("utf-8")) for f in sorted(d.glob("*.json"))] if d.exists() else []
    recs = [r for r in recs if isinstance(r, dict) and r.get("type") and r.get("key")]   # 재료 기록만(보조 파일 제외)
    if sc is None:
        return recs
    order = [str(m.get("id") or f"m{i + 1}") for i, m in enumerate(sc.get("materials") or [])]
    by = {r["id"]: r for r in recs}
    return [by[i] for i in order if i in by]


def palette_list(sid: str) -> list[list[float]]:
    """화풍 시스템 팔레트(역할 순서) → 차트 · 강조 색. 없으면 기본"""
    import sys as _s
    _s.path.insert(0, str(ROOT / "scripts"))
    from drawlib import style as _st
    f = ROOT / "compositions" / sid / "style.json"
    st = _st.resolve(json.loads(f.read_text("utf-8")) if f.exists() else {})
    pal = st.get("palette") or {}
    order = [pal.get(k) for k in ("accent", "accent2", "main", "main_dark", "light")] + ["#ffd60a", "#ff3d6b", "#14c6d0", "#52cc66"]
    return [rgb(c) for c in order if isinstance(c, str) and c.startswith("#")]


def material_jsx(J, rec: dict, words: list[dict], start: float, end: float, sec: float, W: int, H: int, font: str, colors: list,
                 top: float = 0.0, bottom: float = 0.74, t_in: float | None = None, t_out: float | None = None) -> None:
    """top · bottom: 재료가 쓸 세로 구간(화면 비율) — 제목 · 자막과 겹치지 않게"""
    sp = rec.get("spec") or {}
    t0 = cue_time(sp.get("cue"), words, start, end) if t_in is None else t_in
    t0 = 0.0 if t0 is None else t0
    mid = rec["id"]
    typ = rec["type"]
    if typ == "chart":
        data = rec.get("data") or {}
        vals, labs, unit = data.get("values") or [], data.get("labels") or [], data.get("unit", "")
        n = max(1, len(vals))
        vmax = max(vals) if vals else 1
        title_h = 0.05 if data.get("title") else 0.0
        x0, x1, base = 0.16 * W, 0.84 * W, bottom * H - 70            # 아래: 항목 이름 자리
        hmax = max(0.08 * H, base - (top + title_h) * H - 90)         # 위: 제목 + 값 글자 자리
        bw = (x1 - x0) / n * 0.62
        if data.get("title"):
            J(f"var ct = txt(c, {js('Chart title ' + mid)}, {js(data['title'])}, {js(font)}, 60, [1, 1, 1], null, 0, [{W / 2}, {(top + 0.03) * H:.0f}]); popIn(ct, {max(0.0, t0 - 0.1):.2f}, 0.18);")
        for i, (v, lab) in enumerate(zip(vals, labs)):
            cx = x0 + (x1 - x0) * (i + 0.5) / n
            hh = max(8.0, hmax * v / vmax)
            col = colors[i % len(colors)]
            ti = t0 + i * 0.15
            J(f"var b = card(c, {js(f'Bar {mid} {i}')}, {bw:.0f}, {hh:.0f}, {js(col)}, 12); b.property('Transform').property('Anchor Point').setValue([0, {hh / 2:.0f}]); b.property('Transform').property('Position').setValue([{cx:.0f}, {base:.0f}]);")
            J(f"var bs = b.property('Transform').property('Scale'); bs.setValueAtTime({ti:.2f}, [100, 0]); bs.setValueAtTime({ti + 0.55:.2f}, [100, 100]); ease(bs, 80);")
            J(f"var vt = txt(c, {js(f'Value {mid} {i}')}, '0', {js(font)}, 64, [1, 1, 1], null, 0, [{cx:.0f}, {base - hh - 24:.0f}]);")
            J(f"vt.property('Source Text').expression = 'var v = linear(time, {ti:.2f}, {ti + 0.55:.2f}, 0, {v}); (Math.round(v * 10) / 10) + {js(unit)}';")
            J(f"vt.property('Transform').property('Opacity').setValueAtTime({max(0.0, ti - 0.01):.2f}, 0); vt.property('Transform').property('Opacity').setValueAtTime({ti + 0.1:.2f}, 100);")
            J(f"txt(c, {js(f'Label {mid} {i}')}, {js(str(lab))}, {js(font)}, 44, [0.92, 0.92, 0.95], null, 0, [{cx:.0f}, {base + 64:.0f}]);")
        if t_out is not None and t_out < sec - 0.05:   # 다음 재료가 나오면 차트 전체(막대 · 숫자 · 이름 · 제목)가 비킨다
            J(f"for (var li = 1; li <= c.numLayers; li++) {{ var Lc = c.layer(li); if (/ {mid}( |$)/.test(Lc.name)) {{ var oc = Lc.property('Transform').property('Opacity'); oc.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, 100); oc.setValueAtTime({t_out:.2f}, 0); }} }}")
        return
    # 관절 인형은 콘티에 동작(action)을 적은 캐릭터만 — 사물 · 장면 그림(메뉴판 · 폰 · 문서)은 통째로 한 장(글자까지 그대로)
    if typ == "illustration" and rec.get("rig") and sp.get("action") and sp.get("action") != "still":
        # 부품 레이어 인형: 남은 세로 구간 안에 발을 붙이고 동작(idle · walk · wave · bounce)
        fig = {"name": mid, "at": sp.get("at", sp.get("place", "center")), "to": sp.get("to"), "action": sp.get("action", "idle"),
               "cue": sp.get("cue"), "size": round(max(0.3, (bottom - top) * float(sp.get("size", 0.9))), 3), "ground": bottom - 0.01}
        fig = {k2: v for k2, v in fig.items() if v is not None}
        if fig["at"] not in POS_X:
            fig["at"] = "center"
        puppet(J, "", fig, sec, words, start, end, W, H, 0, d=ROOT / rec["rig"])
        return
    f = rec.get("file")
    if not f:
        return
    path = ROOT / f
    J(f"var f = app.project.importFile(new ImportOptions(new File({js(str(path))}))); var ml = c.layers.add(f); ml.name = {js('Mat ' + mid)};")
    if typ == "doc_quote":
        # 페이지를 화면 폭에 맞추고, 찾은 문장으로 확대해 들어가며 형광펜을 긋는다
        hl = rec.get("highlight") or []
        J("var r0 = ml.sourceRectAtTime(0, false);")
        J(f"var k0 = {W * 0.96} / r0.width * 100; ml.property('Transform').property('Scale').setValue([k0, k0]); ml.property('Transform').property('Anchor Point').setValue([0, 0]);")
        J(f"var px = {W * 0.02}, py = {top * H:.0f}; ml.property('Transform').property('Position').setValue([px, py]);")
        for k, (x, y, w, h) in enumerate(hl):
            J(f"var hb = card(c, {js(f'Highlight {mid} {k}')}, {w:.1f}, {h * 1.1:.1f}, [1, 0.86, 0.1], 4); hb.property('Transform').property('Opacity').setValue(55);")
            J(f"hb.property('Transform').property('Anchor Point').setValue([{-w / 2:.1f}, 0]); hb.property('Transform').property('Position').setValue([px + {x:.1f} * k0 / 100, py + {y + h / 2:.1f} * k0 / 100]); hb.property('Transform').property('Scale').setValue([k0, k0]);")
            J(f"var hs = hb.property('Transform').property('Scale'); hs.setValueAtTime({t0 + 0.4 + k * 0.35:.2f}, [0, k0]); hs.setValueAtTime({t0 + 0.75 + k * 0.35:.2f}, [k0, k0]); ease(hs, 60);")
            J("hb.parent = ml;")
        if hl:
            # 편집자처럼: 찾은 줄의 글자가 화면에서 ~64px 이 되게 확대하고, 첫 줄의 가운데로 간다(옆이 잘려도 됨)
            x, y, w, h = hl[0]
            cxp, cyp = x + min(w, W * 0.9) / 2, y + h / 2
            J(f"var zk = Math.max(1.4, Math.min(3.2, 64 / ({h:.1f} * k0 / 100)));")
            J(f"var mp = ml.property('Transform').property('Position'), ms = ml.property('Transform').property('Scale');")
            J(f"mp.setValueAtTime({t0:.2f}, [px, py]); ms.setValueAtTime({t0:.2f}, [k0, k0]);")
            J(f"mp.setValueAtTime({t0 + 0.6:.2f}, [{W / 2} - {cxp:.1f} * k0 / 100 * zk, {(top + bottom) / 2 * H:.0f} - {cyp:.1f} * k0 / 100 * zk]); ms.setValueAtTime({t0 + 0.6:.2f}, [k0 * zk, k0 * zk]); ease(mp, 75); ease(ms, 75);")
        return
    place = sp.get("place", "full" if typ in ("screen", "video") else "center")
    px, py, pw, ph = PLACE.get(place, PLACE["center"])
    if place != "full":                      # 남은 세로 구간 안으로
        py, ph = top + (bottom - top) * (py - 0.15) / 0.7, min(ph, (bottom - top) * 0.92)
    # 크기 · 기준점은 소스의 실제 픽셀 크기로(sourceRectAtTime 은 PNG 해상도 정보에 따라 달라 그림이 커졌다)
    J("var r1 = { left: 0, top: 0, width: ml.source.width, height: ml.source.height };")
    J("ml.property('Transform').property('Anchor Point').setValue([r1.width / 2, r1.height / 2]);")   # 기준점 = 가운데(안 하면 왼쪽 위에 붙음)
    fit = "Math.max" if place == "full" else "Math.min"
    J(f"var k1 = {fit}({W * pw} / r1.width, {H * ph} / r1.height) * 100; ml.property('Transform').property('Scale').setValue([k1, k1]); ml.property('Transform').property('Position').setValue([{W * px:.0f}, {H * py:.0f}]);")
    if place != "full":
        # 등장: 맞춘 크기(k1)의 92% → 100%, 투명 → 보임 (popIn 은 크기를 절대값 100% 로 키프레임해서 맞춘 크기를 덮어썼다)
        J(f"var ms1 = ml.property('Transform').property('Scale'); ms1.setValueAtTime({t0:.2f}, [k1 * 0.92, k1 * 0.92]); ms1.setValueAtTime({t0 + 0.25:.2f}, [k1, k1]); ease(ms1, 70);")
        if t0 > 0.05:   # 0초에 시작하는 재료는 처음부터 보이게 — 첫 프레임이 비면 피드에서 바로 넘겨진다(템포 검사 L32)
            J(f"var mo1 = ml.property('Transform').property('Opacity'); mo1.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); mo1.setValueAtTime({t0 + 0.15:.2f}, 100);")
        # 천천히 다가가기(정지 화면 방지)
        J(f"ml.property('Transform').property('Position').expression = 'value + [0, -18 * Math.min(1, Math.max(0, (time - {t0:.2f}) / {max(1.0, (t_out or sec) - t0):.2f}))]';")
    if t_out is not None and t_out < sec - 0.05:   # 다음 재료가 나오면 비킨다
        J(f"var mo = ml.property('Transform').property('Opacity'); mo.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, 100); mo.setValueAtTime({t_out:.2f}, 0);")


class Jsx:
    """JSX 문장 모음 — 사람이 읽을 수 있게 장면마다 주석을 남긴다"""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, s: str):
        self.lines.append(s)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


PRELUDE = r"""
function ease(prop, inf) { var e = new KeyframeEase(0, inf || 70); for (var k = 1; k <= prop.numKeys; k++) { var arr = []; for (var d = 0; d < (prop.value.length || 1); d++) arr.push(e); try { prop.setTemporalEaseAtKey(k, arr, arr); } catch (err) {} } }
function txt(comp, name, s, font, size, fill, stroke, strokeW, pos) {
  var t = comp.layers.addText(s); t.name = name;
  var d = t.property("Source Text").value;
  d.font = font; d.fontSize = size; d.applyFill = true; d.fillColor = fill; d.justification = ParagraphJustification.CENTER_JUSTIFY;
  if (stroke) { d.applyStroke = true; d.strokeColor = stroke; d.strokeWidth = strokeW; d.strokeOverFill = false; } else { d.applyStroke = false; }
  t.property("Source Text").setValue(d);
  t.property("Transform").property("Position").setValue(pos);
  return t;
}
function fitBox(comp, name, target, color, padX, padY, round) {
  var b = comp.layers.addShape(); b.name = name;
  var g = b.property("Contents").addProperty("ADBE Vector Group");
  var r = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
  r.property("Size").expression = "var q = thisComp.layer('" + target + "').sourceRectAtTime(time, false); [q.width + " + padX + ", q.height + " + padY + "]";
  r.property("Position").expression = "var q = thisComp.layer('" + target + "').sourceRectAtTime(time, false); [q.left + q.width / 2, q.top + q.height / 2]";
  r.property("Roundness").setValue(round);
  g.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  b.property("Transform").property("Position").expression = "thisComp.layer('" + target + "').transform.position";
  b.property("Transform").property("Scale").expression = "thisComp.layer('" + target + "').transform.scale";
  b.property("Transform").property("Opacity").expression = "thisComp.layer('" + target + "').transform.opacity";
  b.moveAfter(comp.layer(target));
  return b;
}
function card(comp, name, w, h, color, round) {
  var b = comp.layers.addShape(); b.name = name;
  var g = b.property("Contents").addProperty("ADBE Vector Group");
  var r = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
  r.property("Size").setValue([w, h]); r.property("Roundness").setValue(round);
  g.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  return b;
}
function popIn(layer, t, dur) {
  var s = layer.property("Transform").property("Scale"), o = layer.property("Transform").property("Opacity");
  s.setValueAtTime(t, [60, 60]); s.setValueAtTime(t + dur, [108, 108]); s.setValueAtTime(t + dur * 1.6, [100, 100]); ease(s, 60);
  o.setValueAtTime(Math.max(0, t - 0.001), 0); o.setValueAtTime(t + dur * 0.5, 100);
}
"""


NEUTRAL_BG = "#16151d"   # 레퍼런스가 없을 때(L30 예외) — 특정 색을 고르지 않은 어두운 중립


def ref_background(sb: dict) -> str | None:
    """콘티에 연결된 레퍼런스 쇼츠에서 배경 톤을 잰다.
    1) ref_style.py 카드(style/style.json)의 배경색이 있으면 그것
    2) 없으면 X-ray 가 남긴 장면 프레임(shots/*.jpg)의 위 · 아래 가장자리 색 중앙값 — 띠 배치(가운데 내용 · 위아래 단색)면 그 단색,
       화면 가득 영상이면 그 영상의 어두운 톤이 나온다"""
    import numpy as np
    from PIL import Image
    cols = []
    for rid in [r for r in (sb.get("reference") or []) if isinstance(r, str)]:
        d = ROOT / "public" / "trends" / "xray" / rid
        st = d / "style" / "style.json"
        if st.exists():
            try:
                bgc = (json.loads(st.read_text("utf-8")).get("layout") or {}).get("background")
                if isinstance(bgc, str) and bgc.startswith("#"):
                    return bgc
            except ValueError:
                pass
        for f in sorted((d / "shots").glob("*.jpg"))[:24]:
            try:
                a = np.asarray(Image.open(f).convert("RGB").resize((54, 96)), dtype=float)
            except OSError:
                continue
            edge = np.concatenate([a[:9].reshape(-1, 3), a[-9:].reshape(-1, 3)])
            cols.append(np.median(edge, axis=0))
    if not cols:
        return None
    c = np.median(np.array(cols), axis=0)
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


def build_jsx(sb: dict, captions: list[dict], scenes: list[dict], out_project: Path, *, width: int = 1080, height: int = 1920, fps: int = 30,
              font: str = "Pretendard-Black") -> str:
    """콘티 → JSX(EffectCraft 스크립트). 실행하면 out_project 에 .ecproj 가 저장된다"""
    sid = sb["id"]
    g = grammar(sb)
    d = sb.get("direction") or {}
    # 배경: 디자인 방향(direct.py) > 레퍼런스 쇼츠에서 잰 톤 > 중립 어두운색 (예전엔 늘 #0f4b7d 파랑이었다)
    bg = rgb(d.get("color_bg") or ref_background(sb) or NEUTRAL_BG)
    total = round(sum(float(s["sec"]) for s in sb["scenes"]), 3)
    W, H = width, height
    J = Jsx()
    J(PRELUDE)
    J(f"var main = app.project.items.addComp('Main', {W}, {H}, 1, {total}, {fps});")
    pills: list[dict] = []
    for k, (sc, tm) in enumerate(zip(sb["scenes"], scenes)):
        oi = int(tm.get("index", k))          # 원래 장면 번호(장면 일부만 렌더해도 재료 · 자막이 맞게)
        n = oi + 1
        start, end, sec = float(tm["start"]), float(tm["end"]), float(tm["sec"])
        words = [w for w in captions if w.get("scene") == oi] or [w for w in captions if start <= w["startMs"] / 1000 < end]
        name = f"S{n:02d} {ROLE_KO.get(sc.get('role'), sc.get('role') or '')}".strip()
        J(f"\n// ---------- 장면 {n}: {sc.get('beat', '')[:60]}")
        J(f"var c = app.project.items.addComp({js(name)}, {W}, {H}, 1, {sec}, {fps});")
        J(f"c.layers.addSolid({js(bg)}, 'BG', {W}, {H}, 1);")
        J("var cam = c.layers.addNull(); cam.name = 'Camera';")
        J(f"cam.property('Transform').property('Position').setValue([{W / 2}, {H / 2}]);")
        # 카메라: 장면 내내 천천히 밀기 + beats '확대' 에서 당기기
        zoom_at = None
        for b in sc.get("beats") or []:
            if b.get("do") == "확대":
                zoom_at = cue_time(b.get("at"), words, start, end)
                break
        J("var zs = cam.property('Transform').property('Scale');")
        if zoom_at is not None:
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({zoom_at}, [104, 104]); zs.setValueAtTime({min(sec, zoom_at + 0.6)}, [122, 122]); zs.setValueAtTime({sec}, [126, 126]); ease(zs, 75);")
        else:
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({sec}, [107, 107]); ease(zs, 40);")
        # 그림 층
        arts = art_files(sid, n)
        figs = [f for f in (sc.get("figures") or []) if isinstance(f, dict)]
        drew = [puppet(J, sid, f, sec, words, start, end, W, H, i) for i, f in enumerate(figs)]
        mats = scene_materials(sid, n, sc)
        if mats:
            colors = palette_list(sid)
            te0 = element(sc, "훅 제목", "제목")
            nl = len(quoted(te0.get("what", ""))) if te0 else 0
            top = (g["title"]["y"] + nl * g["title"]["h"] * 1.6 * 1.25 + 0.02) if nl else 0.2
            # 한 장면에 보이는 재료가 여럿이면 겹치지 않게 차례로: 각자 cue 낱말 시각부터 다음 재료가 나올 때까지(cue 가 없으면 장면을 나눠)
            seqs = [r for r in mats if r.get("type") != "text"]   # 차트도 차례에 넣는다(안 넣으면 그림과 겹침)
            slots = {}
            if len(seqs) == 1:   # 하나뿐이면 장면 처음부터 — 낱말을 기다리는 동안 화면이 비면 넘겨진다
                slots[seqs[0]["id"]] = (0.0, None)
            if len(seqs) > 1:
                ts = [cue_time((r.get("spec") or {}).get("cue"), words, start, end) for r in seqs]
                for k3, tt in enumerate(ts):
                    if tt is None:
                        ts[k3] = sec * k3 / len(seqs)
                ts[0] = min(ts[0], 0.0) if ts[0] is not None else 0.0
                order = sorted(range(len(seqs)), key=lambda k3: ts[k3])
                for o, k3 in enumerate(order):
                    nxt = ts[order[o + 1]] if o + 1 < len(order) else None
                    slots[seqs[k3]["id"]] = (ts[k3], nxt)
            for rec in mats:
                t_in, t_out = slots.get(rec["id"], (None, None))
                material_jsx(J, rec, words, start, end, sec, W, H, font, colors, top=top, bottom=g["subs"]["y"] - 0.03, t_in=t_in, t_out=t_out)
        elif any(drew):
            pass
        elif arts:
            for p in arts:
                J(f"var f = app.project.importFile(new ImportOptions(new File({js(str(p))})));")
                J("var a = c.layers.add(f);")
                J(f"var sz = a.sourceRectAtTime(0, false); var k = Math.max({W} / sz.width, {H} / sz.height) * 100; a.property('Transform').property('Scale').setValue([k, k]);")
                J(f"a.property('Transform').property('Position').setValue([{W / 2}, {H / 2}]); a.parent = cam;   // 화면 위치를 먼저, 부모는 나중(세계 좌표 유지)")
        else:
            # 재료가 없는 장면: 자리표시 상자 대신 이 장면의 핵심어로 화면을 짠다(목록이면 하나씩, 아니면 큰 낱말 하나)
            v = sc.get("visual") or {}
            items = [str(x) for x in (v.get("items") or []) if x][:4]
            key = str(v.get("primary") or "").strip() or (sc.get("caption") or "").split("\n")[0].strip()
            colors = palette_list(sid)
            if items:
                if key:
                    J(f"var kt = txt(c, 'Key', {js(key[:20])}, {js(font)}, 96, {js(colors[0])}, null, 0, [{W / 2}, {H * 0.3:.0f}]); popIn(kt, 0.1, 0.2); kt.parent = cam;")
                for k2, it in enumerate(items):
                    tk = cue_time(it, words, start, end)
                    tk = 0.35 + k2 * 0.45 if tk is None else tk
                    y = H * 0.42 + k2 * 150
                    J(f"var ib = card(c, {js(f'Item {k2 + 1}')}, {int(W * 0.72)}, 116, [1, 1, 1], 28); ib.property('Transform').property('Position').setValue([{W / 2}, {y:.0f}]); ib.property('Transform').property('Opacity').setValue(12); popIn(ib, {tk:.2f}, 0.18); ib.parent = cam;")
                    J(f"var it = txt(c, {js(f'Item text {k2 + 1}')}, {js(f'{k2 + 1}. {it}'[:24])}, {js(font)}, 60, [0.07, 0.09, 0.18], null, 0, [{W / 2}, {y + 20:.0f}]); popIn(it, {tk:.2f}, 0.18); it.parent = cam;")
            elif key:
                J(f"var kt = txt(c, 'Key', {js(key[:16])}, {js(font)}, 150, {js(colors[0])}, null, 0, [{W / 2}, {H * 0.45:.0f}]); popIn(kt, 0.1, 0.22); kt.parent = cam;")
        # 훅 제목 — 노란 상자에 한 줄씩 쌓임
        te = element(sc, "훅 제목", "제목")
        lines = quoted(te.get("what", "")) if te else []
        if lines:
            t0 = cue_time(te.get("cue"), words, start, end) or 0.05
            gt = g["title"]
            size = int(gt["h"] * H * 1.6)
            for i, line in enumerate(lines):
                y = gt["y"] * H + i * size * 1.25
                J(f"var tl = txt(c, 'Title {i + 1}', {js(line)}, {js(font)}, {size}, {js(rgb(gt.get('fg', '#111111')))}, null, 0, [{W / 2}, {y:.0f}]);")
                J(f"fitBox(c, 'TitleBox {i + 1}', 'Title {i + 1}', {js(rgb(gt.get('bg', '#ffd60a')))}, 48, 28, 8);")
                J(f"popIn(tl, {t0 + i * 0.4:.3f}, 0.18);")
                J(f"tl.property('Transform').property('Opacity').setValueAtTime({max(0.0, sec - 0.25):.3f}, 100); tl.property('Transform').property('Opacity').setValueAtTime({sec:.3f}, 0);")
        # 숫자 알약 — 레퍼런스 문법: 위쪽 가운데에 영상 내내 떠 있고 값만 굴러 바뀐다 → 장면이 아니라 Main 에 하나(아래에서 만듦)
        pe = element(sc, "숫자 알약", "알약")
        if pe:
            m = re.findall(r"[‘'\"“]([^’'\"”]+)[’'\"”]", pe.get("what", ""))
            num = m[-1] if m else None
            if num:
                t0 = cue_time(pe.get("cue"), words, start, end)
                pills.append({"t": round(start + (t0 if t0 is not None else 0.2), 3), "text": num, "color": pill_color(pe.get("what", ""), len(pills))})
        # 단어 자막
        gs = g["subs"]
        size = int(gs["h"] * H * 1.6)
        for i, ch in enumerate(chunks(words)):
            a_, b_ = max(0.0, ch["start"] - start), min(sec, ch["end"] - start)
            if b_ <= a_:
                continue
            J(f"var s = txt(c, {js(f'Sub {i + 1:02d}')}, {js(ch['text'])}, {js(font)}, {size}, {js(rgb(gs.get('fg', '#ffffff')))}, [0.05, 0.05, 0.08], {max(3, size // 9)}, [{W / 2}, {gs['y'] * H:.0f}]);")
            J(f"s.inPoint = {a_:.3f}; s.outPoint = {b_:.3f};")
        J(f"var sl = main.layers.add(c); sl.startTime = {start:.3f};")
    if pills:
        gp = g["pill"]
        size = int(gp["h"] * H * 1.5)
        y = gp["y"] * H + size * 0.35
        J("\n// ---------- 숫자 알약(영상 전체): 값이 바뀔 때마다 아래에서 굴러 올라옴")
        J(f"var pl = txt(main, 'PillText', {js(pills[0]['text'])}, {js(font)}, {size}, [1, 1, 1], null, 0, [{W / 2}, {y:.0f}]);")
        J("var pb = fitBox(main, 'Pill', 'PillText', [0.97, 0.15, 0.52], 90, 44, 100);")
        J("var src = pl.property('Source Text'), pp = pl.property('Transform').property('Position'), pc = pb.property('Contents').property(1).property('Contents').property(2).property('Color');")
        J(f"var po = pl.property('Transform').property('Opacity'); po.setValueAtTime(0, 0); po.setValueAtTime({max(0.0, pills[0]['t'] - 0.001):.3f}, 0); po.setValueAtTime({pills[0]['t'] + 0.15:.3f}, 100);")
        for i, e in enumerate(pills):
            t = e["t"]
            if i:   # 바뀌기 직전까지는 제자리(사이 보간으로 천천히 내려가지 않게)
                J(f"pp.setValueAtTime({t - 0.001:.3f}, [{W / 2}, {y:.0f}]);")
            J(f"var d = src.value; d.text = {js(e['text'])}; src.setValueAtTime({t:.3f}, d);")
            J(f"pp.setValueAtTime({t:.3f}, [{W / 2}, {y + size * 1.2:.0f}]); pp.setValueAtTime({t + 0.35:.3f}, [{W / 2}, {y:.0f}]);")
            J(f"pc.setValueAtTime({t:.3f}, {js(e['color'])});")
        J("ease(pp, 80);")
        # 도착한 뒤는 다음 변화까지 그대로(같은 값 두 키 사이 이동 경로가 곡선으로 휘어 처지지 않게)
        J("var arrive = [" + ", ".join(f"{e['t'] + 0.35:.3f}" for e in pills) + "];")
        J("for (var a = 0; a < arrive.length; a++) { var ki = pp.nearestKeyIndex(arrive[a]); pp.setInterpolationTypeAtKey(ki, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.HOLD); }")
        J("for (var k = 1; k <= pc.numKeys; k++) pc.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);   // 색은 한 번에 바뀜")
    J(f"app.project.save(new File({js(str(out_project))}));")
    J("writeLn('saved ' + main.numLayers);")
    return J.text()
