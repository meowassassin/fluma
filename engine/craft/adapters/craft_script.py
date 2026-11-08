"""범용 Craft 재료(craft) — 콘티에 아무 앱의 아무 명령이나 순서대로 적으면 그대로 실행해 재료를 만든다.

고정 어댑터(overlay · chart · model3d …)는 앱마다 기능 몇 개만 쓴다(편향). 이 재료는 catalog 의 명령 9천여 개를
콘티에서 바로 부른다 — 명령은 engine/craft/craft_catalog.py search "<하고 싶은 일>" 로 찾고, 문법은
.claude/skills/crafts/reference/<앱>.md 를 본다.

  { "type": "craft", "id": "m1", "app": "vectorcraft",
    "new":  { 새 문서 · 프로젝트 params (선택 — 앱의 '새로 만들기' 명령 params) },
    "open": "저장소 안 상대 경로 (선택 — 이 파일에서 시작. 원본은 고치지 않고 work 에 사본/새 파일로 저장)",
    "steps": [ { "id": "명령 id", "params": { … } }, … ],
    "export": { "format": "png" | "mp4", "size": [w, h], "time": 초(정지 화면), "start": 초, "end": 초, "fps": 30,
                "duration": 초(정지 그림을 영상으로 늘일 때), 앱별 선택: "comp" · "slide" · "page" · "node" · "dpi" · "view" · "camera" … },
    "as": "image" | "video" (선택 — export.format 을 안 적었을 때 png/mp4 를 고른다) }

경로 규칙
  - params 안 파일 경로(path · src · file · paths …)와 open 은 저장소(ROOT) 안만 읽는다. 상대 경로는 ROOT 기준
    (ROOT 에 없으면 work 기준 — 앞 단계가 만든 파일).
  - 쓰는 경로(export · save 계열 명령의 path, out · dir …)는 work 안만. 상대 경로는 work 기준.
  - "$WORK/이름" 은 work 안 이 재료 폴더(<id>.craft/이름), "$FRAMES" 는 프레임 폴더(<id>.craft/frames/ — 미리 만들어 둔다).
    앞 단계가 $FRAMES 에 PNG 를 쓰면(SolidCraft motion.export_animation · VectorCraft action.batch 등) mp4 내보내기가 그 프레임을 잇는다.
  - 명령 id 가 catalog 에 없으면 실행 전에 거부하고 비슷한 id 3개를 알려 준다.
  - 앱 하나당 시간 제한(기본 300초, CRAFT_SCRIPT_TIMEOUT 또는 재료 "timeout").

결과: out(PNG) 또는 out.with_suffix(".mp4"), 편집 파일 work/<id>.<앱 확장자>, info = {app, editable, steps_run, …}.
SoundCraft 는 소리(wav)라 화면 재료가 아니다 — info["audio"] 에 wav 경로만 남긴다.
"""
from __future__ import annotations

import difflib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TIMEOUT = 300
W0, H0 = 1080, 1920

# 파일 경로로 읽는 params 키(값이 문자열 · 문자열 배열이면 경로로 본다)
PATH_KEYS = {"path", "paths", "src", "file", "files", "image", "images", "mesh", "csv", "xlsx", "pdf", "svg",
             "in", "input", "inputs", "dir", "folder", "out", "output", "outDir", "out_dir", "destinationFolder",
             "projectPath", "target_path", "dest", "save", "lut_path", "font_path", "audio"}
WRITE_KEYS = {"out", "output", "outDir", "out_dir", "destinationFolder", "dest", "save", "target_path"}
WRITE_CMD = re.compile(r"(export|save|write|bake|package|render|extract|split|snapshot|backup|bounce)", re.I)
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")


