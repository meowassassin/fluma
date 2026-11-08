"""SolidCraft 어댑터 — 3D 제품 모형(model3d).

  { "id": "m1", "type": "model3d", "shape": "case", "size": [80, 50, 32], "material": "metal", "logo": "FLUMA", "turntable": true, "sec": 4 }
  { "id": "m2", "type": "model3d", "src": "data/public/uploads/<id>/part.step", "material": "#2563eb" }
  { "id": "m3", "type": "model3d", "commands": [ {"command": "sketch.create", "params": {...}}, … ], "material": "wood" }
  { "id": "m4", "type": "model3d", "shape": "phone", "exploded": true, "sec": 3 }

흐름: 형태(내장 형태 · 에이전트가 쓴 SolidCraft 명령 · STEP/메시 불러오기) → SolidCraft run → .sc(편집 파일) + OBJ
     → TextureCraft(texturecraft.shot): Y 위로 세우기 · 받침 · 재질 · 로고 데칼 → 9:16 PNG, turntable 이면 돌려 찍은 mp4
     exploded 면 SolidCraft motion.export_animation 으로 부품이 벌어졌다 닫히는 프레임 → mp4 (재질은 SolidCraft 외관 색 · PBR)
좌표 단위는 mm. SolidCraft 는 Z 가 위, 앞은 -Y(정면 보기 방향).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

MESH = (".obj", ".stl", ".3mf", ".ply", ".glb", ".gltf")
BREP = (".step", ".stp", ".iges", ".igs", ".fcstd", ".3dm")
# 재질 이름 → SolidCraft 외관(분해도 렌더용). 색만 있으면 색 + PBR
SC_LOOK = {"metal": (None, 0.9, 0.32), "aluminium_brushed": ("#c7ccd3", 0.9, 0.35), "steel_stainless": ("#b8bec6", 0.9, 0.25),
           "chrome": ("#e5e7eb", 1.0, 0.08), "gold_polished": ("#d4a63a", 1.0, 0.2), "copper": ("#c27a4a", 1.0, 0.3),
           "brass": ("#c9a447", 1.0, 0.3), "titanium": ("#9aa0a6", 0.9, 0.35), "wood_oak": ("#b08455", 0.0, 0.7),
           "wood_walnut": ("#6b4a33", 0.0, 0.7), "plastic_glossy": (None, 0.0, 0.25), "plastic_matte": (None, 0.0, 0.7),
           "rubber": ("#1f2937", 0.0, 0.9), "glass": ("#cfe3ea", 0.0, 0.05)}


# ---------------------------------------------------------------- 내장 형태 (치수만 받아 SolidCraft 명령을 만든다)
GAP = 0.3     # 맞붙는 부품 사이 틈(mm) — 딱 붙으면 TextureCraft AO 굽기가 맞닿은 테두리에 톱니 무늬를 낸다


def _plane(origin, x, y):
    return {"origin": list(origin), "x_dir": list(x), "y_dir": list(y)}


def _c(cmd, **p):
    return {"command": cmd, "params": p}


def _case(size):
    """뚜껑 있는 둥근 케이스(이어폰 · 소품 상자): 몸통 + 뚜껑 두 부품"""
    w, d, h = (size + [80, 50, 32][len(size):])[:3]
    lid = max(4.0, h * 0.28)
    r = min(w, d) * 0.22
    cmds = [
        _c("sketch.create", plane="XY"),
        _c("sketch.rectangle.rounded", p0=[-w / 2, -d / 2], p1=[w / 2, d / 2], radius=r),
        _c("solid.extrude", distance=h - lid),
        _c("solid.fillet", edges=[[0, -d / 2, 0]], radius=min(3.0, h * 0.1)),
        _c("solid.shell", faces=[[0, 0, h - lid]], thickness=1.6),
        _c("sketch.create", plane=_plane([0, 0, h - lid], [1, 0, 0], [0, 1, 0])),
        _c("sketch.rectangle.rounded", p0=[-w / 2, -d / 2], p1=[w / 2, d / 2], radius=r),
        _c("solid.extrude", distance=lid, operation="new_body"),
        _c("solid.fillet", edges=[[0, -d / 2, h]], radius=min(lid * 0.6, 4.0), body="Body2"),
    ]
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "lid"}, "_logo_on": "Body1"}
    return cmds, meta, [{"occurrence": "Body2", "translate": [0, 0, h * 1.1]}]


def _phone(size):
    """세로로 선 스마트폰: 몸체 + 화면 유리(앞) + 카메라 섬(뒤)"""
    w, t, h = (size + [72, 8, 150][len(size):])[:3]
    r = w * 0.14
    front = _plane([0, 0, 0], [1, 0, 0], [0, 0, 1])           # 법선 -Y(앞)
    cmds = [
        _c("sketch.create", plane=front),
        _c("sketch.rectangle.rounded", p0=[-w / 2, 0], p1=[w / 2, h], radius=r),
        _c("solid.extrude", distance=t),
        _c("solid.fillet", edges=[[0, -t, h]], radius=min(1.6, t * 0.2)),
        _c("sketch.create", plane=_plane([0, -t, 0], [1, 0, 0], [0, 0, 1])),
        _c("sketch.rectangle.rounded", p0=[-w / 2 + 2.2, 2.2], p1=[w / 2 - 2.2, h - 2.2], radius=r - 2),
        _c("solid.extrude", distance=0.5, operation="new_body"),
        _c("sketch.create", plane=_plane([0, 0, 0], [-1, 0, 0], [0, 0, 1])),   # 법선 +Y(뒤)
        _c("sketch.rectangle.rounded", p0=[-w / 2 + 6, h - 6 - w * 0.36], p1=[-w / 2 + 6 + w * 0.36, h - 6], radius=w * 0.07),
        _c("solid.extrude", distance=1.6, operation="new_body"),
    ]
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "screen", "material": "#0b0f17", "fixed": True, "finish": "glossy"},
            "Body3": {"role": "camera", "material": "#1f2937", "fixed": True, "finish": "glossy"}, "_logo_on": "Body2"}
    return cmds, meta, [{"occurrence": "Body2", "translate": [0, -t * 4, 0]}, {"occurrence": "Body3", "translate": [0, t * 4, 0]}]


def _bottle(size):
    """병(회전체) + 마개"""
    dia, h = (size + [64, 215][len(size):])[:2]
    r = dia / 2
    neck = max(6.0, r * 0.4)
    sh = h * 0.70
    side = _plane([0, 0, 0], [1, 0, 0], [0, 0, 1])
    cmds = [
        _c("sketch.create", plane=side),
        _c("sketch.line", points=[[0, 0], [r, 0], [r, sh], [neck * 1.15, h * 0.86], [neck, h * 0.9], [neck, h], [0, h]], closed=True),
        _c("solid.revolve", axis="Z"),
        _c("solid.fillet", edges=[[r, 0, 0]], radius=r * 0.12),
        _c("solid.fillet", edges=[[r, 0, sh]], radius=r * 0.5, fit="reduce"),
        _c("sketch.create", plane=_plane([0, 0, h + GAP], [1, 0, 0], [0, 1, 0])),
        _c("sketch.circle.center", center=[0, 0], radius=neck * 1.18),
        _c("solid.extrude", distance=h * 0.1, operation="new_body"),
        _c("solid.fillet", edges=[[neck * 1.18, 0, h * 1.1 + GAP]], radius=1.2, body="Body2"),
    ]
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "cap", "material": "#111827", "finish": "matte"}, "_logo_on": "Body1", "_logo_round": True, "_logo_y": 0.4}
    return cmds, meta, [{"occurrence": "Body2", "translate": [0, 0, h * 0.25]}]


def _tumbler(size):
    """텀블러 · 컵(아래가 좁은 회전체, 속이 빈) + 뚜껑"""
    dia, h = (size + [84, 160][len(size):])[:2]
    r = dia / 2
    side = _plane([0, 0, 0], [1, 0, 0], [0, 0, 1])
    cmds = [
        _c("sketch.create", plane=side),
        _c("sketch.line", points=[[0, 0], [r * 0.8, 0], [r, h], [0, h]], closed=True),
        _c("solid.revolve", axis="Z"),
        _c("solid.fillet", edges=[[r * 0.8, 0, 0]], radius=r * 0.15),
        _c("solid.shell", faces=[[0, 0, h]], thickness=2.2),
        _c("sketch.create", plane=_plane([0, 0, h + GAP], [1, 0, 0], [0, 1, 0])),
        _c("sketch.circle.center", center=[0, 0], radius=r + 1),
        _c("solid.extrude", distance=h * 0.09, operation="new_body"),
        _c("solid.fillet", edges=[[r + 1, 0, h * 1.09 + GAP]], radius=h * 0.03, body="Body2"),
    ]
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "lid", "material": "#1f2937", "finish": "matte"}, "_logo_on": "Body1", "_logo_round": True, "_logo_y": 0.5}
    return cmds, meta, [{"occurrence": "Body2", "translate": [0, 0, h * 0.35]}]


def _puck(size):
    """납작한 원형 기기(스마트 태그 · 리모컨 · 충전기): 아래 몸통 + 윗면 판"""
    dia, h = (size + [60, 14][len(size):])[:2]
    r = dia / 2
    cmds = [
        _c("sketch.create", plane="XY"),
        _c("sketch.circle.center", center=[0, 0], radius=r),
        _c("solid.extrude", distance=h * 0.75),
        _c("solid.fillet", edges=[[r, 0, 0]], radius=h * 0.3),
        _c("sketch.create", plane=_plane([0, 0, h * 0.75], [1, 0, 0], [0, 1, 0])),
        _c("sketch.circle.center", center=[0, 0], radius=r),
        _c("solid.extrude", distance=h * 0.25, operation="new_body"),
        _c("solid.fillet", edges=[[r, 0, h]], radius=h * 0.2, body="Body2"),
    ]
    meta = {"Body1": {"role": "body"}, "Body2": {"role": "top", "material": "#f3f4f6", "finish": "glossy"}, "_logo_on": "Body2", "_logo_side": "top", "_logo_y": None}
    return cmds, meta, [{"occurrence": "Body2", "translate": [0, 0, h * 1.4]}]


SHAPES = {"case": _case, "phone": _phone, "bottle": _bottle, "tumbler": _tumbler, "puck": _puck}
ALIASES = {"box": "case", "상자": "case", "케이스": "case", "이어폰 케이스": "case", "smartphone": "phone", "폰": "phone", "스마트폰": "phone",
           "휴대폰": "phone", "병": "bottle", "물병": "bottle", "cup": "tumbler", "컵": "tumbler", "텀블러": "tumbler", "mug": "tumbler",
           "tag": "puck", "태그": "puck", "disc": "puck", "원판": "puck"}


def shape_commands(m: dict) -> tuple[list, dict, list]:
    """콘티 재료 → (SolidCraft 명령, 몸체별 기본값, 분해 이동). 형태 이름 · 명령 목록 · 파일 불러오기 중 하나"""
    from ..materials import _abs
    if m.get("commands"):
        cmds = [c if "command" in c else {"command": c.get("id"), "params": c.get("params") or {}} for c in m["commands"]]
        return cmds, {}, []
    if m.get("src"):
        src = _abs(m["src"])
        if not src.exists():
            raise RuntimeError(f"3D 파일이 없습니다: {m['src']}")
        suf = src.suffix.lower()
        if suf in BREP:
            return [_c("file.insert_step", path=str(src), up=m.get("up", "z"))], {}, []
        if suf in MESH:
            p = {"path": str(src)}
            if suf in (".glb", ".gltf"):
                p["up"] = m.get("up", "y")
            return [_c("file.insert_mesh", **p)], {}, []
        raise RuntimeError(f"모르는 3D 파일 형식: {suf} (STEP · IGES · OBJ · STL · 3MF · glTF)")
    name = str(m.get("shape") or "").strip().lower()
    name = ALIASES.get(name, name)
    if name not in SHAPES:
        raise RuntimeError(f"내장 형태가 아닙니다: '{m.get('shape')}' — {', '.join(SHAPES)} 중 하나, 아니면 commands(SolidCraft 명령 목록) · src(STEP/OBJ/STL)")
    return SHAPES[name]([float(v) for v in (m.get("size") or [])])


# ---------------------------------------------------------------- SolidCraft 실행
def design(m: dict, work: Path, stem: str, cli: str | None = None) -> dict:
    """모형 만들기 → <stem>.sc(편집 파일) · <stem>.obj. 사람이 .sc 를 고쳤으면(만들 때 해시와 다름) 그 파일에서 OBJ 만 다시 뽑는다"""
    from ..materials import cli as _cli, _run, _hash, _load
    cli = cli or _cli("solidcraft")
    sc, obj = work / f"{stem}.sc", work / f"{stem}.obj"
    old = _load(work / f"{stem}.json")
    cmds, meta, moves = shape_commands(m)
    looks = _looks(m, meta)
    edited = sc.exists() and old.get("editable_hash") and _hash(sc) != old["editable_hash"]
    # 곡면을 촘촘히(fine) — 기본(standard) 메시는 둥근 테두리에 톱니가 보인다
    export = [_c("file.export", path=str(obj), quality=m.get("quality", "fine"))]
    if edited:
        _run([cli, "run", _write(work / f"{stem}.export.json", export), "--in", sc], work)
    else:
        sp = _write(work / f"{stem}.solid.json", cmds + looks)
        _run([cli, "run", sp, "--save", sc], work, timeout=300)
        _run([cli, "run", _write(work / f"{stem}.export.json", export), "--in", sc], work)
    if not obj.exists():
        raise RuntimeError("SolidCraft 가 OBJ 를 내보내지 않았습니다")
    bodies = re.findall(r"^o\s+(.+)$", obj.read_text("utf-8", "replace"), re.M)
    return {"sc": sc, "obj": obj, "meta": meta, "moves": moves, "bodies": [b.strip() for b in bodies], "edited": bool(edited), "cmds": cmds}


def _write(p: Path, cmds: list) -> Path:
    p.write_text(json.dumps({"commands": cmds}, ensure_ascii=False, indent=1), "utf-8")
    return p


def _looks(m: dict, meta: dict) -> list:
    """SolidCraft 외관(분해도 · 도면 미리 보기 색). TextureCraft 재질과 같은 이름에서 색 · 금속성을 고른다"""
    from .texturecraft import MATERIALS, CLEAN, DEFAULT, _hex
    out = []
    spec = m.get("material")
    for b, d in meta.items():
        if b.startswith("_"):
            continue
        if isinstance(spec, dict):      # 몸체 이름 · 역할로 콕 집으면 화면 같은 고정 부품도 바꾼다, "*" 는 고정 부품 빼고
            v = spec.get(b) or spec.get(d.get("role", "")) or (None if d.get("fixed") else spec.get("*"))
        else:      # 재질 하나만 주면 본체에만(texturecraft._materials 와 같은 규칙)
            v = d.get("material") or spec
        v = v or d.get("material") or m.get("color")
        if not v:
            continue
        h = _hex(v) if isinstance(v, str) else (v.get("color") if isinstance(v, dict) else None)
        name = MATERIALS.get(str(v).lower(), str(v)) if not h else None
        col, metal, rough = SC_LOOK.get(name or "", (None, 0.0, 0.4))
        if str(v).lower() in CLEAN:
            c0, rough, metal = CLEAN[str(v).lower()]
            col = (m.get("color") if not d.get("material") else None) or c0     # 색 + 표면 이름(아노다이징 등)
        col = h or col or m.get("color") or DEFAULT
        if not _hex(col):
            continue
        out.append(_c("appearance.assign", bodies=[b], color=_hex(col), pbr={"metallic": metal, "roughness": max(0.05, rough), "dielectric_ior": 1.5}))
    return out


def exploded(d: dict, m: dict, out: Path, work: Path, cli: str) -> dict:
    """부품 분해 애니메이션(SolidCraft 헤드리스 렌더러) → mp4. 부품이 둘 이상이어야 한다"""
    from ..materials import _run
    bodies = d["bodies"]
    if len(bodies) < 2:
        raise RuntimeError("분해도는 부품이 둘 이상인 모형만 됩니다(내장 형태 case · phone · bottle · tumbler · puck, 또는 new_body 로 만든 몸체)")
    moves = d["moves"]
    ids = [c.get("command") for c in d["cmds"]]
    own = next((c.get("params") or {} for c in d["cmds"] if c.get("command") == "explode.create"), None)
    looks = _looks(m, {b: {} for b in bodies}) if not d["meta"] else []     # 명령 · 파일로 만든 모형: 몸체 모두 같은 재질 색
    if own is not None:
        # 에이전트가 명령에 분해도를 직접 넣었으면 그것을 쓴다(같은 이름을 또 만들면 움직이지 않는 분해도가 된다)
        view, ex, steps = own.get("name") or "Exploded View 1", dict(own), looks
    else:
        view = "fluma_open"
        ex = {"name": view}
        if moves:
            ex["moves"] = moves
        else:
            ex["scale"] = float(m.get("explode_scale", 2.0))
        comp = [] if any(i in ("component.from_bodies", "component.create") for i in ids) else [_c("component.from_bodies", bodies=bodies)]
        steps = looks + comp + [_c("explode.create", **ex)]
    sp = _write(work / f"{out.stem}.explode.json", steps)
    esc = work / f"{out.stem}.exploded.sc"
    _run([cli, "run", sp, "--in", d["sc"], "--save", esc], work)
    sec, fps = float(m.get("sec", 4)), int(m.get("fps", 30))
    n = max(9, min(int(sec * fps), 301)) | 1                    # 홀수: 가운데 프레임이 가장 벌어진 모습
    fd = work / f"{out.stem}.frames"
    fd.mkdir(exist_ok=True)
    for f in fd.glob("frame-*.png"):
        f.unlink()
    W, H = int(m.get("width", 1080)), int(m.get("height", 1920))
    yaw_deg, pitch_deg = float(m.get("yaw", 32)), float(m.get("pitch", 22))
    fov = float(m.get("fov", 28))
    # 화면 맞추기: 조립 · 분해 상태를 합친 상자(Y 위로 바꿔)를 TextureCraft 와 같은 식으로 맞춘다.
    # SolidCraft 카메라 yaw 는 반대 방향(0 = +Y 를 봄, 앞에서 본다) → SolidCraft yaw = -yaw
    from .texturecraft import fit_distance
    lo, hi = _exploded_box(d["obj"], ex.get("moves") or [], float(ex.get("scale", 0) or (0 if ex.get("moves") else 1)))
    ylo, yhi = [lo[0], lo[2], -hi[1]], [hi[0], hi[2], -lo[1]]
    tgt, dist = fit_distance(ylo, yhi, [yaw_deg], pitch_deg, fov, W / H, float(m.get("fill", 0.86)))
    cam = {"target": [tgt[0], -tgt[2], tgt[1]], "yaw": -math.radians(yaw_deg), "pitch": math.radians(pitch_deg),
           "distance": dist, "fov": math.radians(fov)}
    anim = _write(work / f"{out.stem}.anim.json", [_c("motion.export_animation", view=view, back=m.get("back", True) is not False, samples=n,
                                                       path=str(fd), width=W, height=H, fps=min(fps, 50), grid=False, axes=False,
                                                       camera=cam)])
    _run([cli, "run", anim, "--in", esc], work, timeout=300)
    frames = sorted(fd.glob("frame-*.png"))
    if not frames:
        raise RuntimeError("SolidCraft 가 분해 프레임을 내지 않았습니다")
    mp4 = out.with_suffix(".mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(fd / "frame-%04d.png"),
                        "-vf", "format=yuv420p", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(mp4)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"분해도 영상 만들기 실패: {r.stderr[-200:]}")
    out.write_bytes(frames[len(frames) // 2].read_bytes())    # 가장 벌어진 장면을 PNG 로(미리 보기 · 정지 화면)
    import shutil
    shutil.rmtree(fd, ignore_errors=True)                     # 프레임 폴더는 영상으로 합쳤으니 지운다
    return {"file_suffix": ".mp4", "as": "video", "frames": len(frames), "fps": fps, "sec": round(len(frames) / fps, 2),
            "poster": out.name, "parts": bodies, "exploded_editable": str(esc.name)}


def _boxes(obj: Path) -> dict:
    """OBJ 몸체별 경계 상자 {이름: (lo, hi)} (Z 위 그대로)"""
    out, cur = {}, None
    for line in obj.read_text("utf-8", "replace").splitlines():
        if line.startswith("o "):
            cur = line[2:].strip()
        elif line.startswith("v ") and cur:
            p = [float(v) for v in line.split()[1:4]]
            lo, hi = out.setdefault(cur, ([math.inf] * 3, [-math.inf] * 3))
            for k in range(3):
                lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
    return out


def _exploded_box(obj: Path, moves: list, scale: float) -> tuple[list, list]:
    """조립 상태 + 분해 상태를 모두 담는 상자. 자동 분해(scale)는 가운데에서 scale 배 벌어진다고 어림한다"""
    bx = _boxes(obj)
    if not bx:
        raise RuntimeError("OBJ 에 몸체가 없습니다")
    lo = [min(b[0][k] for b in bx.values()) for k in range(3)]
    hi = [max(b[1][k] for b in bx.values()) for k in range(3)]
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    for name, (blo, bhi) in bx.items():
        t = next((mv["translate"] for mv in moves if mv.get("occurrence") == name), None)
        if t is None and scale:
            bc = [(blo[k] + bhi[k]) / 2 for k in range(3)]
            t = [(bc[k] - c[k]) * scale for k in range(3)]
        if t:
            for k in range(3):
                lo[k], hi[k] = min(lo[k], blo[k] + t[k]), max(hi[k], bhi[k] + t[k])
    return lo, hi


def model3d(m: dict, out: Path, work: Path) -> dict:
    from ..materials import cli, _hash, ROOT
    sc_cli = cli("solidcraft")
    d = design(m, work, out.stem, sc_cli)
    info = {"app": "solidcraft", "editable": str(d["sc"].relative_to(ROOT)) if d["sc"].is_relative_to(ROOT) else str(d["sc"]),
            "editable_hash": _hash(d["sc"]), "parts": d["bodies"]}
    if m.get("exploded"):
        info.update(exploded(d, m, out, work, sc_cli))
        info["apps"] = ["solidcraft"]
        return info
    from . import texturecraft as tc
    meta = dict(d["meta"])
    t = tc.shot(d["obj"], out, work, m, meta)
    t.pop("editable", None)
    proj = work / f"{out.stem}.tcraft"
    info.update(t)
    info["app"] = "solidcraft"
    info["apps"] = ["solidcraft", "texturecraft"]
    info["texture_editable"] = str(proj.relative_to(ROOT)) if proj.is_relative_to(ROOT) else str(proj)
    return info


ADAPTERS = {"model3d@solidcraft": model3d}             # 기본 방법은 Blender(adapters/blender.py) — 모양은 design() 을 그대로 쓴다
