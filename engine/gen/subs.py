#!/usr/bin/env python3
"""자막 · 글자 편집 — 작업 공간 자막 편집 화면과 에이전트가 같이 쓰는 한 가지 모양(엔진은 Craft 하나, 이 도구는 값만 읽고 쓴다).

모드
  dub    클립 재편집(data/compositions/<id>/dub.json) — 자막마다 시각 · 위치 · 크기 · 강조를 자유롭게(EffectCraft 레시피 typo-dub-at)
  story  그 밖의 콘티 — 장면마다 화면 글자(caption) · 제목 · 화면 글자 높이(direction.screen_text_y) · 나레이션 자막 높이(direction.subs.y)

공통 모양(시각은 영상 처음부터 초):
{
  "mode": "dub" | "story", "duration": 26.0,
  "title": ["첫 줄", "둘째 줄"],
  "segments": [{"i": 0, "start": 0.0, "sec": 5.2, "type": "clip"}],           # 장면(dub 은 구간)
  "items": [{"id": "c0", "seg": 0, "t0": 0.1, "t1": 1.6, "text": "근데", "size": "M", "x": 0.5, "y": 0.62, "hot": false}],
  "style": {"screen_text_y": 0.17, "subs_y": 0.7},                          # story 만
  "editable": {"move": true, "time": true, "size": true, "hot": true, "add": true}
}
  python3 engine/gen/subs.py get <id>
  python3 engine/gen/subs.py put <id> <파일.json | ->        # 같은 모양을 받아 저장(사람 · 에이전트 공통). dub 은 콘티도 다시 만든다(초안은 따로 build)
저장할 때마다 앞 판을 data/compositions/<id>/edits/ 에 남긴다(되돌리기 · 비교).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402

SIZES = ("S", "M", "L", "XL")


def dub_path(pid: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "dub.json"


def sb_path(pid: str) -> Path:
    return ROOT / "data" / "storyboards" / f"{pid}.json"


def seg_sec(s: dict) -> float:
    return round((s["out"] - s["in"]) if s["type"] == "clip" else s["sec"], 3)


def get(pid: str) -> dict:
    if dub_path(pid).exists():
        d = json.loads(dub_path(pid).read_text("utf-8"))
        segs, t = [], 0.0
        for i, s in enumerate(d.get("segments") or []):
            sec = seg_sec(s)
            segs.append({"i": i, "start": round(t, 3), "sec": sec, "type": s["type"]}); t += sec
        items = []
        for j, c in enumerate(d.get("captions") or []):
            st = segs[c["seg"]]["start"] if 0 <= c.get("seg", -1) < len(segs) else 0
            items.append({"id": f"c{j}", "seg": c["seg"], "t0": round(st + c["t0"], 3), "t1": round(st + c["t1"], 3), "text": c["text"],
                          "size": c.get("size", "M"), "x": c.get("x", 0.5), "y": c.get("y", 0.6), "hot": bool(c.get("hot"))})
        return {"mode": "dub", "duration": round(t, 3), "title": (d.get("title") or ["", ""]) + [""] * (2 - len(d.get("title") or [])),
                "segments": segs, "items": items, "editable": {"move": True, "time": True, "size": True, "hot": True, "add": True}}
    if not sb_path(pid).exists():
        fail("subs", stage="get", error="콘티가 없다")
    sb = json.loads(sb_path(pid).read_text("utf-8"))
    segs, items, t = [], [], 0.0
    for i, s in enumerate(sb.get("scenes") or []):
        sec = float(s.get("sec") or 0)
        segs.append({"i": i, "start": round(t, 3), "sec": sec, "type": "scene"})
        items.append({"id": f"s{i}", "seg": i, "t0": round(t, 3), "t1": round(t + sec, 3), "text": s.get("caption") or "", "size": "M", "x": 0.5,
                      "y": float((sb.get("direction") or {}).get("screen_text_y") or 0.17), "hot": False})
        t += sec
    d = sb.get("direction") or {}
    title = str(sb.get("title") or "")
    return {"mode": "story", "duration": round(t, 3), "title": [title, ""], "segments": segs, "items": items,
            "style": {"screen_text_y": float(d.get("screen_text_y") or 0.17), "subs_y": float((d.get("subs") or {}).get("y") or 0.7)},
            "editable": {"move": False, "time": False, "size": False, "hot": False, "add": False}}


def backup(pid: str, src: Path) -> None:
    if src.exists():
        d = ROOT / "data" / "compositions" / pid / "edits"; d.mkdir(parents=True, exist_ok=True)
        (d / f"{time.strftime('%Y%m%d-%H%M%S')}-{src.name}").write_bytes(src.read_bytes())


def put(pid: str, m: dict, by: str) -> dict:
    cur = get(pid)
    if m.get("mode") != cur["mode"]:
        fail("subs", stage="put", error=f"모드가 다르다({m.get('mode')} ≠ {cur['mode']})")
    if cur["mode"] == "dub":
        p = dub_path(pid); d = json.loads(p.read_text("utf-8"))
        segs = cur["segments"]
        caps = []
        for it in m.get("items") or []:
            text = str(it.get("text") or "").strip()
            if not text:
                continue
            t0, t1 = float(it["t0"]), float(it["t1"])
            seg = next((s for s in segs if s["start"] - 1e-6 <= t0 < s["start"] + s["sec"]), segs[-1])   # 시작 시각이 든 구간
            a = max(0.0, round(t0 - seg["start"], 3)); b = min(seg["sec"], round(t1 - seg["start"], 3))
            if b - a < 0.15:
                fail("subs", stage="put", error=f"'{text}': 너무 짧다({b - a:.2f}초) — 구간 경계를 넘지 않게")
            caps.append({"seg": seg["i"], "t0": a, "t1": b, "text": text, "size": it.get("size") if it.get("size") in SIZES else "M",
                         "x": round(min(0.95, max(0.05, float(it.get("x", 0.5)))), 3), "y": round(min(0.82, max(0.16, float(it.get("y", 0.6)))), 3),
                         **({"hot": True} if it.get("hot") else {})})
        caps.sort(key=lambda c: (c["seg"], c["t0"]))
        backup(pid, p)
        d["captions"] = caps
        title = [str(x).strip() for x in (m.get("title") or []) if str(x).strip()]
        if title:
            d["title"] = title[:2]
        d.setdefault("edits", []).append({"by": by, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "what": "자막 · 제목"})
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", "utf-8")
        import dub
        dub.to_storyboard(pid)
        return {"saved": len(caps), "next": "초안 다시 만들기(dub.py build) — 확정 미리보기는 정지 화면으로"}
    p = sb_path(pid); sb = json.loads(p.read_text("utf-8"))
    backup(pid, p)
    by_seg = {it["seg"]: it for it in m.get("items") or []}
    for i, s in enumerate(sb.get("scenes") or []):
        if i in by_seg:
            s["caption"] = str(by_seg[i].get("text") or "")[:28]
    if m.get("title") and str(m["title"][0]).strip():
        sb["title"] = str(m["title"][0]).strip()[:40]
    st = m.get("style") or {}
    d = sb.setdefault("direction", {})
    if "screen_text_y" in st:
        d["screen_text_y"] = round(min(0.4, max(0.08, float(st["screen_text_y"]))), 3)
    if "subs_y" in st:
        d["subs"] = {**(d.get("subs") or {}), "y": round(min(0.82, max(0.5, float(st["subs_y"]))), 3)}
    sb.setdefault("meta", {}).setdefault("edits", []).append({"by": by, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "what": "자막 · 제목"})
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"saved": len(by_seg), "next": "초안 다시 만들기 — 확정 미리보기는 정지 화면으로"}


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in ("get", "put"):
        print(__doc__); return 2
    pid = sys.argv[2]
    if sys.argv[1] == "get":
        print(json.dumps(get(pid), ensure_ascii=False)); return 0
    src = sys.argv[3] if len(sys.argv) > 3 else "-"
    m = json.loads(sys.stdin.read() if src == "-" else Path(src).read_text("utf-8"))
    by = sys.argv[4] if len(sys.argv) > 4 else "agent"
    r = put(pid, m, by)
    ok("subs", saved=str(r["saved"]), next=r["next"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
