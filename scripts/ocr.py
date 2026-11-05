#!/usr/bin/env python3
"""다국어 OCR — 화면 속 글자(자막 · 웹 화면 · 짤 글씨)를 위치 · 글자 · 확신도 · 색과 함께 읽는다.

  python3 scripts/ocr.py <그림> [<그림> …] [--langs korean,en] [--json]

오픈소스: RapidOCR(Apache-2.0) + PaddleOCR PP-OCRv5 모델(ONNX, CPU). 처음 쓸 때 모델을 받는다(언어당 수 MB).
방법: 글자 위치 찾기(det)는 한 번, 같은 위치를 언어 모델마다 읽어(rec) 확신도가 가장 높은 것을 고른다.
언어: korean(한글 + 영문 · 숫자) · en · ch(중 · 영 · 일) · japan · latin(유럽어) · cyrillic · arabic … (RapidOCR LangRec)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

LANG_ALIASES = {"ko": "korean", "kr": "korean", "korean": "korean", "en": "en", "english": "en", "ja": "japan", "jp": "japan", "japan": "japan",
                "zh": "ch", "ch": "ch", "latin": "latin", "ru": "cyrillic", "cyrillic": "cyrillic", "ar": "arabic", "arabic": "arabic"}
_ENGINES: dict = {}


def _rapid(lang: str | None):
    """lang=None → 글자 위치 찾기 전용"""
    key = lang or "_det"
    if key in _ENGINES:
        return _ENGINES[key]
    import logging
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
    logging.getLogger("RapidOCR").setLevel(logging.ERROR)
    p = {}
    if lang:
        p.update({"Rec.lang_type": LangRec(lang), "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE})
    _ENGINES[key] = RapidOCR(params=p)
    return _ENGINES[key]


def _crop(img: np.ndarray, quad) -> np.ndarray:
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    x0, x1, y0, y1 = int(max(0, min(xs))), int(min(img.shape[1], max(xs))), int(max(0, min(ys))), int(min(img.shape[0], max(ys)))
    return img[y0:y1, x0:x1]


def _colors(crop: np.ndarray) -> tuple[str, str]:
    """글자 상자의 바탕색(가장 많은 색) · 글자색(바탕과 가장 먼 많은 색)"""
    if crop.size == 0:
        return "#000000", "#ffffff"
    px = (crop.reshape(-1, crop.shape[-1])[:, :3] // 32) * 32 + 16
    vals, cnt = np.unique(px, axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    far = np.linalg.norm(vals.astype(float) - bg.astype(float), axis=1)
    cand = [(c, v) for c, v, d in zip(cnt, vals, far) if d > 120]
    fg = max(cand, key=lambda x: x[0])[1] if cand else (255 - bg)
    hx = lambda v: "#%02x%02x%02x" % tuple(int(min(255, x)) for x in v)
    return hx(bg), hx(fg)


_SEEN: list = []        # 최근에 읽은 프레임(작은 회색 그림, 결과) — 자막이 그대로인 프레임은 다시 읽지 않는다
ACCEPT = 0.9            # 첫 언어로 이만큼 확신하면 다른 언어는 읽지 않는다(언어마다 읽으면 두세 배 느림)


def _thumb(img: np.ndarray) -> np.ndarray:
    return np.asarray(Image.fromarray(img).convert("L").resize((54, 96)), dtype=np.int16)


def read(image, langs=("korean", "en"), min_score: float = 0.5) -> list[dict]:
    """→ [{text, score, lang, box:[x, y, w, h](0~1), bg, fg}] 위에서 아래 순
    langs 는 순서가 중요하다: 첫 언어로 먼저 읽고, 확신이 낮은 글줄만 다음 언어로 다시 읽는다(영상 언어를 앞에)"""
    img = np.array(Image.open(image).convert("RGB")) if not isinstance(image, np.ndarray) else image
    H, W = img.shape[:2]
    langs = [LANG_ALIASES.get(l.strip().lower(), l.strip().lower()) for l in langs if l.strip()]
    th = _thumb(img)
    for t0, key, res in _SEEN:          # 거의 같은 프레임(글자 한 자만 바뀌어도 그 자리 화소가 크게 변한다)
        if key == (tuple(langs), min_score) and t0.shape == th.shape and int(np.abs(t0 - th).max()) < 28:
            return [dict(o) for o in res]
    r0 = _rapid(langs[0])(img, use_cls=False)        # 위치 찾기 + 첫 언어 읽기를 한 번에(글줄을 묶어 읽어 빠르다)
    rows = list(zip(r0.boxes, r0.txts, r0.scores)) if r0.boxes is not None and r0.txts else []
    out = []
    for q, txt, sc in rows:
        crop = _crop(img, q)
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            continue
        best = {"text": str(txt).strip(), "score": round(float(sc), 3), "lang": langs[0]} if str(txt).strip() else None
        if not best or best["score"] < ACCEPT:              # 확신이 낮은 글줄만 다른 언어로
            for lg in langs[1:]:
                r = _rapid(lg)(crop, use_det=False, use_cls=False, use_rec=True)
                t2 = (r.txts or [""])[0] if r.txts else ""
                s2 = float((r.scores or [0])[0]) if r.scores else 0.0
                if t2 and (best is None or s2 > best["score"]):
                    best = {"text": t2.strip(), "score": round(s2, 3), "lang": lg}
                if best and best["score"] >= ACCEPT:
                    break
        if not best or best["score"] < min_score:
            continue
        xs, ys = [float(p[0]) for p in q], [float(p[1]) for p in q]
        bg, fg = _colors(crop)
        out.append({**best, "box": [round(min(xs) / W, 4), round(min(ys) / H, 4), round((max(xs) - min(xs)) / W, 4), round((max(ys) - min(ys)) / H, 4)], "bg": bg, "fg": fg})
    out.sort(key=lambda d: (round(d["box"][1], 2), d["box"][0]))
    _SEEN.insert(0, (th, (tuple(langs), min_score), [dict(o) for o in out]))
    del _SEEN[8:]
    return out


def order_langs(langs, text: str) -> list[str]:
    """영상 말(제목 · 받아쓰기)이 한글이면 korean 을, 아니면 en 을 앞에 — read() 는 첫 언어로 먼저 읽는다"""
    langs = [LANG_ALIASES.get(l.strip().lower(), l.strip().lower()) for l in langs if l.strip()]
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    first = "korean" if hangul >= latin * 0.3 and hangul else "en"
    return sorted(langs, key=lambda l: l != first)


def frames(src, start: float, step: float, n: int) -> list[tuple[float, np.ndarray]]:
    """영상에서 start 초부터 step 초 간격으로 n 장을 한 번에(ffmpeg 를 프레임마다 새로 띄우지 않는다) → [(시각, RGB 배열)]"""
    import subprocess
    import tempfile
    if n <= 0:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-vf", f"fps=1/{step:g}:round=down",
                        "-frames:v", str(n), "-q:v", "2", str(Path(tmp) / "f%05d.jpg")], check=True)
        got = sorted(Path(tmp).glob("f*.jpg"))
        return [(round(start + i * step, 3), np.array(Image.open(f).convert("RGB"))) for i, f in enumerate(got)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--langs", default="korean,en")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = {p: read(p, a.langs.split(",")) for p in a.images}
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return
    for p, rows in res.items():
        print(f"== {p}")
        for d in rows:
            print(f"  {d['score']:.2f} [{d['lang']}] {d['text']}  @ {d['box']}  {d['bg']}/{d['fg']}")


if __name__ == "__main__":
    sys.exit(main())
