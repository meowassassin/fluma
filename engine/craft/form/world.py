"""캐릭터와 세상 — 지형 위 걷기 · 뛰기 · 계단 오르기, 손에 든 소품(들기 · 끌기), 시간 t 의 장면 배치(2026-11-20).

동작을 하나씩 만들어 붙이지 않는다. 몸의 역학을 계산하는 장치 몇 개의 조합이다:
  - 지형: 같은 장면의 캐릭터 아닌 형태(바닥 · 계단 · 경사로 · 소품)의 윗면 높이를 직접 잰다(SDF)
  - 이동: move = 경로 · 속도 · 걸음새(보폭 · 들썩임 · 팔 흔들기 · 기울기 수치) → 시간마다 발 디딤 · 골반 높이 · 팔
  - IK: 손 · 발의 목표만 주면 팔꿈치 · 무릎은 엔진이 푼다(skeleton.ik2)
  - 소품: hold = 아무 형태 + 쥐는 점(grip) — carry 는 손을 따라, drag 는 손잡이는 손 · 바닥점은 지면
뼈대 노드에 쓰는 칸:
  "move": {"path": [[x, z], …], "speed": 1.2, "gait": "walk"|"run", "stride": (키 비율), "bob", "arm_swing", "lean", "t0": 시작 초}
  "hold": {"r": {"prop": <형태 노드>, "grip": [x, y, z], "mode": "carry"|"drag", "ground": [x, y, z]}, "l": …}
  "ik": {"l_hand": [x, y, z](세상 좌표), …}   "at": [x, z] · "face": 도(°) — 움직이지 않을 때 놓는 자리 · 바라보는 방향
"""
from __future__ import annotations

import math

import numpy as np

from . import sdf
from .skeleton import DEFAULT, Ry, expand, joints

GAIT = {"walk": {"stride": 0.36, "bob": 0.012, "arm_swing": 22, "elbow": 14, "lean": 3, "swing_h": 0.07, "knee": 0.96},
        "run": {"stride": 0.62, "bob": 0.03, "arm_swing": 48, "elbow": 85, "lean": 11, "swing_h": 0.16, "knee": 0.9}}


# ---------------------------------------------------------------- 지형
class Ground:
    """캐릭터를 뺀 장면 형태의 윗면 높이 — 아무것도 없으면 0(바닥)"""

    def __init__(self, scene: dict):
        env = _strip_rigs(scene["root"])
        self.ok = env is not None
        if self.ok:
            self.codes, self.P, _ = sdf.compile_scene({"materials": scene["materials"], "root": env})
            self.sd, self.sm = np.empty(64), np.empty(64)

    def __call__(self, x: float, z: float, top: float = 4.0) -> float:
        if not self.ok:
            return 0.0
        y, step = top, 0.02
        prev = None
        while y > -0.2:
            d = sdf.sdf_eval(x, y, z, self.codes, self.P, self.sd, self.sm)[0]
            if d < 0.002:
                lo, hi = y, y + step                     # 경계를 반으로 좁힌다
                for _ in range(8):
                    mid = (lo + hi) / 2
                    if sdf.sdf_eval(x, mid, z, self.codes, self.P, self.sd, self.sm)[0] < 0.002:
                        lo = mid
                    else:
                        hi = mid
                return max(0.0, lo)
            step = max(0.004, min(0.05, d * 0.9))
            prev = y
            y -= step
        return 0.0


def _strip_rigs(n):
    if isinstance(n, dict):
        if "rig" in n:
            return None
        if "children" in n:
            kids = [k for k in (_strip_rigs(c) for c in n["children"]) if k is not None]
            return {**n, "children": kids} if kids else None
        return n
    return n


# ---------------------------------------------------------------- 경로
class Path:
    def __init__(self, pts):
        p = np.asarray(pts, float)[:, :2] if len(pts[0]) == 2 else np.asarray(pts, float)[:, [0, 2]]
        self.p = p
        self.seg = np.hypot(*np.diff(p, axis=0).T) if len(p) > 1 else np.zeros(0)
        self.cum = np.concatenate([[0], np.cumsum(self.seg)])
        self.total = float(self.cum[-1])

    def at(self, d):
        d = min(max(d, 0.0), self.total)
        if len(self.p) == 1:
            return self.p[0], np.array([0.0, 1.0])
        i = int(min(np.searchsorted(self.cum, d, side="right") - 1, len(self.seg) - 1))
        u = (d - self.cum[i]) / (self.seg[i] or 1.0)
        tng = (self.p[i + 1] - self.p[i]) / (self.seg[i] or 1.0)
        return self.p[i] + (self.p[i + 1] - self.p[i]) * u, tng


