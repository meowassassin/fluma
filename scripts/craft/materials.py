"""Craft 파이프라인 — 재료 단계(범용): 콘티 장면의 재료 요청 → 그 일을 하는 Craft 툴 → 같은 형식의 재료 파일.

설계: 볼트 02 Architecture/Craft 파이프라인 설계 (재료 디스패처). 쿠르츠게작트 같은 특정 화풍에 묶이지 않는다.
장면에는 툴 이름 없이 '무엇이 필요한가'만 적는다:

  "materials": [
    { "id": "m1", "type": "chart", "kind": "bar", "labels": ["실재", "가짜"], "values": [80.3, 19.7], "title": "추천 패키지", "cue": "5개" },
    { "id": "m2", "type": "doc_quote", "pdf": "research/x.pdf", "find": "hallucinated packages", "cue": "논문" },
    { "id": "m3", "type": "illustration", "src": "compositions/<id>/craft/art/hacker.svg", "place": "left" },
    { "id": "m4", "type": "photo", "src": "public/uploads/<id>/a.jpg", "cutout": true },
    { "id": "m5", "type": "screen", "src": "public/web/<id>/x.mp4" }
  ]

어느 툴이 만들지는 crafts/<앱>/craft.json 의 provides(능력 목록)로 정한다. 새 툴은 능력 한 줄 + 어댑터 함수 하나.
결과: compositions/<id>/craft/materials/s<NN>/<재료 id>.png (+ .json: 종류 · 크기 · 강조 사각형 · 만든 앱)
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
    spec = importlib.util.spec_from_file_location("fluma_crafts", ROOT / "scripts" / "crafts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def registry() -> dict[str, str]:
    """재료 종류 → 앱 이름 (설치된 앱 먼저, 없으면 설치할 수 있는 앱 — cli() 가 필요할 때 설치한다)"""
    out = {}
    cs = [json.loads(f.read_text("utf-8")) for f in sorted((ROOT / "crafts").glob("*/craft.json"))]
    cs.sort(key=lambda c: not (ROOT / "tools" / "crafts" / c["name"] / "installed.json").exists())
    for c in cs:
        for p in c.get("provides") or []:
            out.setdefault(p["material"], c["name"])
    return out


def cli(app: str) -> str:
    f = ROOT / "tools" / "crafts" / app / "installed.json"
    if not f.exists() and not _crafts().ensure(app):          # 없으면 그 자리에서 설치
        raise RuntimeError(f"Craft 앱 {app} 을 설치하지 못했습니다(이 컴퓨터용 릴리스 · 네트워크 확인: python3 scripts/crafts.py install {app})")
    rel = json.loads(f.read_text("utf-8"))["cli"]
    return str(ROOT / rel)


def _run(args: list, cwd: Path, timeout: int = 300) -> str:
    r = subprocess.run([str(a) for a in args], cwd=str(cwd), text=True, capture_output=True, timeout=timeout,
                       env={**os.environ, "DO_NOT_TRACK": "1", "SOUNDCRAFT_NO_PREFS": "1"})
    if r.returncode != 0:
        raise RuntimeError(f"{Path(str(args[0])).name} 실패: {(r.stderr or r.stdout)[-500:]}")
    return r.stdout


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
        spec = importlib.util.spec_from_file_location("fluma_icons", ROOT / "scripts" / "icons.py")
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
    """PhotoCraft: 사진 정리 · 누끼(피사체 선택 → 마스크)"""
    src = _abs(m["src"])
    cmds = ["select.subject", "layer.layerMask.revealSelection"] if m.get("cutout") else []
    args = [cli("photocraft"), "run", "--in", src]
    for c in cmds:
        args += ["--cmd", c]
    args += ["--out", out]
    _run(args, work)
    return {"app": "photocraft", "cutout": bool(m.get("cutout"))}


def read_text_boxes(f: Path) -> list[dict]:
    """[{text, box:[x, y, w, h](0~1)}] — 글자 인식이 없으면(가벼운 설치) 빈 목록"""
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        import ocr
        return [{"text": o["text"], "box": o["box"]} for o in ocr.read(f)][:80]
    except Exception as e:   # noqa: BLE001 — 글자 인식은 보조: 실패해도 재료는 쓴다
        print(f"[재료] 글자 인식 건너뜀({f.name}): {e}")
        return []


def find_upload(sid: str, m: dict) -> Path | None:
    """사용자가 올린 파일 중 이 재료의 것: 정확한 경로가 없으면 public/uploads/<id>/ 에서 이름에 재료 id 가 든 최신 파일"""
    if m.get("src") and _abs(m["src"]).exists():
        return _abs(m["src"])
    up = ROOT / "public" / "uploads" / sid
    if not up.exists():
        return None
    want = (".mp4", ".mov", ".webm", ".mkv", ".m4v") if m.get("type") in ("screen", "video") else (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm")
    key = str(m.get("id") or "").lower()
    hits = [f for f in up.iterdir() if f.is_file() and f.suffix.lower() in want and key and key in f.stem.lower()]
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def element_video(el: Path, dst: Path, hold: float | list = 1.2, crop: list | None = None) -> bool:
    """도구가 만든 요소 폴더(public/elements/<id>/<이름>/) → 영상 하나.
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


