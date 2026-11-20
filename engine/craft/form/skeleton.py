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
        "l_arm": [0, 8, 0], "l_elbow": 8, "r_arm": [0, 8, 0], "r_elbow": 8,
        "l_leg": [0, 2], "l_knee": 0, "r_leg": [0, 2], "r_knee": 0}
MATS = {"skin": "skin", "hair": "hair", "top": "top", "bottom": "bottom", "shoe": "shoe", "eye": "eye", "mouth": "mouth"}


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


def joints(size: dict, pose: dict) -> dict:
    """관절 위치 · 뼈 방향(순운동학). 키 단위(m)"""
    S = {**DEFAULT, **(size or {})}
    P = {**POSE, **(pose or {})}
    H = float(S["height"]); f = lambda k: float(S[k]) * H  # noqa: E731
    lean = P["lean"]; sp = P["spine"]; hd = P["head"]
    R0 = Rx(-lean[0]) @ Rz(lean[1])
    yhip = f("foot_h") + f("lower_leg") + f("upper_leg")
    pel = np.array([0.0, yhip, 0.0])
    Rs = R0 @ Rx(-sp[0]) @ Rz(sp[1]) @ Ry(sp[2])
    neck0 = pel + Rs @ [0, f("torso"), 0]
    Rh = Rs @ Ry(hd[1]) @ Rx(-hd[0]) @ Rz(hd[2])
    head = neck0 + Rh @ [0, f("neck") + f("head") * 0.5, f("head") * 0.06]
    J = {"S": S, "H": H, "R0": R0, "Rs": Rs, "Rh": Rh, "pelvis": pel, "neck": neck0, "head": head}
    for side, sx in (("l", 1), ("r", -1)):
        arm, elbow = P[f"{side}_arm"], P[f"{side}_elbow"]
        sh = neck0 + Rs @ [sx * f("chest_w") * 0.93, -f("torso") * 0.07, 0]
        Ra = Rs @ Rz(sx * arm[1]) @ Rx(-arm[0]) @ Ry(sx * (arm[2] if len(arm) > 2 else 0))
        el = sh + Ra @ [0, -f("upper_arm"), 0]
        Rf = Ra @ Rx(-elbow)
        wr = el + Rf @ [0, -f("lower_arm"), 0]
        J[f"{side}_shoulder"], J[f"{side}_elbow"], J[f"{side}_wrist"], J[f"{side}_hand"], J[f"{side}_Rf"] = sh, el, wr, wr + Rf @ [0, -f("hand") * 0.55, 0], Rf
        leg, knee = P[f"{side}_leg"], P[f"{side}_knee"]
        hp = pel + R0 @ [sx * f("hip_w"), 0, 0]
        Rt = R0 @ Rz(sx * leg[1]) @ Rx(-leg[0])
        kn = hp + Rt @ [0, -f("upper_leg"), 0]
        Rk = Rt @ Rx(knee)
        an = kn + Rk @ [0, -f("lower_leg"), 0]
        J[f"{side}_hip"], J[f"{side}_knee"], J[f"{side}_ankle"] = hp, kn, an
    # 바닥에 닿기: 무릎을 굽히거나 다리를 들면 발이 뜬다 — 가장 낮은 발목이 곧게 선 높이(발 높이)에 오게 몸 전체를 내린다
    drop = min(J["l_ankle"][1], J["r_ankle"][1]) - f("foot_h")
    if abs(drop) > 1e-6:
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
    z = rz * math.sqrt(max(0.0, 1 - (X / rx) ** 2 - (Y / ry) ** 2)) - inset * 0.05 * h
    return J["head"] + J["Rh"] @ [X, Y, z]


