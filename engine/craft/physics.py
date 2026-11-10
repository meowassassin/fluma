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


def load(xml_path: Path, args: dict | None = None):
    import mujoco
    return mujoco.MjModel.from_xml_string(fill(Path(xml_path).read_text("utf-8"), args))


def simulate(xml_path: Path, sec: float = 4.0, fps: int = 30, args: dict | None = None) -> dict:
    import mujoco
    model = load(xml_path, args)
    data = mujoco.MjData(model)
    if model.nkey:                                   # <keyframe> 가 있으면 첫 상태(처음 속도 · 자세)로 시작
        mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    per = max(1, round(1.0 / (fps * model.opt.timestep)))
    names = {i: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, model.nbody)}
    names = {i: n for i, n in names.items() if n}
    out = {n: [] for n in names.values()}
    frames = int(round(sec * fps)) + 1
    for f in range(frames):
        for i, n in names.items():
            p, q = data.xpos[i], data.xquat[i]
            out[n].append([round(float(v), 5) for v in (*p, *q)])
        for _ in range(per):
            mujoco.mj_step(model, data)
    return {"fps": fps, "sec": sec, "timestep": model.opt.timestep, "bodies": out}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "check"])
    ap.add_argument("scene")
    ap.add_argument("--sec", type=float, default=4.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--args", default="{}")
    ap.add_argument("--out")
    a = ap.parse_args()
    args = json.loads(a.args)
    if a.cmd == "check":
        import mujoco
        m = load(Path(a.scene), args)
        names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(1, m.nbody)]
        print(json.dumps({"ok": True, "bodies": [n for n in names if n], "timestep": m.opt.timestep}, ensure_ascii=False))
        return 0
    res = simulate(Path(a.scene), a.sec, a.fps, args)
    out = Path(a.out) if a.out else Path(a.scene).with_suffix(".traj.json")
    out.write_text(json.dumps(res), "utf-8")
    print(json.dumps({"ok": True, "out": str(out), "bodies": len(res["bodies"]), "frames": int(round(a.sec * a.fps)) + 1}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
