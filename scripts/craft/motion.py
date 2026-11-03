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
    recs = [r for r in recs if isinstance(r, dict) and r.get("type") and r.get("key") and not r.get("missing")]   # 재료 기록만(보조 파일 · 사용자 녹화 대기 제외)
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
                 top: float = 0.0, bottom: float = 0.74, t_in: float | None = None, t_out: float | None = None, layout: str = "card") -> None:
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
        x0, x1, base = 0.16 * W, 0.84 * W, bottom * H - 140           # 아래: 항목 이름 자리(자막과 떨어지게 — 예전엔 자막에 닿았다)
        hmax = max(0.10 * H, base - (top + title_h) * H - 110)        # 위: 제목 + 값 글자 자리
        bw = (x1 - x0) / n * 0.62
        best = vals.index(max(vals)) if vals else -1
        if data.get("title"):
            J(f"var ct = txt(c, {js('Chart title ' + mid)}, {js(data['title'])}, {js(font)}, 60, [1, 1, 1], null, 0, [{W / 2}, {(top + 0.03) * H:.0f}]); popIn(ct, {max(0.0, t0 - 0.1):.2f}, 0.18);")
        for i, (v, lab) in enumerate(zip(vals, labs)):
            cx = x0 + (x1 - x0) * (i + 0.5) / n
            hh = max(8.0, hmax * v / vmax)
            col = colors[i % len(colors)]
            ti = t0 + i * 0.15
            J(f"var b = card(c, {js(f'Bar {mid} {i}')}, {bw:.0f}, {hh:.0f}, {js(col)}, 12); b.property('Transform').property('Anchor Point').setValue([0, {hh / 2:.0f}]); b.property('Transform').property('Position').setValue([{cx:.0f}, {base:.0f}]);")
            J(f"var bs = b.property('Transform').property('Scale'); bs.setValueAtTime({ti:.2f}, [100, 0]); bs.setValueAtTime({ti + 0.55:.2f}, [100, 100]); ease(bs, 80);")
            J(f"var vt = txt(c, {js(f'Value {mid} {i}')}, '0', {js(font)}, {84 if i == best else 64}, {js([1, 0.84, 0.04] if i == best else [1, 1, 1])}, null, 0, [{cx:.0f}, {base - hh - 28:.0f}]);")
            J(f"vt.property('Source Text').expression = 'var v = linear(time, {ti:.2f}, {ti + 0.55:.2f}, 0, {v}); (Math.round(v * 10) / 10) + {js(unit)}';")
            J(f"vt.property('Transform').property('Opacity').setValueAtTime({max(0.0, ti - 0.01):.2f}, 0); vt.property('Transform').property('Opacity').setValueAtTime({ti + 0.1:.2f}, 100);")
            J(f"var lb = txt(c, {js(f'Label {mid} {i}')}, {js(str(lab))}, {js(font)}, 46, [0.92, 0.92, 0.95], null, 0, [{cx:.0f}, {base + 62:.0f}]); var lbo = lb.property('Transform').property('Opacity'); lbo.setValueAtTime({max(0.0, ti - 0.01):.2f}, 0); lbo.setValueAtTime({ti + 0.2:.2f}, 100);")
        if t_out is not None and t_out < sec - 0.05:   # 다음 재료가 나오면 차트 전체(막대 · 숫자 · 이름 · 제목)가 비킨다
            J(f"for (var li = 1; li <= c.numLayers; li++) {{ var Lc = c.layer(li); if (/ {mid}( |$)/.test(Lc.name)) {{ var oc = Lc.property('Transform').property('Opacity'); oc.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, 100); oc.setValueAtTime({t_out:.2f}, 0); }} }}")
        return
    if typ == "stat":
        # 숫자 덧씌우기(레퍼런스 문법): 카드 · 패널 없이 아래 재료 위에 바로 — 화면을 살짝 어둡게 하고 테두리 굵은 큰 숫자,
        # 위에 흰 설명 한 줄. 출처는 화면에 쓰지 않는다(설명란 '사용한 자료'로). 2026-11-03: 어두운 둥근 카드가 'AI 티'
        val = str(sp.get("value") or "")
        mnum = re.match(r"\s*([+\-]?)([\d.,]+)(.*)$", val)
        cy = (top + bottom) / 2 * H
        t1 = t_out if t_out is not None else sec
        J(f"var sd0 = c.layers.addSolid([0, 0, 0], {js('Dim ' + mid)}, {W}, {H}, 1); var sdo = sd0.property('Transform').property('Opacity');")
        J(f"sdo.setValueAtTime(0, 0); sdo.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); sdo.setValueAtTime({t0 + 0.1:.2f}, 68); sdo.setValueAtTime({max(t0 + 0.15, t1 - 0.15):.2f}, 68); sdo.setValueAtTime({t1:.2f}, 0);")
        size = min(300, int(W * 1.0 / max(2.5, len(val))))
        J(f"var sv0 = txt(c, {js('Value ' + mid)}, {js(val)}, {js(font)}, {size}, [1, 0.84, 0.04], [0.02, 0.02, 0.05], {max(12, size // 9)}, [{W / 2}, {cy + size * 0.2:.0f}]);")
        # 등장: 크게 → 제자리(쿵) — 모든 재료가 같은 '살짝 커지기'로 나오지 않게
        J(f"var svs = sv0.property('Transform').property('Scale'); svs.setValueAtTime({max(0.0, t0 - 0.01):.2f}, [150, 150]); svs.setValueAtTime({t0 + 0.12:.2f}, [96, 96]); svs.setValueAtTime({t0 + 0.2:.2f}, [100, 100]);")
        if sp.get("label"):
            lab = str(sp["label"])
            lsz = max(44, min(72, int(W * 0.86 / max(1, len(lab)) * 1.1)))
            J(f"var sl0 = txt(c, {js('Label ' + mid)}, {js(lab)}, {js(font)}, {lsz}, [1, 1, 1], [0.02, 0.02, 0.05], {max(6, lsz // 7)}, [{W / 2}, {cy - size * 0.55:.0f}]);")
            J(f"var sls = sl0.property('Transform').property('Position'); sls.setValueAtTime({t0:.2f}, [{W / 2 - 60}, {cy - size * 0.55:.0f}]); sls.setValueAtTime({t0 + 0.2:.2f}, [{W / 2}, {cy - size * 0.55:.0f}]); ease(sls, 80);")
        for L in ("sv0",) + (("sl0",) if sp.get("label") else ()):
            J(f"var lo_ = {L}.property('Transform').property('Opacity'); lo_.setValueAtTime(0, 0); lo_.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); lo_.setValueAtTime({t0 + 0.06:.2f}, 100); lo_.setValueAtTime({max(t0 + 0.1, t1 - 0.12):.2f}, 100); lo_.setValueAtTime({t1:.2f}, 0);")
        if mnum:
            sign, digits, rest = mnum.group(1), mnum.group(2).replace(",", ""), mnum.group(3)
            dec = len(digits.split(".")[1]) if "." in digits else 0
            try:
                target = float(digits)
                J(f"sv0.property('Source Text').expression = 'var v = linear(time, {t0:.2f}, {t0 + 0.5:.2f}, 0, {target}); {js(sign)} + v.toFixed({dec}) + {js(rest)}';")
            except ValueError:
                pass
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
    if path.suffix.lower() in (".mp4", ".mov", ".webm"):
        J(f"try {{ ml.startTime = {t0:.2f}; }} catch (e) {{}}")   # 녹화는 등장하는 순간부터 재생
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
    # 배치: 콘티가 정하지 않으면 레퍼런스 화면 문법(layout)을 따른다 — 화면 가득(full) 이면 사진 · 캡처 · 영상도 화면 가득
    # 'center' 는 사실상 기본값이라 레퍼런스가 화면 가득이면 화면 가득으로 본다. left · right · top · bottom · card 처럼 뜻이 있는 배치만 지킨다
    place = sp.get("place") or "center"
    if typ in ("screen", "video", "web") and place == "center":
        place = "full"
    if layout == "full" and typ in ("image", "photo") and place == "center":
        place = "full"
    if place == "card":
        place = "center"
    if place == "full" and typ in ("image", "photo", "illustration", "web", "screen", "video"):
        full_still(J, rec, words, start, end, sec, W, H, t0, t_out, bottom, font)
        return
    px, py, pw, ph = PLACE.get(place, PLACE["center"])
    if place != "full":                      # 남은 세로 구간 안으로
        py, ph = top + (bottom - top) * (py - 0.15) / 0.7, min(ph, (bottom - top) * 0.92)
    # 크기 · 기준점은 소스의 실제 픽셀 크기로(sourceRectAtTime 은 PNG 해상도 정보에 따라 달라 그림이 커졌다)
    J("var r1 = { left: 0, top: 0, width: ml.source.width, height: ml.source.height };")
    J("ml.property('Transform').property('Anchor Point').setValue([r1.width / 2, r1.height / 2]);")   # 기준점 = 가운데(안 하면 왼쪽 위에 붙음)
    fit = "Math.max" if place == "full" else "Math.min"
    if typ == "icon":                        # 로고는 작게(가운데 칸의 절반) — 흰 타일 위에
        pw, ph = pw * 0.5, ph * 0.5
    J(f"var k1 = {fit}({W * pw} / r1.width, {H * ph} / r1.height) * 100; ml.property('Transform').property('Scale').setValue([k1, k1]); ml.property('Transform').property('Position').setValue([{W * px:.0f}, {H * py:.0f}]);")
    if typ == "icon":
        # 흰 둥근 타일(앱 아이콘처럼): 로고 색이 배경에 묻히지 않게. 로고에 붙여(parent) 같이 커지고 움직인다
        J(f"var tl = card(c, {js('Tile ' + mid)}, r1.width * 1.6, r1.height * 1.6, [1, 1, 1], r1.width * 0.36); tl.moveAfter(ml); tl.parent = ml; tl.property('Transform').property('Scale').setValue([100, 100]); tl.property('Transform').property('Anchor Point').setValue([0, 0]); tl.property('Transform').property('Position').setValue([r1.width / 2, r1.height / 2]); tl.inPoint = {t0:.2f};")
        if t_out is not None:
            J(f"tl.outPoint = {t_out:.2f};")
    if place != "full":
        # 등장: 맞춘 크기(k1)의 92% → 100%, 투명 → 보임 (popIn 은 크기를 절대값 100% 로 키프레임해서 맞춘 크기를 덮어썼다)
        J(f"var ms1 = ml.property('Transform').property('Scale'); ms1.setValueAtTime({t0:.2f}, [k1 * 0.92, k1 * 0.92]); ms1.setValueAtTime({t0 + 0.25:.2f}, [k1, k1]); ease(ms1, 70);")
        if t0 > 0.05:   # 0초에 시작하는 재료는 처음부터 보이게 — 첫 프레임이 비면 피드에서 바로 넘겨진다(템포 검사 L32)
            J(f"var mo1 = ml.property('Transform').property('Opacity'); mo1.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); mo1.setValueAtTime({t0 + 0.15:.2f}, 100);")
        # 천천히 다가가기(정지 화면 방지)
        J(f"ml.property('Transform').property('Position').expression = 'value + [0, -18 * Math.min(1, Math.max(0, (time - {t0:.2f}) / {max(1.0, (t_out or sec) - t0):.2f}))]';")
    if t_out is not None and t_out < sec - 0.05:   # 다음 재료가 나오면 비킨다
        J(f"var mo = ml.property('Transform').property('Opacity'); mo.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, 100); mo.setValueAtTime({t_out:.2f}, 0);")


