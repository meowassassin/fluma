"""Blender 안에서 사용자 3D 스크립트를 불러 실행 (감사 훅으로 위험한 동작 차단).

  ctx = guard.context(...)       # 스크립트가 받는 값
  mod = guard.load(path, writable=[출력 폴더, 작업 폴더])   # 훅을 건 뒤 불러옴 → mod.build(ctx)
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import types

SECRET = re.compile(r"(\.env($|\.)|\.shortsforge|\.claude|\.ssh|\.aws|\.gnupg|\.netrc|byok|id_rsa)", re.I)
BLOCK = {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty", "os.kill", "pty.spawn",
         "socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto", "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function",
         "os.putenv", "os.unsetenv", "webbrowser.open"}
WRITE_EV = {"os.remove", "os.rmdir", "os.rename", "shutil.rmtree", "shutil.move", "os.chmod", "os.chown", "os.symlink", "os.link", "os.truncate"}
_ON = [False]
# 신뢰 구간: Blender 내장 가져오기(glTF 등)가 내부에서 환경 변수를 만진다. 그 동안만 환경 변수 설정을 허용한다
# (프로세스 실행 · 네트워크는 여전히 막혀 있어 환경 변수만으로는 할 수 있는 일이 없다)
TRUSTABLE = {"os.putenv", "os.unsetenv"}
BL_ROOT = os.path.realpath(os.path.dirname(sys.executable if "blender" in os.path.basename(sys.executable).lower() else os.path.dirname(os.__file__)))
try:
    import bpy  # noqa: E402
    BL_ROOT = os.path.realpath(os.path.dirname(bpy.app.binary_path))
except Exception:  # noqa: BLE001  (Blender 밖에서 불렀을 때)
    pass
_TRUST = [0]


class trusted:
    def __enter__(self):
        _TRUST[0] += 1

    def __exit__(self, *a):
        _TRUST[0] -= 1


def _inside(p, roots):
    try:
        rp = os.path.realpath(os.fsdecode(p))
    except (TypeError, ValueError):
        return False
    return any(rp == r or rp.startswith(r + os.sep) for r in roots)


def install(writable):
    roots = [os.path.realpath(r) for r in [*writable, tempfile.gettempdir()] if r]

    def hook(ev, args):
        if not _ON[0]:
            return
        if _TRUST[0] and ev in TRUSTABLE:
            return
        if _TRUST[0] and ev == "ctypes.dlopen":   # Blender 설치 폴더 안의 라이브러리(glTF Draco 압축 해제기 등)만
            lib = args[0] if args else None
            if lib is None or _inside(lib, [BL_ROOT]):
                return
        if ev in BLOCK or ev.startswith("os.exec") or ev.startswith("os.spawn"):
            raise PermissionError(f"[3D 스크립트] 차단: {ev} — 프로세스 · 네트워크 · 네이티브 호출은 쓸 수 없습니다")
        if ev == "open":
            path, mode = args[0], args[1] if len(args) > 1 else "r"
            if isinstance(path, int):
                return
            if SECRET.search(os.fsdecode(path)):
                raise PermissionError(f"[3D 스크립트] 차단: 비밀 파일 {path}")
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            wants_write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            if wants_write and not _inside(path, roots):
                raise PermissionError(f"[3D 스크립트] 차단: 쓰기는 출력 · 작업 폴더만 ({path})")
        elif ev in WRITE_EV:
            for p in args[:2]:
                if isinstance(p, (str, bytes, os.PathLike)) and not _inside(p, roots):
                    raise PermissionError(f"[3D 스크립트] 차단: {ev} {p}")

    sys.addaudithook(hook)


def context(**kw):
    return types.SimpleNamespace(**kw)


def load(path, writable):
    """훅을 켜고 스크립트를 모듈로 불러온다. 같은 폴더의 다른 .py(공용 부품)도 import 가능."""
    if not _ON[0] and not getattr(sys, "_fl_hook", False):
        install(writable)
        sys._fl_hook = True
    lib = os.environ.get("FL_LIB")
    for d in (lib, os.path.dirname(os.path.abspath(path))):
        if d and d not in sys.path:
            sys.path.insert(0, d)
    import fluma3d  # noqa: F401  (훅 전에 불러 둠: 내부 import 가 막히지 않게)
    spec = importlib.util.spec_from_file_location(f"fl_user_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    _ON[0] = True
    try:
        spec.loader.exec_module(mod)
    finally:
        _ON[0] = False
    if not hasattr(mod, "build"):
        raise SystemExit(f"{path}: def build(ctx): 가 없습니다")
    return mod


def call(fn, *a):
    """사용자 코드 실행 구간만 훅을 켠다 (Blender 의 렌더 · 내부 동작은 그대로)."""
    _ON[0] = True
    try:
        return fn(*a)
    finally:
        _ON[0] = False


def ctx_from_env():
    return json.loads(os.environ["FL_CTX"]) if os.environ.get("FL_CTX") else {}
