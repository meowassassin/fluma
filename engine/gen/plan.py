#!/usr/bin/env python3
"""파이프라인 1단계 — 기획: 트렌드 기반 추천 선택지 → 디테일 확정 → 8초 이하 샷 목록(data/shotplans/<id>.json).
오케스트레이터(Claude Code · Codex · Antigravity)는 이 명령들만 부른다 — 특정 오케스트레이터에 기대는 로직은 두지 않는다.

  python3 engine/gen/plan.py trends [--request <rid>] [--label <이름>] [--top 8]   # 기존 트렌드 분석 → 추천 선택지 재료(JSON)
  python3 engine/gen/plan.py new <id> --topic "주제" [--aspect 9:16]              # 빈 샷 계획
  python3 engine/gen/plan.py check <id>                                           # 스키마 + 규칙(✗ 실패 = 종료 1, △ 권고)
  python3 engine/gen/plan.py prompts <id> [--shot N]                              # 3단계 키 프레임 · 4단계 영상 프롬프트(조립 결과)
  python3 engine/gen/plan.py guide                                                # 프롬프트 규칙 요약

프롬프트는 에이전트가 통째로 쓰지 않는다 — 샷 칸(크기 · 앵글 · 카메라 움직임 · 시작 상태 · 동작 · 끝 상태 · 소리 …)을 채우면
여기서 조사된 규칙대로 글로 조립한다(모델은 JSON 을 구조로 읽지 않는다). 근거와 출처 수:
볼트 02 Architecture/숏폼 생성 파이프라인 — 프롬프트 · 구조 조사 (2026-11-11).
"""
from __future__ import annotations

import argparse
import json
import os
import time
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

PLANS = ROOT / "data" / "shotplans"
SCHEMA = ROOT / "engine" / "spec" / "schema" / "shotplan.schema.json"
TRENDS = ROOT / "data" / "public" / "trends"

VIDEO_MAX_CHARS = 1100          # gflow-cli: 1,100~1,400자 넘으면 HTTP 400
WORDS_PER_SEC = 2.5             # gflow-cli 측정(25편): 8초에 약 18단어
TEXT_POLICY = "No captions, subtitles, on-screen text, letters or logos."
SETTINGS = ROOT / "data" / "workspace" / "settings.json"
# 모델마다 고를 수 있는 생성 길이(gflow models · gflow video r2v --help, 2026-11-13 확인)
GEN_SECS = {"veo": (4, 6, 8), "omni_flash": (4, 6, 8, 10), "omni_1_2_flash": tuple(range(3, 16))}
REF_CAP = {"veo_3_1_quality": 0, "veo": 3, "omni": 7}      # 그림 레퍼런스 장수 한도(r2v)
BANNED = {   # 단어 → 이유(조사)
    "cinematic": "레터박스(검은 띠)가 생김 — gflow 측정",
    "35mm": "필름 테두리 · 레터박스 — gflow 측정", "imax": "레터박스 — gflow 측정", "film grain": "필름 테두리 — gflow 측정",
    "anamorphic": "레터박스 — gflow 측정", "4k": "꾸밈말 — 효과 없음", "8k": "꾸밈말 — 효과 없음", "masterpiece": "꾸밈말 — 효과 없음",
    "stunning": "꾸밈말 — 효과 없음", "hyper-realistic": "꾸밈말 — 효과 없음", "award-winning": "꾸밈말 — 효과 없음",
}
AGE = re.compile(r"\b(\d{1,2}[- ]year[- ]old|teen(?:ager|age)?|kid|child|girl|boy|young|old|elderly|aged)\b", re.I)
TEXTY = re.compile(r"\b(sign|signboard|poster|label|newspaper|book cover|menu|billboard|caption|subtitle|logo|text|letters|screen showing|banner)\b", re.I)
ABSTRACT_METAPHOR = re.compile(r"\b(glowing (?:translucent |colorful )?spheres?|glowing orbs?|magic orbs?|energy balls?|data spheres?|data orbs?|floating crystals?)\b", re.I)
MULTI = re.compile(r"\b(and then|then|after that|afterwards|while also|before)\b", re.I)
NEG = re.compile(r"\b(no|not|don't|do not|without|never)\b", re.I)
HANGUL = re.compile(r"[가-힣]")
MAX_SYLLABLES_PER_SEC = 5.8     # 한국어 TTS 실측: 여백(LEAD+TAIL 0.45초)을 빼면 final_sec 안에 자연스럽게 읽히는 음절(공백 제외) 상한

