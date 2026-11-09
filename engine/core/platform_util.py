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


def env_dir(folder) -> Path:
    """엔진(음성 · 렌더)마다 설치물(가상환경 · 설치 표시)을 두는 곳 — data/cache/envs/<종류>/<이름>.
    2026-11-09: 엔진 폴더 안(.venv)에 두면 Docker 에서 이미지를 바꿀 때마다 설치한 모델이 사라졌다(data/cache 는 볼륨이라 남는다).
    예전에 엔진 폴더에 설치한 것이 있으면 그것을 그대로 쓴다"""
    folder = Path(folder).resolve()
    if (folder / ".venv").exists() and not (folder / ".venv").is_symlink():
        return folder
    root = Path(__file__).resolve().parents[2]
    kind = "voices" if folder.parent.name == "engines" and folder.parent.parent.name == "voice" else "engines"
    name = folder.name if kind == "voices" else folder.parent.name
    return root / "data" / "cache" / "envs" / kind / name


def venv_python(folder) -> Path:
    v = env_dir(folder) / ".venv"
    return v / "Scripts" / "python.exe" if OS == "windows" else v / "bin" / "python"


def which(name: str) -> str | None:
    return shutil.which(name)


def venv_tool(name: str) -> str:
    """가상환경에 설치된 명령(yt-dlp 등) — 저장소 .venv(Windows 는 Scripts\\이름.exe) > 지금 파이썬 옆 > PATH > 이름 그대로.
    2026-11-09: '.venv/bin/yt-dlp' 를 박아 둬 Windows(venv 를 켜지 않고 실행)에서 yt-dlp 를 못 찾아 멈췄다"""
    root = Path(__file__).resolve().parents[2]
    for d in (root / ".venv" / ("Scripts" if OS == "windows" else "bin"), Path(sys.executable).parent):
        f = d / (name + EXE)
        if f.exists():
            return str(f)
    return shutil.which(name) or name


def container_mount(ro: bool = False) -> str:
    """podman/docker -v 의 옵션. SELinux 가 켜진 리눅스에서만 :Z 가 필요하고, macOS · Windows(Docker Desktop)는 쓰지 않는다."""
    selinux = OS == "linux" and Path("/sys/fs/selinux/enforce").exists()
    opts = (["ro"] if ro else []) + (["Z"] if selinux else [])
    return (":" + ",".join(opts)) if opts else ""


PYTHON = sys.executable
