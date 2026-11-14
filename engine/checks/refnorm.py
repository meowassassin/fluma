#!/usr/bin/env python3
"""레퍼런스 기준 검사 — 콘티의 화면 리듬 · 말 리듬을 '잘 되는 쇼츠'(레퍼런스 X-ray)의 실제 수치와 견준다.
2026-11-10: 각본 · 연출 규칙(writer · director 스킬)이 매번 시스템 프롬프트에 들어가는데도 장면 하나가 5~10초 · 나레이션 한 문장 40~60자 ·
'그래서 / 근데'로 이어지는 강의체가 나왔다. 규칙을 읽히는 것만으로는 안 지켜져서, 레퍼런스에서 잰 수치로 렌더 전에 막는다(lint L50~L52).

  python3 engine/checks/refnorm.py targets [레퍼런스 id …]     # 기준 수치(없으면 받아 둔 X-ray 전체)
  python3 engine/checks/refnorm.py check data/storyboards/<id>.json

기준(레퍼런스 X-ray: data/public/trends/xray/<id>/xray.json)
  shot     샷 길이(초) 중앙값 → L50 장면 안 화면 변화 간격(cue 가 다른 재료 · 컷 · 확대 박자)이 중앙값의 2배(최소 2초)를 넘으면 실패
  phrase   말 덩어리 길이(글자, 공백 제외) 중앙값 — 0.25초 넘는 쉼 · 문장부호로 자름 → L51 콘티 구절이 중앙값의 2배(최소 14자)를 넘으면 실패
  cps      초당 글자 → T50 콘티 나레이션 속도가 ±30% 밖이면 권고
  L52      문장 첫머리 접속어(그래서 · 근데 · 그러니까 · 그리고 · 하지만 · 또 · 이렇게 · 그런데)가 문장의 1/3 넘음 → 실패(강의체)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
XRAY = ROOT / "data" / "public" / "trends" / "xray"
CONNECTIVES = ("그래서", "근데", "그러니까", "그리고", "하지만", "그런데", "또 ", "이렇게", "그럼", "결국")
DEFAULT = {"shot_med": 1.8, "shot_p75": 2.6, "phrase_p90": 16, "phrase_med": 9, "cps": 6.5, "refs": [], "n_shots": 0}   # X-ray 가 하나도 없을 때


def _q(xs: list, q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(len(xs) - 1, int(k) + 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _chars(s: str) -> int:
    return len(re.sub(r"[\s.,?!·…~\"'“”‘’()\[\]-]", "", s))


def phrases_from_words(words: list) -> list[str]:
    """음성 인식 단어(타이밍 포함) → 말 덩어리: 0.25초 넘는 쉼이나 문장부호에서 끊는다"""
    out, cur, last_e = [], [], None
    for w in words:
        t = str(w.get("w", "")).strip()
        if not t:
            continue
        if cur and last_e is not None and float(w.get("s", 0)) - last_e > 0.25:
            out.append(" ".join(cur)); cur = []
        cur.append(t)
        last_e = float(w.get("e", w.get("s", 0)))
        if re.search(r"[.?!,]$", t):
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def phrases_from_text(text: str) -> list[str]:
    """콘티 나레이션 → 구절: 문장부호 · 줄바꿈 · ' / '(장면 경계)에서 끊는다(말할 때 숨 쉬는 자리)"""
    return [p.strip() for p in re.split(r"[.?!,\n]|\s/\s", text) if _chars(p) > 0]


def sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[.?!\n]|\s/\s", text) if _chars(p) > 0]


def targets(ref_ids: list[str] | None = None) -> dict:
    files = [XRAY / r / "xray.json" for r in (ref_ids or [])]
    files = [f for f in files if f.exists()] or sorted(XRAY.glob("*/xray.json"))
    shots, phr, cps_l, used = [], [], [], []
    for f in files:
        try:
            x = json.loads(f.read_text("utf-8"))
        except Exception:
            continue
        used.append(x.get("id") or f.parent.name)
        shots += [float(s["end"]) - float(s["start"]) for s in x.get("shots") or [] if float(s["end"]) > float(s["start"])]
        words = [w for seg in x.get("speech") or [] for w in seg.get("words") or []]
        if words and re.search(r"[가-힣]", " ".join(str(w.get("w", "")) for w in words)):   # 한국어 말만(영어는 글자 수가 다르다)
            ps = phrases_from_words(words)
            if len(ps) >= len(words) / 7:       # 쉼 · 문장부호가 남은 인식 결과만(쉼이 모두 0 · 부호 없음이면 구절을 못 자른다 → 말 덩어리 통계에서 뺀다)
                phr += [_chars(p) for p in ps]
            dur = sum(float(seg["end"]) - float(seg["start"]) for seg in x.get("speech") or [])
            if dur > 3:
                cps_l.append(sum(_chars(str(w.get("w", ""))) for w in words) / dur)
    if not shots:
        return dict(DEFAULT)
    t = {"shot_med": round(statistics.median(shots), 2), "shot_p75": round(_q(shots, 0.75), 2), "n_shots": len(shots), "refs": used}
    t.update({"phrase_med": round(statistics.median(phr), 1), "phrase_p90": round(_q(phr, 0.9), 1)} if phr else {"phrase_med": DEFAULT["phrase_med"], "phrase_p90": DEFAULT["phrase_p90"]})
    t["cps"] = round(statistics.median(cps_l), 2) if cps_l else DEFAULT["cps"]
    return t


def visual_units(sc: dict) -> int:
    """장면 안에서 화면이 바뀌는 횟수 — 재료는 등장 시각(cue)이 다를 때만 따로 센다(cue 없이 함께 나오는 재료 · 주석은 한 화면).
    재료 안 컷(cuts · steps · live items)과 '확대' 박자는 하나씩 더한다"""
    cues, together, inner = set(), False, 0
    for m in sc.get("materials") or []:
        if m.get("show") is False:
            continue
        if m.get("cue"):
            cues.add(str(m["cue"]).strip())
        elif m.get("type") != "overlay":
            together = True
        inner += max(0, len(m.get("cuts") or []) - 1) + max(0, len(m.get("steps") or []) - 1) + (max(0, len(m.get("items") or []) - 1) if m.get("type") == "live" else 0)
    beats = sum(1 for b in sc.get("beats") or [] if b.get("do") in ("확대", "zoom", "cut", "컷", "표시", "재료", "글자"))
    marks = {str(k.get("cue")).strip() for m in sc.get("materials") or [] if m.get("type") == "overlay" for k in m.get("marks") or [] if k.get("cue")}
    # 감독 샷 기능이 카메라를 움직이는 장면(motion.py: 충격 · 변화 → 당겨 들어감, 디테일 → 다가감)은 확대 박자가 없어도 화면이 한 번 바뀐다
    auto_cam = 1 if sc.get("shot_fn") in ("충격", "변화", "디테일") and not any(b.get("do") == "확대" for b in sc.get("beats") or []) else 0
    # 2026-11-11: '표시' · 주석 등장을 세지 않아 감독 스킬('시선 한 곳')과 이 검사가 서로 박자를 넣었다 뺐다 했다
    return max(1, len(cues) + (1 if together else 0) + inner + beats + len(marks - cues) + auto_cam)


def check(sb: dict, t: dict | None = None) -> list:
    """→ [(규칙, 장면 번호 | None, 문장)] — lint 와 같은 꼴. L = 실패(렌더 전에 막음), T = 권고"""
    t = t or targets([r for r in (sb.get("reference") or []) if isinstance(r, str)])
    out = []
    if sb.get("format") in ("clip", "ranking"):        # 퍼온 클립 위주 형식은 원본 리듬을 따른다
        return out
    lim_gap = round(max(2.0, t["shot_med"] * 2), 1)          # 중앙값 기준 — 75% 값은 느린 편집 레퍼런스 하나에 크게 흔들렸다
    for i, sc in enumerate(sb.get("scenes") or [], 1):
        sec = float(sc.get("sec") or 0)
        gap = sec / visual_units(sc)
        if sec > 0 and gap > lim_gap:
            out.append(("T51" if sc.get("long_take") else "L50", i, f"화면이 {gap:.1f}초에 한 번 바뀜({sec:g}초 · 화면 단위 {visual_units(sc)}개) — 레퍼런스 샷 중앙값 {t['shot_med']}초. "
                                  f"{lim_gap}초 안으로: 장면을 쪼개거나 cue 로 재료를 문장마다 바꾸거나 beats 확대 · 녹화 cuts 를 넣는다"
                                  + (f" (원테이크: {sc['long_take']})" if sc.get("long_take") else " — 일부러 길게 잡는 원테이크면 장면에 long_take: '이유'")))
    script = sb.get("script") or " / ".join(str(s.get("narration") or "") for s in sb.get("scenes") or [])
    lim_ph = round(max(14, t["phrase_med"] * 2))             # 음성 인식이 구절을 붙여 90% 값이 부풀어(38자) 중앙값 기준
    long_ph = [(p, _chars(p)) for p in phrases_from_text(script) if _chars(p) > lim_ph]
    if long_ph:
        ex = " · ".join(f"「{p[:24]}{'…' if len(p) > 24 else ''}」 {n}자" for p, n in long_ph[:4])
        out.append(("L51", None, f"한숨에 말하기 긴 구절 {len(long_ph)}개(레퍼런스 말 덩어리 중앙값 {t['phrase_med']}자 → {lim_ph}자까지): {ex} — 쉼표 · 마침표로 끊거나 화면에 맡기고 말을 덜어낸다"))
    sents = sentences(script)
    conn = [s for s in sents if s.startswith(CONNECTIVES)]
    if len(sents) >= 4 and len(conn) > len(sents) / 3:
        out.append(("L52", None, f"문장 {len(sents)}개 중 {len(conn)}개가 접속어로 시작(강의체): " + " · ".join(f"「{s[:14]}…」" for s in conn[:4])
                    + " — 접속어를 지우고 화면 전환이 이어 주게 한다(writer 스킬)"))
    dur = sum(float(s.get("sec") or 0) for s in sb.get("scenes") or [])
    if script.strip() and dur > 0 and t.get("cps"):
        cps = _chars(script) / dur
        if abs(cps - t["cps"]) / t["cps"] > 0.3:
            out.append(("T50", None, f"말 속도 {cps:.1f}자/초 — 레퍼런스 {t['cps']}자/초({'빠름' if cps > t['cps'] else '느림 — 말이 비거나 장면이 늘어짐'})"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["targets", "check"])
    ap.add_argument("rest", nargs="*")
    a = ap.parse_args()
    if a.cmd == "targets":
        print(json.dumps(targets(a.rest), ensure_ascii=False))
        return 0
    sb = json.loads(Path(a.rest[0]).read_text("utf-8"))
    t = targets([r for r in (sb.get("reference") or []) if isinstance(r, str)])
    print(json.dumps({"targets": t}, ensure_ascii=False))
    rows = check(sb, t)
    for code, sc, msg in rows:
        print(f"{code} {'장면 ' + str(sc) if sc else '전체'}: {msg}")
    return 1 if any(c.startswith("L") for c, *_ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
