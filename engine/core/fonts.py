#!/usr/bin/env python3
"""디자인 글꼴 설치 — Craft 앱은 시스템 글꼴 폴더만 본다(fontconfig 설정을 따르지 않는다).
engine/assets/fonts 의 글꼴을 사용자 글꼴 폴더에 복사한다. 글꼴은 모두 OFL(licenses/). 이미 있으면 건너뛴다.

  python3 engine/core/fonts.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "assets" / "fonts"
DST = Path.home() / ".local" / "share" / "fonts" / "fluma"
FILES = ("GowunBatang-Bold", "GowunBatang-Regular", "BlackHanSans-Regular", "NanumPenScript-Regular", "SongMyung-Regular", "Gugi-Regular")


def install(dst: Path = DST) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in FILES:
        s, d = SRC / f"{f}.ttf", dst / f"{f}.ttf"
        if s.exists() and (not d.exists() or d.stat().st_size != s.stat().st_size):
            shutil.copyfile(s, d)
            n += 1
    if n and shutil.which("fc-cache"):
        subprocess.run(["fc-cache", "-f", str(dst)], capture_output=True)
    return n


if __name__ == "__main__":
    print(f"글꼴 {install()}개 설치 · {DST}")