def _smooth(w):
    return w * w * (3 - 2 * w)


# ---------------------------------------------------------------- 이동(걸음새)
def locomotion(node: dict, t: float, ground: Ground) -> dict:
    """시간 t 의 (뿌리 위치 · 방향 · 발 목표(세상) · 골반 높이 · 자세 보정)"""
    S = {**DEFAULT, **(node.get("size") or {})}
    H = float(S["height"])
    mv = node["move"]
    g = {**GAIT[mv.get("gait", "walk")], **{k: mv[k] for k in ("stride", "bob", "arm_swing", "elbow", "lean", "swing_h") if k in mv}}
    path = Path(mv["path"])
    s = float(g["stride"]) * H
    v = float(mv.get("speed", 1.2 if mv.get("gait", "walk") == "walk" else 3.0))
    D = min(max(0.0, (t - float(mv.get("t0", 0.0))) * v), path.total)
    moving = D < path.total - 1e-6 and t >= float(mv.get("t0", 0.0))
    xz, tng = path.at(D)
    yaw = math.degrees(math.atan2(tng[0], tng[1]))
    left = np.array([math.cos(math.radians(yaw)), 0.0, -math.sin(math.radians(yaw))])
    hw = float(S["hip_w"]) * H
    fh = float(S["foot_h"]) * H
    feet = {}
    for side, q, sx in (("l", 0, 1), ("r", 1, -1)):
        if not moving:                                   # 멈춤: 두 발을 나란히
            fp, _ = path.at(D + (0.04 * H if side == "l" else -0.04 * H) * 0)
            w3 = np.array([fp[0], 0.0, fp[1]]) + left * sx * hw
            feet[side] = w3 + [0, ground(w3[0], w3[2]) + fh, 0]
            continue
        u = (D / s - q) / 2
        j = math.floor(u); fr = u - j
        plant = (2 * j + q + 0.5) * s
        a2, _ = path.at(plant); b2, _ = path.at(plant + 2 * s)
        A = np.array([a2[0], 0.0, a2[1]]) + left * sx * hw
        B = np.array([b2[0], 0.0, b2[1]]) + left * sx * hw
        ya, yb = ground(A[0], A[2]) + fh, ground(B[0], B[2]) + fh
        if fr < 0.5:                                     # 디딤(발이 붙어 있음)
            feet[side] = A + [0, ya, 0]
        else:                                            # 들어 옮김 — 계단이면 단 높이보다 높이 든다
            w = _smooth((fr - 0.5) / 0.5)
            P_ = A + (B - A) * w
            lift = max(float(g["swing_h"]) * H, abs(yb - ya) + 0.05 * H)
            feet[side] = P_ + [0, ya + (yb - ya) * w + lift * math.sin(math.pi * w), 0]
    leg = (float(S["upper_leg"]) + float(S["lower_leg"])) * H
    base = (feet["l"][1] + feet["r"][1]) / 2 - fh
    ph = math.pi * D / s
    pelvis = base + fh + leg * float(g["knee"]) - (float(g["bob"]) * H * abs(math.cos(ph)) if moving else 0.0)
    A_ = float(g["arm_swing"]) if moving else 4.0
    pose = {"l_arm": [-A_ * math.cos(ph), 8, 0], "r_arm": [A_ * math.cos(ph), 8, 0],
            "l_elbow": float(g["elbow"]), "r_elbow": float(g["elbow"]), "spine": [float(g["lean"]) if moving else 0, 0, 0]}
    return {"origin": np.array([xz[0], 0.0, xz[1]]), "yaw": yaw, "feet": feet, "pelvis_y": pelvis, "pose": pose, "left": left}


def _rot2(a1, a2, b1, b2):
    """a1 → b1 로, a2 가 b2 쪽을 향하게 하는 회전"""
    def basis(x, y):
        x = x / np.linalg.norm(x); y = y - x * float(x @ y); y = y / (np.linalg.norm(y) or 1.0)
        return np.stack([x, y, np.cross(x, y)], 1)
    return basis(np.asarray(b1, float), np.asarray(b2, float)) @ basis(np.asarray(a1, float), np.asarray(a2, float)).T


