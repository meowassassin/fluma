#!/usr/bin/env python3
"""형태(form) 도구 — 데이터로 빚은 형태를 화풍으로 그려 본다. 작성법: engine/craft/form/README.md

  python3 engine/craft/form_cli.py preview <형태.json> [--style cel] [--azimuth 35 --elevation 20]   # 작게(540) 빠르게 → 경로 출력, Read 로 본다
  python3 engine/craft/form_cli.py render  <형태.json> --out <파일.png> [--style flat|cel|sketch|clay] [--bg "#hex"] [--res 1080]
  python3 engine/craft/form_cli.py anim    <형태.json> --out-dir data/compositions/<id>/forms/<이름>.anim [--style cel] [--res 720]   # 움직임(anim) 프레임 묶음 → …/f000.png
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


def _warn_cut(sides):
    if sides:
        print(f"△ 화면 {' · '.join(sides)} 가장자리에서 형태가 잘린다 — 바닥 받침판이면 \"floor\": true(그리지 않고 딛기 · 그림자만), "
              f"소품이면 카메라 radius 를 키우거나 형태를 안으로")


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] not in ("preview", "render", "styles", "anim"):
        print(__doc__); return 2
    cmd, src = a[0], (a[1] if len(a) > 1 else None)
    if not src:
        print(__doc__); return 2
    sc = json.loads((ROOT / src if not Path(src).is_absolute() else Path(src)).read_text("utf-8"))
    view = {k: float(_arg(a, f"--{k}")) for k in ("azimuth", "elevation") if _arg(a, f"--{k}") is not None} or None
    t = time.time()
    name = Path(src).stem
    if cmd == "anim":       # 움직임: anim.tracks 대로 프레임 묶음(…/f000.png) + 확인용 시트 한 장(4칸)
        from PIL import Image
        d = Path(_arg(a, "--out-dir") or TMP / f"{name}.anim")
        d = d if d.is_absolute() else ROOT / d
        an = form.animate(sc, _arg(a, "--style", "cel"), d, res=int(_arg(a, "--res", 720)), view=view, background=_arg(a, "--bg"))
        n = an["frames"]
        pick = sorted({0, n // 4, n // 2, (3 * n) // 4})
        ims = [Image.open(d / f"f{i:03d}.png").convert("RGBA") for i in pick]
        w, h = ims[0].size
        sheet = Image.new("RGBA", (w * len(ims), h), "#f3efe6")
        for k, im in enumerate(ims):
            sheet.alpha_composite(im, (k * w, 0))
        sh = d / "sheet.jpg"; sheet.convert("RGB").resize((w * len(ims) // 2, h // 2)).save(sh)
        rel = lambda p: p.relative_to(ROOT) if p.is_relative_to(ROOT) else p  # noqa: E731
        print(f"{rel(Path(an['first']))}  ({n}장 · {an['fps']}fps · {time.time() - t:.1f}초) — 장면 코드: K.image('<이 경로>', x, y, 배율) 가 반복 재생 · 확인: {rel(sh)}")
        if not _arg(a, "--bg"):
            _warn_cut(sorted({s for im in ims for s in form.edge_cut(im)}))
        return 0
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
    if cmd != "styles" and not _arg(a, "--bg"):
        from PIL import Image
        _warn_cut(form.edge_cut(Image.open(out)))
    if cmd != "styles":
        apart = form.parts_apart(sc, view)
        if apart:
            print(f"△ 떨어진 덩어리 {apart}개 — 몸과 이어지지 않은 부품이 있다(뼈대 rig 로 빚으면 관절에 붙는다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
