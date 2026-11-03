#!/usr/bin/env python3
"""그리기 엔진 — 형태(form.json)를 풀어 그린다. 에이전트는 좌표가 아니라 부품 · 관계 · 비율만 쓴다.

  python3 scripts/draw.py check  <form.json>               # 풀 수 있는지 · 의미로 된 오류 · 경고
  python3 scripts/draw.py render <form.json> --out x.svg [--png x.png] [--view 3/4] [--facing left]

형태 문법은 scripts/drawlib/form.py 맨 위 설명, 설계는 볼트 '그리기 엔진 설계 — 구조로 그리기'.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drawlib import render  # noqa: E402
from drawlib.form import SolveError, solve  # noqa: E402
from drawlib.lint import lint  # noqa: E402


def load(p: str) -> dict:
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"형태 파일을 읽지 못했습니다: {e}")


def to_png(svg_path: Path, png: Path, width: int = 800) -> bool:
    ink = shutil.which("inkscape")
    if ink:
        r = subprocess.run([ink, str(svg_path), "-o", str(png), "-w", str(width), "-b", "#ffffff"], capture_output=True)
        return r.returncode == 0
    try:   # 인크스케이프가 없으면 Playwright(크롬)로
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": width})
            pg.set_content(f'<body style="margin:0;background:#fff"><img src="file://{svg_path.resolve()}" style="width:{width}px"></body>')
            pg.wait_for_timeout(200)
            pg.locator("img").screenshot(path=str(png))
            b.close()
        return True
    except Exception:
        return False


def sheet(svg_path: Path, out: Path, bg: str, ref: str | None) -> Path:
    """비평용 한 장: 배경 위 컬러 · 실루엣 · 흑백 명도 · 엄지손톱 · 레퍼런스(있으면). 비평 고리가 이 한 장을 보고 점수를 매긴다"""
    from PIL import Image, ImageOps
    tmp = out.with_suffix(".src.png")
    ink = shutil.which("inkscape")
    subprocess.run([ink, str(svg_path), "-o", str(tmp), "-w", "600", "-b", bg], capture_output=True, check=True)
    col = Image.open(tmp).convert("RGB")
    subprocess.run([ink, str(svg_path), "-o", str(tmp), "-w", "600"], capture_output=True, check=True)
    al = Image.open(tmp).convert("RGBA").split()[-1]
    sil = Image.new("RGB", col.size, "white"); sil.paste((0, 0, 0), mask=al)
    gray = ImageOps.grayscale(col).convert("RGB")
    th = col.copy(); th.thumbnail((48, 48)); th = th.resize((th.width * 4, th.height * 4), Image.NEAREST)
    tiles = [col, sil, gray, th]
    if ref:
        src = Path(__file__).resolve().parents[1] / "public" / "trends" / "xray" / ref / "src.mp4"
        for t in (6, 20):
            f = out.with_suffix(f".ref{t}.png")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1", "-vf", "scale=-1:600", str(f)], check=False)
            if f.exists():
                tiles.append(Image.open(f).convert("RGB"))
    H = max(t.height for t in tiles)
    canvas = Image.new("RGB", (sum(t.width for t in tiles) + 10 * len(tiles), H), "#202020")
    x = 0
    for t in tiles:
        canvas.paste(t, (x, (H - t.height) // 2)); x += t.width + 10
    canvas.save(out)
    tmp.unlink(missing_ok=True)
    return out


DIMS = ("style", "silhouette", "appeal", "detail", "value")


def critique(a, form: dict, placed, st, findings: list[dict], warns: list[str]) -> None:
    """비평 고리 한 회. --score 없이: 그리고 비평 재료를 낸다. --score 로: 채운 평가지를 기록하고 멈춤 여부를 알려 준다"""
    fp = Path(a.form)
    base = fp.with_name(fp.name.replace(".form.json", ""))
    log = base.with_suffix(".critique.jsonl")
    hist = [json.loads(x) for x in log.read_text("utf-8").splitlines() if x.strip()] if log.exists() else []
    if a.score:
        sc = load(a.score)
        missing = [d for d in DIMS if not isinstance((sc.get("scores") or {}).get(d), (int, float))]
        if missing or not sc.get("evidence"):
            print(json.dumps({"ok": False, "problem": f"점수 · 근거가 빠졌습니다: {', '.join(missing) or 'evidence'}"}, ensure_ascii=False))
            sys.exit(2)
        rec = {"round": len(hist) + 1, "scores": sc["scores"], "lint": [f["code"] for f in findings], "fix": sc.get("fix", []), "changes": sc.get("changes", [])}
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        low = [d for d in DIMS if sc["scores"][d] < 7]
        done = not low and not findings
        print(json.dumps({"ok": True, "round": rec["round"], "done": done, "stop": done or rec["round"] >= 3,
                          "low": low, "history": [{"round": h["round"], **h["scores"]} for h in hist + [rec]]}, ensure_ascii=False, indent=1))
        return
    svg = base.with_suffix(".critique.svg")
    svg.write_text(render.svg(placed, palette=form.get("palette"), style=st), "utf-8")
    bg = a.bg or (st or {}).get("bg") or "#ffffff"
    sh = sheet(svg, base.with_suffix(".critique.png"), bg, a.ref)
    nums = None
    if a.ref:
        col = base.with_suffix(".critique.col.png")
        subprocess.run([shutil.which("inkscape"), str(svg), "-o", str(col), "-h", "1600", "-b", bg], capture_output=True)
        r = subprocess.run([sys.executable, str(Path(__file__).with_name("style_match.py")), a.ref, str(col)], capture_output=True, text=True)
        try:
            nums = json.loads(r.stdout)["frames"][0]
        except (json.JSONDecodeError, KeyError, IndexError):
            nums = None
    blank = base.with_suffix(".critique.todo.json")
    blank.write_text(json.dumps({"scores": {d: None for d in DIMS}, "evidence": {d: "" for d in DIMS}, "keep": [], "fix": [], "quick": [], "changes": []},
                                ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({"ok": True, "round": len(hist) + 1, "sheet": str(sh), "lint": findings, "warnings": warns, "style_match": nums,
                      "todo": str(blank), "rubric": "rules/illustration/critique.md",
                      "next": "비평용 한 장을 보고 평가지를 채운 뒤: draw.py critique <form> --score <평가지>"}, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("form"); c.add_argument("--style"); c.add_argument("--bg", help="배경색(명도 대비 검사)")
    k = sub.add_parser("critique", help="비평 고리 한 회: 그리기 + 비평용 한 장 + lint + 숫자 + 빈 평가지(rules/illustration/critique.md)")
    k.add_argument("form"); k.add_argument("--style"); k.add_argument("--bg"); k.add_argument("--ref")
    k.add_argument("--score", help="채운 평가지 JSON 을 기록에 붙인다(회차 마감)")
    r = sub.add_parser("render"); r.add_argument("form"); r.add_argument("--out", required=True); r.add_argument("--png")
    r.add_argument("--view"); r.add_argument("--facing")
    r.add_argument("--style", help="화풍 카드 style.json, 또는 프리셋 이름(flat-bright · flat-minimal · doodle)")
    r.add_argument("--force", action="store_true", help="P0 lint 가 있어도 그린다(엔진 개발용)")
    r.add_argument("--sheet", help="비평용 한 장 PNG(컬러 · 실루엣 · 흑백 · 엄지손톱 · 레퍼런스)")
    r.add_argument("--bg", help="배경색")
    r.add_argument("--ref", help="비평 한 장에 나란히 놓을 참고 영상 id")
    a = ap.parse_args()

    form = load(a.form)
    if getattr(a, "view", None):
        form["view"] = a.view
    if getattr(a, "facing", None):
        form["facing"] = a.facing
    try:
        placed, warns = solve(form)
    except SolveError as e:
        print(json.dumps({"ok": False, "problems": e.problems}, ensure_ascii=False, indent=1))
        sys.exit(2)
    st = None
    if getattr(a, "style", None):
        st = load(a.style) if a.style.endswith(".json") else {"preset": a.style}
    findings = [f.as_dict() for f in lint(placed, form, st, bg=getattr(a, "bg", None))]
    blocked = [f for f in findings if f["level"] == "P0"]
    if a.cmd == "critique":
        critique(a, form, placed, st, findings, warns)
        return
    if a.cmd == "check":
        print(json.dumps({"ok": not blocked, "parts": len(placed), "warnings": warns, "lint": findings}, ensure_ascii=False, indent=1))
        sys.exit(2 if blocked else 0)
    if blocked and not a.force:
        print(json.dumps({"ok": False, "refused": "그림 lint P0 — 고친 뒤 다시", "lint": findings}, ensure_ascii=False, indent=1))
        sys.exit(2)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render.svg(placed, palette=form.get("palette"), style=st), "utf-8")
    msg = {"ok": True, "svg": str(out), "warnings": warns, "lint": findings}
    if a.png:
        msg["png"] = a.png if to_png(out, Path(a.png)) else None
    if a.cmd == "render" and a.sheet:
        msg["sheet"] = str(sheet(out, Path(a.sheet), a.bg or (st or {}).get("bg") or "#ffffff", a.ref))
    print(json.dumps(msg, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
