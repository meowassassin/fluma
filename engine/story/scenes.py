#!/usr/bin/env python3
"""장면 코드를 장면마다 동시에 쓴다 — 콘티(장면별 내용 · 바탕 · 형태 · 신호 낱말)를 받아 scenes/sNN.jsx 를 병렬로 작성(2026-11-21 속도).

  python3 engine/story/scenes.py write <id> [--scenes 2,5] [--note "고칠 점"] [--jobs 8]

한 에이전트가 장면 8개를 차례로 쓰면 4~5분이 들었다(쓰는 시간 대부분이 생성). 같은 모델 · 같은 지침으로 장면마다 따로 부르면
가장 긴 장면 하나만큼만 걸린다. 공통 지침(장면 부품 · AI 티 규칙 · 안전 영역 · 형태 사용)은 모든 장면에 똑같이 주고(프롬프트 캐시),
장면마다 영상 흐름(모든 장면 요약 · 모티프 · 이웃 장면 바탕)과 그 장면의 상세를 준다. 설정된 런타임(Claude · Codex · Antigravity)을 쓴다.
쓴 뒤: 문법 검사(node --check) — 틀린 장면만 오류를 붙여 한 번 다시. 마지막에 bundle.py check(형식 · 화면 AI 티 · 형태 잘림)를 돌려 보여 준다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "core"))
from result import fail, ok  # noqa: E402


def kit_api() -> str:
    """kit.jsx 의 설명 줄과 함수 머리만 — 장면 작성자가 쓸 부품 목록"""
    out = []
    lines = (ROOT / "engine" / "craft" / "jsx" / "kit.jsx").read_text("utf-8").splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"\s+([a-zA-Z]+): function \(([^)]*)\)", ln)
        if m and m.group(1) not in ("leaves", "layer", "fit", "follow", "P", "S", "O", "R"):
            doc = lines[i - 1].strip() if i and "/**" in lines[i - 1] else ""
            out.append(f"K.{m.group(1)}({m.group(2)})  {doc.strip('/* ').strip()}")
    return "\n".join(out)


GUIDE = """너는 Fluma 쇼츠의 장면 코드 작성자다. EffectCraft(After Effects 호환 ExtendScript, ES3) 장면 코드 한 장면을 쓴다.
화면 1080×1920. 장면 길이는 콘티의 sec. 코드만 쓴다 — 설명 없이 ```jsx 블록 하나.

[문법] ES3: var · function 만(let · const · => · 템플릿 문자열 · 구조 분해 금지). 시각은 초. 나레이션 낱말 시각은 $CUE:낱말(그 낱말이 들리는 초, 숫자처럼 더하고 뺄 수 있다 — 낱말은 장면 나레이션에 실제로 있는 어절 그대로).
[부품]
{api}
- 형태(캐릭터 · 사물) 움직임 프레임: var me = K.image(F + '<이름>.anim/f000.png', x, y, 배율) — 반복 재생된다. F 는 아래 경로.
- 자막(나레이션)은 엔진이 따로 그린다(화면 아래 약 y 1270~1420) — 나레이션 문장을 화면 글자로 다시 쓰지 않는다. 콘티 장면의 caption 은 엔진이 화면 위(y 약 60~240)에 그린다 — 그 두 자리 · 오른쪽 12%(버튼)에는 글자 · 주인공을 두지 않는다.
[화면 — AI 티를 피한다(레퍼런스 13편 실측, 어기면 제작이 막힌다)]
- 바탕: K.scene(초, 바탕) 의 바탕은 콘티 장면의 bg 를 그대로. 없으면 장면의 장소 · 물건 색에서 고르고, 이웃 장면과 다르게. 어두운 남색 · 검정 기본값 금지.
- 빛번짐(glow) · 흔들기(shake) · 렌즈 빛 효과 금지. 강조는 크기 · 색 대비 · 그 물건에 붙인 라벨로.
- 둥근 카드 · 알약(앱 UI 부품)을 띄우지 않는다 — 정보는 장면 속 실제 물건(표지판 · 종이 · 전광판 · 손글씨 라벨)에 쓴다.
- 튀어나오기(K.pop)는 말에서 그 물건이 나오는 순간에만. 나머지 움직임은 뜻이 있는 동작(놓이기 · 그려지기 · 따라 움직이기 · 카메라가 다가가기).
- 주인공(형태 그림)의 자리 · 크기를 이웃 장면과 다르게(전신 · 상반신 · 얼굴 · 손, 3분할 · 가장자리 · 전경).
- 화면 글자는 핵심어 하나만, 그 물건 옆에. 글꼴은 콘티 direction 의 것.
[예]
```jsx
K.scene(3.2, ['#f7e7b4', '#e9c46a']);
var F = '{forms}';
var comb = K.shape('rect', 520, 900, 760, 520, {{fill: '#d99a2b', round: 18}});
var bee = K.image(F + 'bee.anim/f000.png', 260, 640, 60);
K.move(bee, 0, [180, 700], [470, 820], 0.9);
var tag = K.text('1/12 숟가락', 700, 640, 64, '#5a3a12', {{font: 'BagelFatOne-Regular'}});
K.appear(tag, $CUE:숟가락, 0.25);
```
"""


def _outline(sb: dict) -> str:
    rows = []
    for i, s in enumerate(sb.get("scenes") or [], 1):
        v = s.get("visual") or {}
        rows.append(f"{i}. {s.get('sec')}초 · {s.get('shot_fn') or ''} · 바탕 {s.get('bg') or '?'} · 말: {str(s.get('narration') or '')[:60]} · 화면: {str(v.get('primary') or '')[:70]}")
    return "\n".join(rows)


def _forms(sid: str) -> str:
    from PIL import Image
    out = []
    for d in sorted((ROOT / "data" / "compositions" / sid / "forms").glob("*.anim")):
        try:
            a = json.loads((d / "anim.json").read_text("utf-8"))
            w, h = Image.open(d / "f000.png").size
            out.append(f"- {d.stem}: {a.get('frames')}장 {a.get('fps')}fps, 그림 {w}×{h}px(배율 100 = 이 크기)")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out) or "(없음)"


def _scene_prompt(sb: dict, sid: str, n: int, note: str, err: str = "") -> str:
    sc = sb["scenes"][n - 1]
    keep = {k: v for k, v in sc.items() if k not in ("materials",)}
    mats = [m for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("type") != "craft" and m.get("id")]
    if keep.get("features"):                             # 빛번짐 같은 AI 티 효과는 고른 기능이어도 쓰지 않는다
        keep["features"] = [f for f in keep["features"] if not any(b in str(f) for b in ("glow", "lightsweep", "lensflare", "shake"))]
    budget = max(1, round(float(sc.get("sec") or 3) * 0.4))
    scs = sb["scenes"]
    nb = [f"{j}번 바탕 {scs[j - 1].get('bg') or '?'}" for j in (n - 1, n + 1) if 1 <= j <= len(scs)]
    d = sb.get("direction") or {}
    parts = [f"영상: {sb.get('title')} — {sb.get('topic')}",
             f"감독 다섯 기둥: {json.dumps(d.get('anchors') or {}, ensure_ascii=False)}",
             f"글꼴: 제목 {d.get('font_title') or '-'} · 본문 {d.get('font_body') or '-'}",
             f"전체 장면:\n{_outline(sb)}",
             f"쓸 수 있는 형태 움직임(F = data/compositions/{sid}/forms/ 절대 경로는 아래 코드 예의 F):\n{_forms(sid)}",
             f"이웃 장면: {' · '.join(nb)}",
             f"이 장면({n}번) 콘티:\n{json.dumps(keep, ensure_ascii=False, indent=1)}"]
    if mats:                                             # 장면의 다른 재료(사진 · 형태 · 자료)는 장면 코드가 직접 배치한다 — 따로 화면에 깔리지 않는다
        rows = [f"- {m['id']} ({m.get('type')}): {str(m.get('what') or m.get('query') or m.get('desc') or m.get('file') or '')[:80]}" for m in mats]
        parts.append("이 장면의 재료 — 코드에서 K.image('$USE:<id>', x, y, 배율) 로 꼭 배치한다(형태 재료는 움직임이면 그 anim 프레임):\n" + "\n".join(rows))
    if note:
        parts.append(f"고칠 점: {note}")
    if err:
        parts.append(f"앞서 쓴 코드의 오류 — 고쳐서 다시: {err}")
    parts.append(f"화면 글자(K.text)는 이 장면에서 {budget}개까지(레퍼런스 설명형 10초당 1~4.6번) — 말을 글자로 되풀이하지 않는다.")
    parts.append(f"이 장면의 코드(K.scene({sc.get('sec')}, …) 로 시작)를 ```jsx 블록 하나로.")
    return "\n\n".join(parts)


