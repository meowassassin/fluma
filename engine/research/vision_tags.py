#!/usr/bin/env python3
"""화면 종류 가르기(범용) — 어떤 쇼츠든 프레임마다 '무엇이 보이나'를 같은 갈래로 붙인다.

  python3 engine/research/vision_tags.py <그림> [<그림> …]

오픈소스 CLIP ViT-B/32(OpenAI, MIT) — ONNX 양자화판(Xenova/clip-vit-base-patch32, 약 150MB, 처음 쓸 때 받음)을 CPU 로.
글로 적은 갈래(KINDS)와 그림을 견줘 가장 가까운 것을 고른다(제로샷). 학습 없음 · 갈래를 더하려면 KINDS 에 한 줄.
기사(뉴스 화면)는 그림만으로는 '사이트 화면'과 헷갈려 OCR 글(기자 · 입력 · 언론사 · 날짜)로 한 번 더 가른다(ref_channel.NEWS).
결과 갈래는 콘티 scene.screen · 채널 카드 structure.screens 와 같은 이름이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에

REPO = "Xenova/clip-vit-base-patch32"
# 갈래: (이름, 영어 설명 여러 개 — 평균을 쓴다)
KINDS: list[tuple[str, list[str]]] = [
    ("실제 화면", ["a screenshot of a website", "a screenshot of a mobile app user interface", "a screen recording of software on a computer"]),
    ("기사", ["a screenshot of a news article with a headline", "an online newspaper web page"]),
    ("사람", ["a person talking to the camera", "a selfie video of a person speaking", "a close-up of a person's face"]),
    ("실사 영상", ["real-life video footage of a place", "a photo of a street or a room", "documentary footage", "a person sitting at a desk in a dark room", "people walking in a real place"]),
    ("제품", ["a product shot on a clean background", "a close-up of a gadget or product"]),
    ("음식", ["a photo of food", "cooking food in a kitchen"]),
    ("짤", ["a funny meme image", "a reaction gif from a movie or tv show", "a meme with caption text"]),
    ("애니메이션 · 일러스트", ["a cartoon animation", "a flat vector illustration", "an anime drawing"]),
    ("카드(글자)", ["a slide with large text on a plain background", "a title card with big letters"]),
    ("도표", ["a chart or graph", "a diagram with arrows and boxes"]),
    ("게임 화면", ["a video game screenshot", "gameplay footage"]),
    ("픽셀 아트", ["pixel art video game graphics", "an 8-bit retro pixel animation"]),
    ("3D 그래픽", ["a 3D rendered computer graphic", "a 3D animation scene"]),
]
_S: dict = {}


def _load():
    if _S:
        return _S
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    o = ort.SessionOptions(); o.log_severity_level = 3
    _S["vis"] = ort.InferenceSession(hf_hub_download(REPO, "onnx/vision_model_quantized.onnx"), o, providers=["CPUExecutionProvider"])
    txt = ort.InferenceSession(hf_hub_download(REPO, "onnx/text_model_quantized.onnx"), o, providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(hf_hub_download(REPO, "tokenizer.json"))
    embs = []
    for _, prompts in KINDS:
        ids = [tok.encode(p).ids[:77] for p in prompts]
        n = max(len(i) for i in ids)
        arr = np.array([i + [i[-1]] * (n - len(i)) for i in ids], dtype=np.int64)   # 끝 토큰(EOS)으로 채움 — CLIP 은 가장 큰 id(EOS) 자리를 읽는다
        e = txt.run(None, {"input_ids": arr})[0]
        e = e / np.linalg.norm(e, axis=1, keepdims=True)
        m = e.mean(axis=0); embs.append(m / np.linalg.norm(m))
    _S["text"] = np.stack(embs)
    return _S


def _pixels(img: Image.Image) -> np.ndarray:
    img = img.convert("RGB")
    w, h = img.size; s = 224 / min(w, h)
    img = img.resize((max(224, round(w * s)), max(224, round(h * s))), Image.BICUBIC)
    w, h = img.size; l, t = (w - 224) // 2, (h - 224) // 2
    a = np.asarray(img.crop((l, t, l + 224, t + 224)), dtype=np.float32) / 255.0
    a = (a - np.array([0.48145466, 0.4578275, 0.40821073])) / np.array([0.26862954, 0.26130258, 0.27577711])
    return a.transpose(2, 0, 1)[None].astype(np.float32)


def classify(image, ocr_lines: list[dict] | None = None) -> dict:
    """→ {kind, score, top:[(kind, p), …3]}. ocr_lines(ocr.read 결과)가 있으면 기사 표지로 한 번 더 가른다
    로컬 CLIP(프레임당 0.05초 · 무료)."""
    S = _load()
    img = Image.open(image) if not isinstance(image, Image.Image) else image
    # 세로 쇼츠는 위아래 띠(검정 · 제목)가 많아 가운데 정사각을 본다 — 내용이 가운데 띠에 있다
    e = S["vis"].run(None, {"pixel_values": _pixels(img)})[0][0]
    e = e / np.linalg.norm(e)
    logits = 100.0 * S["text"] @ e
    p = np.exp(logits - logits.max()); p /= p.sum()
    order = np.argsort(-p)
    kind, score = KINDS[order[0]][0], float(p[order[0]])
    top3 = [(KINDS[i][0], round(float(p[i]), 3)) for i in order[:3]]
    if ocr_lines is not None:
        import ref_channel
        txt = " ".join(o["text"] for o in ocr_lines)
        if kind in ("실제 화면", "기사", "카드(글자)") and len(ocr_lines) >= 5 and ref_channel.NEWS.search(txt):
            kind = "기사"
        elif kind == "기사" and not ref_channel.NEWS.search(txt):
            kind = "실제 화면"
    return {"kind": kind, "score": round(float(score), 3), "top": top3}


if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f, classify(f))
