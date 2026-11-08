#!/usr/bin/env python3
"""유행 음원 찾기 — 같은 분야 쇼츠들이 '지금 실제로 붙이는 곡'을 모은다(쇼츠 화면 아래 사운드 표시 · 조회수 가중).

  python3 engine/research/trend_music.py "고양이 레전드" "funny cat moments" [--n 25] [--out data/public/trends/music/<이름>.json]

- 후보: yt-dlp 검색(#shorts) → 쇼츠 페이지의 사운드 표시(soundAttributionTitle)
- '오리지널 사운드 · Original sound'(영상에 직접 넣은 소리)는 곡이 아니라 뺀다. 남는 것 = 유튜브 쇼츠 오디오 라이브러리에서 붙인 곡
  → 업로드 때 쇼츠 편집기에서 같은 이름으로 검색해 붙이면 저작권 · 수익 문제가 없다(유튜브가 라이선스를 가진 곡)
- 결과: 곡마다 쓴 쇼츠 수 · 조회수 합 · 예시 쇼츠. 조회수 합 순
요청은 천천히(쇼츠마다 1초 쉼) — 페이지만 읽고 영상은 받지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
YTDLP = str(ROOT / ".venv" / "bin" / "yt-dlp") if (ROOT / ".venv" / "bin" / "yt-dlp").exists() else "yt-dlp"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
ORIGINAL = re.compile(r"오리지널 사운드|원본 사운드|original sound|original audio", re.I)


def search(q: str, n: int) -> list[dict]:
    """유튜브 검색의 쇼츠 칸(trends.py 와 같은 방식 — yt-dlp 는 쇼츠 칸을 거의 못 읽는다)"""
    sys.path.insert(0, str(ROOT / "engine" / "research"))
    import trends as TR
    try:
        return [{"id": v["id"], "title": v.get("title"), "views": v.get("views") or 0} for v in TR.search(q, n)]
    except Exception:  # noqa: BLE001
        return []


def sound_of(vid: str) -> str | None:
    r = subprocess.run(["curl", "-s", "-L", "-m", "30", "-A", UA, "-H", "Accept-Language: ko-KR,ko;q=0.9,en;q=0.6", f"https://www.youtube.com/shorts/{vid}"], capture_output=True, text=True)
    s = r.stdout
    m = re.search(r'soundAttributionTitle":\{"content":"((?:[^"\\]|\\.)*)"', s) or re.search(r'soundAttributionTitle\\x22:\\x7b\\x22content\\x22:\\x22(.*?)\\x22', s)
    if not m:
        return None
    t = m.group(1)
    try:
        t = json.loads(f'"{t}"')
    except ValueError:
        pass
    return t.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="+"); ap.add_argument("--n", type=int, default=25); ap.add_argument("--out")
    a = ap.parse_args()
    seen, rows = set(), []
    for q in a.queries:
        for v in search(q, a.n):
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            v["sound"] = sound_of(v["id"]); v["query"] = q
            rows.append(v)
            time.sleep(1.0)
    songs = defaultdict(lambda: {"shorts": 0, "views": 0, "examples": []})
    for v in rows:
        s = v.get("sound")
        if not s or ORIGINAL.search(s):
            continue
        g = songs[s]; g["shorts"] += 1; g["views"] += v["views"]
        if len(g["examples"]) < 3:
            g["examples"].append({"id": v["id"], "title": v["title"], "views": v["views"]})
    top = sorted(({"sound": k, **g} for k, g in songs.items()), key=lambda x: (-x["views"], -x["shorts"]))
    res = {"queries": a.queries, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "scanned": len(rows),
           "original_sound": sum(1 for v in rows if v.get("sound") and ORIGINAL.search(v["sound"])), "unknown": sum(1 for v in rows if not v.get("sound")), "songs": top}
    out = Path(a.out) if a.out else ROOT / "data" / "public" / "trends" / "music" / (re.sub(r"[^0-9A-Za-z가-힣]+", "-", a.queries[0]).strip("-")[:40] + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), "utf-8")
    print(f"[trend_music] 쇼츠 {len(rows)}편 · 직접 넣은 소리 {res['original_sound']} · 모름 {res['unknown']} · 라이브러리 곡 {len(top)}개 → {out.relative_to(ROOT)}")
    for i, s in enumerate(top[:15], 1):
        print(f"{i:2d}. {s['sound'][:60]:60s} 쇼츠 {s['shorts']} · 조회 {s['views']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
