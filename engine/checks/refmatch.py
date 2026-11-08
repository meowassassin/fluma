#!/usr/bin/env python3
"""레퍼런스 대조 — 레퍼런스를 따라 만든 재료는 원본 프레임과 나란히 놓고 확인해야 통과한다.
썸네일로 짐작해 만들고 비교 없이 넘어가는 일을 도구가 막는다(재료가 바뀌면 다시 확인).

재료 칸:  "ref": {"video": "<쇼츠 id>", "at": [9.3], "me": [0.5], "crop": [x, y, w, h]?}
            at = 레퍼런스 초, me = 내 재료 초(영상일 때 — 없으면 가운데), crop = 레퍼런스에서 볼 영역(0~1)

  python3 engine/checks/refmatch.py sheet <콘티> [재료 id …]          # 대조 그림 data/compositions/<id>/craft/refmatch/<재료>.png
  python3 engine/checks/refmatch.py ok <콘티> <재료 id> --diff "남은 차이 …"   # 그림을 보고 무엇이 다른지 적어 통과(재료 파일 해시와 묶인다)
  python3 engine/checks/refmatch.py show <콘티>                        # 재료마다 상태
  python3 engine/checks/refmatch.py pair <영상 id> <레퍼런스 초> <내 그림 …> [--out 파일] [--crop x,y,w,h]   # 재료 없이 바로 비교(모델링 중)

produce 결과의 D03 = ref 가 있는데 확인 안 함 · 재료가 바뀜 / 3D · 그림 재료인데 레퍼런스 콘티에 ref 없음.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

XRAY = ROOT / "data" / "public" / "trends" / "xray"
NEEDS_REF = ("model3d", "illustration", "craft")     # 그 재료가 화면의 주인공 모양일 때 — 레퍼런스 콘티면 대조 권고


def _d(sid: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "craft" / "refmatch"


def _state(sid: str) -> dict:
    f = _d(sid) / "state.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12]


def grab(video: str, t: float, out: Path, crop=None) -> Path:
    src = XRAY / video / "src.mp4"
    if not src.exists():
        raise RuntimeError(f"레퍼런스 영상이 없습니다: {video} — python3 engine/research/analyze_ref.py {video} --no-channel")
    vf = []
    if crop:
        x, y, w, h = crop
        vf = ["-vf", f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1", *vf, str(out)], check=True)
    return out


def board(left: list[Path], right: list[Path], out: Path, h: int = 900) -> Path:
    """왼쪽 레퍼런스 · 오른쪽 내 결과, 같은 높이로"""
    from PIL import Image, ImageDraw
    ims = [("REF", p) for p in left] + [("ME", p) for p in right]
    tiles = []
    for tag, p in ims:
        im = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255)); bg.alpha_composite(im)
        t = bg.convert("RGB").resize((int(im.width * h / im.height), h))
        ImageDraw.Draw(t).rectangle([0, 0, 58, 20], fill=(0, 0, 0) if tag == "REF" else (0, 110, 200))
        ImageDraw.Draw(t).text((6, 5), tag, fill=(255, 255, 255))
        tiles.append(t)
    c = Image.new("RGB", (sum(t.width for t in tiles) + 8 * (len(tiles) - 1), h), (255, 255, 255))
    x = 0
    for t in tiles:
        c.paste(t, (x, 0)); x += t.width + 8
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out)
    return out


def _mats(sb: dict):
    for n, s in enumerate(sb.get("scenes") or [], 1):
        for m in s.get("materials") or []:
            yield n, m


def _rec(sid: str, n: int, mid: str) -> dict:
    f = ROOT / "data" / "compositions" / sid / "craft" / "materials" / f"s{n:02d}" / f"{mid}.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else {}


def _frames_of(file: Path, at: list | None, d: Path, mid: str) -> list[Path]:
    if file.suffix.lower() not in (".mp4", ".mov", ".webm"):
        return [file]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(file)], capture_output=True, text=True).stdout or 2)
    out = []
    for k, t in enumerate(at or [dur / 2]):
        p = d / f".{mid}-me{k}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(file), "-frames:v", "1", str(p)], check=True)
        out.append(p)
    return out


def make(sb: dict, m: dict, n: int) -> Path | None:
    sid, r = sb["id"], m.get("ref") or {}
    rec = _rec(sid, n, m["id"])
    if not rec.get("file") or not r.get("video"):
        return None
    d = _d(sid); d.mkdir(parents=True, exist_ok=True)
    left = [grab(r["video"], t, d / f".{m['id']}-ref{k}.png", r.get("crop")) for k, t in enumerate(r.get("at") or [0])]
    right = _frames_of(ROOT / rec["file"], r.get("me"), d, m["id"])
    return board(left, right, d / f"{m['id']}.png")


def status(sb: dict) -> list[tuple[int, str, str]]:
    """(장면, 재료 id, 문제) — 문제 없으면 빈 목록"""
    sid = sb["id"]
    st = _state(sid)
    out = []
    has_ref = bool(sb.get("reference"))
    for n, m in _mats(sb):
        mid = m.get("id") or ""
        if not m.get("ref"):
            if has_ref and m.get("type") in NEEDS_REF:
                out.append((n, mid, f"레퍼런스 콘티의 {m.get('type')} 재료에 ref 없음 — 레퍼런스 영상 · 시각을 적고 대조한다"))
            continue
        rec = _rec(sid, n, mid)
        if not rec.get("file"):
            continue
        cur = _sha(ROOT / rec["file"]) if (ROOT / rec["file"]).exists() else ""
        s = st.get(mid) or {}
        if s.get("sha") != cur:
            out.append((n, mid, "레퍼런스와 나란히 확인 안 함" + (" (재료가 바뀜)" if s else "")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("sheet"); a1.add_argument("storyboard"); a1.add_argument("ids", nargs="*")
    a2 = sub.add_parser("ok"); a2.add_argument("storyboard"); a2.add_argument("id"); a2.add_argument("--diff", required=True)
    a3 = sub.add_parser("show"); a3.add_argument("storyboard")
    a4 = sub.add_parser("pair"); a4.add_argument("video"); a4.add_argument("at"); a4.add_argument("me", nargs="+"); a4.add_argument("--out"); a4.add_argument("--crop")
    a = ap.parse_args()
    if a.cmd == "pair":
        out = Path(a.out) if a.out else ROOT / "data" / "workspace" / "refmatch" / f"{a.video}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        crop = [float(x) for x in a.crop.split(",")] if a.crop else None
        left = [grab(a.video, float(t), out.with_name(f".{out.stem}-r{k}.png"), crop) for k, t in enumerate(a.at.split(","))]
        print(board(left, [Path(p) for p in a.me], out))
        return 0
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    sb = json.loads(sp.read_text("utf-8"))
    if a.cmd == "sheet":
        made = [str(p.relative_to(ROOT)) for n, m in _mats(sb) if m.get("ref") and (not a.ids or m.get("id") in a.ids) for p in [make(sb, m, n)] if p]
        ok("refmatch", sheets=made, next="그림을 Read 로 보고 차이를 고친 뒤 refmatch.py ok <콘티> <재료> --diff '남은 차이'")
    elif a.cmd == "ok":
        hit = next(((n, m) for n, m in _mats(sb) if m.get("id") == a.id and m.get("ref")), None)
        if not hit:
            fail("refmatch", stage="ok", error=f"ref 가 있는 재료 '{a.id}' 가 없습니다")
        n, m = hit
        board_f = _d(sb["id"]) / f"{a.id}.png"
        rec = _rec(sb["id"], n, a.id)
        if not board_f.exists() or not rec.get("file") or board_f.stat().st_mtime < (ROOT / rec["file"]).stat().st_mtime:
            fail("refmatch", stage="ok", error="대조 그림이 없거나 재료보다 오래됐습니다 — 먼저 sheet 로 만들어 본다")
        st = _state(sb["id"])
        st[a.id] = {"sha": _sha(ROOT / rec["file"]), "diff": a.diff}
        (_d(sb["id"]) / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), "utf-8")
        ok("refmatch", ok=a.id, diff=a.diff)
    else:
        rows = status(sb)
        for n, mid, why in rows:
            print(f"{n}장면 {mid}: {why}")
        if not rows:
            print("문제 없음")
    return 0


if __name__ == "__main__":
    from result import run_main
    run_main("refmatch", main)
