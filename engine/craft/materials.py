"""Craft 파이프라인 — 재료 단계(범용): 콘티 장면의 재료 요청 → 그 일을 하는 Craft 툴 → 같은 형식의 재료 파일.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 (재료 디스패처). 쿠르츠게작트 같은 특정 화풍에 묶이지 않는다.
장면에는 툴 이름 없이 '무엇이 필요한가'만 적는다:

  "materials": [
    { "id": "m1", "type": "chart", "kind": "bar", "labels": ["실재", "가짜"], "values": [80.3, 19.7], "title": "추천 패키지", "cue": "5개" },
    { "id": "m2", "type": "doc_quote", "pdf": "data/research/x.pdf", "find": "hallucinated packages", "cue": "논문" },
    { "id": "m3", "type": "illustration", "src": "data/compositions/<id>/craft/art/hacker.svg", "place": "left" },
    { "id": "m4", "type": "photo", "src": "data/public/uploads/<id>/a.jpg", "cutout": true },
    { "id": "m5", "type": "screen", "src": "data/public/web/<id>/x.mp4" }
  ]

어느 툴이 만들지는 engine/craft/apps/<앱>/craft.json 의 provides(능력 목록)로 정한다. 새 툴은 능력 한 줄 + 어댑터 함수 하나.
결과: data/compositions/<id>/craft/materials/s<NN>/<재료 id>.png (+ .json: 종류 · 크기 · 강조 사각형 · 만든 앱)
움직임 단계(motion.py)는 어떤 툴이 만든 재료든 같은 방식으로 배치 · 등장 · 확대한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- 능력 목록
def _crafts():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fluma_crafts", ROOT / "engine" / "craft" / "crafts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def registry() -> dict[str, str]:
    """재료 종류 → 기본 앱 이름 (설치된 앱 먼저) — 여러 앱이 같은 재료를 만들 수 있으면 methods() 가 전부를 준다"""
    return {t: apps[0] for t, apps in methods().items()}


def methods() -> dict[str, list[str]]:
    """재료 종류 → 그 재료를 만들 수 있는 앱들(설치된 앱 먼저). 같은 재료를 다른 앱 · 다른 방법으로 만들 수 있게
    (예: chart = gridcraft 계산 + 움직임 단계가 그림 · deckcraft 차트 엔진). 고르는 법: 재료 method > direction.methods > 첫 번째"""
    out: dict[str, list[str]] = {}
    cs = [json.loads(f.read_text("utf-8")) for f in sorted((ROOT / "engine" / "craft" / "apps").glob("*/craft.json"))]
    cs.sort(key=lambda c: not (ROOT / "tools" / "crafts" / c["name"] / "installed.json").exists())
    alt: dict[str, list[str]] = {}
    for c in cs:
        for p in c.get("provides") or []:
            dst = alt if p.get("alt") else out          # alt: 다른 방법(기본 뒤에) — 예: deckcraft 의 chart
            dst.setdefault(p["material"], [])
            if c["name"] not in dst[p["material"]]:
                dst[p["material"]].append(c["name"])
    for t, apps in alt.items():
        out.setdefault(t, []).extend(a for a in apps if a not in out[t])
    return out

def cli(app: str) -> str:
    f = ROOT / "tools" / "crafts" / app / "installed.json"
    if not f.exists() and not _crafts().ensure(app):          # 없으면 그 자리에서 설치
        raise RuntimeError(f"Craft 앱 {app} 을 설치하지 못했습니다(이 컴퓨터용 릴리스 · 네트워크 확인: python3 engine/craft/crafts.py install {app})")
    rel = json.loads(f.read_text("utf-8"))["cli"]
    return str(ROOT / rel)


def _run(args: list, cwd: Path, timeout: int = 300, env: dict | None = None) -> str:
    """앱 CLI 한 번. env: 더 넘길 환경 변수(예: WORDCRAFT_REGION)"""
    r = subprocess.run([str(a) for a in args], cwd=str(cwd), text=True, capture_output=True, timeout=timeout,
                       env={**os.environ, "DO_NOT_TRACK": "1", "SOUNDCRAFT_NO_PREFS": "1", **(env or {})})
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(args[0])).name} 실패: {(r.stderr or r.stdout)[-500:]}")
    return r.stdout


# 재료 파일을 바꾸지 않는 칸(화면에 놓는 방법뿐) — 바꿔도 재료를 다시 만들지 않는다
PLACEMENT_ONLY = ("adjust", "cue", "enter", "note", "why")

def _hash(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""


def _load(p: Path) -> dict:
    try:
        r = json.loads(p.read_text("utf-8"))
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def _abs(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


# ---------------------------------------------------------------- 어댑터 (재료 종류마다 하나)
def chart(m: dict, out: Path, work: Path) -> dict:
    """GridCraft: 데이터를 맞게 다룬다 — CSV/XLSX 읽기, 수식 계산(비율 등). 그림은 움직임 단계(EffectCraft)가 화풍 팔레트로 그린다
    (엑셀 기본 차트 그림은 쇼츠 화풍과 안 맞고 한글이 깨져서 쓰지 않는다)"""
    labels, values = list(m.get("labels") or []), list(m.get("values") or [])
    src = m.get("csv") or m.get("xlsx")
    if src:
        rng = m.get("range", "A1:B20")
        text = _run([cli("gridcraft"), "cat", _abs(src), "--range", rng, "--csv"], work)
        rows = [r.split(",") for r in text.strip().splitlines()[1:] if r.strip()]
        labels = [r[0] for r in rows]
        values = [float(r[1]) for r in rows if len(r) > 1 and r[1].strip()]
    if m.get("percent") and values:
        # 비율은 GridCraft 수식으로 계산(손 계산 금지 — 숫자 근거를 엔진이 검증)
        tmp = work / f"{m['id']}.csv"
        tmp.write_text("v\n" + "\n".join(str(v) for v in values) + "\n", "utf-8")
        n = len(values)
        values = [round(float(_run([cli("gridcraft"), "eval", f"=A{k + 2}/SUM(A2:A{n + 1})*100", "--in", tmp], work).strip()), 1) for k in range(n)]
    data = {"labels": labels, "values": values, "kind": m.get("kind", "bar"), "unit": m.get("unit", "%" if m.get("percent") else ""), "title": m.get("title", "")}
    # 항목 아이콘(Lucide, ISC): 콘티 icons(이름 · false) > 항목 이름에 맞는 일반 아이콘 — 막대만 있으면 밋밋하다(2026-11-04)
    if m.get("icons") is not False:
        import importlib.util
        spec = importlib.util.spec_from_file_location("fluma_icons", ROOT / "engine" / "capture" / "icons.py")
        ic = importlib.util.module_from_spec(spec); spec.loader.exec_module(ic)
        given = list(m.get("icons") or [])
        files = []
        for k, lab in enumerate(labels):
            name = given[k] if k < len(given) and given[k] else ic.concept(str(lab))
            svg = ic.lucide(name) if name else None
            png = out.parent / f"{m['id']}.icon{k}.png"
            if svg:
                try:
                    _run([cli("vectorcraft"), "convert", svg, png, "--scale", "8"], work)
                except Exception:  # noqa: BLE001  아이콘이 없어도 차트는 그린다
                    svg = None
            files.append(str(png.relative_to(ROOT)) if svg and png.exists() else None)
        if any(files):
            data["icons"] = files
    out.with_suffix(".data.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return {"app": "gridcraft", "data": data}


def doc_quote(m: dict, out: Path, work: Path) -> dict:
    """PdfCraft: 문장 찾기 → 그 페이지 렌더. 강조 사각형(픽셀)을 함께 낸다 — 형광펜 · 확대는 움직임 단계가"""
    pdf = _abs(m["pdf"])
    steps = [{"tool": "doc_open", "args": {"path": str(pdf)}},
             {"tool": "text_find", "args": {"doc": 1, "query": m["find"], "limit": 1}}]
    sp = work / f"{m['id']}.steps.json"
    sp.write_text(json.dumps(steps), "utf-8")
    rep = json.loads(_run([cli("pdfcraft"), "run", "--script", sp, "--report", "--root", pdf.parent], work))
    found = _first_match(rep)
    if not found:
        raise RuntimeError(f"PDF 에서 '{m['find']}' 를 찾지 못했습니다")
    page, rects = found
    dpi = int(m.get("dpi", 200))
    _run([cli("pdfcraft"), "render", pdf, "--page", page, "--dpi", dpi, "--out", out], work)
    k = dpi / 72.0
    return {"app": "pdfcraft", "page": page, "highlight": [[r[0] * k, r[1] * k, r[2] * k, r[3] * k] for r in rects]}


def _first_match(rep) -> tuple[int, list] | None:
    """--report 의 text_find 결과에서 첫 일치의 페이지와 줄 사각형 [x, y, w, h](pt)"""
    def walk(o):
        if isinstance(o, dict):
            if "page" in o and ("rects" in o or "lines" in o or "rect" in o):
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    for hit in walk(rep):
        raw = hit.get("rects") or hit.get("lines") or [hit.get("rect")]
        rects = []
        for r in raw:
            r = r.get("rect", r) if isinstance(r, dict) else r
            if isinstance(r, dict):
                x, y = r.get("x", r.get("left", 0)), r.get("y", r.get("top", 0))
                w = r.get("w", r.get("width", r.get("right", 0) - x)); h = r.get("h", r.get("height", r.get("bottom", 0) - y))
                rects.append([x, y, w, h])
            elif isinstance(r, list) and len(r) == 4:
                x0, y0, x1, y1 = r                       # PdfCraft: [왼쪽, 위, 오른쪽, 아래](pt, 왼쪽 위 원점)
                rects.append([x0, y0, x1 - x0, y1 - y0])
        if rects:
            return int(hit["page"]), rects
    return None


def illustration(m: dict, out: Path, work: Path) -> dict:
    """VectorCraft: 에이전트가 그린(또는 사용자) 벡터 → PNG. 편집 파일(.vectorcraft)도 남긴다.
    사람이 VectorCraft 에서 편집 파일을 고쳤으면(만들 때 해시와 다름) 그 파일을 원본으로 쓴다"""
    src = _abs(m["src"])
    keep = out.with_suffix(".vectorcraft")
    old = _load(out.with_suffix(".json"))
    if keep.exists() and old.get("editable_hash") and _hash(keep) != old["editable_hash"]:
        svg = work / f"{m['id']}.edited.svg"
        _run([cli("vectorcraft"), "convert", keep, svg], work)
        src = svg
    scale = m.get("scale") or (40 if m.get("type") == "icon" else 2)    # 아이콘 SVG 는 24px 짜리라 크게 변환해야 흐리지 않다
    _run([cli("vectorcraft"), "convert", src, out, "--scale", str(scale)], work)
    if not src.name.endswith(".edited.svg"):
        _run([cli("vectorcraft"), "convert", src, keep], work)
    info = {"app": "vectorcraft", "editable": str(keep.relative_to(ROOT)), "editable_hash": _hash(keep)}
    if src.suffix == ".svg":
        # 이름 붙은 그룹이 있으면 부품 레이어 + 뼈대로 나눈다 → 움직임 단계가 관절로 움직인다
        from craft.rig import split
        rd = out.parent / f"{m['id']}.rig"
        rig = split(src, rd, lambda a, b: _run([cli("vectorcraft"), "convert", a, b, "--scale", "1"], work))
        if rig:
            info["rig"] = str(rd.relative_to(ROOT))
    return info


def photo(m: dict, out: Path, work: Path) -> dict:
    """PhotoCraft: 사진 정리 · 누끼(피사체 선택 → 마스크). 보통은 adapters/photocraft.py 가 덮어쓴다(장면 카드 · 로고 지우기 …) —
    이것은 그 모듈을 못 불러올 때의 최소 길. PhotoCraft run 은 입력을 위치 인자로 받는다(--in 은 없음)"""
    src = _abs(m["src"])
    cmds = ["select.subject", "layer.layerMask.revealSelection", "select.deselect"] if m.get("cutout") else []
    args = [cli("photocraft"), "run", src]
    for c in cmds:
        args += ["--cmd", c]
    args += ["--out", out]
    _run(args, work)
    return {"app": "photocraft", "cutout": bool(m.get("cutout"))}


def read_text_boxes(f: Path) -> list[dict]:
    """[{text, box:[x, y, w, h](0~1)}] — 글자 인식이 없으면(가벼운 설치) 빈 목록"""
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
        import ocr
        return [{"text": o["text"], "box": o["box"]} for o in ocr.read(f)][:80]
    except Exception as e:   # noqa: BLE001 — 글자 인식은 보조: 실패해도 재료는 쓴다
        print(f"[재료] 글자 인식 건너뜀({f.name}): {e}")
        return []


def find_upload(sid: str, m: dict) -> Path | None:
    """사용자가 올린 파일 중 이 재료의 것: 정확한 경로가 없으면 data/public/uploads/<id>/ 에서 이름에 재료 id 가 든 최신 파일"""
    if m.get("src") and _abs(m["src"]).exists():
        return _abs(m["src"])
    up = ROOT / "data" / "public" / "uploads" / sid
    if not up.exists():
        return None
    want = (".mp4", ".mov", ".webm", ".mkv", ".m4v") if m.get("type") in ("screen", "video") else (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm")
    key = str(m.get("id") or "").lower()
    hits = [f for f in up.iterdir() if f.is_file() and f.suffix.lower() in want and key and key in f.stem.lower()]
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def element_video(el: Path, dst: Path, hold: float | list = 1.2, crop: list | None = None) -> bool:
    """도구가 만든 요소 폴더(data/public/elements/<id>/<이름>/) → 영상 하나.
    짤(meme.py): f0001.png … (meta.fps) · 웹 녹화(webrec.py): 상태 화면 s000.png … 을 hold 초씩 + 실제 녹화 구간 r01/f*.jpg"""
    meta = _load(el / "meta.json")
    frames = sorted(el.glob("f[0-9]*.png"))
    states = sorted(el.glob("s[0-9][0-9][0-9].png"))
    cx, cy_, cw, ch = (crop or [0, 0, 1, 1])
    cf = f"crop=iw*{cw}:ih*{ch}:iw*{cx}:ih*{cy_}," if crop else ""
    enc = ["-vf", f"{cf}scale='min(1440,iw)':-2,tpad=stop_mode=clone:stop_duration=20,format=yuv420p", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)]
    if len(frames) > 1:
        cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(meta.get("fps", 15)), "-i", str(el / "f%04d.png"), *enc]
    elif frames or states:
        # 정지 화면 목록 → hold 초씩 이어 붙이기(실제 녹화 구간이 있으면 그 상태 다음에)
        lst = work_list = el / ".concat.txt"
        rows = []
        seq = states or frames
        if any(el.glob("r[0-9][0-9]")):
            # 실제 녹화 구간(JPG)과 상태 화면(PNG)을 한 줄로 이으면 ffmpeg concat 이 형식이 달라 실패한다 → 상태 화면도 JPG 로
            from PIL import Image
            jd = el / ".jpg"; jd.mkdir(exist_ok=True)
            conv = []
            for s0 in seq:
                j = jd / (s0.stem + ".jpg")
                if not j.exists() or j.stat().st_mtime < s0.stat().st_mtime:
                    Image.open(s0).convert("RGB").save(j, quality=95)
                conv.append(j)
            seq = conv
        for i, s in enumerate(seq):
            h = (hold[i] if i < len(hold) else hold[-1]) if isinstance(hold, list) else hold    # holds: 상태마다 머무는 초(말풍선마다 다르게)
            rows += [f"file '{s.as_posix()}'", f"duration {h}"]
            rec = el / f"r{i + 1:02d}"
            for f in sorted(rec.glob("f*.jpg"))[::1] if rec.exists() else []:
                rows += [f"file '{f.as_posix()}'", "duration 0.0333"]
        rows.append(rows[-2])        # concat 규칙: 마지막 파일을 한 번 더
        work_list.write_text("\n".join(rows) + "\n", "utf-8")
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-fps_mode", "cfr", "-r", "30", *enc]
    else:
        return False
    r = subprocess.run(cmd, capture_output=True, text=True)
    (el / ".concat.txt").unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"[재료] {el.name} 영상 만들기 실패: {r.stderr[-300:]}")
    return r.returncode == 0


def content_box(el: Path, pad: float = 0.03) -> list | None:
    """웹 녹화 · 화면 녹화 요소 폴더에서 '내용이 있는 곳'(배경과 다른 픽셀)을 모든 상태 화면에 걸쳐 잰다 → crop [x, y, w, h] 0~1.
    2026-11-09 git 영상: 세로 페이지 위쪽에 터미널만 있고 아래 2/3 가 빈 검정이라 화면이 비고 글씨가 작았다 → 내용만 잘라 화면에 크게.
    배경이 화면의 80% 이상 내용이면(이미 꽉 참) None"""
    import numpy as np
    from PIL import Image
    shots = sorted(el.glob("s[0-9][0-9][0-9].png")) or sorted(el.glob("f[0-9]*.png"))[::10]
    for rec in sorted(el.glob("r[0-9][0-9]")):
        shots += sorted(rec.glob("f*.jpg"))[::15]
    box = None
    for f in shots[:60]:
        a = np.asarray(Image.open(f).convert("RGB").resize((270, 480)), dtype=np.int16)
        edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        bg = np.median(edge, axis=0)
        mask = np.abs(a - bg).sum(axis=2) > 40
        ys, xs = np.where(mask)
        if len(xs) < 50:
            continue
        b = [xs.min() / 270, ys.min() / 480, (xs.max() + 1) / 270, (ys.max() + 1) / 480]
        box = b if box is None else [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
    if not box:
        return None
    x0, y0, x1, y1 = max(0.0, box[0] - pad), max(0.0, box[1] - pad), min(1.0, box[2] + pad), min(1.0, box[3] + pad)
    if (x1 - x0) * (y1 - y0) > 0.8:
        return None
    return [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)]


def quick_blank_states(el: Path, holds: list | float, n_states: int) -> list | float:
    """앞쪽의 거의 빈 상태 화면(빈 프롬프트 '$ git' 만 있는 것)은 0.3초만 — 매 장면이 빈 화면 타이핑부터 시작하지 않게(L32 첫 1초)"""
    import numpy as np
    from PIL import Image
    states = sorted(el.glob("s[0-9][0-9][0-9].png"))
    if len(states) < 2:
        return holds
    def ink(f):
        a = np.asarray(Image.open(f).convert("L").resize((135, 240)), dtype=np.int16)
        bg = np.median(np.concatenate([a[0], a[-1]]))
        return float((np.abs(a - bg) > 30).mean())
    last = ink(states[-1]) or 1e-6
    hs = list(holds) if isinstance(holds, list) else [float(holds)] * len(states)
    hs += [hs[-1]] * (len(states) - len(hs))
    for i, f in enumerate(states[:-1]):
        if ink(f) < 0.15 * last:
            hs[i] = min(hs[i], 0.3)
        else:
            break
    return hs


def passthrough(m: dict, out: Path, work: Path) -> dict:
    """이미 만들어진 재료(웹 녹화 · 사용자 영상 · 이미지 · 짤)는 그대로 쓴다"""
    src = _abs(m["src"])
    if src.is_dir():                       # 짤 · 웹 녹화 요소 폴더
        hold = float(m.get("hold", 1.2))
        holds = [float(x) for x in m["holds"]] if m.get("holds") else None
        crop = m.get("crop")
        if crop is None and m.get("type") in ("web", "screen") and m.get("fit") != "full":
            crop = content_box(src)                                   # 내용이 있는 곳만(빈 여백 · 작은 글씨 방지) — crop: false 면 끔
        if m.get("type") in ("web", "screen") and m.get("quick_start", True):
            holds = quick_blank_states(src, holds or hold, len(list(src.glob("s[0-9][0-9][0-9].png"))))
            holds = holds if isinstance(holds, list) else None
        if element_video(src, out.with_suffix(".mp4"), holds or hold, crop or None):   # crop: [x, y, w, h] 0~1 (쿠키 안내 · 빈 곳 잘라내기)
            meta = _load(src / "meta.json")
            hl = {}
            if meta.get("marks") and not m.get("highlight_box"):        # 터미널 강조 줄 → 그 줄로 다가가기(잘라 낸 화면 기준 좌표 · 줄이 다 찍힌 시각)
                cx, cy, cw, ch = crop or [0, 0, 1, 1]
                bs = [[(x - cx) / cw, (y - cy) / ch, w / cw, h / ch] for x, y, w, h in meta["marks"]]
                x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
                x1, y1 = max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs)
                h0 = (holds[0] if isinstance(holds, list) and holds else hold)
                rec_sec = sum(float(a_.get("sec") or 0) for a_ in meta.get("actions") or [] if a_.get("do") == "record")
                hl = {"highlight_box": [round(max(0, x0), 4), round(max(0, y0), 4), round(min(1, x1) - max(0, x0), 4), round(min(1, y1) - max(0, y0), 4)],
                      "highlight_t": round(h0 + rec_sec, 2)}
            at = lambda k: sum((holds[i] if i < len(holds) else holds[-1]) for i in range(k)) if holds else hold * k   # k 번째 상태가 보이기 시작하는 초
            # 웹 녹화 단계(동작 → 그 결과 상태가 보이는 시각): 움직임 단계가 '1. 주소 입력' 꼬리표를 띄운다
            steps = [{"t": round(at(int(a.get("to", 0))) - 0.15, 2), "t_end": round(at(int(a.get("to", 0)) + 1), 2), "label": a.get("label")}
                     for a in meta.get("actions") or [] if a.get("label")]
            return {"app": None, "file_suffix": ".mp4", "source": meta.get("source") or meta.get("sources"), "steps": steps, "mobile": bool(meta.get("mobile")), **hl}
        raise RuntimeError(f"요소 폴더에 프레임이 없습니다: {m['src']}")
    if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v") and m.get("_clip"):
        return video_span(m, src, out)
    if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        # 영상: 마지막 프레임을 20초 늘린다(장면보다 짧은 녹화가 끝나면 화면이 비지 않게) · 소리는 뺀다(나레이션과 겹침)
        dst = out.with_suffix(".mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "tpad=stop_mode=clone:stop_duration=20,format=yuv420p",
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)], capture_output=True, text=True)
        if r.returncode == 0:
            return {"app": None, "file_suffix": ".mp4"}
    out.with_suffix(src.suffix).write_bytes(src.read_bytes())
    return {"app": None, "file_suffix": src.suffix}


def video_span(m: dict, src: Path, out: Path) -> dict:
    """구간을 정한 영상: 쓸 구간(in · out) → 화면 비율로 채우기(fit cover) → 장면보다 짧으면
    end: slow(1.25배까지 늦춤 · 기본) | loop | freeze. 끝에는 늘 마지막 프레임 여유(움직임 단계가 장면 끝까지 읽음). 소리는 뺀다(대사는 음성 단계가 넣음)"""
    from . import vclip
    dur = vclip.probe(src)["dur"]
    a, b = vclip.span(m, dur)
    length, sec = b - a, float(m.get("_sec") or 0)
    W, H = int(m["_W"]), int(m["_H"])
    fit = m.get("fit") or "contain"
    end = m.get("end") or "slow"
    vf = [f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}" if fit == "cover" else f"scale='min({W},iw)':-2"]
    pre, k = [], 1.0
    # 장면보다 긴 클립: 그냥 자르면 끝(생성 클립의 end_state — 화면 속으로 들어가는 순간)이 잘려 나간다(2026-11-09: 6초 클립을 3초 장면에 넣어 움직임 중간에 툭 끊김)
    # → 1.25배까지만 빠르게(그 이상은 움직임이 정신없어 AI 티가 난다 — 2026-11-09 2배로 돌려 망침), 그래도 길면 앞을 잘라 끝을 지킨다(생성 클립 기본 · keep: "start" 면 앞부분)
    if sec and length > sec + 0.05 and m.get("keep", "start") == "end":
        k = max(0.8, sec / length)
        if length * k > sec + 0.05:
            a = b - sec / k
            length = b - a
        vf.append(f"setpts={k:.4f}*PTS")
    elif sec > length + 0.05 and end == "slow":
        k = min(1.25, sec / length)
        vf.append(f"setpts={k:.4f}*PTS")
    elif sec > length + 0.05 and end == "loop":
        pre = ["-stream_loop", "-1"]
    # 끝 여유: 장면을 채우는 만큼 + 1초(예전 20초는 FilmCraft 색 · 줌 단계가 클립마다 20초를 더 처리해 렌더가 6배 느려졌다)
    hold = (max(0.0, sec - length * k) + 1.0) if sec else 20.0
    vf.append(f"tpad=stop_mode=clone:stop_duration={hold:.2f},format=yuv420p")
    dst = out.with_suffix(".mp4")
    args = ["ffmpeg", "-v", "error", "-y", *pre, "-ss", f"{a:.3f}"] + (["-t", f"{max(sec, length):.3f}"] if pre else ["-to", f"{b:.3f}"]) + \
           ["-i", str(src), "-vf", ",".join(vf), "-an", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)]
    if pre:   # 반복: -to 는 입력 기준이라 구간을 먼저 잘라 둔 뒤 반복
        cut = out.with_suffix(".cut.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(cut)], check=True)
        args = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(cut), "-t", f"{sec:.3f}", "-vf", ",".join(vf), "-an", "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"영상 구간 {m.get('id')} 처리 실패: {r.stderr[-300:]}")
    return {"app": None, "file_suffix": ".mp4", "clip": {"in": a, "out": b, "fit": fit, "end": end}}


def stock(m: dict, out: Path, work: Path, sid: str) -> dict:
    """무료 스톡 영상(Pexels · Pixabay, engine/capture/stock.py) → 세로 화면 가득(1080×1920 로 가운데 잘라 맞춤) · 소리 없음 · 끝 프레임 유지.
    출처(credit)는 재료 기록에 남겨 설명란 '사용한 자료' 에 쓴다"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fluma_stock", ROOT / "engine" / "capture" / "stock.py")
    st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
    r = st.fetch(sid, m["id"], str(m.get("query") or m.get("what") or ""), int(m.get("pick", 0)), float(m.get("min_sec", 3)), m.get("provider"))
    dst = out.with_suffix(".mp4")
    import sys as _s
    _s.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
    from engines import aspect_size
    W, H = aspect_size(_load(ROOT / "data" / "storyboards" / f"{sid}.json") or None)
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,tpad=stop_mode=clone:stop_duration=20,format=yuv420p"
    ss = ["-ss", str(float(m["trim"]))] if m.get("trim") else []
    q = subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", r["raw"], "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(dst)], capture_output=True, text=True)
    if q.returncode != 0:
        raise RuntimeError(f"스톡 영상 변환 실패: {q.stderr[-200:]}")
    c = r["credit"]
    return {"app": None, "mobile": True, "credit": c, "source": [c["page"]]}


