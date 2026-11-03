#!/usr/bin/env python3
"""
로고 · 아이콘(2D, SVG) 받기 — 장면에 GitHub · Docker 같은 로고나 서비스 아이콘이 필요할 때.

  python3 scripts/icons.py find <낱말>                 # 받을 수 있는 곳 찾기 (로컬 팩 → Simple Icons)
  python3 scripts/icons.py fetch <id> <이름> [<이름> …]  # → compositions/<id>/<이름>.svg (scene.js 에서 "<이름>.svg" 로 쓴다)

찾는 순서
  1. 로컬 아이콘 팩 assets2d/icons/**/<이름>.svg — 사용자가 받아 둔 공식 팩(예: AWS 아키텍처 아이콘은 aws.amazon.com/architecture/icons
     에서 받아 assets2d/icons/aws/ 에 풀면 됨. AWS 약관상 아키텍처 다이어그램 용도로 쓸 수 있다)
  2. Simple Icons (CC0, 브랜드 로고 3000여 개) — https://simpleicons.org . AWS 로고는 없다
  못 찾으면 에이전트가 단순한 SVG 를 직접 그린다(남의 로고를 흉내 내지 말고 '서버 · 버킷 · 지구본' 같은 일반 모양으로).
로고는 상표다: 설명 · 정보 목적으로 원래 모양 · 색 그대로 쓰고, 바꿔 그리거나 우리 것처럼 보이게 쓰지 않는다.
"""
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "assets2d" / "icons"
CACHE = ROOT / "workspace" / "asset-cache" / "icons"
SI_VER = "16.36.0"
SI = f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VER}/icons/{{slug}}.svg"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("+", "plus").replace(".", "dot"))


def local(name: str) -> list[Path]:
    if not PACKS.exists():
        return []
    s = slug(name)
    return sorted(p for p in PACKS.rglob("*.svg") if s in slug(p.stem))


def simple_icon(name: str) -> Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    s = slug(name)
    dst = CACHE / f"{s}.svg"
    if dst.exists():
        return dst
    try:
        with urllib.request.urlopen(SI.format(slug=s), timeout=20) as r:
            svg = r.read().decode("utf-8")
    except Exception:  # noqa: BLE001  (없는 이름 · 오프라인)
        return None
    # Simple Icons 는 검정 단색 path → 공식 브랜드 색을 채운다(없으면 흰색)
    color = "#FFFFFF"
    try:
        with urllib.request.urlopen(f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VER}/data/simple-icons.json", timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        items = data if isinstance(data, list) else data.get("icons", [])
        hit = next((i for i in items if slug(i.get("slug") or i.get("title", "")) == s), None)
        if hit and hit.get("hex"):
            color = "#" + hit["hex"]
    except Exception:  # noqa: BLE001
        pass
    svg = svg.replace("<svg ", f'<svg fill="{color}" ', 1)
    dst.write_text(svg, encoding="utf-8")
    return dst


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("find", "fetch"):
        sys.exit(__doc__)
    if sys.argv[1] == "find":
        name = sys.argv[2]
        hits = local(name)
        for h in hits[:20]:
            print(f"로컬 팩  {h.relative_to(ROOT)}")
        si = simple_icon(name)
        print(f"Simple Icons (CC0)  {slug(name)}  {'있음' if si else '없음'}")
        if not hits and not si:
            print("→ 없음: 일반 모양 SVG 를 직접 그리거나, 공식 아이콘 팩을 assets2d/icons/ 에 받아 두세요")
        return
    sid, names = sys.argv[2], sys.argv[3:]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", sid):
        sys.exit("영상 id 가 올바르지 않음")
    out_dir = ROOT / "compositions" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    for n in names:
        src = (local(n) or [None])[0] or simple_icon(n)
        if not src:
            print(f"✗ {n}: 못 찾음 — 일반 모양 SVG 를 compositions/{sid}/{slug(n)}.svg 로 직접 그리세요", file=sys.stderr)
            continue
        dst = out_dir / f"{slug(n)}.svg"
        shutil.copy2(src, dst)
        origin = "로컬 팩" if PACKS in src.parents else "Simple Icons (CC0)"
        print(f"{dst.name}\t{origin}\t← scene.js 에서 \"{dst.name}\" (K.image 나 <img>)")


if __name__ == "__main__":
    main()