def expand(node: dict) -> dict:
    if node.get("rig") == "quadruped":
        return expand_quad(node)
    J = joints(node.get("size") or {}, node.get("pose") or {})
    M = {**MATS, **(node.get("mats") or {})}
    W = {"sleeve": 0.3, "pants": 1.0, "hair": 0.35, **(node.get("wear") or {})}
    S, H = J["S"], J["H"]
    f = lambda k: float(S[k]) * H  # noqa: E731
    Rs, Rh, R0 = J["Rs"], J["Rh"], J["R0"]
    body, cloth, face = [], [], []
    pel, neck0 = J["pelvis"], J["neck"]
    # 몸통 · 골반 · 목 · 머리
    cloth.append(ell(pel + Rs @ [0, f("torso") * 0.66, 0], [f("chest_w"), f("torso") * 0.34, f("chest_d")], Rs, M["top"]))
    cloth.append(ell(pel + Rs @ [0, f("torso") * 0.3, 0], [f("waist_w"), f("torso") * 0.32, f("chest_d") * 0.9], Rs, M["top"]))
    cloth.append(ell(pel + R0 @ [0, 0.01 * H, 0], [f("pelvis_w"), 0.075 * H, f("chest_d") * 0.95], R0, M["bottom"]))
    hb = J["head"] - Rh @ [0, f("head") * 0.42, 0]
    body.append(seg(neck0 - Rs @ [0, 0.02 * H, 0], hb, f("neck_r"), f("neck_r") * 0.95, M["skin"]))
    h = f("head")
    body.append(ell(J["head"], [S["head_w"] * h / 2, h / 2, S["head_d"] * h / 2], Rh, M["skin"]))
    body.append(ell(J["head"] + Rh @ [S["head_w"] * h / 2 * 0.98, -0.02 * h, -0.05 * h], [0.06 * h, 0.11 * h, 0.07 * h], Rh, M["skin"]))   # 귀
    body.append(ell(J["head"] + Rh @ [-S["head_w"] * h / 2 * 0.98, -0.02 * h, -0.05 * h], [0.06 * h, 0.11 * h, 0.07 * h], Rh, M["skin"]))
    # 팔 · 다리 — 피부 뼈 위에 옷이 덮는 비율만큼 조금 굵은 천
    for side in ("l", "r"):
        sh, el, wr, hd_ = J[f"{side}_shoulder"], J[f"{side}_elbow"], J[f"{side}_wrist"], J[f"{side}_hand"]
        body += [seg(sh, el, f("arm_r"), f("arm_r") * 0.85, M["skin"]), seg(el, wr, f("arm_r") * 0.85, f("wrist_r"), M["skin"]),
                 ell(hd_, [f("hand") * 0.36, f("hand") * 0.55, f("hand") * 0.22], J[f"{side}_Rf"], M["skin"])]
        cov = float(W["sleeve"]) * (f("upper_arm") + f("lower_arm"))
        if cov > 0:
            cloth.append(seg(sh, sh + (el - sh) * min(1.0, cov / f("upper_arm")), f("arm_r") * 1.25, f("arm_r") * 1.12, M["top"]))
            if cov > f("upper_arm"):
                cloth.append(seg(el, el + (wr - el) * min(1.0, (cov - f("upper_arm")) / f("lower_arm")), f("arm_r") * 1.08, f("wrist_r") * 1.2, M["top"]))
        hp, kn, an = J[f"{side}_hip"], J[f"{side}_knee"], J[f"{side}_ankle"]
        body += [seg(hp, kn, f("leg_r"), f("leg_r") * 0.8, M["skin"]), seg(kn, an, f("leg_r") * 0.8, f("ankle_r"), M["skin"])]
        cov = float(W["pants"]) * (f("upper_leg") + f("lower_leg"))
        if cov > 0:
            cloth.append(seg(hp, hp + (kn - hp) * min(1.0, cov / f("upper_leg")), f("leg_r") * 1.12, f("leg_r") * 0.95, M["bottom"]))
            if cov > f("upper_leg"):
                cloth.append(seg(kn, kn + (an - kn) * min(1.0, (cov - f("upper_leg")) / f("lower_leg")), f("leg_r") * 0.95, f("ankle_r") * 1.25, M["bottom"]))
        body.append(ell(an + R0 @ [0, -f("foot_h") * 0.35, f("foot") * 0.28], [f("ankle_r") * 1.35, f("foot_h") * 0.7, f("foot") * 0.55], R0, M["shoe"]))
    # 얼굴(머리 뼈에 붙음 — 고개를 돌리면 같이 돈다)
    e = S["eye"] * h
    for sx in (1, -1):
        face.append(ell(_on_head(J, sx * S["eye_sep"] * S["head_w"] / 2, S["eye_y"]), [e * 0.42, e * 0.6, e * 0.3], Rh, M["eye"]))
    face.append(ell(_on_head(J, 0, S["mouth_y"], 0.3), [S["mouth_w"] * h / 2, 0.018 * h, 0.03 * h], Rh, M["mouth"]))
    if S["nose"] > 0:
        body.append(ell(_on_head(J, 0, -0.12, 0.6), [S["nose"] * h * 0.8, S["nose"] * h, S["nose"] * h], Rh, M["skin"]))
    # 머리카락: 위 · 뒤를 덮는 덩어리 + 뒷머리 길이
    rx, ry, rz = S["head_w"] * h / 2, h / 2, S["head_d"] * h / 2
    hair = [ell(J["head"] + Rh @ [0, 0.13 * h, -0.07 * h], [rx * 1.07, ry * 0.86, rz * 1.02], Rh, M["hair"])]
    if float(W["hair"]) > 0:
        L = float(W["hair"])
        hair.append(ell(J["head"] + Rh @ [0, -0.15 * h - L * 0.35 * h, -0.2 * h], [rx * 1.0, ry * (0.55 + 0.7 * L), rz * 0.62], Rh, M["hair"]))
    k = 0.012 * H
    out = {"op": "union", "children": [
        {"op": "smooth_union", "k": k, "children": body + cloth},
        {"op": "smooth_union", "k": 0.006 * H, "children": hair}] + face}
    for key in ("pos", "rot", "scale", "name"):
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
