"""TextureCraft 어댑터 — 3D 메시에 재질 · 로고를 입히고 9:16 제품 컷(PNG)이나 턴테이블 프레임을 찍는다.

혼자 쓰는 재료 종류는 없다. SolidCraft 어댑터(model3d)가 모형 → OBJ 를 만든 뒤 shot() 을 부른다.
  - 축: SolidCraft OBJ 는 Z 가 위, TextureCraft 는 Y 가 위 → to_y_up() 으로 돌려 세운다(앱 안에서 돌리는 명령은 없다)
  - 받침: 모형 아래에 얇은 원판(Stage)을 붙여 바닥에 놓인 제품처럼 보이게 한다(TextureCraft 는 바닥 · 그림자 무대가 없다)
  - 렌더: 헤드리스 MCP(viewport_render)로 세션 하나에서 여러 장 — CLI render 는 장마다 2초, MCP 는 0.3초
편집 파일: <재료id>.tcraft (TextureCraft 에서 열어 붓질 · 재질을 고칠 수 있다)
"""
from __future__ import annotations

import base64
import json
import math
import subprocess
from pathlib import Path

# 콘티의 쉬운 이름 → TextureCraft 재질(material.list). 그 밖의 이름은 TextureCraft 재질 id 로 그대로 넘긴다
MATERIALS = {
    "metal": "aluminium_brushed", "aluminium": "aluminium_brushed", "aluminum": "aluminium_brushed", "steel": "steel_stainless",
    "stainless": "steel_stainless", "chrome": "chrome", "gold": "gold_polished", "copper": "copper", "brass": "brass", "titanium": "titanium",
    "plastic": "plastic_glossy", "matte": "plastic_matte", "rubber": "rubber",
    "wood": "wood_oak", "oak": "wood_oak", "walnut": "wood_walnut", "bamboo": "bamboo",
    "glass": "glass", "concrete": "concrete", "marble": "marble", "leather": "leather", "paper": "paper",
    "금속": "aluminium_brushed", "알루미늄": "aluminium_brushed", "스테인리스": "steel_stainless", "플라스틱": "plastic_glossy",
    "나무": "wood_oak", "유리": "glass", "가죽": "leather", "고무": "rubber", "금": "gold_polished",
}
# 쉬운 이름 중 무늬 없는 표면(색 · 거칠기 · 금속성) — 자동 UV 가 회전체에서 늘어나 결 무늬가 줄무늬로 깨지므로 무늬 없이 칠한다
CLEAN = {"metal": ("#c3c7cd", 0.48, 1.0), "aluminium": ("#c9cdd2", 0.48, 1.0), "aluminum": ("#c9cdd2", 0.48, 1.0),
         "steel": ("#b4b9bf", 0.45, 1.0), "stainless": ("#b4b9bf", 0.45, 1.0), "chrome": ("#e6e8eb", 0.08, 1.0),
         "gold": ("#e0b44c", 0.3, 1.0), "copper": ("#c98157", 0.38, 1.0), "titanium": ("#8f959c", 0.45, 1.0),
         "plastic": ("#e8eaed", 0.38, 0.0), "matte": ("#e8eaed", 0.7, 0.0), "rubber": ("#1f2937", 0.85, 0.0),
         "금속": ("#c3c7cd", 0.48, 1.0), "알루미늄": ("#c9cdd2", 0.48, 1.0), "스테인리스": ("#b4b9bf", 0.45, 1.0),
         "플라스틱": ("#e8eaed", 0.38, 0.0), "고무": ("#1f2937", 0.85, 0.0), "금": ("#e0b44c", 0.3, 1.0)}
# 색만 준 경우의 표면(거칠기 · 금속성) — plastic 이 기본
FINISH = {"plastic": (0.38, 0.0), "matte": (0.7, 0.0), "metal": (0.45, 1.0), "glossy": (0.15, 0.0), "rubber": (0.85, 0.0)}
STAGE = "Stage"
DEFAULT = "#e8eaed"      # 재질을 안 주면: 흰 플라스틱


