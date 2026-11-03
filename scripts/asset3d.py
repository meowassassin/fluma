#!/usr/bin/env python3
"""
움직이는 3D 모델(동물 · 사람 · 사물) 받기 — Blender 개체 요소용. Blender 안은 네트워크가 막혀 있어 여기서 미리 받는다.

  python3 scripts/asset3d.py list                       # 카탈로그(assets3d/catalog.json): 이름 · 동작 · 라이선스
  python3 scripts/asset3d.py fetch <모델> <영상 id>      # → compositions/<id>/blender/assets/<모델>.glb (+ CREDITS.txt 에 출처)

받은 파일은 workspace/asset-cache/ 에 남겨 같은 모델은 다시 받지 않는다. CC-BY 모델은 CREDITS.txt 의 문구를 영상 설명에 넣는다.
"""
import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "assets3d" / "catalog.json").read_text(encoding="utf-8"))
CACHE = ROOT / "workspace" / "asset-cache"


def find(name: str) -> dict:
    m = next((x for x in CAT["models"] if x["name"] == name), None)
    if not m:
        sys.exit(f"카탈로그에 없음: {name} ({', '.join(x['name'] for x in CAT['models'])})")
    return m


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list")
    f = sp.add_parser("fetch"); f.add_argument("name"); f.add_argument("id")
    a = ap.parse_args()
    if a.cmd == "list":
        for m in CAT["models"]:
            print(f"{m['name']:<8} {m['kind']:<7} {m['title']}\n{'':<16} 동작: {', '.join(m['actions'])} · 상업: {m['commercial']}\n{'':<16} {m['license']}")
        print(f"\n더 찾기: {CAT['more']}")
        return
    if not all(ch.isalnum() or ch in "-_" for ch in a.id):
        sys.exit("영상 id 가 올바르지 않음")
    m = find(a.name)
    CACHE.mkdir(parents=True, exist_ok=True)
    src = CACHE / f"{m['name']}.glb"
    if not src.exists():
        print(f"[받는 중] {m['url']}", file=sys.stderr)
        tmp = src.with_suffix(".part")
        with urllib.request.urlopen(m["url"], timeout=120) as r, open(tmp, "wb") as fo:
            shutil.copyfileobj(r, fo)
        tmp.rename(src)
    dst_dir = ROOT / "compositions" / a.id / "blender" / "assets"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / src.name)
    credits = dst_dir / "CREDITS.txt"
    lines = credits.read_text(encoding="utf-8").splitlines() if credits.exists() else []
    if m["credit"] not in lines:
        lines.append(m["credit"])
        credits.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[모델] {m['title']} · 동작 {', '.join(m['actions'])} · 상업 {m['commercial']}", file=sys.stderr)
    print(f"assets/{src.name}")


if __name__ == "__main__":
    main()
