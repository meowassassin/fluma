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


def read(image, langs=("korean", "en"), min_score: float = 0.5) -> list[dict]:
    """→ [{text, score, lang, box:[x, y, w, h](0~1), bg, fg}] 위에서 아래 순"""
    img = np.array(Image.open(image).convert("RGB")) if not isinstance(image, np.ndarray) else image
    H, W = img.shape[:2]
    langs = [LANG_ALIASES.get(l.strip().lower(), l.strip().lower()) for l in langs if l.strip()]
    det = _rapid(langs[0])(img, use_det=True, use_cls=False, use_rec=False)
    quads = list(det.boxes) if det.boxes is not None else []
    out = []
    for q in quads:
        crop = _crop(img, q)
        if crop.shape[0] < 6 or crop.shape[1] < 6:
            continue
        best = None
        for lg in langs:
            r = _rapid(lg)(crop, use_det=False, use_cls=False, use_rec=True)
            txt = (r.txts or [""])[0] if r.txts else ""
            sc = float((r.scores or [0])[0]) if r.scores else 0.0
            if txt and (best is None or sc > best["score"]):
                best = {"text": txt.strip(), "score": round(sc, 3), "lang": lg}
        if not best or best["score"] < min_score:
            continue
        xs, ys = [float(p[0]) for p in q], [float(p[1]) for p in q]
        bg, fg = _colors(crop)
        out.append({**best, "box": [round(min(xs) / W, 4), round(min(ys) / H, 4), round((max(xs) - min(xs)) / W, 4), round((max(ys) - min(ys)) / H, 4)], "bg": bg, "fg": fg})
    out.sort(key=lambda d: (round(d["box"][1], 2), d["box"][0]))
    return out


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
