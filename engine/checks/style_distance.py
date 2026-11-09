#!/usr/bin/env python3
"""화풍 거리 — 이 영상의 초안 정지 화면이 최근 영상들과 얼마나 닮았나(로컬 CLIP 이미지 임베딩, 무료 · 장당 약 0.05초).
값으로 고치는 방식(knob.py)은 스타일을 정하지 않지만, 초안을 만들 때 지난 영상의 요소를 다시 쓰면 영상들이 비슷해질 수 있다 —
너무 닮았으면 produce 결과에 알린다(막지 않음).

  python3 engine/checks/style_distance.py <id> [--recent 5]   → {"nearest": <영상 id>, "similarity": 0~1, "per_video": {...}}
비교: 장면마다 그 영상의 가장 닮은 장면과의 코사인 유사도를 재고 평균 — 영상끼리의 모습 거리. 0.82 넘으면 거의 같은 모습(같은 영상끼리 약 0.87 · 다른 영상 약 0.65).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
STILLS = ROOT / "data" / "workspace" / "stills"
TOO_CLOSE = 0.82          # 2026-11-10 실측: 다른 영상 0.65 · 같은 영상 다른 시각 0.87


def embed(files: list[Path]) -> np.ndarray:
    from PIL import Image
    import vision_tags as V
    S = V._load()
    out = []
    for f in files:
        with Image.open(f) as im:
            e = S["vis"].run(None, {"pixel_values": V._pixels(im)})[0][0]
        out.append(e / np.linalg.norm(e))
    return np.stack(out) if out else np.zeros((0, 512), np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    if not len(a) or not len(b):
        return 0.0
    return float((a @ b.T).max(axis=1).mean())


def check(sid: str, recent: int = 5) -> dict:
    mine = sorted((STILLS / sid).glob("draft-s*.png"))
    if not mine:
        return {"skipped": "초안 정지 화면 없음"}
    others = sorted((d for d in STILLS.iterdir() if d.is_dir() and d.name != sid and any(d.glob("draft-s*.png"))),
                    key=lambda d: d.stat().st_mtime, reverse=True)[:recent] if STILLS.exists() else []
    if not others:
        return {"skipped": "비교할 지난 영상 없음"}
    a = embed(mine)
    per = {d.name: round(similarity(a, embed(sorted(d.glob("draft-s*.png")))), 3) for d in others}
    near = max(per, key=per.get)
    return {"nearest": near, "similarity": per[near], "per_video": per, "too_close": per[near] >= TOO_CLOSE}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id"); ap.add_argument("--recent", type=int, default=5)
    a = ap.parse_args()
    print(json.dumps(check(a.id, a.recent), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
