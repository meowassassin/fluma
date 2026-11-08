"""FigCraft 어댑터 — 실제 캡처를 폰 · 브라우저 목업에 넣거나, 실제 앱이 없을 때 간단한 앱 화면을 만든다(ui_mock).

  { "id": "m1", "type": "ui_mock", "src": "data/compositions/<id>/craft/src/settings.png", "device": "phone" }
  { "id": "m1", "type": "ui_mock", "src": "…/lcp.png", "device": "browser", "url": "pagespeed.web.dev" }
  { "id": "m2", "type": "ui_mock", "device": "phone", "mock": true,
    "screen": { "title": "알림 설정", "subtitle": "앱마다 따로 끌 수 있어요", "search": "검색",
                "items": [ "방해 금지 모드",
                           { "title": "카카오톡", "sub": "배너 · 소리", "value": "켬", "icon": "톡", "color": "#FEE500" },
                           { "title": "야간 요약", "toggle": true } ],
                "highlight": 1, "button": "저장", "tabs": ["홈", "검색", "설정"], "tab": 2,
                "theme": "light", "accent": "#0A84FF" } }

  - src: 실제 캡처(png · jpg). 화면 비율과 다르면 위쪽을 기준으로 자르고(crop: "top"|"center"|"bottom" 또는 0~1),
    짧으면 캡처 맨 아래 색으로 이어 붙인다. 폰 화면 캡처(세로가 가로의 2배 이상)는 상태 표시줄이 있다고 보고 덧붙이지 않는다
    (statusbar: true | false 로 강제)
  - screen: 실제 앱이 없을 때 그리는 가상 화면 — 콘티에 "mock": true 를 꼭 적는다(가짜 UI 를 실제처럼 보이면 안 된다).
    기록에도 "mock": true 가 남는다
  - items: 글자 또는 {title, sub, value, icon(글자 1~2자), color, toggle(true|false)} — 화면에 안 들어가는 항목은 뺀다(기록 dropped)
  - 결과: 투명 배경 PNG(기기 + 그림자). 기록에 화면 상자 "screen_box", 항목 상자 "item_boxes"([x,y,w,h], 0~1 결과 그림 기준)
    — 같은 장면 overlay 재료의 box 로 그대로 쓸 수 있다. 사람이 고칠 <id>.figcraft 도 남긴다
  - 한글은 글자 단위로 줄이 바뀌므로(FigCraft) 낱말 경계에서 미리 끊어 넣는다(_wrap)
"""
from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

FONT = "Noto Sans CJK KR"
_FONT_DIR = Path("/usr/share/fonts/google-noto-sans-cjk-fonts")
_WEIGHT_FILE = {400: "Regular", 500: "Medium", 600: "Bold", 700: "Bold", 800: "Black", 900: "Black"}


# ---------------------------------------------------------------- 글자 재기 · 낱말 줄바꿈 (designcraft 도 쓴다)
@lru_cache(maxsize=64)
def _pil_font(size: float, weight: int = 400, index: int = 1):
    """Noto Sans CJK(KR = 모음 1번) — 없으면 None(그때는 글자 수로 어림)"""
    try:
        from PIL import ImageFont
        f = _FONT_DIR / f"NotoSansCJK-{_WEIGHT_FILE.get(weight, 'Regular')}.ttc"
        return ImageFont.truetype(str(f), max(1, int(round(size * 4))), index=index)   # 4배로 재서 반올림 오차 줄이기
    except (OSError, ImportError, ValueError):
        return None


def text_width(s: str, size: float, weight: int = 400, tracking: float = 0.0) -> float:
    """글자 폭(디자인 단위). tracking: 글자 사이 추가 간격(크기 대비 비율, -0.02 = -2%)"""
    f = _pil_font(size, weight)
    if f is None:
        w = sum(size * (1.0 if ord(c) > 0x2e80 else 0.56) for c in s)
    else:
        w = f.getlength(s) / 4
    return w + tracking * size * max(0, len(s) - 1)


def _greedy(words: list[str], width: float, size: float, weight: int, tracking: float) -> list[str]:
    lines, cur = [], ""
    for w in words:
        t = f"{cur} {w}" if cur else w
        if not cur or text_width(t, size, weight, tracking) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:            # 한 낱말이 폭보다 길면 그 낱말만 글자 단위로
        while text_width(ln, size, weight, tracking) > width and len(ln) > 1:
            k = len(ln)
            while k > 1 and text_width(ln[:k], size, weight, tracking) > width:
                k -= 1
            out.append(ln[:k])
            ln = ln[k:].lstrip()
        out.append(ln)
    return out


# 줄 끝에 오면 어색한 낱말: 뒷말을 꾸미는 꼴(관형형 '-ㄹ · -ㄴ · -는 · -의')과 부정 · 수식 부사.
# '전환이 안 나올 / 때' 처럼 꾸밈말과 꾸밈 받는 말이 갈라지면 제목이 끊겨 읽힌다
_DANGLE_WORDS = {"안", "못", "더", "덜", "꼭", "잘", "왜", "이", "그", "저", "새", "한", "두", "세", "네", "몇", "첫", "단", "약", "총", "제",
                 "미리", "먼저", "다시", "바로", "같이", "모두", "가장", "아주", "너무", "정말", "진짜", "제일", "훨씬", "이미", "아직", "단지"}


