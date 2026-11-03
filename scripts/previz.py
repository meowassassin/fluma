#!/usr/bin/env python3
"""미리 보기(프리비즈) — 녹화 · 생성에 시간과 돈을 쓰기 전에, 콘티만으로 '대충 만든' 영상을 뽑아 구성 · 타이밍 · 웃음 포인트를 본다.
재료가 아직 없는 자리는 회색 카드(무엇이 들어갈지 · 실사 생성이면 추정 비용)로, 자막 배치 · 제목 띠 · 펀치라인 · 음성 · 박자는 실제와 같게.

  python3 scripts/previz.py grammar storyboards/<id>.json      # 참고 쇼츠 스타일 카드의 자막 항목 → 콘티 grammar(고정 제목 · 펀치라인 · 상황 괄호 · 반응 자막 · 속마음 · 영상 칸)
  python3 scripts/previz.py render storyboards/<id>.json       # 음성(없으면 무료 Edge) → out/<id>-previz.mp4 (540p, 빠름)

화면 문법(grammar)은 손으로 정하지 않는다: 참고 쇼츠에서 잰 위치 · 크기 · 색을 그대로 쓴다(사용자 지적: 레퍼런스의 자막 말투 · 위치까지 맞추기).
최종 화면(compositions/<id>/scene.js)도 같은 부품(K.talk.gram)을 쓴다 — 미리 보기와 결과가 어긋나지 않게.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XR = ROOT / "public" / "trends" / "xray"


def _spec(c: dict) -> dict:
    """자막 항목 하나 → 그릴 값(y 가운데 · 글자 높이 · 상자 여부 · 색)"""
    box = "흰 상자" in c.get("style", "")
    return {"y": c["y"], "h": c["h"], "box": box, "bg": c.get("bg") if box else None, "fg": c.get("fg") or "#f0f0f0"}


def grammar(xid: str) -> dict:
    st = json.loads((XR / xid / "style" / "style.json").read_text(encoding="utf-8"))
    dur = st.get("duration") or 1
    items = st["captions"]["items"]
    long_ = [c for c in items if (c["end"] - c["start"]) >= dur * 0.8]
    short = [c for c in items if (c["end"] - c["start"]) < dur * 0.8]
    # 채널 워터마크: 작은 글씨(h<0.03)로 위에서 계속 바뀌며 나오는 것 — 우리 영상엔 쓰지 않는다
    short = [c for c in short if c["h"] >= 0.03]
    g: dict = {"from": xid}
    tops = sorted([c for c in long_ if c["band"] == "위"], key=lambda c: c["y"])
    if tops:
        g["title"] = {**_spec(tops[0]), "lines": len(tops), "gap": round((tops[-1]["y"] - tops[0]["y"]) / max(1, len(tops) - 1), 3) if len(tops) > 1 else 0}
    bots = [c for c in long_ if c["band"] == "아래"]
    if bots:
        g["punch"] = _spec(bots[0])
    tags = [c for c in short if c["style"].startswith("괄호") and c["band"] == "위"]
    if tags:
        t = sorted(tags, key=lambda c: c["start"])[0]
        g["tag"] = {**_spec(t), "align": "left"}
    thoughts = [c for c in short if c["style"].startswith("괄호") and c["band"] == "가운데"]
    if thoughts:
        g["thought"] = _spec(thoughts[0])
    subs = [c for c in short if c["band"] == "아래" and not c["style"].startswith("괄호")]
    if subs:
        ys = sorted(c["y"] for c in subs)
        hs = sorted(c["h"] for c in subs)
        g["subs"] = {**_spec(subs[len(subs) // 2]), "y": ys[len(ys) // 2], "h": hs[len(hs) // 2], "box": False}
    # 영상 칸: 촬영 카드의 영상 비율로 높이, 제목 아래와 펀치라인 위 사이 가운데
    cp = XR / xid / "style" / "capture.json"
    aspect = json.loads(cp.read_text(encoding="utf-8")).get("aspect") if cp.exists() else None
    if aspect:
        h = min(0.9, 1080 / aspect / 1920)
        top = (g["title"]["y"] + (g["title"]["lines"] - 1) * g["title"].get("gap", 0) + g["title"]["h"] / 2) if "title" in g else 0.2
        bot = (g["punch"]["y"] - g["punch"]["h"] / 2) if "punch" in g else 0.8
        mid = (top + bot) / 2
        g["content"] = {"y0": round(max(0.0, mid - h / 2), 3), "y1": round(min(1.0, mid + h / 2), 3)}
    g["background"] = (st.get("layout") or {}).get("background") or "#000000"
    return g


def cmd_grammar(a):
    p = Path(a.storyboard)
    sb = json.loads(p.read_text(encoding="utf-8"))
    refs = sb.get("reference") or []
    if not refs:
        sys.exit("콘티에 reference(참고 쇼츠 id)가 없습니다 — 화면 문법은 참고 쇼츠에서 잰다")
    sb["grammar"] = grammar(str(refs[0]))
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(sb["grammar"], ensure_ascii=False, indent=1))


def cmd_render(a):
    p = Path(a.storyboard)
    sb = json.loads(p.read_text(encoding="utf-8"))
    if not (ROOT / "public" / "audio" / f"{sb['id']}.wav").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "assemble_audio.py"), str(p)], check=True)
    env = {**os.environ, "FLUMA_PREVIZ": "1"}
    out = ROOT / "out" / f"{sb['id']}-previz.mp4"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "render.py"), str(p), "--draft", "--size", "720", "--out", str(out)], env=env)
    if r.returncode == 0:
        print(f"[미리 보기] {out.relative_to(ROOT)}")
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grammar"); g.add_argument("storyboard")
    r = sub.add_parser("render"); r.add_argument("storyboard")
    a = ap.parse_args()
    {"grammar": cmd_grammar, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    main()
