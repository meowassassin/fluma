#!/usr/bin/env python3
"""시청 지속 검사 — 콘티가 시청자를 붙잡을 구조인지 본다. 한 영상의 취향이 아니라 모든 영상에 드는 규칙이다.

  R01 같은 형식이 이어진다 · R02 형식 가짓수가 적다 · R03 한 인물만 나온다 · R04 8초 넘게 새 일이 없다
  R05 첫 장면에 궁금증이 없다 · R06 사실 영상인데 실제 자료가 없다 · R07 사람이 없다(연기 · 말풍선 없음)
  R08 닳은 표현 · R09 놀라운 사실(surprise)이 표시되지 않았다
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TIRED = ("알아보겠습니다", "살펴보겠습니다", "놀랍게도", "과연", "오늘은", "여러분", "함께 알아", "라고 할 수 있습니다", "중요합니다", "어떻게 생각하시나요")


def form_of(sc: dict) -> str:
    """장면의 형식 — 콘티에 적힌 것(form 재료 · 실제 자료 · 3D · 인물)"""
    fs = []
    for m in sc.get("materials") or []:
        t = m.get("type")
        if m.get("show") is False:                 # 다른 재료의 입력일 뿐 화면에 안 나온다
            continue
        elif t in ("archive", "model3d", "video", "screen", "web", "chart", "doc_quote", "photo", "meme", "live"):
            fs.append(t)
    return fs[0] if fs else (next((m.get("type") for m in sc.get("materials") or [] ), None) or "없음")


CLIP_FORMATS = ("ranking", "clip")       # 퍼온 클립 모음: 같은 종류(실사 클립)가 이어지고 연기하는 인물이 없는 게 형식 자체


def check(sb: dict) -> list:
    out = check_all(sb)
    if sb.get("format") in CLIP_FORMATS:
        out = [r for r in out if r[0] not in ("R01", "R02", "R03", "R07")]
    return out


def check_all(sb: dict) -> list:
    out = []
    S = sb.get("scenes") or []
    forms = [form_of(s) for s in S]
    for i, (a, b) in enumerate(zip(forms, forms[1:]), 2):
        if a == b:
            out.append(("R01", i, f"앞 장면과 같은 형식({a}) — 장면마다 형식을 바꾼다"))
    if len(S) >= 4 and len(set(forms)) < round(len(S) * .7):
        out.append(("R02", None, f"형식 {len(set(forms))}가지뿐(장면 {len(S)}개) — 레퍼런스는 장면마다 다르다"))
    who = [str(m.get("id")).split("_")[0]                                     # 직접 그린 인물(art)은 id 앞부분이 같으면 같은 사람
           for s in S for m in s.get("materials") or [] if m.get("type") in ("art", "relic")]
    if len(S) >= 5 and len(set(who)) < 2:
        out.append(("R03", None, f"인물이 {len(set(who))}명 — 영상이 길수록 다른 사람이 나와야 질리지 않는다"))
    if len(S) >= 5 and not who:
        out.append(("R07", None, "사람이 없다 — 시청자는 사람의 반응을 따라간다"))
    for i, s in enumerate(S, 1):
        n = len(s.get("refine") or [])
        if float(s.get("sec") or 0) > 8 and n < 2:
            out.append(("R04", i, f"{s.get('sec')}초 장면에 변화 {n}건 — 8초 안에 새로운 일이 일어나야 한다"))
    first = str((S[0] if S else {}).get("narration") or "")
    if S and not re.search(r"[?]|그런데|왜|사실|진짜|아시|유명|보셨|기원|사람들이|몰랐", first):
        out.append(("R05", 1, "첫 장면에 궁금증이 없다"))
    if str(sb.get("kind") or "fact") == "fact" and len(S) >= 4 and not any(m.get("type") in ("archive", "relic", "photo", "screen", "web", "video", "doc_quote", "stock") for s in S for m in s.get("materials") or []):
        out.append(("R06", None, "실제 자료가 하나도 없다 — 사실을 다루면 진짜 사진 · 문서를 보여 준다(engine/capture/commons.py)"))
    for i, s in enumerate(S, 1):
        for w in TIRED:
            if w in str(s.get("narration") or ""):
                out.append(("R08", i, f"닳은 표현 '{w}'"))
    if len(S) >= 5 and not any(s.get("surprise") for s in S):
        out.append(("R09", None, "시청자가 놀랄 장면이 표시되지 않았다 — 장면 surprise 칸에 '이 영상의 황당한 사실'을 적는다"))
    return out


if __name__ == "__main__":
    for c, n, m in check(json.loads(Path(sys.argv[1]).read_text("utf-8"))):
        print(c, f"{n}장면" if n else "전체", m)