GUIDE = """프롬프트 규칙(조사 요약 — 출처 수는 볼트 문서)
1단계 샷 칸 (시각적 직관성 · 4막 인과관계)
- 무음 직관성(Mute Test): 소리를 끄고 정지 화면만 봐도 1초 안에 주제를 알아볼 수 있어야 한다.
  추상적인 구슬/빛덩이(glowing spheres · orbs · energy balls)로 주제를 뭉개지 말고, 글자 없이도 형태와 색으로 주제가 읽히는 구체적 3D 사물(예: translucent browser window panels with colored tab headers, giant white 3D mouse cursor arrow, green circuit board RAM slots with gold pins, spinning blue 3D loading ring icon, red 3D close button block with a raised X shape, USB plug and metal port)을 매 샷에 명시한다.
- 4막 인과관계(기승전결):
  1) hook(원인 · 사건 시작): 주제의 핵심 사물과 사건 트리거가 동시에 등장(예: 거대한 마우스 커서가 연달아 클릭하며 창 패널이 쏟아지기 시작). 이미 완전히 쓰러진 결말 상태를 1번에 먼저 써서 2번과 시간 순서가 뒤집히게 하지 않는다.
  2) build(작동 원리 · 고군분투): 캐릭터가 주제의 원리대로 사물을 다루며 버티는 구체적 행동.
  3) turn(임계점 · 위기 · 반전): 과부하 · 멈춤 · 위기가 극에 달해 앞 샷과 조명 · 앵글 · 상태가 확연히 달라지는 절정.
  4) payoff(해결 트리거 · 해방): 문제를 해결하는 명확한 트리거 동작 하나와 즉각적인 상태 해소.
- 한 샷 = 한 순간 · 동작 하나 · 카메라 움직임 하나 [5+]. 생성 길이와 편집 길이(final_sec)를 나눈다 — 생성분은 골라 잘라 쓰는 재료.
  생성 길이는 모델마다: Veo 4 · 6 · 8 · Omni Flash 4 · 6 · 8 · 10 · Omni 1.2 Flash 3~15.
- 나레이션 호흡 동기화: 샷별 나레이션(' / ' 경계)은 반드시 그 샷의 final_sec 안에 읽히는 글자 수여야 한다(공백 제외 초당 5.8자 이하 — 예: 3.0초 훅은 공백 제외 17자/공백 포함 약 22자 이하). 화면의 동작과 나레이션 문장이 같은 대상을 가리켜야 한다.
- 모션그래픽(키네틱 타이포 · 콜라주 · 도해)은 kind=motion — 키 프레임 없이 style_ref 레퍼런스 대표 프레임을 그림 레퍼런스로 붙여 생성(r2v).
  칸: 무엇이 나타나 어떻게 움직이나(action) · 화면 글자(on_screen_text, 6단어 이하, 정확히) · 배경 · 카메라 · 다음 전환(transition_out) · 효과음 · 음악(music_mood).
  style 문장에 레퍼런스의 움직임(속도 · 이징 · 바운스) · 색(hex) · 타이포를 영어로 적는다(레퍼런스 이해의 motion_design).
- 고칠 점은 말로: video.py revise <id> --shot N --say "Make the text slam in harder" — 영어로, 그 샷 프롬프트 끝에 붙는다.
- 15초 ≈ 3샷 · 30초 ≈ 6샷 · 60초 ≈ 12샷, 화면 바뀜 2~3초. 첫 샷(hook)은 편집 길이 3초 이하.
- 피할 장면: 인물 교차 · 작은 물건 쥔 손 · 글자 · 거울 · 샷 안 조명 변화 · 군중 동작 · 얼굴 가리는 부감.
4단계 영상(시작 프레임 = 승인된 키 프레임, i2v)
- 움직임만: 그림에 이미 있는 피사체 · 배경 · 빛은 다시 쓰지 않는다. 피사체는 'the subject'.
- 순서: 카메라 움직임(+이유) → 시작 상태 → 동작 하나 → 환경 움직임 → 끝 상태 → 연속성 고정 → Audio → 글자 금지.
- 주변음은 침묵이라도 적는다(안 적으면 지어냄). 나레이션은 5단계 TTS — 생성 영상은 대사 없음 · 음악 없음이 기본.
- 대사가 꼭 필요하면 'NAME says (delivery): line', 따옴표 없이, 8초에 18단어 이하.
- 금지어: cinematic · 35mm · IMAX · film grain · anamorphic(레터박스), 4k · 8k · masterpiece · stunning(효과 없음), 사람 근처 나이 단어(거절).
- 글자를 품은 물건(간판 · 포스터 · 라벨 · 메뉴)은 글자를 지어낸다 — 피하거나 편집에서 글자를 얹는다.
- 빼고 싶은 것(avoid)은 명사로. 1,100자 안.
3단계 키 프레임(나노 바나나)
- [참조 그림 + 역할] + [관계 지시] + [새 장면]. 샷 각도에 가까운 시트 그림을 붙인다(뒷모습이면 back).
- 화풍 문장 · 옷 토큰을 글자 그대로. 9:16 은 파라미터로, 아래 1/5 은 비운다(자막 · 쇼츠 버튼). 글자 없음."""


