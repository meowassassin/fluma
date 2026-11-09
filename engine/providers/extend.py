#!/usr/bin/env python3
"""세로 확장(아웃페인팅) — 가로 사진을 9:16 으로: 원본은 가운데 그대로 두고 위 · 아래를 같은 장면으로 이어 그린다.
설정 → 보기 · 만들기 · 말하기 의 '고치기 · 이미지 편집 · 세로 확장'(edit.image) 모델을 골랐을 때만. 없으면 지금처럼 가운데 띠 + 흐린 배경.

원본을 지키는 방법: 9:16 캔버스 가운데에 원본을 놓은 그림을 참조로 주고 위아래를 이어 그리게 한 뒤,
모델이 가운데를 조금 바꿨더라도 **원본 픽셀을 다시 덮는다**(가장자리만 부드럽게 섞음) — 사실 자료(사진 · 캡처)가 바뀌지 않는다.

  python3 engine/providers/extend.py <그림> [--out 경로] [--hint "장면 설명(영어)"] [--sid <콘티 id>] [--approve]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

CACHE = ROOT / "data" / "cache" / "providers" / "extend"
W, H = 1080, 1920


def needs(path: Path) -> bool:
    """가로(또는 9:16 보다 넓은) 그림인가"""
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    return w / max(1, h) > (9 / 16) * 1.15


def _canvas(src: Path, out: Path) -> tuple[Path, tuple[int, int, int, int]]:
    """9:16 캔버스 가운데에 원본(폭 맞춤) — 위아래는 원본 가장자리를 늘린 흐린 바탕(모델이 이어 그릴 자리)"""
    from PIL import Image, ImageFilter
    im = Image.open(src).convert("RGB")
    s = W / im.width
    fw, fh = W, max(1, int(im.height * s))
    fg = im.resize((fw, fh))
    bg = im.resize((W, H)).filter(ImageFilter.GaussianBlur(40))
    y = (H - fh) // 2
    bg.paste(fg, (0, y))
    bg.save(out)
    return out, (0, y, fw, y + fh)


def _paste_back(gen: Path, src: Path, box: tuple[int, int, int, int], out: Path) -> Path:
    """생성 결과(9:16) 위에 원본을 다시 덮는다 — 경계 24px 만 부드럽게"""
    from PIL import Image, ImageFilter
    g = Image.open(gen).convert("RGB").resize((W, H))
    x0, y0, x1, y1 = box
    fg = Image.open(src).convert("RGB").resize((x1 - x0, y1 - y0))
    edge = Image.new("L", fg.size, 0)
    edge.paste(255, (0, 24, fg.width, max(25, fg.height - 24)))
    mask = edge.filter(ImageFilter.GaussianBlur(10))
    g.paste(fg, (x0, y0), mask)
    g.save(out, quality=95)
    return out


def vertical(src: Path, out: Path | None = None, hint: str = "", sid: str = "-", approve: bool = False, sb: dict | None = None) -> Path | None:
    """가로 그림 → 9:16 그림(원본 가운데 그대로). 모델이 없거나 이미 세로면 None"""
    import catalog
    import openrouter as OR
    src = Path(src)
    mdl = catalog.chosen("edit.image", sb)
    if not mdl or not needs(src):
        return None
    key = hashlib.sha1(src.read_bytes() + f"|{mdl}|{hint}".encode()).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True)
    done = CACHE / f"{key}.jpg"
    if not done.exists():
        canvas, box = _canvas(src, CACHE / f"{key}.canvas.png")
        est = catalog.estimate_image(mdl)
        catalog.guard(sid, "edit.image", mdl, est, f"세로 확장 {src.name}", approve)
        prompt = ("Extend this image to a full vertical 9:16 frame (outpainting). The original photo occupies the middle band — keep it exactly as it is. "
                  "Continue the same scene naturally above and below it: same perspective, horizon, lighting direction, colors, grain and depth of field. "
                  + (f"Scene: {hint.strip()}. " if hint.strip() else "")
                  + "The added areas contain only the surrounding environment (sky, ceiling, floor, ground, walls, table surface), with no new people, no new animals, no text, no logos.")
        r = OR.make_image(mdl, prompt, CACHE / f"{key}.gen", aspect="9:16", refs=[canvas])
        catalog.record(sid, "edit.image", mdl, r["cost"], f"세로 확장 {src.name}", est=est)
        _paste_back(r["file"], src, box, done)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(done.read_bytes())
        return Path(out)
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image"); ap.add_argument("--out"); ap.add_argument("--hint", default=""); ap.add_argument("--sid", default="-")
    ap.add_argument("--approve", action="store_true", help="사용자가 금액을 보고 승인했을 때만")
    a = ap.parse_args()
    import catalog
    try:
        r = vertical(Path(a.image), Path(a.out) if a.out else None, a.hint, a.sid, a.approve)
    except catalog.NeedApproval as e:
        print(f"[승인 필요] {e}")
        return 20
    print(r if r else "세로 확장 안 함(이미 세로이거나 '고치기' 모델이 없음)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
