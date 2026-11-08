#!/usr/bin/env python3
"""영상 한 편에 사람이 든 품 · 시간 · 비용 · 자체 품질 점검을 한 줄로 — 공개 데모 결과물 옆에 붙는 숫자(2026-11-02 결정).

  python3 engine/core/effort.py <영상 id>            # 사람이 읽는 요약
  python3 engine/core/effort.py <영상 id> --json
  python3 engine/core/effort.py <영상 id> --md       # README 에 붙일 한 줄

재료(모두 도구가 남긴 기록 그대로, 손으로 고치지 않는다):
  사람 개입   data/workspace/effort/<id>.jsonl — 서버가 사람이 화면에서 한 일만 적는다(승인 · 채팅 · 직접 편집 · 되돌리기 · 올리기 · 음성 다시).
              렌더 버튼은 따로 센다(품이 아니라 확인). 에이전트가 스스로 한 일은 들어가지 않는다
  걸린 시간   첫 기록 ~ 최종 렌더 파일이 생긴 시각(사람이 기다린 시간 포함 — 일한 시간이 아님)
  비용        data/workspace/gen-ledger.jsonl 에서 이 영상(project)의 유료 생성 추정액 합 · 음성 엔진
  품질        data/workspace/render/<id>/density.json(edit_density) — 사람 쇼츠 기준과 함께
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
KIND_KO = {"approve": "승인", "chat": "채팅", "edit": "직접 편집", "undo": "되돌리기", "upload": "재료 올리기", "voice": "음성 다시", "render": "렌더 누름"}


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return out


def summary(sid: str) -> dict:
    ev = load_jsonl(ROOT / "data" / "workspace" / "effort" / f"{sid}.jsonl")
    kinds: dict[str, int] = {}
    for e in ev:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    human = sum(v for k, v in kinds.items() if k != "render")
    finals = [p for p in (ROOT / "data" / "out").glob(f"{sid}-*.mp4") if "draft" not in p.name and "-s" not in p.name.split(sid)[-1]]
    final = max(finals, key=lambda p: p.stat().st_mtime) if finals else None
    t0 = datetime.fromisoformat(ev[0]["at"].replace("Z", "+00:00")).timestamp() if ev else None
    t1 = final.stat().st_mtime if final else None
    minutes = round((t1 - t0) / 60) if t0 and t1 and t1 > t0 else None
    usd = round(sum(float(x.get("usd") or 0) for x in load_jsonl(ROOT / "data" / "workspace" / "gen-ledger.jsonl") if x.get("project") == sid), 2)
    sbp = ROOT / "data" / "storyboards" / f"{sid}.json"
    sb = json.loads(sbp.read_text(encoding="utf-8")) if sbp.exists() else {}
    voice = (sb.get("voice") or {}).get("engine") or "edge"
    rd = ROOT / "data" / "workspace" / "render" / sid
    dens = json.loads((rd / "density.json").read_text(encoding="utf-8")) if (rd / "density.json").exists() else None
    look = json.loads((rd / "look-check.json").read_text(encoding="utf-8")) if (rd / "look-check.json").exists() else None
    base = {}
    bp = ROOT / "engine" / "spec" / "presets" / "density.json"
    if bp.exists():
        base = json.loads(bp.read_text(encoding="utf-8")).get("median") or {}
    return {"id": sid, "human_actions": human, "by_kind": kinds, "renders": kinds.get("render", 0), "minutes": minutes,
            "final": str(final.relative_to(ROOT)) if final else None, "paid_usd": usd, "voice": voice,
            "quality": ({"text_px": dens.get("text_px"), "kinds": dens.get("kinds"), "kind_switch": dens.get("kind_switch"), "problems": dens.get("problems") or []} if dens else None),
            "look_ok": (look.get("ok") if look else None), "human_baseline": {k: base.get(k) for k in ("text_px", "kinds", "kind_switch")},
            "logged": bool(ev)}


def md(s: dict) -> str:
    q, b = s["quality"] or {}, s["human_baseline"]
    parts = [f"사람 개입 {s['human_actions']}번", f"{s['minutes']}분" if s["minutes"] is not None else "시간 기록 없음",
             f"유료 생성 ${s['paid_usd']:.2f} · 음성 {s['voice']}"]
    if q:
        parts.append(f"글자 {q['text_px']:.0f}px ({b.get('text_px')}) · 재료 {q['kinds']}가지 ({b.get('kinds')}) · 재료 전환 {q['kind_switch']}/10초 ({b.get('kind_switch')})")
    if s["look_ok"] is not None:
        parts.append("'AI 티' 검사 " + ("통과" if s["look_ok"] else "실패"))
    return " · ".join(parts) + "  — 괄호는 사람이 편집한 쇼츠 기준"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    s = summary(a.id)
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1)); return
    if a.md:
        print(md(s)); return
    if not s["logged"]:
        print("(사람 개입 기록 없음 — 이 기록은 2026-11-02 이후 웹 화면에서 만든 영상부터 남는다)", file=sys.stderr)
    print(md(s))
    if s["by_kind"]:
        print("  " + " · ".join(f"{KIND_KO.get(k, k)} {v}" for k, v in s["by_kind"].items()))
    for p in (s["quality"] or {}).get("problems", []):
        print(f"  ✗ {p}")


if __name__ == "__main__":
    main()
