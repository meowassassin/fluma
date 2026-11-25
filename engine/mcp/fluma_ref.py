#!/usr/bin/env python3
"""레퍼런스 분석 한 번에(작업으로 돈다) — 쇼츠 분해 → 스타일 카드 → 채널 카드.

  python3 engine/mcp/fluma_ref.py <영상 id> [--n 5]
마지막에 FLUMA_RESULT(card=채널 카드 경로 · channel · style=스타일 카드 경로).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("vid")
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    steps = [("[1/3] 쇼츠 분해", ["engine/research/shorts_xray.py", a.vid]),
             ("[2/3] 스타일 카드", ["engine/research/ref_style.py", a.vid]),
             ("[3/3] 채널 카드", ["engine/research/ref_channel.py", a.vid, "--n", str(a.n)])]
    r = None
    for label, args in steps:
        print(f"{label} 단계 시작", flush=True)
        r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            fail("reference", stage=args[0], error=(r.stderr or r.stdout).strip()[-400:])
    last = json.loads(r.stdout.strip().splitlines()[-1])
    ch = last["channel"]
    ok("reference", card=f"data/public/trends/channels/{ch}/channel.md", channel=ch,
       style=f"data/public/trends/xray/{a.vid}/style/style.md")


if __name__ == "__main__":
    main()
