#!/usr/bin/env python3
"""품질 관문 — 경고를 '막음'과 '권고'로 나누고, 막음이 남으면 완성본으로 내보내지 않는다(2026-11-18 사용자 결정).

2026-11-17 제작 7편이 모두 경고가 남은 채 '완성'으로 끝났다(경고를 보고 고친 건 1편). 그래서:
  막음(block)  결과 화면 · 소리를 잰 신호 — 고치거나, 사용자가 사유와 함께 면제해야 통과
  권고(advise) 말투 · 구성 · 절차 신호 — 다 보여 주고 고칠 수 있으면 고친다(막지는 않음)
오탐이 많던 것은 막지 않는다(실측): D03 ref 없음(57건 전부 이 경우 — 지움) · T34 컷 수(연속 craft 장면을 잘못 잼) ·
D10 72~80%(레퍼런스 30편 평균 평평한 면적 중간값 55%, 72% 초과 17% — 80% 초과만 막음) · 절차(D01 · D02 · D04 · D05).

면제: 콘티 "waivers": {"D10:3": {"why": "...", "user_said": "사용자가 한 말 그대로"}} — 키는 코드 또는 코드:장면.
사용자가 요청했을 때만 적는다(에이전트가 스스로 면제하지 않는다).

  python3 engine/checks/quality_gate.py check <id>     # 마지막 produce 결과의 막음이 남았나(publish 가 부른다)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())

BLOCK_CODES = {"D03", "D11", "D12", "D13", "D14", "D15", "T32", "T33"}   # D10 은 값으로(designcheck 가 block 을 정한다)


def issue(code: str, scene, msg: str, block: bool | None = None) -> dict:
    return {"code": code, "scene": scene, "msg": msg, "block": (code in BLOCK_CODES) if block is None else block}


def from_render_line(line: str) -> dict:
    """렌더가 찍은 '✗ …' · '△ …' 줄 — ✗(실패)는 막음, △ 는 T32 · T33 만 막음"""
    s = line.strip()
    m = re.match(r"^[✗△]\s*([A-Z]\d+)?", s)
    code = (m.group(1) if m else None) or ("ED" if s.startswith("✗") else "R?")
    msg = s[m.end():].strip() if m and m.group(1) else s.lstrip("✗△ ").strip()
    return issue(code, None, msg, block=s.startswith("✗") or code in ("T32", "T33"))


def waived(sb: dict, it: dict) -> str | None:
    w = sb.get("waivers") or {}
    for k in (f"{it['code']}:{it['scene']}", it["code"]):
        v = w.get(k)
        if v and (v.get("user_said") if isinstance(v, dict) else None):
            return v.get("why") or v["user_said"]
    return None


def split(sb: dict, issues: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(막음 · 면제됨 · 권고)"""
    block, ok, adv = [], [], []
    for it in issues:
        if not it["block"]:
            adv.append(it)
        elif waived(sb, it):
            ok.append({**it, "waived": waived(sb, it)})
        else:
            block.append(it)
    return block, ok, adv


def line(it: dict) -> str:
    return f"{it['code']} {str(it['scene']) + '장면 ' if it.get('scene') else ''}{it['msg']}"


def path(sid: str) -> Path:
    return ROOT / "data" / "workspace" / "tmp" / sid / "quality.json"


def save(sid: str, video: str, block: list, ok: list, adv: list) -> Path:
    p = path(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"video": video, "block": block, "waived": ok, "advise": adv}, ensure_ascii=False, indent=1), "utf-8")
    return p


def check(sid: str) -> list[str]:
    """최종 렌더 · 업로드 전에 — 마지막 produce 의 막음이 남았으면 그 목록(없으면 빈 목록). produce 를 안 거친 영상(생성 경로)은 통과"""
    p = path(sid)
    if not p.exists():
        return []
    return [line(x) for x in json.loads(p.read_text("utf-8")).get("block") or []]


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "check":
        bad = check(sys.argv[2])
        print("\n".join(bad) or "막음 없음")
        sys.exit(1 if bad else 0)
    print(__doc__)
    sys.exit(2)
