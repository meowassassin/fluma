"""캐릭터와 세상 — 지형 위 걷기 · 뛰기 · 계단 오르기, 손에 든 소품(들기 · 끌기), 시간 t 의 장면 배치(2026-11-20).

동작을 하나씩 만들어 붙이지 않는다. 몸의 역학을 계산하는 장치 몇 개의 조합이다:
  - 지형: 같은 장면의 캐릭터 아닌 형태(바닥 · 계단 · 경사로 · 소품)의 윗면 높이를 직접 잰다(SDF)
  - 이동: move = 경로 · 속도 · 걸음새(보폭 · 들썩임 · 팔 흔들기 · 기울기 수치) → 시간마다 발 디딤 · 골반 높이 · 팔
  - IK: 손 · 발의 목표만 주면 팔꿈치 · 무릎은 엔진이 푼다(skeleton.ik2)
  - 소품: hold = 아무 형태 + 쥐는 점(grip) — carry 는 손을 따라, drag 는 손잡이는 손 · 바닥점은 지면
뼈대 노드에 쓰는 칸:
  "move": {"path": [[x, z], …], "speed": 1.2, "gait": "walk"|"run", "stride": (키 비율), "bob", "arm_swing", "lean", "t0": 시작 초}
  "hold": {"r": {"prop": <형태 노드>, "grip": [x, y, z], "mode": "carry"|"drag", "ground": [x, y, z]}, "l": …}
  "ik": {"l_hand": [x, y, z](세상 좌표), …}   "at": [x, z] · "facing": 도(°) — 움직이지 않을 때 놓는 자리 · 몸이 향하는 방향
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import sdf
from .skeleton import DEFAULT, Ry, expand, joints

GAIT = {"walk": {"stride": 0.36, "bob": 0.014, "arm_swing": 24, "elbow": 18, "elbow_swing": 22, "lean": 3, "swing_h": 0.09, "knee": 0.95,
                 "duty": 0.6, "hip_yaw": 7, "hip_roll": 4, "sway": 0.012, "ramp": 0.45, "lag": 0.07},
        "run": {"stride": 0.62, "bob": 0.03, "arm_swing": 46, "elbow": 80, "elbow_swing": 15, "lean": 11, "swing_h": 0.2, "knee": 0.9,
                "duty": 0.38, "hip_yaw": 11, "hip_roll": 3, "sway": 0.008, "ramp": 0.35, "lag": 0.05}}


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
def _travel(tau: float, v: float, total: float, ramp: float) -> float:
    """가속 · 감속이 있는 이동 거리 — 출발 ramp 초 동안 빨라지고, 끝에서 같은 만큼 느려져 멈춘다"""
    if tau <= 0:
        return 0.0
    d = v * tau * tau / (2 * ramp) if tau < ramp else v * (tau - ramp / 2)
    stop = total - v * ramp / 2                          # 이 거리부터 감속
    if d > stop:
        x = min(1.0, (d - stop) / (v * ramp))           # 0 → 1
        d = stop + v * ramp / 2 * (1 - (1 - x) ** 2)
    return min(d, total)


def locomotion(node: dict, t: float, ground: Ground) -> dict:
    """시간 t 의 (뿌리 위치 · 방향 · 발 목표(세상) · 골반 높이 · 자세 보정).
    사람 걸음의 2차 움직임을 함께: 가속 · 감속, 디딤 비율(걷기 두 발 닿음 · 뛰기 두 발 뜸), 뒤꿈치부터 떼는 발,
    골반 회전 · 기울기 · 좌우 체중 이동, 반대로 도는 어깨, 시선 유지, 늦게 따라오는 팔 · 고개(겹침)"""
    S = {**DEFAULT, **(node.get("size") or {})}
    H = float(S["height"])
    mv = node["move"]
    gait = mv.get("gait", "walk")
    g = {**GAIT[gait], **{k: mv[k] for k in GAIT["walk"] if k in mv}}
    path = Path(mv["path"])
    s = float(g["stride"]) * H
    v = float(mv.get("speed", 1.2 if gait == "walk" else 3.0))
    t0 = float(mv.get("t0", 0.0))
    ramp = float(g["ramp"])
    D = _travel(t - t0, v, path.total, ramp)
    moving = 1e-6 < D < path.total - 1e-6
    xz, tng = path.at(D)
    yaw = math.degrees(math.atan2(tng[0], tng[1]))
    left = np.array([math.cos(math.radians(yaw)), 0.0, -math.sin(math.radians(yaw))])
    hw = float(S["hip_w"]) * H
    fh = float(S["foot_h"]) * H
    duty = float(g["duty"])
    feet, stance = {}, {}
    for side, q, sx in (("l", 0, 1), ("r", 1, -1)):
        if not moving:                                   # 멈춤: 두 발을 나란히
            w3 = np.array([xz[0], 0.0, xz[1]]) + left * sx * hw
            feet[side] = w3 + [0, ground(w3[0], w3[2]) + fh, 0]
            stance[side] = 1.0
            continue
        u = (D / s - q) / 2
        j = math.floor(u); fr = u - j
        plant = (2 * j + q + 0.5) * s
        a2, _ = path.at(plant); b2, _ = path.at(plant + 2 * s)
        A = np.array([a2[0], 0.0, a2[1]]) + left * sx * hw
        B = np.array([b2[0], 0.0, b2[1]]) + left * sx * hw
        ya, yb = ground(A[0], A[2]) + fh, ground(B[0], B[2]) + fh
        if fr < duty:                                    # 디딤
            feet[side] = A + [0, ya, 0]
            stance[side] = 1.0
        else:                                            # 들어 옮김 — 뒤꿈치부터 들고(앞쪽 궤적이 늦게), 계단이면 단보다 높이
            w = (fr - duty) / (1 - duty)
            wf = _smooth(w) ** 1.15
            lift = max(float(g["swing_h"]) * H, abs(yb - ya) + 0.05 * H)
            arc = math.sin(math.pi * min(1.0, w * 1.08)) ** 0.85
            feet[side] = A + (B - A) * wf + [0, ya + (yb - ya) * _smooth(w) + lift * arc, 0]
            stance[side] = 0.0
    leg = (float(S["upper_leg"]) + float(S["lower_leg"])) * H
    base = (feet["l"][1] + feet["r"][1]) / 2 - fh
    ph = math.pi * D / s                                 # 한 걸음 = π
    ramp_k = 1.0 if not moving else min(1.0, (t - t0) / ramp, max(0.0, (path.total - D) / (v * ramp + 1e-6)))
    bob = float(g["bob"]) * H * (0.5 - 0.5 * math.cos(2 * ph)) * ramp_k   # 한 걸음에 두 번 오르내림(두 발이 닿을 때 가장 낮다)
    pelvis = base + fh + leg * float(g["knee"]) - bob
    lag = float(g["lag"]) * v / s * math.pi             # 겹침: 팔 · 고개는 몸보다 조금 늦게(위상 지연)
    pa = ph - lag
    A_ = float(g["arm_swing"]) * ramp_k
    hy = float(g["hip_yaw"]) * math.sin(ph) * ramp_k    # 골반이 앞으로 나가는 다리 쪽으로 돈다
    hr = float(g["hip_roll"]) * math.cos(2 * ph) * ramp_k * (1 if math.sin(ph) > 0 else -1)
    sway = float(g["sway"]) * H * math.sin(ph) * ramp_k
    el0, el1 = float(g["elbow"]), float(g["elbow_swing"])
    lean = float(g["lean"]) * (ramp_k if moving else 0.0) + (4.0 * (1 - ramp_k) if moving and (t - t0) < ramp else 0.0)   # 출발할 때 더 숙인다(예비 동작)
    pose = {"l_arm": [-A_ * math.cos(pa), 9 + 3 * abs(math.cos(pa)), 0], "r_arm": [A_ * math.cos(pa), 9 + 3 * abs(math.cos(pa)), 0],
            "l_elbow": el0 + el1 * max(0.0, -math.cos(pa)) * ramp_k, "r_elbow": el0 + el1 * max(0.0, math.cos(pa)) * ramp_k,
            "spine": [lean, 0, -hy * 1.5], "lean": [0, hr],
            "head": [-lean * 0.4 + 1.5 * math.sin(2 * (ph - lag)) * ramp_k, hy * 0.5, 0]}
    return {"origin": np.array([xz[0], 0.0, xz[1]]) + left * sway, "yaw": yaw + hy, "feet": feet, "pelvis_y": pelvis, "pose": pose, "left": left}


def life(t: float, k: float = 1.0) -> dict:
    """서 있을 때 살아 있는 미세 움직임(더해진다) — 숨쉬기 · 체중 옮기기 · 고개 흔들림. 장면 길이와 상관없이 부드럽게"""
    if k <= 0:
        return {}
    b = math.sin(2 * math.pi * t / 3.4)
    return {"spine": [1.2 * b * k, 1.2 * math.sin(2 * math.pi * t / 5.3) * k, 0], "lean": [0, 1.4 * math.sin(2 * math.pi * t / 5.3) * k],
            "head": [1.5 * math.sin(2 * math.pi * t / 4.1 + 1) * k, 3.0 * math.sin(2 * math.pi * t / 6.7) * k, 1.5 * math.sin(2 * math.pi * t / 5.9 + 2) * k],
            "l_arm": [1.5 * b * k, 0, 0], "r_arm": [1.5 * b * k, 0, 0]}


def _add_pose(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if k in out and isinstance(out[k], (list, tuple)):
            out[k] = [float(a) + float(b) for a, b in zip(list(out[k]) + [0] * 3, list(v) + [0] * 3)][: max(len(out[k]), len(v))]
        elif k in out:
            out[k] = float(out[k]) + float(v if not isinstance(v, (list, tuple)) else v[0])
        else:
            out[k] = v
    return out


def _rot2(a1, a2, b1, b2):
    """a1 → b1 로, a2 가 b2 쪽을 향하게 하는 회전"""
    def basis(x, y):
        x = x / np.linalg.norm(x); y = y - x * float(x @ y); y = y / (np.linalg.norm(y) or 1.0)
        return np.stack([x, y, np.cross(x, y)], 1)
    return basis(np.asarray(b1, float), np.asarray(b2, float)) @ basis(np.asarray(a1, float), np.asarray(a2, float)).T


def cam_dir(camera: dict) -> np.ndarray:
    """카메라가 있는 쪽 방향(세상) — 방위각 · 고도에서"""
    az, el = math.radians(float(camera.get("azimuth", 35))), math.radians(float(camera.get("elevation", 18)))
    return np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])


def _look(node, pose, J, origin, W, target_w):
    """시선: 목표 쪽으로 고개(최대 ±80 · 끄덕 ±45) → 남는 만큼 상체 비틀기(±40) → 눈동자. look_w 로 섞는다(0 원래 · 1 완전히)"""
    w = float(node.get("look_w", 1.0))
    if w <= 0:
        return pose, None
    hl = J["head"]
    tl = W.T @ (np.asarray(target_w, float) - origin)
    d = tl - hl
    yaw = math.degrees(math.atan2(d[0], d[2]))
    pitch = math.degrees(math.atan2(d[1], math.hypot(d[0], d[2])))
    sp = list(pose.get("spine") or [0, 0, 0]) + [0, 0, 0]
    hd = list(pose.get("head") or [0, 0, 0]) + [0, 0, 0]
    head_yaw = max(-80, min(80, yaw * 0.75))
    twist = max(-40, min(40, yaw - head_yaw))
    nod = max(-45, min(45, -pitch))
    new = dict(pose)
    new["head"] = [hd[0] * (1 - w) + nod * w, hd[1] * (1 - w) + head_yaw * w, hd[2] * (1 - w)]
    new["spine"] = [sp[0], sp[1], sp[2] * (1 - w) + twist * w]
    rest = yaw - head_yaw - twist
    eyes = [max(-1, min(1, rest / 30)) * w, max(-1, min(1, pitch / 40)) * w]
    return new, eyes


def place(node: dict, t: float, ground: Ground, targets: dict | None = None, camera: dict | None = None) -> tuple[list[dict], dict]:
    """뼈대 노드 하나 → (세상에 놓인 도형 노드들(캐릭터 + 소품), 관절의 세상 위치)
    look: "camera" | "이름.관절"(다른 캐릭터) | [x, y, z] — 고개 · 상체 · 눈이 그쪽으로(look_w 로 정도)"""
    S = {**DEFAULT, **(node.get("size") or {})}
    H = float(S["height"])
    pose = dict(node.get("pose") or {})
    ik_w = dict(node.get("ik") or {})
    if node.get("move"):
        lo = locomotion(node, t, ground)
        origin, yaw = lo["origin"], lo["yaw"]
        pose = _add_pose(lo["pose"], {k: v for k, v in pose.items() if k in lo["pose"]}) | {k: v for k, v in pose.items() if k not in lo["pose"]}
        pose["weight"] = 0.0                              # 걷는 중에는 걸음 계산이 체중 이동을 맡는다
        ik_w.setdefault("l_foot", lo["feet"]["l"]); ik_w.setdefault("r_foot", lo["feet"]["r"])
        pel_y = lo["pelvis_y"]
    else:
        at = node.get("at") or [0, 0]
        origin, yaw = np.array([at[0], 0.0, at[1]]), float(node.get("facing", 0.0))
        pel_y = None
    W = Ry(yaw)
    fwd, left = W @ [0, 0, 1.0], W @ [1.0, 0, 0]
    if pel_y is None:                                     # 서 있다 — 살아 있는 미세 움직임을 더한다(life 0 이면 끔)
        pose = _add_pose(pose, life(t, float(node.get("life", 1.0))))
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
    face = dict(node.get("face") if isinstance(node.get("face"), dict) else {})
    lk = node.get("look")
    if lk is not None:
        J0 = joints(node.get("size") or {}, pose, ik_local, ground=False)
        tgt = None
        if lk == "camera":
            tgt = origin + W @ J0["head"] + cam_dir(camera or {}) * 50.0
        elif isinstance(lk, str) and targets and lk in targets:
            tgt = targets[lk]
        elif isinstance(lk, (list, tuple)):
            tgt = np.asarray(lk, float)
        if tgt is not None:
            pose, eyes = _look(node, pose, J0, origin, W, tgt)
            if eyes:
                face["look"] = eyes
    body = expand({**{k: v for k, v in node.items() if k not in ("move", "hold", "ik", "at", "facing", "pos", "rot", "look", "look_w")},
                   "pose": pose, "face": face, "_ik": ik_local})
    body["pos"] = origin.tolist()
    body["rotm"] = W.tolist()
    out = [body]
    J = joints(node.get("size") or {}, pose, ik_local, ground=False)
    world_j = {k: origin + W @ v for k, v in J.items() if isinstance(v, np.ndarray) and v.shape == (3,)}
    if holds:
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
    return out, world_j


def prepare(scene: dict, t: float = 0.0) -> dict:
    """시간 t 의 장면 — 뼈대 노드를 세상에 놓고(이동 · 소품 · 시선) 도형으로 펼친 사본.
    두 번 돈다: ① 이름 붙은 캐릭터의 관절 위치 ② 시선(look) · 카메라 초점("이름.관절")을 그 위치로 맞춘다"""
    ground = None
    cam = scene.get("camera") or {}
    world_keys = ("move", "hold", "ik", "at", "look")

    def gr():
        nonlocal ground
        if ground is None:
            ground = Ground(scene)
        return ground

    targets: dict = {}

    def collect(n):
        if isinstance(n, dict):
            if "rig" in n and n.get("name") and n.get("rig") == "humanoid":
                nl = {k: v for k, v in n.items() if k not in ("look",)}
                _, wj = place(nl, t, gr(), None, cam) if any(k in n for k in world_keys) else place({**nl, "at": [0, 0]}, t, gr(), None, cam)
                for k, v in wj.items():
                    targets[f"{n['name']}.{k}"] = v
            for v in n.values():
                collect(v)
        elif isinstance(n, list):
            for v in n:
                collect(v)
    collect(scene["root"])

    def walk(n):
        if isinstance(n, dict):
            if n.get("floor"):                            # 바닥: 발이 딛는 높이 · 그림자에만 쓰고 그리지 않는다(잘린 받침판 · 원판 무대가 안 생긴다)
                return None
            if "rig" in n:
                if n.get("rig") == "humanoid" and any(k in n for k in world_keys):
                    parts, _ = place(n, t, gr(), targets, cam)
                    return parts[0] if len(parts) == 1 else {"op": "union", "children": parts}
                return expand(n)
            return {k: walk(v) for k, v in n.items()}
        if isinstance(n, list):
            return [w for w in (walk(x) for x in n) if w is not None]
        return n
    out = {**scene, "root": walk(scene["root"]) or {"op": "union", "children": []}}
    from .skeleton import AUTO_MATS                       # 뼈대가 쓰는 보조 재료(눈 반사점)가 장면에 없으면 넣는다
    if any(k not in (scene.get("materials") or {}) for k in AUTO_MATS) and "rig" in json.dumps(scene["root"]):
        out["materials"] = {**AUTO_MATS, **(scene.get("materials") or {})}
    def pt(v):
        if isinstance(v, str):
            return targets.get(v)
        return None if v is None else np.asarray(v, float)
    fc, ft = pt(cam.get("focus")), pt(cam.get("focus_to"))
    if cam.get("focus") is not None or cam.get("focus_to") is not None:
        # 카메라 초점 "이름.관절" → 그 관절의 지금 위치. focus_to 와 focus_mix(0~1)로 두 초점 사이를 옮긴다(몸 → 얼굴로 다가가기)
        if fc is not None and ft is not None:
            m = float(cam.get("focus_mix", 0.0))
            fc = fc * (1 - m) + ft * m
        fc = fc if fc is not None else ft
        c2 = {k: v for k, v in cam.items() if k not in ("focus", "focus_to", "focus_mix")}
        if fc is not None:
            c2["focus"] = [float(x) for x in fc]
        out["camera"] = c2
    return out
