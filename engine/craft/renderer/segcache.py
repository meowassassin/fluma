"""EffectCraft 렌더를 장면 구간으로 나눠 캐시한다 — 바뀐 구간만 다시 그린다.

2026-11-18 실측(36초 · 7장면): 아무것도 안 바꾼 재렌더도 매번 52초(전체를 처음부터). 9초 구간만 그리면 14초로 길이에 비례하고,
여러 구간을 동시에 그려도 빨라지지 않는다(렌더가 이미 코어를 다 쓴다) — 그래서 '안 바뀐 구간은 다시 그리지 않기'가 유일한 큰 이득이다.

구간: 메인 컴프 안 장면 컴프 레이어의 시작점(프레임에 맞춤)으로 나눈다.
열쇠: 그 구간에 보이는 메인 레이어 전부의 내용(하위 컴프 · 단색 · 푸티지 파일 해시까지 따라감)을 정규화해 해시.
  - 항목 · 레이어 id 는 빌드마다 밀리므로 빼고, 레이어 참조는 순번으로 바꾼다.
  - 시간은 구간 시작 기준 상대값 — 앞 장면 길이가 바뀌어 밀려도 같은 장면은 다시 그리지 않는다.
  - 키프레임 · 식이 없는 레이어(고정 제목 등)는 시간 칸을 빼고 본다(어느 시각이든 같은 그림).
이어 붙인 결과의 프레임 수가 전체와 다르면 쓰지 않고 전체 렌더로 돌아간다(호출하는 쪽).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

_SKIP = {"id", "uid", "parent", "label", "comment"}


_HASHES: dict | None = None
_HASH_F = Path(__file__).resolve().parents[3] / "data" / "workspace" / "cache" / "filehash.json"


def _content_sha(f: Path, st) -> str:
    """파일 내용 해시 — (경로 · 크기 · 수정 시각)별로 기억해 같은 파일을 두 번 읽지 않는다.
    2026-11-24: 열쇠가 크기 · 수정 시각뿐이라 재료를 같은 내용으로 다시 쓰기만 해도 모든 구간을 다시 렌더했다(반복 실행 렌더 76~125초)"""
    global _HASHES
    if _HASHES is None:
        try:
            _HASHES = json.loads(_HASH_F.read_text("utf-8"))
        except (OSError, ValueError):
            _HASHES = {}
    k = f"{f}|{st.st_size}|{st.st_mtime_ns}"
    if k not in _HASHES:
        h = hashlib.sha1()
        with open(f, "rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        _HASHES[k] = h.hexdigest()
        if not _HASHES.get("__dirty__"):
            import atexit
            atexit.register(_save_hashes)
        _HASHES["__dirty__"] = 1
    return _HASHES[k]


def _save_hashes():
    global _HASHES
    if not _HASHES:
        return
    _HASHES.pop("__dirty__", None)
    if len(_HASHES) > 20000:
        _HASHES = dict(list(_HASHES.items())[-10000:])
    try:
        _HASH_F.parent.mkdir(parents=True, exist_ok=True)
        tmp = _HASH_F.with_suffix(".tmp"); tmp.write_text(json.dumps(_HASHES), "utf-8"); tmp.replace(_HASH_F)
    except OSError:
        pass


def _file_sha(p: str, memo: dict) -> str:
    if p not in memo:
        f = Path(p)
        if not f.exists():
            memo[p] = "missing"
        else:
            st = f.stat()
            memo[p] = hashlib.sha1(f"{p}|{_content_sha(f, st) if st.st_size < (256 << 20) else st.st_mtime_ns}".encode()).hexdigest()
    return memo[p]


def _norm(o, items: dict, memo: dict, files: dict, layer_ix: dict | None = None):
    """id 를 빼고 하위 항목 참조를 그 항목의 정규화 해시로 바꾼 사본"""
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in _SKIP:
                if k == "parent" and v is not None and layer_ix is not None:
                    out["parent"] = layer_ix.get(v, "?")
                continue
            if k == "item" and isinstance(v, int):
                out["item"] = _item_hash(v, items, memo, files)
            elif k == "track_matte" and isinstance(v, int) and layer_ix is not None:
                out[k] = layer_ix.get(v, "?")
            elif k == "path" and isinstance(v, str):
                out[k] = _file_sha(v, files)
            else:
                out[k] = _norm(v, items, memo, files, layer_ix)
        return out
    if isinstance(o, list):
        return [_norm(x, items, memo, files, layer_ix) for x in o]
    return o


def _layers(kind: dict, items: dict, memo: dict, files: dict) -> list:
    ls = kind.get("layers") or []
    ix = {l.get("id"): n for n, l in enumerate(ls)}
    return [_norm(l, items, memo, files, ix) for l in ls]


def _item_hash(iid: int, items: dict, memo: dict, files: dict) -> str:
    if iid in memo:
        return memo[iid]
    memo[iid] = "cycle"
    it = items.get(str(iid)) or {}
    kind = dict(it.get("kind") or {})
    if kind.get("type") == "Comp":
        body = {**_norm({k: v for k, v in kind.items() if k != "layers"}, items, memo, files), "layers": _layers(kind, items, memo, files)}
    else:
        body = _norm(kind, items, memo, files)
    memo[iid] = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return memo[iid]


def _animated(layer: dict) -> bool:
    s = json.dumps(layer.get("props") or {})
    return '"t":' in s or '"expression"' in s


def plan(proj: Path, fps: int, settings: dict) -> tuple[list[dict], int] | None:
    """구간 목록([{f0, f1, key}]) · 전체 프레임 수 — 나눌 수 없으면 None"""
    d = json.loads(proj.read_text("utf-8"))
    items = d.get("items") or {}
    main = next((i for i in items.values() if i.get("name") == "Main" and (i.get("kind") or {}).get("type") == "Comp"), None)
    if not main:
        return None
    k = main["kind"]
    fr = k.get("frame_rate") or {}
    if fr and round(fr.get("num", fps) / max(1, fr.get("den", 1))) != fps:
        return None
    layers = k.get("layers") or []
    scene_starts = sorted({int(l.get("in_point") or 0) for l in layers if (l.get("source") or {}).get("type") == "Comp"})
    dur = int(k.get("duration") or 0)
    # 틱/초: 프로젝트가 쓰는 시간 단위 — 길이(틱)를 프레임 수로 바꿀 때 필요. 30fps 한 프레임의 틱이 정수가 되는 단위다(실측 254016000000/초)
    tps = 254016000000
    total = round(dur / tps * fps)
    if total <= 0 or len(scene_starts) < 2:
        return None
    cuts = sorted({0, total, *[round(s / tps * fps) for s in scene_starts]})
    cuts = [c for c in cuts if 0 <= c <= total]
    memo, files = {}, {}
    ix = {l.get("id"): n for n, l in enumerate(layers)}
    segs = []
    for f0, f1 in zip(cuts, cuts[1:]):
        if f1 <= f0:
            continue
        t0, t1 = f0 / fps * tps, f1 / fps * tps
        parts = []
        for l in layers:
            if int(l.get("in_point") or 0) < t1 and int(l.get("out_point") or dur) > t0:
                n = _norm(l, items, memo, files, ix)
                if _animated(l) or (l.get("source") or {}).get("type") in ("Comp", "Footage"):
                    for key in ("start_time", "in_point", "out_point"):
                        if key in n and n[key] is not None:
                            n[key] = round((int(n[key]) - t0) / tps * fps, 3)   # 구간 시작 기준 프레임
                else:
                    for key in ("start_time", "in_point", "out_point"):
                        n.pop(key, None)
                parts.append(n)
        body = {"v": 1, "fps": fps, "frames": f1 - f0, "settings": settings, "comp": _norm({kk: vv for kk, vv in k.items() if kk not in ("layers", "duration", "work_area", "markers")}, items, memo, files), "layers": parts}
        segs.append({"f0": f0, "f1": f1, "key": hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]})
    return segs, total


def frames(p: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().split(",")[0])
    except ValueError:
        return -1
