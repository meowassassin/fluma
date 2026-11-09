"""콘티를 읽을 때 짧게 적은 칸을 앱 재료로 펼친다(파일은 그대로)
  - archive: 실제 자료(위키미디어 공용) — 받아서 화면을 덮게 놓고 출처 · 저작자 표시를 남긴다
  - refine: {"recipe": 이름, "vars": {…}} 만 적으면 레시피를 펼친다 — 영상마다 코드를 쓰지 않는다
(2026-11-09: 규칙으로 그리던 형식 · 인물 엔진(forms · cast · silhouette)은 없앴다 — 그림은 에이전트가 VectorCraft 로 직접 그린다)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())


def _pmat(mid, w, h, steps, show=True) -> dict:
    r = {"id": mid, "type": "craft", "app": "photocraft", "new": {"width": w, "height": h, "background": "#ffffff"}, "steps": steps, "place": "full",
         "export": {"format": "png", "size": [w, h]}}
    if not show:
        r["show"] = False
    return r


def _archive(m: dict, sb: dict, w: int, h: int) -> list[dict]:
    """실제 자료: 받아서 화면을 덮게 놓고 출처를 콘티에 남긴다"""
    from commons import fetch
    from PIL import Image
    f = ROOT / "data" / "public" / "archive" / sb["id"] / f"{m['id']}.jpg"
    mf = f.with_suffix(".json")
    if not f.exists() or not mf.exists():
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(fetch(m["title"], f, int(m.get("width", 2400))), ensure_ascii=False), "utf-8")
    meta = json.loads(mf.read_text("utf-8"))
    src = sb.setdefault("sources", [])
    if meta.get("page") and meta["page"] not in src:
        src.append(meta["page"])
    sb.setdefault("credits", {})[m["id"]] = f"{meta.get('artist') or ''} · {meta.get('license')}".strip(" ·")
    cf = f.parent / "credits.txt"                     # 설명란 '사용한 자료' — CC BY · BY-SA 는 저작자 표시가 조건이다
    line = f"{meta.get('title')} — {meta.get('artist') or '저작자 미상'} · {meta.get('license')} · {meta.get('page')}"
    old = cf.read_text("utf-8").splitlines() if cf.exists() else []
    if line not in old:
        cf.write_text("\n".join(old + [line]) + "\n", "utf-8")
    with Image.open(f) as im:
        iw, ih = im.size
    fit = m.get("fit", "cover")
    s = (max if fit == "cover" else min)(w / iw, h / ih) * 100
    st = []
    if fit != "cover":                               # 세로 사진: 같은 사진을 흐리게 깔고 가운데에 놓는다
        s2 = max(w / iw, h / ih) * 100
        st += [{"id": "file.placeEmbedded", "params": {"path": str(f.relative_to(ROOT)), "center": [w / 2, h / 2], "smartObject": False, "scale": round(s2, 3)}},
               {"id": "filter.blur.gaussianBlur", "params": {"radius": 42}}, {"id": "layer.newAdjustmentLayer.hueSaturation", "params": {"saturation": -25, "lightness": -46}}]
    st.append({"id": "file.placeEmbedded", "params": {"path": str(f.relative_to(ROOT)), "center": [w / 2, h / 2 + float(m.get("dy", 0))], "smartObject": False, "scale": round(s, 3)}})
    return [_pmat(m["id"], w, h, st, show=m.get("show", True) is not False)]


def _recipe(p: dict) -> dict:
    if p.get("steps") or not p.get("recipe"):
        return p
    from craft import recipes
    r = json.loads((ROOT / ".claude" / "skills" / "refine" / "recipes" / f"{p['recipe']}.json").read_text("utf-8"))
    q = recipes.expand(r, {"COMP": "$COMP", **{k: str(v) for k, v in (p.get("vars") or {}).items()}})
    return {**q, "target": r.get("target", "motion"), "why": p.get("why") or q.get("why")}


def expand_sb(sb: dict) -> dict:
    from engines import aspect_size
    w, h = aspect_size(sb)
    for sc in sb.get("scenes") or []:
        out = []
        for m in sc.get("materials") or []:
            out += _archive(m, sb, w, h) if m.get("type") == "archive" else [m]
        sc["materials"] = out
        sc["refine"] = [_recipe(p) for p in sc.get("refine") or []]
    return sb
