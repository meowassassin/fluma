"""
HyperFrames 엔진 어댑터: 콘티 + 룩 → HTML 컴포지션 프로젝트 → (render) 무음 MP4 / (snapshot) PNG.

프로젝트 폴더 = job.work (workspace/render/<id>/hyperframes/<템플릿>/):
  index.html   콘티·토큰·장면 타이밍·단어 자막을 window.SF 로 인라인. 템플릿 CSS·JS 를 이어 붙임
  gsap.min.js  sf.js  fonts/  captures/…   (렌더 중 네트워크를 쓰지 않도록 전부 로컬 복사)
웹 미리보기는 이 index.html 을 iframe 으로 띄우고 window.__sfSeek(t) 로 시간을 넘긴다.
"""
import html
import json
import os
import shutil
import subprocess
from pathlib import Path

import re

from engines import PUBLIC, ROOT, copy_public, engine_env, run, used_assets  # noqa: E402

HERE = Path(__file__).resolve().parent
BIN = HERE / "node_modules" / ".bin" / "hyperframes"
GSAP = HERE / "node_modules" / "gsap" / "dist" / "gsap.min.js"


def _previz_srcs(sb: dict) -> list[str]:
    """미리 보기가 쓰는 재료 경로(있는 것만) — 아래 복사 규칙이 문자열에서 찾도록 넣는다"""
    out = []
    for sc in sb.get("scenes", []):
        for x in [(sc.get("visual") or {}).get("src"), *[b.get("src") for b in sc.get("beats") or []]]:
            if x:
                out.append(x)
    return out


def available():
    return BIN.exists() and GSAP.exists()


def _css_vars(t: dict) -> str:
    c = t["color"]
    return (f":root{{--bg:{c['bg']};--surface:{c['surface']};--text:{c['text']};--muted:{c['muted']};"
            f"--accent:{c['accent']};--caption:{c.get('caption') or c['text']};--good:{c['good']};--bad:{c['bad']};}}")


