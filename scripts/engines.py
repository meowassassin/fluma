#!/usr/bin/env python3
"""
렌더 엔진 레지스트리와 공용 도구 (2026-10-28, Remotion 제거).

엔진 = engines/<이름>/ 폴더 하나:
  engine.json      이름·라이선스·종류(html|ts|python)·미리보기 방식·텔레메트리 끄는 환경 변수
  adapter.py       build(job) / render(job) -> 무음 mp4 / snapshot(job, seconds) -> [png]
  templates/<T>/   템플릿. meta.json 의 captions: "self"(템플릿이 단어 자막을 그림) | "finish"(마무리 단계가 ASS 로 입힘)

엔진이 받는 입력은 언제나 같다: 콘티 JSON + 룩 토큰(기본 ← 룩) + 장면 타이밍 + 단어 자막 + public/ 자산.
음성 믹스와(필요하면) 단어 자막은 scripts/finish.py 가 엔진과 무관하게 처리한다.

  python3 scripts/engines.py            # 엔진·템플릿 목록과 설치 상태
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ROOT / "engines"
PUBLIC = ROOT / "public"
# 렌더 작업은 서버가 작업마다 따로 폴더를 준다(FLUMA_WORK_ROOT) — 미리보기 빌드 · 정지 화면과 같은 폴더를 겹쳐 쓰지 않게
WORK = Path(os.environ["FLUMA_WORK_ROOT"]) if os.environ.get("FLUMA_WORK_ROOT") else ROOT / "workspace" / "render"
OUT = ROOT / "out"
# 기본은 Craft 파이프라인(재료 → EffectCraft → SoundCraft → FilmCraft). Craft 앱이 설치되지 않은 환경에서만 HyperFrames
DEFAULT_ENGINE = "craft" if (Path(__file__).resolve().parents[1] / "tools" / "crafts" / "effectcraft" / "installed.json").exists() else "hyperframes"
BASE_TOKENS = json.loads((ROOT / "tokens" / "default.json").read_text(encoding="utf-8"))


# ---------- 레지스트리 ----------
def engine_meta(name: str) -> dict:
    p = ENGINES / name / "engine.json"
    if not p.exists():
        raise SystemExit(f"엔진 없음: {name} (engines/ 아래 {', '.join(list_engines()) or '없음'})")
    return json.loads(p.read_text(encoding="utf-8"))


def list_engines() -> list[str]:
    return sorted(d.name for d in ENGINES.iterdir() if (d / "engine.json").exists()) if ENGINES.exists() else []


def list_templates(engine: str) -> list[dict]:
    out = []
    tdir = ENGINES / engine / "templates"
    for d in sorted(tdir.iterdir()) if tdir.exists() else []:
        m = d / "meta.json"
        if m.exists():
            meta = json.loads(m.read_text(encoding="utf-8"))
            meta.setdefault("name", d.name)
            meta["engine"] = engine
            out.append(meta)
    return out


def adapter(engine: str):
    path = ENGINES / engine / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"engine_{engine}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def engine_env(engine: str) -> dict:
    """텔레메트리는 기본으로 끈다 (engine.json env)."""
    env = {**os.environ, "DO_NOT_TRACK": "1"}
    env.update(engine_meta(engine).get("env", {}))
    return env


# ---------- 토큰 ----------
def _merge(a, b):
    if not isinstance(b, dict):
        return a
    out = json.loads(json.dumps(a))
    for k, v in b.items():
        if k.startswith("$") or v is None:
            continue
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def look_tokens(sb: dict | str | None = None) -> dict:
    """완성된 토큰 = 기본(tokens/default.json) ← 콘티 디자인 방향의 색(direction.color_*).
    룩 카탈로그 · 브랜드 키트는 2026-10-29 제거(ADR-0011) — 영상마다 direct.py 가 색을 정한다.
    (예전처럼 이름을 넘겨도 기본 토큰을 돌려준다.)"""
    tokens = json.loads(json.dumps(BASE_TOKENS))
    if isinstance(sb, dict):
        dcol = {k[6:]: v for k, v in (sb.get("direction") or {}).items() if k.startswith("color_") and isinstance(v, str) and v.startswith("#")}
        if dcol:
            tokens = _merge(tokens, {"color": dcol})
    return tokens


# ---------- 작업 ----------
@dataclass
class Job:
    sb: dict
    sb_path: Path
    engine: str
    template: str
    tokens: dict
    fps: int = 30
    draft: bool = False
    work: Path = field(default=Path())
    scenes: list = field(default_factory=list)      # [{"index","start","end","sec"}]
    captions: list = field(default_factory=list)    # Caption[] (영상 기준 ms)
    audio: Path | None = None

    @property
    def width(self) -> int:
        return 540 if self.draft else int(self.tokens["layout"]["width"])

    @property
    def height(self) -> int:
        return 960 if self.draft else int(self.tokens["layout"]["height"])

    @property
    def duration(self) -> float:
        return round(sum(float(s["sec"]) for s in self.sb["scenes"]), 3)


def pick_template(engine: str, sb: dict) -> str:
    """엔진의 템플릿 중 콘티 형식에 맞는 것. 없으면 primary, 그것도 없으면 첫 번째."""
    ts = list_templates(engine)
    if not ts:
        raise SystemExit(f"{engine} 엔진에 템플릿이 없습니다")
    fmt = sb.get("format")
    kinds = {s.get("visual", {}).get("kind") for s in sb.get("scenes", [])}
    for t in ts:
        if fmt in t.get("formats", []) and (not t.get("needs") or set(t["needs"]) & kinds):
            return t["name"]
    prim = [t for t in ts if t.get("primary")]
    return (prim or ts)[0]["name"]


def make_job(sb_path: Path, engine: str | None = None, template: str | None = None, draft: bool = False) -> Job:
    sb_path = Path(sb_path).resolve()
    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    engine = engine or sb.get("engine") or DEFAULT_ENGINE
    engine_meta(engine)
    template = template or sb.get("template") or pick_template(engine, sb)
    if template not in [t["name"] for t in list_templates(engine)]:
        raise SystemExit(f"{engine} 엔진에 템플릿 {template} 없음 ({', '.join(t['name'] for t in list_templates(engine))})")
    tokens = look_tokens(sb)
    t, scenes = 0.0, []
    for i, s in enumerate(sb["scenes"]):
        sec = float(s["sec"])
        scenes.append({"index": i, "start": round(t, 3), "end": round(t + sec, 3), "sec": sec})
        t += sec
    cap_p = PUBLIC / "audio" / f"{sb['id']}.captions.json"
    captions = json.loads(cap_p.read_text(encoding="utf-8")) if cap_p.exists() else []
    audio = PUBLIC / "audio" / f"{sb['id']}.wav"
    work = WORK / sb["id"] / engine / (template + ("-draft" if draft else ""))
    work.mkdir(parents=True, exist_ok=True)
    return Job(sb=sb, sb_path=sb_path, engine=engine, template=template, tokens=tokens, fps=int(tokens["motion"].get("fps", 30)),
               draft=draft, work=work, scenes=scenes, captions=captions, audio=audio if audio.exists() else None)


def template_meta(job: Job) -> dict:
    return next(t for t in list_templates(job.engine) if t["name"] == job.template)


def run(cmd: list, cwd: Path, env: dict | None = None, label: str = "", timeout: int = 1800) -> subprocess.CompletedProcess:
    """엔진 실행. 일부 엔진은 오류에서 종료하지 않고 멈추므로 시간 제한을 둔다."""
    try:
        r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=env, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        tail = ((e.stdout or "")[-1500:] if isinstance(e.stdout, str) else "") + ((e.stderr or "")[-1500:] if isinstance(e.stderr, str) else "")
        raise SystemExit(f"[{label or cmd[0]} 시간 초과 {timeout}s]\n{tail}")
    if r.returncode != 0:
        tail = (r.stdout[-2500:] + "\n" + r.stderr[-2500:]).strip()
        raise SystemExit(f"[{label or cmd[0]} 실패 exit {r.returncode}]\n{tail}")
    return r


def copy_public(paths: list[str], dest: Path):
    """콘티가 쓰는 public/ 자산을 엔진 작업 폴더로 복사 (엔진은 네트워크·외부 경로를 쓰지 않는다)."""
    for rel in paths:
        src = PUBLIC / rel
        if src.exists():
            d = dest / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            if not d.exists() or d.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, d)


def used_assets(sb: dict) -> list[str]:
    return [s["visual"]["asset"] for s in sb.get("scenes", []) if (s.get("visual") or {}).get("asset")]


# ---------- 장면 단위 (장면마다 엔진 섞기) ----------
def sub_job(job: Job, indices: list[int]) -> Job:
    """연속한 장면들만 담은 작업. 시간은 첫 장면을 0초로 당기고, 장면 index 는 원래 번호를 유지한다
    (템플릿의 색 순서 등이 전체 렌더와 같게). 엔진 어댑터는 고칠 필요 없다 — 짧은 콘티 하나로 보인다."""
    idx = sorted(indices)
    if idx != list(range(idx[0], idx[-1] + 1)):
        raise SystemExit(f"장면은 연속이어야 합니다: {idx}")
    t0 = job.scenes[idx[0]]["start"]
    sb = {**job.sb, "scenes": [job.sb["scenes"][i] for i in idx]}
    scenes = [{**job.scenes[i], "start": round(job.scenes[i]["start"] - t0, 3), "end": round(job.scenes[i]["end"] - t0, 3)} for i in idx]
    ms = t0 * 1000
    caps = [{**c, "startMs": c["startMs"] - ms, "endMs": c["endMs"] - ms, "timestampMs": (c.get("timestampMs") or c["startMs"]) - ms}
            for c in job.captions if c.get("scene") in idx]
    work = job.work.parent / f"{job.template}{'-draft' if job.draft else ''}-s{idx[0] + 1}-{idx[-1] + 1}"
    work.mkdir(parents=True, exist_ok=True)
    return Job(**{**job.__dict__, "sb": sb, "scenes": scenes, "captions": caps, "work": work})


def scene_plan(sb: dict, engine: str | None = None, template: str | None = None, overrides: list[str] | None = None) -> list[tuple[str, str]]:
    """장면마다 (엔진, 템플릿). 우선순위: --engines 목록 > 장면 engine/template > 명령줄 --engine/--template > 콘티 engine/template > 기본."""
    base_e = engine or sb.get("engine") or DEFAULT_ENGINE
    plan = []
    for i, s in enumerate(sb["scenes"]):
        e = (overrides[i] if overrides and i < len(overrides) and overrides[i] else None) or s.get("engine") or base_e
        t = s.get("template") if s.get("engine") == e else None
        if not t and e == base_e:
            t = template or (sb.get("template") if (sb.get("engine") or DEFAULT_ENGINE) == e else None)
        engine_meta(e)
        plan.append((e, t or pick_template(e, sb)))
    return plan


def segments(plan: list[tuple[str, str]]) -> list[tuple[str, str, list[int]]]:
    """같은 (엔진, 템플릿)이 이어지는 장면끼리 묶는다 — 묶음 안의 전환은 엔진이 그대로 그린다."""
    out = []
    for i, et in enumerate(plan):
        if out and (out[-1][0], out[-1][1]) == et:
            out[-1][2].append(i)
        else:
            out.append((et[0], et[1], [i]))
    return out


if __name__ == "__main__":
    for e in list_engines():
        m = engine_meta(e)
        try:
            ok = adapter(e).available()
        except Exception as ex:  # noqa: BLE001
            ok = f"확인 실패: {ex}"
        print(f"{e:<12} {m.get('license', ''):<11} {m.get('kind', ''):<7} 미리보기={m.get('preview', '')}  설치={ok}")
        for t in list_templates(e):
            print(f"    - {t['name']:<14} {t.get('mood', '')}")


# ---------- HTML 이 아닌 엔진들이 함께 쓰는 도우미 ----------
def job_data(job: Job) -> dict:
    """엔진에 넘기는 입력 한 덩어리 (HyperFrames 의 window.SF 와 같은 모양)."""
    return {"sb": job.sb, "tokens": job.tokens, "scenes": job.scenes, "captions": job.captions,
            "duration": job.duration, "fps": job.fps, "width": job.width, "height": job.height,
            "assets": [a for a in used_assets(job.sb) if (PUBLIC / a).exists()], "public": str(PUBLIC),
            "fonts": str(PUBLIC / "fonts")}


def write_job(job: Job) -> Path:
    p = job.work / "job.json"
    p.write_text(json.dumps(job_data(job), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def content_key(job: Job, extra: list[Path] = ()) -> str:
    """콘티·토큰·템플릿 파일이 같으면 같은 키 → 초안 렌더 재사용."""
    import hashlib
    h = hashlib.sha1(json.dumps(job_data(job), sort_keys=True, ensure_ascii=False).encode())
    tdir = ENGINES / job.engine / "templates" / job.template
    for f in sorted(list(tdir.rglob("*")) + list(extra)):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def frames_from_video(video: Path, seconds: list[float], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    out = []
    for s in seconds:
        p = outdir / f"at-{s:g}s.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, s):.3f}", "-i", str(video), "-frames:v", "1", str(p)], check=True)
        out.append(p)
    return out


def snapshot_via_draft(job: Job, seconds: list[float], render_fn) -> list[Path]:
    """미리보기 수단이 없는 엔진: 초안을 렌더(내용이 같으면 재사용)해서 프레임을 뽑는다."""
    key = content_key(job)
    draft_dir = job.work.parent / f"{job.template}-snapdraft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    video = draft_dir / f"{key}.mp4"
    if not video.exists():
        for old in draft_dir.glob("*.mp4"):
            old.unlink()
        dj = Job(**{**job.__dict__, "draft": True, "work": draft_dir})
        src = render_fn(dj)
        shutil.move(str(src), video)
    return frames_from_video(video, seconds, job.work / "snaps")
