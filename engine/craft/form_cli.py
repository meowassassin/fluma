#!/usr/bin/env python3
"""형태(form) 도구 — 데이터로 빚은 형태를 화풍으로 그려 본다. 작성법: engine/craft/form/README.md

  python3 engine/craft/form_cli.py preview <형태.json> [--style cel] [--azimuth 35 --elevation 20] [--ref <참고 그림>]  # --ref: 참고 그림 | 내 형태 나란히   # 작게(540) 빠르게 → 경로 출력, Read 로 본다
  (모든 명령: --style 이름 대신 --look '{화풍 값 JSON}' — engine/craft/form/README.md '화풍 값')
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
    lk = _arg(a, "--look")                      # 화풍 값(JSON) — 예: --look '{"bands":2,"mono":true,"tone":7}'
    style_arg = json.loads(lk) if lk else _arg(a, "--style", "cel")
    if cmd == "anim":       # 움직임: anim.tracks 대로 프레임 묶음(…/f000.png) + 확인용 시트 한 장(4칸)
        from PIL import Image
        d = Path(_arg(a, "--out-dir") or TMP / f"{name}.anim")
        d = d if d.is_absolute() else ROOT / d
        an = form.animate(sc, style_arg, d, res=int(_arg(a, "--res", 720)), view=view, background=_arg(a, "--bg"))
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
        out = Path(_arg(a, "--out") or TMP / f"{name}.{'look' if lk else _arg(a, '--style', 'cel')}.png")
        out = out if out.is_absolute() else ROOT / out
        form.draw(sc, style_arg, out, res=res, view=view, background=_arg(a, "--bg"))
        if _arg(a, "--ref"):     # 참고 그림(engine/research/ref_images.py 로 받은 NN.jpg)과 나란히 — 비례 · 실루엣 · 과장 정도를 견준다
            from PIL import Image
            rf = Path(_arg(a, "--ref")); rf = rf if rf.is_absolute() else ROOT / rf
            ref = Image.open(rf).convert("RGB"); ref.thumbnail((540, 540))
            mine = Image.open(out).convert("RGBA"); bg = Image.new("RGBA", mine.size, "#f3efe6"); bg.alpha_composite(mine)
            side = Image.new("RGB", (540 * 2, 540), "#ffffff")
            side.paste(ref, ((540 - ref.width) // 2, (540 - ref.height) // 2)); side.paste(bg.convert("RGB").resize((540, 540)), (540, 0))
            out = out.with_name(out.stem + ".vsref.jpg"); side.save(out, quality=85)
    print(f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}  ({time.time() - t:.1f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
