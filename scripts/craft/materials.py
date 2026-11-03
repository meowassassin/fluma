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
def registry() -> dict[str, str]:
    """재료 종류 → 앱 이름 (설치되어 있고 CLI 가 있는 것만)"""
    out = {}
    for f in sorted((ROOT / "crafts").glob("*/craft.json")):
        c = json.loads(f.read_text("utf-8"))
        inst = ROOT / "tools" / "crafts" / c["name"] / "installed.json"
        if not inst.exists():
            continue
        for p in c.get("provides") or []:
            out.setdefault(p["material"], c["name"])
    return out


def cli(app: str) -> str:
    rel = json.loads((ROOT / "tools" / "crafts" / app / "installed.json").read_text("utf-8"))["cli"]
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
    _run([cli("vectorcraft"), "convert", src, out, "--scale", str(m.get("scale", 2))], work)
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


def passthrough(m: dict, out: Path, work: Path) -> dict:
    """이미 만들어진 재료(웹 녹화 · 사용자 영상 · 이미지)는 그대로 쓴다"""
    src = _abs(m["src"])
    out.with_suffix(src.suffix).write_bytes(src.read_bytes())
    return {"app": None, "file_suffix": src.suffix}


ADAPTERS = {"chart": chart, "doc_quote": doc_quote, "illustration": illustration, "photo": photo}
PASSTHROUGH = {"screen", "video", "image"}


# ---------------------------------------------------------------- 디스패처
def build(sb: dict, indices: list[int] | None = None) -> list[dict]:
    """콘티의 모든 재료를 만든다(입력이 같으면 다시 만들지 않음) → 재료 목록.
    indices: 장면 일부만 렌더할 때 각 장면의 원래 번호(0부터) — 재료 폴더 s<NN> 이 원래 번호와 맞게"""
    sid = sb["id"]
    reg = registry()
    base = ROOT / "compositions" / sid / "craft" / "materials"
    made = []
    scs = sb.get("scenes") or []
    for n, sc in zip([i + 1 for i in indices] if indices else range(1, len(scs) + 1), scs):
        for i, m in enumerate(sc.get("materials") or []):
            m = {"id": m.get("id") or f"m{i + 1}", **m}
            t = m.get("type")
            d = base / f"s{n:02d}"
            d.mkdir(parents=True, exist_ok=True)
            out = d / f"{m['id']}.png"
            meta_p = d / f"{m['id']}.json"
            # 열쇠 = 요청 + 원본 파일 내용 + 사람이 고친 편집 파일 → 무엇이든 바뀌면 다시 만든다
            srcs = [_hash(_abs(m[k])) for k in ("src", "csv", "xlsx", "pdf") if isinstance(m.get(k), str)]
            srcs.append(_hash(out.with_suffix(".vectorcraft")) if t == "illustration" else "")
            old = _load(meta_p)
            if t == "illustration" and old.get("editable_hash") == srcs[-1]:
                srcs[-1] = ""                  # 우리가 만든 그대로면 열쇠에 넣지 않는다
            key = hashlib.sha1(json.dumps([m, srcs], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
            if old.get("key") == key and (not old.get("file") or (ROOT / old["file"]).exists()):
                made.append(old)
                continue
            if t in PASSTHROUGH:
                info = passthrough(m, out, d)
                file = out.with_suffix(info.pop("file_suffix"))
            elif t in ADAPTERS:
                if t not in reg:
                    raise RuntimeError(f"'{t}' 재료를 만들 Craft 앱이 설치되지 않았습니다(Craft 앱 화면에서 설치)")
                info = ADAPTERS[t](m, out, d)
                file = out if out.exists() else None
            elif t == "text":
                info, file = {"app": None}, None
            else:
                raise RuntimeError(f"모르는 재료 종류: {t} (chart · doc_quote · illustration · photo · screen · video · image · text)")
            rec = {"scene": n, "id": m["id"], "type": t, "key": key, "spec": m, "file": str(file.relative_to(ROOT)) if file else None, **info}
            meta_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
            made.append(rec)
    return made