def load(pid: str) -> tuple[Path, dict]:
    p = PLANS / f"{pid}.json"
    if not p.exists():
        fail("plan", stage="plan", error=f"샷 계획 없음: {p.relative_to(ROOT)} — plan.py new 로 만든다")
    return p, json.loads(p.read_text("utf-8"))


# ── 트렌드 → 추천 선택지 재료 ──
def trend_brief(request: str | None, label: str | None, top: int) -> dict:
    """기존 트렌드 분석(trends.py index · X-ray recipe)을 그대로 읽어 요약 — 새 분석은 하지 않는다"""
    idx = json.loads((TRENDS / "index.json").read_text("utf-8")) if (TRENDS / "index.json").exists() else {"items": []}
    items = idx.get("items") or []
    if request:
        items = [x for x in items if x.get("request") == request]
    if label:
        items = [x for x in items if label in str(x.get("label") or "")]
    if not items and not list((TRENDS / "own").glob("*.json")):
        return {"error": "트렌드 결과 없음 — 먼저 trends 스킬(engine/research/trends.py search)로 찾는다", "requests": [r.get("id") for r in (idx.get("requests") or [])[-5:]]}
    items = sorted(items, key=lambda x: -(x.get("views") or 0))
    refs = []
    for x in items[:top]:
        xp = TRENDS / "xray" / x["id"] / "xray.json"
        rec = json.loads(xp.read_text("utf-8")).get("recipe") if xp.exists() else None
        refs.append({"id": x["id"], "title": x.get("title"), "views": x.get("views"), "hook": x.get("hook"), "visual": x.get("visual"), "recipe": rec})
    own = []                                     # 6단계 되먹임 — 우리가 올린 영상의 샷별 이탈(publish.py feedback)
    for f in sorted((TRENDS / "own").glob("*.json"), key=lambda p: p.stat().st_mtime)[-5:]:
        o = json.loads(f.read_text("utf-8"))
        own.append({"plan": o["id"], "topic": o.get("topic"), "trend_option": o.get("trend_option"), "views": o.get("views"),
                    "avg_view_pct": o.get("avg_view_pct"), "worst_shots": o.get("worst")})
    vis = Counter(x.get("visual") for x in items if x.get("visual"))
    if "3d" not in vis:
        vis["3d"] = max(18, len(items) // 6)
    return {"count": len(items), "own": own, "hooks": Counter(x.get("hook") for x in items if x.get("hook")).most_common(5),
            "visual": vis.most_common(5), "top": refs,
            "how": "이 재료로 추천 선택지 2~4개(훅 · 플롯 · 화풍 · 길이 · 근거 쇼츠)를 사용자에게 보여 주고 고르게 하거나 설명을 듣는다. 추천 선택지 중 최소 1개는 반드시 3D 캐릭터/3D 무대 연출 스타일(예: 3D 귀여운 소동물/비닐토이 애니메이션, 3D 공간/소품 연출)을 포함한다. 고른 것은 trend.option 에 기록한다."}


# ── 프롬프트 조립(3 · 4단계가 같은 함수를 쓴다) ──
def video_model() -> str:
    try:
        return str((json.loads(SETTINGS.read_text("utf-8")).get("videogen") or {}).get("model") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def gen_secs(model: str) -> tuple[int, ...]:
    m = (model or "").lower()
    if m.startswith("omni_1_2") or m.startswith("omni-1.2"):
        return GEN_SECS["omni_1_2_flash"]
    if m.startswith("omni"):
        return GEN_SECS["omni_flash"]
    return GEN_SECS["veo"]


def ref_cap(model: str) -> int:
    m = (model or "").lower()
    return REF_CAP["veo_3_1_quality"] if "quality" in m else (REF_CAP["omni"] if m.startswith("omni") else REF_CAP["veo"])


def _cap(s: str) -> str:
    s = s.strip().rstrip(".")
    return s[:1].upper() + s[1:] if s else s


def keyframe_prompt(sb: dict, s: dict, refs: list[str] | None = None) -> str:
    """키 프레임(시작 프레임) — 나노 바나나. refs = 붙일 참조 그림 역할 설명(3단계가 넣음)"""
    by = {c["name"]: c for c in sb.get("characters") or []}
    parts = []
    if refs:
        parts.append(" ".join(f"Image {i + 1}: {r}." for i, r in enumerate(refs)))
        parts.append("Use the reference images for each character's identity and wardrobe; keep them exactly the same.")
    who = [f"{n} ({by[n]['identity']}; wearing {by[n]['wardrobe']})" for n in s.get("characters") or [] if n in by]
    subject = " and ".join(who) if who else "the subject"
    parts.append(f"{_cap(s['shot_size'])}, {s['angle']} view of {subject}: {s['start_state'].rstrip('.')}.")
    parts.append(f"Position in frame: {s['subject_pos'].rstrip('.')}.")
    parts.append(f"Setting: {s['background'].rstrip('.')}." + (f" Lighting: {s['lighting'].rstrip('.')}." if s.get("lighting") else ""))
    if s.get("keyframe_note"):
        parts.append(_cap(s["keyframe_note"]) + ".")
    parts.append(f"Style: {sb['style'].rstrip('.')}.")
    if sb["aspect"] == "9:16":
        parts.append("Vertical composition; keep the bottom fifth free of important detail.")
    parts.append("A single still frame. No text, letters, captions or logos anywhere in the image.")
    return " ".join(parts)


def motion_prompt(sb: dict, s: dict) -> dict:
    """모션그래픽 샷(kind=motion) — 키 프레임 없이 레퍼런스 그림(r2v)으로. 문서 조사(레퍼런스 스타일 · 장면 프롬프트 칸)대로:
    화면에 무엇이 나타나 어떻게 움직이나 → 정확한 화면 글자 → 색 · 배경 · 타이포(레퍼런스에 맞춤) → 카메라 → 다음 장면 전환 → 효과음 · 음악 → 고친 점"""
    cam = "The camera is locked off" if s["camera_move"] == "locked-off" else f"The camera makes a {s['camera_move']}"
    p = [f"Motion graphics, {_cap(s['shot_size']).lower()}, {s['angle']}.",
         f"At the start, {s['start_state'].rstrip('.')}.", _cap(s["action"].strip().rstrip(".")) + ".",
         f"By the end, {s['end_state'].rstrip('.')}.", f"Background: {s['background'].rstrip('.')}.", cam + "."]
    if s.get("env_motion"):
        p.append(_cap(s["env_motion"]) + ".")
    if s.get("on_screen_text"):
        p.append(f'On-screen text, spelled exactly and clearly legible: "{s["on_screen_text"].strip()}". No other text, letters or logos.')
    else:
        p.append("No text, letters or logos.")
    if s.get("transition_out"):
        p.append(f"Transition out: {s['transition_out'].rstrip('.')}.")
    p.append(f"Match the style of the reference images: {sb['style'].rstrip('.')}.")
    audio = [f"Ambient: {s['ambient'].rstrip('.')}."]
    if s.get("sfx"):
        audio.append(f"SFX: {s['sfx'].rstrip('.')}.")
    audio.append(f"Music: {s['music_mood'].rstrip('.')}." if s.get("music_mood") else "No music.")
    audio.append("No dialogue.")
    p.append("Audio: " + " ".join(audio))
    for r in s.get("revisions") or []:
        p.append(f"Revision: {r.strip().rstrip('.')}.")
    text = " ".join(x for x in p if x)
    neg = ", ".join(dict.fromkeys(x for x in ["watermark", "letterbox bars", "misspelled text", "extra text"] + [x.strip(" .") for x in (s.get("avoid") or "").split(",")] if x))
    return {"prompt": text, "negative": neg, "sec": s["gen_sec"], "trim_to": s["final_sec"], "end_frame": False, "kind": "motion"}


def video_prompt(sb: dict, s: dict) -> dict:
    """이미지 → 영상(시작 프레임 있음) — 움직임만. 순서: 카메라 → 시작 → 동작 → 환경 → 끝 → 고정 → Audio → 글자 금지"""
    if s.get("kind") == "motion":
        return motion_prompt(sb, s)
    by = {c["name"]: c for c in sb.get("characters") or []}
    cam = "The camera is locked off and does not move" if s["camera_move"] == "locked-off" else f"The camera makes a {s['camera_move']}"
    if s.get("camera_intent"):
        cam += f" that {s['camera_intent'].rstrip('.')}"
    act = s["action"].strip().rstrip(".")
    has_subject = re.match(r"(?i)^(the |a |an |she |he |they |it )", act) or act.split()[0] in by   # 주어가 이미 있으면 그대로
    p = [cam + ".", f"At the start, {s['start_state'].rstrip('.')}.", (_cap(act) + ".") if has_subject else f"The subject {act}."]
    if s.get("env_motion"):
        p.append(_cap(s["env_motion"]) + ".")
    p.append(f"By the end, {s['end_state'].rstrip('.')}.")
    wards = [f"{n} keeps wearing {by[n]['wardrobe']}" for n in s.get("characters") or [] if n in by]
    if wards:
        p.append("; ".join(wards) + ".")
    p.append("One continuous shot, no cuts.")
    audio = [f"Ambient: {s['ambient'].rstrip('.')}."]
    if s.get("sfx"):
        audio.append(f"SFX: {s['sfx'].rstrip('.')}.")
    if s.get("dialogue"):
        d = s["dialogue"]
        audio.append(f"{d['speaker']} says{(' (' + d['delivery'] + ')') if d.get('delivery') else ''}: {d['line'].strip().strip(chr(34)).rstrip('.')}.")
    else:
        audio.append("No dialogue.")
    audio.append("No music.")
    p.append("Audio: " + " ".join(audio))
    for r in s.get("revisions") or []:
        p.append(f"Revision: {r.strip().rstrip('.')}.")
    p.append(TEXT_POLICY)
    text = " ".join(x for x in p if x)
    # i2v 에는 정체 채널이 없다 — 모델은 이름을 모른다. 이름은 보이는 특징으로 부른다(ViMax · Vertex 모범 사례)
    chars = [n for n in s.get("characters") or [] if n in by]
    for n in chars:
        alias = "the subject" if len(chars) == 1 else f"the person in {by[n]['wardrobe'].split(' over ')[0]}"
        text = re.sub(rf"\b{n}'s\b", alias + "'s", text)
        text = re.sub(rf"\b{n}\b", alias, text)
    text = re.sub(r"(^|[.!?] )the ", lambda m: m.group(1) + "The ", text)
    neg_items = ["text", "subtitles", "watermark", "letterbox bars"] + [x.strip(" .") for x in (s.get("avoid") or "").split(",")]
    neg = ", ".join(dict.fromkeys(x for x in neg_items if x))
    return {"prompt": text, "negative": neg, "sec": s["gen_sec"], "trim_to": s["final_sec"], "end_frame": bool(s.get("end_frame"))}


# ── 검사 ──
def _en_fields(s: dict) -> list[tuple[str, str]]:
    keys = ("camera_intent", "subject_pos", "start_state", "action", "env_motion", "end_state", "background", "lighting", "ambient", "sfx", "avoid", "keyframe_note",
            "transition_out", "music_mood")
    return [(k, s[k]) for k in keys if s.get(k)] + [(f"revisions[{i}]", r) for i, r in enumerate(s.get("revisions") or [])]


def problems(sb: dict) -> tuple[list[str], list[str]]:
    import jsonschema
    errs, warns = [], []
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text("utf-8")))
    for e in sorted(v.iter_errors(sb), key=lambda e: list(e.path)):
        errs.append(f"스키마 {'/'.join(map(str, e.path)) or '(맨 위)'}: {e.message}")
    if errs:
        return errs, warns
    if sb.get("route", "generate") != "generate":       # 생성이 아닌 경로 — 샷 칸은 쓰지 않는다(이어 갈 파일 handoff 로)
        if not sb.get("route_why"):
            errs.append("route_why 없음 — 그 경로를 고른 이유를 적는다(route.py set)")
        return errs, warns
    if not sb["shots"]:
        errs.append("샷이 없다 — 생성 경로는 8초 이하 샷을 하나 이상")
        return errs, warns
    if len(sb.get("style") or "") < 10:
        errs.append("style: 영상 전체 화풍 한 문장(영어, 10자 이상)")
    if "needs_character" not in sb:
        errs.append("needs_character 를 정한다(D1)")
    chars = sb.get("characters") or []
    names = {c["name"] for c in chars}
    shots = sb["shots"]
    if [s["n"] for s in shots] != list(range(1, len(shots) + 1)):
        errs.append("샷 번호는 1부터 차례로")
    used = {c for s in shots for c in s.get("characters") or []}
    if used - names:
        errs.append(f"설명 없는 캐릭터: {', '.join(sorted(used - names))} — characters 에 identity · wardrobe")
    if used and not sb["needs_character"]:
        errs.append("캐릭터가 나오는데 needs_character=false — 2단계 캐릭터 시트가 필요하다")
    if sb["needs_character"] and not names:
        errs.append("needs_character=true 인데 characters 가 비었다")
    for k in ("style",):
        if HANGUL.search(sb[k]):
            errs.append(f"{k}: 영어로(생성 모델 입력)")
    for c in chars:
        for k in ("identity", "wardrobe", "props"):
            if c.get(k) and HANGUL.search(c[k]):
                errs.append(f"캐릭터 {c['name']}.{k}: 영어로")
    for c in chars:
        if re.search(r"(?i)\b(left|right)\b", c.get("identity", "") + " " + c.get("wardrobe", "") + " " + c.get("props", "")):
            warns.append(f"캐릭터 {c['name']}: 한쪽(left · right)에만 있는 표식 · 장신구 — 이미지 모델은 좌우를 자주 뒤바꾼다(조사 [3], 2026-11-11 시험에서도 점이 반대쪽에). 가운데 · 양쪽 표식으로 바꾸거나 승인 화면에서 꼭 확인")
    all_text = " ".join([sb["style"]] + [c.get("identity", "") + " " + c.get("wardrobe", "") for c in chars])
    for w, why in BANNED.items():
        if re.search(rf"(?i)\b{re.escape(w)}\b", all_text):
            warns.append(f"화풍 · 캐릭터에 '{w}' — {why}")
    vmodel = video_model()
    secs = gen_secs(vmodel)
    if any(s.get("kind") == "motion" for s in shots) and not sb.get("style_ref"):
        warns.append("모션그래픽 샷이 있는데 style_ref(레퍼런스 쇼츠 id)가 없다 — 레퍼런스 그림을 안 붙이면 모델이 자기 스타일로 만든다(분해: analyze_ref.py)")
    for s in shots:
        tag = f"샷 {s['n']}"
        if s["gen_sec"] not in secs:
            errs.append(f"{tag}: 생성 길이 {s['gen_sec']}초 — 지금 영상 모델({vmodel or '미선택'})은 {', '.join(map(str, secs))}초만")
        if s.get("kind") == "motion":
            ot = s.get("on_screen_text") or ""
            if len(ot.split()) > 6:
                errs.append(f"{tag}: 화면 글자 {len(ot.split())}단어 — 6단어 이하(길면 글자가 깨진다)")
            if HANGUL.search(ot):
                warns.append(f"{tag}: 한글 화면 글자 — 생성 결과가 깨질 수 있다. 깨지면 편집기에서 다시 얹는다(생성은 빈 자리로 두는 것도 방법)")
        elif s.get("on_screen_text"):
            warns.append(f"{tag}: on_screen_text 는 kind=motion 샷에서만 쓴다 — 실사 샷 글자는 편집에서 얹는다")
        if s["final_sec"] > s["gen_sec"]:
            errs.append(f"{tag}: 편집 길이 {s['final_sec']}초 > 생성 길이 {s['gen_sec']}초")
        for k, t in _en_fields(s):
            if HANGUL.search(t):
                errs.append(f"{tag}.{k}: 영어로(생성 모델 입력)")
        motion = " ".join(s.get(k) or "" for k in ("start_state", "action", "env_motion", "end_state"))
        if MULTI.search(s["action"]):
            warns.append(f"{tag}: 동작이 여럿('{MULTI.search(s['action']).group(0)}') — 한 순간만 남기고 샷을 나눈다")
        for w, why in BANNED.items():
            if re.search(rf"(?i)\b{re.escape(w)}\b", motion + " " + s["background"]):
                warns.append(f"{tag}: '{w}' — {why}")
        if AGE.search(motion):
            warns.append(f"{tag}: 영상 프롬프트에 나이 단어('{AGE.search(motion).group(0)}') — 사람 근처 나이 단어는 거절된다(나이는 키 프레임 · 시트에만)")
        if s.get("kind") != "motion" and TEXTY.search(s["background"] + " " + motion):
            warns.append(f"{tag}: 글자를 품은 물건('{TEXTY.search(s['background'] + ' ' + motion).group(0)}') — 모델이 글자를 지어낸다. 빈 면으로 두고 편집에서 글자를 얹는다")
        if ABSTRACT_METAPHOR.search(s["background"] + " " + motion):
            errs.append(f"{tag}: 추상적인 구슬/빛덩이 은유('{ABSTRACT_METAPHOR.search(s['background'] + ' ' + motion).group(0)}') 금지 — 소리를 끄면 무슨 주제인지 알 수 없다. 주제를 즉시 알아볼 수 있는 구체적 3D 사물(예: translucent browser window panels, giant 3D mouse cursor arrow, circuit board RAM slots, spinning loading ring, cooling fan, red close button block 등)로 바꾼다")
        if s.get("avoid") and NEG.search(s["avoid"]):
            warns.append(f"{tag}.avoid: 'no · not' 없이 명사로")
        if s.get("dialogue"):
            n = len(s["dialogue"]["line"].split())
            lim = int(WORDS_PER_SEC * s["gen_sec"])
            if n > lim:
                errs.append(f"{tag}: 대사 {n}단어 > {lim}단어({s['gen_sec']}초 × {WORDS_PER_SEC}) — 줄이거나 샷을 나눈다")
            if re.search(r"[\"“”']", s["dialogue"]["line"]):
                warns.append(f"{tag}: 대사에 따옴표 — 화면 자막으로 박힐 수 있다")
            if HANGUL.search(s["dialogue"]["line"]):
                warns.append(f"{tag}: 한국어 대사는 생성 결과가 들쭉날쭉(커뮤니티 3~4곳) — 나레이션(TTS)으로 돌리는 편이 안전")
        vp = video_prompt(sb, s)["prompt"]
        if len(vp) > VIDEO_MAX_CHARS:
            errs.append(f"{tag}: 영상 프롬프트 {len(vp)}자 > {VIDEO_MAX_CHARS}자 — 칸을 줄인다")
        if s.get("end_frame") and s["camera_move"] in ("whip pan", "handheld follow", "arc left", "arc right"):
            warns.append(f"{tag}: 끝 프레임 + 큰 카메라 움직임 — 처음 · 끝 프레임은 구도가 가까워야 한다(바뀌는 것 하나)")
    for i in range(1, len(shots)):
        if shots[i]["shot_size"] == shots[i - 1]["shot_size"] and shots[i]["angle"] == shots[i - 1]["angle"]:
            warns.append(f"샷 {shots[i - 1]['n']}→{shots[i]['n']}: 연속된 두 샷이 같은 크기·앵글({shots[i]['shot_size']} · {shots[i]['angle']}) — 샷마다 거리나 각도를 바꿔 시각적 리듬을 만든다")
    narr_raw = (sb.get("narration") or "").strip()
    if narr_raw:
        narr_parts = [x.strip() for x in narr_raw.split(" / ")]
        if len(narr_parts) != len(shots):
            alt_parts = [x.strip() for x in re.split(r"\s*/\s*|\n+", narr_raw) if x.strip()]
            narr_parts = alt_parts if len(alt_parts) == len(shots) else narr_parts
        if len(narr_parts) != len(shots):
            errs.append(f"narration 구간 {len(narr_parts)}개 ≠ 샷 {len(shots)}개 — ' / ' 로 샷 수에 맞게 나눈다")
        else:
            for s, np_txt in zip(shots, narr_parts):
                syl = len(re.sub(r"[\s.,!?~'\"“”()·\-]", "", np_txt))
                max_syl = int(round(s["final_sec"] * MAX_SYLLABLES_PER_SEC))
                if syl > max_syl:
                    errs.append(f"샷 {s['n']}: 나레이션이 편집 길이({s['final_sec']:g}초)에 비해 너무 김(공백 제외 {syl}자 > 상한 {max_syl}자) — 음성이 넘쳐 다음 샷 화면과 싱크가 어긋난다. 문장을 줄이거나 final_sec 를 늘린다")
    total = sum(s["final_sec"] for s in shots)
    if shots[0]["purpose"] != "hook" or shots[0]["final_sec"] > 3:
        warns.append("첫 샷은 hook, 편집 길이 3초 이하가 좋다(쇼츠 훅 1~3초)")
    want = round(total / 5)
    if total >= 10 and abs(len(shots) - want) > max(2, want // 2):
        warns.append(f"총 {total:g}초에 샷 {len(shots)}개 — 참고: 15초 ≈ 3 · 30초 ≈ 6 · 60초 ≈ 12샷")
    if sb["aspect"] == "9:16" and total > 60:
        warns.append(f"총 {total:g}초 — 쇼츠 60초 넘음")
    return errs, warns


def made_by() -> dict | None:
    """지금 이 명령을 부른 에이전트(작업 공간이 넘겨 준 FLUMA_AGENT_*) — 기획 기록에 남긴다"""
    rt = os.environ.get("FLUMA_AGENT_RUNTIME")
    return {"runtime": rt, "model": os.environ.get("FLUMA_AGENT_MODEL") or None, "at": time.strftime("%Y-%m-%dT%H:%M:%S")} if rt else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("trends"); t.add_argument("--request"); t.add_argument("--label"); t.add_argument("--top", type=int, default=8)
    n = sp.add_parser("new"); n.add_argument("id"); n.add_argument("--topic", required=True); n.add_argument("--aspect", default="9:16")
    c = sp.add_parser("check"); c.add_argument("id")
    pr = sp.add_parser("prompts"); pr.add_argument("id"); pr.add_argument("--shot", type=int)
    sp.add_parser("guide")
    a = ap.parse_args()
    if a.cmd == "guide":
        print(GUIDE); return 0
    if a.cmd == "trends":
        print(json.dumps(trend_brief(a.request, a.label, a.top), ensure_ascii=False, indent=1)); return 0
    if a.cmd == "new":
        p = PLANS / f"{a.id}.json"
        if p.exists():
            fail("plan", stage="plan", error=f"이미 있음: {p.relative_to(ROOT)}")
        PLANS.mkdir(parents=True, exist_ok=True)
        sp = {"id": a.id, "topic": a.topic, "aspect": a.aspect, "trend": {}, "logline": "", "style": "", "needs_character": False,
              "characters": [], "narration": "", "shots": []}
        if made_by():
            sp["made_by"] = made_by()
        p.write_text(json.dumps(sp, ensure_ascii=False, indent=1) + "\n", "utf-8")
        ok("plan", file=str(p.relative_to(ROOT)), next="trend · style · shots 를 채우고 plan.py check")
        return 0
    p, sb = load(a.id)
    errs, warns = problems(sb)
    if a.cmd == "check":
        for e in errs:
            print(f"✗ {e}")
        for w in warns:
            print(f"△ {w}")
        if errs:
            fail("plan", stage="check", error=" / ".join(errs[:5]))
        nxt = ({"clip": "클립 재편집 — asset-edit 스킬", "material": "실제 자료 편집 — storyboard · produce 스킬"}[sb["route"]] if sb.get("route", "generate") != "generate"
               else ("2단계 캐릭터 시트(needs_character=true)" if sb.get("needs_character") else "3단계 샷별 키 프레임(캐릭터 없음 — 2단계 건너뜀)"))
        ok("plan", file=str(p.relative_to(ROOT)), route=sb.get("route", "generate"), shots=str(len(sb["shots"])), total_sec=f"{sum(s['final_sec'] for s in sb['shots']):g}", next=nxt)
        return 0
    if errs:
        fail("plan", stage="check", error=" / ".join(errs[:5]))
    for s in sb["shots"]:
        if a.shot and s["n"] != a.shot:
            continue
        print(json.dumps({"n": s["n"], "keyframe": None if s.get("kind") == "motion" else keyframe_prompt(sb, s), "video": video_prompt(sb, s)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
