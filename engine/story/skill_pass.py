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
import re
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

SKILLS = ROOT / ".claude" / "skills"
SHOT_FN = ["자리 잡기", "힘", "압박", "디테일", "반응", "변화", "충격", "여운", "끝"]
ANCHORS = ["emotion", "motif", "object", "break", "final_image"]


def skill_text(name: str) -> str:
    t = (SKILLS / name / "SKILL.md").read_text("utf-8")
    return re.sub(r"^---[\s\S]*?---\n", "", t)


def sfx_names() -> list[str]:
    names = set()
    for d in (ROOT / "assets" / "sfx", ROOT / "engine" / "assets" / "sfx"):
        names.update(p.stem for p in d.glob("*.wav")) if d.exists() else None
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
    """헤드리스 Claude Code — MCP · 설정 없이, JSON 하나를 돌려받는다. tools="Read" + dirs 면 그 폴더의 그림을 직접 본다(정지 화면 검토)"""
    cmd = ["claude", "-p", "--output-format", "json", "--system-prompt", system, "--tools", tools, "--strict-mcp-config",
           "--disable-slash-commands", "--no-session-persistence", "--setting-sources", ""]
    for d in dirs or []:
        cmd += ["--add-dir", d]
    if tools:
        cmd += ["--allowedTools", *(allowed or [tools])]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if r.returncode:
        raise RuntimeError(f"claude 실패: {(r.stderr or r.stdout)[-400:]}")
    out = json.loads(r.stdout)
    txt = out.get("result") or ""
    m = re.search(r"\{[\s\S]*\}", txt)
    if not m:
        raise RuntimeError(f"JSON 없음: {txt[:300]}")
    return json.loads(m.group(0)), float(out.get("total_cost_usd") or 0)


SYS = ("너는 Fluma 쇼츠 제작 파이프라인의 '{role}' 단계다. 아래 스킬 문서를 규칙 그대로 적용해 콘티를 고친다. "
       "추측으로 사실 · 수치를 만들지 않는다(조사 사실 목록에 있는 것만). 출력은 JSON 하나뿐 — 설명 문장 없이. 형식: {fmt}")


# ── 단계별: 프롬프트 · 적용 ──
def viewer_io(sb: dict, sbp: Path) -> tuple[str, str]:
    """시청자 시뮬레이션 — 콘티의 대상 시청자가 장면 순서대로 따라가며 이해가 끊기는 곳을 짚는다(2026-11-11: 개념을 설명 없이 던져 '이해가 안 된다')"""
    fmt = ('{"known_before": ["시청자가 이미 아는 것"], "issues": [{"scene": 번호, "kind": "처음 보는 말|설명 없는 숫자|흐름 끊김|왜?|넘김", "what": "걸린 말 · 화면", '
           '"fix_by": "writer(대사로 풀림)|story(장면을 더하거나 순서를 바꿔야 함)", "how": "어떻게 풀면 되나"}], "understood": "끝까지 본 뒤 내가 이해한 한 줄", "score": 0~10}')
    v = view(sb)
    seq = [{"n": x["n"], "말": x["narration"], "화면 글자": x["caption"], "화면": [m.get("what") or m.get("type") for m in x["materials"]]} for x in v["scenes"]]
    p = (f"# 너는 이 사람이다\n{sb.get('audience') or '이 주제를 처음 보는 일반인'} — 이 주제를 따로 공부한 적은 없다. 쇼츠를 넘기다 이 영상을 처음 본다.\n\n"
         f"# 장면 순서대로 보이는 것(소리 · 화면 글자 · 화면)\n{json.dumps(seq, ensure_ascii=False)}\n\n"
         "할 일: 한 장면씩 차례로 본다. 그 시점까지 나온 것만 안다고 치고, 처음 보는 낱말 · 무엇의 숫자인지 모르는 숫자 · 앞 장면과 이어지지 않는 점프 · '그래서 왜?'가 드는 곳 · 넘기고 싶은 곳을 모두 적는다. "
         "작가 편을 들지 말고 진짜 처음 보는 사람처럼 냉정하게. 다 보고 나서 내가 이해한 한 줄과 이해도 점수를 준다.")
    return SYS.format(role="시청자", fmt=fmt), p


def viewer_apply(sb: dict, patch: dict) -> list[str]:
    return []                                   # 콘티를 고치지 않는다 — 걸린 것을 writer · story 로 넘긴다


