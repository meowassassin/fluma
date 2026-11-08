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
from craft.art import build_all as build_art  # noqa: E402
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


def _env() -> dict:
    # 저장소의 글꼴(Pretendard 등)을 시스템에 설치하지 않고 넘긴다
    return {**os.environ, "DO_NOT_TRACK": "1", "EFFECTCRAFT_FONT_DIRS": str(ROOT / "engine" / "assets" / "fonts")}


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
    """프로젝트를 만들거나(입력이 바뀌었을 때) 사람이 고친 것을 그대로 둔다 → .ecproj 경로"""
    d, proj, man_p = paths(job)
    proj.parent.mkdir(parents=True, exist_ok=True)
    man = json.loads(man_p.read_text("utf-8")) if man_p.exists() else {}
    from engines import aspect_size, aspect_tag
    mkey = "motion" + aspect_tag(job.sb)
    mo = man.get(mkey) or {}
    build_materials(job.sb, [int(t.get("index", i)) for i, t in enumerate(job.scenes)])        # 장면 재료(차트 · 문서 인용 · 일러스트 · 사진 · 화면) → 능력 목록대로 Craft 앱이 만든다
    build_art(job.sb["id"])        # 형태(forms/*.form.json) → 부품 레이어 SVG + 뼈대(그림이 바뀌면 JSX 도 바뀌어 다시 만든다)
    W, H = aspect_size(job.sb)
    jsx = build_jsx(job.sb, job.captions, job.scenes, proj, fps=job.fps, width=W, height=H)
    # 열쇠 = 스크립트 + 불러오는 파일의 내용 — 같은 경로의 재료가 바뀌어도(새로 올린 녹화 · 다시 그린 그림) 다시 만든다
    refs = sorted(set(re.findall(r'new File\("((?:[^"\\]|\\.)*)"\)', jsx)))
    from craft import refine
    rsteps = refine.motion_steps(job.sb, [int(t.get("index", i)) + 1 for i, t in enumerate(job.scenes)])            # 다듬기(장면 컴프 안 레이어에 EffectCraft 명령) — 열쇠에 넣어 바뀌면 다시
    src_key = hashlib.sha1((jsx + json.dumps(rsteps, ensure_ascii=False) + "".join(_sha(Path(json.loads(f'"{r}"'))) for r in refs)).encode()).hexdigest()
    if proj.exists() and mo.get("hash") and _sha(proj) != mo["hash"]:
        print(f"[craft] {proj.relative_to(ROOT)} 은 사람이 고쳤습니다 — 다시 만들지 않고 그대로 렌더합니다", file=sys.stderr)
        mo["edited"] = True
        man[mkey] = mo
        man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
        return proj
    if proj.exists() and mo.get("source") == src_key:
        return proj
    script = job.work / "motion.jsx"
    script.write_text(jsx, "utf-8")
    run([_cli(), "script", script], cwd=job.work, env=_env(), label="effectcraft script", timeout=300)
    if not proj.exists():
        raise SystemExit("EffectCraft 가 프로젝트를 저장하지 않았습니다")
    if rsteps:
        rf = job.work / "refine.motion.json"
        rf.write_text(json.dumps(rsteps, ensure_ascii=False, indent=1), "utf-8")
        try:
            import subprocess
            r = subprocess.run([str(x) for x in (_cli(), "run", "--commands", rf, "--project", proj, "--save")], cwd=str(job.work), env=_env(), capture_output=True, text=True, timeout=600)
            bad = refine.script_failures(r.stdout)
            if r.returncode != 0 or bad:
                print("[craft] 다듬기 실패: " + (" / ".join(bad[:6]) or (r.stderr or r.stdout)[-400:]), file=sys.stderr)
                raise SystemExit("effectcraft 다듬기 실패: " + (" / ".join(bad[:3]) or (r.stderr or r.stdout)[-300:]))
        except SystemExit:
            proj.unlink(missing_ok=True)    # 반쯤 만든 프로젝트를 남기면 다음 실행이 '사람이 고친 파일'로 알고 그대로 쓴다
            raise
    man[mkey] = {"file": str(proj.relative_to(ROOT)), "hash": _sha(proj), "source": src_key, "app": "effectcraft"}
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    return proj


def render(job) -> Path:
    proj = build(job)
    out = job.work / "silent.mp4"
    args = [_cli(), "render", "--project", proj, "--comp", "Main", "--out", out, "--format", "h264", "--audio", "off", "--fps", str(job.fps)]
    if job.draft:
        args += ["--resolution", "half", "--quality", "draft"]
    run(args, cwd=job.work, env=_env(), label="effectcraft render", timeout=1800)
    if not out.exists():
        raise SystemExit("EffectCraft 렌더 출력이 없습니다")
    return out


def snapshot(job, seconds):
    proj = build(job)
    snaps = job.work / "snaps"
    snaps.mkdir(parents=True, exist_ok=True)
    out = []
    for s in seconds:
        p = snaps / f"f{float(s):07.3f}.png"
        run([_cli(), "render-frame", "--project", proj, "--comp", "Main", "--time", str(s), "--out", p], cwd=job.work, env=_env(), label="effectcraft frame", timeout=120)
        out.append(p)
    return out