# ---------------------------------------------------------------- MCP (stdio JSON-RPC) — CADCraft 어댑터도 쓴다
class Mcp:
    """Craft 앱의 헤드리스 MCP 서버 하나를 띄워 도구를 부른다. with 문으로 쓰면 끝날 때 닫는다"""

    def __init__(self, args: list, cwd: Path, timeout: int = 120):
        import os
        self.p = subprocess.Popen([str(a) for a in args], cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, env={**os.environ, "DO_NOT_TRACK": "1"})
        self.n, self.timeout = 0, timeout
        self._rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "fluma", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, o):
        self.p.stdin.write(json.dumps(o, ensure_ascii=False) + "\n")
        self.p.stdin.flush()

    def _rpc(self, method, params):
        import select
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        while True:
            ready, _, _ = select.select([self.p.stdout], [], [], self.timeout)
            if not ready:
                raise RuntimeError(f"MCP 응답 없음({method})")
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP 서버가 끝났습니다({method})")
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("id") == self.n:
                if "error" in r:
                    raise RuntimeError(f"MCP {method} 실패: {r['error'].get('message', r['error'])}")
                return r.get("result") or {}

    def call(self, tool: str, args: dict | None = None) -> dict:
        """도구 결과 → {"text": 글자 합침, "images": [bytes…]}. isError 면 RuntimeError"""
        res = self._rpc("tools/call", {"name": tool, "arguments": args or {}})
        text, imgs = [], []
        for c in res.get("content") or []:
            if c.get("type") == "image":
                imgs.append(base64.b64decode(c["data"]))
            elif c.get("type") == "text":
                text.append(c.get("text", ""))
        if res.get("isError"):
            raise RuntimeError(f"{tool} 실패: {' '.join(text)[:300]}")
        return {"text": "\n".join(text), "images": imgs}

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


# ---------------------------------------------------------------- OBJ 다루기(앱 없이)
def to_y_up(src: Path, dst: Path, stage: bool = True) -> dict:
    """Z 위 OBJ(SolidCraft) → Y 위 OBJ(TextureCraft). (x, y, z) → (x, z, -y) — 앞(-Y)이 카메라 쪽(+Z)이 된다.
    stage 면 바닥에 얇은 원판(Stage)을 붙인다. 돌려준 값: 제품 경계 상자 {min, max}(Y 위) · 몸체 이름들"""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    out, bodies, nv = [], [], 0
    for line in src.read_text("utf-8", "replace").splitlines():
        if line.startswith(("v ", "vn ")):
            p = line.split()
            x, y, z = float(p[1]), float(p[2]), float(p[3])
            q = (x, z, -y)
            if p[0] == "v":
                nv += 1
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])
            out.append(f"{p[0]} {q[0]:.6g} {q[1]:.6g} {q[2]:.6g}")
        elif line.startswith("mtllib"):
            continue                                  # 색은 재질 단계가 다시 칠한다(mtl 경로가 어긋나도 열리게)
        elif line.startswith("o "):                   # 몸체마다 텍스처 세트 하나: 재질 이름 = 몸체 이름(색이 없는 몸체도 나뉘게)
            name = line.split(None, 1)[1].strip()
            bodies.append(name)
            out += [line, f"usemtl {name}"]
        elif line.startswith("usemtl "):
            if not bodies:
                name = line.split(None, 1)[1].strip()
                bodies.append(name)
                out.append(f"usemtl {name}")
        else:
            out.append(line)
    if not nv:
        raise RuntimeError(f"OBJ 에 꼭짓점이 없습니다: {src.name}")
    if not bodies:                                    # 재질 이름이 없는 메시(STL 변환 등) → 하나로
        out.insert(0, "usemtl Body1")
        bodies = ["Body1"]
    if stage:
        out += _disc(lo, hi, nv)
    dst.write_text("\n".join(out) + "\n", "utf-8")
    return {"min": lo, "max": hi, "bodies": bodies}


def _disc_r(lo, hi) -> float:
    """받침 반지름: 제품 바닥 대각선 절반보다 조금 크게"""
    return 0.58 * math.hypot(hi[0] - lo[0], hi[2] - lo[2]) + 0.04 * (hi[1] - lo[1])


