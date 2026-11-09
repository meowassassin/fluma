#!/usr/bin/env python3
"""터미널 녹화 — 명령을 실제로 실행한 출력을 터미널 화면 영상(웹 녹화 요소)으로 만든다. 꾸며 쓴 로그 대신 진짜 로그.

  python3 engine/capture/termrec.py capture <영상 id> <이름> [--cwd 폴더] [--prompt "$ java -jar shop.jar"] [--drop 정규식 …] -- <명령 …>
  python3 engine/capture/termrec.py import  <영상 id> <이름> --log 출력.txt [--prompt …] [--drop …]      # 이미 받아 둔 출력(다른 컴퓨터에서 실행)
  python3 engine/capture/termrec.py render  <영상 id> <이름> [--line-ms 35] [--hold 2.5] [--mark 정규식 …] [--title "IntelliJ · Run: shop"]

capture: 출력 줄마다 실제 시각을 남긴다 → data/compositions/<id>/term/<이름>.json (명령 · 줄 · 실행 시간 · 버린 줄 수)
  --drop 은 JVM 경고처럼 내용과 상관없는 줄만 뺀다(빼는 규칙과 개수를 남긴다). 출력 글자는 고치지 않는다.
render: 그 출력을 터미널 화면에 차례로 찍는 페이지를 만들고, 시간을 한 프레임씩 진행하며 30fps 로 찍는다 → data/public/elements/<id>/<이름>/
  (webrec 와 같은 요소 폴더 형식 — 재료 {"type": "web", "src": …} 로 그대로 쓴다)
  --line-ms: 줄 사이 간격(실제로는 몇 ms 안에 쏟아지는 출력을 눈으로 따라갈 수 있게 늘린다 — meta 에 원래 실행 시간을 같이 남김)
  --mark: 강조할 줄(정규식) — 노란 배경. 맨 끝 줄은 늘 굵게
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
WARN = [r"^WARNING: ", r"^\s*$"]


def term_dir(sid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", sid):
        sys.exit("영상 id 가 올바르지 않음")
    d = ROOT / "data" / "compositions" / sid / "term"
    d.mkdir(parents=True, exist_ok=True)
    return d


def keep(lines: list[dict], drops: list[str]) -> tuple[list[dict], int]:
    pats = [re.compile(p) for p in drops]
    out = [l for l in lines if not any(p.search(l["text"]) for p in pats)]
    return out, len(lines) - len(out)


def cmd_capture(a) -> int:
    d = term_dir(a.id)
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        sys.exit("실행할 명령이 없습니다(-- 뒤에)")
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=a.cwd or None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = [{"t": round(time.time() - t0, 3), "text": ln.rstrip("\n")} for ln in p.stdout]
    code = p.wait()
    real = round(time.time() - t0, 2)
    lines, dropped = keep(lines, (a.drop or []) + WARN)
    rec = {"cmd": cmd, "prompt": a.prompt or ("$ " + " ".join(cmd)), "exit": code, "real_sec": real, "lines": lines,
           "dropped": dropped, "drop_rules": (a.drop or []) + WARN, "source": "captured"}
    (d / f"{a.name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    print(f"[termrec] {a.name}: {len(lines)}줄(버린 줄 {dropped}) · 실행 {real}초 · 종료 코드 {code} → {(d / f'{a.name}.json').relative_to(ROOT)}")
    return 0 if code == 0 else 1


def cmd_import(a) -> int:
    d = term_dir(a.id)
    raw = Path(a.log).read_text("utf-8", errors="replace").splitlines()
    lines, dropped = keep([{"t": 0.0, "text": s} for s in raw], (a.drop or []) + WARN)
    rec = {"cmd": None, "prompt": a.prompt or "$", "exit": 0, "real_sec": None, "lines": lines, "dropped": dropped,
           "drop_rules": (a.drop or []) + WARN, "source": f"imported:{Path(a.log).name}"}
    (d / f"{a.name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    print(f"[termrec] {a.name}: {len(lines)}줄 가져옴(버린 줄 {dropped})")
    return 0


PAGE = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html,body{{margin:0;height:100%;background:#1e1f22;color:#d4d4d4}}
  .bar{{display:flex;align-items:center;gap:7px;padding:11px 14px;background:#2b2d30;font:600 12.5px "Pretendard","Noto Sans CJK KR",sans-serif;color:#b9bcc2;border-bottom:1px solid #393b40}}
  .bar i{{width:11px;height:11px;border-radius:50%;display:inline-block}}
  .bar span{{margin-left:8px}}
  #t{{position:absolute;top:42px;bottom:0;left:0;right:0;overflow:hidden;padding:10px 12px 0;font:{fs}px/1.5 "DejaVu Sans Mono","Noto Sans Mono CJK KR",monospace;white-space:pre-wrap;overflow-wrap:anywhere}}
  .p{{color:#6fb3ff}} .p b{{color:#e6e6e6;font-weight:600}}
  .l{{display:none}} .l.on{{display:block}}
  .k{{color:#cc7832}} .m{{background:rgba(255,214,10,.22);color:#fff3b0}} .last{{font-weight:700;color:#7ee787}}
  .cur{{display:inline-block;width:.6em;background:#d4d4d4}}
</style>
<div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span>{title}</span></div>
<div id="t"><div class="p">{prompt_html}<span id="typed"></span><span class="cur" id="cur">&nbsp;</span></div>{body}</div>
<script>
// 녹화기가 시각마다 부른다: 명령을 몇 글자까지 쳤는지 · 출력을 몇 줄까지 보일지 · 커서 깜빡임
const LS = [...document.querySelectorAll('.l')], CMD = {cmd_js};
window.__render = (chars, n, cursor) => {{
  document.getElementById('typed').textContent = CMD.slice(0, chars);
  document.getElementById('cur').style.visibility = (n > 0 || !cursor) ? 'hidden' : 'visible';
  LS.forEach((l, i) => l.classList.toggle('on', i < n));
  const box = document.getElementById('t'); box.scrollTop = box.scrollHeight;
}};
</script></html>"""


