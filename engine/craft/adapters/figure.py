"""3D 인물 재료(figure) — Blender 인체에 자세 · 복장을 입히고 고른 화풍으로 앱에서 한 획씩 그린다. 그림 실력을 좌표에 맡기지 않는다.
  {"type": "figure", "id": "sp", "kit": "hoplite"|"messenger"|"elder"|"pan"|"office"|"scientist"|"worker"|"casual"|["shirt", "trousers", …], "hands": {"L": "relax", "R": "point"}, "pose": "thrust"|"stand"|"point"|"collapse"|{…},
   "style": "engrave"|"sketch"|"woodcut"|"wash"|"blackfigure"|"inkline"|"pop"(없으면 영상에 맞게 고른다), "style_params": {"density", "line", "contrast", "angle", "ink", "paper", …},
   "anim": "still"|"sketch_in"|"run", "frames": 8, "on_screen": 화면에 나올 높이 px(작으면 굵은 화풍 · 굵은 선으로), "camera": {"loc", "look", "lens"}, "head_yaw": 20, "show": false}
결과: <id>.png(완성) · <id>_f000.png …(그려지는 과정 · 순환) · 단계별 레이어 PSD. 화면에는 motion-figure 레시피로 놓는다."""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

KITS = {"hoplite": ["cuirass", "greaves", "pteruges", "helmet", "shield", "spear", "cloak"], "messenger": ["tunic", "hair"], "elder": ["tunic", "hair", "beard"], "pan": ["hair", "beard", "horns", "goatlegs"],
        # 현대
        "scientist": ["shirt", "trousers", "shoes", "coat", "shorthair", "glasses"], "office": ["shirt", "jacket", "trousers", "shoes", "shorthair"],
        "worker": ["tshirt", "trousers", "shoes", "shorthair"], "casual": ["tshirt", "trousers", "shoes", "hair"],
        "office_f": ["shirt", "jacket", "trousers", "shoes", "longhair"], "scientist_f": ["shirt", "trousers", "shoes", "coat", "longhair", "glasses"], "casual_f": ["tshirt", "trousers", "shoes", "longhair"]}
FEMALE = {"office_f", "scientist_f", "casual_f"}            # kit 이 여성이면 여성 인체(또는 재료에 "body": "female")
CAM = {"hoplite": {"loc": [4.6, -2.5, 1.28], "look": [.36, 0, 1.08], "lens": 58}, "side": {"loc": [.3, -4.3, 1.15], "look": [.05, 0, .98], "lens": 62}}
SETS = ("field", "hills", "mountains")                         # 배경 세트(kit)
SET_STYLE = {"engrave": {"density": .36, "layers": ["outline", "tone"], "fixed": 3, "limit": .97, "abs_tone": True}}   # 풍경 판화: 성긴 가로 빗금 한 겹
TONE = {"elder": .55, "scientist": .45, "scientist_f": .3}                         # 머리 · 수염 밝기(노인은 희게)
LIB = "human-base-meshes-bundle-v1.4.1"


def human_lib() -> Path:
    """Blender Studio 인체 기본 모델(CC0, 49MB) — 없으면 받는다"""
    from ..materials import ROOT
    d = ROOT / "data" / "cache" / "human-base-meshes"
    f = d / LIB / "human_base_meshes_bundle.blend"
    if f.exists():
        return f
    import subprocess
    d.mkdir(parents=True, exist_ok=True)
    z = d / "bundle.zip"
    subprocess.run(["curl", "-sL", "-m", "300", "-A", "Mozilla/5.0", "-o", str(z), f"https://download.blender.org/demo/asset-bundles/human-base-meshes/{LIB}.zip"], check=True)
    shutil.unpack_archive(str(z), str(d))
    z.unlink()
    return f


