"""CADCraft 어댑터 — 도면 화면(drawing): 9:16 도면 PNG.

  { "id": "m1", "type": "drawing", "src": "data/public/uploads/<id>/plan.dxf", "window": [0, 0, 12000, 9000], "paper": "dark" }
  { "id": "m2", "type": "drawing", "cmd": ["rectang {\"p1\":[0,0],\"p2\":[3600,6400]}", {"id": "text", "params": {...}}], "paper": "white" }
  { "id": "m3", "type": "drawing", "model": {"shape": "case", "size": [80, 50, 32]}, "views": ["iso", "top", "front", "right"], "title": "케이스 외형도" }
  { "id": "m4", "type": "drawing", "model": "m1" }      ← 같은 장면의 model3d 재료(m1.sc)에서 도면

흐름: 원본 DXF/DWG · CADCraft 명령(run --cmd) · SolidCraft 3D 모형(file.export_view_dxf 로 정면 · 평면 · 측면 · 등각 투영)
     → CADCraft 한 도면(.dxf, 편집 파일)으로: 3D 는 3각법 배치(평면도는 정면도 위, 우측면도는 정면도 오른쪽) + 전체 치수 + 제목
     → paper "dark"(기본): 헤드리스 MCP render — CAD 화면(어두운 배경 · 흰 선)을 1080×1920 으로, 도면 범위를 9:16 창으로 맞춰
       paper "white": plot(흰 종이 · 검은 선, ISO A4 세로) → 1080×1920 흰 바탕 가운데
mark: [[x0, y0, x1, y1], …](도면 좌표) → 빨간 구름 표시(revcloud). 기록의 "marks" 에 화면 비율 상자([x, y, w, h] 0~1, dark 일 때)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

VIEWS = {   # SolidCraft 카메라(yaw · pitch, 라디안): yaw 0 = +Y 를 봄(정면), -π/2 = 오른쪽에서
    "front": (0.0, 0.0), "top": (0.0, math.pi / 2 - 1e-4), "right": (-math.pi / 2, 0.0), "left": (math.pi / 2, 0.0),
    "back": (math.pi, 0.0), "iso": (-math.pi / 4, math.atan(1 / math.sqrt(2))),
}
LABEL = {"front": "정면도", "top": "평면도", "right": "우측면도", "left": "좌측면도", "back": "배면도", "iso": "등각도"}


def _cmd(c) -> str:
    """콘티 명령 한 줄 → 'id {json}'"""
    if isinstance(c, str):
        return c.strip()
    if isinstance(c, dict) and (c.get("id") or c.get("command")):
        return f"{c.get('id') or c.get('command')} {json.dumps(c.get('params') or {}, ensure_ascii=False)}"
    raise RuntimeError(f"CADCraft 명령 형식이 아닙니다: {str(c)[:80]}")


def _info(cli: str, dxf: Path, work: Path) -> dict:
    from ..materials import _run
    out = _run([cli, "info", dxf, "--compact"], work)
    return json.loads(out[out.find("{"):])


# ---------------------------------------------------------------- 3D 모형 → 투영도
def _model_sc(m: dict, work: Path) -> Path:
    """model: 같은 장면의 model3d 재료 id(그 .sc) 또는 model3d 재료 칸(dict) → SolidCraft 설계 파일"""
    spec = m.get("model")
    if isinstance(spec, str):
        sc = work / f"{spec}.sc"
        if not sc.exists():
            raise RuntimeError(f"같은 장면에 3D 재료 '{spec}' 이 아직 없습니다(model3d 재료를 이 도면보다 앞에 두거나, model 에 형태 칸을 직접 쓴다)")
        return sc
    from .solidcraft import design
    return design(dict(spec), work, f"{m['id']}.model")["sc"]


def model_views(m: dict, work: Path, stem: str) -> tuple[list[dict], list]:
    """SolidCraft 로 보기마다 DXF(보이는 선) → ([{view, dxf}], 모형 크기 [폭 X, 깊이 Y, 높이 Z] mm)"""
    from ..materials import cli, _run
    from .solidcraft import _boxes, _c, _write
    sc = _model_sc(m, work)
    sc_cli = cli("solidcraft")
    obj = work / f"{stem}.views.obj"
    _run([sc_cli, "run", _write(work / f"{stem}.views0.json", [_c("file.export", path=str(obj))]), "--in", sc], work)
    bx = _boxes(obj)
    if not bx:
        raise RuntimeError("3D 모형에 몸체가 없습니다")
    lo = [min(b[0][k] for b in bx.values()) for k in range(3)]
    hi = [max(b[1][k] for b in bx.values()) for k in range(3)]
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    size = max(hi[k] - lo[k] for k in range(3))
    views = [v for v in (m.get("views") or ["iso", "top", "front", "right"]) if v in VIEWS]
    if not views:
        raise RuntimeError(f"views 는 {', '.join(VIEWS)} 중에서")
    cmds, out = [], []
    for v in views:
        yaw, pitch = VIEWS[v]
        f = work / f"{stem}.{v}.dxf"
        # 아주 먼 곳에서 좁은 화각 = 거의 정투영(대상 평면에서 축척 1:1)
        cmds.append(_c("file.export_view_dxf", camera={"target": c, "yaw": yaw, "pitch": pitch, "distance": size * 400, "fov": 0.002},
                       hidden="dashed" if m.get("hidden") else "omit", path=str(f)))
        out.append({"view": v, "dxf": f})
    _run([sc_cli, "run", _write(work / f"{stem}.views.json", cmds), "--in", sc], work)
    for o in out:
        if not o["dxf"].exists():
            raise RuntimeError(f"SolidCraft 가 {o['view']} 도면을 내지 않았습니다")
    return out, [hi[k] - lo[k] for k in range(3)]


def _mm(v: float) -> str:
    """치수 글자: 0.1mm 까지, 끝의 0 은 뺀다(80.04 → 80, 12.35 → 12.4)"""
    return f"{round(v, 1):g}"


def layout_views(cli: str, views: list[dict], work: Path, m: dict, size: list | None = None) -> tuple[list[str], list]:
    """보기 DXF 들을 3각법으로 배치하는 CADCraft 명령 + 전체 범위.
    정면도를 가운데 두고 평면도는 위, 우측면도(좌측면도)는 옆, 배면도는 오른쪽 끝, 등각도는 맨 위"""
    ext = {}
    for v in views:
        e = _info(cli, v["dxf"], work).get("extents") or [[0, 0], [0, 0]]
        ext[v["view"]] = (e[0][0], e[0][1], e[1][0], e[1][1])
    def wh(k):
        x0, y0, x1, y1 = ext[k]
        return x1 - x0, y1 - y0
    fw, fh = wh("front") if "front" in ext else (max(wh(k)[0] for k in ext), max(wh(k)[1] for k in ext))
    gap = 0.35 * max(fw, fh)
    pos = {}                                   # 보기 → 가운데 자리
    pos["front"] = (0.0, 0.0)
    if "top" in ext:
        pos["top"] = (0.0, fh / 2 + gap + wh("top")[1] / 2)
    if "right" in ext:
        pos["right"] = (fw / 2 + gap + wh("right")[0] / 2, 0.0)
    if "left" in ext:
        pos["left"] = (-(fw / 2 + gap + wh("left")[0] / 2), 0.0)
    if "back" in ext:
        x = (pos["right"][0] + wh("right")[0] / 2) if "right" in ext else fw / 2
        pos["back"] = (x + gap + wh("back")[0] / 2, 0.0)
    if "front" not in ext:                     # 정면도 없이: 차례로 세로로 쌓는다
        pos, y = {}, 0.0
        for v in views:
            if v["view"] != "iso":
                pos[v["view"]] = (0.0, y - wh(v["view"])[1] / 2)
                y -= wh(v["view"])[1] + gap
    top_y = max(p[1] + wh(k)[1] / 2 for k, p in pos.items())
    if "iso" in ext:
        xs = [p[0] - wh(k)[0] / 2 for k, p in pos.items()] + [p[0] + wh(k)[0] / 2 for k, p in pos.items()]
        pos["iso"] = ((min(xs) + max(xs)) / 2, top_y + gap * 1.3 + wh("iso")[1] / 2)
    cmds = []
    for v in views:
        k = v["view"]
        x0, y0, x1, y1 = ext[k]
        cx, cy = pos[k]
        cmds.append(_cmd({"id": "import", "params": {"path": str(v["dxf"]), "at": [cx - (x0 + x1) / 2, cy - (y0 + y1) / 2]}}))
    # 범위(치수 · 글자 자리 포함 전)
    boxes = {k: (pos[k][0] - wh(k)[0] / 2, pos[k][1] - wh(k)[1] / 2, pos[k][0] + wh(k)[0] / 2, pos[k][1] + wh(k)[1] / 2) for k in pos}
    X0 = min(b[0] for b in boxes.values()); Y0 = min(b[1] for b in boxes.values())
    X1 = max(b[2] for b in boxes.values()); Y1 = max(b[3] for b in boxes.values())
    span = max(X1 - X0, (Y1 - Y0) * 9 / 16)
    th = span / 34                             # 글자 높이: 도면 폭의 1/34 — 세로 화면에서 읽히게
    cmds.append(_cmd({"id": "setvar", "params": {"name": "DIMSCALE", "value": round(th / 2.5, 4)}}))
    off = th * 2.2
    # 치수 글자는 모형 크기(메시 꼭짓점 상자)로 — 투영 선의 범위는 곡선 근사 오차로 80.04 처럼 나온다
    sx, sy, sz = size or (None, None, None)
    def dim(p1, p2, at, val):
        p = {"p1": p1, "p2": p2, "at": at}
        if val:
            p["text"] = _mm(val)
        cmds.append(_cmd({"id": "dimlinear", "params": p}))
    if "front" in boxes:                       # 전체 치수: 폭 · 높이(정면도), 깊이(측면도나 평면도)
        b = boxes["front"]
        dim([b[0], b[1]], [b[2], b[1]], [(b[0] + b[2]) / 2, b[1] - off], sx)
        dim([b[0], b[1]], [b[0], b[3]], [b[0] - off, (b[1] + b[3]) / 2], sz)
    side = boxes.get("right") or boxes.get("left")
    if side:
        dim([side[0], side[1]], [side[2], side[1]], [(side[0] + side[2]) / 2, side[1] - off], sy)
    elif "top" in boxes:
        b = boxes["top"]
        dim([b[0], b[1]], [b[0], b[3]], [b[0] - off, (b[1] + b[3]) / 2], sy)     # 왼쪽에(오른쪽에 두면 글자가 거꾸로 선다)
    if m.get("labels", True):                  # 보기 이름(정면도 · 평면도 …) — 보기 아래 가운데
        for k, b in boxes.items():
            y = b[1] - (off * 2.1 if k in ("front", "right", "left") else th * 1.4)
            cmds.append(_cmd({"id": "text", "params": {"at": [(b[0] + b[2]) / 2, y], "text": LABEL[k], "height": th * 0.8, "justify": "TC"}}))
    Y0 -= off * 2.1 + th * 1.2
    if m.get("title"):
        cmds.append(_cmd({"id": "text", "params": {"at": [(X0 + X1) / 2, Y0 - th * 1.6], "text": str(m["title"]), "height": th * 1.3, "justify": "TC"}}))
        Y0 -= th * 3.2
    return cmds, [X0 - off * 1.6, Y0, X1 + off * 0.6, Y1]


# ---------------------------------------------------------------- 그리기 → 렌더
def _window(ext, W: int, H: int, margin: float = 0.07) -> list:
    """도면 범위 → 화면 비율(W:H)의 창 [[x0, y0], [x1, y1]] (가운데 맞춤 · 여백)"""
    x0, y0, x1, y1 = ext
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    a = W / H
    if w / h > a:
        h = w / a
    else:
        w = h * a
    w, h = w * (1 + 2 * margin), h * (1 + 2 * margin)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return [[cx - w / 2, cy - h / 2], [cx + w / 2, cy + h / 2]]


def _render_dark(cli: str, dxf: Path, out: Path, work: Path, win, W: int, H: int):
    from .texturecraft import Mcp
    with Mcp([cli, "mcp"], work) as s:
        s.call("open", {"path": str(dxf)})
        r = s.call("render", {"width": W, "height": H, "window": win})
    if not r["images"]:
        raise RuntimeError(f"CADCraft 렌더가 그림을 돌려주지 않았습니다: {r['text'][:200]}")
    out.write_bytes(r["images"][0])


def _mono(im):
    """흰 종이 출력의 단색 펜(monochrome.ctb 처럼): 노랑 · 하늘색 글자가 흰 바탕에서 안 보이므로 색을 가장 어두운 채널로.
    빨간 표시(mark)만 빨강으로 남긴다"""
    import numpy as np
    from PIL import Image
    a = np.asarray(im).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 150) & (g < 120) & (b < 120)
    k = a.min(axis=2)
    k = np.where(k < 235, (k * 0.55).astype(np.int16), k)     # 옅은 회색 선도 또렷하게
    out = np.stack([k, k, k], axis=2)
    out[red] = [220, 38, 38]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def _render_white(cli: str, dxf: Path, out: Path, work: Path, W: int, H: int, landscape: bool = False):
    """plot(흰 종이 출력) → W×H 흰 바탕 가운데(종이 여백은 잘라 낸다)"""
    from ..materials import _run
    from PIL import Image, ImageOps
    raw = work / f"{out.stem}.plot.png"
    _run([cli, "run", dxf, "--cmd", _cmd({"id": "plot", "params": {"path": str(raw), "device": "CADCraft PNG",
                                                                     "paper": "ISO A4 (210.00 x 297.00 MM)", "landscape": landscape,
                                                                     "fit": True, "lineweights": True}})], work)
    if not raw.exists():
        raise RuntimeError("CADCraft plot 이 PNG 를 내지 않았습니다")
    im = _mono(Image.open(raw).convert("RGB"))
    bb = ImageOps.invert(im).getbbox()                 # 그린 부분만
    if bb:
        im = im.crop(bb)
    k = min(W * 0.88 / im.width, H * 0.88 / im.height)
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    page = Image.new("RGB", (W, H), "white")
    page.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    page.save(out)


def drawing(m: dict, out: Path, work: Path) -> dict:
    from ..materials import cli, _run, _abs, _hash, _load, ROOT
    cad = cli("cadcraft")
    dxf = work / f"{out.stem}.dxf"
    old = _load(work / f"{out.stem}.json")
    edited = dxf.exists() and old.get("editable_hash") and _hash(dxf) != old["editable_hash"]
    marks = [list(map(float, r)) for r in (m.get("mark") or [])]
    # 강조 구름: 굵은 빨강, 호 길이는 상자 짧은 변의 1/5(기본값은 큰 도면에서 그냥 네모로 보인다)
    mark_cmds = ([_cmd({"id": "color", "params": {"color": "255,59,48"}}), _cmd({"id": "lweight", "params": {"lineweight": 0.7}}),
                  _cmd({"id": "lwdisplay", "params": {"on": True}})] +
                 [_cmd({"id": "revcloud", "params": {"p1": r[:2], "p2": r[2:4], "arcLength": max(1e-6, min(abs(r[2] - r[0]), abs(r[3] - r[1])) / 5)}})
                  for r in marks]) if marks else []
    ext = None
    source = None
    if edited:
        source = "edited"                        # 사람이 CADCraft 에서 고친 도면 그대로
    elif m.get("src"):
        src = _abs(m["src"])
        if not src.exists():
            raise RuntimeError(f"도면 파일이 없습니다: {m['src']}")
        if src.suffix.lower() not in (".dxf", ".dwg"):
            raise RuntimeError(f"도면은 DXF · DWG 만: {src.name}")
        args = [cad, "run", src]
        for c in mark_cmds:
            args += ["--cmd", c]
        _run(args + ["--save", dxf], work)
        source = "src"
    elif m.get("cmd") or m.get("commands"):
        args = [cad, "run", "--metric"]
        for c in (m.get("cmd") or m.get("commands")):
            args += ["--cmd", _cmd(c)]
        for c in mark_cmds:
            args += ["--cmd", c]
        _run(args + ["--save", dxf], work)
        source = "cmd"
    elif m.get("model"):
        views, size = model_views(m, work, out.stem)
        cmds, _ = layout_views(cad, views, work, m, size)      # 범위는 저장한 도면에서 다시 읽는다(치수 글자까지 들어가게)
        args = [cad, "run", "--metric"]
        for c in cmds + mark_cmds:
            args += ["--cmd", c]
        _run(args + ["--save", dxf], work, timeout=300)
        source = "model"
    else:
        raise RuntimeError("drawing 재료에는 src(DXF · DWG) · cmd(CADCraft 명령 목록) · model(3D 모형) 중 하나가 필요합니다")
    if not dxf.exists():
        raise RuntimeError("CADCraft 가 도면을 저장하지 않았습니다")
    W, H = int(m.get("width", 1080)), int(m.get("height", 1920))
    if m.get("window"):
        x0, y0, x1, y1 = map(float, m["window"])
        ext = [x0, y0, x1, y1]
    if ext is None:
        e = _info(cad, dxf, work).get("extents")
        if not e:
            raise RuntimeError("도면이 비어 있습니다(범위 없음)")
        ext = [e[0][0], e[0][1], e[1][0], e[1][1]]
    win = _window(ext, W, H, float(m.get("margin", 0.07)))
    paper = str(m.get("paper", "dark")).lower()
    if paper in ("white", "paper", "흰", "흰색", "종이"):
        _render_white(cad, dxf, out, work, W, H)
        paper = "white"
    else:
        _render_dark(cad, dxf, out, work, win, W, H)
        paper = "dark"
    info = {"app": "cadcraft", "paper": paper, "size": [W, H], "source": source, "as": "image",
            "editable": str(dxf.relative_to(ROOT)) if dxf.is_relative_to(ROOT) else str(dxf), "editable_hash": _hash(dxf),
            "window": win}
    if marks and paper == "dark":                # 구름 표시 자리(화면 비율) — 움직임 단계가 확대 · 강조에 쓸 수 있다
        (wx0, wy0), (wx1, wy1) = win
        info["marks"] = [{"box": [round((min(r[0], r[2]) - wx0) / (wx1 - wx0), 4), round((wy1 - max(r[1], r[3])) / (wy1 - wy0), 4),
                                  round(abs(r[2] - r[0]) / (wx1 - wx0), 4), round(abs(r[3] - r[1]) / (wy1 - wy0), 4)]} for r in marks]
    return info


ADAPTERS = {"drawing": drawing}
