#!/usr/bin/env python3
"""참고 그림 찾기 — 형태(form)를 빚기 전에 그 대상 · 그림 장르의 실제 그림을 본다(영상에 넣지 않는다, 보기만).

2026-11-20 사용자: 3D 로 빚어 2D 그림으로 쓰는데 무엇을 보고 빚느냐 — 지금은 아무것도 안 보고 기억으로 빚어
비례가 어색하고(고양이) 그림체가 늘 비슷했다. 카툰 · 극화 · 데포르메 · 일본 만화 · 미국 만화처럼 장르마다 형태 과장 · 선 · 명암이 다르다 —
장르별 규칙표 대신 매번 참고 그림을 보고 정한다.

  python3 engine/research/ref_images.py "<이름>" --id <영상 id> --pages <URL> <URL> …   # 기본: 네가 WebSearch(일반 웹 검색)로 찾은 그림 페이지 주소 → 대표 그림을 받아 시트로
  python3 engine/research/ref_images.py "<영어 검색어>" [--id <영상 id>] [--n 8]       # 페이지 없이: Openverse(+ Brave 키가 있으면 웹 이미지) 검색
출력: 번호 붙은 시트 한 장(이것만 Read) + 받은 파일 목록. 검색어는 영어가 결과가 많다(대상 + 장르 + illustration/drawing).
검색원: Openverse(키 없음 · CC 이미지 · 그림 위주로 거름), 설정 → API 키에 Brave Search 키가 있으면 일반 웹 이미지도.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "core"))
from result import fail, ok  # noqa: E402

UA = {"User-Agent": "FlumaStudio/1.0 (local desktop video tool; style reference lookup) python-urllib"}


def _get(url: str, headers: dict | None = None, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=timeout) as r:
        return r.read()


def openverse(q: str, n: int) -> list[dict]:
    out = []
    for cat in ("illustration,digitized_artwork", None):          # 그림 먼저, 모자라면 전체
        params = {"q": q, "page_size": max(n, 10), **({"category": cat} if cat else {})}
        try:
            d = json.loads(_get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)))
        except (OSError, ValueError):
            continue
        for r in d.get("results") or []:
            if r.get("thumbnail") and r["id"] not in {x["id"] for x in out}:
                out.append({"id": r["id"], "title": r.get("title") or "", "thumb": r["thumbnail"], "page": r.get("foreign_landing_url") or r.get("url"), "from": f"openverse/{r.get('source')}"})
        if len(out) >= n:
            break
    return out[:n]


def brave(q: str, n: int) -> list[dict]:
    import apikeys
    key = apikeys.get("BRAVE_API_KEY")
    if not key:
        return []
    try:
        d = json.loads(_get("https://api.search.brave.com/res/v1/images/search?" + urllib.parse.urlencode({"q": q, "count": min(n * 2, 50), "safesearch": "strict"}),
                            {"Accept": "application/json", "X-Subscription-Token": key}))
    except (OSError, ValueError) as e:
        print(f"[ref] Brave 검색 실패: {str(e)[:120]}", file=sys.stderr)
        return []
    return [{"id": f"b{i}", "title": r.get("title") or "", "thumb": (r.get("thumbnail") or {}).get("src"), "page": r.get("url"), "from": "brave"}
            for i, r in enumerate(d.get("results") or []) if (r.get("thumbnail") or {}).get("src")][:n]


SKIP = re.compile(r"logo|icon|avatar|sprite|badge|emoji|button|banner|pixel|tracking|spacer|ads?[/_-]|\.svg|\.gif|data:", re.I)


def pages(urls: list[str], per_page: int = 3) -> list[dict]:
    """에이전트가 일반 웹 검색(WebSearch)으로 찾은 페이지 → 그 페이지의 대표 그림(og:image) + 본문 그림 몇 장.
    공개 페이지를 그대로 여는 것뿐 — 검색 엔진 내부 주소를 긁지 않는다(2026-11-20: 비공식 이미지 검색은 권한 검사에서 막힘)"""
    out = []
    for i, u in enumerate(urls):
        try:
            h = _get(u, timeout=15)[:600_000].decode("utf-8", "ignore")
        except (OSError, ValueError) as e:
            print(f"[ref] 페이지 열기 실패 {u[:80]}: {str(e)[:80]}", file=sys.stderr)
            continue
        t = re.search(r"<title[^>]*>([^<]{0,120})", h, re.I)
        title = re.sub(r"&[a-z#0-9]+;", "", (t.group(1).strip() if t else u))[:70]
        cands = [m.group(1) for m in re.finditer(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\'][^>]*content=["\']([^"\']+)', h, re.I)]
        cands += [m.group(1) for m in re.finditer(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', h, re.I)]
        cands += [m.group(1) for m in re.finditer(r'<img[^>]+?(?:data-src|src)=["\']([^"\']+)', h, re.I)]
        seen, k = set(), 0
        for c in cands:
            c = urllib.parse.urljoin(u, c.replace("&amp;", "&"))
            if c in seen or SKIP.search(c) or not c.startswith("http"):
                continue
            seen.add(c)
            out.append({"id": f"p{i}-{k}", "title": title, "thumb": c, "page": u, "from": "web", "_page": i})
            k += 1
            if k >= per_page * 3:          # 받아 보고 작은 것(아이콘)은 버리므로 넉넉히 후보
                break
    return out


def _fetch(h: dict):
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(_get(h["thumb"], timeout=15))).convert("RGB")
    except Exception:  # noqa: BLE001 - 깨진 · 막힌 그림은 건너뛴다
        return None
    return im if min(im.size) >= 280 else None


def main() -> int:
    a = sys.argv[1:]
    urls = [x for x in a[a.index("--pages") + 1:] if x.startswith("http")] if "--pages" in a else []
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and not x.startswith("http") and (i == 0 or not a[i - 1].startswith("--"))]
    if not pos and not urls:
        print(__doc__); return 2
    q = pos[0] if pos else "web pages"
    sid = a[a.index("--id") + 1] if "--id" in a else "_any"
    from PIL import Image, ImageDraw
    n = int(a[a.index("--n") + 1]) if "--n" in a else (24 if urls else 8)
    hits = pages(urls) if urls else (brave(q, n) + openverse(q, n))[:n]
    if not hits:
        fail("ref_images", stage="search", error=f"'{q}' 참고 그림을 못 찾음 — 영어로 대상 + 장르 + illustration/drawing 처럼 바꿔 보거나, 설정 → API 키에 Brave Search 키를 넣는다")
    d = ROOT / "data" / "workspace" / "look" / "ref" / sid / re.sub(r"[^A-Za-z0-9가-힣]+", "-", q).strip("-")[:60]
    d.mkdir(parents=True, exist_ok=True)
    tiles, rows = [], []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        ims = list(ex.map(_fetch, hits))
    per: dict = {}
    marks: list = []
    import numpy as np

    def _mark(im):                                     # 같은 그림(크기만 다른 것)을 한 번만 — 8×8 밝기 지문
        g = np.asarray(im.convert("L").resize((8, 8)), dtype=np.float32)
        return g > g.mean()
    for h, im in zip(hits, ims):
        if im is None or len(rows) >= n:
            continue
        mk = _mark(im)
        if any(int((mk != o).sum()) <= 6 for o in marks):
            continue
        marks.append(mk)
        if h.get("_page") is not None:                 # 한 페이지에서 너무 많이 가져오지 않게(다양하게)
            if per.get(h["_page"], 0) >= 3:
                continue
            per[h["_page"]] = per.get(h["_page"], 0) + 1
        i = len(rows) + 1
        f = d / f"{i:02d}.jpg"
        im.save(f, quality=88)
        rows.append({k: v for k, v in h.items() if k != "_page"} | {"n": i, "file": str(f.relative_to(ROOT))})
        t = im.copy(); t.thumbnail((300, 300))
        tile = Image.new("RGB", (300, 320), "#ffffff"); tile.paste(t, ((300 - t.width) // 2, 20 + (300 - t.height) // 2))
        ImageDraw.Draw(tile).text((8, 2), str(i), fill="#d62828")
        tiles.append(tile)
    if not tiles:
        fail("ref_images", stage="download", error="그림을 받지 못함")
    cols = 6
    sheet = Image.new("RGB", (300 * cols, 320 * ((len(tiles) + cols - 1) // cols)), "#ffffff")
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * 300, (k // cols) * 320))
    sh = d / "sheet.jpg"; sheet.save(sh, quality=85)
    (d / "refs.json").write_text(json.dumps({"query": q, "items": rows}, ensure_ascii=False, indent=1), "utf-8")
    for r in rows:
        print(f"{r['n']:>2} {r['from']:<22} {r['title'][:60]}")
    ok("ref_images", sheet=str(sh.relative_to(ROOT)), count=str(len(rows)), media=[f"{sh.relative_to(ROOT)} | 참고 그림({q})"],
       next="시트를 Read 로 보고 주제 · 톤에 어울리는 것만 골라(관계없는 사진 · 글 그림은 버린다) 가져올 특징(비례 · 실루엣 · 과장 정도 · 선 · 명암 · 색)을 적는다 — 따라 그리지 않는다. form_cli preview --ref <NN.jpg> 로 견준다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
