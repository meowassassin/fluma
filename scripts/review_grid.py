#!/usr/bin/env python3
"""검토 격자 — 렌더한 영상을 일정 간격 프레임으로 모으고, 칸마다 그 순간 말하는 단어를 붙인다. '다 됐다'는 직접 본 뒤에만.

  python3 scripts/review_grid.py storyboards/<id>.json                       # 최근 렌더(초안 포함) 전체, 0.5초 간격
  python3 scripts/review_grid.py storyboards/<id>.json --from 4 --to 9 --step 0.25 --video out/….mp4

보는 법(에이전트): 격자를 Read 로 열어 장면마다 ①무엇이 주인공인지(실제 화면 · 사람 · 실사 · 그래픽) ②말한 단어에 맞춰
바뀌는지(등장이 아니라 '변화') ③같은 틀 · 같은 등장이 되풀이되는지 ④글자가 폰 크기에서 읽히는지 보고, 고칠 곳을 적는다.
결과: workspace/render/<id>/review-<from>-<to>.jpg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ["/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/System/Library/Fonts/AppleSDGothicNeo.ttc", "C:/Windows/Fonts/malgunbd.ttf"]


def font(size: int):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("--video")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--cols", type=int, default=8)
    a = ap.parse_args()
    sb = json.loads(Path(a.storyboard).read_text(encoding="utf-8"))
    sid = sb["id"]
    vids = sorted((ROOT / "out").glob(f"{sid}-*.mp4"), key=lambda p: p.stat().st_mtime)
    video = Path(a.video) if a.video else (vids[-1] if vids else None)
    if not video or not video.exists():
        sys.exit("렌더한 영상이 없습니다 — render.py --draft 먼저")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout or 0)
    t1 = min(a.t1 or dur, dur)
    cp = ROOT / "public" / "audio" / f"{sid}.captions.json"
    words = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else []
    starts, acc = [], 0.0
    for s in sb.get("scenes", []):
        starts.append(acc); acc += float(s.get("sec") or 0)
    times = []
    t = a.t0
    while t < t1 - 1e-3:
        times.append(round(t, 2)); t += a.step
    cells = []
    W, H = 216, 384
    f_big, f_small = font(20), font(15)
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            fp = Path(tmp) / f"f{i:04d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={W}:{H}", str(fp)], check=True)
            im = Image.open(fp).convert("RGB")
            c = Image.new("RGB", (W, H + 58), (24, 24, 28)); c.paste(im, (0, 0))
            d = ImageDraw.Draw(c)
            sc = max([k for k, st in enumerate(starts) if t >= st - 1e-6] or [0])
            said = " ".join(w["text"].strip() for w in words if w["startMs"] / 1000 <= t + 0.25 and w["endMs"] / 1000 >= t - 0.25)
            d.text((6, H + 4), f"{t:.2f}s · 장면 {sc + 1}", fill=(255, 220, 90), font=f_small)
            d.text((6, H + 26), (said or "—")[:16], fill=(240, 240, 240), font=f_big)
            cells.append(c)
    cols = a.cols
    sheet = Image.new("RGB", (W * cols, (H + 58) * ((len(cells) + cols - 1) // cols)), (12, 12, 14))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % cols) * W, (i // cols) * (H + 58)))
    out = ROOT / "workspace" / "render" / sid / f"review-{a.t0:g}-{t1:g}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    print(json.dumps({"ok": True, "grid": str(out.relative_to(ROOT)), "frames": len(cells), "video": str(video.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
