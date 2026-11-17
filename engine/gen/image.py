#!/usr/bin/env python3
"""이미지 생성 — Google Flow Imagen/Nano Banana(gflow) 및 Antigravity CLI(agy) 이원화 지원.
2 · 3단계(캐릭터 시트 · 키 프레임)가 쓴다.

규칙:
  - 무한 재시도 금지: 호출 한 번 = 생성 한 번. 실패하면 멈추고 보고.
  - 시간 상한: 기본 600초.
  - 백엔드 지원:
      - gflow: gflow image t2i / i2i (Google Flow Imagen, nano-pro · nano2 · nano2-lite · image4)
      - agy: Antigravity CLI image-generator 하위 에이전트 (flash · pro · flash_lite)
      - mock: 로컬 PIL 테스트 이미지 생성 (개발/테스트용)

  python3 engine/gen/image.py <출력.png> --prompt "…" [--ref 경로::역할 …] [--aspect 9:16] [--backend gflow|agy|mock] [--model nano-pro|flash]
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

ASPECTS = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "3:4": 3 / 4, "4:3": 4 / 3, "2:3": 2 / 3}
ALLOW = '{"permissions":{"allow":["invoke_subagent(*)","write_file(*)","read_file(*)","edit_file(*)"]}}'
SETTINGS_PATH = ROOT / "data" / "workspace" / "settings.json"
_GFLOW_THREAD_LOCK = threading.Lock()
_GFLOW_LOCK_PATH = Path("/tmp/fluma_gflow_image.lock")
_AGENT_ONLY_IMAGE = False
_AGENT_WORKER: subprocess.Popen | None = None


@contextmanager
def _gflow_profile_lock():
    """동일 gflow Chrome 프로필 동시 접근(ProfileLockedError)을 막기 위한 스레드·프로세스 락."""
    with _GFLOW_THREAD_LOCK:
        if fcntl is None or os.name == "nt":
            yield
            return
        with _GFLOW_LOCK_PATH.open("a+") as lf:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


class ImageGenError(RuntimeError):
    pass


def _find_gflow() -> Path:
    local = ROOT / "tools" / "gflow" / (".venv/Scripts/gflow.exe" if os.name == "nt" else ".venv/bin/gflow")
    if local.exists():
        return local
    w = shutil.which("gflow")
    return Path(w) if w else local


def _find_agent_python() -> Path:
    local = ROOT / "tools" / "gflow" / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    if local.exists():
        return local
    return Path(sys.executable)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def default_flow_project() -> str | None:
    """설정 imagegen/videogen.flow_project → 없으면 gflow 기본 프로필의 최근 프로젝트 UUID."""
    s = load_settings()
    for section in ("imagegen", "videogen"):
        proj = (s.get(section) or {}).get("flow_project")
        if proj:
            return str(proj)
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


def _is_agent_only_error(msg: str) -> bool:
    low = msg.lower()
    return any(tok in low for tok in ("agent-only", "flow-host-migrated", "#799", "not ported"))


def _close_agent_worker() -> None:
    global _AGENT_WORKER
    p = _AGENT_WORKER
    if p is None:
        return
    _AGENT_WORKER = None
    try:
        if p.stdin:
            p.stdin.close()
        p.wait(timeout=5)
    except Exception:
        p.terminate()
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()


atexit.register(_close_agent_worker)


def parse_reply(text: str) -> dict:
    """agy 답 안의 마지막 {"path": …} JSON 파싱"""
    dec = json.JSONDecoder()
    found = {}
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "path" in obj:
            found = obj
    return found


def _generate_mock(out: Path, aspect: str, prompt: str, model: str) -> dict:
    from PIL import Image, ImageDraw
    ratio = ASPECTS.get(aspect, 9 / 16)
    W = 1080 if ratio <= 1.0 else 1920
    H = int(W / ratio)
    img = Image.new("RGB", (W, H), color=(28, 28, 38))
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, W - 40, H - 40], outline=(99, 102, 241), width=4)
    draw.text((60, 60), f"[MOCK IMAGE]\nModel: {model}\nAspect: {aspect}\nPrompt: {prompt[:80]}...", fill=(240, 240, 255))
    img.save(out)
    return {
        "path": str(out),
        "size": [W, H],
        "aspect_asked": aspect,
        "took_sec": 0.1,
        "via": "mock",
        "backend": "mock",
        "model_asked": model,
        "model_reported": model,
        "prompt": prompt,
    }


_GFLOW_MODEL_ALIASES = {
    "nano-pro": "nano-pro",
    "pro": "nano-pro",
    "nano2": "nano2",
    "nano21": "nano2",
    "flash": "nano2",
    "nano2-lite": "nano2-lite",
    "flash_lite": "nano2-lite",
    "image4": "image4",
    "imagen4": "image4",
}


def _ensure_agent_worker() -> subprocess.Popen:
    global _AGENT_WORKER
    if _AGENT_WORKER is not None and _AGENT_WORKER.poll() is None:
        return _AGENT_WORKER
    py = _find_agent_python()
    if not py.exists():
        raise ImageGenError(f"gflow agent-only 파이썬을 찾을 수 없습니다: {py}")
    env = dict(os.environ)
    env.setdefault("GFLOW_CLI_BROWSER_WINDOW_POSITION", "-30000,-30000")
    cmd = [str(py), str(ROOT / "engine" / "gen" / "flow_agent_i2v.py"), "--server"]
    _AGENT_WORKER = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env, bufsize=1,
    )
    return _AGENT_WORKER


def _run_agent_i2i(out: Path, prompt: str, refs: list[tuple[Path, str]], aspect: str, model_alias: str, timeout: int) -> dict:
    """agent-only Flow UI(#799)에서 참조 이미지 기반 i2i 실행(상주 워커 재사용)."""
    p = _ensure_agent_worker()
    job = {
        "kind": "image",
        "project": default_flow_project(),
        "prompt": prompt,
        "aspect": aspect,
        "model": model_alias,
        "out": str(out),
        "refs": [{"path": str(rp), "role": r} for rp, r in refs],
        "timeout": max(60, int(timeout) - 30),
    }
    try:
        assert p.stdin is not None and p.stdout is not None
        p.stdin.write(json.dumps(job, ensure_ascii=False) + "\n")
        p.stdin.flush()
    except Exception as exc:
        _close_agent_worker()
        raise ImageGenError(f"flow agent-only 이미지 워커 전송 실패: {exc}") from exc

    end = time.time() + timeout
    lines: list[str] = []
    body: dict | None = None
    while time.time() < end:
        if os.name != "nt":
            rdy, _, _ = select.select([p.stdout], [], [], max(0.1, end - time.time()))
            if not rdy:
                break
        line = p.stdout.readline()
        if not line:
            break
        s = line.strip()
        lines.append(s)
        if s.startswith("FLUMA_AGENT_I2V "):
            try:
                body = json.loads(s.split(" ", 1)[1])
                break
            except Exception:
                pass
    if not body:
        _close_agent_worker()
        raise ImageGenError(f"flow agent-only i2i 응답 없음/시간초과: {' | '.join(lines[-4:])[:350]}")
    if not body.get("ok"):
        if body.get("stage") in ("start", "attach"):
            _close_agent_worker()
        raise ImageGenError(f"flow agent-only i2i 실패({body.get('stage')}): {str(body.get('error') or '')[:350]}")
    return body


def _find_gflow_output(tmp_out: Path, stdout: str, stderr: str) -> Path | None:
    for cand in (tmp_out, tmp_out.with_suffix(".jpg"), tmp_out.with_suffix(".jpeg"), tmp_out.with_suffix(".webp")):
        if cand.exists():
            return cand
    for part in (stdout + "\n" + stderr).split():
        clean = part.strip().strip("|").strip()
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            if clean.endswith(ext) and os.path.exists(clean):
                return Path(clean)
    return None


def _generate_gflow(out: Path, prompt: str, refs: list[tuple[Path, str]], aspect: str, model: str, timeout: int) -> dict:
    global _AGENT_ONLY_IMAGE
    gflow_bin = _find_gflow()
    if not gflow_bin.exists():
        raise ImageGenError(f"gflow 바이너리를 찾을 수 없습니다: {gflow_bin}")

    model_alias = _GFLOW_MODEL_ALIASES.get(model, model)
    t0 = time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.parent / f"_gflow_{out.stem}_{int(time.time())}.png"

    target_file: Path | None = None
    agent_res: dict | None = None
    via = "gflow:image"

    with _gflow_profile_lock():
        if refs and _AGENT_ONLY_IMAGE:
            agent_res = _run_agent_i2i(tmp_out, prompt, refs, aspect, model_alias, timeout)
            target_file = Path(agent_res.get("path") or tmp_out)
            via = "gflow:agent-i2i"
        else:
            _close_agent_worker()
            if refs:
                cmd = [str(gflow_bin), "image", "i2i", prompt, "--model", model_alias, "--aspect", aspect, "-o", str(tmp_out)]
                for p, _ in refs:
                    cmd += ["--ref", str(p)]
            else:
                cmd = [str(gflow_bin), "image", "t2i", prompt, "--model", model_alias, "--aspect", aspect, "-o", str(tmp_out)]

            env = dict(os.environ)
            env.setdefault("GFLOW_CLI_BROWSER_WINDOW_POSITION", "-30000,-30000")
            if os.name != "nt" and not env.get("_FLUMA_IN_XVFB"):
                xvfb = shutil.which("xvfb-run")
                if xvfb:
                    env.pop("WAYLAND_DISPLAY", None)
                    env["XDG_SESSION_TYPE"] = "x11"
                    env["GDK_BACKEND"] = "x11"
                    env["QT_QPA_PLATFORM"] = "xcb"
                    env["_FLUMA_IN_XVFB"] = "1"
                    cmd = [xvfb, "-a", "-s", "-screen 0 1920x1080x24", *cmd]

            try:
                r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, cwd=str(out.parent))
            except subprocess.TimeoutExpired:
                raise ImageGenError(f"gflow 이미지 생성 시간 초과({timeout}초)")

            target_file = _find_gflow_output(tmp_out, r.stdout, r.stderr)
            if not target_file or not target_file.exists():
                err_msg = (r.stderr or r.stdout).strip()
                if refs and _is_agent_only_error(err_msg):
                    _AGENT_ONLY_IMAGE = True
                    agent_res = _run_agent_i2i(tmp_out, prompt, refs, aspect, model_alias, timeout)
                    target_file = Path(agent_res.get("path") or tmp_out)
                    via = "gflow:agent-i2i"
                elif "login" in err_msg.lower() or "auth" in err_msg.lower() or "read-only" in err_msg.lower():
                    raise ImageGenError(f"gflow 로그인 또는 인증 필요: {err_msg[:300]}")
                else:
                    raise ImageGenError(f"gflow 이미지 생성 실패 (출력 파일 없음): {err_msg[:400]}")

    took = round(time.time() - t0, 1)
    if not target_file or not target_file.exists():
        raise ImageGenError("gflow 이미지 생성 실패 (출력 파일 없음)")

    from PIL import Image
    im = Image.open(target_file)
    im.convert("RGB").save(out)
    if target_file != out and target_file.exists():
        target_file.unlink(missing_ok=True)

    im = Image.open(out)
    w, h = im.size
    meta = {
        "path": str(out),
        "size": [w, h],
        "aspect_asked": aspect,
        "took_sec": took,
        "via": via,
        "mode": "i2i" if refs else "t2i",
        "backend": "gflow",
        "model_asked": model,
        "model_reported": model_alias,
        "refs": [{"path": str(p), "role": r} for p, r in refs],
        "prompt": prompt,
    }
    if agent_res:
        meta["agent_only"] = True
        if agent_res.get("project_id"):
            meta["flow_project_id"] = agent_res["project_id"]
        if agent_res.get("media_id"):
            meta["flow_media_id"] = agent_res["media_id"]
    want = ASPECTS.get(aspect)
    if want and abs(w / h - want) > 0.03:
        meta["warn"] = f"비율이 다름: {w}×{h}({w / h:.3f}) — 요청 {aspect}({want:.3f})"
    return meta


