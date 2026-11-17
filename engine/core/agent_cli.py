#!/usr/bin/env python3
"""설정된 에이전트 런타임(claude · cursor · codex · antigravity) 통합 실행 도우미.

`data/workspace/settings.json` 의 `agent.cli` 및 `FLUMA_AGENT_RUNTIME` 환경변수를 따라
`claude -p` · `agent -p`(Cursor) · `codex exec` · `agy -p` 중 현재 활성화된 CLI 로 텍스트/JSON 응답을 받는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
SETTINGS = ROOT / "data" / "workspace" / "settings.json"


def runtime(override_env: str = "") -> tuple[str, str]:
    """→ (런타임: claude|cursor|codex|antigravity, 모델 — 없으면 '')"""
    rt = (os.environ.get(override_env) if override_env else "") or os.environ.get("FLUMA_AGENT_RUNTIME") or ""
    a: dict = {}
    try:
        a = json.loads(SETTINGS.read_text("utf-8")).get("agent") or {}
    except (OSError, json.JSONDecodeError):
        pass
    rt = rt or a.get("cli") or "claude"
    model_key = {"claude": "claudeModel", "cursor": "cursorModel", "codex": "codexModel", "antigravity": "agyModel"}.get(rt, "")
    model = os.environ.get("FLUMA_AGENT_MODEL") or (a.get(model_key) if model_key else "") or ""
    return rt, model


def clean_env(rt: str) -> dict[str, str]:
    """구독 로그인 대신 API 키로 과금되지 않게 관련 환경변수를 제거한다."""
    e = dict(os.environ)
    if rt == "claude":
        keep = {"CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "ANTHROPIC_CONFIG_DIR"}
        for k in list(e):
            if k not in keep and (
                k.startswith("ANTHROPIC_")
                or k.startswith("CLAUDE_CODE_USE_")
                or k in ("AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR")
            ):
                e.pop(k, None)
    elif rt == "codex":
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"):
            e.pop(k, None)
    e.pop("FLUMA_AGENT_RUNTIME", None)
    return e


def extract_json(text: str) -> dict:
    """마크다운 코드 블록 등을 벗기고 가장 바깥 `{...}` JSON 객체를 파싱한다."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", t)
    if m:
        t = m.group(1).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise RuntimeError(f"JSON 없음: {t[:300]}")
    return json.loads(t[a:b + 1])


def _run_claude(
    system: str,
    prompt: str,
    model: str,
    timeout: int,
    tools: str,
    dirs: list[str] | None,
    allowed: list[str] | None,
    cwd: str,
) -> tuple[str, float]:
    bin_path = os.environ.get("SF_CLAUDE_BIN") or shutil.which("claude") or "claude"
    cmd = [
        bin_path, "-p", "--output-format", "json",
        "--system-prompt", system,
        "--tools", tools,
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--setting-sources", "",
    ]
    if model:
        cmd += ["--model", model]
    for d in dirs or []:
        cmd += ["--add-dir", d]
    if tools:
        cmd += ["--allowedTools", *(allowed or [tools])]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=clean_env("claude"))
    if r.returncode:
        raise RuntimeError(f"claude 실패: {(r.stderr or r.stdout)[-400:]}")
    out = json.loads(r.stdout)
    return out.get("result") or "", float(out.get("total_cost_usd") or 0)


def _run_codex(
    system: str,
    prompt: str,
    model: str,
    timeout: int,
    tools: str,
    dirs: list[str] | None,
    cwd: str,
) -> tuple[str, float]:
    bin_path = os.environ.get("SF_CODEX_BIN") or shutil.which("codex") or "codex"
    sandbox = "workspace-write" if "Bash" in tools else "read-only"
    full_prompt = f"<SYSTEM>\n{system}\n</SYSTEM>\n\n{prompt}" if system else prompt
    cmd = [bin_path, "exec", "--json", "--skip-git-repo-check", "-s", sandbox]
    for d in dirs or []:
        cmd += ["--add-dir", d]
    if model:
        cmd += ["--model", model]
    cmd.append(full_prompt)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=clean_env("codex"), stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError(f"codex 실패: {(r.stderr or r.stdout)[-400:]}")
    text = ""
    for line in r.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "item.completed" and (ev.get("item") or {}).get("type") == "agent_message":
            text = ev["item"].get("text") or text
    if not text.strip():
        raise RuntimeError(f"codex 응답 비어 있음: {(r.stderr or r.stdout)[-400:]}")
    return text, 0.0


