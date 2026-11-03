#!/usr/bin/env python3
"""말투만 고치기 — 문장 내용(낱말 줄기)은 그대로 두고 어미 · 이음말 · 문장부호만 바뀌었는지 확인한 뒤 콘티에 넣는다.

  python3 scripts/tone_edit.py storyboards/<id>.json <바꿀 글 json>            # 확인만(바뀐 곳 표) — 콘티는 그대로
  python3 scripts/tone_edit.py storyboards/<id>.json <바꿀 글 json> --apply    # 통과하면 콘티 narration 에 넣는다
  python3 scripts/tone_edit.py storyboards/<id>.json <바꿀 글 json> --apply --user-text   # 사용자가 쓴 글 그대로(내용 검사 건너뜀)

바꿀 글 json: {"4": "…새 나레이션…", "6": "…"}  (장면 번호는 1부터)
내용이 바뀌면(낱말이 새로 생기거나 빠짐) 거절하고 어디가 바뀌었는지 보여 준다 — "말투만 바꿔 달라"는 요청에 문장을 새로 쓰지 않게.
사용자가 직접 문장을 불러 준 경우만 --user-text 로 넣는다. 결과: 바뀌기 전 · 후 표(마크다운, 바뀐 곳 굵게).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# 말투 낱말: 이음말 · 군말 · 보조 서술(거예요 · 겁니다 …) — 넣고 빼도 내용이 바뀌지 않는다고 본다
FLEX = {"근데", "그런데", "그래서", "그리고", "이제", "아무튼", "일단", "그냥", "진짜", "약간", "막", "좀", "되게", "뭐", "또", "사실", "참고로",
        "여러분", "여러분들", "여러분들도", "여러분도", "거예요", "거고요", "거죠", "겁니다", "거든요", "건데요", "거", "것", "겁니다만",
        "같아요", "같습니다", "같더라고요", "하더라고요", "합니다", "하고요", "해요", "하죠", "됩니다", "되고요", "돼요", "되겠습니다",
        "있습니다", "있고요", "있어요", "있죠", "있는데", "있는데요", "수", "보시면", "되는", "입니다", "이고요", "이에요", "예요", "이죠", "인데요", "인데"}


def stem(tok: str) -> str:
    """띄어쓰기 단위의 줄기: 문장부호를 떼고 앞 두 글자(한국어 어간은 대개 앞 글자에 있다 — 뚫렸고요 · 뚫렸는데 → 뚫렸)"""
    t = re.sub(r"[^\w가-힣%]", "", tok)
    return t[:2] if re.match(r"[가-힣]", t) else t.lower()


def check(old: str, new: str) -> tuple[bool, list[str]]:
    """내용이 그대로인가 → (통과, 바뀐 내용 낱말 목록)"""
    a, b = old.split(), new.split()
    ka, kb = [stem(x) for x in a], [stem(x) for x in b]
    bad = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        gone = [x for x in a[i1:i2] if re.sub(r"[^\w가-힣]", "", x) not in FLEX]
        came = [x for x in b[j1:j2] if re.sub(r"[^\w가-힣]", "", x) not in FLEX]
        if op == "replace" and len(gone) == len(came):
            # 같은 자리에서 줄기만 같으면 어미 변화 — 줄기가 다르면 내용 변화
            bad += [f"{x}→{y}" for x, y in zip(gone, came) if stem(x) != stem(y)]
        else:
            bad += [f"-{x}" for x in gone] + [f"+{y}" for y in came]
    return not bad, bad


def marked(old: str, new: str) -> str:
    """바뀐 낱말을 굵게"""
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        seg = b[j1:j2]
        out += seg if op == "equal" else [f"**{x}**" for x in seg]
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard")
    ap.add_argument("changes")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--user-text", action="store_true", help="사용자가 직접 불러 준 문장 — 내용 검사 없이 넣는다")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads(sp.read_text(encoding="utf-8"))
    ch = json.loads(Path(a.changes).read_text(encoding="utf-8"))
    rows, refused = [], []
    for k, new in ch.items():
        i = int(k) - 1
        if not (0 <= i < len(sb["scenes"])):
            sys.exit(f"장면 번호가 범위 밖: {k}")
        old = (sb["scenes"][i].get("narration") or "").strip()
        new = str(new).strip()
        ok, bad = check(old, new)
        if not ok and not a.user_text:
            refused.append((k, bad))
        rows.append((k, old, new, ok, bad))
    print("| 장면 | 전 | 후 | 내용 |\n|---|---|---|---|")
    for k, old, new, ok, bad in rows:
        print(f"| {k} | {old} | {marked(old, new)} | {'그대로' if ok else '바뀜: ' + ', '.join(bad)} |")
    if refused and not a.user_text:
        print(json.dumps({"ok": False, "refused": {k: b for k, b in refused},
                          "why": "말투(어미 · 이음말 · 문장부호)만 바꿔야 하는데 내용 낱말이 바뀌었습니다 — 그 낱말을 원래대로 두고 다시. 사용자가 직접 불러 준 문장이면 --user-text"}, ensure_ascii=False))
        sys.exit(2)
    if a.apply:
        for k, _old, new, _ok, _bad in rows:
            sb["scenes"][int(k) - 1]["narration"] = new
        sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "applied": bool(a.apply), "scenes": [k for k, *_ in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
