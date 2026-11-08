"""Craft 앱 기능 사용 기록 — 이 패키지 안에서 부르는 <앱>-cli 호출을 지켜보며, 인자 · 스크립트 파일 · 표준 입력에 나오는
명령 · 효과 · 프리셋 id(기능 목록 .claude/skills/crafts/catalog 와 맞는 것)를 모은다. 단계 코드는 고치지 않는다.
렌더가 끝나면 data/compositions/<id>/craft/usage.json 에 합쳐 쓴다 → engine/craft/craft_catalog.py coverage · craft_variety.py 가 읽는다.
"""
from __future__ import annotations

import atexit
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAT = ROOT / ".claude" / "skills" / "crafts" / "catalog"
SID: str | None = None                 # materials.build 가 정한다
ALL: dict[str, set] = {}               # 이 렌더 전체
CUR: dict[str, set] | None = None      # 지금 만드는 재료 하나(begin ~ take)
_IDS: dict[str, set] = {}
_TOK = re.compile(r"[A-Za-z][\w.\-]{2,80}")
_orig_run, _orig_popen = subprocess.run, subprocess.Popen


def _ids(app: str) -> set:
    if app not in _IDS:
        f = CAT / f"{app}.jsonl"
        s = set()
        if f.exists():
            for ln in f.read_text("utf-8").splitlines():
                try:
                    i = json.loads(ln)["id"]
                except (ValueError, KeyError):
                    continue
                if len(i) >= 3:
                    s.add(i)
        _IDS[app] = s
    return _IDS[app]


def _labels(app: str) -> dict:
    """효과 이름 → id — 스크립트에는 "Add Grain" 처럼 이름으로 적힌다"""
    f = CAT / f"{app}.jsonl"
    out = {}
    if f.exists():
        for ln in f.read_text("utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("kind") == "effect" and r.get("label"):
                out[r["label"]] = r["id"]
    return out


def _app_of(args) -> str | None:
    if not isinstance(args, (list, tuple)) or not args:
        return None
    n = Path(str(args[0])).name
    return n[:-4] if n.endswith("-cli") else None


def _texts(args, kw) -> list[str]:
    out = [str(a) for a in args]
    for a in args[1:]:
        p = Path(str(a))
        if p.suffix.lower() in (".jsx", ".js", ".jsonl", ".json", ".txt", ".cmds", ".script", ".dcs") and len(str(a)) < 1000:
            try:
                if p.is_file() and p.stat().st_size < 8 * 1024 * 1024:
                    out.append(p.read_text("utf-8", errors="ignore"))
            except OSError:
                pass
    inp = kw.get("input")
    if isinstance(inp, (str, bytes)):
        out.append(inp if isinstance(inp, str) else inp.decode("utf-8", "ignore"))
    return out


def note(args, kw) -> None:
    try:
        app = _app_of(args)
        if not app:
            return
        ids = _ids(app)
        if not ids:
            return
        found = set()
        for t in _texts(args, kw):
            found |= set(_TOK.findall(t)) & ids
            found |= {i for lb, i in _labels(app).items() if f'"{lb}"' in t or f'\\"{lb}\\"' in t}
        for d in (ALL, CUR) if CUR is not None else (ALL,):
            d.setdefault(app, set()).update(found)
    except Exception:  # noqa: BLE001  기록은 렌더를 막지 않는다
        pass


def _run(*a, **kw):
    note(a[0] if a else kw.get("args"), kw)
    return _orig_run(*a, **kw)


class _Popen(_orig_popen):  # type: ignore[misc,valid-type]
    def __init__(self, *a, **kw):
        note(a[0] if a else kw.get("args"), kw)
        super().__init__(*a, **kw)


def install() -> None:
    if subprocess.run is not _run:
        subprocess.run = _run
        subprocess.Popen = _Popen


def record(app: str, ids) -> None:
    """앱 밖에서 쓴 기능을 직접 적는다 — Blender 처럼 <앱>-cli 호출로 잡히지 않는 것"""
    ALL.setdefault(app, set()).update(ids)
    if CUR is not None:
        CUR.setdefault(app, set()).update(ids)


def depth(sid: str) -> str:
    """이 영상이 앱을 얼마나 썼나 — 한 줄(앱별 기능 수)"""
    f = ROOT / "data" / "compositions" / sid / "craft" / "usage.json"
    try:
        fs = json.loads(f.read_text("utf-8")).get("features") or []
    except (OSError, ValueError):
        return "기록 없음"
    c: dict[str, int] = {}
    for x in fs:
        c[x["app"]] = c.get(x["app"], 0) + 1
    return f"{len(fs)}개 · " + " · ".join(f"{a} {n}" for a, n in sorted(c.items(), key=lambda v: -v[1]))


def begin() -> None:
    global CUR
    CUR = {}


def take() -> list[dict]:
    global CUR
    cur, CUR = CUR or {}, None
    return [{"app": a, "id": i} for a, s in sorted(cur.items()) for i in sorted(s)]


def flush() -> None:
    if not SID or not ALL:
        return
    f = ROOT / "data" / "compositions" / SID / "craft" / "usage.json"
    try:
        old = json.loads(f.read_text("utf-8")) if f.exists() else {}
        have = {(x["app"], x["id"]) for x in old.get("features") or []}
        have |= {(a, i) for a, s in ALL.items() for i in s}
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"id": SID, "features": [{"app": a, "id": i} for a, i in sorted(have)]}, ensure_ascii=False, indent=1), "utf-8")
    except (OSError, ValueError):
        pass


atexit.register(flush)
