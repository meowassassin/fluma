#!/usr/bin/env python3
"""일괄 제작 — 한 대화에서 "○○ 주제로 N개" 요청을 받으면, 주제마다 새 영상 프로젝트를 만들고 각각 자동 진행으로 완성까지 돌린다.
영상마다 대화 · 맥락이 따로다(한 대화에서 몇 시간씩 이어 가지 않는다). 동시에 도는 수는 설정의 에이전트 동시 실행 수.

  python3 engine/core/batch.py start "주제 1" "주제 2" …  [--from <지금 프로젝트 id>]   # 시작 → 묶음 id
  python3 engine/core/batch.py start --file topics.json                                  # [{"topic": "…", "note": "요청"}] 
  python3 engine/core/batch.py status <묶음 id>                                           # 영상마다 대기 · 만드는 중 · 완성 · 막힘
답에는 ```batch 블록(한 줄: 묶음 id)을 넣으면 작업 공간이 진행 상황을 실시간으로 보여 준다.
주제는 먼저 python3 engine/gen/plan.py vet "…" 로 겹침을 확인한 것만 넣는다.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

API = os.environ.get("FLUMA_API") or "http://127.0.0.1:4310"


def _call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        fail("batch", stage=method.lower(), error=f"{e.code} {e.read().decode()[:300]}")
    except OSError as e:
        fail("batch", stage=method.lower(), error=f"작업 공간 서버에 닿지 않음({API}): {e}")


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] not in ("start", "status"):
        print(__doc__); return 2
    if a[0] == "status":
        if len(a) < 2:
            print(__doc__); return 2
        r = _call("GET", f"/api/batch/{a[1]}")
        mark = {"done": "✓ 완성", "running": "… 만드는 중", "waiting": "· 차례 기다림", "blocked": "✗ 막힘", "stopped": "■ 멈춤", "error": "✗ 시작 못 함"}
        for it in r["items"]:
            print(f"{mark.get(it['state'], it['state']):10} {it['project']}  {it['topic']}" + (f"  → {it['video']}" if it.get("video") else ""))
        s = r["summary"]
        ok("batch", id=r["id"], done=f"{s['done']}/{s['total']}", running=str(s["running"]), waiting=str(s["waiting"]), blocked=str(s["blocked"]))
        return 0
    rest = a[1:]
    frm = rest[rest.index("--from") + 1] if "--from" in rest else os.environ.get("FLUMA_PROJECT")
    if "--file" in rest:
        topics = json.loads(Path(rest[rest.index("--file") + 1]).read_text("utf-8"))
    else:
        skip = {i + 1 for i, x in enumerate(rest) if x in ("--from", "--file")}
        topics = [x for i, x in enumerate(rest) if not x.startswith("--") and i not in skip]
    if not topics:
        fail("batch", stage="start", error="주제가 없습니다")
    r = _call("POST", "/api/batch", {"from": frm, "topics": topics})
    for it in r["items"]:
        print(f"{'시작' if it.get('started') else '실패'}  {it['project']}  {it['topic']}" + (f"  ({it['error']})" if it.get("error") else ""))
    ok("batch", id=r["id"], count=str(len(r["items"])), next=f"python3 engine/core/batch.py status {r['id']} · 답에 ```batch\\n{r['id']}\\n``` 블록")
    return 0


if __name__ == "__main__":
    sys.exit(main())