# ---------------------------------------------------------------- 공통
class Ctx:
    """실행 하나의 상태: 앱 · 작업 폴더 · 남은 시간 · 실행한 명령"""

    def __init__(self, m: dict, out: Path, work: Path):
        self.m, self.out, self.work = m, out, work
        self.app = m["app"]
        self.id = str(m.get("id") or "m1")
        self.dir = work / f"{self.id}.craft"           # 스크립트 · 프레임 · 중간 파일
        self.frames = self.dir / "frames"
        self.ex = dict(m.get("export") or {})
        fmt = (self.ex.get("format") or ("mp4" if m.get("as") == "video" else "png")).lower()
        self.fmt = "mp4" if fmt in ("mp4", "video", "h264") else "png"
        self.deadline = time.monotonic() + float(m.get("timeout") or os.environ.get("CRAFT_SCRIPT_TIMEOUT") or DEFAULT_TIMEOUT)
        self.cli = None
        self.log: list[str] = []
        self.offset = 0                                # 앞에 붙인 명령 수(new) — 실패 번호를 콘티 번호로 맞춘다

    def left(self) -> float:
        t = self.deadline - time.monotonic()
        if t <= 1:
            raise RuntimeError(f"{self.app}: 시간 제한을 넘었습니다")
        return t

    def run(self, args: list, what: str = "", env: dict | None = None, cwd: Path | None = None) -> str:
        args = [str(a) for a in args]
        e = {**os.environ, "DO_NOT_TRACK": "1", "SOUNDCRAFT_NO_PREFS": "1", "VECTORCRAFT_NO_PREFS": "1",
             "WORDCRAFT_REGION": "ko-KR", "EFFECTCRAFT_FONT_DIRS": str(ROOT / "engine" / "assets" / "fonts"), **(env or {})}
        t = self.left()
        try:
            r = subprocess.run(args, cwd=str(cwd or self.dir), text=True, capture_output=True, timeout=t, env=e,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{self.app}: 시간 제한({int(t)}초) 안에 끝나지 않았습니다{' (' + what + ')' if what else ''}")
        self.log.append((r.stdout or "")[-4000:])
        if r.returncode != 0:
            raise RuntimeError(self.fail(r.stdout or "", r.stderr or "", what))
        return r.stdout or ""

    def fail(self, so: str, se: str, what: str) -> str:
        """앱 출력에서 실패한 단계 번호를 찾아 '몇 번째 명령(id)' 으로 알린다"""
        msg = _short((se.strip() or so.strip()).splitlines()[-1] if (se.strip() or so.strip()) else "알 수 없는 오류")
        # 명령마다 JSON 결과 줄을 내는 앱(LightCraft · FilmCraft …): 마지막 줄이 '1개 실패' 같은 요약이면 실패한 줄의 error 를 쓴다
        for ln in so.splitlines():
            if '"ok": false' in ln or '"ok":false' in ln:
                try:
                    j = json.loads(ln[ln.index("{"):])
                    e = j.get("error")
                    msg = _short(f"{j.get('command') or j.get('id') or ''}: {e.get('message') if isinstance(e, dict) else e}")
                    break
                except ValueError:
                    pass
        steps = self.m.get("steps") or []
        ids = ["(new)"] * self.offset + [str((x or {}).get("id") or (x or {}).get("command") or (x or {}).get("tool") or x) if isinstance(x, dict) else str(x) for x in steps]
        n = None
        mm = re.search(r"step (\d+) \(([^)\s]+)\)", se + "\n" + so)
        if mm:                                           # 'step N (id)': 앱마다 0부터 · 1부터가 달라 id 로 맞춘다
            n0, sid = int(mm.group(1)), mm.group(2)
            n = next((n0 - b for b in (0, 1) if 0 <= n0 - b < len(ids) and ids[n0 - b] == sid), None)
        if n is None:
            n = _failed_step(so, se, self.app)
        if n is not None:
            k = n - self.offset
            if 0 <= k < len(steps):
                return f"{self.app}: {k + 1}번째 명령 {steps[k].get('id')} 실패 — {msg}"
            if k < 0:
                return f"{self.app}: 새 문서(new) 만들기 실패 — {msg}"
        return f"{self.app}: {what + ' ' if what else ''}실패 — {msg}"


def _short(s: str, n: int = 300) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


def _failed_step(so: str, se: str, app: str) -> int | None:
    """0부터 센 실패 단계 번호(알 수 있으면)"""
    text = se + "\n" + so
    for pat, base in ((r"\(step (\d+)\)", 0), (r"\bstep[ #]+(\d+)\b", 0), (r"\"\$(\d+)\"", 0), (r"\bline (\d+)\b", 1),
                      (r"\"index\"\s*:\s*(\d+)", 0), (r"\bcommand (\d+)\b", 1)):
        mm = re.search(pat, text, re.I)
        if mm:
            return int(mm.group(1)) - base
    oks, bad = 0, None
    for ln in so.splitlines():                       # 한 줄 JSON 결과: ok:false 가 나온 줄
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        if j.get("ok") is False or "error" in j:
            bad = oks
            break
        if "command" in j or "id" in j or "ok" in j:
            oks += 1
    return bad


def _catalog():
    spec = importlib.util.spec_from_file_location("fluma_craft_catalog", ROOT / "engine" / "craft" / "craft_catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_IDS: dict[str, set] = {}


def _live_ids(app: str) -> set:
    """catalog 이 실행 이름과 다른 앱 — 앱에게 직접 묻는다. PdfCraft catalog 에는 메뉴 id(file.open …)가 섞여 있고
    run --script 가 받는 도구 이름(doc_open · doc_save …) 일부가 빠져 있다"""
    if app != "pdfcraft":
        return set()
    f = ROOT / "tools" / "crafts" / app / "installed.json"
    if not f.exists():
        return set()
    try:
        exe = ROOT / json.loads(f.read_text("utf-8"))["cli"]
        r = subprocess.run([str(exe), "tools"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        d = json.loads(r.stdout)
        d = d.get("tools", d) if isinstance(d, dict) else d
        return {t["name"] for t in d if isinstance(t, dict) and t.get("name")}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return set()


def known_ids(app: str) -> set:
    if app not in _IDS:
        live = _live_ids(app)
        _IDS[app] = live or {r["id"] for r in _catalog().load(app) if r.get("kind") in ("command", "tool")}
    return _IDS[app]


def suggest(app: str, sid: str, n: int = 3) -> list[str]:
    """비슷한 명령 id — catalog 검색(낱말) + 글자 비슷한 것"""
    ids = known_ids(app)
    words = " ".join(re.sub(r"([a-z])([A-Z])", r"\1 \2", sid).replace(".", " ").replace("_", " ").replace("-", " ").split())
    out: list[str] = []
    try:
        for _, r in _catalog().search(words, app=app, n=20):
            if r.get("kind") in ("command", "tool") and r["id"] in ids and r["id"] not in out:
                out.append(r["id"])
    except Exception:  # noqa: BLE001
        pass
    close = difflib.get_close_matches(sid, list(ids), n=n + 3, cutoff=0.4)
    ratio = lambda c: difflib.SequenceMatcher(None, sid.lower(), c.lower()).ratio()   # noqa: E731
    head = sorted(set(close) | {c for c in out[:5] if ratio(c) >= 0.5},
                  key=lambda c: (not c.lower().startswith(sid.lower()), c not in out, -ratio(c)))
    return (head + [c for c in out if c not in head])[:n]


def validate(m: dict) -> list[dict]:
    """콘티 재료 검사 — 실행 전에 거부(앱 · 명령 id · 형식)"""
    app = m.get("app")
    if app not in RUNNERS:
        raise RuntimeError(f"craft 재료: 모르는 앱 '{app}' ({' · '.join(sorted(RUNNERS))})")
    steps = m.get("steps") or []
    if not isinstance(steps, list):
        raise RuntimeError("craft 재료: steps 는 [{id, params}] 목록이어야 합니다")
    ids = known_ids(app)
    norm = []
    for k, s in enumerate(steps):
        if isinstance(s, str):
            s = {"id": s}
        if not isinstance(s, dict) or not (s.get("id") or s.get("command") or s.get("tool")):
            raise RuntimeError(f"craft 재료: {k + 1}번째 명령에 id 가 없습니다")
        sid = str(s.get("id") or s.get("command") or s.get("tool"))
        if ids and sid not in ids:
            sug = suggest(app, sid)
            raise RuntimeError(f"{app}: {k + 1}번째 명령 '{sid}' 는 목록에 없습니다" + (f" — 비슷한 것: {', '.join(sug)}" if sug else ""))
        p = s.get("params", s.get("args", {}))
        if p is None:
            p = {}
        if not isinstance(p, dict):
            raise RuntimeError(f"{app}: {k + 1}번째 명령 {sid} 의 params 는 객체여야 합니다")
        norm.append({**{kk: v for kk, v in s.items() if kk not in ("command", "tool", "args")}, "id": sid, "params": p})
    return norm


# ---------------------------------------------------------------- 경로 지키기
def _inside(p: Path, base: Path) -> bool:
    try:
        p.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def resolve_read(v: str, ctx: Ctx) -> str:
    if v.startswith("builtin:") or "://" in v:
        if "://" in v:
            raise RuntimeError(f"{ctx.app}: 웹 주소는 경로로 쓸 수 없습니다: {v}")
        return v
    if v.startswith("$WORK"):
        return str(ctx.dir / v[5:].lstrip("/"))
    if v == "$FRAMES" or v.startswith("$FRAMES/"):
        return str(ctx.frames / v[7:].lstrip("/")) if len(v) > 7 else str(ctx.frames)
    q = Path(os.path.expanduser(v))
    if not q.is_absolute():
        q = ROOT / q if (ROOT / q).exists() or not (ctx.work / q).exists() else ctx.work / q
    if not (_inside(q, ROOT) or _inside(q, ctx.work)):
        raise RuntimeError(f"{ctx.app}: 저장소 밖 파일은 읽을 수 없습니다: {v}")
    return str(q.resolve())


def resolve_write(v: str, ctx: Ctx) -> str:
    if v.startswith("$WORK"):
        q = ctx.dir / v[5:].lstrip("/")
    elif v == "$FRAMES" or v.startswith("$FRAMES/"):
        q = ctx.frames / v[7:].lstrip("/") if len(v) > 7 else ctx.frames
    else:
        q = Path(os.path.expanduser(v))
        if not q.is_absolute():
            q = ctx.dir / q
    if not _inside(q, ctx.work):
        raise RuntimeError(f"{ctx.app}: 작업 폴더 밖에는 쓸 수 없습니다: {v}")
    q.parent.mkdir(parents=True, exist_ok=True)
    return str(q.resolve())


def _looks_path(v: str) -> bool:
    return bool(v) and ("/" in v or EXT_RE.search(v) is not None) and "\n" not in v and len(v) < 1024


def fix_paths(params, ctx: Ctx, cmd: str):
    """params 안 경로를 검사하고 절대 경로로 바꾼다(앱마다 상대 경로 기준이 달라서)"""
    writes = bool(WRITE_CMD.search(cmd))

    def one(key: str, v):
        if isinstance(v, str):
            if v.startswith("$WORK") or v.startswith("$FRAMES"):
                return resolve_write(v, ctx) if (key in WRITE_KEYS or writes) else resolve_read(v, ctx)
            if key in PATH_KEYS and _looks_path(v) and not v.startswith("$"):
                return resolve_write(v, ctx) if (key in WRITE_KEYS or (writes and key in ("path", "dir", "folder", "file"))) else resolve_read(v, ctx)
            if v.startswith(("/", "~")) and _looks_path(v):          # 키 이름과 상관없이 절대 경로는 검사
                q = Path(os.path.expanduser(v))
                if q.parts[:2] and Path(*q.parts[:2]).exists() and not (_inside(q, ROOT) or _inside(q, ctx.work)):
                    raise RuntimeError(f"{ctx.app}: 저장소 밖 경로는 쓸 수 없습니다: {v}")
            return v
        if isinstance(v, list):
            return [one(key, x) for x in v]
        if isinstance(v, dict):
            return {k: one(k, x) for k, x in v.items()}
        return v

    return {k: one(k, v) for k, v in (params or {}).items()}


# ---------------------------------------------------------------- 내보내기 도움
def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p.resolve())


def _fit_png(src: Path, dst: Path, size) -> None:
    """size [w, h] 에 맞춘다(비율 유지 · 남는 곳 투명). size 가 없으면 그대로 복사"""
    from PIL import Image
    if not size:
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        return
    w, h = int(size[0]), int(size[1])
    with Image.open(src) as im:
        im = im.convert("RGBA")
        if im.size == (w, h):
            im.save(dst)
            return
        k = min(w / im.width, h / im.height)
        r = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        can = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        can.paste(r, ((w - r.width) // 2, (h - r.height) // 2))
        can.save(dst)


def _trim(png: Path, pad: int = 24) -> None:
    """흰 여백 잘라 내기(표 · 문서 쪽에서 내용만)"""
    from PIL import Image, ImageChops
    with Image.open(png) as im:
        im = im.convert("RGB")
        box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
        if box:
            x0, y0, x1, y1 = box
            im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))).save(png)


def _ff(args: list, ctx: Ctx, what: str) -> None:
    ctx.run(["ffmpeg", "-y", "-loglevel", "error", *args], what)


def _vf(size) -> list:
    if not size:
        return ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2"]
    w, h = int(size[0]), int(size[1])
    return ["-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"]


def frames_to_mp4(frames: list[Path], mp4: Path, ctx: Ctx, fps: float) -> None:
    lst = ctx.dir / "frames.txt"
    d = 1.0 / fps
    lst.write_text("".join(f"file '{f.resolve()}'\nduration {d:.6f}\n" for f in frames) + f"file '{frames[-1].resolve()}'\n", "utf-8")
    _ff(["-f", "concat", "-safe", "0", "-i", lst, *_vf(ctx.ex.get("size")), "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264", mp4], ctx, "프레임 → mp4")


def still_to_mp4(png: Path, mp4: Path, ctx: Ctx) -> None:
    dur = float(ctx.ex.get("duration") or (float(ctx.ex["end"]) - float(ctx.ex.get("start", 0)) if ctx.ex.get("end") else 2.0))
    fps = float(ctx.ex.get("fps") or 30)
    _ff(["-loop", "1", "-i", png, "-t", f"{dur:.3f}", *_vf(ctx.ex.get("size")), "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264", mp4], ctx, "정지 화면 → mp4")


def video_to_still(mp4: Path, png: Path, ctx: Ctx) -> None:
    _ff(["-ss", str(float(ctx.ex.get("time", 0))), "-i", mp4, "-frames:v", "1", png], ctx, "영상 → 정지 화면")
    _fit_png(png, png, ctx.ex.get("size"))


def frame_files(ctx: Ctx) -> list[Path]:
    return sorted(p for p in ctx.frames.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg"))


def finish_still(png: Path, ctx: Ctx) -> dict:
    """앱이 정지 그림만 낼 때: png → 재료(png 또는 mp4 — $FRAMES 에 프레임이 있으면 그걸 잇는다)"""
    if ctx.fmt == "png":
        if not png.exists():
            raise RuntimeError(f"{ctx.app}: 내보낸 그림이 없습니다")
        _fit_png(png, ctx.out, ctx.ex.get("size"))
        return {}
    mp4 = ctx.out.with_suffix(".mp4")
    fr = frame_files(ctx)
    if fr:
        frames_to_mp4(fr, mp4, ctx, float(ctx.ex.get("fps") or 30))
    elif png.exists():
        still_to_mp4(png, mp4, ctx)
    else:
        raise RuntimeError(f"{ctx.app}: 내보낸 그림이 없습니다")
    if png.exists():
        _fit_png(png, ctx.out, ctx.ex.get("size"))     # 첫 화면(포스터)도 남긴다
    return {"file_suffix": ".mp4"}


def shift_refs(o, k: int):
    """앞 단계 결과 참조("$N.id" · "$N") — 콘티는 자기 steps 만 0부터 센다. 앞에 붙인 명령(new) 수만큼 민다"""
    if not k:
        return o
    if isinstance(o, str):
        return re.sub(r"(?<!\$)\$(\d+)(?=\.|$)", lambda mm: f"${int(mm.group(1)) + k}", o) if o.startswith("$") else o
    if isinstance(o, list):
        return [shift_refs(x, k) for x in o]
    if isinstance(o, dict):
        return {kk: shift_refs(v, k) for kk, v in o.items()}
    return o


REF = re.compile(r"^\$(\d+|last)(?:\.|$)")


def resolve_refs(o, results: list, offset: int, ctx: Ctx, k: int):
    """앱에 참조 문법이 없을 때 우리가 채운다: "$N.a.0"(N = 콘티 steps 번호, 0부터) · "$last.a" """
    if isinstance(o, str) and REF.match(o):
        head, *path = o[1:].split(".")
        i = len(results) - 1 if head == "last" else int(head) + offset
        if not 0 <= i < len(results):
            raise RuntimeError(f"{ctx.app}: {k + 1}번째 명령의 참조 {o} — 그 단계 결과가 아직 없습니다")
        v = results[i]
        for key in path:
            if isinstance(v, list) and key.isdigit() and int(key) < len(v):
                v = v[int(key)]
            elif isinstance(v, dict) and key in v:
                v = v[key]
            else:
                raise RuntimeError(f"{ctx.app}: {k + 1}번째 명령의 참조 {o} — 결과에 '{key}' 가 없습니다: {_short(json.dumps(results[i], ensure_ascii=False), 160)}")
        return v
    if isinstance(o, list):
        return [resolve_refs(x, results, offset, ctx, k) for x in o]
    if isinstance(o, dict):
        return {kk: resolve_refs(v, results, offset, ctx, k) for kk, v in o.items()}
    return o


def _jsonl(lines: list) -> str:
    return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines)


def _open_copy(ctx: Ctx, ed: Path) -> Path | None:
    """open 파일을 편집 파일 자리로 복사(원본은 고치지 않는다)"""
    if not ctx.m.get("open"):
        return None
    src = Path(resolve_read(ctx.m["open"], ctx))
    if not src.exists():
        raise RuntimeError(f"{ctx.app}: open 파일이 없습니다: {ctx.m['open']}")
    if src.suffix.lower() == ed.suffix.lower():
        if src.resolve() != ed.resolve():
            shutil.copyfile(src, ed)
        return ed
    return src


def _opened(ctx: Ctx) -> Path | None:
    if not ctx.m.get("open"):
        return None
    p = Path(resolve_read(ctx.m["open"], ctx))
    if not p.exists():
        raise RuntimeError(f"{ctx.app}: open 파일이 없습니다: {ctx.m['open']}")
    return p


# ---------------------------------------------------------------- 앱별 실행기
# 각 실행기: (ctx, steps) -> (편집 파일 Path | None, info dict). steps 는 [{"id","params"}] (경로 정리 끝)

def r_vectorcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.vectorcraft"
    src = _opened(ctx)
    seq = []
    if not src:
        seq.append({"command": "file.new", "params": {"width": W0, "height": H0, "units": "Pixels", **(ctx.m.get("new") or {})}})
    ctx.offset = len(seq)
    seq += [{"command": s["id"], "params": shift_refs(s["params"], ctx.offset)} for s in steps]
    f = ctx.dir / "steps.json"
    f.write_text(json.dumps(seq, ensure_ascii=False, indent=1), "utf-8")
    png = ctx.dir / "export.png"
    args = [ctx.cli, "run"] + (["--in", src] if src else []) + ["--commands", f, "--export", ed, "--export", png]
    if ctx.ex.get("scale"):
        args += ["--scale", ctx.ex["scale"]]
    ctx.run(args, "run")
    return ed, finish_still(png, ctx)


def r_effectcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.ecproj"
    src = _open_copy(ctx, ed)
    seq = []
    if not src:
        seq.append({"command": "comp.new", "params": {"name": "Main", "width": W0, "height": H0, "duration": 3, "fps": 30, **(ctx.m.get("new") or {})}})
    ctx.offset = len(seq)
    seq += [{"command": s["id"], "params": s["params"]} for s in steps]
    f = ctx.dir / "steps.json"
    f.write_text(json.dumps(seq, ensure_ascii=False, indent=1), "utf-8")
    if seq:
        args = [ctx.cli, "run", "--commands", f] + (["--project", ed, "--save"] if src else ["--empty", "--save-as", ed])
        ctx.run(args, "run")
    comp = ["--comp", str(ctx.ex["comp"])] if ctx.ex.get("comp") else []
    if ctx.fmt == "mp4":
        mp4 = ctx.out.with_suffix(".mp4")
        rng = []
        if ctx.ex.get("start") is not None:
            rng += ["--start", ctx.ex["start"]]
        if ctx.ex.get("end") is not None:
            rng += ["--end", ctx.ex["end"]]
        ctx.run([ctx.cli, "render", "--project", ed, *comp, "--out", mp4, "--format", "h264", "--audio", "off", *rng,
                 *(["--fps", ctx.ex["fps"]] if ctx.ex.get("fps") else [])], "render")
        if ctx.ex.get("size"):
            tmp = ctx.dir / "render.mp4"
            shutil.move(mp4, tmp)
            _ff(["-i", tmp, *_vf(ctx.ex["size"]), "-pix_fmt", "yuv420p", "-c:v", "libx264", mp4], ctx, "크기 맞추기")
        video_to_still(mp4, ctx.out, ctx)
        return ed, {"file_suffix": ".mp4"}
    png = ctx.dir / "frame.png"
    ctx.run([ctx.cli, "render-frame", "--project", ed, *comp, "--time", float(ctx.ex.get("time", 0)), "--out", png], "render-frame")
    return ed, finish_still(png, ctx)


def r_filmcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.fcproj"
    src = _open_copy(ctx, ed)
    seq = []
    if not src:
        seq.append({"id": "file.newSequence", "params": {"name": "Main", "width": W0, "height": H0, "fps": 30, **(ctx.m.get("new") or {})}})
    ctx.offset = len(seq)
    seq += [{"id": s["id"], "params": s["params"]} for s in steps]
    if any(REF.search(x) for s in steps for x in _strings(s["params"])):
        # FilmCraft 스크립트에는 앞 결과 참조가 없다 → 한 명령씩 돌려 "$N.clips.0" 같은 참조를 채운다
        results: list = []
        for k, x in enumerate(seq):
            first = k == 0 and not src
            p = resolve_refs(x["params"], results, ctx.offset, ctx, k - ctx.offset)
            so = ctx.run([ctx.cli, "--compact", *(["--save-as", ed] if first else ["--project", ed, "--save"]), "exec", x["id"],
                          json.dumps(p, ensure_ascii=False)], f"{k - ctx.offset + 1}번째 명령 {x['id']}" if k >= ctx.offset else "new")
            try:
                results.append(json.loads(so[so.index("{"):]))
            except ValueError:
                results.append({})
    else:
        f = ctx.dir / "script.jsonl"
        f.write_text(_jsonl(seq), "utf-8")
        ctx.run([ctx.cli, "--compact", *(["--project", ed, "--save"] if src else ["--save-as", ed]), "run", f], "run")
    if ctx.fmt == "mp4":
        mp4 = ctx.out.with_suffix(".mp4")
        rng = ["--start", ctx.ex.get("start", 0), "--end", ctx.ex["end"]] if ctx.ex.get("end") is not None else []
        ctx.run([ctx.cli, "--project", ed, "export", mp4, "--format", "h264", "--no-audio", *rng], "export")
        if ctx.ex.get("size"):
            tmp = ctx.dir / "export.mp4"
            shutil.move(mp4, tmp)
            _ff(["-i", tmp, *_vf(ctx.ex["size"]), "-pix_fmt", "yuv420p", "-c:v", "libx264", mp4], ctx, "크기 맞추기")
        video_to_still(mp4, ctx.out, ctx)
        return ed, {"file_suffix": ".mp4"}
    png = ctx.dir / "frame.png"
    ctx.run([ctx.cli, "--project", ed, "render", "--seconds", float(ctx.ex.get("time", 0)), "--out", png], "render")
    return ed, finish_still(png, ctx)


def r_photocraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.psd"
    src = _opened(ctx)
    args = [ctx.cli, "run"]
    args += [src] if src else ["--new", json.dumps({"width": W0, "height": H0, **(ctx.m.get("new") or {})}, ensure_ascii=False)]
    for s in steps:
        args += ["--cmd", s["id"], "--params", json.dumps(s["params"], ensure_ascii=False)]
    args += ["--out", ed]
    ctx.run(args, "run")
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "convert", ed, png], "convert")
    return ed, finish_still(png, ctx)


