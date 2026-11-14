#!/usr/bin/env python3
"""실제 에셋 경로 — 퍼온 클립 재편집 쇼츠(밈 · 반응 · 더빙 자막). 생성 경로의 2~4단계(캐릭터 시트 · 키 프레임 · 영상 생성)를 건너뛰고
1 기획 → [이 도구] → 5 Craft 편집 → 6 렌더 · 업로드로 간다. 화면 · 자막은 Craft 도구가 맡는다:
  클립 · 끼워 넣기 · 검은 화면 = 장면(FilmCraft 조립), 제목 두 줄 = EffectCraft 레시피 typo-headline,
  더빙 자막(낱말 · 구마다 크기 · 위치 · 나타남 · 사라짐) = EffectCraft 레시피 typo-dub-at, 삐 소리 = 효과음.

더빙 계획(data/compositions/<id>/dub.json) — 에이전트가 원래 말(clip.py --subs)과 끊을 자리(engine/capture/cutaway.py)를 보고 쓴다:
{
  "clip": "data/public/elements/<id>/c1/clip.mp4",
  "title": ["첫 줄(흰색)", "둘째 줄(노랑)"],
  "segments": [                                           # 화면 순서대로. 각 2초 이상(편집 엔진 장면 최소)
    {"type": "clip", "in": 30.9, "out": 35.8},            # 원본 소리 그대로
    {"type": "insert", "src": "<그림 · 영상 경로>", "sec": 3, "bleep": true, "credit": "출처"},   # 끊어 넣기(원본 소리 없음, bleep 이면 삐)
    {"type": "black", "sec": 2}                           # 검은 화면 + 글자만
  ],
  "captions": [ {"seg": 0, "t0": 0.2, "t1": 1.1, "text": "근데", "size": "M", "x": 0.35, "y": 0.52} ]   # seg 기준 초, x · y 는 화면 비율(0~1)
}
  python3 engine/gen/dub.py check <id>
  python3 engine/gen/dub.py storyboard <id>      # → data/storyboards/<id>.json (format clip, 나레이션 없음)
  python3 engine/gen/dub.py build <id>           # → 초안 렌더(engine/render.py --draft)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402

W, H = 1080, 1920
SIZES = {"S": 52, "M": 72, "L": 100, "XL": 140}
SAFE_TOP, SAFE_BOTTOM = 0.08, 0.82
WINDOW = {"scale": 1.18, "dy": 0.06}    # 가운데 창: 레퍼런스(밈 클립 쇼츠)처럼 화면 폭 거의 가득 · 제목 아래로 조금 내림 — 콘티 adjust 로 영상마다 바꿀 수 있다      # 위 상태 표시줄 · 아래 쇼츠 제목 · 버튼


def load(pid: str) -> dict:
    p = ROOT / "data" / "compositions" / pid / "dub.json"
    if not p.exists():
        fail("dub", stage="dub", error=f"더빙 계획 없음: {p.relative_to(ROOT)}")
    return json.loads(p.read_text("utf-8"))


def problems(d: dict) -> list[str]:
    errs = []
    if not (ROOT / str(d.get("clip") or "-")).exists():
        errs.append(f"클립 없음: {d.get('clip')}")
    segs = d.get("segments") or []
    if not segs:
        errs.append("segments 가 비었다")
    for i, s in enumerate(segs):
        sec = (s.get("out", 0) - s.get("in", 0)) if s.get("type") == "clip" else s.get("sec", 0)
        if s.get("type") not in ("clip", "insert", "black"):
            errs.append(f"segment {i}: type 은 clip · insert · black")
        elif sec < 2:
            errs.append(f"segment {i}: {sec:.2f}초 < 2초(편집 엔진 장면 최소) — 이웃과 합치거나 늘린다")
        elif sec > 12:
            errs.append(f"segment {i}: {sec:.2f}초 > 12초 — 나눈다")
        if s.get("type") == "insert" and not (ROOT / str(s.get("src") or "-")).exists():
            errs.append(f"segment {i}: 끼워 넣을 파일 없음 {s.get('src')}")
    for j, c in enumerate(d.get("captions") or []):
        if not 0 <= c.get("seg", -1) < len(segs):
            errs.append(f"caption {j}: seg 번호가 없다")
            continue
        s = segs[c["seg"]]
        sec = (s["out"] - s["in"]) if s["type"] == "clip" else s["sec"]
        if not (0 <= c["t0"] < c["t1"] <= sec + 1e-6):
            errs.append(f"caption {j} '{c['text']}': 시각 {c['t0']}~{c['t1']} 이 장면 0~{sec:.2f} 밖")
        if c.get("size", "M") not in SIZES:
            errs.append(f"caption {j}: size 는 {'/'.join(SIZES)}")
        if not (SAFE_TOP + 0.08 <= c.get("y", 0.5) <= SAFE_BOTTOM):
            errs.append(f"caption {j} '{c['text']}': y {c.get('y')} — 제목 띠 · 아래 18% 를 피한다({SAFE_TOP + 0.08:.2f}~{SAFE_BOTTOM})")
    if not d.get("title") or len(d["title"]) > 2:
        errs.append("title 은 한두 줄")
    return errs


def to_storyboard(pid: str) -> Path:
    d = load(pid)
    errs = problems(d)
    if errs:
        fail("dub", stage="check", error=" / ".join(errs[:6]))
    t1, t2 = (d["title"] + [""])[:2]
    scenes = []
    for i, s in enumerate(d["segments"]):
        sec = round((s["out"] - s["in"]) if s["type"] == "clip" else s["sec"], 2)
        refine = [{"recipe": "typo-headline", "vars": {"L1": t1, "L2": t2, "Y": "230", "SIZE": "84", "C1": "[1,1,1]", "T0": "0", "T1": str(sec), "BAND": "0", "NM": "Title"}}]
        for c in d.get("captions") or []:
            if c["seg"] == i:
                refine.append({"recipe": "typo-dub-at", "vars": {"TEXT": c["text"].replace('"', "'"), "X": str(round(c.get("x", 0.5) * W)), "Y": str(round(c.get("y", 0.5) * H)),
                                                                 "SIZE": str(SIZES[c.get("size", "M")]), "T0": str(c["t0"]), "T1": str(c["t1"]),
                                                                 **({"COLOR": "[1,0.86,0.2]"} if c.get("hot") else {}), "NM": f"Dub {i}.{c['t0']}"}})
        if s["type"] == "clip":
            mats = [{"id": f"g{i:02d}", "type": "video", "src": d["clip"], "in": s["in"], "out": s["out"], "audio": True, "place": "center", "adjust": dict(WINDOW), "what": "퍼온 클립 구간"}]
            vis = "footage"
        elif s["type"] == "insert":
            kind = "video" if Path(s["src"]).suffix.lower() in (".mp4", ".mov", ".webm") else "image"
            mats = [{"id": f"g{i:02d}", "type": kind, "src": s["src"], "place": "center", "adjust": dict(WINDOW), "what": "끊어 넣기", **({"audio": False} if kind == "video" else {}),
                     **({"credit": s["credit"]} if s.get("credit") else {})}]
            vis = "still" if kind == "image" else "footage"
        else:
            mats, vis = [], "text"
        sc = {"role": "hook" if i == 0 else "item", "sec": sec, "caption": "", "narration": "", "visual": {"kind": vis}, "materials": mats, "refine": refine}
        if s.get("bleep"):
            sc["sfx"] = [{"name": "bleep", "at": 0.0, "keep": True}]
        scenes.append(sc)
    total = sum(x["sec"] for x in scenes)
    out = ROOT / "data" / "storyboards" / f"{pid}.json"
    old = json.loads(out.read_text("utf-8")) if out.exists() else {}
    sb = {"id": pid, "version": 1, "engine": "craft", "format": "clip", "aspect": "9:16", "duration_sec": max(5, min(60, round(total))),
          "title": (t1 + " " + t2).strip()[:40], "cta": "", "kind": "story", "language": "ko",
          "music": {"use": False, "hold": True, "why": "음악 기능 보류 — 원본 소리 그대로"},
          "direction": {"layout": "card", "color_bg": "#000000", "background": "#000000", "frame": {"round": True, "shadow": False, "push": 1.0}, "cam_push": 1.0,
                        "bg_preset": None, "bg_motion": False, "locked": ["color_bg", "layout"], **(old.get("direction") or {})},
          "meta": {"source": "dub", "dub": f"data/compositions/{pid}/dub.json", "pipeline": "fluma-shortform v2 · 실제 에셋 경로"},
          "scenes": scenes}
    out.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for k in ("check", "storyboard", "build"):
        x = sp.add_parser(k); x.add_argument("pid")
    a = ap.parse_args()
    if a.cmd == "check":
        errs = problems(load(a.pid))
        for e in errs:
            print(f"✗ {e}")
        if errs:
            fail("dub", stage="check", error=" / ".join(errs[:6]))
        ok("dub", next="dub.py storyboard → build"); return 0
    sbp = to_storyboard(a.pid)
    if a.cmd == "storyboard":
        ok("dub", storyboard=str(sbp.relative_to(ROOT))); return 0
    # 소리 단계 먼저 — 이걸 건너뛰면 초안에 소리 트랙이 아예 없다(2026-11-12 시험). 나레이션은 없고 클립 원음 · 효과음만 섞인다
    ra = subprocess.run([sys.executable, "engine/voice/assemble_audio.py", str(sbp.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, timeout=1800)
    if ra.returncode:
        fail("dub", stage="audio", error=(ra.stderr or ra.stdout).strip()[-400:])
    r = subprocess.run([sys.executable, "engine/render.py", str(sbp.relative_to(ROOT)), "--draft"], cwd=ROOT, capture_output=True, text=True, timeout=3600)
    import assemble
    b = assemble.block(r.stdout)
    if r.returncode or b.get("head") != "FLUMA_RESULT":
        fail("dub", stage="render", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-400:]])[0])
    ok("dub", storyboard=str(sbp.relative_to(ROOT)), file=b["file"][0], next="초안을 보고 자막 위치 · 크기 · 시각을 dub.json 에서 고쳐 다시 build — 화면 세부는 Craft(refine · knob)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
