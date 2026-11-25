#!/usr/bin/env python3
"""Fluma MCP 서버(stdio) — 에이전트(Claude Code · Codex · Antigravity · Cursor …)가 Fluma 를 도구로 쓴다.

  python3 engine/mcp_server.py
  MCP 클라이언트 설정: {"command": "<repo>/.venv/bin/python", "args": ["<repo>/engine/mcp_server.py"]}

설계(볼트 02 Architecture/MCP 전환 설계 — Fluma 를 도구 서버로): 판단은 에이전트, 계산 · 측정 · 관문은 서버.
  · 몇 분 걸리는 일은 *_start → 작업 id → job_wait / job_status (작업은 서버가 꺼져도 계속 돈다)
  · 무거운 작업은 동시에 1개(FLUMA_HEAVY_SLOTS), 메모리가 모자라면 비기를 기다린다
  · 같은 프로젝트의 같은 작업이 돌고 있으면 새로 띄우지 않고 그 작업에 붙는다
외부 SDK 없이 JSON-RPC 2.0(MCP 2025-06-18: initialize · tools/list · tools/call · ping)만 구현한다.
레퍼런스의 영상 · 대사는 분석 재료일 뿐 결과물에 옮기지 않는다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
sys.path.insert(0, str(ROOT / "engine" / "mcp"))
import fluma_jobs as jobs  # noqa: E402
import fluma_project as project  # noqa: E402
import fluma_tools as tools  # noqa: E402
import fluma_stage as stage  # noqa: E402
import fluma_flow as flow  # noqa: E402

PY = sys.executable
# job_wait 한 번에 기다릴 최대 초 — 런타임의 도구 시간 제한보다 짧아야 한다. 기본 55(어느 런타임이든 안전),
# 스튜디오는 시간 제한을 늘려 띄우고 --wait-max 290 을 준다(2026-11-25: 렌더 대기에 55초 호출 12번 — 호출마다 대화 25만 토큰을 다시 읽음)
WAIT_MAX = 55
if "--wait-max" in sys.argv:
    try:
        WAIT_MAX = max(10, min(900, int(sys.argv[sys.argv.index("--wait-max") + 1])))
    except (IndexError, ValueError):
        pass
VERSION = "2.1.0"
XR = ROOT / "data" / "public" / "trends" / "xray"
CH = ROOT / "data" / "public" / "trends" / "channels"
VID = re.compile(r"(?:shorts/|v=|youtu\.be/)?([A-Za-z0-9_-]{11})")

INSTRUCTIONS = """Fluma makes vertical short videos (YouTube Shorts) from real material. You (the agent) make the judgement calls; Fluma computes, measures and enforces the quality gate.
Workflow: project_status(project) tells you the state and `next` (what to do and which tool). Long work (produce, reference analysis) starts a job: call the *_start tool, then job_wait(job_id) repeatedly until status is done/error/needs_input — do not poll with shell sleeps. A job keeps running even if this server restarts.
Making a video — default flow, four calls. Judge the structure first (hook type, a job per scene — show with examples, situations and demos, never a slideshow of definitions): plan_submit (structure + script + assets) → design_submit (direction + every scene in the design language) → design_patch only for scenes that need it → finish (review → final render → quality gate). Do not read engine code or example files; the tools return the rules and errors field by field. Look only at the small preview images.
Step tools (for scene-by-scene work with a person; judgement is yours, Fluma never calls another LLM): storyboard_get → write/fix with storyboard_patch (use the writer · director · designer prompts) → lint until pass → prep_start (music, voice, audio → scene lengths) → scene_build_start / scene_still to look while you work → review_frames, look at every still, review_submit(problems) → render_start(mode="final") → quality_gate. Fix only changed scenes; render the whole video once at the end.
Rules: a video with remaining quality-gate blocks is not finished and must not be uploaded. Never waive a block on your own — waive needs the user's own words. Reply to the user in Korean."""


def _ro(desc: str, props: dict, req: list[str] | None = None) -> dict:
    return {"description": desc, "inputSchema": {"type": "object", "properties": props, "required": req or [], "additionalProperties": False},
            "annotations": {"readOnlyHint": True}}


def _rw(desc: str, props: dict, req: list[str] | None = None, destructive: bool = False) -> dict:
    return {"description": desc, "inputSchema": {"type": "object", "properties": props, "required": req or [], "additionalProperties": False},
            "annotations": {"readOnlyHint": False, "destructiveHint": destructive}}