def _render(m: dict):
    """Blender 패스 + 화풍 그리기(둘 다 내용으로 캐시) → (프레임 경로들, 완성 기록, 순환 여부)"""
    from ..materials import ROOT, cli
    from ..figure import paint as pt
    from ..figure.choose import KIND
    kit = m.get("kit", "messenger")
    style = m.get("style") or "engrave"
    anim = m.get("anim") or KIND[style]
    cycle = anim == "run"
    spec = {"lib": str(human_lib()), "costume": KITS.get(kit, kit) if isinstance(kit, str) else kit, "pose": m.get("pose", "stand"), "head_yaw": m.get("head_yaw", 18),
            "camera": m.get("camera") or CAM["hoplite" if kit == "hoplite" else "side"], "size": m.get("size") or ([1500, 1300] if cycle else [1800, 2000]), "swing": m.get("swing", 0), "passes": 3, "hands": m.get("hands") or {}, "body": m.get("body") or ("female" if kit in FEMALE else "male"),
            "hair_tone": m.get("hair_tone", TONE.get(kit, .16) if isinstance(kit, str) else .16)}
    if cycle:
        spec.update(cycle={"frames": int(m.get("frames", 8)), "stride": m.get("stride", .36)}, subdiv=2, samples=20)
    if kit in SETS:                                               # 배경 세트: 사람 없이 땅 · 언덕 · 산맥 · 달을 같은 손으로
        spec = {"set": kit, "size": m.get("size") or [1920, 1080], "moon": m.get("moon"), "sun": m.get("sun") or [84, 0, 170], "light": m.get("light", 1.4), "eye": m.get("eye", 1.6), "lens": m.get("lens", 30), "far": m.get("far", True)}
    code = (ROOT / "engine" / "craft" / "figure" / "scene.py").read_bytes()          # 엔진을 고치면 다시 렌더
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode() + code).hexdigest()[:10]
    d = ROOT / "data" / "cache" / "figure" / key                 # 같은 인물 · 자세는 영상 · 장면이 달라도 다시 렌더하지 않는다
    n = spec.get("cycle", {}).get("frames", 1)
    with _lock(d):
        _blender(spec, d, n)
    m["_shade_dir"] = str(d)
    P = cli("photocraft")
    params = dict(m.get("style_params") or {})
    if kit in SETS:
        params = {**SET_STYLE.get(style, {}), **params}
    params.setdefault("ground", m.get("ground", not cycle and kit not in SETS))     # 서 있는 인물은 땅을 함께 그린다(달리기는 공중 프레임이 있어 끔)
    sty = (ROOT / "engine" / "craft" / "figure" / "styles.py").read_bytes()          # 화풍 코드가 바뀌어도 다시 그린다
    d0, d = d, d / hashlib.sha1(json.dumps([style, params, anim, m.get("frames")], sort_keys=True).encode() + sty).hexdigest()[:8]
    with _lock(d):
        return _paint(P, d0, d, style, params, anim, cycle, n, m)


BLENDERS = threading.BoundedSemaphore(2)      # Blender 동시 2개 — 인체 모델이 메모리를 많이 쓴다
_LOCKS: dict = {}
_LK = threading.Lock()


def _lock(d: Path):
    """같은 인물 · 같은 화풍을 두 장면이 동시에 그리지 않게"""
    with _LK:
        return _LOCKS.setdefault(str(d), threading.Lock())


def _blender(spec: dict, d: Path, n: int) -> None:
    from ..materials import ROOT, cli
    if not (d / f"p_{n - 1:03d}_normal.png").exists():
        import subprocess
        d.mkdir(parents=True, exist_ok=True)
        spec["out"] = str((d / "p").resolve())
        f = d / "spec.json"
        f.write_text(json.dumps(spec), "utf-8")
        with BLENDERS:
            r = subprocess.run([cli("blender"), "-b", "--python", str(ROOT / "engine" / "craft" / "figure" / "scene.py"), "--", str(f)], capture_output=True, text=True, timeout=540, stdin=subprocess.DEVNULL)
        if r.returncode or not (d / f"p_{n - 1:03d}_normal.png").exists():
            raise RuntimeError("Blender 인물 렌더 실패: " + (r.stderr or r.stdout)[-400:])


