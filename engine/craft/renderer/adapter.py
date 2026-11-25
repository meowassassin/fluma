"""Craft 엔진 어댑터 — 콘티 → EffectCraft 프로젝트(engine/craft/motion.py) → 헤드리스 렌더 → 무음 MP4.

제작 파일은 data/compositions/<id>/craft/motion/<id>.ecproj 에 남는다(사람이 EffectCraft 로 열어 고칠 수 있음).
data/compositions/<id>/craft/craft.json 에 생성 때의 해시를 적는다. 그 뒤 파일 해시가 달라졌으면 사람이 고친 것 —
다시 생성하지 않고 고친 프로젝트를 그대로 렌더한다(덮어쓰기 금지). 다시 생성하려면 craft.json 의 motion 항목을 지운다.
"""
import hashlib
import re
import json
import os
import sys
from pathlib import Path
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에

from engines import ROOT, run  # noqa: E402
from craft.materials import build as build_materials  # noqa: E402
from craft.motion import build_jsx  # noqa: E402

HERE = Path(__file__).resolve().parent


def _cli() -> Path:
    f = ROOT / "tools" / "crafts" / "effectcraft" / "installed.json"
    if not f.exists():                                          # 없으면 그 자리에서 설치
        import importlib.util
        spec = importlib.util.spec_from_file_location("fluma_crafts", ROOT / "engine" / "craft" / "crafts.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.ensure("effectcraft")
    try:
        rel = json.loads(f.read_text("utf-8"))["cli"]
    except (OSError, KeyError, json.JSONDecodeError):
        raise SystemExit("EffectCraft 가 설치되지 않았습니다 — Craft 앱 화면에서 설치하거나 python3 engine/craft/crafts.py install effectcraft")
    return ROOT / rel


def _env(lean: bool = False) -> dict:
    # 저장소의 글꼴(Pretendard 등)을 시스템에 설치하지 않고 넘긴다
    e = {**os.environ, "DO_NOT_TRACK": "1", "EFFECTCRAFT_FONT_DIRS": __import__("fonts").font_dirs()}
    if lean:                                   # 한 번에 한 프레임씩(동시에 여러 프레임을 들고 있지 않게) — 시간은 약 10% 늘고 메모리는 약 1GB 준다
        e.setdefault("EFFECTCRAFT_CPU_INFLIGHT", "1")
    return e


# 구간 렌더를 '작은 캐시'로(2026-11-25 실측). EffectCraft 기본 설정은 편집 앱용 캐시(레이어 1GB · 자료 1GB · 미리보기 3GB)를 잡아
# 한 번 그리고 끝나는 렌더가 3초 구간에 2.75GB 를 썼다. 같은 실행 안에서 캐시를 줄이고 렌더 대기열로 그리면 1.2GB ·
# 결과는 바이트까지 같다(md5 동일). 설정 파일은 CLI 가 읽지 않아 prefs.set → renderQueue 를 한 번의 run 으로 부른다. 끄려면 FLUMA_EC_LEAN=0
LEAN = os.environ.get("FLUMA_EC_LEAN", "1") != "0"
LEAN_CACHE = {"memory.layerCacheMb": 128, "memory.mediaCacheMb": 128, "memory.previewCacheMb": 0}


def _lean_commands(out: Path, start: float, end: float, fps: int, draft: bool) -> list[dict]:
    add = {"comp": "Main", "format": "h264", "output": str(out), "timeSpan": "custom", "start": round(start, 6), "end": round(end, 6),
           "frameRate": fps, "audio": "off", **({"resolution": "half", "quality": "draft"} if draft else {})}
    return [{"command": "prefs.set", "params": {"values": LEAN_CACHE}},
            {"command": "renderQueue.add", "params": add},
            {"command": "renderQueue.render", "params": {"wait": True}}]


def available():
    try:
        return _cli().exists()
    except SystemExit:
        return False


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""


def paths(job):
    """비율마다 프로젝트를 따로(9:16 을 사람이 고쳐도 16:9 렌더가 덮어쓰지 않게)"""
    from engines import aspect_tag
    d = ROOT / "data" / "compositions" / job.sb["id"] / "craft"
    return d, d / "motion" / f"{job.sb['id']}{aspect_tag(job.sb)}.ecproj", d / "craft.json"


def build(job) -> Path:
    """프로젝트를 만들거나(입력이 바뀌었을 때) 사람이 고친 것을 그대로 둔다 → .ecproj 경로.
    같은 영상의 빌드는 한 번에 하나(produce 렌더 · 정지 화면 · 미리보기가 동시에 프로젝트를 쓰면 반쯤 쓴 파일이 남았다, 2026-11-24)"""
    from platform_util import file_lock
    _, _, man_p = paths(job)
    man_p.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(man_p.with_suffix(".lock")):
        return _build(job)


def _build(job) -> Path:
    d, proj, man_p = paths(job)
    proj.parent.mkdir(parents=True, exist_ok=True)
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    from engines import aspect_size, aspect_tag
    mkey = "motion" + aspect_tag(job.sb)
    mo = man.get(mkey) or {}
    build_materials(job.sb, [int(t.get("index", i)) for i, t in enumerate(job.scenes)])        # 장면 재료(차트 · 문서 인용 · 일러스트 · 사진 · 화면) → 능력 목록대로 Craft 앱이 만든다
    W, H = aspect_size(job.sb)
    jsx = build_jsx(job.sb, job.captions, job.scenes, proj, fps=job.fps, width=W, height=H)
    # 열쇠 = 스크립트 + 불러오는 파일의 내용 — 같은 경로의 재료가 바뀌어도(새로 올린 녹화 · 다시 그린 그림) 다시 만든다
    refs = sorted(set(re.findall(r'new File\("((?:[^"\\]|\\.)*)"\)', jsx)))
    from craft import refine
    rsteps = refine.motion_steps(job.sb, [int(t.get("index", i)) + 1 for i, t in enumerate(job.scenes)])            # 다듬기(장면 컴프 안 레이어에 EffectCraft 명령) — 열쇠에 넣어 바뀌면 다시
    src_key = hashlib.sha1((jsx + json.dumps(rsteps, ensure_ascii=False) + "".join(_sha(Path(json.loads(f'"{r}"'))) for r in refs)).encode()).hexdigest()
    # 2026-11-24: 빌드가 중간에 끊기면(다듬기 시간 초과 · 동시 빌드) 프로젝트 해시가 기록과 달라져 '사람이 고침'으로 굳고, 콘티를 고쳐도 옛 프로젝트를 렌더했다.
    # 빌드 중 표시(building)가 남아 있으면 사람이 고친 것이 아니라 끊긴 빌드 — 다시 만든다
    if proj.exists() and mo.get("hash") and not mo.get("building") and _sha(proj) != mo["hash"]:
        print(f"[craft] {proj.relative_to(ROOT)} 은 사람이 고쳤습니다 — 다시 만들지 않고 그대로 렌더합니다", file=sys.stderr)
        mo["edited"] = True
        man[mkey] = mo
        man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
        return proj
    if proj.exists() and mo.get("source") == src_key:
        return proj
    man[mkey] = {**mo, "building": True}
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    script = job.work / "motion.jsx"
    script.write_text(jsx, "utf-8")
    run([_cli(), "script", script], cwd=job.work, env=_env(), label="effectcraft script", timeout=300)
    if not proj.exists():
        raise SystemExit("EffectCraft 가 프로젝트를 저장하지 않았습니다")
    if rsteps:
        rf = job.work / "refine.motion.json"
        rf.write_text(json.dumps(rsteps, ensure_ascii=False, indent=1), "utf-8")
        import shutil
        import subprocess
        bak = proj.with_suffix(proj.suffix + ".pre-refine")
        shutil.copy2(proj, bak)             # 다듬기 기록 하나가 깨져도(레이어 이름이 바뀜 등) 초벌 프로젝트로 돌아가 렌더는 계속한다(2026-11-11)
        try:
            r = subprocess.run([str(x) for x in (_cli(), "run", "--commands", rf, "--project", proj, "--save")], cwd=str(job.work), env=_env(), capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            r = subprocess.CompletedProcess([], 1, "", "다듬기 600초 초과")
        bad = refine.script_failures(r.stdout)
        if r.returncode != 0 or bad:
            print("[craft] 다듬기 기록을 적용하지 못해 건너뜀(초벌로 렌더): " + (" / ".join(bad[:6]) or (r.stderr or r.stdout)[-400:]), file=sys.stderr)
            shutil.copy2(bak, proj)
        bak.unlink(missing_ok=True)
    man[mkey] = {"file": str(proj.relative_to(ROOT)), "hash": _sha(proj), "source": src_key, "app": "effectcraft"}
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return proj


def render(job) -> Path:
    proj = build(job)
    out = job.work / "silent.mp4"
    extra = ["--resolution", "half", "--quality", "draft"] if job.draft else []
    if os.environ.get("FLUMA_SEGCACHE", "1") != "0":
        try:
            if _render_segments(job, proj, out, extra):
                return out
        except Exception as e:  # noqa: BLE001 - 캐시는 빨리 가는 길일 뿐, 실패하면 전체 렌더
            print(f"[craft] 구간 캐시를 쓰지 못해 전체 렌더: {str(e)[:200]}", file=sys.stderr)
    args = [_cli(), "render", "--project", proj, "--comp", "Main", "--out", out, "--format", "h264", "--audio", "off", "--fps", str(job.fps), *extra]
    run(args, cwd=job.work, env=_env(), label="effectcraft render", timeout=1800)
    if not out.exists():
        raise SystemExit("EffectCraft 렌더 출력이 없습니다")
    return out


def _profile(job, rec: dict) -> None:
    """렌더 안쪽 기록 — data/workspace/results/render-profile.jsonl(구간마다 초 · 최대 메모리, 동시 수, 이어 붙이기)"""
    import time
    f = ROOT / "data" / "workspace" / "results" / "render-profile.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": job.sb.get("id"), "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stage": "segments", **rec}, ensure_ascii=False) + "\n")


