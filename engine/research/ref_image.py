#!/usr/bin/env python3
"""시각 · 화풍 · 작품 · 실물 레퍼런스 이미지 수집, 밀착 시트 생성 및 샷 계획 연동(Stage 0.5).

사용자가 특정 화풍 · 작품 · 캐릭터 · 실물을 언급했을 때 LLM 기억으로만 프롬프트를 쓰지 않고,
웹에서 실제 이미지를 검색/수집해 밀착 시트로 눈으로 확인한 뒤 2 · 3단계 참조(`style_refs`)로 넘긴다.

  python3 engine/research/ref_image.py search <plan id> "<영문 검색어>" [--limit 6] [--source auto|bing|commons]
  python3 engine/research/ref_image.py pick <plan id> 1 3 --role style --note "Ghibli watercolor sky" [--no-sync]
  python3 engine/research/ref_image.py fetch <plan id> <URL 또는 로컬경로...> --role style --note "..." [--no-sync]
  python3 engine/research/ref_image.py status <plan id>
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))
import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

ROLES = ("style", "character", "prop", "background")
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def refs_dir(pid: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "refs"


def load_meta(pid: str) -> dict[str, Any]:
    p = refs_dir(pid) / "refs.json"
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return {"query": "", "candidates": [], "picked": []}


def save_meta(pid: str, data: dict[str, Any]) -> Path:
    d = refs_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "refs.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return p


def _font(size: int = 24):
    try:
        return ImageFont.truetype(str(ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf"), size)
    except OSError:
        return ImageFont.load_default()


def parse_bing_html(body: str, limit: int = 12) -> list[dict[str, str]]:
    """Bing 이미지 검색 HTML 에서 murl · turl · title 을 뽑는다."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'class="iusc"[^>]*\bm="([^"]+)"', body):
        raw = html.unescape(m.group(1))
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            continue
        url = str(info.get("murl") or info.get("turl") or "").strip()
        thumb = str(info.get("turl") or "").strip()
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        out.append({
            "url": url,
            "thumb": thumb,
            "title": str(info.get("t") or info.get("desc") or "").strip()[:120],
            "source": "bing",
        })
        if len(out) >= limit:
            break
    return out


def search_bing(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Bing 공개 이미지 검색 결과(API 키 불필요)."""
    url = "https://www.bing.com/images/search?" + urllib.parse.urlencode({"q": query, "form": "HDRSC2", "first": 1})
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=15)
    r.raise_for_status()
    return parse_bing_html(r.text, limit=limit)


def search_commons(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Wikimedia Commons 공개 이미지 검색(engine/capture/commons.py 재사용)."""
    sys.path.insert(0, str(ROOT / "engine" / "capture"))
    import commons  # noqa: E402

    rows = commons.search(query, limit)
    out: list[dict[str, str]] = []
    for row in rows:
        u = str(row.get("thumb") or row.get("url") or "").strip()
        if not u.startswith("http"):
            continue
        out.append({
            "url": str(row.get("url") or u),
            "thumb": u,
            "title": str(row.get("title") or "").replace("File:", "")[:120],
            "source": "commons",
        })
    return out


def _download_image(urls: list[str], out_path: Path, max_edge: int = 1024, min_edge: int = 160) -> tuple[int, int] | None:
    """후보 URL 목록(원본 → 썸네일)을 받아 PIL 로 검증한 뒤 저장한다."""
    for u in urls:
        if not u or not u.startswith("http"):
            continue
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=12)
            if r.status_code != 200 or not r.content:
                continue
            with Image.open(io.BytesIO(r.content)) as im:
                rgb = im.convert("RGB")
                w, h = rgb.size
                if min(w, h) < min_edge:
                    continue
                if max(w, h) > max_edge:
                    scale = max_edge / max(w, h)
                    rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                rgb.save(out_path, format="JPEG", quality=90)
                return rgb.size
        except (requests.RequestException, OSError):
            continue
    return None


def make_contact_sheet(items: list[dict[str, Any]], out_path: Path, label_key: str = "index") -> Path | None:
    """번호 · 출처 · 해상도를 붙인 한 장짜리 밀착 시트를 만든다(에이전트 육안 확인용)."""
    valid = [x for x in items if (ROOT / x["path"]).exists()]
    if not valid:
        return None
    cols = min(3, len(valid))
    rows = (len(valid) + cols - 1) // cols
    cell_w, cell_h, hdr = 420, 420, 56
    pad = 16
    sheet = Image.new("RGB", (cols * cell_w + (cols + 1) * pad, rows * (cell_h + hdr) + (rows + 1) * pad), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = _font(22)
    for idx, item in enumerate(valid):
        r, c = divmod(idx, cols)
        x0 = pad + c * (cell_w + pad)
        y0 = pad + r * (cell_h + hdr + pad)
        with Image.open(ROOT / item["path"]) as raw:
            im = raw.convert("RGB")
            im.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
            px = x0 + (cell_w - im.width) // 2
            py = y0 + hdr + (cell_h - im.height) // 2
            sheet.paste(im, (px, py))
        tag = f"#{item.get(label_key, idx + 1)} [{item.get('role') or item.get('source', 'ref')}] {item.get('w', '')}x{item.get('h', '')}"
        title = str(item.get("note") or item.get("title") or "")[:36]
        draw.text((x0 + 4, y0 + 2), tag, font=font, fill=(245, 220, 120))
        if title:
            draw.text((x0 + 4, y0 + 28), title, font=_font(18), fill=(210, 210, 220))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="JPEG", quality=90)
    return out_path


def search_and_save(pid: str, query: str, limit: int = 6, source: str = "auto") -> dict[str, Any]:
    """웹 이미지 검색 → 후보 다운로드 → 번호 붙은 밀착 시트 생성."""
    raw_hits: list[dict[str, str]] = []
    errors: list[str] = []
    sources_to_try = ["bing", "commons"] if source == "auto" else [source]
    for src in sources_to_try:
        try:
            hits = search_bing(query, limit * 2) if src == "bing" else search_commons(query, limit * 2)
            raw_hits.extend(hits)
            if len(raw_hits) >= limit * 2:
                break
        except Exception as e:  # noqa: BLE001 — 한 소스 실패 시 다음 소스로 fallback
            errors.append(f"{src}: {e}")
    cdir = refs_dir(pid) / "candidates"
    if cdir.exists():
        for old in cdir.glob("cand_*.jpg"):
            old.unlink()
    saved: list[dict[str, Any]] = []
    for h in raw_hits:
        idx = len(saved) + 1
        out_p = cdir / f"cand_{idx:02d}.jpg"
        sz = _download_image([h["url"], h.get("thumb", "")], out_p)
        if not sz:
            continue
        host = urllib.parse.urlparse(h["url"]).netloc
        saved.append({
            "index": idx,
            "path": str(out_p.relative_to(ROOT)),
            "url": h["url"],
            "source": h["source"],
            "host": host,
            "title": h.get("title", ""),
            "w": sz[0],
            "h": sz[1],
        })
        if len(saved) >= limit:
            break
    meta = load_meta(pid)
    meta["query"] = query
    meta["candidates"] = saved
    sheet = make_contact_sheet(saved, refs_dir(pid) / "candidates_sheet.jpg", label_key="index")
    if sheet:
        meta["candidates_sheet"] = str(sheet.relative_to(ROOT))
    save_meta(pid, meta)
    return {
        "query": query,
        "count": len(saved),
        "sheet": meta.get("candidates_sheet"),
        "candidates": saved,
        "errors": errors,
    }


def _copy_as_png(src_path: Path, dst_path: Path, max_edge: int = 1280) -> tuple[int, int]:
    with Image.open(src_path) as raw:
        im = raw.convert("RGB")
        w, h = im.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst_path, format="PNG")
        return im.size


def sync_to_shotplan(pid: str, picked: list[dict[str, Any]]) -> bool:
    """고른 레퍼런스 목록을 data/shotplans/<pid>.json 의 style_refs 칸에 적는다."""
    sp_path = ROOT / "data" / "shotplans" / f"{pid}.json"
    if not sp_path.exists():
        return False
    sb = json.loads(sp_path.read_text("utf-8"))
    sb["style_refs"] = [
        {
            "path": p["path"],
            "role": p["role"],
            **({"note": p["note"]} if p.get("note") else {}),
            **({"source": p["url"]} if p.get("url") else {}),
        }
        for p in picked[:4]
    ]
    sp_path.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return True


def pick_candidates(pid: str, indices: list[int], role: str, note: str = "", sync: bool = True, replace: bool = False) -> dict[str, Any]:
    """밀착 시트에서 고른 후보 번호를 정식 레퍼런스(ref_NN.png)로 확정한다."""
    if role not in ROLES:
        raise ValueError(f"role 은 {ROLES} 중 하나여야 합니다: {role}")
    meta = load_meta(pid)
    by_idx = {c["index"]: c for c in meta.get("candidates") or []}
    picked = [] if replace else list(meta.get("picked") or [])
    existing_urls = {p.get("url") for p in picked if p.get("url")}
    added: list[dict[str, Any]] = []
    for idx in indices:
        cand = by_idx.get(idx)
        if not cand:
            raise ValueError(f"후보 #{idx} 가 없습니다 (가능: {sorted(by_idx)})")
        src = ROOT / cand["path"]
        if not src.exists():
            raise ValueError(f"후보 파일이 없습니다: {cand['path']}")
        if cand.get("url") in existing_urls:
            continue
        num = len(picked) + 1
        dst = refs_dir(pid) / f"ref_{num:02d}.png"
        w, h = _copy_as_png(src, dst)
        entry = {
            "index": num,
            "path": str(dst.relative_to(ROOT)),
            "role": role,
            "note": note or cand.get("title") or "",
            "url": cand.get("url", ""),
            "w": w,
            "h": h,
        }
        picked.append(entry)
        added.append(entry)
        if cand.get("url"):
            existing_urls.add(cand["url"])
    meta["picked"] = picked
    sheet = make_contact_sheet(picked, refs_dir(pid) / "picked_sheet.jpg", label_key="index")
    if sheet:
        meta["picked_sheet"] = str(sheet.relative_to(ROOT))
    save_meta(pid, meta)
    synced = sync_to_shotplan(pid, picked) if sync else False
    return {"added": added, "total": len(picked), "sheet": meta.get("picked_sheet"), "synced": synced}


def fetch_direct(pid: str, sources: list[str], role: str, note: str = "", sync: bool = True) -> dict[str, Any]:
    """직접 찾은 URL 또는 로컬 파일(사용자 첨부)을 정식 레퍼런스로 저장한다."""
    if role not in ROLES:
        raise ValueError(f"role 은 {ROLES} 중 하나여야 합니다: {role}")
    meta = load_meta(pid)
    picked = list(meta.get("picked") or [])
    added: list[dict[str, Any]] = []
    for src in sources:
        num = len(picked) + 1
        dst = refs_dir(pid) / f"ref_{num:02d}.png"
        tmp = refs_dir(pid) / f"_tmp_{num:02d}.jpg"
        src_url = ""
        if src.startswith("http://") or src.startswith("https://"):
            sz = _download_image([src], tmp, min_edge=120)
            if not sz:
                raise RuntimeError(f"이미지를 받지 못했거나 손상됨: {src}")
            w, h = _copy_as_png(tmp, dst)
            tmp.unlink(missing_ok=True)
            src_url = src
        else:
            lp = Path(src) if Path(src).is_absolute() else (ROOT / src)
            if not lp.exists():
                raise RuntimeError(f"로컬 파일이 없습니다: {src}")
            w, h = _copy_as_png(lp, dst)
        entry = {
            "index": num,
            "path": str(dst.relative_to(ROOT)),
            "role": role,
            "note": note,
            "url": src_url,
            "w": w,
            "h": h,
        }
        picked.append(entry)
        added.append(entry)
    meta["picked"] = picked
    sheet = make_contact_sheet(picked, refs_dir(pid) / "picked_sheet.jpg", label_key="index")
    if sheet:
        meta["picked_sheet"] = str(sheet.relative_to(ROOT))
    save_meta(pid, meta)
    synced = sync_to_shotplan(pid, picked) if sync else False
    return {"added": added, "total": len(picked), "sheet": meta.get("picked_sheet"), "synced": synced}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="웹 이미지 검색 후 밀착 시트 생성")
    s.add_argument("id")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=6)
    s.add_argument("--source", choices=("auto", "bing", "commons"), default="auto")

    p = sub.add_parser("pick", help="밀착 시트에서 고른 후보 번호를 확정")
    p.add_argument("id")
    p.add_argument("indices", nargs="+", type=int)
    p.add_argument("--role", choices=ROLES, default="style")
    p.add_argument("--note", default="")
    p.add_argument("--replace", action="store_true")
    p.add_argument("--no-sync", action="store_true")

    f = sub.add_parser("fetch", help="직접 URL 또는 로컬 이미지를 레퍼런스로 저장")
    f.add_argument("id")
    f.add_argument("sources", nargs="+")
    f.add_argument("--role", choices=ROLES, default="style")
    f.add_argument("--note", default="")
    f.add_argument("--no-sync", action="store_true")

    st = sub.add_parser("status", help="현재 저장된 시각 레퍼런스 상태")
    st.add_argument("id")

    a = ap.parse_args()
    if a.cmd == "search":
        res = search_and_save(a.id, a.query, limit=a.limit, source=a.source)
        if not res["count"]:
            fail("ref_image", stage="search", error=f"이미지를 찾지 못함 ({'; '.join(res['errors']) or '검색 결과 0건'})")
        ok("ref_image", count=res["count"], sheet=res["sheet"], next="sheet 를 read_file 로 열어 보고 ref_image.py pick 실행")
        return 0
    if a.cmd == "pick":
        try:
            res = pick_candidates(a.id, a.indices, a.role, note=a.note, sync=not a.no_sync, replace=a.replace)
        except Exception as e:  # noqa: BLE001
            fail("ref_image", stage="pick", error=str(e))
        ok("ref_image", picked=res["total"], sheet=res["sheet"], synced=res["synced"])
        return 0
    if a.cmd == "fetch":
        try:
            res = fetch_direct(a.id, a.sources, a.role, note=a.note, sync=not a.no_sync)
        except Exception as e:  # noqa: BLE001
            fail("ref_image", stage="fetch", error=str(e))
        ok("ref_image", picked=res["total"], sheet=res["sheet"], synced=res["synced"])
        return 0
    meta = load_meta(a.id)
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
