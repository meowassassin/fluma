"""음성 엔진 공통: 엔진마다 자기 가상환경(.venv)의 파이썬으로 run.py 를 돌린다 (의존성 충돌 방지)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from platform_util import venv_python as _vp  # noqa: E402


def venv_python(here: Path) -> Path:
    return _vp(here)   # Windows: .venv\Scripts\python.exe


def installed(here: Path) -> bool:
    """설치기(scripts/install.py)가 끝까지 성공하고 import 확인까지 했을 때만 생기는 표시 — 빈 가상환경을 '사용 가능'으로 보지 않게"""
    return venv_python(here).exists() and (here / ".installed").exists()


def run_engine(here: Path, text: str, out_wav: Path, voice: str, speed: float, timeout: int = 900):
    req = out_wav.with_suffix(".req.json")
    req.write_text(json.dumps({"text": text, "out": str(out_wav), "voice": voice, "speed": speed}, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([str(venv_python(here)), str(here / "run.py"), str(req)], capture_output=True, text=True, timeout=timeout)
    req.unlink(missing_ok=True)
    if r.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"{here.name} 합성 실패: {(r.stderr or r.stdout)[-600:]}")