def _paint(P, d0: Path, d: Path, style, params, anim, cycle, n, m):
    from ..figure import paint as pt
    d.mkdir(parents=True, exist_ok=True)
    if cycle:
        with ThreadPoolExecutor(4) as ex:
            rs = list(ex.map(lambda k: pt.paint(P, d0 / f"p_{k:03d}_shade.png", d0 / f"p_{k:03d}_normal.png", d / f"f{k}.psd", style, params, seed=k + 1) if not (d / f"f{k}.png").exists() else {"png": str(d / f"f{k}.png"), "psd": str(d / f"f{k}.psd"), "strokes": 0}, range(n)))
        frames = [Path(r["png"]) for r in rs]
        final = rs[0]
    else:
        cf = d / "final.json"
        if cf.exists():
            final = json.loads(cf.read_text("utf-8"))
        else:
            final = pt.paint(P, d0 / "p_000_shade.png", d0 / "p_000_normal.png", d / "f.psd", style, params, reveal=int(m.get("frames", 14)) if anim == "sketch_in" else 0)
            cf.write_text(json.dumps(final), "utf-8")
        frames = [Path(x) for x in final["frames"]] + [Path(final["png"])] if anim == "sketch_in" else [Path(final["png"])]
    return frames, final, cycle


FOOT = 90           # 잘린 그림에서 발끝 줄 아래 여백 — motion-figure 는 기준점을 (가운데, 높이-FOOT)에 둔다: Y 가 곧 땅 높이


def _foot(m: dict) -> int | None:
    from PIL import Image
    import numpy as np
    d = m.get("_shade_dir")
    if not d:
        return None
    ys = []
    for f in sorted(Path(d).glob("p_*_shade.png")):
        a = np.array(Image.open(f))[..., 3] > 128
        r = np.where(a.any(1))[0]
        if len(r):
            ys.append(int(r[-1]))
    return max(ys) if ys else None


def warm(ms: list[dict], workers: int = 3) -> None:
    """영상 안 인물 재료를 동시에 미리 그린다 — 뒤의 재료 빌드는 캐시만 읽는다. 실패는 그 재료 빌드에서 다시 드러난다"""
    if len(ms) < 2:
        return
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda m: _try(_render, m), ms))


def _try(f, *a):
    try:
        return f(*a)
    except Exception:  # noqa: BLE001
        return None


def figure(m: dict, out: Path, work: Path) -> dict:
    from PIL import Image
    from ..materials import ROOT, _hash
    from ..figure.choose import KIND
    m = dict(m)
    frames, final, cycle = _render(m)
    style = m.get("style") or "engrave"
    anim = m.get("anim") or KIND[style]
    want = int(m.get("frames", 0) or 0)
    if anim == "sketch_in" and want and len(frames) != want:          # 레시피 N 과 언제나 같은 수로 — 마지막은 완성
        frames = [frames[round(i * (len(frames) - 1) / (want - 1))] for i in range(want)]
    # 모든 프레임이 같은 자리에 오도록 합친 상자로 자른다
    box = None
    for f in frames:
        b = Image.open(f).convert("RGBA").getbbox()
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    pad = 24
    W, H = Image.open(frames[0]).size
    foot = _foot(m) if m.get("kit") not in SETS else None                                               # 발이 닿는 줄(Blender 알파 맨 아래) — 그림 아래쪽 FOOT px 에 오게 자른다
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), (foot + FOOT) if foot else min(H, box[3] + pad))
    if m.get("kit") in SETS:
        box = (0, 0, W, H + FOOT)                                # 화면 전체 — 기준점(가운데, 높이-FOOT) = 화면 아래 가운데
    names = []
    for k, f in enumerate(frames):
        dst = out.with_name(f"{out.stem}_f{k:03d}.png")
        Image.open(f).convert("RGBA").crop(box).save(dst)
        names.append(dst.name)
    Image.open(frames[-1] if not cycle else frames[0]).convert("RGBA").crop(box).save(out)
    psd = out.with_suffix(".psd")
    shutil.copy2(final["psd"], psd)
    return {"app": "blender+photocraft", "as": "image", "style": style, "anim": anim, "frames": names, "size": [box[2] - box[0], box[3] - box[1]], "strokes": final["strokes"],
            "editable": str(psd.relative_to(ROOT)) if psd.resolve().is_relative_to(ROOT) else str(psd), "editable_hash": _hash(psd), "apps": ["blender", "photocraft"]}


ADAPTERS = {"figure": figure}