PID = {"type": "string", "description": "프로젝트 id (예: 2026-11-24-suaozaw-01)"}
JID = {"type": "string", "description": "작업 id (…_start 가 돌려준 job.id)"}

TOOLS: dict[str, dict] = {
    # ---------- 프로젝트 ----------
    "project_list": _ro("List recent Fluma projects (id, title, whether a storyboard and a finished video exist).",
                        {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}),
    "project_status": _ro("State of one project: plan check, storyboard, audio, materials built, latest video, quality gate (blocks/advice), running jobs, and `next` = what to do now and which tool to call. Call this first.",
                          {"project": PID}, ["project"]),
    # ---------- 제작 ----------
    "produce_start": _rw("One-shot production from the storyboard (voice → checks → materials → render → quality gate) as a job; follow with job_wait. With judge=agent it needs your review_submit first. Prefer the step tools (prep_start, review_frames, render_start) when iterating. Same project already producing → returns that job (joined=true).",
                         {"project": PID,
                          "scenes": {"type": "string", "description": "일부 장면만 (예: '3' 또는 '2-4'). 없으면 전체"},
                          "keep_going": {"type": "boolean", "default": False, "description": "검사(lint) 실패가 있어도 렌더까지(확인용)"},
                          "preview_only": {"type": "boolean", "default": False, "description": "초안 화질로(납품 렌더 없이)"},
                          "judge": {"type": "string", "enum": ["agent", "engine"], "default": "agent",
                                    "description": "agent(기본): 판단은 당신이, 엔진은 LLM 을 부르지 않음 · engine: 예전처럼 엔진이 Claude 를 불러 스킬 단계를 돎(느림)"}},
                         ["project"]),
    # ---------- 굵은 도구(기본 흐름 — 판단 지점 넷, 순서는 서버가) ----------
    "plan_submit": _rw("Step 1 of the default flow. Decide the structure BEFORE writing lines: concept{angle, structure}, hook{options: 3 × {type, line} with different openings, pick, why}, "
                       "and a job per scene. " + flow.DIRECTION_CARD + " Then submit the script (title, format, audience, concept, hook, scenes[{role, job, narration, caption, screen}], research.facts with sources) "
                       "and optionally the assets to make (web captures, terminal recordings, icons, forms). The server checks it at once, reviews it in the background, "
                       "and starts voice + asset jobs right away. Returns the confirmed script and the scene design language card. Then design without waiting.",
                       {"project": PID, "script": {"type": "object", "description": "{title, format, audience, concept: {angle, structure}, hook: {options: [{type, line}×3], pick, why}, scenes: [{role, job, narration, caption, screen}], research: {facts: [{claim, value, source}]}, concepts_order?, cta?}"},
                        "assets": {"type": "array", "items": {"type": "object"}, "description": flow.ASSET_FORMAT}},
                       ["project", "script"]),
    "assets_start": _rw("Start (or redo) the asset job alone — web captures, terminal recordings, icons, forms. " + flow.ASSET_FORMAT,
                        {"project": PID, "assets": {"type": "array", "items": {"type": "object"}}}, ["project", "assets"]),
    "design_submit": _rw("Step 2. Submit the video direction (concept{angle, breaks, structure, cliches}, intent{summary, must, must_not}, art{palette{bg, ink, accent}, rule, avoid}, cta, hashtags, fonts?) "
                         "and every scene's design in script order: scenes[{design, beat, shot_fn, screen, visual_kind}]. Invalid fields come back one by one before anything is written. "
                         "The server waits for voice/assets, compiles designs to scene code, checks, builds and returns review stills.",
                         {"project": PID, "video": {"type": "object"}, "scenes": {"type": "array", "items": {"type": "object"}}}, ["project", "video", "scenes"]),
    "design_patch": _rw("Step 3 (only if needed). Change some scenes: {\"3\": {design, …}} and/or video fields. Rebuilds and returns stills for those scenes only.",
                        {"project": PID, "scenes": {"type": "object"}, "video": {"type": "object"}}, ["project"]),
    "finish": _rw("Step 4. Submit your review of the stills (problems=[] if none) → final render → quality gate, in one call. Blocks come back to fix with design_patch.",
                  {"project": PID, "problems": {"type": "array", "items": {"type": "object"}}, "looked": {"type": "array", "items": {"type": "integer"}},
                   "notes": {"type": "string"}}, ["project"]),
    "assets_status": _ro("Results of the asset job started by plan_submit (src to use in designs, small preview image paths, errors).", {"project": PID}, ["project"]),
    # ---------- 콘티 · 검사 ----------
    "storyboard_get": _ro("Read a project's storyboard. view=edit (script, scenes, captions, materials), design (+ layout, subtitle, font, material adjust), full (raw JSON).",
                          {"project": PID, "view": {"type": "string", "enum": ["edit", "design", "full"], "default": "edit"}}, ["project"]),
    "storyboard_patch": _rw("Change storyboard fields. Top-level keys merge (null deletes). Scenes by number: {\"scenes\": {\"3\": {\"caption\": \"…\"}}}. Saved only if the schema check passes; only your changes are applied on top of the current file.",
                            {"project": PID, "patch": {"type": "object"}}, ["project", "patch"]),
    "lint": _ro("Run the storyboard checks. fail (L rules) blocks production; advise (T/V/D/R) is guidance.", {"project": PID}, ["project"]),
    # ---------- 음성 · 빌드 · 정지 화면 · 렌더 ----------
    "prep_start": _rw("Job: script → background music → voice → narration audio. Scene lengths are set from the real audio here. Run after the script is final.",
                      {"project": PID}, ["project"]),
    "scene_build_start": _rw("Job: build the scene project (materials + motion) without rendering video. Catches scene-code errors early. Unchanged inputs are reused.",
                             {"project": PID, "scenes": {"type": "string", "description": "'3' 또는 '2-4' — 없으면 전체"}}, ["project"]),
    "scene_still": _ro("Still frames straight from the scene project (no video render, ~1s). Give scenes (two stills each: middle, end) or exact seconds. Returns paths and images.",
                       {"project": PID, "scenes": {"type": "array", "items": {"type": "integer", "minimum": 1}, "maxItems": 8},
                        "seconds": {"type": "array", "items": {"type": "number", "minimum": 0}, "maxItems": 12},
                        "images": {"type": "boolean", "default": True}}, ["project"]),
    "render_start": _rw("Job: render video. mode=preview → quick draft (optionally some scenes). mode=final → the whole video at delivery quality; the server first requires lint pass and a fresh review_submit, then applies the quality gate.",
                        {"project": PID, "mode": {"type": "string", "enum": ["preview", "final"], "default": "preview"},
                         "scenes": {"type": "string", "description": "preview 만: '3' 또는 '2-4'"}}, ["project"]),
    # ---------- 화면 검토 · 측정 · 관문 ----------
    "review_frames": _ro("Before the final render: rebuild, return stills of every scene (or the given scenes), code-level screen checks (visual_tell) and the previous review's problems. Look at every image, then call review_submit.",
                         {"project": PID, "scenes": {"type": "array", "items": {"type": "integer", "minimum": 1}, "maxItems": 8},
                          "images": {"type": "boolean", "default": True}}, ["project"]),
    "review_submit": _rw("Record your screen review of the current build. problems: [{scene, kind, what, fix}] — kind 겹침 / 잘림 / 안전 영역 blocks the final render; others advise. Empty list = nothing wrong. Tied to the current build: if scenes change, review again.",
                         {"project": PID,
                          "problems": {"type": "array", "items": {"type": "object", "properties": {
                              "scene": {"type": ["integer", "null"]}, "kind": {"type": "string"}, "what": {"type": "string"}, "fix": {"type": "string"}},
                              "required": ["what"]}},
                          "looked": {"type": "array", "items": {"type": "integer"}}, "notes": {"type": "string"}}, ["project", "problems"]),
    "measure": _ro("Measure the latest full video (empty frames, text size, contrast …) without re-rendering.", {"project": PID}, ["project"]),
    "quality_gate": _ro("Quality-gate verdict of the latest final render: finished (no blocks), blocks, waived, advice. A video with blocks is not finished.", {"project": PID}, ["project"]),
    "waive": _rw("Exempt one block ONLY when the user explicitly said to keep it. user_said must be the user's own words, quoted exactly. Never on your own.",
                 {"project": PID, "code": {"type": "string"}, "scene": {"type": ["integer", "null"]}, "why": {"type": "string"},
                  "user_said": {"type": "string"}}, ["project", "code", "why", "user_said"]),
    # ---------- 작업 ----------
    "job_wait": _ro("Wait up to `timeout` seconds for a job to finish and return its state (status, stage, progress 0..1, result or error). If still running, call again — do not start the work again.",
                    {"job_id": JID, "timeout": {"type": "integer", "minimum": 1, "maximum": WAIT_MAX, "default": WAIT_MAX if WAIT_MAX > 55 else 45}}, ["job_id"]),
    "job_status": _ro("Current state of a job without waiting; optionally the last log lines.",
                      {"job_id": JID, "log_lines": {"type": "integer", "minimum": 0, "maximum": 200, "default": 0}}, ["job_id"]),
    "job_list": _ro("Recent jobs, optionally only one project's or only active ones.",
                    {"project": PID, "active_only": {"type": "boolean", "default": False}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}}),
    "job_cancel": _rw("Cancel a running or waiting job (stops its processes). Only when the user asks or the job is clearly stuck.",
                      {"job_id": JID}, ["job_id"], destructive=True),
    # ---------- 레퍼런스 ----------
    "analyze_reference_start": _rw("Analyze a reference YouTube Short and several other Shorts from its channel (cuts, camera, colour, speech, rhythm, tone). Starts a job (minutes); when done, result.card is the channel card path — read it with channel_card.",
                                   {"url": {"type": "string", "description": "YouTube Shorts URL 또는 11자 id"},
                                    "videos": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}}, ["url"]),
    "channel_card": _ro("Return a previously built channel card (Markdown).", {"channel_id": {"type": "string"}}, ["channel_id"]),
    "style_card": _ro("Return a previously built single-video style card (Markdown).", {"video_id": {"type": "string"}}, ["video_id"]),
    "voice_profile": _ro("Measure a voice recording: median pitch, intonation range, phrase-ending drop, loudness variation. JSON.",
                         {"audio_path": {"type": "string"}}, ["audio_path"]),
}