def build(job) -> Path:
    """index.html 과 자산을 job.work 에 만든다. 미리보기도 이것을 쓴다."""
    proj = job.work
    tdir = HERE / "templates" / job.template
    for f in (GSAP, HERE / "lib" / "sf.js", HERE / "lib" / "kit.js"):
        shutil.copy2(f, proj / f.name)
    fonts = proj / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in [*(PUBLIC / "fonts").glob("*.woff2"), *(PUBLIC / "fonts").glob("*.ttf"), *(PUBLIC / "fonts").glob("JetBrains*.otf")]:
        if not (fonts / f.name).exists():
            shutil.copy2(f, fonts / f.name)
    assets = [a for a in used_assets(job.sb) if (PUBLIC / a).exists()]
    copy_public(assets, proj)
    css = "\n".join(p.read_text(encoding="utf-8") for p in sorted(tdir.glob("*.css")))
    js = "\n".join(p.read_text(encoding="utf-8") for p in sorted(tdir.glob("*.js")))
    if job.template == "Composed":
        # 영상마다 짠 컴포지션: compositions/<id>/scene.js (+ style.css) 를 템플릿 앞에 붙이고, 쓰는 자산을 복사
        cdir = ROOT / "compositions" / job.sb["id"]
        own = "\n".join(p.read_text(encoding="utf-8") for p in sorted(cdir.glob("*.js"))) if cdir.exists() else ""
        # 미리 보기(scripts/previz.py render): 장면 코드 대신 콘티만으로 짜는 화면 — 재료가 없으면 회색 카드
        if os.environ.get("FLUMA_PREVIZ"):
            own = (Path(__file__).parent / "previz.js").read_text(encoding="utf-8")
            own += "\n" + "".join(f'void "{x}";' for x in _previz_srcs(job.sb))
        css += "\n" + ("\n".join(p.read_text(encoding="utf-8") for p in sorted(cdir.glob("*.css"))) if cdir.exists() else "")
        ovr = cdir / "overrides.json"
        ovr_data = {}
        if ovr.exists():   # 빈 파일 · 깨진 JSON 이어도 페이지 스크립트가 통째로 죽지 않게
            try:
                ovr_data = json.loads(ovr.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                ovr_data = {}
        js = own + "\n" + (f"window.FLUMA_OVR = {json.dumps(ovr_data, ensure_ascii=False)};\n" if ovr_data else "") + js
        refs = set(re.findall(r"[\"'`]((?:captures|trends|stills|images|audio|fonts|uploads)/[^\"'`]+?\.(?:png|jpe?g|webp|svg|gif))[\"'`]", own))
        copy_public([r for r in refs if (PUBLIC / r).exists()], proj)
        # 연속 이미지(K.seq): 레이어 요소(scripts/element.py) · 올린 영상 프레임 폴더를 통째로 복사하고, meta 를 페이지에 넣는다
        seqs = {}
        for rel in set(re.findall(r"[\"'`]((?:elements|uploads)/[A-Za-z0-9가-힣_.-]+/[A-Za-z0-9가-힣_.-]+)[\"'`]", own)):
            src = PUBLIC / rel
            if src.is_dir():
                shutil.copytree(src, proj / rel, dirs_exist_ok=True)
                mp = src / "meta.json"
                if mp.exists():
                    seqs[rel] = json.loads(mp.read_text(encoding="utf-8"))
        if seqs:
            js = f"window.SF_SEQ = {json.dumps(seqs, ensure_ascii=False)};\n" + js
        for ch in set(re.findall(r"[\"'`]characters/([a-z0-9-]+)/", own)):
            src = ROOT / "characters" / ch
            if src.exists():
                shutil.copytree(src, proj / "characters" / ch, dirs_exist_ok=True)
        for f in (cdir.glob("*") if cdir.exists() else []):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                shutil.copy2(f, proj / f.name)
    data = {"sb": job.sb, "tokens": job.tokens, "scenes": job.scenes, "captions": job.captions,
            "duration": job.duration, "fps": job.fps, "assets": assets}
    dur = f"{job.duration:.3f}"
    # 고해상도 출력(1440 · 2160): 1080×1920 으로 짠 화면을 그대로 두고 통째로 키워 그 크기로 찍는다 → 글자 · 도형이 실제로 선명
    scale = float(os.environ.get("FLUMA_RENDER_SCALE", "1") or 1) if not job.draft else 1.0
    rw, rh = round(1080 * scale), round(1920 * scale)
    zoom_css = f"html, body {{ margin: 0; width: {rw}px; height: {rh}px; overflow: hidden; }} #root {{ transform: scale({scale}); transform-origin: 0 0; }}" if scale != 1 else ""
    page = f"""<!doctype html>
<html lang="ko" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={rw}, height={rh}" />
<title>{html.escape(job.sb.get('title', job.sb['id']))}</title>
<script src="gsap.min.js"></script>
<style>
{css}
{_css_vars(job.tokens)}
{zoom_css}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{rw}" data-height="{rh}"></div>
<script>window.SF = {json.dumps(data, ensure_ascii=False)};</script>
<script src="sf.js"></script>
<script src="kit.js"></script>
<script>
{js}
</script>
</body>
</html>
"""
    (proj / "index.html").write_text(page, encoding="utf-8")
    (proj / "meta.json").write_text(json.dumps({"id": job.sb["id"], "name": job.sb.get("title", job.sb["id"])}, ensure_ascii=False), encoding="utf-8")
    return proj / "index.html"


def render(job) -> Path:
    build(job)
    out = job.work / "silent.mp4"
    # 중간 파일은 거의 무손실(CRF 12) — 마무리 인코딩(finish)에서 한 번만 원하는 화질로 줄인다
    cmd = [BIN, "render", "-o", out, "--fps", str(job.fps), "-q", "draft" if job.draft else "standard", *([] if job.draft else ["--crf", "12"]), "--quiet"]
    run(cmd, cwd=job.work, env=engine_env("hyperframes"), label="hyperframes render")
    return out


def snapshot(job, seconds: list[float]) -> list[Path]:
    """호출마다 따로 폴더를 쓴다 (웹 썸네일과 에이전트 정지 화면이 동시에 돌아도 섞이지 않게). 프레임 번호 순서 = seconds 순서."""
    import tempfile
    build(job)
    snaps = Path(tempfile.mkdtemp(prefix="snaps-", dir=job.work))
    at = ",".join(f"{max(0.0, min(job.duration - 0.05, s)):.2f}" for s in seconds)
    r = run([BIN, "snapshot", "--at", at, "-o", snaps, "--no-end", "--json"], cwd=job.work, env=engine_env("hyperframes"), label="hyperframes snapshot")
    pngs = sorted(snaps.glob("frame-*.png"), key=lambda p: int(re.search(r"frame-(\d+)", p.name).group(1))) or sorted(snaps.glob("*.png"))
    if not pngs:
        raise SystemExit("스냅샷 없음:\n" + r.stdout[-800:])
    # 오래된 스냅샷 폴더 정리 (최근 6개만)
    olds = sorted(job.work.glob("snaps-*"), key=lambda p: p.stat().st_mtime)[:-6]
    for o in olds:
        shutil.rmtree(o, ignore_errors=True)
    return pngs