def _norm(t: str) -> str:
    return re.sub(r"[\s,.!?·'\"’”“()]+", "", str(t)).lower()


def focus_events(rec: dict, words: list[dict], start: float, t0: float, t_out: float | None, sec: float) -> list[dict]:
    """나레이션이 캡처 속 글자(숫자 · 낱말)를 말하는 순간 → 그 글자 상자로 확대 · 동그라미.
    재료 단계가 남긴 글자 인식 결과(rec["ocr"]: [{text, box(0~1)}])와 단어 시각을 맞춘다. 재료 하나에 최대 3번"""
    ocr = [o for o in (rec.get("ocr") or []) if o.get("text") and o.get("box")]
    if not ocr:
        return []
    end_t = t_out if t_out is not None else sec
    out, used = [], set()
    for w in words:
        tw = w["startMs"] / 1000 - start
        if tw < t0 + 0.4 or tw > end_t - 0.6:
            continue
        key = _norm(w.get("text") or "")
        key = re.sub(r"(은|는|이|가|을|를|에|의|도|로|으로|요|죠|예요|이에요)$", "", key)
        if len(key) < 2 or not (re.search(r"\d", key) or len(key) >= 3):
            continue
        for k, o in enumerate(ocr):
            if k in used or key not in _norm(o["text"]):
                continue
            x, y, bw, bh = o["box"]
            if bw > 0.9 or bh > 0.3:          # 거의 전체 문단이면 짚을 의미가 없다
                continue
            used.add(k)
            out.append({"t": round(tw, 2), "box": [x, y, bw, bh], "text": o["text"]})
            break
        if len(out) >= 3:
            break
    # 너무 붙은 짚기는 하나만(1.2초 간격)
    keep = []
    for e in out:
        if not keep or e["t"] - keep[-1]["t"] >= 1.2:
            keep.append(e)
    return keep