def _card(md: Path, cut: str | None = None) -> str:
    if not md.exists():
        raise ValueError(f"카드가 없습니다: {md.relative_to(ROOT)}")
    t = md.read_text(encoding="utf-8")
    return t.split(cut)[0] if cut and cut in t else t


def _job_out(job: dict, log_lines: int = 0) -> dict:
    out = jobs.brief(job)
    if log_lines:
        out["log_tail"] = jobs.log_tail(job["id"], log_lines)
    if job.get("status") in ("queued", "waiting", "running"):
        out["hint"] = "아직 도는 중 — job_wait 를 다시 부른다(새로 시작하지 않는다)"
    elif job.get("status") == "needs_input":
        out["hint"] = "사용자만 줄 수 있는 것이 필요 — result 의 needs · how 를 사용자에게 한 번에 묻는다"
    elif job.get("status") == "error" and not log_lines:
        out["hint"] = "error 의 짧은 이유를 보고 고친 뒤 한 번 다시. 자세히는 job_status(log_lines=40)"
    return out


def call(name: str, a: dict):
    if a.get("project") and any(name in s for s in stage.BLOCKS.values()):
        stage.check(project.check_id(a["project"]), name)       # 자동 진행: 단계를 마친 대화는 다음 단계를 새 대화로(fluma_stage)
    if name == "project_list":
        return project.list_projects(int(a.get("limit") or 20))
    if name == "project_status":
        return project.status(a.get("project", ""))
    if name == "produce_start":
        pid = project.check_id(a.get("project", ""))
        sb = ROOT / "data" / "storyboards" / f"{pid}.json"
        if not sb.exists():
            raise ValueError(f"콘티가 없습니다: {sb.relative_to(ROOT)} — 먼저 콘티를 쓴다")
        cmd = [PY, str(ROOT / "engine" / "produce.py"), str(sb.relative_to(ROOT))]
        if a.get("judge", "agent") == "agent":
            cmd += ["--judge", "agent"]
        sc = str(a.get("scenes") or "").strip()
        if sc:
            if not re.fullmatch(r"\d+(-\d+)?", sc):
                raise ValueError("scenes 는 '3' 또는 '2-4' 형식")
            cmd += ["--scenes", sc]
        if a.get("keep_going"):
            cmd.append("--keep-going")
        if a.get("preview_only"):
            cmd.append("--preview-only")
        job = jobs.submit("produce", cmd, project=pid, label=f"제작 {pid}" + (f" 장면 {sc}" if sc else ""),
                          key=f"produce:{pid}", heavy=True, mem_gb=3.0, timeout=3600)
        return _job_out(job)
    if name in ("plan_submit", "design_submit", "design_patch", "finish", "assets_status", "assets_start"):
        pid = project.check_id(a.get("project", ""))
        budget = float(max(30, WAIT_MAX - 10))
        if name == "plan_submit":
            return flow.plan_submit(pid, a.get("script") or {}, a.get("assets"))
        if name == "design_submit":
            return flow.design_submit(pid, a.get("video") or {}, a.get("scenes") or [], budget)
        if name == "design_patch":
            return flow.design_patch(pid, a.get("scenes"), a.get("video"), budget)
        if name == "finish":
            return flow.finish(pid, a.get("problems"), a.get("looked"), a.get("notes") or "", budget)
        if name == "assets_start":
            return _job_out(flow.assets_start(pid, a.get("assets") or []))
        return flow.assets_status(pid)
    if name == "storyboard_get":
        return tools.storyboard_get(a.get("project", ""), a.get("view") or "edit")
    if name == "storyboard_patch":
        return tools.storyboard_patch(a.get("project", ""), a.get("patch") or {})
    if name == "lint":
        return tools.lint(a.get("project", ""))
    if name == "prep_start":
        return _job_out(tools.prep_start(a.get("project", "")))
    if name == "scene_build_start":
        return _job_out(tools.scene_build_start(a.get("project", ""), a.get("scenes")))
    if name == "render_start":
        return _job_out(tools.render_start(a.get("project", ""), a.get("mode") or "preview", a.get("scenes")))
    if name == "scene_still":
        return tools.scene_still(a.get("project", ""), a.get("scenes"), a.get("seconds"), a.get("images", True))
    if name == "review_frames":
        return tools.review_frames(a.get("project", ""), a.get("scenes"), a.get("images", True))
    if name == "review_submit":
        return tools.review_submit(a.get("project", ""), a.get("problems") or [], a.get("looked"), a.get("notes") or "")
    if name == "measure":
        return tools.measure(a.get("project", ""))
    if name == "quality_gate":
        return tools.quality_gate(a.get("project", ""))
    if name == "waive":
        return tools.waive(a.get("project", ""), a.get("code", ""), a.get("why", ""), a.get("user_said", ""), a.get("scene"))
    if name == "job_wait":
        return _job_out(jobs.wait(a.get("job_id", ""), float(min(WAIT_MAX, max(1, int(a.get("timeout") or (WAIT_MAX if WAIT_MAX > 55 else 45)))))))
    if name == "job_status":
        return _job_out(jobs.get(a.get("job_id", "")), int(a.get("log_lines") or 0))
    if name == "job_list":
        pid = a.get("project")
        return [jobs.brief(j) for j in jobs.list_jobs(project=project.check_id(pid) if pid else None,
                                                     active_only=bool(a.get("active_only")), limit=int(a.get("limit") or 10))]
    if name == "job_cancel":
        return _job_out(jobs.cancel(a.get("job_id", "")))
    if name == "analyze_reference_start":
        m = VID.search(str(a.get("url", "")))
        if not m:
            raise ValueError("YouTube Shorts URL 또는 11자 id 가 필요합니다")
        vid, n = m.group(1), max(1, min(10, int(a.get("videos") or 5)))
        job = jobs.submit("reference", [PY, str(ROOT / "engine" / "mcp" / "fluma_ref.py"), vid, "--n", str(n)],
                          label=f"레퍼런스 분석 {vid}", key=f"reference:{vid}", heavy=True, mem_gb=1.5, timeout=3600)
        return _job_out(job)
    if name == "channel_card":
        cid = str(a.get("channel_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", cid):
            raise ValueError("channel_id 형식이 올바르지 않습니다")
        return _card(CH / cid / "channel.md")
    if name == "style_card":
        m = VID.search(str(a.get("video_id", "")))
        if not m:
            raise ValueError("video_id 가 필요합니다")
        return _card(XR / m.group(1) / "style" / "style.md")
    if name == "voice_profile":
        p = Path(str(a.get("audio_path", ""))).expanduser()
        if not p.is_file():
            raise ValueError("소리 파일이 없습니다")
        r = subprocess.run([PY, "engine/voice/voice_profile.py", str(p)], cwd=ROOT, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-300:])
        return r.stdout.strip()
    raise ValueError(f"모르는 도구: {name}")


