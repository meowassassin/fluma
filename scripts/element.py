#!/usr/bin/env python3
"""
레이어 요소 — 한 장면 안에서 여러 엔진 · 생성 모델을 섞는다.

HyperFrames 컴포지션(scene.js)이 합성기다. 다른 엔진 · 모델은 '요소'를 만들고, scene.js 가 K.seq 로 같은 시간축에 겹친다:
  public/elements/<id>/<이름>/f0001.png …  + meta.json {frames, fps, ext, pad, w, h, bbox, transparent, role, engine, model, license}

  # 생성 모델: 첫 프레임 그림(글 → 그림) → 영상(그림 → 영상). --role plate = 장면 뒤 배경판, element = 투명 요소(--cutout)
  python3 scripts/element.py gen <id> <이름> --image-prompt "그림 설명" --prompt "움직임 설명" [--sec 4] [--role plate|element]
          [--image 그림.png] [--model wan22,ltx23] [--cutout [u2net|isnet-anime]] [--pingpong] [--size 576x1024]
  # 만화 사이 그림(키 그림 두 장, ToonCrafter)
  python3 scripts/element.py interp <id> <이름> --image a.png --image2 b.png --prompt "동작" [--cutout]
  # 그림 한 장 (움직임은 scene.js 에서 K 로)
  python3 scripts/element.py image <id> <이름> --image-prompt "그림 설명" [--cutout] [--size 768x768]
  # Blender 개체 하나(움직이는 사물 · 동물 · 사람): compositions/<id>/blender/<이름>.py 의 def build(ctx) — 모델은 scripts/asset3d.py fetch
  python3 scripts/element.py blender <id> <이름> [--script …] [--sec 4] [--size 1080x1080] [--still 0.5,2] [--draft]
  # Manim 투명 요소: compositions/<id>/manim/<이름>.py 의 class Main(Scene)
  python3 scripts/element.py manim <id> <이름> [--scene N] [--script compositions/<id>/manim/<이름>.py] [--sec 4] [--size 1080x1080] [--draft]
  #   --scene N: 그 장면 길이 · 나레이션 단어 타이밍을 SF_STYLE["words"] 로 → 스크립트가 cue("S3") 로 말에 맞춰 움직임
  # 이미 있는 영상 · 그림을 요소로 (배경 제거 가능)
  python3 scripts/element.py import <id> <이름> --src 파일 [--cutout] [--pingpong] [--model wan22]
  python3 scripts/element.py list <id>
  # 재사용 라이브러리(library3d/): 한 번 렌더한 3D 개체 · 요소를 저장해 두고 다른 영상에 다시 쓴다(새로 만들 필요가 있을 때만 렌더)
  python3 scripts/element.py library                          # 저장된 개체 목록(설명 · 길이 · 출처)
  python3 scripts/element.py save <id> <이름> --as <라이브러리 이름> --desc "회전하는 서버 랙, 파란 림 라이트"
  python3 scripts/element.py reuse <라이브러리 이름> <id> [<이름>]   # → public/elements/<id>/<이름>/

그림 설명에는 콘티 룩의 색과 '2D 평면 일러스트 · 글자 없음'이 자동으로 붙는다(--raw 로 끔). 글자 · 숫자는 생성 모델에 시키지 않는다 —
HyperFrames 층(K.text · K.counter)이 그 위에 정확하게 그린다.
마지막 줄: scene.js 에 넣을 K.seq(...) 한 줄
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import genvideo  # noqa: E402
from engines import PUBLIC, look_tokens  # noqa: E402

STYLE = "flat 2D vector illustration, clean shapes, soft shading, no text, no letters, no watermark"


def safe(name: str) -> str:
    if not name or not all(ch.isalnum() or ch in "-_" for ch in name):
        raise SystemExit("이름은 영문 · 숫자 · - _ 만")
    return name


def sb_of(sid: str) -> dict:
    p = ROOT / "storyboards" / f"{sid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def colors(sid: str) -> dict:
    sb = sb_of(sid)
    c = dict(look_tokens(sb)["color"])
    c.update({k[6:]: v for k, v in (sb.get("direction") or {}).items() if k.startswith("color_") and isinstance(v, str)})
    return c


def styled(sid: str, desc: str, raw: bool) -> str:
    if raw:
        return desc
    c = colors(sid)
    return f"{desc}, {STYLE}, color palette {c['accent']} {c['surface']} {c['bg']}"


def out_dir(sid: str, name: str) -> Path:
    d = PUBLIC / "elements" / sid / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


# ---------- 프레임 ----------
def probe(video: Path) -> tuple[float, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate:format=duration",
                        "-of", "json", str(video)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    num, den = d["streams"][0]["r_frame_rate"].split("/")
    return float(d["format"].get("duration") or 0), round(float(num) / float(den or 1))


def explode(src: Path, d: Path, ext: str, max_w: int) -> int:
    """영상 → f0001.<ext> … (긴 변 max_w 로 줄임). 그림 한 장이면 프레임 1개."""
    vf = f"scale='min({max_w},iw)':-2"
    args = ["-q:v", "3"] if ext == "jpg" else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-an", *args, str(d / f"f%04d.{ext}")], check=True)
    return len(list(d.glob(f"f*.{ext}")))


def pingpong(d: Path, ext: str) -> int:
    """앞으로 → 뒤로 이어 붙여 끊김 없이 반복되게 (K.seq loop)."""
    fs = sorted(d.glob(f"f*.{ext}"))
    n = len(fs)
    for k, f in enumerate(reversed(fs[1:-1])):
        shutil.copy2(f, d / f"f{n + k + 1:04d}.{ext}")
    return len(list(d.glob(f"f*.{ext}")))


def cutout(d: Path, model: str) -> None:
    """배경 제거(rembg, CPU) → 투명 PNG. 평면 2D 일러스트 · 마스코트 · 사물은 u2net(기본, 가장 깨끗), 셀 애니 화풍 인물은 isnet-anime.
    isnet-general-use 는 평면 그림 안쪽에 얼룩, birefnet 은 RAM 16GB 에서 메모리 부족 (2026-10-29 시험)."""
    try:
        from rembg import new_session, remove
    except ImportError:
        raise SystemExit("배경 제거에 rembg 가 필요합니다: uv pip install --python .venv/bin/python 'rembg[cpu]'")
    from PIL import Image
    sess = new_session(model)
    fs = sorted(d.glob("f*.*"))
    for k, f in enumerate(fs):
        im = Image.open(f).convert("RGB")
        remove(im, session=sess).save(d / f"f{k + 1:04d}.png")
        if f.suffix != ".png":
            f.unlink()
        if k % 10 == 0:
            print(f"[배경 제거] {k + 1}/{len(fs)}", file=sys.stderr)


def finish(d: Path, sid: str, name: str, fps: int, role: str, info: dict) -> None:
    from PIL import Image
    fs = sorted(d.glob("f*.*"))
    if not fs:
        raise SystemExit("프레임이 없습니다")
    ext = fs[0].suffix[1:]
    first = Image.open(fs[0])
    w, h = first.size
    transparent = first.mode in ("RGBA", "LA")
    bbox = [0, 0, w, h]
    if transparent:  # 프레임 전체에서 실제로 보이는(알파 > 0) 영역 — 겹침 검사가 쓴다
        boxes = [b for f in fs[:: max(1, len(fs) // 12)] if (b := Image.open(f).getchannel("A").getbbox())]
        if boxes:
            bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
    meta = {"frames": len(fs), "fps": fps, "ext": ext, "pad": 4, "w": w, "h": h, "size": max(w, h), "bbox": bbox,
            "transparent": transparent, "role": role, **info}
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    rel = f"elements/{sid}/{name}"
    sec = len(fs) / fps
    print(f"[요소] {rel} · {meta.get('engine')}{'/' + meta['model'] if meta.get('model') else ''} · {len(fs)}프레임 {sec:.1f}초 · {w}×{h}"
          f" · {'투명' if transparent else '불투명'} · {role}", file=sys.stderr)
    if info.get("license"):
        print(f"[요소] 라이선스 {info['license']} · 상업 {info.get('commercial', '?')}", file=sys.stderr)
    if role == "plate":
        print(f'K.seq(c.root, "{rel}", {{ name: "{name}", x: 0, y: 0, w: 1080, h: 1920, fit: "cover", under: true, loop: true, at: 0 }})')
    else:
        print(f'K.seq(c.root, "{rel}", {{ name: "{name}", x: 240, y: 620, w: 600, h: {round(600 * h / w)}, loop: true, at: 0 }})')


def license_info(m: dict) -> dict:
    return {"model": m["name"], "license": m["license"]["model"], "commercial": m["license"]["commercial"]}


# ---------- 명령 ----------
def first_frame(a) -> tuple[Path | None, dict | None]:
    if a.image:
        return Path(a.image).resolve(), None
    if not a.image_prompt:
        return None, None
    p, m = genvideo.generate("t2i", styled(a.id, a.image_prompt, a.raw), size=a.size, seed=a.seed,
                             log=lambda s: print(s, file=sys.stderr))
    return p, m


def cmd_gen(a):
    img, im = first_frame(a)
    if not img:
        raise SystemExit("--image 또는 --image-prompt 가 필요합니다")
    prompt = a.prompt if a.raw else f"{a.prompt}, keep the flat 2D illustration style, smooth subtle motion, no text"
    vid, m = genvideo.generate("i2v", prompt, str(img), sec=a.sec, size=a.size, seed=a.seed,
                               models=a.model.split(",") if a.model else None, log=lambda s: print(s, file=sys.stderr))
    d = out_dir(a.id, safe(a.name))
    ext = "png" if a.cutout else "jpg"
    explode(vid, d, ext, 1080)
    _, fps = probe(vid)
    if a.cutout:
        cutout(d, a.cutout)
    if a.pingpong:
        pingpong(d, "png" if a.cutout else ext)
    info = {"engine": "gen", **license_info(m), "prompt": a.prompt, "image_prompt": a.image_prompt,
            "first_frame": im["name"] if im else "upload", "source": str(vid.relative_to(ROOT))}
    finish(d, a.id, a.name, fps, "element" if a.cutout else a.role, info)


def cmd_interp(a):
    vid, m = genvideo.generate("interp", a.prompt, str(Path(a.image).resolve()), str(Path(a.image2).resolve()),
                               seed=a.seed, log=lambda s: print(s, file=sys.stderr))
    d = out_dir(a.id, safe(a.name))
    explode(vid, d, "png", 1080)
    _, fps = probe(vid)
    if a.cutout:
        cutout(d, a.cutout)
    if a.pingpong:
        pingpong(d, "png")
    finish(d, a.id, a.name, fps, "element" if a.cutout else a.role, {"engine": "gen", **license_info(m), "prompt": a.prompt})


def cmd_image(a):
    img, m = first_frame(a)
    if not img:
        raise SystemExit("--image 또는 --image-prompt 가 필요합니다")
    d = out_dir(a.id, safe(a.name))
    explode(img, d, "png", 1440)
    if a.cutout:
        cutout(d, a.cutout)
    info = {"engine": "gen", **(license_info(m) if m else {}), "image_prompt": a.image_prompt}
    finish(d, a.id, a.name, 30, "element" if a.cutout else a.role, info)


def cmd_import(a):
    src = Path(a.src).resolve()
    d = out_dir(a.id, safe(a.name))
    explode(src, d, "png" if a.cutout else "jpg", 1080)
    fps = probe(src)[1] if src.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv", ".gif") else 30
    if a.cutout:
        cutout(d, a.cutout)
    if a.pingpong:
        pingpong(d, "png" if a.cutout else "jpg")
    info = {"engine": "gen", **license_info(genvideo.model_meta(a.model))} if a.model else {"engine": "import"}
    finish(d, a.id, a.name, fps, "element" if a.cutout else a.role, {**info, "source": a.src})


def cmd_manim(a):
    """Manim 을 투명 PNG 연속 이미지로. 스크립트는 SF_STYLE(json: colors · sec · w · h · font)을 읽어 룩 색으로 그린다."""
    import engines as E
    man = E.adapter("manim")
    if not man.available():
        raise SystemExit("Manim 엔진이 설치되지 않았습니다 (설정 → 렌더 엔진)")
    from platform_util import container_mount
    script = Path(a.script or ROOT / "compositions" / a.id / "manim" / f"{a.name}.py").resolve()
    if not script.exists():
        raise SystemExit(f"스크립트 없음: {script} — class Main(Scene) 을 쓰세요")
    w, h = (int(v) for v in a.size.lower().split("x"))
    if a.draft:
        w, h = w // 2, h // 2
    work = Path(tempfile.mkdtemp(prefix=f"manim-{a.name}-", dir=ROOT / "workspace" / "tmp"))
    style = {"colors": colors(a.id), "sec": a.sec, "w": w, "h": h, "font": "Pretendard", "words": scene_words(a.id, a.scene)}
    if a.scene is not None and not a.sec_given:   # 장면 길이 = 음성이 정한 그 장면 길이
        sb = sb_of(a.id)
        if 0 <= a.scene < len(sb.get("scenes", [])):
            style["sec"] = a.sec = float(sb["scenes"][a.scene]["sec"])
    (work / "style.json").write_text(json.dumps(style, ensure_ascii=False), encoding="utf-8")
    shutil.copy2(script, work / "scene.py")
    for f in script.parent.glob("*.py"):   # 같은 폴더의 부품 모듈
        if f != script:
            shutil.copy2(f, work / f.name)
    MRW, MRO = container_mount(), container_mount(ro=True)
    cmd = [man.RUNTIME, "run", "--rm"] + (["--userns=keep-id"] if man.RUNTIME.endswith("podman") else [])
    cmd += ["-v", f"{work}:/work{MRW}", "-v", f"{PUBLIC / 'fonts'}:/usr/share/fonts/sf{MRO}", "-w", "/work",
            "-e", "SF_STYLE=/work/style.json", man.META["image"],
            "manim", "render", "-t", "--format", "mov", "-r", f"{w},{h}", "--fps", "30", "--disable_caching",
            "--media_dir", "/work/media", "-o", "element", "/work/scene.py", "Main"]
    # 0.22 의 --format png 는 마지막 프레임 한 장뿐 → 알파 있는 mov(-t) 로 렌더하고 ffmpeg 로 투명 PNG 를 푼다
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    movs = sorted((work / "media").rglob("element.mov"))
    if r.returncode != 0 or not movs:
        raise SystemExit(f"Manim 실패:\n{(r.stdout + r.stderr)[-1800:]}")
    d = out_dir(a.id, safe(a.name))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(movs[-1]), "-pix_fmt", "rgba", str(d / "f%04d.png")], check=True)
    shutil.rmtree(work, ignore_errors=True)
    finish(d, a.id, a.name, 30, "element", {"engine": "manim", "script": str(script.relative_to(ROOT)), "license": "MIT", "commercial": "가능"})


def cmd_blender(a):
    """Blender 개체 요소 — scripts/blender_run.py 에 맡긴다(스크립트 검사 · 감사 훅 · 투명 PNG · bbox · 고정점 anchors)."""
    if getattr(a, "bg", False) and not a.still:
        # 백그라운드: Fluma 서버의 작업 대기열에 맡기고 바로 돌아온다(서버가 꺼져 있으면 여기서 그대로 렌더)
        import urllib.request
        port = os.environ.get("FLUMA_PORT", "4310")
        body = json.dumps({"id": a.id, "name": a.name, "sec": a.sec, "size": a.size, "script": a.script, "draft": a.draft, "args": a.arg}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/bg/blender", data=body, method="POST",
                                     headers={"content-type": "application/json", "x-fluma-client": "agent"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                job = json.loads(r.read() or b"{}").get("jobId")
            w, h = (int(x) for x in a.size.lower().split("x")); sw = min(720, w)
            print(f"[3D 백그라운드] elements/{a.id}/{a.name} 렌더를 맡겼습니다(작업 {job}). 기다리지 말고 화면 구성을 계속 짜세요 — 끝나면 미리보기가 저절로 갱신됩니다.")
            print(f'K.seq(c.root, "elements/{a.id}/{a.name}", {{ name: "{a.name}", x: {(1080 - sw) // 2}, y: 560, w: {sw}, h: {round(sw * h / w)}, at: 0 }})')
            print(f"진행 확인: python3 scripts/element.py list {a.id}  (요소가 목록에 나오면 끝난 것)")
            return
        except Exception as e:  # noqa: BLE001
            print(f"[3D 백그라운드] 서버에 맡기지 못해 여기서 렌더합니다: {e}", file=sys.stderr)
    script = a.script or f"compositions/{a.id}/blender/{a.name}.py"
    cmd = [sys.executable, str(ROOT / "scripts" / "blender_run.py"), a.id, script, "--sec", str(a.sec), "--size", a.size]
    cmd += ["--still", a.still] if a.still else ["--name", safe(a.name)]
    if a.draft:
        cmd.append("--draft")
    for kv in a.arg:
        cmd += ["--arg", kv]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    if not a.still:   # 요소 meta 에 엔진 · 라이선스 정보를 맞춰 둔다
        mp = PUBLIC / "elements" / a.id / a.name / "meta.json"
        if mp.exists():
            m = json.loads(mp.read_text(encoding="utf-8"))
            credits = ROOT / "compositions" / a.id / "blender" / "assets" / "CREDITS.txt"
            m.update({"engine": "blender", "role": "element", "license": "모델 라이선스는 CREDITS.txt", "credit": credits.read_text(encoding="utf-8").strip() if credits.exists() else None})
            m.setdefault("commercial", "가능" if not credits.exists() else "출처 표기 필요")
            mp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def scene_words(sid: str, scene: int | None) -> list[dict]:
    """그 장면 나레이션 단어와 장면 안 시각(초) — 요소 스크립트가 음성에 맞춰 움직이게(cue)"""
    if scene is None:
        return []
    sb = sb_of(sid)
    cp = PUBLIC / "audio" / f"{sid}.captions.json"
    if not sb or not cp.exists():
        return []
    start = sum(float(s["sec"]) for s in sb["scenes"][:scene])
    return [{"text": str(w["text"]).strip(), "at": round(w["startMs"] / 1000 - start, 3), "end": round(w["endMs"] / 1000 - start, 3)}
            for w in json.loads(cp.read_text(encoding="utf-8")) if w.get("scene") == scene]


LIB = ROOT / "library3d"


def cmd_save(a):
    src = PUBLIC / "elements" / a.id / a.name
    if not (src / "meta.json").exists():
        raise SystemExit(f"요소 없음: elements/{a.id}/{a.name}")
    dst = LIB / safe(a.as_)
    if dst.exists() and not a.force:
        raise SystemExit(f"이미 있음: library3d/{a.as_} (덮어쓰려면 --force)")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst / "frames")
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    for d in ("blender", "manim"):   # 만든 스크립트 · 모델 출처도 같이 (다시 만들거나 고칠 때)
        sp = ROOT / "compositions" / a.id / d / f"{a.name}.py"
        if sp.exists():
            shutil.copy2(sp, dst / f"{d}.py")
        cr = ROOT / "compositions" / a.id / d / "assets" / "CREDITS.txt"
        if cr.exists():
            shutil.copy2(cr, dst / "CREDITS.txt")
    info = {"name": a.as_, "desc": a.desc, "engine": meta.get("engine"), "frames": meta["frames"], "fps": meta["fps"],
            "sec": round(meta["frames"] / meta["fps"], 2), "size": [meta["w"], meta["h"]], "transparent": meta.get("transparent"),
            "commercial": meta.get("commercial", "가능"), "credit": meta.get("credit"), "from": f"{a.id}/{a.name}"}
    (dst / "item.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[라이브러리] library3d/{a.as_} 저장 · {info['sec']}초 · {info['engine']}")


def cmd_reuse(a):
    src = LIB / safe(a.lib) / "frames"
    if not src.exists():
        raise SystemExit(f"라이브러리에 없음: {a.lib} (python3 scripts/element.py library)")
    name = safe(a.name or a.lib)
    dst = out_dir(a.id, name)
    shutil.rmtree(dst)
    shutil.copytree(src, dst)
    m = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    m["reused"] = a.lib
    (dst / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[재사용] library3d/{a.lib} → elements/{a.id}/{name} · {m['frames']}프레임 (다시 렌더하지 않음)", file=sys.stderr)
    print(f'K.seq(c.root, "elements/{a.id}/{name}", {{ name: "{name}", x: 240, y: 620, w: 600, h: {round(600 * m["h"] / m["w"])}, loop: true, at: 0 }})')


def cmd_library(a):
    items = sorted(LIB.glob("*/item.json")) if LIB.exists() else []
    if not items:
        print("라이브러리가 비었습니다 — 좋은 3D 개체를 만들면 element.py save 로 저장하세요")
    for f in items:
        i = json.loads(f.read_text(encoding="utf-8"))
        print(f"{i['name']:<20} {i.get('engine') or '?':<8} {i['sec']}초 {i['size'][0]}×{i['size'][1]} · 상업 {i.get('commercial')} · {i.get('desc') or ''}")


def cmd_list(a):
    base = PUBLIC / "elements" / a.id
    for d in sorted(base.iterdir()) if base.exists() else []:
        mp = d / "meta.json"
        if mp.exists():
            m = json.loads(mp.read_text(encoding="utf-8"))
            print(f"elements/{a.id}/{d.name:<16} {m.get('engine', '?'):<7} {m.get('model', ''):<12} {m['frames']}프레임 {m['frames'] / m['fps']:.1f}초"
                  f" {m['w']}×{m['h']} {'투명' if m.get('transparent') else '불투명'} {m.get('role', '')} · 상업 {m.get('commercial', '?')}")


def main():
    ap = argparse.ArgumentParser(description="레이어 요소 만들기")
    sp = ap.add_subparsers(dest="cmd", required=True)

    def common(p, vid=True):
        p.add_argument("id")
        p.add_argument("name")
        p.add_argument("--role", default="plate", choices=["plate", "element"], help="plate = 장면 뒤 배경판, element = 위에 얹는 요소")
        p.add_argument("--cutout", nargs="?", const="u2net", help="배경 제거 모델 (기본 u2net, 애니 인물은 isnet-anime)")
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--raw", action="store_true", help="그림 설명에 룩 색 · 2D 화풍을 붙이지 않음")
        if vid:
            p.add_argument("--pingpong", action="store_true", help="앞뒤로 이어 끊김 없는 반복")

    g = sp.add_parser("gen"); common(g)
    g.add_argument("--prompt", required=True, help="움직임 설명 (영어 권장)")
    g.add_argument("--image"); g.add_argument("--image-prompt")
    g.add_argument("--sec", type=float, default=4.0)
    g.add_argument("--size", default="576x1024")
    g.add_argument("--model", help="i2v 모델 순서 (기본: genmodels 의 order 순, 마지막은 kenburns)")
    i = sp.add_parser("interp"); common(i)
    i.add_argument("--image", required=True); i.add_argument("--image2", required=True); i.add_argument("--prompt", required=True)
    m = sp.add_parser("image"); common(m, vid=False)
    m.add_argument("--image"); m.add_argument("--image-prompt"); m.add_argument("--size", default="768x768")
    n = sp.add_parser("manim"); n.add_argument("id"); n.add_argument("name")
    n.add_argument("--script"); n.add_argument("--sec", type=float); n.add_argument("--size", default="1080x1080")
    n.add_argument("--scene", type=int, help="장면 번호(0부터) — 그 장면 길이 · 나레이션 단어 타이밍(SF_STYLE.words)을 넘긴다")
    n.add_argument("--draft", action="store_true")
    bl = sp.add_parser("blender"); bl.add_argument("id"); bl.add_argument("name")
    bl.add_argument("--script"); bl.add_argument("--sec", type=float, default=4.0); bl.add_argument("--size", default="1080x1080")
    bl.add_argument("--still", help="정지 화면만 (예: 0.5,2) → 경로 출력"); bl.add_argument("--draft", action="store_true")
    bl.add_argument("--arg", action="append", default=[], help="key=value → ctx.args")
    bl.add_argument("--bg", action="store_true", help="본 렌더를 Fluma 서버의 작업으로 맡기고 바로 돌아옴(진행률은 화면에)")
    s = sp.add_parser("import"); common(s); s.add_argument("--src", required=True)
    s.add_argument("--model", help="다른 곳에서 이 생성 모델로 만든 파일이면 이름 (라이선스 기록)")
    ls = sp.add_parser("list"); ls.add_argument("id")
    sv = sp.add_parser("save"); sv.add_argument("id"); sv.add_argument("name"); sv.add_argument("--as", dest="as_", required=True)
    sv.add_argument("--desc", default=""); sv.add_argument("--force", action="store_true")
    ru = sp.add_parser("reuse"); ru.add_argument("lib"); ru.add_argument("id"); ru.add_argument("name", nargs="?")
    sp.add_parser("library")
    a = ap.parse_args()
    if a.cmd == "manim":
        a.sec_given = a.sec is not None
        a.sec = a.sec if a.sec is not None else 4.0
    if getattr(a, "id", None) and not all(ch.isalnum() or ch in "-_" for ch in a.id):
        raise SystemExit("id 가 올바르지 않음")
    os.chdir(ROOT)
    {"gen": cmd_gen, "interp": cmd_interp, "image": cmd_image, "manim": cmd_manim, "blender": cmd_blender, "import": cmd_import, "list": cmd_list,
     "save": cmd_save, "reuse": cmd_reuse, "library": cmd_library}[a.cmd](a)


if __name__ == "__main__":
    main()
