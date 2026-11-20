#!/usr/bin/env python3
"""형태(form) 도구 — 데이터로 빚은 형태를 화풍으로 그려 본다. 작성법: engine/craft/form/README.md

  python3 engine/craft/form_cli.py preview <형태.json> [--style cel] [--azimuth 35 --elevation 20]   # 작게(540) 빠르게 → 경로 출력, Read 로 본다
  python3 engine/craft/form_cli.py render  <형태.json> --out <파일.png> [--style flat|cel|sketch|clay] [--bg "#hex"] [--res 1080]
  python3 engine/craft/form_cli.py styles                                                              # 네 화풍 한 장 비교(같은 형태)
콘티에는 재료 {"type": "form", "scene": "$FILE:data/compositions/<id>/forms/<이름>.json", "style": (없으면 direction.art.style)} 로 넣는다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft import form  # noqa: E402

TMP = ROOT / "data" / "workspace" / "tmp" / "form"


def _arg(a: list[str], k: str, d=None):
    return a[a.index(k) + 1] if k in a else d


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] not in ("preview", "render", "styles"):
        print(__doc__); return 2
    cmd, src = a[0], (a[1] if len(a) > 1 else None)
    if not src:
        print(__doc__); return 2
    sc = json.loads((ROOT / src if not Path(src).is_absolute() else Path(src)).read_text("utf-8"))
    view = {k: float(_arg(a, f"--{k}")) for k in ("azimuth", "elevation") if _arg(a, f"--{k}") is not None} or None
    t = time.time()
    name = Path(src).stem
    if cmd == "styles":
        from PIL import Image
        TMP.mkdir(parents=True, exist_ok=True)
        tiles = [form.draw(sc, s, res=540, view=view, background="#f3efe6") for s in form.STYLES]
        sheet = Image.new("RGB", (540 * 4, 540), "#f3efe6")
        for i, im in enumerate(tiles):
            sheet.paste(im.convert("RGB"), (i * 540, 0))
        out = TMP / f"{name}.styles.png"; sheet.save(out)
    else:
        res = 540 if cmd == "preview" else int(_arg(a, "--res", 1080))
        out = Path(_arg(a, "--out") or TMP / f"{name}.{_arg(a, '--style', 'cel')}.png")
        out = out if out.is_absolute() else ROOT / out
        form.draw(sc, _arg(a, "--style", "cel"), out, res=res, view=view, background=_arg(a, "--bg"))
    print(f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}  ({time.time() - t:.1f}초)")
    if cmd != "styles":
        apart = form.parts_apart(sc, view)
        if apart:
            print(f"△ 떨어진 덩어리 {apart}개 — 몸과 이어지지 않은 부품이 있다(뼈대 rig 로 빚으면 관절에 붙는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