SKILLS = ROOT / ".claude" / "skills"
MCP_NOTE = ("\n\n---\n이 지침을 Fluma MCP 도구로 실행한다: 콘티는 storyboard_get · storyboard_patch, 검사는 lint, 음성은 prep_start, "
            "화면 확인은 scene_still · review_frames → review_submit, 완성은 render_start(mode=final) → quality_gate. "
            "오래 걸리는 도구는 job_wait 로 기다린다. 본문의 `python3 engine/...` 명령은 같은 일을 하는 도구가 있으면 도구를 쓴다.")


def _skills() -> dict[str, dict]:
    out = {}
    for f in sorted(SKILLS.glob("*/SKILL.md")) if SKILLS.exists() else []:
        t = f.read_text("utf-8")
        m = re.match(r"^---\n([\s\S]*?)\n---\n", t)
        meta = {}
        for ln in (m.group(1).splitlines() if m else []):
            if ":" in ln:
                k, v = ln.split(":", 1)
                meta[k.strip()] = v.strip()
        out[meta.get("name") or f.parent.name] = {"description": meta.get("description", ""), "body": t[m.end():] if m else t}
    return out


def prompts_list() -> list[dict]:
    return [{"name": n, "description": d["description"][:300],
             "arguments": [{"name": "project", "description": "프로젝트 id(있으면)", "required": False},
                           {"name": "request", "description": "사용자가 한 말(있으면)", "required": False}]}
            for n, d in _skills().items()]