def passthrough(m: dict, out: Path, work: Path) -> dict:
    """이미 만들어진 재료(웹 녹화 · 사용자 영상 · 이미지 · 짤)는 그대로 쓴다"""
    src = _abs(m["src"])
    if src.is_dir():                       # 짤 · 웹 녹화 요소 폴더
        hold = float(m.get("hold", 1.2))
        holds = [float(x) for x in m["holds"]] if m.get("holds") else None
        if element_video(src, out.with_suffix(".mp4"), holds or hold, m.get("crop")):   # crop: [x, y, w, h] 0~1 (쿠키 안내 · 빈 곳 잘라내기)
            meta = _load(src / "meta.json")
            at = lambda k: sum((holds[i] if i < len(holds) else holds[-1]) for i in range(k)) if holds else hold * k   # k 번째 상태가 보이기 시작하는 초
            # 웹 녹화 단계(동작 → 그 결과 상태가 보이는 시각): 움직임 단계가 '1. 주소 입력' 꼬리표를 띄운다
            steps = [{"t": round(at(int(a.get("to", 0))) - 0.15, 2), "t_end": round(at(int(a.get("to", 0)) + 1), 2), "label": a.get("label")}
                     for a in meta.get("actions") or [] if a.get("label")]
            return {"app": None, "file_suffix": ".mp4", "source": meta.get("source") or meta.get("sources"), "steps": steps, "mobile": bool(meta.get("mobile"))}
        raise RuntimeError(f"요소 폴더에 프레임이 없습니다: {m['src']}")
    if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        # 영상: 마지막 프레임을 20초 늘린다(장면보다 짧은 녹화가 끝나면 화면이 비지 않게) · 소리는 뺀다(나레이션과 겹침)
        dst = out.with_suffix(".mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", "tpad=stop_mode=clone:stop_duration=20,format=yuv420p",
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)], capture_output=True, text=True)
        if r.returncode == 0:
            return {"app": None, "file_suffix": ".mp4"}
    out.with_suffix(src.suffix).write_bytes(src.read_bytes())
    return {"app": None, "file_suffix": src.suffix}


