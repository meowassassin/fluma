#!/usr/bin/env python3
"""레퍼런스 고르기 — 검색 결과 후보를 표 하나 + 썸네일 시트 한 장으로(2026-11-17).

전에는 에이전트가 plan.py trends 출력을 grep 으로 여러 번 다시 보고, 데이터 파일에서 id 를 찾고,
썸네일을 한 장씩 열어 봐서 레퍼런스 고르기에만 5~12분이 걸렸다. 이 명령 한 번 → 시트 한 장을 Read → 2~3편을 골라
`analyze_ref.py <id1> <id2> <id3>` 한 명령으로 분석한다.

  python3 engine/research/ref_pick.py --request <검색 요청 id>     # trends.py search 가 알려 준 r… id
  python3 engine/research/ref_pick.py --ids a b c                    # 이미 아는 후보
  python3 engine/research/ref_pick.py --label "<검색 이름>" --top 12
출력: 번호 · id · 조회수 · 화면 종류 · 제목 표, 시트 경로(data/workspace/look/pick/<이름>.jpg — 번호가 표와 같다)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
INDEX = ROOT / "data" / "public" / "trends" / "index.json"
VISUAL = {"screen": "화면", "2d": "2D", "live": "실사", "3d": "3D", "slides": "슬라이드", "meme": "밈"}


def candidates(a) -> list[dict]:
    items = json.loads(INDEX.read_text("utf-8")).get("items") or []
    if a.ids:
        by = {x["id"]: x for x in items}
        return [by[i] for i in a.ids if i in by]
    pick = [x for x in items if (a.request and x.get("request") == a.request) or (a.label and x.get("label") == a.label)]
    seen, out = set(), []
    for x in sorted(pick, key=lambda x: -(x.get("views") or 0)):
        if x["id"] not in seen:
            seen.add(x["id"]); out.append(x)
    return out[: a.top]


def sheet(rows: list[dict], name: str) -> Path | None:
    from PIL import Image, ImageDraw, ImageFont
    tw, th, cols = 180, 320, 6
    thumbs = []
    for x in rows:
        f = ROOT / "data" / "public" / (x.get("thumb") or f"trends/thumbs/{x['id']}.jpg")
        try:
            im = Image.open(f).convert("RGB")
        except OSError:
            im = Image.new("RGB", (tw, th), (40, 40, 40))
        im.thumbnail((tw, th)); canvas = Image.new("RGB", (tw, th), (20, 20, 20)); canvas.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
        thumbs.append(canvas)
    if not thumbs:
        return None
    rws = (len(thumbs) + cols - 1) // cols
    out = Image.new("RGB", (cols * tw, rws * th), (12, 12, 12))
    try:
        font = ImageFont.truetype(str(ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf"), 26)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(out)
    for k, (im, x) in enumerate(zip(thumbs, rows)):
        px, py = (k % cols) * tw, (k // cols) * th
        out.paste(im, (px, py))
        d.rectangle([px, py, px + 62, py + 36], fill=(255, 214, 10))
        d.text((px + 8, py + 2), str(k + 1), fill=(0, 0, 0), font=font)
    p = ROOT / "data" / "workspace" / "look" / "pick" / f"{name}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    out.save(p, quality=85)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--request"); ap.add_argument("--label"); ap.add_argument("--ids", nargs="*"); ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    if not (a.request or a.label or a.ids):
        ap.error("--request · --label · --ids 중 하나")
    rows = candidates(a)
    if not rows:
        print("후보가 없습니다 — trends.py search 를 먼저 돌리거나 요청 id 를 확인하세요"); return 1
    print("| # | id | 조회수 | 화면 | 훅 | 제목 |\n|---|---|---|---|---|---|")
    for k, x in enumerate(rows, 1):
        print(f"| {k} | {x['id']} | {x.get('views') or 0:,} | {VISUAL.get(x.get('visual'), x.get('visual') or '?')} | {x.get('hook') or ''} | {(x.get('title') or '')[:60]} |")
    p = sheet(rows, a.request or (a.label or "ids").replace(" ", "_")[:40])
    if p:
        print(f"\n썸네일 시트(번호 = 표의 #): {p.relative_to(ROOT)} — 이 한 장만 Read 로 보고 2~3편 골라 analyze_ref.py <id…> 한 명령으로")
    return 0


if __name__ == "__main__":
    sys.exit(main())