MAT_VERSION = "12"    # 재료를 만드는 방식이 바뀌면 올린다(열쇠에 들어가 예전 결과를 다시 만든다) — 2: 아이콘 고해상도 · 영상 마지막 프레임 유지 · 요소 폴더 · 3: 차트 항목 아이콘 · 4: 앱별 어댑터 · 5: craft 재료 · 레시피 · 6: 생성 클립 · 7: 재료마다 방법(앱) 고르기 · 8: 느낌(feel) 입히기 · 9: 긴 생성 클립은 빠르게 해 끝을 지킴 · 10: 빠르기 상한 1.25배 · 11: 생성 경로 제거(완전 로컬) · 12: 웹 녹화 내용만 자르기 · 빈 시작 짧게
#                       4: 앱별 어댑터(PhotoCraft 카드 · PdfCraft 진짜 형광펜 · FilmCraft 다듬기 · 새 재료 종류) · 사람이 고친 편집 파일 열쇠 일반화
ADAPTERS = {"chart": chart, "doc_quote": doc_quote, "illustration": illustration, "photo": photo, "icon": illustration}   # icon: icons.py 로 받은 SVG
PASSTHROUGH = {"screen", "video", "image", "meme", "web"}    # meme: meme.py fetch 폴더 · web: webrec.py 폴더
FEEL_TYPES = {"video", "stock", "photo", "image", "photo_grade"}   # 영상 느낌(direction.feel)을 입히는 실사 재료 — feel.py 와 같게


