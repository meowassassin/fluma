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
  --typed: 명령을 이미 친 상태로 시작(결과 줄부터) — 3초 안팎 장면은 이걸로
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
WARN = [r"^WARNING: ", r"^\s*$", r"^\s*[~^]{3,}\s*$"]   # 파이썬 3.11+ 오류 위치 표시(~~~^^^) — 화면에선 잡음


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
  /* 2026-11-16: 밋밋한 기본 터미널 → 실제 개발 화면처럼(JetBrains Mono · 둥근 창 · 그림자 · 상태 코드 색 · 줄이 부드럽게 올라옴) */
  html,body{{margin:0;height:100%;background:radial-gradient(120% 90% at 20% 0%,#2a2350 0%,#14131c 55%,#0d0d12 100%);color:#cdd6f4;overflow:hidden}}
  .win{{position:absolute;inset:14px 12px;border-radius:14px;background:#181825;box-shadow:0 18px 40px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.07);overflow:hidden}}
  .bar{{position:relative;display:flex;align-items:center;gap:7px;height:36px;padding:0 14px;background:#11111b;font:600 12px "Pretendard",sans-serif;color:#9399b2}}
  .bar i{{width:11px;height:11px;border-radius:50%;display:inline-block}}
  .bar span{{position:absolute;left:0;right:0;text-align:center;pointer-events:none}}
  #t{{position:absolute;top:36px;bottom:0;left:0;right:0;overflow:hidden;padding:12px 14px 0;font:500 {fs}px/1.55 "JetBrains Mono","FiraCode Nerd Font Mono","Noto Sans Mono CJK KR",monospace;white-space:pre-wrap;overflow-wrap:anywhere;letter-spacing:-.01em}}
  .p{{color:#a6e3a1;font-weight:700}} .p .arw{{color:#89b4fa}} .p b{{color:#cdd6f4;font-weight:600}} #typed{{color:#f5e0dc;font-weight:600}}
  .l{{display:block;opacity:0;transform:translateY(8px);padding-left:2.4ch;text-indent:-2.4ch}}   /* 긴 줄은 들여쓴 채로 감싼다 — 어디까지가 한 줄인지 보이게 */
  body.focus .l:not(.m), body.focus .l:not(.m) span{{color:#7f849c!important;font-weight:400!important}}   /* 볼 줄(--mark)이 있으면 나머지는 흐리게 */
  #probe{{position:absolute;visibility:hidden;white-space:pre;font:inherit}}
  .k{{color:#cba6f7}} .ok{{color:#a6e3a1;font-weight:700}} .warn{{color:#f9e2af;font-weight:700}} .err{{color:#f38ba8;font-weight:700}}
  .url{{color:#89dceb}} .num{{color:#fab387}} .dim{{color:#6c7086}}
  .l.m{{padding:2px 8px 2px calc(2.4ch + 8px);margin:2px -8px;background:linear-gradient(90deg,rgba(249,226,175,.28),rgba(249,226,175,.08));box-shadow:inset 3px 0 0 #f9e2af;border-radius:4px;color:#fff6d6}}
  .cur{{display:inline-block;width:.55em;height:1.1em;vertical-align:-.15em;background:#f5e0dc;border-radius:1px;margin-left:1px}}
</style>
<div class="win"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i><i style="background:#28c840"></i><span>{title}</span></div>
<div id="t"><div class="p">{prompt_html}<span id="typed"></span><span class="cur" id="cur"></span></div>{body}</div></div>
<script>
// 녹화기가 시각마다 부른다: 명령을 몇 글자까지 쳤는지 · 출력을 몇 줄까지(소수 = 올라오는 중) · 커서 깜빡임
const LS = [...document.querySelectorAll('.l')], CMD = {cmd_js};
// 글자 크기를 화면 폭에 맞춘다: 가장 긴 줄이 한 줄에 들어가도록 줄이되 기본의 80% 아래로는 줄이지 않는다(그보다 길면 들여쓴 채 감싼다)
(() => {{ const box = document.getElementById('t'), pr = document.createElement('span'); pr.id = 'probe'; box.appendChild(pr);
  const avail = box.clientWidth - 28; let w = 0; LS.forEach(l => {{ pr.textContent = l.textContent; w = Math.max(w, pr.getBoundingClientRect().width); }});
  const fs = parseFloat(getComputedStyle(box).fontSize); if (w > avail) box.style.fontSize = Math.max(fs * 0.8, fs * avail / w) + 'px'; pr.remove();
  if (document.querySelector('.l.m')) document.body.classList.add('focus'); }})();
window.__render = (chars, n, cursor) => {{
  document.getElementById('typed').textContent = CMD.slice(0, chars);
  document.getElementById('cur').style.visibility = (n > 0 || !cursor) ? 'hidden' : 'visible';
  LS.forEach((l, i) => {{ const k = Math.max(0, Math.min(1, n - i)), e = 1 - Math.pow(1 - k, 3);
    l.style.opacity = e; l.style.transform = `translateY(${{(1 - e) * 8}}px)`; l.style.display = k > 0 ? 'block' : 'none'; }});
  const box = document.getElementById('t'); box.scrollTop = box.scrollHeight;
}};
</script></html>"""


TOKENS = re.compile(
    r"(?P<ok>\b2\d\d\b(?: [A-Z][A-Za-z]+)*)|(?P<warn>\b[34]\d\d\b(?: [A-Z][A-Za-z]+)*)|(?P<err>\b5\d\d\b(?: [A-Z][A-Za-z]+)*)"
    r"|(?P<url>https?://\S+|(?<=[\s\"'])/[\w.\-/?=&%]+)|(?P<k>\b(?:select|from|where|join|insert|update|delete|GET|POST|PUT|DELETE|PATCH)\b)")


def colorize(text: str) -> str:
    """상태 코드 · 주소 · 오류 줄에 색 — 2xx 초록 · 3xx/4xx 노랑 · 5xx · Traceback · Error 빨강.
    날 글자에서 한 번에 훑어 조각마다 감싼다(2026-11-16: 감싼 HTML 위에 다시 바꾸다 '</span>' 이 화면에 새어 나왔다)"""
    if re.search(r"Traceback|^\w*(Error|Exception)\b|^\s*raise\b", text):
        return f'<span class="err">{html.escape(text)}</span>'
    if re.match(r"\s*File \"", text):
        t = html.escape(text)
        return re.sub(r"(line \d+)", r'<span class="num">\1</span>', t).replace("File ", '<span class="dim">File </span>', 1)
    out, i = [], 0
    for m in TOKENS.finditer(text):
        out.append(html.escape(text[i:m.start()]))
        out.append(f'<span class="{m.lastgroup}">{html.escape(m.group(0))}</span>')
        i = m.end()
    out.append(html.escape(text[i:]))
    return "".join(out)


def cmd_render(a) -> int:
    d = term_dir(a.id)
    rec = json.loads((d / f"{a.name}.json").read_text("utf-8"))
    lines = [l for l in rec["lines"] if not re.match(r"^\s*[~^]{3,}\s*$", l["text"])]   # 오류 위치 표시 줄은 잡음
    marks = [re.compile(p) for p in (a.mark or [])]
    body = []
    for k, l in enumerate(lines):
        cls = "l" + (" m" if any(p.search(l["text"]) for p in marks) else "") + (" last" if k == len(lines) - 1 else "")
        body.append(f'<div class="{cls}">{colorize(l["text"])}</div>')
    prompt = rec.get("prompt") or "$"
    pm = re.match(r"^(\S+\s?)(.*)$", prompt)
    prompt_head, cmd_text = (pm.group(1), pm.group(2)) if pm else ("$ ", prompt)
    page = PAGE.format(fs=a.font, title=html.escape(a.title or "Terminal"), prompt_html=('<span class="arw">❯</span> ' if prompt_head.strip() in ("$", ">", "%", "#") else html.escape(prompt_head)),
                       body="".join(body), line_ms=a.line_ms, cmd_js=json.dumps(cmd_text, ensure_ascii=False))
    hp = d / f"{a.name}.html"
    hp.write_text(page, "utf-8")
    # 시간을 직접 한 프레임씩 진행하며 찍는다(브라우저 화면 녹화는 마지막 변화를 늦게 · 빠뜨려 보내 마지막 줄이 안 찍혔다)
    FPS = 30
    t_type0, type_ms = 0.5, min(0.038, 1.2 / max(1, len(cmd_text)))
    t_out0 = t_type0 + len(cmd_text) * type_ms + 0.45
    if a.typed:      # 명령을 이미 친 상태에서 결과 줄부터(director: 장면은 행동 중간에서 시작 — 2026-11-11 QR: 2초 장면이 타이핑만 하다 끝났다)
        t_type0, t_out0 = -1.0, 0.15
    dur = round(t_out0 + len(lines) * a.line_ms / 1000 + a.hold, 2)
    vw, vh = (int(x) for x in a.viewport.split("x"))
    dst = ROOT / "data" / "public" / "elements" / a.id / a.name
    if dst.exists():
        import shutil
        shutil.rmtree(dst)
    (dst / "r01").mkdir(parents=True)

    def state(t: float) -> tuple[int, int, bool]:
        chars = 0 if t < t_type0 else min(len(cmd_text), int((t - t_type0) / type_ms) + 1)
        n = 0 if t < t_out0 else min(float(len(lines)), round((t - t_out0) * 1000 / max(a.line_ms, 1) / 0.12, 0) * 0.12 + 1.0)   # 소수 = 그 줄이 올라오는 중
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
    r.add_argument("--line-ms", type=int, default=90); r.add_argument("--typed", action="store_true", help="명령을 이미 친 상태로 시작 — 결과 줄이 바로 나온다(짧은 장면)"); r.add_argument("--hold", type=float, default=2.5); r.add_argument("--mark", action="append")
    r.add_argument("--title"); r.add_argument("--font", type=float, default=16, help="글자 크기(px, 390 폭 기준 — 14 면 세로 화면에서 약 42px). 2026-11-09: 10.5 는 세로 화면에서 읽히지 않았다"); r.add_argument("--viewport", default="390x620", help="영상에서 위 제목 띠 아래 영역(1080×1718)과 같은 비율 — 세로로 길면 아래(새 줄이 찍히는 곳)가 잘린다"); r.add_argument("--scale", type=int, default=3)
    argv = sys.argv[1:]
    cmd = argv[argv.index("--") + 1:] if "--" in argv else []
    a = ap.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if a.sub == "capture":
        a.cmd = cmd
    return {"capture": cmd_capture, "import": cmd_import, "render": cmd_render}[a.sub](a)


if __name__ == "__main__":
    from result import run_main
    run_main("termrec", main)
