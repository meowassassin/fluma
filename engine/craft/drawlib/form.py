"""그리기 엔진 2단계 — 형태(form.json)를 풀어 덩어리 배치로. 좌표 없음.

설계: 볼트 02 Architecture/그리기 엔진 설계 — 구조로 그리기.md (3.1 · 3.2절)

형태는 부품 나무다. 부품마다
  shape   blob · ellipsoid · capsule · box · cylinder · sweep · leaf
  size    단위 높이(U) 기준 비율 — { h, w } 또는 capsule · sweep 은 len + r [시작, 끝]
  attach  { to: 부모, v: 0(위)~1(아래), az: 둘레 각도(0 정면 · ±90 옆 · 180 뒤) 또는 u: 가로 위치(−1 왼쪽 끝 ~ 1 오른쪽 끝,
          납작한 물체 · 가로로 긴 상자용), inset: 파고들기(U) }
          이름으로도: top · bottom · front · back · side_near · side_far · center
  dir     관(capsule · sweep)이 뻗는 방향: 부모의 아래쪽에서 잰 각도. 0 = 아래로 늘어짐 · 90 = 앞(바라보는 쪽) · 180 = 위 · −90 = 뒤.
          좌우 대칭(mirror)해도 그대로 — 두 다리는 같은 쪽으로 걷는다
  splay   몸 바깥으로 벌어지는 각도(도). 붙은 쪽 바깥으로 벌어지고, 대칭 부품은 저절로 반대로 벌어진다(팔 · 다리 벌림)
  tilt    부모 축에 대한 기울기(도)
  merge   true 면 부모와 한 실루엣으로 부드럽게 합친다(머리 + 몸 · 몸 + 꼬리). 색 역할이 같을 때만
  decal   true 면 표면 무늬(눈 · 배 · 무늬 · 창문): 부모 표면에 납작하게 붙고, 뒤쪽 면에 오면 그리지 않는다.
          무늬 위의 무늬(눈동자)는 시점 회전을 다시 받지 않는다
  mirror  다른 부품 id — 그 부품을 둘레 각도 · 방향만 뒤집어 복사(좌우 대칭)
  role    색 역할 main · main_dark · accent · accent2 · light · dark · white · black
  ground  true 면 이 부품의 가장 낮은 점이 바닥에 닿게 전체를 옮긴다(발)
  limb    2관절 팔다리: { shape: "limb", len, r: [어깨, 관절, 끝], bend: 관절 각도(+ = 앞으로 접힘), kind: arm | leg, dir, splay }
          → <id>(윗마디) + <id>_lo(아랫마디) 두 부품으로 펼쳐진다. ground 는 아랫마디에
  cut     true 면 부모를 이 모양으로 파낸다(후드 구멍 · 입 · 창). 구멍은 부모 색보다 어두운 그늘로 채워지고,
          이 부품에 붙인 자식(얼굴 등)은 구멍 안에 그려진다

시점(view)과 바라보는 쪽(facing)은 형태 전체에 하나: 둘레 각도 az 가 화면 x 와 앞뒤(z)로 투영된다.
  x = 반폭 × sin(az + yaw),  z = cos(az + yaw)   (yaw: front 0 · 3/4 35 · side 80)
그래서 3/4 에서 먼 쪽 팔 · 눈은 몸 뒤나 가장자리로 저절로 간다. facing=left 는 마지막에 좌우를 뒤집는다.
둘레 각도 부호: 음수(az < 0) = 보는 사람 쪽(가까운 면), 양수 = 먼 면. side_near = −90, side_far = +90.

못 풀면 그리지 않고 '의미로 된 오류'를 돌려준다(SolveError). 좌표를 고치라고 하지 않고 관계를 고치라고 말한다.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import geom

U = 100.0                                       # 단위 높이 1 = 100 (그림 좌표)
YAW = {"front": 0.0, "3/4": 35.0, "side": 80.0}
SHAPES = {"blob", "ellipsoid", "capsule", "box", "cylinder", "sweep", "leaf", "limb"}
ROLES = {"main", "main_dark", "accent", "accent2", "light", "dark", "white", "black"}
NAMED = {
    "top": (0.0, 0.0), "bottom": (1.0, 0.0), "center": (0.5, 0.0), "front": (0.5, 0.0), "back": (0.5, 180.0),
    "side_near": (0.5, -90.0), "side_far": (0.5, 90.0),
}


class SolveError(Exception):
    """형태를 풀 수 없음 — problems 는 사람이 읽는 문장 목록"""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Placed:
    id: str
    shape: geom.Shape
    z: float                      # 앞뒤(클수록 앞)
    role: str
    parent: str | None
    layer: str                    # 같은 layer 끼리 한 실루엣(merge)
    pivot: tuple[float, float]    # 부모에 붙은 점(관절) — 5단계 뼈대에서 회전축
    angle: float                  # 화면에서 이 부품의 '아래' 축 각도(도)
    spec: dict = field(default_factory=dict)


# ---------------------------------------------------------------- 부품 하나의 제 좌표 틀
@dataclass
class Frame:
    """부품의 틀: top(위 끝 가운데) · 축 각도 · 높이 · 반폭 프로필"""
    top: np.ndarray
    angle: float          # 0 = 아래가 화면 아래
    h: float
    w: float
    profile: str          # 'ellipse' (가운데가 가장 넓음) · 'flat' (높이 내내 같음) · 'taper' (위→아래 반지름 보간)
    r0: float = 0.0
    r1: float = 0.0
    path: list | None = None          # 굽은 관(sweep)의 실제 중심선 — 붙을 자리가 곡선을 따라가게

    def down(self) -> np.ndarray:
        a = math.radians(self.angle)
        return np.array([math.sin(a), math.cos(a)])

    def right(self) -> np.ndarray:
        d = self.down()
        return np.array([d[1], -d[0]])           # 아래 축을 시계 반대로 90° — 화면 오른쪽(바라보는 쪽)

    def half_width(self, v: float) -> float:
        if self.profile == "ellipse":
            return self.w / 2 * math.sqrt(max(0.0, 1 - (2 * v - 1) ** 2))
        if self.profile == "taper":
            return self.r0 + (self.r1 - self.r0) * v
        return self.w / 2

    def along(self, v: float) -> tuple[np.ndarray, np.ndarray]:
        """중심선 위 v(0~1) 의 점과 그 자리 오른쪽 방향(곡선이면 곡선을 따라)"""
        if not self.path:
            return self.top + self.down() * (v * self.h), self.right()
        P = np.asarray(self.path, float)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        s = np.r_[0, np.cumsum(seg)]
        t = v * s[-1]
        i = int(min(max(np.searchsorted(s, t) - 1, 0), len(seg) - 1))
        f = (t - s[i]) / seg[i] if seg[i] > 0 else 0.0
        q = P[i] + (P[i + 1] - P[i]) * f
        d = (P[i + 1] - P[i]) / (seg[i] or 1.0)
        return q, np.array([d[1], -d[0]])

    def point(self, v: float, az: float, yaw: float, inset: float = 0.0) -> tuple[np.ndarray, float]:
        """표면 점(v, az) → 화면 점과 앞뒤 z. inset 만큼 안쪽으로"""
        s, c = math.sin(math.radians(az + yaw)), math.cos(math.radians(az + yaw))
        if self.path:
            q, rt = self.along(v)
            return q + rt * (max(self.half_width(v) - inset, 0.0) * s), c
        hw = max(self.half_width(v) - inset, 0.0)
        # 위 · 아래 끝(v=0,1)은 둘레와 상관없이 끝점, 그 사이는 반폭만큼 옆으로
        p = self.top + self.down() * (v * self.h) + self.right() * (hw * s)
        if v in (0.0, 1.0):
            p = p + self.down() * (inset if v == 0.0 else -inset)
        return p, c


def _num(spec: dict, key: str, default=None, lo=None, hi=None, problems=None, pid="?"):
    v = spec.get(key, default)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        problems.append(f"{pid}: {key} 는 숫자여야 합니다 (지금 {spec.get(key)!r})")
        return default
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        problems.append(f"{pid}: {key}={v:g} 는 {lo:g}~{hi:g} 사이여야 합니다")
    return v


def _expand_limbs(parts: list[dict], problems: list[str]) -> list[dict]:
    """limb → 윗마디 capsule + 아랫마디 capsule(윗마디 끝에 붙고 bend 만큼 꺾임)"""
    out = []
    for p in parts:
        if p.get("shape") != "limb":
            out.append(p)
            continue
        pid = p.get("id")
        L = float(p.get("len", 0.6))
        r = [float(x) for x in (p.get("r") or [0.08, 0.065, 0.055])]
        if len(r) == 2:
            r = [r[0], (r[0] + r[1]) / 2, r[1]]
        kind = p.get("kind") or ("leg" if p.get("ground") else "arm")
        up = {k: v for k, v in p.items() if k not in ("shape", "len", "r", "bend", "ground", "kind")}
        up.update({"shape": "capsule", "len": round(L * 0.52, 4), "r": [r[0], r[1]], "limb_kind": kind})
        lo = {"id": f"{pid}_lo", "shape": "capsule", "len": round(L * 0.5, 4), "r": [r[1], r[2]], "role": p.get("role", "main"),
              "attach": {"to": pid, "at": "bottom", "inset": round(r[1] * 0.9, 4)}, "dir": float(p.get("bend", 0)), "limb_kind": kind}
        if p.get("ground"):
            lo["ground"] = True
        out += [up, lo]
    return out


def _expand_mirrors(parts: list[dict], problems: list[str]) -> list[dict]:
    byid = {p.get("id"): p for p in parts}
    out = []
    for p in parts:
        m = p.get("mirror")
        if not m:
            out.append(p)
            continue
        src = byid.get(m)
        if not src:
            problems.append(f"{p.get('id')}: mirror 대상 '{m}' 이 없습니다")
            continue
        q = copy.deepcopy(src)
        q.update({k: v for k, v in p.items() if k not in ("mirror",)})
        att = dict(q.get("attach") or {})
        if isinstance(att.get("at"), str) and att["at"] in ("side_near", "side_far"):
            att["at"] = "side_far" if att["at"] == "side_near" else "side_near"
        if "az" in att:
            att["az"] = -float(att["az"])
        q["attach"] = att
        if "u" in att:
            att["u"] = -float(att["u"])
        q["attach"] = att
        q["_mirror_of"] = m
        out.append(q)
    return out


ARCHETYPES = Path(__file__).resolve().parents[3] / "data" / "library" / "archetypes"


def _deep(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def expand(form: dict) -> dict:
    """archetype(몸 설계도)를 펼친다: 설계도 부품 ← 같은 id 는 덮어쓰기, 새 id 는 더하기, remove 목록은 빼기"""
    name = form.get("archetype")
    if not name:
        return form
    f = ARCHETYPES / f"{name}.form.json"
    if not f.exists():
        have = " · ".join(sorted(p.name[: -len('.form.json')] for p in ARCHETYPES.glob("*.form.json")))
        raise SolveError([f"archetype '{name}' 이 없습니다 — {have} 중에서 고르거나 parts 로 직접 지으세요"])
    base = json.loads(f.read_text("utf-8"))
    parts = {p["id"]: p for p in base.get("parts", [])}
    order = [p["id"] for p in base.get("parts", [])]
    for p in form.get("parts") or []:
        pid = p.get("id")
        if pid in parts:
            parts[pid] = _deep(parts[pid], p)
        else:
            parts[pid] = p
            order.append(pid)
    gone = set(form.get("remove") or [])
    out = {**base, **{k: v for k, v in form.items() if k not in ("parts", "archetype", "remove")}}
    out["parts"] = [parts[i] for i in order if i not in gone and (parts[i].get("mirror") not in gone)]
    return out


def solve(form: dict) -> tuple[list[Placed], list[str]]:
    """형태 → 배치된 덩어리들(뒤 → 앞 순서)과 경고. 풀 수 없으면 SolveError"""
    form = expand(form)
    problems: list[str] = []
    warnings: list[str] = []
    view = form.get("view", "3/4")
    if view not in YAW:
        problems.append(f"view 는 {' · '.join(YAW)} 중 하나여야 합니다 (지금 {view!r})")
    yaw = YAW.get(view, 35.0)
    facing = form.get("facing", "right")
    if facing not in ("left", "right"):
        problems.append("facing 은 left 또는 right 입니다")

    parts = _expand_limbs(_expand_mirrors(list(form.get("parts") or []), problems), problems)
    if not parts:
        raise SolveError(["parts 가 비어 있습니다 — 부품을 하나 이상 주세요"])
    ids = [p.get("id") for p in parts]
    for i, pid in enumerate(ids):
        if not pid or not isinstance(pid, str):
            problems.append(f"{i}번째 부품에 id 가 없습니다")
        elif ids.count(pid) > 1:
            problems.append(f"id '{pid}' 가 두 번 쓰였습니다")
    byid = {p.get("id"): p for p in parts}
    roots = [p for p in parts if not (p.get("attach") or {}).get("to")]
    if len(roots) != 1:
        problems.append(f"뿌리 부품(attach.to 없음)은 하나여야 합니다 — 지금 {len(roots)}개: {', '.join(str(r.get('id')) for r in roots)}")
    for p in parts:
        to = (p.get("attach") or {}).get("to")
        if to and to not in byid:
            problems.append(f"{p.get('id')}: 붙일 부모 '{to}' 가 없습니다")
        if p.get("shape") not in SHAPES:
            problems.append(f"{p.get('id')}: shape 는 {' · '.join(sorted(SHAPES))} 중 하나입니다 (지금 {p.get('shape')!r})")
        if p.get("role", "main") not in ROLES:
            problems.append(f"{p.get('id')}: role 은 {' · '.join(sorted(ROLES))} 중 하나입니다")
        for bad in ("x", "y", "cx", "cy", "pos", "position", "points", "pts"):
            if bad in p:
                problems.append(f"{p.get('id')}: 좌표({bad})는 쓰지 않습니다 — attach(어디에 · v · az)와 크기 비율로 말해 주세요")
    if problems:
        raise SolveError(problems)

    # 부모 → 자식 순서(순환 검사)
    order, state = [], {}

    def visit(pid, chain):
        if state.get(pid) == 2:
            return
        if state.get(pid) == 1:
            problems.append(f"붙이기가 고리를 이룹니다: {' → '.join(chain + [pid])}")
            return
        state[pid] = 1
        to = (byid[pid].get("attach") or {}).get("to")
        if to:
            visit(to, chain + [pid])
        state[pid] = 2
        order.append(pid)

    for pid in byid:
        visit(pid, [])
    if problems:
        raise SolveError(problems)

    frames: dict[str, Frame] = {}
    hidden: set[str] = set()
    zs: dict[str, float] = {}
    placed: dict[str, Placed] = {}
    for pid in order:
        p = byid[pid]
        shape = p["shape"]
        size = p.get("size") or {}
        att = p.get("attach") or {}
        parent = att.get("to")
        tilt = _num(p, "tilt", 0.0, -180, 180, problems, pid)

        # --- 크기 (U 비율)
        if shape in ("capsule", "sweep"):
            length = _num(p, "len", None, 0.02, 6, problems, pid)
            r = p.get("r") or [0.08, 0.06]
            if not isinstance(r, list) or not r:
                problems.append(f"{pid}: r 는 [시작 반지름, 끝 반지름] 입니다")
                continue
            r0, r1 = float(r[0]), float(r[-1])
            if length is None:
                problems.append(f"{pid}: {shape} 에는 len(길이, 단위 높이 비율)이 필요합니다")
                continue
            h, w = length * U, 2 * max(r0, r1) * U
        else:
            h = _num(size, "h", None, 0.02, 8, problems, pid)
            w = _num(size, "w", h, 0.02, 8, problems, pid)
            if h is None:
                problems.append(f"{pid}: size.h(높이, 단위 높이 비율)가 필요합니다")
                continue
            h, w = h * U, w * U
            r0 = r1 = 0.0

        # --- 놓기
        if parent is None:
            angle = tilt
            pf_top = np.array([0.0, 0.0])
            z = 0.0
            pivot = np.array([0.0, h / 2])
            joint = pivot
        else:
            pf = frames.get(parent)
            if pf is None:
                problems.append(f"{pid}: 부모 '{parent}' 를 먼저 풀지 못했습니다")
                continue
            at = att.get("at")
            if isinstance(at, str):
                if at not in NAMED:
                    problems.append(f"{pid}: attach.at '{at}' 는 {' · '.join(NAMED)} 중 하나입니다")
                    continue
                v, az = NAMED[at]
            else:
                v, az = 0.5, 0.0
            v = _num(att, "v", v, 0, 1, problems, pid)
            az = _num(att, "az", az, -180, 180, problems, pid)
            inset = (_num(att, "inset", 0.05, -0.2, 2, problems, pid) or 0.0) * U
            parent_decal = bool(byid[parent].get("decal"))
            if "u" in att:   # 가로 위치: 납작한 물체 · 가로로 긴 상자 — 앞면에 붙는다
                u = _num(att, "u", 0.0, -1, 1, problems, pid)
                joint = pf.top + pf.down() * (v * pf.h) + pf.right() * (pf.half_width(v) * u)
                if v in (0.0, 1.0):
                    joint = joint + pf.down() * (inset if v == 0.0 else -inset)
                zc = 0.3
                side = u
            else:
                joint, zc = pf.point(v, az, 0.0 if parent_decal else yaw, inset)
                side = math.sin(math.radians(az + (0.0 if parent_decal else yaw)))
            if p.get("decal") and not parent_decal and zc < 0.15:
                hidden.add(pid)                         # 뒤쪽 면의 무늬는 안 보인다(자식도 함께)
            if parent in hidden:
                hidden.add(pid)
            if parent_decal:
                zc = 1.0                                # 무늬 위의 무늬는 늘 그 무늬 앞
            z = zs[parent] + zc * 0.5 + 0.01           # 앞쪽 표면에 붙으면 부모보다 앞, 뒤쪽이면 뒤
            # 관 모양은 붙은 점에서 dir 방향으로 뻗는다. 덩어리는 붙은 자리 반대쪽 끝이 붙는다
            if shape in ("capsule", "sweep"):
                # dir: + = 바라보는 쪽(앞). splay: 붙은 쪽 바깥으로(대칭 부품은 side 부호가 반대라 저절로 반대로 벌어짐)
                splay = _num(p, "splay", 0.0, -90, 90, problems, pid) or 0.0
                out = -1.0 if side < -1e-6 else 1.0 if side > 1e-6 else 0.0
                angle = pf.angle + _num(p, "dir", 0.0, -180, 180, problems, pid) + out * splay
                pf_top = joint
            else:
                angle = pf.angle + tilt
                d = np.array([math.sin(math.radians(angle)), math.cos(math.radians(angle))])
                own_v = 1.0 if v < 0.34 else 0.0 if v > 0.66 else 0.5     # 위에 붙으면 아래 끝이, 아래에 붙으면 위 끝이
                pf_top = joint - d * (own_v * h)
            pivot = joint

        prof = "taper" if shape in ("capsule", "sweep") else ("ellipse" if shape in ("blob", "ellipsoid") else "flat")
        fr = Frame(top=np.asarray(pf_top, float), angle=angle, h=h, w=w, profile=prof, r0=r0 * U, r1=r1 * U)
        frames[pid] = fr
        zs[pid] = z
        g = _build(shape, fr, p, problems, pid)
        if isinstance(g, geom.Sweep):
            fr.path = list(g.pts)
        if g is None:
            continue
        layer = pid
        if p.get("limb_kind") and parent and byid.get(parent, {}).get("limb_kind") and parent in placed:
            layer = placed[parent].layer          # 2관절 팔다리는 한 덩어리로 그린다(뼈대에는 관절이 그대로 남는다)
        elif p.get("merge") and parent:
            if p.get("role", "main") == byid[parent].get("role", "main"):
                layer = placed[parent].layer if parent in placed else parent
            else:
                warnings.append(f"{pid}: 색 역할이 부모와 달라 합치지 않고 따로 그립니다 (merge 는 같은 색끼리)")
        placed[pid] = Placed(pid, g, z, p.get("role", "main"), parent, layer, (float(pivot[0]), float(pivot[1])), angle, p)

    if problems:
        raise SolveError(problems)
    for h_id in hidden:
        placed.pop(h_id, None)
    # --- 떠 있는 부품 검사 (부모와 겹치거나 닿아야 한다)
    for pl in placed.values():
        if not pl.parent or pl.parent not in placed:
            continue
        gap = _gap(pl.shape, placed[pl.parent].shape)
        if gap > 0.02 * U:
            problems.append(f"{pl.id}: '{pl.parent}' 에 닿지 않고 {gap / U:.2f} 단위 떠 있습니다 — attach.inset 을 키우거나 v · az 를 몸 쪽으로")
    if problems:
        raise SolveError(problems)

    # --- 바닥: ground 부품의 가장 낮은 점을 y=0 에
    feet = [pl for pl in placed.values() if pl.spec.get("ground")]
    if feet:
        lows = [pl.shape.bounds()[3] for pl in feet]
        if max(lows) - min(lows) > 0.06 * U:
            warnings.append(f"발 높이가 {(max(lows) - min(lows)) / U:.2f} 단위 다릅니다 — 다리 길이 · dir 를 맞추면 둘 다 바닥에 닿습니다")
        dy = -max(lows)
        for pl in placed.values():
            pl.shape = _Shift(pl.shape, 0.0, dy)
            pl.pivot = (pl.pivot[0], pl.pivot[1] + dy)

    if facing == "left":
        for pl in placed.values():
            pl.shape = _Flip(pl.shape)
            pl.pivot = (-pl.pivot[0], pl.pivot[1])
            pl.angle = -pl.angle

    # 개구부: cut 부품 모양으로 부모를 파내고, 그 부품은 '구멍 안 그늘' 레이어가 된다(부모 바로 앞, 자식은 그 위)
    for pl in list(placed.values()):
        if pl.spec.get("cut") and pl.parent in placed:
            par = placed[pl.parent]
            par.spec = {**par.spec, "_uncut": par.spec.get("_uncut", par.shape)}   # 파내기 전 모양(구멍 검사용)
            par.shape = geom.Subtract(par.shape, pl.shape, k=0.02 * U)
            pl.spec = {**pl.spec, "cavity_of": par.role}
            pl.z = par.z + 0.005
    return sorted(placed.values(), key=lambda q: q.z), warnings


# ---------------------------------------------------------------- 덩어리 만들기
def _build(shape: str, fr: Frame, p: dict, problems: list[str], pid: str) -> geom.Shape | None:
    d, r = fr.down(), fr.right()
    top = fr.top
    c = top + d * (fr.h / 2)
    rot = -fr.angle            # geom 의 rot 는 시계 방향(+) — 우리 축 각도와 반대
    if shape == "ellipsoid":
        return geom.Ellipse((c[0], c[1]), fr.w / 2, fr.h / 2, rot)
    if shape == "blob":
        # 콩 · 달걀: 위 · 아래 부풂(bulge)이 다른 관. 1 이면 반폭 그대로
        # 달걀: 반폭(t) = 최대 반폭 × √(1−t²) × (1 + 기울기 × t), t = −1(위) ~ 1(아래). 곡률이 끊기지 않는다
        b = p.get("bulge") or {}
        top_r, bot_r = float(b.get("top", 0.85)), float(b.get("bottom", 1.0))
        skew = (bot_r - top_r) / (bot_r + top_r) * 1.6
        hw = fr.w / 2 / (1 + abs(skew) * 0.38)          # 최대 폭이 w 를 넘지 않게
        ts = np.linspace(-1, 1, 49)
        right = [(hw * math.sqrt(max(0.0, 1 - t * t)) * (1 + skew * t), (t + 1) / 2 * fr.h) for t in ts]
        local = right + [(-x, y) for x, y in reversed(right[1:-1])]
        pts = [tuple(top + r * x + d * y) for x, y in local]
        return geom.Polygon(pts)
    if shape == "box":
        return geom.Box((c[0], c[1]), fr.w, fr.h, float(p.get("round", 0.08)) * U, rot)
    if shape == "cylinder":
        cap = fr.w / 2 * float(p.get("cap", 0.35))          # 위 · 아래 타원 뚜껑(위에서 본 정도)
        body = geom.Box((c[0], c[1]), fr.w, fr.h - cap, 0.0, rot)
        lid = top + d * (cap / 2)
        bot = top + d * (fr.h - cap / 2)
        return geom.Union([body, geom.Ellipse((lid[0], lid[1]), fr.w / 2, cap / 2, rot), geom.Ellipse((bot[0], bot[1]), fr.w / 2, cap / 2, rot)])
    if shape == "capsule":
        e = top + d * fr.h
        return geom.Capsule((top[0], top[1]), (e[0], e[1]), fr.r0, fr.r1)
    if shape == "sweep":
        # 곡선 관: 시작에서 dir 로 뻗어 bend(도)만큼 휘어진다. 반지름은 r 목록을 고르게 보간
        bend = float(p.get("bend", 30.0))
        rs = [float(x) * U for x in (p.get("r") or [0.08, 0.02])]
        n = max(6, len(rs) * 2)
        pts, radii = [], []
        ang = fr.angle
        q = top.copy()
        step = fr.h / (n - 1)
        for i in range(n):
            pts.append((q[0], q[1]))
            t = i / (n - 1)
            radii.append(float(np.interp(t, np.linspace(0, 1, len(rs)), rs)))
            ang -= bend / (n - 1)
            q = q + np.array([math.sin(math.radians(ang)), math.cos(math.radians(ang))]) * step
        return geom.Sweep(pts, radii, k=min(radii) * 0.6)
    if shape == "leaf":
        e = top + d * fr.h
        return geom.Leaf((top[0], top[1]), (e[0], e[1]), fr.w)
    return None


@dataclass
class _Shift(geom.Shape):
    a: geom.Shape
    dx: float
    dy: float

    def sdf(self, X, Y):
        return self.a.sdf(X - self.dx, Y - self.dy)

    def bounds(self):
        b = self.a.bounds()
        return (b[0] + self.dx, b[1] + self.dy, b[2] + self.dx, b[3] + self.dy)


@dataclass
class _Flip(geom.Shape):
    a: geom.Shape

    def sdf(self, X, Y):
        return self.a.sdf(-X, Y)

    def bounds(self):
        b = self.a.bounds()
        return (-b[2], b[1], -b[0], b[3])


def _gap(a: geom.Shape, b: geom.Shape) -> float:
    """두 덩어리 사이 틈(겹치면 0). a 를 덮는 거친 격자에서 b 까지의 최소 거리"""
    x0, y0, x1, y1 = a.bounds()
    res = max((x1 - x0), (y1 - y0)) / 40 or 1.0
    X, Y = np.meshgrid(np.arange(x0, x1 + res, res), np.arange(y0, y1 + res, res))
    da, db = a.sdf(X, Y), b.sdf(X, Y)
    inside = da <= res
    if not inside.any():
        return 0.0
    return float(max(0.0, db[inside].min()))
