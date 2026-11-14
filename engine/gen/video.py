#!/usr/bin/env python3
"""파이프라인 4단계 — 영상 생성(이원화). 하나의 VideoGenerator 인터페이스 뒤에 경로 B(gflow-cli MCP · Google Flow/Veo, 기본)와
경로 A(Antigravity CLI · Gemini 챗, Flow 크레딧 부족 시)를 둔다. 입력 · 출력은 두 경로가 같다(스펙 4단계).
  입력: 샷 프롬프트(1단계 칸에서 조립) · 시작 프레임(승인 ② 키 프레임) · [끝 프레임]
        — 캐릭터 시트는 넘기지 않는다: Veo · Flow 는 시작 프레임과 참조를 한 요청에 같이 받지 못해, 캐릭터는 키 프레임 안에 그려져 있다(사용자 결정 2026-11-11)
  출력: 샷 클립 파일 + 메타(경로 · 모델 · 시도 횟수)

경로 선택(스펙 4단계 · 확정): 영상 단위. 생성 전에 크레딧 잔액(gflow_get_credits, 크레딧 안 씀)을 보고
  필요 크레딧(샷 수 × 고른 모델의 샷당 비용) 이상이면 영상 전체를 B, 부족하면 영상 전체를 A(사용자에게 알림).
  B 진행 중 크레딧이 떨어지면 멈추고 묻는다(남은 샷을 A 로 넘기지 않음). 잠금 · 고장 등 다른 실패는 멈추고 보고(자동 전환 없음).
  모델은 사용자가 설정에서 고른다(data/workspace/settings.json videogen.model) — 안 골랐으면 생성을 시작하지 않는다.
재생성: 샷당 최대 3회(videogen.max_attempts, 두 경로 합산) — 재생성도 경로 선택(크레딧 확인)부터 다시.
무한 루프 금지: 모든 호출에 시간 상한, 실패하면 멈추고 보고. 시도 기록(attempt)은 제출 **전에** 디스크에 쓴다 —
  제출 뒤 결과를 모르면 'indeterminate' 로 두고 다시 제출하지 않는다(크레딧이 이미 빠졌을 수 있음 — 사용자 확인 뒤 회수).

  python3 engine/gen/video.py plan <plan id>                      # 경로 · 필요 크레딧 · 잔액(생성 안 함)
  python3 engine/gen/video.py run <plan id> [--shots 1,2] [--backend flow|antigravity|mock]
  python3 engine/gen/video.py status <plan id>                    # 샷별 시도 · 상태
  python3 engine/gen/video.py approve <plan id> --shots 1,2       # 샷 검토 통과
설정(data/workspace/settings.json 의 videogen): {"model": "veo_3_1_lite", "credits": {"veo_3_1_lite": 10, …}, "max_attempts": 3, "timeout_sec": 900}
"""
from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, needs_input, ok  # noqa: E402
import keyframe as kfmod  # noqa: E402
import plan as planmod  # noqa: E402

SETTINGS = ROOT / "data" / "workspace" / "settings.json"


def _find_gflow() -> Path:
    local = ROOT / "tools" / "gflow" / (".venv/Scripts/gflow.exe" if os.name == "nt" else ".venv/bin/gflow")
    if local.exists():
        return local
    if os.name == "nt":
        local_cmd = ROOT / "tools" / "gflow" / ".venv/Scripts/gflow"
        if local_cmd.exists():
            return local_cmd
    import shutil
    w = shutil.which("gflow")
    return Path(w) if w else local


GFLOW = _find_gflow()
# Flow 도움말 16526234(2026-11-11 확인) 기준 기본값 — 사용자가 설정에서 바꾼다. 초당 값은 길이를 곱한다
DEFAULT_CREDITS = {"veo_3_1_lite": 10, "veo_3_1_lite_lower_priority": 10, "veo_3_1_fast": 20, "veo_3_1_quality": 100,
                   "omni_1_2_flash": {"per_sec": 3}, "omni_flash": {"per_sec": 3}}


def default_flow_project() -> str | None:
    """설정 videogen.flow_project → 없으면 gflow 가 기록한 기본 프로필의 가장 최근 프로젝트"""
    v = (json.loads(SETTINGS.read_text("utf-8")).get("videogen") or {}) if SETTINGS.exists() else {}
    if v.get("flow_project"):
        return str(v["flow_project"])
    import sqlite3
    import tomllib
    home = Path(os.environ.get("GFLOW_CLI_HOME") or Path.home() / ".local" / "share" / "gflow-cli")
    db, cfg = home / "gflow.db", home / "config.toml"
    if not db.exists():
        return None
    prof = (tomllib.loads(cfg.read_text("utf-8")).get("default_profile") if cfg.exists() else None) or "default"
    with sqlite3.connect(db) as c:
        row = c.execute("select flow_project_id from projects where profile_name=? order by created_at desc limit 1", (prof,)).fetchone()
    return row[0] if row else None


