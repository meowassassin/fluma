"""프로세스 다루기 — 부모와 끊긴 실행 · 살아 있나 · 자식까지 끄기 · 기다리지 않는 잠금 (Linux · macOS · Windows).

produce.py 의 뒤에서 돌리기와 MCP 작업 대기열(engine/mcp/fluma_jobs.py)이 같이 쓴다.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())


def spawn_detached(cmd: list[str], log: Path, env: dict, cwd: Path | None = None) -> int:
    """부모와 완전히 끊긴 프로세스로 띄우고 pid 를 돌려준다(기록은 log 로).
    2026-11-17: 새 세션(start_new_session)으로만 떼면 여전히 부모의 자식이라, 에이전트 Bash 시간 제한이 자식까지 줄줄이 끄면서
    렌더 도중 결과 없이 죽었다. POSIX 는 두 번 갈라(double fork) 고아로 만들어 init 아래로 보낸다(새 세션의 리더 → 프로세스 그룹 id = pid).
    Windows 는 분리 실행 플래그"""
    cwd = cwd or ROOT
    if os.name != "posix":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        with log.open("w") as lf:
            return subprocess.Popen(cmd, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, creationflags=flags).pid
    r, w = os.pipe()
    mid = os.fork()
    if mid == 0:                                    # 중간 프로세스: 새 세션을 만들고 진짜 작업을 하나 더 갈라 낸 뒤 바로 끝난다
        try:
            os.close(r)
            os.setsid()
            pid = os.fork()
            if pid == 0:
                os.close(w)
                fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                nul = os.open(os.devnull, os.O_RDONLY)
                os.dup2(nul, 0); os.dup2(fd, 1); os.dup2(fd, 2)
                os.chdir(str(cwd))
                os.execve(cmd[0], cmd, env)
            os.write(w, str(pid).encode())
        finally:
            os._exit(0)
    os.close(w)
    got = os.read(r, 32)
    os.close(r)
    os.waitpid(mid, 0)
    return int(got or b"0")


def alive(pid) -> bool:
    """그 pid 가 아직 도나(좀비는 죽은 것으로)"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name != "posix":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
    except PermissionError:                         # 남의 프로세스 — 살아 있음
        return True
    except OSError:
        return False
    try:                                            # 좀비(끝났지만 거두지 않음)는 /proc 에 Z 로 남는다
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(") ")[-1][:1] != "Z"
    except OSError:
        return True


def kill_tree(pid: int, grace: float = 3.0) -> None:
    """그 프로세스와 자식 전부 끄기. POSIX 는 프로세스 그룹(spawn_detached 로 띄운 것은 그룹 리더), Windows 는 taskkill /T"""
    if os.name != "posix":
        subprocess.run(["taskkill", "/pid", str(pid), "/T", "/F"], capture_output=True)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                return
        t0 = time.time()
        while time.time() - t0 < grace:
            if not alive(pid):
                return
            time.sleep(0.2)


def try_lock(path: Path):
    """기다리지 않는 잠금 — 잡으면 열린 파일(쥐고 있는 동안 잠김, 닫거나 프로세스가 죽으면 풀림), 못 잡으면 None"""
    f = open(path, "a+")
    try:
        if os.name != "posix":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except OSError:
        f.close()
        return None


def tree_rss_mb(pid: int) -> float:
    """그 프로세스와 자식 전부의 실제 메모리(RSS) 합 — psutil 이 없거나 이미 끝났으면 0"""
    try:
        import psutil
        p = psutil.Process(pid)
        procs = [p, *p.children(recursive=True)]
    except Exception:  # noqa: BLE001
        return 0.0
    tot = 0
    for q in procs:
        try:
            tot += q.memory_info().rss
        except Exception:  # noqa: BLE001 — 그사이 끝남
            pass
    return tot / (1 << 20)


class PeakMem:
    """with PeakMem(pid) as pm: … → pm.peak_mb (0.5초마다 재서 가장 큰 값)"""

    def __init__(self, pid: int, every: float = 0.5):
        import threading
        self.pid, self.every, self.peak_mb = pid, every, 0.0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak_mb = max(self.peak_mb, tree_rss_mb(self.pid))
            self._stop.wait(self.every)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._t.join(timeout=2)
