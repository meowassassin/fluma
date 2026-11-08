import shutil
import subprocess
from pathlib import Path


def available() -> bool:
    return bool(shutil.which("espeak-ng"))


def synth(text, out_wav: Path, voice=None, speed=1.0):
    subprocess.run(["espeak-ng", "-v", voice or "ko", "-s", str(int(165 * speed)), "-w", str(out_wav), text], check=True, capture_output=True)
