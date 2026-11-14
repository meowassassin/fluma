#!/usr/bin/env python3
"""파이프라인 전체 상태 한 번에(작업 공간 승인 화면이 읽는다) — 샷 계획 · 검사 · 캐릭터(①) · 키 프레임(②) · 클립(샷 검토) · 콘티 · 초안.

  python3 engine/gen/status.py <plan id>          # JSON 한 줄
  python3 engine/gen/status.py --list              # 샷 계획 목록
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
import character as charmod  # noqa: E402
import keyframe as kfmod  # noqa: E402
import plan as planmod  # noqa: E402
import video as videomod  # noqa: E402


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


def provenance(pid: str, sb: dict) -> dict:
    """단계마다 '실제로 무엇으로 만들었나' — 결과 파일에 남은 기록만 모은다(지금 설정은 보지 않는다).
    기록이 없으면 그 칸을 비운다 — 화면은 '기록 없음'으로 보여 준다."""
    comp = ROOT / "data" / "compositions" / pid
    out: dict = {}
    if sb.get("made_by"):
        out["plan"] = sb["made_by"]

    def img_models(recs: list[dict]) -> list[dict]:
        seen, res = set(), []
        for r in recs:
            m = r.get("model_reported") or r.get("model_asked")
            k = (m, r.get("via"))
            if m and k not in seen:
                seen.add(k); res.append({"model": m, "via": r.get("via")})
        return res
    chars = [v for f in comp.glob("characters/*/sheet.json") for v in ((_j(f) or {}).get("views") or {}).values() if isinstance(v, dict)]
    if chars:
        out["character"] = img_models(chars)
    kf = _j(comp / "keyframes" / "keyframes.json") or {}
    kfr = [x for s in (kf.get("shots") or {}).values() for x in (s or {}).values() if isinstance(x, dict)]
    if kfr:
        out["keyframe"] = img_models(kfr)
    # 영상: 고른(검토) 테이크의 시도 기록, 없으면 마지막 시도
    review = _j(comp / "clips" / "review.json") or {}
    vids, seen = [], set()
    for d in sorted((comp / "clips").glob("s*")) if (comp / "clips").is_dir() else []:
        n = str(int(d.name[1:])) if d.name[1:].isdigit() else None
        take = (review.get(n) or {}).get("take") if n else None
        at = d / f"attempt_{take}.json" if take else max(d.glob("attempt_*.json"), key=lambda x: x.stat().st_mtime, default=None)
        r = _j(at) if at else None
        if r and (r.get("model"), r.get("backend")) not in seen:
            seen.add((r.get("model"), r.get("backend"))); vids.append({"model": r.get("model"), "backend": r.get("backend")})
    if vids:
        out["video"] = vids
    vm = _j(ROOT / "data" / "audio" / f"{pid}.voice.meta.json")
    if vm:
        out["voice"] = vm
    craft_apps = set()
    us = _j(comp / "craft" / "usage.json")
    if us:
        craft_apps.update(f.get("app") for f in us.get("features") or [] if f.get("app"))
    # 각 장면 재료(materials)에 실제로 투입된 모든 Craft 앱 수집
    mats_dir = comp / "craft" / "materials"
    if mats_dir.is_dir():
        for mf in mats_dir.glob("s*/*.json"):
            mj = _j(mf)
            if mj and mj.get("app"):
                craft_apps.add(mj["app"])
    if craft_apps:
        out["draft"] = sorted(craft_apps)
        out["materials"] = sorted(craft_apps)
    return out


def gather(pid: str) -> dict:
    pp = planmod.PLANS / f"{pid}.json"
    sb = json.loads(pp.read_text("utf-8"))
    try:
        errs, warns = planmod.problems(sb)
    except Exception as e:  # noqa: BLE001
        errs, warns = [f"검사 실패: {e}"], []
    out: dict = {"id": pid, "plan": sb, "check": {"errors": errs, "warnings": warns}, "steps": {}, "route": sb.get("route", "generate")}
    out["provenance"] = provenance(pid, sb)
    if out["route"] != "generate":                    # 생성이 아닌 경로 — 편집 · 렌더 상태만
        sbp = ROOT / "data" / "storyboards" / f"{pid}.json"
        drafts = sorted((ROOT / "data" / "out").glob(f"{pid}-*draft*.mp4"), key=lambda p: p.stat().st_mtime)
        finals = [p for p in sorted((ROOT / "data" / "out").glob(f"{pid}-*.mp4"), key=lambda p: p.stat().st_mtime) if "draft" not in p.name]
        out.update(characters=[], keyframes=[], clips=[], edit={"storyboard": sbp.exists(), "draft": drafts[-1].name if drafts else None, "final": finals[-1].name if finals else None},
                   next={"clip": "클립 재편집 — 더빙 계획(dub.json) → dub.py build", "material": "실제 자료 편집 — 콘티 → produce.py"}[out["route"]])
        return out
    chars = []
    if sb.get("needs_character") and not errs:
        for r in charmod.status(pid):
            d = charmod.cdir(pid, r["name"])
            r["files"] = {v: f"{rel(d / f'{v}.png')}?t={mtime(d / f'{v}.png')}" for v in charmod.VIEWS if (d / f"{v}.png").exists()}
            r["candidates_files"] = [f"{rel(d / c)}?t={mtime(d / c)}" for c in r.get("candidates") or []]
            chars.append(r)
    out["characters"] = chars
    kfs = []
    if not errs:
        kd = kfmod.kdir(pid)
        for r in kfmod.status(pid):
            n = r["shot"]
            f, e = kd / f"s{n:02d}.png", kd / f"s{n:02d}_end.png"
            mf, cf, sf = kd / f"s{n:02d}_mask.png", kd / f"s{n:02d}_compose.png", kd / f"s{n:02d}_stage.png"
            r["first"] = f"{rel(f)}?t={mtime(f)}" if f.exists() else None
            r["end"] = f"{rel(e)}?t={mtime(e)}" if e.exists() else None
            r["mask_url"] = f"{rel(mf)}?t={mtime(mf)}" if mf.exists() else None
            r["compose_url"] = f"{rel(cf)}?t={mtime(cf)}" if cf.exists() else None
            r["stage_url"] = f"{rel(sf)}?t={mtime(sf)}" if sf.exists() else None
            r["candidates_files"] = [
                {"name": c, "num": i + 1, "url": f"{rel(kd / c)}?t={mtime(kd / c)}"}
                for i, c in enumerate(r.get("candidates") or [])
                if (kd / c).exists()
            ]
            kfs.append(r)
    out["keyframes"] = kfs
    clips = []
    if not errs:
        cfg = videomod.settings()
        out["videogen"] = {"model": cfg["model"], "max_attempts": cfg["max_attempts"]}
        comp_clips = ROOT / "data" / "compositions" / pid / "clips"
        for r in videomod.status(pid):
            r["clip_url"] = rel(r.get("clip"))
            sdir = comp_clips / f"s{r['shot']:02d}"
            takes = []
            if sdir.is_dir():
                for tf in sorted(sdir.glob("take_*.mp4")):
                    takes.append({"name": tf.name, "url": f"{rel(tf)}?t={mtime(tf)}"})
            r["takes"] = takes
            clips.append(r)
    out["clips"] = clips
    sbp = ROOT / "data" / "storyboards" / f"{pid}.json"
    drafts = sorted((ROOT / "data" / "out").glob(f"{pid}-*draft*.mp4"), key=lambda p: p.stat().st_mtime)
    finals = [p for p in sorted((ROOT / "data" / "out").glob(f"{pid}-*.mp4"), key=lambda p: p.stat().st_mtime) if "draft" not in p.name]
    out["edit"] = {"storyboard": sbp.exists(), "draft": drafts[-1].name if drafts else None, "final": finals[-1].name if finals else None}
    # 지금 해야 할 단계
    if errs:
        nxt = "1 기획 — 샷 계획 검사 실패"
    elif chars and any(c["state"] != "승인" for c in chars):
        nxt = "2 캐릭터 시트 · 승인 ①"
    elif any(k["state"] != "승인" for k in kfs):
        nxt = "3 키 프레임 · 승인 ②"
    elif any(not c["approved"] for c in clips):
        nxt = "4 영상 생성 · 샷 검토"
    elif not out["edit"]["draft"]:
        nxt = "5 편집 — 초안 만들기"
    else:
        nxt = "5 편집 · 6 렌더 · 업로드"
    out["next"] = nxt
    return out


def find_thumb(pid: str) -> str | None:
    comp = ROOT / "data" / "compositions" / pid
    if not comp.is_dir():
        return None
    kf1 = comp / "keyframes" / "s01.png"
    if kf1.is_file():
        return f"{pid}/keyframes/s01.png"
    for cand in comp.glob("keyframes/*.png"):
        return f"{pid}/keyframes/{cand.name}"
    th = comp / "craft" / "edit" / f"{pid}.thumb.png"
    if th.is_file():
        return f"{pid}/craft/edit/{pid}.thumb.png"
    for cand in comp.glob("craft/materials/*/*.jpg"):
        return f"{pid}/craft/materials/{cand.parent.name}/{cand.name}"
    front = next(comp.glob("characters/*/front.png"), None)
    if front:
        return f"{pid}/characters/{front.parent.name}/front.png"
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
                    "shots": len(d.get("shots") or []),
                    "updated": int(p.stat().st_mtime),
                    "thumb": find_thumb(p.stem),
                    "style": d.get("style", ""),
                    "route": d.get("route", "generate"),
                })
            except (json.JSONDecodeError, OSError):
                continue
        print(json.dumps(rows, ensure_ascii=False)); return 0
    print(json.dumps(gather(sys.argv[1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
