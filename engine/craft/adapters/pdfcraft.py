"""PdfCraft 어댑터 — 문서 인용 재료(type: doc_quote). 기본 materials.doc_quote() 를 덮어쓴다.

기본 어댑터는 쪽 전체를 렌더하고 사각형만 넘겨 움직임 단계가 가짜 형광펜을 그렸다. 여기서는 PdfCraft 가 직접:
  1. 문장 찾기(text_find) — 줄이 바뀌며 낱말이 끊긴 문장(예: '이\\n용자')은 줄 글(text_lines)을 이어 찾고 줄마다 조각으로 다시 찾는다
  2. 사각형 다듬기 — 렌더 픽셀로 글자 잉크를 재서, 사각형이 글자보다 훨씬 넓거나(텍스트 프레임 폭) 큰 글씨에서 위아래로 밀렸으면 맞춘다
  3. 개인정보 가리기(선택) — 정규식에 걸린 글자를 실제로 지운다(검은 상자). 원본은 건드리지 않고 work 의 사본에서
  4. 진짜 주석 — 형광펜(comment_add highlight, 여러 줄이면 줄마다) · 빨간 상자(rectangle) · 밑줄
  5. 찾은 문장 주변 줄만 잘라(page_set_box) 화면 폭 1080px 에 맞는 dpi 로 내보내기(doc_export_images)

콘티 칸:
  pdf        PDF 경로(필수, 저장소 기준 상대 경로 또는 절대 경로)
  find       찾을 문장(필수). 줄바꿈 · 띄어쓰기가 원문과 달라도 찾는다
  page       이 쪽부터 찾기(선택)
  mark       "highlight"(기본) · "underline" · "box"(빨간 상자) · "both"(형광펜 + 상자) · "none"
  color      형광펜 색(기본 yellow, #RRGGBB 또는 이름)
  context    찾은 문장 위아래로 함께 보일 줄 수(기본 2)
  crop       false → 쪽 전체를 내보낸다(기본 true: 문장 주변만)
  width      내보낼 그림 폭 px(기본 1080) — dpi = width / 자른 폭(pt) × 72
  redact     ["정규식", …] 또는 "email" · "phone" 같은 PdfCraft 패턴 이름 — 걸린 글자를 지운다

기록(info) 칸 — 기본 어댑터와 같은 이름을 그대로 쓴다:
  page       찾은 쪽 번호(1부터)
  highlight  [[x, y, w, h], …] 나온 PNG 기준 픽셀(줄마다 하나) — 움직임 단계가 이 줄로 확대해 들어간다
  highlighted true — 형광펜이 이미 그려져 있으니 움직임 단계는 가짜 형광펜을 그리지 않는다(mark 가 none 이면 false)
  crop       잘라 낸 사각형 [x0, y0, x1, y1](pt) · dpi · size [폭, 높이](px) · redacted(지운 개수)
  editable   주석이 든 PDF(work/<id>.marked.pdf) — 사람이 PdfCraft 로 열어 형광펜을 옮기거나 지울 수 있다
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

PATTERNS = {"phone", "email", "credit-card", "ssn", "date"}   # PdfCraft redact_mark 의 내장 패턴
# 한국 개인정보 기본 정규식(이름만 적으면 이걸 쓴다) — PdfCraft 내장 phone 은 미국식이라 010-1234-5678 을 놓칠 수 있다
KO_PATTERNS = {
    "phone": r"0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}",
    "email": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    "rrn": r"\d{6}-[1-4]\d{6}",                 # 주민등록번호
}


# ---------------------------------------------------------------- PdfCraft 실행
def _pc(steps: list, name: str, work: Path, mid: str) -> list:
    """steps 를 한 번에 돌리고 각 단계 결과 목록을 돌려준다(실패한 단계가 있으면 RuntimeError)"""
    from ..materials import _run, cli
    sp = work / f"{mid}.{name}.json"
    sp.write_text(json.dumps(steps, ensure_ascii=False), "utf-8")
    out = _run([cli("pdfcraft"), "run", "--script", sp, "--report", "--root", work], work)
    try:
        rep = json.loads(out)
    except ValueError as e:
        raise RuntimeError(f"PdfCraft 결과를 읽지 못했습니다: {out[-300:]}") from e
    res = []
    for s in rep.get("steps") or []:
        if s.get("status") != "ok":
            raise RuntimeError(f"PdfCraft {s.get('tool')} 실패: {json.dumps(s.get('error') or s.get('result'), ensure_ascii=False)[:300]}")
        r = s.get("result")
        res.append(r[0] if isinstance(r, list) and len(r) == 1 else r)
    return res


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


# ---------------------------------------------------------------- 찾기
def _wt(ch: str) -> float:
    """글자 폭 어림(전각 1) — 사각형을 줄 안에서 나눌 때만 쓴다"""
    if ch.isspace():
        return 0.3
    if ord(ch) >= 0x1100:
        return 1.0
    if ch.isalnum():
        return 0.55
    return 0.35


def _slice_rect(line: dict, a: int, b: int) -> list:
    """줄 사각형에서 글자 a:b 부분을 글자 폭 어림으로 잘라 낸다"""
    t = line["text"]
    x0, y0, x1, y1 = line["rect"]
    tot = sum(_wt(c) for c in t) or 1.0
    s = sum(_wt(c) for c in t[:a]) / tot
    e = sum(_wt(c) for c in t[:b]) / tot
    return [x0 + (x1 - x0) * s, y0, x0 + (x1 - x0) * e, y1]


def _span_lines(lines: list, query: str) -> list | None:
    """여러 줄에 걸친 문장: 줄 글을 공백 없이 이어 붙여 찾고, 걸친 줄마다 (줄, 시작, 끝) 을 돌려준다.
    줄 끝 하이픈은 먼저 그대로(English-/to-German), 안 되면 지우고(낱말 나눔 trans-/former) 잇는다"""
    q = _squash(query).lower()
    if not q:
        return None
    for drop in (False, True):
        flat, where = [], []
        for li, ln in enumerate(lines):
            t = ln.get("text") or ""
            end = len(t.rstrip()) - 1
            hy = drop and end > 0 and t[end] in "-\u00ad" and li + 1 < len(lines)
            for ci, ch in enumerate(t):
                if ch.isspace() or ch == "\u00ad" or (hy and ci == end):
                    continue
                flat.append(ch.lower())
                where.append((li, ci))
        k = "".join(flat).find(q)
        if k < 0:
            continue
        spans: dict[int, list] = {}
        for li, ci in where[k:k + len(q)]:
            sp = spans.setdefault(li, [ci, ci + 1])
            sp[0], sp[1] = min(sp[0], ci), max(sp[1], ci + 1)
        return [(li, a, b) for li, (a, b) in sorted(spans.items())]
    return None


def _locate(m: dict, src: Path, work: Path) -> tuple[int, list, list]:
    """→ (쪽 번호, 줄 사각형 [[x0,y0,x1,y1](pt)…], 그 쪽 줄 목록)"""
    mid, query = m["id"], m["find"]
    start = int(m.get("page") or 1)
    r = _pc([{"tool": "doc_open", "args": {"path": src.name}},
             {"tool": "text_find", "args": {"doc": 1, "query": query, "limit": 1, "start_page": start}}], "find", work, mid)
    npages = int((r[0] or {}).get("pages") or 1)
    hits = (r[1] or {}).get("matches") or []
    if hits:
        page = int(hits[0]["page"])
        lines = _pc([{"tool": "doc_open", "args": {"path": src.name}},
                     {"tool": "text_lines", "args": {"doc": 1, "page": page}}], "lines", work, mid)[1].get("lines") or []
        return page, [list(map(float, x)) for x in hits[0]["rects"]], lines
    # 바로 못 찾음 → 줄이 바뀌며 끊긴 문장일 수 있다. 쪽마다 줄 글을 이어서 찾는다
    pages = list(range(start, npages + 1))
    res = _pc([{"tool": "doc_open", "args": {"path": src.name}}] +
              [{"tool": "text_lines", "args": {"doc": 1, "page": p}} for p in pages], "lines", work, mid)[1:]
    for p, rl in zip(pages, res):
        lines = rl.get("lines") or []
        spans = _span_lines(lines, query)
        if not spans:
            continue
        # 줄마다 조각을 다시 찾아 정확한 사각형을 얻는다(같은 쪽에 같은 조각이 또 있으면 그 줄과 겹치는 것)
        pieces = [lines[li]["text"][a:b].strip() for li, a, b in spans]
        found = _pc([{"tool": "doc_open", "args": {"path": src.name}}] +
                    [{"tool": "text_find", "args": {"doc": 1, "query": pc or "?", "start_page": p, "limit": 200}} for pc in pieces],
                    "pieces", work, mid)[1:]
        rects = []
        for (li, a, b), pc, f in zip(spans, pieces, found):
            ly0, ly1 = lines[li]["rect"][1], lines[li]["rect"][3]
            best = None
            if len(_squash(pc)) >= 2:
                for h in f.get("matches") or []:
                    if int(h["page"]) != p:
                        continue
                    for rc in h.get("rects") or []:
                        if min(rc[3], ly1) - max(rc[1], ly0) > 0.5 * (ly1 - ly0):
                            best = list(map(float, rc))
                            break
                    if best:
                        break
            rects.append(best or _slice_rect(lines[li], a, b))
        return p, rects, lines
    raise RuntimeError(f"PDF 에서 '{query}' 를 찾지 못했습니다(띄어쓰기 · 줄바꿈을 무시하고도 없음 — 글자가 그림으로 된 스캔 PDF 일 수 있습니다)")


# ---------------------------------------------------------------- 사각형 다듬기(잉크)
def _ink_fix(rects: list, png: Path, k: float) -> list:
    """렌더(k = px/pt)에서 글자 잉크를 재서 사각형을 맞춘다.
    - 잉크 폭이 사각형 폭의 85% 미만이면(텍스트 프레임 폭으로 나온 경우) 잉크 폭으로 줄인다
    - 큰 글씨(24pt 이상)에서 잉크 가운데가 사각형 가운데와 15% 넘게 어긋나면 위아래로 옮긴다
    본문 크기 글자는 위아래 오차가 1pt 미만이라 건드리지 않는다(위아래 줄 잉크를 잘못 잡지 않게)"""
    try:
        from PIL import Image
    except ImportError:
        return rects
    im = Image.open(png).convert("L")
    W, H = im.size
    px = im.load()
    out = []
    for x0, y0, x1, y1 in rects:
        h = y1 - y0
        X0, X1 = max(0, int(x0 * k)), min(W, int(x1 * k + 1))
        Y0, Y1 = max(0, int((y0 - 0.25 * h) * k)), min(H, int((y1 + 0.25 * h) * k + 1))
        if X1 - X0 < 2 or Y1 - Y0 < 2:
            out.append([x0, y0, x1, y1])
            continue
        vals = [px[x, y] for y in range(Y0, Y1) for x in range(X0, X1)]
        bg = max(set(v // 16 for v in vals), key=[v // 16 for v in vals].count) * 16 + 8
        ink = [(x, y) for y in range(Y0, Y1) for x in range(X0, X1) if abs(px[x, y] - bg) > 64]
        if not ink:
            out.append([x0, y0, x1, y1])
            continue
        iy0, iy1 = int(y0 * k), int(y1 * k)
        cols = [x for x, y in ink if iy0 <= y <= iy1]
        if cols:
            ix0, ix1 = min(cols) / k, (max(cols) + 1) / k
            if ix1 - ix0 < 0.85 * (x1 - x0):
                pad = 0.08 * h
                x0, x1 = max(x0, ix0 - pad), min(x1, ix1 + pad)
        if h >= 24:
            rows = [y for x, y in ink if x0 * k <= x <= x1 * k and Y0 <= y < Y1]
            c_ink = (min(rows) + max(rows) + 1) / 2 / k
            dy = c_ink - (y0 + y1) / 2
            if abs(dy) > 0.04 * h:                # DesignCraft 큰 제목: text_find 가 글자보다 ~8% 아래로 나온다
                y0, y1 = y0 + dy, y1 + dy
        out.append([round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)])
    return out


# ---------------------------------------------------------------- 자를 곳
def _crop(rects: list, lines: list, page_wh: tuple, ctx: int) -> list:
    """찾은 줄 위아래 ctx 줄까지(같은 단의 줄만) — 줄이 반쯤 잘리지 않게 줄 경계에 맞춰 자른다"""
    hx0, hy0 = min(r[0] for r in rects), min(r[1] for r in rects)
    hx1, hy1 = max(r[2] for r in rects), max(r[3] for r in rects)
    # 같은 단: 찾은 사각형과 가로로 겹치는 줄. 문장이 짧아도 그 줄 전체 폭은 보이게
    col = [ln["rect"] for ln in lines if ln.get("rect") and ln["rect"][0] < hx1 and ln["rect"][2] > hx0 and (ln.get("text") or "").strip()]
    col.sort(key=lambda r: r[1])
    rows: list = []                               # 한 줄이 여러 조각으로 나와도 눈에 보이는 줄 하나로 묶는다
    for r in col:
        if rows and min(rows[-1][3], r[3]) - max(rows[-1][1], r[1]) > 0.5 * min(r[3] - r[1], rows[-1][3] - rows[-1][1]):
            q = rows[-1]
            rows[-1] = [min(q[0], r[0]), min(q[1], r[1]), max(q[2], r[2]), max(q[3], r[3])]
        else:
            rows.append(list(r))
    col = rows
    hit =[i for i, r in enumerate(col) if min(r[3], hy1) - max(r[1], hy0) > 0]
    i0, i1 = (max(0, hit[0] - ctx), min(len(col), hit[-1] + ctx + 1)) if hit else (0, 0)
    sel = col[i0:i1]
    xs0 = [r[0] for r in sel] + [hx0]
    xs1 = [r[2] for r in sel] + [hx1]
    top, bot = min([r[1] for r in sel] + [hy0]), max([r[3] for r in sel] + [hy1])
    lh = max(4.0, (hy1 - hy0) / max(1, len(rects)))
    pad = max(10.0, 0.9 * lh)
    # 위아래 여백은 바깥 줄과의 틈 절반까지만 — 넘으면 옆 줄이 반쯤 잘려 보인다
    above = [r[3] for r in col[:i0] if r[3] <= top + 0.5]
    below = [r[1] for r in col[i1:] if r[1] >= bot - 0.5]
    pt = min(pad, (top - max(above)) / 2) if above else pad
    pb = min(pad, (min(below) - bot) / 2) if below else pad
    pw, ph = page_wh
    return [round(max(0, min(xs0) - pad), 2), round(max(0, top - max(0.0, pt)), 2),
            round(min(pw, max(xs1) + pad), 2), round(min(ph, bot + max(0.0, pb)), 2)]


def _vpad(rects: list, lines: list, p: float, bw: float) -> float:
    """상자 위아래 여백 — 바로 위 · 아래 줄과의 틈 안에서(상자 선이 옆 줄 글자를 긋지 않게)"""
    top, bot = min(r[1] for r in rects), max(r[3] for r in rects)
    hx0, hx1 = min(r[0] for r in rects), max(r[2] for r in rects)
    gaps = []
    for ln in lines:
        r = ln.get("rect")
        if not r or r[0] >= hx1 or r[2] <= hx0 or not (ln.get("text") or "").strip():
            continue
        if r[3] <= top + 0.5:
            gaps.append(top - r[3])
        elif r[1] >= bot - 0.5:
            gaps.append(r[1] - bot)
    if not gaps:
        return p
    return max(0.6, min(p, min(gaps) / 2 - bw / 2))


def _outline(rects: list, p: float, py: float) -> list:
    """여러 줄 문장을 감싸는 다각형(글자 선택 모양): 첫 줄은 시작점부터, 끝 줄은 끝점까지.
    첫 줄 시작이 끝 줄 끝보다 오른쪽이면(두 줄이 안 겹침) 하나로 못 감싸니 [] → 줄마다 상자"""
    if len(rects) < 2:
        return []
    f, l = rects[0], rects[-1]
    xl = min(r[0] for r in rects[1:]) - p
    xr = max(r[2] for r in rects[:-1]) + p
    m1 = (f[3] + rects[1][1]) / 2                 # 첫 줄 아래 경계
    m2 = (rects[-2][3] + l[1]) / 2                # 끝 줄 위 경계
    if f[0] - p >= l[2] + p and len(rects) == 2:
        return []
    pts = [[f[0] - p, f[1] - py], [xr, f[1] - py], [xr, m2], [l[2] + p, m2], [l[2] + p, l[3] + py],
           [xl, l[3] + py], [xl, m1], [f[0] - p, m1]]
    return [[round(x, 2), round(y, 2)] for x, y in pts]


def _redact_words(texts: list, pats: list) -> tuple[list, list]:
    """콘티 redact → (PdfCraft 내장 패턴 이름들, 정규식에 걸린 글자 목록).
    phone · email · rrn 은 우리 정규식으로만 찾는다 — PdfCraft 내장 phone · email 패턴은 한국어 문서에서
    줄을 넘어 엉뚱한 글자('1. 조사 개요' 의 1)까지 지웠다(2026-11-05 시험). 나머지 내장 이름(credit-card · ssn · date)은 그대로 넘긴다"""
    names, words = [], []
    for p in pats:
        rx = KO_PATTERNS.get(p)
        if rx is None and p in PATTERNS:
            names.append(p)
            continue
        try:
            c = re.compile(rx or p)
        except re.error as e:
            raise RuntimeError(f"redact 정규식이 잘못됐습니다: {p} ({e})") from e
        for t in texts:
            words += [w.group(0).strip() for w in c.finditer(t) if w.group(0).strip()]
    return sorted(set(names)), sorted(set(words), key=len, reverse=True)


# ---------------------------------------------------------------- 어댑터
def doc_quote(m: dict, out: Path, work: Path) -> dict:
    """PdfCraft: 문장 찾기 → 진짜 형광펜 · 상자 → (개인정보 가리기) → 문장 주변만 고해상도 PNG"""
    from ..materials import _abs, _run, cli, ROOT
    if not m.get("pdf") or not m.get("find"):
        raise RuntimeError("doc_quote 재료에는 pdf 와 find 칸이 필요합니다")
    pdf = _abs(m["pdf"])
    if not pdf.exists():
        raise RuntimeError(f"PDF 가 없습니다: {m['pdf']}")
    mid = m["id"]
    work.mkdir(parents=True, exist_ok=True)
    src = work / f"{mid}.src.pdf"                 # 원본은 그대로 두고 사본만 다룬다
    shutil.copyfile(pdf, src)

    page, rects, lines = _locate(m, src, work)

    # 잉크 재기용 렌더(2배) — 쪽 크기(pt)도 여기서 안다
    probe = work / f"{mid}.probe.png"
    _run([cli("pdfcraft"), "render", src, "--page", page, "--dpi", 144, "--out", probe], work)
    try:
        from PIL import Image
        with Image.open(probe) as im:
            pw, ph = im.size[0] / 2.0, im.size[1] / 2.0
    except ImportError:
        pw, ph = max(r[2] for r in rects) + 72, max(r[3] for r in rects) + 72
    rects = _ink_fix(rects, probe, 2.0)
    probe.unlink(missing_ok=True)

    # 개인정보 가리기: 정규식은 쪽 글을 뽑아 파이썬으로 찾고, 걸린 글자를 words 로 넘긴다
    steps = [{"tool": "doc_open", "args": {"path": src.name}}]
    redacted = 0
    pats = m.get("redact") or []
    if isinstance(pats, str):
        pats = [pats]
    if pats:
        tx = _pc([{"tool": "doc_open", "args": {"path": src.name}}, {"tool": "text_extract", "args": {"doc": 1}}], "text", work, mid)[1]
        names, words = _redact_words(list(_strings(tx)), pats)
        for n in names:
            steps.append({"tool": "redact_mark", "args": {"doc": 1, "pattern": n}})
        if words:
            steps.append({"tool": "redact_mark", "args": {"doc": 1, "words": words[:1000]}})
        if names or words:
            steps.append({"tool": "redact_apply", "args": {"doc": 1}})

    # 진짜 주석: 형광펜은 줄마다 quad(왼위 · 오른위 · 왼아래 · 오른아래), 상자는 줄 전체를 감싸게
    mark = str(m.get("mark") or "highlight").lower()
    color = m.get("color") or "yellow"
    quads = [[x0, y0, x1, y0, x0, y1, x1, y1] for x0, y0, x1, y1 in rects]
    if mark in ("highlight", "both"):
        steps.append({"tool": "comment_add", "args": {"doc": 1, "page": page, "type": "highlight", "quads": quads, "color": color}})
    if mark == "underline":
        steps.append({"tool": "comment_add", "args": {"doc": 1, "page": page, "type": "underline", "quads": quads, "color": m.get("color") or "red"}})
    if mark in ("box", "both"):
        lh = rects[0][3] - rects[0][1]
        p = max(3.0, 0.35 * lh)
        bc, bw = m.get("box_color") or "red", round(max(1.2, 0.14 * lh), 2)
        py = _vpad(rects, lines, p, bw)
        pts = _outline(rects, p, py)
        if pts:
            steps.append({"tool": "comment_add", "args": {"doc": 1, "page": page, "type": "polygon", "points": pts, "color": bc, "width": bw}})
        else:
            for x0, y0, x1, y1 in rects:
                steps.append({"tool": "comment_add", "args": {"doc": 1, "page": page, "type": "rectangle", "color": bc, "width": bw,
                                                              "rect": [round(x0 - p, 2), round(y0 - py, 2), round(x1 + p, 2), round(y1 + py, 2)]}})
    marked = work / f"{mid}.marked.pdf"
    steps.append({"tool": "doc_save", "args": {"doc": 1, "path": marked.name}})

    # 자르기 + 내보내기(문서 사본의 그 쪽만)
    crop = _crop(rects, lines, (pw, ph), int(m.get("context", 2))) if m.get("crop", True) else [0.0, 0.0, pw, ph]
    cw = crop[2] - crop[0]
    dpi = round(max(72.0, min(1200.0, float(m.get("width", 1080)) / cw * 72.0)), 1)
    if m.get("crop", True):
        steps.append({"tool": "page_set_box", "args": {"doc": 1, "pages": [page], "rect": crop}})
    exp = work / f"{mid}.exp"
    shutil.rmtree(exp, ignore_errors=True)
    steps.append({"tool": "doc_export_images", "args": {"doc": 1, "pages": [page], "dpi": dpi, "folder": exp.name}})
    res = _pc(steps, "mark", work, mid)
    for r in res:
        if isinstance(r, dict) and "applied" in r:
            redacted += int(r.get("applied") or 0)
    got = sorted(exp.glob(f"*_page_{page}.png"))
    if not got:
        raise RuntimeError("PdfCraft 가 잘라 낸 쪽 그림을 내보내지 않았습니다")
    shutil.move(str(got[0]), out)
    shutil.rmtree(exp, ignore_errors=True)
    src.unlink(missing_ok=True)                   # 사본은 다 썼다(가린 판은 marked.pdf 에)

    try:
        from PIL import Image
        with Image.open(out) as im:
            iw, ih = im.size
    except ImportError:
        iw, ih = round(cw * dpi / 72), round((crop[3] - crop[1]) * dpi / 72)
    k = iw / cw                                   # 실제 px/pt(PdfCraft 가 dpi 를 낮췄어도 맞게)
    hl = [[round((x0 - crop[0]) * k, 1), round((y0 - crop[1]) * k, 1), round((x1 - x0) * k, 1), round((y1 - y0) * k, 1)]
          for x0, y0, x1, y1 in rects]
    try:
        ed = str(marked.relative_to(ROOT))
    except ValueError:
        ed = marked.name
    fx0, fy0 = min(h[0] for h in hl), min(h[1] for h in hl)
    focus = [fx0, fy0, round(max(h[0] + h[2] for h in hl) - fx0, 1), round(max(h[1] + h[3] for h in hl) - fy0, 1)]
    return {"app": "pdfcraft", "as": "image", "page": page, "highlight": hl, "focus": focus, "highlighted": mark != "none",
            "mark": mark, "crop": crop, "dpi": dpi, "size": [iw, ih], "redacted": redacted, "editable": ed}


def _strings(o):
    """text_extract 결과에서 글 조각만 꺼낸다(모양이 dict · list 어느 쪽이어도)"""
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


ADAPTERS = {"doc_quote": doc_quote}