def _generate_agy(out: Path, prompt: str, refs: list[tuple[Path, str]], aspect: str, model: str, timeout: int, _retry_quota: bool = True) -> dict:
    if not shutil.which("agy"):
        raise ImageGenError("agy(Antigravity CLI)가 없습니다")
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    ref_txt = ""
    if refs:
        ref_txt = ("Input reference images (attach them to the image generation in this order, as Image 1, Image 2, …):\n"
                   + "\n".join(f"- Image {i + 1}: {p} — {r}" for i, (p, r) in enumerate(refs)) + "\n")
    brief = (f"Use the image-generator subagent (model: {model}) to generate ONE image (image name: {out.stem}).\n"
             f"Aspect ratio: {aspect}. Generate it at that aspect ratio.\n{ref_txt}"
             f"Image prompt (use it verbatim):\n{prompt}\n\n"
             "Do not try to copy or move the generated artifact file yourself; just let image-generator save it in its default artifact directory. "
             "Do not run shell commands. When image-generator returns the saved file path, reply immediately with ONLY a JSON object: "
             '{"path": "<absolute path returned by image-generator>", "model": "<model actually used>", "aspect": "<aspect actually used>"}')
    t0 = time.time()
    try:
        agy_brain_root = Path.home() / ".gemini" / "antigravity-cli"
        extra = ["--add-dir", str(ROOT)]
        if agy_brain_root.exists():
            extra += ["--add-dir", str(agy_brain_root)]
        for d in dict.fromkeys(str(p.parent) for p, _ in refs if p.parent != out.parent):
            extra += ["--add-dir", d]
        r = subprocess.run(["agy", "-p", brief, "--dangerously-skip-permissions", "--settings", ALLOW, "--output-format", "json", "--print-timeout", f"{timeout}s", *extra],
                           capture_output=True, text=True, timeout=timeout + 30, cwd=str(out.parent))
    except subprocess.TimeoutExpired:
        raise ImageGenError(f"시간 초과({timeout}초) — 다시 시도하기 전에 사용자에게 보고")

    took = round(time.time() - t0, 1)
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        raise ImageGenError(f"agy 응답을 읽지 못함: {(r.stderr or r.stdout)[-400:]}")

    from PIL import Image
    reply = parse_reply(str(res.get("response") or ""))
    if not out.exists():
        brain = (Path.home() / ".gemini" / "antigravity-cli" / "brain" / str(res.get("conversation_id") or "-")).resolve()
        src = Path(str(reply.get("path") or "")).expanduser()
        try:
            src = src.resolve()
        except OSError:
            src = Path("-")
        if not src.is_file() and brain.is_dir():
            imgs = sorted(
                [p for p in brain.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if imgs:
                src = imgs[0]
        if not (src.is_file() and (brain in src.parents or ROOT in src.parents)):
            if res.get("denied_actions"):
                raise ImageGenError(f"agy 권한 거부: {res['denied_actions']}")
            resp_str = f"{res.get('response') or ''} {res.get('error') or ''}"
            if any(k in resp_str for k in ("429", "RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED")):
                if _retry_quota:
                    fallback_model = "pro" if model != "pro" else "flash_lite"
                    time.sleep(5)
                    return _generate_agy(out, prompt, refs, aspect, fallback_model, timeout, _retry_quota=False)
                raise ImageGenError("429 QUOTA_EXHAUSTED (이미지 생성 모델 일시 할당량 초과)")
            raise ImageGenError(f"그림이 저장되지 않음 — agy 답: {str(res.get('response'))[:300]}")
        Image.open(src).convert("RGB").save(out)

    w, h = Image.open(out).size
    meta = {
        "path": str(out),
        "size": [w, h],
        "aspect_asked": aspect,
        "took_sec": took,
        "via": "agy:image-generator",
        "mode": "i2i" if refs else "t2i",
        "backend": "agy",
        "model_asked": model,
        "model_reported": reply.get("model"),
        "agy_conversation": res.get("conversation_id"),
        "refs": [{"path": str(p), "role": r} for p, r in refs],
        "prompt": prompt,
        "agy": res.get("response"),
        "usage": res.get("usage"),
    }
    want = ASPECTS.get(aspect)
    if want and abs(w / h - want) > 0.03:
        meta["warn"] = f"비율이 다름: {w}×{h}({w / h:.3f}) — 요청 {aspect}({want:.3f})"
    return meta


def generate(out: Path, prompt: str, refs: list[tuple[Path, str]] | None = None, aspect: str = "9:16",
             model: str | None = None, backend: str | None = None, timeout: int = 600) -> dict:
    """이미지 한 장 생성. 백엔드(agy/gflow/mock)와 모델을 선택하여 실행한다."""
    cfg = load_settings().get("imagegen") or {}
    chosen_backend = backend or cfg.get("backend") or ("agy" if shutil.which("agy") else "gflow")
    chosen_model = model or cfg.get("model") or ("nano-pro" if chosen_backend == "gflow" else "flash")

    out = out.resolve()
    resolved_refs = [(Path(p).resolve(), r) for p, r in refs or []]
    for p, _ in resolved_refs:
        if not p.exists() or p.stat().st_size == 0:
            raise ImageGenError(f"참조 그림 없음 또는 빈 파일: {p}")

    if chosen_backend == "mock":
        return _generate_mock(out, aspect, prompt, chosen_model)
    elif chosen_backend == "gflow":
        try:
            return _generate_gflow(out, prompt, resolved_refs, aspect, chosen_model, timeout)
        except ImageGenError as gflow_err:
            if shutil.which("agy"):
                try:
                    return _generate_agy(out, prompt, resolved_refs, aspect, "flash", timeout)
                except ImageGenError as agy_err:
                    raise ImageGenError(f"gflow 실패({gflow_err}) → agy 폴백 실패({agy_err})") from agy_err
            raise
    else:
        return _generate_agy(out, prompt, resolved_refs, aspect, chosen_model, timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--ref", action="append", default=[], help="경로::역할")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--backend", choices=["gflow", "agy", "mock"], default=None, help="gflow | agy | mock")
    ap.add_argument("--model", default=None, help="gflow: nano-pro, nano2, nano2-lite, image4 / agy: flash, pro, flash_lite")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    refs = [(Path(x.split("::", 1)[0]), x.split("::", 1)[1] if "::" in x else "reference") for x in a.ref]
    try:
        res = generate(Path(a.out), a.prompt, refs, a.aspect, a.model, a.backend, a.timeout)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    except ImageGenError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