def _run_cursor(
    system: str,
    prompt: str,
    model: str,
    timeout: int,
    cwd: str,
) -> tuple[str, float]:
    bin_path = os.environ.get("SF_CURSOR_AGENT_BIN") or shutil.which("agent") or "agent"
    full = f"<FLUMA_SYSTEM>\n{system}\n</FLUMA_SYSTEM>\n\n{prompt}" if system else prompt
    cmd = [bin_path, "-p", "-f", "--trust", "--output-format", "stream-json", "--workspace", cwd]
    m = model or ""
    eff = os.environ.get("FLUMA_AGENT_EFFORT") or ""
    if eff and not re.search(r"\[", m):
        e = "high" if eff == "max" else eff
        cmd += ["--model", f"{m or 'auto'}[effort={e}]"]
    elif m:
        cmd += ["--model", m]
    cmd.append(full)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30, cwd=cwd, env=dict(os.environ), stdin=subprocess.DEVNULL)
    text = ""
    ok = False
    for line in reversed(r.stdout.splitlines()):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "result":
            text = str(obj.get("result") or text)
            ok = obj.get("subtype") == "success" and not obj.get("is_error")
            if text:
                break
        if obj.get("type") == "assistant" and not text:
            parts = obj.get("message", {}).get("content") or []
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if r.returncode and not text.strip():
        raise RuntimeError(f"cursor agent 실패: {(r.stderr or r.stdout)[-400:]}")
    if not text.strip():
        raise RuntimeError(f"cursor agent 응답 비어 있음: {(r.stderr or r.stdout)[-400:]}")
    if not ok and r.returncode:
        raise RuntimeError(f"cursor agent 실패: {(r.stderr or r.stdout)[-400:]}")
    return text, 0.0


def _run_agy(
    system: str,
    prompt: str,
    model: str,
    timeout: int,
    tools: str,
    dirs: list[str] | None,
    cwd: str,
    allow_web: bool,
) -> tuple[str, float]:
    bin_path = os.environ.get("SF_AGY_BIN") or shutil.which("agy") or "agy"
    full_prompt = f"<SYSTEM>\n{system}\n</SYSTEM>\n\n{prompt}" if system else prompt
    allow: list[str] = []
    if "Read" in tools:
        allow.append("read_file(*)")
    if "Bash" in tools:
        allow.append("run_command(*)")
    if allow_web:
        allow.append("search_web(*)")
    cmd = [
        bin_path, "-p", full_prompt,
        "--output-format", "json",
        "--disable-slash-commands",
        "--print-timeout", f"{timeout}s",
        "--settings", json.dumps({"permissions": {"allow": allow}}),
    ]
    if "Bash" in tools:
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd.append("--sandbox")
    for d in dict.fromkeys(dirs or ([str(ROOT)] if allow else [])):
        cmd += ["--add-dir", d]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30, cwd=cwd, env=clean_env("antigravity"), stdin=subprocess.DEVNULL)
    text = ""
    for line in reversed(r.stdout.splitlines()):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "response" in obj:
            text = str(obj.get("response") or "")
            break
    if r.returncode and not text.strip():
        raise RuntimeError(f"agy 실패: {(r.stderr or r.stdout)[-400:]}")
    if not text.strip():
        raise RuntimeError(f"agy 응답 비어 있음: {(r.stderr or r.stdout)[-400:]}")
    return text, 0.0


def run_agent(
    system: str,
    prompt: str,
    *,
    override_env: str = "",
    timeout: int = 900,
    tools: str = "",
    dirs: list[str] | None = None,
    allowed: list[str] | None = None,
    cwd: str | None = None,
    allow_web: bool = False,
) -> tuple[str, float]:
    """현재 설정된 에이전트 CLI 로 프롬프트를 실행하고 `(텍스트, 비용 USD)` 를 돌려준다."""
    rt, model = runtime(override_env)
    work_cwd = cwd or str(ROOT)
    if rt == "antigravity":
        return _run_agy(system, prompt, model, timeout, tools, dirs, work_cwd, allow_web)
    if rt == "cursor":
        return _run_cursor(system, prompt, model, timeout, work_cwd)
    if rt == "codex":
        return _run_codex(system, prompt, model, timeout, tools, dirs, work_cwd)
    if rt == "claude":
        return _run_claude(system, prompt, model, timeout, tools, dirs, allowed, work_cwd)
    raise RuntimeError(f"모르는 에이전트 런타임: {rt}")
