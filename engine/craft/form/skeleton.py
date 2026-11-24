"""뼈대 캐릭터 — 관절 위치를 계산하고 뼈 위에 부품을 붙여 형태(SDF) 트리로 펼친다(2026-11-20).

부품을 하나씩 좌표로 놓으면 다리와 발이 떨어지고, 자세를 바꾸기 어려워 차렷으로 굳고, 얼굴이 머리를 따라 돌지 않았다.
뼈대에서는 부품 위치를 관절에서 계산하므로 떨어질 수 없고, 자세는 관절 각도 몇 개로 정한다.

형태 JSON 안에 노드로 쓴다:
  {"rig": "humanoid", "pos": [0,0,0],
   "size": {"height": 1.7, "head": 0.14, …},            # 비율(키에 대한 비) — 아래 DEFAULT 참고, 그림체에 맞게 영상마다 정한다
   "pose": {"spine": [앞, 옆, 비틀기], "head": [끄덕, 돌리기, 갸웃], "l_arm": [앞, 벌리기, 비틀기], "l_elbow": 굽힘,
            "r_arm": …, "r_elbow": …, "l_leg": [앞, 벌리기], "l_knee": 굽힘, "r_leg": …, "r_knee": …, "lean": [앞, 옆]},   # 도(°)
   "mats": {"skin": "skin", "hair": "hair", "top": "shirt", "bottom": "pants", "shoe": "shoe", "eye": "eye", "mouth": "mouth"},
   "wear": {"sleeve": 0.3, "pants": 1.0, "hair": 0.4}}  # 소매가 덮는 팔 비율 · 바지가 덮는 다리 비율 · 뒷머리 길이(0 없음)
좌표: y 위, 얼굴은 +z, 캐릭터의 왼쪽이 +x. 발바닥이 y = 0 (곧게 섰을 때).
"""
from __future__ import annotations

import math

import numpy as np

DEFAULT = {
    "height": 1.7, "head": 0.14, "head_w": 0.78, "head_d": 0.88, "neck": 0.035, "neck_r": 0.03,
    "torso": 0.29, "chest_w": 0.115, "chest_d": 0.07, "waist_w": 0.088, "pelvis_w": 0.1, "hip_w": 0.062,
    "upper_arm": 0.175, "lower_arm": 0.15, "arm_r": 0.032, "wrist_r": 0.023, "hand": 0.05,
    "upper_leg": 0.245, "lower_leg": 0.235, "leg_r": 0.052, "ankle_r": 0.03, "foot": 0.13, "foot_h": 0.04,
    "eye": 0.07, "eye_sep": 0.36, "eye_y": 0.0, "mouth_w": 0.16, "mouth_y": -0.27, "nose": 0.035,
}
POSE = {"lean": [0, 0], "spine": [0, 0, 0], "head": [0, 0, 0],
        "l_arm": [4, 9, 0], "l_elbow": 14, "r_arm": [4, 9, 0], "r_elbow": 14,
        "l_leg": [0, 2], "l_knee": 0, "r_leg": [0, 2], "r_knee": 0, "weight": 0.45}
# weight: 서 있을 때 체중을 싣는 쪽(+ 왼다리 · − 오른다리 · 0 두 다리 똑같이 — 마네킹처럼 보인다). 걷기 · 발 목표가 있으면 쓰지 않는다
MATS = {"skin": "skin", "hair": "hair", "top": "top", "bottom": "bottom", "shoe": "shoe", "eye": "eye", "mouth": "mouth", "eye_hi": "eye_hi"}
AUTO_MATS = {"eye_hi": {"color": "#ffffff", "gloss": 0.0}}   # 장면에 없으면 world.prepare 가 넣는다(눈 반사점)


