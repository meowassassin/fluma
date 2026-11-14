#!/usr/bin/env python3
"""초안 · 레퍼런스 나란히 보기 — 에이전트(Claude Code)가 Read 로 직접 보는 프레임 모음 한 장.
위 줄: 내 초안(같은 간격 12장, 시각 · 장면 번호) · 아래 줄: 레퍼런스(같은 비율 시각의 프레임, X-ray 원본에서).
리듬(언제 화면이 바뀌나) · 구도(피사체 크기 · 여백) · 글자 크기 · 색을 같은 자리에서 견준다.

  python3 engine/checks/sheet.py <초안.mp4> data/storyboards/<id>.json [--n 12]
→ data/compositions/<id>/craft/review/sheet.png
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
XRAY = ROOT / "data" / "public" / "trends" / "xray"


def _dur(f: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _frame(f: Path, t: float, w: int):
    from PIL import Image
    import io
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(f), "-frames:v", "1", "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.stdout else None


def _font(size: int):
    from PIL import ImageFont
    for f in (ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf", Path("/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc")):
        try:
            return ImageFont.truetype(str(f), size)
        except Exception:
            continue
    return ImageFont.load_default()


def make(video: Path, sb: dict, n: int = 12, w: int = 150) -> Path:
    from PIL import Image, ImageDraw
    sid = sb["id"]
    dur = _dur(video)
    starts, acc = [], 0.0
    for s in sb.get("scenes") or []:
        starts.append(acc)
        acc += float(s.get("sec") or 0)
    rows = [("내 초안", video, dur, lambda t: f"S{sum(1 for x in starts if x <= t + 1e-6)} {t:.1f}s")]
    ref = next((XRAY / r / "src.mp4" for r in (sb.get("reference") or []) if isinstance(r, str) and (XRAY / r / "src.mp4").exists()), None)
    if ref:
        rows.append((f"레퍼런스 {ref.parent.name}", ref, _dur(ref), lambda t: f"{t:.1f}s"))
    h = int(w * 16 / 9)
    pad, head = 6, 26
    W = n * (w + pad) + pad + 120
    H = len(rows) * (h + head + pad) + pad
    sheet = Image.new("RGB", (W, H), (18, 18, 24))
    d = ImageDraw.Draw(sheet)
    fs, fl = _font(15), _font(17)
    for ri, (label, f, D, tag) in enumerate(rows):
        y = pad + ri * (h + head + pad)
        d.text((pad, y + head + h // 2 - 10), label, font=fl, fill=(235, 235, 240))
        for k in range(n):
            t = (k + 0.5) / n * D
            im = _frame(f, t, w)
            x = 120 + pad + k * (w + pad)
            if im is not None:
                sheet.paste(im.resize((w, h)), (x, y + head))
            d.text((x + 2, y + 4), tag(t), font=fs, fill=(200, 200, 210))
    out = ROOT / "data" / "compositions" / sid / "craft" / "review" / "sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("storyboard")
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    out = make(Path(a.video), json.loads(Path(a.storyboard).read_text("utf-8")), a.n)
    print(str(out.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
