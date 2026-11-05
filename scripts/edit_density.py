#!/usr/bin/env python3
"""편집 밀도 — 영상이 '슬라이드'인지 사람이 편집한 쇼츠인지 숫자로 잰다(같은 잣대로 사람 쇼츠 · 우리 렌더 둘 다).

  python3 scripts/edit_density.py <영상.mp4> [...]            # 숫자만
  python3 scripts/edit_density.py out/<id>-....mp4 --check storyboards/<id>.json   # 사람 쇼츠 기준과 비교, 모자라면 실패(종료 코드 1)
  python3 scripts/edit_density.py baseline                     # 받아 둔 사람 쇼츠(public/trends/xray/*/src.mp4) → presets/density.json

잰 것(사람 쇼츠와 '슬라이드'를 실제로 가르는 것 — 2026-11-02 사람 5편 · 우리 2편 비교에서 확인):
  text_px        화면 속 글자 높이 중앙값(1920 기준 px, OCR) — 사람 34~65, 페이지를 통째로 축소한 우리 데모 20. 말하는 부분을 잘라 크게 보여 주는지
  kinds          재료 종류 수(실제 화면 · 짤 · 사람 · 기사 · 도표 …, 1초마다 CLIP 분류) — 사람 대부분 5~6, 우리 데모 2
  kind_switch    10초당 재료 종류가 바뀌는 횟수 — 사람 대부분 2.4 이상, 우리 데모 1.1
아래 픽셀 숫자는 참고만(사람 쇼츠도 범위가 넓어 둘을 가르지 못했다):
  beats_per_10s  10초당 화면 변화 수 — 컷 · 확대 · 짤 삽입 · 강조 표시 · 글자 등장처럼 화면의 일부(1% 이상)가 새로 바뀌는 순간
  fill           화면 채움 — 16x9 칸 중 내용(무늬 · 글자 · 사진)이 있는 칸 비율의 중앙값. 작은 판을 가운데 띄우고 나머지가 빈 바탕이면 낮다
  longest_still  가장 오래 아무것도 안 바뀐 구간(초)
  cuts_per_10s   화면 대부분이 바뀌는 컷

왜(2026-11-02): 시험 영상이 '거의 슬라이드'였다 — 웹 페이지 전체를 작은 판에 축소(채움 3%), 문장마다 그림 한 장, 얹는 것 없음.
기존 검사는 '틀린 것'(기울기 · 글로우 · 겹침)만 봐서 빈약함을 못 잡았다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def measure(path: str, step: int = 3) -> dict:
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    prev, n, beats, cuts, active = None, 0, [], 0, False
    fills, last_change, longest = [], 0.0, 0.0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        n += 1
        if n % step:
            continue
        t = n / fps
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (180, 320))
        # 채움: 칸마다 경계(무늬 · 글자) 밀도 또는 밝기 변화가 있으면 '내용 있음'
        ed = cv2.Canny(g, 60, 140)
        cells = ed.reshape(16, 20, 9, 20).mean(axis=(1, 3))
        sd = g.reshape(16, 20, 9, 20).std(axis=(1, 3))
        fills.append(float(np.mean((cells > 6) | (sd > 18))))
        gf = g.astype(np.float32)
        if prev is not None:
            frac = float(np.mean(np.abs(gf - prev) > 20))
            ch = frac > 0.01
            if ch and not active:
                beats.append(t)
                if frac > 0.5:
                    cuts += 1
            if ch:
                longest = max(longest, t - last_change); last_change = t
            active = ch
        prev = gf
    dur = n / fps if n else 0
    longest = max(longest, dur - last_change)
    if not dur:
        return {"ok": False, "error": "프레임을 못 읽음"}
    return {"ok": True, "sec": round(dur, 1), "beats_per_10s": round(len(beats) / dur * 10, 1), "cuts_per_10s": round(cuts / dur * 10, 1),
            "fill": round(float(np.median(fills)), 2), "longest_still": round(longest, 1)}


def semantic(path: str) -> dict:
    """1초마다: 재료 종류(CLIP) · 화면 속 글자 높이(OCR)"""
    import os
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import vision_tags
    from rapidocr import RapidOCR
    ocr = RapidOCR(params={"Det.limit_type": "max", "Det.limit_side_len": 960})   # 작은 초안을 키워 읽지 않는다(글자 높이는 화면 비율로 잰다)
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    kinds, hs, d = [], [], tempfile.mkdtemp()
    # 0.5초마다 — 1초 간격이면 1.5초 남짓 나오는 짤을 건너뛰었다(2026-11-02 영어판에서 확인).
    # 재료 분류는 내용이 있는 곳만 잘라서: 검은 바탕 가운데 작은 판(짤 · 화면)을 프레임 통째로 보면 늘 '실제 화면'으로 나왔다
    step = 0.5
    # 처음부터 차례로 읽으며 필요한 프레임만 쓴다 — 프레임마다 위치를 옮기면(seek) 매번 앞 키프레임부터 다시 풀어 수십 초가 걸렸다(2026-11-05)
    want = [int((k * step + step / 2) * fps) for k in range(int(dur / step))]
    frames_at, idx = {}, 0
    for k, target in enumerate(want):
        while idx < target:
            if not cap.grab():
                break
            idx += 1
        ok, f = cap.read()
        idx += 1
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        rows, cols = (g.mean(axis=1) > 14).nonzero()[0], (g.mean(axis=0) > 14).nonzero()[0]
        crop = f[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1] if len(rows) > 20 and len(cols) > 20 else f
        fp = os.path.join(d, f"{k}.jpg"); cv2.imwrite(fp, crop)
        kinds.append(vision_tags.classify(fp)["kind"]); os.remove(fp)
        if k % 4 == 0:   # 글자 크기는 2초마다(OCR 이 무겁다 — 중앙값이라 2초면 충분)
            # 초마다 그 화면의 글자 크기(중앙값) 하나 — 글자 덩어리를 통째로 세면 작은 글자가 수백 개인 논문 한 화면이
            # 영상 전체 값을 끌어내렸다(2026-11-02). 시간으로 재야 '보는 사람이 읽는 크기'다
            r = ocr(f, use_cls=False, use_rec=False)   # 글자 높이만 필요 — 글자 읽기(인식)를 건너뛰면 7배 빠르다(1.9 → 0.27초/장, 2026-11-05)
            if r and r.boxes is not None and len(r.boxes):
                hs.append(float(np.median([(np.linalg.norm(b[3] - b[0]) + np.linalg.norm(b[2] - b[1])) / 2 / f.shape[0] * 1920 for b in r.boxes])))
    # 한 번 스친(0.5초) 분류는 잡음 — 이웃과 다르고 앞뒤가 같으면 앞뒤를 따른다
    kinds = [kinds[i - 1] if 0 < i < len(kinds) - 1 and kinds[i - 1] == kinds[i + 1] != kinds[i] else x for i, x in enumerate(kinds)]
    sw = sum(1 for x, y in zip(kinds, kinds[1:]) if x != y)
    return {"kinds": len(set(kinds)), "kind_list": sorted(set(kinds)), "kind_switch": round(sw / max(dur, 1) * 10, 1),
            "text_px": round(float(np.median(hs)), 0) if hs else None}


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "presets" / "density.json"
DEFAULT = {"text_px": 47, "kinds": 5, "kind_switch": 3.5}   # baseline 이 없을 때(2026-11-02 사람 쇼츠 5편 중앙값)


def ref_density(xid: str) -> dict | None:
    """참고 쇼츠 자체의 편집 밀도(분해할 때 받아 둔 원본이 있으면 재서 style/density.json 에 둔다)"""
    d = ROOT / "public" / "trends" / "xray" / str(xid)
    cp = d / "style" / "density.json"
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    src = d / "src.mp4"
    if not src.exists():
        return None
    m = {**measure(str(src)), **semantic(str(src))}
    m = {k: m.get(k) for k in ("text_px", "kinds", "kind_switch", "beats_per_10s", "fill", "longest_still")}
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return m


def base_of(sb: dict) -> dict:
    """기준: 참고 쇼츠가 있으면 그 영상에서 잰 값(꽁트처럼 재료가 한 종류인 형식에 정보 쇼츠 기준을 들이대지 않게, 2026-11-02),
    없으면 형식 프리셋 · 사람 쇼츠 중앙값(presets/density.json)"""
    b = dict(DEFAULT)
    if BASE.exists():
        b.update(json.loads(BASE.read_text(encoding="utf-8")).get("median") or {})
    b.update(((sb.get("preset") or {}).get("density")) or {})
    for r in sb.get("reference") or []:
        rd = ref_density(r)
        if rd:
            b.update({k: v for k, v in rd.items() if v is not None}); b["_from"] = f"참고 {r}"
            break
    return b


def check(m: dict, sb: dict) -> list[str]:
    """사람 쇼츠 기준(presets/density.json · 콘티 preset.density)과 비교 — 크게 모자라면 문제 목록"""
    b, probs = base_of(sb), []
    # 글자 하한: 사람 쇼츠 중앙값의 0.7배와 38px 중 작은 것 — 사람 쇼츠도 34px(코딩애플)까지 내려간다. 너무 높게 잡으면 화면을 과하게 당겨 답답해진다
    need_px = min(b["text_px"] * 0.7, 38)
    if m.get("text_px") is not None and m["text_px"] < need_px:
        probs.append(f"화면 속 글자가 작음 {int(m['text_px'])}px — 최소 {int(need_px)}px(사람 편집 중앙값 {int(b['text_px'])}px)(페이지 전체를 축소하지 말고 말하는 부분을 잘라 크게: K.web read)")
    short = m["sec"] < 15
    # 실제 화면 위주 영상(재료 70% 이상이 웹 녹화 · 화면 · 영상 · 스톡): 터미널 · 대화창 · 문서가 CLIP 으로는 모두 '실제 화면' 한 종류라
    # 종류 수 · 종류 전환으로 재면 늘 모자라게 나온다 → 화면 내용이 바뀐 횟수(beats)로 본다. 종류 구분은 lint L35 가 재료 기록으로 본다(2026-11-05)
    mats = [m_ for sc in sb.get("scenes") or [] for m_ in sc.get("materials") or [] if isinstance(m_, dict)]
    real = bool(mats) and sum(1 for m_ in mats if m_.get("type") in ("web", "screen", "video", "stock")) >= 0.7 * len(mats)
    if real:
        if m.get("beats_per_10s") is not None and m["beats_per_10s"] < b["kind_switch"] * 0.5:
            probs.append(f"화면이 10초에 {m['beats_per_10s']}번 바뀜 — 사람 편집 {b['kind_switch']}번(녹화 안에서 줄 · 말풍선 · 스크롤이 이어지게, 또는 녹화를 짧게 나눠)")
        if m["longest_still"] > 6:
            probs.append(f"{m['longest_still']}초 동안 화면이 그대로")
        return probs
    need_k = max(1, min(round(b["kinds"]), round(b["kinds"] * (0.4 if short else 0.6)) or 1))
    if m.get("kinds") is not None and m["kinds"] < need_k:
        probs.append(f"재료 종류 {m['kinds']}가지({', '.join(m.get('kind_list') or [])}) — 사람 편집 {b['kinds']}가지(실제 화면 사이에 짤 · 사람 · 기사 · 사진을 단어에 맞춰)")
    if m.get("kind_switch") is not None and m["kind_switch"] < b["kind_switch"] * 0.5:
        probs.append(f"재료가 10초에 {m['kind_switch']}번 바뀜 — 사람 편집 {b['kind_switch']}번(한 문장 안에서도 재료를 바꾸기: 콘티 beats)")
    if m["longest_still"] > 6:
        probs.append(f"{m['longest_still']}초 동안 화면이 그대로")
    return probs


def cmd_baseline():
    rows = []
    for v in sorted((ROOT / "public" / "trends" / "xray").glob("*/src.mp4")):
        m = {**measure(str(v)), **semantic(str(v))}
        rows.append({"video": v.parent.name, **{k: m.get(k) for k in ("sec", "text_px", "kinds", "kind_switch", "beats_per_10s", "fill", "longest_still")}})
        print(rows[-1], flush=True)
    med = {k: round(float(np.median([r[k] for r in rows if r.get(k) is not None])), 1) for k in ("text_px", "kinds", "kind_switch", "beats_per_10s", "fill", "longest_still")}
    BASE.parent.mkdir(parents=True, exist_ok=True)
    BASE.write_text(json.dumps({"measured": __import__("time").strftime("%Y-%m-%d"), "videos": len(rows), "median": med, "rows": rows,
                                "note": "사람이 편집한 쇼츠의 편집 밀도(숫자만). scripts/edit_density.py baseline"}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("기준(중앙값):", med)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", help="영상 파일들, 또는 baseline")
    ap.add_argument("--check", help="콘티 JSON — preset.density 와 비교")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fast", action="store_true", help="픽셀 숫자만(재료 종류 · 글자 크기는 안 잼)")
    a = ap.parse_args()
    if a.videos == ["baseline"]:
        cmd_baseline(); return
    bad = False
    for v in a.videos:
        m = measure(v)
        if m.get("ok") and not a.fast:
            m.update(semantic(v))
        if a.check and m.get("ok"):
            m["problems"] = check(m, json.loads(Path(a.check).read_text(encoding="utf-8")))
            bad |= bool(m["problems"])
        if a.json:
            print(json.dumps({"video": v, **m}, ensure_ascii=False)); continue
        print(f"{Path(v).name[:48]:48} {m.get('sec')}초 · 글자 {m.get('text_px')}px · 재료 {m.get('kinds')}가지 · 재료 전환 {m.get('kind_switch')}/10초 · 최장 정지 {m.get('longest_still')}초")
        for p in m.get("problems") or []:
            print(f"   ✗ {p}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
