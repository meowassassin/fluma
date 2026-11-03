#!/usr/bin/env python3
"""Blender 로 3D 요소를 만들어 컴포지션에 얹는다 (투명 배경 PNG 연속 이미지).

  python3 scripts/blender_element.py <영상 id> <이름> --kind text|number|badge|orb|cube|svg [--text "1,600"] [--color "#FF5A78"]
          [--sec 3] [--size 720] [--svg logo.svg] [--no-spin] [--draft]

결과: public/elements/<id>/<이름>/f0001.png … + meta.json → scene.js 에서
  K.seq(c.root, "elements/<id>/<이름>", { x, y, w: 600, h: 600, at: 0.2, loop: false })
색을 안 주면 콘티의 디자인 방향 강조색(direction.color_accent) → 룩 강조색 순으로 쓴다.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engines" / "blender"))
sys.path.insert(0, str(ROOT / "scripts"))
from adapter import BIN  # noqa: E402  (OS 마다 위치가 다름)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id"); ap.add_argument("name")
    ap.add_argument("--kind", default="text", choices=["text", "number", "badge", "orb", "cube", "svg"])
    ap.add_argument("--text", default="")
    ap.add_argument("--color")
    ap.add_argument("--sec", type=float, default=3.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", type=int, default=720)
    ap.add_argument("--svg")
    ap.add_argument("--no-spin", action="store_true")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    if not BIN.exists():
        sys.exit("Blender 없음: engines/blender/dist/blender (설정 → 렌더 엔진)")
    if not all(ch.isalnum() or ch in "-_" for ch in a.name):
        sys.exit("이름은 영문 · 숫자 · - _ 만")
    color = a.color
    if not color:
        sbp = ROOT / "storyboards" / f"{a.id}.json"
        sb = json.loads(sbp.read_text(encoding="utf-8")) if sbp.exists() else {}
        color = (sb.get("direction") or {}).get("color_accent") or "#FF5A78"
    out = ROOT / "public" / "elements" / a.id / a.name
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    env = {**os.environ, "SF_OUT": str(out), "SF_KIND": a.kind, "SF_TEXT": a.text or a.name, "SF_COLOR": color, "SF_SEC": str(a.sec),
           "SF_FPS": str(a.fps), "SF_SIZE": str(a.size), "SF_SPIN": "0" if a.no_spin else "1", "SF_QUALITY": "draft" if a.draft else "final",
           "SF_FONTS": str(ROOT / "public" / "fonts"), "SF_SVG": str(Path(a.svg).resolve()) if a.svg else ""}
    r = subprocess.run([str(BIN), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "1", "-P", str(ROOT / "engines" / "blender" / "element.py")],
                       env=env, capture_output=True, text=True, timeout=3600)
    frames = sorted(out.glob("f*.png"))
    if r.returncode != 0 or not frames:
        sys.exit(f"Blender 실패:\n{(r.stdout + r.stderr)[-1500:]}")
    meta = {"frames": len(frames), "fps": a.fps, "ext": "png", "pad": 4, "size": a.size, "kind": a.kind, "text": a.text, "color": color}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    rel = f"elements/{a.id}/{a.name}"
    print(f"[3D 요소] {rel} · {len(frames)} 프레임 · {a.size}px")
    print(f'K.seq(c.root, "{rel}", {{ x: 240, y: 520, w: 600, h: 600, frames: {len(frames)}, fps: {a.fps}, at: 0 }})')


if __name__ == "__main__":
    main()
