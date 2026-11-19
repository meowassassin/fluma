"""장면 재료 — 카드·목업 편향을 막고 증거(로고 · 캡처 · 문서 · 실제 화면)를 기본으로 맞춘다.

  python3 engine/story/material_evidence.py <콘티.json> [--write]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine"))

EVIDENCE = frozenset({
    "web", "screen", "video", "photo", "photo_grade", "image", "stock", "meme", "live",
    "doc_quote", "document", "archive", "chart",
})
SLIDE = frozenset({"info_card", "diagram", "template_card", "thumbnail"})
SKIP_ROLES = frozenset({"outro", "cta", "mood"})
EXEMPT_FMT = frozenset({"daily", "emotional", "clip", "ranking"})

BRANDS: list[tuple[str, str]] = [
    (r"\bCursor\b", "cursor"),
    (r"\bClaude\b", "anthropic"),
    (r"\bAnthropic\b", "anthropic"),
    (r"\bChatGPT\b", "openai"),
    (r"\bOpenAI\b", "openai"),
    (r"\bGitHub\b", "github"),
    (r"\bDocker\b", "docker"),
    (r"\bKubernetes\b|k8s\b", "kubernetes"),
    (r"\bAWS\b", "amazonwebservices"),
    (r"\bGCP\b|Google Cloud\b", "googlecloud"),
    (r"\bAzure\b", "microsoftazure"),
    (r"\bVS\s*Code\b|Visual Studio Code\b", "visualstudiocode"),
    (r"\bNotion\b", "notion"),
    (r"\bSlack\b", "slack"),
    (r"\bFigma\b", "figma"),
    (r"\bJira\b", "jira"),
    (r"\bPostgres|PostgreSQL\b", "postgresql"),
    (r"\bRedis\b", "redis"),
    (r"\bNginx\b", "nginx"),
    (r"\bTerraform\b", "terraform"),
    (r"\bVercel\b", "vercel"),
    (r"\bNext\.js\b", "nextdotjs"),
    (r"\bReact\b", "react"),
    (r"\bTypeScript\b", "typescript"),
    (r"\bPython\b", "python"),
    (r"\bLinux\b", "linux"),
    (r"\bNVIDIA\b", "nvidia"),
]

VISUAL_FOR = {
    "web": "screenshot",
    "screen": "screenshot",
    "video": "footage",
    "photo": "still",
    "photo_grade": "still",
    "image": "still",
    "stock": "footage",
    "meme": "still",
    "live": "footage",
    "doc_quote": "screenshot",
    "document": "screenshot",
    "archive": "still",
    "chart": "chart",
    "ui_mock": "screenshot",
    "icon": "still",
    "illustration": "still",
    "diagram": "chart",
    "info_card": "text",
    "template_card": "text",
}


def _icons_mod():
    spec = importlib.util.spec_from_file_location("fluma_icons", ROOT / "engine" / "capture" / "icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _primary(mats: list[dict]) -> list[dict]:
    return [m for m in mats if isinstance(m, dict) and m.get("type") not in ("overlay", "stat", "text")]


def is_evidence(m: dict) -> bool:
    t = m.get("type")
    if t in EVIDENCE:
        return True
    if t in ("icon", "illustration") and m.get("src"):
        return True
    if t == "ui_mock" and m.get("src") and not m.get("mock"):
        return True
    return False


def is_mock_only(m: dict) -> bool:
    return m.get("type") == "ui_mock" and bool(m.get("mock")) and not m.get("src")


def slide_count(mats: list[dict]) -> int:
    return sum(1 for m in _primary(mats) if m.get("type") in SLIDE or is_mock_only(m))


def brands_in(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pat, slug in BRANDS:
        if re.search(pat, text, re.I):
            if slug not in seen:
                seen.add(slug)
                out.append((slug, slug))
    for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", text):
        w = m.group(0)
        if w in ("Git", "Pull", "Request", "Merge", "Deploy", "Check", "Flag", "Roll", "Back"):
            continue
        ic = _icons_mod()
        si = ic.simple_icon(w)
        if si and w.lower() not in seen:
            seen.add(w.lower())
            out.append((w, ic.slug(w)))
    return out[:4]


def fetch_icon(sid: str, slug: str) -> str | None:
    ic = _icons_mod()
    src = (ic.local(slug) or [None])[0] or ic.simple_icon(slug)
    if not src:
        return None
    out_dir = ROOT / "data" / "compositions" / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{slug}.svg"
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        shutil.copy2(src, dst)
    return str(dst.relative_to(ROOT))


def _scene_blob(sc: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                sc.get("caption", ""),
                sc.get("narration", ""),
                str((sc.get("visual") or {}).get("primary", "")),
                str((sc.get("visual") or {}).get("secondary", "")),
            ],
        )
    )


def _dedupe_slides(mats: list[dict], fmt: str | None) -> list[dict]:
    prim = _primary(mats)
    slides = [m for m in prim if m.get("type") in SLIDE or is_mock_only(m)]
    if len(slides) <= 1:
        return mats
    keep: dict | None = None
    designed = next((m for m in slides if m.get("type") == "ui_mock" and str(m.get("id") or "").endswith("app")), None)
    if designed is not None:   # 디자이너가 새로 만든 앱 화면이 이긴다(2026-11-18 감사: 앞에 있던 도표만 남기고 지웠다)
        keep = designed
    elif fmt == "compare":
        keep = next((m for m in slides if m.get("type") == "diagram"), None) or slides[0]
    else:
        keep = next((m for m in slides if m.get("type") != "info_card"), slides[0])
    drop_ids = {m.get("id") for m in slides if m is not keep}
    out = []
    for m in mats:
        if m.get("id") in drop_ids and m.get("type") in SLIDE | {"ui_mock"}:
            continue
        out.append(m)
    return out


def _ensure_icon(sid: str, scene_i: int, sc: dict, mats: list[dict]) -> list[dict]:
    if any(m.get("type") in ("icon", "illustration") for m in mats):
        return mats
    hits = brands_in(_scene_blob(sc))
    if not hits:
        return mats
    slug = hits[0][1]
    rel = fetch_icon(sid, slug)
    if not rel:
        return mats
    cue = hits[0][0]
    icon = {
        "id": f"s{int(scene_i):02d}logo",
        "type": "icon",
        "src": rel,
        "what": f"{hits[0][0]} 로고",
        "place": "center",
        "cue": cue if len(cue) <= 24 else None,
    }
    return [icon] + mats


def _sync_visual(sc: dict, mats: list[dict]) -> bool:
    vis = sc.setdefault("visual", {})
    prim = _primary(mats)
    if not prim:
        return False
    for m in prim:
        if is_evidence(m):
            k = VISUAL_FOR.get(m.get("type"), "screenshot")
            if vis.get("kind") not in ("screenshot", "footage", "still", "chart", "code"):
                vis["kind"] = k
            return True
    if slide_count(mats) and vis.get("kind") in ("screenshot", "footage", "still", "code"):
        vis["kind"] = "chart" if any(m.get("type") == "diagram" for m in prim) else "text"
        return True
    return False


def _sync_screen(sc: dict, mats: list[dict]) -> bool:
    prim = _primary(mats)
    has_ev = any(is_evidence(m) for m in prim)
    has_mock = any(is_mock_only(m) for m in prim)
    screen = str(sc.get("screen") or "")
    changed = False
    if has_ev and screen in ("", "카드(글자)", "도표", "아이콘 · 그래픽"):
        sc["screen"] = "실제 화면"
        changed = True
    elif slide_count(mats) >= 1 and not has_ev and screen == "실제 화면":
        sc["screen"] = "카드(글자)" if any(m.get("type") == "info_card" for m in prim) else "도표"
        changed = True
    elif has_mock and not has_ev and screen == "실제 화면":
        sc["screen"] = "앱 화면"
        changed = True
    return changed


def normalize_scene(sc: dict, sb: dict, *, scene_i: int = 0) -> list[str]:
    sid = sb.get("id", "")
    fmt = sb.get("format")
    ch: list[str] = []
    mats = [m for m in sc.get("materials") or [] if isinstance(m, dict)]
    if not mats:
        return ch
    new = _dedupe_slides(mats, fmt)
    if new != mats:
        ch.append("slides_deduped")
        mats = new
    if slide_count(mats) >= 1 and not any(is_evidence(m) for m in _primary(mats)):
        nm = _ensure_icon(sid, scene_i, sc, mats)
        if nm != mats:
            ch.append("icon")
            mats = nm
    if _sync_visual(sc, mats):
        ch.append("visual.kind")
    if _sync_screen(sc, mats):
        ch.append("screen")
    sc["materials"] = mats
    return ch


def apply_storyboard(sb: dict) -> list[str]:
    changed: list[str] = []
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        sc.pop("n", None)
        for tag in normalize_scene(sc, sb, scene_i=i):
            changed.append(f"s{i}.{tag}")
        sc.pop("n", None)  # 콘티 스키마에 없는 필드 — 정규화용으로만 쓴다
    return changed


def apply_file(sbp: Path, write: bool = True) -> list[str]:
    sbp = sbp if sbp.is_absolute() else ROOT / sbp
    sb = json.loads(sbp.read_text("utf-8"))
    ch = apply_storyboard(sb)
    if write and ch:
        sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return ch


def material_evidence_checks(sb: dict) -> list[tuple[str, int | None, str]]:
    """L59~L63 — 콘티 칸만으로 막는다(렌더 전)."""
    out: list[tuple[str, int | None, str]] = []
    fmt = sb.get("format")
    exempt = fmt in EXEMPT_FMT
    scenes = sb.get("scenes") or []

    for i, sc in enumerate(scenes, 1):
        role = sc.get("role") or ""
        mats = [m for m in sc.get("materials") or [] if isinstance(m, dict)]
        prim = _primary(mats)
        ev = [m for m in prim if is_evidence(m)]
        slides = [m for m in prim if m.get("type") in SLIDE]
        mocks = [m for m in prim if is_mock_only(m)]

        if len(slides) > 1:
            out.append(("L60", i, f"장면 {i}: 카드·도표 재료가 {len(slides)}개 — 한 장면에 하나만(비교 장면은 diagram 하나)"))

        screen = str(sc.get("screen") or "")
        if screen == "실제 화면" and not ev and not exempt:
            out.append(
                (
                    "L61",
                    i,
                    f"장면 {i}: screen=실제 화면인데 증거 재료 없음(web · screen · photo · doc_quote · icon+src · 캡처 ui_mock) — "
                    "info_card/diagram/mock 만으로 채우지 않는다",
                )
            )

        if mocks and not ev and role not in SKIP_ROLES and not exempt:
            out.append(
                (
                    "L62",
                    i,
                    f"장면 {i}: mock ui_mock 만 있음 — 실제 캡처(src) · web 녹화 · 브랜드 icon · photo 를 주재료로(crafts: 기술 증거)",
                )
            )

        nar = (sc.get("narration") or "").strip()
        if nar and role not in SKIP_ROLES | {"hook"} and not ev and slide_count(mats) >= 1 and not exempt:
            out.append(
                (
                    "L59",
                    i,
                    f"장면 {i}: 말만 있고 증거 재료 없음 — 최소 하나: web · screen · photo · icon · doc_quote · 실캡처",
                )
            )

    if not exempt and scenes:
        body = [
            (i, sc)
            for i, sc in enumerate(scenes, 1)
            if (sc.get("role") or "") not in SKIP_ROLES | {"hook"}
            and (sc.get("narration") or "").strip()
        ]
        if body:
            slide_body = sum(
                1
                for i, sc in body
                if slide_count([m for m in sc.get("materials") or [] if isinstance(m, dict)]) >= 1
                and not any(is_evidence(m) for m in _primary(sc.get("materials") or []))
            )
            if slide_body >= max(2, len(body) * 6 // 10):
                out.append(
                    (
                        "L63",
                        None,
                        f"본문 {len(body)}장면 중 {slide_body}개가 카드·도표·가상 목업만 — IT·설명 숏폼은 시각 증거가 주인공 "
                        "(crafts: web/screen → overlay, icon은 icons.py)",
                    )
                )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("storyboard")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true", help="L59~L63만 출력")
    a = ap.parse_args()
    sbp = Path(a.storyboard)
    if a.check:
        sb = json.loads((sbp if sbp.is_absolute() else ROOT / sbp).read_text("utf-8"))
        rows = material_evidence_checks(sb)
        for row in rows:
            print(f"{row[0]}\t{row[1] or ''}\t{row[2]}")
        return 1 if rows else 0
    ch = apply_file(sbp, write=a.write or True)
    print(json.dumps({"changed": ch}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())