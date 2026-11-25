#!/usr/bin/env python3
"""화면 쓰기 도구함 — 대본이 통과한 자리(bundle.py script)에서 한 번에 준다(2026-11-25 속도 2 · 3).

2026-11-24 실측: 대본 뒤 화면을 쓰기 전에 예시 JSON · 다른 영상의 장면 코드 · 콘티 · 도구 --help 를 3분 동안 읽었고,
콘티 · 장면 코드의 고정 칸(자막 · 길이 · 재료 칸 · 안전 띠)을 매번 손으로 다시 썼다.
여기서 (1) 대본으로 묶음 뼈대(콘티 + 장면 코드 첫머리)를 만들고 (2) K 함수 · 캡처 도구 쓰는 법을 짧게 뽑는다.
판단 칸(콘셉트 · 색 · 무엇을 어떻게 보여 줄지)은 ◆ 로 비워 둔다 — 남아 있으면 apply 가 S02 로 막는다.
K 함수 목록과 도구 쓰는 법은 코드(kit.jsx · 도구 docstring)에서 그때그때 읽어 문서와 어긋나지 않는다.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
MARK = "◆"
TOOLS = [("engine/capture/termrec.py", ("capture", "render")), ("engine/capture/webrec.py", ("run",)),
         ("engine/capture/icons.py", ("fetch",)), ("engine/craft/form_cli.py", ("preview", "render", "anim")),
         ("engine/craft/craft_catalog.py", ("search",)), ("engine/core/fonts.py", ("list",))]


def k_api() -> list[str]:
    """kit.jsx 의 K 함수 — 이름(인자) + 바로 위 /** */ 한 줄"""
    out, doc, inside = [], "", False
    for ln in (ROOT / "engine" / "craft" / "jsx" / "kit.jsx").read_text("utf-8").splitlines():
        m = re.match(r"\s*/\*\*(.*?)(\*/)?\s*$", ln)
        if m:
            doc, inside = m.group(1).strip(), not m.group(2)
            continue
        if inside:
            inside = "*/" not in ln
            c = ln.strip().lstrip("*").replace("*/", "").strip()
            if c and len(doc) < 160:
                doc = f"{doc} {c}"[:220]
            continue
        for name, args in re.findall(r"(?:^\s*|[,{]\s*)([a-zA-Z]\w*): function \(([^)]*)\)", ln):
            if name not in ("C", "fit", "layer", "leaves"):
                out.append(f"K.{name}({args})" + (f" — {doc}" if doc else ""))
            doc = ""
    return out


def tool_lines() -> list[str]:
    out = []
    for f, subs in TOOLS:
        d = ast.get_docstring(ast.parse((ROOT / f).read_text("utf-8"))) or ""
        for ln in d.splitlines():
            s = ln.strip()
            if s.startswith(f"python3 {f}") and (s.split()[2:3] or [""])[0] in subs:
                out.append(re.sub(r"\s{2,}#", "  #", s)[:200])
    out.append('webrec 계획 JSON: {"start": URL, "viewport": [w, h], "scale": 2, "hide": [css], "steps": [{"do": "wait|scroll|click|type|press|hover|goto", …}]} → data/public/elements/<id>/<이름>/s000.png')
    return out


def _sec(narration: str, cps: float) -> float:
    return round(max(1.5, len(narration.replace(" ", "")) / cps + 0.4), 1)


def _cue_words(narration: str) -> list[str]:
    """$CUE 로 쓸 만한 낱말(말 속 그대로) — 숫자 · 고유명사 · 두 글자 넘는 낱말"""
    ws = [w.strip(".,!?·'\"()…") for w in narration.split()]
    return [w for w in dict.fromkeys(ws) if len(w) >= 2][:8]


def draft(sid: str, inp: dict, sb: dict) -> tuple[Path, list[str]]:
    """묶음 뼈대 — data/workspace/tmp/<id>/bundle.json + data/compositions/<id>/scenes/sNN.jsx(없거나 아직 뼈대일 때만 씀)"""
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import lint
    cps = lint.voice_cps(sb)
    comp = ROOT / "data" / "compositions" / sid
    (comp / "scenes").mkdir(parents=True, exist_ok=True)
    try:
        plan = json.loads((ROOT / "data" / "shotplans" / f"{sid}.json").read_text("utf-8"))
    except (OSError, ValueError):
        plan = {}
    try:
        facts = json.loads((ROOT / "data" / "research" / f"{sid}.json").read_text("utf-8")).get("facts") or []
    except (OSError, ValueError):
        facts = []
    scenes, wrote = [], []
    for i, (x, src) in enumerate(zip(sb["scenes"], inp.get("scenes") or []), 1):
        sec = _sec(x.get("narration") or "", cps)
        rel = f"data/compositions/{sid}/scenes/s{i:02d}.jsx"
        f = ROOT / rel
        if not f.exists() or MARK in f.read_text("utf-8"):
            f.write_text("\n".join([
                f"// 장면 {i} [{x.get('role')}] 말: {x.get('narration')}",
                f"// 화면 글자(엔진이 위 띠에 그림): {x.get('caption')} · 보일 것: {src.get('screen') or MARK}",
                f"// 낱말 시각: $CUE:<말 속 낱말> — 후보 {' · '.join(_cue_words(x.get('narration') or ''))}",
                "// 화면 1080x1920 · 비울 곳: 위 y 60~240(화면 글자) · 아래 y 1270~1420(자막) · 오른쪽 x 950~(버튼)",
                f"var F = '{comp}/';   // 형태 · 아이콘(F + 'forms/이름.png', F + '이름.svg') · 캡처는 '{ROOT}/data/public/elements/{sid}/<이름>/s000.png'",
                f"K.scene({sec}, '{MARK}바탕색');",
                f"// {MARK} 장면 코드 — 주인공 하나 · K.fx 효과 하나 이상(craft_catalog.py search) · 말에 맞춘 움직임",
                ""]), "utf-8")
            wrote.append(rel)
        scenes.append({"role": x.get("role"), "sec": sec, "beat": MARK, "shot_fn": MARK, "screen": MARK,
                       "caption": x.get("caption") or "", "narration": x.get("narration") or "",
                       "visual": {"kind": MARK}, "features": [MARK],
                       "materials": [{"id": f"s{i:02d}", "type": "craft", "app": "effectcraft", "new": {"duration": sec}, "place": "full",
                                      "export": {"format": "mp4", "start": 0, "end": sec},
                                      "steps": [{"id": "script.run", "params": {"name": f"s{i:02d}", "code": f"$FILE:{rel}"}}]}]})
    story = {"id": sid, "version": 1, "format": sb.get("format") or MARK, "language": "ko", "engine": "craft",
             "audience": sb.get("audience") or MARK, "topic": plan.get("topic") or sb.get("title"), "title": sb.get("title"),
             "duration_sec": round(sum(s["sec"] for s in scenes)), "cta": MARK,
             **({"reference": plan["reference"]} if isinstance(plan.get("reference"), list) else {}),
             **({"concepts_order": inp["concepts_order"]} if inp.get("concepts_order") else {}),
             "concept": {"angle": MARK, "breaks": MARK, "structure": MARK, "cliches": [MARK]},
             "intent": {"summary": MARK, "must": [MARK], "must_not": [MARK]},
             "direction": {"art": {"palette": {"bg": MARK, "ink": MARK, "accent": MARK}, "rule": MARK, "avoid": MARK}},
             "sources": [x["source"] for x in facts if str(x.get("source") or "").startswith("http")][:12],
             "hashtags": [MARK], "scenes": scenes}
    out = ROOT / "data" / "workspace" / "tmp" / sid / "bundle.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or MARK in out.read_text("utf-8"):
        out.write_text(json.dumps({"storyboard": story, "files": {}}, ensure_ascii=False, indent=1), "utf-8")
    return out, wrote


def text(sid: str, inp: dict, sb: dict) -> str:
    """script 가 찍는 도구함(짧게) — 뼈대 경로 · K 함수 · 캡처 도구"""
    try:
        out, wrote = draft(sid, inp, sb)
    except Exception as e:  # noqa: BLE001 — 뼈대를 못 만들어도 대본 단계는 이어 간다
        return f"(묶음 뼈대를 못 만듦: {e})"
    rel = out.relative_to(ROOT)
    return "\n".join([
        f"묶음 뼈대(대본 · 길이 · 재료 칸 · 장면 코드 첫머리를 채워 둠 — 예시 · 다른 영상 파일을 읽지 말고 {MARK} 칸만 채운다):",
        f"- 콘티: {rel} → 다 채우면 bundle.py apply {rel}",
        f"- 장면 코드: data/compositions/{sid}/scenes/s01.jsx … (첫머리 아래를 이어 쓴다 · {MARK} 이 남으면 apply 가 S02 로 막는다)",
        "- 재료를 더 붙일 때: 장면 materials 에 {\"id\", \"type\": \"web|icon|form|…\", \"src\": 경로} — 장면 코드에서는 K.image(경로, x, y, 배율)",
        "K 함수(장면 코드에 자동으로 붙음):", *[f"  {x}" for x in k_api()],
        "재료 만들기:", *[f"  {x}" for x in tool_lines()],
    ])


if __name__ == "__main__":
    for x in k_api():
        print(x)
    for x in tool_lines():
        print(x)