def r_figcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.figcraft"
    src = _opened(ctx)
    seq = []
    if ctx.m.get("new") is not None or not src:
        seq.append({"command": "frame.create", "as": "new",
                    "params": {"x": 0, "y": 0, "width": W0, "height": H0, "name": "Frame", **(ctx.m.get("new") or {})}})
    ctx.offset = len(seq)
    for s in steps:
        x = {"command": s["id"], "params": s["params"]}
        if s.get("as"):
            x["as"] = s["as"]
        seq.append(x)
    f = ctx.dir / "script.json"
    f.write_text(json.dumps(seq, ensure_ascii=False, indent=1), "utf-8")
    ctx.run([ctx.cli, "run", f, *(["--in", src] if src else []), "--out", ed], "run")
    png = ctx.dir / "export.png"
    node = ctx.ex.get("node") or (None if src else (ctx.m.get("new") or {}).get("name", "Frame"))
    ctx.run([ctx.cli, "export", ed, "-o", png, *(["--node", str(node)] if node else []), "--scale", ctx.ex.get("scale", 1)], "export")
    return ed, finish_still(png, ctx)


def r_designcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.designcraft"
    src = _opened(ctx)
    lines = []
    if not src:
        lines.append(f"file.new {json.dumps({'width': W0, 'height': H0, 'intent': 'mobile', 'pages': 1, **(ctx.m.get('new') or {})}, ensure_ascii=False)}")
    ctx.offset = len(lines)
    lines += [f"{s['id']} {json.dumps(shift_refs(s['params'], ctx.offset), ensure_ascii=False)}" for s in steps]
    f = ctx.dir / "script.dcs"
    f.write_text("\n".join(lines) + "\n", "utf-8")
    ctx.run([ctx.cli, "script", f, *(["--in", src] if src else []), "--save", ed], "script")
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "run", "--in", ed, "--page", int(ctx.ex.get("page", 0)), "--scale", ctx.ex.get("scale", 1), "--export", png], "export")
    return ed, finish_still(png, ctx)