# ── 공통 인터페이스 ──
@dataclass
class GenRequest:
    shot: int
    prompt: str
    start_frame: Path | None
    end_frame: Path | None
    sec: int
    aspect: str
    model: str
    out: Path
    refs: list = field(default_factory=list)      # 레퍼런스(r2v: 그림 · 영상 파일 경로 또는 Flow 프로젝트 미디어 UUID) — 모션그래픽 샷
    project: str | None = None                    # 같은 콘티의 샷 · 수정 테이크가 공유하는 Flow 프로젝트 UUID


@dataclass
class GenResult:
    ok: bool
    path: Path | None = None
    model: str | None = None
    backend: str = ""
    error: str | None = None
    kind: str | None = None          # credits · locked · broken · timeout · indeterminate · unsupported
    raw: dict = field(default_factory=dict)


class VideoGenerator(Protocol):
    name: str
    def available(self) -> tuple[bool, str]: ...
    def credits(self) -> int | None: ...
    def generate(self, req: GenRequest, timeout: int) -> GenResult: ...


# ── 경로 B: gflow-cli MCP(stdio) ──
def _bg_browser_cmd(cmd: list[str], env: dict | None = None) -> tuple[list[str], dict]:
    """생성 시 브라우저 창이 사용자 화면(Wayland/X11)에 뜨지 않도록 가상 디스플레이(xvfb-run)와 화면 밖 좌표를 건다.
    reCAPTCHA Enterprise 는 headless=True 를 403 으로 막으므로, 가상 모니터 위에서 headed 로 돌린다."""
    e = dict(os.environ if env is None else env)
    e.setdefault("GFLOW_CLI_BROWSER_WINDOW_POSITION", "-30000,-30000")
    if os.name != "nt" and not e.get("_FLUMA_IN_XVFB"):
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            e.pop("WAYLAND_DISPLAY", None)
            e["XDG_SESSION_TYPE"] = "x11"
            e["GDK_BACKEND"] = "x11"
            e["QT_QPA_PLATFORM"] = "xcb"
            e["_FLUMA_IN_XVFB"] = "1"
            cmd = [xvfb, "-a", "-s", "-screen 0 1920x1080x24", *cmd]
    return cmd, e