def _dangle(w: str) -> float:
    w = w.rstrip("\"'”’)")
    if not w:
        return 0.0
    if w[-1] in ",.!?:;·…" or w.endswith(("다", "요", "죠", "까")):
        return -0.15                              # 문장 · 구가 끝나는 자리 — 끊기 좋다
    if w in _DANGLE_WORDS:
        return 1.0
    c = w[-1]
    if c in "의" or (c in "한된던운" and len(w) > 1) or w.endswith(("라는", "하는", "되는", "있는", "없는", "다는", "이라는")):
        return 0.6
    if "가" <= c <= "힣" and c not in "을를" and (ord(c) - 0xAC00) % 28 == 8:
        return 0.6                                # ㄹ 받침: 관형형(나올 · 볼 · 할)일 때가 많다(을 · 를 은 빼고)
    return 0.0


def break_penalty(lines: list[str]) -> float:
    """줄 끝 낱말의 어색함 합(마지막 줄 제외) — 0 이면 자연스럽게 끊겼다"""
    return sum(max(0.0, _dangle(ln.split()[-1])) for ln in lines[:-1] if ln.split())


def _balanced(words: list[str], n: int, width: float, size: float, weight: int, tracking: float) -> list[str] | None:
    """n 줄로 나누는 모든 경우 중 (줄 길이 고르기 + 어색한 끊김 벌점)이 가장 작은 것 — 제목용(낱말 수가 적다)"""
    import itertools
    if n > 4 or len(words) > 18:
        return None
    best, best_cost = None, None
    for cuts in itertools.combinations(range(1, len(words)), n - 1):
        b = (0, *cuts, len(words))
        lines = [" ".join(words[b[i]:b[i + 1]]) for i in range(n)]
        ws = [text_width(ln, size, weight, tracking) for ln in lines]
        if max(ws) > width:
            continue
        mx = max(ws)
        cost = sum(((mx - w) / width) ** 2 for w in ws[:-1]) + (max(0.0, (mx - ws[-1]) / width - 0.25)) ** 2
        cost += sum(_dangle(words[c - 1]) for c in cuts) * 0.35
        if ws[-1] < width * 0.18 and n > 1:    # 마지막 줄에 짧은 낱말 하나
            cost += 0.4
        if best_cost is None or cost < best_cost:
            best, best_cost = lines, cost
    return best


def wrap(text: str, width: float, size: float, weight: int = 400, tracking: float = 0.0,
         balance: bool = False, max_lines: int | None = None) -> list[str]:
    """낱말(띄어쓰기) 경계에서 줄을 나눈다. 사용자가 넣은 \\n 은 그대로 지킨다.
    balance: 줄 수는 그대로 두고 줄 길이를 고르게(제목에서 한 낱말만 다음 줄로 넘어가는 것 막기).
    max_lines 를 넘으면 마지막 줄 끝을 … 로 자른다"""
    lines: list[str] = []
    for para in str(text or "").split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        got = _greedy(words, width, size, weight, tracking)
        if balance and len(got) > 1 and all(text_width(w, size, weight, tracking) <= width for w in words):
            got = _balanced(words, len(got), width, size, weight, tracking) or got
        lines += got
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = ellipsize(lines[-1] + "…", width, size, weight, tracking)
    return lines


def ellipsize(s: str, width: float, size: float, weight: int = 400, tracking: float = 0.0) -> str:
    """한 줄에 안 들어가면 끝을 … 로"""
    s = str(s or "")
    if text_width(s, size, weight, tracking) <= width:
        return s
    t = s.rstrip("…")
    while t and text_width(t.rstrip() + "…", size, weight, tracking) > width:
        t = t[:-1]
    return t.rstrip() + "…"