def colorize(text: str) -> str:
    t = html.escape(text)
    return re.sub(r"\b(select|from|where|join|left join|on|in|insert|update|delete)\b", r'<span class="k">\1</span>', t)


def cmd_render(a) -> int:
    d = term_dir(a.id)
    rec = json.loads((d / f"{a.name}.json").read_text("utf-8"))
    lines = rec["lines"]
    marks = [re.compile(p) for p in (a.mark or [])]
    body = []
    for k, l in enumerate(lines):
        cls = "l" + (" m" if any(p.search(l["text"]) for p in marks) else "") + (" last" if k == len(lines) - 1 else "")
        body.append(f'<div class="{cls}">{colorize(l["text"])}</div>')
    prompt = rec.get("prompt") or "$"
    pm = re.match(r"^(\S+\s?)(.*)$", prompt)
    prompt_head, cmd_text = (pm.group(1), pm.group(2)) if pm else ("$ ", prompt)
    page = PAGE.format(fs=a.font, title=html.escape(a.title or "Terminal"), prompt_html=f"{html.escape(prompt_head)}",
                       body="".join(body), line_ms=a.line_ms, cmd_js=json.dumps(cmd_text, ensure_ascii=False))
    hp = d / f"{a.name}.html"
    hp.write_text(page, "utf-8")
    # 시간을 직접 한 프레임씩 진행하며 찍는다(브라우저 화면 녹화는 마지막 변화를 늦게 · 빠뜨려 보내 마지막 줄이 안 찍혔다)
    FPS = 30
    t_type0, type_ms = 0.5, min(0.038, 1.2 / max(1, len(cmd_text)))
    t_out0 = t_type0 + len(cmd_text) * type_ms + 0.45
    dur = round(t_out0 + len(lines) * a.line_ms / 1000 + a.hold, 2)
    vw, vh = (int(x) for x in a.viewport.split("x"))
    dst = ROOT / "data" / "public" / "elements" / a.id / a.name
    if dst.exists():
        import shutil
        shutil.rmtree(dst)
    (dst / "r01").mkdir(parents=True)

    def state(t: float) -> tuple[int, int, bool]:
        chars = 0 if t < t_type0 else min(len(cmd_text), int((t - t_type0) / type_ms) + 1)
        n = 0 if t < t_out0 else min(len(lines), int((t - t_out0) * 1000 / a.line_ms) + 1)
        return chars, n, int(t * 2) % 2 == 0

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=a.scale, is_mobile=True, has_touch=True)
        pg.goto(hp.resolve().as_uri(), wait_until="load")
        pg.evaluate("document.fonts.ready")
        shot = lambda: pg.screenshot(type="jpeg", quality=92, animations="disabled")
        pg.evaluate("([c, n, k]) => __render(c, n, k)", [0, 0, True]); pg.screenshot(path=str(dst / "s000.png"))
        last, img = None, None
        for i in range(int(dur * FPS)):
            st = state(i / FPS)
            if st != last:
                pg.evaluate("([c, n, k]) => __render(c, n, k)", list(st)); img = shot(); last = st
            (dst / "r01" / f"f{i + 1:05d}.jpg").write_bytes(img)
        pg.evaluate("([c, n, k]) => __render(c, n, k)", [len(cmd_text), len(lines), False]); pg.screenshot(path=str(dst / "s001.png"))
        # 강조 줄(--mark)의 자리 — 나레이션이 없어도 재료 단계가 그 줄로 다가가게(highlight_box)
        marks = pg.evaluate("() => Array.from(document.querySelectorAll('.m')).map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })")
        b.close()
    meta = {"kind": "web", "viewport": [vw, vh], "scale": a.scale, "mobile": True, "states": ["s000.png", "s001.png"],
            "actions": [{"do": "record", "from": 0, "to": 1, "label": None, "box": None, "sec": dur}], "masked": 0, "sources": [],
            "license": "실제 실행 출력(직접 실행)",
            "marks": [[round(x / vw, 4), round(y / vh, 4), round(w / vw, 4), round(h / vh, 4)] for x, y, w, h in (marks or []) if w and h],
            "terminal": {"cmd": rec.get("cmd"), "prompt": prompt, "real_sec": rec.get("real_sec"), "lines": len(lines), "dropped": rec.get("dropped"),
                         "drop_rules": rec.get("drop_rules"), "line_ms": a.line_ms, "note": "실제 실행 출력 — 글자는 그대로, 줄 사이 간격만 늘림"}}
    (dst / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    print(f"[termrec] {a.name}: {len(lines)}줄 · 영상 {dur}초 → data/public/elements/{a.id}/{a.name}/ (재료: {{\"type\": \"web\", \"src\": \"data/public/elements/{a.id}/{a.name}\", \"mobile\": true}})")
    from result import ok
    ok("termrec", element=str(dst.relative_to(ROOT)), sec=dur, lines=len(lines), material=json.dumps({"type": "web", "src": str(dst.relative_to(ROOT))}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="sub", required=True)
    c = sub.add_parser("capture"); c.add_argument("id"); c.add_argument("name"); c.add_argument("--cwd"); c.add_argument("--prompt"); c.add_argument("--drop", action="append"); c.set_defaults(cmd=[])
    i = sub.add_parser("import"); i.add_argument("id"); i.add_argument("name"); i.add_argument("--log", required=True); i.add_argument("--prompt"); i.add_argument("--drop", action="append")
    r = sub.add_parser("render"); r.add_argument("id"); r.add_argument("name")
    r.add_argument("--line-ms", type=int, default=35); r.add_argument("--hold", type=float, default=2.5); r.add_argument("--mark", action="append")
    r.add_argument("--title"); r.add_argument("--font", type=float, default=14, help="글자 크기(px, 390 폭 기준 — 14 면 세로 화면에서 약 42px). 2026-11-09: 10.5 는 세로 화면에서 읽히지 않았다"); r.add_argument("--viewport", default="390x620", help="영상에서 위 제목 띠 아래 영역(1080×1718)과 같은 비율 — 세로로 길면 아래(새 줄이 찍히는 곳)가 잘린다"); r.add_argument("--scale", type=int, default=3)
    argv = sys.argv[1:]
    cmd = argv[argv.index("--") + 1:] if "--" in argv else []
    a = ap.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if a.sub == "capture":
        a.cmd = cmd
    return {"capture": cmd_capture, "import": cmd_import, "render": cmd_render}[a.sub](a)


if __name__ == "__main__":
    from result import run_main
    run_main("termrec", main)