def writer_io(sb: dict, sbp: Path) -> tuple[str, str]:
    import aitell
    found = aitell.find(sb)
    fmt = '{"script": "장면 경계 / 로 나눈 전체 대본(장면 수와 같은 칸 수)", "captions": {"장면 번호": "화면 글자(28자 이하, 말을 받아 적지 않음)"}, "title": "고정 제목(24자 이하)", "why": ["고친 이유"]}'
    p = (f"# 스킬: writer\n{skill_text('writer')}\n\n# 함께: humanizer-ko\n{skill_text('humanizer-ko')[:9000]}\n\n"
         f"# 조사 사실(이것만 쓴다)\n" + "\n".join(facts(sb)) + "\n\n# 레퍼런스와 견준 검토표\n" + ref_review(sbp) +
         f"\n\n# 시청자 시뮬레이션이 걸린 곳(대사로 풀 것 — 개념은 쓰기 전에 쉬운 말로 소개, 숫자는 무엇의 숫자인지 먼저)\n{json.dumps(viewer_issues(sb, 'writer'), ensure_ascii=False)}"
         f"\n\n# 감지기가 찾은 AI 티(꼭 고친다)\n{json.dumps(found, ensure_ascii=False)}\n\n# 콘티\n{json.dumps(view(sb), ensure_ascii=False)}\n\n"
         "할 일: writer 스킬 5장 '내기 전 스스로 검사'를 모두 통과하게 script · caption · title 을 고친다. 장면 수와 순서는 그대로. 뜻(사실)은 바꾸지 않는다. 고칠 게 없으면 원래 값을 그대로 돌려준다.")
    return SYS.format(role="각본가", fmt=fmt), p


def viewer_issues(sb: dict, who: str) -> list:
    f = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / "viewer.json"
    try:
        iss = (json.loads(f.read_text("utf-8")).get("patch") or {}).get("issues") or []
    except (OSError, ValueError):
        return []
    return [i for i in iss if i.get("fix_by", "writer").startswith(who)]


def writer_apply(sb: dict, patch: dict) -> list[str]:
    ch = []
    scn = sb.get("scenes") or []
    if isinstance(patch.get("script"), str):
        parts = [x.strip() for x in patch["script"].split("/")]
        if len(parts) == len(scn) and all(parts):
            if patch["script"] != sb.get("script"):
                sb["script"] = patch["script"]
                for s, t in zip(scn, parts):
                    s["narration"] = t
                ch.append("script")
        else:
            ch.append(f"script 버림(칸 {len(parts)} ≠ 장면 {len(scn)})")
    for k, v in (patch.get("captions") or {}).items():
        i = int(k) - 1
        if 0 <= i < len(scn) and isinstance(v, str) and 0 < len(v) <= 28 and v != scn[i].get("caption"):
            scn[i]["caption"] = v
            ch.append(f"s{i + 1}.caption")
    if isinstance(patch.get("title"), str) and 0 < len(patch["title"]) <= 24 and patch["title"] != sb.get("title"):
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
    fmt = ('{"direction": {"layout": "full|band", "subs": {"y": 0~1, "box": true|false}, "screen_text_y": 0~1, "font_title": "", "font_body": "", "cam_push": 1.0~1.1}, '
           '"materials": {"재료 id": {"adjust": {"scale": 배수(0.6~1.6), "dx": 화면 너비 비율(-0.25~0.25), "dy": 화면 높이 비율(-0.25~0.25)}, "color": "#RRGGBB(overlay 주석만)"}}, "ui_scenes": [{"scene": 장면 번호, "replace": "바꿀 재료 id 또는 null", "what": "앱 화면 설명", "components": ["Table", "Badge"]}], "why": ["이유"]}')
    vr = subprocess.run([sys.executable, str(ROOT / "engine" / "craft" / "craft_variety.py"), "check", str(sbp)], capture_output=True, text=True, timeout=120).stdout[-2000:]
    p = (f"# 스킬: designer\n{skill_text('designer')}\n\n# 재료 다양성 검사(crafts 스킬 0절 — 반복이 있으면 장면 구도 · 크기로 다르게)\n{vr}\n\n# 앱 화면 규칙(crafts 스킬)\n{astryx}\n\n# 레퍼런스 실측(style.md)\n{st}\n\n# 콘티\n{json.dumps(view(sb, True), ensure_ascii=False)}\n\n"
         "할 일: designer 3장 검사(시선 한 곳 · 안전 영역 · 띠를 70% 이상 채움 · 글자 세 단계 · 앞 장면과 다른 구도)를 통과하게 값을 정한다. "
         "실험 결과 · 로그 · 데이터가 '앱 화면'으로 보이면 더 진짜 같은 장면만 ui_scenes 로 고른다(없으면 빈 배열). 실제 촬영 · 실제 출력 화면은 바꾸지 않는다.")
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
    for k in ("font_title", "font_body"):
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
    sid = sb["id"]
    n = int(item.get("scene") or 0)
    name = f"s{n:02d}_app"
    ui = ROOT / "data" / "compositions" / sid / "ui" / f"{name}.tsx"
    ui.parent.mkdir(parents=True, exist_ok=True)
    sc = (sb.get("scenes") or [])[n - 1]
    ex = (ROOT / "tools" / "ui-scenes" / "examples" / "db-table.tsx").read_text("utf-8")
    sysm = "너는 Astryx(Meta 디자인 시스템) React 장면 파일을 쓰는 디자이너다. 출력은 JSON 하나: {\"tsx\": \"파일 전체\"}. 컴포넌트 속성은 문서 그대로(추측 금지)."
    prompt = (f"# 만들 화면\n{item.get('what')}\n장면 나레이션: {sc.get('narration')}\n화면 글자: {sc.get('caption')}\n\n# 컴포넌트 문서\n{astryx_doc(item.get('components') or ['Card', 'Text'])}\n\n"
              f"# 예시 파일(형식만 — 내용은 새로)\n{ex}\n\n규칙: `export default function Scene()` 하나, 데이터는 파일 안에, 세로 9:16 화면 높이를 위아래로 꽉 채운다(padding 48, 빈 아래쪽 금지), "
              "영상에서 읽히게 크게(본문 글자 약 40px · 숫자 56px 이상 — style 로 키운다), 한 화면에 볼 곳 하나, 한국어, 실제 데이터만(콘티에 있는 숫자).")
    err = ""
    for _ in range(2):
        res, c = claude(sysm, prompt + (f"\n\n# 직전 빌드 오류(고친다)\n{err}" if err else ""))
        cost.append(c)
        ui.write_text(res.get("tsx", ""), "utf-8")
        bg = str((sb.get("direction") or {}).get("color_bg") or "#000000").lstrip("#")
        light = sum(int(bg[i:i + 2], 16) for i in (0, 2, 4)) / 765 > 0.5 if len(bg) >= 6 else False   # 영상 바탕이 밝으면 밝은 테마
        r = subprocess.run(["node", str(ROOT / "tools" / "ui-scenes" / "build.mjs"), str(ui), str(ui.with_suffix("")), "--mode", "light" if light else "dark", "--png", "1080x1920"], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            return str(ui.relative_to(ROOT))
        err = (r.stderr or r.stdout)[-2500:]
    return None


def stills(sb: dict, sbp: Path) -> list[str]:
    """장면마다 가운데 시각의 정지 화면(engine/core/still.py) — 렌더가 끝난 뒤"""
    tm = json.loads((ROOT / "data" / "public" / "audio" / f"{sb['id']}.timing.json").read_text("utf-8"))
    ts = [f"{(float(t['start']) + float(t['end'])) / 2:.2f}" for t in tm]
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "core" / "still.py"), str(sbp), *ts], capture_output=True, text=True, timeout=900)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip().endswith(".png")]


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