def r_deckcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.deckcraft"
    src = _opened(ctx)
    lines = []
    if not src:
        lines.append("file.new=" + json.dumps({"size": [540, 960], "blank": True, **(ctx.m.get("new") or {})}, ensure_ascii=False))
        if not any(s["id"].startswith("slide.new") for s in steps):
            lines.append('slide.new={"layout":"blank"}')
    ctx.offset = len(lines)
    lines += [s["id"] + ("=" + json.dumps(s["params"], ensure_ascii=False) if s["params"] else "") for s in steps]
    f = ctx.dir / "cmds.txt"
    f.write_text("\n".join(lines) + "\n", "utf-8")
    ctx.run([ctx.cli, "run", *(["--in", src] if src else []), "--cmd-file", f, "--save", ed], "run")
    slide = int(ctx.ex.get("slide", 0))
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "render", ed, "--slide", slide, "--scale", ctx.ex.get("scale", 2), png], "render")
    if ctx.fmt == "mp4" and slide > 0 and not frame_files(ctx) and ctx.ex.get("transition", True):
        # 그 슬라이드로 들어오는 전환을 프레임으로 → 끝 화면 유지
        fps = float(ctx.ex.get("fps") or 30)
        tdur = float(ctx.ex.get("transition_sec", 0.8))
        n = max(2, int(round(tdur * fps)))
        ts = ",".join(f"{k / (n - 1):.3f}" for k in range(n))
        ctx.frames.mkdir(parents=True, exist_ok=True)
        try:
            ctx.run([ctx.cli, "render-transition", ed, "--slide", slide, "--t", ts, "--width", int((ctx.ex.get("size") or [W0])[0]), ctx.frames / "t.png"], "render-transition")
        except RuntimeError:
            pass
        fr = frame_files(ctx)
        hold = max(0, int(round((float(ctx.ex.get("duration") or 2.0) - tdur) * fps)))
        if fr:
            frames_to_mp4(fr + [png] * hold, ctx.out.with_suffix(".mp4"), ctx, fps)
            _fit_png(png, ctx.out, ctx.ex.get("size"))
            return ed, {"file_suffix": ".mp4"}
    return ed, finish_still(png, ctx)