def place(node: dict, t: float, ground: Ground) -> list[dict]:
    """뼈대 노드 하나 → 세상에 놓인 도형 노드들(캐릭터 + 소품)"""
    S = {**DEFAULT, **(node.get("size") or {})}
    H = float(S["height"])
    pose = dict(node.get("pose") or {})
    ik_w = dict(node.get("ik") or {})
    if node.get("move"):
        lo = locomotion(node, t, ground)
        origin, yaw = lo["origin"], lo["yaw"]
        for k, v in lo["pose"].items():
            pose.setdefault(k, v)
        ik_w.setdefault("l_foot", lo["feet"]["l"]); ik_w.setdefault("r_foot", lo["feet"]["r"])
        pel_y = lo["pelvis_y"]
    else:
        at = node.get("at") or [0, 0]
        origin, yaw = np.array([at[0], 0.0, at[1]]), float(node.get("face", 0.0))
        pel_y = None
    W = Ry(yaw)
    fwd, left = W @ [0, 0, 1.0], W @ [1.0, 0, 0]
    if pel_y is None:                                     # 서 있는 자리의 지형 높이만큼 올린다
        g0 = ground(origin[0], origin[2])
        pel_y = g0 + (float(S["foot_h"]) + float(S["upper_leg"]) + float(S["lower_leg"])) * H
        if not any(k.endswith("_foot") for k in ik_w):
            for side, sx in (("l", 1), ("r", -1)):
                p3 = origin + left * sx * float(S["hip_w"]) * H
                ik_w.setdefault(f"{side}_foot", p3 + [0, ground(p3[0], p3[2]) + float(S["foot_h"]) * H, 0])
    holds = node.get("hold") or {}
    for side, hd in holds.items():                        # 끌기: 손을 몸 옆 · 조금 뒤로(목표를 주지 않았으면)
        if (hd or {}).get("mode") == "drag" and f"{side}_hand" not in ik_w:
            sx = 1 if side == "l" else -1
            ik_w[f"{side}_hand"] = origin + [0, pel_y - 0.03 * H, 0] + left * sx * 0.16 * H - fwd * 0.2 * H
    Wi = W.T
    ik_local = {k: (Wi @ (np.asarray(v, float) - origin)).tolist() for k, v in ik_w.items()}
    ik_local["pelvis_y"] = pel_y
    body = expand({**{k: v for k, v in node.items() if k not in ("move", "hold", "ik", "at", "face", "pos", "rot")}, "pose": pose, "_ik": ik_local})
    body["pos"] = origin.tolist()
    body["rotm"] = W.tolist()
    out = [body]
    if holds:
        J = joints(node.get("size") or {}, pose, ik_local, ground=False)
        for side, hd in holds.items():
            if not hd or "prop" not in hd:
                continue
            hand = origin + W @ J[f"{side}_hand"]
            g = np.asarray(hd.get("grip", [0, 0, 0]), float)
            if hd.get("mode") == "drag":
                q = np.asarray(hd.get("ground", [0, 0, 0]), float)
                L = float(np.linalg.norm(g - q))
                G = hand - fwd * L * 0.7
                for _ in range(3):                         # 바닥점이 지면에 닿게 뒤로 거리를 맞춘다
                    gy = ground(G[0], G[2])
                    hd_ = math.sqrt(max(L * L - (hand[1] - gy) ** 2, 1e-6))
                    G = hand - fwd * hd_
                    G[1] = gy
                R = _rot2(g - q, [1.0, 0, 0], hand - G, left)
            else:
                R = W @ J[f"{side}_Rf"]
            out.append({"op": "union", "children": [hd["prop"]], "pos": (hand - R @ g).tolist(), "rotm": R.tolist()})
    return out


def prepare(scene: dict, t: float = 0.0) -> dict:
    """시간 t 의 장면 — 뼈대 노드(move · hold · ik · at 이 있으면 세상 배치)를 도형으로 펼친 사본"""
    ground = None

    def walk(n):
        nonlocal ground
        if isinstance(n, dict):
            if "rig" in n:
                if any(k in n for k in ("move", "hold", "ik", "at")):
                    if ground is None:
                        ground = Ground(scene)
                    parts = place(n, t, ground)
                    return parts[0] if len(parts) == 1 else {"op": "union", "children": parts}
                return expand(n)
            return {k: walk(v) for k, v in n.items()}
        if isinstance(n, list):
            return [walk(x) for x in n]
        return n
    return {**scene, "root": walk(scene["root"])}
