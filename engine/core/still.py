#!/usr/bin/env python3
"""
정지 화면 (에이전트·장면 코멘트·썸네일용). 엔진의 snapshot 을 쓴다.

  python3 engine/core/still.py data/storyboards/<id>.json <초> [<초> …] [--engine 이름] [--template 이름] [--out 폴더]
  python3 engine/core/still.py data/storyboards/<id>.json 1.5 7 12

마지막 줄들에 PNG 경로를 출력한다 (기본 data/workspace/stills/<id>-<엔진>-<템플릿>-<초>.png).
"""
import argparse
import shutil
import sys
from pathlib import Path
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from engines import ROOT, adapter, make_job  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("seconds", nargs="+", type=float)
    ap.add_argument("--engine")
    ap.add_argument("--template")
    ap.add_argument("--out", default=str(ROOT / "data" / "workspace" / "stills"))
    a = ap.parse_args()
    job = make_job(Path(a.storyboard), a.engine, a.template)
    pngs = adapter(job.engine).snapshot(job, a.seconds)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for s, p in zip(a.seconds, pngs):
        dst = out / f"{job.sb['id']}-{job.engine}-{job.template}-{s:g}.png"
        shutil.copy2(p, dst)
        print(dst)


if __name__ == "__main__":
    main()
