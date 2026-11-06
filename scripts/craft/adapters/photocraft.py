"""PhotoCraft 어댑터 — 사진 · 캡처 재료(type: photo).

콘티 칸(모두 선택):
  src          원본 사진 · 캡처(필수)
  cutout       true → 피사체 누끼(고전 알고리즘: 단순 배경만 쓸 만함)
  alpha_text   true → 흰 배경 캡처의 글자만 남긴 투명 PNG(Color to Alpha). "alpha_color" 로 지울 색
  clean        [[x,y,w,h], …] → 로고 · 워터마크 지우기(Remove 툴). 0~1 이면 비율, 그보다 크면 원본 픽셀
  frame        "card" → 화면 비율(9:16 · 16:9 · 1:1) 장면 카드: 흐린 배경 채우기 · 둥근 모서리 · 그림자
  title        카드 위 제목(줄바꿈 \\n, 없으면 알아서 나눈다)
  highlight    [x,y,w,h] 강조 상자(원본 기준, 0~1 또는 픽셀) — 카드면 노란 상자를 그린다
  spotlight    true → 강조 상자 밖을 어둡게(카드일 때)

사람이 고칠 편집 파일: 카드는 work/<id>.psd(레이어 · 스마트 오브젝트 그대로).
PhotoCraft run 은 입력을 위치 인자로 받는다(`run <FILE> --cmd …`) — 예전 materials.photo() 의 `--in` 은 늘 실패했다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

FONT = "Noto Sans CJK KR"          # Pretendard 는 시스템 글꼴이 아니라 PhotoCraft 가 못 쓴다
ACCENT = "#ffd60a"
K = 0.5523                         # 원을 베지어로 그릴 때 손잡이 길이 비율


def _rel(p: Path) -> str:
    from ..materials import ROOT
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _cmd(args: list, cid: str, params: dict | None = None) -> None:
    args += ["--cmd", cid]
    if params is not None:
        args += ["--params", json.dumps(params, ensure_ascii=False)]


def _results(stdout: str) -> dict:
    """각 --cmd 결과 줄({"command","result"}) → {명령: [결과…]}"""
    out: dict = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out.setdefault(r.get("command"), []).append(r.get("result"))
    return out


def _size(P: str, f: Path, work: Path) -> tuple[int, int]:
    from ..materials import _run
    d = json.loads(_run([P, "info", f, "--compact"], work))
    return int(d["width"]), int(d["height"])


def _box(b, w: int, h: int) -> tuple[float, float, float, float]:
    """[x,y,w,h] — 모두 0~1 이면 비율, 아니면 픽셀 → 픽셀"""
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        raise RuntimeError(f"상자는 [x, y, w, h] 네 숫자여야 합니다: {b}")
    x, y, bw, bh = (float(v) for v in b)
    if max(x, y, bw, bh) <= 1.0:
        x, y, bw, bh = x * w, y * h, bw * w, bh * h
    return x, y, bw, bh


def _aspect(m: dict, out: Path) -> tuple[int, int]:
    """화면 크기: 콘티 aspect(out = compositions/<id>/craft/materials/sNN/x.png 에서 콘티를 찾는다) · 렌더 옵션 FLUMA_ASPECT"""
    import sys
    from ..materials import ROOT, _load
    sys.path.insert(0, str(ROOT / "scripts"))
    from engines import aspect_size
    sb = None
    try:
        sid = out.parents[3].name if out.parents[2].name == "craft" else None
        sb = _load(ROOT / "storyboards" / f"{sid}.json") if sid else None
    except IndexError:
        pass
    if m.get("aspect"):
        sb = {**(sb or {}), "aspect": m["aspect"]}
    return aspect_size(sb or None)


def _round_rect(x: float, y: float, w: float, h: float, r: float) -> dict:
    """둥근 사각형 경로(벡터 마스크용)"""
    r = max(0.0, min(r, w / 2, h / 2))
    c = r * K
    x1, y1 = x + w, y + h

    def kn(ax, ay, ix, iy, ox, oy):
        return {"anchor": [ax, ay], "in": [ix, iy], "out": [ox, oy], "smooth": True}
    knots = [
        kn(x + r, y, x + r - c, y, x + r, y), kn(x1 - r, y, x1 - r, y, x1 - r + c, y),
        kn(x1, y + r, x1, y + r - c, x1, y + r), kn(x1, y1 - r, x1, y1 - r, x1, y1 - r + c),
        kn(x1 - r, y1, x1 - r + c, y1, x1 - r, y1), kn(x + r, y1, x + r, y1, x + r - c, y1),
        kn(x, y1 - r, x, y1 - r + c, x, y1 - r), kn(x, y + r, x, y + r, x, y + r - c),
    ]
    return {"subpaths": [{"closed": True, "knots": knots}]}


def _em(text: str) -> float:
    """글자 너비 어림(굵은 고딕, 글자 크기 = 1): 한글 · 한자 1, 영문 · 숫자 0.62, 띄어쓰기 0.3"""
    return sum(0.3 if c == " " else 0.62 if ord(c) < 0x1100 else 1.0 for c in text)


def _wrap(text: str, max_em: float) -> list[str]:
    """제목 줄 나누기: \\n 이 있으면 그대로, 없으면 줄 수를 먼저 정하고 낱말 단위로 고르게(한 줄만 짧게 남지 않게)"""
    if "\n" in text:
        return [s.strip() for s in text.split("\n") if s.strip()][:3]
    words = text.split()
    n = min(3, max(1, -(-int(_em(text) * 100) // int(max_em * 100))))
    target = _em(text) / n
    lines, cur = [], ""
    for wd in words:
        nxt = f"{cur} {wd}".strip()
        # 지금 줄에 붙이면 목표보다 반 낱말 넘게 길어지거나 한 줄 폭을 넘으면 새 줄
        if cur and len(lines) < n - 1 and (_em(nxt) - _em(wd) / 2 > target or _em(nxt) > max_em):
            lines.append(cur)
            cur = wd
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- 1단계: 원본 다듬기(지우기 · 누끼 · 글자만)
def _prep(P: str, m: dict, src: Path, work: Path) -> tuple[Path, dict]:
    from ..materials import _run
    w, h = _size(P, src, work)
    args = [P, "run", src]
    info: dict = {}
    if m.get("clean"):
        strokes = []
        for b in m["clean"]:
            x, y, bw, bh = _box(b, w, h)
            # 상자를 덮는 붓질 한 획: 짧은 변보다 조금 굵게, 긴 변을 따라
            size = max(8.0, min(bw, bh) * 1.25)
            if bw >= bh:
                cy = y + bh / 2
                pts = [[x + size * 0.4, cy], [x + bw - size * 0.4, cy]] if bw > size * 0.8 else [[x + bw / 2, cy]]
            else:
                cx = x + bw / 2
                pts = [[cx, y + size * 0.4], [cx, y + bh - size * 0.4]] if bh > size * 0.8 else [[cx, y + bh / 2]]
            strokes.append({"points": [[round(p[0], 1), round(p[1], 1)] for p in pts], "size": round(size, 1), "hardness": 80})
        _cmd(args, "paint.remove", {"points": strokes[0]["points"], "size": strokes[0]["size"], "strokes": strokes, "closeLoops": False})
        info["cleaned"] = len(strokes)
    if m.get("cutout"):
        _cmd(args, "select.subject")
        _cmd(args, "layer.layerMask.revealSelection")
        _cmd(args, "select.deselect")
    if m.get("alpha_text"):
        # Background 는 투명을 못 가진다 → 일반 레이어로 바꾼 뒤 흰색을 알파로
        _cmd(args, "layer.new.layerFromBackground", {"ifPresent": True})
        _cmd(args, "filter.other.colorToAlpha", {"color": m.get("alpha_color", "#ffffff")})
        if m.get("trim", True) and not m.get("frame"):     # 글자 둘레 빈 곳을 잘라 오버레이로 쓰기 좋게
            _cmd(args, "image.trim", {"basedOn": "transparent"})
    if len(args) == 3:                  # 할 일이 없으면 원본을 그대로(PNG 로)
        return src, info
    dst = work / f"{m['id']}.prep.png"
    _run(args + ["--out", dst], work)
    return dst, info


# ---------------------------------------------------------------- 2단계: 장면 카드
def _card(P: str, m: dict, orig: Path, img: Path, out: Path, work: Path) -> dict:
    from ..materials import _run, _hash
    W, H = _aspect(m, out)
    w, h = _size(P, img, work)
    ow, oh = _size(P, orig, work)
    u = min(W, H)                                   # 기준 길이(1080)
    margin = round(u * 0.065)
    title = str(m.get("title") or "").strip()
    fsize = round(u * (0.078 if W < H else 0.062))
    lines = _wrap(title, (W - 2 * margin) / fsize) if title else []
    widest = max((_em(t) for t in lines), default=0)
    if widest * fsize > W - 2 * margin or len(lines) > 2:     # 넘치거나 세 줄이면 글자를 줄인다
        fsize = round(min(fsize * 0.86, (W - 2 * margin) / max(widest, 1)))
    lead = round(fsize * 1.28)
    top = round(H * (0.11 if W < H else 0.07))      # 쇼츠 위쪽 UI 를 피한다
    bottom = round(H * (0.72 if W < H else 0.93))   # 아래는 자막 · 버튼 자리(움직임 단계 자막이 0.76 — 0.80 이면 강조 상자와 겹쳤다, 2026-11-06)
    t_h = len(lines) * lead
    gap = round(u * 0.05) if lines else 0
    avail_w, avail_h = W - 2 * margin, bottom - top - t_h - gap
    s = min(avail_w / w, avail_h / h, float(m.get("max_scale", 3.0)))
    pw, ph = w * s, h * s
    # 제목 + 사진을 한 덩어리로: 남는 높이는 위 40% · 아래 60% 로 나눠 화면 가운데보다 살짝 위에
    spare = max(0.0, (bottom - top) - (t_h + gap + ph))
    top = round(top + spare * 0.4)
    cx = W / 2
    px, py = cx - pw / 2, top + t_h + gap
    rad = round(u * 0.028)

    psd = work / f"{m['id']}.psd"
    args = [P, "run", "--new", json.dumps({"width": W, "height": H, "background": "#0d0f13", "name": m["id"]})]
    # 배경: 같은 사진을 화면 가득 채워 흐리고 어둡게 — 빈 띠 없이 사진 색이 이어진다
    cover = max(W / ow, H / oh) * 100 * 1.08
    _cmd(args, "file.placeEmbedded", {"path": str(orig), "scale": round(cover, 2), "center": [W / 2, H / 2], "smartObject": False})
    _cmd(args, "layer.setProps", {"name": "Backdrop"})
    _cmd(args, "filter.blur.gaussianBlur", {"radius": round(u * 0.045)})
    _cmd(args, "layer.newAdjustmentLayer.hueSaturation", {"saturation": -20, "lightness": -55})
    _cmd(args, "layer.setProps", {"name": "Backdrop Dim"})
    # 위아래를 더 어둡게(제목 · 자막이 잘 읽히게) — 투명도 단계가 있는 그라데이션 사각형
    _cmd(args, "shape.create", {"kind": "rect", "rect": [0, 0, W, H], "stroke": None, "name": "Vignette",
                                "fill": {"gradient": {"stops": [[0, "#000000"], [1, "#000000"]], "angle": 90, "style": "linear",
                                                      "opacityStops": [[0, 0.6], [0.3, 0.0], [0.7, 0.0], [1, 0.6]]}}})
    # 사진 · 캡처: 스마트 오브젝트(사람이 내용만 바꿀 수 있게) + 둥근 모서리 + 그림자 + 얇은 테두리
    _cmd(args, "file.placeEmbedded", {"path": str(img), "scale": round(s * 100, 3), "center": [round(cx, 2), round(py + ph / 2, 2)]})
    _cmd(args, "layer.setProps", {"name": "Photo"})
    _cmd(args, "layer.vectorMask.add", {"path": _round_rect(px, py, pw, ph, rad)})
    _cmd(args, "layer.layerStyle.dropShadow", {"color": "#000000", "opacity": 65, "distance": round(u * 0.012), "size": round(u * 0.05), "angle": 90})
    _cmd(args, "layer.layerStyle.stroke", {"size": max(2, round(u * 0.002)), "position": "inside", "color": "#ffffff", "opacity": 22, "add": True})
    hl_card = None
    if m.get("highlight"):
        hx, hy, hw, hh = _box(m["highlight"], w, h)       # 다듬은 그림도 원본과 크기가 같다(trim 안 함)
        pad = round(u * 0.012)
        bx, by, bw, bh = px + hx * s - pad, py + hy * s - pad, hw * s + 2 * pad, hh * s + 2 * pad
        hl_card = [round(bx / W, 4), round(by / H, 4), round(bw / W, 4), round(bh / H, 4)]
        if m.get("spotlight"):
            _cmd(args, "select.rect", {"x": round(bx), "y": round(by), "width": round(bw), "height": round(bh), "feather": round(u * 0.01)})
            _cmd(args, "select.inverse")
            _cmd(args, "layer.newAdjustmentLayer.hueSaturation", {"lightness": -50, "saturation": -50})
            _cmd(args, "layer.setProps", {"name": "Spotlight"})
            _cmd(args, "select.deselect")
        sw = max(6, round(u * 0.009))
        _cmd(args, "shape.create", {"kind": "roundedRect", "rect": [round(bx), round(by), round(bw), round(bh)], "radii": round(u * 0.016),
                                    "fill": None, "stroke": {"width": sw, "color": m.get("highlight_color", ACCENT), "align": "center"}, "name": "Highlight"})
        _cmd(args, "layer.layerStyle.dropShadow", {"color": "#000000", "opacity": 45, "distance": 0, "size": round(u * 0.012)})
    for k, line in enumerate(lines):
        _cmd(args, "type.create", {"x": round(W / 2), "y": round(top + fsize * 0.92 + k * lead), "text": line, "align": "center",
                                   "font": FONT, "weight": 900, "size": fsize, "color": m.get("title_color", "#ffffff"), "name": f"Title {k + 1}"})
        _cmd(args, "layer.layerStyle.dropShadow", {"color": "#000000", "opacity": 70, "distance": round(u * 0.004), "size": round(u * 0.014), "angle": 90})
    _run(args + ["--out", psd], work)
    _run([P, "convert", psd, out], work)
    info = {"frame": "card", "size": [W, H], "photo_box": [round(px / W, 4), round(py / H, 4), round(pw / W, 4), round(ph / H, 4)],
            "editable": _rel(psd), "editable_hash": _hash(psd), "as": "image", "full_frame": True}
    if hl_card:
        info["highlight_box"] = hl_card     # 카드 기준 0~1 — 움직임 단계가 확대 · 짚기에 쓴다
    if lines:
        info["title"] = "\n".join(lines)
    return info


# ---------------------------------------------------------------- 어댑터
def photo(m: dict, out: Path, work: Path) -> dict:
    """PhotoCraft: 사진 · 캡처 정리 — 지우기(clean) → 누끼(cutout) · 글자만(alpha_text) → (선택) 장면 카드(frame: card)"""
    from ..materials import cli, _abs, _run, _hash, _load
    if not m.get("src"):
        raise RuntimeError("photo 재료에 src(사진 · 캡처 경로)가 없습니다")
    src = _abs(m["src"])
    if not src.exists():
        raise RuntimeError(f"사진 파일이 없습니다: {m['src']}")
    P = cli("photocraft")
    work.mkdir(parents=True, exist_ok=True)
    img, info = _prep(P, m, src, work)
    frame = m.get("frame")
    if frame and frame != "card":
        raise RuntimeError(f"모르는 frame: {frame} (card 만 됩니다)")
    psd = work / f"{m['id']}.psd"
    old = _load(out.with_suffix(".json"))
    if frame == "card" and psd.exists() and old.get("editable_hash") and _hash(psd) != old["editable_hash"]:
        # 사람이 PhotoCraft 에서 카드 PSD 를 고쳤다(만들 때 해시와 다름) → 다시 짜지 않고 그 PSD 를 그대로 PNG 로
        _run([P, "convert", psd, out], work)
        keep = {k: old[k] for k in ("frame", "size", "photo_box", "highlight_box", "title", "as", "full_frame", "cleaned") if k in old}
        info.update({**keep, "editable": _rel(psd), "editable_hash": _hash(psd), "edited_by_hand": True})
    elif frame == "card":
        info.update(_card(P, m, src, img, out, work))
    elif img != src:
        shutil.move(str(img), str(out))
    else:
        _run([P, "run", src, "--out", out], work)       # jpg · webp 도 PNG 하나로 맞춘다
    if not out.exists():
        raise RuntimeError("PhotoCraft 가 결과 PNG 를 만들지 않았습니다")
    info.setdefault("size", list(_size(P, out, work)))
    if m.get("highlight") and frame != "card" and not (m.get("alpha_text") and m.get("trim", True)):
        # 카드가 아니면 그리지 않고 자리만 넘긴다(그림 기준 0~1) — 움직임 단계가 상자 · 확대로 짚는다
        sw, sh = info["size"]
        x, y, bw, bh = _box(m["highlight"], sw, sh)
        info["highlight_box"] = [round(x / sw, 4), round(y / sh, 4), round(bw / sw, 4), round(bh / sh, 4)]
    return {"app": "photocraft", "cutout": bool(m.get("cutout")), "alpha_text": bool(m.get("alpha_text")), **info}


ADAPTERS = {"photo": photo}
