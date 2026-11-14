"""실사 합성 재료(live) — 업로드한 실사 · 생성 영상 위에 글자 · 그림을 공간에 맞춰 얹는다. 본체는 engine/craft/live.py.
EffectCraft(카메라 추적 · 분리 · 채우기 · 합성)를 쓰고, 합성 프로젝트(.ecproj)가 편집 파일로 남는다."""
from __future__ import annotations

import shutil
from pathlib import Path


def live_material(m: dict, out: Path, work: Path) -> dict:
    from ..live import compose
    from ..materials import ROOT, _hash, find_upload
    src = Path(m["src"]) if m.get("src") else None
    if not src:
        raise RuntimeError(f"{m.get('id')}: src(올린 영상) 가 필요합니다")
    abs_of = lambda p: str(p if Path(p).is_absolute() else ROOT / p)  # noqa: E731
    spec = {**m, "src": abs_of(src), "items": [{**i, **{k: abs_of(i[k]) for k in ("file",) if i.get(k)}} for i in m.get("items") or []]}
    r = compose(spec, work / f"{out.stem}.live")
    dst = out.with_suffix(".mp4")
    shutil.copyfile(r["file"], dst)
    proj = Path(r["project"])
    return {"app": "effectcraft", "apps": ["effectcraft"],
            "file_suffix": ".mp4", "as": "video", "mobile": True, "editable": str(proj.relative_to(ROOT)), "editable_hash": _hash(proj),
            "follow_px": r["follow_px"], "aov": r["aov"], "check": r.get("check")}


ADAPTERS = {"live": live_material}
