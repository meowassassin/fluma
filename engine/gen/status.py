#!/usr/bin/env python3
"""프로젝트 상태 한 번에(작업 공간이 읽는다) — 기획 기록 · 검사 · 경로 · 재료 · 음성 · 콘티 · 초안 · 최종본.

  python3 engine/gen/status.py <plan id>          # JSON 한 줄
  python3 engine/gen/status.py --list              # 프로젝트 목록
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
import plan as planmod  # noqa: E402


def rel(p: Path | str | None) -> str | None:
    if not p:
        return None
    p = Path(p)
    try:
        return str(p.resolve().relative_to(ROOT / "data" / "compositions"))
    except ValueError:
        return None


def mtime(p: Path) -> int:
    return int(p.stat().st_mtime) if p.exists() else 0


def _j(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


from craft.usage import DRAFT_APPS  # noqa: E402


def provenance(pid: str, sb: dict) -> dict:
    """단계마다 '실제로 무엇으로 만들었나' — 결과 파일에 남은 기록만 모은다(지금 설정은 보지 않는다).
    기록이 없으면 그 칸을 비운다 — 화면은 '기록 없음'으로 보여 준다."""
    comp = ROOT / "data" / "compositions" / pid
    out: dict = {}
    if sb.get("made_by"):
        out["plan"] = sb["made_by"]

    vm = _j(ROOT / "data" / "audio" / f"{pid}.voice.meta.json")
    if vm:
        out["voice"] = vm
    # 재료: 장면 재료 기록마다 실제로 만든 도구(Craft 앱 · 화면 녹화 · 스톡 …) / 초안: 조립 단계 기록(usage.json)에서 재료 앱을 뺀 것
    mat_tools, mat_apps = [], set()
    mats_dir = comp / "craft" / "materials"
    if mats_dir.is_dir():
        for mf in sorted(mats_dir.glob("s*/*.json")):
            mj = _j(mf)
            if not isinstance(mj, dict) or not mj.get("type"):
                continue
            tool = material_tool(mj.get("spec") or mj, mj.get("app"))
            if tool and tool not in mat_tools:
                mat_tools.append(tool)
            if mj.get("app"):
                mat_apps.add(mj["app"])
    if mat_tools:
        out["materials"] = mat_tools
    us = _j(comp / "craft" / "usage.json")
    if us:
        used = [a for a in dict.fromkeys(f.get("app") for f in us.get("features") or [] if f.get("app"))]
        draft = [a for a in used if a in DRAFT_APPS]          # usage.json 에는 재료 앱 기능도 섞여 있다 — 조립 단계 앱만
        if draft:
            out["draft"] = draft
    return out


def material_tool(m: dict, app: str | None = None) -> str | None:
    """재료 하나 → 그걸 만드는 도구 이름(Craft 앱 id 또는 'capture:web' 같은 출처 종류)"""
    if app:
        return app
    t = m.get("type")
    if t == "craft":
        return m.get("app")
    if t == "web":
        src = ROOT / str(m.get("src") or "")
        meta = _j(src / "meta.json") if src.is_dir() else None
        return "capture:terminal" if (meta or {}).get("terminal") else "capture:web"
    if t == "stock":
        return "stock"
    if t in ("screen", "image", "video", "photo") and not m.get("method"):
        return "capture:file"
    if t == "meme":
        return "capture:web"
    try:
        from craft.materials import methods
        ms = methods().get(t) or []
        return m.get("method") or (ms[0] if ms else None)
    except Exception:  # noqa: BLE001
        return None


def planned_tools(sb: dict | None) -> dict:
    """아직 안 한 단계에 '이 영상에서 쓸 도구'(흐리게) — 콘티 재료에서 정해진다. 콘티가 없으면 비움(지어내지 않는다)"""
    if not sb:
        return {}
    mats = []
    for sc in sb.get("scenes") or []:
        for m in sc.get("materials") or []:
            t_ = material_tool(m)
            if t_ and t_ not in mats:
                mats.append(t_)
    return {"materials": mats, "draft": list(DRAFT_APPS)} if mats else {"draft": list(DRAFT_APPS)}


def gather(pid: str) -> dict:
    pp = planmod.PLANS / f"{pid}.json"
    sb = json.loads(pp.read_text("utf-8"))
    try:
        errs, warns = planmod.problems(sb)
    except Exception as e:  # noqa: BLE001
        errs, warns = [f"검사 실패: {e}"], []
    out: dict = {"id": pid, "plan": sb, "check": {"errors": errs, "warnings": warns}, "steps": {}, "route": sb.get("route") or "material"}
    out["provenance"] = provenance(pid, sb)
    sbp = ROOT / "data" / "storyboards" / f"{pid}.json"
    drafts = sorted((ROOT / "data" / "out").glob(f"{pid}-*draft*.mp4"), key=lambda p: p.stat().st_mtime)
    finals = [p for p in sorted((ROOT / "data" / "out").glob(f"{pid}-*.mp4"), key=lambda p: p.stat().st_mtime) if "draft" not in p.name]
    story = _j(sbp) if sbp.exists() else None
    out["planned"] = planned_tools(story)
    nmat = sum(len(sc.get("materials") or []) for sc in (story or {}).get("scenes") or [])
    built = len([f for f in (ROOT / "data" / "compositions" / pid / "craft" / "materials").glob("s*/*.json")]) if nmat else 0
    out["artifacts"] = {"research": (ROOT / "data" / "research" / f"{pid}.json").exists(),
                        "audio": (ROOT / "data" / "audio" / f"{pid}.wav").exists(),
                        "materials": [min(built, nmat), nmat]}
    out["edit"] = {"storyboard": sbp.exists(), "draft": drafts[-1].name if drafts else None, "final": finals[-1].name if finals else None}
    out["next"] = {"clip": "클립 재편집 — 더빙 계획(dub.json) → dub.py build"}.get(out["route"], "실제 자료 편집 — 콘티 → produce.py")
    return out


def find_thumb(pid: str) -> str | None:
    comp = ROOT / "data" / "compositions" / pid
    if not comp.is_dir():
        return None
    th = comp / "craft" / "edit" / f"{pid}.thumb.png"
    if th.is_file():
        return f"{pid}/craft/edit/{pid}.thumb.png"
    for cand in comp.glob("craft/materials/*/*.jpg"):
        return f"{pid}/craft/materials/{cand.parent.name}/{cand.name}"
    return None


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        rows = []
        for p in sorted(planmod.PLANS.glob("*.json"), key=lambda p: -p.stat().st_mtime):
            try:
                d = json.loads(p.read_text("utf-8"))
                rows.append({
                    "id": p.stem,
                    "topic": d.get("topic") or p.stem,
                    "updated": int(p.stat().st_mtime),
                    "thumb": find_thumb(p.stem),
                    "route": d.get("route") or "material",
                })
            except (json.JSONDecodeError, OSError):
                continue
        print(json.dumps(rows, ensure_ascii=False)); return 0
    print(json.dumps(gather(sys.argv[1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
