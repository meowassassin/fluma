#!/usr/bin/env python3
"""여러 버전 한 번에 — 훅 · 첫 장면 · 제목만 바꾼 2~4개를 초안으로 뽑아 나란히 비교한다.

  python3 scripts/variants.py render storyboards/<id>.json [--scenes 1] [--aspect 9:16]

콘티에 적는다(바꿀 칸만, 장면 번호는 1부터):
  "variants": [
    {"name": "숫자 훅",   "scenes": {"1": {"caption": "쿼리 101번?", "narration": "…"}}},
    {"name": "질문 훅",   "title": "…", "scenes": {"1": {"materials": [ … ]}}}
  ]
버전마다 storyboards/<id>-v<k>.json 을 만들어 음성(assemble_audio) → 초안 렌더(기본: 장면 1만)를 하고,
out/<id>-variants.mp4 (나란히, 버전 이름 표시) 와 버전별 영상을 남긴다. 마지막에 채팅에 붙일 ```media 블록을 출력한다.
원본 콘티는 바꾸지 않는다 — 고른 버전을 원본에 옮기는 것은 사람이(또는 에이전트가 확인받고) 한다.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def font_file() -> str | None:
    """나란히 영상의 버전 이름(한글)에 쓸 글꼴 파일"""
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK KR:bold"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def variant_sb(sb: dict, k: int, v: dict) -> dict:
    s2 = copy.deepcopy({key: val for key, val in sb.items() if key != "variants"})
    s2["id"] = f"{sb['id']}-v{k}"
    s2["variant_of"] = {"id": sb["id"], "name": v["name"]}
    if v.get("title"):
        s2["title"] = v["title"]
    for num, patch in (v.get("scenes") or {}).items():
        i = int(num) - 1
        if not 0 <= i < len(s2["scenes"]):
            raise SystemExit(f"버전 '{v['name']}': 장면 {num} 이 없습니다")
        s2["scenes"][i] = {**s2["scenes"][i], **patch}
    return s2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("storyboard"); r.add_argument("--scenes", default="1", help="렌더할 장면(1부터, 예: 1 · 1-2 · all)"); r.add_argument("--aspect")
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads(sp.read_text("utf-8"))
    vs = sb.get("variants") or []
    if len(vs) < 1:
        sys.exit("콘티에 variants 가 없습니다 — 바꿀 칸만 적은 버전 2~4개를 먼저 넣으세요(scripts/variants.py 맨 위 설명)")
    # 원본도 비교에 넣는다(버전 0)
    items = [("원본", sb)] + [(v["name"], variant_sb(sb, k + 1, v)) for k, v in enumerate(vs)]
    outs: list[tuple[str, Path]] = []
    for name, s2 in items:
        p2 = ROOT / "storyboards" / f"{s2['id']}.json"
        if s2 is not sb:
            p2.write_text(json.dumps(s2, ensure_ascii=False, indent=1), "utf-8")
        out = ROOT / "out" / f"{sb['id']}-variant-{len(outs)}.mp4"
        print(f"[버전] {len(outs)}. {name} — 음성 · 초안 렌더", flush=True)
        au = subprocess.run([PY, str(ROOT / "scripts" / "assemble_audio.py"), str(p2)], cwd=ROOT, capture_output=True, text=True)
        if au.returncode != 0:
            print(f"  ✗ 음성 실패: {au.stderr.strip()[-300:]}", file=sys.stderr)
            continue
        cmd = [PY, str(ROOT / "scripts" / "render.py"), str(p2), "--draft", "--out", str(out)]
        if a.scenes != "all":
            cmd += ["--scenes", a.scenes]
        if a.aspect:
            cmd += ["--aspect", a.aspect]
        rr = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if rr.returncode != 0 or not out.exists():
            print(f"  ✗ 렌더 실패: {(rr.stderr or rr.stdout).strip()[-300:]}", file=sys.stderr)
            continue
        outs.append((name, out))
    if len(outs) < 2:
        sys.exit("비교할 버전이 2개 미만입니다(위 오류 참고)")
    # 나란히: 버전마다 폭 360 으로 줄이고 위에 이름 — 소리는 원본 것(버전마다 들어 보려면 버전별 영상을)
    fnt = font_file()
    ins, fl = [], []
    for i, (name, p) in enumerate(outs):
        ins += ["-i", str(p)]
        label = name.replace("'", "’").replace(":", "∶")
        txt = f",drawtext=fontfile='{fnt}':text='{i}. {label}':fontsize=26:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-tw)/2:y=h-th-24" if fnt else ""   # 아래에(위쪽 제목 · 훅을 가리지 않게)
        fl.append(f"[{i}:v]scale=360:-2,setsar=1{txt}[v{i}]")
    fl.append("".join(f"[v{i}]" for i in range(len(outs))) + f"hstack=inputs={len(outs)}:shortest=1[out]")
    cmp_ = ROOT / "out" / f"{sb['id']}-variants.mp4"
    q = subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fl), "-map", "[out]", "-map", "0:a?", "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", str(cmp_)], capture_output=True, text=True)
    if q.returncode != 0:
        print(f"✗ 나란히 영상 실패: {q.stderr[-300:]}", file=sys.stderr)
    media = ([f"{cmp_.relative_to(ROOT)} | 나란히 비교"] if cmp_.exists() else []) + [f"{p.relative_to(ROOT)} | {i}. {name}" for i, (name, p) in enumerate(outs)]
    from result import ok
    ok("variants", file=str(cmp_.relative_to(ROOT)) if cmp_.exists() else None, media=media)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts"))
    from result import run_main
    run_main("variants", main)