def full_still(J, rec: dict, words: list[dict], start: float, end: float, sec: float, W: int, H: int, t0: float, t_out: float | None, bottom: float, font: str = "") -> None:
    """화면 가득 문법(레퍼런스): 그림을 폭에 꽉 채우고, 남는 위아래는 같은 그림을 크게 흐리게 깔아 채운다.
    천천히 다가가고(정지 방지), 말이 캡처 속 글자를 짚으면 그곳으로 확대 + 노란 동그라미, 세로로 긴 캡처는 1.5초마다 아래로 훑는다"""
    mid = rec["id"]
    end_t = t_out if t_out is not None else sec
    # 흐린 그림 배경은 쓰지 않는다 — 재료마다 밝기가 달라 화면 전체가 번쩍였다(2026-11-03: 0.07초 사이 4 ↔ 82, 30초에 18번). 배경은 장면 내내 같은 어두운 그라데이션
    J("var r1 = { width: ml.source.width, height: ml.source.height }; ml.property('Transform').property('Anchor Point').setValue([r1.width / 2, r1.height / 2]);")
    # 폭에 꽉(조금 여백) — 세로로 너무 길면 화면 높이의 82% 까지만 보이고 나머지는 훑는다
    J(f"var k1 = {W * 0.96} / r1.width * 100; var hh = r1.height * k1 / 100; var cy = {H * 0.45:.0f};")
    phone = rec.get("type") in ("web", "screen", "video") and (rec.get("mobile") or (rec.get("spec") or {}).get("mobile"))
    if phone:
        # 폰 화면 녹화: 세로 화면을 가득(레퍼런스처럼 액자 없이) — 자막 · 단계 꼬리표가 그 위에
        J(f"k1 = Math.max({W} / r1.width, {H} / r1.height) * 100; hh = r1.height * k1 / 100; cy = {H / 2};")
    J("ml.property('Transform').property('Scale').setValue([k1, k1]); ml.property('Transform').property('Position').setValue([" + f"{W / 2}" + ", cy]);")
    if not phone:
        J("try { var dsh = ml.property('Effects').addProperty('ADBE Drop Shadow'); dsh.property('Opacity').setValue(70); dsh.property('Distance').setValue(18); dsh.property('Softness').setValue(60); dsh.property('Direction').setValue(180); } catch (e) {}")
    for k, stp in enumerate(rec.get("steps") or []):
        # 단계 꼬리표('1. 주소 입력'): 그 동작이 화면에 나오는 순간 — 아래쪽 보라 알약(레퍼런스 문법)
        ts = t0 + float(stp["t"])
        te_ = min(end_t, t0 + float(stp.get("t_end", stp["t"] + 1.2)))
        if not stp.get("label") or ts >= end_t - 0.2:
            continue
        J(f"var sp{k} = txt(c, {js(f'Step {mid} {k}')}, {js(str(stp['label']))}, {js(font)}, 64, [1, 1, 1], null, 0, [{W / 2}, {H * 0.64:.0f}]);")
        J(f"var sb{k} = fitBox(c, {js(f'StepBox {mid} {k}')}, {js(f'Step {mid} {k}')}, [0.42, 0.36, 0.95], 26, 34, 16);")
        for L in (f"sp{k}", f"sb{k}"):
            J(f"var so_ = {L}.property('Transform').property('Opacity'); so_.setValueAtTime(0, 0); so_.setValueAtTime({max(0.0, ts - 0.01):.2f}, 0); so_.setValueAtTime({ts + 0.08:.2f}, 100); so_.setValueAtTime({max(ts + 0.1, te_ - 0.08):.2f}, 100); so_.setValueAtTime({te_:.2f}, 0);")
    if t0 > 0.05:
        for L in ("ml",):
            J(f"var o_ = {L}.property('Transform').property('Opacity'); o_.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); o_.setValueAtTime({t0 + 0.2:.2f}, 100);")
    if t_out is not None and t_out < sec - 0.05:
        for L in ("ml",):
            J(f"var oo_ = {L}.property('Transform').property('Opacity'); oo_.setValueAtTime({max(t0 + 0.25, t_out - 0.2):.2f}, 100); oo_.setValueAtTime({t_out:.2f}, 0);")
    if phone:
        # 자막 그림자: 밝은 화면 위 자막이 읽히게 아래쪽을 부드럽게 어둡게(가장자리는 흐림으로 풀어서)
        J(f"var shd = card(c, {js('Shade ' + mid)}, {W * 1.4:.0f}, {H * 0.36:.0f}, [0, 0, 0], 0); shd.property('Transform').property('Position').setValue([{W / 2}, {H * 0.9:.0f}]);")
        J("try { var sbl = shd.property('Effects').addProperty('ADBE Gaussian Blur 2'); sbl.property(1).setValue(120); } catch (e) {}")
        J(f"var sho = shd.property('Transform').property('Opacity'); sho.setValueAtTime(0, 0); sho.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); sho.setValueAtTime({t0 + 0.2:.2f}, 62);")
        if t_out is not None and t_out < sec - 0.05:
            J(f"sho.setValueAtTime({max(t0 + 0.25, t_out - 0.2):.2f}, 62); sho.setValueAtTime({t_out:.2f}, 0);")
        return            # 폰 화면은 확대 · 훑기 없이 그대로(녹화 자체가 움직인다)
    ev = focus_events(rec, words, start, t0, t_out, sec)
    J("var ps = ml.property('Transform').property('Position'), ss = ml.property('Transform').property('Scale');")
    J(f"ss.setValueAtTime({t0:.2f}, [k1, k1]); ps.setValueAtTime({t0:.2f}, [{W / 2}, cy]);")
    if ev:
        for n, e in enumerate(ev):
            x, y, bw, bh = e["box"]
            tf = e["t"]
            # 짚을 글자 상자의 가운데를 화면 가운데(위쪽 45%)로, 상자 폭이 화면의 60% 가 되게(최대 2.6배)
            J(f"var bx = {x + bw / 2:.4f} * r1.width, by = {y + bh / 2:.4f} * r1.height, bwp = {bw:.4f} * r1.width;")
            J(f"var kz = Math.max(k1, Math.min(k1 * 2.6, {W * 0.6} / bwp * 100));")
            J(f"ss.setValueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, ss.valueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, false)); ps.setValueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, ps.valueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, false));")
            J(f"ss.setValueAtTime({tf + 0.35:.2f}, [kz, kz]); ps.setValueAtTime({tf + 0.35:.2f}, [{W / 2} - (bx - r1.width / 2) * kz / 100, {H * 0.42:.0f} - (by - r1.height / 2) * kz / 100]);")
            # 노란 동그라미: 그림의 자식 레이어(그림 좌표) — 확대 · 이동을 같이 따라간다
            J(f"var rg = c.layers.addShape(); rg.name = {js(f'Ring {mid} {n}')}; var rgg = rg.property('Contents').addProperty('ADBE Vector Group');")
            J(f"var rge = rgg.property('Contents').addProperty('ADBE Vector Shape - Ellipse'); rge.property('Size').setValue([bwp * 1.25 + 30, {bh:.4f} * r1.height * 2.0 + 30]);")
            J("var rgs = rgg.property('Contents').addProperty('ADBE Vector Graphic - Stroke'); rgs.property('Color').setValue([1, 0.84, 0.04]); rgs.property('Stroke Width').setValue(10 * 100 / kz);")
            J("rg.parent = ml; rg.property('Transform').property('Position').setValue([bx, by]);")
            end_r = ev[n + 1]["t"] - 0.2 if n + 1 < len(ev) else end_t
            J(f"rg.inPoint = {tf + 0.25:.2f}; rg.outPoint = {max(tf + 0.6, end_r):.2f};")
            J(f"var rgsc = rg.property('Transform').property('Scale'); rgsc.setValueAtTime({tf + 0.25:.2f}, [40, 40]); rgsc.setValueAtTime({tf + 0.5:.2f}, [100, 100]); ease(rgsc, 70);")
        J("ease(ss, 80); ease(ps, 80);")
    elif not rec.get("_under_overlay") and len([o for o in (rec.get("ocr") or []) if o.get("box") and o["box"][2] < 0.95]) >= 3 and end_t - t0 >= 2.4:
        # 짚을 낱말이 없으면: 글자 줄을 1.5초마다 차례로 따라가며 확대(사람이 문서를 읽어 주듯) — 화면이 1~2초마다 바뀐다
        lines = [o for o in rec["ocr"] if o.get("box") and o["box"][2] < 0.95 and o["box"][3] < 0.2]
        n_st = max(1, min(len(lines), int((end_t - t0 - 0.6) // 1.5)))
        pick = [lines[round(k * (len(lines) - 1) / max(1, n_st - 1))] for k in range(n_st)] if n_st > 1 else lines[:1]
        for k, o in enumerate(pick):
            x, y, bw, bh = o["box"]
            tf = t0 + 0.6 + k * 1.5
            J(f"var bx = {x + bw / 2:.4f} * r1.width, by = {y + bh / 2:.4f} * r1.height;")
            J(f"var kz = Math.max(k1 * 1.25, Math.min(k1 * 1.9, {W * 0.9} / ({bw:.4f} * r1.width) * 100));")
            J(f"ss.setValueAtTime({tf:.2f}, ss.valueAtTime({tf:.2f}, false)); ps.setValueAtTime({tf:.2f}, ps.valueAtTime({tf:.2f}, false));")
            J(f"ss.setValueAtTime({tf + 0.4:.2f}, [kz, kz]); ps.setValueAtTime({tf + 0.4:.2f}, [{W / 2} - (bx - r1.width / 2) * kz / 100, {H * 0.43:.0f} - (by - r1.height / 2) * kz / 100]);")
        J("ease(ss, 80); ease(ps, 80);")
    else:
        # 짚을 글자가 없으면: 세로로 길면 1.5초마다 아래로 훑고, 아니면 천천히 다가간다
        J(f"var over = hh - {H * 0.82:.0f};")
        steps = max(1, int((end_t - t0) // 1.5))
        J(f"if (over > 40) {{ var y0 = cy + hh / 2 - {H * 0.41:.0f}; ps.setValueAtTime({t0:.2f}, [{W / 2}, y0]); for (var st = 1; st <= {steps}; st++) {{ var tt = {t0:.2f} + st * {(end_t - t0) / (steps + 1):.3f}; ps.setValueAtTime(tt - 0.01, [{W / 2}, y0 - over * (st - 1) / {steps}]); ps.setValueAtTime(tt + 0.45, [{W / 2}, y0 - over * st / {steps}]); }} ease(ps, 80); }}")
        J(f"ss.setValueAtTime({end_t:.2f}, [k1 * 1.07, k1 * 1.07]);")


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
function glow(c, name, color, size, opa, x, y, sx, sy, sp, ph, off) {
  var g = c.layers.addShape(); g.name = name;
  var grp = g.property("Contents").addProperty("ADBE Vector Group");
  grp.property("Contents").addProperty("ADBE Vector Shape - Ellipse").property("Size").setValue([size, size]);
  grp.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  try { g.property("Effects").addProperty("ADBE Gaussian Blur 2").property(1).setValue(size * 0.35); } catch (e) {}
  g.property("Transform").property("Opacity").setValue(opa);
  g.property("Transform").property("Position").expression = "var T = time + " + off + "; [" + x + " + " + sx + " * Math.sin(T * " + sp + " + " + ph + "), " + y + " + " + sy + " * Math.cos(T * " + (sp * 0.8) + " + " + ph + ")]";
  g.property("Transform").property("Scale").expression = "var T = time + " + off + "; var s = 100 + 8 * Math.sin(T * " + (sp * 1.3) + " + " + ph + "); [s, s]";
  return g;
}
// 배경 움직임(엔진 기능): 바탕 그라데이션 + 천천히 떠다니는 빛 두 개 + 아주 옅은 질감. off = 장면 시작 시각(장면이 바뀌어도 빛이 이어 움직임)
function dressBg(c, bg, off, top, bottom, ga, gb) {
  try { var r = bg.property("Effects").addProperty("ADBE Ramp"); r.property(1).setValue([540, 0]); r.property(2).setValue(top); r.property(3).setValue([540, 1920]); r.property(4).setValue(bottom); } catch (e) {}
  var g1 = glow(c, "Glow A", ga, 900, 11, 180, 380, 90, 70, 0.18, 0.0, off);
  var g2 = glow(c, "Glow B", gb, 820, 8, 920, 1500, 80, 90, 0.15, 2.1, off);
  g1.moveBefore(bg); g2.moveBefore(bg);
  try { var t = c.layers.addSolid([0.5, 0.5, 0.5], "Texture noise", 1080, 1920, 1); var fn = t.property("Effects").addProperty("ADBE Fractal Noise");
        try { fn.property("Evolution").expression = "(time + " + off + ") * 60"; } catch (e) {}
        t.property("Transform").property("Opacity").setValue(3); t.moveBefore(bg); } catch (e) {}
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


def ref_layout(sb: dict) -> str:
    """레퍼런스 화면 문법: 'full'(화면 가득 영상 · 캡처) 또는 'card'(단색 바탕 가운데 띠).
    스타일 카드(ref_style)의 띠 비율이 있으면 그것, 없으면 장면 프레임의 위 · 아래 가장자리가 단색인지(표준편차)로 본다"""
    import numpy as np
    from PIL import Image
    votes = []
    for rid in [r for r in (sb.get("reference") or []) if isinstance(r, str)]:
        d = ROOT / "public" / "trends" / "xray" / rid
        st = d / "style" / "style.json"
        if st.exists():
            try:
                lb = (json.loads(st.read_text("utf-8")).get("layout") or {}).get("letterbox_ratio")
                if lb is not None:
                    votes.append("card" if lb > 0.5 else "full")
                    continue
            except ValueError:
                pass
        for f in sorted((d / "shots").glob("*.jpg"))[:24]:
            try:
                a = np.asarray(Image.open(f).convert("L").resize((54, 96)), dtype=float)
            except OSError:
                continue
            edge = np.concatenate([a[:10].ravel(), a[-10:].ravel()])
            votes.append("card" if edge.std() < 14 else "full")
    if not votes:
        return "card"
    return "full" if votes.count("full") >= votes.count("card") else "card"


def build_jsx(sb: dict, captions: list[dict], scenes: list[dict], out_project: Path, *, width: int = 1080, height: int = 1920, fps: int = 30,
              font: str = "Pretendard-Black") -> str:
    """콘티 → JSX(EffectCraft 스크립트). 실행하면 out_project 에 .ecproj 가 저장된다"""
    sid = sb["id"]
    g = grammar(sb)
    d = sb.get("direction") or {}
    # 배경: 디자인 방향(direct.py) > 레퍼런스 쇼츠에서 잰 톤 > 중립 어두운색 (예전엔 늘 #0f4b7d 파랑이었다)
    bg = rgb(d.get("color_bg") or ref_background(sb) or NEUTRAL_BG)
    layout = d.get("layout") or ref_layout(sb)            # 레퍼런스 화면 문법: full(화면 가득) · card(가운데 띠)
    pal = palette_list(sid)
    bg_top = [round(v * 0.62, 4) for v in bg]                 # 배경 그라데이션: 위는 어둡게, 아래는 강조색을 조금 섞어
    bg_bot = [round(min(1.0, v * 0.85 + a * 0.15), 4) for v, a in zip(bg, pal[1] if len(pal) > 1 else bg)]
    glow_a, glow_b = (pal[1] if len(pal) > 1 else [1, 0.24, 0.42]), (pal[2] if len(pal) > 2 else [0.08, 0.78, 0.82])
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
        J(f"var bgL = c.layers.addSolid({js(bg)}, 'BG', {W}, {H}, 1);")
        if d.get("bg_motion", True):   # 배경 움직임(엔진 기능) — 사람이 프로젝트 파일에 손으로 넣지 않아도 되게
            J(f"dressBg(c, bgL, {start:.3f}, {js(bg_top)}, {js(bg_bot)}, {js(glow_a)}, {js(glow_b)});")
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
            seqs = [r for r in mats if r.get("type") not in ("text", "stat")]   # 차트도 차례에 넣는다(안 넣으면 그림과 겹침) · 숫자(stat)는 덧씌우기
            slots = {}
            cues_all = sorted(t for t in (cue_time((r.get("spec") or {}).get("cue"), words, start, end) for r in mats) if t is not None)
            for r in mats:
                if r.get("type") == "stat":     # 덧씌우기: 그 낱말부터 다음 재료가 나올 때까지(최대 2.4초)
                    ti = cue_time((r.get("spec") or {}).get("cue"), words, start, end) or 0.0
                    nx = [t for t in cues_all if t > ti + 0.3]
                    slots[r["id"]] = (ti, min(ti + 2.4, nx[0]) if nx else sec)   # 마지막 덧씌우기는 장면 끝까지
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
            if any(r.get("type") == "stat" for r in mats):
                for r in seqs:
                    r["_under_overlay"] = True      # 숫자를 덧씌우는 장면의 바탕 재료는 줄 따라 확대하지 않는다(어지러움)
            for rec in sorted(mats, key=lambda r: r.get("type") == "stat"):   # 숫자 덧씌우기는 맨 나중(위)에
                t_in, t_out = slots.get(rec["id"], (None, None))
                material_jsx(J, rec, words, start, end, sec, W, H, font, colors, top=top, bottom=g["subs"]["y"] - 0.03, t_in=t_in, t_out=t_out, layout=layout)
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
        # 숫자 펀치: 나레이션이 숫자를 말하는 순간 화면을 살짝 어둡게 하고 큰 숫자를 0.9초 — 장면마다 한 번(제목 상자에 같은 숫자가 있으면 건너뜀)
        title_txt = " ".join(quoted((element(sc, "훅 제목", "제목") or {}).get("what", "")))
        has_num_mat = any(m.get("type") in ("stat", "chart") for m in sc.get("materials") or [])
        if d.get("number_punch", True) and not has_num_mat:     # 숫자 재료가 있는 장면은 그 재료가 숫자를 보여 준다
            cands = []
            shown_nums = set()
            for m in sc.get("materials") or []:
                if m.get("type") == "stat":
                    shown_nums.update(re.findall(r"\d[\d.,]*", str(m.get("value") or "")))
            for r in scene_materials(sb["id"], n, sc):
                if r.get("type") == "chart":
                    shown_nums.update(str(v).rstrip("0").rstrip(".") if "." in str(v) else str(v) for v in ((r.get("data") or {}).get("values") or []))
            for w in words:
                mnum = re.search(r"\d[\d.,]*\s*(%|퍼센트|초|배|개|명|원|만|억)?", w.get("text") or "")
                tw = w["startMs"] / 1000 - start
                if not mnum or tw < 0.3 or tw > sec - 1.0 or mnum.group(0).strip() in title_txt:
                    continue
                num = mnum.group(0).strip().replace("퍼센트", "%")
                if num.rstrip("%초배개명원만억") in shown_nums:      # 수치 카드 · 차트가 이미 그 숫자를 크게 보여 준다
                    continue
                unit = mnum.group(1) or ""
                rank = 0 if unit in ("%", "퍼센트") else 1 if unit in ("배", "개", "명", "원", "만", "억") else 2   # 퍼센트 > 배 · 개 > 초
                cands.append((rank, tw, num))
            if cands:
                _, tw, num = sorted(cands)[0]
                J(f"var dim = c.layers.addSolid([0, 0, 0], 'Punch dim', {W}, {H}, 1); dim.inPoint = {tw:.2f}; dim.outPoint = {tw + 0.95:.2f}; var dO = dim.property('Transform').property('Opacity'); dO.setValueAtTime({tw:.2f}, 0); dO.setValueAtTime({tw + 0.1:.2f}, 55); dO.setValueAtTime({tw + 0.8:.2f}, 55); dO.setValueAtTime({tw + 0.95:.2f}, 0);")
                J(f"var pn = txt(c, 'Punch', {js(num)}, {js(font)}, {min(300, int(W * 1.1 / max(2, len(num))))}, [1, 0.84, 0.04], [0.02, 0.02, 0.05], 14, [{W / 2}, {H * 0.47:.0f}]); pn.inPoint = {tw:.2f}; pn.outPoint = {tw + 0.95:.2f};")
                J(f"var pS = pn.property('Transform').property('Scale'); pS.setValueAtTime({tw:.2f}, [55, 55]); pS.setValueAtTime({tw + 0.12:.2f}, [112, 112]); pS.setValueAtTime({tw + 0.22:.2f}, [100, 100]); pS.setValueAtTime({tw + 0.95:.2f}, [104, 104]);")
                J(f"var pO = pn.property('Transform').property('Opacity'); pO.setValueAtTime({tw + 0.8:.2f}, 100); pO.setValueAtTime({tw + 0.95:.2f}, 0);")
        # 자막: 구절 단위(레퍼런스는 한 번에 한 구절을 크게) — 숫자 · 핵심어가 든 구절은 노란색
        gs = g["subs"]
        size = int(gs["h"] * H * 1.75)
        keys = [_norm(x) for x in re.findall(r"[가-힣A-Za-z0-9.%+]{2,}", str((sc.get("visual") or {}).get("primary") or ""))]
        for i, ch in enumerate(chunks(words, max_chars=13, max_words=4)):
            a_, b_ = max(0.0, ch["start"] - start), min(sec, ch["end"] - start)
            if b_ <= a_:
                continue
            hot = bool(re.search(r"\d", ch["text"])) or any(k and k in _norm(ch["text"]) for k in keys)
            fg = [1.0, 0.84, 0.04] if hot else rgb(gs.get("fg", "#ffffff"))
            J(f"var s = txt(c, {js(f'Sub {i + 1:02d}')}, {js(ch['text'])}, {js(font)}, {size}, {js(fg)}, [0.02, 0.02, 0.05], {max(6, size // 5)}, [{W / 2}, {gs['y'] * H:.0f}]);")
            J(f"s.inPoint = {a_:.3f}; s.outPoint = {b_:.3f}; var sS = s.property('Transform').property('Scale'); sS.setValueAtTime({a_:.3f}, [88, 88]); sS.setValueAtTime({a_ + 0.09:.3f}, [100, 100]);")
        J(f"var sl = main.layers.add(c); sl.startTime = {start:.3f};")
    # 위쪽 고정 주제 제목(레퍼런스: '컴퓨터 버그의 유래'처럼 영상 내내 위에 떠 있음) — 콘티 direction.pin_title > pin_title > 짧은 제목
    pin = d.get("pin_title") or sb.get("pin_title") or (sb.get("title") if len(sb.get("title") or "") <= 24 else None)
    if pin and d.get("pin", True):
        J("\n// ---------- 위쪽 고정 주제 제목(영상 전체)")
        psz = max(36, min(52, int(W * 0.84 / max(1, len(pin)))))   # 한 줄에 들어가게
        J(f"var pt = txt(main, 'PinTitle', {js(pin)}, {js(font)}, {psz}, [1, 1, 1], null, 0, [{W / 2}, {H * 0.062:.0f}]);")
        J("var pbx = fitBox(main, 'PinBox', 'PinTitle', [0.05, 0.05, 0.08], 56, 30, 18); pbx.property('Transform').property('Opacity').setValue(82);")
        g["pill"] = {**g["pill"], "y": max(g["pill"]["y"], 0.115)}      # 숫자 알약은 그 아래로
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