def review_io(sb: dict, sbp: Path) -> tuple[str, str]:
    imgs = stills(sb, sbp)
    sheet = ROOT / "data" / "compositions" / sb["id"] / "craft" / "review" / "sheet.png"
    fmt = ('{"direction": {"subs": {"y": 0.55~0.82, "box": true|false}, "screen_text_y": 0.08~0.3}, "materials": {"재료 id": {"adjust": {"scale": 0.6~1.6, "dx": -0.25~0.25, "dy": -0.25~0.25}, "color": "#RRGGBB(overlay 주석만)"}}, '
           '"problems": [{"scene": 번호, "what": "본 문제"}], "why": ["이유"]}')
    p = (f"# 스킬: designer (3장 '보고 고친다'가 이 단계)\n{skill_text('designer')}\n\n# 콘티\n{json.dumps(view(sb, True), ensure_ascii=False)}\n\n"
         "# 볼 그림(Read 로 하나씩 연다 — 장면 순서)\n" + "\n".join(f"장면 {i + 1}: {x}" for i, x in enumerate(imgs)) + (f"\n레퍼런스와 나란히: {sheet}" if sheet.exists() else "") +
         "\n\n할 일: 그림을 실제로 열어 보고 designer 3장 1~5 를 장면마다 확인한다 — 특히 글자 · 숫자 · 주석이 서로 겹침, 재료가 화면 밖으로 잘림(증거 줄 · 글자), "
         "띠 안 주인공이 70% 미만, 안전 영역 침범. 문제 있는 장면만 값으로 고친다(문제가 없으면 materials 를 비운다). 본 문제는 problems 에 적는다.")
    return SYS.format(role="디자이너(정지 화면 검토)", fmt=fmt), p


OWNER = {"writer": ("L03", "L04", "L05", "L08", "L13", "L14", "L31", "L51", "L52", "L55"), "director": ("L41", "L50", "L54", "L29", "L32"), "designer": ("L12", "L33", "L34", "L35", "L53")}


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


