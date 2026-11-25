#!/usr/bin/env python3
"""스킬 단계 — 콘티에 스킬을 '파이프라인으로' 적용한다(권고 · 검사 땜질 대신).
2026-11-11 점검: 감독 · 각본가 · 디자이너 스킬은 에이전트가 읽기만 했고, 엔진은 그 칸을 거의 안 읽었다.
그래서 단계마다 해당 SKILL.md 를 지시문으로 내 Claude Code(헤드리스 `claude -p`)를 불러, 그 스킬이 맡은 칸만 고친 결과를 받아 적용한다.

  python3 engine/story/skill_pass.py all <콘티.json>            # writer → director → designer(+ Astryx 앱 화면)
  python3 engine/story/skill_pass.py writer <콘티.json> [--force]
  python3 engine/story/skill_pass.py status <콘티.json>          # 단계별 마지막 실행 · 바뀐 칸

단계가 고칠 수 있는 칸(허용 목록 밖은 버린다):
  writer   (writer + humanizer-ko)  script · 장면 caption · title — aitell.py 가 찾은 문제를 같이 넘긴다
  director (director)              direction.anchors · 장면 shot_fn · beats(확대 · 표시) · sfx (장면 길이는 음성 단계가 정한다)
  designer (designer + crafts 의 Astryx 절) direction.layout · subs · screen_text_y · font_title · font_body · cam_push · 재료 adjust · 앱 화면(ui_mock → Astryx .tsx)
기록: data/compositions/<id>/skill_pass/<단계>.json (입력 해시 · 고친 것 · 이유 · 비용). 입력이 그대로면 다시 부르지 않는다(--force 로 강제).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402


def _log_skill_timing(sid: str, phase: str, sec: float, **extra) -> None:
    sec = round(sec, 1)
    print(f"[스킬 타이밍] {phase} {sec}초", flush=True)
    try:
        p = ROOT / "data" / "workspace" / "results" / "skill-pass-timings.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"id": sid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "phase": phase, "sec": sec, **extra}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass

SKILLS = ROOT / ".claude" / "skills"
SHOT_FN = ["자리 잡기", "힘", "압박", "디테일", "반응", "변화", "충격", "여운", "끝"]
ANCHORS = ["emotion", "motif", "object", "break", "final_image"]


def skill_text(name: str) -> str:
    t = (SKILLS / name / "SKILL.md").read_text("utf-8")
    return re.sub(r"^---[\s\S]*?---\n", "", t)


def sfx_names() -> list[str]:
    """고를 수 있는 효과음 — 파일이 있고 콘티 형식(스키마)이 허용하는 이름만.
    2026-11-22 시험 9: assets/sfx/bleep.wav 가 있어 감독 단계에 'bleep' 을 보여 줬지만 형식이 막아 제작이 한 번 멈췄다"""
    names = set()
    for d in (ROOT / "assets" / "sfx", ROOT / "engine" / "assets" / "sfx"):
        names.update(p.stem for p in d.glob("*.wav")) if d.exists() else None
    try:
        sch = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
        allowed = set(sch["$defs"]["scene"]["properties"]["sfx"]["anyOf"][1]["items"]["properties"]["name"]["enum"])
        names &= allowed
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return sorted(names)


def view(sb: dict, design: bool = False) -> dict:
    """에이전트에게 보일 콘티(제작 칸만 — 긴 refine 스크립트 등은 뺀다)"""
    sc = []
    for i, s in enumerate(sb.get("scenes") or [], 1):
        sc.append({"n": i, "role": s.get("role"), "sec": s.get("sec"), "beat": s.get("beat"), "screen": s.get("screen"), "shot_fn": s.get("shot_fn"),
                   "narration": s.get("narration"), "caption": s.get("caption"), "beats": s.get("beats"), "sfx": s.get("sfx"),
                   "materials": [{k: m.get(k) for k in ("id", "type", "what", "cue", "value", "label", *(("adjust", "ui") if design else ())) if m.get(k) is not None} for m in s.get("materials") or []]})
    d = sb.get("direction") or {}
    return {"id": sb.get("id"), "format": sb.get("format"), "duration_sec": sb.get("duration_sec"), "title": sb.get("title"), "audience": sb.get("audience"),
            "intent": sb.get("intent"), "constraints": sb.get("constraints"), "script": sb.get("script"), "reference": sb.get("reference"),
            "direction": {k: d.get(k) for k in ("anchors", "layout", "captions", "motion", "color_bg", "color_text", "color_accent", "feel", *(("subs", "font_title", "font_body", "cam_push", "screen_text_y") if design else ())) if k in d},
            "scenes": sc}


def facts(sb: dict) -> list[str]:
    """조사 파일(출처 URL 이 콘티 sources 와 겹치는 것)의 사실 — 각본가가 없는 수치를 지어내지 않게"""
    src = set(sb.get("sources") or [])
    out = []
    for f in (ROOT / "data" / "research").glob("*.json"):
        try:
            r = json.loads(f.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        fs = r.get("facts") or []
        if any(x.get("source") in src for x in fs):
            out += [f"{x.get('claim')} ({x.get('value')}) — {x.get('source')}" for x in fs]
    return out


def ref_review(sbp: Path) -> str:
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "story" / "review.py"), str(sbp)], capture_output=True, text=True, timeout=120)
    return r.stdout[:6000]


def claude(system: str, prompt: str, timeout: int = 900, tools: str = "", dirs: list[str] | None = None, allowed: list[str] | None = None, cwd: str = "/tmp") -> tuple[dict, float]:
    """설정된 에이전트(Claude Code · Codex · Antigravity)를 헤드리스로 불러 JSON 하나를 돌려받는다."""
    from agent_cli import extract_json, run_agent
    txt, cost = run_agent(
        system,
        prompt,
        override_env="FLUMA_SKILL_RUNTIME",
        timeout=timeout,
        tools=tools,
        dirs=dirs,
        allowed=allowed,
        cwd=cwd,
    )
    return extract_json(txt), cost


SYS = ("너는 Fluma 쇼츠 제작 파이프라인의 '{role}' 단계다. 아래 스킬 문서를 규칙 그대로 적용해 콘티를 고친다. "
       "추측으로 사실 · 수치를 만들지 않는다(조사 사실 목록에 있는 것만). 출력은 JSON 하나뿐 — 설명 문장 없이. 형식: {fmt}")


# ── 단계별: 프롬프트 · 적용 ──
def brief(items: list, n: int = 4, w: int = 90) -> str:
    """에이전트에게 돌려줄 짧은 목록 — 항목마다 w 자, n 개까지(전문은 파일). 2026-11-20: 시청자 지적 전문(수백 자)이 매번 대화에 쌓여 컨텍스트가 커졌다"""
    out = [str(x)[:w] + ("…" if len(str(x)) > w else "") for x in items[:n]]
    return " / ".join(out) + (f" 외 {len(items) - n}건" if len(items) > n else "")


def _baseline_path(sid: str, name: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "skill_pass" / f"{name}_baseline.json"


def _sb_shape(sid: str) -> dict:
    """기준 목록이 유효한 콘티 모양 — 장면 수와 장면별 대사 · 화면 글자"""
    try:
        sb = json.loads((ROOT / "data" / "storyboards" / f"{sid}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    sc = sb.get("scenes") or []
    return {"n": len(sc), "text": [hashlib.sha1(f"{x.get('narration')}|{x.get('caption')}".encode()).hexdigest()[:10] for x in sc]}


def baseline(sid: str, name: str) -> list:
    """첫 판정이 막은 문제 목록(수렴 기준) — 다음 판정은 이것이 풀렸는지만 본다. 없으면 [].
    2026-11-24: 기준이 한 번도 지워지지 않아, 장면을 넣고 빼거나 대사를 크게 고친 뒤에도 옛 번호의 문제로 막거나 새 문제를 권고로만 흘렸다 →
    장면 수가 달라졌거나 장면 절반 넘게 대사가 바뀌면 기준을 버리고 처음 판정으로 돌아간다"""
    try:
        rec = json.loads(_baseline_path(sid, name).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    shape, now = rec.get("shape") or {}, _sb_shape(sid)
    if shape and now and (shape.get("n") != now.get("n") or sum(a != b for a, b in zip(shape.get("text") or [], now.get("text") or [])) * 2 > now.get("n", 0)):
        try:
            _baseline_path(sid, name).unlink()
        except OSError:
            pass
        return []
    return rec.get("items") or []


def _verify_block(items: list, key: str) -> str:
    return ("\n\n# 확인 모드 — 앞선 판정이 짚은 문제 목록(이것만 판정한다)\n" + json.dumps(
        [{"id": i + 1, "scene": x.get("scene"), "kind": x.get("kind"), "what": x.get("what")} for i, x in enumerate(items)], ensure_ascii=False) +
        f"\n할 일을 바꾼다: 위 목록의 항목마다 지금 콘티에서 풀렸는지만 판정해 '{key}' 칸에 [{{\"id\": 번호, \"resolved\": true|false, \"why\": \"짧게\"}}] 로 낸다. "
        "목록에 없는 새 문제는 'new' 칸에 권고로만 적는다(막지 않는다). 기준을 바꾸지 말 것 — 고쳐졌으면 resolved: true.")


def converge(sid: str, name: str, patch: dict, list_key: str, is_blocking) -> dict:
    """수렴(2026-11-20 실측: 시청자 · 검토 판정이 부를 때마다 새 문제를 찾아 7편 중 5편이 상한 4번까지 반복).
    첫 판정: 막는 문제를 기준 목록으로 저장. 다음부터: 기준 중 아직 안 풀린 것만 막고, 새 지적은 advice(권고)로."""
    base = baseline(sid, name)
    items = [x for x in (patch.get(list_key) or []) if isinstance(x, dict)]
    if not base:
        blocking = [x for x in items if is_blocking(x)]
        if blocking:
            bp = _baseline_path(sid, name); bp.parent.mkdir(parents=True, exist_ok=True)
            bp.write_text(json.dumps({"items": blocking, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "shape": _sb_shape(sid)}, ensure_ascii=False, indent=1), "utf-8")
        return patch
    ver = {int(v.get("id", 0)): v for v in (patch.get("verify") or []) if isinstance(v, dict)}
    left = [x for i, x in enumerate(base, 1) if not (ver.get(i) or {}).get("resolved")]
    out = dict(patch)
    out[list_key] = left
    adv = []
    for x in (patch.get("new") or []) + [y for y in items if y not in left]:
        if isinstance(x, dict) and x not in adv:
            adv.append(x)
    out["advice"] = adv[:12]
    out["converge"] = {"base": len(base), "left": len(left)}
    if "score" in out:
        out["score"] = 8 if not [x for x in left if is_blocking(x)] else min(int(out.get("score") or 6), 6)
    return out


def viewer_io(sb: dict, sbp: Path) -> tuple[str, str]:
    """시청자 시뮬레이션 — 콘티의 대상 시청자가 장면 순서대로 따라가며 이해가 끊기는 곳을 짚는다(2026-11-11: 개념을 설명 없이 던져 '이해가 안 된다')"""
    fmt = ('{"known_before": ["시청자가 이미 아는 것"], "issues": [{"scene": 번호, "kind": "처음 보는 말|설명 없는 숫자|흐름 끊김|왜?|넘김|도입 약함|슬라이드 쇼", "what": "걸린 말 · 화면", '
           '"fix_by": "writer(대사로 풀림)|story(장면을 더하거나 순서를 바꿔야 함)", "how": "어떻게 풀면 되나"}], "understood": "끝까지 본 뒤 내가 이해한 한 줄", "score": 0~10}')
    v = view(sb)
    seq = [{"n": x["n"], "말": x["narration"], "화면 글자": x["caption"], "화면": [m.get("what") or m.get("type") for m in x["materials"]]} for x in v["scenes"]]
    p = (f"# 너는 이 사람이다\n{sb.get('audience') or '이 주제를 처음 보는 일반인'} — 이 주제를 따로 공부한 적은 없다. 쇼츠를 넘기다 이 영상을 처음 본다.\n\n"
         f"# 장면 순서대로 보이는 것(소리 · 화면 글자 · 화면)\n{json.dumps(seq, ensure_ascii=False)}\n\n"
         "할 일: 한 장면씩 차례로 본다. 그 시점까지 나온 것만 안다고 치고, 처음 보는 낱말 · 무엇의 숫자인지 모르는 숫자 · 앞 장면과 이어지지 않는 점프 · '그래서 왜?'가 드는 곳 · 넘기고 싶은 곳을 모두 적는다. "
         "작가 편을 들지 말고 진짜 처음 보는 사람처럼 냉정하게. "
         "또 첫 장면에서 엄지가 멈췄는지 본다 — 예시 · 질문 · 상황 · 증거 없이 정의 · 설명으로 시작하면 kind '도입 약함'(fix_by story). "
         "장면들이 설명 · 정의만 차례로 넘기는 슬라이드 같으면(보여 주는 예시 · 상황 · 반전이 없음) kind '슬라이드 쇼'(fix_by story, how 에 어느 장면을 예시 · 상황으로 바꿀지). "
         "다 보고 나서 내가 이해한 한 줄과 이해도 점수를 준다.")
    base = baseline(sb["id"], "viewer")
    if base:
        p += _verify_block(base, "verify")
    return SYS.format(role="시청자", fmt=fmt), p


def viewer_apply(sb: dict, patch: dict) -> list[str]:
    return []                                   # 콘티를 고치지 않는다 — 걸린 것을 writer · story 로 넘긴다


def cue_words(sb: dict) -> dict[int, list[str]]:
    """장면마다 화면이 맞춰 둔 낱말 — 장면 코드 · 재료의 $CUE:낱말, beats[].at, 재료 cue.
    2026-11-19 실측: 각본가가 제작 단계에서 대사를 다듬어 이 낱말이 사라지면, 에이전트가 장면 코드의 신호 낱말을 다시 맞추느라 왕복했다"""
    import re as _re
    from craft.cues import CUE
    out: dict[int, list[str]] = {}

    def walk(x, acc):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("cue", "at") and isinstance(v, str) and v.strip() and not v.startswith("$"):
                    acc.append(v.strip())
                walk(v, acc)
        elif isinstance(x, list):
            for v in x:
                walk(v, acc)

    for i, sc in enumerate(sb.get("scenes") or []):
        acc: list[str] = []
        walk({k: v for k, v in sc.items() if k not in ("narration", "caption")}, acc)
        txt = json.dumps(sc, ensure_ascii=False)
        for ref in _re.findall(r"\$FILE:([^\"\s]+)", txt):
            try:
                txt += (ROOT / ref).read_text("utf-8")
            except OSError:
                pass
        acc += [m.group(1).strip() for m in CUE.finditer(txt)]
        nar = str(sc.get("narration") or "")
        words = [w for w in dict.fromkeys(acc) if w and _re.sub(r"\s", "", w) in _re.sub(r"\s", "", nar)]   # 지금 대사에 있는 것만(검사용 숫자 · 위치 이름은 빠진다)
        if words:
            out[i] = words
    return out


def writer_io(sb: dict, sbp: Path) -> tuple[str, str]:
    import aitell
    found = aitell.find(sb)
    fmt = '{"script": "장면 경계 / 로 나눈 전체 대본(장면 수와 같은 칸 수)", "captions": {"장면 번호": "화면 글자(28자 이하, 말을 받아 적지 않음)"}, "title": "고정 제목(24자 이하)", "why": ["고친 이유"]}'
    p = (f"# 스킬: writer\n{skill_text('writer')}\n\n# 함께: humanizer-ko\n{skill_text('humanizer-ko')[:9000]}\n\n"
         f"# 조사 사실(이것만 쓴다)\n" + "\n".join(facts(sb)) + "\n\n# 레퍼런스와 견준 검토표\n" + ref_review(sbp) +
         f"\n\n# 시청자 시뮬레이션이 걸린 곳(대사로 풀 것 — 개념은 쓰기 전에 쉬운 말로 소개, 숫자는 무엇의 숫자인지 먼저)\n{json.dumps(viewer_issues(sb, 'writer') + viewer_issues(sb, 'story'), ensure_ascii=False)}"
         f"\n\n# 감지기가 찾은 AI 티(꼭 고친다)\n{json.dumps(found, ensure_ascii=False)}\n\n# 길이 예산(넘기면 음성 뒤 검사 L70 · L05 에 막혀 대본을 다시 고치게 된다)\n{length_budget(sb)}"
         f"\n\n# 사용자 요구(어기면 이 답은 버려진다 — 톤 · 시제 · 금지어까지 그대로 지킨다)\n{must_block(sb)}"
         f"\n\n# 사람이 직접 정한 칸(이 값 그대로 돌려준다)\n{json.dumps(sorted(text_locks(sb)), ensure_ascii=False)}"
         f"\n\n# 화면이 맞춰 둔 낱말(장면 번호: 낱말 — 대사를 고쳐도 이 낱말은 그 장면 대사에 글자 그대로 남긴다. 빠지면 그 장면 수정은 버려진다)\n{json.dumps({str(k + 1): v for k, v in cue_words(sb).items()}, ensure_ascii=False)}"
         f"\n\n# 콘티\n{json.dumps(view(sb), ensure_ascii=False)}\n\n"
         "할 일: writer 스킬 5장 '내기 전 스스로 검사'를 모두 통과하게 script · caption · title 을 고친다. 장면 수와 순서는 그대로. 뜻(사실)은 바꾸지 않는다. "
         "길이 예산을 넘기지 않는다(줄일 때는 곁가지를 덜고, 늘릴 이유가 없으면 늘리지 않는다). 고칠 게 없으면 원래 값을 그대로 돌려준다.")
    return SYS.format(role="각본가", fmt=fmt), p


def _narration_max() -> int:
    try:
        s = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
        return int(json.dumps(s).split('"narration": {"type": "string", "maxLength": ', 1)[1].split(",", 1)[0])
    except (OSError, ValueError, IndexError):
        return 60


NARRATION_MAX = _narration_max()   # 콘티 스키마의 장면 대사 한도(lint L01)


def length_budget(sb: dict) -> str:
    """각본가가 쓰기 전에 아는 길이 상한 — 2026-11-18: 11-17 제작 9편에서 각본가 126번(137분) · 시청자 155번(82분).
    각본가가 예산 없이 쓰면 음성 뒤 L70(전체) · L05(훅)에 막혀 대사를 줄이고, 줄인 대사가 승인을 깨 검토가 처음부터 다시 돌았다"""
    import lint
    scenes = sb.get("scenes") or []
    speed = float((sb.get("voice") or {}).get("speed") or 1.0) or 1.0
    cps = lint.SPEECH_CPS * speed
    mx = lint.LONG_MAX_SEC if sb.get("allow_long") else lint.SCOPE_MAX_SEC.get(sb.get("format") or "", 40)
    now = [len(str(x.get("narration") or "").replace(" ", "")) for x in scenes]
    rows = [f"- 전체 나레이션(공백 뺀 글자): 지금 {sum(now)}자 / 상한 {int(mx * cps * 0.92)}자({mx}초 · 초당 {cps:.1f}자)",
            f"- 장면 하나의 나레이션: 공백 포함 {NARRATION_MAX}자 이하(넘긴 장면은 버려진다)"
            + "".join(f" · {i + 1}장면 지금 {len(str(x.get('narration') or ''))}자" for i, x in enumerate(scenes) if len(str(x.get("narration") or "")) > NARRATION_MAX - 8)]
    hook = next((i for i, x in enumerate(scenes) if x.get("role") == "hook"), None)
    if hook is not None:
        try:
            hmax = max(lint.LIM["hook_sec_max"], lint.ref_first_shot(sb) + 0.5)
        except Exception:  # noqa: BLE001 - 레퍼런스 카드가 없을 때
            hmax = lint.LIM["hook_sec_max"]
        rows.append(f"- 훅(장면 {hook + 1}): 지금 {now[hook]}자 / 상한 {int(hmax * cps * 0.95)}자({hmax:.1f}초)")
    return "\n".join(rows)


def viewer_issues(sb: dict, who: str) -> list:
    f = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "viewer.json"
    try:
        iss = (json.loads(f.read_text("utf-8")).get("patch") or {}).get("issues") or []
    except (OSError, ValueError):
        return []
    return [i for i in iss if i.get("fix_by", "writer").startswith(who)]


def _text_fields(sb: dict) -> dict:
    """각본가가 고치는 칸 — 장면 대사 · 화면 글자 · 고정 제목"""
    out = {"title": sb.get("title") or ""}
    for i, s in enumerate(sb.get("scenes") or [], 1):
        out[f"s{i}.narration"] = s.get("narration") or ""
        out[f"s{i}.caption"] = s.get("caption") or ""
    return out


def _locks_path(sid: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "skill_pass" / "text_locks.json"


def text_locks(sb: dict) -> set:
    """사람(에이전트 · 사용자)이 정한 칸 — 각본가가 다시 쓰지 않는다.
    2026-11-18 실측: 각본가가 사용자가 요구한 회고 톤 대사를 현재형으로 되돌려, 에이전트가 손으로 되돌린 뒤 각본가를 또 돌렸다"""
    keys = {str(k) for k in sb.get("locked_text") or []}
    try:
        d = json.loads(_locks_path(sb["id"]).read_text("utf-8"))
        if d.get("scenes") == len(sb.get("scenes") or []):
            keys |= set(d.get("keys") or [])
    except (OSError, ValueError):
        pass
    return keys


def update_text_locks(sb: dict) -> list[str]:
    """각본가가 마지막으로 낸 뒤 누군가 고친 칸을 잠근다(2026-11-18 감사: 각본가가 낸 칸만 잠가, 에이전트가 고친 다른 칸은 되돌릴 수 있었다).
    절반 넘게 바뀌었거나 장면 수가 바뀌면 새 초안으로 보고 잠금을 푼다"""
    sid, n = sb["id"], len(sb.get("scenes") or [])
    try:
        d = json.loads(_locks_path(sid).read_text("utf-8"))
    except (OSError, ValueError):
        d = {}
    keys = set(d.get("keys") or []) if d.get("scenes") == n else set()
    try:
        rec = json.loads((ROOT / "data" / "compositions" / sid / "skill_pass" / "writer.json").read_text("utf-8"))
    except (OSError, ValueError):
        rec = {}
    tout, cur = rec.get("text_out") or {}, _text_fields(sb)
    diff = [k for k in cur if k in tout and cur[k] != tout[k]]
    if len(diff) > len(cur) / 2:          # 콘티를 새로 썼다(초안) — 각본가가 다듬을 차례, 잠금도 새로
        keys, added = set(), []
    else:                                 # 각본가가 낸 뒤 누군가(에이전트 · 사용자 · knob) 고친 칸 = 사람이 정한 칸
        added = [k for k in diff if k not in keys]
        keys |= set(added)
    _locks_path(sid).parent.mkdir(parents=True, exist_ok=True)
    _locks_path(sid).write_text(json.dumps({"scenes": n, "keys": sorted(keys)}, ensure_ascii=False, indent=1), "utf-8")
    return added


def must_block(sb: dict) -> str:
    """사용자 요구(콘티 intent.must · must_not · constraints) — 각본가 · 디자이너가 어기면 안 되는 것"""
    it = sb.get("intent") or {}
    rows = [f"- 꼭: {x}" for x in it.get("must") or []] + [f"- 금지: {x}" for x in it.get("must_not") or []] + [f"- 조건: {x}" for x in sb.get("constraints") or []]
    return "\n".join(rows) or "(없음)"


def _nows(t) -> str:
    import re as _re
    return _re.sub(r"\s", "", str(t))


def writer_apply(sb: dict, patch: dict) -> list[str]:
    ch = []
    scn = sb.get("scenes") or []
    locked = set(patch.get("_locked") or [])
    if isinstance(patch.get("script"), str):
        parts = [x.strip() for x in patch["script"].split("/")]
        speak = [i for i, x in enumerate(scn) if x.get("say") is not False]     # 말 없는 장면(say: false)은 script 칸이 없다(script.py)
        if len(parts) == len(speak) and len(speak) != len(scn):
            full = [""] * len(scn)
            for i, t in zip(speak, parts):
                full[i] = t
            parts = full
        if len(parts) == len(scn) and all(parts[i] for i in speak):
            # 잠근 칸(사람이 고친 대사) · 한도(60자)를 넘긴 칸은 받지 않고 지금 대사를 둔다
            keep = [i for i in speak if f"s{i + 1}.narration" in locked]
            cw = cue_words(sb)       # 화면 신호 낱말이 빠진 장면은 지금 대사를 둔다
            lost = [i for i in speak if i not in keep and i in cw and any(_nows(w) not in _nows(parts[i]) for w in cw[i])]
            keep += lost
            if lost:
                ch.append("신호 낱말이 빠져 그대로 둔 대사: " + ", ".join(f"{i + 1}장면" for i in lost))
            over = [i for i in speak if i not in keep and len(parts[i]) > NARRATION_MAX]
            parts = [scn[i].get("narration") or "" if (i in keep or i in over or i not in speak) else parts[i] for i in range(len(scn))]
            if over:
                ch.append("한도 넘긴 대사 버림: " + ", ".join(f"{i + 1}장면" for i in over))
            if any(parts[i] != (scn[i].get("narration") or "") for i in speak):
                sb["script"] = " / ".join(parts[i] for i in speak)
                for i in speak:
                    scn[i]["narration"] = parts[i]
                ch.append("script")
        else:
            ch.append(f"script 버림(칸 {len(parts)} ≠ 장면 {len(scn)})")
    for k, v in (patch.get("captions") or {}).items():
        i = int(k) - 1
        if 0 <= i < len(scn) and isinstance(v, str) and 0 < len(v) <= 28 and v != scn[i].get("caption") and f"s{i + 1}.caption" not in locked:
            scn[i]["caption"] = v
            ch.append(f"s{i + 1}.caption")
    if isinstance(patch.get("title"), str) and 0 < len(patch["title"]) <= 24 and patch["title"] != sb.get("title") and "title" not in locked:
        sb["title"] = patch["title"]
        ch.append("title")
    return ch


def director_io(sb: dict, sbp: Path) -> tuple[str, str]:
    fmt = ('{"anchors": {"emotion": "", "motif": "", "object": "", "break": "", "final_image": ""}, "scenes": {"장면 번호": {"shot_fn": "' + " | ".join(SHOT_FN) +
           '", "beats": [{"do": "확대|표시", "at": "그 장면 나레이션에 실제로 있는 낱말"}], "sfx": [{"name": "' + " | ".join(sfx_names()) + '", "at": 초, "keep": true}]}}, "why": ["이유"]}')
    p = (f"# 스킬: director\n{skill_text('director')}\n\n# 레퍼런스와 견준 검토표\n{ref_review(sbp)}\n\n# 콘티\n{json.dumps(view(sb), ensure_ascii=False)}\n\n"
         "할 일: director 9장 '내기 전 감독 검사'를 통과하게 다섯 기둥(anchors) · 장면마다 shot_fn · 확대/표시 박자 · 사건 소리를 정한다. "
         "장면 길이(sec)는 음성 단계가 실측으로 정하므로 바꾸지 않는다 — 리듬은 대사 길이(각본가)와 박자로. 바꿀 필요 없는 칸은 빼도 된다.")
    return SYS.format(role="감독", fmt=fmt), p


def director_apply(sb: dict, patch: dict) -> list[str]:
    ch = []
    d = sb.setdefault("direction", {})
    a = patch.get("anchors") or {}
    if all(str(a.get(k) or "").strip() for k in ANCHORS):
        new = {k: str(a[k]) for k in ANCHORS}
        if new != d.get("anchors"):
            d["anchors"] = new
            ch.append("anchors")
    scn = sb.get("scenes") or []
    sfx_ok = set(sfx_names())
    secs = {}
    for k, v in (patch.get("scenes") or {}).items():
        i = int(k) - 1
        if not (0 <= i < len(scn)) or not isinstance(v, dict):
            continue
        s = scn[i]
        if v.get("shot_fn") in SHOT_FN and v["shot_fn"] != s.get("shot_fn"):
            s["shot_fn"] = v["shot_fn"]
            ch.append(f"s{i + 1}.shot_fn")
        if isinstance(v.get("beats"), list):
            nar = str(s.get("narration") or "")
            bs = []
            for b in v["beats"]:
                if not isinstance(b, dict) or b.get("do") not in ("확대", "표시", "재료", "글자"):
                    continue
                if isinstance(b.get("at"), str) and b["at"] and b["at"] in nar:
                    bs.append({"do": b["do"], "at": b["at"], **({"what": b["what"]} if b.get("what") else {})})
                elif isinstance(b.get("t"), (int, float)):
                    bs.append({"do": b["do"], "t": float(b["t"])})
            if bs and bs != s.get("beats"):
                s["beats"] = bs
                ch.append(f"s{i + 1}.beats")
        if isinstance(v.get("sfx"), list):
            fx = [{"name": e["name"], "at": float(e.get("at", 0)), "keep": bool(e.get("keep", True))} for e in v["sfx"] if isinstance(e, dict) and e.get("name") in sfx_ok]
            if fx != (s.get("sfx") or []):
                s["sfx"] = fx
                ch.append(f"s{i + 1}.sfx")
        pass                                             # sec 는 음성 단계(assemble_audio fit)가 정한다 — 감독이 바꾸면 서로 덮어썼다
    if secs:
        new = [secs.get(i, float(s.get("sec") or 0)) for i, s in enumerate(scn)]
        if abs(sum(new) - float(sb.get("duration_sec") or sum(new))) < 0.05 and min(new) >= 2:
            for s, x in zip(scn, new):
                s["sec"] = x
            ch.append("sec")
        else:
            ch.append("sec 버림(합계 · 최소 2초)")
    return ch


def designer_io(sb: dict, sbp: Path) -> tuple[str, str]:
    st = ""
    for rid in sb.get("reference") or []:
        f = ROOT / "data" / "public" / "trends" / "xray" / rid / "style" / "style.md"
        if f.exists():
            st += f"\n## {rid}\n" + f.read_text("utf-8")[:3000]
    crafts = skill_text("crafts")
    astryx = crafts[crafts.find("## 앱 · 대시보드 화면은 Astryx"):][:2500] if "Astryx" in crafts else ""
    try:                                                  # 쓸 수 있는 글꼴(목록 — 없으면 렌더 때 받는다)
        import fonts as _fonts
        font_list = "\n".join(f"- {f['ps']} ({f['name']}) · {'/'.join(f.get('use', []))} · {f['mood']}" for f in _fonts.catalog())
    except Exception:  # noqa: BLE001
        font_list = ""
    fmt = ('{"direction": {"layout": "full|band", "subs": {"y": 0~1, "box": true|false}, "screen_text_y": 0~1, "font_title": "PostScript 이름", "font_subs": "PostScript 이름", "font_body": "PostScript 이름", "cam_push": 1.0~1.1, "mode": "shorts|animation|comic|cinematic", "letterbox": 0~0.25}, '
           '"materials": {"재료 id": {"adjust": {"scale": 배수(0.6~1.6), "dx": 화면 너비 비율(-0.25~0.25), "dy": 화면 높이 비율(-0.25~0.25)}, "color": "#RRGGBB(overlay 주석만)"}}, "ui_scenes": [{"scene": 장면 번호, "replace": "바꿀 재료 id 또는 null", "what": "앱 화면 설명", "components": ["Table", "Badge"]}], "why": ["이유"]}')
    p = (f"# 스킬: designer\n{skill_text('designer')}\n\n# 앱 화면 규칙(crafts 스킬)\n{astryx}\n\n# 레퍼런스 실측(style.md)\n{st}\n\n# 콘티\n{json.dumps(view(sb, True), ensure_ascii=False)}\n\n"
         "할 일: designer 3장 검사(시선 한 곳 · 안전 영역 · 띠를 70% 이상 채움 · 글자 세 단계 · 앞 장면과 다른 구도)를 통과하게 값을 정한다. "
         "재료는 crafts 기술 증거(web · screen · icon · photo · doc_quote)가 주인공 — info_card·diagram·mock ui_mock 으로 장면을 채우지 않는다(L59~L63). "
         "실험 결과 · 로그 · 데이터가 '앱 화면'으로 보이면 web · 실캡처가 우선이고, 그다음에만 ui_scenes(없으면 빈 배열). "
         "콘티 materials[].ui 에 .tsx 가 이미 있고 빌드가 되면 ui_scenes 에 넣지 않는다 — adjust·layout 만 고친다. 실제 촬영 · 실제 출력 화면은 바꾸지 않는다. "
         "화면 전체 2D 장면(type craft · place full)은 장면 코드가 배치를 정한다 — 그 재료에는 adjust(scale · dx · dy · rot)를 주지 않는다(줘도 쓰이지 않음). "
         "글꼴: 아래 목록에서 이 영상의 주제 · 톤(direction.art · concept)에 맞게 제목(font_title) · 자막(font_subs) · 본문(font_body)을 고른다 — 자막은 오래 읽으니 또렷한 것, 제목은 성격 있는 것. 최근 영상과 같은 조합을 피하고 기본(Pretendard)만 고르지 않는다."
         + (f"\n\n# 쓸 수 있는 글꼴(PostScript 이름 · 쓰임 · 분위기)\n{font_list}" if font_list else ""))
    return SYS.format(role="디자이너", fmt=fmt), p


def designer_apply(sb: dict, patch: dict) -> list[str]:
    ch = []
    d = sb.setdefault("direction", {})
    pd = patch.get("direction") or {}
    if pd.get("layout") in ("full", "band") and pd["layout"] != d.get("layout"):
        d["layout"] = pd["layout"]; ch.append("layout")
    if isinstance(pd.get("subs"), dict):
        sub = {k: v for k, v in pd["subs"].items() if (k == "y" and isinstance(v, (int, float)) and 0.55 <= v <= 0.82) or (k == "box" and isinstance(v, bool))}
        if sub and {**(d.get("subs") or {}), **sub} != d.get("subs"):
            d["subs"] = {**(d.get("subs") or {}), **sub}; ch.append("subs")
    if isinstance(pd.get("screen_text_y"), (int, float)) and 0.08 <= pd["screen_text_y"] <= 0.3 and float(pd["screen_text_y"]) != d.get("screen_text_y"):
        d["screen_text_y"] = float(pd["screen_text_y"]); ch.append("screen_text_y")
    if pd.get("mode") in ("shorts", "animation", "comic", "cinematic") and pd["mode"] != d.get("mode"):
        d["mode"] = pd["mode"]; ch.append("mode")
    if isinstance(pd.get("letterbox"), (int, float)) and 0 <= pd["letterbox"] <= 0.25 and float(pd["letterbox"]) != d.get("letterbox"):
        d["letterbox"] = float(pd["letterbox"]); ch.append("letterbox")
    for k in ("font_title", "font_subs", "font_body"):
        if isinstance(pd.get(k), str) and pd[k] and pd[k] != d.get(k):
            d[k] = pd[k]; ch.append(k)
    if isinstance(pd.get("cam_push"), (int, float)) and 1.0 <= pd["cam_push"] <= 1.1 and float(pd["cam_push"]) != d.get("cam_push"):
        d["cam_push"] = float(pd["cam_push"]); ch.append("cam_push")
    mats = {m.get("id"): m for s in sb.get("scenes") or [] for m in s.get("materials") or []}
    for mid, v in (patch.get("materials") or {}).items():
        col = (v or {}).get("color")
        if mid in mats and mats[mid].get("type") == "overlay" and isinstance(col, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", col) and col != mats[mid].get("color"):
            mats[mid]["color"] = col; ch.append(f"{mid}.color")          # 주석 색(모티프 색 맞추기 — 읽힘 = 초록 등)
        adj = (v or {}).get("adjust") or {}
        if mid in mats and adj:
            a = {}
            for k, x in adj.items():
                if k not in ("scale", "dx", "dy") or not isinstance(x, (int, float)):
                    continue
                if k == "scale":
                    if 0.6 <= x <= 1.6:
                        a[k] = float(x)
                    continue
                if abs(x) > 1:                                   # 픽셀로 준 값 → 화면 비율(1080 × 1920)
                    x = x / (1080 if k == "dx" else 1920)
                if abs(x) <= 0.25:
                    a[k] = round(float(x), 4)
            from craft.motion import FRAME_KEYS, owns_frame
            if owns_frame(mats[mid]):
                # 화면 전체를 장면 코드가 그리는 2D 장면 — 배치는 장면 코드가 정한다(합성 단계도 이 값을 쓰지 않는다)
                a = {k: v for k, v in a.items() if k not in FRAME_KEYS}
            if a and {**(mats[mid].get("adjust") or {}), **a} != mats[mid].get("adjust"):
                mats[mid]["adjust"] = {**(mats[mid].get("adjust") or {}), **a}; ch.append(f"{mid}.adjust")
    return ch


# ── Astryx 앱 화면(디자이너가 고른 장면만) ──
def astryx_doc(names: list[str]) -> str:
    out = []
    for n in names[:6]:
        r = subprocess.run(["npm", "--prefix", str(ROOT / "tools" / "ui-scenes"), "run", "-s", "astryx", "--", "component", n], capture_output=True, text=True, timeout=120)
        out.append(r.stdout[:2500])
    return "\n".join(out)


def build_ui(sb: dict, item: dict, cost: list) -> str | None:
    from ui_build import ensure_ui_built, scene_ui_satisfied  # noqa: E402

    sid = sb["id"]
    n = int(item.get("scene") or 0)
    rep = item.get("replace")
    sc = (sb.get("scenes") or [])[n - 1]
    for m in sc.get("materials") or []:
        if rep and m.get("id") != rep:
            continue
        if not rep and m.get("type") != "ui_mock":
            continue
        rel = m.get("ui")
        if isinstance(rel, str) and rel.strip():
            if ensure_ui_built(rel, sb):
                print(f"[ui 빌드] 기존 {rel} — Agent 생략", flush=True)
                return rel
    if scene_ui_satisfied(sb, n, rep):
        return next(
            (m["ui"] for m in sc.get("materials") or [] if m.get("ui")),
            None,
        )
    name = f"s{n:02d}_app"
    ui = ROOT / "data" / "compositions" / sid / "ui" / f"{name}.tsx"
    ui.parent.mkdir(parents=True, exist_ok=True)
    ex = (ROOT / "tools" / "ui-scenes" / "examples" / "db-table.tsx").read_text("utf-8")
    sysm = "너는 Astryx(Meta 디자인 시스템) React 장면 파일을 쓰는 디자이너다. 출력은 JSON 하나: {\"tsx\": \"파일 전체\"}. 컴포넌트 속성은 문서 그대로(추측 금지)."
    t_doc = time.perf_counter()
    docs = astryx_doc(item.get("components") or ["Card", "Text"])
    _log_skill_timing(sid, f"ui_s{n}_astryx_doc", time.perf_counter() - t_doc, scene=n)
    prompt = (f"# 만들 화면\n{item.get('what')}\n장면 나레이션: {sc.get('narration')}\n화면 글자: {sc.get('caption')}\n\n# 컴포넌트 문서\n{docs}\n\n"
              f"# 예시 파일(형식만 — 내용은 새로)\n{ex}\n\n규칙: `export default function Scene()` 하나, 데이터는 파일 안에, 세로 9:16 화면 높이를 위아래로 꽉 채운다(padding 48, 빈 아래쪽 금지), "
              "영상에서 읽히게 크게(본문 글자 약 40px · 숫자 56px 이상 — style 로 키운다), 한 화면에 볼 곳 하나, 한국어, 실제 데이터만(콘티에 있는 숫자).")
    err = ""
    for attempt in range(2):
        t_ag = time.perf_counter()
        res, c = claude(sysm, prompt + (f"\n\n# 직전 빌드 오류(고친다)\n{err}" if err else ""))
        _log_skill_timing(sid, f"ui_s{n}_agent", time.perf_counter() - t_ag, scene=n, attempt=attempt + 1)
        cost.append(c)
        ui.write_text(res.get("tsx", ""), "utf-8")
        bg = str((sb.get("direction") or {}).get("color_bg") or "#000000").lstrip("#")
        light = sum(int(bg[i:i + 2], 16) for i in (0, 2, 4)) / 765 > 0.5 if len(bg) >= 6 else False   # 영상 바탕이 밝으면 밝은 테마
        t_b = time.perf_counter()
        r = subprocess.run(["node", str(ROOT / "tools" / "ui-scenes" / "build.mjs"), str(ui), str(ui.with_suffix("")), "--mode", "light" if light else "dark", "--png", "1080x1920"], capture_output=True, text=True, timeout=300)
        _log_skill_timing(sid, f"ui_s{n}_build", time.perf_counter() - t_b, scene=n, ok=r.returncode == 0)
        if r.returncode == 0:
            return str(ui.relative_to(ROOT))
        err = (r.stderr or r.stdout)[-2500:]
    return None


def stills(sb: dict, sbp: Path) -> list[str]:
    """장면마다 가운데 시각의 정지 화면(engine/core/still.py) — 렌더가 끝난 뒤"""
    tm = json.loads((ROOT / "data" / "public" / "audio" / f"{sb['id']}.timing.json").read_text("utf-8"))
    ts = [f"{(float(t['start']) + float(t['end'])) / 2:.2f}" for t in tm]
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "core" / "still.py"), str(sbp), *ts], capture_output=True, text=True, timeout=900)
    out = [ln.strip() for ln in r.stdout.splitlines() if ln.strip().endswith(".png")]
    if r.returncode != 0 or len(out) != len(ts):          # 2026-11-24: 정지 화면이 실패해도 그림 없이 검토해 '문제 없음'으로 관문을 지났다
        raise RuntimeError(f"정지 화면 {len(out)}/{len(ts)}장 — still.py 실패: {(r.stderr or r.stdout)[-600:]}")
    return out


def run_refine(sbp: Path) -> dict:
    """refine 스킬을 단계로 — 정지 화면 검토가 '값으로 못 고친' 문제를 받아 최대 두 장면을 session.py(try → 그림 보기 → keep)로 다듬는다.
    이 단계만 도구가 필요하다: 정해진 명령(session · recipes · craft_catalog)과 그림 읽기만 허용"""
    sb = json.loads(sbp.read_text("utf-8"))
    rp = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "review.json"
    probs = (json.loads(rp.read_text("utf-8")).get("problems") or []) if rp.exists() else []
    if not probs:
        return {"pass": "refine", "skipped": "검토가 남긴 문제 없음"}
    rel = str(sbp.relative_to(ROOT))
    fmt = '{"kept": [{"scene": 번호, "target": "motion|sound|edit|재료 id", "recipe_or_pass": "", "why": ""}], "left": ["못 고친 것"]}'
    p = (f"# 스킬: refine\n{skill_text('refine')}\n\n# 정지 화면 검토가 남긴 문제(값 조정으로 못 고친 것)\n{json.dumps(probs, ensure_ascii=False)}\n\n"
         f"# 콘티 경로\n{rel}\n\n할 일: 문제 중 영향이 큰 장면 최대 두 개를 refine 스킬 순서대로 다듬는다 — 검증된 레시피(recipes.py list) 먼저, "
         "try 의 전 · 후 PNG 를 Read 로 반드시 열어 보고, 좋아졌을 때만 keep(--why 필수). 근거 없는 효과는 넣지 않는다. 마지막에 JSON 하나로 보고.")
    allowed = ["Bash(python3 engine/craft/session.py:*)", "Bash(python3 engine/render.py:*)", "Bash(python3 engine/core/still.py:*)", "Bash(python3 engine/craft/recipes.py:*)", "Bash(python3 engine/craft/craft_catalog.py:*)", "Read"]
    res, cost = claude(SYS.format(role="다듬기(refine)", fmt=fmt), p, timeout=2400, tools="Bash,Read", dirs=[str(ROOT)], allowed=allowed, cwd=str(ROOT))
    rec = {"pass": "refine", "kept": res.get("kept"), "left": res.get("left"), "cost_usd": round(cost, 4)}
    (ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "refine.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    return rec


def _hook_index(sb: dict) -> int:
    sc = sb.get("scenes") or []
    return next((i for i, x in enumerate(sc) if x.get("role") == "hook"), 0)


def run_refine_hook(sbp: Path) -> dict:
    """훅 장면 하나만 앱 기능으로 다듬는다(2026-11-19: refine 은 영상 전체 · 문제 있을 때만이라 한 번도 안 돌았고, 에이전트는 Craft 기능 9,152개 중 0.9% 만 썼다).
    영상당 한 번 · 훅 장면 내용이 바뀌지 않으면 다시 하지 않는다. 결과가 좋아졌을 때만 keep"""
    sb = json.loads(sbp.read_text("utf-8"))
    sid = sb["id"]
    hi = _hook_index(sb)
    scene = (sb.get("scenes") or [{}])[hi]
    h = hashlib.sha1(json.dumps({"m": scene.get("materials"), "r": scene.get("refine")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    rec_p = ROOT / "data" / "compositions" / sid / "skill_pass" / "refine_hook.json"
    try:
        old = json.loads(rec_p.read_text("utf-8"))
    except (OSError, ValueError):
        old = {}
    if h in (old.get("hash"), old.get("hash_after")):
        return {"pass": "refine_hook", "skipped": "훅 장면 그대로"}
    if _runs(sid, "refine_hook") >= pass_max("refine_hook"):
        return {"pass": "refine_hook", "skipped": f"refine_hook 상한({pass_max('refine_hook')}회/영상)"}
    _runs(sid, "refine_hook", add=1)
    t0 = time.perf_counter()
    rel, n = str(sbp.relative_to(ROOT)), hi + 1
    fmt = '{"kept": [{"scene": 번호, "target": "motion|sound|edit|재료 id", "features": ["카탈로그 id"], "why": ""}], "tried": ["시도했지만 안 남긴 것"], "left": ["못 한 것"]}'
    p = (f"# 스킬: refine\n{skill_text('refine')}\n\n# 콘티 경로\n{rel}\n# 다듬을 장면\n{n}(훅 — 영상의 첫인상)\n\n"
         f"할 일: 이 장면 하나만 다듬는다. ① `python3 engine/craft/session.py show {rel} {n}` ② `python3 engine/craft/craft_catalog.py search \"<하고 싶은 일 — 영어로: glow · film grain · light sweep …>\"` 로 "
         "EffectCraft 효과 · 프리셋 · 글자 애니메이터 · 빛 · 질감 중 이 장면 뜻에 맞는 1~2개를 고른다(K 도형을 더하는 건 다듬기가 아니다) "
         f"③ `session.py try {rel} {n} --target motion --pass '<JSON>'` → 전 · 후 PNG 를 Read 로 반드시 열어 본다 ④ 분명히 좋아졌을 때만 `session.py keep`(--why 필수). "
         "시도는 최대 3번. 마지막에 JSON 하나로 보고.")
    allowed = ["Bash(python3 engine/craft/session.py:*)", "Bash(python3 engine/core/still.py:*)", "Bash(python3 engine/craft/recipes.py:*)", "Bash(python3 engine/craft/craft_catalog.py:*)", "Read"]
    res, cost = claude(SYS.format(role="다듬기(refine · 훅 장면)", fmt=fmt), p, timeout=900, tools="Bash,Read", dirs=[str(ROOT)], allowed=allowed, cwd=str(ROOT))
    sb2 = json.loads(sbp.read_text("utf-8"))
    sc2 = (sb2.get("scenes") or [{}])[hi]
    h2 = hashlib.sha1(json.dumps({"m": sc2.get("materials"), "r": sc2.get("refine")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    rec = {"pass": "refine_hook", "scene": n, "hash": h, "hash_after": h2, "kept": res.get("kept"), "tried": res.get("tried"), "left": res.get("left"), "cost_usd": round(cost, 4)}
    rec_p.parent.mkdir(parents=True, exist_ok=True)
    rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    _log_skill_timing(sid, "refine_hook", time.perf_counter() - t0, kept=len(res.get("kept") or []))
    return rec


def _digest(files: list[str]) -> str:
    """정지 화면 내용의 지문 — 검토 캐시 키(파일 이름은 시각이라 같아도 그림이 바뀔 수 있다)"""
    h = hashlib.sha1()
    for x in files:
        try:
            h.update((ROOT / x if not Path(x).is_absolute() else Path(x)).read_bytes())
        except OSError:
            h.update(x.encode())
    return h.hexdigest()[:16]


_REVIEW_CTX: dict = {}


def review_io(sb: dict, sbp: Path) -> tuple[str, str]:
    imgs = stills(sb, sbp)
    # 바뀐 장면만 다시 본다(2026-11-19 속도: 장면 하나를 고쳐도 검토가 전 장면을 다시 열어 44~69초) — 그림이 같은 장면은 지난 검토 결과를 그대로 쓴다
    digs = [_digest([x]) for x in imgs]
    try:
        prev = json.loads((ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "review.json").read_text("utf-8"))
    except (OSError, ValueError):
        prev = {}
    old = prev.get("scene_digests") or []
    same = {i + 1 for i, d in enumerate(digs) if i < len(old) and old[i] == d and not prev.get("stale")} if len(old) == len(digs) else set()
    look = [i for i in range(len(imgs)) if i + 1 not in same]
    _REVIEW_CTX.clear()
    _REVIEW_CTX.update(digests=digs, same=sorted(same), prev_problems=[x for x in (prev.get("problems") or []) if isinstance(x, dict) and x.get("scene") in same])
    if same and look:
        imgs_note = "\n".join(f"장면 {i + 1}: {imgs[i]}" for i in look) + f"\n(장면 {', '.join(str(x) for x in sorted(same))} 은 지난 검토 뒤 그림이 그대로라 보지 않는다 — 그 장면 값은 고치지 않는다)"
    else:
        imgs_note = "\n".join(f"장면 {i + 1}: {x}" for i, x in enumerate(imgs))
    sheet = ROOT / "data" / "compositions" / sb["id"] / "craft" / "review" / "sheet.png"
    fmt = ('{"direction": {"subs": {"y": 0.55~0.82, "box": true|false}, "screen_text_y": 0.08~0.3}, "materials": {"재료 id": {"adjust": {"scale": 0.6~1.6, "dx": -0.25~0.25, "dy": -0.25~0.25}, "color": "#RRGGBB(overlay 주석만)"}}, '
           '"problems": [{"scene": 번호, "kind": "겹침|잘림|안전 영역|작은 글자|시선 분산|기타", "what": "본 문제(어느 재료 · 글자)", "fix": "어떻게 고치면 되나(장면 코드의 어느 값)"}], "why": ["이유"]}')
    p = (f"# 스킬: designer (3장 '보고 고친다'가 이 단계)\n{skill_text('designer')}\n\n# 콘티\n{json.dumps(view(sb, True), ensure_ascii=False)}\n\n"
         "# 볼 그림(Read 로 하나씩 연다 — 장면 순서)\n" + imgs_note +
         f"\n(그림 지문 {_digest(imgs)} — 그림이 같으면 검토를 다시 하지 않는다)" + (f"\n레퍼런스와 나란히: {sheet}" if sheet.exists() else "") +
         "\n\n할 일: 그림을 실제로 열어 보고 designer 3장 1~5 를 장면마다 확인한다 — 특히 글자 · 숫자 · 주석이 서로 겹침, 재료가 화면 밖으로 잘림(증거 줄 · 글자), "
         "띠 안 주인공이 70% 미만, 안전 영역 침범. 문제 있는 장면만 값으로 고친다(문제가 없으면 materials 를 비운다). 본 문제는 problems 에 적는다. "
         "화면 전체 2D 장면(type craft · place full)은 장면 코드가 배치를 정해 adjust 가 쓰이지 않는다 — 그 안의 잘림 · 겹침은 값을 주지 말고 problems 에만 적는다. "
         "problems 는 품질 관문에 올라가 겹침 · 잘림 · 안전 영역은 완성을 막는다 — 지금 그림에서 실제로 보이는 것만 적고, 고친 뒤 사라졌으면 적지 않는다.")
    base = baseline(sb["id"], "review")
    if base:   # 수렴: 앞선 검토가 막은 것이 풀렸는지만(새 지적은 권고) — 값 고치기(materials · direction)는 그대로 해도 된다
        p += _verify_block(base, "verify")
    return SYS.format(role="디자이너(정지 화면 검토)", fmt=fmt), p


OWNER = {"writer": ("L03", "L04", "L05", "L08", "L13", "L14", "L31", "L51", "L52", "L55"), "director": ("L41", "L50", "L54", "L29", "L32"), "designer": ("L12", "L33", "L34", "L35", "L53")}


def _hard_lint(sb: dict) -> set:
    """막는 검사 실패(L)의 (코드, 장면) — 각본가 수정 전후 비교용"""
    import lint
    try:
        return {(f[0], f[1] if len(f) > 2 else None) for f in lint.lint(sb) if not str(f[0]).startswith("T")}
    except Exception:  # noqa: BLE001 - 검사가 깨지면 비교하지 않는다(받아들임)
        return set()


def _lint_lines(sb: dict, keys: list) -> list[str]:
    import lint
    want = set(keys)
    return [f"{c} {f'{s + 1}장면 ' if isinstance(s, int) else ''}{m}" for c, s, m, *_ in lint.lint(sb) if (c, s) in want]


def lint_owners(sbp: Path) -> dict:
    """lint 실패 줄 → 담당 단계별 목록"""
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "checks" / "lint.py"), str(sbp)], capture_output=True, text=True, timeout=300)
    by: dict = {}
    for ln in r.stdout.splitlines():
        code = ln.split(" ", 1)[0]
        if code == "L01" and "/narration" in ln:                # 대사 길이(스키마) — 각본가 몫
            code = "L14"
        for n, codes in OWNER.items():
            if code in codes:
                by.setdefault(n, []).append(ln.strip())
    return by


PASSES = {"viewer": (viewer_io, viewer_apply), "writer": (writer_io, writer_apply), "director": (director_io, director_apply), "designer": (designer_io, designer_apply), "review": (review_io, designer_apply)}

_NEED = ("writer", "director", "designer")


def words_hash(sb: dict) -> str:
    """대본의 말(제목 · 나레이션 · 화면 글자)만의 해시 — 목소리 · 재료 · 연출 칸이 바뀌어도 그대로다(produce 의 --prep 기록과 같은 식)"""
    return hashlib.sha1(json.dumps([sb.get("title"), [(x.get("narration"), x.get("caption")) for x in sb.get("scenes") or []]], ensure_ascii=False).encode()).hexdigest()[:16]


def _approved_path(sid: str) -> Path:
    return ROOT / "data" / "compositions" / sid / "skill_pass" / "approved.json"


def mark_approved(sbp: Path, **info) -> None:
    """이해 관문(시청자 · 각본가 · 검사 되먹임)을 마친 최종 대본을 기록한다.
    2026-11-17: 음성 실패 뒤 재시도마다 대본 검토 9분을 처음부터 다시 했고, 검사 되먹임의 각본가가 마지막에 대본을 고쳐
    음성 직전 이해 관문이 또 돌았다 — 끝난 대본의 말 해시를 남겨 같은 말이면 건너뛴다"""
    sb = json.loads(sbp.read_text("utf-8"))
    p = _approved_path(sb["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"words": words_hash(sb), "texts": _texts(sb), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **info}, ensure_ascii=False), "utf-8")


def _texts(sb: dict) -> list:
    return [sb.get("title") or ""] + [f"{x.get('narration') or ''}\n{x.get('caption') or ''}" for x in sb.get("scenes") or []]


SMALL_EDIT = 0.8   # 장면마다 승인된 말과 이만큼 같으면(길이 맞추기 · 낱말 손질) 승인을 유지한다


def is_approved(sbp: Path) -> bool:
    """같은 말이거나, 승인된 대본을 조금만 손본 말이면 승인으로 본다.
    2026-11-18: 길이 검사를 맞추려 몇 글자 줄일 때마다 승인이 깨져 시청자 · 각본가가 처음부터 다시 돌았다(편당 약 24분).
    장면 수가 바뀌었거나 어느 장면이든 크게 바뀌었으면 다시 검토한다."""
    from difflib import SequenceMatcher
    try:
        sb = json.loads(sbp.read_text("utf-8"))
        rec = json.loads(_approved_path(sb["id"]).read_text("utf-8"))
    except (OSError, ValueError, KeyError):
        return False
    if rec.get("words") == words_hash(sb):
        return True
    old, new = rec.get("texts") or [], _texts(sb)
    return bool(old) and len(old) == len(new) and all(SequenceMatcher(None, a, b).ratio() >= SMALL_EDIT for a, b in zip(old, new))


WRITER_MAX = 3   # (예전 이름 — PASS_MAX["writer"])
# 영상 하나에 단계별 실제 LLM 실행 상한. 넘으면 그 단계는 건너뛰고 남은 문제는 에이전트가 직접 고친다(FLUMA_PASS_MAX_<이름> 으로 바꿈).
# 2026-11-18 실측(11-17 9편): 시청자 최대 40번 · 각본가 33번/편 — 제작을 다시 돌릴 때마다 입력이 조금씩 바뀌어 단계가 매번 다시 돌았다.
PASS_MAX = {"writer": WRITER_MAX, "viewer": 4, "director": 2, "designer": 2, "review": 4, "refine_hook": 2}


def pass_max(name: str) -> int:
    env = os.environ.get(f"FLUMA_PASS_MAX_{name.upper()}") or (os.environ.get("FLUMA_WRITER_MAX") if name == "writer" else None)
    return int(env) if env else PASS_MAX.get(name, 99)


def _runs(sid: str, name: str, add: int = 0) -> int:
    p = ROOT / "data" / "compositions" / sid / "skill_pass" / f"{name}_runs.json"
    n = (json.loads(p.read_text("utf-8")).get("n", 0) if p.exists() else 0) + add
    if add:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"n": n}), "utf-8")
    return n


def produce_skill_steps(sbp: Path) -> list[str]:
    """produce 시작 시 skill_pass 에 돌릴 단계 — 기본 writer·director·designer 전부.

    - FLUMA_PRODUCE_SKILLS=0 / FLUMA_SKIP_SKILLS=1 → []
    - lint 실패 시에도 전부 돌린 뒤 skill_pass 안에서 되먹임(담당별 --force)
    """
    if os.environ.get("FLUMA_SKIP_SKILLS") == "1" or os.environ.get("FLUMA_PRODUCE_SKILLS") == "0":
        return []
    return ["writer", "director", "designer"]


def parallel_passes(names: list[str], sbp: Path, force: bool, issues: dict | None = None) -> list[dict]:
    """서로 다른 칸을 고치는 단계(감독: 연출 · 박자 · 소리 / 디자이너: 배치 · 자막 · 글꼴 · 앱 화면)는 모델 호출을 동시에 보내고,
    받은 답은 차례로 적용한다(파일을 동시에 쓰지 않게). 2026-11-16: 차례로 부르면 단계마다 20~50초가 그대로 더해졌다"""
    sb = json.loads(sbp.read_text("utf-8"))
    todo, out = {}, []
    for n in names:
        system, prompt = PASSES[n][0](sb, sbp)
        if issues and issues.get(n):
            prompt += "\n\n# 검사(lint)가 막은 것 — 이 단계 담당, 꼭 고친다(스킬 규칙과 함께 만족시키는 방법으로)\n" + "\n".join(issues[n])
        rec_p = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / f"{n}.json"
        h = hashlib.sha1((system + prompt).encode()).hexdigest()[:16]
        if not force and rec_p.exists() and json.loads(rec_p.read_text("utf-8")).get("hash") == h:
            out.append({"pass": n, "skipped": "입력 그대로"})
            continue
        if _runs(sb["id"], n) >= pass_max(n):
            out.append({"pass": n, "skipped": f"{n} 상한({pass_max(n)}회/영상)"})
            continue
        todo[n] = (system, prompt)
    if not todo:
        return out
    with ThreadPoolExecutor(max_workers=len(todo)) as ex:
        futs = {n: ex.submit(claude, *sp) for n, sp in todo.items()}
        got = {n: f.result() for n, f in futs.items()}
    for n in names:
        if n in got:
            out.append(run_pass(n, sbp, True, (issues or {}).get(n), pre=got[n]))
    return out


BLOCKING = ("처음 보는 말", "설명 없는 숫자", "흐름 끊김", "넘김")


def viewer_open(sbp: Path) -> tuple[int, list]:
    """마지막 시청자 검토의 (점수, 아직 대사로 풀어야 할 이해 막힘)"""
    sb = json.loads(sbp.read_text("utf-8"))
    f = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "viewer.json"
    try:
        r = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return 0, []
    if r.get("stale"):           # 상한에 닿아 고친 대본을 다시 못 봤다 — 옛 판정으로 막지 않는다
        return STORY_BLOCK_BELOW, []
    score = int((r.get("patch") or {}).get("score") or r.get("score") or 0)
    issues = [i for i in viewer_issues(sb, "writer") if i.get("kind") in BLOCKING]
    ver = (r.get("patch") or {}).get("verify") or []
    if not score and ver and all(v.get("resolved") for v in ver if isinstance(v, dict)) and not issues and not r.get("problems"):
        # 수렴 검토(지난 지적만 확인)는 점수를 내지 않는다 — 모두 해결이면 통과(2026-11-22: '점수 0, 0건'으로 막아 왕복 한 번)
        score = 8
    return score, issues


STORY_BLOCK_BELOW = 7


def story_blocking(sbp: Path) -> list:
    """콘티 구조 문제로 멈출지 — 시청자 이해 점수가 STORY_BLOCK_BELOW 미만일 때만.
    2026-11-17 실측: 시청자 검토는 부를 때마다 새 '구조' 지적을 찾는다(점수는 7로 같음). 지적이 하나라도 있으면 멈추게 했더니
    에이전트가 콘티를 고치고 produce 를 다시 돌리는 일을 다섯 번 넘게 반복했다(검토 한 번 30~45초 + 고치기 1~2분).
    점수가 기준 이상이면 구조 지적은 각본가 · 감독에게 '제안'으로만 넘긴다(writer_io 가 함께 읽는다)."""
    score, _ = viewer_open(sbp)
    if score >= STORY_BLOCK_BELOW:
        return []
    return viewer_issues(json.loads(sbp.read_text("utf-8")), "story")


def comprehension_loop(sbp: Path, force: bool = False, rounds: int = 2, always_write: bool = False) -> list[dict]:
    """이해 관문(2026-11-16): 시청자 검토 → 각본가 → 고친 대본을 다시 시청자 검토.
    - 콘티 구조 문제(fix_by story)는 첫 검토에서 바로 멈춘다 — 대사를 고쳐 봐야 안 풀리므로 각본가 루프를 돌지 않는다
      (2026-11-16 실측: 첫 검토 25초에 찾은 구조 문제를 각본가 루프 4분 뒤에야 알렸다)
    - 나아지지 않으면 멈춘다: 점수가 8 이상 · 막힘이 1개 이하 · 직전보다 점수가 안 오르고 막힘도 안 줄면 끝
      (시청자는 매번 새 지적을 찾아 점수가 7에 머물러, 막힘 0개 조건으로는 늘 최대 횟수까지 돌았다)
    입력(대본)이 그대로면 해시로 건너뛰므로 다시 불러도 비용이 없다 — produce 가 음성 직전에 한 번 더 부른다.
    이해 관문을 이미 마친 말(approved.json)과 같으면 시청자도 부르지 않는다."""
    if not force and is_approved(sbp):
        return [{"pass": "comprehension", "skipped": "검토를 마친 대본 그대로"}]
    out = [run_pass("viewer", sbp, force)]

    def story_block() -> bool:
        st = story_blocking(sbp)
        if st:
            out.append({"pass": "comprehension", "story": [f"{i.get('scene')}장면 {i.get('kind')}: {i.get('what')} → {i.get('how')}" for i in st]})
        return bool(st)

    if story_block():
        return out
    if always_write:                                   # 처음 쓸 때는 각본가(말투 · AI 티 · 시청자 막힘)를 꼭 한 번 거친다
        pre_lint = lint_owners(sbp).get("writer")       # 검사에 걸릴 대사 문제도 첫 호출에 같이(나중 되먹임 왕복을 줄인다)
        out += [run_pass("writer", sbp, force, pre_lint), run_pass("viewer", sbp, False)]
        if story_block():
            return out
    prev = None
    for _ in range(rounds):
        score, open_ = viewer_open(sbp)
        if score >= 8 or len(open_) <= 1 or (prev and score <= prev[0] and len(open_) >= prev[1]):
            break
        if always_write and score >= 7:   # 처음 쓰기(시청자 → 각본가 → 시청자)를 이미 거쳤고 관문(7)을 넘으면 한 바퀴 더 돌지 않는다(2026-11-18: 각본가 · 시청자 한 쌍 약 100초)
            break
        prev = (score, len(open_))
        out.append(run_pass("writer", sbp, True))
        out.append(run_pass("viewer", sbp, False))
        if story_block():
            return out
    score, open_ = viewer_open(sbp)
    out.append({"pass": "comprehension", "score": score, "open": [f"{i.get('scene')}장면 {i.get('kind')}: {i.get('what')}" for i in open_]})
    return out


def run_pass(name: str, sbp: Path, force: bool, issues: list[str] | None = None, pre: tuple | None = None) -> dict:
    t_pass = time.perf_counter()
    import copy
    import sbio
    base = sbio.load(sbp)                        # 시작 때 읽은 것 — 끝에 '이 단계가 바꾼 칸만' 지금 파일에 얹는다(LLM 을 기다리는 동안 에이전트가 고친 칸을 지우지 않게)
    sb = copy.deepcopy(base)
    sid = sb["id"]
    rec_p = ROOT / "data" / "compositions" / sid / "skill_pass" / f"{name}.json"
    rec_p.parent.mkdir(parents=True, exist_ok=True)
    io, apply = PASSES[name]
    if name == "writer":
        update_text_locks(sb)
    system, prompt = io(sb, sbp)
    if issues:
        prompt += "\n\n# 검사(lint)가 막은 것 — 이 단계 담당, 꼭 고친다(스킬 규칙과 함께 만족시키는 방법으로)\n" + "\n".join(issues)
    h = hashlib.sha1((system + prompt).encode()).hexdigest()[:16]
    if pre is None and not force and rec_p.exists() and json.loads(rec_p.read_text("utf-8")).get("hash") == h:
        _log_skill_timing(sid, name, time.perf_counter() - t_pass, skipped=True)
        return {"pass": name, "skipped": "입력 그대로"}
    if name == "review" and pre is None and not force and rec_p.exists() and _REVIEW_CTX.get("digests") and len(_REVIEW_CTX.get("same") or []) == len(_REVIEW_CTX["digests"]):
        _log_skill_timing(sid, name, time.perf_counter() - t_pass, skipped=True)
        return {"pass": name, "skipped": "모든 장면 그림이 지난 검토와 같음"}
    cap = pass_max(name)
    if pre is None and _runs(sid, name) >= cap:
        if name in ("review", "viewer") and rec_p.exists():   # 그림 · 대본이 바뀌었는데 다시 못 봤다 — 지난 검토는 막음이 아니라 권고로(D21 · 이해 관문, 2026-11-19: 상한 뒤 옛 판정이 고친 대본을 계속 막음)
            r0 = json.loads(rec_p.read_text("utf-8"))
            same = set(_REVIEW_CTX.get("same") or []) if name == "review" and _REVIEW_CTX.get("digests") else None
            if same is None:
                r0["stale"] = True
            else:                                      # 그림이 지난 검토 그대로인 장면의 문제는 분명히 안 풀렸다 — 그것만 계속 막는다(2026-11-24)
                r0.pop("stale", None)
                for x in r0.get("problems") or []:
                    if isinstance(x, dict):
                        x["stale"] = x.get("scene") not in same
            rec_p.write_text(json.dumps(r0, ensure_ascii=False, indent=1), "utf-8")
        _log_skill_timing(sid, name, time.perf_counter() - t_pass, skipped=True, capped=True)
        return {"pass": name, "skipped": f"{name} 상한({cap}회/영상) — 남은 문제는 에이전트가 직접 고친다"}
    _runs(sid, name, add=1)
    review_ctx = dict(_REVIEW_CTX) if name == "review" else {}
    t_ag = time.perf_counter()
    if name == "review":
        patch, cost = claude(system, prompt, timeout=1500, tools="Read", dirs=[str(ROOT / "data" / "workspace" / "stills"), str(ROOT / "data" / "compositions" / sb["id"])])
    elif pre is not None:                       # 다른 단계와 동시에 이미 받아 온 답(parallel_passes)
        patch, cost = pre
    else:
        patch, cost = claude(system, prompt)
    _log_skill_timing(sid, f"{name}_agent", time.perf_counter() - t_ag)
    if name == "viewer" and isinstance(patch, dict):
        patch = converge(sid, "viewer", patch, "issues", lambda x: x.get("kind") in BLOCKING or str(x.get("fix_by", "")).startswith("story"))
    elif name == "review" and isinstance(patch, dict):
        patch = converge(sid, "review", patch, "problems", lambda x: any(k in str(x.get("kind") or "") for k in ("겹침", "잘림", "안전 영역")))
    costs = [cost]
    before = _hard_lint(json.loads(sbp.read_text("utf-8"))) if name == "writer" else None
    text_in = _text_fields(sb)
    if name == "writer":
        locked = sorted(text_locks(sb))
        patch = dict(patch, _locked=locked)
    changed = apply(sb, patch)
    if name == "writer" and changed:
        new = sorted(_hard_lint(sb) - before)
        if new and all(sc is not None for _, sc in new):   # 장면에서 깬 검사면 그 장면 글만 되돌리고 나머지 고친 점은 받는다 — 각본가를 다시 부르지 않는다(2026-11-19: 다시 부른 것까지 버려져 165초가 사라짐)
            orig = sbio.load(sbp)
            bad = {int(sc) for _, sc in new}
            for k in bad:
                if k < len(sb.get("scenes") or []) and k < len(orig.get("scenes") or []):
                    for f in ("narration", "caption"):
                        sb["scenes"][k][f] = orig["scenes"][k].get(f)
            if not sorted(_hard_lint(sb) - before):
                changed = [c for c in changed if not any(str(c).startswith(f"s{k + 1}.") for k in bad)] + [f"(장면 {', '.join(str(k + 1) for k in sorted(bad))} 은 검사를 깨서 되돌림)"]
                new = []
        if new:   # 한 번은 깬 검사를 알려 주고 다시 쓰게 한다(버리면 각본가 한 번 · 약 60초가 그냥 사라졌다)
            msgs = _lint_lines(sb, new)
            patch2, cost2 = claude(system, prompt + "\n\n# 직전 답이 새로 깬 검사 — 이것을 깨지 않게 다시 낸다(나머지 고친 점은 살린다)\n" + "\n".join(msgs))
            costs.append(cost2)
            base2 = sbio.load(sbp)
            sb2 = copy.deepcopy(base2)
            patch2 = dict(patch2, _locked=locked)
            ch2 = apply(sb2, patch2)
            new2 = sorted(_hard_lint(sb2) - before) if ch2 else []
            if not new2:
                sb, base, patch, changed, new = sb2, base2, patch2, ch2 + ["(검사를 알려 준 뒤 다시 씀)"], []
            else:
                new = new2
            cost = sum(costs)
        if new:   # 그래도 검사 실패를 새로 만들면 받지 않는다 — 대본이 나빠지지 않게(2026-11-18 실측: 고친 대사가 L08 · L51 · L01 을 새로 깨 되먹임 · 재시도가 이어졌다)
            rec = {"pass": name, "hash": h, "changed": [], "rejected": [f"{c} {s if s is not None else ''}".strip() for c, s in new], "cost_usd": round(cost, 4), "patch": patch, "text_in": text_in, "text_out": text_in}
            rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
            _log_skill_timing(sid, name, time.perf_counter() - t_pass, changed=0, rejected=len(new))
            return {"pass": name, "changed": [], "why": [f"새 검사 실패를 만들어 버림: {', '.join(rec['rejected'][:6])}"], "cost_usd": round(cost, 4)}
    if name == "designer":
        from ui_build import scene_ui_satisfied  # noqa: E402

        ui_items = []
        for it in patch.get("ui_scenes") or []:
            n = int(it.get("scene") or 0)
            if scene_ui_satisfied(sb, n, it.get("replace")):
                changed.append(f"s{n}.ui_mock(기존·빌드)")
                continue
            ui_items.append(it)

        def _apply_ui(it: dict, ui: str | None) -> None:
            if not ui:
                changed.append(f"s{it.get('scene')} 앱 화면 빌드 실패(타입 검사 2번)")
                return
            n = int(it["scene"])
            sc = sb["scenes"][n - 1]
            mats = sc.setdefault("materials", [])
            new = {"id": f"s{n:02d}app", "type": "ui_mock", "device": "phone", "mock": True, "ui": ui, "what": it.get("what")}
            rep = it.get("replace")
            idx = next((k for k, m in enumerate(mats) if m.get("id") == rep), None)
            if idx is not None:
                mats[idx] = new
            else:
                mats.append(new)
            changed.append(f"s{n}.ui_mock")

        def _scene_has_evidence(n: int) -> bool:
            from material_evidence import _primary, is_evidence  # noqa: E402

            sc_ = (sb.get("scenes") or [])[n - 1]
            return any(is_evidence(m) for m in _primary(sc_.get("materials") or []))

        if len(ui_items) <= 1:
            for it in ui_items:
                n = int(it.get("scene") or 0)
                if not _scene_has_evidence(n) and not it.get("replace"):
                    changed.append(f"s{n}.ui_mock(증거 없음 — icon/web 콘티 필요)")
                    continue
                try:
                    ui = build_ui(sb, it, costs)
                except (RuntimeError, subprocess.TimeoutExpired) as e:
                    changed.append(f"앱 화면 실패: {e}")
                    continue
                _apply_ui(it, ui)
        else:
            built: dict[int, str | None] = {}

            def _run(it: dict) -> tuple[int, str | None]:
                local_cost: list = []
                try:
                    return int(it["scene"]), build_ui(sb, it, local_cost)
                except (RuntimeError, subprocess.TimeoutExpired):
                    return int(it["scene"]), None
                finally:
                    costs.extend(local_cost)

            with ThreadPoolExecutor(max_workers=min(3, len(ui_items))) as ex:
                futs = [ex.submit(_run, it) for it in ui_items]
                for fut in as_completed(futs):
                    sn, ui = fut.result()
                    built[sn] = ui
            for it in ui_items:
                n = int(it.get("scene") or 0)
                if not _scene_has_evidence(n) and not it.get("replace"):
                    changed.append(f"s{n}.ui_mock(증거 없음 — icon/web 콘티 필요)")
                    continue
                _apply_ui(it, built.get(n))
    sb = sbio.save(sbp, base, sb, indent=1)
    # 적용 뒤 입력 해시(다음엔 건너뛰게)
    system2, prompt2 = io(sb, sbp)
    rec = {"pass": name, "hash": hashlib.sha1((system2 + prompt2).encode()).hexdigest()[:16], "changed": changed, "why": patch.get("why"), "problems": patch.get("problems") or patch.get("issues"), "score": patch.get("score"), "understood": patch.get("understood"), "cost_usd": round(sum(costs), 4), "patch": patch}
    if name == "writer":
        rec.update(text_in=text_in, text_out=_text_fields(sb))
    if name == "review":          # 이번에 안 본(그림이 그대로인) 장면의 지난 문제는 이어 붙인다 · 다음 비교용 장면 지문은 고친 뒤 그림 기준
        keep = [x for x in review_ctx.get("prev_problems") or [] if x.get("scene") in set(review_ctx.get("same") or [])]
        rec["problems"] = keep + [x for x in (rec.get("problems") or []) if not (isinstance(x, dict) and x.get("scene") in set(review_ctx.get("same") or []))]
        # 검토가 실제로 본 그림(고치기 전)의 지문 — 고친 뒤 그림 지문을 남기면 다음 검토가 '그대로'라며 보지 않고 고치기 전 문제를 영원히 이어 붙였다(2026-11-24)
        rec["scene_digests"] = review_ctx.get("digests") or []
        rec["looked"] = [i + 1 for i in range(len(rec["scene_digests"])) if i + 1 not in set(review_ctx.get("same") or [])]
    rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    _log_skill_timing(sid, name, time.perf_counter() - t_pass, changed=len(changed or []))
    return {k: rec[k] for k in ("pass", "changed", "why", "problems", "score", "understood", "cost_usd") if rec.get(k) is not None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["all", "pipeline", "comprehension", "visual", "viewer", "writer", "director", "designer", "review", "refine", "refine_hook", "status"])
    ap.add_argument("storyboard")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--write", action="store_true", help="comprehension: 시청자 → 각본가 → 시청자(produce 의 처음 쓰기와 같은 순서) — bundle.py script 가 쓴다")
    a = ap.parse_args()
    sbp = Path(a.storyboard); sbp = sbp if sbp.is_absolute() else ROOT / sbp
    sid = json.loads(sbp.read_text("utf-8"))["id"]
    if a.which == "status":
        recs = {}
        for f in (ROOT / "data" / "compositions" / sid / "skill_pass").glob("*.json"):
            r = json.loads(f.read_text("utf-8")); recs[f.stem] = {k: r.get(k) for k in ("changed", "cost_usd")}
        ok("skill_pass", status=json.dumps(recs, ensure_ascii=False))
        return 0
    out = []
    if a.which in ("refine", "refine_hook"):
        try:
            r = run_refine(sbp) if a.which == "refine" else run_refine_hook(sbp)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            fail("skill_pass", stage=a.which, error=str(e)[:400])
        print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
        ok("skill_pass", passes=json.dumps([r], ensure_ascii=False))
        return 0
    skip_viewer = os.environ.get("FLUMA_SKIP_VIEWER", "0") == "1"

    def _viewer_gate(sbn: dict) -> None:
        story = story_blocking(sbp)
        if story:
            fail("skill_pass", stage="story", error=f"시청자 시뮬레이션: 콘티 구조를 다시 써야 함 {len(story)}건 — " + brief([f"{i.get('scene')}장면 {i.get('kind')}: {i.get('what')}" for i in story])
                 + f" · 고칠 방법까지 전문: data/compositions/{sbn['id']}/skill_pass/viewer.json")

    try:
        which = a.which
        if which == "pipeline":
            which = "all"
        if a.which == "visual":                                   # 감독 · 디자이너만(동시에) — produce --prep 뒤
            for r in parallel_passes(["director", "designer"], sbp, a.force):
                out.append(r); print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
            ok("skill_pass", passes=json.dumps(out, ensure_ascii=False))
            return 0
        if a.which == "comprehension":
            out = comprehension_loop(sbp, a.force, rounds=1, always_write=a.write)
            for r in out:
                print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
            _viewer_gate(json.loads(sbp.read_text("utf-8")))
            if out[-1].get("score", 10) < 7:
                fail("skill_pass", stage="comprehension", error=f"처음 보는 시청자가 이해하지 못함(점수 {out[-1]['score']}, {len(out[-1]['open'])}건) — " + brief(out[-1]["open"])
                     + f" · 전문: data/compositions/{json.loads(sbp.read_text('utf-8'))['id']}/skill_pass/viewer.json")
            if not out[-1].get("skipped"):
                mark_approved(sbp, by="comprehension", score=out[-1].get("score"))
            ok("skill_pass", passes=json.dumps(out, ensure_ascii=False))
            return 0
        steps = [a.which]
        if which == "all":
            steps = ["director", "designer"]
            if skip_viewer:
                steps = ["writer"] + steps
            else:
                for r in comprehension_loop(sbp, a.force, rounds=1, always_write=True):   # 시청자 → 각본가 → 재검토(한 바퀴까지)
                    out.append(r); print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
                _viewer_gate(json.loads(sbp.read_text("utf-8")))
        par = [n for n in steps if n in ("director", "designer")]
        if len(par) == 2:                                          # 감독 · 디자이너는 동시에
            for r in parallel_passes(par, sbp, a.force):
                out.append(r); print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
            steps = [n for n in steps if n not in par]
        for n in steps:
            single = lint_owners(sbp).get(n) if a.which != "all" and n in OWNER else None   # 단독으로 부를 때도 지금 걸린 담당 검사를 넘긴다
            out.append(run_pass(n, sbp, a.force, single))
            print(f"[스킬 단계] {json.dumps(out[-1], ensure_ascii=False)}", flush=True)
        if which == "all" and a.which != "pipeline":
            for rnd in range(2):                                   # 검사 되먹임: 걸린 규칙을 담당 단계로 돌려보낸다(최대 두 
                by = lint_owners(sbp)
                if not by:
                    break
                if by.get("writer") and rnd == 0:
                    out.append(run_pass("writer", sbp, True, by["writer"]))
                    print(f"[스킬 단계 · 되먹임 {rnd + 1}] {json.dumps(out[-1], ensure_ascii=False)}", flush=True)
                for r in parallel_passes([n for n in ("director", "designer") if by.get(n)], sbp, True, by):
                    out.append(r); print(f"[스킬 단계 · 되먹임 {rnd + 1}] {json.dumps(r, ensure_ascii=False)}", flush=True)
            # 검사 되먹임까지 끝난 최종 대본을 승인으로 남긴다 — 음성 직전 이해 관문 · 재시도가 같은 말을 다시 검토하지 않게.
            # 점수가 관문 기준(7) 아래면 남기지 않는다: 그때는 음성 직전 관문이 그대로 막아 사람에게 알린다
            comp = [r for r in out if r.get("pass") == "comprehension"]
            if not skip_viewer and comp and (comp[-1].get("skipped") or comp[-1].get("score", 0) >= 7):
                mark_approved(sbp, by="all", score=comp[-1].get("score"))
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        fail("skill_pass", stage="skill_pass", error=str(e)[:400])
    ok("skill_pass", passes=json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