def r_lightcraft(ctx: Ctx, steps):
    src = _opened(ctx)
    if not src:
        raise RuntimeError("lightcraft: 사진 보정이라 open(원본 사진)이 꼭 있어야 합니다")
    ed = ctx.work / f"{ctx.id}.lcsettings.json"
    png = ctx.dir / "export.png"
    seq = [{"command": s["id"], "params": s["params"]} for s in steps]
    size = ctx.ex.get("size")
    exp = {"path": str(png), "format": "png", "dontEnlarge": False}
    if size:
        exp.update({"width": int(size[0]), "height": int(size[1]), "fit": "widthHeight"})
    else:
        exp["longEdge"] = 0
    seq += [{"command": "app.export", "params": exp}, {"command": "develop.get", "params": {}}]
    f = ctx.dir / "script.jsonl"
    f.write_text(_jsonl(seq), "utf-8")
    so = ctx.run([ctx.cli, "run", "--import", src, "--script", f], "run")
    for ln in reversed(so.splitlines()):
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        if j.get("command") == "develop.get" and j.get("ok"):
            ed.write_text(json.dumps({"source": _rel(src), "settings": j.get("result")}, ensure_ascii=False, indent=1), "utf-8")
            break
    return (ed if ed.exists() else None), finish_still(png, ctx)


