#!/usr/bin/env python3
"""느낌(룩) 단계 — 영상 전체의 느낌(현실 다큐 · 몽환 · 필름 · 차가운 테크 …)을 사용자가 시안을 보고 고른다. 완전 로컬(생성 없음).
어떤 느낌을 제안할지는 에이전트(Claude)가 주제 · 레퍼런스 · 콘셉트를 보고 판단해 적는다. 코드는 칸 검사 · 시안 렌더 · 적용만.

  python3 engine/story/feel.py check <id>                 # 안 파일 검사
  python3 engine/story/feel.py preview <id>               # 시안 → data/out/feel-<id>.png(실제 자료에 안마다 색 · 질감을 입힌 줄, 맨 왼쪽은 원본 · 무료)
  python3 engine/story/feel.py pick <id> <번호|이름> <콘티.json>   # 사용자가 고른 안을 콘티 direction.feel 에 — 사용자가 고를 때만

안 파일: data/workspace/feel/<id>.json
  {"options": [{                              # 2~4안, 서로 멀리
     "name": "새벽 다큐", "why": "레퍼런스 3편이 모두 … / 콘셉트의 한 방이 …",
     "style_en": "documentary, 35mm film look", "mood_en": "quiet, intimate", "color_en": "muted teal and warm skin tones",
     "lighting_en": "soft window light, low contrast",
     "grade": {"temp": 0.1, "contrast": 1.05, "saturation": 0.85, "brightness": 0.0, "lift": 0.2, "grain": 0.3, "bloom": 0.0,
               "vignette": 0.3, "mono": false}}],
   "preview_images": ["data/public/uploads/<id>/a.jpg"]   # (선택) 시안에 쓸 그림 — 없으면 올린 그림 · 재료 · 레퍼런스 장면에서 고른다
  }
grade 범위: temp -1(차갑게)~1(따뜻하게) · contrast 0.6~1.6 · saturation 0~2 · brightness -0.3~0.3 · lift 0~1(검정 띄우기 · 필름) ·
           grain 0~1 · bloom 0~1(번짐 · 몽환) · vignette 0~1 · mono
고른 느낌은 실제 재료(영상 · 스톡 · 사진)에 같은 색 · 질감으로 입혀진다(materials.py). 그림 · 영상 생성은 2026-11-09 에 없앴다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

STORE = ROOT / "data" / "workspace" / "feel"
RANGE = {"temp": (-1, 1), "contrast": (0.6, 1.6), "saturation": (0, 2), "brightness": (-0.3, 0.3), "lift": (0, 1),
         "grain": (0, 1), "bloom": (0, 1), "vignette": (0, 1)}
TEXT = ("name", "why", "style_en", "mood_en", "color_en", "lighting_en")
IMG = (".png", ".jpg", ".jpeg", ".webp")
FEEL_TYPES = {"video", "stock", "photo", "image", "photo_grade"}     # 느낌을 입히는 실사 재료


def vf(g: dict | None) -> str:
    """grade → ffmpeg 필터(영상 · 그림 같은 식). 빈 grade 는 ''"""
    if not g:
        return ""
    f = []
    t = float(g.get("temp") or 0)
    if abs(t) > 0.01:
        f.append(f"colortemperature=temperature={6500 - t * 2500:.0f}:mix=0.85")
    c, s, b = float(g.get("contrast", 1) or 1), float(g.get("saturation", 1) if g.get("saturation") is not None else 1), float(g.get("brightness") or 0)
    if abs(c - 1) > 0.01 or abs(s - 1) > 0.01 or abs(b) > 0.005:
        f.append(f"eq=contrast={c:.3f}:saturation={s:.3f}:brightness={b:.3f}")
    lift = float(g.get("lift") or 0)
    if lift > 0.01:
        lo, hi = lift * 0.16, 1 - lift * 0.06
        f.append(f"curves=all='0/{lo:.3f} 1/{hi:.3f}'")
    if g.get("mono"):
        f.append("hue=s=0")
    bloom = float(g.get("bloom") or 0)
    if bloom > 0.01:
        f.append(f"split[a][b];[b]gblur=sigma={6 + bloom * 24:.1f}[g];[a][g]blend=all_mode=screen:all_opacity={0.15 + bloom * 0.45:.2f}")
    v = float(g.get("vignette") or 0)
    if v > 0.01:
        f.append(f"vignette=angle={0.25 + v * 0.55:.3f}")
    gr = float(g.get("grain") or 0)
    if gr > 0.01:
        f.append(f"noise=alls={gr * 22:.0f}:allf=t")
    return ",".join(f)


def apply(src: Path, g: dict, dst: Path) -> Path:
    """그림 · 영상 한 개에 느낌을 입힌다(소리는 그대로)"""
    chain = vf(g)
    if not chain:
        return src
    video = src.suffix.lower() not in IMG
    args = ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", f"[0:v]{chain},format=yuv420p" if video else f"[0:v]{chain}"]
    args += (["-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18"] if video else ["-frames:v", "1"]) + [str(dst)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"느낌 입히기 실패({src.name}): {r.stderr[-300:]}")
    return dst


def check(d: dict) -> tuple[list, list]:
    bad, note = [], []
    ops = d.get("options") or []
    if not 2 <= len(ops) <= 4:
        bad.append(f"안은 2~4개 — 지금 {len(ops)}개")
    names = set()
    for o in ops:
        n = o.get("name") or "?"
        for k in TEXT:
            if not str(o.get(k) or "").strip():
                bad.append(f"{n}: {k} 가 비었음")
        if n in names:
            bad.append(f"이름 '{n}' 이 겹침")
        names.add(n)
        g = o.get("grade")
        if not isinstance(g, dict):
            bad.append(f"{n}: grade 가 없음")
            continue
        for k, (lo, hi) in RANGE.items():
            if k in g and not lo <= float(g[k]) <= hi:
                bad.append(f"{n}: grade.{k}={g[k]} 가 범위({lo}~{hi}) 밖")
    gs = [json.dumps(o.get("grade"), sort_keys=True) for o in ops]
    if len(set(gs)) < len(gs):
        bad.append("grade 가 같은 안이 있음 — 안끼리 눈으로 구별되게")
    return bad, note


def _load(fid: str) -> dict:
    f = STORE / f"{fid}.json"
    if not f.exists():
        fail("feel", stage="feel", error=f"안 파일이 없습니다: {f.relative_to(ROOT)}")
    return json.loads(f.read_text("utf-8"))


VID = (".mp4", ".mov", ".webm", ".mkv")


def _frame(v: Path, td: Path) -> Path | None:
    """영상의 40% 지점 한 장"""
    try:
        from craft import vclip
        dur = vclip.probe(v)["dur"] or 1
    except Exception:  # noqa: BLE001
        dur = 1
    out = td / f"{abs(hash(str(v)))}.png"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur * 0.4:.2f}", "-i", str(v), "-frames:v", "1", str(out)], capture_output=True)
    return out if r.returncode == 0 and out.exists() else None


def preview_sources(fid: str, d: dict, td: Path, n: int = 3) -> list[Path]:
    """시안 그림: 지정한 것 → 올린 그림 · 영상(키프레임 등) → 이 영상의 재료(사진 · 클립) → 마지막으로 레퍼런스 쇼츠 장면(글자가 얹혀 있을 수 있음)"""
    got: list[Path] = [ROOT / s for s in d.get("preview_images") or [] if (ROOT / s).exists()]
    own = []
    up = ROOT / "data" / "public" / "uploads" / fid
    if up.exists():
        own += sorted((f for f in up.iterdir() if f.suffix.lower() in IMG + VID), key=lambda f: f.stat().st_mtime)
    for base in (ROOT / "data" / "public" / "elements" / fid, ROOT / "data" / "compositions" / fid / "materials"):
        if base.exists():
            own += sorted(f for f in base.rglob("*") if f.is_file() and (f.suffix.lower() in VID and "_h" not in f.stem
                                                                        or f.suffix.lower() in (".jpg", ".jpeg") or (f.suffix.lower() == ".png" and "thumb" not in f.name)))
    sbf = ROOT / "data" / "storyboards" / f"{fid}.json"
    if sbf.exists():
        sb = json.loads(sbf.read_text("utf-8"))
        for sc in sb.get("scenes") or []:                 # 콘티 재료가 가리키는 원본(퍼온 클립 · 사진)
            for m in sc.get("materials") or []:
                q = ROOT / str(m.get("src") or "") if isinstance(m, dict) and m.get("src") else None
                if q and q.is_file() and q.suffix.lower() in IMG + VID:
                    own.append(q)
        for rid in sb.get("reference") or []:
            shots = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "shots"
            if shots.exists():
                fs = sorted(shots.glob("*.jpg"))
                own += fs[len(fs) // 3: len(fs) // 3 + 1] + fs[2 * len(fs) // 3: 2 * len(fs) // 3 + 1]
    seen, out = set(), []
    for p in got + own:
        if p.resolve() in seen:
            continue
        seen.add(p.resolve())
        q = _frame(p, td) if p.suffix.lower() in VID else p
        if q:
            out.append(q)
        if len(out) >= n:
            break
    return out


def preview(fid: str, d: dict) -> Path:
    """같은 실제 자료에 안마다 느낌(색 · 질감)을 입힌 시트 — 맨 왼쪽은 원본(무료 · 로컬)"""
    from PIL import Image, ImageDraw, ImageFont
    td_ = tempfile.TemporaryDirectory()
    srcs = preview_sources(fid, d, Path(td_.name))
    if not srcs:
        fail("feel", stage="feel", error="시안에 쓸 그림이 없습니다 — 레퍼런스 X-ray 를 하거나, 장면 사진을 올리거나, preview_images 를 적으세요")
    ops = d["options"]
    W, H, pad, head = 270, 480, 12, 70
    cols = 1 + len(ops)
    sheet = Image.new("RGB", (pad + cols * (W + pad), head + len(srcs) * (H + pad) + pad), (18, 18, 22))
    dr = ImageDraw.Draw(sheet)
    font = None
    for fp in (ROOT / "engine" / "assets" / "fonts").glob("Pretendard-Bold*"):
        font = ImageFont.truetype(str(fp), 24)
        break
    font = font or ImageFont.load_default()
    small = ImageFont.truetype(font.path, 15) if hasattr(font, "path") else font
    labels = [("원본", "")] + [(f"{i + 1}. {o['name']}", o.get("style_en", "")[:34]) for i, o in enumerate(ops)]
    for c, (t, sub) in enumerate(labels):
        x = pad + c * (W + pad)
        dr.text((x, 14), t, fill=(240, 240, 240), font=font)
        dr.text((x, 44), sub, fill=(150, 150, 160), font=small)
    top = 0
    with tempfile.TemporaryDirectory() as td:
        for r, src in enumerate(srcs):
            base = Path(td) / f"s{r}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-frames:v", "1", "-vf",
                            f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2}", str(base)], check=True)
            for c in range(cols):
                img = base if c == 0 else apply(base, ops[c - 1]["grade"], Path(td) / f"s{r}-{c}.png")
                with Image.open(img) as im:
                    sheet.paste(im.convert("RGB").resize((W, H)), (pad + c * (W + pad), head + (r + top) * (H + pad)))
    td_.cleanup()
    out = ROOT / "data" / "out" / f"feel-{fid}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("id")
    sub.add_parser("preview").add_argument("id")
    p = sub.add_parser("pick"); p.add_argument("id"); p.add_argument("which"); p.add_argument("storyboard")
    a = ap.parse_args()
    d = _load(a.id)
    bad, note = check(d)
    if bad:
        fail("feel", stage="feel", error=" / ".join(bad[:12]), notes=note)
    if a.cmd == "check":
        ok("feel", options=len(d["options"]), notes=note)
        return 0
    if a.cmd == "preview":
        out = preview(a.id, d)
        ok("feel", sheet=out.relative_to(ROOT).as_posix(), options=[o["name"] for o in d["options"]], media=[f"{out.relative_to(ROOT).as_posix()} | 느낌 시안"])
        return 0
    ops = d["options"]
    o = ops[int(a.which) - 1] if a.which.isdigit() and 1 <= int(a.which) <= len(ops) else next((x for x in ops if x.get("name") == a.which), None)
    if not o:
        fail("feel", stage="feel", error=f"그런 안이 없습니다: {a.which}")
    sp = Path(a.storyboard)
    sp = sp if sp.is_absolute() else ROOT / sp
    sb = json.loads(sp.read_text("utf-8"))
    dr = sb.setdefault("direction", {})
    dr["feel"] = {k: o.get(k) for k in (*TEXT, "grade")}
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    ok("feel", picked=o["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
