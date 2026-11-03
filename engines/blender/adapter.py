"""Blender 엔진 어댑터: job.json → Blender(포터블 5.2 LTS, 백그라운드) 가 장면마다 3D 를 짓고 EEVEE 로 PNG 프레임 → ffmpeg → 무음 MP4.
초안은 12fps 로 렌더하고 30fps 로 늘린다(빠르게). 정지 화면(snapshot)은 그 시각만 바로 렌더."""
import shutil
import subprocess
from pathlib import Path

from engines import run, write_job  # noqa: E402

HERE = Path(__file__).resolve().parent
def _find_bin():
    """dist/ 안의 공식 빌드: Linux blender/blender · macOS Blender.app/Contents/MacOS/Blender · Windows blender/blender.exe"""
    d = HERE / "dist"
    for p in (d / "blender" / "blender", d / "blender" / "blender.exe", d / "Blender.app" / "Contents" / "MacOS" / "Blender"):
        if p.exists():
            return p
    return d / "blender" / "blender"


BIN = _find_bin()


def available():
    return BIN.exists()


def build(job) -> Path:
    return write_job(job)


def _custom_scripts(job):
    """장면의 "blender" 스크립트: compositions/<id>/blender/ 안만 허용, 실행 전 검사 + HDRI 미리 받기"""
    import sys
    sys.path.insert(0, str(HERE / "lib"))
    import host
    root = HERE.parents[1]
    base = (root / "compositions" / job.sb["id"] / "blender").resolve()
    found = []
    for s in job.sb["scenes"]:
        if not s.get("blender"):
            continue
        p = (root / s["blender"]).resolve()
        if base not in p.parents or not p.exists():
            raise SystemExit(f"장면 3D 스크립트는 compositions/{job.sb['id']}/blender/ 안에 있어야 합니다: {s['blender']}")
        bad = [m for f in sorted(p.parent.glob("*.py")) for m in host.lint(f) if f == p or "def build" not in m]
        if bad:
            raise SystemExit(f"{s['blender']} 검사에서 막힘:\n  " + "\n  ".join(bad))
        host.prefetch(p)
        found.append(p)
    return found


def _blender(job, extra_env: dict):
    jp = build(job)
    env = {"SF_JOB": str(jp), "SF_OUT": str(job.work / "frames"), **extra_env}
    import os
    if _custom_scripts(job):   # 에이전트가 짠 코드가 돈다 → 키 · 토큰 없는 환경으로
        import host
        base_env = host.env({"FL_ROOT": HERE.parents[1]})
    else:
        base_env = {**os.environ, "FL_LIB": str(HERE / "lib"), "FL_ROOT": str(HERE.parents[1])}
    # 진행률: Blender 는 끝날 때까지 말이 없어 화면이 멈춘 것처럼 보임 → 프레임 폴더를 세어 15초마다 알림
    import threading, time
    out_dir = Path(env["SF_OUT"]); stop = threading.Event()
    total = sum(round(float(s["sec"]) * int(env.get("SF_RFPS", job.fps))) for s in job.scenes) if not env.get("SF_STILLS") else 0
    t0 = time.time()
    def tick():
        while not stop.wait(15):
            n = len(list(out_dir.glob("f*.png")))
            if total and n:
                left = (time.time() - t0) / n * (total - n)
                print(f"[blender] 프레임 {n}/{total} · 남은 시간 약 {left / 60:.0f}분", flush=True)
    th = threading.Thread(target=tick, daemon=True); th.start()
    try:
        run([str(BIN), "-b", "--factory-startup", "-noaudio", "--python-exit-code", "1", "-P", str(HERE / "templates" / job.template / "scene.py")],
            cwd=job.work, env={**base_env, **env}, label="blender", timeout=4 * 3600)
    finally:
        stop.set()


ELEMENT_ONLY = "Blender 는 개체 요소 전용입니다(장면 전체 3D 없음). scripts/element.py blender <id> <이름> 으로 요소를 만들어 scene.js 에 K.seq 로 얹으세요."


def render(job) -> Path:
    raise SystemExit(ELEMENT_ONLY)


def snapshot(job, seconds):
    raise SystemExit(ELEMENT_ONLY)
