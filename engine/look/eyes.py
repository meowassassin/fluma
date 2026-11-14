#!/usr/bin/env python3
"""눈 — 영상 · 그림을 '지금 설정된 에이전트'(Claude Code · Codex · Antigravity)에게 보여 주고 답을 받는다. 유료 보기 API(OpenRouter 등) 없이.

에이전트 CLI 는 영상 파일을 직접 보지 못하므로, 영상은 '시각이 적힌 프레임 모음 그림'(contact sheet) + 대사(단어 시각)로 바꿔 넘긴다.
그림은 런타임마다 다르게 건넨다:
  claude       claude -p … — 그림 파일 경로를 주고 Read 도구로 열어 보게 한다(그 밖의 도구는 막음)
  codex        codex exec -i 그림 … — 그림을 첫 메시지에 붙인다(읽기 전용 샌드박스)
  antigravity  agy -p … — read_file(*) 만 허용, 그림 폴더를 --add-dir
어느 런타임을 쓸지: FLUMA_LOOK_RUNTIME > FLUMA_AGENT_RUNTIME(에이전트가 부른 경우 같은 에이전트) > 설정(data/workspace/settings.json agent.cli) > claude
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

XRAY = ROOT / "data" / "public" / "trends" / "xray"
WORK = ROOT / "data" / "workspace" / "look"
SETTINGS = ROOT / "data" / "workspace" / "settings.json"
TIMEOUT = int(os.environ.get("FLUMA_LOOK_TIMEOUT", "420"))

SYSTEM = ("너는 숏폼 영상 편집자다. 그림은 영상에서 뽑은 프레임 모음이고, 칸마다 왼쪽 위에 그 프레임의 시각(초)이 적혀 있다. "
          "말(대사)은 단어 시각과 함께 텍스트로 준다. 본 것만 근거로, 시각을 붙여 구체적으로 답한다. 파일을 고치거나 다른 명령을 실행하지 않는다.")


# ---------------------------------------------------------------- 어느 에이전트로 볼까
def runtime() -> tuple[str, str]:
    """→ (런타임, 모델 — 없으면 '')"""
    rt = os.environ.get("FLUMA_LOOK_RUNTIME") or os.environ.get("FLUMA_AGENT_RUNTIME") or ""
    a = {}
    try:
        a = (json.loads(SETTINGS.read_text("utf-8")).get("agent") or {})
    except (OSError, json.JSONDecodeError):
        pass
    rt = rt or a.get("cli") or "claude"
    model = os.environ.get("FLUMA_LOOK_MODEL") or {"claude": a.get("claudeModel"), "codex": a.get("codexModel"), "antigravity": a.get("agyModel")}.get(rt) or ""
    return rt, model


def _env(rt: str) -> dict:
    """구독 로그인 대신 API 키로 몰래 청구되지 않게(studio/runtimes.mjs agentEnv 와 같은 규칙)"""
    e = dict(os.environ)
    if rt == "claude":
        keep = {"CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "ANTHROPIC_CONFIG_DIR"}
        for k in list(e):
            if k not in keep and (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_CODE_USE_") or k in ("AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR")):
                e.pop(k, None)
    if rt == "codex":
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"):
            e.pop(k, None)
    e.pop("FLUMA_AGENT_RUNTIME", None)
    return e


# ---------------------------------------------------------------- 영상 → 그림
def _dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _font(size: int):
    from PIL import ImageFont
    for f in (ROOT / "engine" / "assets" / "fonts" / "Pretendard-Bold.otf", Path("/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Bold.ttc")):
        if f.exists():
            try:
                return ImageFont.truetype(str(f), size)
            except OSError:
                pass
    return ImageFont.load_default()


def sheets(video: Path, out_dir: Path, t0: float = 0.0, t1: float | None = None, cols: int = 4, rows: int = 3, max_sheets: int = 3,
           width: int = 260) -> list[Path]:
    """영상 구간 → 프레임 모음 그림들(칸마다 시각 표시). 프레임 간격은 구간 길이에 맞춰 고르게(최대 cols*rows*max_sheets 칸)"""
    from PIL import Image, ImageDraw
    d = _dur(video)
    t1 = min(d, t1) if t1 else d
    if t1 <= t0:
        raise SystemExit(f"영상 구간이 비었습니다: {video}")
    n = min(cols * rows * max_sheets, max(cols * rows, int((t1 - t0) / 0.5)))
    times = [t0 + (t1 - t0) * (i + 0.5) / n for i in range(n)]
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(times):
            f = Path(td) / f"{i:03d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(f)],
                           capture_output=True)
            if f.exists():
                frames.append((t, Image.open(f).convert("RGB")))
    if not frames:
        raise SystemExit(f"프레임을 뽑지 못했습니다: {video}")
    fw, fh = frames[0][1].size
    font = _font(max(14, width // 12))
    out = []
    per = cols * rows
    for s in range(0, len(frames), per):
        chunk = frames[s:s + per]
        r = (len(chunk) + cols - 1) // cols
        im = Image.new("RGB", (cols * fw + (cols + 1) * 4, r * fh + (r + 1) * 4), (24, 24, 24))
        dr = ImageDraw.Draw(im)
        for k, (t, fr) in enumerate(chunk):
            x, y = 4 + (k % cols) * (fw + 4), 4 + (k // cols) * (fh + 4)
            im.paste(fr, (x, y))
            lab = f"{t:.1f}s"
            dr.rectangle([x, y, x + font.getlength(lab) + 10, y + font.size + 8], fill=(0, 0, 0))
            dr.text((x + 5, y + 3), lab, fill=(255, 230, 80), font=font)
        p = out_dir / f"sheet-{s // per + 1}.jpg"
        im.save(p, quality=85)
        out.append(p)
    return out


def _yt(x: str) -> str | None:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([\w-]{11})", x)
    if m:
        return m.group(1)
    return x if re.fullmatch(r"[\w-]{11}", x) else None


def speech_of(item: str) -> list[dict]:
    """대사(단어 · 문장 시각) — 분해해 둔 X-ray 가 있으면 그것, 없으면 로컬 faster-whisper"""
    vid = _yt(item)
    if vid and (XRAY / vid / "xray.json").exists():
        sp = json.loads((XRAY / vid / "xray.json").read_text("utf-8")).get("speech") or []
        return [{"t": [round(float(s.get("start", 0)), 2), round(float(s.get("end", 0)), 2)], "text": s.get("text", "")} for s in sp]
    p = Path(item)
    if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".m4v") and p.exists():
        try:
            sys.path.insert(0, str(ROOT / "engine" / "capture"))
            from clip import transcribe
            ws = transcribe(p)
            lines, cur = [], None
            for w in ws:                                   # 단어 → 0.8초 이상 쉬면 줄 바꿈
                if cur and float(w["start"]) - cur["t"][1] <= 0.8:
                    cur["t"][1] = round(float(w["end"]), 2); cur["text"] += " " + w["word"].strip()
                else:
                    cur = {"t": [round(float(w["start"]), 2), round(float(w["end"]), 2)], "text": w["word"].strip()}; lines.append(cur)
            return lines
        except Exception as e:  # noqa: BLE001
            print(f"[눈] 받아쓰기 건너뜀: {e}", file=sys.stderr)
    return []


def resolve(items: list[str], out_dir: Path, t0: float = 0.0, t1: float | None = None) -> tuple[list[Path], dict]:
    """영상 · 그림 · 유튜브 id(분해해 둔 것) → (그림들, 곁들일 텍스트 {항목: 대사})"""
    imgs: list[Path] = []
    extra: dict = {}
    for k, it in enumerate(items):
        vid = _yt(it)
        p = Path(it) if Path(it).is_absolute() else ROOT / it
        if vid and (XRAY / vid / "src.mp4").exists():
            p = XRAY / vid / "src.mp4"
        elif vid and not p.exists():
            raise SystemExit(f"{vid}: 아직 받아 둔 영상이 없습니다 — 먼저 python3 engine/research/analyze_ref.py {vid}")
        if not p.exists():
            raise SystemExit(f"파일이 없습니다: {it}")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            imgs.append(p)
            continue
        got = sheets(p, out_dir / f"m{k}", t0, t1)
        imgs += got
        sp = speech_of(vid or str(p))
        extra[it] = {"길이초": round(_dur(p), 2), "프레임모음": [g.name for g in got], "대사": sp[:80]}
    return imgs, extra


# ---------------------------------------------------------------- 묻기
def _json(text: str):
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1)
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    return json.loads(t)


def _run(cmd: list[str], rt: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, cwd=ROOT, env=_env(rt), capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"{rt}: {TIMEOUT}초 안에 답하지 않았습니다")


def ask_images(images: list[Path], question: str, json_mode: bool = False) -> dict:
    """그림들 + 질문 → {"text", "json"?, "runtime", "model"}"""
    rt, model = runtime()
    images = [Path(i).resolve() for i in images]
    rel = [i.relative_to(ROOT).as_posix() if i.is_relative_to(ROOT) else str(i) for i in images]
    q = question + ("\n\n답은 JSON 하나만(설명 · 코드 블록 없이)." if json_mode else "")
    if rt == "claude":
        prompt = f"{SYSTEM}\n\n" + (("먼저 아래 그림 파일을 Read 도구로 모두 열어 본다(순서대로):\n" + "\n".join(f"- {r}" for r in rel) + "\n\n") if rel else "") + q
        cmd = [shutil.which("claude") or "claude", "-p", prompt, "--output-format", "json", "--strict-mcp-config",
               "--allowedTools", "Read", "--disallowedTools", "Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch"]
        if model:
            cmd += ["--model", model]
        r = _run(cmd, rt)
        try:
            text = json.loads(r.stdout).get("result") or ""
        except json.JSONDecodeError:
            text = ""
    elif rt == "codex":
        prompt = f"{SYSTEM}\n\n" + (("붙인 그림 순서: " + ", ".join(Path(r).name for r in rel) + "\n\n") if rel else "") + q
        cmd = [shutil.which("codex") or "codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only"]
        for i in images:
            cmd += ["-i", str(i)]
        if model:
            cmd += ["--model", model]
        cmd.append(prompt)
        r = _run(cmd, rt)
        text = ""
        for line in r.stdout.splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message":
                text = e["item"].get("text") or text
    elif rt == "antigravity":
        prompt = f"{SYSTEM}\n\n" + (("먼저 아래 그림 파일을 파일 읽기 도구로 모두 열어 본다(순서대로):\n" + "\n".join(f"- {r}" for r in rel) + "\n\n") if rel else "") + q
        cmd = [shutil.which("agy") or "agy", "-p", prompt, "--output-format", "stream-json", "--sandbox",
               "--settings", json.dumps({"permissions": {"allow": ["read_file(*)"]}}), "--add-dir", str(ROOT)]
        if model:
            cmd += ["--model", model]
        r = _run(cmd, rt)
        text = ""
        for line in r.stdout.splitlines()[::-1]:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "result":
                text = (e.get("result") or {}).get("response") or ""
                break
    else:
        raise SystemExit(f"모르는 런타임: {rt}")
    if not text.strip():
        err = (r.stderr or r.stdout or "").strip()[-400:]
        hint = " — Codex 로그인(결제) 상태를 확인하세요(codex login status)" if rt == "codex" and "401" in err else ""
        raise SystemExit(f"{rt} 가 답하지 않았습니다{hint}: {err}")
    out = {"text": text, "runtime": rt, "model": model or "기본"}
    if json_mode:
        try:
            out["json"] = _json(text)
        except ValueError:
            out["json"] = None
    return out


def ask(items: list[str], question: str, json_mode: bool = False, t0: float = 0.0, t1: float | None = None, tag: str = "ask") -> dict:
    """영상 · 그림 · 유튜브 id + 질문 → ask_images 결과(+ 쓴 그림 경로)"""
    d = WORK / tag
    if d.exists():
        shutil.rmtree(d)
    imgs, extra = resolve(items, d, t0, t1)
    q = question
    if extra:
        q += "\n\n영상 정보(프레임 모음 그림 이름 · 대사와 시각):\n" + json.dumps(extra, ensure_ascii=False)[:12000]
    r = ask_images(imgs, q, json_mode)
    r["images"] = [i.relative_to(ROOT).as_posix() if i.is_relative_to(ROOT) else str(i) for i in imgs]
    return r
