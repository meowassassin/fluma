#!/usr/bin/env python3
"""파이프라인 2단계 — 캐릭터 시트(나노 바나나) · 사용자 승인 ①.
샷 계획의 needs_character=true 일 때만. 캐릭터마다 front · back · left · right 를 **각각 개별 파일**로 만든다(스펙 2단계).

만드는 순서(조사: 정면 먼저 → 나머지는 정면을 참조로 한 장씩 [4곳 + Google 공식 '한 각도씩, 앞 그림을 다음 입력에']):
  1. front — 참조 없이(--candidates N 이면 N장 만들어 고른다)
  2. back · left · right — 확정한 front 를 Image 1 로 붙여 한 장씩(동시에 셋)
좌우는 프롬프트로 확실히 못 고친다(조사 [3]) — 어느 어깨가 카메라 쪽인지 적고, 승인 화면에서 꼭 눈으로 확인한다.

  python3 engine/gen/character.py make <plan id> <이름> [--views front|back,left,right|all] [--candidates 2] [--model flash]
  python3 engine/gen/character.py pick <plan id> <이름> <front 후보 번호>      # front 후보 중 하나를 front.png 로
  python3 engine/gen/character.py sheet <plan id> <이름>                       # 승인용 한 장(4방향 나란히)
  python3 engine/gen/character.py approve <plan id> <이름>                     # 승인 ① — 지금 파일 · 설명의 해시에 묶음
  python3 engine/gen/character.py status <plan id>                             # 캐릭터별 상태(없음 · 만듦 · 승인 · 승인 무효)
파일: data/compositions/<plan id>/characters/<이름>/{front,back,left,right}.png · sheet.json(프롬프트 · 메타 · 승인)
승인은 입력 해시에 묶인다 — 설명(identity · wardrobe · style)이나 그림이 바뀌면 자동으로 무효가 된다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402
import image as imagegen  # noqa: E402
import plan as planmod  # noqa: E402

VIEWS = ("front", "back", "left", "right")
VIEW_TEXT = {
    "front": "front view, facing the camera directly",
    "back": "back view, facing directly away from the camera so only the back of the head and body are visible",
    "left": "left side profile: the character faces screen-left, the character's LEFT shoulder is nearest the camera, feet pointing screen-left",
    "right": "right side profile: the character faces screen-right, the character's RIGHT shoulder is nearest the camera, feet pointing screen-right",
}
COMMON = ("Relaxed A-pose, arms held slightly away from the body, standing straight, head to toe fully visible including the feet, "
          "centered, the figure fills most of the frame height. Plain neutral light grey background, flat even studio lighting, no cast shadows. "
          "No text, letters, labels, captions or logos anywhere in the image.")


def cdir(pid: str, name: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "characters" / name


def char_of(sb: dict, name: str) -> dict:
    c = next((c for c in sb.get("characters") or [] if c["name"] == name), None)
    if not c:
        fail("character", stage="character", error=f"샷 계획에 캐릭터 '{name}' 이 없다")
    return c


def desc(c: dict) -> str:
    return f"{c['identity'].rstrip('.')}; wearing {c['wardrobe'].rstrip('.')}" + (f"; carrying {c['props'].rstrip('.')}" if c.get("props") else "")


def prompt_for(sb: dict, c: dict, view: str, with_ref: bool) -> str:
    head = ("Image 1 is the approved front view of this exact character. Generate the SAME character — preserve the face, hairstyle, "
            "body proportions, wardrobe, colours and art style exactly as in Image 1; change only the viewing angle. " if with_ref else "")
    return (f"{head}Full-body character reference sheet image, {VIEW_TEXT[view]}. {desc(c)}. {COMMON} "
            f"Style: {sb['style'].rstrip('.')}. Same scale and framing as a standard turnaround.")


def input_hash(sb: dict, c: dict, d: Path) -> str:
    h = hashlib.sha256((desc(c) + "|" + sb["style"]).encode())
    for v in VIEWS:
        f = d / f"{v}.png"
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()[:16]


def load_meta(d: Path) -> dict:
    p = d / "sheet.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"views": {}, "candidates": [], "approval": None}


def save_meta(d: Path, m: dict) -> None:
    (d / "sheet.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), "utf-8")


def sync_plan(pid: str, name: str, m: dict, d: Path) -> None:
    """샷 계획 characters[].sheet 에 경로 · 승인 상태를 적는다(3단계가 읽는다)"""
    p, sb = planmod.load(pid)
    for c in sb.get("characters") or []:
        if c["name"] == name:
            c["sheet"] = {v: str((d / f"{v}.png").relative_to(ROOT)) for v in VIEWS if (d / f"{v}.png").exists()}
            c["sheet"]["approved"] = bool(m.get("approval")) and m["approval"].get("hash") == input_hash(sb, c, d)
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")


def make(pid: str, name: str, views: list[str], candidates: int, model: str | None = None, backend: str | None = None) -> dict:
    _, sb = planmod.load(pid)
    if not sb.get("needs_character"):
        fail("character", stage="character", error="needs_character=false — 2단계를 건너뛰고 3단계(키 프레임)로")
    c = char_of(sb, name)
    d = cdir(pid, name); d.mkdir(parents=True, exist_ok=True)
    m = load_meta(d)
    done, errors = [], []
    if "front" in views:
        outs = [d / ("front.png" if candidates == 1 else f"front_c{i + 1}.png") for i in range(candidates)]
        pr = prompt_for(sb, c, "front", False)
        with ThreadPoolExecutor(max_workers=min(3, candidates)) as ex:
            futs = [ex.submit(imagegen.generate, o, pr, None, "9:16", model, backend) for o in outs]
            for o, f in zip(outs, futs):
                try:
                    meta = f.result(); done.append(o.name)
                    if candidates == 1:
                        m["views"]["front"] = meta
                    else:
                        m["candidates"] = [x for x in m.get("candidates") or [] if x["path"] != meta["path"]] + [meta]
                except imagegen.ImageGenError as e:
                    errors.append(f"{o.name}: {e}")
        if candidates == 1 and "front" in [x.split('.')[0] for x in done]:
            for v in ("back", "left", "right"):          # 정면이 바뀌면 나머지는 옛 정면 기준 — 다시 만들어야 한다
                if v in m["views"] and v not in views:
                    m["views"][v]["stale"] = True
    rest = [v for v in views if v != "front"]
    if rest:
        front = d / "front.png"
        if not front.exists():
            fail("character", stage="character", error="front.png 가 없다 — 먼저 front 를 만들고(후보면 pick) 나머지를 만든다")
        with ThreadPoolExecutor(max_workers=2) as ex:
            futs = {v: ex.submit(imagegen.generate, d / f"{v}.png", prompt_for(sb, c, v, True),
                                 [(front, f"approved front view of {name} — identity, wardrobe and style to preserve")], "9:16", model, backend) for v in rest}
            for v, f in futs.items():
                try:
                    m["views"][v] = f.result(); done.append(f"{v}.png")
                except imagegen.ImageGenError as e:
                    errors.append(f"{v}: {e}")
    m["approval"] = None                                  # 무엇이든 새로 만들면 승인은 풀린다
    m["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_meta(d, m)
    sync_plan(pid, name, m, d)
    warns = [f"{v}: {x['warn']}" for v, x in m["views"].items() if x.get("warn")] + [f"{v}: 옛 정면 기준 — 다시 만든다" for v, x in m["views"].items() if x.get("stale")]
    return {"made": done, "errors": errors, "warns": warns, "dir": str(d.relative_to(ROOT))}


def sheet_png(pid: str, name: str) -> Path:
    """승인용 한 장 — 4방향 나란히 + 라벨(좌우 확인 안내)"""
    from PIL import Image, ImageDraw, ImageFont
    d = cdir(pid, name)
    ims = []
    for v in VIEWS:
        f = d / f"{v}.png"
        im = Image.open(f).convert("RGB") if f.exists() else Image.new("RGB", (540, 960), (60, 60, 60))
        ims.append((v, im.resize((int(im.width * 900 / im.height), 900))))
    W = sum(i.width for _, i in ims) + 20 * (len(ims) + 1)
    sheet = Image.new("RGB", (W, 1000), (30, 30, 30)); dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf"), 34)
    except OSError:
        font = ImageFont.load_default()
    x = 20
    label = {"front": "front 정면", "back": "back 뒤", "left": "left 왼쪽 옆(왼어깨가 앞)", "right": "right 오른쪽 옆(오른어깨가 앞)"}
    for v, im in ims:
        sheet.paste(im, (x, 80)); dr.text((x + 6, 24), label[v], font=font, fill=(240, 240, 240)); x += im.width + 20
    out = d / "sheet.png"; sheet.save(out)
    return out


def status(pid: str) -> list[dict]:
    _, sb = planmod.load(pid)
    rows = []
    for c in sb.get("characters") or []:
        d = cdir(pid, c["name"]); m = load_meta(d)
        have = [v for v in VIEWS if (d / f"{v}.png").exists()]
        ap = m.get("approval")
        st = "없음" if not have else ("승인" if ap and ap.get("hash") == input_hash(sb, c, d) else ("승인 무효(입력이 바뀜)" if ap else ("만듦 · 승인 대기" if len(have) == 4 else "만드는 중")))
        rows.append({"name": c["name"], "views": have, "candidates": [Path(x["path"]).name for x in m.get("candidates") or []], "state": st})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    mk = sp.add_parser("make"); mk.add_argument("pid"); mk.add_argument("name"); mk.add_argument("--views", default="all")
    mk.add_argument("--candidates", type=int, default=1); mk.add_argument("--model", default=None)
    mk.add_argument("--backend", default=None, choices=["gflow", "agy", "mock"])
    pk = sp.add_parser("pick"); pk.add_argument("pid"); pk.add_argument("name"); pk.add_argument("n", type=int)
    for k in ("sheet", "approve"):
        x = sp.add_parser(k); x.add_argument("pid"); x.add_argument("name")
    st = sp.add_parser("status"); st.add_argument("pid")
    a = ap.parse_args()
    if a.cmd == "make":
        views = list(VIEWS) if a.views == "all" else [v.strip() for v in a.views.split(",")]
        if any(v not in VIEWS for v in views):
            fail("character", stage="character", error=f"views 는 {', '.join(VIEWS)} 중에서")
        if a.candidates > 1 and views != ["front"]:
            fail("character", stage="character", error="후보 여러 장은 front 만(--views front) — 고른 뒤 pick → back,left,right")
        if a.views == "all" and a.candidates == 1:
            r1 = make(a.pid, a.name, ["front"], 1, a.model, a.backend)          # 정면 먼저, 그다음 정면을 참조로 나머지
            if r1["errors"]:
                fail("character", stage="front", error=" / ".join(r1["errors"]))
            r = make(a.pid, a.name, ["back", "left", "right"], 1, a.model, a.backend)
            r["made"] = r1["made"] + r["made"]
        else:
            r = make(a.pid, a.name, views, a.candidates, a.model, a.backend)
        sh = sheet_png(a.pid, a.name) if not a.candidates > 1 else None
        for w in r["warns"]:
            print(f"△ {w}")
        if r["errors"]:
            fail("character", stage="make", error=" / ".join(r["errors"]), made=",".join(r["made"]))
        ok("character", made=",".join(r["made"]), sheet=str(sh.relative_to(ROOT)) if sh else "", dir=r["dir"],
           next="승인용 그림을 사용자에게 보여 주고(좌우 확인) 승인 ① 또는 재생성(--views 로 그 방향만)")
        return 0
    if a.cmd == "pick":
        d = cdir(a.pid, a.name); m = load_meta(d)
        src = d / f"front_c{a.n}.png"
        if not src.exists():
            fail("character", stage="character", error=f"후보 없음: {src.name}")
        (d / "front.png").write_bytes(src.read_bytes())
        meta = next((x for x in m.get("candidates") or [] if Path(x["path"]).name == src.name), None)
        if meta is None:                                  # 후보 기록이 없으면(생성 중 실패 · 손으로 넣은 파일) 프롬프트만이라도 남긴다
            _, sb0 = planmod.load(a.pid)
            meta = {"prompt": prompt_for(sb0, char_of(sb0, a.name), "front", False), "note": "후보 기록 없음 — 파일만 골랐다"}
        m["views"]["front"] = {**meta, "path": str(d / "front.png"), "picked_from": src.name}
        for v in ("back", "left", "right"):               # 정면이 바뀌었으니 나머지는 다시
            if v in m["views"]:
                m["views"][v]["stale"] = True
        m["approval"] = None; save_meta(d, m); _, sb = planmod.load(a.pid); sync_plan(a.pid, a.name, m, d)
        ok("character", front=str((d / "front.png").relative_to(ROOT)), next=f"character.py make {a.pid} {a.name} --views back,left,right")
        return 0
    if a.cmd == "sheet":
        ok("character", sheet=str(sheet_png(a.pid, a.name).relative_to(ROOT))); return 0
    if a.cmd == "approve":
        _, sb = planmod.load(a.pid); c = char_of(sb, a.name); d = cdir(a.pid, a.name)
        missing = [v for v in VIEWS if not (d / f"{v}.png").exists()]
        if missing:
            fail("character", stage="character", error=f"아직 없는 방향: {', '.join(missing)}")
        m = load_meta(d)
        if any(x.get("stale") for x in m["views"].values()):
            fail("character", stage="character", error="옛 정면 기준으로 만든 방향이 있다 — 다시 만든 뒤 승인")
        m["approval"] = {"status": "approved", "hash": input_hash(sb, c, d), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        save_meta(d, m); sync_plan(a.pid, a.name, m, d)
        ok("character", approved=a.name, hash=m["approval"]["hash"]); return 0
    print(json.dumps(status(a.pid), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
