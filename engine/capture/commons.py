#!/usr/bin/env python3
"""실제 자료 — Wikimedia Commons 에서 재사용 가능한 사진 · 그림을 찾고 출처와 함께 받는다.
CC0 · 공공 저작물 · CC BY · CC BY-SA 만 쓴다. 출처 · 저작자 · 라이선스를 meta 에 남겨 설명란 '사용한 자료'에 넣는다.

  python3 engine/capture/commons.py search "black-figure amphora runners" [--n 10]
  python3 engine/capture/commons.py fetch <영상 id> <이름> "File:…jpg" [--width 1920]
콘티: {"type": "archive", "id": "a1", "title": "File:…jpg"} — 파일 이름은 search 로 찾아 눈으로 보고 고른다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "fluma-research/1.0"}
OK = ("cc0", "public domain", "pd", "cc by", "cc-by")


def _open(url: str, timeout: int = 60) -> bytes:
    """요청 제한을 지킨다 — 429 면 서버가 알려 준 만큼 기다렸다가 다시 묻고, 계속 막히면 멈춘다"""
    for k in range(5):
        time.sleep(1.5)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == 4:
                raise
            time.sleep(min(90, float(e.headers.get("Retry-After") or (10 * (k + 1)))))
    raise RuntimeError("자료를 받지 못했습니다")


def _get(params: dict) -> dict:
    return json.loads(_open(API + "?" + urllib.parse.urlencode({"format": "json", **params}), 30))


def _meta(p: dict) -> dict:
    i = (p.get("imageinfo") or [{}])[0]
    m = i.get("extmetadata") or {}
    v = lambda k: re.sub(r"<[^>]+>", "", str((m.get(k) or {}).get("value") or "")).strip()  # noqa: E731
    return {"title": p.get("title"), "w": i.get("width"), "h": i.get("height"), "license": v("LicenseShortName"), "artist": v("Artist")[:120], "page": i.get("descriptionurl"), "url": i.get("url"), "thumb": i.get("thumburl")}


def allowed(lic: str) -> bool:
    l = (lic or "").lower()
    return any(l.startswith(k) or k in l for k in OK) and "nc" not in l.split() and "-nd" not in l and "-nc" not in l


def search(q: str, n: int = 10) -> list:
    d = _get({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": n * 2, "gsrsearch": f"{q} filetype:bitmap", "prop": "imageinfo", "iiprop": "size|url|extmetadata", "iiurlwidth": 480, "iiextmetadatafilter": "LicenseShortName|Artist"})
    r = [_meta(p) for p in (d.get("query") or {}).get("pages", {}).values()]
    return [x for x in r if allowed(x["license"])][:n]


def fetch(title: str, dst: Path, width: int = 1920) -> dict:
    d = _get({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "size|url|extmetadata", "iiurlwidth": width, "iiextmetadatafilter": "LicenseShortName|Artist"})
    m = _meta(next(iter(d["query"]["pages"].values())))
    if not allowed(m["license"]):
        raise RuntimeError(f"재사용할 수 없는 라이선스입니다: {m['license']}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(_open(m["thumb"] or m["url"]))
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("search"); a.add_argument("query"); a.add_argument("--n", type=int, default=10)
    b = sub.add_parser("fetch"); b.add_argument("sid"); b.add_argument("name"); b.add_argument("title"); b.add_argument("--width", type=int, default=1920)
    x = ap.parse_args()
    if x.cmd == "search":
        for r in search(x.query, x.n):
            print(json.dumps(r, ensure_ascii=False))
        return 0
    f = ROOT / "data" / "public" / "archive" / x.sid / f"{x.name}.jpg"
    print(json.dumps({**fetch(x.title, f, x.width), "file": str(f.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