def _editable(old: dict, d: Path) -> Path | None:
    """예전 기록의 편집 파일(.psd · .fcproj · .sc · .dxf · .vectorcraft …) — 저장소 기준 상대 경로, 아니면 재료 폴더 기준"""
    e = old.get("editable")
    if not isinstance(e, str) or not e:
        return None
    q = Path(e)
    if q.is_absolute():
        return q
    return ROOT / q if (ROOT / q).exists() or not (d / q).exists() else d / q


def _depends(t: str, m: dict) -> str | None:
    """같은 장면의 다른 재료를 읽어 만드는 재료 → 그 재료 id (overlay 의 target · drawing 의 model id)"""
    if t == "overlay" and m.get("target"):
        return str(m["target"])
    if t == "drawing" and isinstance(m.get("model"), str) and m["model"]:
        return m["model"]
    return None


def _post(fn, m: dict, file: Path, work: Path, info: dict) -> dict | None:
    """POST 다듬기 — 4번째 인자(passthrough 기록: steps 등)를 받는 함수면 넘긴다"""
    import inspect
    try:
        n = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        n = 3
    return fn(m, file, work, info) if n >= 4 else fn(m, file, work)


def plugins() -> tuple[dict, dict]:
    """앱별 어댑터 꽂기 — engine/craft/adapters/<앱>.py 가 ADAPTERS = {재료 종류: fn(m, out, work) -> info} 와
    (선택) POST = {재료 종류: fn(m, file, work) -> dict | None} 를 내놓는다.
      - ADAPTERS 는 같은 이름의 기본 어댑터를 덮어쓴다. info 에 "file_suffix"(예: ".mp4")가 있으면 그 확장자 파일이 재료다
      - POST 는 그대로 쓰는 재료(screen · video · web …)를 만든 뒤 다듬는다 — 돌려준 dict 의 "file"(Path)이 있으면 그 파일로 바뀐다
    모듈 하나가 불러지지 않아도(앱 미설치 · 오류) 나머지는 쓴다"""
    import importlib
    ad, post = {}, {}
    for f in sorted((Path(__file__).parent / "adapters").glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__package__}.adapters.{f.stem}")
        except Exception as e:  # noqa: BLE001
            print(f"[재료] 어댑터 {f.stem} 을 불러오지 못했습니다: {e}")
            continue
        ad.update(getattr(mod, "ADAPTERS", {}) or {})
        post.update(getattr(mod, "POST", {}) or {})
    return ad, post