class FlowMCP:
    """gflow mcp run 을 stdio 로 띄워 JSON-RPC 로 부른다. 출력 경로는 서버의 GFLOW_CLI_OUTPUT_DIR 안이어야 한다(gflow 규칙)"""
    name = "flow"

    def __init__(self, out_dir: Path, no_spend: bool = False):
        self.out_dir = out_dir
        self.no_spend = no_spend
        self.p = None
        self.i = 0

    def _login(self) -> tuple[bool, str]:
        """gflow 브라우저 로그인을 실행한다 (전용 Chrome 세션 열림)"""
        if not GFLOW.exists():
            return False, f"gflow-cli 없음({GFLOW})"
        print("[gflow] Google 계정 로그인 브라우저를 엽니다...", file=sys.stderr)
        try:
            r = subprocess.run([str(GFLOW), "auth", "login", "--browser", "auto"], capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                return True, "gflow 로그인 성공"
            return False, f"gflow 로그인 실패: {r.stderr or r.stdout}"
        except Exception as e:
            return False, f"gflow 자동 로그인 실행 실패: {e}"

    def available(self, auto_login: bool = True) -> tuple[bool, str]:
        if not GFLOW.exists():
            return False, f"gflow-cli 없음({GFLOW})"
        try:
            cmd, env = _bg_browser_cmd([str(GFLOW), "auth", "status"])
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            if "No profiles" in out or r.returncode != 0:
                if auto_login:
                    ok_log, msg_log = self._login()
                    if ok_log:
                        return True, ""
                    return False, f"gflow 자동 로그인 필요: {msg_log}"
                return False, f"gflow 로그인 안 됨 — `{GFLOW} auth login --browser chrome`"
            return True, ""
        except Exception as e:
            if auto_login:
                ok_log, msg_log = self._login()
                if ok_log:
                    return True, ""
            return False, f"gflow 상태 확인 실패: {e}"

    def _start(self):
        if self.p:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "GFLOW_CLI_OUTPUT_DIR": str(self.out_dir)}
        args = [str(GFLOW), "mcp", "run"] + (["--no-spend"] if self.no_spend else [])
        args, env = _bg_browser_cmd(args, env)
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env, bufsize=1)
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "fluma", "version": "1"}}, 120)
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); self.p.stdin.flush()

    def _rpc(self, method: str, params: dict, timeout: int) -> dict:
        self.i += 1
        rid = self.i
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n"); self.p.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:                    # 응답 하나를 시간 상한 안에서만 기다린다(폴링 아님)
            r, _, _ = select.select([self.p.stdout], [], [], max(0.1, end - time.time()))
            if not r:
                break
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("gflow mcp 가 끝남")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"])[:400])
                return msg.get("result") or {}
        raise TimeoutError(f"{method} {timeout}초 안에 응답 없음")

    def _tool(self, name: str, args: dict, timeout: int) -> dict:
        self._start()
        res = self._rpc("tools/call", {"name": name, "arguments": args}, timeout)
        txt = "".join(c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text")
        try:
            body = json.loads(txt) if txt.strip().startswith("{") else {"text": txt}
        except json.JSONDecodeError:
            body = {"text": txt}
        body["_is_error"] = bool(res.get("isError"))
        return body

    def credits(self) -> int | None:
        b = self._tool("gflow_get_credits", {}, 180)
        for k in ("credits", "balance", "total_credits"):
            if isinstance(b.get(k), (int, float)):
                return int(b[k])
        return None

    agent_only = False   # 이 계정이 Flow 의 agent-only 화면(#799)이면 i2v 는 flow_agent_i2v.py 로(gflow 0.98 은 거절, #1220)

    def _agent_i2v(self, req: GenRequest, timeout: int) -> GenResult:
        """agent-only 계정의 i2v — 채팅 칸에 시작 프레임을 붙이고 에이전트에게 시킨다(engine/gen/flow_agent_i2v.py, gflow 부품 재사용).
        MCP 가 프로필을 잡고 있으면 브라우저를 못 여니 먼저 닫는다. Veo 3.1 Lite 첫 프레임 i2v 는 8초만 된다(측정)."""
        self.close()
        project = req.project or default_flow_project()
        if not project:
            return GenResult(False, backend=self.name, error="Flow 프로젝트가 없다 — `gflow project list` 로 하나 만들거나 설정 videogen.flow_project", kind="broken")
        sec = 8 if req.model.startswith("veo_3_1_lite") else req.sec
        py = GFLOW.parent / ("python.exe" if os.name == "nt" else "python")
        cmd = [str(py), str(ROOT / "engine" / "gen" / "flow_agent_i2v.py"), "--project", project, "--image", str(req.start_frame),
               "--prompt", req.prompt, "--out", str(req.out), "--sec", str(sec), "--model", req.model, "--timeout", str(timeout)]
        cmd, env = _bg_browser_cmd(cmd)
        main_sites = [str(p) for p in (ROOT / ".venv").glob("lib/python*/site-packages")]
        if main_sites:
            curr_py = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (main_sites[0] + (os.pathsep + curr_py if curr_py else ""))
        try:
            r = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True, timeout=timeout + 300)
        except subprocess.TimeoutExpired:
            return GenResult(False, backend=self.name, error="agent-only i2v 시간 초과", kind="indeterminate", raw={"flow_project_id": project})
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("FLUMA_AGENT_I2V ")), None)
        b = json.loads(line.split(" ", 1)[1]) if line else {"ok": False, "stage": "start", "error": (r.stderr or r.stdout)[-400:]}
        raw = {"flow_project_id": project, "flow_media_id": b.get("media_id"), "agent_only": True, "first_frame_diff": b.get("first_frame_diff")}
        if b.get("ok") and req.out.exists():
            return GenResult(True, req.out, req.model, self.name, raw=raw)
        # 제출 전(attach · start) 실패는 청구 없음 → broken, 제출 뒤 실패는 청구됐을 수 있음 → indeterminate(자동 재제출 금지)
        kind = "indeterminate" if b.get("stage") == "generate" else "broken"
        if "credit" in str(b.get("error", "")).lower():
            kind = "credits"
        return GenResult(False, backend=self.name, error=f"agent-only i2v({b.get('stage')}): {b.get('error')}", kind=kind, raw=raw)

    def generate(self, req: GenRequest, timeout: int) -> GenResult:
        if req.start_frame and not req.end_frame and self.agent_only:
            return self._agent_i2v(req, timeout)
        args = {"prompt": req.prompt, "aspect": req.aspect, "model": req.model, "duration": req.sec, "count": 1, "output": req.out.name, "wait": True}
        if req.project:
            args["project"] = req.project
        if req.start_frame:                     # 시작 프레임이 있으면 i2v(Flow 는 시작 프레임과 레퍼런스를 함께 받지 않는다)
            args.update(mode="i2v", initial_frame=str(req.start_frame))
            if req.end_frame:
                args["end_frame"] = str(req.end_frame)
        elif req.refs:                          # 모션그래픽: 레퍼런스 그림 · 영상 · 프로젝트 미디어 UUID(재료 · Ingredients)
            args.update(mode="r2v", reference_images=[str(r) for r in req.refs])
        else:
            args["mode"] = "t2v"
        try:
            b = self._tool("gflow_generate_video", args, timeout)
        except TimeoutError as e:
            return GenResult(False, backend=self.name, error=str(e), kind="indeterminate")
        is_err = b.get("_is_error") or b.get("status") == "failed" or "error" in b
        if is_err:
            txt = json.dumps(b, ensure_ascii=False)
            if req.start_frame and not req.end_frame and "agent-only" in txt.lower():   # 제출 전 거절(exit 36, 청구 없음)
                FlowMCP.agent_only = True                                             # 이 실행의 나머지 샷도 바로 그 경로로
                return self._agent_i2v(req, timeout)
            err_obj = b.get("error") if isinstance(b.get("error"), dict) else {}
            err_title = err_obj.get("title") or err_obj.get("detail") or txt[:200]
            kind = "credits" if "credit" in txt.lower() else ("locked" if any(w in txt.lower() for w in ("253", "locked", "unusual activity", "come back tomorrow")) else "broken")
            return GenResult(False, backend=self.name, error=f"{err_title}: {txt[:400]}", kind=kind, raw=b)
        out = self.out_dir / req.out.name
        if not out.exists():
            cand = []                               # gflow 가 상대 경로(파일 이름만)로 돌려줘도 출력 폴더 안에서 찾는다
            for x in json.dumps(b).split('"'):
                if x.endswith(".mp4"):
                    q = Path(x)
                    if q.is_absolute() and q.is_file():
                        cand.append(q)
                    elif (self.out_dir / q.name).is_file():
                        cand.append(self.out_dir / q.name)
            out = cand[0] if cand else out
        if not out.exists():
            return GenResult(False, backend=self.name, error="성공 응답인데 파일 없음 — Flow 프로젝트에서 회수(gflow_download_media)", kind="indeterminate", raw=b)
        if out != req.out:
            shutil.move(str(out), req.out)
        return GenResult(True, req.out, req.model, self.name, raw=b)

    def close(self):
        """gflow mcp 를 끝낸다 — terminate 뒤 wait 로 거둬 좀비(<defunct>)를 남기지 않는다, 안 끝나면 kill"""
        if not self.p:
            return
        try:
            self.p.terminate()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.p.kill()
            try:
                self.p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        finally:
            self.p = None


