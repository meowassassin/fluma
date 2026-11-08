"""Blender 밖(일반 파이썬)에서 사용자 3D 스크립트를 실행하기 전 준비: 검사 · HDRI 미리 받기 · 깨끗한 환경변수.

사용자 스크립트(data/compositions/<id>/src/*.py)는 에이전트가 쓰는 코드다. 그래서
  1) 실행 전 검사: 프로세스 · 네트워크 · ctypes · eval/exec · 비밀 파일 경로를 쓰면 거부 (이유를 알려 줌)
  2) 환경변수에서 키 · 토큰을 빼고 Blender 를 띄움
  3) Blender 안에서는 guard.py 의 감사 훅이 한 번 더 막음 (쓰기는 출력 폴더 · 작업 폴더 · 임시 폴더만)
"""
import ast
import os
import re
import tempfile
import urllib.request
from pathlib import Path

LIB = Path(__file__).resolve().parent
CACHE = LIB.parents[1] / "assets"             # engine/assets/hdri/<이름>_<해상도>.hdr
BANNED_MODULES = {"subprocess", "socket", "_socket", "ctypes", "_ctypes", "urllib", "http", "requests", "httpx", "ftplib", "smtplib",
                  "multiprocessing", "importlib", "pty", "shutil", "webbrowser", "asyncio", "ssl", "pickle", "marshal", "code", "runpy"}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint", "globals", "vars"}
OS_ATTRS = {"system", "popen", "spawnl", "spawnv", "spawnve", "execv", "execve", "execl", "fork", "forkpty", "kill", "putenv", "unsetenv",
            "environ", "remove", "unlink", "rmdir", "removedirs", "rename", "replace", "chmod", "chown", "symlink", "link", "truncate"}   # os · shutil 에 붙을 때만
BANNED_ATTRS = {"__subclasses__", "__globals__", "__builtins__", "__code__", "f_globals", "gi_frame", "__loader__"}   # 어디에 붙어도
SECRET = re.compile(r"(\.env\b|\.shortsforge|\.claude|\.ssh|\.aws|\.gnupg|\.netrc|byok|id_rsa|/etc/shadow)", re.I)
HDRI = re.compile(r"world_hdri\(\s*[\"']([A-Za-z0-9_]+)[\"'](?:[^)]*?res\s*=\s*[\"'](\dk)[\"'])?")
SAFE_ENV = ("FL_CYCLES", "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
            "__GLX_VENDOR_LIBRARY_NAME", "__NV_PRIME_RENDER_OFFLOAD", "VK_ICD_FILENAMES", "LIBGL_ALWAYS_SOFTWARE", "MESA_LOADER_DRIVER_OVERRIDE")


def lint(path: Path) -> list[str]:
    """금지 사항 목록 (비어 있으면 통과). 줄 번호를 붙여 에이전트가 바로 고치게."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return [f"{e.lineno}: 문법 오류 — {e.msg}"]
    bad = []
    for n in ast.walk(tree):
        ln = getattr(n, "lineno", 0)
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in BANNED_MODULES:
                    bad.append(f"{ln}: import {a.name} — 3D 스크립트에서는 쓸 수 없음 (프로세스 · 네트워크 · 파일 삭제 차단)")
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] in BANNED_MODULES:
                bad.append(f"{ln}: from {n.module} import … — 쓸 수 없음")
            if n.module in ("os", "shutil") and any(a.name in OS_ATTRS for a in n.names):
                bad.append(f"{ln}: from os import {', '.join(a.name for a in n.names)} — 쓸 수 없음")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in BANNED_CALLS:
            bad.append(f"{ln}: {n.func.id}() — 쓸 수 없음")
        elif isinstance(n, ast.Attribute) and (n.attr in BANNED_ATTRS or
                                               (n.attr in OS_ATTRS and isinstance(n.value, ast.Name) and n.value.id in ("os", "shutil", "posix", "nt", "sys"))):
            bad.append(f"{ln}: {getattr(n.value, 'id', '')}.{n.attr} — 쓸 수 없음 (파일 삭제 · 프로세스 · 환경변수)")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and SECRET.search(n.value):
            bad.append(f"{ln}: 비밀 파일 경로 \"{n.value[:40]}\" — 읽을 수 없음")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body):
        bad.append("1: def build(ctx): 가 없음 — 장면을 짓는 함수가 필요")
    return bad


def prefetch(path: Path, log=print):
    """스크립트에 적힌 world_hdri("이름") 을 Poly Haven(CC0) 에서 미리 받는다."""
    for name, res in set(HDRI.findall(path.read_text(encoding="utf-8"))):
        res = res or "1k"
        dst = CACHE / "hdri" / f"{name}_{res}.hdr"
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        log(f"[3D] HDRI 받는 중: {name} ({res}, Poly Haven CC0)")
        tmp = dst.with_suffix(".part")
        try:
            urllib.request.urlretrieve(f"https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/{res}/{name}_{res}.hdr", tmp)
            tmp.rename(dst)
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            raise SystemExit(f"HDRI '{name}' 를 받지 못함 ({e}) — 이름을 polyhaven.com/hdris 에서 확인하세요")


def env(extra: dict) -> dict:
    """키 · 토큰이 없는 환경변수 (Blender 와 사용자 스크립트가 보게 될 것)."""
    e = {k: v for k, v in os.environ.items() if k in SAFE_ENV}
    e.setdefault("TMPDIR", tempfile.gettempdir())
    e["PYTHONNOUSERSITE"] = "1"
    e["PYTHONDONTWRITEBYTECODE"] = "1"   # 스크립트 폴더에 __pycache__ 를 남기지 않게
    e["FL_LIB"] = str(LIB)
    e["FL_CACHE"] = str(CACHE)
    return {**e, **{k: str(v) for k, v in extra.items()}}