def run_pass(name: str, sbp: Path, force: bool, issues: list[str] | None = None) -> dict:
    sb = json.loads(sbp.read_text("utf-8"))
    rec_p = ROOT / "data" / "compositions" / sb["id"] / "skill_pass" / f"{name}.json"
    rec_p.parent.mkdir(parents=True, exist_ok=True)
    io, apply = PASSES[name]
    system, prompt = io(sb, sbp)
    if issues:
        prompt += "\n\n# 검사(lint)가 막은 것 — 이 단계 담당, 꼭 고친다(스킬 규칙과 함께 만족시키는 방법으로)\n" + "\n".join(issues)
    h = hashlib.sha1((system + prompt).encode()).hexdigest()[:16]
    if not force and rec_p.exists() and json.loads(rec_p.read_text("utf-8")).get("hash") == h:
        return {"pass": name, "skipped": "입력 그대로"}
    if name == "review":
        patch, cost = claude(system, prompt, timeout=1500, tools="Read", dirs=[str(ROOT / "data" / "workspace" / "stills"), str(ROOT / "data" / "compositions" / sb["id"])])
    else:
        patch, cost = claude(system, prompt)
    costs = [cost]
    changed = apply(sb, patch)
    if name == "designer":
        for it in patch.get("ui_scenes") or []:
            try:
                ui = build_ui(sb, it, costs)
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                changed.append(f"앱 화면 실패: {e}")
                continue
            if ui:
                n = int(it["scene"]); sc = sb["scenes"][n - 1]
                mats = sc.setdefault("materials", [])
                new = {"id": f"s{n:02d}app", "type": "ui_mock", "device": "phone", "mock": True, "ui": ui, "what": it.get("what")}
                rep = it.get("replace")
                idx = next((k for k, m in enumerate(mats) if m.get("id") == rep), None)
                if idx is not None:
                    mats[idx] = new
                else:
                    mats.append(new)
                changed.append(f"s{n}.ui_mock(Astryx)")
            else:
                changed.append(f"s{it.get('scene')} 앱 화면 빌드 실패(타입 검사 2번)")
    sbp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
    # 적용 뒤 입력 해시(다음엔 건너뛰게)
    system2, prompt2 = io(sb, sbp)
    rec = {"pass": name, "hash": hashlib.sha1((system2 + prompt2).encode()).hexdigest()[:16], "changed": changed, "why": patch.get("why"), "problems": patch.get("problems") or patch.get("issues"), "score": patch.get("score"), "understood": patch.get("understood"), "cost_usd": round(sum(costs), 4), "patch": patch}
    rec_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    return {k: rec[k] for k in ("pass", "changed", "why", "problems", "score", "understood", "cost_usd") if rec.get(k) is not None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", choices=["all", "viewer", "writer", "director", "designer", "review", "refine", "status"])
    ap.add_argument("storyboard")
    ap.add_argument("--force", action="store_true")
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
    if a.which == "refine":
        try:
            r = run_refine(sbp)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            fail("skill_pass", stage="refine", error=str(e)[:400])
        print(f"[스킬 단계] {json.dumps(r, ensure_ascii=False)}", flush=True)
        ok("skill_pass", passes=json.dumps([r], ensure_ascii=False))
        return 0
    try:
        if a.which == "all":
            out.append(run_pass("viewer", sbp, a.force))
            print(f"[스킬 단계] {json.dumps(out[-1], ensure_ascii=False)}", flush=True)
            sbn = json.loads(sbp.read_text("utf-8"))
            story = viewer_issues(sbn, "story")
            if story:                                  # 장면을 더하거나 순서를 바꿔야 풀리는 이해 문제 — 대사 다듬기로는 안 된다
                fail("skill_pass", stage="story", error="시청자 시뮬레이션: 콘티 구조를 다시 써야 함 — " + " / ".join(f"{i.get('scene')}장면 {i.get('kind')}: {i.get('what')} → {i.get('how')}" for i in story)[:900])
        for n in (["writer", "director", "designer"] if a.which == "all" else [a.which]):
            single = lint_owners(sbp).get(n) if a.which != "all" and n in OWNER else None   # 단독으로 부를 때도 지금 걸린 담당 검사를 넘긴다
            out.append(run_pass(n, sbp, a.force, single))
            print(f"[스킬 단계] {json.dumps(out[-1], ensure_ascii=False)}", flush=True)
        if a.which == "all":
            for rnd in range(2):                                   # 검사 되먹임: 걸린 규칙을 담당 단계로 돌려보낸다(최대 두 바퀴)
                by = lint_owners(sbp)
                if not by:
                    break
                for n in ("writer", "director", "designer"):
                    if by.get(n):
                        out.append(run_pass(n, sbp, True, by[n]))
                        print(f"[스킬 단계 · 되먹임 {rnd + 1}] {json.dumps(out[-1], ensure_ascii=False)}", flush=True)
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        fail("skill_pass", stage="skill_pass", error=str(e)[:400])
    ok("skill_pass", passes=json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