def _disc(lo, hi, nv0: int, seg: int = 96) -> list[str]:
    """제품 아래 얇은 받침 원판(Stage)"""
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    r = _disc_r(lo, hi)
    t = max(1.0, 0.035 * r)
    y1, y0 = lo[1] - 0.05, lo[1] - 0.05 - t
    L = ["o Stage", "usemtl Stage"]
    for y in (y1, y0):
        for k in range(seg):
            a = 2 * math.pi * k / seg
            L.append(f"v {cx + r * math.cos(a):.5g} {y:.5g} {cz + r * math.sin(a):.5g}")
    L += [f"v {cx:.5g} {y1:.5g} {cz:.5g}", f"v {cx:.5g} {y0:.5g} {cz:.5g}"]
    top, bot, ct, cb = nv0 + 1, nv0 + 1 + seg, nv0 + 2 * seg + 1, nv0 + 2 * seg + 2
    for k in range(seg):
        a, b = k, (k + 1) % seg
        L.append(f"f {ct} {top + b} {top + a}")                       # 윗면(위에서 보면 반시계)
        L.append(f"f {cb} {bot + a} {bot + b}")
        L.append(f"f {top + a} {top + b} {bot + b} {bot + a}")         # 옆면
    return L


def fit_distance(lo, hi, yaw_list, pitch: float, fov: float, aspect: float, fill: float = 0.78, extra: list | None = None) -> tuple[list, float]:
    """카메라 거리: 여러 yaw(턴테이블) 모두에서 상자 모서리 8개(+ extra 점들)가 화면 fill 비율 안에 들어오는 가장 가까운 거리.
    대상은 상자 가운데. fov 는 세로 화각(도 — 렌더로 확인), aspect = 폭/높이.
    TextureCraft 카메라: 눈 = 대상 + d·(cos p · sin y, sin p, cos p · cos y)"""
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])] + list(extra or [])
    ty = math.tan(math.radians(fov) / 2)
    tx = ty * aspect

    def fits(d):
        for yw in yaw_list:
            yr, pr = math.radians(yw), math.radians(pitch)
            f = (-math.cos(pr) * math.sin(yr), -math.sin(pr), -math.cos(pr) * math.cos(yr))      # 보는 방향
            r = (math.cos(yr), 0.0, -math.sin(yr))                                              # 오른쪽
            u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])  # 위 = 오른쪽 × 앞
            eye = [c[k] - d * f[k] for k in range(3)]
            for p in corners:
                v = [p[k] - eye[k] for k in range(3)]
                z = sum(v[k] * f[k] for k in range(3))
                if z <= 1e-6:
                    return False
                if abs(sum(v[k] * r[k] for k in range(3)) / z) > tx * fill or abs(sum(v[k] * u[k] for k in range(3)) / z) > ty * fill:
                    return False
        return True

    size = max(hi[k] - lo[k] for k in range(3)) or 1.0
    a, b = size * 0.05, size * 200
    for _ in range(60):
        mid = (a + b) / 2
        a, b = (a, mid) if fits(mid) else (mid, b)
    return c, b


# ---------------------------------------------------------------- 재질 · 로고 · 렌더
def _hex(c: str) -> str | None:
    c = str(c).strip()
    if c.startswith("#") and len(c) in (4, 7):
        return c if len(c) == 7 else "#" + "".join(ch * 2 for ch in c[1:])
    return None


DARK = {"steel_dark", "wood_walnut", "rubber", "marble_black", "cast_iron", "slate", "asphalt", "bark", "leather", "copper_patina"}


def _ink(spec) -> str:
    """로고 글자색: 밝은 표면엔 짙은 회색, 어두운 표면엔 흰색"""
    h = spec.get("color") if isinstance(spec, dict) else _hex(spec) if spec else None
    if h and _hex(h):
        h = _hex(h)
        r, g, b = (int(h[k:k + 2], 16) for k in (1, 3, 5))
        return "#1f2937" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 else "#ffffff"
    name = MATERIALS.get(str(spec).lower(), str(spec)) if spec else ""
    return "#ffffff" if name in DARK else "#1f2937"


def _aspect(logo: dict) -> float:
    """로고 폭 / 높이. 글자는 대략(한글 1, 라틴 0.62 글자 높이), 그림은 실제 크기"""
    if logo.get("text"):
        lines = str(logo["text"]).split("\n")
        wide = max(sum(1.0 if ord(ch) > 0x1100 else 0.62 for ch in ln) for ln in lines)
        return max(0.5, wide / (1.1 * len(lines)))
    try:
        from PIL import Image
        with Image.open(logo["image"]) as im:
            return im.width / max(1, im.height)
    except Exception:  # noqa: BLE001
        return 1.0


