#!/usr/bin/env python3
"""목소리 특징을 숫자로 잰다 — 레퍼런스 화자와 우리 나레이션을 같은 잣대로 견주기 위해(목소리를 복제하지 않는다).

  python3 engine/voice/voice_profile.py <소리 파일> [--segs <구간 json>]

잰 값
  f0_median    평균 음높이(Hz) — 낮이
  range_st     억양 폭(반음, 10~90 백분위) — 작을수록 평평 · 단조
  end_drop_st  말끝 처리(반음) — 구절 마지막 0.35초 음높이가 구절 전체보다 얼마나 내려가나(음수 = 툭 떨어짐, 양수 = 올림)
  end_fall     말끝이 1반음 넘게 떨어지는 구절 비율
  energy_sd_db 세기 변화(dB 표준편차) — 작을수록 힘을 빼고 고르게 말함
  cps          초당 글자 수(공백 제외) — 구간 글이 있을 때만
구간(segs): [{start, end, text}] — 레퍼런스는 받아쓰기 구간, 우리 음성은 단어 시각(<wav>.words.json)을 쉼표 · 마침표에서 묶는다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 16000
HOP = 0.01


def load(path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def f0_track(x: np.ndarray, fmin: float = 60, fmax: float = 400) -> tuple[np.ndarray, np.ndarray]:
    """40ms 창 · 10ms 간격 자기상관(FFT) → (프레임별 F0 Hz, 0 = 무성), (프레임별 세기 dB)"""
    win, hop = int(.04 * SR), int(HOP * SR)
    n = max(0, (len(x) - win) // hop)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(win)[None, :]
    fr = fr - fr.mean(axis=1, keepdims=True)
    rms = np.sqrt((fr ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    spec = np.fft.rfft(fr, 2 * win, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, :win]
    ac = ac / (ac[:, :1] + 1e-12)
    lo, hi = int(SR / fmax), int(SR / fmin)
    lag = lo + np.argmax(ac[:, lo:hi], axis=1)
    peak = ac[np.arange(n), lag]
    loud = db > (np.percentile(db, 95) - 30)
    f0 = np.where((peak > .45) & loud, SR / lag, 0.0)
    # 옥타브 튐 걸러내기: 중앙값에서 ±1옥타브 넘게 벗어난 값은 버린다
    v = f0[f0 > 0]
    if len(v) > 20:
        med = np.median(v)
        f0[(f0 > 0) & ((f0 > med * 1.9) | (f0 < med / 1.9))] = 0
    return f0, db


def segs_from_words(words: list[dict], text: str | None = None) -> list[dict]:
    """단어 시각(ms) → 쉼표 · 마침표에서 끊은 구절 [{start, end, text}] (초).
    단어에 문장부호가 없는 엔진(edge 등)은 원문(text)의 띄어쓰기 단위를 단어 수가 같을 때 대신 쓴다"""
    toks = (text or "").split()
    if toks and len(toks) == len(words) and not any(re.search(r"[.,?!…]$", w.get("text", "")) for w in words):
        words = [{**w, "text": t} for w, t in zip(words, toks)]
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.,?!…]$", w.get("text", "")):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [{"start": c[0]["startMs"] / 1000, "end": c[-1]["endMs"] / 1000, "text": " ".join(w["text"] for w in c)} for c in out if c]


def profile(path, segs: list[dict] | None = None) -> dict:
    x = load(path)
    f0, db = f0_track(x)
    v = f0[f0 > 0]
    if len(v) < 30:
        return {"f0_median": None, "note": "목소리가 거의 없음"}
    med = float(np.median(v))
    st = 12 * np.log2(v / med)
    out = {"f0_median": round(med, 1), "range_st": round(float(np.percentile(st, 90) - np.percentile(st, 10)), 2),
           "energy_sd_db": round(float(np.std(db[f0 > 0])), 2), "voiced_sec": round(len(v) * HOP, 1)}
    drops = []
    for s in segs or []:
        a, b = int(s["start"] / HOP), int(s["end"] / HOP)
        seg = f0[a:b]; sv = seg[seg > 0]
        if b - a < 60 or len(sv) < 20:          # 0.6초 미만 구절은 말끝을 재지 않는다
            continue
        tail = seg[max(0, len(seg) - 35):]; tv = tail[tail > 0]
        if len(tv) < 5:
            continue
        drops.append(12 * np.log2(np.median(tv) / np.median(sv)))
    if drops:
        out["end_drop_st"] = round(float(np.median(drops)), 2)
        out["end_fall"] = round(float(np.mean(np.array(drops) < -1)), 2)
        out["phrases"] = len(drops)
    chars = sum(len(re.sub(r"\s", "", s.get("text", ""))) for s in segs or [])
    talk = sum(max(0.0, s["end"] - s["start"]) for s in segs or [])
    if chars and talk > 1:
        out["cps"] = round(chars / talk, 2)
    return out


# 거리: 음높이(반음) · 억양 폭 · 말끝 · 세기 변화 — 사람 귀에 큰 순서로 무게
WEIGHTS = {"f0": 1.0, "range_st": 0.5, "end_drop_st": 0.8, "energy_sd_db": 0.25}


def distance(ref: dict, got: dict) -> float:
    if not ref.get("f0_median") or not got.get("f0_median"):
        return 99.0
    d = WEIGHTS["f0"] * abs(12 * np.log2(got["f0_median"] / ref["f0_median"]))
    for k in ("range_st", "end_drop_st", "energy_sd_db"):
        if ref.get(k) is not None and got.get(k) is not None:
            d += WEIGHTS[k] * abs(got[k] - ref[k])
    return round(float(d), 2)


def compare(ref: dict, got: dict) -> list[dict]:
    """사람이 읽는 비교표 [{항목, 레퍼런스, 우리, 판정}]"""
    rows = []
    if ref.get("f0_median") and got.get("f0_median"):
        dst = 12 * np.log2(got["f0_median"] / ref["f0_median"])
        rows.append({"item": "음높이", "ref": f"{ref['f0_median']}Hz", "got": f"{got['f0_median']}Hz",
                     "verdict": "비슷" if abs(dst) < 1.5 else ("높음" if dst > 0 else "낮음") + f" ({dst:+.1f}반음)"})
    for k, name, tol, hi, lo in (("range_st", "억양 폭", 1.5, "오르내림이 큼", "더 평평함"),
                                 ("end_drop_st", "말끝", 0.8, "말끝이 덜 떨어짐(올라감)", "말끝이 더 떨어짐"),
                                 ("energy_sd_db", "세기 변화", 1.5, "힘이 더 들어감", "더 고름"),
                                 ("cps", "말 속도(초당 글자)", 0.8, "더 빠름", "더 느림")):
        if ref.get(k) is None or got.get(k) is None:
            continue
        dv = got[k] - ref[k]
        rows.append({"item": name, "ref": ref[k], "got": got[k], "verdict": "비슷" if abs(dv) < tol else (hi if dv > 0 else lo)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("--segs", help="구간 json([{start,end,text}]) 또는 단어 시각 json(<wav>.words.json)")
    a = ap.parse_args()
    segs = None
    sp = Path(a.segs) if a.segs else Path(str(a.audio) + ".words.json")
    if sp.exists():
        d = json.loads(sp.read_text(encoding="utf-8"))
        segs = segs_from_words(d) if d and "startMs" in d[0] else d
    print(json.dumps(profile(a.audio, segs), ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