def _render_segments(job, proj: Path, out: Path, extra: list[str]) -> bool:
    """장면 구간마다 열쇠로 캐시하고 바뀐 구간만 그린 뒤 이어 붙인다(engine/craft/renderer/segcache.py)"""
    import shutil
    import subprocess
    import time
    sys.path.insert(0, str(Path(__file__).parent))
    from segcache import frames, plan
    cli = _cli()
    try:                                                       # 렌더러 · 글꼴이 바뀌면 구간을 다시 그린다(2026-11-24: 이름만 열쇠에 있었다)
        cst = cli.stat(); cli_id = f"{cli.name}:{cst.st_size}:{int(cst.st_mtime)}"
    except OSError:
        cli_id = cli.name
    fonts = os.environ.get("EFFECTCRAFT_FONT_DIRS", "")
    fsig = hashlib.sha1("|".join(f"{q}:{q.stat().st_size}" for d_ in fonts.split(os.pathsep) if d_ and Path(d_).is_dir() for q in sorted(Path(d_).iterdir()) if q.is_file()).encode()).hexdigest()[:12] if fonts else ""
    p = plan(proj, job.fps, {"extra": extra, "cli": cli_id, "fonts": fsig})
    if not p:
        return False
    segs, total = p
    cache = paths(job)[0] / "segcache"
    cache.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    todo = []
    for s in segs:
        f = cache / f"{s['key']}.mp4"
        s["file"] = f
        if not (f.exists() and f.stat().st_size > 1000):
            todo.append(s)

    prof = []

    def one(s):
        f = s["file"]; tmp = f.with_suffix(f".part{os.getpid()}.mp4")
        st: dict = {}
        # 렌더는 start ≤ k/fps < end 인 프레임 k 를 그린다 — 경계를 반 프레임 당겨야 소수 반올림에 흔들리지 않는다(실측: 6.666667 이 200번째 프레임을 빼먹음)
        t0_, t1_ = max(0.0, (s["f0"] - 0.5) / job.fps), (s["f1"] - 0.5) / job.fps
        if LEAN:
            cf = job.work / f"seg-{s['key']}.json"
            cf.write_text(json.dumps(_lean_commands(tmp, t0_, t1_, job.fps, bool(extra))), "utf-8")
            try:
                run([_cli(), "run", "--commands", cf, "--project", proj], cwd=job.work, env=_env(lean=True), label="effectcraft render(구간)", timeout=1800, stats=st)
            except SystemExit as e:
                print(f"[craft] 작은 캐시 렌더 실패 — 기본 렌더로: {str(e)[:160]}", file=sys.stderr)
                tmp.unlink(missing_ok=True)
            cf.unlink(missing_ok=True)
        if not (tmp.exists() and frames(tmp) == s["f1"] - s["f0"]):
            run([_cli(), "render", "--project", proj, "--comp", "Main", "--out", tmp, "--format", "h264", "--audio", "off", "--fps", str(job.fps),
                 "--start", f"{t0_:.6f}", "--end", f"{t1_:.6f}", *extra], cwd=job.work, env=_env(), label="effectcraft render(구간)", timeout=1800, stats=st)
        prof.append({"f0": s["f0"], "f1": s["f1"], "lean": LEAN, **st})
        if not tmp.exists() or frames(tmp) != s["f1"] - s["f0"]:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(f)
        return True
    # 바뀐 구간을 함께 그린다 — 렌더 하나가 CPU 약 2.7코어 · 메모리 약 3.7GB(1080×1920, 2026-11-24 실측)라 남은 메모리만큼(최대 3)
    from platform_util import mem_available_gb
    avail = mem_available_gb()
    per = (0.9 if extra else 1.5) if LEAN else (2.0 if extra else 4.2)   # 작은 캐시: 1080×1920 구간 최대 약 1.2GB(2026-11-25 실측)
    jobs = max(1, min(int(os.environ.get("FLUMA_SEG_JOBS", "3")), int(avail // per), len(todo), max(1, (os.cpu_count() or 4) // 3)))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        okk = list(ex.map(one, todo))
    if not all(okk):
        return False
    made = len(todo)
    t_cat = time.time()
    lst = job.work / "segments.txt"
    lst.write_text("".join(f"file '{s['file'].as_posix()}'\n" for s in segs), "utf-8")
    tmp_out = out.with_suffix(".cat.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(tmp_out)], capture_output=True, text=True)
    if r.returncode != 0 or frames(tmp_out) != total:
        tmp_out.unlink(missing_ok=True)
        return False
    shutil.move(str(tmp_out), out)
    _profile(job, {"segments": len(segs), "rendered": made, "jobs": jobs, "avail_gb": round(avail, 1), "draft": bool(extra),
                   "render_sec": round(t_cat - t0, 1), "concat_sec": round(time.time() - t_cat, 1),
                   "peak_mb_max": max((x.get("peak_mb", 0) for x in prof), default=0), "segs": sorted(prof, key=lambda x: x["f0"])})
    print(f"[craft] 구간 렌더: {len(segs)}구간 중 {made}구간만 새로 그림 · 동시 {jobs}({time.time() - t0:.1f}초)", file=sys.stderr)
    # 오래된 구간 파일 정리(이번에 안 쓴 것 중 하루 지난 것)
    keep = {s["file"].name for s in segs}
    for f in cache.glob("*.mp4"):
        if f.name not in keep and time.time() - f.stat().st_mtime > 86400:
            f.unlink(missing_ok=True)
    return True


def snapshot(job, seconds):
    proj = build(job)
    snaps = job.work / "snaps"
    snaps.mkdir(parents=True, exist_ok=True)
    out = [snaps / f"f{float(s):07.3f}.png" for s in seconds]

    def one(sp):
        s, p = sp
        run([_cli(), "render-frame", "--project", proj, "--comp", "Main", "--time", str(s), "--out", p], cwd=job.work, env=_env(), label="effectcraft frame", timeout=120)
    # 장면마다 프로젝트를 여는 프로세스를 하나씩 차례로 띄웠다(정지 화면 7장 약 10~20초) — 3개씩 함께
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=int(os.environ.get("FLUMA_STILL_JOBS", "3"))) as ex:
        list(ex.map(one, zip(seconds, out)))
    return out