def r_pdfcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.pdf"
    src = _opened(ctx)
    seq = []
    if src:
        seq.append({"tool": "doc_open", "args": {"path": str(src)}})
    elif ctx.m.get("new") is not None:
        seq.append({"tool": "doc_create", "args": dict(ctx.m["new"])})
    ctx.offset = len(seq)
    seq += [{"tool": s["id"], "args": s["params"]} for s in steps]
    seq.append({"tool": "doc_save", "args": {"doc": int(ctx.ex.get("doc", 1)), "path": str(ed)}})
    f = ctx.dir / "steps.json"
    f.write_text(json.dumps(seq, ensure_ascii=False, indent=1), "utf-8")
    root = os.path.commonpath([str(ROOT), str(ctx.work.resolve())])
    so = ctx.run([ctx.cli, "run", "--script", f, "--report", "--root", root], "run")
    try:
        rep = json.loads(so[so.index("{"):])
        for k, st in enumerate(rep.get("steps") or []):
            if str(st.get("status", "ok")).lower() not in ("ok", "success", "done"):
                n = k - ctx.offset
                sid = steps[n]["id"] if 0 <= n < len(steps) else seq[k]["tool"]
                raise RuntimeError(f"pdfcraft: {n + 1}번째 명령 {sid} 실패 — {_short(json.dumps(st.get('error') or st.get('result'), ensure_ascii=False))}")
    except ValueError:
        pass
    if not ed.exists():
        raise RuntimeError("pdfcraft: 결과 PDF 를 저장하지 못했습니다(doc_save)")
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "render", ed, "--page", int(ctx.ex.get("page", 1)), "--dpi", int(ctx.ex.get("dpi", 200)), "--out", png], "render")
    return ed, finish_still(png, ctx)