def _code(txt: str) -> str:
    m = re.findall(r"```(?:jsx|js|javascript)?\s*\n(.*?)```", txt, re.S)
    return (max(m, key=len) if m else txt).strip() + "\n"


_FX: dict | None = None


def _fx_table() -> dict:
    """EffectCraft 효과 id → (화면 이름, 속성 이름들) — .claude/skills/crafts/catalog/effectcraft.jsonl"""
    global _FX
    if _FX is None:
        _FX = {}
        f = ROOT / ".claude" / "skills" / "crafts" / "catalog" / "effectcraft.jsonl"
        for ln in (f.read_text("utf-8").splitlines() if f.exists() else []):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("kind") == "effect":
                try:
                    ps = [x.get("name") for x in json.loads(r.get("params") or "[]") if isinstance(x, dict)]
                except ValueError:
                    ps = []
                _FX[r["id"]] = (r.get("label") or "", [x for x in ps if x])
    return _FX


def _fx_check(code: str) -> tuple[str, str]:
    """K.fx 의 효과 이름 · 속성 이름을 실제 목록과 대조 — 철자만 다르면 바로잡고, 없는 것은 오류로(그 장면만 다시 쓴다).
    2026-11-21: 'ec.blur.directionalblur'(없는 효과) 로 빌드가 멈췄다. 장면 작성자는 목록을 검색할 수 없다"""
    import difflib
    fx = _fx_table()
    if not fx:
        return code, ""
    errs = []
    for m in re.finditer(r"K\.fx\(\s*[^,]+,\s*'([^']+)'\s*(,\s*\{[^;]*?\})?", code):
        name, props = m.group(1), m.group(2) or ""
        if not name.startswith("ec."):
            continue
        if name not in fx:
            near = difflib.get_close_matches(name, list(fx), n=1, cutoff=0.8)
            if near:
                code = code.replace(f"'{name}'", f"'{near[0]}'"); name = near[0]
            else:
                errs.append(f"없는 효과 {name} — 비슷한 것: {', '.join(difflib.get_close_matches(name, list(fx), n=3, cutoff=0.5)) or '없음(빼라)'}")
                continue
        for pn in re.findall(r"'([^']+)'\s*:", props):
            if fx[name][1] and pn not in fx[name][1]:
                errs.append(f"{name} 에 속성 '{pn}' 없음 — 있는 것: {', '.join(fx[name][1][:8])}")
    return code, "; ".join(errs)


