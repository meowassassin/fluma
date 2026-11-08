"""DeckCraft 어댑터 — 도식 재료(type: diagram).

단계 · 비교 · 순환 · 조직도를 글만 주면 DeckCraft SmartArt 가 배치까지 계산한다(좌표로 그리지 않는다).
슬라이드를 540×960pt(= 1080×1920px) 세로로 만들고 render 로 PNG 를 바로 낸다(PDF 를 거치지 않는다).
DeckCraft 는 빌드 애니메이션을 렌더하지 못한다 → 정지 PNG 와 함께 항목별 투명 레이어 PNG 를 내서
움직임 단계가 하나씩 등장시킨다(같은 슬라이드에서 다른 항목을 숨기고 투명 배경으로 내보낸 것 — 위치가 그대로 맞는다).

순서(work 폴더에서, 모두 창 없이):
  1. 새 덱(세로 · 한글 글꼴 Noto Sans CJK KR) → 제목 글상자 → SmartArt(종류 · 레이아웃 · 스타일 · 색) → 화면에 맞는 크기
  2. 도형 목록(slide.inspect)으로 글 칸 크기를 재서 글자 크기를 정한다(SmartArt 기본 글자는 쇼츠에서 너무 작다) · 굵게 · 연결선 밝게
  3. 렌더: 전체 PNG(배경 포함) · 바탕(배경 + 제목만) · 항목별 레이어(투명, 내용만 잘라 box 기록)

콘티 칸:
  kind     "steps"(세로 단계 · 기본) · "compare"(두 칸 비교) · "cycle"(순환) · "hierarchy"(조직도 · 나무)
           · "pyramid" · "timeline" · "list"(세로 상자 목록)
  items    ["항목", …] — 앞에 탭(\\t) = 하위 항목(compare · hierarchy). compare 는 [["무료", "광고 있음", …], ["유료", …]] 도 된다
  title    제목(선택, 위쪽 가운데)
  cues     ["낱말", …] 항목마다 등장 시각을 맞출 나레이션 낱말(선택, 없으면 움직임 단계가 0.5초 간격)
  theme    DeckCraft 테마(기본 Nocturne — 어두운 바탕) · Paper · Slate · Harbor · Ember · Meadow · Coral Reef · DeckCraft
  style    SmartArt 스타일(기본 polished) · colors 색(기본 colorful) · layout SmartArt 레이아웃 직접(45종, deckcraft-cli describe smartArt.layout)
  transparent true → 전체 PNG 도 배경 없이(실제 화면 위에 겹칠 때)

기록(info) 칸:
  app "deckcraft" · as "image" · kind · layout · size [1080, 1920]
  layers   [{"file": 항목 PNG(투명 · 내용만), "box": [x, y, w, h](0~1, 이 재료 그림 기준), "cue": 낱말 | null, "text": 항목 글}, …] — 차례대로 등장
  base     바탕 PNG(배경 + 제목, 도식 없음) — 레이어를 하나씩 올릴 때 밑그림
  editable 편집 덱(work/<id>.deckcraft — DeckCraft 에서 SmartArt 그대로 고칠 수 있다 · convert 로 pptx)
"""
from __future__ import annotations

import json
from pathlib import Path

W_PT, H_PT = 540, 960
BOTTOM_PT = 660     # 도식 아래 끝(pt) — 그 아래(화면 73%~)는 자막 자리. 860 이면 마지막 칸이 자막과 겹쳤다(2026-11-06 통합 시험)
SCALE = 2
# kind → (insert.smartArt kind, smartArt.layout)
KINDS = {
    "steps": ("process", "verticalProcess"),
    "compare": ("list", "hBulletList"),
    "cycle": ("cycle", "cycle"),
    "hierarchy": ("hierarchy", "hierarchy"),
    "pyramid": ("pyramid", "pyramid"),
    "timeline": ("process", "timeline"),
    "list": ("list", "blockList"),
}
FONT = "Noto Sans CJK KR"      # Pretendard 는 시스템 글꼴이 아니라 DeckCraft 가 못 쓴다
LINE = "#C9D3E6"               # 조직도 연결선(기본은 남색이라 어두운 바탕에서 안 보인다)
BODY_TEXT = "#1F2430"          # 하위 항목 글자색