def expand_recipe(m: dict) -> dict:
    """"recipe": "<이름>" → 레시피의 craft 재료 + "fill"(바꿀 칸, JSON 포인터 → 값) + 콘티의 나머지 칸(id · cue · place …)"""
    name = m.get("recipe")
    if not name:
        return m
    import copy
    f = ROOT / ".claude" / "skills" / "crafts" / "recipes" / f"{name}.json"
    if not f.exists():
        raise RuntimeError(f"레시피 {name} 이 없습니다 — python3 engine/craft/craft_variety.py list")
    mat = copy.deepcopy(json.loads(f.read_text("utf-8"))["material"])
    for ptr, val in (m.get("fill") or {}).items():
        keys = [k for k in str(ptr).split("/") if k != ""]
        cur = mat
        try:
            for k in keys[:-1]:
                cur = cur[int(k)] if isinstance(cur, list) else cur[k]
            last = keys[-1]
            if isinstance(cur, list):
                cur[int(last)] = val
            else:
                cur[last] = val
        except (KeyError, IndexError, ValueError, TypeError):
            raise RuntimeError(f"레시피 {name} 에 {ptr} 칸이 없습니다(레시피 slots 의 at 을 쓰세요)")
    rest = {k: v for k, v in m.items() if k not in ("recipe", "fill", "type")}
    return {**mat, **rest, "type": "craft", "recipe": name}