# ── 경로 A: Antigravity CLI · Gemini 챗 ──
class Antigravity:
    """경로 A — Antigravity CLI(agy)로 Gemini 챗에서 영상 생성(스펙: Flow 크레딧 부족 시). 오케스트레이터 Antigravity 와는 별개 호출.
    2026-11-12 확인: 이 agy 빌드의 하위 에이전트 목록에는 영상 생성이 없었다(사용자: '된다고 가정하고 진행'). 그래서 요청은 하되,
    영상 파일이 돌아오지 않으면 비공식 우회 없이 'unsupported' 로 멈추고 보고한다(스펙 4장)"""
    name = "antigravity"
    ALLOW = '{"permissions":{"allow":["invoke_subagent(*)","write_file(*)","read_file(*)","edit_file(*)"]}}'

    def available(self) -> tuple[bool, str]:
        return (True, "") if shutil.which("agy") else (False, "agy(Antigravity CLI)가 없다")

    def credits(self) -> int | None:
        return None

    def generate(self, req: GenRequest, timeout: int) -> GenResult:
        req.out.parent.mkdir(parents=True, exist_ok=True)
        brief = (f"Using Gemini video generation (Veo / Omni) available to you, generate exactly ONE video and save it as {req.out}.\n"
                 + (f"Start frame (first frame of the video, image-to-video): {req.start_frame}\n" if req.start_frame else "")
                 + (f"End frame: {req.end_frame}\n" if req.end_frame else "")
                 + ("Style reference images (match their style closely; do not copy their content): " + ", ".join(map(str, req.refs)) + "\n" if req.refs else "") +
                 f"Duration: {req.sec} seconds. Aspect ratio: {req.aspect}.\nVideo prompt (use verbatim):\n{req.prompt}\n\n"
                 "Do not run shell commands. If you cannot generate video, do not substitute anything — reply that video generation is unavailable. "
                 'Reply with only a JSON object: {"path": "<absolute path or null>", "model": "<model used>", "note": "<anything that went wrong>"}')
        dirs = []
        for p in (req.start_frame, req.end_frame, *req.refs):
            if not p:
                continue
            pp = Path(p) if not isinstance(p, Path) else p
            if pp.exists():
                dirs.append(str(pp.parent))
        add_dirs = [x for d in dict.fromkeys(dirs) for x in ("--add-dir", d)]
        try:
            r = subprocess.run(["agy", "-p", brief, "--dangerously-skip-permissions", "--settings", self.ALLOW, "--output-format", "json", "--print-timeout", f"{timeout}s", *add_dirs],
                               capture_output=True, text=True, timeout=timeout + 30, cwd=str(req.out.parent))
        except subprocess.TimeoutExpired:
            return GenResult(False, backend=self.name, error=f"시간 초과({timeout}초)", kind="indeterminate")
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return GenResult(False, backend=self.name, error=(r.stderr or r.stdout)[-300:], kind="broken")
        from image import parse_reply
        reply = parse_reply(str(res.get("response") or ""))
        src = Path(str(reply.get("path") or "-")).expanduser()
        brain = (Path.home() / ".gemini" / "antigravity-cli" / "brain" / str(res.get("conversation_id") or "-")).resolve()
        if not req.out.exists() and src.is_file() and src.suffix.lower() in (".mp4", ".mov", ".webm") and brain in src.resolve().parents:
            shutil.copy(src, req.out)
        if not req.out.exists():
            return GenResult(False, backend=self.name, error=f"영상이 돌아오지 않음 — {str(res.get('response'))[:300]}", kind="unsupported", raw=res)
        return GenResult(True, req.out, reply.get("model") or "gemini", self.name, raw=res)


