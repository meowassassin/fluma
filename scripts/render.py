#!/usr/bin/env python3
"""
렌더 진입점 (엔진 무관): 콘티 → 엔진(무음 영상) → 마무리(음성 + 필요하면 단어 자막) → out/

  python3 scripts/render.py storyboards/<id>.json                      # 콘티의 engine/template, 없으면 기본(HyperFrames, 자동 템플릿)
  python3 scripts/render.py storyboards/<id>.json --draft             # 미리보기용 초안 (빠름)
  python3 scripts/render.py storyboards/<id>.json --build             # 렌더 없이 엔진 프로젝트만 (HTML 엔진 미리보기용)

엔진: 모든 장면을 HyperFrames 가 합성한다(2026-10-29, ADR-0011). Manim · Blender · 생성 모델은 scripts/element.py 로 만든
레이어 요소를 scene.js 가 장면 안에 겹친다. (예전 장면별 엔진 섞기 경로는 남아 있지만 HyperFrames 밖의 장면 엔진은 없다.)

장면 일부만:
  python3 scripts/render.py storyboards/<id>.json --scenes 3        # 3번 장면만 (1부터), 음성·자막도 그 구간
  python3 scripts/render.py storyboards/<id>.json --scenes 2-4

마지막 줄에 결과 경로를 출력한다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
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


def gate_check(a, sid: str):
    """제작 관문(scripts/gate.py): 전체 최종 렌더는 사용자가 의도 카드와 시안(장면 1~3)을 확인한 뒤에만"""
    if a.build or a.draft or a.scenes:
        return
    g = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "gate.py"), "check", sid, "--for", "render"], capture_output=True, text=True)
    if g.returncode != 0:
        sys.exit(g.stderr.strip() or f"제작 관문에서 막혔습니다 — python3 scripts/gate.py status {sid}")
    # 'AI 티' 화면 검사(look_check.py): 실패한 화면으로 최종 렌더하지 않는다. 결과가 없거나 장면 파일이 바뀌었으면 여기서 다시 잰다
    root = Path(__file__).resolve().parents[1]
    js = root / "compositions" / sid / "scene.js"
    lc = root / "workspace" / "render" / sid / "look-check.json"
    if js.exists():
        import hashlib
        sha = hashlib.sha1(js.read_bytes()).hexdigest()[:12]
        fresh = lc.exists() and json.loads(lc.read_text(encoding="utf-8")).get("scene_js_sha") == sha
        if not fresh:
            allow = json.loads(lc.read_text(encoding="utf-8")).get("allow", []) if lc.exists() else []
            subprocess.run([sys.executable, str(root / "scripts" / "look_check.py"), str(root / "storyboards" / f"{sid}.json"), *(["--allow", ",".join(allow)] if allow else [])], capture_output=True, text=True)
        r = json.loads(lc.read_text(encoding="utf-8")) if lc.exists() else {"ok": True}
        if not r.get("ok"):
            sys.exit(f"'AI 티' 화면 검사에서 막혔습니다: {', '.join(r.get('categories', {}))} — python3 scripts/look_check.py storyboards/{sid}.json 로 확인하고 고치세요")
        # 편집 밀도(edit_density.py): 초안 렌더에서 잰 '슬라이드 같음'(작은 글자 · 재료 한 종류 · 재료 전환 없음)이 남아 있으면 최종 렌더하지 않는다
        dp = root / "workspace" / "render" / sid / "density.json"
        d = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else None
        if not d or d.get("scene_js_sha") != sha:
            sys.exit(f"편집 밀도를 아직 안 쟀습니다(화면이 바뀐 뒤) — 먼저 초안: python3 scripts/render.py storyboards/{sid}.json --draft")
        if d.get("problems") and not d.get("allowed"):
            sys.exit("편집 밀도가 사람 편집 기준에 모자랍니다:\n  " + "\n  ".join(d["problems"]) + "\n고친 뒤 초안을 다시 렌더하세요")


def density(sb: dict, sb_path: Path, video: Path):
    """초안 전체를 사람 편집 기준(presets/density.json)과 견준다 → workspace/render/<id>/density.json (lint L28 · 최종 렌더 관문이 읽는다)"""
    import hashlib
    root = Path(__file__).resolve().parents[1]
    sid = sb["id"]
    js = root / "compositions" / sid / "scene.js"
    r = subprocess.run([sys.executable, str(root / "scripts" / "edit_density.py"), str(video), "--check", str(sb_path), "--json"], capture_output=True, text=True)
    try:
        m = json.loads([ln for ln in r.stdout.splitlines() if ln.startswith("{")][-1])
    except (IndexError, json.JSONDecodeError):
        print(f"[편집 밀도] 재지 못함: {r.stderr[-300:]}"); return
    m["scene_js_sha"] = hashlib.sha1(js.read_bytes()).hexdigest()[:12] if js.exists() else None
    m["allowed"] = bool((sb.get("intent") or {}).get("density_ok"))   # 사용자가 의도 카드에서 '단순한 화면이 맞다'고 정한 경우만
    dp = root / "workspace" / "render" / sid / "density.json"
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
        print("[조립] FilmCraft 프로젝트 compositions/" + job.sb["id"] + "/craft/edit/")
    return bool(done)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--engine")
    ap.add_argument("--template")
    ap.add_argument("--engines", help="장면 순서대로 엔진 (쉼표, '-' = 기본). 장면마다 엔진 섞기")
    ap.add_argument("--scenes", help="이 장면만 렌더 (1부터, 예: 3 또는 2-4)")
    ap.add_argument("--draft", action="store_true")
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
    # 화면 구성 없이 렌더하면 안내 화면이 영상에 박힌다 → 렌더 · 초안은 막는다(미리보기 빌드는 콘티 미리보기로 허용)
    cdir = Path(__file__).resolve().parents[1] / "compositions" / job.sb["id"]
    if not os.environ.get("FLUMA_PREVIZ") and job.template == "Composed" and not a.build and not (cdir / "scene.js").exists() and not (cdir / "graph.js").exists():   # 설계도만으로 된 영상(graph.js)도 허용
        sys.exit(f"화면 구성이 아직 없습니다: compositions/{job.sb['id']}/scene.js — 홈의 '제작 시작'이나 에이전트에게 \"화면을 짜 줘\"(compose 스킬)를 먼저 하세요")
    # 장면 설계도의 에셋 권리: 참고용(분해도 누끼 등) · 권리 미상 에셋을 쓰는 노드가 있으면 최종 렌더를 막는다(초안 · 미리보기는 허용)
    gp = Path(__file__).resolve().parents[1] / "scenes" / f"{job.sb['id']}.scene.json"
    if gp.exists() and not a.build and not a.draft and json.loads(gp.read_text(encoding="utf-8")).get("fidelity") == "sketch":
        print("[애니메틱] 설계도가 스케치 단계 — 연필 밑그림 영상으로 렌더합니다(참고용 에셋 허용, 공개용 아님)")
    elif gp.exists() and not a.build and not a.draft:
        g = json.loads(gp.read_text(encoding="utf-8")); assets = g.get("assets") or {}
        used = {n["asset"] for sc in g.get("scenes", []) for n in sc.get("nodes", []) if n.get("asset")}
        bad = [f"{k}({assets[k].get('src')}) — {assets[k].get('rights', {}).get('status', 'unknown')}" for k in sorted(used)
               if k in assets and assets[k].get("rights", {}).get("status", "unknown") in ("reference-only", "unknown")]
        if bad:
            sys.exit("쓸 권리가 확인되지 않은 에셋이 있어 최종 렌더를 멈춥니다:\n  " + "\n  ".join(bad) + "\n설계도에서 rights 를 own · licensed · cc0 · cc-by · generated 로 확인하거나 그 노드를 빼세요")
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
    if not a.scenes and not os.environ.get("FLUMA_PREVIZ"):   # 템포(첫 1초 · 멈춤 · 말 끊김 · 컷 밀도) — 넘기지 않고 보게 하는 기본기
        try:
            import tempo_check
            t = tempo_check.check(out)
            t["id"] = job.sb["id"]
            tempo_check.save(job.sb["id"], t)
            print(f"[템포] 첫 컷 {t['first_cut']}초 · 컷 {t['cuts_per_10s']}/10초 · 최장 멈춤 {t['longest_freeze']}초 · 첫 1초 변화 {t['first_second_change']}")
            narrated = any(str(s.get("narration") or "").strip() for s in job.sb.get("scenes") or [])
            for code, msg in tempo_check.problems(t, narrated):
                print(f"   {'✗' if code.startswith('L') else '△'} {code} {msg}")
        except Exception as e:   # 검사 실패가 렌더를 막지 않게
            print(f"[템포] 검사하지 못함: {e}")
    done(out, a)


def done(out, a) -> None:
    """결과 규약(scripts/result.py): FLUMA_RESULT 블록 — 서버 · 에이전트가 이 블록의 file 을 읽는다"""
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
