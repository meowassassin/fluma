#!/usr/bin/env python3
"""렌더 전 화면 검사 — 장면마다 정지 화면 한 장(자막 · 고정 제목을 뺀 내용만)으로 빈 화면(D10)과 자막 · 제목 자리에 깔린 내용을 잰다.

2026-11-19 실측: 품질 관문 막음(빈 화면 · 자막에 가린 그림 · 제목에 가린 문서)은 렌더 뒤 검토(LLM 1분)에서야 나와,
장면 코드를 고치고 다시 렌더하는 일이 여러 번 돌았다(제작 뒤 27분). 렌더 없이 장면 프레임만 찍어 같은 문제를 먼저 본다.

  python3 engine/checks/preflight.py <id> [--at 0.6]
출력: 장면마다 평평한 면적 · 자막 자리 · 제목 자리에 든 내용 비율, 겹침 구역을 빨갛게 그린 시트 한 장(이것만 Read).
막음(✗)은 품질 관문이 막을 것(D10) · 큰 겹침, 권고(△)는 확인할 것. 사진 · 녹화를 화면 가득 깐 장면은 자막 밑에 그림이 깔리는 게 정상이다.
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

# 자막 · 제목 자리 안 윤곽선 밀도(9px 로 굵힌 가장자리의 면적 비율) — 2026-11-19 실측: 제목에 걸친 문서 0.065 · 고친 뒤 0.0,
# 통과한 영상들 0~0.06(자막 띠가 더 넓어 같은 물체도 값이 작다)
UNDER = {"title": (0.055, 0.02), "subs": (0.08, 0.03)}     # (막음, 권고)
SIDE = 0.03            # 오른쪽 12% 띠 윤곽 밀도(권고)
EDGE = 0.06            # 화면 끝 1.5% 띠
FULL_BLEED = 0.55      # 화면 전체의 이만큼 넘게 내용이면 사진 · 녹화를 가득 깐 장면(자막 밑 그림이 정상)


def _band(mask, y0: float, y1: float):
    h = mask.shape[0]
    a, b = max(0, int(y0 * h)), min(h, int(y1 * h) + 1)
    return float(mask[a:b].mean()) if b > a else 0.0


def measure(sid: str, at: float = 0.6) -> tuple[list[dict], Path]:
    import cv2
    import numpy as np
    from craft import motion
    from craft.renderer import adapter as A
    from designcheck import FLAT_BLOCK, flat_share
    from engines import make_job
    from knob import scene_span
    sp = ROOT / "data" / "storyboards" / f"{sid}.json"
    job = make_job(sp, None, None, False)      # 초안(draft)은 배경 질감 · 효과를 빼서 관문보다 15~25% 더 비어 보였다 — 납품 설정으로 찍는다
    zones = motion.overlay_zones(job.sb)
    d0, proj0, man0 = A.paths(job)
    pre = d0 / "preflight"
    A.paths = lambda j: (pre, pre / "motion" / f"{j.sb['id']}.ecproj", pre / "craft.json")   # 진짜 프로젝트를 건드리지 않게 따로 만든다
    motion.NO_OVERLAY = True
    n = len(job.sb["scenes"])
    RS = (0.15, 0.3, 0.5, 0.7, 0.88)          # 품질 관문(designcheck._frames)과 같은 자리 — 같은 값이 나오게
    secs = []
    for i in range(n):
        start, sec = scene_span(job.sb, i)
        secs += [round(start + max(0.05, min(sec - 0.05, sec * r)), 3) for r in RS]
        secs.append(round(start + max(0.05, min(sec - 0.05, sec * at)), 3))
    shots = A.snapshot(job, secs)
    rows, thumbs = [], []
    per = len(RS) + 1
    for i in range(n):
        grp = [cv2.imread(str(p)) for p in shots[i * per:(i + 1) * per]]
        if any(x is None for x in grp):
            continue
        img = grp[-1]
        # D10: 관문처럼 270×480 으로 줄여 5장 평균 / 겹침: 원본 크기 한 장(블록이 커지면 띠 옆 글자가 띠 안으로 번진다)
        def _flat(x):          # 영상에선 자막 · 제목 상자가 그 띠를 채운다(관문은 그걸 내용으로 센다) — 뺀 띠는 내용으로 친다
            m = flat_share(cv2.cvtColor(cv2.resize(x, (270, 480), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)).copy()
            hh, ww = m.shape
            for kz, (y0, y1) in zones.items():
                if kz == "letterbox":
                    continue
                x0, x1 = (int(ww * 0.12), int(ww * 0.88)) if kz == "subs" else (int(ww * 0.2), int(ww * 0.8))
                m[int(y0 * hh):int(y1 * hh) + 1, x0:x1] = False
            return float(m.mean())
        fs = sum(_flat(x) for x in grp[:-1]) / len(RS)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        whole = float((~flat_share(gray)).mean())
        # 겹침은 무늬가 아니라 윤곽선으로 — 흰 문서 카드 · 단색 도형은 무늬가 없어 '빈 곳'으로 세어졌다(2026-11-19: 제목에 가린 문서를 놓침)
        content = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((9, 9), np.uint8)) > 0
        r = {"scene": i + 1, "flat": round(fs, 3), "content": round(whole, 3), "under": {}}
        full = whole > FULL_BLEED
        for k, (y0, y1) in zones.items():
            if k == "letterbox":
                continue
            r["under"][k] = round(_band(content, y0, y1), 3)
        probs = []
        if fs > FLAT_BLOCK - 0.03:     # 관문보다 조금 일찍(이 값은 관문보다 평균 0.04 낮게 나온다 — 2026-11-19 두 편 실측)
            probs.append(("✗", f"D10 빈 화면 — 평평한 면적 {fs * 100:.0f}%(관문 {FLAT_BLOCK * 100:.0f}% 넘으면 막음) → 재료를 키우거나 배경에 층 · 무늬"))
        for k, v in r["under"].items():
            name = "자막" if k == "subs" else "고정 제목"
            hi, lo = UNDER.get(k, (0.08, 0.03))
            if v > hi and not full:
                probs.append(("✗", f"{name} 자리에 윤곽 {v * 100:.1f}% — 그림 · 글자가 {name}에 가린다 → 재료를 {name} 자리 밖으로(adjust.dy · scale, 장면 코드 y)"))
            elif v > lo and not full:
                probs.append(("△", f"{name} 자리에 윤곽 {v * 100:.1f}% — 끝부분이 걸치는지 시트에서 확인"))
        # 좌우: 오른쪽 12% 는 좋아요 · 댓글 버튼 자리, 화면 끝 1.5% 에 닿으면 잘려 보인다(2026-11-19 검토 D21 '안전 영역' · '잘림' — 렌더 뒤에야 나와 다시 렌더)
        Hh, Ww = content.shape
        ya, yb = int(0.15 * Hh), int(0.80 * Hh)
        right = float(content[ya:yb, int(0.88 * Ww):int(0.985 * Ww)].mean())
        edge = max(float(content[ya:yb, :int(0.015 * Ww)].mean()), float(content[ya:yb, int(0.985 * Ww):].mean()))
        r["right"], r["edge"] = round(right, 3), round(edge, 3)
        if not full:
            if right > SIDE:      # 권고만 — 상자 테두리 · 그림이 걸친 건 괜찮고, 글자 · 라벨이면 고친다(윤곽만으로는 구분이 안 됨, 2026-11-19 완성본 3장면이 상자 테두리로 걸림)
                probs.append(("△", f"오른쪽 12%(좋아요 · 댓글 버튼 자리)에 윤곽 {right * 100:.1f}% — 글자 · 라벨이 걸치면 x 0.86 안으로(장면 코드 배치 폭 · adjust.dx)"))
            if edge > EDGE:
                probs.append(("✗", f"화면 끝에 닿은 내용(윤곽 {edge * 100:.1f}%) — 잘려 보인다 → 양옆 여백 0.06 이상"))
        r["problems"] = probs
        rows.append(r)
        t = img.copy()
        h, w = t.shape[:2]
        for k, (y0, y1) in zones.items():
            ov = t.copy()
            cv2.rectangle(ov, (0, int(y0 * h)), (w, int(y1 * h)), (40, 40, 230), -1)
            t = cv2.addWeighted(ov, 0.28, t, 0.72, 0)
        mark = "✗" if any(x[0] == "✗" for x in probs) else "△" if probs else "ok"
        cv2.putText(t, f"{i + 1} {mark if mark != '✗' else 'X'}", (24, 90), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255) if probs else (0, 180, 0), 6)
        thumbs.append(cv2.resize(t, (270, 480)))
    out = ROOT / "data" / "workspace" / "stills" / sid / "preflight.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    if thumbs:
        cols = 4
        blank = np.zeros_like(thumbs[0])
        while len(thumbs) % cols:
            thumbs.append(blank)
        sheet = np.vstack([np.hstack(thumbs[k:k + cols]) for k in range(0, len(thumbs), cols)])
        cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
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
    ok("preflight", hard=str(hard), sheet=rel, media=[f"{rel} | 렌더 전 화면(빨간 띠 = 자막 · 제목 자리)"], sec=str(round(time.time() - t0, 1)),
       next=("✗ 를 모두 한 번에 고친 뒤 전체 produce" if hard else "전체 produce"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
