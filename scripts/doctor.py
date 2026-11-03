#!/usr/bin/env python3
"""Fluma 준비 점검 · 설치 — 처음 쓰는 사람이 10분 안에 첫 영상까지 가게.

  python3 scripts/doctor.py              # 무엇이 있고 없는지만
  python3 scripts/doctor.py --sizes      # 무엇이 용량을 차지하는지 · 지워도 되는지
  python3 scripts/doctor.py --fix        # 가벼운 시작(lite)에 필요한 것 설치: .venv · 파이썬 패키지 · Chromium · npm 패키지
  python3 scripts/doctor.py --fix --profile analysis   # + 레퍼런스 분석(받아쓰기 · OCR · 화면 분류)
  python3 scripts/doctor.py --fix --profile full       # + 누끼 · 생성 API · 유튜브 업로드

lite = 콘티 · Edge 음성(무료) · HyperFrames 화면 · 렌더 · 검사. 무거운 모델(Blender · SAM · 생성 모델)은 설정 화면에서 필요할 때 설치.
시스템 프로그램(Node 20+ · ffmpeg)은 설치하지 않고 명령만 알려 준다(관리자 권한이 필요할 수 있어서).
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
REQ = {"lite": "requirements.txt", "analysis": "requirements-analysis.txt", "full": "requirements-full.txt"}


def vpy() -> Path:
    return VENV / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def run(cmd: list[str], cwd: Path | None = None) -> bool:
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd).returncode == 0


def version(cmd: list[str]) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[0]
    except Exception:  # noqa: BLE001
        return None


def checks() -> list[tuple[str, bool, str]]:
    out = []
    out.append(("Python 3.10+", sys.version_info >= (3, 10), platform.python_version()))
    nv = version(["node", "-v"])
    out.append(("Node.js 20+", bool(nv) and int(nv.lstrip("v").split(".")[0]) >= 20, nv or "없음 — https://nodejs.org (20 이상)"))
    fv = version(["ffmpeg", "-version"])
    hint = {"Darwin": "brew install ffmpeg", "Windows": "winget install ffmpeg"}.get(platform.system(), "sudo apt install ffmpeg · sudo dnf install ffmpeg")
    out.append(("ffmpeg", bool(fv), fv.split(" Copyright")[0] if fv else f"없음 — {hint}"))
    out.append((".venv 파이썬", vpy().exists(), str(vpy()) if vpy().exists() else "없음 — --fix"))
    ok_pkgs = vpy().exists() and subprocess.run([str(vpy()), "-c", "import jsonschema, playwright, edge_tts, PIL, numpy"], capture_output=True).returncode == 0
    out.append(("파이썬 패키지(lite)", ok_pkgs, "jsonschema · playwright · edge-tts · pillow · numpy"))
    ok_an = vpy().exists() and subprocess.run([str(vpy()), "-c", "import faster_whisper, rapidocr, onnxruntime, tokenizers, cv2"], capture_output=True).returncode == 0
    out.append(("레퍼런스 분석 패키지(선택)", ok_an, "faster-whisper · rapidocr · onnxruntime · opencv — --profile analysis"))
    ok_chr = vpy().exists() and subprocess.run([str(vpy()), "-c", "from playwright.sync_api import sync_playwright as s\nwith s() as p: p.chromium.launch().close()"], capture_output=True, timeout=120).returncode == 0
    out.append(("Chromium(렌더 · 미리보기)", ok_chr, "playwright install chromium"))
    out.append(("웹 앱 npm 패키지", (ROOT / "web" / "node_modules").exists(), "web/ 에서 npm install"))
    out.append(("HyperFrames 엔진", (ROOT / "engines" / "hyperframes" / "node_modules" / "hyperframes").exists(), "engines/hyperframes/ 에서 npm install"))
    return out


def fix(profile: str) -> bool:
    ok = True
    if not vpy().exists():
        print("· 가상환경 만들기 (.venv)")
        venv.EnvBuilder(with_pip=True).create(VENV)
    uv = shutil.which("uv")
    req = str(ROOT / "scripts" / REQ[profile])
    print(f"· 파이썬 패키지 ({profile})")
    ok &= run([uv, "pip", "install", "--python", str(vpy()), "-r", req] if uv else [str(vpy()), "-m", "pip", "install", "-r", req])
    print("· Chromium")
    ok &= run([str(vpy()), "-m", "playwright", "install", "chromium"])
    npm = shutil.which("npm")
    if not npm:
        print("  ✗ npm 이 없습니다 — Node.js 20+ 를 먼저 설치하세요"); return False
    for d in (ROOT / "web", ROOT / "engines" / "hyperframes"):
        print(f"· npm install ({d.relative_to(ROOT)})")
        ok &= run([npm, "install", "--no-audit", "--no-fund"], cwd=d)
    return ok


def du(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    tot = 0
    for f in p.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink():
                tot += f.stat().st_size
        except OSError:
            pass
    return tot


# 용량 큰 것: (경로, 무엇, 지워도 되나 · 다시 얻는 법)
HEAVY = [
    (".venv", "파이썬 패키지(필수)", "지우면 doctor.py --fix 로 다시"),
    ("voices/melotts/.venv", "MeloTTS 음성 엔진(선택)", "안 쓰면 지워도 됨 — 설정 → 미디어 → 음성에서 다시 설치"),
    ("voices/chatterbox/.venv", "Chatterbox 음성 엔진(선택)", "안 쓰면 지워도 됨 — 다시 설치 가능"),
    ("voices/cosyvoice/.venv", "CosyVoice 음성 엔진(선택)", "안 쓰면 지워도 됨"),
    ("voices/xtts/.venv", "XTTS 음성 엔진(선택 · 비상업)", "안 쓰면 지워도 됨"),
    ("voices/supertonic/.venv", "Supertonic 음성 엔진(선택)", "안 쓰면 지워도 됨"),
    ("engines/blender/dist", "Blender(선택 · 3D 요소)", "안 쓰면 지워도 됨 — 설정 → 미디어 → 렌더 엔진에서 다시 설치"),
    ("tools/vision", "옛 화풍 분류기(torch) — 이제 안 씀", "지워도 됨(scripts/vision_tags.py 가 대신)"),
    ("web/node_modules", "웹 앱 패키지(필수)", "지우면 npm install"),
    ("engines/hyperframes/node_modules", "HyperFrames(필수)", "지우면 npm install"),
    ("library3d", "3D 요소 라이브러리(선택)", "재사용 3D 개체"),
    ("workspace", "작업물 · 대화 · 렌더 캐시", "workspace/tmp · workspace/render/_jobs 는 지워도 됨"),
    ("public/trends", "트렌드 썸네일 · 분해도 · 채널 카드", "다시 분석하면 생김(채널 카드는 프리셋 재료)"),
    ("out", "렌더 결과", "필요 없는 영상만"),
    ("~/.cache/ms-playwright", "Chromium(렌더 · 미리보기, 필수) — 옛 버전이 겹쳐 쌓임", "playwright install 로 최신만 두고 옛 chromium-* · firefox-* 는 지워도 됨"),
    ("~/.cache/huggingface", "모델 캐시(받아쓰기 · 화면 분류 · 음성 엔진 모델)", "다른 프로그램 모델도 섞여 있음 — 필요할 때 다시 받음"),
]


def sizes():
    rows = []
    for rel, what, note in HEAVY:
        p = Path(rel).expanduser() if rel.startswith("~") else ROOT / rel
        b = du(p)
        if b > 20 * 2 ** 20:
            rows.append((b, rel, what, note))
    rows.sort(reverse=True)
    print("Fluma 용량 (20MB 이상)")
    for b, rel, what, note in rows:
        print(f"  {b / 2 ** 30:5.2f} GB  {rel:<36} {what} — {note}")
    print(f"  합계 {sum(r[0] for r in rows) / 2 ** 30:.2f} GB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", action="store_true", help="무엇이 용량을 차지하는지 · 지워도 되는지")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--profile", choices=list(REQ), default="lite")
    a = ap.parse_args()
    if a.sizes:
        sizes(); return 0
    if a.fix and not fix(a.profile):
        print("\n일부 설치가 실패했습니다 — 위 출력을 확인하세요")
    print("\nFluma 준비 상태")
    rows = checks()
    for name, ok, note in rows:
        print(f"  {'✓' if ok else '✗'} {name:<26} {note}")
    must = [r for r in rows if not r[0].endswith("(선택)")]
    if all(ok for _, ok, _ in must):
        print("\n준비 완료 — 시작:  npm --prefix web run dev   →  http://localhost:4311")
        return 0
    print("\n빠진 것이 있습니다 — python3 scripts/doctor.py --fix  (Node · ffmpeg 는 위 안내대로 직접 설치)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
