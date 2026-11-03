#!/usr/bin/env python3
"""
음원 분리 — 목소리 / 나머지(음악 · 효과음). torch 없이 ONNX(UVR MDX-Net Kim_Vocal_2)와 numpy STFT 로 CPU 에서.

  python3 scripts/separate.py <소리 · 영상 파일> <출력 폴더>   → vocals.m4a · music.m4a (나머지)

모델(약 66MB)은 처음 쓸 때 ~/.rembg/models/uvr/ 에 받는다. 44.1kHz 스테레오로 바꿔 넣고, 26만 샘플(약 6초) 조각을
가장자리를 겹쳐 처리한다(조각 경계에서 소리가 튀지 않게). 1분 소리에 CPU 로 수십 초.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

MODEL = Path.home() / ".rembg" / "models" / "uvr" / "Kim_Vocal_2.onnx"
URL = "https://huggingface.co/seanghay/uvr_models/resolve/main/Kim_Vocal_2.onnx"
SR, N_FFT, HOP, DIM_F, DIM_T = 44100, 7680, 1024, 3072, 256
CHUNK = HOP * (DIM_T - 1)        # 261120 샘플 — 모델 한 번에 들어가는 길이
TRIM = N_FFT // 2                 # 조각 양끝 버리는 길이(겹침)
WIN = np.hanning(N_FFT + 1)[:-1].astype(np.float32)   # 주기형 Hann (torch.hann_window 와 같음)


def load(path: str | Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).T.copy()   # [2, n]


def stft(x: np.ndarray) -> np.ndarray:
    """[C, CHUNK] → [C, bins, DIM_T] (center=True, reflect 패딩)"""
    x = np.pad(x, ((0, 0), (N_FFT // 2, N_FFT // 2)), mode="reflect")
    fr = np.lib.stride_tricks.sliding_window_view(x, N_FFT, axis=1)[:, ::HOP][:, :DIM_T]
    return np.fft.rfft(fr * WIN, axis=2).transpose(0, 2, 1)


def istft(S: np.ndarray, n: int) -> np.ndarray:
    """[C, bins, T] → [C, n] (겹쳐 더하기 · 창 제곱합으로 나눔)"""
    fr = np.fft.irfft(S.transpose(0, 2, 1), n=N_FFT, axis=2) * WIN
    L = N_FFT + HOP * (fr.shape[1] - 1)
    out = np.zeros((S.shape[0], L), np.float32); wsum = np.zeros(L, np.float32)
    for t in range(fr.shape[1]):
        out[:, t * HOP:t * HOP + N_FFT] += fr[:, t]; wsum[t * HOP:t * HOP + N_FFT] += WIN ** 2
    out /= np.maximum(wsum, 1e-8)
    return out[:, N_FFT // 2:N_FFT // 2 + n]


def session():
    import onnxruntime as ort
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, MODEL)
    o = ort.SessionOptions(); o.enable_cpu_mem_arena = False
    return ort.InferenceSession(str(MODEL), o, providers=["CPUExecutionProvider"])


def vocals(mix: np.ndarray, sess=None, log=lambda p: None) -> np.ndarray:
    """mix [2, n] → 목소리 [2, n]. 나머지(음악 · 효과음) = mix - 목소리"""
    sess = sess or session()
    n = mix.shape[1]
    step = CHUNK - 2 * TRIM
    pad = np.pad(mix, ((0, 0), (TRIM, TRIM + step)))
    out = np.zeros((2, n + step), np.float32)
    total = (n + step - 1) // step
    for k, i in enumerate(range(0, n, step)):
        seg = pad[:, i:i + CHUNK]
        if seg.shape[1] < CHUNK:
            seg = np.pad(seg, ((0, 0), (0, CHUNK - seg.shape[1])))
        S = stft(seg)[:, :DIM_F]                                     # [2, DIM_F, DIM_T] 복소
        x = np.stack([S[0].real, S[0].imag, S[1].real, S[1].imag])[None].astype(np.float32)
        y = sess.run(None, {"input": x})[0][0]
        V = np.zeros((2, N_FFT // 2 + 1, DIM_T), np.complex64)
        V[0, :DIM_F] = y[0] + 1j * y[1]; V[1, :DIM_F] = y[2] + 1j * y[3]
        v = istft(V, CHUNK)
        out[:, i:i + step] = v[:, TRIM:TRIM + step]
        log((k + 1) / total)
    return out[:, :n]


def save(x: np.ndarray, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(x.T, -1, 1).astype(np.float32).tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "aac", "-b:a", "128k", str(path)], input=pcm, check=True)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], Path(sys.argv[2])
    mix = load(src)
    v = vocals(mix, log=lambda p: print(f"@progress {p:.2f} 소리 나누는 중", flush=True))
    save(v, out / "vocals.m4a"); save(mix - v, out / "music.m4a")
    e = lambda a: float(np.sqrt((a ** 2).mean()) + 1e-9)
    print(f"목소리 {e(v) / e(mix):.2f} · 나머지 {e(mix - v) / e(mix):.2f} (원본 대비 음량)")


if __name__ == "__main__":
    main()
