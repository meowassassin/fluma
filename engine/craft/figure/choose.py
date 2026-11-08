"""화풍 고르기 — 주제 · 분위기 · 장면 형식 · 앞 영상 이력에서 후보를 점수로 고른다. 점수는 제안일 뿐이고, 콘티의 direction.art.figure 나 재료 style 이 언제나 이긴다.
같은 화풍이어도 영상마다 칸(밀도 · 선 굵기 · 대비 · 빗금 각도)을 달리해 똑같아지지 않게 한다."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
HIST = ROOT / "data" / "workspace" / "figure-styles.json"
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from craft.figure.styles import STYLES  # noqa: E402

FAT = ("blackfigure", "woodcut", "pop")      # 작게 놓아도 읽히는 화풍
KIND = {"sketch": "sketch_in", "engrave": "still", "woodcut": "still", "wash": "sketch_in", "blackfigure": "still", "inkline": "sketch_in", "pop": "still"}


def history() -> dict:
    try:
        return json.loads(HIST.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def remember(sid: str, style: str) -> None:
    h = history()
    h[sid] = style
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(h, ensure_ascii=False, indent=0), "utf-8")


def rank(sb: dict, form: str | None = None) -> list[tuple[str, float, str]]:
    text = " ".join(str(sb.get(k) or "") for k in ("title", "topic", "tone", "mood")) + " " + str((sb.get("direction") or {}).get("art", "")) + " " + " ".join(str(sc.get("narration") or "") for sc in (sb.get("scenes") or [])[:4])
    h = history()
    recent = [v for k, v in list(h.items())[-3:] if k != sb.get("id")]
    out = []
    for name, st in STYLES.items():
        hits = [m for m in st["mood"] if m in text]
        sc = len(hits) * 2 + (2 if form and form in st["fits"] else 0) - recent.count(name) * 1.5
        out.append((name, sc, f"{st['title']}: 주제어 {hits or '없음'}" + (f" · {form} 장면과 어울림" if form and form in st["fits"] else "") + (f" · 최근 {recent.count(name)}번 씀" if name in recent else "")))
    return sorted(out, key=lambda r: -r[1])


def vary(sid: str, style: str) -> dict:
    """영상마다 같은 화풍도 조금씩 다르게"""
    b = hashlib.sha1(f"{sid}:{style}".encode()).digest()
    return {"density": round(.85 + b[0] / 255 * .35, 2), "line": round(.9 + b[1] / 255 * .3, 2), "contrast": round(1.1 + b[2] / 255 * .4, 2), "angle": -40 - b[3] % 35}


def pick(sb: dict, material: dict | None = None, form: str | None = None) -> dict:
    m = material or {}
    art = (sb.get("direction") or {}).get("art")
    fixed = m.get("style") or (art.get("figure") if isinstance(art, dict) else None)
    ranked = rank(sb, form)
    small = float(m.get("on_screen") or 0)                  # 화면에 나올 높이(px). 작게 쓰면 가는 선은 사라진다
    style = fixed or (next((r[0] for r in ranked if r[0] in FAT), ranked[0][0]) if small and small < 360 else ranked[0][0])
    params = {**vary(sb.get("id", ""), style), **(m.get("style_params") or {})}
    if small and "line" not in (m.get("style_params") or {}):
        params["line"] = round(params["line"] * max(1.0, 620 / small), 2)      # 줄어드는 만큼 선을 키운다
    return {"style": style, "params": params, "anim": m.get("anim") or KIND[style]}
