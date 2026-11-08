"""Fluma 경로 — 저장소 루트 · engine 아래 묶음을 import 경로에 넣는다(모든 명령의 첫 줄이 부른다).
  ROOT   저장소 루트
  ENGINE engine/ (제작 엔진)
  DATA   data/   (실행 중 생기는 데이터: 콘티 · 제작 파일 · 음성 · 렌더 · 작업 공간)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
DATA = ROOT / "data"
for _d in [ENGINE, *sorted(d for d in ENGINE.iterdir() if d.is_dir() and d.name[0] not in "._")]:
    if str(_d) not in sys.path:
        sys.path.append(str(_d))

# 저장소 글꼴을 Craft 앱이 보게 한다 — 앱들은 시스템 글꼴만 찾으므로 fontconfig 설정을 넘긴다(자식 프로세스에 물려줌)
_fc = Path(__file__).resolve().parent / "assets" / "fontconfig.conf"
if _fc.exists():
    os.environ.setdefault("FONTCONFIG_FILE", str(_fc))
