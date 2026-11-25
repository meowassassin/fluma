#!/usr/bin/env python3
"""장면 설계 언어 — "무엇을 · 어디에 · 어느 말에 · 어떻게"를 조합으로 쓰면 EffectCraft 장면 코드(K 키트)로 컴파일한다(2026-11-25).

2026-11-25 실측: 에이전트가 장면마다 좌표 · 키프레임 코드를 손으로 써서(최근 129장면 중앙 27줄) 한 편 화면 쓰기에 $5.70 · 10분.
그런데 실제로 쓰는 K 함수는 10개 남짓, 효과는 19종뿐이었다. 낱말을 조합하게 하면 쓰는 양은 줄고 표현은 넓어진다.
바닥은 그대로다: 결과는 지금과 같은 K 코드이고, 콘티 재료 칸에 "$DESIGN:data/compositions/<id>/design/sNN.json" 을 쓰면
재료 처리 맨 앞(scenefile.inline)에서 컴파일돼 $CUE · 재료 캐시 · 검사 · 렌더가 손으로 쓴 장면과 똑같이 돈다.

설계 한 장면:
  {"bg": "#d9e6dc" | ["#위", "#아래"] | "bg",                 # 색 토큰(bg · ink · accent · muted · paper · surface) 도 된다
   "camera": {"move": "push|pull|pan_left|pan_right|rise|sink", "amount": 0.06, "on": "낱말"},
   "els": [요소, …]}
요소:
  id(필수) · kind: text | tag | box | circle | ring | line | arrow | image | capture | form | icon | code
  text · src(그림: "forms/x.png" · "capture:이름" · "capture:이름/s001.png" · 저장소 경로) · code(kind=code: K 코드)
  role: hero | support | aside | backdrop      (at 이 없으면 hero · support · aside 가 위에서 아래로 쌓인다)
  at:   {"below|above|left|right|over": 요소id, "gap": 40, "dx", "dy"} · {"slot": [i, n], "of": 요소id | "row": "top|middle|bottom"} · {"x": 540, "y": 900}
        (어느 것이든 안전 영역 안으로 맞춘다 — 일부러 밖에 두려면 "free": true)
  size: xl | l | m | s | xs | {"w": 픽셀} | {"h": 픽셀}
  style: {"color", "fill", "stroke", "font": "title|body|글꼴 이름", "round", "opacity", "align"}
  on: 나레이션 낱말("$CUE" 와 같음, "낱말+0.3" · "낱말@end") | at_sec: 초 | after: 요소id
  enter: fade | pop | drop | rise | slide_left | slide_right | slide_up | slide_down | write | draw | grow | wipe | cut  (또는 {"name", "dur"})
  exit:  {"on" | "at_sec", "name": fade | cut | drop_out}
  motion: drift | float | pulse | spin | sway
  emph: [{"on": 낱말, "do": scale | tint | underline | circle | dim_others, "color": 토큰}]
  marks: [{"box": [x, y, 폭, 높이], "style": "box|highlight|underline", "on": 낱말}]   # 그림(캡처) 안 한 구역에 강조 — 비율 0~1, preview 를 보고
  zoom: {"box": [x, y, 폭, 높이], "on": 낱말}       # 그 낱말에 그 구역으로 확대(강조도 같이 따라감)
  fx: [{"id": "ec.blur.gaussian", "Blurriness": [14, 0]}, …]   # EffectCraft 카탈로그 전체. [a, b] = 들어올 때 a→b, [[초, 값], …] = 요소 시작 기준 키
  children: [요소, …]   (kind=group — 함께 움직이는 묶음, 자리는 묶음 기준)
안전 영역(엔진이 보장): 위 화면 글자 띠 y<260 · 아래 자막 띠 y>1250 · 오른쪽 버튼 띠 x>950 에는 backdrop 말고 두지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
W, H = 1080, 1920
SAFE = (72, 270, 940, 1240)                       # x0 y0 x1 y1 — 화면 글자 띠 · 자막 띠 · 오른쪽 버튼 띠를 비운 곳
KINDS = {"text", "tag", "box", "circle", "ring", "line", "arrow", "image", "capture", "form", "icon", "code", "group"}
ROLES = {"hero", "support", "aside", "backdrop"}
ENTERS = {"fade", "pop", "drop", "rise", "slide_left", "slide_right", "slide_up", "slide_down", "write", "draw", "grow", "wipe", "cut"}
EXITS = {"fade", "cut", "drop_out"}
MOTIONS = {"drift", "float", "pulse", "spin", "sway"}
EMPHS = {"scale", "tint", "underline", "circle", "dim_others"}
CAMERA = {"push", "pull", "pan_left", "pan_right", "rise", "sink", "none"}
RELS = ("below", "above", "left", "right", "over")
SIZES = {"xl": 128, "l": 92, "m": 66, "s": 48, "xs": 36}
BOX = {"hero": (840, 820), "support": (700, 520), "aside": (420, 360), "backdrop": (W, H)}
BANNED_FX = re.compile(r"glow|lensflare|lens_flare|ADBE Glo2|shake", re.I)    # 빛번짐 · 렌즈 빛 · 흔들기 — 막음(visual_tell V03 · V04)
TOKENS = ("bg", "ink", "accent", "muted", "paper", "surface")


# ---------------- 검증 ----------------
def validate(design: dict, where: str = "") -> list[str]:
    """칸 단위 오류 목록 — 비어 있으면 통과. 쓰는 순간 그 칸만 고치게(묶음 전체를 다시 쓰지 않게)"""
    out = []
    p = where or "design"
    if not isinstance(design, dict):
        return [f"{p}: 객체여야 함"]
    for k in design:
        if k not in ("bg", "camera", "els", "note"):
            out.append(f"{p}.{k}: 모르는 칸 — bg · camera · els")
    cam = design.get("camera")
    if cam is not None:
        if not isinstance(cam, dict) or cam.get("move") not in CAMERA:
            out.append(f"{p}.camera.move: {sorted(CAMERA)} 중 하나")
    els = design.get("els")
    if not isinstance(els, list) or not els:
        return out + [f"{p}.els: 요소 목록이 필요함"]
    ids: set = set()

    def walk(lst, pre):
        for i, e in enumerate(lst):
            q = f"{pre}[{i}]"
            if not isinstance(e, dict):
                out.append(f"{q}: 객체여야 함"); continue
            eid = e.get("id")
            if not isinstance(eid, str) or not eid:
                out.append(f"{q}.id: 필요함")
            elif eid in ids:
                out.append(f"{q}.id: '{eid}' 가 겹침")
            else:
                ids.add(eid)
            q = f"{pre}[{eid or i}]"
            k = e.get("kind")
            if k not in KINDS:
                out.append(f"{q}.kind: '{k}' — {sorted(KINDS)} 중 하나")
            if k in ("text", "tag") and not str(e.get("text") or "").strip():
                out.append(f"{q}.text: 필요함")
            if k in ("image", "capture", "form", "icon") and not e.get("src"):
                out.append(f"{q}.src: 필요함(forms/x.png · capture:이름 · 저장소 경로)")
            if k == "code" and not str(e.get("code") or "").strip():
                out.append(f"{q}.code: K 코드가 필요함")
            if k == "group" and not isinstance(e.get("children"), list):
                out.append(f"{q}.children: 묶을 요소 목록이 필요함")
            if e.get("role") is not None and e["role"] not in ROLES:
                out.append(f"{q}.role: {sorted(ROLES)} 중 하나")
            sz = e.get("size")
            if sz is not None and not ((isinstance(sz, str) and sz in SIZES) or (isinstance(sz, dict) and set(sz) <= {"w", "h"} and all(isinstance(v, (int, float)) for v in sz.values()))):
                out.append(f"{q}.size: {list(SIZES)} 또는 {{w}} · {{h}}")
            en = e.get("enter")
            en_n = en.get("name") if isinstance(en, dict) else en
            if en is not None and en_n not in ENTERS:
                out.append(f"{q}.enter: '{en_n}' — {sorted(ENTERS)} 중 하나")
            ex = e.get("exit")
            if ex is not None and (not isinstance(ex, dict) or ex.get("name", "fade") not in EXITS or not (ex.get("on") or ex.get("at_sec") is not None)):
                out.append(f"{q}.exit: {{on | at_sec, name: {sorted(EXITS)}}}")
            mo = e.get("motion")
            if mo is not None and mo not in MOTIONS:
                out.append(f"{q}.motion: {sorted(MOTIONS)} 중 하나")
            for j, m in enumerate(e.get("emph") or []):
                if not isinstance(m, dict) or m.get("do") not in EMPHS or not m.get("on"):
                    out.append(f"{q}.emph[{j}]: {{on: 낱말, do: {sorted(EMPHS)}}}")
            for key in ("marks",):
                for j, m in enumerate(e.get(key) or []):
                    b = m.get("box") if isinstance(m, dict) else None
                    if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b)):
                        out.append(f"{q}.marks[{j}].box: [x, y, 폭, 높이] — 그림 안 비율 0~1(preview 그림을 보고)")
                    elif m.get("style", "box") not in ("box", "highlight", "underline"):
                        out.append(f"{q}.marks[{j}].style: box | highlight | underline")
            if (e.get("marks") or e.get("zoom")) and k not in ("image", "capture", "form", "icon"):
                out.append(f"{q}: marks · zoom 은 그림(capture · image · form · icon)에만")
            z = e.get("zoom")
            if z is not None:
                b = z.get("box") if isinstance(z, dict) else None
                if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b) and b[2] > 0 and b[3] > 0):
                    out.append(f"{q}.zoom: {{box: [x, y, 폭, 높이](0~1), on: 낱말}}")
            for j, f in enumerate(e.get("fx") or []):
                if not isinstance(f, dict) or not isinstance(f.get("id"), str):
                    out.append(f"{q}.fx[{j}]: {{id: 카탈로그 id, 속성: 값}}")
                elif BANNED_FX.search(f["id"]):
                    out.append(f"{q}.fx[{j}]: '{f['id']}' 금지(빛번짐 · 렌즈 빛 · 흔들기) — 다른 효과로")
            at = e.get("at")
            if at is not None:
                if not isinstance(at, dict):
                    out.append(f"{q}.at: 객체여야 함")
                elif "slot" in at:
                    s = at["slot"]
                    if not (isinstance(s, list) and len(s) == 2 and all(isinstance(v, int) for v in s) and 1 <= s[0] <= s[1]):
                        out.append(f"{q}.at.slot: [몇 번째, 몇 개 중] (1부터)")
                elif not any(r in at for r in RELS) and not ("x" in at and "y" in at):
                    out.append(f"{q}.at: below|above|left|right|over · slot · x,y 중 하나")
            if k == "group":
                walk(e["children"], f"{q}.children")

    walk(els, f"{p}.els")

    def refs(lst):
        for e in lst:
            if not isinstance(e, dict):
                continue
            at = e.get("at") or {}
            for r in RELS + ("of",):
                t = at.get(r) if isinstance(at, dict) else None
                if isinstance(t, str) and t not in ids:
                    out.append(f"{p}.els[{e.get('id')}].at.{r}: 없는 요소 '{t}'")
            if e.get("after") and e["after"] not in ids:
                out.append(f"{p}.els[{e.get('id')}].after: 없는 요소 '{e['after']}'")
            if e.get("kind") == "group":
                refs(e.get("children") or [])

    refs(els)
    return out


# ---------------- 컴파일 ----------------
def _palette(sb: dict) -> dict:
    d = sb.get("direction") or {}
    art = (d.get("art") or {}).get("palette") or {}
    return {"bg": art.get("bg") or d.get("color_bg") or "#f4f1ea", "ink": art.get("ink") or d.get("color_text") or "#1d1d1d",
            "accent": art.get("accent") or d.get("color_accent") or "#d9480f", "muted": art.get("muted") or d.get("color_muted") or "#8a8a8a",
            "paper": art.get("paper") or "#fbf6ea", "surface": art.get("surface") or d.get("color_surface") or "#ffffff"}


def _fonts(sb: dict) -> dict:
    d = sb.get("direction") or {}
    return {"title": d.get("font_title") or "Pretendard", "body": d.get("font_body") or d.get("font_title") or "Pretendard"}


def _svg_png(svg: Path, scale: float) -> tuple[Path, float]:
    """SVG → PNG(보일 배율의 2배, 2~64) — 이미 있으면 다시 만들지 않는다. (PNG 경로, 변환 배율)"""
    import math
    f = max(2, min(64, 2 ** math.ceil(math.log2(max(1.0, scale * 2)))))
    out = svg.with_name(f"{svg.stem}.x{f}.png")
    if not out.exists() or out.stat().st_mtime < svg.stat().st_mtime:
        if str(ROOT / "engine") not in sys.path:
            sys.path.insert(0, str(ROOT / "engine"))
            import paths  # noqa: F401
        from craft.materials import _run, cli
        _run([cli("vectorcraft"), "convert", svg, out, "--scale", str(f)], svg.parent)
    return out, float(f)


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _text_w(s: str, size: float) -> float:
    w = 0.0
    for ch in s:
        w += size * (0.98 if ord(ch) > 0x2E80 else 0.56 if ch != " " else 0.3)
    return w


def _img_size(path: Path) -> tuple[int, int, float, float]:
    """(보이는 폭, 보이는 높이, 보이는 부분 가운데가 그림 가운데에서 벗어난 x, y) — 투명 여백은 빼고 잰다(형태 · 아이콘)"""
    if path.suffix.lower() == ".svg":                  # 아이콘(Simple Icons 등) — 크기는 width · height 또는 viewBox
        try:
            head = path.read_text("utf-8", errors="ignore")[:2000]
            m = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head)
            mw, mh = re.search(r'\swidth="([\d.]+)', head), re.search(r'\sheight="([\d.]+)', head)
            if mw and mh:
                return float(mw.group(1)), float(mh.group(1)), 0.0, 0.0
            if m:
                return float(m.group(1)), float(m.group(2)), 0.0, 0.0
        except OSError:
            pass
        return 24.0, 24.0, 0.0, 0.0
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            if im.mode in ("RGBA", "LA") or "transparency" in im.info:
                bb = im.convert("RGBA").getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
                if bb:
                    return bb[2] - bb[0], bb[3] - bb[1], (bb[0] + bb[2]) / 2 - w / 2, (bb[1] + bb[3]) / 2 - h / 2
            return w, h, 0.0, 0.0
    except Exception:  # noqa: BLE001
        return 800, 800, 0.0, 0.0


class _Ctx:
    def __init__(self, sb: dict, sid: str, n: int):
        self.sb, self.sid, self.n = sb, sid, n
        self.pal, self.fonts = _palette(sb), _fonts(sb)
        self.box: dict[str, tuple[float, float, float, float]] = {}   # id → (cx, cy, w, h)
        self.start: dict[str, str] = {}                                 # id → JS 시각 식
        self.lines: list[str] = []

    def color(self, v, default="ink"):
        v = v or default
        return self.pal.get(v, v) if isinstance(v, str) else v

    def font(self, v, big=False):
        if v in (None, ""):
            return self.fonts["title" if big else "body"]
        return self.fonts.get(v, v)

    def src(self, s: str) -> Path:
        if s.startswith("capture:"):
            name = s[8:]
            p = ROOT / "data" / "public" / "elements" / self.sid / name
            if p.is_dir():
                shots = sorted(p.glob("s*.png")) or sorted(p.glob("*.png"))
                if not shots:
                    raise ValueError(f"capture:{name} — 캡처 그림이 없음")
                return shots[-1]
            if not p.is_file():
                have = sorted(x.name for x in p.parent.iterdir()) if p.parent.is_dir() else []
                raise ValueError(f"capture:{name} — 없는 캡처(있는 것: {', '.join(have[:12]) or '없음'})")
            return p
        p = Path(s)
        if p.is_absolute():
            return p
        for base in (ROOT / "data" / "compositions" / self.sid, ROOT):
            if (base / p).exists():
                return base / p
        raise ValueError(f"src '{s}' — 파일이 없음(영상 폴더 기준 forms/x.png · 아이콘 x.svg · capture:이름)")


def _time(ctx: _Ctx, e: dict) -> str:
    if e.get("at_sec") is not None:
        return f"{float(e['at_sec']):.3f}"
    if e.get("on"):
        return f"$CUE:{e['on']}"
    if e.get("after") and e["after"] in ctx.start:
        return f"({ctx.start[e['after']]} + 0.35)"
    return "0.05"


def _size_px(e: dict, role: str) -> tuple[float, float]:
    sz = e.get("size")
    bw, bh = BOX.get(role, BOX["support"])
    if isinstance(sz, dict):
        return float(sz.get("w") or bw), float(sz.get("h") or bh)
    if sz in SIZES:
        f = {"xl": 1.0, "l": 0.75, "m": 0.52, "s": 0.32, "xs": 0.2}[sz]
        return BOX["hero"][0] * f, BOX["hero"][1] * f
    return bw, bh


def _measure(ctx: _Ctx, e: dict) -> tuple[float, float]:
    """요소의 크기(w, h) — 배치 전에"""
    k, role = e.get("kind"), e.get("role") or "support"
    if k == "text":
        size = SIZES.get(e.get("size") if isinstance(e.get("size"), str) else "", SIZES["xl" if role == "hero" else "m"])
        lines = str(e["text"]).split("\n")
        return min(SAFE[2] - SAFE[0], max(_text_w(x, size) for x in lines)), size * 1.25 * len(lines)
    if k == "tag":
        size = SIZES.get(e.get("size") if isinstance(e.get("size"), str) else "", SIZES["m"])
        return min(SAFE[2] - SAFE[0], _text_w(str(e["text"]), size) + size * 1.1), size * 1.9
    if k in ("image", "capture", "form", "icon"):
        iw, ih, ox, oy = _img_size(ctx.src(str(e["src"])))
        bw, bh = _size_px(e, role)
        if role == "backdrop":
            f = max(W / iw, H / ih)
        else:
            f = min(bw / iw, bh / ih)
        e["_scale"] = round(f * 100, 2)
        e["_off"] = (ox, oy)
        return iw * f, ih * f
    if k in ("box", "circle", "ring"):
        return _size_px(e, role if e.get("size") is None else "support") if e.get("size") is not None else ((W, H) if role == "backdrop" else (320, 320))
    if k in ("line", "arrow"):
        sz = e.get("size")
        w = float(sz.get("w", 600)) if isinstance(sz, dict) else {"xl": 860, "l": 640, "m": 420, "s": 260, "xs": 140}.get(sz, 420)
        ang = float((e.get("style") or {}).get("angle", 0)) % 180
        return (8, w) if 45 < ang < 135 else (w, 8)     # 세운 선은 상자도 세로로(배치가 맞게)
    if k == "group":
        ws, hs = [], []
        for c in e["children"]:
            cw, ch = _measure(ctx, c)
            ws.append(cw); hs.append(ch)
        return max(ws or [100]), sum(hs or [100]) + 30 * max(0, len(hs) - 1)
    return (400, 300)


def _layout(ctx: _Ctx, els: list[dict]) -> None:
    """요소마다 상자(cx, cy, w, h). 관계 · slot · 좌표가 없는 hero · support · aside 는 안전 영역 안에서 위→아래로 쌓고 세로 가운데"""
    sizes = {e["id"]: _measure(ctx, e) for e in els}
    flow = [e for e in els if not e.get("at") and (e.get("role") or "support") != "backdrop"]
    gap = 48
    total = sum(sizes[e["id"]][1] for e in flow) + gap * max(0, len(flow) - 1)
    room = SAFE[3] - SAFE[1]
    if total > room:                                   # 넘치면 비율대로 줄인다(그림 · 도형)
        f = room / total
        for e in flow:
            w, h = sizes[e["id"]]
            sizes[e["id"]] = (w * f, h * f)
            if "_scale" in e:
                e["_scale"] = round(e["_scale"] * f, 2)
        total = room
    y = SAFE[1] + (room - total) / 2
    cx = (SAFE[0] + SAFE[2]) / 2
    for e in flow:
        w, h = sizes[e["id"]]
        ctx.box[e["id"]] = (cx, y + h / 2, w, h)
        y += h + gap
    for e in els:
        if (e.get("role") or "") == "backdrop" and not e.get("at"):
            ctx.box[e["id"]] = (W / 2, H / 2, *sizes[e["id"]])
    pending = [e for e in els if e["id"] not in ctx.box]
    for _ in range(len(pending) + 2):                   # 관계는 대상이 먼저 놓여야 — 몇 바퀴 돈다
        left = []
        for e in pending:
            at, (w, h) = e["at"], sizes[e["id"]]
            if "x" in at and "y" in at:
                ctx.box[e["id"]] = (float(at["x"]), float(at["y"]), w, h); continue
            if "slot" in at:
                i, n = at["slot"]
                tgt = at.get("of")
                if tgt and tgt not in ctx.box:
                    left.append(e); continue
                if tgt:
                    tx, ty, tw, th = ctx.box[tgt]
                    yy = ty + th / 2 + at.get("gap", 70) + h / 2
                else:
                    yy = {"top": SAFE[1] + h / 2 + 20, "bottom": SAFE[3] - h / 2 - 20}.get(at.get("row"), (SAFE[1] + SAFE[3]) / 2)
                span = SAFE[2] - SAFE[0]
                xx = SAFE[0] + span * (i - 0.5) / n
                w = min(w, span / n - 24)
                ctx.box[e["id"]] = (xx, yy, w, h); continue
            rel = next(r for r in RELS if r in at)
            tgt = at[rel]
            if tgt not in ctx.box:
                left.append(e); continue
            tx, ty, tw, th = ctx.box[tgt]
            g = float(at.get("gap", 40))
            pos = {"below": (tx, ty + th / 2 + g + h / 2), "above": (tx, ty - th / 2 - g - h / 2),
                   "left": (tx - tw / 2 - g - w / 2, ty), "right": (tx + tw / 2 + g + w / 2, ty), "over": (tx, ty)}[rel]
            ctx.box[e["id"]] = (pos[0] + float(at.get("dx", 0)), pos[1] + float(at.get("dy", 0)), w, h)
        pending = left
        if not pending:
            break
    for e in pending:                                  # 대상이 없거나 돌고 도는 관계 — 가운데
        ctx.box[e["id"]] = ((SAFE[0] + SAFE[2]) / 2, (SAFE[1] + SAFE[3]) / 2, *sizes[e["id"]])
    for e in els:                                      # 안전 영역 안으로(backdrop · 좌표를 직접 준 것 제외)
        if (e.get("role") or "") == "backdrop" or (e.get("at") or {}).get("free"):   # free: 일부러 화면 밖 · 띠 위에(들어오는 연출 등)
            continue
        cx_, cy_, w, h = ctx.box[e["id"]]
        cx_ = min(max(cx_, SAFE[0] + w / 2), SAFE[2] - w / 2) if w < SAFE[2] - SAFE[0] else (SAFE[0] + SAFE[2]) / 2
        cy_ = min(max(cy_, SAFE[1] + h / 2), SAFE[3] - h / 2) if h < SAFE[3] - SAFE[1] else (SAFE[1] + SAFE[3]) / 2
        ctx.box[e["id"]] = (cx_, cy_, w, h)


def _enter(ctx: _Ctx, v: str, e: dict, t: str) -> None:
    en = e.get("enter") or ("write" if e.get("kind") == "text" and (e.get("role") or "") != "hero" else "fade")
    name = en.get("name") if isinstance(en, dict) else en
    dur = float(en.get("dur", 0.35)) if isinstance(en, dict) else 0.35
    cx, cy, w, h = ctx.box[e["id"]]
    L = ctx.lines.append
    if name == "cut":
        L(f"K.appear({v}, {t}, 0);")
    elif name == "fade":
        L(f"K.appear({v}, {t}, {dur});")
    elif name == "pop":
        L(f"K.pop({v}, {t});")
    elif name in ("drop", "rise", "slide_left", "slide_right", "slide_up", "slide_down"):
        dx, dy = {"drop": (0, -90), "rise": (0, 90), "slide_left": (260, 0), "slide_right": (-260, 0), "slide_up": (0, 200), "slide_down": (0, -200)}[name]
        L(f"K.appear({v}, {t}, {min(dur, 0.25)}); K.move({v}, {t}, [{cx + dx:.0f}, {cy + dy:.0f}], [{cx:.0f}, {cy:.0f}], {dur});")
    elif name in ("write", "wipe"):
        L(f"K.appear({v}, {t}, 0); K.write({v}, {t}{', ' + str(dur) if isinstance(en, dict) and 'dur' in en else ''});")
    elif name == "draw" and e.get("kind") in ("line", "arrow"):     # 선은 길이 방향으로 자란다(채운 사각형에 획 그리기는 거의 안 보였다)
        L(f"K.appear({v}, {t}, 0); (function(){{var s=K.S({v}); s.setValueAtTime({t}, [0,100]); s.setValueAtTime({t}+{max(dur, 0.35)}, [100,100]); K.ease(s, 70);}})();")
    elif name == "draw":
        if e.get("kind") in ("box", "circle", "ring"):
            L(f"K.appear({v}, {t}, 0); K.draw({v}, {t}, {max(dur, 0.45)});")
        else:
            L(f"K.appear({v}, {t}, 0); K.write({v}, {t});")
    elif name == "grow":
        L(f"K.appear({v}, {t}, 0.1); (function(){{var s=K.S({v}); s.setValueAtTime({t}, [0,0]); s.setValueAtTime({t}+{dur}, [100,100]); K.ease(s, 80);}})();")


def _fx(ctx: _Ctx, v: str, e: dict, t: str) -> None:
    for f in e.get("fx") or []:
        props = {}
        anim = []
        for k, val in f.items():
            if k == "id":
                continue
            if isinstance(val, list) and len(val) == 2 and all(isinstance(x, (int, float)) for x in val):
                anim.append((k, val))
            elif isinstance(val, list) and val and all(isinstance(x, list) and len(x) == 2 for x in val):
                anim.append((k, val))
            else:
                props[k] = val
        L = ctx.lines.append
        L(f"(function(){{var f=K.fx({v}, {_js(f['id'])}, {_js(props)});")
        for k, val in anim:
            if all(isinstance(x, (int, float)) for x in val):
                L(f" f.property({_js(k)}).setValueAtTime({t}, {_js(val[0])}); f.property({_js(k)}).setValueAtTime({t}+0.4, {_js(val[1])});")
            else:
                for tt, vv in val:
                    L(f" f.property({_js(k)}).setValueAtTime({t}+{float(tt)}, {_js(vv)});")
        L("})();")


def _after(ctx: _Ctx, v: str, e: dict, els_vars: dict) -> None:
    L = ctx.lines.append
    mo = e.get("motion")
    if mo == "drift":
        L(f"K.P({v}).expression = 'value + [Math.sin(time*0.6)*10, -time*6]';")
    elif mo == "float":
        L(f"K.P({v}).expression = 'value + [0, Math.sin(time*2.2)*9]';")
    elif mo == "pulse":
        L(f"K.S({v}).expression = 'var s = 1 + 0.025*Math.sin(time*4); [value[0]*s, value[1]*s]';")
    elif mo == "spin":
        L(f"K.R({v}).expression = 'value + time*20';")
    elif mo == "sway":
        L(f"K.R({v}).expression = 'value + Math.sin(time*1.6)*3';")
    for m in e.get("emph") or []:
        t = f"$CUE:{m['on']}"
        cx, cy, w, h = ctx.box[e["id"]]
        col = ctx.color(m.get("color"), "accent")
        if m["do"] == "scale":
            L(f"(function(){{var s=K.S({v}); var b=s.valueAtTime({t},false); s.setValueAtTime({t}, b); s.setValueAtTime({t}+0.18, [b[0]*1.12,b[1]*1.12]); s.setValueAtTime({t}+0.45, b); K.ease(s,70);}})();")
        elif m["do"] == "tint":
            L(f"(function(){{var f=K.fx({v}, 'ec.color.tint', {{}}); try{{f.property('Map White To').setValue({_js(col)});}}catch(x){{}} var a=f.property('Amount to Tint'); a.setValueAtTime(0,0); a.setValueAtTime({t},0); a.setValueAtTime({t}+0.25,100);}})();")
        elif m["do"] == "underline":
            L(f"(function(){{var u=K.shape('rect', {cx:.0f}, {cy + h / 2 + 14:.0f}, {w:.0f}, 10, {{fill:{_js(col)}}}); K.appear(u,{t},0); K.draw(u,{t},0.35);}})();")
        elif m["do"] == "circle":
            L(f"(function(){{var c=K.shape('ellipse', {cx:.0f}, {cy:.0f}, {w + 70:.0f}, {h + 70:.0f}, {{stroke:{_js(col)}, strokeW:10}}); K.appear(c,{t},0); K.draw(c,{t},0.45);}})();")
        elif m["do"] == "dim_others":
            for oid, ov in els_vars.items():
                if oid != e["id"]:
                    L(f"K.dim({ov}, {t}, 30);")
    ex = e.get("exit")
    if ex:
        t = f"{float(ex['at_sec']):.3f}" if ex.get("at_sec") is not None else f"$CUE:{ex['on']}"
        name = ex.get("name", "fade")
        if name == "cut":
            L(f"K.fadeOut({v}, {t}, 0.04);")
        elif name == "drop_out":
            cx, cy, *_ = ctx.box[e["id"]]
            L(f"K.fadeOut({v}, {t}, 0.25); K.move({v}, {t}, null, [{cx:.0f}, {cy + 120:.0f}], 0.3);")
        else:
            L(f"K.fadeOut({v}, {t}, 0.25);")


def _emit(ctx: _Ctx, e: dict, v: str) -> None:
    """요소 하나를 만든다(자리 · 크기까지) — 등장 · 효과 · 움직임은 따로"""
    k, st = e["kind"], e.get("style") or {}
    cx, cy, w, h = ctx.box[e["id"]]
    role = e.get("role") or "support"
    L = ctx.lines.append
    op = st.get("opacity")
    if k == "text":
        size = SIZES.get(e.get("size") if isinstance(e.get("size"), str) else "", SIZES["xl" if role == "hero" else "m"])
        lines = str(e["text"]).split("\n")
        top = cy - h / 2 + size * 0.95
        o = {"font": ctx.font(st.get("font"), size >= SIZES["l"]), "align": st.get("align", "center")}
        if st.get("stroke"):
            o.update(stroke=ctx.color(st["stroke"]), strokeW=st.get("strokeW", 8))
        if len(lines) == 1:
            L(f"var {v} = K.text({_js(lines[0])}, {cx:.0f}, {top:.0f}, {size}, {_js(ctx.color(st.get('color')))}, {_js(o)});")
        else:
            L(f"var {v} = K.text({_js(chr(13).join(lines))}, {cx:.0f}, {top:.0f}, {size}, {_js(ctx.color(st.get('color')))}, {_js(o)});")
    elif k == "tag":
        size = SIZES.get(e.get("size") if isinstance(e.get("size"), str) else "", SIZES["m"])
        fill = ctx.color(st.get("fill"), "ink")
        col = ctx.color(st.get("color"), "paper")
        L(f"var {v} = K.shape('rect', 0, 0, {w:.0f}, {h:.0f}, {{fill:{_js(fill)}, round:{st.get('round', 0)}}});")
        L(f"K.follow(K.text({_js(str(e['text']))}, 0, {size * 0.36:.0f}, {size}, {_js(col)}, {_js({'font': ctx.font(st.get('font'), True)})}), {v});")
        L(f"K.P({v}).setValue([{cx:.0f}, {cy:.0f}]);")
    elif k in ("box", "circle", "ring"):
        o = {"round": st.get("round", 0)}
        if k == "ring" or st.get("stroke"):
            o.update(stroke=ctx.color(st.get("stroke"), "ink"), strokeW=st.get("strokeW", 8))
            if k != "ring" and st.get("fill"):
                o["fill"] = ctx.color(st["fill"])
        else:
            o["fill"] = ctx.color(st.get("fill"), "surface")
        L(f"var {v} = K.shape({_js('rect' if k == 'box' else 'ellipse')}, {cx:.0f}, {cy:.0f}, {w:.0f}, {h:.0f}, {_js(o)});")
    elif k in ("line", "arrow"):
        ln = max(w, h)
        L(f"var {v} = K.shape('rect', {cx:.0f}, {cy:.0f}, {ln:.0f}, {st.get('strokeW', 8)}, {{fill:{_js(ctx.color(st.get('color'), 'ink'))}}});")
        if k == "arrow":                               # 끝에 45도 돌린 네모 반쪽 = 화살촉
            L(f"(function(){{var hd=K.shape('rect', {w / 2 - 12:.0f}, 0, 36, 36, {{fill:{_js(ctx.color(st.get('color'), 'ink'))}}}); K.R(hd).setValue(45); K.follow(hd, {v});}})();")
        if st.get("angle"):
            L(f"K.R({v}).setValue({float(st['angle'])});")
    elif k in ("image", "capture", "form", "icon"):
        p = ctx.src(str(e["src"]))
        if p.suffix.lower() == ".svg":                 # SVG 는 그 크기로 그리면 흐리다 — 보일 크기보다 크게 PNG 로(VectorCraft, 재료 경로와 같은 방법)
            p, f2 = _svg_png(p, e.get("_scale", 100) / 100)
            e["_scale"] = round(100 / f2 * e.get("_scale", 100) / 100, 3) if f2 else e.get("_scale", 100)
        ox, oy = e.get("_off") or (0, 0)
        f = e.get("_scale", 100) / 100
        L(f"var {v} = K.image({_js(str(p))}, {cx - ox * f:.0f}, {cy - oy * f:.0f}, {e.get('_scale', 100)});")
        if st.get("round") or st.get("frame"):
            L(f"K.fx({v}, 'ec.perspective.dropshadow', {{'Opacity': 18}});")
        if e.get("marks") or e.get("zoom"):
            _marks_zoom(ctx, e, v, cx, cy, w, h, cx - ox * f, cy - oy * f, e.get("_scale", 100))
    elif k == "code":
        L(f"var {v} = (function(box){{ var cx=box[0], cy=box[1], w=box[2], h=box[3];\n{e['code']}\n}})([{cx:.0f}, {cy:.0f}, {w:.0f}, {h:.0f}]);")
    if op is not None and k != "code":
        L(f"K.O({v}).setValue({float(op)});")


def _marks_zoom(ctx: _Ctx, e: dict, v: str, cx: float, cy: float, w: float, h: float, px: float, py: float, sc: float) -> None:
    """그림 안 구역 강조 · 확대. 확대는 그림의 위치 · 크기 키를 바꾸고, 강조는 같은 변환을 계산해 따라 움직인다(부모로 묶지 않는다)"""
    L = ctx.lines.append
    t0 = _time(ctx, e)
    z = e.get("zoom")
    k, tz, shift = 1.0, None, (0.0, 0.0)
    if z:
        zx, zy, zw, zh = z["box"]
        rcx, rcy = cx - w / 2 + (zx + zw / 2) * w, cy - h / 2 + (zy + zh / 2) * h      # 화면에서 그 구역의 가운데
        k = max(1.0, min(3.5, (SAFE[2] - SAFE[0]) / max(1.0, zw * w), (SAFE[3] - SAFE[1]) * 0.75 / max(1.0, zh * h)))
        T = ((SAFE[0] + SAFE[2]) / 2, (SAFE[1] + SAFE[3]) / 2)
        shift = (T[0] - (cx + k * (rcx - cx)), T[1] - (cy + k * (rcy - cy)))          # 확대 뒤 그림 가운데가 옮겨 갈 만큼
        tz = f"$CUE:{z['on']}" if z.get("on") else f"({t0} + 0.6)"
        L(f"(function(){{var p=K.P({v}), s=K.S({v}); p.setValueAtTime({tz}, [{px:.0f}, {py:.0f}]); p.setValueAtTime({tz}+0.6, [{px + shift[0] + (k - 1) * (px - cx):.0f}, {py + shift[1] + (k - 1) * (py - cy):.0f}]);"
          f" s.setValueAtTime({tz}, [{sc}, {sc}]); s.setValueAtTime({tz}+0.6, [{sc * k:.2f}, {sc * k:.2f}]); K.ease(p, 70); K.ease(s, 70);}})();")
    for j, m in enumerate(e.get("marks") or []):
        mx, my, mw, mh = m["box"]
        style = m.get("style", "box")
        col = ctx.color(m.get("color"), "accent")
        lx, ly = cx - w / 2 + (mx + mw / 2) * w, cy - h / 2 + (my + mh / 2) * h      # 확대 전 자리
        bw, bh = mw * w, mh * h
        tm = f"$CUE:{m['on']}" if m.get("on") else (f"({tz}+0.65)" if tz else f"({t0} + 0.4)")
        mv = f"{v}_m{j}"
        if style == "highlight":
            L(f"var {mv} = K.shape('rect', {lx:.0f}, {ly:.0f}, {bw:.0f}, {bh:.0f}, {{fill:{_js(col)}}}); K.O({mv}).setValue(0); K.O({mv}).setValueAtTime({tm}, 0); K.O({mv}).setValueAtTime({tm}+0.2, 38);")
        elif style == "underline":
            L(f"var {mv} = K.shape('rect', {lx:.0f}, {ly + bh / 2:.0f}, {bw:.0f}, 6, {{fill:{_js(col)}}}); K.appear({mv}, {tm}, 0); (function(){{var s=K.S({mv}); s.setValueAtTime({tm}, [0,100]); s.setValueAtTime({tm}+0.3, [100,100]);}})();")
        else:
            L(f"var {mv} = K.shape('rect', {lx:.0f}, {ly:.0f}, {bw + 16:.0f}, {bh + 16:.0f}, {{stroke:{_js(col)}, strokeW:6, round:6}}); K.appear({mv}, {tm}, 0); K.draw({mv}, {tm}, 0.4);")
        if z:                                           # 확대와 같은 변환으로 따라간다
            nx, ny = cx + k * (lx - cx) + shift[0], cy + k * (ly - cy) + shift[1]
            L(f"(function(){{var p=K.P({mv}), s=K.S({mv}); p.setValueAtTime({tz}, [{lx:.0f}, {ly:.0f}]); p.setValueAtTime({tz}+0.6, [{nx:.0f}, {ny:.0f}]);"
              f" s.setValueAtTime({tz}, [100, 100]); s.setValueAtTime({tz}+0.6, [{100 * k:.1f}, {100 * k:.1f}]); K.ease(p, 70); K.ease(s, 70);}})();")


def compile_scene(design: dict, sb: dict, n: int) -> str:
    """설계 한 장면 → K 코드(문자열). n 은 1부터"""
    errs = validate(design, f"s{n:02d}")
    if errs:
        raise ValueError("장면 설계 오류: " + " · ".join(errs[:12]))
    sid = sb["id"]
    ctx = _Ctx(sb, sid, n)
    flat: list[tuple[dict, str | None]] = []           # (요소, 부모 묶음 id)

    def walk(lst, parent):
        for e in lst:
            flat.append((e, parent))
            if e["kind"] == "group":
                walk(e["children"], e["id"])

    walk(design["els"], None)
    top = [e for e, par in flat if par is None]
    _layout(ctx, top)
    for e, par in flat:                                 # 묶음 안 요소: 묶음 상자 안에서 위→아래(관계 · 좌표가 있으면 그것대로)
        if par is not None and e["id"] not in ctx.box:
            pass
    groups = [e for e, par in flat if e["kind"] == "group"]
    for g in groups:
        gx, gy, gw, gh = ctx.box[g["id"]]
        sub = _Ctx(sb, sid, n)
        sub.box = dict(ctx.box)
        saved = SAFE
        globals()["SAFE"] = (gx - gw / 2, gy - gh / 2, gx + gw / 2, gy + gh / 2)
        try:
            _layout(sub, g["children"])
        finally:
            globals()["SAFE"] = saved
        ctx.box.update({c["id"]: sub.box[c["id"]] for c in g["children"]})
    bg = design.get("bg") or "bg"
    bgv = [ctx.color(x) for x in bg] if isinstance(bg, list) else ctx.color(bg)
    L = ctx.lines.append
    L(f"// 장면 {n} — 설계 언어에서 컴파일(engine/craft/design_lang.py) · 손으로 고치지 말고 설계를 고친다")
    L(f"K.scene(K.C.duration, {_js(bgv)});")
    var = {e["id"]: f"e_{re.sub(r'[^A-Za-z0-9_]', '_', e['id'])}" for e, _ in flat}
    order = sorted([e for e, _ in flat], key=lambda e: 0 if (e.get("role") == "backdrop") else 1)
    for e in order:
        if e["kind"] == "group":
            gx, gy, *_ = ctx.box[e["id"]]
            L(f"var {var[e['id']]} = K.C.layers.addNull(); {var[e['id']]}.name = {_js('G_' + e['id'])}; K.P({var[e['id']]}).setValue([0, 0]);")
            continue
        ctx.start[e["id"]] = _time(ctx, e)
        _emit(ctx, e, var[e["id"]])
    for e, par in flat:                                 # 묶음: 자식을 원점 기준 묶음(null)에 붙인다 — 묶음이 움직이면 같이
        if par is not None:
            L(f"{var[e['id']]}.parent = {var[par]};")
    for e in order:
        t = ctx.start.get(e["id"]) or _time(ctx, e)
        ctx.start[e["id"]] = t
        if e["kind"] == "group":
            gx, gy, *_ = ctx.box[e["id"]]
            nm = e.get("enter")
            if nm:
                name = nm.get("name") if isinstance(nm, dict) else nm
                d = {"drop": (0, -90), "rise": (0, 90), "slide_left": (260, 0), "slide_right": (-260, 0), "slide_up": (0, 200), "slide_down": (0, -200)}.get(name)
                if d:
                    L(f"K.move({var[e['id']]}, {t}, [{d[0]}, {d[1]}], [0, 0], 0.4);")
            continue
        if e["kind"] != "code":
            _enter(ctx, var[e["id"]], e, t)
        _fx(ctx, var[e["id"]], e, t)
        _after(ctx, var[e["id"]], e, {k: var[k] for k in ctx.start if k != e["id"]})
    cam = design.get("camera") or {}
    mv = cam.get("move", "none")
    if mv != "none":
        a = float(cam.get("amount", 0.06))
        t0 = f"$CUE:{cam['on']}" if cam.get("on") else "0"
        L("(function(){ var cam = K.C.layers.addNull(); cam.name = 'CAM'; K.P(cam).setValue([0,0]);")
        L("  for (var i = 1; i <= K.C.numLayers; i++) { var l = K.C.layer(i); if (l !== cam && l.name !== 'BG' && !l.parent) l.parent = cam; }")
        L(f"  var tr = cam.property('Transform'); tr.property('Anchor Point').setValue([{W // 2}, {H // 2}]); tr.property('Position').setValue([{W // 2}, {H // 2}]);")
        if mv in ("push", "pull"):
            s0, s1 = (100, 100 * (1 + a)) if mv == "push" else (100 * (1 + a), 100)
            L(f"  var s = tr.property('Scale'); s.setValueAtTime({t0}, [{s0},{s0}]); s.setValueAtTime(K.C.duration, [{s1:.1f},{s1:.1f}]); K.ease(s, 40);")
        else:
            dx, dy = {"pan_left": (W * a, 0), "pan_right": (-W * a, 0), "rise": (0, H * a), "sink": (0, -H * a)}[mv]
            L(f"  var p = tr.property('Position'); p.setValueAtTime({t0}, [{W // 2},{H // 2}]); p.setValueAtTime(K.C.duration, [{W // 2 + dx:.0f},{H // 2 + dy:.0f}]); K.ease(p, 40);")
        L("})();")
    return "\n".join(ctx.lines) + "\n"


# ---------------- 파일 ----------------
PREFIX = "$DESIGN:"


def design_path(sid: str, n: int) -> Path:
    return ROOT / "data" / "compositions" / sid / "design" / f"s{n:02d}.json"


def compile_ref(ref: str) -> str:
    """"$DESIGN:data/compositions/<id>/design/sNN.json" → K 코드. 콘티는 data/storyboards/<id>.json 에서 읽는다"""
    f = Path(ref[len(PREFIX):].strip())
    f = f if f.is_absolute() else ROOT / f
    f = f.resolve()
    if ROOT.resolve() not in f.parents:
        raise RuntimeError(f"$DESIGN: 저장소 밖 파일은 쓸 수 없습니다: {f}")
    m = re.match(r"s(\d+)\.json$", f.name)
    if not (m and f.parent.name == "design"):
        raise RuntimeError(f"$DESIGN: data/compositions/<id>/design/sNN.json 이어야 함: {f.name}")
    sid = f.parent.parent.name
    sb = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
    code = compile_scene(json.loads(f.read_text("utf-8")), sb, int(m.group(1)))
    out = f.parent / f"s{int(m.group(1)):02d}.gen.jsx"           # 보기용(사람 · 에이전트가 컴파일 결과를 확인) — 렌더는 위 문자열을 쓴다
    if not out.exists() or out.read_text("utf-8") != code:
        out.write_text(code, "utf-8")
    return code


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    print(compile_ref(PREFIX + sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
