#!/usr/bin/env python3
"""레퍼런스 쇼츠 분석을 Fluma 서버 작업으로 맡긴다 — 분해(shorts_xray) → 스타일 카드(ref_style) → 채널 카드(ref_channel).

  python3 engine/research/analyze_ref.py <쇼츠 id 또는 URL> [--channel N] [--deep] [--wait 540]

기본은 빠른 분석(편당 1분 안팎): 샷 · 글자 · 대사 · 소리를 잰다.
--deep: 누끼 · 음원 분리까지(분해도 레이어가 필요할 때만 — 편당 수 분 · 메모리 많이 씀)
--channel N: 같은 채널 쇼츠 N편으로 말투 카드(크리에이터 말투를 따라 할 때만 — N편을 더 분석하므로 오래 걸린다. 브랜드 광고 · 분위기 참고에는 필요 없음)

에이전트가 스크립트를 직접 백그라운드로 돌리면 턴이 끝날 때 함께 죽는다(2026-11-04: 채널 분석이 3/6편에서 끊겨 처음부터 다시).
서버 작업은 턴과 상관없이 끝까지 돌고, 화면(트렌드 · 작업 목록)에 진행률이 보인다. 이미 끝난 단계는 건너뛴다.
--wait 초 동안 진행을 출력하며 기다린다. 그 안에 안 끝나면 '아직 도는 중' 을 알리고 끝난다 — 같은 명령을 다시 부르면 같은 작업에 붙는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from result import fail, ok, running  # noqa: E402  결과 규약(engine/core/result.py)

API = os.environ.get("FLUMA_API", f"http://127.0.0.1:{os.environ.get('PORT', '4310')}")


def vid_of(s: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="+", help="쇼츠 id 또는 URL — 여러 개면 동시에(서버가 두 편씩) 돌리고 모두 기다린다")
    ap.add_argument("--channel", "--n", dest="n", type=int, default=0, help="같은 채널에서 더 볼 쇼츠 수(0 = 채널 카드 안 만듦, 기본)")
    ap.add_argument("--no-channel", action="store_true", help="(옛 옵션 — 이제 기본이 채널 카드 없음)")
    ap.add_argument("--deep", action="store_true", help="누끼 · 음원 분리까지(분해도 레이어용 — 느림)")
    ap.add_argument("--force", action="store_true", help="이미 끝난 단계도 다시")
    ap.add_argument("--fast", action="store_true", help="빠르게: 같은 채널 2편 · 가벼운 받아쓰기(base). 분석 정확도는 조금 낮다")
    ap.add_argument("--wait", type=float, default=540, help="기다릴 최대 초(명령 한 번의 시간 제한 안쪽)")
    a = ap.parse_args()
    vids = list(dict.fromkeys(vid_of(v) for v in a.video))
    body = {"n": a.n, "channel": a.n > 0 and not a.no_channel, "force": a.force, "fast": a.fast, "deep": a.deep}
    try:
        jobs = {v: call("POST", f"/api/trends/xray/{v}", body)["jobId"] for v in vids}
    except urllib.error.URLError as e:
        fail("analyze_ref", stage="server", error=f"Fluma 서버({API})에 닿지 못했습니다: {e}")
    print(f"[분석] 서버 작업 {len(jobs)}개 — 턴이 끝나도 계속 돈다", flush=True)
    t0, last, done = time.time(), {}, {}
    while True:
        for v, jid in jobs.items():
            if v in done:
                continue
            j = call("GET", f"/api/jobs/{jid}")
            st = j.get("status")
            line = f"{int((j.get('progress') or 0) * 100)}% {j.get('stage') or ''}".strip()
            if line != last.get(v):
                print(f"  {int(time.time() - t0):>4}s  {v}  {line}", flush=True); last[v] = line
            if st in ("done", "succeeded", "ok", "completed"):
                r = j.get("result") or {}
                done[v] = {"video": v, "xray": r.get("url"), "style": r.get("style"), "channel": r.get("channel"),
                           "card": (f"data/public/trends/channels/{r['channel'].split('/channels/')[1].split('/')[0]}/channel.md" if r.get("channel") else None)}
            elif st in ("error", "failed", "canceled", "cancelled", "timeout"):
                done[v] = {"video": v, "error": f"{j.get('error') or st} {j.get('detail') or ''}".strip()}
        if len(done) == len(jobs):
            bad = [d for d in done.values() if d.get("error")]
            if len(vids) == 1:
                d = done[vids[0]]
                if bad:
                    fail("analyze_ref", stage="analyze", error=d["error"])
                ok("analyze_ref", **d)
            if len(bad) == len(vids):
                fail("analyze_ref", stage="analyze", error=" / ".join(f"{d['video']}: {d['error']}" for d in bad))
            ok("analyze_ref", videos=[d["video"] for d in done.values() if not d.get("error")],
               failed=[f"{d['video']}: {d['error']}" for d in bad] or None, took_sec=int(time.time() - t0))
        if time.time() - t0 > a.wait:
            running("analyze_ref", videos=vids, done=list(done), progress=last, next="같은 명령을 다시 부르면 이 작업들에 붙어 이어서 기다린다")
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