# ── 시험용: 크레딧 없이 전 과정(키 프레임을 길이만큼 늘린 영상) ──
class Mock:
    name = "mock"

    def __init__(self, balance: int = 10_000):
        self.balance = balance

    def available(self) -> tuple[bool, str]:
        return True, ""

    def credits(self) -> int | None:
        return self.balance

    def generate(self, req: GenRequest, timeout: int) -> GenResult:
        req.out.parent.mkdir(parents=True, exist_ok=True)
        src = req.start_frame or (req.refs[0] if req.refs else None)
        if src:
            sp = Path(src) if not isinstance(src, Path) else src
            if not sp.exists():
                src = None
            elif sp.suffix.lower() in (".mp4", ".mov", ".webm"):
                mid = sp.with_suffix(".mid.png")
                if not mid.exists():
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.5", "-i", str(sp), "-frames:v", "1", str(mid)], capture_output=True)
                src = mid if mid.exists() else None
        if not src:                                  # 그림이 하나도 없으면 단색
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x303040:s=720x1280:d={req.sec}", "-pix_fmt", "yuv420p", str(req.out)],
                               capture_output=True, text=True, timeout=timeout)
            return GenResult(r.returncode == 0, req.out if r.returncode == 0 else None, "mock", self.name, error=r.stderr[-300:] or None, kind=None if r.returncode == 0 else "broken")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(src), "-t", str(req.sec), "-vf",
                            "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,zoompan=z='1+0.0008*on':d=1:s=720x1280:fps=24",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(req.out)], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            return GenResult(False, backend=self.name, error=r.stderr[-300:], kind="broken")
        return GenResult(True, req.out, "mock", self.name)


# ── 설정 · 크레딧 계산 · 시도 기록 ──
def settings() -> dict:
    s = json.loads(SETTINGS.read_text("utf-8")) if SETTINGS.exists() else {}
    v = s.get("videogen") or {}
    return {"backend": v.get("backend") or "gflow", "model": v.get("model"), "credits": {**DEFAULT_CREDITS, **(v.get("credits") or {})}, "max_attempts": int(v.get("max_attempts") or 3),
            "timeout_sec": int(v.get("timeout_sec") or 900)}


def shot_cost(cfg: dict, model: str, sec: int) -> int | None:
    c = cfg["credits"].get(model)
    if isinstance(c, dict) and c.get("per_sec"):
        return int(c["per_sec"] * sec)
    return int(c) if isinstance(c, (int, float)) else None


def cdir(pid: str) -> Path:
    return ROOT / "data" / "compositions" / pid / "clips"


def style_refs(sb: dict, model: str, *, prefer_video: bool = True) -> list[Path]:
    """모션그래픽 샷에 붙일 레퍼런스(영상 클립 우선, 없으면 대표 프레임) — 모델 한도까지, 한 자리는 고치기용으로 남김"""
    sys.path.insert(0, str(ROOT / "engine" / "look"))
    import anchor
    refs = sb.get("style_ref") or []
    cap = max(0, planmod.ref_cap(model) - 1)
    if not refs or not cap:
        return []
    per = max(1, cap // len(refs))
    out: list[Path] = []
    picker = getattr(anchor, "_pick_clips", anchor._pick_frames) if prefer_video else anchor._pick_frames
    for rid in refs:
        out += picker(rid, per)
    return out[:cap]


def plan_project_id(pid: str) -> str | None:
    """같은 콘티(pid)의 앞선 시도에서 기록된 Flow 프로젝트 UUID 를 찾아 돌려준다"""
    d = cdir(pid)
    if not d.exists():
        return None
    for p in sorted(d.glob("s*/attempt_*.json"), reverse=True):
        try:
            a = json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if a.get("flow_project_id"):
            return str(a["flow_project_id"])
    return None


def last_take_frame(pid: str, n: int) -> Path | None:
    """말로 고칠 때 — 지난 테이크 가운데 프레임을 뽑아 돌려준다(하위 호환 · 폴백용)"""
    at = [a for a in attempts(pid, n) if a.get("state") == "done" and a.get("path") and Path(a["path"]).exists()]
    if not at:
        return None
    v = Path(at[-1]["path"]); f = v.with_suffix(".mid.png")
    if not f.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(max(0.1, float(at[-1].get("sec") or 4) / 2)), "-i", str(v), "-frames:v", "1", str(f)], capture_output=True)
    return f if f.exists() else None


def last_take_ref(pid: str, n: int, *, backend: str = "flow", project_id: str | None = None) -> str | Path | None:
    """말로 고칠 때 — Flow 경로면 같은 프로젝트의 지난 테이크 flow_media_id(@멘션) 또는 클립(.mp4)을, 그 외엔 클립/프레임을 돌려준다"""
    at = [a for a in attempts(pid, n) if a.get("state") == "done" and (a.get("flow_media_id") or (a.get("path") and Path(a["path"]).exists()))]
    if not at:
        return None
    last = at[-1]
    if backend == "flow" and last.get("flow_media_id"):
        if not project_id or not last.get("flow_project_id") or last.get("flow_project_id") == project_id:
            return str(last["flow_media_id"])
    if last.get("path") and Path(last["path"]).exists():
        if backend == "mock":
            return last_take_frame(pid, n)
        return Path(last["path"])
    return last_take_frame(pid, n)