def prompts_get(name: str, args: dict) -> dict:
    sk = _skills().get(name)
    if not sk:
        raise ValueError(f"없는 prompt: {name}")
    head = ""
    if args.get("project"):
        head += f"프로젝트: {args['project']} (먼저 project_status)\n"
    if args.get("request"):
        head += f"사용자 요청: {args['request']}\n"
    return {"description": sk["description"][:300],
            "messages": [{"role": "user", "content": {"type": "text", "text": (head + "\n" if head else "") + sk["body"].strip() + MCP_NOTE}}]}


_OUT = threading.Lock()


def reply(id_, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id_}
    msg.update({"error": error} if error else {"result": result})
    with _OUT:                                       # job_wait 는 따로 도는 줄기에서 답한다 — 줄이 섞이지 않게
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n"); sys.stdout.flush()


def tool_result(value, is_error: bool = False) -> dict:
    if isinstance(value, tuple):                     # (값, [그림 콘텐츠]) — 정지 화면 도구
        value, imgs = value
        out = tool_result(value, is_error)
        out["content"] += imgs
        return out
    if isinstance(value, str):
        return {"content": [{"type": "text", "text": value}], "isError": is_error}
    text = json.dumps(value, ensure_ascii=False, indent=1)
    out = {"content": [{"type": "text", "text": text}], "isError": is_error}
    if isinstance(value, dict):
        out["structuredContent"] = value
    return out


