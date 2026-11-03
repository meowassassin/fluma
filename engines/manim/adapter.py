"""Manim 엔진 어댑터: job.json → 컨테이너(podman, 버전 고정 이미지) 안에서 manim render → 무음 MP4.

마운트: 작업 폴더(/work, 쓰기), 템플릿(/tpl, 읽기), public/fonts(/usr/share/fonts/sf, 읽기 — Pretendard 를 Pango 가 찾도록).
podman 이 없으면 docker 를 쓴다.
"""
import json
import shutil
import subprocess
from pathlib import Path

from platform_util import container_mount  # noqa: E402
from engines import PUBLIC, run, snapshot_via_draft, write_job  # noqa: E402

HERE = Path(__file__).resolve().parent
META = json.loads((HERE / "engine.json").read_text(encoding="utf-8"))
RUNTIME = shutil.which("podman") or shutil.which("docker")


def available():
    if not RUNTIME:
        return False
    return subprocess.run([RUNTIME, "image", "exists" if RUNTIME.endswith("podman") else "inspect", META["image"]], capture_output=True).returncode == 0


def build(job) -> Path:
    return write_job(job)


def render(job) -> Path:
    build(job)
    tpl = HERE / "templates" / job.template
    q = ["-ql"] if job.draft else ["-qh"]
    cmd = [RUNTIME, "run", "--rm"]
    MRW, MRO = container_mount(), container_mount(ro=True)   # :Z 는 SELinux 리눅스에서만
    if RUNTIME.endswith("podman"):
        cmd += ["--userns=keep-id"]
    cmd += ["-v", f"{job.work}:/work{MRW}", "-v", f"{tpl}:/tpl{MRO}", "-v", f"{PUBLIC / 'fonts'}:/usr/share/fonts/sf{MRO}",
            "-w", "/work", "-e", "SF_JOB=/work/job.json", META["image"],
            "manim", "render", *q, "--fps", str(job.fps), "-r", f"{job.width},{job.height}", "--format", "mp4",
            "--media_dir", "/work/media", "--disable_caching", "-o", "silent", "/tpl/scene.py", "Main"]
    run(cmd, cwd=job.work, label="manim")
    found = sorted((job.work / "media").rglob("silent.mp4"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise SystemExit("manim 출력 없음")
    out = job.work / "silent.mp4"
    shutil.copy2(found[-1], out)
    return out


def snapshot(job, seconds):
    return snapshot_via_draft(job, seconds, render)
