#!/usr/bin/env python3
"""무료 스톡 영상(실제 촬영 영상) 찾기 · 받기 — 일상 · 감성 · 광고 장면의 바탕(B-roll). 생성 영상이 아니다.

  python3 scripts/stock.py search "<영어 검색어>" [--provider pexels|pixabay] [--min-sec 4] [--n 8]
  python3 scripts/stock.py fetch <영상 id> <재료 id> "<영어 검색어>" [--pick 0] [--min-sec 4]   # → compositions/<id>/stock/<재료 id>.mp4

콘티 재료:  {"id": "commute", "type": "stock", "query": "subway commute morning", "min_sec": 4, "pick": 0}
  query 는 영어가 잘 찾힌다(두 사이트 모두 영어 태그). 세로(9:16) 영상을 먼저 고르고, 없으면 가로 영상을 가운데로 잘라 쓴다.
  같은 영상 안의 다른 재료가 이미 쓴 클립은 건너뛴다(workspace/asset-cache/stock/used-<영상 id>.json).
키: 설정 → API 키의 Pexels(PEXELS_API_KEY) · Pixabay(PIXABAY_API_KEY). 값은 출력 · 기록하지 않는다.
라이선스: Pexels License · Pixabay Content License — 무료 · 상업 사용 가능, 표기 의무는 없지만 설명란에 출처를 남긴다(credit 칸).
사람 얼굴이 크게 나오는 클립은 초상권 문제가 있을 수 있어 사용자가 확인한다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
CACHE = ROOT / "workspace" / "asset-cache" / "stock"
UA = {"User-Agent": "Fluma/1.0 (+https://github.com/meowassassin/fluma)"}


def _get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _key(name: str) -> str:
    import apikeys
    return apikeys.get(name)


def pexels(query: str, per: int = 15) -> list[dict]:
    k = _key("PEXELS_API_KEY")
    if not k:
        return []
    q = urllib.parse.urlencode({"query": query, "per_page": per, "orientation": "portrait", "size": "medium"})
    data = _get(f"https://api.pexels.com/videos/search?{q}", {"Authorization": k})
    out = []
    for v in data.get("videos") or []:
        files = [f for f in v.get("video_files") or [] if f.get("file_type") == "video/mp4" and f.get("link")]
        if not files:
            continue
        out.append({"provider": "pexels", "id": str(v["id"]), "duration": float(v.get("duration") or 0), "width": v.get("width"), "height": v.get("height"),
                    "page": v.get("url"), "author": (v.get("user") or {}).get("name"), "license": "Pexels License (https://www.pexels.com/license/)",
                    "files": [{"url": f["link"], "w": f.get("width") or 0, "h": f.get("height") or 0} for f in files]})
    return out


def pixabay(query: str, per: int = 20) -> list[dict]:
    k = _key("PIXABAY_API_KEY")
    if not k:
        return []
    q = urllib.parse.urlencode({"key": k, "q": query[:100], "per_page": per, "safesearch": "true"})
    data = _get(f"https://pixabay.com/api/videos/?{q}")
    out = []
    for v in data.get("hits") or []:
        files = [{"url": f["url"], "w": f.get("width") or 0, "h": f.get("height") or 0} for f in (v.get("videos") or {}).values() if f.get("url")]
        if not files:
            continue
        big = max(files, key=lambda f: f["w"] * f["h"])
        out.append({"provider": "pixabay", "id": str(v["id"]), "duration": float(v.get("duration") or 0), "width": big["w"], "height": big["h"],
                    "page": v.get("pageURL"), "author": v.get("user"), "license": "Pixabay Content License (https://pixabay.com/service/license-summary/)",
                    "files": files})
    return out


def search(query: str, provider: str | None = None, min_sec: float = 3.0) -> list[dict]:
    """세로 · 충분히 긴 것 먼저. provider 를 정하지 않으면 Pexels → Pixabay"""
    found: list[dict] = []
    for name, fn in (("pexels", pexels), ("pixabay", pixabay)):
        if provider and provider != name:
            continue
        try:
            found += fn(query)
        except Exception as e:  # noqa: BLE001  (키 오류 · 네트워크) — 다음 공급자로
            print(f"[스톡] {name} 검색 실패: {str(e)[:120]}", file=sys.stderr)
        if found and not provider:
            break
    found = [c for c in found if c["duration"] >= min_sec]
    found.sort(key=lambda c: (not (c["height"] or 0) > (c["width"] or 0), -min(c["duration"], 12)))
    return found


def best_file(c: dict) -> dict:
    """세로 1080 에 가장 가까운(작지 않은) 파일 — 너무 큰 4K 는 받지 않는다"""
    fs = sorted(c["files"], key=lambda f: (min(f["w"], f["h"]) < 720, abs(min(f["w"], f["h"]) - 1080)))
    return fs[0]


def used_path(sid: str) -> Path:
    return CACHE / f"used-{sid}.json"


def fetch(sid: str, mid: str, query: str, pick: int = 0, min_sec: float = 3.0, provider: str | None = None) -> dict:
    """→ {"file": compositions/<id>/stock/<mid>.mp4, "credit": …}. 같은 영상의 다른 재료가 쓴 클립은 건너뛴다"""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", sid) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", mid):
        raise ValueError("영상 id · 재료 id 가 올바르지 않음")
    if not (_key("PEXELS_API_KEY") or _key("PIXABAY_API_KEY")):
        raise RuntimeError("스톡 영상 키가 없습니다 — 설정 → API 키에서 Pexels 또는 Pixabay 키를 넣어 주세요(무료)")
    CACHE.mkdir(parents=True, exist_ok=True)
    used = json.loads(used_path(sid).read_text("utf-8")) if used_path(sid).exists() else {}
    taken = {v for k, v in used.items() if k != mid}
    cands = [c for c in search(query, provider, min_sec) if f"{c['provider']}:{c['id']}" not in taken]
    if not cands:
        raise RuntimeError(f"'{query}' 에 맞는 스톡 영상이 없습니다(최소 {min_sec}초) — 검색어를 바꿔 보세요(영어가 잘 찾힘)")
    c = cands[min(pick, len(cands) - 1)]
    f = best_file(c)
    raw = CACHE / f"{c['provider']}-{c['id']}-{f['w']}x{f['h']}.mp4"
    if not raw.exists():
        req = urllib.request.Request(f["url"], headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(raw, "wb") as o:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                o.write(b)
    used[mid] = f"{c['provider']}:{c['id']}"
    used_path(sid).write_text(json.dumps(used, ensure_ascii=False, indent=1), "utf-8")
    credit = {"provider": c["provider"], "id": c["id"], "page": c["page"], "author": c["author"], "license": c["license"], "query": query,
              "duration": c["duration"], "size": [f["w"], f["h"]]}
    return {"raw": str(raw), "credit": credit}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--provider"); s.add_argument("--min-sec", type=float, default=3); s.add_argument("--n", type=int, default=8)
    f = sub.add_parser("fetch"); f.add_argument("id"); f.add_argument("mid"); f.add_argument("query"); f.add_argument("--pick", type=int, default=0); f.add_argument("--min-sec", type=float, default=3); f.add_argument("--provider")
    a = ap.parse_args()
    if a.cmd == "search":
        rows = search(a.query, a.provider, a.min_sec)
        if not rows:
            print("없음 — 키가 없거나 검색어에 맞는 영상이 없습니다(영어 검색어가 잘 찾힘)")
            return 1
        for i, c in enumerate(rows[: a.n]):
            print(f"{i}. {c['provider']} {c['id']}  {c['duration']:.0f}초  {c['width']}×{c['height']}  {c['author']}  {c['page']}")
        return 0
    from result import needs_input, ok
    if not (_key("PEXELS_API_KEY") or _key("PIXABAY_API_KEY")):
        needs_input("stock", needs=["PEXELS_API_KEY 또는 PIXABAY_API_KEY(무료)"], how="설정 → API 키 — 채팅에 키를 붙이지 말고 설정 화면에")
    r = fetch(a.id, a.mid, a.query, a.pick, a.min_sec, a.provider)
    c = r["credit"]
    ok("stock", file=r["raw"], credit=f"{c['provider']} · {c.get('author')} — {c['page']}", license=c["license"])


if __name__ == "__main__":
    from result import run_main
    run_main("stock", main)
