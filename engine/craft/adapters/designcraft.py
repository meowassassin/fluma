"""DesignCraft 어댑터 — 한글 조판이 좋은 정보 카드(info_card) · 썸네일(thumbnail).

info_card: 제목 · 본문 · 요점 · 출처를 흰 카드 한 장에 조판한다. 여러 장이면 데이터 병합(data.merge)으로 같은 틀에서 찍는다.

  { "id": "m1", "type": "info_card", "kicker": "알아두기", "title": "버그라는 말은 에디슨이 먼저 썼다",
    "body": "1878년 편지에서 기계의 작은 결함을 bug 라고 불렀습니다.",
    "points": ["1947년 일지는 '처음 발견된 진짜 벌레'", "용어 자체는 그보다 70년 앞서"],
    "source": "Edison 편지, 1878 · 스미소니언", "accent": "#2563EB", "theme": "light" }
  { "id": "m1", "type": "info_card", "rows": [ {"title": "…", "points": ["…"]}, {"title": "…"} ], "row": 1 }
  { "id": "m1", "type": "info_card", "csv": "data/tips.csv", "row": "02" }

  - rows · csv: 한 줄 = 카드 한 장(칸: name · kicker · title · body · points(목록, CSV 면 | 로 구분) · source).
    모든 줄을 한 틀에 병합하므로 카드 크기 · 칸 위치가 같다(시리즈 카드). row(0부터 번호 또는 name 값)를 주면 그 장이 재료,
    안 주면 첫 장이 재료이고 나머지는 기록 "pages" 에 남는다
  - frame: "card"(기본: 카드만, 둥근 모서리 밖은 투명 + 옅은 그림자) | "full"(1080×1920 배경까지 — 콘티 place 는 "full")
  - theme: "light" | "dark", accent: 강조색(번호 · 머리말)
  - 글이 넘치면 제목 크기를 줄이고, 본문은 6줄 · 요점은 3줄에서 … 로 자른다(기록 clipped)

thumbnail: 썸네일 PNG 두 장 — 세로 1080×1920(재료 파일) + 가로 1280×720(기록 "landscape").

  { "id": "m9", "type": "thumbnail" }                                   ← 콘티 title · 첫 장면 자막 · 첫 사진 재료로
  { "id": "m9", "type": "thumbnail", "title": "컴퓨터 버그, 진짜 벌레였다", "hook": "1947년 하버드",
    "src": "data/compositions/<id>/craft/src/logbook.jpg", "emphasis": "진짜 벌레", "accent": "#FFD400" }

  - title 이 없으면 콘티 title, hook 이 없으면 콘티 badge · 첫 장면 자막, src 가 없으면 앞 장면에서 만든 사진 · 그림 재료(없으면 글자만)
  - emphasis: 제목에서 강조색으로 칠할 낱말(없으면 콘티 hook_number 가 제목에 있을 때 그것)
  - 사람이 고칠 .designcraft 두 개(세로 · 가로)를 남긴다

글꼴은 Noto Sans CJK KR(시스템 설치본 — Pretendard 는 DesignCraft 가 못 읽는다). 줄은 낱말 경계에서 미리 끊어(강제 줄바꿈 U+2028)
FigCraft 어댑터와 같은 글자 재기(wrap)를 쓴다 — 렌더 결과와 칸 높이가 맞는다.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
from pathlib import Path

FONT = "Noto Sans CJK KR"
LS = " "                     # DesignCraft 강제 줄바꿈(같은 단락 안)
_STYLE = {400: "Regular", 500: "Medium", 700: "Bold", 900: "Black"}


def _wrapper():
    from . import figcraft
    return figcraft


# ---------------------------------------------------------------- DesignCraft 스크립트
class _Script:
    """한 줄 = 명령 하나. add() 는 단계 번호를 돌려준다("$N.id" · "$N.story" 로 잇는다)"""

    def __init__(self):
        self.lines: list[str] = []
        self.swatches: dict[str, str] = {}

    def add(self, cmd: str, params: dict | None = None) -> int:
        self.lines.append(cmd + (" " + json.dumps(params, ensure_ascii=False) if params is not None else ""))
        return len(self.lines) - 1

    def swatch(self, color: str) -> str:
        """#hex → 견본 이름(처음 쓸 때 만든다). [Paper] · [Black] · [None] 은 그대로"""
        if color.startswith("["):
            return color
        c = color.upper()
        if c not in self.swatches:
            nm = f"C{c.lstrip('#')}"
            self.add("swatch.create", {"name": nm, "color": c})
            self.swatches[c] = nm
        return self.swatches[c]

    def box(self, rect, fill: str | None, radius: float = 0, shadow: dict | None = None, opacity: float | None = None) -> int:
        n = self.add("frame.create", {"rect": [round(v, 2) for v in rect], "content": "unassigned"})
        self.add("object.stroke", {"swatch": "[None]", "ids": [f"${n}.id"]})
        self.add("object.fill", {"swatch": self.swatch(fill) if fill else "[None]", "ids": [f"${n}.id"]})
        if radius:
            self.add("object.cornerOptions", {"shape": "rounded", "size": radius, "ids": [f"${n}.id"]})
        if shadow:
            self.add("object.dropShadow", {"on": True, "ids": [f"${n}.id"], **shadow})
        if opacity is not None:
            self.add("object.opacity", {"opacity": opacity, "ids": [f"${n}.id"]})
        return n

    def text(self, rect, text: str, size: float, color: str, weight: int = 400, leading: float | None = None,
             tracking: int = 0, align: str = "left", field: str | None = None, vjust: str | None = None,
             label: str | None = None, runs: list[tuple[int, int, str]] | None = None) -> int:
        """글 상자. field 를 주면 빈 상자에 병합 칸을 넣는다(값은 data.merge 가). runs: [(시작 바이트, 끝 바이트, 색)] 부분 색"""
        p = {"rect": [round(v, 2) for v in rect], "content": "text"}
        if not field:
            p["text"] = text
        n = self.add("frame.create", p)
        if field:
            self.add("data.placeholder.add", {"field": field, "story": f"${n}.story", "at": 0})
        self.add("object.textFrameOptions", {"inset": 0, "verticalJustification": vjust or "top", "ids": [f"${n}.id"]})
        self.add("text.select", {"story": f"${n}.story", "anchor": 0, "focus": 1 << 20})
        attrs = {"fontFamily": FONT, "fontStyle": _STYLE.get(weight, "Regular"), "size": size, "fill": self.swatch(color),
                 "tracking": tracking}
        if leading:
            attrs["leading"] = {"kind": "points", "value": round(leading, 2)}
        self.add("type.char", {"attrs": attrs})
        self.add("type.para", {"attrs": {"align": align, "hyphenate": False}})
        for a, b, col in runs or []:
            self.add("text.select", {"story": f"${n}.story", "anchor": a, "focus": b})
            self.add("type.char", {"attrs": {"fill": self.swatch(col)}})
        if label:
            self.add("object.label", {"label": label, "ids": [f"${n}.id"]})
        return n


