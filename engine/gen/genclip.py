#!/usr/bin/env python3
"""실사 생성 클립 — 그림 시안 → 사용자가 고름 → 그 그림으로 영상. 오픈라우터 키 · 모델이 있으면 Fluma 가 직접(key · pick-key · run, 비용 관문),
없으면 프롬프트를 써 주고 사용자가 자기 도구로 만들어 올린다(prompts). 어느 쪽이든 결과는 재료로 쓴다.
실제 자료(퍼온 클립 · 스톡 · 사진 · 화면)로 안 되는 컷에만 — 쓸지 말지는 사용자가 고른다(plan 스킬 '실사 · 느낌' 단계).

콘티 재료(장면의 materials):
  {"id": "walk", "type": "video", "gen": "seedance", "image_model": "seedream",
   "prompt": "…영어로 무엇이 일어나는가…", "cast": ["mina"], "camera": "slow push-in", "gen_sec": 5, "people": 1,
   "line": "클립 속 대사(있으면)", "in": 0.4, "out": 4.6, "fit": "cover", "end": "slow"}
콘티 최상위(선택) "cast": [{"name": "mina", "look": "20대 여성, 짧은 단발, 파란 티셔츠 …", "ref": "data/public/uploads/<id>/mina.png"}]
  → 장면마다 같은 인물이 나오도록 같은 외모 설명 · 기준 그림을 붙인다.
고른 느낌(direction.feel — engine/story/feel.py)이 있으면 그림 · 영상 프롬프트의 style · mood · color · lighting 이 된다.

이미지 먼저 → 영상(샷마다):
  1단계 그림: 키프레임 프롬프트 → <재료 id>.png 로 올림 → shotplan.py check(+ 에이전트가 직접 보고 확인)
  2단계 영상: 그 그림을 첫 프레임으로 → <재료 id>.mp4 로 올림 → shotplan.py check

  python3 engine/gen/genclip.py prompts data/storyboards/<id>.json [--model seedance] [--image-model seedream]
        → data/compositions/<id>/gen/prompts.md (사용자에게 그대로 보여 줄 문서)
  python3 engine/gen/genclip.py status data/storyboards/<id>.json      # 샷마다 어느 단계인가

오픈라우터 키가 있고 설정 → 모델 에서 '그리기' · '찍기' 모델을 골랐으면 Fluma 가 직접 만든다(비용 관문: 영상당 상한 안이면 그대로, 넘으면 사용자 승인 뒤 --approve):
  python3 engine/gen/genclip.py key data/storyboards/<id>.json [--mid walk] [--n 3] [--approve]   # 1단계: 키프레임 시안 n장 → 사용자에게 보여 준다
  python3 engine/gen/genclip.py pick-key data/storyboards/<id>.json <재료 id> <번호>             # 사용자가 고른 시안을 키프레임으로 — 사용자가 고를 때만
  python3 engine/gen/genclip.py run data/storyboards/<id>.json [--mid walk] [--approve]            # 2단계: 고른 키프레임 → 영상(작업이 끊겨도 다시 부르면 이어 받음)

올리는 곳: 편집기의 올리기 또는 data/public/uploads/<id>/ 에 이름에 재료 id 가 든 파일(walk.png · walk.mp4).
생성 클립이 든 영상은 업로드 때 '변경 · 합성 콘텐츠' 표시가 자동으로 켜진다(upload_youtube.py).
워터마크는 지우지 않는다 — 서비스 약관상 워터마크 없는 내보내기(유료 플랜)를 쓴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401


def gen_materials(sb: dict) -> list[tuple[int, dict]]:
    """(장면 번호 0부터, 재료) — 생성 클립 재료만"""
    out = []
    for i, sc in enumerate(sb.get("scenes") or []):
        for k, m in enumerate(sc.get("materials") or []):
            if isinstance(m, dict) and m.get("type") == "video" and m.get("gen"):
                out.append((i, {"id": m.get("id") or f"m{k + 1}", **m}))
    return out


def has_generated(sb: dict) -> bool:
    return bool(gen_materials(sb))


def clip_file(sid: str, m: dict) -> Path | None:
    from craft.materials import find_upload
    return find_upload(sid, {**m, "type": "video"})


def words(f: Path, a: float, b: float, work: Path, prompt: str | None = None) -> list[dict]:
    """클립 대사 받아쓰기 → [{text, startMs, endMs}] (구간 시작 기준). 결과는 work 에 캐시"""
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{f.stat().st_size}:{f.stat().st_mtime_ns}:{a}:{b}".encode()).hexdigest()[:12]
    cache = work / f"{f.stem}.{key}.words.json"
    if cache.exists():
        return json.loads(cache.read_text("utf-8"))
    wav = work / f"{f.stem}.{key}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(f), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    out = []
    try:
        from shorts_xray import speech
        for s in speech(wav, "base", prompt=prompt):
            for w in s.get("words") or []:
                if w.get("w"):
                    out.append({"text": w["w"], "startMs": int(w["s"] * 1000), "endMs": int(w["e"] * 1000)})
    except Exception as e:  # noqa: BLE001  (받아쓰기 모델 없음 등)
        print(f"[생성 클립] {f.name} 받아쓰기 실패 — 대사 확인 없이 진행: {e}")
    cache.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    wav.unlink(missing_ok=True)
    return out


def stage(sb: dict, sp: dict) -> str:
    """'그림' (키프레임 기다림) · '영상' (클립 기다림) · '완료'"""
    import shotplan
    m = next(m for _i, m in gen_materials(sb) if m["id"] == sp["id"])
    if clip_file(sb["id"], m):
        return "완료"
    return "영상" if shotplan.keyframe_file(sb["id"], sp["id"]) else "그림"


def _block(rows: list, r: dict, kind: str) -> None:
    rows += [f"#### 안 {r['variant']} — {r.get('title') or r['model']}", "```", r["prompt"], "```"]
    if r.get("negative"):
        rows += ["부정 프롬프트 칸:", "```", r["negative"], "```"]
    if r.get("references"):
        rows.append("올릴 참조: " + ", ".join(f"`{x}`" for x in r["references"]))
    st = r.get("settings") or {}
    if kind == "video":
        rows.append(f"설정: {st.get('duration', 0):g}초 · {st.get('aspect')}" + (" · 소리 켜기" if st.get("audio") else ""))
    elif st.get("how"):
        rows.append(f"설정: {st['how']}")
    for nt in r.get("notes") or []:
        rows.append(f"- ⚠ {nt}")
    rows.append("")


def prompts(sb: dict, model: str | None = None, image_model: str | None = None, n_variants: int = 3) -> str:
    """사용자가 자기 생성 도구에 그대로 붙여 넣을 문서 — 샷마다 1단계 그림 · 2단계 영상(지금 단계를 먼저)"""
    import shotplan
    from look import look
    lk = look(sb)
    sps = shotplan.specs(sb)
    fe = shotplan.feel_of(sb)
    cast = {c.get("name"): c for c in sb.get("cast") or [] if isinstance(c, dict)}
    sid = sb["id"]
    rows = [f"# 실사 생성 컷 — {sb.get('title') or sid}", "",
            "아래 프롬프트를 내 도구(Dreamina · Gemini · Midjourney …)에 붙여 넣어 만들고 올려 주세요. (오픈라우터 키를 넣고 설정에서 그리기 · 찍기 모델을 고르면 Fluma 가 직접 만듭니다.)",
            f"- **1단계 그림**: 키프레임을 만들어 `{sps[0]['id'] if sps else 'walk'}.png` 처럼 재료 id 이름으로 올림 → 확인",
            f"- **2단계 영상**: 그 그림을 시작 이미지로 넣고 영상 프롬프트로 만들어 `{sps[0]['id'] if sps else 'walk'}.mp4` 로 올림 → 확인",
            f"- 올리는 곳: 편집기의 올리기 또는 `data/public/uploads/{sid}/`. 워터마크 없는 내보내기 · 가장 높은 해상도",
            f"- 확인: `python3 engine/gen/shotplan.py check data/storyboards/{sid}.json` 이 설계와 다른 점과 고칠 문구를 준다", ""]
    if fe:
        rows += [f"## 고른 느낌 — {fe.get('name')}", "", f"- {fe.get('style_en') or ''} · {fe.get('mood_en') or ''} · {fe.get('color_en') or ''}".strip(" ·"), ""]
    if lk:
        rows += ["## 레퍼런스에서 잰 값(프롬프트에 반영됨)", "",
                 f"- 레퍼런스 {', '.join(lk['refs'])} · 샷 평균 {lk['shot_sec']}초({lk['pace']}) · 카메라 " + ", ".join(f"{k} {v}" for k, v in list(lk['camera_mix'].items())[:3]),
                 f"- 색 {lk['color']} · {lk['key']} · {lk['temperature']}" + (f" · 음악 {lk['bpm']:.0f} BPM" if lk.get("bpm") else ""), ""]
    if cast:
        rows += ["## 등장인물 — 모든 그림 · 클립에 같은 문구 · 같은 기준 그림", ""]
        for nm, c in cast.items():
            rows.append(f"- **{nm}**: {c.get('look') or ''}" + (f" — 기준 그림 `{c['ref']}`" if c.get("ref") else ""))
        rows.append("")
    for sp in sps:
        st = stage(sb, sp)
        sc = sb["scenes"][sp["scene"]]
        rows += [f"## {sp['scene'] + 1}장면 · `{sp['id']}` · 쓸 길이 {sp['duration']:g}초(앞뒤 여유 포함 {sp['request_sec']:g}초) — 지금: **{st}**", ""]
        if (sc.get("narration") or "").strip():
            rows += [f"- 나레이션(화면 밖 목소리, 클립에는 넣지 않음): {sc['narration'].strip()[:120]}", ""]
        if st == "완료":
            rows += ["클립이 올라와 있습니다. 다시 만들려면 아래 2단계를 다시.", ""]
        rows += ["### 1단계 — 키프레임 그림", ""]
        if sp.get("keyframe"):
            rows += [f"올라온 그림: `{sp['keyframe']}`", ""]
        for k in range(max(1, n_variants)):
            _block(rows, shotplan.compile_image(sp, image_model, k, lk), "image")
        rows += ["### 2단계 — 영상(키프레임을 시작 이미지로)", ""]
        if not sp.get("keyframe"):
            rows += ["> 그림을 올리면 이 단계 프롬프트가 '움직임 · 카메라 위주'로 바뀝니다(다시 `genclip.py prompts`).", ""]
        mdl = model or sp.get("gen") or "seedance"
        for k in range(max(1, n_variants)):
            r = shotplan.compile_prompt(sp, mdl, k, lk)
            if r.get("error"):
                rows += [f"> ⚠ {r['error']}", ""]
                break
            _block(rows, r, "video")
    return "\n".join(rows)


# ---------------------------------------------------------------- 오픈라우터로 직접 만들기(그림 시안 → 고르기 → 영상)
FAMILY = (("seedance", "seedance"), ("veo", "veo"), ("gemini-omni", "omni"), ("kling", "kling"), ("wan", "wan"), ("hailuo", "hailuo"),
          ("runway", "runway"), ("happyhorse", "wan"))


def family(model_id: str) -> str:
    """오픈라우터 모델 id → 프롬프트 문법 카드(engine/gen/models/cards). 카드가 없으면 일반 문법"""
    m = model_id.lower()
    return next((f for k, f in FAMILY if k in m), "generic")


def _sid_dirs(sb: dict) -> tuple[Path, Path]:
    g = ROOT / "data" / "compositions" / sb["id"] / "gen"
    up = ROOT / "data" / "public" / "uploads" / sb["id"]
    g.mkdir(parents=True, exist_ok=True)
    up.mkdir(parents=True, exist_ok=True)
    return g, up


def make_keys(sb: dict, mid: str | None = None, n: int = 3, approve: bool = False) -> list[str]:
    """1단계: 키프레임 시안 n장(설계대로 · 더 가까이 · 다른 각도) — 고르는 것은 사용자(pick-key)"""
    import catalog
    import openrouter as OR
    import shotplan
    from look import look
    model = catalog.chosen("make.image", sb)
    if not model:
        raise SystemExit("그리기 모델이 없습니다 — 설정 → 모델 → 그리기(키가 없으면 prompts 로 프롬프트만)")
    lk = look(sb)
    g, _up = _sid_dirs(sb)
    sps = [x for x in shotplan.specs(sb) if not mid or x["id"] == mid]
    each = catalog.estimate_image(model)
    total = None if each is None else round(each * n * len(sps), 4)
    catalog.guard(sb["id"], "make.image", model, total, f"키프레임 시안 {len(sps)}샷 × {n}장", approve)
    made = []
    for sp in sps:
        for k in range(n):
            r = shotplan.compile_image(sp, None, k % 3, lk)
            got = OR.make_image(model, r["prompt"], g / f"{sp['id']}-k{k + 1}", aspect=sp["aspect"])
            catalog.record(sb["id"], "make.image", model, got["cost"], f"{sp['id']} 키프레임 시안 {k + 1}", est=each)
            made.append(str(got["file"].relative_to(ROOT)))
    return made


def pick_key(sb: dict, mid: str, n: int) -> str:
    g, up = _sid_dirs(sb)
    src = next(iter(sorted(g.glob(f"{mid}-k{n}.*"))), None)
    if not src:
        raise SystemExit(f"시안 {mid}-k{n} 이 없습니다 — 먼저 key")
    for old in up.glob(f"{mid}.*"):
        if old.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            old.unlink()
    dst = up / f"{mid}{src.suffix}"
    dst.write_bytes(src.read_bytes())
    return str(dst.relative_to(ROOT))


def run(sb: dict, mid: str | None = None, approve: bool = False) -> list[str]:
    """2단계: 고른 키프레임을 첫 프레임으로 영상 — 작업 id 를 jobs.json 에 남겨 끊겨도 이어 받는다"""
    import catalog
    import openrouter as OR
    import shotplan
    from look import look
    model = catalog.chosen("make.video", sb)
    if not model:
        raise SystemExit("찍기 모델이 없습니다 — 설정 → 모델 → 찍기(키가 없으면 prompts 로 프롬프트만)")
    meta = next((m for m in catalog.raw().get("videos/models") or [] if m["id"] == model), {})
    lk = look(sb)
    g, up = _sid_dirs(sb)
    jobs_f = g / "jobs.json"
    jobs = json.loads(jobs_f.read_text("utf-8")) if jobs_f.exists() else {}
    done = []
    for sp in shotplan.specs(sb):
        if mid and sp["id"] != mid:
            continue
        if not sp.get("keyframe"):
            raise SystemExit(f"{sp['id']}: 키프레임이 없습니다 — 1단계(key → 사용자가 pick-key)부터")
        durs = meta.get("supported_durations") or []
        dur = min([d for d in durs if d >= sp["request_sec"] - 0.05] or [max(durs)] if durs else [round(sp["request_sec"])])
        res = "720p" if "720p" in (meta.get("supported_resolutions") or []) else ((meta.get("supported_resolutions") or [None])[0])
        audio = bool(sp.get("dialogue")) and bool(meta.get("generate_audio"))
        j = jobs.get(sp["id"])
        if not j or j.get("status") in ("failed", "downloaded") or j.get("model") != model:
            r = shotplan.compile_prompt(sp, family(model), 0, lk)
            if r.get("error"):
                raise SystemExit(r["error"])
            est = catalog.estimate_video(model, dur, res or "720p", audio)
            catalog.guard(sb["id"], "make.video", model, est, f"{sp['id']} 영상 {dur}초", approve)
            sub = OR.video_submit(model, r["prompt"], aspect=sp["aspect"], duration=dur, resolution=res, first_frame=ROOT / sp["keyframe"], audio=audio)
            j = {"job": sub["id"], "model": model, "est": est, "status": sub.get("status"), "prompt": r["prompt"]}
            jobs[sp["id"]] = j
            jobs_f.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), "utf-8")
            print(f"[생성] {sp['id']}: 작업 {j['job']} 시작 — {model} · {dur}초 · 예상 ${est if est is not None else '?'}")
        st = OR.video_wait(j["job"], on_tick=lambda x: print(f"[생성] {sp['id']}: {x.get('status')}", flush=True))
        j["status"] = st.get("status")
        if st.get("status") != "completed":
            jobs_f.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), "utf-8")
            raise SystemExit(f"{sp['id']}: 생성 실패 — {st.get('error') or st}")
        out = OR.video_download(j["job"], up / f"{sp['id']}.mp4")
        cost = (st.get("usage") or {}).get("cost")
        catalog.record(sb["id"], "make.video", model, cost, f"{sp['id']} 영상 {dur}초", est=j.get("est"), extra={"job": j["job"]})
        j["status"] = "downloaded"
        jobs_f.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), "utf-8")
        done.append(str(out.relative_to(ROOT)))
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("key", "run"):
        s = sub.add_parser(n); s.add_argument("storyboard"); s.add_argument("--mid"); s.add_argument("--approve", action="store_true", help="사용자가 금액을 보고 승인했을 때만")
        if n == "key":
            s.add_argument("--n", type=int, default=3)
    pk = sub.add_parser("pick-key"); pk.add_argument("storyboard"); pk.add_argument("mid"); pk.add_argument("n", type=int)
    for n in ("prompts", "status"):
        s = sub.add_parser(n); s.add_argument("storyboard")
        if n == "prompts":
            s.add_argument("--model", help="영상: seedance(dreamina) · kling · veo · omni · hailuo · runway · wan — 생략하면 재료의 gen")
            s.add_argument("--image-model", help="그림: seedream · nanobanana · gptimage · midjourney — 생략하면 재료의 image_model 또는 영상 모델과 짝")
            s.add_argument("--variants", type=int, default=3)
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads((sp if sp.is_absolute() else ROOT / sp).read_text("utf-8"))
    gm = gen_materials(sb)
    if not gm:
        print("생성 클립 재료가 없습니다(type: video + gen)")
        return 1
    if a.cmd in ("key", "run", "pick-key"):
        import catalog
        try:
            if a.cmd == "key":
                print("\n".join(make_keys(sb, a.mid, a.n, a.approve)))
            elif a.cmd == "pick-key":
                print(pick_key(sb, a.mid, a.n))
            else:
                print("\n".join(run(sb, a.mid, a.approve)))
        except catalog.NeedApproval as e:
            print(f"[승인 필요] {e}")
            return 20
        return 0
    if a.cmd == "prompts":
        out = ROOT / "data" / "compositions" / sb["id"] / "gen" / "prompts.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompts(sb, a.model, a.image_model, a.variants), "utf-8")
        print(f"{len(gm)}개 샷 → {out.relative_to(ROOT)}")
        return 0
    import shotplan
    from craft import vclip
    left = 0
    for sp_ in shotplan.specs(sb):
        st = stage(sb, sp_)
        m = next(m for _i, m in gm if m["id"] == sp_["id"])
        f = clip_file(sb["id"], m)
        extra = ""
        if f:
            p = vclip.probe(f)
            extra = f" · {f.relative_to(ROOT)} · {p['dur']:.1f}초 · {p['w']}×{p['h']}" + (" · 소리 있음" if p["audio"] else "")
        elif sp_.get("keyframe"):
            extra = f" · 그림 {sp_['keyframe']}"
        left += st != "완료"
        print(f"  {'✓' if st == '완료' else '·'} {sp_['scene'] + 1}장면 {sp_['id']}: {st if st != '완료' else '완료'}{' 기다림' if st != '완료' else ''}{extra}")
    print(f"완료 {len(gm) - left}/{len(gm)}")
    return 0 if not left else 10


if __name__ == "__main__":
    sys.exit(main())
