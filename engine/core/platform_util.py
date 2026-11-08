"""운영체제 차이를 한곳에서 — Linux · macOS · Windows 에서 같은 코드가 돌게.

venv_python(폴더)   : 가상환경 파이썬 (Windows 는 .venv\\Scripts\\python.exe)
which(이름)         : PATH 에서 실행 파일 찾기 (Windows 의 .exe/.cmd 포함)
container_mount()   : 컨테이너 볼륨 접미사 (SELinux 리눅스만 :Z)
OS                  : "linux" | "mac" | "windows"
"""
import os
import platform
import shutil
import sys
from pathlib import Path

OS = "windows" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"
ARCH = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
EXE = ".exe" if OS == "windows" else ""


def venv_python(folder) -> Path:
    v = Path(folder) / ".venv"
    return v / "Scripts" / "python.exe" if OS == "windows" else v / "bin" / "python"


def which(name: str) -> str | None:
    return shutil.which(name)


def container_mount(ro: bool = False) -> str:
    """podman/docker -v 의 옵션. SELinux 가 켜진 리눅스에서만 :Z 가 필요하고, macOS · Windows(Docker Desktop)는 쓰지 않는다."""
    selinux = OS == "linux" and Path("/sys/fs/selinux/enforce").exists()
    opts = (["ro"] if ro else []) + (["Z"] if selinux else [])
    return (":" + ",".join(opts)) if opts else ""


PYTHON = sys.executable
