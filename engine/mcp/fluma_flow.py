"""굵은 도구 — 에이전트는 판단할 때만 부르고, 정해진 순서는 서버가 돌린다(2026-11-25).

2026-11-25 실측: 한 편에 도구 호출 178번 · 모델 생각 12.1분 · $11.24. 캡처 → 쓰기 → 검사 → 빌드 → 정지 화면 → 검토 → 렌더 → 기다리기를
에이전트가 한 걸음씩 불렀다. 여기서는 판단 지점 넷만 남긴다.

  plan_submit   대본(+ 사실 · 만들 재료) → 즉시 검사 · 대본 검토(뒤에서) · 음성 · 재료 캡처를 동시에 시작
  design_submit 영상 방향 + 장면 설계(engine/craft/design_lang.py) → 칸별 검증 → 콘티 · 설계 파일 → 검사 → (음성 뒤) 빌드 · 검토 묶음
  design_patch  바뀐 장면만 → 다시 검증 · 빌드 · 그 장면 검토 묶음
  finish        검토 결과 → 완성 렌더 → 품질 관문 → 완성 또는 막음
잘게 나뉜 도구(prep_start · review_frames · render_start …)는 그대로 둔다 — 사람과 한 장면씩 다듬을 때.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fluma_jobs as jobs  # noqa: E402
import fluma_tools as tools  # noqa: E402
from fluma_jobs import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "engine" / "story"))
from craft import design_lang as dl  # noqa: E402

PY = sys.executable
SHOT_FN = ["자리 잡기", "힘", "압박", "디테일", "반응", "변화", "충격", "여운", "끝"]


def _schema_enums() -> tuple[list, list, list]:
    s = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
    sc = s["$defs"]["scene"]["properties"]
    return s["properties"]["format"]["enum"], sc["role"]["enum"], sc["screen"]["enum"]


def _visual_kinds() -> list:
    s = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
    return s["$defs"]["scene"]["properties"]["visual"]["properties"]["kind"]["enum"]


ASSET_FORMAT = (
    "재료(assets) 형식 — plan_submit(assets=[…]) 또는 assets_start: "
    '{"kind": "web", "name": "rfc790", "plan": {"start": "https://…", "viewport": [1280, 800], "scale": 2, "hide": ["css"], '
    '"steps": [{"do": "wait", "ms": 800}, {"do": "scroll", "by": 600}, {"do": "click", "target": "text=…"}]}} · '
    '{"kind": "term", "name": "ping", "cmd": ["ping", "-c", "2", "127.0.0.1"], "prompt": "$ ping -c 2 127.0.0.1", "mark": ["정규식"]} · '
    '{"kind": "icon", "names": ["python", "github"]} (Simple Icons 이름) · '
    '{"kind": "form", "name": "teapot", "form": {형태 JSON}, "style": "cel"}. '
    "결과(assets_status)의 src 를 설계 src 에 그대로(capture:이름 · 이름.svg · forms/이름.png), 볼 때는 preview(작은 그림)만 Read")


def language_card() -> str:
    """설계 언어 요약 — 도구 결과로 준다(엔진 코드 · 예시 파일을 읽지 않게)"""
    doc = (dl.__doc__ or "").split("설계 한 장면:", 1)[-1]
    fmts, roles, screens = _schema_enums()
    return ("장면 설계 언어(design_submit 의 scenes[].design):" + doc.rstrip() +
            f"\n허용 값 — 콘티 format: {' | '.join(fmts)} · 장면 role: {' | '.join(roles)} · screen: {' | '.join(screens)} · "
            f"visual_kind: {' | '.join(_visual_kinds())} · shot_fn: {' | '.join(SHOT_FN)}"
            "\n효과 id 는 engine/craft/craft_catalog.py search \"낱말\" 로 찾는다(빛번짐 · 렌즈 빛 · 흔들기 금지). "
            "그림은 plan_submit 이 돌려준 assets[].src 를 쓴다. 볼 때는 preview(작은 그림)만 Read.\n" + ASSET_FORMAT)


# ---------------- ① 대본 ----------------
HOOK_TYPES = ["질문", "예시", "상황", "증거 먼저", "전후 대비", "믿음 뒤집기", "숫자 주장", "궁금증 간격", "두 선택지", "고백"]
JOBS = ["질문", "예시", "상황", "시연", "증거", "비교", "비유", "반전", "답", "설명", "맺음"]
OPEN_JOBS = {"질문", "예시", "상황", "증거", "반전", "시연"}
SHOW_JOBS = {"예시", "상황", "시연", "비유", "비교"}
DIRECTION_CARD = (
    "구성부터(감독 · 작가 기준, 2026-11-25): 대본을 쓰기 전에 각도 · 구조를 정하고 훅 후보 3개를 서로 다른 여는 방식으로 쓴 뒤 고른다. "
    "여는 방식: " + " · ".join(HOOK_TYPES) + " — 정의 · 설명으로 시작하지 않는다(엄지가 멈출 이유가 없다). "
    "장면마다 할 일(job) 하나: " + " · ".join(JOBS) + ". 설명만 잇는 슬라이드 쇼 금지 — 예시 · 상황 · 시연 · 비유로 보여 주고, 앞 장면이 남긴 궁금증에 다음 장면이 답한다(질문 → 답, 기대 → 뒤집기). "
    "다섯 기둥(감정 · 모티프 · 기준 물건 · 꺾임 · 끝 그림)이 장면을 잇고, 장면마다 보는 사람의 눈이 갈 곳은 하나 — 글자 · 카드가 아니라 물건 · 화면 · 상황이 주인공.")


def _check_plan(script: dict) -> list[str]:
    """구성 검사 — 훅 · 장면 할 일이 슬라이드 쇼가 되지 않게. 2026-11-25 Opus 실측: 정의문 훅 + 설명 · 카드만 이어 '슬라이드 쇼 같다'"""
    out = []
    c = script.get("concept") or {}
    for k in ("angle", "structure"):
        if not str(c.get(k) or "").strip():
            out.append(f"script.concept.{k}: 필요함 — 대본보다 먼저 정한다")
    h = script.get("hook") or {}
    opts = h.get("options") or []
    if len(opts) < 3:
        out.append("script.hook.options: 훅 후보 3개 [{type, line}] — 서로 다른 여는 방식으로")
    else:
        bad = [i for i, o in enumerate(opts) if not isinstance(o, dict) or o.get("type") not in HOOK_TYPES or not str(o.get("line") or "").strip()]
        out += [f"script.hook.options[{i}]: {{type: {' | '.join(HOOK_TYPES)}, line: 첫 말}}" for i in bad]
        if not bad and len({o["type"] for o in opts}) < 2:
            out.append("script.hook.options: 여는 방식이 모두 같음 — 서로 다른 방식 2개 이상")
    if not isinstance(h.get("pick"), int) or not 0 <= h.get("pick", -1) < len(opts):
        out.append("script.hook.pick: 고른 후보 번호(0부터)")
    if not str(h.get("why") or "").strip():
        out.append("script.hook.why: 고른 이유 한 줄")
    jobs = [s.get("job") for s in script.get("scenes") or []]
    bad = [i + 1 for i, j in enumerate(jobs) if j not in JOBS]
    if bad:
        return out + [f"script.scenes[{i}].job: {' | '.join(JOBS)} 중 하나" for i in bad]
    if jobs and jobs[0] not in OPEN_JOBS:
        out.append(f"script.scenes[1].job: 첫 장면이 '{jobs[0]}' — 첫 장면은 {' · '.join(sorted(OPEN_JOBS))} 중 하나(설명 · 정의로 열지 않는다)")
    n_exp = sum(1 for j in jobs if j == "설명")
    if n_exp > max(1, int(len(jobs) * 0.4)):
        out.append(f"script.scenes[].job: 설명 {n_exp}/{len(jobs)}장면 — 슬라이드 쇼가 된다. 예시 · 상황 · 시연 · 비유 · 비교로 보여 준다")
    for i in range(1, len(jobs)):
        if jobs[i] == jobs[i - 1] == "설명":
            out.append(f"script.scenes[{i}~{i + 1}].job: 설명이 연달아 — 사이에 예시 · 질문 · 반전을")
            break
    if not SHOW_JOBS & set(jobs[1:]):
        out.append("script.scenes[].job: 본문에 예시 · 상황 · 시연 · 비유 · 비교가 하나도 없음")
    return out


def plan_submit(pid: str, script: dict, assets: list | None = None) -> dict:
    if not isinstance(script, dict) or not script.get("scenes"):
        raise ValueError("script 는 {title, format, audience, concept{angle, structure}, hook{options[3], pick, why}, scenes: [{role, job, narration, caption, screen}], research?: {facts}}")
    bad = _check_plan(script)
    if bad:
        raise ValueError(f"구성 오류 {len(bad)}건 — 대본보다 구성을 먼저 고친다: " + " · ".join(bad[:12]) + " | " + DIRECTION_CARD)
    tmp = ROOT / "data" / "workspace" / "tmp" / pid
    tmp.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "compositions" / pid / "skill_pass").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "compositions" / pid / "skill_pass" / "plan_card.json").write_text(
        json.dumps({"concept": script.get("concept"), "hook": script.get("hook"), "jobs": [s.get("job") for s in script["scenes"]]}, ensure_ascii=False, indent=1), "utf-8")
    plain = {k: v for k, v in script.items() if k not in ("hook",)}
    plain["scenes"] = [{k: v for k, v in s.items() if k != "job"} for s in script["scenes"]]
    f = tmp / "script.json"
    f.write_text(json.dumps({**plain, "id": pid}, ensure_ascii=False), "utf-8")
    r = subprocess.run([PY, "engine/story/bundle.py", "script", str(f.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, timeout=180,
                       env={**os.environ, "FLUMA_NO_KIT": "1"})
    if r.returncode != 0:
        bad = [ln[2:] for ln in r.stdout.splitlines() if ln.startswith("✗ ")]
        err = next((ln[6:] for ln in r.stdout.splitlines() if ln.startswith("error=")), "")
        raise ValueError("대본 막힘 — 대본만 고쳐 다시 plan_submit: " + " · ".join(bad or [err or (r.stderr or "")[-300:]]))
    sbp = ROOT / "data" / "compositions" / pid / "script.sb.json"
    ssb = json.loads(sbp.read_text("utf-8"))
    sb_path = ROOT / "data" / "storyboards" / f"{pid}.json"
    _write_words(pid, sb_path, ssb, script)
    prep = tools.prep_start(pid)
    out: dict = {"script": [{"scene": i, "role": x.get("role"), "narration": x.get("narration"), "caption": x.get("caption")}
                            for i, x in enumerate(ssb["scenes"], 1)],
                 "review": "시청자 · 각본가 검토는 뒤에서 — 고친 말은 음성 직전에 콘티로 옮긴다(막히면 design_submit 이 알린다)",
                 "prep_job": prep.get("id")}
    if assets:
        out["assets_job"] = assets_start(pid, assets).get("id")
    out["next"] = ("대본 검토(시청자 · 각본가)는 뒤에서 1~3분 — 기다리지 말고 장면을 설계해 design_submit 한 번. 검토가 대본을 막으면 design_submit 이 "
                   "설계는 저장한 채로 막힌 이유를 돌려준다(대사만 고쳐 plan_submit → design_patch 로 이어 감). 재료가 아직이면 assets_start")
    out["language"] = language_card()
    return out


def assets_start(pid: str, assets: list) -> dict:
    """재료 미리 만들기 작업(캡처 · 터미널 · 아이콘 · 형태) — 대본과 따로도 부를 수 있다"""
    if not isinstance(assets, list) or not assets:
        raise ValueError("assets 는 목록 — " + ASSET_FORMAT)
    bad = [f"assets[{i}]: kind {a.get('kind')!r} — web · term · icon · form" for i, a in enumerate(assets)
           if not isinstance(a, dict) or a.get("kind") not in ("web", "term", "icon", "form")]
    need = {"web": ("name", "plan"), "term": ("name", "cmd"), "icon": ("names",), "form": ("name", "form")}
    bad += [f"assets[{i}].{k}: 필요함" for i, a in enumerate(assets) if isinstance(a, dict) for k in need.get(a.get("kind"), ()) if not a.get(k)]
    if bad:
        raise ValueError(" · ".join(bad) + " — " + ASSET_FORMAT)
    tmp = ROOT / "data" / "workspace" / "tmp" / pid
    tmp.mkdir(parents=True, exist_ok=True)
    spec = tmp / "assets.req.json"
    spec.write_text(json.dumps(assets, ensure_ascii=False), "utf-8")
    (tmp / "assets.json").unlink(missing_ok=True)
    return jobs.submit("assets", [PY, "engine/mcp/fluma_assets.py", pid, str(spec.relative_to(ROOT))], project=pid, label=f"재료 미리 만들기 {pid}",
                       key=f"assets:{pid}", heavy=False, mem_gb=1.5, timeout=1800)


def _write_words(pid: str, sb_path: Path, ssb: dict, script: dict) -> None:
    """대본의 말로 최소 콘티를 쓴다(음성이 바로 돌게) — 이미 있으면 말 · 장면 수만 맞춘다(다른 칸은 그대로)"""
    import sbio
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import lint
    cps = lint.voice_cps(ssb)
    try:
        plan = json.loads((ROOT / "data" / "shotplans" / f"{pid}.json").read_text("utf-8"))
    except (OSError, ValueError):
        plan = {}
    scenes = [{"role": x.get("role"), "sec": round(max(1.5, len(str(x.get("narration") or "").replace(" ", "")) / cps + 0.4), 1),
               "caption": x.get("caption") or "", "narration": x.get("narration") or "", "visual": {"kind": "text"}}
              for x in ssb["scenes"]]
    jobs = [s.get("job") for s in script.get("scenes") or []]
    for s, j in zip(scenes, jobs):
        if j:
            s["beat"] = j
    if sb_path.exists():
        base = sbio.load(sb_path)
        mine = copy.deepcopy(base)
        mine["title"] = ssb.get("title") or mine.get("title")
        if script.get("concept"):
            mine["concept"] = {**(mine.get("concept") or {}), **script["concept"]}
        old = mine.get("scenes") or []
        if len(old) == len(scenes):
            for o, n in zip(old, scenes):
                o.update(role=n["role"], caption=n["caption"], narration=n["narration"], **({"beat": n["beat"]} if n.get("beat") else {}))
        else:
            mine["scenes"] = scenes
        sbio.save(sb_path, base, mine)
        return
    sb = {"id": pid, "version": 1, "format": ssb.get("format") or "concept", "language": "ko", "engine": "craft",
          "audience": ssb.get("audience") or script.get("audience") or "", "topic": plan.get("topic") or ssb.get("title"), "title": ssb.get("title"),
          "duration_sec": round(sum(s["sec"] for s in scenes)), "cta": script.get("cta") or (scenes[-1]["caption"] or ssb.get("title")),
          **({"reference": plan["reference"]} if isinstance(plan.get("reference"), list) else {}),
          **({"concepts_order": script["concepts_order"]} if script.get("concepts_order") else {}),
          **({"concept": script["concept"]} if script.get("concept") else {}),
          "sources": ssb.get("sources") or [], "scenes": scenes}
    sb_path.parent.mkdir(parents=True, exist_ok=True)
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _review_tool_failed(reason: str) -> bool:
    """검토가 '대본이 나빠서'가 아니라 검토를 못 해서 실패했나 — LLM 호출 오류 · 한도 · 시간 초과 · 결과 없음"""
    r = reason.lower()
    return any(k in r for k in ("claude 실패", "is_error", "api_error", "hit your", "limit", "rate", "timeout", "시간 초과", "결과 없이 끝남", "25분 안에"))


def assets_status(pid: str) -> dict:
    try:
        return json.loads((ROOT / "data" / "workspace" / "tmp" / pid / "assets.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"done": False, "items": []}


# ---------------- ② 설계 ----------------
VIDEO_KEYS = {"concept", "intent", "art", "anchors", "cta", "hashtags", "fonts", "concepts_order", "reference"}
ANCHORS = ("emotion", "motif", "object", "break", "final_image")
SCENE_KEYS = {"design", "beat", "shot_fn", "screen", "visual_kind"}


def _check_video(v: dict) -> list[str]:
    out = [f"video.{k}: 모르는 칸 — {sorted(VIDEO_KEYS)}" for k in v if k not in VIDEO_KEYS]
    c = v.get("concept") or {}
    for k in ("angle", "breaks", "structure"):
        if not str(c.get(k) or "").strip():
            out.append(f"video.concept.{k}: 필요함(영상마다 새로 — angle · structure 는 plan_submit 에 낸 것을 그대로)")
    a = v.get("art") or {}
    pal = a.get("palette") or {}
    for k in ("bg", "ink", "accent"):
        if not str(pal.get(k) or "").startswith("#"):
            out.append(f"video.art.palette.{k}: '#rrggbb'")
    for k in ("rule", "avoid"):
        if not str(a.get(k) or "").strip():
            out.append(f"video.art.{k}: 필요함")
    an = v.get("anchors") or {}
    for k in ANCHORS:
        if not str(an.get(k) or "").strip():
            out.append(f"video.anchors.{k}: 필요함(감독 다섯 기둥 — emotion 감정 · motif 모티프 · object 기준 물건 · break 꺾임 · final_image 끝 그림)")
    it = v.get("intent") or {}
    if not str(it.get("summary") or "").strip():
        out.append("video.intent.summary: 필요함")
    tags = v.get("hashtags") or []
    if not tags or any(not str(t).startswith("#") for t in tags):
        out.append("video.hashtags: ['#…', …] (모두 # 로 시작)")
    if not str(v.get("cta") or "").strip():
        out.append("video.cta: 필요함")
    out += _schema_errors(v)
    return out


def _schema_errors(v: dict) -> list[str]:
    """콘티 스키마의 같은 칸 규칙(길이 · 형식 · 허용 값)으로 미리 — 다 낸 뒤 lint 에서 알지 않게(2026-11-25: cta 길이)"""
    try:
        import jsonschema
        s = json.loads((ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json").read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    props = s.get("properties") or {}
    dprops = ((props.get("direction") or {}).get("properties") or {})
    for k, sub, val in [("cta", props.get("cta"), v.get("cta")), ("hashtags", props.get("hashtags"), v.get("hashtags")),
                        ("concept", props.get("concept"), v.get("concept")), ("intent", props.get("intent"), v.get("intent")),
                        ("reference", props.get("reference"), v.get("reference")), ("concepts_order", props.get("concepts_order"), v.get("concepts_order")),
                        ("art", dprops.get("art"), v.get("art")), ("anchors", dprops.get("anchors"), v.get("anchors"))]:
        if sub is None or val is None:
            continue
        sch = {**sub, "$defs": s.get("$defs", {})}
        for e in jsonschema.Draft202012Validator(sch).iter_errors(val):
            path = ".".join(str(x) for x in e.absolute_path)
            out.append(f"video.{k}{'.' + path if path else ''}: {e.message[:140]}")
    return out


def _check_scene(n: int, s: dict) -> list[str]:
    _, _, screens = _schema_enums()
    out = [f"scenes[{n}].{k}: 모르는 칸 — {sorted(SCENE_KEYS)}" for k in s if k not in SCENE_KEYS]
    if s.get("screen") is not None and s["screen"] not in screens:
        out.append(f"scenes[{n}].screen: '{s['screen']}' — {' | '.join(screens)}")
    if s.get("visual_kind") is not None and s["visual_kind"] not in _visual_kinds():
        out.append(f"scenes[{n}].visual_kind: '{s['visual_kind']}' — {' | '.join(_visual_kinds())}")
    if s.get("shot_fn") is not None and s["shot_fn"] not in SHOT_FN:
        out.append(f"scenes[{n}].shot_fn: '{s['shot_fn']}' — {' | '.join(SHOT_FN)}")
    if "design" in s:
        out += dl.validate(s["design"], f"scenes[{n}].design")
    return out


def _visual_of(d: dict) -> dict:
    kinds, texts, tags = [], [], []

    def walk(els):
        for e in els or []:
            kinds.append(e.get("kind"))
            if e.get("kind") == "text":
                texts.append(str(e.get("text") or ""))
            if e.get("kind") == "tag":
                tags.append(str(e.get("text") or ""))
            walk(e.get("children"))
    walk(d.get("els"))
    kind = ("screenshot" if "capture" in kinds else "code" if "code" in kinds else "still" if {"image", "form"} & set(kinds)
            else "icon" if "icon" in kinds else "list" if len(tags) >= 2 else "text")
    out = {"kind": kind}
    if texts or tags:
        out["primary"] = (texts or tags)[0][:80]
    if len(tags) >= 2:
        out["items"] = [x[:40] for x in tags[:5]]
    return out


def _cue_words(d: dict) -> list[tuple[str, str]]:
    out = []
    if (d.get("camera") or {}).get("on"):
        out.append(("camera.on", d["camera"]["on"]))

    def walk(els):
        for e in els or []:
            if e.get("on"):
                out.append((f"els[{e.get('id')}].on", e["on"]))
            for j, m in enumerate(e.get("emph") or []):
                if isinstance(m, dict) and m.get("on"):
                    out.append((f"els[{e.get('id')}].emph[{j}].on", m["on"]))
            if isinstance(e.get("exit"), dict) and e["exit"].get("on"):
                out.append((f"els[{e.get('id')}].exit.on", e["exit"]["on"]))
            walk(e.get("children"))
    walk(d.get("els"))
    return out


def _retarget(word: str, old: str, words: list[dict]) -> str | None:
    """고치기 전 대사에서 그 낱말의 자리(글자 비율)를 고친 대사의 같은 자리 낱말로 — 빌드의 $CUE 와 같은 생각(cues._at_frac)"""
    import re
    norm = lambda s: re.sub(r"[\W_]", "", str(s))  # noqa: E731
    o, k = norm(old), norm(word)
    if not o or not k or k not in o or not words:
        return None
    frac = (o.index(k) + len(k) / 2) / len(o)
    lens = [len(norm(w["text"])) for w in words]
    tot = sum(lens) or 1
    acc, best = 0, None
    for w, n_ in zip(words, lens):
        mid = (acc + n_ / 2) / tot
        if best is None or abs(mid - frac) < best[0]:
            best = (abs(mid - frac), w)
        acc += n_
    txt = re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", best[1]["text"].strip()) if best else ""
    return txt or None


def _set_cue(d: dict, where: str, new: str) -> None:
    """where(_cue_words 의 자리)에 새 낱말 — 뒤붙임(+0.3 · @end)은 그대로"""
    import re
    def swap(raw: str) -> str:
        m = re.match(r"^(.*?)((?:@end)?(?:[+-]\d+(?:\.\d+)?)?)$", str(raw))
        return new + (m.group(2) if m else "")
    if where == "camera.on":
        d["camera"]["on"] = swap(d["camera"]["on"]); return
    m = re.match(r"els\[(.+?)\]\.(on|exit\.on|emph\[(\d+)\]\.on)$", where)
    if not m:
        return

    def walk(els):
        for e in els or []:
            if e.get("id") == m.group(1):
                if m.group(2) == "on":
                    e["on"] = swap(e["on"])
                elif m.group(2) == "exit.on":
                    e["exit"]["on"] = swap(e["exit"]["on"])
                else:
                    e["emph"][int(m.group(3))]["on"] = swap(e["emph"][int(m.group(3))]["on"])
            walk(e.get("children"))
    walk(d.get("els"))


def _check_cues(pid: str, sm: dict[int, dict]) -> tuple[list[str], list[str]]:
    """보낸 설계 + 이미 저장된 설계의 on 낱말이 그 장면 음성에 있는지. 각본가가 대사를 고쳐 낱말이 사라졌으면
    고치기 전 자리의 낱말로 옮기고(설계에 반영) 알린다 — 2026-11-25: 그 한 낱말 때문에 설계 전체를 다시 냈다. 음성 전이면 건너뛴다"""
    from craft import cues
    sb = json.loads((ROOT / "data" / "storyboards" / f"{pid}.json").read_text("utf-8"))
    if not (ROOT / "data" / "audio" / f"{pid}.timing.json").exists():
        return [], []
    try:
        sub = (json.loads((ROOT / "data" / "compositions" / pid / "skill_pass" / "script_bg.json").read_text("utf-8")).get("submitted") or {}).get("scenes") or []
    except (OSError, ValueError):
        sub = []
    errs, notes = [], []
    for n in range(1, len(sb.get("scenes") or []) + 1):
        from_file = (sm.get(n) or {}).get("design") is None
        d = (sm.get(n) or {}).get("design")
        if d is None and dl.design_path(pid, n).exists():
            d = json.loads(dl.design_path(pid, n).read_text("utf-8"))
        if not d:
            continue
        try:
            words, _ = cues.scene_words(sb, n - 1)
        except RuntimeError:
            continue
        said = " ".join(w["text"].strip() for w in words)
        moved = False
        for where, raw in _cue_words(d):
            m = cues.CUE.fullmatch(f"$CUE:{raw}")
            word = m.group(1).strip() if m else str(raw)
            if cues.find(words, word, strict=False) is not None:
                continue
            old = (sub[n - 1].get("narration") if n - 1 < len(sub) else "") or ""
            new = _retarget(word, old, words)
            if new:
                _set_cue(d, where, new)
                moved = True
                notes.append(f"{n}장면 {where}: '{word}' → '{new}'(각본가가 고친 대사의 같은 자리)")
            else:
                errs.append(f"scenes[{n}].design.{where}: '{word}' — 들리는 낱말: {said[:100]}")
        if moved:
            if from_file:
                dl.design_path(pid, n).write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
            else:
                sm[n]["design"] = d
    return errs, notes


def _fx_ids(d: dict) -> list[str]:
    out = []

    def walk(els):
        for e in els or []:
            out.extend(f["id"] for f in e.get("fx") or [] if isinstance(f, dict) and f.get("id"))
            walk(e.get("children"))
    walk(d.get("els"))
    return list(dict.fromkeys(out))[:6]


def _wait_jobs(pid: str, budget: float) -> dict:
    """음성(prep) · 재료(assets) 작업이 끝나기를 기다린다(budget 초까지). 남은 작업 · 오류를 돌려준다"""
    t0 = time.time()
    state = {}
    for j in jobs.list_jobs(project=pid, limit=20):
        if j.get("kind") in ("prep", "assets") and j.get("status") in ("queued", "waiting", "running"):
            left = budget - (time.time() - t0)
            j = jobs.wait(j["id"], max(1.0, left)) if left > 1 else j
        if j.get("kind") in ("prep", "assets") and j.get("kind") not in state:
            state[j["kind"]] = {"id": j["id"], "status": j.get("status"), **({"error": str(j.get("error"))[:400]} if j.get("error") else {})}
    return state


def _apply(pid: str, video: dict | None, scenes: dict[int, dict]) -> list[int]:
    import sbio
    sp = ROOT / "data" / "storyboards" / f"{pid}.json"
    base = sbio.load(sp)
    sb = copy.deepcopy(base)
    if video:
        for k in ("concept", "intent", "cta", "hashtags", "concepts_order", "reference"):
            if k in video:
                sb[k] = video[k]
        d = sb.setdefault("direction", {})
        if "art" in video:
            d["art"] = {**(d.get("art") or {}), **video["art"]}
        if "anchors" in video:
            d["anchors"] = {k: video["anchors"][k] for k in ANCHORS if k in video["anchors"]}
        f = video.get("fonts") or {}
        if f.get("title"):
            d["font_title"] = f["title"]
        if f.get("body"):
            d["font_body"] = f["body"]
    changed = []
    for n, s in scenes.items():
        sc = sb["scenes"][n - 1]
        for k in ("beat", "shot_fn", "screen"):
            if k in s:
                sc[k] = s[k]
        if "design" in s:                              # 검사(L11 구체성 · L12 증거)가 보는 칸을 설계에서 채운다 — 에이전트가 따로 쓰지 않게
            sc["visual"] = {**(sc.get("visual") or {}), **_visual_of(s["design"])}
        if "visual_kind" in s:
            sc["visual"] = {**(sc.get("visual") or {}), "kind": s["visual_kind"]}
        if "design" in s:
            p = dl.design_path(pid, n)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(s["design"], ensure_ascii=False, indent=1), "utf-8")
            sc["features"] = _fx_ids(s["design"]) or sc.get("features") or []
            changed.append(n)
        if "design" in s or dl.design_path(pid, n).exists():
            dur = round(float(sc.get("sec") or 3) + 0.6, 2)
            ref = f"$DESIGN:{dl.design_path(pid, n).relative_to(ROOT)}"
            sc["materials"] = [{"id": f"s{n:02d}", "type": "craft", "app": "effectcraft", "new": {"duration": dur}, "place": "full",
                                "export": {"format": "mp4", "start": 0, "end": dur}, "steps": [{"id": "script.run", "params": {"name": f"s{n:02d}", "code": ref}}]}]
    import bundle
    bundle.normalize(sb)                                 # 형식 오타(정수 칸 소수 · 허용 값 철자)만 바로잡는다
    sbio.save(sp, base, sb)
    return changed


def _scene_map(scenes, n_total: int) -> dict[int, dict]:
    if isinstance(scenes, list):
        if len(scenes) != n_total:
            raise ValueError(f"scenes 는 장면 {n_total}개 전부(대본 순서) — 받은 것 {len(scenes)}개")
        return {i: s for i, s in enumerate(scenes, 1)}
    if isinstance(scenes, dict):
        out = {}
        for k, v in scenes.items():
            if not str(k).isdigit() or not 1 <= int(k) <= n_total:
                raise ValueError(f"없는 장면: {k}")
            out[int(k)] = v
        return out
    raise ValueError("scenes 는 목록(전부) 또는 {\"3\": {…}}")


def _submit(pid: str, video: dict | None, scenes, budget: float, partial: bool):
    sp = ROOT / "data" / "storyboards" / f"{pid}.json"
    if not sp.exists():
        raise ValueError("콘티가 없습니다 — plan_submit 부터")
    n_total = len(json.loads(sp.read_text("utf-8")).get("scenes") or [])
    sm = _scene_map(scenes, n_total) if not partial or scenes else {}
    errs = (_check_video(video) if (video and not partial) else []) + [e for n, s in sm.items() for e in _check_scene(n, s)]
    if not partial:
        errs += [f"scenes[{n}].design: 필요함" for n, s in sm.items() if "design" not in s]
    if errs:
        raise ValueError(f"설계 칸 오류 {len(errs)}건 — 그 칸만 고쳐 다시(다른 칸은 그대로 보내도 된다): " + " · ".join(errs[:30]))
    waited = _wait_jobs(pid, budget * 0.6)              # 음성이 끝나야 장면 길이 · 말 시각이 정해진다
    prep = waited.get("prep") or {}
    blocked = None
    if prep.get("status") == "error":
        import bundle
        g = bundle.script_gate(pid, wait=False)
        blocked = {"reason": g.get("reason") or str(prep.get("error"))[:600], **({"script": g["script"]} if g.get("script") else {})}
    sbj = json.loads(sp.read_text("utf-8"))
    for n, s in sm.items():                              # 미리 컴파일 — 없는 그림 · 캡처 같은 오류를 저장 전에 그 칸으로
        if "design" in s:
            try:
                dl.compile_scene(s["design"], sbj, n)
            except (ValueError, RuntimeError) as e:
                errs.append(f"scenes[{n}].design: {e}")
    if errs:
        raise ValueError(f"설계 오류 {len(errs)}건 — 그 칸만 고쳐 다시: " + " · ".join(errs[:20]))
    if blocked and _review_tool_failed(blocked.get("reason") or ""):   # 검토 도구(LLM 호출) 자체가 실패 — 대본 문제가 아니다
        changed = _apply(pid, video, sm)
        return {"saved_scenes": changed, "script_review_failed": str(blocked.get("reason"))[:300],
                "next": "대본 검토 도구가 실패했다(사용량 한도 · 네트워크 등 — 대본 문제 아님). 대사를 고치지 말고 같은 대본 그대로 plan_submit 을 다시 부른 뒤 "
                        "design_patch(scenes={}) 로 이어 간다(설계는 저장됨). 다시 실패하면 사용자에게 알린다"}
    if blocked:                                          # 대본 검토가 막았다 — 설계는 저장해 두고(대본만 고치면 그대로 쓴다) 이유를 돌려준다
        changed = _apply(pid, video, sm)
        return {"saved_scenes": changed, "script_blocked": blocked,
                "next": "막힌 이유대로 대사만 고쳐 plan_submit(장면 수가 같으면 설계는 그대로 남는다) → design_patch(scenes={}) 로 이어 간다"
                        "(낱말이 바뀐 장면은 서버가 같은 자리 낱말로 옮긴다)"}
    var = _variety(pid, sm) if any("design" in s for s in sm.values()) else []
    if var:
        raise ValueError(f"화면 다양성 {len(var)}건 — 그 장면 설계만 바꿔 다시: " + " · ".join(var))
    bad, moved = _check_cues(pid, sm)                    # 음성이 끝났으면 말에 맞출 낱말을 지금 대조한다(빌드에서 멈추지 않게)
    if bad:
        raise ValueError(f"말 낱말(on) 오류 {len(bad)}건 — 그 칸만 들리는 낱말로 고쳐 다시: " + " · ".join(bad[:20]))
    changed = _apply(pid, video, sm)
    lt = tools.lint(pid)
    out: dict = {"saved_scenes": changed, "jobs": waited, **({"cues_moved": moved} if moved else {})}
    if not lt["pass"]:
        out.update(lint_fail=lt["fail"][:20], next="막힌 칸을 design_patch 로 고친다(그 장면 · 칸만)")
        return out
    if prep.get("status") not in (None, "done"):
        out["next"] = "음성이 아직 — 잠시 뒤 review_frames(빌드 · 정지 화면) 또는 design_patch 를 부르면 이어 간다"
        return out
    rv, imgs = tools.review_frames(pid, scenes=(sorted(sm) if partial else None))
    out["review"] = {k: rv[k] for k in ("stills", "visual_tell", "design_precheck", "unchanged_note", "previous_problems") if k in rv}
    out["advise"] = lt["advise"][:12]
    out["next"] = ("정지 화면을 보고: 고칠 장면이 있으면 design_patch(그 장면만) · 없으면 finish(problems=[]) — finish 가 완성 렌더 · 품질 관문까지 한다")
    return out, imgs


def design_submit(pid: str, video: dict, scenes: list, budget: float = 280):
    cur = _current_video(pid)                            # plan_submit 에 낸 구성(각도 · 구조)은 다시 쓰지 않아도 된다
    video = {**video, "concept": {**(cur.get("concept") or {}), **((video or {}).get("concept") or {})}}
    return _submit(pid, video, scenes, budget, partial=False)


PLAIN = {"text", "tag", "box", "circle", "ring", "line", "arrow"}


def _kinds(d: dict) -> set:
    out = set()

    def walk(els):
        for e in els or []:
            out.add(e.get("kind"))
            walk(e.get("children"))
    walk(d.get("els"))
    return out


def _bg_key(d: dict, pal: dict) -> tuple[str, float]:
    bg = d.get("bg") or "bg"
    first = bg[0] if isinstance(bg, list) else bg
    hx = pal.get(first, first) if isinstance(first, str) else "#000000"
    try:
        r, g, b = (int(str(hx).lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    except ValueError:
        lum = 0.5
    return (str(bg), lum)


def _variety(pid: str, sm: dict[int, dict]) -> list[str]:
    """화면 다양성 — 글자 · 상자만인 장면, 같은 바탕 반복, 어두운 바탕 비율(screen_rules 와 같은 기준, 2026-11-25 Opus 실측: 5/7 장면이 같은 남색 · 상자 + 글자)"""
    sb = json.loads((ROOT / "data" / "storyboards" / f"{pid}.json").read_text("utf-8"))
    n = len(sb.get("scenes") or [])
    designs = {}
    for i in range(1, n + 1):
        d = (sm.get(i) or {}).get("design")
        if d is None and dl.design_path(pid, i).exists():
            d = json.loads(dl.design_path(pid, i).read_text("utf-8"))
        if d:
            designs[i] = d
    if len(designs) < max(3, n - 1):
        return []
    out = []
    plain = [i for i, d in designs.items() if _kinds(d) <= PLAIN and sb["scenes"][i - 1].get("role") not in ("outro", "cta")]
    cap = max(1, int(n * 0.3))
    if len(plain) > cap:
        out.append(f"화면: 글자 · 상자만인 장면 {len(plain)}/{n}({', '.join(map(str, plain))}장면) — {cap}개까지. 주인공을 물건 · 화면 · 상황으로: "
                   "form(사물 · 인물) · capture(+ marks 강조 · zoom 확대) · icon · image · code(직접 연출)")
    pal = dl._palette(sb)
    keys = [_bg_key(d, pal) for d in designs.values()]
    from collections import Counter
    top, cnt = Counter(k for k, _ in keys).most_common(1)[0]
    if cnt > max(2, n // 2):
        out.append(f"화면: 같은 바탕 {top} 이 {cnt}/{n}장면 — 이야기의 장이 바뀌면 바탕을 바꾼다({min(4, n)}가지 이상)")
    dark = sum(1 for _, l in keys if l < 0.2)
    if dark > max(1, n // 2):
        out.append(f"화면: 어두운 바탕 {dark}/{n}장면 — 절반 이하로(장면의 장소 · 물건 색에서)")
    return out


def design_patch(pid: str, scenes: dict | None = None, video: dict | None = None, budget: float = 280):
    if video:
        bad = _check_video({**_current_video(pid), **video})
        if bad:
            raise ValueError("video 칸 오류: " + " · ".join(bad))
    return _submit(pid, video, scenes or {}, budget, partial=True)


def _current_video(pid: str) -> dict:
    sb = json.loads((ROOT / "data" / "storyboards" / f"{pid}.json").read_text("utf-8"))
    d = sb.get("direction") or {}
    return {"concept": sb.get("concept") or {}, "intent": sb.get("intent") or {}, "art": d.get("art") or {}, "anchors": d.get("anchors") or {},
            "cta": sb.get("cta"), "hashtags": sb.get("hashtags") or [], **({"reference": sb["reference"]} if sb.get("reference") else {})}


# ---------------- ④ 마무리 ----------------
def finish(pid: str, problems: list | None = None, looked: list | None = None, notes: str = "", budget: float = 280) -> dict:
    sb = json.loads((ROOT / "data" / "storyboards" / f"{pid}.json").read_text("utf-8"))
    n = len(sb.get("scenes") or [])
    seen = tools._seen(pid)
    if seen.get("stamp") != tools.build_stamp(pid) or set(range(1, n + 1)) - set(seen.get("scenes") or []):
        tools.review_frames(pid, images=False)           # 지금 빌드를 다 봤다는 기록 — 에이전트는 바뀐 장면을 이미 design_* 결과로 봤다
    rs = tools.review_submit(pid, problems or [], looked or list(range(1, n + 1)), notes)
    if rs.get("blocking"):
        return {"review": rs, "next": "막는 문제를 design_patch 로 고친 뒤 finish 다시"}
    job = tools.render_start(pid, "final")
    j = jobs.wait(job["id"], budget)
    if j.get("status") != "done":
        return {"job": jobs.brief(j), "next": f"완성 렌더가 도는 중 — job_wait('{job['id']}') 뒤 quality_gate"}
    qg = tools.quality_gate(pid)
    return {"video": (qg or {}).get("video"), "quality_gate": qg,
            "next": "막음 0 이면 완성 — 영상을 보여 주고 끝낸다" if not (qg or {}).get("block") else "막음을 design_patch 로 고친 뒤 finish 다시"}