def r_solidcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.sc"
    src = _opened(ctx)
    f = ctx.dir / "script.json"
    f.write_text(json.dumps({"commands": [{"command": s["id"], "params": s["params"]} for s in steps]}, ensure_ascii=False, indent=1), "utf-8")
    ctx.frames.mkdir(parents=True, exist_ok=True)
    ctx.run([ctx.cli, "run", f, *(["--in", src] if src else []), "--save", ed], "run")
    size = ctx.ex.get("size") or [W0, H0]
    png = ctx.dir / "export.png"
    if ctx.ex.get("mode") == "render":
        args = [ctx.cli, "render", ed, "--out", png, "--width", int(size[0]), "--height", int(size[1])]
        if ctx.ex.get("setup"):
            args += ["--setup", ctx.ex["setup"]]
        if ctx.ex.get("samples"):
            args += ["--progressive", "--samples", int(ctx.ex["samples"])]
    else:
        args = [ctx.cli, "snapshot", ed, "--out", png, "--width", int(size[0]), "--height", int(size[1]), "--no-grid", "--no-axes"]
        if ctx.ex.get("camera"):
            args += ["--camera", json.dumps(ctx.ex["camera"])]
        elif ctx.ex.get("view"):
            args += ["--view", ctx.ex["view"]]
    ctx.run(args, "snapshot")
    return ed, finish_still(png, ctx)


def r_cadcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.dxf"
    src = _opened(ctx)
    args = [ctx.cli, "run"] + ([src] if src else []) + ([] if src or ctx.ex.get("imperial") else ["--metric"])
    for s in steps:
        args += ["--cmd", f"{s['id']} {json.dumps(s['params'], ensure_ascii=False)}" if s["params"] else s["id"]]
    png = ctx.dir / "export.png"
    args += ["--save", ed, "--export", png]
    if ctx.ex.get("window"):
        args.append("--window=" + ",".join(str(v) for v in ctx.ex["window"]))
    else:
        args += ["--view", "extents"]
    ctx.run(args, "run")
    return ed, finish_still(png, ctx)


def r_texturecraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.tcraft"
    src = _opened(ctx)
    base = str(src) if src else (ctx.m.get("new") or {}).get("mesh", "builtin:material_ball")
    if not str(base).startswith("builtin:") and not src:
        base = resolve_read(str(base), ctx)
    f = ctx.dir / "batch.json"
    f.write_text(json.dumps({"open": base, "steps": [{"id": s["id"], "params": s["params"]} for s in steps], "save": str(ed)},
                            ensure_ascii=False, indent=1), "utf-8")
    ctx.run([ctx.cli, "batch", f], "batch")
    size = ctx.ex.get("size") or [540, 960]
    png = ctx.dir / "export.png"
    opt = []
    for k in ("yaw", "pitch", "samples", "camera"):
        if ctx.ex.get(k) is not None:
            opt += [f"--{k}", ctx.ex[k]]
    ctx.run([ctx.cli, "render", ed, png, "--size", f"{int(size[0])}x{int(size[1])}", *opt], "render")
    if ctx.fmt == "mp4" and ctx.ex.get("turntable") and not frame_files(ctx):
        ctx.frames.mkdir(parents=True, exist_ok=True)
        n = int(ctx.ex.get("frames", 36))
        y0 = float(ctx.ex.get("yaw", 0))
        rest = [x for x in opt if x not in ("--yaw",)]
        if "--yaw" in opt:
            i = opt.index("--yaw")
            rest = opt[:i] + opt[i + 2:]
        for k in range(n):
            ctx.run([ctx.cli, "render", ed, ctx.frames / f"f{k:04d}.png", "--size", f"{int(size[0])}x{int(size[1])}", "--yaw", y0 + 360.0 * k / n, *rest], "turntable")
    return ed, finish_still(png, ctx)


