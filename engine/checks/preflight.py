#!/usr/bin/env python3
"""렌더 전 화면 검사 — 렌더가 쓸 프로젝트에서 장면마다 프레임만 찍어(렌더 없음 · LLM 없음) 빈 화면(D10)과 화면 끝 잘림을 잰다.

2026-11-19: 품질 관문 막음이 렌더 뒤에야 나와 고치고 다시 렌더하는 일이 여러 번 돌았다 → 렌더 전에 같은 값을 잰다.
2026-11-20: 처음엔 자막을 뺀 검사용 프로젝트를 따로 만들어 매번 약 25초(프로젝트 빌드)가 들었고, 한 편 내내 한 번도 막지 못했다.
  자막 · 제목 자리 겹침은 렌더 전 디자이너 검토(LLM)가 잡아 produce 가 렌더 전에 멈추므로, 여기서는 렌더와 같은 프로젝트를 쓴다
  (빌드는 렌더와 함께 쓰고 프레임만 몇 초).

  python3 engine/checks/preflight.py <id> [--at 0.6]
출력: 장면마다 평평한 면적 · 화면 끝 윤곽, 시트 한 장(이것만 Read). 막음(✗)은 품질 관문이 막을 것, 권고(△)는 확인할 것.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "story"))
sys.path.insert(0, str(ROOT / "engine" / "checks"))
from result import fail, ok  # noqa: E402

SIDE = 0.03            # 오른쪽 12% 띠 윤곽 밀도(권고) — 상자 테두리 · 그림이 걸친 건 괜찮아 막지 않는다
EDGE = 0.06            # 화면 끝 1.5% 띠 윤곽 밀도(막음)
FULL_BLEED = 0.55      # 화면 전체의 이만큼 넘게 내용이면 사진 · 녹화를 가득 깐 장면(끝에 닿는 게 정상)
RS = (0.15, 0.3, 0.5, 0.7, 0.88)   # 품질 관문(designcheck._frames)과 같은 자리 — 같은 값이 나오게


def measure(sid: str, at: float = 0.6) -> tuple[list[dict], Path]:
    import cv2
    import numpy as np
    from craft.renderer import adapter as A
    from designcheck import FLAT_BLOCK, flat_share
    from engines import make_job
    from knob import scene_span
    job = make_job(ROOT / "data" / "storyboards" / f"{sid}.json", None, None, False)   # 납품 설정 — 초안은 배경 질감 · 효과가 빠져 더 비어 보인다
    n = len(job.sb["scenes"])
    secs = []
    for i in range(n):
        start, sec = scene_span(job.sb, i)
        secs += [round(start + max(0.05, min(sec - 0.05, sec * r)), 3) for r in RS + (at,)]
    shots = A.snapshot(job, secs)
    per = len(RS) + 1
    rows, thumbs = [], []
    for i in range(n):
        grp = [cv2.imread(str(p)) for p in shots[i * per:(i + 1) * per]]
        if any(x is None for x in grp):
            continue
        img = grp[-1]
        # D10: 관문처럼 270×480 으로 줄여 5장 평균
        fs = sum(float(flat_share(cv2.cvtColor(cv2.resize(x, (270, 480), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)).mean()) for x in grp[:-1]) / len(RS)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        whole = float((~flat_share(gray)).mean())
        content = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((9, 9), np.uint8)) > 0   # 윤곽선 — 흰 카드 · 단색 도형도 잡힌다
        Hh, Ww = content.shape
        ya, yb = int(0.15 * Hh), int(0.80 * Hh)
        right = float(content[ya:yb, int(0.88 * Ww):int(0.985 * Ww)].mean())
        edge = max(float(content[ya:yb, :int(0.015 * Ww)].mean()), float(content[ya:yb, int(0.985 * Ww):].mean()))
        r = {"scene": i + 1, "flat": round(fs, 3), "content": round(whole, 3), "right": round(right, 3), "edge": round(edge, 3)}
        probs = []
        if fs > FLAT_BLOCK:
            probs.append(("✗", f"D10 빈 화면 — 평평한 면적 {fs * 100:.0f}%(관문 {FLAT_BLOCK * 100:.0f}% 넘으면 막음) → 재료를 키우거나 배경에 층 · 무늬"))
        if whole <= FULL_BLEED:
            if edge > EDGE:
                probs.append(("✗", f"화면 끝에 닿은 내용(윤곽 {edge * 100:.1f}%) — 잘려 보인다 → 양옆 여백 0.06 이상"))
            if right > SIDE:
                probs.append(("△", f"오른쪽 12%(좋아요 · 댓글 버튼 자리)에 윤곽 {right * 100:.1f}% — 글자 · 라벨이 걸치면 x 0.86 안으로"))
        r["problems"] = probs
        rows.append(r)
        t = cv2.resize(img, (270, 480))
        mark = "X" if any(x[0] == "✗" for x in probs) else "!" if probs else "ok"
        cv2.putText(t, f"{i + 1} {mark}", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255) if probs else (0, 180, 0), 2)
        thumbs.append(t)
    out = ROOT / "data" / "workspace" / "stills" / sid / "preflight.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    if thumbs:
        cols = 4
        blank = np.zeros_like(thumbs[0])
        while len(thumbs) % cols:
            thumbs.append(blank)
        cv2.imwrite(str(out), np.vstack([np.hstack(thumbs[k:k + cols]) for k in range(0, len(thumbs), cols)]), [cv2.IMWRITE_JPEG_QUALITY, 82])
    return rows, out


def main() -> int:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        print(__doc__); return 2
    at = float(sys.argv[sys.argv.index("--at") + 1]) if "--at" in sys.argv else 0.6
    t0 = time.time()
    try:
        rows, sheet = measure(a[0], at)
    except Exception as e:  # noqa: BLE001
        fail("preflight", stage="snapshot", error=str(e)[:300])
    hard = 0
    for r in rows:
        for m, msg in r["problems"]:
            hard += m == "✗"
            print(f"{m} 장면{r['scene']} {msg}")
    rel = str(sheet.relative_to(ROOT))
    (ROOT / "data" / "workspace" / "tmp" / a[0]).mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "workspace" / "tmp" / a[0] / "preflight.json").write_text(json.dumps({"rows": rows, "hard": hard}, ensure_ascii=False, indent=1), "utf-8")
    ok("preflight", hard=str(hard), sheet=rel, media=[f"{rel} | 렌더 전 화면"], sec=str(round(time.time() - t0, 1)),
       next=("✗ 를 모두 한 번에 고친 뒤 전체 produce" if hard else "전체 produce"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
