#!/usr/bin/env python3
"""레퍼런스 쇼츠 분석을 Fluma 서버 작업으로 맡긴다 — 분해(shorts_xray) → 스타일 카드(ref_style) → 채널 카드(ref_channel).

  python3 scripts/analyze_ref.py <쇼츠 id 또는 URL> [--n 5] [--no-channel] [--wait 540]

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from result import fail, ok, running  # noqa: E402  결과 규약(scripts/result.py)

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
    ap.add_argument("video")
    ap.add_argument("--n", type=int, default=5, help="같은 채널에서 더 볼 쇼츠 수")
    ap.add_argument("--no-channel", action="store_true")
    ap.add_argument("--force", action="store_true", help="이미 끝난 단계도 다시")
    ap.add_argument("--fast", action="store_true", help="빠르게: 같은 채널 2편 · 가벼운 받아쓰기(base). 분석 정확도는 조금 낮다")
    ap.add_argument("--wait", type=float, default=540, help="기다릴 최대 초(명령 한 번의 시간 제한 안쪽)")
    a = ap.parse_args()
    vid = vid_of(a.video)
    try:
        jid = call("POST", f"/api/trends/xray/{vid}", {"n": a.n, "channel": not a.no_channel, "force": a.force, "fast": a.fast})["jobId"]
    except urllib.error.URLError as e:
        fail("analyze_ref", stage="server", error=f"Fluma 서버({API})에 닿지 못했습니다: {e}")
    print(f"[분석] 서버 작업 {jid[:8]} — 턴이 끝나도 계속 돈다", flush=True)
    t0, last = time.time(), None
    while True:
        j = call("GET", f"/api/jobs/{jid}")
        st = j.get("status")
        line = f"{int((j.get('progress') or 0) * 100)}% {j.get('stage') or ''}".strip()
        if line != last:
            print(f"  {int(time.time() - t0):>4}s  {line}", flush=True); last = line
        if st in ("done", "succeeded", "ok", "completed"):
            r = j.get("result") or {}
            ok("analyze_ref", video=vid, xray=r.get("url"), style=r.get("style"), channel=r.get("channel"),
               card=(f"public/trends/channels/{r['channel'].split('/channels/')[1].split('/')[0]}/channel.md" if r.get("channel") else None))
        if st in ("error", "failed", "canceled", "cancelled", "timeout"):
            fail("analyze_ref", stage=j.get("stage") or st, error=f"{j.get('error') or st} {j.get('detail') or ''}".strip())
        if time.time() - t0 > a.wait:
            running("analyze_ref", video=vid, job=jid, progress=line, next="같은 명령을 다시 부르면 이 작업에 붙어 이어서 기다린다")
        time.sleep(4)


if __name__ == "__main__":
    sys.exit(main())