def input_key(sb: dict, s: dict, kd: Path) -> str:
    """재생성 횟수는 같은 입력(프롬프트 + 시작 · 끝 프레임)끼리 센다 — 상한 뒤 사용자와 프롬프트 · 시작 프레임을 고치면 새로 센다(스펙 4단계)"""
    import hashlib
    h = hashlib.sha256(planmod.video_prompt(sb, s)["prompt"].encode())
    h.update(json.dumps(sb.get("style_ref") or []).encode() if s.get("kind") == "motion" else b"")
    for f in (kd / f"s{s['n']:02d}.png", kd / f"s{s['n']:02d}_end.png"):
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()[:16]


def used(pid: str, sb: dict, s: dict) -> int:
    key = input_key(sb, s, kfmod.kdir(pid))
    return sum(1 for a in attempts(pid, s["n"]) if a.get("input") == key)


def attempts(pid: str, n: int) -> list[dict]:
    d = cdir(pid) / f"s{n:02d}"
    return [json.loads(p.read_text("utf-8")) for p in sorted(d.glob("attempt_*.json"))] if d.exists() else []


def write_attempt(pid: str, n: int, rec: dict) -> Path:
    d = cdir(pid) / f"s{n:02d}"; d.mkdir(parents=True, exist_ok=True)
    p = d / f"attempt_{rec['n']}.json"
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    return p


def approved_shots(pid: str) -> set[int]:
    return {r["shot"] for r in kfmod.status(pid) if r["state"] == "승인"}


def make_backend(name: str, pid: str):
    norm = "flow" if name in ("flow", "gflow") else name
    return {"flow": lambda: FlowMCP(cdir(pid) / "_flow_out"), "antigravity": Antigravity, "mock": Mock}[norm]()


def route(pid: str, shots: list[dict], cfg: dict, prefer: str | None) -> dict:
    """영상 단위 경로 판단 — 생성하지 않는다"""
    target_backend = prefer or cfg.get("backend") or "gflow"
    if target_backend == "mock":
        return {"backend": "mock", "need": 0, "balance": None, "why": "시험(mock)"}
    if target_backend == "antigravity":
        a_ok, a_why = Antigravity().available()
        if not a_ok:
            return {"stop": f"경로 A(Antigravity) 사용 불가 — {a_why}"}
        return {"backend": "antigravity", "need": 0, "balance": None, "why": "설정된 영상 생성 경로: Antigravity CLI (Gemini)", "notice": True}

    if not cfg["model"]:
        return {"stop": "영상 생성 모델을 고르지 않았다 — 설정에서 videogen.model 을 고른다(`gflow models` 목록)"}
    costs = [shot_cost(cfg, cfg["model"], s["gen_sec"]) for s in shots]
    if any(c is None for c in costs):
        return {"stop": f"모델 {cfg['model']} 의 샷당 크레딧 비용이 설정에 없다 — videogen.credits 에 적는다"}
    need = sum(costs)
    flow = make_backend("flow", pid)
    okf, why = flow.available()
    if not okf:
        return {"stop": f"경로 B(Google Flow) 사용 불가 — {why}"}
    try:
        bal = flow.credits()
    except Exception as e:  # noqa: BLE001
        flow.close()
        return {"stop": f"크레딧 조회 실패(경로 B 고장으로 보고 — 자동 전환 없음): {e}"}
    flow.close()
    if bal is None:
        return {"stop": "크레딧 잔액을 읽지 못했다 — 보고"}
    if bal >= need:
        return {"backend": "flow", "need": need, "balance": bal, "why": f"잔액 {bal} ≥ 필요 {need}"}
    a_ok, a_why = Antigravity().available()   # 경로 A 는 요청해 봐야 안다 — 영상이 안 오면 그 샷에서 멈추고 보고
    if not a_ok:
        return {"stop": f"Flow 크레딧 부족(잔액 {bal} < 필요 {need}) — 경로 A 로 넘겨야 하는데 {a_why}", "need": need, "balance": bal}
    return {"backend": "antigravity", "need": need, "balance": bal, "why": f"잔액 {bal} < 필요 {need} — 경로 A(사용자에게 알림)", "notice": True}