def _dc(lines: list, work: Path, name: str, src: Path | None = None, save: Path | None = None,
        export: Path | None = None, transparent: bool = False) -> list:
    """명령 줄들을 --cmd-file 로 돌린다 → [(명령 id, 결과), …]"""
    from ..materials import _run, cli
    cf = work / name
    cf.write_text("\n".join(lines) + "\n", "utf-8")
    args = [cli("deckcraft"), "run"]
    if src:
        args += ["--in", src]
    args += ["--cmd-file", cf, "--print"]
    if save:
        args += ["--save", save]
    if export:
        args += ["--export", export, "--export-params", json.dumps({"transparentBackground": transparent, "scale": SCALE})]
    try:
        out = _run(args, work, timeout=120)
    except RuntimeError as e:
        raise RuntimeError(f"DeckCraft 실패: {str(e)[-300:]}") from e
    finally:
        cf.unlink(missing_ok=True)
    res = []
    for ln in out.splitlines():
        k, sep, v = ln.partition(" → ")
        if sep:
            try:
                res.append((k.strip(), json.loads(v)))
            except ValueError:
                res.append((k.strip(), v))
    return res


def _c(cmd: str, **p) -> str:
    return f"{cmd}={json.dumps(p, ensure_ascii=False)}" if p else cmd


def norm_items(items, kind: str) -> list[str]:
    """콘티 items → SmartArt 줄(탭 = 하위). compare 의 [[머리, 내용…], …] 도 받는다"""
    out = []
    for it in items or []:
        if isinstance(it, (list, tuple)):
            if not it:
                continue
            out.append(str(it[0]).strip())
            out += ["\t" + str(x).strip() for x in it[1:] if str(x).strip()]
        else:
            s = str(it).rstrip()
            if s.strip():
                out.append(s)
    if not out:
        raise RuntimeError("diagram 재료에는 items(항목 목록)가 필요합니다")
    if kind == "compare" and not any(s.startswith("\t") for s in out) and len(out) > 2:
        raise RuntimeError("compare 는 [[\"A\", \"A 내용\"…], [\"B\", \"B 내용\"…]] 또는 탭(\\t)으로 하위 항목을 적어 주세요")
    return out


def _text_box(c: dict) -> list:
    """도형 안에서 글이 들어갈 폭 — 삼각형(피라미드 꼭대기)은 가운데 절반쯤"""
    x, y, w, h = c["box"]
    return [x, y, w * 0.36, h] if c.get("preset") in ("triangle", "isoscelesTriangle") else [x, y, w, h]


def _height(kind: str, lines: list[str], y0: float) -> float:
    """도식 높이(pt) — 비교 · 목록은 하위 항목 수만큼만(꽉 채우면 빈 칸이 길게 남는다)"""
    full = BOTTOM_PT - y0
    if kind in ("compare", "list"):
        tops = [s for s in lines if not s.startswith("\t")]
        subs = max(1, len(lines) - len(tops))
        per = subs / max(1, len(tops)) if kind == "compare" else subs
        want = (110 + 56 * per) if kind == "compare" else (len(tops) * 80 + 56 * subs)
        return round(min(full, max(220, want)), 1)
    return full


def _wt(ch: str) -> float:
    if ch.isspace():
        return 0.3
    return 1.0 if ord(ch) >= 0x1100 else 0.58


def font_for(box: list, text: str, lo: float = 14, hi: float = 30) -> float:
    """글 칸 [x, y, w, h](pt) 안에 들어가는 글자 크기 — 가장 긴 줄이 폭의 80%, 줄들이 높이의 75% 안"""
    lines = [ln for ln in (text or "").split("\n") if ln.strip()] or [" "]
    em = max(sum(_wt(c) for c in ln) for ln in lines) or 1.0
    by_w = box[2] * 0.80 / em
    by_h = box[3] * 0.75 / (len(lines) * 1.3)
    return round(max(lo, min(hi, by_w, by_h)), 1)