def _surface_steps(spec, finish: str = "plastic") -> list[dict]:
    """재질 한 칸 → 단계들. 색(#rrggbb) 이면 채우기 층, 이름이면 TextureCraft 재질"""
    if isinstance(spec, dict):                  # {"color": "#..", "roughness": .., "metallic": ..}
        return [{"id": "layer.add.fill", "params": {k: spec[k] for k in ("color", "roughness", "metallic") if k in spec}}]
    h = _hex(spec) if spec else None
    if h:
        rough, metal = FINISH.get(finish, FINISH["plastic"])
        return [{"id": "layer.add.fill", "params": {"color": h, "roughness": rough, "metallic": metal}}]
    if str(spec).lower() in CLEAN:
        col, rough, metal = CLEAN[str(spec).lower()]
        return [{"id": "layer.add.fill", "params": {"color": col, "roughness": rough, "metallic": metal}}]
    name = MATERIALS.get(str(spec).lower(), str(spec))
    return [{"id": "material.apply", "params": {"material": name}}]


def build_project(cli: str, mesh: Path, proj: Path, work: Path, bodies: list[str], materials: dict, box: dict,
                  logo: dict | None = None, stage_color: str = "#d9dde3", resolution: int = 1024, bake: bool = True) -> dict:
    """메시 → .tcraft: 굽기 → 몸체(텍스처 세트)마다 재질 → 받침 → 로고 데칼. 실패한 단계 번호를 메시지에 넣는다"""
    from ..materials import _run
    info = json.loads(_run([cli, "info", mesh], work))
    sets = list(info.get("textureSets") or [])
    # bake=False: 단색 · PBR 값만 칠할 때 — 굽기를 건너뛴다(GPU 메모리 · 시간 절약, 스마트 재질 · 먼지 같은 표면 효과에는 굽기가 필요)
    steps = [{"id": "bake.run", "params": {"ts": "all", "resolution": resolution}}] if bake else []
    for i, name in enumerate(sets):
        steps.append({"id": "textureSet.select", "params": {"ts": i}})
        if not bake:
            steps.append({"id": "textureSet.resolution", "params": {"ts": i, "resolution": resolution}})
        if name == STAGE:
            steps.append({"id": "layer.add.fill", "params": {"color": stage_color, "roughness": 0.55, "metallic": 0.0}})
        else:
            steps += _surface_steps(materials.get(name) or materials.get("*") or DEFAULT, materials.get("finish", "plastic"))
    lo, hi = box["min"], box["max"]
    if logo:
        # 데칼은 고른 텍스처 세트에만 붙는다 → 앞면에 있는 몸체(logo_on, 기본: 첫 몸체)
        on = logo.get("on") or bodies[0]
        if on in sets:
            steps.append({"id": "textureSet.select", "params": {"ts": sets.index(on)}})
        if logo.get("image"):
            steps.append({"id": "resource.import", "params": {"path": str(logo["image"])}})
            res = Path(logo["image"]).name
        else:
            steps.append({"id": "resource.text", "params": {"text": logo["text"], "font": "Noto Sans CJK KR", "style": logo.get("style", "Bold"),
                                                            "size": 256, "color": logo.get("color") or _ink(materials.get(on)), "name": "logo"}})
            res = "Text_logo.png"
        w, h = hi[0] - lo[0], hi[1] - lo[1]
        side = logo.get("side", "front")
        if side == "top":
            pos, nrm, up = [(lo[0] + hi[0]) / 2, hi[1] + 0.01, (lo[2] + hi[2]) / 2], [0, 1, 0], [0, 0, -1]
            size = logo.get("size") or 0.22 * min(w, hi[2] - lo[2])
        elif logo.get("round"):
            # 둥근 몸체: 카메라 쪽(yaw)을 보는 자리에 — 앞면(+Z)에 두면 비스듬히 돌아가 보인다
            a = math.radians(float(logo.get("yaw", 0)))
            rad = max(hi[0] - lo[0], hi[2] - lo[2]) / 2
            cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
            pos = [cx + (rad + 0.01) * math.sin(a), lo[1] + h * float(logo.get("y", 0.55)), cz + (rad + 0.01) * math.cos(a)]
            nrm, up = [math.sin(a), 0, math.cos(a)], [0, 1, 0]
        else:
            pos, nrm, up = [(lo[0] + hi[0]) / 2, lo[1] + h * float(logo.get("y", 0.55)), hi[2] + 0.01], [0, 0, 1], [0, 1, 0]
        if side != "top":
            # 폭 기준: 평면은 몸체 폭의 0.6, 둥근 몸체도 0.62(데칼은 평면 투영이라 옆으로 많이 돌아가는 곳은 늘어난다)
            room = w * (0.62 if logo.get("round") else 0.6)
            size = logo.get("size") or min(0.22 * h, room / _aspect(logo))
        steps.append({"id": "layer.add.decal", "params": {"image": res, "position": pos, "normal": nrm, "up": up, "size": size, "name": "logo"}})
    steps.append({"id": "display.set", "params": {"shadows": True, "aoIntensity": 0.9, "taa": True, "exposure": 0.4}})
    sp = work / (proj.stem + ".tc.json")
    sp.write_text(json.dumps({"open": str(mesh), "steps": steps, "save": str(proj)}, ensure_ascii=False, indent=1), "utf-8")
    try:
        out = _run([cli, "batch", sp], work, timeout=300)
    except RuntimeError as e:
        if "unknown material" in str(e):
            raise RuntimeError(f"모르는 재질입니다 — 쉬운 이름({', '.join(sorted(set(CLEAN) | set(MATERIALS)))[:300]}…), 색 '#rrggbb', "
                               f"또는 TextureCraft 재질 id(texturecraft-cli run builtin:cube material.list): {str(e)[-120:]}") from None
        raise
    try:
        rep = json.loads(out[:out.rfind("}") + 1]) if "{" in out else {}
    except ValueError:
        rep = {}
    if rep.get("failed") or not proj.exists():
        f = rep.get("failed") or {}
        raise RuntimeError(f"TextureCraft 재질 단계 실패({f.get('index')}: {f.get('id')}): {str(f.get('error'))[:200]}")
    return {"texture_sets": sets}