def _files_in(o) -> list[Path]:
    """재료 칸 안의 저장소 파일 경로(문자열) — craft 재료의 입력이 바뀌면 다시 만들려고"""
    out = []
    if isinstance(o, dict):
        for v in o.values():
            out += _files_in(v)
    elif isinstance(o, list):
        for v in o:
            out += _files_in(v)
    elif isinstance(o, str) and len(o) < 400 and "/" in o and not o.startswith("$"):
        q = _abs(o)
        try:
            if q.is_file() and ROOT in q.resolve().parents:
                out.append(q)
        except OSError:
            pass
    return out


# ---------------------------------------------------------------- 디스패처
def build(sb: dict, indices: list[int] | None = None) -> list[dict]:
    """콘티의 모든 재료를 만든다(입력이 같으면 다시 만들지 않음) → 재료 목록.
    indices: 장면 일부만 렌더할 때 각 장면의 원래 번호(0부터) — 재료 폴더 s<NN> 이 원래 번호와 맞게"""
    sid = sb["id"]
    reg = registry()
    plug, post = plugins()
    adapters = {**ADAPTERS, **plug}
    from . import usage
    usage.SID = sid
    base = ROOT / "data" / "compositions" / sid / "craft" / "materials"
    made = []
    scs = sb.get("scenes") or []
    nums = [i + 1 for i in indices] if indices else list(range(1, len(scs) + 1))
    if not indices and base.exists():   # 전체 빌드: 콘티에 없는 장면 폴더(장면이 줄었을 때)는 지운다
        for d in base.glob("s[0-9][0-9]"):
            if int(d.name[1:]) > len(scs):
                import shutil
                shutil.rmtree(d, ignore_errors=True)
    for n, sc in zip(nums, scs):
        # 콘티에서 빠진 재료(기록 · 파일 · 뼈대)는 지운다 — 남겨 두면 움직임 단계가 지운 재료까지 그린다
        d0 = base / f"s{n:02d}"
        keep = {str(m.get("id") or f"m{i + 1}") for i, m in enumerate(sc.get("materials") or [])}
        if d0.exists():
            for f in list(d0.iterdir()):
                stem = f.name.split(".")[0]
                owner, _, part = stem.rpartition("_")
                if stem and stem not in keep and not (owner in keep and (part in ("base", "jaw", "mouth") or (len(part) == 4 and part[0] == "f" and part[1:].isdigit()))):   # 유물 재료의 레이어 그림은 그 재료의 것
                    if f.is_dir():
                        import shutil
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        f.unlink(missing_ok=True)
        for i, m in enumerate(sc.get("materials") or []):
            m = expand_recipe({"id": m.get("id") or f"m{i + 1}", **m})
            t = m.get("type")
            rq = (sb.get("direction") or {}).get("render_quality")
            if rq and m.get("method") == "blender" and not m.get("quality"):     # 영상 전체 품질 단계 — 재료 열쇠에 들어가 바뀌면 다시 만든다
                m = {**m, "quality": rq}
            dm = ((sb.get("direction") or {}).get("methods") or {}).get(t)
            if dm and not m.get("method"):           # 방향이 정한 방법(앱)도 재료 칸에 — 바뀌면 열쇠가 달라져 다시 만든다
                m = {**m, "method": dm}
            if t == "video" and any(k in m for k in ("in", "out", "fit", "end")):
                from engines import aspect_size        # 구간 영상: 화면 크기 · 장면 길이에 맞춰 만든다
                _W, _H = aspect_size(sb)
                m = {**m, "_clip": True, "_W": _W, "_H": _H, "_sec": float(sc.get("sec") or 0)}
            d = base / f"s{n:02d}"
            d.mkdir(parents=True, exist_ok=True)
            out = d / f"{m['id']}.png"
            meta_p = d / f"{m['id']}.json"
            # 열쇠 = 요청 + 원본 파일 내용 + 사람이 고친 편집 파일 → 무엇이든 바뀌면 다시 만든다
            srcs = [_hash(_abs(m[k])) if not _abs(m[k]).is_dir() else "|".join(f"{f.name}:{f.stat().st_size}" for f in sorted(_abs(m[k]).iterdir()))
                    for k in ("src", "csv", "xlsx", "pdf", "template", "script", "bridge", "physics", "ui") if isinstance(m.get(k), str)]   # physics: MuJoCo 장면(MJCF) — 바뀌면 다시 계산 · 렌더
            srcs += [_hash(_abs(i[k])) for i in m.get("items") or [] if isinstance(i, dict) for k in ("script", "file") if isinstance(i.get(k), str) and _abs(i[k]).is_file()]   # live 재료의 요소
            srcs += [_hash(_abs(v)) for v in (m.get("bind") or {}).values() if isinstance(v, str) and _abs(v).is_file()]   # physics 재료가 입히는 그림
            old = _load(meta_p)
            # 사람이 고친 편집 파일: 기록의 editable_hash(우리가 만든 그대로의 해시)와 다르면 열쇠에 넣는다 → 다시 만들어 그 파일을 쓴다.
            # editable_hash 를 남기는 어댑터(그림 · 사진 카드 · 화면 다듬기 · 3D · 도면)만 — 고친 파일을 알아보고 덮어쓰지 않는 어댑터들
            ed_p = _editable(old, d)
            ed_now = _hash(ed_p) if ed_p else ""
            hand = bool(old.get("editable_hash") and ed_now and ed_now != old["editable_hash"])
            srcs.append(ed_now if hand else "")
            dep = _depends(t, m)              # 대상 재료(캡처 · 3D)가 바뀌면 주석 · 도면도 다시
            if dep:
                srcs.append(_load(d / f"{dep}.json").get("key") or "missing")
            if isinstance(m.get("uses"), dict):   # 다른 재료의 결과를 쓴다(앱을 넘나든다): Blender 화면 · 표면 등 — 그 재료가 바뀌면 다시
                got = {}
                for name, mid in m["uses"].items():
                    u = _load(d / f"{mid}.json")
                    if not u.get("file"):
                        raise RuntimeError(f"재료 {m['id']}: uses '{name}' 의 재료 {mid} 가 없습니다 — 같은 장면에서 먼저 적는다")
                    srcs.append(u.get("key") or "missing")
                    got[name] = str((ROOT / u["file"]).resolve())
                m = {**m, "_uses": got}
            if t == "craft":                   # craft 재료: 칸 안의 입력 파일 · 레시피 내용이 바뀌면 다시
                srcs += [f"{q.relative_to(ROOT)}:{_hash(q)}" for q in _files_in({k: v for k, v in m.items() if k not in ("src", "csv", "xlsx", "pdf")})]
            if m.get("ask"):                   # 사용자가 올린 파일(이름으로 찾은 것)도 열쇠에 — 새로 올리면 다시 만든다
                up_f = find_upload(sid, m)
                srcs.append(f"{up_f.name}:{_hash(up_f)}" if up_f else "missing")
            feel = ((sb.get("direction") or {}).get("feel") or {}) if t in FEEL_TYPES else {}
            if feel.get("grade"):              # 고른 느낌(engine/story/feel.py)이 바뀌면 실사 재료를 다시 입힌다
                srcs.append(json.dumps(feel["grade"], sort_keys=True))
            if t == "stock":                   # 스톡 영상은 화면 비율대로 잘라 만든다 → 비율이 바뀌면 다시
                from engines import aspect_of
                srcs.append(aspect_of(sb))
            # 열쇠에서 뺀다: adjust(배치 조정 — 움직임 단계가 레이어에 얹음) · cue · enter · place(재료 파일 자체는 같다)
            # 2026-11-10: 크기만 바꿔도 EffectCraft 원테이크 재료를 9초 동안 다시 렌더했다
            mk = {k: v for k, v in m.items() if k not in PLACEMENT_ONLY}
            key = hashlib.sha1(json.dumps([mk, srcs, MAT_VERSION], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            # 예전 열쇠(2026-11-10 전: 모든 칸 포함, adjust 는 없었음)로 만든 재료도 그대로 쓰고 새 열쇠로 옮긴다
            legacy = hashlib.sha1(json.dumps([{k: v for k, v in m.items() if k != "adjust"}, srcs, MAT_VERSION], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            if old.get("key") == legacy and legacy != key and (not old.get("file") or (ROOT / old["file"]).exists()):
                old["key"] = key
                meta_p.write_text(json.dumps(old, ensure_ascii=False, indent=1), "utf-8")
            if old.get("key") == key and (not old.get("file") or (ROOT / old["file"]).exists()):
                # 예전 기록(글자 인식 전)에는 글자 위치가 없다 → 채워 둔다(짚기 · 재료 검사가 쓴다)
                if "ocr" not in old and old.get("file") and t in ("image", "photo", "screen") and Path(old["file"]).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    old["ocr"] = read_text_boxes(ROOT / old["file"])
                    meta_p.write_text(json.dumps(old, ensure_ascii=False, indent=1), "utf-8")
                made.append(old)
                continue
            if t in PASSTHROUGH and m.get("ask") and not find_upload(sid, m):
                # 사용자 녹화 대기: 자동 브라우저로 못 찍는 화면(로그인 · 측정 결과 · 앱)은 사용자에게 부탁한다(검사 L36).
                # 그동안 렌더는 이 재료 없이(장면 핵심어 화면으로) 진행한다
                rec = {"scene": n, "id": m["id"], "type": t, "key": "missing", "spec": m, "file": None, "missing": True, "ask": m["ask"],
                       "upload_hint": f"data/public/uploads/{sid}/ 에 이름에 '{m['id']}' 가 든 파일(예: {m['id']}.mp4)"}
                meta_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
                made.append(rec)
                print(f"[재료] {n}장면 {m['id']}: 사용자 녹화 대기 — {m['ask']}")
                continue
            usage.begin()
            if t in PASSTHROUGH:
                if m.get("ask"):
                    m = {**m, "src": str(find_upload(sid, m).relative_to(ROOT))}
                info = passthrough(m, out, d)
                file = out.with_suffix(info.pop("file_suffix"))
                if t in post:                      # 앱으로 다듬기(화면 녹화 줌 · 흐림 · 빨리 감기 등)
                    extra = _post(post[t], m, file, d, info) or {}
                    file = Path(extra.pop("file", file))
                    info.update(extra)
            elif t == "stock":                     # 무료 스톡 영상(실제 촬영) — 키는 설정 화면
                info = stock(m, out, d, sid)
                file = out.with_suffix(".mp4")
            elif t in adapters or any(k.startswith(f"{t}@") for k in adapters):
                # 같은 재료를 어느 앱으로: 재료 method > direction.methods > 기본(어댑터 '종류@앱' 이 있으면 그 앱의 방법)
                how = m.get("method")
                fn = adapters.get(f"{t}@{how}") if how else None
                if how and not fn and how != reg.get(t):
                    raise RuntimeError(f"'{t}' 재료를 {how} 로 만드는 방법이 없습니다 — 가능한 것: {', '.join([reg.get(t, '?')] + [k.split('@')[1] for k in adapters if k.startswith(t + '@')])}")
                fn = fn or adapters.get(t)
                if fn is None:
                    raise RuntimeError(f"'{t}' 재료의 기본 방법이 없습니다 — method 를 적으세요")
                if fn is ADAPTERS.get(t) and t not in plug and (t if t != "icon" else "illustration") not in reg:
                    raise RuntimeError(f"'{t}' 재료를 만들 Craft 앱이 설치되지 않았습니다(Craft 앱 화면에서 설치)")
                info = fn(m, out, d)
                if how:
                    info.setdefault("method", how)
                suf = info.pop("file_suffix", None)
                file = out.with_suffix(suf) if suf else out
                file = file if file.exists() else None
            elif t == "physics":                   # 물리로 움직이는 2D 요소(MuJoCo) — 결과(위치 · 회전)를 움직임 단계가 레이어 키로 넣는다
                from . import physics as _phys
                scene = (ROOT / str(m.get("physics") or "")).resolve()
                if not m.get("physics") or not scene.is_file() or (ROOT / "data" / "compositions") not in scene.parents:
                    raise RuntimeError(f"physics 재료 {m['id']}: physics 에 data/compositions/<id>/ 안의 장면(.mjcf.xml 또는 .py)을 적으세요")
                res = _phys.simulate(scene, float(m.get("sec") or 4), int(m.get("fps") or 30), {k: v for k, v in (m.get("args") or {}).items() if not isinstance(v, (dict, list))},
                                     m.get("ctrl"), m.get("goals"), poses=m.get("poses"), expect=m.get("expect"))
                file = out.with_suffix(".traj.json")
                file.write_text(json.dumps(res), "utf-8")
                info = {"app": "mujoco", "bodies": len(res["bodies"])}
                print(f"[재료] {n}장면 {m['id']}: 물리 계산(MuJoCo) 물체 {len(res['bodies'])}개 · {res['sec']}초")
            elif t in ("text", "stat"):            # 글자 · 수치 카드는 움직임 단계가 바로 그린다(앱 없음)
                info, file = {"app": None}, None
            else:
                raise RuntimeError(f"모르는 재료 종류: {t} ({' · '.join(sorted({*adapters, *PASSTHROUGH, 'stock', 'text', 'stat', 'physics'}))})")
            if file and feel.get("grade") and file.exists():      # 영상 전체 느낌을 실사 재료에 같은 색 · 질감으로
                from feel import apply as feel_apply
                file = feel_apply(file, feel["grade"], file.with_name(f"{file.stem}.feel{file.suffix}"))
                info["feel"] = feel.get("name")
            rec = {"scene": n, "id": m["id"], "type": t, "key": key, "spec": m, "file": str(file.relative_to(ROOT)) if file else None, **info}
            if m.get("refine") and file:           # 다듬기: 초벌 위에 앱의 전체 명령으로 디테일(engine/craft/refine.py) — 기록은 콘티의 재료 칸
                from .refine import apply_material
                rec = apply_material(rec, m, d)
            feats = usage.take()
            if feats and not rec.get("steps_run"):
                rec["features"] = feats
            if hand:
                # 고친 파일을 썼다 — 기준 해시는 처음 만든 그대로 둔다(다음 빌드도 '사람이 고침'으로 알아보고 덮어쓰지 않게)
                rec["editable_hash"] = old["editable_hash"]
                rec["edited"] = True
                print(f"[재료] {n}장면 {m['id']}: 사람이 고친 편집 파일({ed_p.name})로 다시 만들었습니다")
            # 캡처 · 사진 속 글자 위치(글자 인식) — 움직임 단계가 '말하는 낱말을 화면에서 짚기(확대 · 동그라미)'에 쓴다
            if file and t in ("image", "photo", "screen") and file.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                rec["ocr"] = read_text_boxes(file)
            meta_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
            made.append(rec)
    return made
