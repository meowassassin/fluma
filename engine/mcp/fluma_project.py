"""프로젝트 상태 — 에이전트가 '다음에 무엇을 할지' 한 번에 알게 짧게.

기획(data/shotplans) · 콘티(data/storyboards) · 음성 · 재료 · 렌더(data/out) · 품질 관문(quality.json) · 도는 작업을 모아
next(다음 할 일 + 부를 도구)를 정한다. 판단(무엇을 어떻게 고칠지)은 에이전트 몫 — 여기는 사실만.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fluma_jobs import ROOT, brief, list_jobs  # noqa: E402
from detach import alive  # noqa: E402

DATA = ROOT / "data"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,80}$")
_gen = None


def _gen_status():
    """engine/gen/status.py 를 이름 충돌 없이 불러 둔다(상주 서버라 한 번만)"""
    global _gen
    if _gen is None:
        spec = importlib.util.spec_from_file_location("fluma_gen_status", ROOT / "engine" / "gen" / "status.py")
        _gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_gen)
    return _gen


def check_id(pid: str) -> str:
    if not isinstance(pid, str) or not ID.match(pid):
        raise ValueError("프로젝트 id 형식이 올바르지 않습니다")
    return pid


def _j(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _when(p: Path) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))


def list_projects(limit: int = 30) -> list[dict]:
    ids: dict[str, float] = {}
    for d in (DATA / "shotplans", DATA / "storyboards"):
        for p in d.glob("*.json") if d.exists() else []:
            ids[p.stem] = max(ids.get(p.stem, 0), p.stat().st_mtime)
    rows = []
    for pid, m in sorted(ids.items(), key=lambda x: -x[1])[:limit]:
        sb = _j(DATA / "storyboards" / f"{pid}.json") or {}
        plan = _j(DATA / "shotplans" / f"{pid}.json") or {}
        full = _videos(pid)[0]
        rows.append({"id": pid, "title": sb.get("title") or plan.get("topic") or pid, "updated": time.strftime("%Y-%m-%dT%H:%M", time.localtime(m)),
                     "storyboard": bool(sb), "video": full[-1].name if full else None})
    return rows


def _videos(pid: str) -> tuple[list[Path], list[Path]]:
    """(전체 영상, 일부 장면 영상) — 오래된 것부터. 이름에 -s3-7 처럼 장면 범위가 있으면 일부"""
    out = DATA / "out"
    vids = sorted(out.glob(f"{pid}-*.mp4"), key=lambda p: p.stat().st_mtime) if out.exists() else []
    part = re.compile(r"-s\d+(-\d+)?(-draft)?\.mp4$")
    return [v for v in vids if not part.search(v.name)], [v for v in vids if part.search(v.name)]


def status(pid: str) -> dict:
    pid = check_id(pid)
    plan_p, sb_p = DATA / "shotplans" / f"{pid}.json", DATA / "storyboards" / f"{pid}.json"
    if not plan_p.exists() and not sb_p.exists():
        raise ValueError(f"없는 프로젝트입니다: {pid}")
    out: dict = {"id": pid}
    g = None
    if plan_p.exists():
        try:
            g = _gen_status().gather(pid)
        except Exception as e:  # noqa: BLE001 — 기획 파일이 깨져도 나머지 상태는 보여 준다
            out["plan"] = {"error": str(e)[:300]}
    if g:
        out["route"] = g.get("route")
        out["plan"] = {"topic": (g.get("plan") or {}).get("topic"), "errors": g["check"]["errors"], "warnings": g["check"]["warnings"][:8]}
    sb = _j(sb_p)
    if sb:
        scenes = sb.get("scenes") or []
        nmat = sum(len(s.get("materials") or []) for s in scenes)
        built = len(list((DATA / "compositions" / pid / "craft" / "materials").glob("s*/*.json"))) if nmat else 0
        out["storyboard"] = {"path": str(sb_p.relative_to(ROOT)), "title": sb.get("title"), "format": sb.get("format"),
                             "scenes": len(scenes), "duration_sec": sb.get("duration_sec"), "updated": _when(sb_p),
                             "materials": {"built": min(built, nmat), "total": nmat}}
    audio = DATA / "audio" / f"{pid}.wav"
    out["audio"] = {"path": str(audio.relative_to(ROOT)), "updated": _when(audio)} if audio.exists() else None
    full, part = _videos(pid)
    out["video"] = {"latest": str(full[-1].relative_to(ROOT)) if full else None, "updated": _when(full[-1]) if full else None,
                    "partial": str(part[-1].relative_to(ROOT)) if part else None}
    q = _j(DATA / "workspace" / "tmp" / pid / "quality.json")
    if q:
        stale = bool(full) and q.get("video") != str(full[-1].relative_to(ROOT))
        out["quality"] = {"video": q.get("video"), "stale": stale, "block": q.get("block") or [], "waived": len(q.get("waived") or []),
                          "advise": [f"{a.get('code')}{':' + str(a['scene']) if a.get('scene') else ''} {a.get('msg', '')}"[:160] for a in (q.get("advise") or [])][:10]}
    pg = _j(DATA / "workspace" / "progress" / f"{pid}.json")
    if pg and pg.get("running") and alive(pg.get("pid")):
        out["produce_running"] = {"stage": pg.get("stage"), "done": pg.get("done")}
    bg = _j(DATA / "compositions" / pid / "skill_pass" / "script_bg.json")
    if bg:                                      # 뒤에서 도는 대본 검토(bundle.py script) — 결과는 prep 이 받는다
        out["script_review"] = {"status": bg.get("status"), "secs": bg.get("secs"), **({"error": str(bg.get("error"))[:300]} if bg.get("error") else {})}
    jobs = [brief(j) for j in list_jobs(project=pid, limit=5)]
    out["jobs"] = jobs
    out["next"] = _next(out, sb_p.exists(), bool(g))
    return out


def _next(s: dict, has_sb: bool, has_plan: bool) -> dict:
    """다음 할 일(사실 기준). tool = 부를 MCP 도구"""
    act = [j for j in s.get("jobs") or [] if j.get("status") in ("queued", "waiting", "running")]
    if act or s.get("produce_running"):
        j = act[0] if act else {}
        return {"do": "도는 작업이 끝나기를 기다린다", "tool": "job_wait", "args": {"job_id": j.get("id")} if j else {}}
    if has_plan and (s.get("plan") or {}).get("errors"):
        return {"do": "기획 검사 오류를 고친다", "why": s["plan"]["errors"][:5]}
    if (s.get("script_review") or {}).get("status") == "error":
        return {"do": "대본 검토가 막았다 — 대사만 고쳐 다시 bundle.py script", "why": s["script_review"].get("error")}
    if not has_sb:
        return {"do": "대본을 쓰고 plan_submit(대본 · 사실 · 만들 재료) — 음성 · 재료가 바로 시작된다", "tool": "plan_submit", "args": {"project": s["id"]}}
    if not (s.get("video") or {}).get("latest") and not (DATA / "compositions" / s["id"] / "design").is_dir() \
            and not any((DATA / "compositions" / s["id"] / "scenes").glob("s*.jsx")):
        return {"do": "영상 방향 + 모든 장면 설계를 design_submit 한 번", "tool": "design_submit", "args": {"project": s["id"]}}
    if not (s.get("video") or {}).get("latest"):
        pid = s["id"]
        if not s.get("audio"):
            return {"do": "음성 · 장면 길이를 만든다", "tool": "prep_start", "args": {"project": pid}}
        try:
            from fluma_tools import review_fresh
            fresh, why = review_fresh(pid)
        except Exception as e:  # noqa: BLE001
            fresh, why = False, str(e)[:200]
        if not fresh:
            return {"do": "정지 화면을 보고 검토를 제출한다", "why": why, "tool": "review_frames", "args": {"project": pid}}
        return {"do": "완성 렌더 → 품질 관문", "tool": "render_start", "args": {"project": pid, "mode": "final"}}
    q = s.get("quality")
    if not q:
        return {"do": "제작해 품질 관문 결과를 만든다", "tool": "produce_start", "args": {"project": s["id"]}}
    if q.get("stale"):
        return {"do": "마지막 영상이 관문 판정 뒤에 바뀌었다 — 다시 제작해 판정한다", "tool": "produce_start", "args": {"project": s["id"]}}
    if q.get("block"):
        return {"do": "막음을 고친 뒤 다시 제작한다(막음이 남으면 완성 · 업로드 불가)",
                "why": [f"{b.get('code')}{':' + str(b['scene']) if b.get('scene') else ''} {b.get('msg', '')}"[:160] for b in q["block"]][:8],
                "tool": "produce_start", "args": {"project": s["id"]}}
    return {"do": "완성 — 영상을 보여 주고 사용자의 다음 요청을 기다린다(업로드는 사용자가 말할 때만)", "video": s["video"]["latest"]}