def r_gridcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.xlsx"
    src = _opened(ctx)
    f = ctx.dir / "script.jsonl"
    f.write_text("".join(f"{s['id']}={json.dumps(s['params'], ensure_ascii=False)}\n" for s in steps), "utf-8")
    ctx.run([ctx.cli, "run", *(["--in", src] if src else []), "--script", f, "--out", ed, "--quiet"], "run")
    info = {}
    try:
        info["table"] = ctx.run([ctx.cli, "cat", ed, "--range", ctx.ex.get("range", "A1:H30"), "--csv"], "cat").strip()[:4000]
    except RuntimeError:
        pass
    # 그림: 시트 → PDF(GridCraft) → PNG(PdfCraft). GridCraft PDF 는 한글이 빠진다(참고 문서) — 숫자 · 영문 표용
    pdf = ctx.dir / "sheet.pdf"
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "convert", ed, pdf], "convert pdf")
    from ..materials import cli as _cli
    ctx.run([_cli("pdfcraft"), "render", pdf, "--page", 1, "--dpi", int(ctx.ex.get("dpi", 200)), "--out", png], "render")
    if ctx.ex.get("trim", True):
        _trim(png, int(ctx.ex.get("pad", 24)))
    info.update(finish_still(png, ctx))
    return ed, info


def r_wordcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.docx"
    src = _opened(ctx)
    cmds = []
    if not src:
        new = {"width": 360, "height": 640, **(ctx.m.get("new") or {})}
        cmds.append({"command": "layout.size", "params": {"width": new["width"], "height": new["height"]}})
        if new.get("margins"):
            cmds.append({"command": "layout.margins", "params": new["margins"]})
    ctx.offset = len(cmds)
    cmds += [{"command": s["id"], "params": s["params"]} for s in steps]
    script = {"commands": cmds, "save": [str(ed)]}
    if src:
        script["file"] = str(src)
    f = ctx.dir / "script.json"
    f.write_text(json.dumps(script, ensure_ascii=False, indent=1), "utf-8")
    ctx.run([ctx.cli, "run", "--script", f, "--print"], "run")
    png = ctx.dir / "export.png"
    ctx.run([ctx.cli, "render", ed, png, "--page", int(ctx.ex.get("page", 1)), "--scale", ctx.ex.get("scale", 3)], "render")
    return ed, finish_still(png, ctx)


def r_soundcraft(ctx: Ctx, steps):
    ed = ctx.work / f"{ctx.id}.scraft"
    src = _opened(ctx)
    f = ctx.dir / "steps.txt"
    f.write_text("".join(f"{s['id']} {json.dumps(s['params'], ensure_ascii=False)}\n" for s in steps), "utf-8")
    wav = ctx.out.with_suffix(".wav")
    args = [ctx.cli, "script", f, *(["--in", src] if src else []), "--bounce", wav, "--save", ed]
    if ctx.ex.get("end") is not None:
        args += ["--end", ctx.ex["end"]]
    so = ctx.run(args, "script")
    info = {"audio": _rel(wav), "media": "audio"}
    mm = re.search(r"\{[^{}]*lufs[^{}]*\}", so, re.I)
    if mm:
        try:
            info["loudness"] = json.loads(mm.group(0))
        except ValueError:
            pass
    return ed, info


RUNNERS = {
    "vectorcraft": r_vectorcraft, "effectcraft": r_effectcraft, "filmcraft": r_filmcraft, "photocraft": r_photocraft,
    "figcraft": r_figcraft, "designcraft": r_designcraft, "deckcraft": r_deckcraft, "lightcraft": r_lightcraft,
    "pdfcraft": r_pdfcraft, "solidcraft": r_solidcraft, "cadcraft": r_cadcraft, "texturecraft": r_texturecraft,
    "gridcraft": r_gridcraft, "wordcraft": r_wordcraft, "soundcraft": r_soundcraft,
}


# ---------------------------------------------------------------- 재료 어댑터
def craft(m: dict, out: Path, work: Path) -> dict:
    steps = validate(m)
    ctx = Ctx(m, out, work)
    if ctx.dir.exists():
        shutil.rmtree(ctx.dir, ignore_errors=True)
    ctx.dir.mkdir(parents=True, exist_ok=True)
    if any(isinstance(v, str) and "$FRAMES" in v for s in steps for v in _strings(s["params"])):
        ctx.frames.mkdir(parents=True, exist_ok=True)
    fixed = [{**s, "params": fix_paths(s["params"], ctx, s["id"])} for s in steps]
    if m.get("new"):
        m = {**m, "new": fix_paths(m["new"], ctx, "new")}
        ctx.m = m
    from ..materials import cli
    ctx.cli = cli(ctx.app)
    for p in (out, out.with_suffix(".mp4")):
        p.unlink(missing_ok=True)
    ed, info = RUNNERS[ctx.app](ctx, fixed)
    res = {"app": ctx.app, "steps_run": [s["id"] for s in fixed], **info}
    if ed and Path(ed).exists():
        res["editable"] = _rel(Path(ed))
    return res


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


ADAPTERS = {"craft": craft}
