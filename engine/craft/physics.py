#!/usr/bin/env python3
"""물리로 움직임 계산 — MuJoCo(DeepMind, Apache-2.0)가 떨어짐 · 부딪힘 · 튕김 · 쌓임 · 넘어짐을 계산하고, 렌더는 Blender 가 한다.
손으로 짠 키프레임보다 자연스러운 움직임(2026-11-09 · 11-10 영상: '카메라 · 움직임이 딱딱하다', '꾸러미 움직임이 어울리지 않는다').

  python3 engine/craft/physics.py run <장면.mjcf.xml> [--sec 4] [--fps 30] [--args '{"friction": 0.6}'] [--out 궤적.json]
  python3 engine/craft/physics.py check <장면.mjcf.xml>          # 문법만 확인 · 물체(body) 이름 목록

장면(MJCF — MuJoCo 의 XML)에 {{이름}} 을 쓰면 args 값으로 바뀐다 — 마찰 · 탄성 · 높이 · 미는 힘 같은 숫자를 코드에 박지 않고
콘티 재료의 args 로 둔다(대화로 고칠 때 knob.py set <id> <요소>.args.friction=0.4).
결과: {"fps", "sec", "bodies": {이름: [[x, y, z, qw, qx, qy, qz], …프레임마다]}} — 이름 있는 body 만. 좌표는 MuJoCo 그대로(Z 위, 미터) = Blender 와 같은 축.
Blender 쪽: fluma3d.physics(ctx.args["physics"], {"이름": 물체, …}) 가 프레임마다 위치 · 회전 키를 넣는다.
재료 쓰는 법(콘티): {"type": "model3d", "method": "blender", "script": "…/scene.py", "physics": "…/scene.mjcf.xml", "args": {…}, "sec": 4}

2D 장면(EffectCraft 레이어 · 자막 · 아이콘 · 막대): 재료 {"type": "physics", "physics": "…/coins.py", "bind": {"coin*": "…/coin.svg"}, "args": {…}}
  — 계산 결과를 화면 평면(x 오른쪽, z 위 → 화면 아래쪽 바닥)으로 비춰 레이어마다 위치 · 회전 키를 넣는다(engine/craft/motion.py).
장면을 파이썬으로 조립(dm_control.mjcf, 반복 배치 · 무작위 흩뿌리기): <이름>.py 에 def scene(args) → mjcf.RootElement · mujoco.MjSpec · XML 글.
카메라: spring_follow(목표 [(초, x, y, 확대)], 단단함, 출렁임) — 목표를 스프링으로 따라가 늦게 붙고 부드럽게 멈춘다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def fill(xml: str, args: dict | None) -> str:
    """{{이름}} → args 값. 빠진 이름이 있으면 멈춘다(조용히 0 이 되면 물체가 이상하게 움직인다)"""
    args = args or {}

    def rep(m):
        k = m.group(1)
        if k not in args:
            raise KeyError(f"장면의 {{{{{k}}}}} 에 넣을 값이 args 에 없습니다")
        return str(args[k])
    return re.sub(r"\{\{\s*([A-Za-z_][\w]*)\s*\}\}", rep, xml)


def scene_xml(path: Path, args: dict | None = None) -> str:
    """장면 → MJCF 글. .py 면 그 안의 scene(args) 를 부른다(dm_control.mjcf 로 조립) · 그 밖은 XML 에 {{이름}} 채우기"""
    path = Path(path)
    if path.suffix == ".py":
        import runpy
        ns = runpy.run_path(str(path))
        if "scene" not in ns:
            raise RuntimeError(f"{path.name}: def scene(args) 가 없습니다")
        try:
            out = ns["scene"](dict(args or {}))
        except ModuleNotFoundError as e:
            if "dm_control" in str(e):
                raise RuntimeError("dm_control 이 없습니다 — .venv/bin/python -m pip install --no-deps dm_control dm-env absl-py lxml dm-tree") from e
            raise
        return out if isinstance(out, str) else out
    return fill(path.read_text("utf-8"), args)


def load(xml_path: Path, args: dict | None = None):
    """장면 → MjModel. dm_control 로 조립한 장면은 붙인 모델(menagerie 손 등)의 메시 파일까지 assets 로 넘긴다.
    XML 장면은 장면 파일 옆에서 읽어 <include> · 메시 경로가 그 폴더 기준으로 풀린다"""
    import mujoco
    x = scene_xml(xml_path, args)
    if hasattr(x, "compile"):                                # mujoco.MjSpec(myo_sim.load_spec 등) — 그대로 컴파일
        return x.compile()
    if not isinstance(x, str):
        return mujoco.MjModel.from_xml_string(x.to_xml_string(), assets=x.get_assets())
    xml_path = Path(xml_path)
    if xml_path.suffix != ".py" and ("<include" in x or "file=" in x):
        tmp = xml_path.with_name(f".{xml_path.stem}.filled.xml")
        tmp.write_text(x, "utf-8")
        try:
            return mujoco.MjModel.from_xml_path(str(tmp))
        finally:
            tmp.unlink(missing_ok=True)
    return mujoco.MjModel.from_xml_string(x)


def shapes(model) -> dict:
    """body 이름 → 첫 geom 의 모양(type box|sphere|capsule|cylinder|ellipsoid · size 반지름/반길이 · rgba) — 2D 에서 그림 크기를 맞춘다"""
    import mujoco
    kinds = {int(mujoco.mjtGeom.mjGEOM_BOX): "box", int(mujoco.mjtGeom.mjGEOM_SPHERE): "sphere", int(mujoco.mjtGeom.mjGEOM_CAPSULE): "capsule",
             int(mujoco.mjtGeom.mjGEOM_CYLINDER): "cylinder", int(mujoco.mjtGeom.mjGEOM_ELLIPSOID): "ellipsoid"}
    out = {}
    for i in range(1, model.nbody):
        n = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or f"body{i}"
        if model.body_geomnum[i] == 0:
            continue
        g = int(model.body_geomadr[i])
        out[n] = {"type": kinds.get(int(model.geom_type[g]), "box"), "size": [round(float(v), 5) for v in model.geom_size[g]],
                  "rgba": [round(float(v), 3) for v in model.geom_rgba[g]], "pos": [round(float(v), 5) for v in model.geom_pos[g]]}
    return out


def ctrl_at(model, sched: list, t: float):
    """조종 값 시간표 [[초, {"작동기 이름": 값}], …] → 그 시각의 ctrl(작동기마다 앞뒤 키 사이 직선)"""
    import mujoco
    import numpy as np
    u = np.zeros(model.nu)
    for a in range(model.nu):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a)
        ks = [(float(tt), float(v[name])) for tt, v in sched if name in v]
        if not ks:
            continue
        ks.sort()
        if t <= ks[0][0]:
            u[a] = ks[0][1]
        elif t >= ks[-1][0]:
            u[a] = ks[-1][1]
        else:
            for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
                if t0 <= t <= t1:
                    u[a] = v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
                    break
    return u


def simulate(xml_path: Path, sec: float = 4.0, fps: int = 30, args: dict | None = None, ctrl: list | None = None,
             goals: list | None = None, visual: Path | None = None, plan_opts: dict | None = None,
             poses: list | None = None, expect: list | None = None) -> dict:
    """ctrl: 조종 값 시간표(손가락 굽히기 · 근육 켜기) · goals: 목표(계획기가 조종 값을 찾는다 — plan()) · visual: 모양(메시) 내보낼 .visual.json"""
    import mujoco
    model = load(xml_path, args)
    data = mujoco.MjData(model)
    if model.nkey:                                   # <keyframe> 가 있으면 첫 상태(처음 속도 · 자세)로 시작
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    planned = plan(model, data, goals, sec, **(plan_opts or {})) if goals else None
    posed = pose_ctrl(model, poses) if poses else None
    record, report = check_contacts(model, data, expect) if (model.nu and (poses or goals or ctrl or expect)) else (None, None)
    if record:
        record(data, initial=True)
    per = max(1, round(1.0 / (fps * model.opt.timestep)))
    names = {i: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, model.nbody)}
    names = {i: (n or f"body{i}") for i, n in names.items()}   # 이름 없는 body 도(모양 내보내기와 같은 이름)
    out = {n: [] for n in names.values()}
    frames = int(round(sec * fps)) + 1
    for f in range(frames):
        for i, n in names.items():
            p, q = data.xpos[i], data.xquat[i]
            out[n].append([round(float(v), 5) for v in (*p, *q)])
        for _ in range(per):
            if posed is not None:
                data.ctrl[:] = posed(data.time)
            elif planned is not None:
                data.ctrl[:] = planned(data.time)
            elif ctrl:
                data.ctrl[:] = ctrl_at(model, ctrl, data.time)
            mujoco.mj_step(model, data)
            if data.warning[mujoco.mjtWarning.mjWARN_BADQACC].number:
                # MuJoCo 는 발산하면 경고만 남기고 처음으로 되돌린다 — 손이 계속 처음 자세로 돌아가는데 결과는 '정상'처럼 보였다(2026-11-10 MyoHand)
                raise RuntimeError(f"물리 계산이 {data.time:.3f}초 근처에서 발산했습니다 — 적분기를 implicitfast 로, 작동기 kp · kv 를 낮추거나 timestep 을 줄인다")
            if record:
                record(data)
    res = {"fps": fps, "sec": sec, "timestep": model.opt.timestep, "bodies": out, "shapes": shapes(model)}
    if planned is not None:
        res["motion"] = motion_report(res, planned.info)
    if report:
        res["contacts"] = report()
    if posed is not None:
        res["ik_err"] = posed.info["ik_err"]
    for w in (res.get("motion") or {}).get("warn", []) + (res.get("contacts") or {}).get("warn", []):
        print(f"[물리] △ {w}", flush=True)
    if visual:
        res["visual"] = str(export_visual(model, Path(visual)))
    return res


def export_visual(model, out: Path) -> Path:
    """보이는 모양(geom)을 Blender 가 다시 지을 수 있게 — body · 모양 종류 · 크기 · body 안 자리 · 색, 메시는 정점 · 면 그대로(.visual.json).
    충돌용 geom(group 3)이 따로 있는 모델(menagerie)은 보이는 것(group 0~2)만"""
    import mujoco
    kinds = {int(mujoco.mjtGeom.mjGEOM_BOX): "box", int(mujoco.mjtGeom.mjGEOM_SPHERE): "sphere", int(mujoco.mjtGeom.mjGEOM_CAPSULE): "capsule",
             int(mujoco.mjtGeom.mjGEOM_CYLINDER): "cylinder", int(mujoco.mjtGeom.mjGEOM_ELLIPSOID): "ellipsoid", int(mujoco.mjtGeom.mjGEOM_MESH): "mesh",
             int(mujoco.mjtGeom.mjGEOM_PLANE): "plane"}
    vis_groups = {0, 1, 2} if any(int(g) == 3 for g in model.geom_group) else {0, 1, 2, 3, 4, 5}
    meta, meshes = [], {}
    for g in range(model.ngeom):
        b = int(model.geom_bodyid[g])
        if int(model.geom_group[g]) not in vis_groups or float(model.geom_rgba[g][3]) == 0:
            continue
        kind = kinds.get(int(model.geom_type[g]))
        if not kind or kind == "plane":
            continue
        mat = int(model.geom_matid[g])
        rgba = model.mat_rgba[mat] if mat >= 0 else model.geom_rgba[g]
        e = {"body": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or f"body{b}", "type": kind,
             "size": [round(float(v), 6) for v in model.geom_size[g]], "pos": [round(float(v), 6) for v in model.geom_pos[g]],
             "quat": [round(float(v), 6) for v in model.geom_quat[g]], "rgba": [round(float(v), 4) for v in rgba]}
        if kind == "mesh":
            m = int(model.geom_dataid[g])
            va, vn, fa, fn = int(model.mesh_vertadr[m]), int(model.mesh_vertnum[m]), int(model.mesh_faceadr[m]), int(model.mesh_facenum[m])
            key = f"m{m}"
            if key not in meshes:
                meshes[key] = {"v": [[round(float(c), 6) for c in v] for v in model.mesh_vert[va:va + vn]],
                               "f": [[int(c) for c in f] for f in model.mesh_face[fa:fa + fn]]}
            e["mesh"] = key
        meta.append(e)
    out = Path(out).with_suffix(".json") if Path(out).suffix != ".json" else Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"geoms": meta, "meshes": meshes}, separators=(",", ":")), "utf-8")   # JSON — Blender 안(샌드박스)에서 numpy 없이 읽는다
    return out


def plan(model, data, goals: list, sec: float, horizon: float = 0.5, samples: int = 32, every: float = 0.05, noise: float = 0.3,
         w_ctrl: float = 0.002, w_pose: float = 0.02, w_vel: float = 0.0005, w_smooth: float = 0.5, seed: int = 0):
    """목표를 주면 조종 값을 찾는다 — DeepMind mujoco_mpc 의 Predictive Sampling(예측 표본 추출)을 파이썬으로:
    지금 계획(조종 값 몇 점) + 흔든 계획 N개를 horizon 초 앞까지 굴려 보고 비용이 가장 낮은 것을 고른다 → every 초마다 다시.
    goals: [{"t": 초부터, "body": "이름" | "site": "점 이름", "to": [x, y, z], "w": 1}]  — 그 물체 · 점을 그 자리로(손끝 · 공 · 몸통)
           [{"t": 0, "body": "torso", "move": [1, 0, 0], "w": 1}]   — 그 방향으로 나아가기(걷기 · 기어가기)
           [{"t": 0, "body": "torso", "height": 1.2}]               — 그 높이 유지(일어서기)
           [{"t": 0, "body": "torso", "upright": 1, "w": 2}]        — 위가 하늘을 보게(뒤집혀 구르며 가지 않게)
    목표 말고도 늘 드는 비용(2026-11-10: 쓰지 않는 손가락이 3초에 47cm 꿈틀 · 손끝 떨림 · Ant 가 55% 뒤집힌 채 '전진'):
      w_pose   목표와 상관없는 관절(다른 손가락 · 다리)은 처음 자세에서 멀어질수록 — 목표 물체로 가는 사슬(손끝 → 손목)은 빼고
      w_vel    그 관절들이 빨리 움직일수록(꿈틀거림)
      w_smooth 조종 값이 바로 전 값에서 튀거나 계획 안에서 급히 바뀔수록(0.05초마다 다시 계획할 때 이어지게)
    돌려주는 것: 시각 → ctrl 함수(simulate 가 매 단계 부른다) · .info 에 검사용 목록(쉬어야 할 body · 목표 body · 똑바로 설 body)"""
    import mujoco
    import numpy as np
    rng = np.random.default_rng(seed)
    nu = model.nu
    if nu == 0:
        raise RuntimeError("작동기(actuator)가 없는 장면이라 계획할 조종 값이 없습니다")
    lo = np.where(model.actuator_ctrllimited, model.actuator_ctrlrange[:, 0], -1.0)
    hi = np.where(model.actuator_ctrllimited, model.actuator_ctrlrange[:, 1], 1.0)
    span = hi - lo
    # 쉬는 값: 근육(myo_sim 손 등)은 0(꺼짐) · 모터 · 위치 작동기는 가운데
    rest = np.where(model.actuator_dyntype == int(mujoco.mjtDyn.mjDYN_MUSCLE), lo, (lo + hi) / 2)
    K = 3                                                    # 계획 = 조종 값 점 3개(그 사이 직선)
    knots = np.tile(rest, (K, 1))
    # 목표 대상: body(물체 중심) 또는 site(손끝 · 모서리처럼 모델에 찍힌 점 — 예: MyoHand IFtip_r)
    for g in goals:
        g["_key"] = ("site", g["site"]) if g.get("site") else ("body", g["body"])
    ids, gbody = {}, set()
    for g in goals:
        kind, n = g["_key"]
        i = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE if kind == "site" else mujoco.mjtObj.mjOBJ_BODY, n)
        if i < 0:
            raise RuntimeError(f"목표의 {kind} '{n}' 가 장면에 없습니다")
        ids[g["_key"]] = i
        gbody.add(int(model.site_bodyid[i]) if kind == "site" else i)
    # 목표 사슬(목표 body 와 그 조상 — 손끝 → 손가락 마디 → 손바닥 → 손목)과 같은 나무(root)의 나머지 관절 = 쉬어야 할 관절
    chain = set()
    for b in gbody:
        while b > 0:
            chain.add(b)
            b = int(model.body_parentid[b])
    roots = {int(model.body_rootid[b]) for b in gbody}
    rj = [j for j in range(model.njnt) if int(model.jnt_type[j]) in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))
          and int(model.body_rootid[model.jnt_bodyid[j]]) in roots]
    idle_j = [j for j in rj if int(model.jnt_bodyid[j]) not in chain]
    qa = np.array([int(model.jnt_qposadr[j]) for j in idle_j], dtype=int)
    da = np.array([int(model.jnt_dofadr[j]) for j in rj], dtype=int)
    q0 = data.qpos[qa].copy() if len(qa) else np.zeros(0)
    jr = np.array([max(1e-3, float(model.jnt_range[j][1] - model.jnt_range[j][0])) if model.jnt_limited[j] else 1.0 for j in idle_j])

    def pos_of(d, key):
        return d.site_xpos[ids[key]] if key[0] == "site" else d.xpos[ids[key]]
    sim = mujoco.MjData(model)
    steps = max(1, int(horizon / model.opt.timestep))
    kinds = ("to", "move", "height", "upright")

    def active(t):
        cur = {}
        for g in sorted(goals, key=lambda g: g.get("t", 0)):
            if g.get("t", 0) <= t + 1e-9:
                cur[(g["_key"], next(k for k in kinds if k in g))] = g
        return list(cur.values())

    def u_at(kn, s):
        x = min(1.0, max(0.0, s / horizon)) * (K - 1)
        i = min(K - 2, int(x))
        return kn[i] + (kn[i + 1] - kn[i]) * (x - i)

    def cost(kn, t0, u_prev):
        c = w_smooth * (float(np.sum(((kn[0] - u_prev) / span) ** 2)) + 0.5 * float(np.sum((np.diff(kn, axis=0) / span) ** 2)))
        mujoco.mj_copyData(sim, model, data)
        gs = active(t0)
        x0 = {g["_key"]: pos_of(sim, g["_key"]).copy() for g in gs if "move" in g}
        for k in range(steps):
            sim.ctrl[:] = u_at(kn, k * model.opt.timestep)
            mujoco.mj_step(model, sim)
            if k % 10 == 9 or k == steps - 1:
                for g in gs:
                    p = pos_of(sim, g["_key"])
                    w = float(g.get("w", 1.0))
                    if "to" in g:
                        c += w * float(np.sum((p - np.asarray(g["to"])) ** 2))
                    elif "height" in g:
                        c += w * (float(p[2]) - float(g["height"])) ** 2
                    elif "upright" in g:
                        c += w * (1.0 - float(sim.xmat[ids[g["_key"]]][8])) if g["_key"][0] == "body" else 0.0
                    else:
                        c -= w * float(np.dot(p - x0[g["_key"]], np.asarray(g["move"], dtype=float)))
                c += w_ctrl * float(np.sum(((sim.ctrl - rest) / span) ** 2))
                if len(qa):
                    c += w_pose * float(np.sum(((sim.qpos[qa] - q0) / jr) ** 2))
                if len(da):
                    c += w_vel * float(np.sum(sim.qvel[da] ** 2))
        return c

    table = []                                               # (시각, 그때 고른 계획)
    t = 0.0
    u_prev = rest.copy()
    # 기본은 끝까지 계획. 목표에 hold(초)를 적으면 마지막 목표 뒤 그만큼만 계획하고 그 뒤는 마지막 조종 값 유지 — 근육 · 위치 작동기처럼
    # 값이 곧 자세인 모델(손)에서 계획 시간을 줄인다. 힘(모터) 작동기는 값을 유지하면 계속 밀리니 hold 를 쓰지 않는다
    holds = [float(g["hold"]) for g in goals if "hold" in g]
    until = min(sec, max(float(g.get("t", 0)) for g in goals) + max(holds)) if holds else sec
    while t < until + 1e-9:
        best, best_c = knots, cost(knots, t, u_prev)
        for _ in range(samples):
            cand = np.clip(knots + rng.normal(0, noise, knots.shape) * span, lo, hi)
            c = cost(cand, t, u_prev)
            if c < best_c:
                best, best_c = cand, c
        knots = best
        table.append((t, knots.copy()))
        # 실제 상태도 every 초만큼 앞으로(이 계획으로) — 다음 계획은 거기서
        n_adv = max(1, int(every / model.opt.timestep))
        for k in range(n_adv):
            data.ctrl[:] = u_at(knots, k * model.opt.timestep)
            mujoco.mj_step(model, data)
        u_prev = data.ctrl.copy()
        t += every
        knots = np.vstack([u_at(knots, every + i * horizon / (K - 1)) for i in range(K)])   # 계획을 every 초 앞으로 밀어 다음 출발점으로
    # 계획을 찾느라 굴린 실제 상태를 처음으로 되돌린다(simulate 가 처음부터 다시 굴리며 같은 조종 값을 쓴다)
    mujoco.mj_resetData(model, data)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)

    def at(time):
        i = min(len(table) - 1, max(0, int(time / every + 1e-9)))
        t0, kn = table[i]
        return u_at(kn, time - t0)
    name = lambda b: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or f"body{b}"  # noqa: E731
    idle_b = sorted({int(model.jnt_bodyid[j]) for j in idle_j})
    leaves = [b for b in idle_b if not any(int(model.body_parentid[c]) == b for c in idle_b)]   # 쉬어야 할 사슬의 끝(다른 손가락 끝)
    at.info = {"idle": [name(b) for b in leaves], "goal": [name(b) for b in gbody],
               "upright": [g["body"] for g in goals if "upright" in g and g.get("body")]}
    return at


def motion_report(res: dict, info: dict | None = None) -> dict:
    """움직임이 어색한지 숫자로 — 계획(goals) 장면의 결과에 붙는다(simulate · gym_run). 2026-11-10: 숫자(도미노가 넘어졌나)만 보고 '됐다'고 했다가
    쓰지 않는 손가락이 꿈틀 · 손끝이 떨림 · Ant 가 뒤집혀 구른 것을 놓쳤다.
      idle_cm_s   쉬어야 할 사슬 끝(다른 손가락 끝)이 초당 움직인 거리(cm) — 큰 값 = 꿈틀
      jitter      목표 물체의 가속 방향이 바뀐 비율(축마다 프레임당) — 큰 값 = 덜덜 떨림
      flipped     똑바로 서야 할 몸이 뒤집힌 프레임 비율"""
    import math
    info = info or {}
    fps, B = res["fps"], res["bodies"]
    sec = max(1e-6, (len(next(iter(B.values()))) - 1) / fps)

    def travel(n):
        r = B[n]
        return sum(math.dist(r[i][:3], r[i + 1][:3]) for i in range(len(r) - 1))

    def flips(n):
        r = [row[:3] for row in B[n]]
        acc = [[r[i + 2][k] - 2 * r[i + 1][k] + r[i][k] for k in range(3)] for i in range(len(r) - 2)]
        ch = sum(1 for i in range(len(acc) - 1) for k in range(3) if abs(acc[i][k]) > 1e-6 and abs(acc[i + 1][k]) > 1e-6 and (acc[i][k] > 0) != (acc[i + 1][k] > 0))
        return ch / max(1, 3 * (len(acc) - 1))

    def up(n):
        bad = 0
        for row in B[n]:
            _, _, _, w, x, y, _z = row
            bad += (1 - 2 * (x * x + y * y)) < 0
        return bad / len(B[n])
    rep = {"idle_cm_s": round(max([travel(n) for n in info.get("idle", []) if n in B] or [0]) * 100 / sec, 1),
           "jitter": round(max([flips(n) for n in info.get("goal", []) if n in B] or [0]), 2),
           "flipped": round(max([up(n) for n in info.get("upright", []) if n in B] or [0]), 2)}
    warn = []
    if rep["idle_cm_s"] > 6:
        warn.append(f"쓰지 않는 부분이 꿈틀댐(초당 {rep['idle_cm_s']}cm) — w_pose · w_vel 을 올리거나 목표 시각을 늦춘다")
    if rep["jitter"] > 0.35:
        warn.append(f"목표 물체가 떨림(가속 방향 바뀜 {rep['jitter']}) — w_smooth 를 올린다")
    if rep["flipped"] > 0.1:
        warn.append(f"몸이 뒤집힌 프레임 {int(rep['flipped'] * 100)}% — upright 목표를 넣거나 무게를 올린다")
    rep["warn"] = warn
    return rep


def actor_dofs(model) -> list[int]:
    """작동기가 움직이는 나무(손 · 팔 · 몸)의 자유도 — 관절 · 힘줄로 잇는 관절을 따라 그 나무(root) 전체. 나머지(도미노 · 버튼)는 물체"""
    import mujoco
    js = set()
    for a in range(model.nu):
        if int(model.actuator_trntype[a]) == int(mujoco.mjtTrn.mjTRN_JOINT):
            js.add(int(model.actuator_trnid[a][0]))
        elif int(model.actuator_trntype[a]) == int(mujoco.mjtTrn.mjTRN_TENDON):
            t = int(model.actuator_trnid[a][0])
            for w in range(int(model.tendon_adr[t]), int(model.tendon_adr[t]) + int(model.tendon_num[t])):
                if int(model.wrap_type[w]) == int(mujoco.mjtWrap.mjWRAP_JOINT):
                    js.add(int(model.wrap_objid[w]))
    roots = {int(model.body_rootid[model.jnt_bodyid[j]]) for j in js}
    dofs = []
    for j in range(model.njnt):
        if int(model.body_rootid[model.jnt_bodyid[j]]) in roots:
            n = {int(mujoco.mjtJoint.mjJNT_FREE): 6, int(mujoco.mjtJoint.mjJNT_BALL): 3}.get(int(model.jnt_type[j]), 1)
            dofs += list(range(int(model.jnt_dofadr[j]), int(model.jnt_dofadr[j]) + n))
    return dofs


def ik(model, q, targets: list, iters: int = 400) -> tuple:
    """mink(역기구학)로 손끝 · 몸 점을 그 자리에 놓는 관절 값 → (q, 남은 오차 m). 작동기 나무 밖(도미노 등)은 얼린다 · 나머지 관절은 지금 자세에 묶어 둔다"""
    import mink
    import numpy as np
    cfg = mink.Configuration(model, q.copy())
    frames = []
    for tg in targets:
        ft = mink.FrameTask(tg.get("site") or tg["body"], "site" if tg.get("site") else "body", position_cost=1.0, orientation_cost=0.0)
        ft.set_target(mink.SE3.from_translation(np.asarray(tg["to"], dtype=float)))
        frames.append(ft)
    post = mink.PostureTask(model, cost=float(targets[0].get("keep", 0.02)) if targets else 0.02)
    post.set_target(q.copy())
    act = set(actor_dofs(model))
    freeze = [d for d in range(model.nv) if d not in act]
    cons = [mink.DofFreezingTask(model, dof_indices=freeze)] if freeze else []
    lim = [mink.ConfigurationLimit(model)]
    err = 1.0
    for _ in range(iters):
        v = mink.solve_ik(cfg, [*frames, post], 0.02, "daqp", 1e-3, limits=lim, constraints=cons)
        cfg.integrate_inplace(v, 0.02)
        err = max(float(np.linalg.norm(f.compute_error(cfg)[:3])) for f in frames) if frames else 0.0
        if err < 2e-4:
            break
    return cfg.q.copy(), err


def pose_ctrl(model, poses: list):
    """동작 = 사람이 정하는 자세 키(애니메이터처럼) → 위치 작동기의 목표값. 물리는 닿았을 때의 반응만 계산한다(2026-11-10: 무작위 계획기로
    관절 값을 찾게 했더니 손끝이 떨고 다른 손가락이 꿈틀대고 손등이 버튼을 눌렀다 — 위치 제어 손은 '목표 각도'를 주는 게 본래 쓰임).
    poses: [{"t": 0}                                       — 처음 자세(모델 기본 · keyframe)
            {"t": 0.4, "ik": [{"site" | "body": "손끝", "to": [x, y, z]}]}   — 그 점이 그 자리에 오는 자세(mink)
            {"t": 0.6, "joints": {"관절 이름 또는 패턴(*FFJ*)": 각도}}
            {"t": 1.0, "back": 0}]                          — n 번째 키 자세로 돌아가기
    키 사이는 최소 저크 곡선(사람 손 움직임처럼 천천히 출발 · 천천히 멈춤). 돌려주는 것: 시각 → ctrl 함수(.info: 키마다 IK 오차)"""
    import fnmatch
    import mujoco
    import numpy as np
    d = mujoco.MjData(model)
    if model.nkey:
        mujoco.mj_resetDataKeyframe(model, d, 0)
    mujoco.mj_forward(model, d)
    q = d.qpos.copy()
    lo = np.where(model.actuator_ctrllimited, model.actuator_ctrlrange[:, 0], -np.inf)
    hi = np.where(model.actuator_ctrllimited, model.actuator_ctrlrange[:, 1], np.inf)
    is_pos = np.array([int(model.actuator_biastype[a]) == int(mujoco.mjtBias.mjBIAS_AFFINE) and float(model.actuator_biasprm[a][1]) < 0 for a in range(model.nu)])
    if not is_pos.any():
        raise RuntimeError("위치 작동기(목표 각도를 받는 작동기)가 없습니다 — 근육 모델은 position_drive(spec) 로 바꿔 쓴다")
    keys, errs = [], []
    for p in sorted(poses, key=lambda p: float(p.get("t", 0))):
        if "back" in p:
            q = keys[int(p["back"])][1].copy()
        if p.get("joints"):
            for j in range(model.njnt):
                n = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or ""
                v = next((val for pat, val in p["joints"].items() if fnmatch.fnmatchcase(n, pat) or n.endswith("/" + pat)), None)
                if v is not None:
                    q[int(model.jnt_qposadr[j])] = float(v)
        if p.get("ik"):
            q, e = ik(model, q, p["ik"])
            errs.append(round(e, 4))
            if e > 0.005:
                print(f"[물리] △ {p.get('t')}초 자세: 손끝이 목표에 {e * 1000:.0f}mm 못 미침(닿지 않는 자리) — 물체를 손 쪽으로 옮긴다", flush=True)
        keys.append((float(p.get("t", 0)), q.copy(), p))

    # ---- 애니메이션 원칙으로 키 사이를 짓는다(애니메이터가 곡선 편집기에서 하는 일) ----
    # ease: 속도 곡선(Blender 베지어처럼) · anticipate: 반대로 살짝 뒤로 갔다가 · overshoot: 지나쳤다 돌아와 멈춤(여운)
    # arc: 손끝 · 몸 점이 직선이 아니라 호로(그 점을 IK 로 따라가며) · overlap: 뿌리 관절이 먼저, 끝 관절이 늦게(시차)
    EASE = {"linear": (0.0, 0.0, 1.0, 1.0), "in": (0.42, 0.0, 1.0, 1.0), "out": (0.0, 0.0, 0.58, 1.0), "inout": (0.42, 0.0, 0.58, 1.0),
            "snap": (0.7, 0.0, 0.15, 1.0), "soft": (0.25, 0.1, 0.25, 1.0)}

    def bez(x, c):                                       # CSS · Blender 와 같은 3차 베지어 시간 곡선
        x1, y1, x2, y2 = c
        lo_, hi_ = 0.0, 1.0
        for _ in range(30):
            m = (lo_ + hi_) / 2
            bx = 3 * (1 - m) ** 2 * m * x1 + 3 * (1 - m) * m * m * x2 + m ** 3
            lo_, hi_ = (m, hi_) if bx < x else (lo_, m)
        m = (lo_ + hi_) / 2
        return 3 * (1 - m) ** 2 * m * y1 + 3 * (1 - m) * m * m * y2 + m ** 3

    def shape(x, opt):                                   # 구간 진행 0~1 → 자세 섞음 비율(0 밑 · 1 위로도 간다)
        e = opt.get("ease", "inout")
        sv = bez(x, EASE.get(e, EASE["inout"])) if isinstance(e, str) else bez(x, tuple(e))
        a = float(opt.get("anticipate", 0))
        if a and x < 0.3:
            sv -= a * np.sin(np.pi * x / 0.3)
        o = float(opt.get("overshoot", 0))
        if o and x > 0.55:
            sv += o * np.sin(np.pi * (x - 0.55) / 0.45)
        return sv

    act = actor_dofs(model)
    act_j = [j for j in range(model.njnt) if int(model.jnt_dofadr[j]) in act and int(model.jnt_type[j]) in (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))]
    depth = {}
    for j in act_j:                                      # 관절의 깊이(뿌리에서 몇 번째 관절인가) — 시차에 쓴다
        b, n = int(model.jnt_bodyid[j]), 0
        while b > 0:
            n += sum(1 for k in act_j if int(model.jnt_bodyid[k]) == b)
            b = int(model.body_parentid[b])
        depth[j] = n
    dmax = max(depth.values() or [1])
    path_cache = {}

    def arc_samples(k):                                   # 이 구간 손끝을 호로 — 베지어 점 9개를 IK 로 풀어 관절 자세 줄을 만든다
        if k in path_cache:
            return path_cache[k]
        _, q0, _ = keys[k]
        _, q1, opt = keys[k + 1]
        tg = opt["ik"]
        dd = mujoco.MjData(model)
        dd.qpos[:] = q0
        mujoco.mj_forward(model, dd)
        out = []
        h = opt.get("arc")
        lift = np.array(h, dtype=float) if isinstance(h, (list, tuple)) else np.array([0, 0, float(h)])
        for i in range(9):
            sx = i / 8
            pts = []
            for g in tg:
                key = ("site", g["site"]) if g.get("site") else ("body", g["body"])
                idx = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE if key[0] == "site" else mujoco.mjtObj.mjOBJ_BODY, key[1])
                p0 = (dd.site_xpos[idx] if key[0] == "site" else dd.xpos[idx]).copy()
                p1 = np.asarray(g["to"], dtype=float)
                mid = (p0 + p1) / 2 + lift
                pts.append({**g, "to": list((1 - sx) ** 2 * p0 + 2 * (1 - sx) * sx * mid + sx * sx * p1)})
            qs, _ = ik(model, out[-1] if out else q0, pts, iters=150)
            out.append(qs)
        path_cache[k] = out
        return out

    def q_at(time):
        if time <= keys[0][0]:
            return keys[0][1]
        if time >= keys[-1][0]:
            return keys[-1][1]
        k = max(i for i in range(len(keys)) if keys[i][0] <= time)
        t0, q0, _ = keys[k]
        t1, q1, opt = keys[k + 1]
        sv = shape((time - t0) / max(1e-9, t1 - t0), opt)
        if opt.get("arc") and opt.get("ik"):
            smp = arc_samples(k)
            f = min(max(sv, 0.0), 1.0) * 8
            i = min(7, int(f))
            qa = smp[i] + (smp[i + 1] - smp[i]) * (f - i)
            if sv < 0:                                     # 예비 동작: 처음 방향의 반대로
                qa = q0 + (smp[1] - q0) * sv * 8
            elif sv > 1:                                   # 지나침: 마지막 방향으로 더
                qa = q1 + (smp[8] - smp[7]) * (sv - 1) * 8
            return qa
        return q0 + (q1 - q0) * sv

    lag = max([float(p.get("overlap", 0)) for _, _, p in keys] + [0.0])
    dt_tab = 1.0 / 200
    t_end = keys[-1][0] + lag + 0.2
    times = np.arange(0.0, t_end + dt_tab, dt_tab)
    qtab = np.array([q_at(t) for t in times])
    if lag > 0 and act_j:                                 # 시차: 끝 관절일수록 늦게 따라온다(같은 곡선을 늦춰 읽는다)
        for j in act_j:
            a_ = int(model.jnt_qposadr[j])
            delay = lag * depth[j] / max(1, dmax)
            qtab[:, a_] = np.interp(times - delay, times, qtab[:, a_])
    utab = []
    for qq in qtab:
        d.qpos[:] = qq
        mujoco.mj_kinematics(model, d)
        mujoco.mj_comPos(model, d)
        mujoco.mj_tendon(model, d)
        mujoco.mj_transmission(model, d)
        utab.append(np.clip(d.actuator_length.copy(), lo, hi))
    utab = np.array(utab)
    rest = np.zeros(model.nu)

    def at(time):
        i = min(len(times) - 1, max(0, int(time / dt_tab)))
        j = min(len(times) - 1, i + 1)
        f = min(1.0, max(0.0, time / dt_tab - i))
        return np.where(is_pos, utab[i] + (utab[j] - utab[i]) * f, rest)
    at.info = {"ik_err": errs}
    return at


def retime(res: dict, ramps: list) -> dict:
    """속도 연출 — 부딪히는 순간은 느리게, 나머지는 그대로(또는 빠르게). ramps: [{"from": 1.0, "to": 1.4, "speed": 0.3}, …]
    speed 0.3 = 그 구간을 0.3배속(약 3.3배 길게). 결과는 같은 fps 의 새 프레임 줄(영상 길이가 바뀐다 — 콘티 sec 도 맞춘다)"""
    import numpy as np
    fps = res["fps"]
    n = len(next(iter(res["bodies"].values())))
    sim_t = np.arange(n) / fps

    def speed(t):
        for r in ramps:
            a, b, sp = float(r["from"]), float(r["to"]), float(r["speed"])
            edge = min(0.12, (b - a) / 4)               # 속도가 갑자기 바뀌지 않게 가장자리를 부드럽게
            if a - edge <= t <= b + edge:
                if t < a:
                    return 1 + (sp - 1) * (t - (a - edge)) / edge
                if t > b:
                    return sp + (1 - sp) * (t - b) / edge
                return sp
        return 1.0
    out_t, t = [], 0.0
    while t <= sim_t[-1] + 1e-9:
        out_t.append(t)
        t += speed(t) / fps
    bodies = {}
    for name, rows in res["bodies"].items():
        arr = np.array(rows, dtype=float)
        cols = [np.interp(out_t, sim_t, arr[:, k]) for k in range(arr.shape[1])]
        new = np.stack(cols, axis=1)
        q = new[:, 3:7]
        q /= np.linalg.norm(q, axis=1, keepdims=True)       # 사원수는 다시 길이 1로(짧은 보간이라 충분)
        bodies[name] = [[round(float(v), 5) for v in row] for row in new]
    return {**res, "bodies": bodies, "sec": round(len(out_t) / fps, 3), "retime": ramps}


def position_drive(spec, kp: float = 5.0, kv: float = 0.3, prefix: str = ""):
    """근육 모델(MyoHand 등)의 근육을 떼고 관절마다 위치 작동기를 단다 — 영상에서는 '자세를 정하면 그대로' 움직이는 쪽이 맞다
    (근육 39개로 동작을 찾는 건 연구 과제). 장면 .py 의 scene() 안에서: spec = myo_sim.load_spec(...); physics.position_drive(spec)"""
    import mujoco
    # 가벼운 손가락 뼈 + 위치 작동기 감쇠(kv)는 기본 적분기(Euler)에서 0.002초 만에 발산한다 → 암시적 적분(implicitfast)
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    for a in list(spec.actuators):
        spec.delete(a)
    for t in list(spec.tendons):
        spec.delete(t)
    for j in spec.joints:
        if j.type in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE) and (not prefix or j.name.startswith(prefix)):
            a = spec.add_actuator(name=f"pos_{j.name}", target=j.name, trntype=mujoco.mjtTrn.mjTRN_JOINT)
            a.set_to_position(kp=kp, kv=kv)
            if j.range[1] > j.range[0]:
                a.ctrlrange = [j.range[0], j.range[1]]
                a.ctrllimited = mujoco.mjtLimited.mjLIMITED_TRUE
    return spec


def check_contacts(model, data, expect: list | None = None) -> dict:
    """시작 겹침 · 누가 무엇에 닿았나 · 파고든 깊이 — simulate 가 매 단계 부르는 기록기(record) + 끝난 뒤 판정(report)"""
    import mujoco
    act = set(actor_dofs(model))
    actor_bodies = {int(model.dof_bodyid[dd]) for dd in act}
    actor_roots = {int(model.body_rootid[b]) for b in actor_bodies}
    name = lambda b: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or f"body{b}"  # noqa: E731
    st = {"first": {}, "deep": 0.0, "deep_pair": None, "start": []}

    def record(d, initial=False):
        for c in d.contact[:d.ncon]:
            b1, b2 = int(model.geom_bodyid[c.geom1]), int(model.geom_bodyid[c.geom2])
            r1, r2 = int(model.body_rootid[b1]), int(model.body_rootid[b2])
            if r1 == r2:
                continue
            a1, a2 = r1 in actor_roots, r2 in actor_roots
            if initial and (a1 or a2) and not (a1 and a2) and c.dist < -0.001:
                st["start"].append((name(b1), name(b2), round(-c.dist * 1000, 1)))
            if a1 != a2 and r1 != 0 and r2 != 0:      # 작동하는 손 ↔ 물체(바닥 제외)
                hand, obj = (b1, b2) if a1 else (b2, b1)
                st["first"].setdefault(name(obj), (round(float(d.time), 3), name(hand)))
            if (a1 or a2) and -c.dist > st["deep"]:
                st["deep"], st["deep_pair"] = -c.dist, (name(b1), name(b2))

    def report():
        warn = []
        if st["start"]:
            warn.append("시작부터 겹침: " + ", ".join(f"{a}↔{b} {mm}mm" for a, b, mm in st["start"][:4]) + " — 물체를 떼어 놓는다(겹친 채 시작하면 튕겨 나간다)")
        if st["deep"] > 0.003:
            warn.append(f"파고듦 {st['deep'] * 1000:.1f}mm({' ↔ '.join(st['deep_pair'])}) — 접촉을 단단하게(solref 0.005 · 모델과 같게) · 물체 질량을 현실에 맞게")
        for e in expect or []:
            got = st["first"].get(e["touch"])
            if not got:
                warn.append(f"{e['touch']} 에 손이 닿지 않음 — 기대: {e['by']}")
            elif not got[1].endswith(e["by"]):
                warn.append(f"{e['touch']} 에 먼저 닿은 건 {got[1]}({got[0]}초) — 기대: {e['by']}")
        return {"first_touch": st["first"], "deep_mm": round(st["deep"] * 1000, 1), "start_overlap": st["start"], "warn": warn}
    return record, report


def load_policy(path: Path):
    """stable-baselines3 정책(policy.pth)을 torch 없이 읽는다 — 텐서 다시 짓기만 허락하는 제한 unpickler(다른 코드는 실행하지 않음).
    SAC(actor.latent_pi · actor.mu) · PPO(mlp_extractor.policy_net · action_net) → 관측 → 행동 함수(결정적, tanh 로 [-1, 1])"""
    import collections
    import pickle
    import zipfile
    import numpy as np
    z = zipfile.ZipFile(path)
    base = z.namelist()[0].split("/")[0]
    DT = {"FloatStorage": np.float32, "DoubleStorage": np.float64, "LongStorage": np.int64, "IntStorage": np.int32, "HalfStorage": np.float16}

    class St:
        def __init__(self, dt, key):
            self.dt, self.key = dt, key

    def rebuild(storage, offset, size, stride, *_):
        raw = np.frombuffer(z.read(f"{base}/data/{storage.key}"), dtype=storage.dt)
        if not size:
            return raw[offset:offset + 1].reshape(())
        span = max((sz - 1) * st for sz, st in zip(size, stride)) + 1
        arr = raw[offset:offset + span]
        return np.lib.stride_tricks.as_strided(arr, shape=tuple(size), strides=tuple(st * arr.itemsize for st in stride)).copy()

    class U(pickle.Unpickler):
        def find_class(self, mod, name):
            if (mod, name) == ("torch._utils", "_rebuild_tensor_v2"):
                return rebuild
            if (mod, name) == ("collections", "OrderedDict"):
                return collections.OrderedDict
            if mod == "torch" and name in DT:
                return name
            raise pickle.UnpicklingError(f"허용하지 않는 객체: {mod}.{name}")

        def persistent_load(self, pid):
            return St(DT[pid[1]], pid[2])
    sd = U(z.open(f"{base}/data.pkl")).load()
    if "actor.mu.weight" in sd:
        layers = [(sd[f"actor.latent_pi.{i}.weight"], sd[f"actor.latent_pi.{i}.bias"]) for i in range(0, 10, 2) if f"actor.latent_pi.{i}.weight" in sd]
        head = (sd["actor.mu.weight"], sd["actor.mu.bias"])
        squash = True
    else:
        layers = [(sd[f"mlp_extractor.policy_net.{i}.weight"], sd[f"mlp_extractor.policy_net.{i}.bias"]) for i in range(0, 10, 2) if f"mlp_extractor.policy_net.{i}.weight" in sd]
        head = (sd["action_net.weight"], sd["action_net.bias"])
        squash = False

    def act(obs):
        h = np.asarray(obs, dtype=np.float32)
        for w, b in layers:
            h = np.maximum(0, w @ h + b) if squash else np.tanh(w @ h + b)
        a = head[0] @ h + head[1]
        return np.tanh(a) if squash else np.clip(a, -1, 1)
    return act


def policy_fetch(repo: str, checked_license: bool = False) -> Path:
    """Hugging Face 의 학습된 정책(stable-baselines3)에서 policy.pth 만 받는다 — 예: farama-minari/Ant-v5-SAC-expert(학습 단계 simple · medium · expert).
    라이선스가 적혀 있지 않은 저장소가 많다 → --checked-license(사람이 확인했다)일 때만 받는다. 받은 정책은 저장소에 넣지 않는다(data/)"""
    import json as _json
    import urllib.request
    root = Path(__file__).resolve().parents[2]
    dst = root / "data" / "assets" / "policies" / repo.replace("/", "__")
    if (dst / "policy.pth").exists():
        return dst
    meta = _json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}", timeout=30))
    lic = (meta.get("cardData") or {}).get("license")
    if not lic and not checked_license:
        raise RuntimeError(f"{repo}: 라이선스가 적혀 있지 않습니다 — 사람이 확인한 뒤 --checked-license 로 받는다(영상 설명란에 출처를 남긴다)")
    f = next((s["rfilename"] for s in meta.get("siblings", []) if s["rfilename"].endswith("/policy.pth")), None)
    if not f:
        raise RuntimeError(f"{repo}: policy.pth 가 없습니다(stable-baselines3 정책이 아님)")
    dst.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(f"https://huggingface.co/{repo}/resolve/main/{f}", dst / "policy.pth")
    (dst / "CREDIT.txt").write_text(f"{repo} — https://huggingface.co/{repo} — license: {lic or '적혀 있지 않음(사람이 확인)'}\n", "utf-8")
    return dst


def gym_run(env_id: str, sec: float, fps: int, policy: str = "random", goals: list | None = None, visual: Path | None = None, seed: int = 0) -> dict:
    """Gymnasium 의 MuJoCo 환경(Ant · Humanoid · HalfCheetah · Hopper …)을 굴려 같은 결과 꼴로 — 'AI 가 배우기 전(무작위) · 계획한 뒤' 비교 장면용.
    policy: random(무작위 조종) · zero(가만히) · 학습된 정책(policy.pth 경로 · 'hf:farama-minari/Ant-v5-SAC-expert' — 진짜 'AI 가 배운' 걸음)
            · plan(goals 로 계획기 — 학습이 아니다, 'AI 가 배웠다'고 보여 주지 않는다)"""
    import gymnasium as gym
    import mujoco
    import numpy as np
    env = gym.make(env_id)
    env.reset(seed=seed)
    u = env.unwrapped
    model, data = u.model, u.data
    names = {i: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, model.nbody)}
    names = {i: (n or f"body{i}") for i, n in names.items()}   # 이름 없는 body 도(모양 내보내기와 같은 이름)
    out = {n: [] for n in names.values()}
    dt = u.dt
    planned = None
    if policy == "plan":
        snap = mujoco.MjData(model)
        mujoco.mj_copyData(snap, model, data)
        planned = plan(model, data, goals or [{"t": 0, "body": names[1], "move": [1, 0, 0]}], sec)
        mujoco.mj_copyData(data, model, snap)
        mujoco.mj_forward(model, data)
    learned = None
    if policy not in ("random", "zero", "plan"):          # 학습된 정책: policy.pth 경로 · 그 폴더 · 'hf:저장소'(policy_fetch 로 받은 것)
        pp = policy_fetch(policy[3:]) / "policy.pth" if policy.startswith("hf:") else Path(policy)
        learned = load_policy(pp / "policy.pth" if pp.is_dir() else pp)
    obs, _ = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    t = 0.0
    frames = int(round(sec * fps)) + 1
    for f in range(frames):
        for i, n in names.items():
            out[n].append([round(float(v), 5) for v in (*data.xpos[i], *data.xquat[i])])
        while t < (f + 1) / fps - 1e-9:
            if learned:
                act = learned(obs)
            elif planned:
                act = planned(data.time)
            else:
                act = np.zeros(env.action_space.shape) if policy == "zero" else rng.uniform(env.action_space.low, env.action_space.high)
            obs, *_ = env.step(act)
            t += dt
    res = {"fps": fps, "sec": sec, "timestep": model.opt.timestep, "bodies": out, "shapes": shapes(model), "env": env_id, "policy": policy}
    # 학습된 정책 · 무작위는 뒤집힘만 본다(걸음의 출렁임은 떨림이 아니고, w_smooth 같은 계획기 조언은 맞지 않는다)
    res["motion"] = motion_report(res, planned.info if planned else {"upright": [names[1]]})
    for w in res["motion"]["warn"]:
        print(f"[물리] △ {w}", flush=True)
    if visual:
        res["visual"] = str(export_visual(model, Path(visual)))
    env.close()
    return res


SOURCES = {   # 받아 쓸 수 있는 모델 저장소(폴더 하나만 받는다) — 라이선스는 받을 때 확인
    "menagerie": "https://github.com/google-deepmind/mujoco_menagerie.git",
    "myo": "https://github.com/MyoHub/myo_sim.git",
}
OK_LICENSE = ("apache license", "permission is hereby granted", "redistribution and use", "creative commons attribution 4.0", "cc-by-4.0", "bsd")
NO_LICENSE = ("non-commercial", "noncommercial", "research purposes only", "not for commercial")


def fetch(source: str, model: str) -> Path:
    """모델 폴더 하나만 받아 data/assets/mujoco/<source>/<model>/ 에 둔다. 라이선스 글을 읽어 상업 이용이 막힌 것은 받지 않는다 → CREDIT.txt"""
    import shutil
    import subprocess
    import tempfile
    root = Path(__file__).resolve().parents[2]
    if source not in SOURCES:
        raise RuntimeError(f"모르는 출처: {source} ({', '.join(SOURCES)})")
    dst = root / "data" / "assets" / "mujoco" / source / model.strip("/").replace("/", "_")
    if (dst / "CREDIT.txt").exists():
        return dst
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", SOURCES[source], tmp], check=True)
        subprocess.run(["git", "-C", tmp, "sparse-checkout", "set", "--no-cone", f"/{model.strip('/')}/", "/LICENSE"], check=True)
        src = Path(tmp) / model
        if not src.is_dir():
            raise RuntimeError(f"{source} 에 {model} 폴더가 없습니다")
        lic = next((f for f in (src / "LICENSE", src / "LICENSE.txt", Path(tmp) / "LICENSE") if f.is_file()), None)
        text = lic.read_text("utf-8", "ignore").lower() if lic else ""
        if not text or any(k in text for k in NO_LICENSE) or not any(k in text for k in OK_LICENSE):
            raise RuntimeError(f"{source}/{model}: 라이선스가 없거나 상업 이용이 분명하지 않아 받지 않았습니다 — 저장소의 LICENSE 를 직접 확인하세요")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"))
        if lic.parent != src:
            shutil.copy(lic, dst / "LICENSE")
    first = (dst / "LICENSE").read_text("utf-8", "ignore").strip().splitlines()[0][:80] if (dst / "LICENSE").exists() else "?"
    (dst / "CREDIT.txt").write_text(f"{model} — {SOURCES[source].removesuffix('.git')} — {first}\n영상 설명란 · NOTICE 에 이 줄을 남긴다\n", "utf-8")
    return dst


def project2d(res: dict, W: int, H: int, width_m: float = 3.6, x0: float = 0.5, ground: float = 0.74) -> dict:
    """3D 결과 → 화면 평면. 세상 x → 화면 오른쪽, z → 화면 위. width_m: 화면 폭에 들어갈 세상 너비(미터) · x0: 세상 원점의 화면 가로 위치(비율) ·
    ground: 바닥(z=0)의 화면 세로 위치(비율). 회전은 물체의 x 축이 화면에서 기운 각(도, 시계 방향 +) → {"ppm", "bodies": {이름: [[px, py, 도], …]}}"""
    import math
    ppm = W / width_m
    ox, oy = W * x0, H * ground
    out = {}
    for n, rows in res["bodies"].items():
        seq = []
        for x, _y, z, qw, qx, qy, qz in rows:
            r00 = 1 - 2 * (qy * qy + qz * qz)          # 회전 행렬의 첫 열(물체 x 축) 중 x · z
            r20 = 2 * (qx * qz - qw * qy)
            seq.append([round(ox + x * ppm, 1), round(oy - z * ppm, 1), round(math.degrees(math.atan2(-r20, r00)), 2)])
        out[n] = seq
    return {"ppm": ppm, "bodies": out}


def spring_follow(targets: list, fps: int = 30, sec: float | None = None, stiffness: float = 60.0, damping: float = 0.75) -> list:
    """카메라를 목표에 스프링으로 매단다 — targets: [(초, x, y, 확대), …](그 시각부터 그 목표). 결과: 프레임마다 [x, y, 확대].
    stiffness: 단단함(클수록 빨리 붙음, 30~150) · damping: 1 이면 출렁임 없이 멈춤, 0.5 쯤이면 살짝 지나쳤다 돌아옴"""
    import math
    targets = sorted(targets, key=lambda t: t[0])
    sec = sec if sec is not None else targets[-1][0] + 1.5
    w0 = math.sqrt(stiffness)
    sub = 8
    dt = 1.0 / (fps * sub)
    pos = list(targets[0][1:4])
    vel = [0.0, 0.0, 0.0]
    out = []
    for f in range(int(round(sec * fps)) + 1):
        t = f / fps
        out.append([round(pos[0], 2), round(pos[1], 2), round(pos[2], 4)])
        goal = [v for tt, *v in targets if tt <= t + 1e-9][-1] if any(tt <= t + 1e-9 for tt, *_ in targets) else targets[0][1:4]
        for _ in range(sub):
            for k in range(3):
                a = w0 * w0 * (goal[k] - pos[k]) - 2 * damping * w0 * vel[k]
                vel[k] += a * dt
                pos[k] += vel[k] * dt
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "check", "fetch", "gym", "policy"])
    ap.add_argument("scene", help="장면 파일 · fetch 는 <menagerie|myo>/<모델 폴더> · gym 은 환경 이름(Ant-v5)")
    ap.add_argument("--sec", type=float, default=4.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--args", default="{}")
    ap.add_argument("--out")
    ap.add_argument("--ctrl", help="조종 값 시간표 JSON [[초, {작동기: 값}], …]")
    ap.add_argument("--goals", help="목표 JSON [{\"t\", \"body\", \"to\" | \"move\" | \"height\"}] — 계획기가 조종 값을 찾는다")
    ap.add_argument("--policy", default="random", help="gym: random · zero · policy.pth 경로 · hf:<저장소>(학습된 정책) · plan(계획기 — 학습 아님)")
    ap.add_argument("--poses", help="자세 키 JSON [{\"t\": 0}, {\"t\": 0.4, \"ik\": [{\"site\": \"손끝\", \"to\": [x,y,z]}]}, …] — 위치 작동기로 그대로")
    ap.add_argument("--expect", help="닿음 기대 JSON [{\"touch\": \"button\", \"by\": \"distph2_r\"}] — 다른 부위가 먼저 닿으면 경고")
    ap.add_argument("--checked-license", action="store_true", help="policy: 라이선스가 안 적힌 정책을 사람이 확인하고 받는다")
    ap.add_argument("--visual", action="store_true", help="모양(메시)도 내보낸다(.visual.json) — Blender 의 F.mjcf_build")
    a = ap.parse_args()
    args = json.loads(a.args)
    if a.cmd == "fetch":
        src, _, model = a.scene.partition("/")
        d = fetch(src, model)
        print(json.dumps({"ok": True, "dir": str(d), "credit": (d / "CREDIT.txt").read_text("utf-8").splitlines()[0]}, ensure_ascii=False))
        return 0
    if a.cmd == "policy":
        d = policy_fetch(a.scene, a.checked_license)
        print(json.dumps({"ok": True, "dir": str(d), "credit": (d / "CREDIT.txt").read_text("utf-8").strip()}, ensure_ascii=False))
        return 0
    if a.cmd == "gym":
        out = Path(a.out or f"{a.scene}.traj.json")
        res = gym_run(a.scene, a.sec, a.fps, a.policy, json.loads(a.goals) if a.goals else None, out.with_suffix(".visual.json") if a.visual else None)
        out.write_text(json.dumps(res), "utf-8")
        print(json.dumps({"ok": True, "out": str(out), "bodies": len(res["bodies"])}, ensure_ascii=False))
        return 0
    if a.cmd == "check":
        import mujoco
        m = load(Path(a.scene), args)
        names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, m.nbody)]
        print(json.dumps({"ok": True, "bodies": [n for n in names if n], "timestep": m.opt.timestep}, ensure_ascii=False))
        return 0
    out = Path(a.out) if a.out else Path(a.scene).with_suffix(".traj.json")
    res = simulate(Path(a.scene), a.sec, a.fps, args, json.loads(a.ctrl) if a.ctrl else None, json.loads(a.goals) if a.goals else None,
                   out.with_suffix(".visual.json") if a.visual else None, poses=json.loads(a.poses) if a.poses else None,
                   expect=json.loads(a.expect) if a.expect else None)
    out.write_text(json.dumps(res), "utf-8")
    print(json.dumps({"ok": True, "out": str(out), "bodies": len(res["bodies"]), "frames": int(round(a.sec * a.fps)) + 1}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