def handle(req: dict):
    mid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
    if mid is None:          # 알림(notifications/initialized · cancelled 등)은 답하지 않는다
        return
    if method == "initialize":
        reply(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                    "serverInfo": {"name": "fluma", "version": VERSION}, "instructions": INSTRUCTIONS})
    elif method == "tools/list":
        reply(mid, {"tools": [{"name": k, **v} for k, v in TOOLS.items()]})
    elif method == "tools/call" and params.get("name") == "job_wait":
        # 오래 기다리는 동안 다른 도구 호출(나란히 부른 것)이 막히지 않게 따로 돈다 — 작업 상태는 파일이라 읽기만 한다
        threading.Thread(target=_tool_call, args=(mid, "job_wait", params.get("arguments") or {}), daemon=True).start()
    elif method == "tools/call":
        _tool_call(mid, params.get("name", ""), params.get("arguments") or {})
    elif method == "prompts/list":
        reply(mid, {"prompts": prompts_list()})
    elif method == "prompts/get":
        try:
            reply(mid, prompts_get(params.get("name", ""), params.get("arguments") or {}))
        except ValueError as e:
            reply(mid, error={"code": -32602, "message": str(e)})
    elif method == "ping":
        reply(mid, {})
    else:
        reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


def _tool_call(mid, name: str, args: dict):
    try:
        reply(mid, tool_result(call(name, args)))
    except (ValueError, RuntimeError) as e:          # 도구 오류는 MCP 결과로 돌려준다(에이전트가 읽고 고침)
        reply(mid, tool_result(str(e), True))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(traceback.format_exc())
        reply(mid, tool_result(f"{type(e).__name__}: {e}", True))


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            reply(None, error={"code": -32700, "message": "parse error"}); continue
        handle(req)


if __name__ == "__main__":
    main()