def _cue_check(code: str, narration: str) -> tuple[str, str]:
    """$CUE:낱말이 그 장면 대사에 있는지(음성 엔진과 같은 맞춤 — craft.cues.find). 어절과 조금 다르면 그 어절로 바로잡고,
    없으면 오류로(그 장면만 다시). 2026-11-21: 대사에 없는 신호 낱말(L73)로 콘티 검사가 한 번 더 돌았다"""
    import difflib
    try:
        from craft.cues import CUE, find
    except Exception:  # noqa: BLE001
        return code, ""
    toks = narration.split()
    words = [{"text": w, "start": 0.0, "end": 0.0} for w in toks]
    errs = []
    for m in list(CUE.finditer(code)):
        w = m.group(1).strip()
        if not w or (words and find(words, w, strict=False) is not None):
            continue
        clean = [re.sub(r"[^\w%]", "", t) for t in toks]
        near = difflib.get_close_matches(w, clean, n=1, cutoff=0.6)
        if near and near[0]:
            code = code.replace(f"$CUE:{w}", f"$CUE:{near[0]}")
        else:
            errs.append(f"신호 낱말 '{w}' 이 대사에 없음 — 대사의 어절 중에서: {' '.join(clean[:20])}")
    return code, "; ".join(errs)


def _syntax(code: str) -> str:
    probe = re.sub(r"\$CUE:[^\s,;)\]}+\-*/]+", "0", code).replace("$USE:", "")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write("var K = {}, C = {}, app = {}; function ease(){}\n" + probe)
    r = subprocess.run(["node", "--check", fh.name], capture_output=True, text=True, timeout=30)
    Path(fh.name).unlink(missing_ok=True)
    return "" if r.returncode == 0 else (r.stderr or "").strip().splitlines()[-1][:200] if r.stderr else "문법 오류"