def Rx(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def align_y(d):
    """+y 를 방향 d 로 돌리는 회전 행렬"""
    d = np.asarray(d, float); d = d / (np.linalg.norm(d) or 1.0)
    y = np.array([0.0, 1.0, 0.0]); v = np.cross(y, d); c = float(y @ d); sn = float(np.linalg.norm(v))
    if sn < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    k = v / sn
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + sn * K + (1 - c) * (K @ K)


def seg(a, b, r1, r2, mat):
    """두 관절 사이 둥근 원뿔(a 쪽 r1, b 쪽 r2)"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    h = float(np.linalg.norm(b - a))
    if h <= abs(r1 - r2) + 1e-4:
        return {"prim": "sphere", "r": float(max(r1, r2)), "pos": (a if r1 >= r2 else b).tolist(), "mat": mat}
    return {"prim": "roundcone", "r1": float(r1), "r2": float(r2), "h": h, "pos": a.tolist(), "rotm": align_y(b - a).tolist(), "mat": mat}


def ell(c, radii, R, mat):
    return {"prim": "ellipsoid", "radii": [float(x) for x in radii], "pos": np.asarray(c, float).tolist(), "rotm": np.asarray(R).tolist(), "mat": mat}


def ik2(A, T, L1, L2, pole):
    """두 뼈 IK — 뿌리 A 에서 목표 T 로(길이 L1 · L2), 가운데 관절은 pole 쪽으로 굽는다. (가운데 관절, 끝) — 닿지 않으면 쭉 편다"""
    A, T, pole = np.asarray(A, float), np.asarray(T, float), np.asarray(pole, float)
    v = T - A
    d = float(np.linalg.norm(v)) or 1e-6
    u = v / d
    dmin = math.sqrt(L1 * L1 + L2 * L2 - 2 * L1 * L2 * math.cos(math.radians(30)))   # 가장 많이 굽혀도 150°(관절 안쪽 30°)
    d = min(max(d, dmin), L1 + L2 - 1e-4)
    ca = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    a = math.acos(max(-1.0, min(1.0, ca)))
    n = np.cross(u, pole)
    if np.linalg.norm(n) < 1e-6:
        n = np.cross(u, [1.0, 0.0, 0.0])
    b = np.cross(n / np.linalg.norm(n), u)
    mid = A + u * L1 * math.cos(a) + b * L1 * math.sin(a)
    return mid, A + u * d


def frame_from(down, fwd_hint):
    """뼈 방향(아래 = −y 가 down)과 앞 방향 힌트로 회전 행렬 — 손 · 발 같은 끝 부품의 방향"""
    y = -np.asarray(down, float); y /= (np.linalg.norm(y) or 1.0)
    z = np.asarray(fwd_hint, float) - y * float(np.dot(fwd_hint, y))
    if np.linalg.norm(z) < 1e-6:
        z = np.cross(y, [1.0, 0.0, 0.0])
    z /= np.linalg.norm(z)
    x = np.cross(y, z)
    return np.stack([x, y, z], 1)


# 관절 가동 범위(°) — 사람 몸이 실제로 움직이는 범위. 자세 값이 이 밖이면 끝에서 멈춘다(무릎이 앞으로 · 팔꿈치가 뒤로 꺾이는 일이 없게)
LIMITS = {"lean": [(-30, 30), (-25, 25)], "spine": [(-25, 60), (-35, 35), (-45, 45)], "head": [(-45, 60), (-80, 80), (-40, 40)],
          "arm": [(-60, 180), (-15, 180), (-60, 60)], "elbow": (0, 150), "leg": [(-30, 125), (-15, 70)], "knee": (0, 150),
          "grip": (0, 1), "spread": (0, 30), "weight": (-1, 1)}


def _lim(v, rng):
    if isinstance(rng, tuple):
        return min(max(float(v), rng[0]), rng[1])
    v = list(v) + [0] * (len(rng) - len(v))
    return [min(max(float(x), a), b) for x, (a, b) in zip(v, rng)]


def clamp_pose(P: dict) -> dict:
    out = dict(P)
    for k, v in P.items():
        key = k.split("_", 1)[1] if k[:2] in ("l_", "r_") else k
        if key in LIMITS:
            out[k] = _lim(v, LIMITS[key])
    return out


def joints(size: dict, pose: dict, ik: dict | None = None, ground: bool = True) -> dict:
    """관절 위치 · 뼈 방향(순운동학 + 손발 목표가 있으면 IK). 키 단위(m), 캐릭터 기준 좌표(얼굴 +z).
    ik: {"l_foot" | "r_foot" | "l_hand" | "r_hand": [x, y, z]} — 발은 발목, 손은 손목 위치. pelvis_y 로 골반 높이를 정할 수 있다"""
    S = {**DEFAULT, **(size or {})}
    P = clamp_pose({**POSE, **(pose or {})})
    H = float(S["height"]); f = lambda k: float(S[k]) * H  # noqa: E731
    ik = ik or {}
    lean = list(P["lean"]); sp = list(P["spine"]) + [0, 0, 0]; hd = list(P["head"]) + [0, 0, 0]
    # 체중 싣기(콘트라포스토) — 2026-11-21: 두 다리에 반씩 실려 마네킹처럼 섰다. 받치는 다리 쪽으로 골반이 옮겨 가며 그쪽 엉덩이가 올라가고,
    # 어깨는 반대로 기울고, 쉬는 다리는 무릎이 굽는다. 걷기 · 발 목표(IK)가 있으면 그쪽 계산이 다리를 정하므로 끈다
    w = float(P.get("weight", 0.0))                       # 걷는 중이면 world.locomotion 이 weight 0 으로 준다(발 목표가 있어도 서 있으면 골반만 옮기고 무릎은 IK 가 굽힘)
    shift = 0.0
    if w:
        lean[1] = lean[1] + 7 * w
        sp[1] = sp[1] - 11 * w
        hd[2] = hd[2] + 4 * w
        shift = 0.04 * H * w
        fs = "r" if w > 0 else "l"; ss = "l" if w > 0 else "r"       # 쉬는 다리 · 받치는 다리
        a = abs(w)
        P = {**P, f"{fs}_knee": max(P[f"{fs}_knee"], 24 * a), f"{fs}_leg": [P[f"{fs}_leg"][0] + 10 * a, P[f"{fs}_leg"][1] + 6 * a],
             f"{ss}_leg": [P[f"{ss}_leg"][0], P[f"{ss}_leg"][1] - 3 * a]}
    # 2026-11-21: 등뼈 · 고개 · 몸 기울기의 앞뒤 부호가 팔다리와 반대였다(+ 가 뒤로 젖힘) — '앞으로 숙여'가 젖혀지고 달리기가 뒤로 기울었다.
    # 모든 관절에서 + 가 앞(숙이기 · 고개 숙이기 · 팔 앞으로 · 다리 앞으로)
    R0 = Rx(lean[0]) @ Rz(lean[1])
    yhip = f("foot_h") + f("lower_leg") + f("upper_leg")
    pel = np.array([shift, float(ik["pelvis_y"]) if "pelvis_y" in ik else yhip, 0.0])
    # 등뼈 두 마디 — 숙이기 · 옆으로 굽히기 · 비틀기를 허리(40%)와 가슴(60%)이 나눠 가져 곡선으로 휜다(한 마디면 골반에서 경첩처럼 꺾였다)
    Rw = R0 @ Rx(sp[0] * 0.4) @ Rz(sp[1] * 0.4) @ Ry(sp[2] * 0.35)
    mid = pel + Rw @ [0, f("torso") * 0.42, 0]
    Rs = Rw @ Rx(sp[0] * 0.6) @ Rz(sp[1] * 0.6) @ Ry(sp[2] * 0.65)
    neck0 = mid + Rs @ [0, f("torso") * 0.58, 0]
    Rh = Rs @ Ry(hd[1]) @ Rx(hd[0]) @ Rz(hd[2])
    head = neck0 + Rh @ [0, f("neck") + f("head") * 0.5, f("head") * 0.06]
    J = {"S": S, "H": H, "R0": R0, "Rs": Rs, "Rw": Rw, "Rh": Rh, "pelvis": pel, "mid": mid, "neck": neck0, "head": head}
    for side, sx in (("l", 1), ("r", -1)):
        arm, elbow = P[f"{side}_arm"], P[f"{side}_elbow"]
        sh = neck0 + Rs @ [sx * f("chest_w") * 0.93, -f("torso") * 0.07, 0]
        Ra = Rs @ Rz(sx * arm[1]) @ Rx(-arm[0]) @ Ry(sx * (arm[2] if len(arm) > 2 else 0))
        el = sh + Ra @ [0, -f("upper_arm"), 0]
        Rf = Ra @ Rx(-elbow)
        wr = el + Rf @ [0, -f("lower_arm"), 0]
        if f"{side}_hand" in ik:                       # 손 목표 — 팔꿈치는 뒤 · 바깥으로 굽는다
            el, wr = ik2(sh, ik[f"{side}_hand"], f("upper_arm"), f("lower_arm"), Rs @ [sx * 0.4, 0, -1.0])
            Rf = frame_from(wr - el, Rs @ [0, 0, 1.0])
        J[f"{side}_shoulder"], J[f"{side}_elbow"], J[f"{side}_wrist"], J[f"{side}_hand"], J[f"{side}_Rf"] = sh, el, wr, wr + Rf @ [0, -f("hand") * 0.55, 0], Rf
        leg, knee = P[f"{side}_leg"], P[f"{side}_knee"]
        hp = pel + R0 @ [sx * f("hip_w"), 0, 0]
        Rt = R0 @ Rz(sx * leg[1]) @ Rx(-leg[0])
        kn = hp + Rt @ [0, -f("upper_leg"), 0]
        Rk = Rt @ Rx(knee)
        an = kn + Rk @ [0, -f("lower_leg"), 0]
        if f"{side}_foot" in ik:                       # 발 목표(계단 · 바닥) — 무릎은 앞으로 굽는다
            kn, an = ik2(hp, ik[f"{side}_foot"], f("upper_leg"), f("lower_leg"), R0 @ [0, 0, 1.0])
        J[f"{side}_hip"], J[f"{side}_knee"], J[f"{side}_ankle"] = hp, kn, an
    # 바닥에 닿기: 무릎을 굽히거나 다리를 들면 발이 뜬다 — 가장 낮은 발목이 곧게 선 높이(발 높이)에 오게 몸 전체를 내린다
    drop = min(J["l_ankle"][1], J["r_ankle"][1]) - f("foot_h")
    if ground and not ({"l_foot", "r_foot"} & set(ik)) and abs(drop) > 1e-6:   # 발 목표가 있으면(지형 위) 내리지 않는다
        for key, v in list(J.items()):
            if isinstance(v, np.ndarray) and v.shape == (3,) and not key.endswith("Rf"):
                J[key] = v - np.array([0.0, drop, 0.0])
    return J


def _on_head(J, x, y, inset=0.15):
    """머리(타원) 앞 표면 위의 점 — 머리 좌표(가운데 0, 머리 높이 단위)"""
    S, H = J["S"], J["H"]
    h = S["head"] * H
    rx, ry, rz = S["head_w"] * h / 2, h / 2, S["head_d"] * h / 2
    X, Y = x * h, y * h
    z = rz * math.sqrt(max(0.0, 1 - (X / rx) ** 2 - (Y / ry) ** 2))
    # 턱(아래 앞으로 나온 타원)이 더 앞이면 그 표면에 — 입 · 볼이 턱에 묻히지 않게
    jy, jz, jrx, jry, jrz = -h * 0.28, h * 0.12, rx * 0.72, h * 0.22, rz * 0.8
    q = 1 - (X / jrx) ** 2 - ((Y - jy) / jry) ** 2
    if q > 0:
        z = max(z, jz + jrz * math.sqrt(q))
    z -= inset * 0.05 * h
    return J["head"] + J["Rh"] @ [X, Y, z]


FACE = {"smile": 0.3, "open": 0.0, "brow": 0.0, "brow_y": 0.0, "eyelid": 0.0, "blush": 0.0, "look": [0.0, 0.0]}
HAIR = {"top": 0.6, "bangs": 0.5, "side": 0.3, "back": 0.35, "tail": 0.0, "bun": 0.0, "spikes": 0, "part": 0.0}


def _hand(J, side, f, M, mode, grip, spread):
    """손: 손바닥 + 엄지(기본, mitten) 또는 손가락 다섯(fingers). grip 0 펴기 … 1 주먹, spread 손가락 벌림(°)"""
    Rf, wr = J[f"{side}_Rf"], J[f"{side}_wrist"]
    sx = 1 if side == "l" else -1
    hs = f("hand")
    palm_c = wr + Rf @ [0, -hs * 0.45, 0]
    parts = [ell(palm_c, [hs * 0.38, hs * 0.48, hs * 0.16], Rf, M["skin"])]
    curl = 95 * float(grip)
    if mode == "fingers":
        for i, xo in enumerate((-0.27, -0.09, 0.09, 0.27)):
            Rg = Rf @ Rz(sx * (xo * float(spread) * 2))
            base = palm_c + Rf @ [xo * hs, -hs * 0.45, 0]
            ln = hs * (0.42 if i in (1, 2) else 0.36)
            mid = base + Rg @ [0, -ln * 0.55, 0]
            Rg2 = Rg @ Rx(-curl)
            tip = mid + Rg2 @ [0, -ln * 0.45, 0]
            parts += [seg(base, mid, hs * 0.075, hs * 0.07, M["skin"]), seg(mid, tip, hs * 0.07, hs * 0.06, M["skin"])]
    tb = palm_c + Rf @ [-sx * hs * 0.3, -hs * 0.05, hs * 0.08]
    Rt = Rf @ Rz(-sx * (40 - 25 * float(grip))) @ Rx(-30 * float(grip))
    parts.append(seg(tb, tb + Rt @ [0, -hs * 0.42, 0], hs * 0.09, hs * 0.07, M["skin"]))
    return parts


def _face(J, S, h, M, F):
    """표정: 눈(눈꺼풀 · 시선) · 눈썹(높이 · 기울기) · 입(웃음 −1 찡그림 … 1 웃음 · 벌림 0~1) · 볼.
    2026-11-21 구조 변경: 이목구비를 3D 구슬 · 막대로 얼굴에 박지 않는다(입에 구슬 이음 자국, 눈이 구슬 모양) —
    얼굴 표면 위 점들로 된 '획'(선 · 채움 · 점)으로 내고, 화풍이 렌더 뒤 화면에 투영해 매끈한 곡선으로 그린다(style.draw_strokes).
    가려지면(머리카락 · 고개 돌림) 깊이로 지운다. 돌려주는 것: (형태 목록, 획 목록)"""
    out, strokes = [], []
    e = S["eye"]
    lid = max(0.06, 1 - float(F["eyelid"]))
    lx, ly = (F.get("look") or [0, 0])[:2]
    sm, op = float(F["smile"]), float(F["open"])
    for sx in (1, -1):
        ex, ey = sx * S["eye_sep"] * S["head_w"] / 2, S["eye_y"]
        # 눈 = 층: 흰자(눈 모양) → 그 안에 잘려 들어간 홍채 · 동공(시선을 따라 움직이고 눈꺼풀에 가려진다) → 반사점 → 위 눈꺼풀 선.
        # 2026-11-21: 검은 아몬드 하나 + 반사점이라 흰자 · 눈동자가 없는 벌레 눈 같았다
        W2, up_h, lo_h = e * 0.95, e * 0.8 * lid, e * (0.5 - 0.3 * max(sm, 0)) * lid
        ring = [(ex + sx * u * W2, ey + up_h * (1 - u * u) ** 0.7 + 0.12 * e * u) for u in np.linspace(-1, 1, 11)]          # 위(안 → 바깥, 눈꼬리 살짝 올라감)
        ring += [(ex + sx * u * W2, ey - lo_h * (1 - u * u) ** 1.1 + 0.12 * e * u) for u in np.linspace(1, -1, 11)[1:-1]]  # 아래(바깥 → 안)
        ix, iy = ex + 0.35 * e * lx * 0 + 0.55 * e * lx, ey + 0.05 * e + 0.4 * e * ly                                       # 홍채 가운데(시선)
        ir = e * 0.62

        def disk(cx, cy, rr, n=16):
            return [_on_head(J, cx + rr * math.cos(t), cy + rr * math.sin(t), -0.22).tolist() for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]
        lidl = [(ex + sx * u * W2 * (1.0 + 0.08 * max(u, 0)), ey + up_h * (1 - u * u) ** 0.7 + 0.12 * e * u + 0.006 + 0.03 * e * max(u - 0.7, 0) / 0.3)
                for u in np.linspace(-1, 1, 11)]
        strokes.append({"kind": "eye", "pts": [_on_head(J, x, y, -0.2).tolist() for x, y in ring],
                        "iris": disk(ix, iy, ir), "pupil": disk(ix, iy, ir * 0.45),
                        "hi": _on_head(J, ix + sx * 0 + 0.3 * ir, iy + 0.35 * ir, -0.3).tolist(), "hi_r": ir * 0.28 * h,
                        "lid": [_on_head(J, x, y, -0.25).tolist() for x, y in lidl], "lid_w": 0.028 * h,
                        "mat": M["eye"], "sclera": "#fbf7f1", "lidc": "#2a1c14"})
        # 눈썹: 붓 획 하나(안쪽이 굵고 바깥이 가늘게). brow > 0 이면 안쪽이 내려가 화남, < 0 걱정
        by = ey + 0.13 + 0.06 * float(F["brow_y"])
        tilt = float(F["brow"]) * 0.045
        bl = [(ex + sx * u * e * 0.85, by + 0.018 * (1 - u * u) - tilt * (-u) + 0.0) for u in np.linspace(-1, 1, 7)]
        strokes.append({"kind": "line", "pts": [_on_head(J, x, y, -0.2).tolist() for x, y in bl], "w": 0.03 * h, "taper": [1.0, 0.3], "mat": M["hair"]})
        if float(F["blush"]) > 0 and M.get("blush"):
            out.append(ell(_on_head(J, ex * 1.15, ey - 0.13, 0.5), [e * h * 0.6, e * h * 0.3, e * h * 0.2], J["Rh"], M["blush"]))
    my, mw = S["mouth_y"], S["mouth_w"]
    if op > 0.12:                                         # 벌린 입: 위 입술선 + 아래로 둥근 채움(웃으면 넓고 아래가 큼)
        wq = mw / 2 * (0.8 + 0.3 * max(sm, 0))
        ring = [(u * wq, my + 0.04 * sm * (u * u - 0.3)) for u in np.linspace(-1, 1, 9)]
        ring += [(u * wq * 0.9, my - (0.03 + 0.09 * op) * (1 - u * u) ** 0.9) for u in np.linspace(1, -1, 9)[1:-1]]
        strokes.append({"kind": "fill", "pts": [_on_head(J, x, y, -0.2).tolist() for x, y in ring], "mat": M["mouth"]})
    else:                                                 # 다문 입: 끝이 가늘어지는 곡선 하나 — 끝이 올라가면 웃음, 내려가면 찡그림
        ml = [(u * mw / 2, my + 0.05 * sm * (u * u - 0.35)) for u in np.linspace(-1, 1, 9)]
        strokes.append({"kind": "line", "pts": [_on_head(J, x, y, -0.2).tolist() for x, y in ml], "w": 0.024 * h, "taper": [0.25, 0.25], "mat": M["mouth"]})
    return out, strokes


_HAIR_STROKES: list = []


def _hair(J, S, h, M, Hs):
    """머리 모양: 윗머리 볼륨 · 앞머리 · 옆머리 · 뒷머리 길이 · 포니테일 · 올림머리 · 뻗친 머리 · 가르마.
    2026-11-21 구조 변경: 큰 타원 덩어리(헬멧)가 아니라 머리 다발(뿌리 → 가운데 → 가늘어지는 끝, 두피를 따라 휘는 뭉치)로 짓는다 —
    다발 사이에 선이 생기고 실루엣 끝이 갈라져 그린 머리처럼 보인다. 윗머리 껍데기는 다발 사이 틈을 가리는 바탕"""
    Rh, c = J["Rh"], J["head"]
    rx, ry, rz = S["head_w"] * h / 2, h / 2, S["head_d"] * h / 2
    v, part = float(Hs["top"]), float(Hs["part"])

    def on(phi, el, lift=0.0):                       # 머리 위 점: phi 0 = 앞, 90 = 왼쪽(+x) · el 위(+90) ~ 아래(-90)
        d = np.array([math.sin(math.radians(phi)) * math.cos(math.radians(el)), math.sin(math.radians(el)),
                      math.cos(math.radians(phi)) * math.cos(math.radians(el))])
        t = 1.0 / math.sqrt((d[0] / rx) ** 2 + (d[1] / ry) ** 2 + (d[2] / rz) ** 2)
        return c + Rh @ (d * t * (1.0 + lift))

    def lock(p0, p1, p2, r0, r2):                    # 다발 하나: 두 마디로 휘어 끝이 뾰족
        rm = (r0 + r2) * 0.55
        return [seg(p0, p1, r0, rm, M["hair"]), seg(p1, p2, rm, r2, M["hair"])]

    out = [ell(c + Rh @ [0, 0.08 * h + 0.04 * h * v, -0.06 * h], [rx * (1.0 + 0.07 * v), ry * (0.8 + 0.12 * v), rz * (0.98 + 0.05 * v)], Rh, M["hair"])]
    if float(Hs["bangs"]) > 0:
        bg = float(Hs["bangs"])
        n = 5 + int(round(2 * bg))
        for i in range(n):
            u = i / (n - 1) * 2 - 1
            phi = u * 60 + part * 25
            tip_el = 32 - 24 * bg + 8 * u * u + (3 if i % 2 else -2)        # 가운데가 짧고 옆이 길게, 끝 높이를 조금씩 엇갈리게
            out += lock(on(phi * 0.55, 64, 0.05), on(phi * 0.92, 47, 0.1), on(phi * 1.02, tip_el, 0.025), 0.14 * h, 0.014 * h)
    if float(Hs["side"]) > 0:
        sd = float(Hs["side"])
        for sx in (1, -1):
            for k, ph in enumerate((72, 92)):
                out += lock(on(sx * ph, 45, 0.06), on(sx * (ph + 6), 5, 0.12), on(sx * (ph + 4), -20 - 45 * sd - 6 * k, 0.06), 0.09 * h, 0.014 * h)
    if float(Hs["back"]) > 0:
        L = float(Hs["back"])
        for k in range(7):
            ph = 110 + k * (140 / 6)
            tip = on(ph, -25, 0.08) + np.array([0.0, -L * 0.75 * h, 0.0]) + Rh @ np.array([0, 0, -0.04 * h])
            out += lock(on(ph, 45, 0.05), on(ph, -5, 0.14), tip, 0.13 * h, 0.02 * h)
    # 하이라이트 띠: 머리 위를 가로지르는 넓은 획(앞머리 · 다발에 가려지면 끊긴다) — 반사 얼룩 대신(style.draw_strokes)
    band = [on(ph, 58 - 6 * abs(ph) / 70, 0.16 + 0.05 * v).tolist() for ph in np.linspace(-70, 70, 9)]
    _HAIR_STROKES.append({"kind": "line", "pts": band, "w": 0.05 * h, "taper": [0.0, 0.0], "mat": M["hair"], "light": 0.3})
    if float(Hs["tail"]) > 0:                         # 포니테일: 뒤통수에서 아래로 늘어진 관
        L = float(Hs["tail"]) * h * 1.6
        a = c + Rh @ [0, 0.12 * h, -rz * 0.95]
        b = a + Rh @ [0, -L * 0.45, -L * 0.25]
        d = b + np.array([0.0, -L * 0.55, 0.0])
        out += [seg(a, b, 0.11 * h, 0.1 * h, M["hair"]), seg(b, d, 0.1 * h, 0.04 * h, M["hair"])]
    if float(Hs["bun"]) > 0:
        out.append(ell(c + Rh @ [0, ry * 1.08, -rz * 0.7], [0.23 * h * float(Hs["bun"])] * 3, Rh, M["hair"]))
    n = int(Hs["spikes"])
    for i in range(n):                                # 뻗친 머리: 위로 퍼지는 뾰족한 다발
        ang = (i / max(1, n - 1) - 0.5) * 110
        Rk = Rh @ Rz(ang) @ Rx(-25)
        base = c + Rh @ [0, ry * 0.55, -0.05 * h]
        out.append({"prim": "roundcone", "r1": 0.13 * h, "r2": 0.015 * h, "h": 0.45 * h, "pos": base.tolist(), "rotm": Rk.tolist(), "mat": M["hair"]})
    return out


def expand(node: dict) -> dict:
    if node.get("rig") == "quadruped":
        return expand_quad(node)
    if node.get("rig") == "bird":
        return expand_bird(node)
    J = joints(node.get("size") or {}, node.get("pose") or {}, node.get("_ik"), ground=not node.get("_ik"))
    M = {**MATS, **(node.get("mats") or {})}
    W = {"sleeve": 0.3, "pants": 1.0, **(node.get("wear") or {})}
    Fc = {**FACE, **(node.get("face") or {})}
    Hs = {**HAIR, **({"back": W["hair"]} if "hair" in W else {}), **(node.get("hair") or {})}
    P = {**POSE, **(node.get("pose") or {})}
    S, H = J["S"], J["H"]
    f = lambda k: float(S[k]) * H  # noqa: E731
    Rs, Rh, R0 = J["Rs"], J["Rh"], J["R0"]
    pel, neck0 = J["pelvis"], J["neck"]
    SU = lambda k, ch: {"op": "smooth_union", "k": k, "children": [c for c in ch if c]}  # noqa: E731
    JU = lambda at, k, reach, ch: {"op": "joint_union", "at": np.asarray(at, float).tolist(), "k": k, "reach": reach, "children": ch}  # noqa: E731
    # 2026-11-21 구조 변경: 몸 전체를 한 반경(키의 1.2%)으로 녹여 붙이던 것을 부위 묶음 → 관절마다 그 굵기에 맞는 반경으로 차례로 붙인다.
    # 한 반경이면 어깨 · 엉덩이처럼 굵은 이음매는 울퉁불퉁 끊겨 보이고, 키우면 손가락 · 귀 같은 작은 부위가 녹았다.
    # 묶음 안의 부품끼리만 매끈하게 섞이고(그 묶음의 반경), 묶음과 묶음은 관절 반경으로 이어진다.
    Rw, mid = J["Rw"], J["mid"]
    torso = [ell(mid + Rs @ [0, f("torso") * 0.26, 0], [f("chest_w") * 0.97, f("torso") * 0.3, f("chest_d")], Rs, M["top"]),      # 가슴: 가슴 마디
             ell(pel + Rw @ [0, f("torso") * 0.38, 0], [f("waist_w") * 1.05, f("torso") * 0.28, f("chest_d") * 0.92], Rw, M["top"])]  # 허리: 허리 마디
    for side in ("l", "r"):
        sh = J[f"{side}_shoulder"]
        torso.append(ell(sh + Rs @ [0, 0.004 * H, 0], [f("arm_r") * 1.15] * 3, Rs, M["top"]))                       # 어깨 근육
        torso.append(seg(neck0 + Rs @ [0, -0.01 * H, -0.01 * H], sh, f("neck_r") * 1.1, f("arm_r") * 1.15, M["top"]))  # 승모근
    hips = [ell(pel + R0 @ [0, 0.015 * H, -0.005 * H], [f("pelvis_w"), 0.07 * H, f("chest_d") * 0.95], R0, M["bottom"])]
    h = f("head")
    hb = J["head"] - Rh @ [0, h * 0.42, 0]
    neck = [seg(neck0 - Rs @ [0, 0.02 * H, 0], hb, f("neck_r"), f("neck_r") * 0.95, M["skin"])]
    head = [ell(J["head"], [S["head_w"] * h / 2, h / 2, S["head_d"] * h / 2], Rh, M["skin"]),
            ell(J["head"] + Rh @ [0, -h * 0.28, h * 0.12], [S["head_w"] * h / 2 * 0.72, h * 0.22, S["head_d"] * h / 2 * 0.8], Rh, M["skin"])]   # 턱
    ears = [ell(J["head"] + Rh @ [sx * S["head_w"] * h / 2 * 0.98, -0.02 * h, -0.05 * h], [0.06 * h, 0.11 * h, 0.07 * h], Rh, M["skin"]) for sx in (1, -1)]
    if S["nose"] > 0:
        head.append(ell(_on_head(J, 0, -0.12, 0.6), [S["nose"] * h * 0.8, S["nose"] * h, S["nose"] * h], Rh, M["skin"]))
    arms, legs = [], []
    for side in ("l", "r"):
        sh, el, wr = J[f"{side}_shoulder"], J[f"{side}_elbow"], J[f"{side}_wrist"]
        arm = [seg(sh, el, f("arm_r"), f("arm_r") * 0.85, M["skin"]), seg(el, wr, f("arm_r") * 0.85, f("wrist_r"), M["skin"])]
        cov = float(W["sleeve"]) * (f("upper_arm") + f("lower_arm"))
        if cov > 0:
            arm.append(seg(sh, sh + (el - sh) * min(1.0, cov / f("upper_arm")), f("arm_r") * 1.25, f("arm_r") * 1.12, M["top"]))
            if cov > f("upper_arm"):
                arm.append(seg(el, el + (wr - el) * min(1.0, (cov - f("upper_arm")) / f("lower_arm")), f("arm_r") * 1.08, f("wrist_r") * 1.2, M["top"]))
        hand = {"op": "union", "children": _hand(J, side, f, M, node.get("hands", "mitten"), P.get(f"{side}_grip", 0.3), P.get(f"{side}_spread", 8))}
        upper = SU(0.004 * H, [x for x in arm if x is not arm[1]])
        arm_g = JU(el, f("arm_r") * 0.45, f("arm_r") * 2.2, [upper, arm[1]])            # 팔꿈치 둘레에서만
        arms.append((sh, JU(wr, f("wrist_r") * 0.7, f("wrist_r") * 3.0, [arm_g, hand])))  # 손목 둘레에서만
        hp, kn, an = J[f"{side}_hip"], J[f"{side}_knee"], J[f"{side}_ankle"]
        leg = [seg(hp, kn, f("leg_r"), f("leg_r") * 0.8, M["skin"]), seg(kn, an, f("leg_r") * 0.8, f("ankle_r"), M["skin"])]
        cov = float(W["pants"]) * (f("upper_leg") + f("lower_leg"))
        if cov > 0:
            leg.append(seg(hp, hp + (kn - hp) * min(1.0, cov / f("upper_leg")), f("leg_r") * 1.12, f("leg_r") * 0.95, M["bottom"]))
            if cov > f("upper_leg"):
                leg.append(seg(kn, kn + (an - kn) * min(1.0, (cov - f("upper_leg")) / f("lower_leg")), f("leg_r") * 0.95, f("ankle_r") * 1.25, M["bottom"]))
        foot = ell(an + R0 @ [0, -f("foot_h") * 0.35, f("foot") * 0.28], [f("ankle_r") * 1.35, f("foot_h") * 0.7, f("foot") * 0.55], R0, M["shoe"])
        thigh = SU(0.004 * H, [x for x in leg if x is not leg[1]])
        leg_g = JU(kn, f("leg_r") * 0.4, f("leg_r") * 2.2, [thigh, leg[1]])              # 무릎 둘레에서만
        legs.append((hp, JU(an, f("ankle_r") * 0.6, f("ankle_r") * 3.0, [leg_g, foot])))
    trunk = SU(0.03 * H, torso)
    for sh, arm in arms:                                                               # 어깨: 어깨 관절 둘레에서만 팔 굵기만큼(옆구리에 붙은 팔은 녹지 않는다)
        trunk = JU(sh, f("arm_r") * 0.9, f("arm_r") * 2.6, [trunk, arm])
    trunk = JU(pel + Rw @ [0, f("torso") * 0.2, 0], 0.04 * H, f("torso") * 0.6, [trunk, *hips])   # 허리 → 골반
    for hp, leg in legs:                                                               # 엉덩이: 고관절 둘레에서만(두 허벅지는 서로 녹지 않는다)
        trunk = JU(hp, f("leg_r") * 0.8, f("leg_r") * 2.0, [trunk, leg])
    headg = SU(0.006 * H, [SU(0.012 * H, head), *ears])
    neck_g = JU(hb, f("neck_r") * 0.5, f("neck_r") * 3.0, [*neck, headg])              # 턱 밑은 좁게
    trunk = JU(neck0, f("neck_r") * 1.0, f("neck_r") * 3.5, [trunk, neck_g])           # 쇄골 쪽은 넓게
    face, strokes = _face(J, S, h, M, Fc)
    _HAIR_STROKES.clear()
    hair = _hair(J, S, h, M, Hs)
    strokes = strokes + list(_HAIR_STROKES)
    out = {"op": "union", "children": [trunk, {"op": "smooth_union", "k": 0.006 * H, "children": hair}] + face,
           "_roles": {"skin": [M["skin"]], "hair": [M["hair"]]}, "_strokes": strokes}      # 화풍이 피부 · 머리카락을 그림처럼 칠한다(style.Ctx._illustrate)
    for key in ("pos", "rot", "rotm", "scale", "name"):
        if key in node:
            out[key] = node[key]
    return out


# ---------------------------------------------------------------- 네 발 동물(고양이 · 개 · 여우 …)
QUAD = {"height": 0.3, "body": 1.45, "chest": 0.36, "belly": 0.32, "hip": 0.33, "neck": 0.28, "neck_r": 0.19, "neck_up": 45,
        "head": 0.52, "head_w": 0.9, "snout": 0.26, "snout_r": 0.3, "ear": 0.32, "ear_w": 0.45,
        "upper_leg": 0.38, "lower_leg": 0.38, "leg_r": 0.1, "paw": 0.11, "tail": 1.1, "tail_r": 0.07, "tail_n": 5,
        "eye": 0.12, "eye_sep": 0.42, "eye_y": 0.12}
QPOSE = {"spine": [0, 0], "neck": [0, 0], "head": [0, 0, 0], "tail": [20, 0, 20],
         "fl": [0, 0], "fl_knee": 0, "fr": [0, 0], "fr_knee": 0, "bl": [0, 0], "bl_knee": 0, "br": [0, 0], "br_knee": 0}
QMATS = {"fur": "fur", "belly": "fur", "nose": "nose", "eye": "eye", "ear": "fur", "paw": "fur", "tail": "fur"}


def expand_quad(node: dict) -> dict:
    """네 발 동물 — 어깨 · 엉덩이를 잇는 척추, 다리 넷, 목 · 머리(주둥이 · 귀 · 눈), 마디 꼬리. 얼굴 +z, 왼쪽 +x"""
    S = {**QUAD, **(node.get("size") or {})}
    P = {**QPOSE, **(node.get("pose") or {})}
    M = {**QMATS, **(node.get("mats") or {})}
    H = float(S["height"]); f = lambda k: float(S[k]) * H  # noqa: E731
    half = f("body") / 2
    yleg = f("upper_leg") + f("lower_leg")
    Rb = Rx(-P["spine"][0]) @ Ry(P["spine"][1])
    sh = np.array([0.0, yleg, 0.0]) + Rb @ [0, 0, half * 0.55]
    hp = np.array([0.0, yleg, 0.0]) + Rb @ [0, 0, -half * 0.6]
    parts, face = [], []
    parts.append(ell(sh + Rb @ [0, f("chest") * 0.15, 0], [f("chest") * 0.85, f("chest"), f("chest") * 1.15], Rb, M["fur"]))
    parts.append(ell((sh + hp) / 2 + Rb @ [0, -0.02 * H, 0], [f("belly") * 0.85, f("belly"), half * 0.75], Rb, M["belly"]))
    parts.append(ell(hp + Rb @ [0, f("hip") * 0.1, 0], [f("hip") * 0.9, f("hip"), f("hip") * 1.1], Rb, M["fur"]))
    feet = []
    for name, base, sx in (("fl", sh, 1), ("fr", sh, -1), ("bl", hp, 1), ("br", hp, -1)):
        top = base + Rb @ [sx * f("chest") * 0.45, -f("chest") * 0.25, 0]
        Rl = Rx(-P[name][0]) @ Rz(sx * P[name][1])
        kn = top + Rl @ [0, -f("upper_leg"), 0]
        Rk = Rl @ Rx(P[f"{name}_knee"] * (1 if name[0] == "f" else -1))
        an = kn + Rk @ [0, -f("lower_leg"), 0]
        parts += [seg(top, kn, f("leg_r") * (1.25 if name[0] == "b" else 1.1), f("leg_r") * 0.85, M["fur"]), seg(kn, an, f("leg_r") * 0.85, f("leg_r") * 0.7, M["fur"])]
        parts.append(ell(an + [0, f("paw") * 0.25, f("paw") * 0.3], [f("paw") * 0.75, f("paw") * 0.5, f("paw")], np.eye(3), M["paw"]))
        feet.append(an[1])
    Rn = Rb @ Rx(-(S["neck_up"] + P["neck"][0])) @ Ry(P["neck"][1])
    n0 = sh + Rb @ [0, f("chest") * 0.35, f("chest") * 0.6]
    n1 = n0 + Rn @ [0, 0, f("neck")]
    parts.append(seg(n0, n1, f("neck_r"), f("neck_r") * 0.9, M["fur"]))
    hd = P["head"]
    Rh = Rb @ Ry(P["neck"][1] + hd[1]) @ Rx(-hd[0]) @ Rz(hd[2])
    hc = n1 + Rh @ [0, f("head") * 0.1, f("head") * 0.15]
    hr = [f("head") * S["head_w"] / 2, f("head") * 0.45, f("head") * 0.5]
    parts.append(ell(hc, hr, Rh, M["fur"]))
    sn = hc + Rh @ [0, -hr[1] * 0.35, hr[2] * 0.75]
    parts.append(ell(sn, [f("head") * S["snout_r"], f("head") * S["snout_r"] * 0.7, f("head") * S["snout"]], Rh, M["fur"]))
    face.append(ell(sn + Rh @ [0, f("head") * S["snout_r"] * 0.45, f("head") * S["snout"] * 0.92], [f("head") * 0.07, f("head") * 0.05, f("head") * 0.05], Rh, M["nose"]))
    for sx in (1, -1):
        ex, ey = sx * S["eye_sep"] * hr[0], S["eye_y"] * f("head")
        ez = hr[2] * math.sqrt(max(0.0, 1 - (ex / hr[0]) ** 2 - (ey / hr[1]) ** 2)) * 0.96
        e = S["eye"] * f("head")
        face.append(ell(hc + Rh @ [ex, ey, ez], [e * 0.5, e * 0.6, e * 0.3], Rh, M["eye"]))
        base = hc + Rh @ [sx * hr[0] * 0.55, hr[1] * 0.75, -hr[2] * 0.1]
        parts.append({"prim": "roundcone", "r1": f("head") * S["ear_w"] * 0.5, "r2": f("head") * 0.02, "h": f("head") * S["ear"],
                      "pos": base.tolist(), "rotm": (Rh @ Rz(-sx * 18)).tolist(), "mat": M["ear"]})
    tl = P["tail"]
    pts = [hp + Rb @ [0, f("hip") * 0.3, -f("hip") * 0.9]]
    d = Rb @ Rx(-tl[0]) @ Ry(tl[1]) @ np.array([0.0, 0.0, -1.0])
    n = int(S["tail_n"]); L = f("tail") / n
    for i in range(n):
        pts.append(pts[-1] + d * L)
        d = Rx(-tl[2] / n) @ d
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        parts.append(seg(a, b, f("tail_r") * (1 - 0.35 * i / n), f("tail_r") * (1 - 0.35 * (i + 1) / n), M["tail"]))
    out = {"op": "union", "children": [{"op": "smooth_union", "k": 0.04 * H, "children": parts}] + face}
    drop = min(feet)
    out["pos"] = (np.asarray(node.get("pos", [0, 0, 0]), float) - [0, drop, 0]).tolist()
    for key in ("rot", "scale", "name"):
        if key in node:
            out[key] = node[key]
    return out


# ---------------------------------------------------------------- 새(오리 · 닭 · 참새 …)
BIRD = {"height": 0.3, "body": 1.15, "body_r": 0.42, "neck": 0.32, "neck_r": 0.15, "neck_up": 65, "head": 0.4,
        "beak": 0.34, "beak_r": 0.1, "beak_down": 8, "eye": 0.13, "wing": 0.95, "wing_w": 0.42, "tail": 0.42, "tail_w": 0.32,
        "leg": 0.42, "leg_r": 0.035, "toe": 0.2}
BPOSE = {"tilt": 0, "neck": [0, 0], "head": [0, 0, 0], "wings": [0, 0], "tail": [10, 0.5], "l_leg": [0], "l_knee": 0, "r_leg": [0], "r_knee": 0}
BMATS = {"body": "body", "belly": "body", "wing": "body", "tail": "body", "beak": "beak", "leg": "beak", "eye": "eye"}


def expand_bird(node: dict) -> dict:
    """새 — 몸통 · 목 · 머리 · 부리 · 눈, 날개 둘(날갯짓 wings[0] · 펼침 wings[1]), 꼬리(들기 · 부채), 다리 둘(무릎 · 발가락). 얼굴 +z"""
    S = {**BIRD, **(node.get("size") or {})}
    P = {**BPOSE, **(node.get("pose") or {})}
    M = {**BMATS, **(node.get("mats") or {})}
    H = float(S["height"]); f = lambda k: float(S[k]) * H  # noqa: E731
    Rb = Rx(-P["tilt"])
    c = np.array([0.0, f("leg") + f("body_r") * 0.55, 0.0])
    parts, face = [], []
    parts.append(ell(c, [f("body_r") * 0.82, f("body_r"), f("body") / 2], Rb, M["body"]))
    parts.append(ell(c + Rb @ [0, -f("body_r") * 0.2, f("body") * 0.12], [f("body_r") * 0.78, f("body_r") * 0.85, f("body") * 0.36], Rb, M["belly"]))
    n0 = c + Rb @ [0, f("body_r") * 0.5, f("body") / 2 * 0.62]
    Rn = Rb @ Ry(P["neck"][1]) @ Rx(-(S["neck_up"] + P["neck"][0]))
    n1 = n0 + Rn @ [0, 0, f("neck")]
    parts.append(seg(n0, n1, f("neck_r") * 1.15, f("neck_r"), M["body"]))
    hd = P["head"]
    Rh = Rb @ Ry(P["neck"][1] + hd[1]) @ Rx(-hd[0]) @ Rz(hd[2])
    hr = f("head") / 2
    hc = n1 + Rh @ [0, hr * 0.35, hr * 0.15]
    parts.append(ell(hc, [hr * 0.85, hr * 0.95, hr], Rh, M["body"]))
    bb = hc + Rh @ [0, -hr * 0.12, hr * 0.8]
    bd = Rh @ Rx(S["beak_down"]) @ np.array([0.0, 0.0, 1.0])
    face.append(seg(bb, bb + bd * f("beak"), f("beak_r") * 1.0, f("beak_r") * 0.25, M["beak"]))
    for sx in (1, -1):
        e = S["eye"] * f("head")
        face.append(ell(hc + Rh @ [sx * hr * 0.62, hr * 0.22, hr * 0.55], [e * 0.3, e * 0.55, e * 0.5], Rh, M["eye"]))
        ws = c + Rb @ [sx * f("body_r") * 0.7, f("body_r") * 0.3, f("body") * 0.15]
        Rw = Rb @ Rz(sx * float(P["wings"][0])) @ Ry(-sx * float(P["wings"][1]))
        parts.append(ell(ws + Rw @ [sx * f("body_r") * 0.12, -f("wing_w") * 0.15, -f("wing") * 0.32], [f("body_r") * 0.16, f("wing_w") * 0.5, f("wing") * 0.5], Rw, M["wing"]))
    tl = P["tail"]
    Rt = Rb @ Rx(-float(tl[0]))
    parts.append(ell(c + Rb @ [0, f("body_r") * 0.25, -f("body") / 2 * 0.8] + Rt @ [0, 0, -f("tail") * 0.35],
                     [f("tail_w") * (0.4 + 0.6 * float(tl[1])), f("body_r") * 0.12, f("tail") * 0.5], Rt, M["tail"]))
    feet = []
    for side, sx in (("l", 1), ("r", -1)):
        hp = c + Rb @ [sx * f("body_r") * 0.35, -f("body_r") * 0.55, 0]
        Rl = Rx(-float(P[f"{side}_leg"][0]))
        kn = hp + Rl @ [0, -f("leg") * 0.45, 0]
        an = kn + Rl @ Rx(float(P[f"{side}_knee"])) @ [0, -f("leg") * 0.55, 0]
        parts += [seg(hp, kn, f("leg_r") * 1.6, f("leg_r"), M["leg"]), seg(kn, an, f("leg_r"), f("leg_r") * 0.9, M["leg"])]
        for ang in (-30, 0, 30):
            d = Ry(ang) @ np.array([0.0, 0.0, 1.0])
            parts.append(seg(an, an + d * f("toe") + [0, -f("leg_r") * 0.5, 0], f("leg_r") * 0.9, f("leg_r") * 0.6, M["leg"]))
        parts.append(seg(an, an + np.array([0, -f("leg_r") * 0.5, -f("toe") * 0.45]), f("leg_r") * 0.9, f("leg_r") * 0.6, M["leg"]))
        feet.append(an[1] - f("leg_r") * 1.1)
    out = {"op": "union", "children": [{"op": "smooth_union", "k": 0.03 * H, "children": parts}] + face}
    out["pos"] = (np.asarray(node.get("pos", [0, 0, 0]), float) - [0, min(feet), 0]).tolist()
    for key in ("rot", "scale", "name"):
        if key in node:
            out[key] = node[key]
    return out
