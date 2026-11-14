#!/usr/bin/env python3
"""파이프라인 6단계 — 렌더링 → 유튜브 업로드 → 영상 분석 → (기존 트렌드 분석을 거쳐) 1단계 입력.

  python3 engine/gen/publish.py final <plan id>                       # 최종 렌더(engine/render.py — 초안 아님)
  python3 engine/gen/publish.py upload <plan id> [--privacy private|unlisted|public] [--publish-at ISO]
        # 사용자가 명시적으로 올리라고 할 때만. engine/publish/upload_youtube.py(중복 업로드 방지 · YOUTUBE_CLIENT_SECRET)
  python3 engine/gen/publish.py feedback <plan id>                    # youtube.stats.json(작업 공간이 YouTube Analytics 에서 받아 둔 것) → 샷별 시청 지속
        # → data/public/trends/own/<id>.json + 트렌드 목록(index.json)에 '내 영상'으로 → plan.py trends 가 1단계 추천 재료로 함께 보여 준다
분석 숫자는 YouTube Analytics 가 약 2일 늦게 채운다. 시청 지속(elapsedVideoTimeRatio → audienceWatchRatio)을 샷 경계(편집 길이 누적)에 겹쳐
'어느 샷에서 빠져나갔나'와 그 샷의 칸(목적 · 샷 크기 · 카메라 움직임)을 같이 남긴다 — 다음 기획이 같은 실수를 피하게.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402
import assemble as asm  # noqa: E402
import plan as planmod  # noqa: E402

TRENDS = ROOT / "data" / "public" / "trends"
PUBLISHED = ROOT / "data" / "storyboards" / "_published.jsonl"


def published(pid: str) -> dict | None:
    if not PUBLISHED.exists():
        return None
    rows = [json.loads(x) for x in PUBLISHED.read_text("utf-8").splitlines() if x.strip()]
    return next((r for r in reversed(rows) if r.get("id") == pid), None)


def no_mock(pid: str, stage: str) -> None:
    """mock 클립(키 프레임을 늘린 가짜 영상)이 섞인 영상은 최종본 · 업로드로 내보내지 않는다"""
    bad = asm.videomod.mock_shots(pid)
    if bad:
        fail("publish", stage=stage, error=f"샷 {bad} 이(가) 시험용 mock 클립이다 — 실제 생성 경로(video.py run --shots {','.join(map(str, bad))})로 다시 만들고 검토 통과 뒤 진행")


def final(pid: str) -> str:
    no_mock(pid, "final")
    # 2-엔진 규칙: 편집기로 넘긴 영상은 편집기에서 내보낸 것(exported.mp4 / <id>-editor.mp4)이 최종본입니다.
    # Craft는 그 전 단계 초안만 만듭니다.
    ed_out = ROOT / "data" / "out" / f"{pid}-editor.mp4"
    if not ed_out.exists():
        comp_out = ROOT / "data" / "compositions" / pid / "editor" / "exported.mp4"
        if comp_out.exists():
            (ROOT / "data" / "out").mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(comp_out, ed_out)
    if ed_out.exists():
        return str(ed_out.relative_to(ROOT))

    sbp = ROOT / "data" / "storyboards" / f"{pid}.json"
    if not sbp.exists():
        fail("publish", stage="final", error="콘티가 없다 — 5단계(assemble.py build)부터")
    r = subprocess.run([sys.executable, "engine/render.py", str(sbp.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, timeout=5400)
    b = asm.block(r.stdout)
    if r.returncode or b.get("head") != "FLUMA_RESULT":
        fail("publish", stage="final", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-400:]])[0])
    return b["file"][0]


def upload(pid: str, privacy: str, publish_at: str | None) -> dict:
    no_mock(pid, "upload")
    # 2-엔진 규칙: 편집기에서 내보낸 최종본 우선
    ed_out = ROOT / "data" / "out" / f"{pid}-editor.mp4"
    if not ed_out.exists():
        comp_out = ROOT / "data" / "compositions" / pid / "editor" / "exported.mp4"
        if comp_out.exists():
            (ROOT / "data" / "out").mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(comp_out, ed_out)

    if ed_out.exists():
        target = ed_out
    else:
        outs = sorted((ROOT / "data" / "out").glob(f"{pid}-*.mp4"), key=lambda p: p.stat().st_mtime)
        outs = [p for p in outs if "draft" not in p.name]
        if not outs:
            fail("publish", stage="upload", error="최종 렌더가 없다 — 편집기에서 내보내거나 publish.py final 부터")
        target = outs[-1]

    cmd = [sys.executable, "engine/publish/upload_youtube.py", f"data/storyboards/{pid}.json", str(target.relative_to(ROOT)), "--privacy", privacy]
    if publish_at:
        cmd += ["--publish-at", publish_at]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3600)
    if r.returncode:
        fail("publish", stage="upload", error=(r.stderr or r.stdout).strip()[-400:])
    return published(pid) or {}


def _rows(rep: dict) -> list[dict]:
    cols = rep.get("cols") or []
    return [dict(zip(cols, row)) for row in rep.get("rows") or []]


def feedback(pid: str) -> dict:
    _, sb = planmod.load(pid)
    sp = ROOT / "data" / "compositions" / pid / "youtube.stats.json"
    if not sp.exists():
        fail("publish", stage="feedback", error="youtube.stats.json 이 없다 — 작업 공간에서 이 영상의 유튜브 통계를 한 번 불러온다(분석은 업로드 약 2일 뒤 채워짐)")
    st = json.loads(sp.read_text("utf-8"))
    summ = (_rows(st.get("summary") or {}) or [{}])[0]
    ret = sorted(_rows(st.get("retention") or {}), key=lambda r: float(r.get("elapsedVideoTimeRatio") or 0))
    total = sum(s["final_sec"] for s in sb["shots"]) or 1
    shots, t = [], 0.0
    for s in sb["shots"]:
        a, b = t / total, (t + s["final_sec"]) / total
        inside = [float(r.get("audienceWatchRatio") or 0) for r in ret if a <= float(r.get("elapsedVideoTimeRatio") or 0) <= b]
        before = [float(r.get("audienceWatchRatio") or 0) for r in ret if float(r.get("elapsedVideoTimeRatio") or 0) <= a]
        start = (before[-1] if before else (inside[0] if inside else None))
        end = inside[-1] if inside else None
        shots.append({"n": s["n"], "purpose": s["purpose"], "shot_size": s["shot_size"], "camera_move": s["camera_move"], "final_sec": s["final_sec"],
                      "watch_start": start, "watch_end": end, "drop": round(start - end, 3) if start is not None and end is not None else None})
        t += s["final_sec"]
    traffic = _rows(st.get("traffic") or {})[:5]
    pub = published(pid) or {}
    own = {"id": pid, "video_id": st.get("videoId") or pub.get("video_id"), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "topic": sb["topic"],
           "trend_option": (sb.get("trend") or {}).get("option"), "views": summ.get("views"), "avg_view_pct": summ.get("averageViewPercentage"),
           "avg_view_sec": summ.get("averageViewDuration"), "shots": shots, "traffic": traffic,
           "worst": sorted([x for x in shots if x["drop"] is not None], key=lambda x: -x["drop"])[:2]}
    (TRENDS / "own").mkdir(parents=True, exist_ok=True)
    (TRENDS / "own" / f"{pid}.json").write_text(json.dumps(own, ensure_ascii=False, indent=1), "utf-8")
    # 기존 트렌드 목록에도 '내 영상'으로 올린다 — trends 화면 · X-ray(shorts_xray) 를 그대로 거칠 수 있게
    ip = TRENDS / "index.json"
    idx = json.loads(ip.read_text("utf-8")) if ip.exists() else {"requests": [], "items": []}
    vid = own["video_id"]
    if vid:
        idx["items"] = [x for x in idx.get("items") or [] if x.get("id") != vid] + [{
            "id": vid, "title": sb.get("title") or sb["topic"], "views": own["views"], "label": "내 영상", "via": "own", "request": "own",
            "url": f"https://www.youtube.com/shorts/{vid}", "own": {"plan": pid, "avg_view_pct": own["avg_view_pct"]}}]
        ip.write_text(json.dumps(idx, ensure_ascii=False, indent=1), "utf-8")
    return own


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("final"); f.add_argument("pid")
    u = sp.add_parser("upload"); u.add_argument("pid"); u.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"]); u.add_argument("--publish-at")
    fb = sp.add_parser("feedback"); fb.add_argument("pid")
    a = ap.parse_args()
    if a.cmd == "final":
        ok("publish", file=final(a.pid), next="사용자가 올리라고 하면 publish.py upload"); return 0
    if a.cmd == "upload":
        r = upload(a.pid, a.privacy, a.publish_at)
        ok("publish", url=str(r.get("url")), video_id=str(r.get("video_id")), next="약 2일 뒤 작업 공간에서 통계를 불러오고 publish.py feedback"); return 0
    r = feedback(a.pid)
    ok("publish", avg_view_pct=str(r["avg_view_pct"]), worst=", ".join(f"샷 {x['n']}({x['purpose']} · {x['camera_move']}) -{x['drop']}" for x in r["worst"]) or "없음",
       next="plan.py trends 가 다음 기획 추천에 이 결과를 함께 보여 준다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