def write(sid: str, only: list[int] | None, note: str, jobs: int) -> dict:
    from agent_cli import run_agent
    sp = ROOT / "data" / "storyboards" / f"{sid}.json"
    sb = json.loads(sp.read_text("utf-8"))
    forms = str(ROOT / "data" / "compositions" / sid / "forms") + "/"
    system = GUIDE.format(api=kit_api(), forms=forms)
    todo = only or list(range(1, len(sb.get("scenes") or []) + 1))
    sd = ROOT / "data" / "compositions" / sid / "scenes"
    sd.mkdir(parents=True, exist_ok=True)
    times, cost = {}, 0.0

    def one(n: int):
        t0 = time.time()
        err, c = "", 0.0
        for attempt in range(2):
            txt, cc = run_agent(system, _scene_prompt(sb, sid, n, note, err), override_env="FLUMA_SKILL_RUNTIME", timeout=420)
            c += cc
            code = _code(txt).replace("var F = '{forms}';", f"var F = '{forms}';")
            code, fx_err = _fx_check(code)
            code, cue_err = _cue_check(code, str(sb["scenes"][n - 1].get("narration") or ""))
            err = _syntax(code) or fx_err or cue_err
            if not err:
                break
        (sd / f"s{n:02d}.jsx").write_text(code, "utf-8")
        return n, round(time.time() - t0, 1), err, c

    with ThreadPoolExecutor(max_workers=max(1, min(jobs, len(todo)))) as ex:
        for n, sec, err, c in ex.map(one, todo):
            times[n] = (sec, err)
            cost += c
    changed = False
    for n in todo:
        for m in sb["scenes"][n - 1].get("materials") or []:     # 이미 이어진 장면 코드 재료에도 다른 재료 연결표(uses)를 채운다
            if isinstance(m, dict) and m.get("type") == "craft" and m.get("id") == f"s{n:02d}":
                others = {x["id"]: x["id"] for x in sb["scenes"][n - 1]["materials"] if isinstance(x, dict) and x.get("id") and x.get("type") != "craft"}
                if others and m.get("uses") != {**others, **(m.get("uses") or {})}:
                    m["uses"] = {**others, **(m.get("uses") or {})}; changed = True                                      # 콘티의 장면 재료가 파일을 가리키게(없을 때만)
        sc = sb["scenes"][n - 1]
        ref = f"$FILE:data/compositions/{sid}/scenes/s{n:02d}.jsx"
        if not any(isinstance(m, dict) and m.get("type") == "craft" and ref in json.dumps(m, ensure_ascii=False) for m in sc.get("materials") or []):
            # 다른 재료(사진 · 형태)가 있어도 장면 코드를 잇는다 — 2026-11-21: 이어지지 않아 장면 코드가 안 쓰이고 연출 설명이 글자로 찍혔다
            sc["materials"] = [m for m in sc.get("materials") or [] if not (isinstance(m, dict) and m.get("type") == "craft" and m.get("id") == f"s{n:02d}")]
            others = {m["id"]: m["id"] for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("id") and m.get("type") != "craft"}
            sc.setdefault("materials", []).append({"id": f"s{n:02d}", "type": "craft", "app": "effectcraft", "new": {"duration": sc.get("sec")}, "place": "full",
                                                   **({"uses": others} if others else {}),
                                                   "export": {"format": "mp4", "start": 0, "end": sc.get("sec")},
                                                   "steps": [{"id": "script.run", "params": {"name": f"s{n:02d}", "code": ref}}]})
            changed = True
    if changed:
        sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return {"times": times, "cost": round(cost, 3)}


def main() -> int:
    a = sys.argv[1:]
    if len(a) < 2 or a[0] != "write":
        print(__doc__); return 2
    sid = a[1]
    only = [int(x) for x in a[a.index("--scenes") + 1].split(",")] if "--scenes" in a else None
    note = a[a.index("--note") + 1] if "--note" in a else ""
    jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 8
    t0 = time.time()
    try:
        r = write(sid, only, note, jobs)
    except Exception as e:  # noqa: BLE001
        fail("scenes", stage="write", error=str(e)[:400])
    bad = {n: e for n, (s, e) in r["times"].items() if e}
    for n, (s, e) in sorted(r["times"].items()):
        print(f"- 장면 {n}: {s}초" + (f" · 문법 오류 남음: {e}" if e else ""))
    chk = subprocess.run([sys.executable, "engine/story/bundle.py", "check", sid], cwd=ROOT, capture_output=True, text=True, timeout=600)
    print("\n".join(ln for ln in chk.stdout.splitlines() if ln.startswith(("✗", "△")))[:3000])
    ok("scenes", sec=str(round(time.time() - t0, 1)), scenes=",".join(map(str, sorted(r["times"]))), cost=str(r["cost"]),
       syntax_errors=",".join(map(str, bad)) or "0", check="막힘 있음 — 위 ✗ 를 고칠 장면만 --scenes N --note \"…\" 로 다시" if "✗" in chk.stdout else "통과",
       next=f"python3 engine/produce.py data/storyboards/{sid}.json --prep --bg → produce")
    return 0


if __name__ == "__main__":
    sys.exit(main())
