#!/usr/bin/env python3
"""분석 · 누끼 모델을 미리 받아 둔다 — 처음 쓰는 순간 수백 MB 를 받느라 멈추지 않게(Docker 이미지 · doctor.py --fix 가 부른다).
  받아쓰기 faster-whisper small · 화면 분류 CLIP(Xenova/clip-vit-base-patch32) · OCR(rapidocr) · 누끼(rembg isnet-general-use · u2net)
하나가 실패해도 나머지는 받는다(실패한 것은 처음 쓸 때 다시 받는다).
"""
from __future__ import annotations

import os
import sys

WHISPER = os.environ.get("XRAY_WHISPER", "small")


def whisper() -> None:
    from faster_whisper import WhisperModel
    WhisperModel(WHISPER, device="cpu", compute_type="int8")


def clip() -> None:
    from huggingface_hub import hf_hub_download
    for f in ("onnx/vision_model_quantized.onnx", "onnx/text_model_quantized.onnx", "tokenizer.json"):
        hf_hub_download("Xenova/clip-vit-base-patch32", f)


def ocr() -> None:
    from rapidocr import RapidOCR
    RapidOCR()


def matte() -> None:
    from rembg import new_session
    for m in ("isnet-general-use", "u2net"):
        new_session(m)


def main() -> int:
    bad = []
    for name, fn in (("받아쓰기", whisper), ("화면 분류", clip), ("OCR", ocr), ("누끼", matte)):
        print(f"· 모델: {name}", flush=True)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — 하나 실패해도 계속
            print(f"  ✗ {name}: {e}", file=sys.stderr)
            bad.append(name)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
