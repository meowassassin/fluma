#!/usr/bin/env python3
"""결과 미리보기 — 그림(SVG) · 영상 · 이미지를 PNG 로 만들어 에이전트가 직접 보고(Read), 채팅에 그대로 띄울 블록을 출력한다.
사용자에게 '렌더해 주세요 · 이 경로를 열어 보세요' 를 부탁하지 않기 위해서(ImageMagick · 승인 없이 된다).

  python3 engine/core/preview.py <파일> [<파일> …] [--at 1.5,4,8] [--width 1080]
    .svg             → 같은 이름 .png (Chromium 으로 그대로 렌더 — 글꼴 · 필터 포함)
    .mp4 · .mov …    → --at 초마다 정지 화면 <이름>-<초>s.png (없으면 처음 · 가운데 · 끝)
    .png · .jpg …    → 그대로
마지막에 ```media 블록을 출력한다 — 답에 그대로 붙이면 채팅에 그림 · 영상이 바로 뜬다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VID = (".mp4", ".mov", ".webm", ".m4v")


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def svg_png(svg: Path, width: int) -> Path:
    """SVG 를 HTML 안에 넣어 요소만 찍는다(SVG 문서를 직접 열어 찍으면 Chromium 이 멈춘다). 크기가 없으면 width 에 맞춤"""
    from playwright.sync_api import sync_playwright
    out = svg.with_suffix(".png")
    html = ("<!doctype html><meta charset=utf-8><style>html,body{margin:0;background:#fff}"
            f"#v{{display:inline-block}}#v>svg{{display:block;max-width:{width}px;height:auto}}</style>"
            f"<div id=v>{svg.read_text('utf-8', errors='replace')}</div>")
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": width})
        pg.set_content(html, wait_until="load")
        pg.locator("#v > svg").first.screenshot(path=str(out), timeout=15000)
        b.close()
    return out


def duration(v: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(v)], capture_output=True, text=True)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError):
        return 0.0


def video_frames(v: Path, at: list[float], width: int) -> list[Path]:
    d = duration(v)
    ts = at or [0.3, d / 2, max(0.0, d - 0.3)]
    outs = []
    for t in ts:
        o = v.with_name(f"{v.stem}-{t:g}s.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(v), "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2", str(o)], check=True)
        outs.append(o)
    return outs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--at", default="", help="영상: 정지 화면을 뽑을 초(쉼표)")
    ap.add_argument("--width", type=int, default=1080)
    a = ap.parse_args()
    at = [float(x) for x in a.at.split(",") if x.strip()]
    show: list[tuple[str, str]] = []      # (채팅에 띄울 경로, 설명)
    for f in a.files:
        p = Path(f)
        p = p if p.is_absolute() else ROOT / p
        if not p.exists():
            print(f"✗ 없음: {f}", file=sys.stderr)
            continue
        ext = p.suffix.lower()
        if ext == ".svg":
            o = svg_png(p, a.width)
            print(f"→ {rel(o)}  (Read 로 보기)")
            show.append((rel(o), p.stem))
        elif ext in VID:
            for o in video_frames(p, at, a.width):
                print(f"→ {rel(o)}  (Read 로 보기)")
            show.append((rel(p), p.stem))          # 채팅에는 영상 자체
        elif ext in IMG:
            show.append((rel(p), p.stem))
        else:
            show.append((rel(p), p.name))
    from result import fail, ok
    if not show:
        fail("preview", stage="files", error="보여 줄 파일이 없습니다(경로 확인)")
    print("\n채팅에 그대로 붙이기:\n```media")
    for s, c in show:
        print(f"{s} | {c}")
    print("```")
    ok("preview", media=[f"{s} | {c}" for s, c in show])


if __name__ == "__main__":
    sys.exit(main())
