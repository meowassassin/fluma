#!/usr/bin/env python3
"""
렌더 진입점 (엔진 무관): 콘티 → 엔진(무음 영상) → 마무리(음성 + 필요하면 단어 자막) → data/out/

  python3 engine/render.py data/storyboards/<id>.json                      # 콘티의 engine/template, 없으면 기본(Craft)
  python3 engine/render.py data/storyboards/<id>.json --draft             # 미리보기용 초안 (빠름)
  python3 engine/render.py data/storyboards/<id>.json --build             # 렌더 없이 엔진 프로젝트만 (HTML 엔진 미리보기용)

엔진: Craft 파이프라인(재료 → EffectCraft → SoundCraft → FilmCraft). HyperFrames · Blender · Manim 은 2026-11-06 제거.

장면 일부만:
  python3 engine/render.py data/storyboards/<id>.json --scenes 3        # 3번 장면만 (1부터), 음성·자막도 그 구간
  python3 engine/render.py data/storyboards/<id>.json --scenes 2-4

마지막 줄에 결과 경로를 출력한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from engines import OUT, ROOT, adapter, make_job, scene_plan, segments, sub_job, template_meta  # noqa: E402
from finish import finish  # noqa: E402


def parse_scenes(arg: str, n: int) -> list[int]:
    a, _, b = arg.partition("-")
    lo, hi = int(a), int(b or a)
    if not 1 <= lo <= hi <= n:
        raise SystemExit(f"--scenes 는 1~{n} 범위: {arg}")
    return list(range(lo - 1, hi))


def ensure(eng_name: str):
    eng = adapter(eng_name)
    if not eng.available():
        raise SystemExit(f"{eng_name} 엔진이 설치되지 않았습니다 (engines/{eng_name}/engine.json 의 install 참고)")
    return eng


def conform(src: Path, dst: Path, w: int, h: int, fps: int, dur: float):
    """엔진마다 크기·fps·길이가 미세하게 다를 수 있어 이어 붙이기 전에 맞춘다 (모자라면 마지막 프레임을 늘림)."""
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration=2"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-an", "-vf", vf, "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(dst)], check=True)


def design_gate(a, sb: dict, sb_path: Path) -> None:
    """최종본 관문 — 아트 디렉션 · 다듬기 없이, 또는 초안이 디자인 검사에 크게 걸린 채로는 최종본을 내지 않는다. --force 로 넘길 수 있다"""
    if a.build or a.draft or a.scenes or a.force:
        return
    sys.path.insert(0, str(ROOT / "engine" / "checks"))
    from craft.design import art_problems
    from craft.refine import coverage
    from designcheck import findings
    bad = list(art_problems(sb))
    if not coverage(sb)["grid"]:
        bad.append("다듬은 장면이 없음(refine 0건)")
    draft = OUT / f"{sb['id']}-craft-Scenes-draft.mp4"
    if draft.exists():
        f = findings(draft, sb)
        n = max(1, len(sb.get("scenes") or []))
        empty = [x for x in f if x["code"] in ("D10", "D12")]
        if len(empty) * 2 > n:
            bad.append(f"빈 화면 · 작은 주인공이 {len(empty)}건(장면 {n}개)")
        bad += [x["msg"] for x in f if x["code"] in ("D14",)]
    if bad:   # 2026-11-09: 승인 · 다듬기를 강제하지 않는다(영상 한 편 10분) — 알리기만 하고 최종본을 낸다. 막으려면 FLUMA_STRICT_GATE=1
        msg = "최종본 관문 권고 — " + " / ".join(bad[:6]) + " (refine 스킬로 다듬으면 더 좋아진다)"
        if os.environ.get("FLUMA_STRICT_GATE"):
            sys.exit(msg)
        print(f"[관문] {msg}")


def gate_check(a, sid: str):
    """제작 관문(engine/checks/gate.py): 전체 최종 렌더는 사용자가 의도 카드와 시안(장면 1~3)을 확인한 뒤에만"""
    if a.build or a.draft or a.scenes:
        return
    g = subprocess.run([sys.executable, str(ROOT / "engine" / "checks" / "gate.py"), "check", sid, "--for", "render"], capture_output=True, text=True)
    if g.returncode != 0:   # 의도 카드 · 시안 승인을 기다리지 않는다(알리기만) — 막으려면 FLUMA_STRICT_GATE=1
        msg = g.stderr.strip() or f"제작 관문 — python3 engine/checks/gate.py status {sid}"
        if os.environ.get("FLUMA_STRICT_GATE"):
            sys.exit(msg)
        print(f"[관문] {msg.splitlines()[-1] if msg else ''} — 승인 없이 진행")


def density(sb: dict, sb_path: Path, video: Path):
    """초안 전체를 사람 편집 기준(engine/spec/presets/density.json)과 견준다 → data/workspace/render/<id>/density.json (lint L28 · 최종 렌더 관문이 읽는다)"""
    import hashlib
    root = Path(__file__).resolve().parents[1]
    sid = sb["id"]
    js = root / "data" / "compositions" / sid / "scene.js"
    r = subprocess.run([sys.executable, str(root / "engine" / "checks" / "edit_density.py"), str(video), "--check", str(sb_path), "--json"], capture_output=True, text=True)
    try:
        m = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    except (IndexError, json.JSONDecodeError):
        print(f"[편집 밀도] 재지 못함: {r.stderr[-300:]}"); return
    m["scene_js_sha"] = hashlib.sha1(js.read_bytes()).hexdigest()[:12] if js.exists() else None
    m["allowed"] = bool((sb.get("intent") or {}).get("density_ok"))   # 사용자가 의도 카드에서 '단순한 화면이 맞다'고 정한 경우만
    dp = root / "data" / "workspace" / "render" / sid / "density.json"
    dp.parent.mkdir(parents=True, exist_ok=True)
    dp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[편집 밀도] 글자 {m.get('text_px')}px · 재료 {m.get('kinds')}가지 · 재료 전환 {m.get('kind_switch')}/10초 · 최장 정지 {m.get('longest_still')}초")
    for x in m.get("problems") or []:
        print(f"   ✗ {x}")


def render_mix(a, sb_path: Path):
    base = make_job(sb_path, a.engine, a.template, a.draft)
    overrides = [x if x not in ("", "-") else None for x in a.engines.split(",")] if a.engines else None
    plan = scene_plan(base.sb, a.engine, a.template, overrides)
    segs = segments(plan)
    sel, t_sel = None, 0.0
    if a.scenes:   # 일부 장면만: 묶음을 그 범위로 자르고, 음성 · 자막은 그 구간만
        sel = parse_scenes(a.scenes, len(base.sb["scenes"]))
        segs = [(e, t, [i for i in ix if i in sel]) for e, t, ix in segs]
        segs = [x for x in segs if x[2]]
        t_sel = base.scenes[sel[0]]["start"]
    print("[캐스팅] " + " | ".join(f"{e}/{t} 장면 {ix[0] + 1}{'-' + str(ix[-1] + 1) if len(ix) > 1 else ''}" for e, t, ix in segs))
    parts, ranges, manifest = [], [], []
    mixdir = base.work.parent.parent / "mix"
    mixdir.mkdir(parents=True, exist_ok=True)
    for k, (e, t, ix) in enumerate(segs):
        eng = ensure(e)
        sj = sub_job(make_job(sb_path, e, t, a.draft), ix)
        t0 = base.scenes[ix[0]]["start"]
        started = time.time()
        print(f"[묶음 {k + 1}/{len(segs)}] {e} · {t} · 장면 {ix[0] + 1}–{ix[-1] + 1} · {sj.duration:.1f}s")
        silent = eng.render(sj)
        part = mixdir / f"part{k:02d}-{e}-{t}-s{ix[0] + 1}-{ix[-1] + 1}{'-draft' if a.draft else ''}.mp4"
        conform(Path(silent), part, base.width, base.height, base.fps, sj.duration)
        parts.append(part)
        selfcap = template_meta(sj).get("captions", "finish") == "self"
        if not selfcap:
            ranges.append((t0 - t_sel, t0 - t_sel + sj.duration))
        manifest.append({"engine": e, "template": t, "scenes": [i + 1 for i in ix], "start": t0, "sec": sj.duration,
                         "captions": "self" if selfcap else "finish", "render_s": round(time.time() - started, 1)})
    lst = mixdir / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    silent = mixdir / f"silent{'-draft' if a.draft else ''}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent)], check=True)
    tag = f"-s{sel[0] + 1}-{sel[-1] + 1}" if sel else ""
    out = Path(a.out) if a.out else OUT / f"{base.sb['id']}-mix{tag}{'-draft' if a.draft else ''}.mp4"
    kw = {"offset": t_sel, "scenes": sel} if sel else {}
    finish(silent, base.sb, out, burn_captions=bool(ranges), tokens=base.tokens, burn_ranges=ranges, **kw)
    out.with_suffix(".mix.json").write_text(json.dumps({"storyboard": str(sb_path), "draft": a.draft, "segments": manifest}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[완료] {out}")
    done(out, a)


def craft_finish(job, silent: Path, out: Path) -> bool:
    """Craft 엔진: 소리는 SoundCraft 세션으로 섞고, 조립은 FilmCraft 프로젝트로 — 단계마다 열어 고칠 수 있는 파일이 남는다.
    앱이 없거나 실패하면 False(기존 ffmpeg 마무리로)"""
    from craft.audio import mix
    from craft.edit import assemble
    au = mix(job.sb, job.duration)
    if not au:
        return False
    print(f"[소리] SoundCraft 세션 {au[0].relative_to(ROOT) if str(au[0]).startswith(str(ROOT)) else au[0]}")
    done = assemble(job.sb, silent, au[1], out, fps=job.fps, width=job.width, height=job.height)
    if done:
        print("[조립] FilmCraft 프로젝트 data/compositions/" + job.sb["id"] + "/craft/edit/")
    return bool(done)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--engine")
    ap.add_argument("--template")
    ap.add_argument("--engines", help="장면 순서대로 엔진 (쉼표, '-' = 기본). 장면마다 엔진 섞기")
    ap.add_argument("--scenes", help="이 장면만 렌더 (1부터, 예: 3 또는 2-4)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--force", action="store_true", help="최종본 디자인 관문을 알고 넘긴다")
    ap.add_argument("--build", action="store_true", help="렌더하지 않고 엔진 프로젝트만 만든다")
    ap.add_argument("--out", help="출력 경로")
    ap.add_argument("--size", choices=["720", "1080", "1440", "2160"], default="1080", help="출력 세로 해상도(9:16). 1440 · 2160 은 화면을 그만큼 크게 그려서(글자 · 도형이 실제로 선명) 뽑는다")
    ap.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], help="출력 비율(기본: 콘티 aspect, 없으면 9:16). --size 는 짧은 변 기준")
    ap.add_argument("--quality", choices=["standard", "high", "max"], default="high", help="화질(용량): standard CRF 21 · high 18 · max 15")
    ap.add_argument("--fps", type=int, choices=[30, 60], help="초당 프레임(기본: 디자인 토큰, 보통 30)")
    a = ap.parse_args()
    # 엔진 어댑터(화면 배율) · 마무리 인코딩(출력 크기 · CRF)이 읽는다
    os.environ["FLUMA_RENDER_SCALE"] = {"1440": "1.3333333", "2160": "2"}.get(a.size, "1")
    if a.aspect:
        os.environ["FLUMA_ASPECT"] = a.aspect
    _asp = a.aspect or json.loads(Path(a.storyboard).read_text(encoding="utf-8")).get("aspect") or "9:16"
    # 출력 세로 크기: --size 는 짧은 변 — 9:16 이면 세로가 16/9 배, 16:9 · 1:1 이면 세로 = 짧은 변
    os.environ["FLUMA_OUT_H"] = str({"720": 1280, "1080": 1920, "1440": 2560, "2160": 3840}[a.size] if _asp == "9:16" else int(a.size))
    os.environ["FLUMA_CRF"] = {"standard": "21", "high": "18", "max": "15"}[a.quality]
    sb_path = Path(a.storyboard)

    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    mixed = a.engines or (not a.engine and any(s.get("engine") for s in sb["scenes"]))
    gate_check(a, sb["id"])
    design_gate(a, sb, sb_path)
    if mixed and not a.build:
        return render_mix(a, sb_path)

    job = make_job(sb_path, a.engine, a.template, a.draft)
    if a.fps:
        job.fps = a.fps
    from engines import aspect_tag
    tag = ("" if a.size == "1080" else f"-{a.size}p") + aspect_tag(job.sb)
    if a.scenes:
        ix = parse_scenes(a.scenes, len(job.sb["scenes"]))
        offset, job = job.scenes[ix[0]]["start"], sub_job(job, ix)
        tag += f"-s{ix[0] + 1}" + (f"-{ix[-1] + 1}" if len(ix) > 1 else "")
    eng = ensure(job.engine)
    print(f"[엔진] {job.engine} · 템플릿 {job.template} · {job.duration:.1f}s{' · 초안' if a.draft else ''}{' · 장면 ' + a.scenes if a.scenes else ''}")
    if a.build:
        print(eng.build(job))
        return
    silent = eng.render(job)
    meta = template_meta(job)
    out = Path(a.out) if a.out else OUT / f"{job.sb['id']}-{job.engine}-{job.template}{tag}{'-draft' if a.draft else ''}.mp4"
    kw = {"offset": offset, "scenes": ix} if a.scenes else {}
    if not (job.engine == "craft" and not a.scenes and craft_finish(job, Path(silent), out)):
        finish(silent, job.sb, out, burn_captions=meta.get("captions", "finish") != "self", tokens=job.tokens, **kw)
    print(f"[완료] {out}")
    if a.draft and not a.scenes and not os.environ.get("FLUMA_PREVIZ"):   # 미리 보기는 편집 밀도를 재지 않는다(자리표시 카드라)
        density(job.sb, sb_path, out)
        critique(job.sb, out)
    if not a.scenes and not os.environ.get("FLUMA_PREVIZ"):   # 템포(첫 1초 · 멈춤 · 말 끊김 · 컷 밀도) — 넘기지 않고 보게 하는 기본기
        try:
            import tempo_check
            t = tempo_check.check(out)
            t["id"] = job.sb["id"]
            tempo_check.save(job.sb["id"], t)
            print(f"[템포] 첫 컷 {t['first_cut']}초 · 컷 {t['cuts_per_10s']}/10초 · 최장 멈춤 {t['longest_freeze']}초 · 첫 1초 변화 {t['first_second_change']}")
            narrated = any(str(s.get("narration") or "").strip() for s in job.sb.get("scenes") or [])
            for code, msg in tempo_check.problems(t, narrated, job.sb):
                print(f"   {'✗' if code.startswith('L') else '△'} {code} {msg}")
        except Exception as e:   # 검사 실패가 렌더를 막지 않게
            print(f"[템포] 검사하지 못함: {e}")
    done(out, a)


def critique(sb: dict, out: Path) -> None:
    """초안이 나오면 보기(VL) 모델이 바로 본다 — 계획(전환 · 글자 · 연출)이 실제로 화면에 나왔는지, 어색한 곳은 어디인지.
    2026-11-09: 계획한 '끊김 없는 줌' · 큰 세리프 글자가 초안에서 빠졌는데 아무도 몰랐다(비평이 초안 파일 이름을 못 찾아 돌지 않음).
    보기 모델이 없거나 한도를 넘으면 건너뛴다(렌더는 그대로)."""
    sys.path.insert(0, str(ROOT / "engine" / "providers"))
    try:
        import catalog
        import see
        if not catalog.chosen("see.video", sb):
            # 조용히 건너뛰지 않는다 — 2026-11-09 영상은 보기 모델이 꺼져 있어 초안 32번 동안 비평이 한 번도 안 돌았는데 아무도 몰랐다
            print("[VL 비평] 꺼짐 — 설정 → 보기 · 말하기 에서 '영상 이해' 모델을 고르면 초안마다 움직임 · 호흡을 봅니다(지금은 정지 화면만 확인)", flush=True)
            return
        print("[VL 비평] 보기 모델이 초안을 봅니다…", flush=True)
        d = see.critique(sb["id"], str(out))
    except SystemExit as e:
        print(f"[VL 비평] 건너뜀: {e}"); return
    except Exception as e:  # noqa: BLE001 — 승인 필요 · 네트워크 · 모델 오류가 렌더를 막지 않게
        print(f"[VL 비평] 건너뜀: {str(e)[:300]}"); return
    issues = sorted(d.get("issues") or [], key=lambda i: {"high": 0, "mid": 1}.get(i.get("severity"), 2))
    print(f"[VL 비평] {str(d.get('overall') or '')[:400]}")
    an = d.get("anchor") if isinstance(d.get("anchor"), dict) else None
    if an:
        print(f"   기준점 {an.get('score')}/10 — 다른 점: {' · '.join(str(x) for x in an.get('misses') or []) or '없음'}")
    for i in issues[:10]:
        t = i.get("t") or []
        when = f"{t[0]}~{t[1]}초" if isinstance(t, list) and len(t) == 2 else ""
        print(f"   {'✗' if i.get('severity') == 'high' else '△'} 장면 {i.get('scene', '?')} {when} {i.get('what', '')} → {i.get('fix', '')}")
    print(f"   전체: data/workspace/critique/{sb['id']}.json — high 부터 고치고 다시 초안 렌더")


def done(out, a) -> None:
    """결과 규약(engine/core/result.py): FLUMA_RESULT 블록 — 서버 · 에이전트가 이 블록의 file 을 읽는다"""
    from result import ok
    p = Path(out).resolve()
    try:
        rel = str(p.relative_to(Path(__file__).resolve().parents[1]))
    except ValueError:
        rel = str(p)
    kind = "초안" if a.draft else "최종"
    ok("render", file=rel, media=[f"{rel} | {kind} 렌더"], draft=str(bool(a.draft)).lower())


if __name__ == "__main__":
    from result import run_main
    run_main("render", main)