def stock(m: dict, out: Path, work: Path, sid: str) -> dict:
    """무료 스톡 영상(Pexels · Pixabay, scripts/stock.py) → 세로 화면 가득(1080×1920 로 가운데 잘라 맞춤) · 소리 없음 · 끝 프레임 유지.
    출처(credit)는 재료 기록에 남겨 설명란 '사용한 자료' 에 쓴다"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fluma_stock", ROOT / "scripts" / "stock.py")
    st = importlib.util.module_from_spec(spec); spec.loader.exec_module(st)
    r = st.fetch(sid, m["id"], str(m.get("query") or m.get("what") or ""), int(m.get("pick", 0)), float(m.get("min_sec", 3)), m.get("provider"))
    dst = out.with_suffix(".mp4")
    import sys as _s
    _s.path.insert(0, str(ROOT / "scripts"))
    from engines import aspect_size
    W, H = aspect_size(_load(ROOT / "storyboards" / f"{sid}.json") or None)
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,tpad=stop_mode=clone:stop_duration=20,format=yuv420p"
    ss = ["-ss", str(float(m["trim"]))] if m.get("trim") else []
    q = subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", r["raw"], "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(dst)], capture_output=True, text=True)
    if q.returncode != 0:
        raise RuntimeError(f"스톡 영상 변환 실패: {q.stderr[-200:]}")
    c = r["credit"]
    return {"app": None, "mobile": True, "credit": c, "source": [c["page"]]}


MAT_VERSION = "3"     # 재료를 만드는 방식이 바뀌면 올린다(열쇠에 들어가 예전 결과를 다시 만든다) — 2: 아이콘 고해상도 · 영상 마지막 프레임 유지 · 요소 폴더 · 3: 차트 항목 아이콘
ADAPTERS = {"chart": chart, "doc_quote": doc_quote, "illustration": illustration, "photo": photo, "icon": illustration}   # icon: icons.py 로 받은 SVG
PASSTHROUGH = {"screen", "video", "image", "meme", "web"}    # meme: meme.py fetch 폴더 · web: webrec.py 폴더


# ---------------------------------------------------------------- 디스패처
def build(sb: dict, indices: list[int] | None = None) -> list[dict]:
    """콘티의 모든 재료를 만든다(입력이 같으면 다시 만들지 않음) → 재료 목록.
    indices: 장면 일부만 렌더할 때 각 장면의 원래 번호(0부터) — 재료 폴더 s<NN> 이 원래 번호와 맞게"""
    sid = sb["id"]
    reg = registry()
    base = ROOT / "compositions" / sid / "craft" / "materials"
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
                if stem and stem not in keep:
                    if f.is_dir():
                        import shutil
                        shutil.rmtree(f, ignore_errors=True)
                    else:
                        f.unlink(missing_ok=True)
        for i, m in enumerate(sc.get("materials") or []):
            m = {"id": m.get("id") or f"m{i + 1}", **m}
            t = m.get("type")
            d = base / f"s{n:02d}"
            d.mkdir(parents=True, exist_ok=True)
            out = d / f"{m['id']}.png"
            meta_p = d / f"{m['id']}.json"
            # 열쇠 = 요청 + 원본 파일 내용 + 사람이 고친 편집 파일 → 무엇이든 바뀌면 다시 만든다
            srcs = [_hash(_abs(m[k])) if not _abs(m[k]).is_dir() else "|".join(f"{f.name}:{f.stat().st_size}" for f in sorted(_abs(m[k]).iterdir()))
                    for k in ("src", "csv", "xlsx", "pdf") if isinstance(m.get(k), str)]
            srcs.append(_hash(out.with_suffix(".vectorcraft")) if t == "illustration" else "")
            if m.get("ask"):                   # 사용자가 올린 파일(이름으로 찾은 것)도 열쇠에 — 새로 올리면 다시 만든다
                up_f = find_upload(sid, m)
                srcs.append(f"{up_f.name}:{_hash(up_f)}" if up_f else "missing")
            if t == "stock":                   # 스톡 영상은 화면 비율대로 잘라 만든다 → 비율이 바뀌면 다시
                from engines import aspect_of
                srcs.append(aspect_of(sb))
            old = _load(meta_p)
            if t == "illustration" and old.get("editable_hash") == srcs[-1]:
                srcs[-1] = ""                  # 우리가 만든 그대로면 열쇠에 넣지 않는다
            key = hashlib.sha1(json.dumps([m, srcs, MAT_VERSION], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
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
                       "upload_hint": f"public/uploads/{sid}/ 에 이름에 '{m['id']}' 가 든 파일(예: {m['id']}.mp4)"}
                meta_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
                made.append(rec)
                print(f"[재료] {n}장면 {m['id']}: 사용자 녹화 대기 — {m['ask']}")
                continue
            if t in PASSTHROUGH:
                if m.get("ask"):
                    m = {**m, "src": str(find_upload(sid, m).relative_to(ROOT))}
                info = passthrough(m, out, d)
                file = out.with_suffix(info.pop("file_suffix"))
            elif t == "stock":                     # 무료 스톡 영상(실제 촬영) — 키는 설정 화면
                info = stock(m, out, d, sid)
                file = out.with_suffix(".mp4")
            elif t in ADAPTERS:
                if (t if t != "icon" else "illustration") not in reg:
                    raise RuntimeError(f"'{t}' 재료를 만들 Craft 앱이 설치되지 않았습니다(Craft 앱 화면에서 설치)")
                info = ADAPTERS[t](m, out, d)
                file = out if out.exists() else None
            elif t in ("text", "stat"):            # 글자 · 수치 카드는 움직임 단계가 바로 그린다(앱 없음)
                info, file = {"app": None}, None
            else:
                raise RuntimeError(f"모르는 재료 종류: {t} (chart · stat · doc_quote · illustration · icon · photo · screen · web · video · stock · meme · image · text)")
            rec = {"scene": n, "id": m["id"], "type": t, "key": key, "spec": m, "file": str(file.relative_to(ROOT)) if file else None, **info}
            # 캡처 · 사진 속 글자 위치(글자 인식) — 움직임 단계가 '말하는 낱말을 화면에서 짚기(확대 · 동그라미)'에 쓴다
            if file and t in ("image", "photo", "screen") and file.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                rec["ocr"] = read_text_boxes(file)
            meta_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
            made.append(rec)
    return made
