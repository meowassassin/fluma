"""FilmCraft 어댑터 — 화면 녹화(screen · video · web) 다듬기: 펀치인 줌 · 개인정보 흐림 · 빨리 감기.

재료 칸(모두 선택 — 하나도 없으면 아무것도 하지 않는다):
  "zoom":  [{"t": 2.0, "box": [x, y, w, h], "dur": 1.5, "scale": 180?}]   t 는 녹화 시각(초), box 는 0~1(녹화 화면 기준, 1 보다 크면 픽셀)
  "blur":  [[x, y, w, h], …]  또는 [{"box": [x, y, w, h], "amount": 60}]   녹화 내내 흐림(이메일 · 키 · 계정명)
  "speed": [{"from": 5.0, "to": 12.0, "x": 4}]                            녹화 시각 구간을 x 배로(설치 · 로딩 빨리 감기)
  "grade": "Teal Shadows, Warm Skin"                                     Lumetri 색 프리셋(lumetri.presets) — 콘티 direction.grade 가 기본이라
                                                                           한 영상의 클립들이 같은 톤이 된다
결과: <재료id>.fc.mp4(다듬은 영상) + <재료id>.fcproj(사람이 FilmCraft 에서 고칠 프로젝트).
사람이 .fcproj 를 고쳤으면(만들 때 해시와 다름) 다시 만들지 않고 그 프로젝트로 내보내기만 한다.
키프레임 time 은 시퀀스 시각(ticks)이다 — 줌 · 흐림을 원본 시각 그대로 건 다음 자르고 속도를 바꾸면(키프레임이 클립 안쪽 시각을 따라감,
렌더로 확인) 줌이 빨리 감긴 구간에서도 같은 화면에 걸린다. 속도를 바꾸면 웹 녹화 단계(steps) 시각도 새 시각으로 고친다.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

TICKS = 254016000000          # FilmCraft 1초
RAMP = 0.3                    # 줌이 들어가고 나오는 시간(초)
SRC_PRESET = "Match Source – Adaptive High Bitrate"


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else ""


def _probe(f: Path) -> tuple[int, int, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "json", str(f)], capture_output=True, text=True)
    try:
        s = json.loads(r.stdout)["streams"][0]
        a, b = (s.get("r_frame_rate") or "30/1").split("/")
        fps = float(a) / float(b or 1)
        return int(s["width"]), int(s["height"]), fps if 1 <= fps <= 120 else 30.0
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        raise RuntimeError(f"영상 크기를 읽지 못했습니다: {f.name}")


def _box(b, W: int, H: int) -> tuple[float, float, float, float]:
    """[x, y, w, h] → 픽셀. 모두 1 이하면 0~1 비율로 본다"""
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        raise RuntimeError(f"상자는 [x, y, w, h] 여야 합니다: {b}")
    x, y, w, h = (float(v) for v in b)
    if max(x, y, w, h) <= 1.0:
        x, y, w, h = x * W, y * H, w * W, h * H
    if w <= 0 or h <= 0:
        raise RuntimeError(f"상자 크기가 0 입니다: {b}")
    return x, y, w, h


def _tk(sec: float, fps: float) -> int:
    """초 → 프레임 경계에 맞춘 ticks"""
    return int(round(round(sec * fps) * TICKS / fps))


# ---------------------------------------------------------------- 줌
def zoom_keys(zooms: list[dict], W: int, H: int) -> list[tuple[float, float, list[float]]]:
    """줌 요청 → (시각, scale %, position[x, y]) 키프레임. 상자 가운데를 화면 가운데로, 상자가 화면의 88% 를 채우게(115~300%).
    화면 밖(검은 테두리)이 보이지 않게 position 을 막는다. 앞 줌이 끝나기 전에 다음 줌이 오면 100% 로 돌아가지 않고 바로 옮긴다"""
    C = [W / 2, H / 2]
    zs = sorted((z for z in zooms if isinstance(z, dict) and z.get("box") is not None), key=lambda z: float(z.get("t", 0)))
    keys: list[tuple[float, float, list[float]]] = []
    for i, z in enumerate(zs):
        x, y, w, h = _box(z["box"], W, H)
        k = float(z["scale"]) / 100 if z.get("scale") else min(3.0, 0.88 * min(W / w, H / h))
        k = max(1.15, k)                 # 넓은 상자라도 펀치인이 눈에 보이게
        bx, by = x + w / 2, y + h / 2
        pos = [round(min(k * W / 2, max(W - k * W / 2, C[0] - (bx - C[0]) * k)), 1),
               round(min(k * H / 2, max(H - k * H / 2, C[1] - (by - C[1]) * k)), 1)]
        dur = max(RAMP, float(z.get("dur", 1.5)))
        t = max(0.0, float(z.get("t", 0)), keys[-1][0] if keys else 0.0)     # 앞 줌과 겹치면 앞 줌이 끝난 뒤에
        if not keys or keys[-1][1] == 100.0:
            if not keys or keys[-1][0] < t:
                keys.append((t, 100.0, C))                                   # 여기까지는 원래 크기
        elif keys[-1][0] < t:
            keys.append((t, keys[-1][1], keys[-1][2]))                       # 앞 줌을 여기까지 붙잡고 바로 옮긴다
        keys.append((t + RAMP, round(k * 100, 2), pos))
        keys.append((t + RAMP + dur, round(k * 100, 2), pos))
        nxt = float(zs[i + 1].get("t", 0)) if i + 1 < len(zs) else None
        if nxt is None or nxt > t + 2 * RAMP + dur:
            keys.append((t + 2 * RAMP + dur, 100.0, C))
    return keys


def zoom_lines(clip: int, keys: list, fps: float) -> list[dict]:
    out = []
    for t, s, pos in keys:
        tk = _tk(t, fps)
        out.append({"id": "effects.setParam", "params": {"clip": clip, "effect": "motion", "param": "scale", "value": s, "time": tk, "keyframe": True}})
        out.append({"id": "effects.setParam", "params": {"clip": clip, "effect": "motion", "param": "position", "value": pos, "time": tk, "keyframe": True}})
    if keys:   # 기계적인 등속 대신 부드럽게 들어가고 나오기(클립이 0초에 원본 0초로 놓여 있어 media 시각 = 시퀀스 시각)
        kf = [{"clip": clip, "effect": 0, "param": p, "time": _tk(t, fps)} for t, _s, _p in keys for p in ("scale", "position")]
        out.append({"id": "effects.setInterpolation", "params": {"keyframes": kf, "interpolation": "bezier"}})
    return out


# ---------------------------------------------------------------- 흐림
def blur_lines(clip: int, blurs: list, W: int, H: int, first_index: int = 3) -> list[dict]:
    """상자마다 gaussian_blur 하나 + 사각 마스크(원본 픽셀 좌표 — 줌을 해도 화면 내용을 따라감). 새 효과 번호는 3번부터"""
    out = []
    for k, b in enumerate(blurs):
        box, amt = (b.get("box"), float(b.get("amount", 60))) if isinstance(b, dict) else (b, 60.0)
        x, y, w, h = _box(box, W, H)
        pad = max(6.0, 0.01 * W)                     # 글자 가장자리가 새지 않게 조금 넓게
        idx = first_index + k
        out += [{"id": "effects.apply", "params": {"clips": [clip], "effect": "gaussian_blur"}},
                {"id": "effects.setParam", "params": {"clip": clip, "effect": idx, "param": "blurriness", "value": amt}},
                {"id": "masks.add", "params": {"clip": clip, "effect": idx, "shape": "rectangle",
                                               "center": [round(x + w / 2, 1), round(y + h / 2, 1)], "size": [round(w + 2 * pad, 1), round(h + 2 * pad, 1)]}}]
    return out


# ---------------------------------------------------------------- 속도
def speed_ranges(speed: list) -> list[tuple[float, float, float]]:
    """[(from, to, 배)] — 시각순 · 겹치는 구간은 버림 · 배는 0.1~20"""
    rs = []
    for s in speed or []:
        if not isinstance(s, dict):
            continue
        a, b, x = float(s.get("from", 0)), float(s.get("to", 0)), float(s.get("x", 1))
        if b > a and x > 0 and abs(x - 1) > 1e-6:
            rs.append((a, b, min(20.0, max(0.1, x))))
    rs.sort()
    out: list[tuple[float, float, float]] = []
    for r in rs:
        if out and r[0] < out[-1][1]:
            print(f"[재료] 빨리 감기 구간이 겹쳐 뺍니다: {r[0]}~{r[1]}초")
            continue
        out.append(r)
    return out


def remap(t: float, ranges: list[tuple[float, float, float]]) -> float:
    """녹화 시각 → 속도를 바꾼 뒤 영상 시각"""
    shift = 0.0
    for a, b, x in ranges:
        if t <= a:
            break
        seg = min(t, b) - a
        shift += seg - seg / x
    return round(t - shift, 3)


def _steps_from_src(m: dict) -> list[dict]:
    """passthrough 가 요소 폴더(웹 녹화)에서 만든 단계 시각을 같은 식으로 다시 구한다(POST 는 info 를 받지 않으므로)"""
    from ..materials import _abs, _load
    src = _abs(m["src"]) if m.get("src") else None
    if not src or not src.is_dir():
        return []
    meta = _load(src / "meta.json")
    hold = float(m.get("hold", 1.2))
    holds = [float(x) for x in m["holds"]] if m.get("holds") else None
    at = lambda k: sum((holds[i] if i < len(holds) else holds[-1]) for i in range(k)) if holds else hold * k   # noqa: E731
    return [{"t": round(at(int(a.get("to", 0))) - 0.15, 2), "t_end": round(at(int(a.get("to", 0)) + 1), 2), "label": a.get("label")}
            for a in meta.get("actions") or [] if a.get("label")]


# ---------------------------------------------------------------- FilmCraft 실행
def _fc(fc: str, *args, cwd: Path, timeout: int = 600) -> str:
    from ..materials import _run
    return _run([fc, "--compact", *args], cwd, timeout=timeout)


def _script(fc: str, proj: Path, lines: list[dict], work: Path, name: str) -> list[dict]:
    sp = work / f".{proj.stem}.{name}.jsonl"
    sp.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), "utf-8")
    try:
        out = _fc(fc, "--project", proj, "--save", "run", sp, cwd=work)
    finally:
        sp.unlink(missing_ok=True)
    return [json.loads(ln) for ln in out.splitlines() if ln.strip().startswith("{")]


def _v1(fc: str, proj: Path, work: Path) -> list[dict]:
    seq = json.loads(_fc(fc, "--project", proj, "inspect", "sequence", cwd=work))
    return (seq.get("video") or [{}])[0].get("items") or []


def trim(m: dict, file: Path, work: Path, info: dict | None = None) -> dict | None:
    """화면 녹화 mp4 를 FilmCraft 로 다듬는다. zoom · blur · speed 칸이 없으면 None(그대로 씀)"""
    zooms, blurs, ranges = list(m.get("zoom") or []), list(m.get("blur") or []), speed_ranges(m.get("speed") or [])
    grade = m.get("grade") or (m.get("_grade") if m.get("gen") else None)
    if not (zooms or blurs or ranges or grade):
        return None
    if Path(file).suffix.lower() not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        return None                                   # 이미지 화면은 다듬을 것이 없다(줌은 움직임 단계가)
    from ..materials import cli, _load, ROOT
    fc = cli("filmcraft")
    file = Path(file).resolve()
    proj = work.resolve() / f"{m['id']}.fcproj"
    dst = work.resolve() / f"{m['id']}.fc.mp4"
    old = _load(work / f"{m['id']}.json")
    edited = proj.exists() and old.get("editable_hash") and _sha(proj) != old["editable_hash"]
    W, H, fps = _probe(file)
    if not edited:
        proj.unlink(missing_ok=True)
        _fc(fc, "--save-as", proj, "exec", "file.newSequence", json.dumps({"name": m["id"], "width": W, "height": H, "fps": round(fps, 3)}), cwd=work)
        item = json.loads(_fc(fc, "--project", proj, "--save", "import", file, cwd=work))["items"][0]
        res = _script(fc, proj, [{"id": "timeline.place", "params": {"item": item, "track": "V1", "seconds": 0, "insert": False, "audio": False}}], work, "place")
        clip = res[0]["result"]["clips"][0]
        keys = zoom_keys(zooms, W, H)
        lines = zoom_lines(clip, keys, fps) + blur_lines(clip, blurs, W, H)
        if lines:
            res = _script(fc, proj, lines, work, "fx")
            bad = [r for r in res if not r.get("ok", True)]
            if bad:
                raise RuntimeError(f"FilmCraft 줌 · 흐림 실패: {bad[0]}")
            applied = [r["result"]["applied"][0]["index"] for r in res if r.get("id") == "effects.apply"]
            if applied and applied != list(range(3, 3 + len(applied))):
                raise RuntimeError(f"FilmCraft 흐림 효과 번호가 예상과 다릅니다: {applied}")
        if grade:   # 색 맞추기: 한 영상의 클립들을 같은 Lumetri 프리셋으로(클립마다 다른 색감을 한 톤으로)
            res = _script(fc, proj, [{"id": "lumetri.applyPreset", "params": {"name": grade, "clips": [clip]}}], work, "grade")
            if any(not r.get("ok", True) for r in res):
                raise RuntimeError(f"FilmCraft 색 프리셋 '{grade}' 실패: {res} (이름은 lumetri.presets)")
        if ranges:
            # 구간 경계에서 자르고(뒤에서부터) → 그 조각만 속도 변경(리플: 뒤 조각이 당겨짐). 줌 · 흐림 키프레임은 조각마다 복사된다
            cuts = sorted({_tk(t, fps) for a, b, _x in ranges for t in (a, b)}, reverse=True)
            _script(fc, proj, [{"id": "timeline.razor", "params": {"time": c, "track": "V1"}} for c in cuts], work, "razor")
            items = _v1(fc, proj, work)
            sp_lines = []
            for a, b, x in sorted(ranges, reverse=True):
                ta = _tk(a, fps)
                hit = next((it for it in items if it.get("sourceIn") == ta), None)
                if not hit:
                    print(f"[재료] {m['id']}: {a}초에서 자른 조각을 찾지 못해 빨리 감기를 건너뜁니다")
                    continue
                sp_lines.append({"id": "clip.speedDuration", "params": {"clips": [hit["clip"]], "speed": round(x * 100, 2), "ripple": True}})
            if sp_lines:
                _script(fc, proj, sp_lines, work, "speed")
    else:
        print(f"[재료] {proj.name} 은 사람이 고쳤습니다 — 그 프로젝트로 내보냅니다")
    _fc(fc, "--project", proj, "export", dst, "--preset", SRC_PRESET, "--no-audio", cwd=work, timeout=600)
    if not dst.exists():
        raise RuntimeError("FilmCraft 가 다듬은 영상을 내보내지 못했습니다")
    out = {"file": dst, "app": "filmcraft", "editable": str(proj.relative_to(ROOT)) if proj.is_relative_to(ROOT) else str(proj),
           "editable_hash": old.get("editable_hash") if edited else _sha(proj), "as": "video"}
    if edited:
        out["edited"] = True
    if zooms:
        out["zoomed"] = [{"t": remap(float(z.get("t", 0)), ranges), "box": z.get("box"),
                          "dur": round(remap(float(z.get("t", 0)) + float(z.get("dur", 1.5)), ranges) - remap(float(z.get("t", 0)), ranges), 3)}
                         for z in zooms if isinstance(z, dict)]
    if blurs:
        out["blurred"] = len(blurs)
    if grade:
        out["graded"] = grade
    if ranges:
        out["time_map"] = [{"from": a, "to": b, "x": x, "at": remap(a, ranges), "until": remap(b, ranges)} for a, b, x in ranges]
        steps = (info or {}).get("steps")
        if steps is None:
            steps = _steps_from_src(m)
        if steps:
            out["steps"] = [{**s, "t": remap(float(s["t"]), ranges), **({"t_end": remap(float(s["t_end"]), ranges)} if s.get("t_end") is not None else {})}
                            for s in steps]
    return out


POST = {"screen": trim, "video": trim, "web": trim}
