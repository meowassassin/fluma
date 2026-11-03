#!/usr/bin/env python3
"""제작 관문 — 사용자 의도를 확인하고, 시안(장면 1~3)을 사용자가 본 뒤에만 최종 렌더 · 유료 생성으로 넘어간다.

  python3 scripts/gate.py status <id>              # 지금 어디까지 확인됐나
  python3 scripts/gate.py intent <id>              # 사용자가 의도 카드(콘티 intent)를 확인했다 — 사용자가 채팅 · 버튼으로 '좋다'고 한 뒤에만
  python3 scripts/gate.py draft  <id>              # 사용자가 시안(render.py --draft --scenes 1-3)을 보고 '좋다'고 했다
  python3 scripts/gate.py check  <id> --for render|gen   # render.py(최종)가 부른다 — 막히면 종료 코드 3

왜: 레퍼런스 느낌 · 말투 · 화면을 사용자 의도와 다르게 잡은 채 전체를 만들고 고치면 공수가 커지고,
    실사 생성(Seedance · Wan …)은 한 번마다 돈이 든다(2026-11-02 바이낸스 영상: 수정 요청 약 20번 · 나레이션 18번 다시 합성).
규칙
  · 의도(intent.summary · reference_use)가 확인된 뒤 바뀌면 다시 확인
  · 시안 승인은 장면 1~3 의 화면 구성(visual · elements · screen · beat)에 묶인다 — 그 칸이 바뀌면 다시 시안. 나레이션 어미만 바뀌면 그대로
  · 유료 생성은 의도 확인 + 시안 승인 둘 다 필요
기록: workspace/render/<id>/gate.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sb_of(sid: str) -> tuple[Path, dict]:
    p = ROOT / "storyboards" / f"{sid}.json"
    if not p.exists():
        sys.exit(f"콘티가 없습니다: {p}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def gate_path(sid: str) -> Path:
    d = ROOT / "workspace" / "render" / sid; d.mkdir(parents=True, exist_ok=True)
    return d / "gate.json"


def read(sid: str) -> dict:
    p = gate_path(sid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write(sid: str, g: dict):
    gate_path(sid).write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")


def h(o) -> str:
    return hashlib.sha1(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def intent_hash(sb: dict) -> str | None:
    it = sb.get("intent") or {}
    return h([it.get("summary"), it.get("reference_use")]) if it.get("summary") else None


def draft_hash(sb: dict) -> str:
    return h([{k: sc.get(k) for k in ("visual", "elements", "screen", "beat")} for sc in sb.get("scenes", [])[:3]])


def draft_video(sid: str) -> Path | None:
    vids = sorted((ROOT / "out").glob(f"{sid}-*-s1-3*-draft.mp4"), key=lambda p: p.stat().st_mtime)
    return vids[-1] if vids else None


def status(sid: str) -> dict:
    _, sb = sb_of(sid)
    g = read(sid)
    ih = intent_hash(sb)
    intent_ok = bool(ih and g.get("intent", {}).get("hash") == ih)
    draft_ok = g.get("draft", {}).get("hash") == draft_hash(sb)
    why = []
    if not ih:
        why.append("의도 카드(콘티 intent.summary)가 비어 있음 — 사용자가 원하는 것 · 레퍼런스에서 가져올 것을 적고 확인받기")
    elif not intent_ok:
        why.append("의도 카드를 사용자가 아직 확인하지 않음(또는 확인 뒤 바뀜) — 보여 주고 '좋다'를 받은 뒤 gate.py intent")
    if not draft_ok:
        dv = draft_video(sid)
        why.append("시안 승인 없음(또는 승인 뒤 장면 1~3 화면이 바뀜) — " + (f"시안 {dv.relative_to(ROOT)} 을 보여 주고 '좋다'를 받은 뒤 gate.py draft" if dv else
                   f"먼저 python3 scripts/render.py storyboards/{sid}.json --draft --scenes 1-3"))
    return {"intent": intent_ok, "draft": draft_ok, "why": why, "log": g.get("log", [])[-5:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["status", "intent", "draft", "check"])
    ap.add_argument("id")
    ap.add_argument("--for", dest="purpose", choices=["render", "gen"], default="render")
    ap.add_argument("--by", default="chat", help="누가 확인했나(chat · button)")
    a = ap.parse_args()
    sp, sb = sb_of(a.id)
    g = read(a.id)
    log = g.setdefault("log", [])
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    if a.cmd == "intent":
        ih = intent_hash(sb)
        if not ih:
            sys.exit("의도 카드(콘티 intent.summary)가 비어 있습니다 — 먼저 적으세요")
        g["intent"] = {"hash": ih, "at": now, "by": a.by}
        sb.setdefault("intent", {})["confirmed"] = True
        sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log.append({"at": now, "what": "intent", "by": a.by}); write(a.id, g)
        print(json.dumps({"ok": True, "intent": True}, ensure_ascii=False)); return
    if a.cmd == "draft":
        dv = draft_video(a.id)
        if not dv:
            sys.exit(f"시안 영상이 없습니다 — python3 scripts/render.py storyboards/{a.id}.json --draft --scenes 1-3")
        g["draft"] = {"hash": draft_hash(sb), "at": now, "by": a.by, "video": str(dv.relative_to(ROOT))}
        log.append({"at": now, "what": "draft", "by": a.by}); write(a.id, g)
        print(json.dumps({"ok": True, "draft": True, "video": str(dv.relative_to(ROOT))}, ensure_ascii=False)); return
    st = status(a.id)
    if a.cmd == "status":
        print(json.dumps(st, ensure_ascii=False)); return
    missing = [k for k in ("intent", "draft") if not st[k]]
    if missing:
        what = "최종 렌더" if a.purpose == "render" else "유료 생성"
        print(f"[관문] {what} 전에 사용자 확인이 필요합니다:\n  " + "\n  ".join(st["why"]), file=sys.stderr)
        sys.exit(3)
    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