def render(cli: str, proj: Path, work: Path, frames: list[tuple[float, float]], target, distance: float, fov: float,
           size: tuple[int, int], dst: list[Path], samples: int | None = None):
    """같은 세션에서 (yaw, pitch) 마다 한 장씩. 카메라 대상 · 거리 · 화각은 먼저 정한다"""
    W, H = size
    with Mcp([cli, "mcp", "--read-root", proj.parent, "--write-root", proj.parent], work) as s:
        s.call("project_open", {"path": proj.name})
        s.call("command_run", {"id": "camera.set", "params": {"target": list(target), "distance": distance, "fov": fov,
                                                             "yaw": frames[0][0], "pitch": frames[0][1]}})
        for (yaw, pitch), f in zip(frames, dst):
            a = {"width": W, "height": H, "yaw": yaw, "pitch": pitch}
            if samples:
                a["samples"] = samples
            r = s.call("viewport_render", a)
            if not r["images"]:
                raise RuntimeError(f"TextureCraft 렌더가 그림을 돌려주지 않았습니다: {r['text'][:200]}")
            f.write_bytes(r["images"][0])


def shot(mesh_z_up: Path, out: Path, work: Path, m: dict, bodies_meta: dict | None = None) -> dict:
    """Z 위 OBJ → 재질 · 로고 → 9:16 정지 PNG(out) 또는 턴테이블 mp4(out.with_suffix('.mp4')).
    m: 콘티 재료(material · logo · turntable · sec · yaw · pitch · stage · finish). bodies_meta: 형태가 정한 몸체별 기본 재질"""
    from ..materials import cli as _cli, _abs
    cli = _cli("texturecraft")
    stem = out.stem
    mesh = work / f"{stem}.y.obj"
    stage = m.get("stage", True) is not False
    box = to_y_up(mesh_z_up, mesh, stage=stage)
    bodies = box["bodies"]
    mats = _materials(m, bodies, bodies_meta or {})
    logo = None
    if m.get("logo"):
        lg = m["logo"]
        lg = {"text": lg} if isinstance(lg, str) and not lg.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else lg
        lg = {"image": lg} if isinstance(lg, str) else dict(lg)
        if lg.get("image"):
            p = _abs(lg["image"])
            if not p.exists():
                raise RuntimeError(f"로고 그림이 없습니다: {lg['image']}")
            lg["image"] = p
        if (bodies_meta or {}).get("_logo_on") and not lg.get("on"):
            lg["on"] = bodies_meta["_logo_on"]
        for k in ("side", "round", "y"):         # 형태가 정한 로고 자리(윗면 · 둥근 몸체 · 높이)
            if (bodies_meta or {}).get(f"_logo_{k}") is not None:
                lg.setdefault(k, bodies_meta[f"_logo_{k}"])
        logo = lg
    yaw0 = float(m.get("yaw", 32))
    if logo is not None:
        logo.setdefault("yaw", yaw0)
    proj = work / f"{stem}.tcraft"
    st = build_project(cli, mesh, proj, work, bodies, mats, box, logo, stage_color=m.get("stage_color", "#d9dde3"))
    W, H = int(m.get("width", 1080)), int(m.get("height", 1920))
    fov = float(m.get("fov", 28))
    pitch = float(m.get("pitch", 18))
    yaw0 = float(m.get("yaw", 32))
    lo, hi = box["min"], box["max"]
    rim = []
    if stage:                                   # 받침 테두리도 화면 안에
        r = _disc_r(lo, hi)
        cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
        rim = [(cx + r * math.cos(a / 12 * math.pi), lo[1], cz + r * math.sin(a / 12 * math.pi)) for a in range(24)]
    info = {"app": "texturecraft", "editable": None, "size": [W, H], "materials": mats, "texture_sets": st["texture_sets"]}
    if m.get("turntable"):
        sec = float(m.get("sec", 4))
        fps = int(m.get("fps", 30))
        n = max(12, min(int(sec * fps), 300))
        turns = float(m.get("turns", 1))
        yaws = [yaw0 + 360.0 * turns * k / n for k in range(n)]
        target, d = fit_distance(lo, hi, yaws[:: max(1, n // 24)], pitch, fov, W / H, float(m.get("fill", 0.86)), rim)
        target[1] = target[1] + (hi[1] - lo[1]) * 0.02
        fd = work / f"{stem}.frames"
        fd.mkdir(exist_ok=True)
        for f in fd.glob("f*.png"):
            f.unlink()
        files = [fd / f"f{k + 1:04d}.png" for k in range(n)]
        render(cli, proj, work, [(y, pitch) for y in yaws], target, d, fov, (W, H), files)
        mp4 = out.with_suffix(".mp4")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(fd / "f%04d.png"),
                            "-vf", "format=yuv420p", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(mp4)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"턴테이블 영상 만들기 실패: {r.stderr[-200:]}")
        # 첫 장은 PNG 로도 남긴다(미리 보기 · 썸네일). 프레임 폴더는 지운다(1080×1920 120장이면 수백 MB)
        out.write_bytes(files[0].read_bytes())
        import shutil
        shutil.rmtree(fd, ignore_errors=True)
        info.update({"file_suffix": ".mp4", "as": "video", "frames": n, "fps": fps, "sec": round(n / fps, 2), "poster": str(out.name)})
    else:
        target, d = fit_distance(lo, hi, [yaw0], pitch, fov, W / H, float(m.get("fill", 0.86)), rim)
        render(cli, proj, work, [(yaw0, pitch)], target, d, fov, (W, H), [out], samples=int(m.get("samples", 64)) or None)
        info["as"] = "image"
    info["camera"] = {"target": [round(v, 2) for v in target], "distance": round(d, 2), "fov": fov, "pitch": pitch, "yaw": yaw0}
    return info


def _materials(m: dict, bodies: list[str], meta: dict) -> dict:
    """콘티 material(문자 · 색 · {몸체: 재질}) + 형태 기본값 → {몸체: 재질}"""
    spec = m.get("material")
    out = {}
    for b in bodies:
        d = meta.get(b) or {}
        if isinstance(spec, dict):
            v = spec.get(b) or spec.get(d.get("role", "")) or (None if d.get("fixed") else spec.get("*"))
        else:
            v = None if d.get("material") else spec     # 재질 하나만 주면 본체에만(마개 · 화면처럼 제 색이 있는 부품은 그대로)
        if v is None:
            v = d.get("material")
        if isinstance(v, str) and v.lower() in CLEAN and m.get("color") and _hex(m["color"]) and not d.get("material"):
            v = {"color": _hex(m["color"]), "roughness": CLEAN[v.lower()][1], "metallic": CLEAN[v.lower()][2]}   # 색 + 표면(아노다이징 금속 등)
        if v is None and not d.get("fixed"):
            v = m.get("color") or DEFAULT
        if isinstance(v, str) and _hex(v) and d.get("finish") and not m.get("finish"):
            v = {"color": _hex(v), "roughness": FINISH[d["finish"]][0], "metallic": FINISH[d["finish"]][1]}
        out[b] = v or DEFAULT
    if m.get("finish"):
        out["finish"] = m["finish"]
    return out


ADAPTERS: dict = {}     # 혼자 쓰는 재료 없음 — model3d(SolidCraft 어댑터)가 shot() 을 부른다