# ---------------------------------------------------------------- FigCraft 스크립트 만들기
class _Doc:
    """FigCraft run 스크립트 — 단계마다 이름(as)을 붙여 {"$ref": 이름} 으로 부모를 잇는다"""

    def __init__(self):
        self.steps: list[dict] = []
        self.n = 0

    def add(self, command: str, params: dict, name: str | None = None) -> dict:
        self.n += 1
        nm = name or f"n{self.n}"
        self.steps.append({"command": command, "params": params, "as": nm})
        return {"$ref": nm}

    def frame(self, parent, x, y, w, h, name, fill=None, radius=0, clip=False, **props) -> dict:
        p = {"fills": [fill] if fill else [], "cornerRadius": radius, "clipsContent": clip, **props}
        if parent is None:
            return self.add("frame.create", {"x": x, "y": y, "width": w, "height": h, "name": name, "props": p}, name)
        return self.add("node.create", {"type": "frame", "parent": parent, "x": x, "y": y, "width": w, "height": h,
                                        "name": name, "props": p})

    def rect(self, parent, x, y, w, h, fill, radius=0, name="Rect", **props) -> dict:
        return self.add("node.create", {"type": "rectangle", "parent": parent, "x": x, "y": y, "width": w, "height": h,
                                        "name": name, "props": {"fills": [fill] if fill else [], "cornerRadius": radius, **props}})

    def ellipse(self, parent, x, y, w, h, fill, name="Dot") -> dict:
        return self.add("node.create", {"type": "ellipse", "parent": parent, "x": x, "y": y, "width": w, "height": h,
                                        "name": name, "props": {"fills": [fill]}})

    def text(self, parent, x, y, w, s, size, color, weight=400, align="left", name="Text", lh=None, tracking=0.0) -> dict:
        props = {"fontSize": size, "fontFamily": FONT, "fontWeight": weight, "fills": [color], "textAlign": align,
                 "textAutoResize": "height"}
        if lh:
            props["lineHeight"] = lh
        if tracking:
            props["letterSpacing"] = f"{tracking * 100:.1f}%"
        return self.add("node.create", {"type": "text", "parent": parent, "x": x, "y": y, "width": w, "text": s,
                                        "name": name, "props": props})

    def path(self, parent, x, y, d, stroke=None, fill=None, weight=2.0, name="Icon") -> dict:
        props = {"fills": [fill] if fill else []}
        if stroke:
            props.update({"strokes": [stroke], "strokeWeight": weight, "strokeCap": "round", "strokeJoin": "round"})
        return self.add("node.create", {"type": "vector", "parent": parent, "x": x, "y": y, "path": d, "name": name,
                                        "props": props})

    def image(self, parent, path: Path, x, y, w, h, name="Screenshot") -> dict:
        return self.add("image.place", {"path": str(path), "parent": parent, "x": x, "y": y, "width": w, "height": h,
                                        "name": name, "mode": "fill"})


def _fig_run(doc: _Doc, work: Path, oid: str, node: str, out: Path, scale: float, timeout: int = 120) -> Path:
    """스크립트 실행 → <oid>.figcraft(사람이 고칠 파일) → node 하나만 투명 PNG 로"""
    from ..materials import cli
    exe = cli("figcraft")
    sf = work / f"{oid}.fig.json"
    sf.write_text(json.dumps(doc.steps, ensure_ascii=False, indent=1), "utf-8")
    fc = work / f"{oid}.figcraft"
    env = {**os.environ, "DO_NOT_TRACK": "1"}
    try:
        r = subprocess.run([exe, "run", str(sf), "--out", str(fc)], cwd=str(work), text=True, capture_output=True,
                           timeout=timeout, env=env)
        if r.returncode != 0 or not fc.exists():
            bad = [ln for ln in r.stdout.splitlines() if '"ok":false' in ln]
            raise RuntimeError(f"FigCraft 스크립트 실패({oid}): {(bad[0] if bad else r.stderr or r.stdout).strip()[-400:]}")
        r = subprocess.run([exe, "export", str(fc), "-o", str(out), "--node", node, "--scale", f"{scale:g}"],
                           cwd=str(work), text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"FigCraft 가 {timeout}초 안에 끝나지 않았습니다({oid})")
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"FigCraft 내보내기 실패({oid}): {(r.stderr or r.stdout).strip()[-400:]}")
    return fc


