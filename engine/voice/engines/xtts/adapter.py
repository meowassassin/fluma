from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from _common import installed, run_engine  # noqa: E402


def available() -> bool:
    return installed(HERE)


def synth(text, out_wav: Path, voice=None, speed=1.0):
    run_engine(HERE, text, out_wav, voice or "Ana Florence", speed, timeout=1800)