def run(pid: str, sel: list[int] | None, prefer: str | None) -> dict:
    _, sb = planmod.load(pid)
    cfg = settings()
    ok_shots = approved_shots(pid) | {s["n"] for s in sb["shots"] if s.get("kind") == "motion"}   # 모션그래픽 샷은 키 프레임(승인 ②)이 없다
    shots = [s for s in sb["shots"] if (not sel or s["n"] in sel)]
    not_ok = [s["n"] for s in shots if s["n"] not in ok_shots]
    if not_ok:
        fail("video", stage="video", error=f"승인 ② 안 된 샷: {not_ok} — 영상 생성은 승인된 샷만(스펙 4장)")
    over = [s["n"] for s in shots if used(pid, sb, s) >= cfg["max_attempts"]]
    if over:
        fail("video", stage="video", error=f"재생성 상한({cfg['max_attempts']}회, 두 경로 합산) 도달: 샷 {over} — 더 만들지 않는다. 프롬프트(1단계 샷 칸)나 시작 프레임(3단계)을 사용자와 고치면 다시 생성할 수 있다")
    rt = route(pid, shots, cfg, prefer)
    if rt.get("stop"):
        fail("video", stage="route", error=rt["stop"])
    be = make_backend(rt["backend"], pid)
    model = cfg["model"] or "mock"
    kd = kfmod.kdir(pid)
    proj_id = plan_project_id(pid) if be.name == "flow" else None
    done, stopped = [], None
    try:
        for s in shots:
            n = s["n"]
            prev = attempts(pid, n)
            # indeterminate 로 기록되었으나 실제 파일(takeN.mp4)이 정상 다운로드되어 있는 경우 자동 복구
            for a in prev:
                if a.get("state") == "indeterminate":
                    expected = Path(a["path"]) if a.get("path") else (cdir(pid) / f"s{n:02d}" / f"take{a.get('n', 1)}.mp4")
                    if expected.exists() and expected.stat().st_size > 10_000:
                        a["state"] = "done"
                        a["kind"] = None
                        a["error"] = None
                        a["path"] = str(expected)
                        write_attempt(pid, n, a)
            # --shots 지정 없이 전체 실행할 때 이미 성공(done)한 클립이 있는 샷은 건너뛰어 크레딧 중복 소모 방지
            if not sel and any(a.get("state") == "done" and a.get("path") and Path(a["path"]).exists() for a in prev):
                done.append(n)
                continue
            if any(a.get("state") == "indeterminate" for a in prev):
                stopped = f"샷 {n}: 앞 시도 결과를 모름(indeterminate) — 다시 제출하지 않는다. Flow 프로젝트에서 회수 여부를 사용자와 확인"
                break
            vp = planmod.video_prompt(sb, s)
            prompt = vp["prompt"] + (f" Avoid: {vp['negative']}." if vp["negative"] else "")
            k = len(prev) + 1
            out = cdir(pid) / f"s{n:02d}" / f"take{k}.mp4"
            if s.get("kind") == "motion":
                refs: list = list(style_refs(sb, model, prefer_video=(be.name != "mock")))
                lt = last_take_ref(pid, n, backend=be.name, project_id=proj_id) if s.get("revisions") else None
                if lt and planmod.ref_cap(model) > len(refs):
                    refs.append(lt)
                    prompt += " The last reference is the previous attempt: keep everything in it except the revisions."
                req = GenRequest(n, prompt, None, None, s["gen_sec"], sb["aspect"], model, out, refs=refs, project=proj_id)
            else:
                start_p = kd / f"s{n:02d}.png"         # 무대(_stage) · 캔버스(_compose) 가이드는 시작 프레임이 아니다
                if not start_p.exists():
                    start_p = None
                refs = []
                if not start_p:
                    refs = list(style_refs(sb, model, prefer_video=False))
                    for cname in s.get("characters") or []:
                        cd = ROOT / "data" / "compositions" / pid / "characters" / cname
                        for view in ("front.png", "left.png", "right.png"):
                            vp = cd / view
                            if vp.exists() and vp not in refs:
                                refs.append(vp)
                req = GenRequest(n, prompt, start_p, (kd / f"s{n:02d}_end.png") if s.get("end_frame") else None, s["gen_sec"], sb["aspect"], model, out, refs=refs, project=proj_id)
            rec = {"n": k, "shot": n, "input": input_key(sb, s, kd), "backend": be.name, "model": model, "route": rt.get("why"), "prompt": prompt,
                   "start_frame": str(req.start_frame) if req.start_frame else None, "refs": [str(r) for r in req.refs], "shot_kind": s.get("kind", "live"),
                   "end_frame": str(req.end_frame) if req.end_frame else None, "sec": req.sec, "flow_project_id": proj_id, "state": "recorded", "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            write_attempt(pid, n, rec)                      # 제출 전에 기록
            rec["state"] = "submitted"; write_attempt(pid, n, rec)
            res = be.generate(req, cfg["timeout_sec"])
            raw_proj = (res.raw or {}).get("flow_project_id") or ((res.raw or {}).get("params") or {}).get("project")
            raw_media = (res.raw or {}).get("flow_media_id")
            if raw_proj and not proj_id:
                proj_id = str(raw_proj)
            rec.update({"state": "done" if res.ok else ("indeterminate" if res.kind in ("indeterminate", "timeout") else "failed"),
                        "error": res.error, "kind": res.kind, "path": str(res.path) if res.path else None,
                        "flow_project_id": str(raw_proj) if raw_proj else proj_id,
                        "flow_media_id": str(raw_media) if raw_media else None,
                        "raw": res.raw,
                        "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
            write_attempt(pid, n, rec)
            if res.ok:
                done.append(n); continue
            if res.kind == "credits":
                stopped = f"샷 {n}: 진행 중 Flow 크레딧 부족 — 남은 샷을 경로 A 로 넘기지 않고 멈춘다(화풍 일관성). 사용자에게 묻는다"
            else:
                stopped = f"샷 {n}: {res.kind} — {res.error} (자동 전환 · 재시도 없음, 보고)"
            break
    finally:
        if hasattr(be, "close"):
            be.close()
    return {"route": rt, "done": done, "stopped": stopped}


def status(pid: str) -> list[dict]:
    _, sb = planmod.load(pid)
    cfg = settings()
    rows = []
    rv = json.loads((cdir(pid) / "review.json").read_text("utf-8")) if (cdir(pid) / "review.json").exists() else {}
    for s in sb["shots"]:
        at = attempts(pid, s["n"])
        last = at[-1] if at else {}
        rows.append({"shot": s["n"], "attempts": len(at), "left": cfg["max_attempts"] - used(pid, sb, s), "state": last.get("state", "없음"),
                     "backend": last.get("backend"), "clip": last.get("path"),
                     "approved": bool(at) and (rv.get(str(s["n"])) or {}).get("take") == last.get("n")})   # 통과는 그 테이크에만
    return rows


def mock_shots(pid: str) -> list[int]:
    """통과(review.json)한 테이크가 mock(키 프레임을 늘린 가짜 클립)인 샷 — 조립은 경고, 최종 렌더 · 업로드는 막는다"""
    rv = json.loads((cdir(pid) / "review.json").read_text("utf-8")) if (cdir(pid) / "review.json").exists() else {}
    out = []
    for k, r in rv.items():
        a = next((x for x in attempts(pid, int(k)) if x.get("n") == r.get("take")), {})
        if a.get("backend") == "mock":
            out.append(int(k))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p1 = sp.add_parser("plan"); p1.add_argument("pid"); p1.add_argument("--shots")
    r = sp.add_parser("run"); r.add_argument("pid"); r.add_argument("--shots"); r.add_argument("--backend", choices=["flow", "antigravity", "mock"])
    st = sp.add_parser("status"); st.add_argument("pid")
    rv_ = sp.add_parser("revise", help="말로 고치기 — 그 샷 프롬프트 끝에 고칠 점을 붙인다(영어). 다음 run 에 반영"); rv_.add_argument("pid"); rv_.add_argument("--shots", required=True); rv_.add_argument("--say", required=True)
    av = sp.add_parser("approve"); av.add_argument("pid"); av.add_argument("--shots", required=True)
    sp.add_parser("login")
    sp.add_parser("check")
    a = ap.parse_args()
    if a.cmd == "login":
        ok_l, msg_l = FlowMCP(ROOT / "data" / "workspace" / "tmp")._login()
        if not ok_l:
            fail("video", stage="login", error=msg_l)
        ok("video", message=msg_l)
        return 0
    if a.cmd == "check":
        ok_c, msg_c = FlowMCP(ROOT / "data" / "workspace" / "tmp").available(auto_login=False)
        print(json.dumps({"available": ok_c, "msg": msg_c}, ensure_ascii=False))
        return 0
    sel = [int(x) for x in a.shots.split(",")] if getattr(a, "shots", None) else None
    if a.cmd == "plan":
        _, sb = planmod.load(a.pid)
        shots = [s for s in sb["shots"] if not sel or s["n"] in sel]
        rt = route(a.pid, shots, settings(), None)
        if rt.get("stop"):
            needs_input("video", needs=[rt["stop"]], how="설정 · 로그인 · 크레딧을 사용자와 확인")
        ok("video", backend=rt["backend"], need=str(rt["need"]), balance=str(rt["balance"]), why=rt["why"]); return 0
    if a.cmd == "run":
        res = run(a.pid, sel, a.backend)
        if res["stopped"]:
            fail("video", stage="generate", error=res["stopped"], done=",".join(map(str, res["done"])))
        ok("video", backend=res["route"]["backend"], done=",".join(map(str, res["done"])), why=str(res["route"].get("why")),
           notice="경로 A 로 생성 — 사용자에게 알린다" if res["route"].get("notice") else "",
           next="샷을 사용자에게 보여 주고 통과(approve) 또는 그 샷만 재생성(run --shots — 크레딧 확인부터 다시)")
        return 0
    if a.cmd == "revise":
        if planmod.HANGUL.search(a.say):
            fail("video", stage="revise", error="고칠 점은 영어로(생성 모델 입력) — 예: Make the text slam in harder")
        pp, sb = planmod.load(a.pid)
        for s in sb["shots"]:
            if s["n"] in sel:
                s.setdefault("revisions", []).append(a.say.strip())
        errs, _ = planmod.problems(sb)
        if errs:
            fail("video", stage="revise", error=" / ".join(errs[:3]))
        pp.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", "utf-8")
        ok("video", revised=a.shots, next="video.py run --shots " + a.shots + " — 프롬프트가 바뀌어 재생성 횟수는 새로 센다(사용자 요청 수정)"); return 0
    if a.cmd == "approve":
        p = cdir(a.pid) / "review.json"
        rv = json.loads(p.read_text("utf-8")) if p.exists() else {}
        for n in sel:
            at = attempts(a.pid, n)
            if not at or at[-1].get("state") != "done":
                fail("video", stage="video", error=f"샷 {n}: 통과시킬 클립이 없다")
            rv[str(n)] = {"take": at[-1]["n"], "path": at[-1]["path"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(rv, ensure_ascii=False, indent=1), "utf-8")
        ok("video", approved=a.shots); return 0
    print(json.dumps(status(a.pid), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