def _rel(p: Path) -> str:
    from ..materials import ROOT
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- 캡처 다듬기
def _lum(c) -> float:
    r, g, b = c[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _hex(c) -> str:
    return "#{:02X}{:02X}{:02X}".format(*[int(v) for v in c[:3]])


def _edge_color(im, top: bool) -> tuple:
    """캡처 맨 위 · 맨 아래 줄의 대표 색(가장 흔한 색) — 상태 표시줄 · 이어 붙일 바탕"""
    row = im.crop((0, 0 if top else im.height - 2, im.width, 2 if top else im.height)).convert("RGB").resize((64, 1))
    cols = sorted(row.getcolors(64) or [(1, (255, 255, 255))], reverse=True)
    return cols[0][1]


def _fit_capture(src: Path, aspect: float, crop, work: Path, oid: str) -> tuple[Path, tuple, tuple]:
    """캡처를 화면 비율(가로/세로)에 맞춘 PNG 로 — 길면 자르고(crop), 짧으면 아래 색으로 늘린다.
    → (파일, 위쪽 색, 아래쪽 색)"""
    from PIL import Image
    with Image.open(src) as im0:
        im = im0.convert("RGB")
    top_c, bot_c = _edge_color(im, True), _edge_color(im, False)
    W, H = im.size
    want_h = round(W / aspect)
    if H > want_h:
        if isinstance(crop, (int, float)) and not isinstance(crop, bool):
            y0 = int((H - want_h) * min(max(float(crop), 0.0), 1.0))
        else:
            y0 = {"center": (H - want_h) // 2, "bottom": H - want_h}.get(str(crop), 0)
        im = im.crop((0, y0, W, y0 + want_h))
    elif H < want_h:
        bg = Image.new("RGB", (W, want_h), bot_c)
        bg.paste(im, (0, 0))
        im = bg
    f = work / f"{oid}.screen.png"
    im.save(f)
    return f, top_c, bot_c


# ---------------------------------------------------------------- 작은 아이콘(벡터 경로, 24 단위 상자 기준)
_CHEVRON = "M0 0 L6 6.5 L0 13"
_LOCK = "M2 7 L10 7 L10 14 L2 14 Z M3.5 7 L3.5 4.5 C3.5 1.5 8.5 1.5 8.5 4.5 L8.5 7"
_WIFI = "M0 4 C5 -1 12 -1 17 4 M3 7.5 C6.5 4.5 10.5 4.5 14 7.5 M6.5 11 C7.8 10 9.2 10 10.5 11"
_SEARCH = "M6 0 C9.3 0 12 2.7 12 6 C12 9.3 9.3 12 6 12 C2.7 12 0 9.3 0 6 C0 2.7 2.7 0 6 0 Z M10.5 10.5 L14 14"


def _circle(cx: float, cy: float, r: float) -> str:
    k = r * 0.5523
    return (f"M{cx} {cy - r} C{cx + k} {cy - r} {cx + r} {cy - k} {cx + r} {cy} C{cx + r} {cy + k} {cx + k} {cy + r} {cx} {cy + r} "
            f"C{cx - k} {cy + r} {cx - r} {cy + k} {cx - r} {cy} C{cx - r} {cy - k} {cx - k} {cy - r} {cx} {cy - r} Z")


# 탭 막대 아이콘(24 상자, 선) — 탭 이름의 낱말로 고른다
_TAB_ICONS = [
    (("홈", "home", "메인"), "M3 11 L12 3.5 L21 11 M5.5 9 L5.5 20.5 L18.5 20.5 L18.5 9"),
    (("검색", "찾기", "search", "탐색"), _circle(10.5, 10.5, 6.5) + " M15.5 15.5 L21 21"),
    (("알림", "소식", "noti"), "M6 17 L6 11 C6 7 8.5 4.5 12 4.5 C15.5 4.5 18 7 18 11 L18 17 L20 19 L4 19 Z M10 21.5 L14 21.5"),
    (("내", "마이", "프로필", "my", "계정", "나"), _circle(12, 8, 4) + " M4 21 C4 16.5 7.5 14 12 14 C16.5 14 20 16.5 20 21"),
    (("설정", "setting", "더보기"), _circle(12, 12, 3.2) + " " + _circle(12, 12, 8.2)),
    (("채팅", "메시지", "대화", "chat"), "M4 5 L20 5 L20 16 L10 16 L6 20 L6 16 L4 16 Z"),
    (("장바구니", "쇼핑", "cart", "주문"), "M3 4 L6 4 L8.5 15 L18.5 15 L20.5 8 L7 8 M9 19.5 L9.1 19.5 M17 19.5 L17.1 19.5"),
]
_TAB_DEFAULT = "M4 4 L10 4 L10 10 L4 10 Z M14 4 L20 4 L20 10 L14 10 Z M4 14 L10 14 L10 20 L4 20 Z M14 14 L20 14 L20 20 L14 20 Z"


def _tab_icon(label: str) -> str:
    low = label.lower()
    for keys, d in _TAB_ICONS:
        if any(k in low for k in keys):
            return d
    return _TAB_DEFAULT


def _status_bar(d: _Doc, scr, W: float, color: str, bg: str | None):
    """iOS 상태 표시줄(9:41 · 신호 · 와이파이 · 배터리) — 높이 54"""
    if bg:
        d.rect(scr, 0, 0, W, 54, bg, name="StatusBg")
    d.text(scr, 34, 16, 70, "9:41", 17, color, 600, "center", name="Time")
    x = W - 96
    for i, h in enumerate((4, 6.5, 9, 11.5)):             # 신호 막대
        d.rect(scr, x + i * 4.6, 31 - h, 3.2, h, color, 1, name="Signal")
    d.path(scr, x + 23, 21, _WIFI, stroke=color, weight=2.2, name="Wifi")
    d.rect(scr, x + 46, 20, 25, 12, None, 3.5, name="Battery", strokes=[color], strokeWeight=1.2, opacity=0.45)
    d.rect(scr, x + 48, 22, 19, 8, color, 2, name="BatteryLevel")
    d.rect(scr, x + 72, 24, 1.6, 4, color, 1, name="BatteryCap", opacity=0.45)


# ---------------------------------------------------------------- 가상 화면(screen)
_LIGHT = {"bg": "#F2F2F7", "group": "#FFFFFF", "label": "#000000", "sec": "#8A8A8E", "sep": "#D8D8DC",
          "field": "#E3E3E8", "bar": "#F9F9F9"}
_DARK = {"bg": "#000000", "group": "#1C1C1E", "label": "#FFFFFF", "sec": "#8D8D93", "sep": "#38383A",
         "field": "#1C1C1E", "bar": "#121212"}
_ICON_COLORS = ["#0A84FF", "#34C759", "#FF9F0A", "#FF375F", "#5E5CE6", "#64D2FF", "#FF6B35", "#30B0C7"]


def _item(it) -> dict:
    return {"title": str(it)} if not isinstance(it, dict) else {**it, "title": str(it.get("title") or it.get("text") or "")}


def _toggle(d: _Doc, parent, x, y, on: bool, accent: str, off: str):
    d.rect(parent, x, y, 51, 31, "#34C759" if on else off, 15.5, name="Toggle")
    d.add("node.create", {"type": "ellipse", "parent": parent, "x": x + (22 if on else 2), "y": y + 2, "width": 27,
                          "height": 27, "name": "Knob", "props": {"fills": ["#FFFFFF"], "effects": [
                              {"type": "dropShadow", "color": "#00000033", "offset": [0, 2], "radius": 4}]}})


def _list_rows(d: _Doc, parent, x0, y0, W, items: list[dict], c: dict, accent: str, hl, wide: bool,
               bottom: float, chevron: bool) -> tuple[list[list[float]], list[str]]:
    """그룹 목록(둥근 흰 판 안의 줄들) — 아래 경계를 넘는 항목은 뺀다 → (항목 상자들, 뺀 항목 제목)"""
    has_icon = any(it.get("icon") for it in items)
    pad = 20 if wide else 16
    fs, ss = (19, 15) if wide else (17, 13.5)
    rows, y = [], 0.0
    for it in items:
        h = (72 if wide else 64) if it.get("sub") else (56 if wide else 48)
        if y0 + y + h > bottom:
            break
        rows.append((it, y, h))
        y += h
    dropped = [it["title"] for it in items[len(rows):]]
    if not rows:
        return [], dropped
    grp = d.frame(parent, x0, y0, W, y, "List", c["group"], 12 if not wide else 14, clip=True)
    boxes = []
    for i, (it, ry, h) in enumerate(rows):
        if hl is not None and i == hl:
            d.rect(grp, 0, ry, W, h, accent, name="Highlight", opacity=0.14)
        tx = pad
        if has_icon:
            ic = 30 if not wide else 36
            col = it.get("color") or _ICON_COLORS[i % len(_ICON_COLORS)]
            d.rect(grp, pad, ry + (h - ic) / 2, ic, ic, col, 7 if not wide else 9, name="IconTile")
            glyph = str(it.get("icon") or it["title"][:1])[:2]
            gs = ic * (0.5 if len(glyph) == 1 else 0.4)
            ink = "#000000" if _lum(_rgb(col)) > 170 else "#FFFFFF"
            d.text(grp, pad, ry + (h - gs * 1.45) / 2, ic, glyph, gs, ink, 700, "center", name="IconGlyph")
            tx = pad + ic + 14
        # 오른쪽: 토글 · 값 · 꺾쇠
        right = W - pad
        if isinstance(it.get("toggle"), bool):
            _toggle(d, grp, right - 51, ry + (h - 31) / 2, it["toggle"], accent, c["field"])
            right -= 51 + 10
        else:
            if chevron:
                d.path(grp, right - 7, ry + h / 2 - 6.5, _CHEVRON, stroke=c["sec"], weight=2.2, name="Chevron")
                right -= 7 + 12
            if it.get("value") not in (None, ""):
                v = ellipsize(str(it["value"]), W * 0.32, fs)
                vw = text_width(v, fs) + 4
                d.text(grp, right - vw, ry + (h - fs * 1.45) / 2, vw, v, fs, c["sec"], 400, "right", name="Value")
                right -= vw + 10
        tw = right - tx
        if it.get("sub"):
            d.text(grp, tx, ry + h / 2 - fs * 1.4 + 1, tw, ellipsize(it["title"], tw, fs, 500), fs, c["label"], 500, name="Title")
            d.text(grp, tx, ry + h / 2 + 2, tw, ellipsize(str(it["sub"]), tw, ss), ss, c["sec"], 400, name="Sub")
        else:
            d.text(grp, tx, ry + (h - fs * 1.45) / 2, tw, ellipsize(it["title"], tw, fs), fs, c["label"], 400, name="Title")
        if i < len(rows) - 1:
            d.rect(grp, tx, ry + h - 0.6, W - tx, 0.6, c["sep"], name="Separator")
        boxes.append([x0, y0 + ry, W, h])
    return boxes, dropped


def _rgb(h: str) -> tuple:
    h = str(h).lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (128, 128, 128)


def _phone_screen(d: _Doc, scr, W: float, H: float, sc: dict) -> tuple[list, list]:
    """폰 가상 화면(iOS 설정 · 목록 앱 문법): 큰 제목 → 검색 → 그룹 목록 → 버튼 → 탭 막대"""
    c = _DARK if sc.get("theme") == "dark" else _LIGHT
    accent = sc.get("accent") or "#0A84FF"
    d.rect(scr, 0, 0, W, H, c["bg"], name="Background")
    _status_bar(d, scr, W, c["label"], None)
    y = 60.0
    if sc.get("back"):
        d.path(scr, 14, y + 9, "M7 0 L0 8 L7 16", stroke=accent, weight=2.6, name="Back")
        d.text(scr, 28, y + 4, 160, ellipsize(str(sc["back"]), 150, 17), 17, accent, 400, name="BackLabel")
    y += 40
    title = wrap(sc.get("title") or "", W - 32, 32, 700, -0.01, balance=True, max_lines=2)
    if title and title[0]:
        d.text(scr, 16, y, W - 32, "\n".join(title), 32, c["label"], 700, name="LargeTitle", lh="120%", tracking=-0.01)
        y += 32 * 1.2 * len(title) + 6
    if sc.get("subtitle"):
        sub = wrap(sc["subtitle"], W - 32, 15, max_lines=2)
        d.text(scr, 16, y, W - 32, "\n".join(sub), 15, c["sec"], 400, name="Subtitle", lh="135%")
        y += 15 * 1.35 * len(sub) + 4
    y += 10
    if sc.get("search"):
        d.rect(scr, 16, y, W - 32, 38, c["field"], 11, name="Search")
        d.path(scr, 26, y + 12, _SEARCH, stroke=c["sec"], weight=2, name="SearchIcon")
        d.text(scr, 48, y + 8, W - 80, ellipsize(str(sc["search"]), W - 90, 17), 17, c["sec"], 400, name="SearchText")
        y += 38 + 18
    if sc.get("header"):
        d.text(scr, 32, y, W - 64, ellipsize(str(sc["header"]), W - 64, 13), 13, c["sec"], 400, name="SectionHeader")
        y += 26
    tabs = [str(t) for t in (sc.get("tabs") or [])][:5]
    bottom = H - (84 if tabs else 34) - (74 if sc.get("button") else 0) - 8
    items = [_item(it) for it in (sc.get("items") or [])]
    boxes, dropped = _list_rows(d, scr, 16, y, W - 32, items, c, accent, sc.get("highlight"), False, bottom,
                                sc.get("chevron", True))
    if sc.get("button"):
        by = H - (84 if tabs else 34) - 66
        d.rect(scr, 16, by, W - 32, 52, accent, 14, name="Button")
        d.text(scr, 16, by + 13, W - 32, ellipsize(str(sc["button"]), W - 64, 17, 600), 17, "#FFFFFF", 600, "center",
               name="ButtonLabel")
    if tabs:
        d.rect(scr, 0, H - 84, W, 84, c["bar"], name="TabBar", opacity=0.96)
        d.rect(scr, 0, H - 84, W, 0.6, c["sep"], name="TabBarLine")
        cur = sc.get("tab", 0)
        tw = W / len(tabs)
        for i, t in enumerate(tabs):
            col = accent if i == cur else c["sec"]
            d.path(scr, tw * i + tw / 2 - 12, H - 77, _tab_icon(t), stroke=col, weight=2.0 if i == cur else 1.7, name="TabIcon")
            d.text(scr, tw * i, H - 48, tw, ellipsize(t, tw - 8, 11, 500), 11, col, 500, "center", name="TabLabel")
    return boxes, dropped


def _web_screen(d: _Doc, scr, W: float, H: float, sc: dict) -> tuple[list, list, float]:
    """웹 가상 화면: 사이트 머리(이름 · 메뉴) → 큰 제목 → 목록 → 버튼 → (항목 상자, 뺀 항목, 내용 끝 y)"""
    c = _DARK if sc.get("theme") == "dark" else {**_LIGHT, "bg": "#FFFFFF", "group": "#F6F7F9"}
    accent = sc.get("accent") or "#2563EB"
    d.rect(scr, 0, 0, W, H, c["bg"], name="Background")
    d.rect(scr, 0, 64, W, 1, c["sep"], name="HeaderLine")
    site = str(sc.get("site") or sc.get("app") or "")
    if site:
        d.rect(scr, 40, 20, 24, 24, accent, 7, name="Logo")
        d.text(scr, 74, 19, 300, ellipsize(site, 280, 19, 700), 19, c["label"], 700, name="SiteName")
    tabs = [str(t) for t in (sc.get("tabs") or [])][:5]
    x = W - 40
    for i, t in enumerate(reversed(tabs)):
        tw = text_width(t, 16, 500) + 4
        x -= tw
        on = (len(tabs) - 1 - i) == sc.get("tab", -1)
        d.text(scr, x, 22, tw, t, 16, accent if on else c["sec"], 500, name="Nav")
        x -= 28
    y = 112.0
    title = wrap(sc.get("title") or "", W - 80, 40, 700, -0.01, balance=True, max_lines=2)
    if title and title[0]:
        d.text(scr, 40, y, W - 80, "\n".join(title), 40, c["label"], 700, name="H1", lh="122%", tracking=-0.01)
        y += 40 * 1.22 * len(title) + 10
    if sc.get("subtitle"):
        sub = wrap(sc["subtitle"], W - 80, 19, max_lines=2)
        d.text(scr, 40, y, W - 80, "\n".join(sub), 19, c["sec"], 400, name="Lead", lh="140%")
        y += 19 * 1.4 * len(sub) + 6
    y += 22
    bottom = H - 40 - (80 if sc.get("button") else 0)
    items = [_item(it) for it in (sc.get("items") or [])]
    boxes, dropped = _list_rows(d, scr, 40, y, W - 80, items, c, accent, sc.get("highlight"), True, bottom,
                                sc.get("chevron", False))
    end = y + sum(b[3] for b in boxes)
    if sc.get("button"):
        bl = ellipsize(str(sc["button"]), W - 160, 18, 600)
        bw = text_width(bl, 18, 600) + 64
        by = end + 28 if boxes else y
        d.rect(scr, 40, by, bw, 54, accent, 12, name="Button")
        d.text(scr, 40, by + 14, bw, bl, 18, "#FFFFFF", 600, "center", name="ButtonLabel")
        end = by + 54
    return boxes, dropped, end


# ---------------------------------------------------------------- 기기 틀
_PAD = 64          # 그림자가 잘리지 않게 둘레 여백(디자인 단위)


def _phone(d: _Doc, src_info, sc: dict | None) -> dict:
    """iPhone 류(화면 390×844 디자인 단위). 몸체 · 버튼 · 다이내믹 아일랜드 · 홈 표시줄"""
    SW, SH, B = 390.0, 844.0, 13.0
    BW, BH = SW + B * 2, SH + B * 2
    root = d.frame(None, 0, 0, BW + _PAD * 2, BH + _PAD * 2 + 24, "Mock")
    for (yy, hh) in ((190, 34), (250, 62), (326, 62)):          # 왼쪽 버튼(동작 · 음량)
        d.rect(root, _PAD - 3, _PAD + yy, 5, hh, "#2C2C2E", 2, name="SideButton")
    d.rect(root, _PAD + BW - 2, _PAD + 270, 5, 96, "#2C2C2E", 2, name="PowerButton")
    body = d.frame(root, _PAD, _PAD, BW, BH, "Phone", "#1C1C1E", 66, clip=True,
                   strokes=["#48484A"], strokeWeight=2, strokeAlign="inside",
                   effects=[{"type": "dropShadow", "color": "#00000059", "offset": [0, 28], "radius": 56},
                            {"type": "dropShadow", "color": "#00000026", "offset": [0, 4], "radius": 10}])
    scr = d.frame(body, B, B, SW, SH, "Screen", "#FFFFFF", 54, clip=True)
    boxes, dropped, dark = [], [], False
    if src_info:
        f, top_c, has_bar = src_info
        dark = _lum(top_c) < 110
        if has_bar:
            d.image(scr, f, 0, 0, SW, SH)
        else:
            d.image(scr, f, 0, 54, SW, SH - 54)
            _status_bar(d, scr, SW, "#FFFFFF" if dark else "#000000", _hex(top_c))
    else:
        boxes, dropped = _phone_screen(d, scr, SW, SH, sc or {})
        dark = (sc or {}).get("theme") == "dark"
    d.rect(scr, SW / 2 - 62, 11, 124, 36, "#000000", 18, name="DynamicIsland")
    d.rect(scr, SW / 2 - 70, SH - 13, 140, 5, "#FFFFFF" if dark else "#000000", 3, name="HomeIndicator")
    ox, oy = _PAD + B, _PAD + B
    return {"root_w": BW + _PAD * 2, "root_h": BH + _PAD * 2 + 24, "screen": [ox, oy, SW, SH],
            "items": [[ox + b[0], oy + b[1], b[2], b[3]] for b in boxes], "dropped": dropped}


def _browser(d: _Doc, src_info, sc: dict | None, url: str, content_h: float) -> dict:
    """데스크톱 브라우저 창(폭 960): 신호등 단추 · 주소창(자물쇠 + 주소) · 내용"""
    W, TB = 960.0, 52.0
    H = TB + content_h
    root = d.frame(None, 0, 0, W + _PAD * 2, H + _PAD * 2 + 16, "Mock")
    win = d.frame(root, _PAD, _PAD, W, H, "Browser", "#FFFFFF", 14, clip=True,
                  strokes=["#00000026"], strokeWeight=1, strokeAlign="inside",
                  effects=[{"type": "dropShadow", "color": "#00000052", "offset": [0, 26], "radius": 54},
                           {"type": "dropShadow", "color": "#0000001F", "offset": [0, 3], "radius": 8}])
    d.rect(win, 0, 0, W, TB, "#EDEEF0", name="Toolbar")
    d.rect(win, 0, TB - 1, W, 1, "#D5D7DB", name="ToolbarLine")
    for i, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        d.ellipse(win, 20 + i * 21, TB / 2 - 6.5, 13, 13, col, name="Light")
    d.path(win, 92, TB / 2 - 6.5, "M6 0 L0 6.5 L6 13", stroke="#8A8D93", weight=2, name="BackArrow")
    d.path(win, 116, TB / 2 - 6.5, "M0 0 L6 6.5 L0 13", stroke="#C2C4C8", weight=2, name="FwdArrow")
    aw = W * 0.56
    ax = (W - aw) / 2
    d.rect(win, ax, 10, aw, TB - 20, "#FFFFFF", (TB - 20) / 2, name="Address", strokes=["#D5D7DB"], strokeWeight=1)
    u = ellipsize(url, aw - 70, 14)
    uw = text_width(u, 14) + 2
    lx = ax + (aw - uw - 18) / 2
    d.path(win, lx, TB / 2 - 7, _LOCK, stroke="#6B6F76", weight=1.5, name="Lock")
    d.text(win, lx + 18, TB / 2 - 10, uw + 4, u, 14, "#3C3F44", 400, name="URL")
    boxes, dropped = [], []
    if src_info:
        d.image(win, src_info[0], 0, TB, W, content_h)
    else:
        scr = d.frame(win, 0, TB, W, content_h, "Page", "#FFFFFF")
        boxes, dropped, _ = _web_screen(d, scr, W, content_h, sc or {})
    ox, oy = _PAD, _PAD + TB
    return {"root_w": W + _PAD * 2, "root_h": H + _PAD * 2 + 16, "screen": [ox, oy, W, content_h],
            "items": [[ox + b[0], oy + b[1], b[2], b[3]] for b in boxes], "dropped": dropped}


def _ratio(b, W, H) -> list[float]:
    return [round(b[0] / W, 4), round(b[1] / H, 4), round(b[2] / W, 4), round(b[3] / H, 4)]


def ui_mock(m: dict, out: Path, work: Path) -> dict:
    from ..materials import _abs
    device = str(m.get("device") or "").lower()
    if not device:          # 정하지 않으면 캡처 모양으로: 세로로 긴 캡처는 폰, 넓은 캡처는 브라우저
        device = "phone"
        if isinstance(m.get("src"), str) and _abs(m["src"]).exists():
            from PIL import Image
            with Image.open(_abs(m["src"])) as im:
                device = "phone" if im.height / max(1, im.width) >= 1.3 else "browser"
    if device not in ("phone", "browser"):
        raise RuntimeError(f"ui_mock device 는 phone 또는 browser 입니다(받은 값: {device})")
    sc = m.get("screen") if isinstance(m.get("screen"), dict) else None
    src = _abs(m["src"]) if isinstance(m.get("src"), str) and m["src"] else None
    if src is not None and not src.exists():
        raise RuntimeError(f"ui_mock 캡처 파일이 없습니다: {m['src']}")
    if src is None and sc is None:
        raise RuntimeError("ui_mock 에 src(실제 캡처) 또는 screen({title, items}) 이 필요합니다")
    oid = m["id"]
    d = _Doc()
    src_info = None
    if device == "phone":
        if src:
            from PIL import Image
            with Image.open(src) as im:
                tall = im.height / max(1, im.width) >= 2.0
            has_bar = bool(m.get("statusbar")) if isinstance(m.get("statusbar"), bool) else tall
            # 상태 표시줄을 덧붙이면 그 아래 화면 비율에 맞춘다
            asp = 390 / (844 if has_bar else 844 - 54)
            f, top_c, _ = _fit_capture(src, asp, m.get("crop"), work, oid)
            src_info = (f, top_c, has_bar)
        lay = _phone(d, src_info, sc)
        scale = 2.0
    else:
        url = str(m.get("url") or (sc or {}).get("url") or "").replace("https://", "").replace("http://", "").rstrip("/")
        if src:
            from PIL import Image
            with Image.open(src) as im:
                ch = 960 * im.height / max(1, im.width)
            ch = min(max(ch, 960 * 0.5), 960 * 1.35)            # 너무 납작 · 너무 길면 자르거나 늘린다
            f, top_c, _ = _fit_capture(src, 960 / ch, m.get("crop"), work, oid)
            src_info = (f, top_c, False)
        else:
            # 높이를 안 주면 내용 길이에 맞춘다(빈 아래쪽 없이) — 한 번 재 보고 다시 그린다
            ch = (sc or {}).get("height")
            if not ch:
                _, _, end = _web_screen(_Doc(), None, 960, 4000, {**(sc or {}), "items": (sc or {}).get("items") or []})
                ch = min(max(end + 56, 480), 960 * 1.35)
            ch = float(ch)
            url = url or "example.com"
        lay = _browser(d, src_info, sc, url or (src.stem if src else ""), ch)
        scale = 1.2
    fc = _fig_run(d, work, oid, "Mock", out, scale)
    W, H = lay["root_w"], lay["root_h"]
    info = {"app": "figcraft", "device": device, "editable": _rel(fc),
            "size": [round(W * scale), round(H * scale)],
            "screen_box": _ratio(lay["screen"], W, H),
            "transparent": True, "as": "image"}
    if lay["items"]:
        info["item_boxes"] = [_ratio(b, W, H) for b in lay["items"]]
    if lay["dropped"]:
        info["dropped"] = lay["dropped"]
        print(f"[재료] {oid}: 화면에 안 들어가 뺀 항목 {len(lay['dropped'])}개 — {' · '.join(lay['dropped'][:3])}")
    if src is None:
        info["mock"] = True               # 가상 화면 — 콘티에 mock 표시가 있어야 한다(실제 서비스처럼 보이면 안 됨)
        if not m.get("mock"):
            print(f"[재료] {oid}: 가상 앱 화면입니다 — 콘티 재료에 \"mock\": true 를 적어 주세요")
    else:
        info["source"] = _rel(src)
    return info


ADAPTERS = {"ui_mock": ui_mock}
