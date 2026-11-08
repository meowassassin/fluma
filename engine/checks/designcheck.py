#!/usr/bin/env python3
"""디자인 검사 — 렌더된 영상을 프레임으로 재서 'AI 티 · 싼 티' 신호를 찾는다. 콘티가 아니라 결과를 본다.

  python3 engine/checks/designcheck.py <영상.mp4> data/storyboards/<id>.json

잰다(장면마다, 사람이 보는 첫인상의 원인들):
  D10 빈 화면    무늬 없는 평평한 면적이 화면 대부분
  D11 멈춘 장면  장면 안에서 화면이 거의 안 변한다
  D12 작은 주인공  내용이 있는 영역이 화면의 일부뿐
  D13 같은 구도  이어진 장면의 윤곽이 거의 같다
  D14 기본 보라  채도 있는 색이 보라에 몰린다(AI 도구의 기본 색)
  D15 어두운 영상 영상 전체가 어둡다
숫자는 좋은 디자인을 보장하지 않는다 — 나쁜 신호를 거를 뿐이다. 통과한 뒤에도 사람이 본다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FLAT = 0.72          # D10: 평평한 칸 비율
STILL = 0.012        # D11: 바뀐 화소 비율(장면 평균)
SMALL = 0.30         # D12: 내용 상자 면적 비율
SAME = 0.82          # D13: 윤곽 상관
PURPLE = 0.55        # D14: 채도 있는 화소 중 보라 비율
DARK = 32            # D15: 평균 밝기


def _frames(video: Path, sb: dict):
    import cv2
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
    secs = [float(s.get("sec") or 0) for s in sb.get("scenes") or []]
    k = total / (sum(secs) or total)                     # 형식 최소 길이 등으로 늘어난 만큼 맞춘다
    out, t = [], 0.0
    long_ = []
    for s in secs:                                       # 원테이크처럼 긴 장면은 창으로 나눈다 — 가운데 한 장으로는 장면을 대표하지 못한다
        n = max(1, round(s * k / 5))
        long_ += [s * k / n] * n
    for d in long_:
        fs = []
        for r in (0.15, 0.3, 0.5, 0.7, 0.88):
            cap.set(cv2.CAP_PROP_POS_MSEC, (t + d * r) * 1000)
            ok, f = cap.read()
            if ok:
                fs.append(cv2.resize(f, (270, 480), interpolation=cv2.INTER_AREA))
        out.append((t, d, fs))
        t += d
    cap.release()
    return out


def flat_share(g):
    import numpy as np
    b = 12
    h, w = g.shape
    H, W = h // b, w // b
    std = g[:H * b, :W * b].reshape(H, b, W, b).astype(np.float32).std(axis=(1, 3))
    return std < 3.0


def measure(video: Path, sb: dict) -> list:
    import cv2
    import numpy as np
    rows, edges, sat_hue, lums = [], [], [], []
    for i, (t, d, fs) in enumerate(_frames(video, sb), 1):
        if not fs:
            continue
        gs = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in fs]
        mid = gs[len(gs) // 2]
        flats = [flat_share(g) for g in gs]
        flat = float(np.mean([f.mean() for f in flats]))
        still = float(np.mean([(cv2.absdiff(a, b) > 12).mean() for a, b in zip(gs, gs[1:])])) if len(gs) > 1 else 0.0
        box = 1.0
        ys, xs = np.nonzero(~flats[len(gs) // 2])
        if len(xs):
            box = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1) / flats[0].size
        else:
            box = 0.0
        e = cv2.Canny(cv2.resize(mid, (135, 240)), 60, 160).astype(np.float32).ravel()
        edges.append((i, e))
        hsv = cv2.cvtColor(fs[len(fs) // 2], cv2.COLOR_BGR2HSV)
        m = hsv[:, :, 1] > 70
        sat_hue.append(hsv[:, :, 0][m & (hsv[:, :, 2] > 50)])
        lums.append(float(mid.mean()))
        rows.append({"scene": i, "at": round(t, 1), "sec": round(d, 1), "flat": round(flat, 3), "change": round(still, 4), "box": round(float(box), 3), "lum": round(lums[-1], 1)})
    out = []
    for r in rows:
        if r["flat"] > FLAT:
            out.append(("D10", r["scene"], f"빈 화면 — 평평한 면적 {r['flat'] * 100:.0f}%"))
        if r["change"] < STILL and r["sec"] >= 2:
            out.append(("D11", r["scene"], f"멈춘 장면 — {r['sec']}초 동안 바뀐 화소 {r['change'] * 100:.1f}%"))
        if r["box"] < SMALL:
            out.append(("D12", r["scene"], f"작은 주인공 — 내용 상자가 화면의 {r['box'] * 100:.0f}%"))
    for (a, x), (b, y) in zip(edges, edges[1:]):
        if x.std() and y.std():
            c = float(np.corrcoef(x, y)[0, 1])
            if c > SAME:
                out.append(("D13", b, f"같은 구도 — {a}장면과 윤곽 상관 {c:.2f}"))
    hs = np.concatenate(sat_hue) if sat_hue else np.array([])
    purple = float(((hs >= 118) & (hs <= 150)).mean()) if hs.size > 500 else 0.0
    if purple > PURPLE:
        out.append(("D14", None, f"기본 보라 — 채도 있는 색의 {purple * 100:.0f}%"))
    lum = float(np.mean(lums)) if lums else 255.0
    if lum < DARK:
        out.append(("D15", None, f"어두운 영상 — 평균 밝기 {lum:.0f}/255"))
    return [{"code": c, "scene": s, "msg": m} for c, s, m in out] + [{"rows": rows}]


def findings(video: Path, sb: dict) -> list:
    return [x for x in measure(video, sb) if "code" in x]


def main() -> int:
    v, sp = Path(sys.argv[1]), Path(sys.argv[2])
    r = measure(v, json.loads(sp.read_text("utf-8")))
    for x in r:
        if "rows" in x:
            for w in x["rows"]:
                print(w)
        else:
            print(x["code"], f"{x['scene']}장면" if x["scene"] else "전체", x["msg"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
