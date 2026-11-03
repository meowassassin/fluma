#!/usr/bin/env python3
"""
캐릭터(진행자 · 마스코트) 립싱크 — 마무리 단계에서 입힌다(렌더 엔진과 무관).
브랜드 키트는 2026-10-29 제거(ADR-0011). 색은 콘티의 direction 이 정한다.

  characters/<이름>/character.json + parts/*.svg
      base(몸 + 뜬 눈, 입 없음) · eyes_closed · mouth.{closed,a,e,i,o,u} — 모두 같은 캔버스(viewbox), 겹치면 맞물린다

립싱크: 단어 자막 타이밍(startMs/endMs) 안에서 음절마다 입 모양을 바꾼다.
한글은 모음(중성)으로: ㅏㅑㅓㅕㅘ→a · ㅐㅒㅔㅖㅙㅞㅚ→e · ㅣㅟㅢㅡ→i · ㅗㅛㅝ→o · ㅜㅠ→u. 영문은 모음 글자로.

  python3 scripts/character_overlay.py visemes storyboards/<id>.json     # 입 모양 구간 확인
  python3 scripts/character_overlay.py list
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHARS = ROOT / "characters"
CACHE = ROOT / "workspace" / "render" / "_characters"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
VCLASS = {**{v: "a" for v in "ㅏㅑㅓㅕㅘ"}, **{v: "e" for v in "ㅐㅒㅔㅖㅙㅞㅚ"}, **{v: "i" for v in "ㅣㅟㅢㅡ"}, **{v: "o" for v in "ㅗㅛㅝ"}, **{v: "u" for v in "ㅜㅠ"}}


def load_character(name: str | None) -> dict | None:
    if not name:
        return None
    p = CHARS / name / "character.json"
    if not p.exists():
        raise SystemExit(f"캐릭터 없음: characters/{name}/character.json")
    c = json.loads(p.read_text(encoding="utf-8"))
    c["_dir"] = str(p.parent)
    return c


def resolve(sb: dict) -> dict | None:
    """콘티 → 캐릭터 (character 키, 없으면 없음)."""
    return load_character(sb.get("character"))


def _raster_chromium(svg: Path, width: int, out: Path):
    try:
        import re as _re
        from playwright.sync_api import sync_playwright
        txt = svg.read_text(encoding="utf-8")
        vb = _re.search(r'viewBox="([\d.\s-]+)"', txt)
        w0, h0 = (float(x) for x in vb.group(1).split()[2:4]) if vb else (400.0, 480.0)
        h = round(width * h0 / w0)
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": width, "height": h})
            import base64
            data = "data:image/svg+xml;base64," + base64.b64encode(svg.read_bytes()).decode()   # 빈 페이지는 file:// 을 못 읽음 → 데이터 주소로
            pg.set_content(f'<html><body style="margin:0;background:transparent"><img src="{data}" style="width:{width}px;height:{h}px;display:block"></body></html>')
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(out), omit_background=True)
            b.close()
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


def raster(svg: Path, width: int) -> Path:
    """SVG → PNG (inkscape). 내용 · 크기가 같으면 캐시."""
    import hashlib
    key = hashlib.sha1(svg.read_bytes() + str(width).encode()).hexdigest()[:10]
    out = CACHE / f"{svg.stem}-{width}-{key}.png"
    if not out.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        import shutil
        if shutil.which("inkscape"):
            r = subprocess.run(["inkscape", str(svg), "--export-type=png", f"--export-filename={out}", "-w", str(width)], capture_output=True, text=True)
            err = r.stderr
        else:   # inkscape 가 없는 환경(대부분의 macOS · Windows): 이미 쓰는 Chromium(Playwright)으로 투명 배경 PNG
            err = _raster_chromium(svg, width, out)
        if not out.exists():
            raise SystemExit(f"SVG 변환 실패 {svg}: {str(err)[-500:]}")
    return out


def syllable_shapes(text: str) -> list[str]:
    out = []
    word = text.strip()
    i = 0
    while i < len(word):
        ch = word[i]
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            out.append(VCLASS[JUNG[((o - 0xAC00) // 28) % 21]])
        elif ch.lower() in "aeiouy":
            out.append({"y": "i"}.get(ch.lower(), ch.lower()))
            while i + 1 < len(word) and word[i + 1].lower() in "aeiouy":
                i += 1
        elif ch.isdigit():
            out.append("a")
        i += 1
    return out or ["a"]


def visemes(captions: list[dict]) -> dict[str, list[tuple[float, float]]]:
    """단어 자막 → 입 모양별 구간(초). 음절마다 같은 길이, 끝 20% 는 닫음(자연스럽게)."""
    spans: dict[str, list[tuple[float, float]]] = {k: [] for k in "aeiou"}
    for c in captions:
        a, b = c["startMs"] / 1000, c["endMs"] / 1000
        shapes = syllable_shapes(c["text"])
        step = (b - a) / len(shapes)
        for k, s in enumerate(shapes):
            s0, s1 = a + k * step, a + k * step + step * 0.8
            if spans[s] and s0 - spans[s][-1][1] < 0.03:
                spans[s][-1] = (spans[s][-1][0], s1)
            else:
                spans[s].append((s0, s1))
    return spans


def overlay_graph(char: dict | None, captions: list[dict], w: int, h: int, first_input: int) -> tuple[list[str], list[str], str]:
    """마무리 단계에 붙일 ffmpeg 입력과 필터. 반환: (입력 인자들, 필터 줄들, 마지막 라벨). 입력 영상 라벨은 [base]."""
    ins, f, last, n = [], [], "base", first_input
    S = w / 1080

    def add_png(path: Path):
        nonlocal n
        ins.extend(["-loop", "1", "-i", str(path)])
        n += 1
        return n - 1

    if char:
        P, d = char["placement"], Path(char["_dir"])
        cw = int(P.get("width", 240) * S)
        vb = char.get("viewbox", [400, 480])
        ch = int(cw * vb[1] / vb[0])
        x = f"W-{cw}-{int(P.get('margin', 36) * S)}" if P.get("side", "right") == "right" else f"{int(P.get('margin', 36) * S)}"
        idle = char.get("idle", {})
        y = f"H-{ch}-{int(P.get('bottom', 36) * S)}+{idle.get('bob_px', 8) * S:.1f}*sin(2*PI*t/{idle.get('bob_period', 2.4)})"
        parts = char["parts"]
        layers = [("base", parts["base"], None), ("mclosed", parts["mouth"]["closed"], None)]
        spans = visemes(captions)
        for s in "aeiou":
            if spans[s] and s in parts["mouth"]:
                layers.append((f"m{s}", parts["mouth"][s], "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in spans[s])))
        be, bl = idle.get("blink_every", 3.4), idle.get("blink_len", 0.12)
        layers.append(("blink", parts["eyes_closed"], f"lt(mod(t+0.7,{be}),{bl})"))
        for name, rel, enable in layers:
            k = add_png(raster(d / rel, cw))
            nxt = f"c{name}"
            en = f":enable='{enable}'" if enable else ""
            f.append(f"[{last}][{k}:v]overlay=x={x}:y='{y}':shortest=1{en}[{nxt}]")
            last = nxt
    return ins, f, last


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for d in sorted(CHARS.glob("*/character.json")):
            print("character", d.parent.name, "·", json.loads(d.read_text())["title"])
    elif len(sys.argv) > 2 and sys.argv[1] == "visemes":
        sb = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        caps = json.loads((ROOT / "public" / "audio" / f"{sb['id']}.captions.json").read_text(encoding="utf-8"))
        for c in caps[:8]:
            print(f"{c['startMs']:>6}–{c['endMs']:<6} {c['text'].strip():<10} {' '.join(syllable_shapes(c['text']))}")
        print({k: len(v) for k, v in visemes(caps).items()})
    else:
        sys.exit(__doc__)
