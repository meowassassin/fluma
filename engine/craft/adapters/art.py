"""직접 그린 그림 재료(art) — illustrate 스킬로 그린 SVG 를 VectorCraft 로 렌더한다. 편집 파일이 남는다.
  {"type": "art", "id": "hd_think0", "svg": "data/compositions/<id>/art/x.svg", "hide": ["shock"]}
hide: 지울 그룹 id — 눈 · 입 그룹만 바꿔 표정을 만든다. 몸을 다시 그리지 않는다. 화면에는 motion-cast 레시피로 놓는다."""
from __future__ import annotations

import re
from pathlib import Path


def drop(s: str, ids) -> str:
    for i in ids or []:
        m = re.search(r'<g id="%s"[^>]*>' % re.escape(i), s)
        if not m:
            raise RuntimeError(f"그림에 그룹 {i} 가 없습니다")
        d, k = 1, m.end()
        for t in re.finditer(r"<g\b|</g>", s[k:]):
            d += 1 if t.group() != "</g>" else -1
            if d == 0:
                s = s[:m.start()] + s[k + t.end():]
                break
    return s


def art(m: dict, out: Path, work: Path) -> dict:
    from ..materials import ROOT, _hash, _run, cli
    src = ROOT / m["svg"]
    tmp = work / f"{m['id']}.svg"
    tmp.write_text(drop(src.read_text("utf-8"), m.get("hide")), "utf-8")
    _run([cli("vectorcraft"), "convert", tmp, out, "--scale", str(m.get("scale", 1))], work)
    ed = work / f"{m['id']}.vectorcraft"
    _run([cli("vectorcraft"), "convert", tmp, ed], work)
    return {"app": "vectorcraft", "as": "image", "editable": str(ed.relative_to(ROOT)), "editable_hash": _hash(ed)}


ADAPTERS = {"art": art}
