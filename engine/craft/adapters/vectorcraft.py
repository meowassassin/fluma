"""VectorCraft 어댑터 — 실제 화면 위 주석 오버레이(overlay) · 틀 하나로 찍어 내는 카드(template_card).

overlay: 같은 장면의 대상 재료(캡처 · 사진 · 영상) 위에 놓을 점선 박스 · 곡선 화살표 · 설명 글자를
  마크 하나 = 레이어 하나로 그리고, 레이어마다 투명 PNG 로 내보낸다(대상 이미지와 같은 크기로 그린 뒤
  내용만 잘라 box 를 0~1 비율로 기록). 사람이 고칠 .vectorcraft(맨 아래에 대상 화면이 템플릿 레이어로 깔림)도 남긴다.

  { "id": "m2", "type": "overlay", "target": "m1",
    "marks": [ { "kind": "box",   "box": [0.67, 0.015, 0.19, 0.037], "text": "공유 링크", "cue": "링크" },
               { "kind": "arrow", "box": [0.67, 0.015, 0.19, 0.037], "text": "여기 누르기", "cue": "누르면" },
               { "kind": "label", "box": [0.05, 0.45, 0.9, 0.05], "text": "결과는 아래에", "cue": null } ],
    "style": "hand", "color": "#ff2d55" }

  - box: [x, y, w, h] — 0~1 이면 대상 이미지 비율, 1 보다 크면 픽셀. arrow 는 box 대신 "from" · "to": [x, y] 도 된다
    (box 만 주면 그 상자를 가리키고, 꼬리는 빈 쪽에서 출발한다). box · arrow 에 text 를 주면 설명 글자가 같은 레이어에 붙는다
  - style: "clean"(기본: 점선 · 균일한 선) | "hand"(손그림: 굵기가 변하는 마커 선 · 살짝 흔들림 · 둘러 그린 동그라미)
  - 글꼴은 Noto Sans CJK KR(VectorCraft 는 Pretendard woff2 를 읽지 못한다)

template_card: 변수(variable.define · bind) + 데이터 세트(dataset.import) + action.batch(png) 로 틀 하나에서 카드를 찍는다.

  { "id": "m1", "type": "template_card", "template": "data/compositions/<id>/craft/art/price.vectorcraft",
    "csv": "data/2026-11-05-price.csv", "row": 0 }
  { "id": "m1", "type": "template_card", "values": { "품목": "배추 1포기", "가격": "4,980원", "반응": "평소 가격" } }

  - row: 0부터 센 행 번호 또는 CSV name 열 값. values 를 주면 CSV 대신 그 한 줄을 쓴다
  - template 이 없으면(또는 파일이 없으면) 기본 틀(제목 · 큰 값 · 반응 한 줄 카드)을 work 에 만들어 남긴다 —
    CSV 머리글(name 제외) 앞에서부터 셋을 제목 · 큰 값 · 반응 줄 변수로 묶는다
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

FONT = "Noto Sans CJK KR"
ACCENT = "#ff2d55"


# ---------------------------------------------------------------- 공통: VectorCraft 배치 실행
def _vc(steps: list, work: Path, name: str, exports: list | None = None, inp: Path | None = None,
        timeout: int = 180) -> list[dict]:
    """steps 를 run 배치로 돌려 단계별 결과(dict) 목록을 돌려준다. 실패하면 RuntimeError"""
    from ..materials import cli
    f = work / f"{name}.steps.json"
    f.write_text(json.dumps(steps, ensure_ascii=False, indent=1), "utf-8")
    args = [cli("vectorcraft"), "run"]
    if inp:
        args += ["--in", str(inp)]
    args += ["--commands", str(f)]
    for e in exports or []:
        args += ["--export", str(e)]
    try:
        r = subprocess.run(args, cwd=str(work), text=True, capture_output=True, timeout=timeout,
                           env={**os.environ, "VECTORCRAFT_NO_PREFS": "1", "DO_NOT_TRACK": "1"})
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"VectorCraft 가 {timeout}초 안에 끝나지 않았습니다({name})")
    if r.returncode != 0:
        raise RuntimeError(f"VectorCraft 실패({name}): {(r.stderr or r.stdout).strip()[-400:]}")
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _rel(p: Path) -> str:
    from ..materials import ROOT
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- overlay
def _target_file(m: dict, work: Path) -> tuple[Path, dict]:
    from ..materials import ROOT, _load
    tid = m.get("target")
    if not tid:
        raise RuntimeError("overlay 재료에 target(같은 장면 재료 id)이 없습니다")
    rec = _load(work / f"{tid}.json")
    f = ROOT / rec["file"] if rec.get("file") else None
    if not f or not f.exists():
        raise RuntimeError(f"overlay 대상 재료 {tid} 가 아직 없습니다(같은 장면에서 overlay 보다 앞에 두고, 만들어졌는지 확인)")
    return f, rec


def _size_and_ref(f: Path, work: Path, oid: str) -> tuple[int, int, Path | None]:
    """대상 파일의 픽셀 크기 + 편집 파일 바닥에 깔 참고 이미지(영상이면 첫 프레임)"""
    if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        from PIL import Image
        with Image.open(f) as im:
            return im.width, im.height, f
    ref = work / f"{oid}.ref.png"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(f), "-frames:v", "1", str(ref)],
                       check=True, timeout=60, capture_output=True)
        from PIL import Image
        with Image.open(ref) as im:
            return im.width, im.height, ref
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise RuntimeError(f"overlay 대상 {f.name} 의 크기를 읽지 못했습니다: {e}")


def _px_box(b, W: int, H: int) -> list[float] | None:
    if not b or len(b) != 4:
        return None
    x, y, w, h = (float(v) for v in b)
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.0:      # 0~1 비율
        return [x * W, y * H, w * W, h * H]
    return [x, y, w, h]


def _px_pt(p, W: int, H: int) -> list[float] | None:
    if not p or len(p) != 2:
        return None
    x, y = (float(v) for v in p)
    return [x * W, y * H] if max(abs(x), abs(y)) <= 1.0 else [x, y]


def _measure(texts: list[tuple[str, float]], work: Path, oid: str) -> list[dict]:
    """글자 상자 크기를 VectorCraft 로 잰다(같은 글꼴 · 크기 그대로) → [{w, h, top}] (top: 기준선에서 상자 위까지)"""
    if not texts:
        return []
    steps = [{"command": "file.new", "params": {"width": 2000, "height": 2000, "units": "Pixels"}}]
    for t, size in texts:
        steps.append({"command": "text.create", "params": {"x": 1000, "y": 1000, "text": t, "size": size,
                                                         "font": FONT, "style": "Black", "justify": "center"}})
    res = _vc(steps, work, f"{oid}.measure")
    out = []
    for r in res[1:1 + len(texts)]:
        b = (r.get("result") or {}).get("bounds") or {}
        out.append({"w": b.get("width", 0.0), "h": b.get("height", 0.0), "top": 1000 - b.get("y", 1000)})
    return out


def _arrow_path(a: list[float], b: list[float], bend: float) -> dict:
    """a → b 곡선(가운데가 옆으로 휜 3차 베지어). bend: 길이 대비 휨(+ 왼쪽)"""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    c1 = [a[0] + dx * 0.25 + nx * L * bend, a[1] + dy * 0.25 + ny * L * bend]
    c2 = [a[0] + dx * 0.75 + nx * L * bend * 0.6, a[1] + dy * 0.75 + ny * L * bend * 0.6]
    return {"anchors": [{"x": a[0], "y": a[1], "out": c1}, {"x": b[0], "y": b[1], "in": c2}]}


def _loop_path(box: list[float], pad: float, seed: int) -> dict:
    """손으로 둘러 그린 동그라미 — 한 바퀴하고 조금 더 돌아 끝이 겹친다(타원 근사 베지어, 반지름을 조금씩 흔든다)"""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    rx, ry = w / 2 + pad * 1.6, h / 2 + pad * 1.6
    n = 9                                         # 1.1바퀴를 9토막
    a0 = math.radians(-160)
    span = 2 * math.pi * 1.1
    k = 4 / 3 * math.tan(span / n / 4)            # 호 → 베지어 손잡이 길이
    jit = [1.0, 1.03, 0.98, 1.02, 0.97, 1.04, 0.99, 1.01, 1.05, 1.08]
    jit = jit[seed % 3:] + jit[:seed % 3]
    pts = []
    for i in range(n + 1):
        t = a0 + span * i / n
        s = jit[i % len(jit)]
        px, py = cx + rx * s * math.cos(t), cy + ry * s * math.sin(t)
        tx, ty = -rx * s * math.sin(t) * k, ry * s * math.cos(t) * k
        pts.append({"x": px, "y": py, "in": [px - tx, py - ty], "out": [px + tx, py + ty]})
    pts[0].pop("in")
    pts[-1].pop("out")
    return {"anchors": pts}


def _label_steps(text: str, cx: float, cy: float, me: dict, size: float, s: float, color: str,
                 hand: bool, W: int, H: int, base: int) -> tuple[list, list[float]]:
    """색 알약 위 흰 글자. (cx, cy) 가운데. 화면 밖으로 나가지 않게 민다 → (단계들, 알약 상자 [x, y, w, h])"""
    px, py = 26 * s, 14 * s
    bw, bh = me["w"] + px * 2, me["h"] + py * 2
    m = 12 * s
    x = min(max(cx - bw / 2, m), max(m, W - m - bw))
    y = min(max(cy - bh / 2, m), max(m, H - m - bh))
    rot = -2.5 if hand else 0
    steps = [
        {"command": "shape.rectangle", "params": {"x": x, "y": y, "width": bw, "height": bh, "radius": bh / 2 if not hand else bh * 0.3, "rotation": rot}},
        {"command": "paint.setFill", "params": {"id": f"${base}.id", "color": color}},
        {"command": "paint.setStroke", "params": {"id": f"${base}.id", "none": True}},     # shape 기본 검은 1pt 선 지우기
        {"command": "effect.apply", "params": {"id": f"${base}.id", "effect": "stylize.dropShadow",
                                               "params": {"x": 0, "y": 4 * s, "blur": 10 * s, "opacity": 35}}},
        {"command": "text.create", "params": {"x": x + bw / 2, "y": y + py + me["top"], "text": text, "size": size, "font": FONT,
                                              "style": "Black", "color": "#ffffff", "justify": "center", "rotation": rot}},
    ]
    if hand:
        steps.append({"command": "effect.apply", "params": {"id": f"${base}.id", "effect": "distort.roughen",
                                                            "params": {"size": 0.25, "detail": 5, "points": "smooth", "seed": base}}})
    return steps, [x, y, bw, bh]


def overlay(m: dict, out: Path, work: Path) -> dict:
    """대상 재료 위 주석(박스 · 화살표 · 글자) — 마크마다 레이어 · 투명 PNG, 편집 파일 .vectorcraft"""
    from PIL import Image
    tf, trec = _target_file(m, work)
    oid = m["id"]
    W, H, ref = _size_and_ref(tf, work, oid)
    marks = [mk for mk in (m.get("marks") or []) if isinstance(mk, dict)]
    if not marks:
        raise RuntimeError("overlay 재료에 marks(박스 · 화살표 · 글자)가 없습니다")
    hand = m.get("style") == "hand"
    s = min(W, H) / 1080
    color0 = m.get("color") or ACCENT
    size0 = float(m.get("size") or 52) * s

    # 1) 글자 크기 재기 — 알약 · 화살표 꼬리 위치를 정하려고
    texts = [(str(mk["text"]), float(mk.get("size") or 0) * s or size0) for mk in marks if mk.get("text")]
    meas = iter(_measure(texts, work, oid))

    steps: list = [{"command": "file.new", "params": {"width": W, "height": H, "units": "Pixels"}}]
    if ref:     # 맨 아래 레이어 = 대상 화면(템플릿: 잠기고 흐리게, 내보내지 않음) — 사람이 위치를 보며 고친다
        steps += [{"command": "file.place", "params": {"path": str(ref.resolve()), "rect": [0, 0, W, H]}},
                  {"command": "layer.setProps", "params": {"id": 1, "name": "대상 화면 (내보내지 않음)", "template": True}}]
    layer_idx: list[int] = []
    for k, mk in enumerate(marks):
        kind = mk.get("kind") or "box"
        if kind not in ("box", "arrow", "label"):
            raise RuntimeError(f"overlay 마크 kind 는 box · arrow · label 중 하나입니다(받은 값: {kind})")
        color = mk.get("color") or color0
        box = _px_box(mk.get("box"), W, H)
        layer_idx.append(len(steps))
        steps.append({"command": "layer.new", "params": {"name": f"{k + 1:02d} {kind}" + (f" · {mk['text']}" if mk.get("text") else ""), "top": True}})
        text = str(mk["text"]) if mk.get("text") else None
        me = next(meas) if text else None
        tsize = float(mk.get("size") or 0) * s or size0
        if kind == "label":
            if not box:
                raise RuntimeError(f"overlay label 마크({k + 1}번)에 box 가 없습니다")
            if not text:
                raise RuntimeError(f"overlay label 마크({k + 1}번)에 text 가 없습니다")
            st, _ = _label_steps(text, box[0] + box[2] / 2, box[1] + box[3] / 2, me, tsize, s, color, hand, W, H, len(steps))
            steps += st
            continue
        if kind == "box":
            if not box:
                raise RuntimeError(f"overlay box 마크({k + 1}번)에 box 가 없습니다")
            pad = 10 * s
            i = len(steps)
            if hand:
                steps += [{"command": "path.create", "params": _loop_path(box, pad, k)},
                          {"command": "paint.setFill", "params": {"id": f"${i}.id", "none": True}},
                          {"command": "paint.setStroke", "params": {"id": f"${i}.id", "color": color}},
                          {"command": "stroke.set", "params": {"id": f"${i}.id", "weight": 12 * s, "cap": "round", "join": "round", "profile": "lens"}},
                          {"command": "effect.apply", "params": {"id": f"${i}.id", "effect": "distort.roughen",
                                                                 "params": {"size": 0.4, "detail": 4, "points": "smooth", "seed": k + 3}}}]
            else:
                steps += [{"command": "shape.rectangle", "params": {"x": box[0] - pad, "y": box[1] - pad, "width": box[2] + pad * 2,
                                                                    "height": box[3] + pad * 2, "radius": 16 * s}},
                          {"command": "paint.setFill", "params": {"id": f"${i}.id", "none": True}},
                          {"command": "paint.setStroke", "params": {"id": f"${i}.id", "color": color}},
                          {"command": "stroke.set", "params": {"id": f"${i}.id", "weight": 7 * s, "dash": [22 * s, 13 * s], "cap": "round", "join": "round"}},
                          {"command": "effect.apply", "params": {"id": f"${i}.id", "effect": "stylize.dropShadow",
                                                                 "params": {"x": 0, "y": 2 * s, "blur": 6 * s, "opacity": 30}}}]
            if text:    # 설명 꼬리표: 박스 위(자리가 없으면 아래), 박스 왼쪽 끝에 맞춘다
                gap = (pad * 2.6 if hand else pad) + 10 * s
                bh = me["h"] + 28 * s
                cy = box[1] - gap - bh / 2
                if cy - bh / 2 < 12 * s:
                    cy = box[1] + box[3] + gap + bh / 2
                cx = box[0] - pad + (me["w"] + 52 * s) / 2
                st, _ = _label_steps(text, cx, cy, me, tsize, s, color, hand, W, H, len(steps))
                steps += st
            continue
        # arrow — 끝: to 또는 box 가장자리, 꼬리: from 또는 빈 쪽
        to = _px_pt(mk.get("to"), W, H)
        fr = _px_pt(mk.get("from"), W, H)
        gap = 18 * s
        if not to:
            if not box:
                raise RuntimeError(f"overlay arrow 마크({k + 1}번)에 box 또는 to 가 없습니다")
            bx, by = box[0] + box[2] / 2, box[1] + box[3] / 2
            below = by < H * 0.55                     # 상자가 위쪽이면 아래에서 올라오고, 아래쪽이면 위에서 내려온다
            to = [bx, box[1] + box[3] + gap] if below else [bx, box[1] - gap]
        if not fr:
            up = to[1] < H * 0.55
            fx = to[0] + (W / 2 - to[0]) * 0.55 + (-1 if to[0] > W / 2 else 1) * W * 0.06
            fr = [fx, to[1] + H * 0.16 * (1 if up else -1)]
        lab = None
        if text:        # 글자를 꼬리에 두고, 화살표는 글자 상자 가장자리에서 출발
            lab_at = (fr[0], fr[1])
            _, lab = _label_steps(text, fr[0], fr[1], me, tsize, s, color, hand, W, H, 0)
            lx, ly, lw, lh = lab
            fr = [lx + lw / 2, ly - gap * 0.6] if to[1] < ly else [lx + lw / 2, ly + lh + gap * 0.6]
        bend = (0.22 if fr[0] < to[0] else -0.22) * (1 if to[1] < fr[1] else -1)
        i = len(steps)
        steps += [{"command": "path.create", "params": _arrow_path(fr, to, bend)},
                  {"command": "paint.setFill", "params": {"id": f"${i}.id", "none": True}},
                  {"command": "paint.setStroke", "params": {"id": f"${i}.id", "color": color}},
                  {"command": "stroke.set", "params": {"id": f"${i}.id", "weight": (13 if hand else 9) * s, "cap": "round", "join": "round",
                                                       "endArrow": "Arrow" if hand else "Triangle", "arrowAlign": "tip",
                                                       "profile": "taperStart" if hand else "uniform"}}]
        if hand:
            steps.append({"command": "effect.apply", "params": {"id": f"${i}.id", "effect": "distort.roughen",
                                                                "params": {"size": 0.3, "detail": 3, "points": "smooth", "seed": k + 7}}})
        else:
            steps.append({"command": "effect.apply", "params": {"id": f"${i}.id", "effect": "stylize.dropShadow",
                                                                "params": {"x": 0, "y": 2 * s, "blur": 6 * s, "opacity": 30}}})
        if lab:     # 글자는 화살표 위에 그린다(단계 번호가 맞도록 여기서 만든다)
            st, _ = _label_steps(text, lab_at[0], lab_at[1], me, tsize, s, color, hand, W, H, len(steps))
            steps += st

    # 2) 레이어마다 내보내기: 그 레이어만 보이게 → 투명 PNG(대상과 같은 크기)
    layers_dir = work / f"{oid}.layers"
    shutil.rmtree(layers_dir, ignore_errors=True)
    layers_dir.mkdir(parents=True)
    ids = [f"${i}.id" for i in layer_idx]
    full = []
    if ref:
        steps.append({"command": "layer.setProps", "params": {"id": 1, "visible": False}})
    for k, lid in enumerate(ids):
        for j, other in enumerate(ids):
            steps.append({"command": "layer.setProps", "params": {"id": other, "visible": j == k}})
        f = layers_dir / f"{k + 1:02d}.full.png"
        full.append(f)
        steps.append({"command": "file.export", "params": {"path": str(f), "format": "png", "background": "transparent"}})
    for other in ids:
        steps.append({"command": "layer.setProps", "params": {"id": other, "visible": True}})
    steps.append({"command": "file.export", "params": {"path": str(out), "format": "png", "background": "transparent"}})   # 마크 전체(투명)
    if ref:
        steps.append({"command": "layer.setProps", "params": {"id": 1, "visible": True}})
    keep = out.with_suffix(".vectorcraft")
    _vc(steps, work, oid, exports=[keep])

    # 3) 내용만 잘라 box(0~1) 기록 — 움직임 단계가 대상 사각형 위 같은 자리에 등장시킨다
    layers = []
    for k, (mk, f) in enumerate(zip(marks, full)):
        if not f.exists():
            raise RuntimeError(f"overlay 레이어 {k + 1} 을 내보내지 못했습니다")
        with Image.open(f) as im:
            im = im.convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if not bb:
                raise RuntimeError(f"overlay 레이어 {k + 1}({mk.get('kind')})이 비어 있습니다 — box 가 화면 밖인지 확인")
            p = max(2, int(4 * s))
            bb = (max(0, bb[0] - p), max(0, bb[1] - p), min(W, bb[2] + p), min(H, bb[3] + p))
            cf = layers_dir / f"{k + 1:02d}.png"
            im.crop(bb).save(cf)
        f.unlink(missing_ok=True)
        layers.append({"file": _rel(cf), "box": [round(bb[0] / W, 5), round(bb[1] / H, 5), round((bb[2] - bb[0]) / W, 5), round((bb[3] - bb[1]) / H, 5)],
                       "cue": mk.get("cue") or None, "kind": mk.get("kind") or "box"})
    return {"app": "vectorcraft", "target": m["target"], "target_file": trec.get("file"),
            "width": W, "height": H, "layers": layers, "style": "hand" if hand else "clean",
            "editable": _rel(keep)}


# ---------------------------------------------------------------- template_card
def _read_rows(m: dict, work: Path) -> tuple[Path, list[str], list[dict]]:
    """CSV(또는 values 한 줄) → (CSV 파일, 머리글, 행들). name 열이 없으면 card1, card2 … 를 붙인 사본을 쓴다"""
    from ..materials import _abs
    if isinstance(m.get("values"), dict) and m["values"]:
        rows = [{"name": "card1", **{str(k): str(v) for k, v in m["values"].items()}}]
        heads = ["name", *[str(k) for k in m["values"]]]
    elif m.get("csv"):
        src = _abs(m["csv"])
        if not src.exists():
            raise RuntimeError(f"template_card CSV 가 없습니다: {m['csv']}")
        rd = csv.DictReader(io.StringIO(src.read_text("utf-8-sig")))
        heads = list(rd.fieldnames or [])
        rows = [dict(r) for r in rd]
        if "name" not in heads:
            heads = ["name", *heads]
            rows = [{"name": f"card{i + 1}", **r} for i, r in enumerate(rows)]
    else:
        raise RuntimeError("template_card 에 csv 또는 values 가 필요합니다")
    if not rows:
        raise RuntimeError("template_card CSV 에 행이 없습니다")
    f = work / f"{m['id']}.data.csv"
    with f.open("w", encoding="utf-8", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=heads, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return f, heads, rows


def default_template(path: Path, fields: list[str], work: Path) -> Path:
    """기본 틀(960×720, 투명 바탕): 흰 둥근 카드 + 제목(작게) · 값(크게) · 반응 한 줄(색 알약). 변수 = CSV 머리글"""
    W, Hh = 960, 720
    f = list(fields) + [None] * 3
    steps = [{"command": "file.new", "params": {"width": W, "height": Hh, "units": "Pixels"}},
             {"command": "layer.setProps", "params": {"id": 1, "name": "카드"}},
             {"command": "shape.rectangle", "params": {"x": 30, "y": 22, "width": W - 60, "height": Hh - 72, "radius": 56}},
             {"command": "paint.setFill", "params": {"id": "$2.id", "color": "#ffffff"}},
             {"command": "paint.setStroke", "params": {"id": "$2.id", "none": True}},
             {"command": "effect.apply", "params": {"id": "$2.id", "effect": "stylize.dropShadow", "params": {"x": 0, "y": 10, "blur": 24, "opacity": 28}}},
             {"command": "object.setProps", "params": {"id": "$2.id", "name": "카드 바탕"}}]
    binds = []
    if f[0]:        # 제목: 회색 · 작게
        i = len(steps)
        steps += [{"command": "text.create", "params": {"x": W / 2, "y": 190, "text": f[0], "size": 64, "font": FONT, "style": "Bold",
                                                         "color": "#55575e", "justify": "center"}},
                  {"command": "object.setProps", "params": {"id": f"${i}.id", "name": f"제목 ({f[0]})"}}]
        binds.append((f[0], i))
    if f[1]:        # 값: 아주 크게, 카드 넓이에 맞춰 줄인다
        i = len(steps)
        steps += [{"command": "text.create", "params": {"x": 80, "y": 240, "text": f[1], "size": 190, "font": FONT, "style": "Black",
                                                         "color": "#111216", "justify": "center",
                                                         "area": {"width": W - 160, "height": 230, "fit": "shrinkText", "fitMinPercent": 40}}},
                  {"command": "object.setProps", "params": {"id": f"${i}.id", "name": f"값 ({f[1]})"}}]
        binds.append((f[1], i))
    if f[2]:        # 반응 한 줄: 색 알약 위 흰 글자
        i = len(steps)
        steps += [{"command": "shape.rectangle", "params": {"x": 150, "y": 520, "width": W - 300, "height": 110, "radius": 55}},
                  {"command": "paint.setFill", "params": {"id": f"${i}.id", "color": ACCENT}},
                  {"command": "paint.setStroke", "params": {"id": f"${i}.id", "none": True}},
                  {"command": "object.setProps", "params": {"id": f"${i}.id", "name": "반응 알약"}}]
        j = len(steps)
        steps += [{"command": "text.create", "params": {"x": 170, "y": 538, "text": f[2], "size": 54, "font": FONT, "style": "Black",
                                                         "color": "#ffffff", "justify": "center",
                                                         "area": {"width": W - 340, "height": 76, "fit": "shrinkText", "fitMinPercent": 50}}},
                  {"command": "object.setProps", "params": {"id": f"${j}.id", "name": f"반응 ({f[2]})"}}]
        binds.append((f[2], j))
    for name, i in binds:
        steps += [{"command": "variable.define", "params": {"name": name, "kind": "text"}},
                  {"command": "variable.bind", "params": {"variable": name, "ids": [f"${i}.id"]}}]
    path.parent.mkdir(parents=True, exist_ok=True)
    _vc(steps, work, f"{path.stem}.make", exports=[path])
    if not path.exists():
        raise RuntimeError("template_card 기본 틀을 만들지 못했습니다")
    return path


def template_card(m: dict, out: Path, work: Path) -> dict:
    """틀(.vectorcraft) + CSV → action.batch 로 행마다 PNG, 그중 row 번째를 재료로"""
    from ..materials import _abs
    data, heads, rows = _read_rows(m, work)
    fields = [h for h in heads if h != "name"]
    # 행 고르기: 번호 또는 name 값
    row = m.get("row", 0)
    names = [r["name"] for r in rows]
    if isinstance(row, str) and not row.lstrip("-").isdigit():
        if row not in names:
            raise RuntimeError(f"template_card row '{row}' 가 CSV name 열에 없습니다({' · '.join(names[:8])})")
        idx = names.index(row)
    else:
        idx = int(row)
    if not -len(rows) <= idx < len(rows):
        raise RuntimeError(f"template_card row {row} 가 범위 밖입니다(행 {len(rows)}개)")
    tpl_s = m.get("template") or m.get("src")
    tpl = _abs(tpl_s) if tpl_s else None
    made_default = False
    if not tpl or not tpl.exists():
        tpl = default_template(work / f"{m['id']}.template.vectorcraft", fields, work)
        made_default = True
    cards = work / f"{m['id']}.cards"
    shutil.rmtree(cards, ignore_errors=True)
    cards.mkdir(parents=True)
    steps = [{"command": "dataset.import", "params": {"path": str(data.resolve())}},
             {"command": "action.batch", "params": {
                 "source": "datasets", "destination": "folder", "destinationFolder": str(cards.resolve()), "datasetFileNaming": "dataSetName",
                 "commands": [{"command": "document.export", "params": {"path": str((cards / "card.png").resolve()), "format": "png",
                                                                         "background": "transparent"}}]}}]
    res = _vc(steps, work, f"{m['id']}.batch", inp=tpl)
    imp = next((r.get("result") or {} for r in res if r.get("command") == "dataset.import"), {})
    bat = next((r.get("result") or {} for r in res if r.get("command") == "action.batch"), {})
    if bat.get("failed"):
        errs = [p.get("error") for p in bat.get("processed") or [] if p.get("error")]
        raise RuntimeError(f"template_card 일괄 내보내기 실패: {str(errs[:2])[:300]}")
    unbound = list(imp.get("defined") or [])     # 틀에 같은 이름 변수가 없어 새로 생긴 것 = 글자가 바뀌지 않는 머리글
    if fields and len(unbound) >= len(fields):
        raise RuntimeError(f"template_card 틀에 CSV 머리글({' · '.join(fields)})과 같은 이름의 변수가 없습니다(VectorCraft 변수 패널에서 이름을 맞추세요)")
    import re as _re
    pngs = sorted(cards.glob("*.png"), key=lambda p: [int(t) if t.isdigit() else t for t in _re.split(r"(\d+)", p.stem)])
    if names and len(pngs) == len(rows) and not (cards / f"{names[0]}.png").exists():
        # VectorCraft 버전마다 일괄 내보내기 파일 이름이 다르다(v0.21 = 행 이름, v0.22 = 'Data Set 1') → 내보낸 순서대로 행 이름을 붙인다
        for p_, nm in zip(pngs, names):
            p_.rename(cards / f"{nm}.png")
        pngs = [cards / f"{nm}.png" for nm in names]
    want = cards / f"{names[idx]}.png"
    pick = want if want.exists() else (pngs[idx] if len(pngs) == len(rows) else None)
    if not pick or not pick.exists():
        raise RuntimeError(f"template_card 카드 PNG 를 찾지 못했습니다(나온 파일 {len(pngs)}개)")
    shutil.copyfile(pick, out)
    from PIL import Image
    with Image.open(out) as im:
        size = [im.width, im.height]
    info = {"app": "vectorcraft", "as": "image", "width": size[0], "height": size[1], "row": names[idx],
            "values": {k: rows[idx].get(k, "") for k in fields}, "cards": _rel(cards), "editable": _rel(tpl)}
    if made_default:
        info["default_template"] = True
    if unbound:     # 틀에 없는 머리글 — 글자가 바뀌지 않는다
        info["unbound"] = unbound
    return info


ADAPTERS = {"overlay": overlay, "template_card": template_card}
