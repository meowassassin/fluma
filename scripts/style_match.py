#!/usr/bin/env python3
"""우리 정지 화면이 참고 쇼츠 그림체에 얼마나 가까운지 숫자로 잰다(그림 · 카툰 레퍼런스용).

  python3 scripts/style_match.py <참고 영상 id> <우리 png ...> [--at 3,12,25] [--out 파일.jpg]

참고 영상(public/trends/xray/<id>/src.mp4)에서 --at 초(기본: 고르게 5장)를 뽑아 평균을 내고,
우리 그림마다 같은 값을 재서 차이를 보여 준다. 나란히 놓은 비교 그림도 만든다(--out).

재는 것 (모두 0~1)
  bright   평균 밝기             — 쿠르츠게작트는 밝다(밝은 하늘 · 쨍한 원색)
  sat      평균 채도             — 원색 위주인지
  subject  주인공 크기           — 바탕색과 다른 픽셀 중 가장 큰 덩어리의 화면 비율
  detail   잔무늬 밀도           — 윤곽선 픽셀 비율(풀결 · 물결선 · 반짝이 같은 작은 무늬)
  palette  팔레트 거리           — 두 그림의 대표색 6개 사이 평균 거리(작을수록 비슷)
점수 score = 1 − 2 × 평균 차이. 통과 pass = 고칠 점(hints)이 하나도 없을 때 — 점수만으로 넘기지 않는다.

참고 영상의 그림을 따라 그리거나 따오는 데 쓰지 않는다 — 숫자만 비교한다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
W = 270  # 재는 크기(세로 화면 1080 의 1/4)


def load(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGB")
    return im.resize((W, round(W * im.height / im.width)))


def frames(vid: str, at: list[float] | None) -> list[Image.Image]:
    src = ROOT / "public" / "trends" / "xray" / vid / "src.mp4"
    if not src.exists():
        raise SystemExit(f"참고 영상이 없습니다: {src} (트렌드에서 분해를 먼저)")
    if not at:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                                   capture_output=True, text=True).stdout.strip() or 10)
        at = [round(dur * k / 6, 2) for k in range(1, 6)]
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, t in enumerate(at):
            f = Path(d) / f"{i}.png"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1", str(f)], check=True)
            out.append(load(f))
    return out


def palette(im: Image.Image, k: int = 6) -> np.ndarray:
    q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = np.array(q.getpalette()[: k * 3], dtype=float).reshape(-1, 3) / 255
    return pal


def measure(im: Image.Image) -> dict:
    a = np.asarray(im, dtype=float) / 255
    hsv = np.asarray(im.convert("HSV"), dtype=float) / 255
    edges = np.asarray(im.convert("L").filter(ImageFilter.FIND_EDGES), dtype=float) / 255
    # 바탕색 = 가장 흔한 대표색. 그와 먼 픽셀 중 가장 큰 연결 덩어리 = 주인공
    pal = palette(im)
    q = np.asarray(im.quantize(colors=6, method=Image.Quantize.MEDIANCUT))
    bg = np.bincount(q.ravel()).argmax()
    fg = np.linalg.norm(a - pal[bg], axis=2) > 0.18
    subject = biggest(fg) / fg.size
    return {"bright": float(hsv[..., 2].mean()), "sat": float(hsv[..., 1].mean()), "subject": float(subject),
            "detail": float((edges > 0.12).mean()), "_pal": pal}


def biggest(mask: np.ndarray) -> int:
    """4-연결 덩어리 중 가장 큰 것의 픽셀 수 (작은 그림이라 단순 탐색).
    왼쪽 끝부터 오른쪽 끝까지 닿는 덩어리(바닥 · 하늘 띠)는 주인공이 아니라 배경 층이라 뺀다"""
    seen = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    best = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]; seen[y0, x0] = True; n = 0; left = right = False
        while stack:
            y, x = stack.pop(); n += 1
            left |= x == 0; right |= x == w - 1
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; stack.append((yy, xx))
        if not (left and right):
            best = max(best, n)
    return best


def pal_dist(p: np.ndarray, q: np.ndarray) -> float:
    d = np.linalg.norm(p[:, None, :] - q[None, :, :], axis=2)
    return float((d.min(axis=1).mean() + d.min(axis=0).mean()) / 2 / np.sqrt(3))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vid"); ap.add_argument("ours", nargs="+")
    ap.add_argument("--at", help="참고 영상에서 뽑을 초, 쉼표로")
    ap.add_argument("--out", help="나란히 놓은 비교 그림(jpg)")
    a = ap.parse_args()
    refs = frames(a.vid, [float(x) for x in a.at.split(",")] if a.at else None)
    rm = [measure(r) for r in refs]
    ref = {k: float(np.mean([m[k] for m in rm])) for k in ("bright", "sat", "subject", "detail")}
    ref_pal = np.concatenate([m["_pal"] for m in rm])
    rows = []
    for p in a.ours:
        im = load(Path(p)); m = measure(im)
        diff = {k: round(m[k] - ref[k], 3) for k in ref}
        pd = pal_dist(m["_pal"], ref_pal)
        score = 1 - 2 * float(np.mean([abs(v) for v in diff.values()] + [pd]))
        hints = []
        if diff["bright"] < -0.12: hints.append("더 밝게 — 참고는 밝은 바탕 · 쨍한 색")
        if diff["sat"] < -0.1: hints.append("채도 올리기 — 회색 · 남색 대신 원색")
        if m["subject"] < ref["subject"] * 0.5: hints.append("주인공을 크게 · 한 덩어리로 — 바탕과 확실히 다른 색의 큰 형태 하나")
        if diff["detail"] < -0.02: hints.append("작은 무늬 더하기 — 풀결 · 물결선 · 반짝이")
        if diff["detail"] > 0.04: hints.append("잡동사니 줄이기 — 알약 · 상자 · 선이 너무 많음")
        if pd > 0.18: hints.append("팔레트를 참고 대표색 쪽으로")
        rows.append({"file": p, "score": round(score, 3), "pass": not hints, "ours": {k: round(m[k], 3) for k in ref}, "diff": diff, "palette_dist": round(pd, 3), "hints": hints})
    print(json.dumps({"ref": {k: round(v, 3) for k, v in ref.items()}, "frames": rows}, ensure_ascii=False, indent=1))
    if a.out:
        tiles = refs[:3] + [load(Path(p)) for p in a.ours[:3]]
        h = max(t.height for t in tiles)
        sheet = Image.new("RGB", (W * len(tiles), h), (20, 20, 20))
        for i, t in enumerate(tiles):
            sheet.paste(t, (i * W, 0))
        sheet.save(a.out, quality=88)
        print(f"비교 그림: {a.out} (왼쪽 {min(3, len(refs))}장 참고 · 오른쪽 우리)", file=sys.stderr)


if __name__ == "__main__":
    main()