def _dc(args: list, work: Path, what: str, stdin: str | None = None, timeout: int = 120) -> str:
    from ..materials import cli
    try:
        r = subprocess.run([cli("designcraft"), *[str(a) for a in args]], cwd=str(work), text=True, capture_output=True,
                           timeout=timeout, input=stdin, env={**os.environ, "DO_NOT_TRACK": "1"})
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"DesignCraft 가 {timeout}초 안에 끝나지 않았습니다({what})")
    if r.returncode != 0:
        raise RuntimeError(f"DesignCraft 실패({what}): {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout


def _run_script(sc: _Script, work: Path, name: str, save: Path, inp: Path | None = None) -> None:
    f = work / f"{name}.dcs"
    f.write_text("\n".join(sc.lines) + "\n", "utf-8")
    args = ["script", str(f)]
    if inp:
        args += ["--in", str(inp)]
    _dc(args + ["--save", str(save)], work, name)
    if not save.exists():
        raise RuntimeError(f"DesignCraft 가 {save.name} 을 쓰지 않았습니다")


def _export(doc: Path, out: Path, work: Path, page: int = 0) -> None:
    _dc(["run", "--in", str(doc), "--page", str(page), "--scale", "1", "--export", str(out)], work, out.name)
    if not out.exists():
        raise RuntimeError(f"DesignCraft 내보내기 실패: {out.name}")


def _rel(p: Path) -> str:
    from ..materials import ROOT
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _u8(s: str, i: int) -> int:
    """글자 위치 → UTF-8 바이트 위치(text.select 는 바이트로 센다)"""
    return len(s[:i].encode("utf-8"))


def _lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ---------------------------------------------------------------- info_card
_THEMES = {
    "light": {"page": "#ECEAE6", "card": "#FFFFFF", "ink": "#16181D", "body": "#434852", "muted": "#8B9099", "rule": "#E6E3DE"},
    "dark": {"page": "#0E1014", "card": "#1B1E24", "ink": "#F4F5F7", "body": "#C5C9D1", "muted": "#7D838D", "rule": "#2C3038"},
}
CW, CX = 936.0, 72.0               # 카드 폭 · 왼쪽(1080 폭 안)
PAD = 76.0                          # 카드 안 여백
TW = CW - PAD * 2                   # 글 폭
NUM_W = 74.0                        # 요점 번호 칸


def _rows(m: dict) -> list[dict]:
    from ..materials import _abs
    if isinstance(m.get("rows"), list) and m["rows"]:
        rows = [r if isinstance(r, dict) else {"title": str(r)} for r in m["rows"]]
    elif isinstance(m.get("csv"), str):
        f = _abs(m["csv"])
        if not f.exists():
            raise RuntimeError(f"info_card CSV 가 없습니다: {m['csv']}")
        rows = list(csv.DictReader(f.read_text("utf-8-sig").splitlines()))
        if not rows:
            raise RuntimeError(f"info_card CSV 에 줄이 없습니다: {m['csv']}")
    else:
        rows = [{k: m.get(k) for k in ("name", "kicker", "title", "body", "points", "source")}]
    out = []
    for i, r in enumerate(rows):
        pts = r.get("points")
        if isinstance(pts, str):
            pts = [p.strip() for p in pts.replace("\n", "|").split("|") if p.strip()]
        out.append({"name": str(r.get("name") or i), "kicker": str(r.get("kicker") or "").strip(),
                    "title": str(r.get("title") or "").strip(), "body": str(r.get("body") or "").strip(),
                    "points": [str(p).strip() for p in (pts or []) if str(p).strip()],
                    "source": str(r.get("source") or "").strip()})
    if not any(r["title"] or r["body"] or r["points"] for r in out):
        raise RuntimeError("info_card 에 title · body · points 중 하나는 있어야 합니다")
    return out


def _title_size(rows: list[dict]) -> int:
    """제목: 모든 줄이 3줄 안에 들어가는 가장 큰 크기(76 → 56) — 시리즈 카드는 같은 크기"""
    fg = _wrapper()
    fits = []
    for s in (76, 70, 64, 60, 56):
        ws = [fg.wrap(r["title"], TW, s, 700, -0.025, balance=True) for r in rows if r["title"]]
        if all(len(w) <= 3 for w in ws):
            fits.append((sum(fg.break_penalty(w) for w in ws), s))
            if fits[-1][0] == 0 or len(fits) >= 2:
                break
    return min(fits, key=lambda x: (x[0], -x[1]))[1] if fits else 56


def _card_layout(rows: list[dict], t_size: int | None = None) -> dict:
    """줄들을 재서 칸 높이(줄 수의 최댓값)를 정한다 → 칸별 (글자 크기, 줄 간격, 줄 수) + 줄마다 끊은 글"""
    fg = _wrapper()
    clipped = []
    t_size = t_size or _title_size(rows)
    t_lead = round(t_size * 1.3)
    b_size, b_lead, p_size, p_lead = 40, 64, 42, 60
    pw = TW - NUM_W
    out_rows = []
    for r in rows:
        t = fg.wrap(r["title"], TW, t_size, 700, -0.025, balance=True, max_lines=3) if r["title"] else []
        b = fg.wrap(r["body"], TW, b_size, 400, -0.01, max_lines=6) if r["body"] else []
        ps = [fg.wrap(p, pw, p_size, 500, -0.015, max_lines=3) for p in r["points"][:5]]
        if len(fg.wrap(r["body"], TW, b_size, 400, -0.01)) > 6 or len(r["points"]) > 5 or \
                any(len(fg.wrap(p, pw, p_size, 500, -0.015)) > 3 for p in r["points"][:5]):
            clipped.append(r["name"])
        out_rows.append({**r, "t": t, "b": b, "ps": ps})
    n_t = max((len(r["t"]) for r in out_rows), default=0)
    n_b = max((len(r["b"]) for r in out_rows), default=0)
    n_p = max((len(r["ps"]) for r in out_rows), default=0)
    p_lines = [max((len(r["ps"][i]) for r in out_rows if i < len(r["ps"])), default=0) for i in range(n_p)]
    return {"rows": out_rows, "t": (t_size, t_lead, n_t), "b": (b_size, b_lead, n_b), "p": (p_size, p_lead, p_lines),
            "kicker": any(r["kicker"] for r in out_rows), "source": any(r["source"] for r in out_rows), "clipped": clipped}


def _card_template(L: dict, th: dict, accent: str, full: bool, min_h: float = 0) -> tuple[_Script, list, float, float]:
    """병합 틀 → (스크립트, 병합 칸 이름 목록, 카드 위 y, 카드 높이). min_h: 시리즈의 다른 카드에 맞춘 높이 —
    남는 높이는 출처 위에 둔다(내용은 위에서부터 붙여 쌓고 출처는 카드 바닥에)"""
    t_size, t_lead, n_t = L["t"]
    b_size, b_lead, n_b = L["b"]
    p_size, p_lead, p_lines = L["p"]
    # 세로 길이 먼저 계산(위에서부터 쌓는다)
    y = PAD
    parts = []
    if L["kicker"]:
        parts.append(("kicker", y))
        y += 34 + 30
    if n_t:
        parts.append(("title", y))
        y += t_lead * n_t - (t_lead - t_size) * 0.5
    if n_b or p_lines:
        y += 40
        parts.append(("rule", y))
        y += 2 + 40
    if n_b:
        parts.append(("body", y))
        y += b_lead * n_b
        if p_lines:
            y += 36
    for i, n in enumerate(p_lines):
        parts.append((f"p{i + 1}", y))
        y += p_lead * n + (28 if i < len(p_lines) - 1 else 0)
    if L["source"]:
        y += 52
        parts.append(("source", y))
        y += 30
    ch = y + PAD - 8
    if min_h > ch:
        parts = [(nm, yy + (min_h - ch) if nm == "source" else yy) for nm, yy in parts]
        ch = min_h
    # 카드 자리: 화면 위 2/3 의 가운데(아래 1/3 은 자막 자리). 카드만 낼 때는 문서가 카드 크기
    if full:
        W, H = 1080.0, 1920.0
        top = max(200.0, min(860.0 - ch / 2, 1360.0 - ch))
        x0 = CX
    else:
        W, H, top, x0 = CW, ch, 0.0, 0.0
    sc = _Script()
    sc.add("file.new", {"width": W, "height": H, "units": "points", "margins": 0, "pages": 1, "intent": "mobile"})
    sc.add("swatch.create", {"name": "Reserved", "color": "#000000"})    # 자리 맡기: 병합 칸이 정해지면 data.source.select 로 바꾼다(단계 번호 유지)
    if full:
        sc.box([0, 0, W, H], th["page"])
        sc.box([x0, top, x0 + CW, top + ch], th["card"], 40, {"distance": 18, "size": 46, "opacity": 22})
    else:
        sc.box([0, 0, W, H], th["card"])
    fields = []
    X = x0 + PAD
    for name, yy in parts:
        Y = top + yy
        if name == "kicker":
            sc.text([X, Y, X + TW, Y + 50], "", 30, accent, 700, 40, 40, field="kicker", label="kicker")
            fields.append("kicker")
        elif name == "title":
            sc.text([X, Y, X + TW, Y + t_lead * n_t + 20], "", t_size, th["ink"], 700, t_lead, -25, field="title", label="title")
            fields.append("title")
        elif name == "rule":
            sc.box([X, Y, X + 64, Y + 5], accent, 2.5)
        elif name == "body":
            sc.text([X, Y, X + TW, Y + b_lead * n_b + 20], "", b_size, th["body"], 400, b_lead, -10, field="body", label="body")
            fields.append("body")
        elif name == "source":
            sc.text([X, Y, X + TW, Y + 44], "", 27, th["muted"], 400, 36, 0, field="source", label="source")
            fields.append("source")
        else:
            i = int(name[1:]) - 1
            sc.text([X, Y + 3, X + NUM_W, Y + p_lead], "", 34, accent, 900, p_lead, -10, field=f"n{i + 1}", label=f"n{i + 1}")
            sc.text([X + NUM_W, Y, X + TW, Y + p_lead * p_lines[i] + 20], "", p_size, th["ink"], 500, p_lead, -15,
                    field=f"p{i + 1}", label=f"p{i + 1}")
            fields += [f"n{i + 1}", f"p{i + 1}"]
    return sc, fields, top, ch


def _card_values(r: dict, fields: list[str]) -> dict:
    v = {"kicker": r["kicker"], "title": LS.join(r["t"]), "body": LS.join(r["b"]), "source": f"출처  {r['source']}" if r["source"] else ""}
    for i in range(5):
        has = i < len(r["ps"])
        v[f"n{i + 1}"] = f"{i + 1:02d}" if has else ""
        v[f"p{i + 1}"] = LS.join(r["ps"][i]) if has else ""
    return {k: v.get(k, "") for k in fields}


def _round_alpha(f: Path, radius: float, shadow: bool = True) -> tuple[int, int]:
    """카드만 낸 PNG: 둥근 모서리 밖을 투명하게 + 둘레에 옅은 그림자(움직임 단계가 배경 위에 그대로 놓는다)"""
    from PIL import Image, ImageDraw, ImageFilter
    with Image.open(f) as im0:
        im = im0.convert("RGBA")
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    im.putalpha(mask)
    if not shadow:
        im.save(f)
        return w, h
    m = 56
    canvas = Image.new("RGBA", (w + m * 2, h + m * 2), (0, 0, 0, 0))
    sh = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([m, m + 16, m + w, m + h + 16], radius=radius, fill=70)
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    canvas.paste(Image.new("RGBA", canvas.size, (0, 0, 0, 255)), (0, 0), sh)
    canvas.alpha_composite(im, (m, m))
    canvas.save(f)
    return canvas.size


def info_card(m: dict, out: Path, work: Path) -> dict:
    rows = _rows(m)
    th = _THEMES.get(str(m.get("theme") or "light"), _THEMES["light"])
    accent = str(m.get("accent") or ("#2563EB" if th is _THEMES["light"] else "#7AA2FF"))
    full = str(m.get("frame") or "card") == "full"
    oid = m["id"]
    # 어느 장이 재료인가
    pick = 0
    if m.get("row") is not None:
        rv = m["row"]
        names = [r["name"] for r in rows]
        if isinstance(rv, int) and not isinstance(rv, bool) and 0 <= rv < len(rows):
            pick = rv
        elif str(rv) in names:
            pick = names.index(str(rv))
        else:
            raise RuntimeError(f"info_card row {rv} 가 없습니다(0~{len(rows) - 1} 또는 name: {' · '.join(names[:5])})")
    # 칸 줄 수가 같은 줄끼리 한 틀로 병합한다(한 줄 제목 카드에 두 줄 자리가 비지 않게). 카드 높이는 시리즈 전체 최댓값
    t_size = _title_size(rows)
    groups: dict[str, list[int]] = {}
    lays = []
    for i, r in enumerate(rows):
        Li = _card_layout([r], t_size)
        lays.append(Li)
        sig = json.dumps([Li["t"], Li["b"], Li["p"], Li["kicker"], Li["source"]])
        groups.setdefault(sig, []).append(i)
    min_h = max(_card_template(Li, th, accent, full)[3] for Li in lays)
    clipped = [n for Li in lays for n in Li["clipped"]]
    pages, where = [], {}
    for gi, idx in enumerate(groups.values()):
        if m.get("row") is not None and pick not in idx:
            continue
        L = _card_layout([rows[i] for i in idx], t_size)
        sc, fields, top, ch = _card_template(L, th, accent, full, min_h)
        tag = oid if len(groups) == 1 else f"{oid}.g{gi + 1}"
        # 병합 칸 목록을 알려 줄 CSV(머리글만) — data.source.select 는 파일이 있어야 한다
        fcsv = work / f"{tag}.fields.csv"
        fcsv.write_text(",".join(fields) + "\n" + ",".join("x" for _ in fields) + "\n", "utf-8")
        sc.lines[1] = ("data.source.select " + json.dumps({"path": str(fcsv), "name": f"{tag}.csv"}, ensure_ascii=False))
        tpl = work / f"{tag}.template.designcraft"
        _run_script(sc, work, f"{tag}.template", tpl)
        mg = _Script()
        mg.add("data.merge", {"rows": [_card_values(r, fields) for r in L["rows"]]})
        merged = work / f"{tag}.designcraft"
        _run_script(mg, work, f"{tag}.merge", merged, inp=tpl)
        for k, i in enumerate(idx):
            where[i] = (merged, tpl, k, top, ch)
    for i in range(len(rows)):
        if i not in where:
            continue
        merged_i, _, k, _, _ = where[i]
        f = out if i == pick else out.with_name(f"{out.stem}.p{i + 1:02d}.png")
        _export(merged_i, f, work, k)
        size = _round_alpha(f, 40) if not full else (1080, 1920)
        pages.append(f)
    merged, tpl, _, top, ch = where[pick]
    L = {"rows": [{"name": r["name"]} for r in rows], "clipped": clipped}
    info = {"app": "designcraft", "editable": _rel(merged), "template": _rel(tpl), "as": "image",
            "size": list(size), "frame": "full" if full else "card", "font": FONT}
    if full:
        info["card_box"] = [round(CX / 1080, 4), round(top / 1920, 4), round(CW / 1080, 4), round(ch / 1920, 4)]
    else:
        info["transparent"] = True
    if len(rows) > 1:
        info["rows"] = len(rows)
        info["row"] = L["rows"][pick]["name"]
        if m.get("row") is None:
            info["pages"] = [_rel(p) for p in pages]
    if L["clipped"]:
        info["clipped"] = L["clipped"]
        print(f"[재료] {oid}: 글이 길어 일부를 … 로 잘랐습니다({' · '.join(L['clipped'][:3])}) — 본문 6줄 · 요점 5개(각 3줄)까지")
    return info


# ---------------------------------------------------------------- thumbnail
def _storyboard(out: Path) -> dict:
    """재료 경로(data/compositions/<id>/craft/materials/sNN/…)에서 콘티를 찾는다"""
    from ..materials import ROOT, _load
    try:
        sid = out.resolve().relative_to(ROOT / "data" / "compositions").parts[0]
    except ValueError:
        return {}
    return _load(ROOT / "data" / "storyboards" / f"{sid}.json")


def _pick_image(out: Path) -> Path | None:
    """앞에서 만든 사진 · 그림 재료 중 첫째(썸네일 바탕)"""
    from ..materials import ROOT, _load
    base = out.parent.parent
    for rec_f in sorted(base.glob("s[0-9][0-9]/*.json")):
        rec = _load(rec_f)
        if rec.get("type") in ("photo", "image", "illustration", "stock_photo") and rec.get("file"):
            f = ROOT / rec["file"]
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and f.exists() and f != out:
                return f
    return None


def _prep_bg(src: Path, W: int, H: int, work: Path, name: str) -> Path:
    """바탕 사진을 그 비율로 미리 잘라 둔다(가운데 기준, 얼굴 · 물체가 위쪽이면 위 1/3 기준) — DesignCraft fill 이 자르는 위치를 정하지 않아도 되게"""
    from PIL import Image, ImageEnhance, ImageFilter
    with Image.open(src) as im0:
        im = im0.convert("RGB")
    f = work / f"{name}.bg.png"
    if H > W and im.width / im.height > 1.1:
        # 가로 사진을 세로 화면에 꽉 채우면 너무 확대돼 흐려진다 → 흐린 배경 위에 사진을 폭 맞춰 위쪽에(쇼츠 썸네일 문법)
        k = max(W / im.width, H / im.height)
        back = im.resize((max(W, round(im.width * k)), max(H, round(im.height * k))), Image.LANCZOS)
        bx, by = (back.width - W) // 2, (back.height - H) // 2
        back = back.crop((bx, by, bx + W, by + H)).filter(ImageFilter.GaussianBlur(38))
        back = ImageEnhance.Brightness(back).enhance(0.55)
        fw = W
        fh = round(im.height * fw / im.width)
        fit = im.resize((fw, fh), Image.LANCZOS)
        back.paste(fit, (0, max(120, round(H * 0.36 - fh / 2))))
        back.save(f)
        return f
    k = max(W / im.width, H / im.height)
    nw, nh = max(W, round(im.width * k)), max(H, round(im.height * k))
    im = im.resize((nw, nh), Image.LANCZOS)
    x0 = (nw - W) // 2
    y0 = int((nh - H) * (0.35 if H > W else 0.5))
    im.crop((x0, y0, x0 + W, y0 + H)).save(f)
    return f


def _title_runs(lines: list[str], emph: str, color: str) -> list[tuple[int, int, str]]:
    s = LS.join(lines)
    runs = []
    if emph:
        flat = s.replace(LS, " ")
        i = flat.find(emph)
        if i >= 0:
            runs.append((_u8(s, i), _u8(s, i + len(emph)), color))
    return runs


def _thumb(W: int, H: int, title: str, hook: str, bg: Path | None, emph: str, accent: str) -> tuple[_Script, dict]:
    fg = _wrapper()
    tall = H > W
    sc = _Script()
    sc.add("file.new", {"width": W, "height": H, "units": "points", "margins": 0, "pages": 1, "intent": "mobile"})
    if bg:
        n = sc.add("frame.create", {"rect": [0, 0, W, H], "content": "graphic"})
        sc.add("object.stroke", {"swatch": "[None]", "ids": [f"${n}.id"]})
        sc.add("file.place", {"path": str(bg), "frame": f"${n}.id"})
        sc.add("object.fit", {"mode": "fillProportionally", "ids": [f"${n}.id"]})
        # 글 자리를 어둡게: 세로는 아래쪽, 가로는 왼쪽
        g = sc.box([0, H * 0.38, W, H] if tall else [0, 0, W * 0.78, H], "#000000")
        sc.add("object.gradient", {"kind": "linear", "angle": -90 if tall else 0, "ids": [f"${g}.id"],
                                   "stops": [{"location": 0, "color": "#000000", "opacity": 0 if tall else 88},
                                             {"location": 55, "color": "#000000", "opacity": 62 if tall else 55},
                                             {"location": 100, "color": "#000000", "opacity": 90 if tall else 0}]})
    else:
        g = sc.box([0, 0, W, H], "#121317")
        sc.add("object.gradient", {"kind": "linear", "angle": -90, "ids": [f"${g}.id"],
                                   "stops": [{"location": 0, "color": "#1C1E24"}, {"location": 100, "color": "#08090B"}]})
    # 제목: 가장 큰 크기부터 줄 수 안에 들어가는 것
    tw = W - 144 if tall else W * (0.6 if bg else 0.84)
    max_l = 3
    sizes = (150, 136, 124, 112, 100, 92) if tall else (104, 96, 88, 80, 72, 64)
    # 들어가는 크기 중 가장 큰 것 — 단 꾸밈말이 줄 끝에 걸리면('안 나올 / 때') 한 단계 작은 크기에서 더 낫게 끊기는지 본다
    t_size, fits = sizes[-1], []
    for s in sizes:
        ls = fg.wrap(title, tw, s, 900, -0.03, balance=True)
        if len(ls) <= max_l and all(fg.text_width(ln, s, 900, -0.03) <= tw for ln in ls):
            fits.append((fg.break_penalty(ls), s))
            if fits[-1][0] == 0 or len(fits) >= 3:
                break
    if fits:
        t_size = min(fits, key=lambda x: (x[0], -x[1]))[1]
    lines = fg.wrap(title, tw, t_size, 900, -0.03, balance=True, max_lines=max_l)
    t_lead = round(t_size * 1.16)
    th_ = t_lead * len(lines)
    k_size = 46 if tall else 34
    hook_l = fg.ellipsize(hook, tw - 60, k_size, 700) if hook else ""
    k_h = k_size * 1.75
    gap = 34 if tall else 22
    block = (k_h + gap if hook_l else 0) + th_
    if tall:
        x = 72.0
        bottom = 1560.0 if bg else 900.0 + block / 2         # 아래 ~360 은 쇼츠 화면 단추 자리
        y = bottom - block
    else:
        x = 64.0
        y = (H - block) / 2
    if hook_l:
        kw = fg.text_width(hook_l, k_size, 700) + 52
        ink = "#111111" if _lum(accent) > 150 else "#FFFFFF"
        sc.box([x, y, x + kw, y + k_h], accent, k_h * 0.22)
        sc.text([x, y, x + kw, y + k_h], hook_l, k_size, ink, 700, k_size * 1.2, -10, "center", vjust="center", label="hook")
        y += k_h + gap
    tn = sc.text([x, y, x + tw + 40, y + th_ + t_size * 0.4], LS.join(lines), t_size, "#FFFFFF", 900, t_lead, -30,
                 runs=_title_runs(lines, emph, accent), label="title")
    sc.add("object.dropShadow", {"on": True, "distance": 4 if tall else 3, "size": 18 if tall else 12, "opacity": 55, "ids": [f"${tn}.id"]})
    return sc, {"title_lines": lines, "title_size": t_size}


def thumbnail(m: dict, out: Path, work: Path) -> dict:
    from ..materials import _abs
    sb = _storyboard(out)
    sc0 = (sb.get("scenes") or [{}])[0] if sb else {}
    title = str(m.get("title") or sb.get("title") or "").strip()
    if not title:
        raise RuntimeError("thumbnail 에 title 이 없습니다(콘티 title 도 비어 있음)")
    hook = m.get("hook")
    if hook is None:
        cap = str(sc0.get("caption") or "").replace("\n", " ").strip()
        hook = sb.get("badge") or (cap if cap and cap.replace(" ", "") not in title.replace(" ", "") else "")
    hook = str(hook or "").strip()
    emph = str(m.get("emphasis") or "")
    if not emph and sb.get("hook_number") and str(sb["hook_number"]) in title:
        emph = str(sb["hook_number"])
    accent = str(m.get("accent") or "#FFD400")
    src = None
    if isinstance(m.get("src"), str) and m["src"]:
        src = _abs(m["src"])
        if not src.exists():
            raise RuntimeError(f"thumbnail 바탕 그림이 없습니다: {m['src']}")
    elif m.get("src") is not False:
        src = _pick_image(out)
    oid = m["id"]
    info = {"app": "designcraft", "as": "image", "title": title, "hook": hook, "font": FONT}
    for tag, (W, H), f in (("v", (1080, 1920), out), ("h", (1280, 720), out.with_name(f"{out.stem}.16x9.png"))):
        bg = _prep_bg(src, W, H, work, f"{oid}.{tag}") if src else None
        sc, meta = _thumb(W, H, title, hook, bg, emph, accent)
        doc = work / (f"{oid}.designcraft" if tag == "v" else f"{oid}.16x9.designcraft")
        _run_script(sc, work, f"{oid}.{tag}", doc)
        _export(doc, f, work)
        if tag == "v":
            info.update({"editable": _rel(doc), "size": [W, H], "title_lines": meta["title_lines"]})
        else:
            info.update({"landscape": _rel(f), "landscape_editable": _rel(doc)})
    if src:
        info["background"] = _rel(src)
    return info


ADAPTERS = {"info_card": info_card, "thumbnail": thumbnail}