def units_of(children: list, lines: list[str], kind: str) -> tuple[list[dict], list]:
    """SmartArt 도형들 → (항목(등장 단위) 목록 [{text, ids, box, head}], 바탕에 둘 도형 id 목록).
    - 등장 단위: hierarchy 는 모든 칸, 나머지는 맨 위 수준 항목. 머리 칸은 글이 항목과 같은(또는 첫 줄이 같은) 칸,
      나머지 글 칸(하위 항목)은 가장 가까운 머리 칸의 항목에 붙는다 — 도형 순서는 레이아웃마다 달라 글로 찾는다
    - 작은 화살표는 가장 가까운 두 칸 중 뒤 항목에 → 'A → B' 화살표는 B 와 함께 등장(순환의 마지막 화살표는 마지막 항목과)
    - 조직도 연결선은 아래 끝에 닿는 자식 칸과
    - 여러 항목에 걸친 큰 도형(타임라인 막대 등)은 바탕 — 처음부터 보인다"""
    tops = [s.strip() for s in lines if kind == "hierarchy" or not s.startswith("\t")]
    texts = [c for c in children if (c.get("text") or "").strip()]
    others = [c for c in children if not (c.get("text") or "").strip()]
    units: list[dict] = []
    used: set = set()
    for t in tops:
        c = next((c for c in texts if c["id"] not in used and c["text"].strip() == t), None) or \
            next((c for c in texts if c["id"] not in used and c["text"].strip().split("\n")[0].strip() == t), None)
        if c:
            used.add(c["id"])
            units.append({"text": t, "ids": [c["id"]], "boxes": [c["box"]], "head": [c["id"]]})
    if not units:
        return [], []

    def gap(a, b):
        dx = max(0.0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
        dy = max(0.0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
        return (dx * dx + dy * dy) ** 0.5

    def centre(a, b):
        return ((a[0] + a[2] / 2 - b[0] - b[2] / 2) ** 2 + (a[1] + a[3] / 2 - b[1] - b[3] / 2) ** 2) ** 0.5

    for c in [c for c in texts if c["id"] not in used]:
        k = min(range(len(units)), key=lambda i: (min(gap(c["box"], b) for b in units[i]["boxes"]), i))
        units[k]["ids"].append(c["id"])
        units[k]["boxes"].append(c["box"])
    heads = [u["boxes"][0] for u in units]
    span = max(h[0] + h[2] for h in heads) - min(h[0] for h in heads)
    frame = []
    for o in others:
        k = None
        bx = o["box"]
        if len(units) > 2 and bx[2] > 0.6 * span and bx[2] > 2.5 * max(h[2] for h in heads):
            frame.append(o["id"])
            continue
        if o.get("preset") == "line":
            ox0, ox1, oy1 = bx[0], bx[0] + bx[2], bx[1] + bx[3]
            best = 0.0
            for i, h in enumerate(heads):
                ov = min(ox1, h[0] + h[2]) - max(ox0, h[0])
                if abs(h[1] - oy1) <= 8 and ov > best:
                    best, k = ov, i
        elif "arrow" in str(o.get("preset") or "").lower() or "Arrow" in str(o.get("name") or ""):
            ds = sorted((gap(bx, h), i) for i, h in enumerate(heads))
            k = max(i for d, i in ds[:2] if d <= ds[0][0] + 6)
        if k is None:                             # 점 · 장식: 가운데가 가장 가까운 항목
            k = min(range(len(units)), key=lambda i: centre(bx, heads[i]))
        units[k]["ids"].append(o["id"])
        units[k]["boxes"].append(bx)
    for u in units:
        bs = u.pop("boxes")
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        u["box"] = [x0, y0, max(b[0] + b[2] for b in bs) - x0, max(b[1] + b[3] for b in bs) - y0]
    return units, frame


def _crop_layer(f: Path, dst: Path) -> list | None:
    """투명 PNG 의 내용만 잘라 dst 로 → box [x, y, w, h](0~1)"""
    from PIL import Image
    with Image.open(f) as im:
        im = im.convert("RGBA")
        W, H = im.size
        bb = im.getchannel("A").getbbox()
        if not bb:
            return None
        p = 6
        bb = (max(0, bb[0] - p), max(0, bb[1] - p), min(W, bb[2] + p), min(H, bb[3] + p))
        im.crop(bb).save(dst)
    return [round(bb[0] / W, 5), round(bb[1] / H, 5), round((bb[2] - bb[0]) / W, 5), round((bb[3] - bb[1]) / H, 5)]


def diagram(m: dict, out: Path, work: Path) -> dict:
    """DeckCraft: 항목 글 → SmartArt 도식 → 세로 PNG + 항목별 레이어"""
    from ..materials import _run, cli, ROOT
    mid = m["id"]
    work.mkdir(parents=True, exist_ok=True)
    kind = str(m.get("kind") or "steps")
    if kind not in KINDS and not m.get("layout"):
        raise RuntimeError(f"모르는 diagram kind: {kind} ({' · '.join(KINDS)})")
    sa_kind, layout = KINDS.get(kind, ("list", None))
    layout = m.get("layout") or layout
    lines = norm_items(m.get("items"), kind)
    title = str(m.get("title") or "").strip()

    # 1. 덱 · 제목 · SmartArt
    y0 = 200 if title else 110
    cmds = [_c("file.new", theme=m.get("theme") or "Nocturne", size=[W_PT, H_PT], blank=True),
            _c("design.fonts", major=FONT, minor=FONT),
            _c("slide.new", layout="blank")]
    if title:
        cmds += [_c("insert.textBox", rect=[30, 70, W_PT - 60, 110], text=title),
                 _c("format.size", size=34 if len(title) <= 14 else 28), _c("format.bold"), _c("format.align", align="center")]
    h = _height(kind, lines, y0)                  # 비교 · 목록은 짧게, 가운데보다 조금 위에
    cmds += [_c("insert.smartArt", kind=sa_kind, items=lines)]
    if layout:
        cmds.append(_c("smartArt.layout", kind=layout))
    cmds += [_c("smartArt.style", style=m.get("style") or "polished"),
             _c("smartArt.colors", colors=m.get("colors") or "colorful"),
             _c("shape.setBounds", x=30, y=round(y0 + (BOTTOM_PT - y0 - h) * 0.4, 1), w=W_PT - 60, h=h),
             _c("slide.inspect")]
    deck = work / f"{mid}.deckcraft"
    res = _dc(cmds, work, f"{mid}.build.txt", save=deck)
    ins = next((v for k, v in reversed(res) if k == "slide.inspect"), None) or {}
    shapes = ins.get("shapes") or []
    group = next((s for s in shapes if s.get("kind") == "group" and "SmartArt" in str(s.get("name"))), None)
    if not group:
        raise RuntimeError("DeckCraft 가 SmartArt 를 만들지 못했습니다")
    children = group.get("children") or []
    title_ids = [s["id"] for s in shapes if s is not group]

    # 2. 글자 크기 · 굵게 · 연결선
    units, frame = units_of(children, lines, kind)
    heads = [c for c in children if any(c["id"] in u["head"] for u in units)]
    bodies = [c for c in children if (c.get("text") or "").strip() and c not in heads]
    fix = []
    if heads:
        fs = min(font_for(_text_box(c), c["text"], lo=13, hi=30) for c in heads)
        fix += [_c("selection.select", ids=[c["id"] for c in heads]), _c("format.size", size=fs), _c("format.bold")]
    if bodies:
        # 하위 항목 칸은 옅은 바탕이라 테마 글자색(어두운 테마에선 흰색)이면 안 읽힌다 → 짙은 글자
        fb = min(font_for(c["box"], c["text"], lo=13, hi=26) for c in bodies)
        fix += [_c("selection.select", ids=[c["id"] for c in bodies]), _c("format.size", size=fb), _c("format.color", color=BODY_TEXT)]
    lines_ids = [c["id"] for c in children if c.get("preset") == "line"]
    if lines_ids:
        fix.append(_c("shape.line", color=LINE, width=2, ids=lines_ids))
    if fix:
        _dc(fix, work, f"{mid}.fix.txt", src=deck, save=deck)

    # 3. 렌더 — 전체 · 바탕 · 항목별
    args = [cli("deckcraft"), "render", deck, "--slide", 0, "--scale", SCALE]
    if m.get("transparent"):
        args.append("--transparent")
    _run([*args, out], work)
    every = [c["id"] for c in children]
    items_ids = [i for i in every if i not in frame]
    base = out.parent / f"{mid}.base.png"
    _dc([_c("shape.visible", visible=False, ids=items_ids)], work, f"{mid}.base.txt", src=deck, export=base,
        transparent=bool(m.get("transparent")))
    ldir = out.parent / f"{mid}.layers"
    ldir.mkdir(exist_ok=True)
    for f in ldir.glob("*.png"):
        f.unlink()
    cues = list(m.get("cues") or [])
    layers = []
    for k, u in enumerate(units):
        hide = [i for i in every if i not in u["ids"]] + title_ids
        tmp = work / f"{mid}.layer.tmp.png"
        _dc([_c("shape.visible", visible=False, ids=hide)], work, f"{mid}.layer.txt", src=deck, export=tmp, transparent=True)
        dst = ldir / f"{k + 1:02d}.png"
        box = _crop_layer(tmp, dst)
        tmp.unlink(missing_ok=True)
        if box:
            layers.append({"file": _rel(dst, ROOT), "box": box, "cue": (cues[k] if k < len(cues) else None) or None, "text": u["text"]})

    from PIL import Image
    with Image.open(out) as im:
        size = list(im.size)
    return {"app": "deckcraft", "as": "image", "kind": kind, "layout": layout, "size": size, "title": title or None,
            "layers": layers, "base": _rel(base, ROOT), "editable": _rel(deck, ROOT)}


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.resolve().relative_to(root))
    except ValueError:
        return str(p)



# ---------------------------------------------------------------- 차트(다른 방법) — chart@deckcraft
CHART_KIND = {"bar": "column", "column": "column", "hbar": "bar", "line": "line", "pie": "pie", "donut": "doughnut",
              "doughnut": "doughnut", "area": "area", "stacked": "stackedColumn"}


def chart_deck(m: dict, out: Path, work: Path) -> dict:
    """DeckCraft 차트 엔진으로 차트 그림 — 기본 방법(GridCraft 계산 + 움직임 단계가 막대를 그림)과 다른 모양이 필요할 때.
    콘티: {"type": "chart", "method": "deckcraft", "kind": "bar|hbar|line|pie|donut|area|stacked", "labels": [...], "values": [...]
           (또는 "series": [{"name", "values"}]), "title", "unit", "theme"(DeckCraft 테마), "transparent"}"""
    from ..materials import _run, cli
    mid = m["id"]
    work.mkdir(parents=True, exist_ok=True)
    labels = [str(x) for x in (m.get("labels") or [])]
    series = m.get("series") or [{"name": m.get("unit") or m.get("title") or "값", "values": list(m.get("values") or [])}]
    if not labels or not series or not series[0].get("values"):
        raise RuntimeError("chart(deckcraft): labels 와 values(또는 series)가 필요합니다")
    kind = CHART_KIND.get(str(m.get("kind") or "bar"), "column")
    title = str(m.get("title") or "").strip()
    y0 = 200 if title else 110
    cmds = [_c("file.new", theme=m.get("theme") or "Nocturne", size=[W_PT, H_PT], blank=True),
            _c("design.fonts", major=FONT, minor=FONT),
            _c("slide.new", layout="blank")]
    if title:
        cmds += [_c("insert.textBox", rect=[30, 70, W_PT - 60, 110], text=title),
                 _c("format.size", size=34 if len(title) <= 14 else 28), _c("format.bold"), _c("format.align", align="center")]
    cmds += [_c("insert.chart", type=kind, rect=[30, y0, W_PT - 60, BOTTOM_PT - y0], categories=labels,
                series=[{"name": str(x.get("name") or ""), "values": [float(v) for v in x.get("values") or []]} for x in series]),
             _c("format.size", size=18),
             _c("chart.options", title=None, dataLabels=True, gridlines=False, legend=("b" if len(series) > 1 or kind in ("pie", "doughnut") else None))]
    deck = work / f"{mid}.deckcraft"
    _dc(cmds, work, f"{mid}.chart.txt", save=deck)
    args = [cli("deckcraft"), "render", deck, "--slide", 0, "--scale", SCALE]
    if m.get("transparent"):
        args.append("--transparent")
    _run([*args, out], work)
    from ..materials import ROOT
    vals = [float(v) for x in series for v in x.get("values") or []]
    warn = None
    if kind in ("column", "bar", "stackedColumn") and vals and min(vals) > 0.3 * max(vals):
        # DeckCraft 는 축 최솟값을 자동으로 잡는다(명령 없음) → 값이 0 에서 멀면 차이가 과장돼 보인다
        warn = "DeckCraft 막대 차트는 세로축이 0 부터가 아닐 수 있다 — 기준선이 중요한 비교는 기본 방법(method 없이)"
        print(f"[재료] {mid}: {warn}")
    return {"app": "deckcraft", "as": "image", "method": "deckcraft", "kind": kind, **({"warn": warn} if warn else {}), "size": [W_PT * SCALE, H_PT * SCALE],
            "editable": _rel(deck, ROOT), "data": {"labels": labels, "series": series, "title": title}}


ADAPTERS = {"diagram": diagram, "chart@deckcraft": chart_deck}
