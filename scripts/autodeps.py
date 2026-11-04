"""선택 패키지 자동 설치 — 스크립트가 아직 없는 패키지(OpenCV · Whisper · OCR …)를 import 하면 그 자리에서 설치하고 이어 간다.
사람에게 "pip install 해 주세요" 를 부탁하지 않기 위해서. pip 는 Windows · macOS · Linux 에서 같은 방법으로 설치한다.

doctor.py --fix(그리고 Docker 이미지)가 이 파일을 가상환경(.venv)의 site-packages 에 fluma_autodeps.py 로 복사하고
fluma_autodeps.pth 로 켠다 → .venv 의 파이썬으로 도는 모든 스크립트에 적용된다. 끄려면 FLUMA_AUTO_INSTALL=0.
아래 목록에 있는 모듈만 설치한다(이름이 비슷한 다른 패키지를 받는 일이 없게).
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import os
import shutil
import subprocess
import sys

# 모듈 이름 → 설치할 패키지(버전 범위는 scripts/requirements-*.txt 와 같게)
PACKAGES = {
    "cv2": "opencv-python-headless>=4.9,<5",
    "onnxruntime": "onnxruntime>=1.18",
    "faster_whisper": "faster-whisper>=1.1",
    "rapidocr": "rapidocr>=3.0",
    "huggingface_hub": "huggingface-hub>=0.24",
    "tokenizers": "tokenizers>=0.19",
    "rembg": "rembg[cpu]>=2.0",
    "gradio_client": "gradio_client>=1.3",
    "googleapiclient": "google-api-python-client>=2.100",
    "google_auth_oauthlib": "google-auth-oauthlib>=1.2",
    "youtube_transcript_api": "youtube-transcript-api>=1.0",
}


class _AutoInstall(importlib.abc.MetaPathFinder):
    tried: set[str] = set()

    def find_spec(self, name, path=None, target=None):
        if path is not None or name not in PACKAGES or name in self.tried:   # 최상위 모듈만 · 한 번만
            return None
        self.tried.add(name)
        if importlib.machinery.PathFinder.find_spec(name) is not None:      # 이미 있음
            return None
        pkg = PACKAGES[name]
        print(f"[Fluma] '{name}' 이 없어 설치합니다: {pkg} (한 번만, 잠시 걸려요)", file=sys.stderr, flush=True)
        uv = shutil.which("uv")
        cmd = [uv, "pip", "install", "--python", sys.executable, pkg] if uv else [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", pkg]
        r = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
        if r.returncode != 0:
            print(f"[Fluma] {pkg} 설치 실패 — python3 scripts/doctor.py 로 원인을 확인하세요", file=sys.stderr, flush=True)
            return None
        importlib.invalidate_caches()
        return importlib.machinery.PathFinder.find_spec(name)


def install() -> None:
    if os.environ.get("FLUMA_AUTO_INSTALL", "1") != "0" and not any(isinstance(f, _AutoInstall) for f in sys.meta_path):
        sys.meta_path.append(_AutoInstall())     # 맨 뒤: 이미 있는 모듈은 평소대로 찾는다


install()
