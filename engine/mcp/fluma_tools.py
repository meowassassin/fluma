"""MCP 제작 도구(P1 · P2) — 콘티 읽기 · 고치기, 검사, 음성 · 빌드 · 정지 화면 · 렌더, 화면 검토 제출, 측정, 품질 관문, 면제.

판단(무엇을 고칠지)은 에이전트, 여기는 계산 · 측정 · 관문. 무거운 것은 작업(fluma_jobs)으로.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fluma_jobs as jobs  # noqa: E402
from fluma_jobs import ROOT  # noqa: E402
from fluma_project import check_id  # noqa: E402

PY = sys.executable
DATA = ROOT / "data"
SCHEMA = ROOT / "engine" / "spec" / "schema" / "storyboard.schema.json"
REVIEW_BLOCK_KINDS = ("겹침", "잘림", "안전 영역")
_schema = None


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def sb_path(pid: str) -> Path:
    p = DATA / "storyboards" / f"{check_id(pid)}.json"
    if not p.exists():
        raise ValueError(f"콘티가 없습니다: {_rel(p)}")
    return p


def _load(pid: str) -> dict:
    return json.loads(sb_path(pid).read_text("utf-8"))


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


# ---------- 콘티 ----------
def storyboard_get(pid: str, view: str = "edit") -> dict:
    sb = _load(pid)
    if view == "full":
        return sb
    from story.skill_pass import view as sp_view
    out = sp_view(sb, design=(view == "design"))
    out["waivers"] = sb.get("waivers") or {}
    return out


def _merge_patch(dst, patch):
    """객체는 칸 단위로 합침, null 은 지움, 목록은 통째로 바꿈(장면은 scenes 의 번호 키로 따로)"""
    if not isinstance(patch, dict) or not isinstance(dst, dict):
        return copy.deepcopy(patch)
    out = dict(dst)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_patch(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


PROTECTED = {"id", "version", "waivers"}   # waivers 는 waive 도구로만(사용자 말이 있어야)


def _validate(sb: dict) -> list[str]:
    global _schema
    try:
        import jsonschema
    except ImportError:
        return []
    if _schema is None:
        _schema = json.loads(SCHEMA.read_text("utf-8"))
    v = jsonschema.Draft202012Validator(_schema)
    errs = sorted(v.iter_errors(sb), key=lambda e: list(e.path))
    return [f"{'/'.join(str(x) for x in e.path) or '(전체)'}: {e.message[:200]}" for e in errs[:12]]


def storyboard_patch(pid: str, patch: dict) -> dict:
    """patch: 콘티 칸 → 새 값. 장면은 {"scenes": {"3": {"caption": "…"}}} 처럼 번호(1부터)로. 형식 검사를 통과해야 저장"""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch 가 비었습니다")
    bad = PROTECTED & set(patch)
    if bad:
        raise ValueError(f"이 도구로 못 바꾸는 칸: {', '.join(sorted(bad))} (면제는 waive)")
    sp = sb_path(pid)
    base = json.loads(sp.read_text("utf-8"))
    mine = copy.deepcopy(base)
    changed = []
    scenes_patch = patch.get("scenes")
    if isinstance(scenes_patch, dict):
        for k, v in scenes_patch.items():
            try:
                n = int(k)
            except ValueError:
                raise ValueError(f"scenes 의 키는 장면 번호(1부터): {k}") from None
            if not 1 <= n <= len(mine.get("scenes") or []):
                raise ValueError(f"없는 장면: {n}")
            mine["scenes"][n - 1] = _merge_patch(mine["scenes"][n - 1], v)
            changed += [f"scenes.{n}.{f}" for f in (v or {})]
    elif scenes_patch is not None:
        mine["scenes"] = copy.deepcopy(scenes_patch)
        changed.append("scenes(전체)")
    for k, v in patch.items():
        if k == "scenes":
            continue
        mine = _merge_patch(mine, {k: v})
        changed.append(k)
    errs = _validate(mine)
    if errs:
        raise ValueError("형식 검사 실패 — 저장하지 않음:\n" + "\n".join(errs))
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import sbio
    sbio.save(sp, base, mine)
    return {"saved": _rel(sp), "changed": changed, "next": "lint 로 확인 → 화면이 바뀌었으면 scene_build_start · scene_still"}


# ---------- 검사 ----------
def lint(pid: str) -> dict:
    sp = sb_path(pid)
    r = _run(["engine/checks/lint.py", _rel(sp)], 180)
    rows = []
    for ln in (r.stdout or "").splitlines():
        m = re.match(r"^\s*([LTVDR]\d{2})\b\s*(?:scene=(\S+))?\s*(.*)$", ln.strip())
        if m:
            sc = m.group(2)                            # lint.py 는 장면을 0부터 센다 — 도구는 1부터(다른 도구 · 콘티 패치와 같게)
            rows.append({"code": m.group(1), "scene": int(sc) + 1 if sc and sc.isdigit() else None, "msg": m.group(3)[:240]})
    fails = [x for x in rows if x["code"].startswith("L")]
    return {"pass": not fails, "fail": fails, "advise": [x for x in rows if not x["code"].startswith("L")][:30],
            **({"error": (r.stderr or "").strip()[-400:]} if r.returncode not in (0, 1) and not rows else {})}


# ---------- 작업으로 도는 단계 ----------
def _job(kind: str, pid: str, args: list[str], label: str, *, heavy: bool, mem_gb: float, timeout: int = 3600, key: str | None = None) -> dict:
    return jobs.submit(kind, [PY, *args], project=pid, label=label, key=key or f"{kind}:{pid}", heavy=heavy, mem_gb=mem_gb, timeout=timeout)


def prep_start(pid: str) -> dict:
    """대본 → 음악 · 목소리 → 음성(장면 길이 확정). 판단 단계(LLM)는 에이전트 몫이라 엔진은 부르지 않는다"""
    sp = sb_path(pid)
    return _job("prep", pid, ["engine/produce.py", _rel(sp), "--prep", "--judge", "agent"], f"음성 · 길이 {pid}", heavy=False, mem_gb=1.5, timeout=1800)


def scene_build_start(pid: str, scenes: str | None = None) -> dict:
    sp = sb_path(pid)
    args = ["engine/render.py", _rel(sp), "--build"] + (["--scenes", _scenes(scenes)] if scenes else [])
    return _job("build", pid, args, f"장면 빌드 {pid}" + (f" 장면 {scenes}" if scenes else ""), heavy=True, mem_gb=2.0, timeout=1800,
                key=f"build:{pid}:{scenes or 'all'}")


def render_start(pid: str, mode: str = "preview", scenes: str | None = None) -> dict:
    sp = sb_path(pid)
    rel = _rel(sp)
    if mode == "final":
        if scenes:
            raise ValueError("완성(final) 렌더는 전체만 — 일부 장면은 mode=preview")
        # 완성은 produce 를 판단 없이(--judge agent) 돌린다: 검사(lint) · 화면 검토 제출 확인 · 렌더 · 품질 관문 · 메타데이터
        return _job("produce", pid, ["engine/produce.py", rel, "--judge", "agent", "--no-audio"], f"완성 렌더 {pid}", heavy=True, mem_gb=3.0,
                    key=f"produce:{pid}")
    args = ["engine/render.py", rel, "--draft"] + (["--scenes", _scenes(scenes)] if scenes else [])
    return _job("render", pid, args, f"초안 렌더 {pid}" + (f" 장면 {scenes}" if scenes else ""), heavy=True, mem_gb=2.5,
                key=f"render:{pid}:{scenes or 'all'}")


def _scenes(s) -> str:
    s = str(s).strip()
    if not re.fullmatch(r"\d+(-\d+)?", s):
        raise ValueError("scenes 는 '3' 또는 '2-4' 형식")
    return s


# ---------- 정지 화면 ----------
def _scene_times(sb: dict) -> list[tuple[float, float]]:
    t, out = 0.0, []
    for s in sb.get("scenes") or []:
        d = float(s.get("sec") or 0)
        out.append((t, t + d))
        t += d
    return out


def _image(path: Path, width: int = 540) -> dict | None:
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        return {"type": "image", "data": base64.b64encode(buf.getvalue()).decode(), "mimeType": "image/jpeg"}
    except Exception:  # noqa: BLE001 — 그림을 못 붙여도 경로는 준다
        return None


def scene_still(pid: str, scenes: list[int] | None = None, seconds: list[float] | None = None, images: bool = True) -> tuple[dict, list[dict]]:
    """프로젝트에서 바로 정지 화면(렌더 없이). scenes 면 장면마다 가운데 · 끝 직전 두 장"""
    sp = sb_path(pid)
    sb = json.loads(sp.read_text("utf-8"))
    spans = _scene_times(sb)
    pts: list[tuple[str, float]] = []
    if seconds:
        pts = [(f"{s:g}초", float(s)) for s in seconds[:12]]
    else:
        want = scenes or list(range(1, len(spans) + 1))
        for n in want[:8]:
            if not 1 <= int(n) <= len(spans):
                raise ValueError(f"없는 장면: {n}")
            a, b = spans[int(n) - 1]
            pts += [(f"장면 {n} 가운데", round((a + b) / 2, 2)), (f"장면 {n} 끝", round(max(a, b - 0.25), 2))]
    r = _run(["engine/core/still.py", _rel(sp), *[f"{t:.2f}" for _, t in pts]], 600)
    paths = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().endswith(".png")]
    if r.returncode != 0 or len(paths) != len(pts):
        raise RuntimeError("정지 화면 실패: " + ((r.stderr or r.stdout) or "").strip()[-500:])
    rows = [{"label": lab, "t": t, "path": _rel(Path(p))} for (lab, t), p in zip(pts, paths)]
    imgs = [im for p in paths for im in [_image(Path(p))] if im] if images else []
    return {"stills": rows}, imgs[:12]


# ---------- 화면 검토(에이전트가 보고 제출) ----------
def build_stamp(pid: str) -> str | None:
    """지금 장면 프로젝트(전체 빌드)의 지문 — 같은 입력이면 바이트까지 같다. 검토가 '지금 그림'을 봤는지 이걸로 안다"""
    p = DATA / "compositions" / pid / "craft" / "motion" / f"{pid}.ecproj"
    return hashlib.sha1(p.read_bytes()).hexdigest()[:16] if p.exists() else None


_SENT: dict[str, dict[str, str]] = {}   # 프로젝트 → {정지 화면 이름: 그림 지문} — 서버(에이전트 대화)마다 따로


def review_frames(pid: str, scenes: list[int] | None = None, images: bool = True) -> tuple[dict, list[dict]]:
    """검토용: 전체 빌드 → 장면별 정지 화면 + 장면 코드만 읽는 화면 검사(visual_tell) + 지난 검토 문제"""
    sp = sb_path(pid)
    r = _run(["engine/render.py", _rel(sp), "--build"], 1800)
    if r.returncode != 0:
        raise RuntimeError("장면 빌드 실패(장면 코드 오류): " + ((r.stderr or r.stdout) or "").strip()[-600:])
    out, _ = scene_still(pid, scenes=scenes, images=False)
    imgs = []
    sent = _SENT.setdefault(pid, {})
    for row in out["stills"]:                          # 이 대화(서버 한 번 = 에이전트 대화 하나)에 이미 보낸 그림과 같으면 다시 보내지 않는다
        h = hashlib.sha1((ROOT / row["path"]).read_bytes()).hexdigest()[:16]
        if sent.get(row["label"]) == h:
            row["same_as_before"] = True
            continue
        im = _image(ROOT / row["path"]) if images else None
        if im:
            imgs.append(im)
            sent[row["label"]] = h
    if any(r.get("same_as_before") for r in out["stills"]):
        out["unchanged_note"] = "same_as_before 인 장면은 지난번에 보낸 그림과 바이트까지 같아 그림을 빼고 보냈다(이미 본 것) — 다시 보려면 scene_still"
    sb = json.loads(sp.read_text("utf-8"))
    try:
        sys.path.insert(0, str(ROOT / "engine" / "checks"))
        import visual_tell as vt
        out["visual_tell"] = [{"code": x["code"], "scene": x["scene"], "msg": x["msg"][:220], "block": x["block"]} for x in vt.find(sb, pid)]
    except Exception as e:  # noqa: BLE001
        out["visual_tell_error"] = str(e)[:200]
    prev = _review_rec(pid)
    out["previous_problems"] = (prev or {}).get("problems") or []
    out["stamp"] = build_stamp(pid)
    try:
        out["design_precheck"] = design_precheck(pid, sb, scenes, out["stamp"])
    except Exception as e:  # noqa: BLE001 — 미리 재기를 못 해도 검토는 이어 간다(렌더 뒤 관문이 그대로 잰다)
        out["design_precheck_error"] = str(e)[:200]
    seen = _seen(pid)                                  # 이 빌드에서 정지 화면을 보여 준 장면 — review_submit 이 확인한다
    seen = seen if seen.get("stamp") == out["stamp"] else {"stamp": out["stamp"], "scenes": []}
    seen["scenes"] = sorted(set(seen["scenes"]) | set(scenes or range(1, len(sb.get("scenes") or []) + 1)))
    _seen_path(pid).write_text(json.dumps(seen), "utf-8")
    out["how"] = ("정지 화면을 보고 겹침(글자 · 물체가 서로 가림) · 잘림(글자 · 근거가 화면 밖) · 안전 영역(위 12% · 아래 18% 플랫폼 UI 자리) · "
                  "읽기 어려움을 찾는다. 다 본 뒤 review_submit(problems=[{scene, kind, what, fix}], looked=[본 장면]) — 문제가 없으면 problems=[]. "
                  "kind 가 겹침 · 잘림 · 안전 영역이면 완성 렌더를 막는다. design_precheck 의 block 은 렌더 뒤 품질 관문이 같은 기준으로 막을 것"
                  "(멈춘 장면 · 빈 화면 · 작은 주인공 · 같은 구도 등) — 렌더 전에 같이 고친다(남아 있으면 완성 렌더를 시작하지 않는다). 장면 코드를 고치면 review_frames 부터 다시")
    return out, imgs


def _pre_path(pid: str) -> Path:
    return DATA / "compositions" / pid / "skill_pass" / "design_pre.json"


def design_precheck(pid: str, sb: dict, scenes: list[int] | None, stamp: str | None) -> list[dict]:
    """렌더 뒤 디자인 검사(designcheck D10~D15)를 렌더 전 정지 화면으로 같은 시각 · 같은 기준으로 잰다.
    2026-11-24 실측: 멈춘 장면(D11)을 3.5분 완성 렌더 뒤에야 알아 렌더를 한 번 더 했다. 스틸 값은 영상 값과 거의 같다(0.0985 ↔ 0.0977).
    일부 장면만 볼 때는 장면별 검사(D10 · D11 · D12)만 — 이어진 장면 · 영상 전체 검사(D13 · D14 · D15)는 전체를 볼 때"""
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import designcheck as dc
    import quality_gate as qg
    import cv2
    want = set(scenes or range(1, len(sb.get("scenes") or []) + 1))
    wins = [w for w in dc.windows(sb) if w[0] in want]
    times = [x for w in wins for x in w[3]]
    if not times:
        return []
    r = _run(["engine/core/still.py", _rel(sb_path(pid)), *[f"{x:.2f}" for x in times], "--out", str(DATA / "workspace" / "stills" / "pre")], 600)
    paths = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().endswith(".png")]
    if r.returncode != 0 or len(paths) != len(times):
        raise RuntimeError("미리 재기 정지 화면 실패: " + ((r.stderr or r.stdout) or "").strip()[-300:])
    it = iter(paths)
    frames = [(sc, t0, d, [cv2.resize(cv2.imread(next(it)), (270, 480), interpolation=cv2.INTER_AREA) for _ in ts]) for sc, t0, d, ts in wins]
    full = not scenes
    found = [x for x in dc.findings_frames(frames) if full or x["code"] in ("D10", "D11", "D12")]
    items = []
    for x in found:
        it_ = {"code": x["code"], "scene": x["scene"], "msg": x["msg"], "block": x.get("block", x["code"] in qg.BLOCK_CODES)}
        if not qg.waived(sb, it_):
            items.append(it_)
    try:
        rec = json.loads(_pre_path(pid).read_text("utf-8"))
    except (OSError, ValueError):
        rec = {}
    if rec.get("stamp") != stamp or full:
        rec = {"stamp": stamp, "scenes": [], "items": []}
    rec["scenes"] = sorted(set(rec["scenes"]) | want)
    rec["items"] = [x for x in rec["items"] if x.get("scene") not in want] + items
    _pre_path(pid).write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    return items


def precheck_blocks(pid: str) -> list[dict]:
    """produce(--judge agent)가 렌더 전에: 지금 빌드로 미리 잰 디자인 막음(없거나 낡았으면 빈 목록 — 렌더 뒤 관문이 그대로 잰다)"""
    try:
        rec = json.loads(_pre_path(pid).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    if rec.get("stamp") != build_stamp(pid):
        return []
    sb = _load(pid)
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    import quality_gate as qg
    return [x for x in rec.get("items") or [] if x.get("block") and not qg.waived(sb, x)]


def _seen_path(pid: str) -> Path:
    p = DATA / "compositions" / pid / "skill_pass" / "review_seen.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _seen(pid: str) -> dict:
    try:
        return json.loads(_seen_path(pid).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _review_rec(pid: str) -> dict | None:
    try:
        return json.loads((DATA / "compositions" / pid / "skill_pass" / "review.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


def review_submit(pid: str, problems: list[dict], looked: list[int] | None = None, notes: str = "") -> dict:
    sb = _load(pid)
    stamp = build_stamp(pid)
    if not stamp:
        raise ValueError("전체 빌드가 없습니다 — review_frames 를 먼저(빌드 · 정지 화면)")
    n = len(sb.get("scenes") or [])
    seen = _seen(pid)
    if seen.get("stamp") != stamp:
        raise ValueError("지금 빌드의 정지 화면을 아직 보지 않았습니다 — review_frames 를 먼저(장면이 바뀌면 다시)")
    missing = sorted(set(range(1, n + 1)) - set(seen.get("scenes") or []))
    if missing:
        raise ValueError(f"아직 안 본 장면: {missing} — review_frames(scenes=[…]) 로 마저 보고 제출")
    clean = []
    for x in problems or []:
        if not isinstance(x, dict) or not str(x.get("what") or "").strip():
            raise ValueError("problems 항목은 {scene, kind, what, fix} — what 이 필요")
        sc = x.get("scene")
        if sc is not None and not (isinstance(sc, int) and 1 <= sc <= n):
            raise ValueError(f"없는 장면: {sc}")
        clean.append({"scene": sc, "kind": str(x.get("kind") or "").strip(), "what": str(x["what"]).strip()[:400],
                      **({"fix": str(x["fix"]).strip()[:300]} if x.get("fix") else {})})
    rec = {"pass": "review", "by": "agent", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stamp": stamp, "looked": looked or list(range(1, n + 1)),
           "problems": clean, "why": [notes] if notes else [], "changed": []}
    f = DATA / "compositions" / pid / "skill_pass" / "review.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), "utf-8")
    blocks = [p for p in clean if any(k in p["kind"] for k in REVIEW_BLOCK_KINDS)]
    pre = precheck_blocks(pid)
    blocks += [{"scene": x.get("scene"), "kind": x["code"], "what": x["msg"]} for x in pre]
    import fluma_stage
    end = None if blocks else fluma_stage.mark(pid, "reviewed")
    return {"saved": _rel(f), "stamp": stamp, "blocking": len(blocks), **({"design_precheck_block": pre} if pre else {}),
            "next": (f"막는 문제 {len(blocks)}건 — 장면 코드 · storyboard_patch 로 고친 뒤 review_frames 다시" if blocks
                     else end or "render_start(mode=final) 로 완성 렌더(서버가 lint · 검토 지문 · 품질 관문을 확인)")}


def review_fresh(pid: str) -> tuple[bool, str]:
    """produce(--judge agent)가 렌더 전에 부른다: 에이전트 검토가 지금 빌드를 봤나"""
    rec = _review_rec(pid)
    if not rec or rec.get("by") != "agent":
        return False, "에이전트 화면 검토가 없습니다 — review_frames 로 보고 review_submit"
    if rec.get("stamp") != build_stamp(pid):
        return False, "화면 검토 뒤에 장면이 바뀌었습니다 — review_frames 로 다시 보고 review_submit"
    return True, "ok"


# ---------- 측정 · 관문 ----------
def _latest_full(pid: str) -> Path | None:
    from fluma_project import _videos
    full = _videos(pid)[0]
    return full[-1] if full else None


def measure(pid: str) -> dict:
    """마지막 전체 영상을 잰다: 디자인(빈 화면 · 글자 크기 · 대비 …) — 렌더를 다시 하지 않는다"""
    v = _latest_full(pid)
    if not v:
        raise ValueError("전체 영상이 없습니다 — render_start 먼저")
    sb = _load(pid)
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    from designcheck import findings
    rows = [{"code": x["code"], "scene": x.get("scene"), "msg": str(x.get("msg"))[:220], "block": bool(x.get("block"))} for x in findings(v, sb)]
    return {"video": _rel(v), "findings": rows, "blocking": sum(1 for x in rows if x["block"])}


def quality_gate(pid: str) -> dict:
    q = None
    try:
        q = json.loads((DATA / "workspace" / "tmp" / check_id(pid) / "quality.json").read_text("utf-8"))
    except (OSError, ValueError):
        pass
    v = _latest_full(pid)
    if not q:
        return {"judged": False, "why": "아직 완성 렌더(render_start mode=final)를 하지 않아 판정이 없습니다"}
    stale = bool(v) and q.get("video") != _rel(v)
    blocks = q.get("block") or []
    return {"judged": True, "video": q.get("video"), "stale": stale, "finished": not blocks and not stale,
            "block": blocks, "waived": q.get("waived") or [], "advise": (q.get("advise") or [])[:15]}


def waive(pid: str, code: str, why: str, user_said: str, scene: int | None = None) -> dict:
    """사용자가 그대로 두라고 한 막음만. user_said = 사용자가 한 말 그대로(에이전트가 지어내지 않는다)"""
    if not re.fullmatch(r"[A-Z]\d{2}", code or ""):
        raise ValueError("code 는 D21 · T32 같은 형식")
    if not str(user_said or "").strip() or len(user_said.strip()) < 4:
        raise ValueError("user_said(사용자가 한 말 그대로)가 없으면 면제할 수 없습니다 — 스스로 면제 금지")
    if not str(why or "").strip():
        raise ValueError("why 가 필요합니다")
    sp = sb_path(pid)
    base = json.loads(sp.read_text("utf-8"))
    mine = copy.deepcopy(base)
    key = f"{code}:{scene}" if scene else code
    mine.setdefault("waivers", {})[key] = {"why": why.strip()[:300], "user_said": user_said.strip()[:500], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    sys.path.insert(0, str(ROOT / "engine" / "story"))
    import sbio
    sbio.save(sp, base, mine)
    return {"waived": key, "next": "render_start(mode=final) 로 다시 판정"}
