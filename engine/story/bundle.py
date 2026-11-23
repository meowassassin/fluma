#!/usr/bin/env python3
"""콘티 묶음 — 콘티 · 장면 코드 · 형태 · 조사 사실을 파일 하나로 받아 한 번에 저장하고, 모든 검사를 바로 돌려 묶어서 알린다.

2026-11-19 속도(한 편 15분): 콘티 · 장면 파일 · 형태를 따로 쓰고, 검사 → 고침 → 검사를 여러 번 돌아 도구 왕복이 수십 번이었다.
음성을 만들기 전에 검사를 끝내면 음성 뒤 다시 고칠 일도 준다.

  python3 engine/story/bundle.py script <대본.json>     # ① 대본만(제목 · 장면별 역할 · 대사 · 화면 글자 · 화면 한 줄) — 길이 검사 + 시청자 · 각본가 검토
  python3 engine/story/bundle.py apply <묶음.json>      # ② 통과한 대본 그대로 콘티 · 장면 코드 · 형태 → 저장 + 검사 → 막힘(L)만 고쳐 다시 apply
  python3 engine/story/bundle.py check <id>             # 저장된 콘티를 다시 검사만
2026-11-22 대본 먼저: 시청자 검토가 대본을 돌려보내면 콘티 · 장면 코드 · 형태까지 다시 썼다(한 번 80초~수 분). 대본을 먼저 통과시키면
되돌아갈 때 대사만 고친다. 검토 기준 · 횟수는 produce 와 같다(통과 기록 approved.json 을 produce 가 그대로 쓴다).
대본 형식:
  {"id", "title", "format"?, "audience"?, "allow_long"?, "voice"?, "concepts_order"?,
   "scenes": [{"role": "hook|…|outro", "narration": "말", "caption": "화면 글자", "screen": "화면에 보일 것 한 줄"}],
   "research": {"facts": [{"claim", "value", "source"}]}}                        # 선택 — 사실은 여기서 저장(각본가가 이것만 쓴다)
묶음 형식:
  {"storyboard": {…콘티 전체…},
   "files": {"scenes/s01.jsx": "장면 코드", "forms/duck.json": {…형태…}},       # data/compositions/<id>/ 아래
   "research": {"facts": [{"claim", "value", "source"}], "visual_entities": […]}}   # 선택 — data/research/<id>.json + 기획 기록에 연결
콘티 안에서는 "$FILE:data/compositions/<id>/scenes/s01.jsx" 처럼 가리킨다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(ROOT / "engine" / "checks"))
from result import fail, ok  # noqa: E402


def _form_problems(sid: str) -> list[str]:
    """형태 파일이 계산되는지(문법 · 도형 칸) — 렌더 전에"""
    out = []
    try:
        from craft.form import sdf
    except Exception:  # noqa: BLE001
        return out
    for f in sorted((ROOT / "data" / "compositions" / sid / "forms").glob("*.json")):
        try:
            sdf.compile_scene(json.loads(f.read_text("utf-8")))
        except Exception as e:  # noqa: BLE001
            out.append(f"L39 형태 {f.name}: {str(e)[:120]}")
    return out


def check(sid: str) -> tuple[list[str], list[str]]:
    import lint
    sb = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
    fails = lint.lint(sb, [t for t in lint.recent_titles() if t != sb.get("title")])
    hard = [f"{c} {'' if i is None else f'장면{i + 1} '}{m}" for c, i, m in fails if not c.startswith("T")]
    soft = [f"{c} {'' if i is None else f'장면{i + 1} '}{m}" for c, i, m in fails if c.startswith("T")]
    # 2026-11-21 속도(품질 그대로): 빌드 뒤 · LLM 검토에서 막던 것을 쓰는 자리에서 — 화면 AI 티(visual_tell)와 형태 프레임 잘림.
    # 같은 검사를 앞당길 뿐이다(제작 단계도 그대로 다시 잰다). 지난 영상: 렌더 전 검토에서 4번 막혀 9분
    try:
        import quality_gate as qg
        import visual_tell as vt
        for x in vt.find(sb, sid):
            if qg.waived(sb, x):
                continue
            (hard if x["block"] else soft).append(f"{x['code']} {x['msg']}")
    except Exception as e:  # noqa: BLE001
        soft.append(f"V00 화면 AI 티 검사 못 함: {e}")
    return hard + _form_problems(sid) + _form_cuts(sid), soft


def _form_cuts(sid: str) -> list[str]:
    """형태 움직임 프레임이 화면 가장자리에서 잘리는지(받침판 · 소품) — 클로즈업(카메라 focus)은 일부러 자른 것이라 뺀다"""
    from PIL import Image
    sys.path.insert(0, str(ROOT / "engine"))
    from craft import form
    out = []
    for d in sorted((ROOT / "data" / "compositions" / sid / "forms").glob("*.anim")):
        try:
            src = json.loads((d.parent / f"{d.stem}.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        cam = src.get("camera") or {}
        if cam.get("focus") is not None or (src.get("anim") or {}).get("tracks", {}).get("camera"):
            continue
        fr = sorted(d.glob("f*.png"))
        sides = sorted({x for f in fr[:: max(1, len(fr) // 3)][:4] for x in form.edge_cut(Image.open(f))})
        if sides:
            out.append(f"L40 형태 {d.stem}: 프레임 {' · '.join(sides)} 가장자리에서 형태가 잘린다 — 바닥 받침판이면 \"floor\": true, 소품이면 카메라 radius 를 키우거나 형태를 안으로")
    return out


def normalize(sb: dict) -> list[str]:
    """뜻이 바뀌지 않는 형식 오타만 바로잡는다 — 정수 칸의 소수(반올림) · 허용 목록 값의 철자 차이(가장 가까운 값).
    2026-11-21: 콘티 검사 왕복 5번 중 3번이 이런 것(duration_sec 30.6 · screen '실제 사진')이었다. 문구 길이 같은 내용 오류는 그대로 둔다"""
    import difflib
    try:
        import jsonschema
        schema = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    notes = []
    for _ in range(3):
        changed = False
        def flat(errs):                                   # anyOf · oneOf 안쪽 오류까지(효과음 sfx 는 anyOf 로 정의돼 겉에는 anyOf 하나만 보인다)
            for x in errs:
                yield x
                if x.context:
                    yield from flat(x.context)
        for e in flat(jsonschema.Draft202012Validator(schema).iter_errors(sb)):
            path = list(e.absolute_path)
            if not path:
                continue
            parent = sb
            for k in path[:-1]:
                parent = parent[k]
            key, val = path[-1], e.instance
            if e.validator == "type" and e.validator_value == "integer" and isinstance(val, float):
                parent[key] = int(round(val)); notes.append(f"{'/'.join(map(str, path))}: {val} → {parent[key]}"); changed = True
            elif e.validator == "enum" and isinstance(val, str):
                opts = [o for o in e.validator_value if isinstance(o, str)]
                near = difflib.get_close_matches(val, opts, n=1, cutoff=0.8)   # 철자 · 띄어쓰기 차이만(뜻이 다른 값으로 바꾸지 않는다)
                if near:
                    parent[key] = near[0]; notes.append(f"{'/'.join(map(str, path))}: '{val}' → '{near[0]}'"); changed = True
                elif "sfx" in map(str, path) and key == "name" and len(path) >= 3:   # 없는 효과음(감독 단계가 지어낸 이름) — 그 효과음만 뺀다
                    holder = sb
                    for k in path[:-2]:
                        holder = holder[k]
                    holder.pop(path[-2]); notes.append(f"{'/'.join(map(str, path[:-1]))}: 없는 효과음 '{val}' 뺌"); changed = True
                    break
        if not changed:
            break
    return notes


def apply(path: Path) -> str:
    b = json.loads(path.read_text("utf-8"))
    sb = b.get("storyboard")
    if not isinstance(sb, dict) or not sb.get("id"):
        fail("bundle", stage="read", error="storyboard(id 포함)가 필요합니다")
    sid = sb["id"]
    comp = ROOT / "data" / "compositions" / sid
    for rel, body in (b.get("files") or {}).items():
        f = (comp / rel).resolve()
        if comp.resolve() not in f.parents:
            fail("bundle", stage="files", error=f"영상 폴더 밖 경로: {rel}")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=1), "utf-8")
    if isinstance(b.get("research"), dict):
        _save_research(sid, b["research"], sb)
    try:                                                # 맨 위 script(' / ' 로 장면 경계)를 장면 나레이션에 나눠 넣는다 — 대본 확정 대조(S01)가 장면 칸을 본다
        sys.path.insert(0, str(ROOT / "engine" / "story"))
        import script as _script
        _script.apply(sb)
    except ValueError as e:
        fail("bundle", stage="script", error=str(e))
    except Exception:  # noqa: BLE001
        pass
    for note in normalize(sb):                          # 뜻이 같은 형식 오타만(정수 칸 소수 · 허용 값 철자 · 없는 효과음) — 검사 왕복 한 번을 아낀다
        print(f"- 형식 바로잡음: {note}")
    sp = ROOT / "data" / "storyboards" / f"{sid}.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    if sp.exists():
        shutil.copyfile(sp, sp.with_suffix(".json.prev"))
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return sid


def _save_research(sid: str, research: dict, sb: dict) -> None:
    rf = ROOT / "data" / "research" / f"{sid}.json"
    rf.parent.mkdir(parents=True, exist_ok=True)
    rf.write_text(json.dumps(research, ensure_ascii=False, indent=1), "utf-8")
    if (ROOT / "data" / "shotplans" / f"{sid}.json").exists():
        subprocess.run([sys.executable, "engine/gen/plan.py", "research", sid], cwd=ROOT, capture_output=True, text=True, timeout=60)
    srcs = [f.get("source") for f in research.get("facts") or [] if str(f.get("source") or "").startswith("http")]
    sb["sources"] = list(dict.fromkeys((sb.get("sources") or []) + srcs))


def script_problems(sb: dict) -> list[str]:
    """대사만으로 볼 수 있는 막힘 — 장면 대사 길이 · 전체 길이(글자 수 어림) · 장면 수 · 훅 길이 · 끝이 훅으로 돌아오는지(L08)"""
    import lint
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import skill_pass as sp
    out = []
    scenes = sb.get("scenes") or []
    try:                                          # 2026-11-23 시험 10: 대본의 role(myth · mechanism)이 통과한 뒤 apply 에서 막혔다
        sch = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
        roles, formats = sch["$defs"]["scene"]["properties"]["role"]["enum"], sch["properties"]["format"]["enum"]
    except (OSError, ValueError, KeyError):
        roles = formats = None
    if formats and sb.get("format") not in formats:
        out.append(f"L01 format '{sb.get('format')}' — 허용: {' | '.join(formats)}")
    for i, x in enumerate(scenes, 1):
        if roles and x.get("role") not in roles:
            out.append(f"L01 장면{i} role '{x.get('role')}' — 허용: {' | '.join(roles)}")
        n = len(str(x.get("narration") or ""))
        if n > sp.NARRATION_MAX:
            out.append(f"L01 장면{i} 대사 {n}자 > {sp.NARRATION_MAX}자")
        if len(str(x.get("caption") or "").replace("\n", "")) > 28:
            out.append(f"L01 장면{i} 화면 글자 28자 넘음")
    out += [f"{c} {m}" for c, m in lint.scope_problems(sb, estimate=True)]
    cps = lint.voice_cps(sb)
    hook = next((i for i, x in enumerate(scenes) if x.get("role") == "hook"), None)
    if hook is not None:
        hsec = len(str(scenes[hook].get("narration") or "").replace(" ", "")) / cps
        if hsec > lint.LIM["hook_sec_max"] + 0.5:
            out.append(f"L05 장면{hook + 1} 훅 대사 약 {hsec:.1f}초 > {lint.LIM['hook_sec_max']}초")
    outro = next((x for x in scenes if x.get("role") in ("outro", "cta")), None)
    if hook is not None and outro is not None:
        hk = lint._keywords(f"{scenes[hook].get('caption', '')} {scenes[hook].get('narration', '')}")
        if not hk & lint._keywords(f"{outro.get('caption', '')} {outro.get('narration', '')}"):
            out.append("L08 마지막 장면이 훅의 핵심어를 다시 말하지 않음")
    return out


def screen_rules() -> str:
    """화면(콘티 · 장면 코드)을 쓰기 전에 알아야 할 막힘 — 2026-11-22 시험 9: 쓴 뒤 apply 3번 + 제작 1번을 이것들로 되돌아갔다
    (format · role 허용 값, 정수 칸, 지어낸 효과음, 어두운 바탕 · 같은 바탕 · 빛번짐 · 둥근 카드, 자막 자리와 겹침). 규칙은 검사(lint · visual_tell)와 같다"""
    try:
        sch = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
        fmt = sch["properties"]["format"].get("enum") or []
        role = sch["$defs"]["scene"]["properties"]["role"].get("enum") or []
    except (OSError, ValueError, KeyError):
        fmt, role = [], []
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import skill_pass as sp
    return "\n".join([
        "화면을 쓰기 전에(어기면 apply · 제작이 막힌다):",
        f"- format: {' | '.join(fmt)} · 장면 role: {' | '.join(role)} · duration_sec 은 정수 · 효과음 sfx name: {' | '.join(sp.sfx_names())}",
        "- 바탕(K.scene 두 번째 인자): 장면의 장소 · 물건 색에서. 어두운 바탕은 장면의 절반 이하, 이야기의 장이 바뀌면 바탕 색을 바꾼다(7장면이면 4가지 이상)",
        "- 빛번짐(glow) · 흔들기(shake) · 렌즈 빛 금지. 둥근 카드 · 알약 상자는 장면에 하나까지 — 정보는 장면 속 물건(표지판 · 라벨 · 손글씨)에",
        "- 본문 장면마다 숫자 · 고유명사 · 화면 재료 중 하나(L11)",
        "- 자막(나레이션)은 엔진이 화면 아래(y 약 1270~1420)에, 장면 caption 은 위(y 약 60~240)에 그린다 — 그 두 띠와 오른쪽 12%(버튼)에는 글자 · 주인공을 두지 않는다",
    ])


def script(path: Path) -> int:
    """① 대본 단계 — 길이 검사(LLM 없음) → 시청자 → 각본가 → 시청자(produce 의 이해 관문과 같은 순서 · 횟수). 통과하면 확정 대본을 찍는다"""
    s = json.loads(path.read_text("utf-8"))
    s = s.get("storyboard") if isinstance(s.get("storyboard"), dict) else s
    sid = s.get("id")
    if not sid or not s.get("scenes"):
        fail("bundle", stage="script", error="id 와 scenes(장면별 role · narration · caption · screen)가 필요합니다")
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    sb = {k: v for k, v in s.items() if k not in ("research", "scenes")}
    sb.setdefault("version", 1)
    if isinstance(s.get("research"), dict):
        _save_research(sid, s["research"], sb)
    if isinstance(s.get("script"), str) and s["script"].strip():   # 대본을 한 덩어리(' / ')로 썼으면 장면에 나눈다
        import script as _script
        ps = _script.pieces(s["script"])
        if len(ps) != len(s["scenes"]):
            fail("bundle", stage="script", error=f"script 조각 {len(ps)}개 ≠ 장면 {len(s['scenes'])}개")
        for x, p_ in zip(s["scenes"], ps):
            x["narration"] = p_
        sb.pop("script", None)
    sb["scenes"] = [{"role": x.get("role"), "narration": x.get("narration") or "", "caption": x.get("caption") or "",
                     "materials": [{"type": "note", "what": x["screen"]}] if x.get("screen") else []} for x in s["scenes"]]
    probs = script_problems(sb)
    if probs:
        for x in probs:
            print(f"✗ {x}")
        fail("bundle", stage="script", error=f"대본 막힘 {len(probs)}건 — 대본만 고쳐 다시 script", hard=str(len(probs)))
    sbp = ROOT / "data" / "compositions" / sid / "script.sb.json"
    sbp.parent.mkdir(parents=True, exist_ok=True)
    sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1), "utf-8")
    r = subprocess.run([sys.executable, "engine/story/skill_pass.py", "comprehension", str(sbp), "--write"], cwd=ROOT, capture_output=True, text=True, timeout=1500)
    err = next((ln[6:] for ln in r.stdout.splitlines() if ln.startswith("error=")), "")
    if r.returncode != 0:
        cur = json.loads(sbp.read_text("utf-8"))        # 각본가가 이미 고친 대사 — 여기서부터 고친다(처음 대본으로 되돌리지 않게)
        print("지금 대본(각본가가 고친 것 — 이걸 고쳐 다시 script):")
        print(f"- 제목: {cur.get('title')}")
        for i, x in enumerate(cur["scenes"], 1):
            print(f"- 장면{i} [{x.get('role')}] 말: {x.get('narration')} | 화면 글자: {x.get('caption')}")
        fail("bundle", stage="script", error=(err or "시청자 검토 막힘") + " — 대본만 고쳐 다시 script(콘티 · 장면은 아직 쓰지 않는다)")
    done = json.loads(sbp.read_text("utf-8"))
    probs = script_problems(done)                       # 각본가가 고친 뒤에도 길이 검사 통과인지
    if probs:
        fail("bundle", stage="script", error="각본가가 고친 대본이 길이 검사에 걸림: " + " · ".join(probs) + " — 대본만 줄여 다시 script")
    print("확정 대본(콘티에 글자 그대로 옮긴다 — 바꾸면 검토를 다시 받는다):")
    print(f"- 제목: {done.get('title')}")
    for i, x in enumerate(done["scenes"], 1):
        print(f"- 장면{i} [{x.get('role')}] 말: {x.get('narration')} | 화면 글자: {x.get('caption')}")
    print(screen_rules())
    ok("bundle", stage="script", file=str(sbp.relative_to(ROOT)), next="이 대본 그대로, 위 '화면을 쓰기 전에' 를 지켜 콘티 · 형태 · 장면 코드를 묶음으로 써서 bundle.py apply 한 번")
    return 0


def main() -> int:
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("apply", "check", "script"):
        print(__doc__); return 2
    if a[0] == "script":
        return script(Path(a[1]) if Path(a[1]).is_absolute() else ROOT / a[1])
    sid = apply(Path(a[1]) if Path(a[1]).is_absolute() else ROOT / a[1]) if a[0] == "apply" else a[1]
    hard, soft = check(sid)
    if a[0] == "apply":
        sys.path.insert(0, str(ROOT / "engine" / "story"))
        import skill_pass as _sp
        sbp = ROOT / "data" / "storyboards" / f"{sid}.json"
        if not _sp.is_approved(sbp):                    # 대본이 검토받은 것과 다르다(또는 검토 전) — 화면을 다 쓴 뒤 되돌아가지 않게
            hard.insert(0, "S01 대사 · 제목이 검토를 통과한 대본과 다름(또는 검토 전) — bundle.py script 로 대본부터 통과시키고, 확정 대본을 글자 그대로 콘티에 옮긴다")
    for x in hard:
        print(f"✗ {x}")
    for x in soft[:12]:
        print(f"△ {x}")
    rel = f"data/storyboards/{sid}.json"
    if hard:
        fail("bundle", stage="check", error=f"막힘 {len(hard)}건 — 전부 한 번에 고친다(묶음을 Write 로 통째로 다시 쓰거나 Edit 를 한 응답에 나란히) → 다시 apply 한 번", file=rel, hard=str(len(hard)), soft=str(len(soft)))
    ok("bundle", file=rel, soft=str(len(soft)), next=f"python3 engine/produce.py {rel} --prep --bg → 재료 · 장면 확인 → python3 engine/produce.py {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
