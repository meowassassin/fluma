#!/usr/bin/env python3
"""영상마다 직접 짠 Blender 3D 스크립트 실행 (정해진 템플릿이 아니라 그 영상만의 3D).

  python3 scripts/blender_run.py <영상 id> <스크립트> --name <요소 이름> [--sec 3] [--size 1080x1080] [--opaque] [--draft]
  python3 scripts/blender_run.py <영상 id> <스크립트> --still 0.4,1.5,2.8 [--size …]     # 빠른 확인: 정지 화면만 → 경로 출력 (Read 로 보기)
  python3 scripts/blender_run.py --check <스크립트>                                     # 검사만

<스크립트> = compositions/<영상 id>/blender/<이름>.py (그 폴더 안만). 같은 폴더의 다른 .py 를 import 해 부품을 나눠도 되고,
assets/ 에 둔 텍스처 · glb 모델은 ctx.assets 로 찾는다. 도구 모음: engines/blender/lib/fluma3d.py (import fluma3d as F)

결과(요소): public/elements/<id>/<이름>/f0001.png … + meta.json(투명 배경 · 보이는 영역 bbox) → scene.js 의 K.seq 로 얹음.
권한: 스크립트는 검사(프로세스 · 네트워크 · 삭제 · 비밀 파일 금지)를 통과해야 실행되고, Blender 안에서도 감사 훅이 같은 것을 막음.
쓰기는 출력 폴더와 compositions/<id>/blender/ 아래만.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engines" / "blender"))
sys.path.insert(0, str(ROOT / "engines" / "blender" / "lib"))
sys.path.insert(0, str(ROOT / "scripts"))
from adapter import BIN  # noqa: E402
import host  # noqa: E402


def palette(sb_id: str) -> dict:
    """콘티의 디자인 방향 색 → 룩 색 순서 (scene 들과 같은 팔레트)"""
    try:
        from engines import look_tokens
        sbp = ROOT / "storyboards" / f"{sb_id}.json"
        sb = json.loads(sbp.read_text(encoding="utf-8")) if sbp.exists() else {}
        col = dict(look_tokens(sb)["color"])
        col.update({k[6:]: v for k, v in (sb.get("direction") or {}).items() if k.startswith("color_") and isinstance(v, str)})
        return col
    except Exception:  # noqa: BLE001
        return {"bg": "#0B0D14", "surface": "#161A24", "text": "#F5F5F7", "muted": "#8A8F9C", "accent": "#FF5A78"}


def resolve_script(sb_id: str, script: str) -> Path:
    base = (ROOT / "compositions" / sb_id / "blender").resolve()
    p = Path(script)
    p = (p if p.is_absolute() else (ROOT / p)).resolve()
    if not p.exists() and (base / script).exists():
        p = (base / script).resolve()
    if base not in p.parents or p.suffix != ".py":
        sys.exit(f"스크립트는 compositions/{sb_id}/blender/ 안의 .py 여야 합니다: {script}")
    if not p.exists():
        sys.exit(f"없음: {p.relative_to(ROOT)}")
    return p


def alpha_bbox(frames: list[Path]) -> list | None:
    """모든 프레임에서 보이는(알파>8) 영역을 합친 상자 [x0,y0,x1,y1] (요소 이미지 픽셀). 겹침 검사가 이걸 쓴다."""
    try:
        from PIL import Image
    except ImportError:
        return None
    box = None
    for f in frames[:: max(1, len(frames) // 24)] + frames[-1:]:
        im = Image.open(f)
        if im.mode != "RGBA":
            return None
        b = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        if b:
            box = list(b) if not box else [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
    return box


def lint_all(p: Path):
    bad = []
    for f in sorted(p.parent.glob("*.py")):
        bad += [f"{f.name}:{m}" for m in host.lint(f)] if f == p else [f"{f.name}:{m}" for m in host.lint(f) if "def build" not in m]
    if bad:
        sys.exit("스크립트 검사에서 막힘 — 고친 뒤 다시 실행하세요:\n  " + "\n  ".join(bad))


def run_blender(script: Path, out: Path, ctx: dict, stills: str = "", pad: int = 4, timeout: int = 3600):
    if not BIN.exists():
        sys.exit("Blender 없음 — 설정 → 렌더 엔진 → Blender 설치")
    lint_all(script)
    host.prefetch(script)
    env = host.env({"FL_SCRIPT": script, "FL_OUT": out, "FL_CTX": json.dumps(ctx, ensure_ascii=False), "FL_STILLS": stills, "FL_PAD": pad})
    r = subprocess.run([str(BIN), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "1", "-P", str(host.LIB / "runner.py")],
                       env=env, capture_output=True, text=True, timeout=timeout, cwd=str(script.parent))
    log = r.stdout + r.stderr
    if r.returncode != 0:
        tb = log[log.rfind("Traceback"):] if "Traceback" in log else log[-1500:]
        sys.exit(f"Blender 스크립트 실패:\n{tb[-2000:]}")
    return log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id", nargs="?")
    ap.add_argument("script", nargs="?")
    ap.add_argument("--name")
    ap.add_argument("--still", default="")
    ap.add_argument("--sec", type=float, default=3.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1080x1080")
    ap.add_argument("--opaque", action="store_true", help="투명 대신 배경까지 그림 (화면 전체를 3D 로 덮을 때)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--arg", action="append", default=[], help="key=value → ctx.args (스크립트 하나를 여러 요소에 재사용)")
    ap.add_argument("--check")
    a = ap.parse_args()
    if a.check:
        bad = host.lint(Path(a.check))
        print("통과" if not bad else "막힘:\n  " + "\n  ".join(bad))
        sys.exit(1 if bad else 0)
    if not a.id or not a.script:
        ap.error("<영상 id> <스크립트> 가 필요합니다")
    if not a.still and not a.name:
        ap.error("--name <요소 이름> 또는 --still <초,초> 가 필요합니다")
    if a.name and not all(ch.isalnum() or ch in "-_" for ch in a.name):
        sys.exit("이름은 영문 · 숫자 · - _ 만")
    script = resolve_script(a.id, a.script)
    w, h = (int(x) for x in a.size.lower().split("x"))
    work = ROOT / "compositions" / a.id / "blender"
    assets = work / "assets"
    ctx = {"id": a.id, "w": w, "h": h, "fps": a.fps, "sec": a.sec, "transparent": not a.opaque, "draft": a.draft or bool(a.still),
           "colors": palette(a.id), "fonts": str(ROOT / "public" / "fonts"), "assets": str(assets), "work": str(work),
           "args": dict(kv.split("=", 1) for kv in a.arg if "=" in kv)}
    t0 = time.time()
    if a.still:
        out = ROOT / "workspace" / "tmp" / "blender" / a.id / (a.name or script.stem)
        shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
        run_blender(script, out, ctx, stills=a.still)
        for p in sorted(out.glob("s*.png")):
            print(p.relative_to(ROOT))
        print(f"[3D 확인] {len(a.still.split(','))} 장 · {time.time() - t0:.0f}초 — Read 로 열어 보고, 좋으면 --name 으로 본 렌더")
        return
    if a.fps != 30 or a.draft:
        print(f"[주의] 본 렌더인데 fps {a.fps}{' · 초안 품질' if a.draft else ''} — 영상(30fps)과 다르면 프레임이 반복돼 끊겨 보입니다. 확인용이면 --still 을 쓰세요", flush=True)
    out = ROOT / "public" / "elements" / a.id / a.name
    tmp = out.with_name(out.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    run_blender(script, tmp, ctx)
    frames = sorted(tmp.glob("f*.png"))
    if not frames:
        sys.exit("프레임이 나오지 않았습니다")
    bbox = alpha_bbox(frames) if not a.opaque else [0, 0, w, h]
    meta = {"frames": len(frames), "fps": a.fps, "ext": "png", "pad": 4, "w": w, "h": h, "size": max(w, h), "bbox": bbox,
            "script": str(script.relative_to(ROOT)), "transparent": not a.opaque}
    ap_ = tmp / "anchors.json"
    if ap_.exists():   # 3D 고정점: {이름: [[x, y, 보임], …프레임마다]} (요소 이미지 픽셀)
        meta["anchors"] = json.loads(ap_.read_text(encoding="utf-8")); ap_.unlink()
    (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(out, ignore_errors=True); tmp.rename(out)
    rel = f"elements/{a.id}/{a.name}"
    print(f"[3D 요소] {rel} · {len(frames)} 프레임 · {w}x{h} · 보이는 영역 {bbox} · {time.time() - t0:.0f}초")
    sw = 760
    print(f'K.seq(c.root, "{rel}", {{ name: "{a.name}", x: {(1080 - sw) // 2}, y: 560, w: {sw}, h: {round(sw * h / w)}, at: 0 }})')
    if meta.get("anchors"):
        print(f"3D 고정점: {', '.join(meta['anchors'])} → K.seq 옵션 pins: [{{ name: \"{next(iter(meta['anchors']))}\", el: 라벨.el, dx: 0, dy: -40 }}]")
    print(f"다음: python3 scripts/overlap_check.py storyboards/{a.id}.json — 글자 · 다른 요소와 겹치는지 확인")


if __name__ == "__main__":
    main()
