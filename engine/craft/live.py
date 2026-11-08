#!/usr/bin/env python3
"""실사 합성 — 실사 · 생성 영상에서 카메라 · 바닥을 풀어 3D · 2D 요소가 그 공간에 붙게 한다.

  python3 engine/craft/live.py solve <영상> --out <폴더> [--aov 도]   # 카메라 추적 → solve.json

solve.json: w · h · fps · frames · aov(가로 시야각) · vfov(세로) · cams(프레임마다 Blender 카메라 4×4) · ground(바닥 찾은 정도) · follow_px(광학 흐름으로 잰 독립 오차) · points(바닥 좌표계 3D 점) · tried(시야각 후보별 결과)
바닥 좌표계: z = 위(바닥 면이 z=0), 첫 프레임 화면 가운데 근처가 원점, 첫 프레임 카메라까지 거리 20 단위.
EffectCraft 3D Camera Tracker 를 쓴다(GPU 필요 없음, 영상 4초 · 후보 하나에 약 6초). 카메라 움직임이 없거나 무늬가 없으면 풀리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401


def _docs(text: str) -> list:
    d, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        c = [x for x in (text.find("{", i), text.find("[", i)) if x >= 0]
        if not c:
            break
        i = min(c)
        try:
            v, i = d.raw_decode(text, i)
            out.append(v)
        except ValueError:
            i += 1
    return out


# ---------------------------------------------------------------- 수학(순수 파이썬 — 앱 없이 시험)
def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mv(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return [x / n for x in a]


def rot_ae(ori):
    """After Effects 식 Orientation(도) → 3×3 (x 오른쪽 · y 아래 · z 앞). R = Rz · Ry · Rx"""
    x, y, z = [math.radians(v) for v in ori]
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    return mul(rz, mul(ry, rx))


def project(world, pos, ori, zoom, w, h):
    """세상 점 → 화면 픽셀(앞이 z+)"""
    R = rot_ae(ori)
    d = [world[i] - pos[i] for i in range(3)]
    c = [dot([R[0][i], R[1][i], R[2][i]], d) for i in range(3)]        # Rᵀ · d
    if c[2] <= 1e-6:
        return None
    return [w / 2 + zoom * c[0] / c[2], h / 2 + zoom * c[1] / c[2]]


def fit_plane(pts, iters=400, tol_ratio=0.012, seed=3):
    """RANSAC 평면: (점, 법선, 일치 비율)"""
    rnd = random.Random(seed)
    if len(pts) < 8:
        return None
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    tol = tol_ratio * math.sqrt(sum((b - a) ** 2 for a, b in zip(lo, hi)))
    best = (0, None)
    for _ in range(iters):
        a, b, c = rnd.sample(pts, 3)
        n = cross([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
        if dot(n, n) < 1e-9:
            continue
        n = unit(n)
        k = sum(1 for p in pts if abs(dot(n, [p[i] - a[i] for i in range(3)])) < tol)
        if k > best[0]:
            best = (k, (a, n))
    if not best[1]:
        return None
    a, n = best[1]
    inl = [p for p in pts if abs(dot(n, [p[i] - a[i] for i in range(3)])) < tol]
    return [sum(p[i] for p in inl) / len(inl) for i in range(3)], n, len(inl) / len(pts)


def to_scene(pos0, R0, center, normal):
    """EffectCraft 세상 → 바닥 좌표계: (회전 B, 원점, 배율)"""
    # 카메라 쪽이 위
    up = [pos0[i] - center[i] for i in range(3)]
    n = normal if dot(normal, up) > 0 else [-x for x in normal]
    right = [R0[0][0], R0[1][0], R0[2][0]]                          # 첫 프레임 화면 오른쪽
    x = unit([right[i] - dot(right, n) * n[i] for i in range(3)])
    y = cross(n, x)
    k = 20.0 / math.sqrt(sum((pos0[i] - center[i]) ** 2 for i in range(3)))
    return [x, y, n], center, k


def cam_matrix(pos, ori, B, O, k):
    """프레임 카메라 → Blender 4×4(카메라는 -Z 를 보고 Y 가 위)"""
    R = rot_ae(ori)
    col = lambda j: mv(B, [R[0][j], R[1][j], R[2][j]])  # noqa: E731
    r, d, f = col(0), col(1), col(2)
    u, b = [-v for v in d], [-v for v in f]
    p = [k * v for v in mv(B, [pos[i] - O[i] for i in range(3)])]
    return [[r[0], u[0], b[0], p[0]], [r[1], u[1], b[1], p[1]], [r[2], u[2], b[2], p[2]], [0, 0, 0, 1]]


# ---------------------------------------------------------------- 앱
def _probe(video: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration", "-of", "json", str(video)], capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    a, b = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": float(a) / float(b), "sec": float(s.get("duration") or 0)}


def to_pixel(cam, p, f, w, h):
    """바닥 좌표계 점 → 화면 픽셀(Blender 카메라 행렬, 카메라는 -Z 를 본다)"""
    d = [p[i] - cam[i][3] for i in range(3)]
    x, y, z = [sum(cam[r][c] * d[r] for r in range(3)) for c in range(3)]
    if z >= -1e-6:
        return None
    return [w / 2 + f * x / -z, h / 2 - f * y / -z]


def follow_error(video: Path, cams: list, points: list, vfov: float, w: int, h: int, n: int = 60) -> dict:
    """독립 검증 — 풀린 3D 점을 첫 프레임에 찍고 광학 흐름으로 실제 픽셀을 따라가, 풀린 카메라의 투영과 견준다.
    camera.points 의 화면 좌표는 풀린 점의 재투영이라 오차가 언제나 0 이다 — 이 값으로 판단하면 안 된다."""
    import cv2
    import numpy as np
    f = h / 2 / math.tan(math.radians(vfov) / 2)
    seed = [(p, to_pixel(cams[0], p, f, w, h)) for p in points]
    seed = [(p, uv) for p, uv in seed if uv and 8 < uv[0] < w - 8 and 8 < uv[1] < h - 8]
    seed = random.Random(5).sample(seed, min(n * 3, len(seed)))
    cap = cv2.VideoCapture(str(video))
    ok, fr = cap.read()
    if not ok or not seed:
        return {"median": None, "p95": None, "n": 0}
    prev = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    pts = np.array([uv for _, uv in seed], np.float32).reshape(-1, 1, 2)
    alive = np.ones(len(seed), bool)
    errs: list = []
    lk = dict(winSize=(25, 25), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    k = 0
    while True:
        ok, fr = cap.read()
        k += 1
        if not ok or k >= len(cams):
            break
        cur = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        nx, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, **lk)
        bk, st2, _ = cv2.calcOpticalFlowPyrLK(cur, prev, nx, None, **lk)
        good = (st.ravel() == 1) & (st2.ravel() == 1) & (np.abs(bk - pts).reshape(-1, 2).max(1) < 0.8)
        alive &= good
        pts, prev = nx, cur
        if k % 4:
            continue
        for i in np.flatnonzero(alive):
            uv = to_pixel(cams[k], seed[i][0], f, w, h)
            if uv:
                errs.append(math.hypot(uv[0] - float(pts[i][0][0]), uv[1] - float(pts[i][0][1])))
    cap.release()
    errs.sort()
    if not errs:
        return {"median": None, "p95": None, "n": 0}
    return {"median": round(errs[len(errs) // 2], 3), "p95": round(errs[int(len(errs) * 0.95)], 3), "n": int(alive.sum())}


def _solve_once(ec: str, video: Path, v: dict, out: Path, aov: float) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    proj = out / "solve.ecproj"
    js = out / "new.jsx"
    js.write_text(f"""var c=app.project.items.addComp('Live',{v['w']},{v['h']},1,{v['sec']:.3f},{v['fps']:.3f});
var f=app.project.importFile(new ImportOptions(new File({json.dumps(str(video))}))); var l=c.layers.add(f); l.name='Plate';
app.project.save(new File({json.dumps(str(proj))}));""", "utf-8")
    r = subprocess.run([ec, "script", str(js)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"실사 프로젝트 실패: {(r.stderr or r.stdout)[-300:]}")
    n = max(1, round(v["sec"] * v["fps"]))
    times = [v["sec"] * k / 5 for k in range(5)]
    steps = [{"command": "comp.open", "params": {"comp": "Live"}},
             {"command": "track.camera", "params": {"layer": "Plate", "shotType": "specify", "aov": aov, "solveMethod": "auto", "wait": True}},
             {"command": "camera.solveStatus", "params": {"layer": "Plate"}},
             {"command": "camera.createFromSolve", "params": {"kind": "camera", "layer": "Plate"}}] + \
            [{"command": "camera.points", "params": {"layer": "Plate", "time": t}} for t in times]
    sp = out / "solve.steps.json"
    sp.write_text(json.dumps(steps), "utf-8")
    r = subprocess.run([ec, "run", "--commands", str(sp), "--project", str(proj), "--save"], capture_output=True, text=True, timeout=1800)
    docs = _docs(r.stdout)
    st = [d for d in docs if isinstance(d, dict) and "solved" in d]
    pts = [d for d in docs if isinstance(d, dict) and isinstance(d.get("points"), list)]
    if r.returncode != 0 or not st or not st[-1].get("solved") or not pts:
        raise RuntimeError(f"카메라를 풀지 못했습니다 — 카메라가 움직이고 무늬가 보이는 영상이어야 합니다: {(r.stderr or r.stdout)[-300:]}")
    rd = out / "read.jsx"
    rd.write_text(f"""var c=null;for(var i=1;i<=app.project.numItems;i++){{if(app.project.item(i).name=="Live")c=app.project.item(i);}}
var cam=null;for(var i=1;i<=c.numLayers;i++){{if(c.layer(i) instanceof CameraLayer)cam=c.layer(i);}}
var T=cam.property("Transform");var o=[];
for(var k=0;k<{n};k++){{var t=k/{v['fps']:.3f};o.push({{p:T.property("Position").valueAtTime(t,false),o:T.property("Orientation").valueAtTime(t,false)}});}}
writeLn(JSON.stringify({{zoom:cam.property("Camera Options").property("Zoom").value,frames:o}}));""", "utf-8")
    r = subprocess.run([ec, "script", str(rd), str(proj)], capture_output=True, text=True, timeout=300)
    cam = next((d for d in _docs(r.stdout) if isinstance(d, dict) and "frames" in d), None)
    if not cam:
        raise RuntimeError(f"카메라 값을 읽지 못했습니다: {(r.stderr or r.stdout)[-300:]}")
    zoom, fr = float(cam["zoom"]), cam["frames"]
    wp = [list(q) for q in {tuple(round(x, 3) for x in p["world"]): 1 for d in pts for p in d["points"]}]
    # 바닥: 첫 프레임 화면 아래쪽 점 위주로 평면을 찾는다 — 벽을 고르지 않게
    low = [p["world"] for p in pts[0]["points"] if p["comp"][1] > v["h"] * 0.55]
    pl = fit_plane(low if len(low) >= 12 else wp)
    if not pl:
        raise RuntimeError("바닥 면을 찾지 못했습니다")
    center, normal, ratio = pl
    B, O, k = to_scene(fr[0]["p"], rot_ae(fr[0]["o"]), center, normal)
    res = {"w": v["w"], "h": v["h"], "fps": v["fps"], "frames": len(fr), "aov": aov, "vfov": math.degrees(2 * math.atan(v["h"] / 2 / zoom)),
           "cams": [cam_matrix(q["p"], q["o"], B, O, k) for q in fr], "ground": {"inlier": round(ratio, 3), "points": len(low)},
           "points": [[k * x for x in mv(B, [p[i] - O[i] for i in range(3)])] for p in wp], "tracks": st[-1].get("tracks")}
    res["follow_px"] = follow_error(video, res["cams"], res["points"], res["vfov"], v["w"], v["h"])
    return res


AOVS = (22, 28, 34, 40, 48, 58, 70)       # 가로 시야각 후보 — 렌즈를 모르는 영상. 시야각은 자동으로 풀면 크게 틀린다(시험: 정답 33° → 27°)


def solve(video: Path, out: Path, aov: float | None = None) -> dict:
    from craft.materials import cli
    ec = str(cli("effectcraft"))
    v = _probe(video)
    tried, best = [], None
    for a in ([aov] if aov else AOVS):
        try:
            r = _solve_once(ec, video, v, out / f"a{int(a * 10)}", float(a))
        except RuntimeError as e:
            tried.append({"aov": a, "error": str(e)[:120]})
            continue
        m = r["follow_px"]["median"]
        tried.append({"aov": a, "follow_px": r["follow_px"]})
        if m is not None and (best is None or m < best["follow_px"]["median"]):
            best = r
    if not best:
        raise RuntimeError(f"어떤 시야각으로도 카메라를 풀지 못했습니다: {tried}")
    if not aov:                              # 가장 좋은 후보 양옆을 한 번 더
        i = AOVS.index(int(best["aov"]))
        for a in (([(AOVS[i - 1] + best["aov"]) / 2] if i else []) + ([(AOVS[i + 1] + best["aov"]) / 2] if i + 1 < len(AOVS) else [])):
            try:
                r = _solve_once(ec, video, v, out / f"a{int(a * 10)}", float(a))
            except RuntimeError:
                continue
            tried.append({"aov": a, "follow_px": r["follow_px"]})
            if r["follow_px"]["median"] is not None and r["follow_px"]["median"] < best["follow_px"]["median"]:
                best = r
    best["tried"] = tried
    (out / "solve.json").write_text(json.dumps(best), "utf-8")
    return best


def ground_hit(cam, u, v, f, w, h):
    """화면 픽셀 → 바닥(z=0) 위 점. 하늘을 가리키면 None"""
    d = [(u - w / 2) / f, -(v - h / 2) / f, -1.0]
    r = [sum(cam[i][j] * d[j] for j in range(3)) for i in range(3)]
    if r[2] >= -1e-6:
        return None
    t = -cam[2][3] / r[2]
    return [cam[i][3] + r[i] * t for i in range(2)] + [0.0]


def height_unit(cam, p, f, h):
    """그 점에서 화면 높이 1 에 해당하는 씬 길이"""
    d = [p[i] - cam[i][3] for i in range(3)]
    depth = -sum(cam[r][2] * d[r] for r in range(3))
    return depth * h / f


def anchor_path(video: Path, s: dict, f: dict) -> list:
    """2D 요소가 따라갈 프레임별 픽셀.
    {"at": [u, v], "frame": n}: 장면에 고정된 곳 — 풀린 3D 점(없으면 바닥)에 붙여 카메라로 투영
    "moving": true 를 더하면 움직이는 물체 — 그 픽셀을 광학 흐름으로 앞뒤로 따라간다"""
    w, h, n = s["w"], s["h"], s["frames"]
    fl = h / 2 / math.tan(math.radians(s["vfov"]) / 2)
    u, v = f["at"]
    k = int(f.get("frame", 0))
    if f.get("moving"):
        return _lk_path(video, u, v, k, n)
    near = []
    for p in s["points"]:
        q = to_pixel(s["cams"][k], p, fl, w, h)
        if q and math.hypot(q[0] - u, q[1] - v) < 24:
            near.append((math.hypot(q[0] - u, q[1] - v), p))
    if not near:                                     # 근처에 풀린 점이 없다 — 바닥으로 보면 벽에서 밀리므로 픽셀을 직접 따라간다
        return _lk_path(video, u, v, k, n)
    p = min(near, key=lambda x: x[0])[1]
    out = [to_pixel(c, p, fl, w, h) for c in s["cams"]]
    last = [u, v]
    for i, q in enumerate(out):
        out[i] = last = q or last
    return out


def _lk_path(video: Path, u: float, v: float, k: int, n: int) -> list:
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video))
    frames = []
    while len(frames) < n:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
    cap.release()
    path = [None] * len(frames)
    path[k] = [u, v]
    lk = dict(winSize=(41, 41), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    for rng in (range(k + 1, len(frames)), range(k - 1, -1, -1)):
        p = np.array([[[u, v]]], np.float32)
        last = k
        for i in rng:
            nx, st, _ = cv2.calcOpticalFlowPyrLK(frames[last], frames[i], p, None, **lk)
            if st[0][0] != 1:
                break
            p, last = nx, i
            path[i] = [float(p[0][0][0]), float(p[0][0][1])]
    good = [i for i, q in enumerate(path) if q]
    for i in range(len(path)):
        path[i] = path[i] or path[min(good, key=lambda g: abs(g - i))]
    return path


def _alphas(ec: str, proj: Path, layer: str, work: Path, n: int, fps: float) -> list:
    """분리한 층의 프레임별 알파(¼ 크기) — 윤곽 · 위치를 읽으려고 그 층만 켠 사본을 렌더한다"""
    import cv2
    d = work / "alpha" / layer.replace(" ", "_")
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.png"):
        f.unlink()
    tmp = work / "alpha.ecproj"
    tmp.write_bytes(proj.read_bytes())
    js = work / "solo.jsx"
    js.write_text(f"""var c=null;for(var i=1;i<=app.project.numItems;i++){{if(app.project.item(i).name=="Live")c=app.project.item(i);}}
c.workAreaStart=0;c.workAreaDuration=c.duration;
for(var i=1;i<=c.numLayers;i++){{c.layer(i).enabled=(c.layer(i).name=={_jstr(layer)});}}app.project.save();""", "utf-8")
    r = subprocess.run([ec, "script", str(js), str(tmp)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"층 분리 실패: {(r.stderr or r.stdout)[-300:]}")
    r = subprocess.run([ec, "render", "--project", str(tmp), "--comp", "Live", "--out", str(d / "f.png"), "--format", "png", "--channels", "rgba", "--resolution", "quarter", "--fps", str(round(fps))], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"윤곽 렌더 실패: {(r.stderr or r.stdout)[-300:]}")
    fs = sorted(d.glob("*.png"))
    out = [cv2.imread(str(f), cv2.IMREAD_UNCHANGED)[:, :, 3] for f in fs]
    return out[:n] + [out[-1]] * (n - len(out))


def cut_path(alphas: list, where: str = "top", scale: int = 4) -> tuple[list, list]:
    """분리한 물체의 프레임별 위치 + 보임 여부. 화면에서 사라진 프레임은 가장 가까운 위치를 쓰고 보임을 끈다"""
    import numpy as np
    path, seen = [], []
    for a in alphas:
        ys, xs = np.nonzero(a > 128)
        if len(xs) < 60:
            path.append(None)
            seen.append(False)
            continue
        x = float(xs.mean())
        y = float(ys.mean()) if where == "center" else float(np.percentile(ys, 3))
        path.append([x * scale, y * scale])
        seen.append(True)
    good = [i for i, q in enumerate(path) if q]
    if not good:
        raise RuntimeError("분리한 물체가 어느 프레임에도 없습니다")
    return [q or path[min(good, key=lambda g: abs(g - i))] for i, q in enumerate(path)], seen


def cut_sheet(memo: dict, out: Path) -> None:
    """분리 확인 그림 — 물체마다 고른 프레임의 매트. 사람이나 에이전트가 새는 곳을 보고 획을 고친다"""
    import cv2
    import numpy as np
    rows = []
    for name, al in memo.items():
        idx = [round(i * (len(al) - 1) / 7) for i in range(8)]
        rows.append(np.hstack([cv2.copyMakeBorder(al[i], 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=90) for i in idx]))
    cv2.imwrite(str(out), np.vstack(rows))


def contour(a, scale: int = 4, grow: int = 3) -> list:
    """알파 → 마스크 점 목록(프레임 공통 점 수 없이 프레임마다 키)"""
    import cv2
    import numpy as np
    m = cv2.dilate((a > 96).astype(np.uint8), np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return []
    c = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.2, True)
    return [[float(x) * scale, float(y) * scale] for [[x, y]] in c]


def _strokes(ly: str, c: dict, n: int) -> list:
    a, b = c.get("span") or (0, n - 1)
    st = [{"command": "roto.stroke", "params": {"layer": ly, "kind": x.get("kind", "fg"), "points": x["points"], "frame": x["frame"], "radius": x.get("radius", 20)}} for x in c["strokes"] if a <= x["frame"] <= b]
    return st + [{"command": "roto.span", "params": {"layer": ly, "start": a, "end": b}}, {"command": "roto.propagate", "params": {"layer": ly, "direction": "both", "wait": True}}]


def _run(ec: str, steps: list, proj: Path, work: Path, what: str, timeout: int = 1800) -> None:
    f = work / "steps.json"
    f.write_text(json.dumps(steps, ensure_ascii=False), "utf-8")
    r = subprocess.run([ec, "run", "--commands", str(f), "--project", str(proj), "--save"], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{what} 실패: {(r.stderr or r.stdout)[-400:]}")


def _script(ec: str, js: str, work: Path, what: str, proj: Path | None = None) -> None:
    f = work / "step.jsx"
    f.write_text(js, "utf-8")
    r = subprocess.run([ec, "script", str(f), *([str(proj)] if proj else [])], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"{what} 실패: {(r.stderr or r.stdout)[-400:]}")


def patch_homography(s: dict, r: int, t: int, box: list):
    """프레임 r → t 의 평면 변환 — 물체 주변에서 바닥에 붙은 풀린 3D 점(추적된 진짜 무늬)을 두 프레임에 투영해 대응을 얻는다.
    벽 점이 섞이면 틀어지고, 계산한 바닥면만 쓰면 지평선 근처에서 조금만 기울어도 크게 밀린다. 지나가는 물체에는 영향받지 않는다"""
    import cv2
    import numpy as np
    w, h = s["w"], s["h"]
    f = h / 2 / math.tan(math.radians(s["vfov"]) / 2)
    x0, y0, x1, y1 = box
    tol = abs(s["cams"][r][2][3]) * 0.04
    low = [p for p in s["points"] if abs(p[2]) < tol]
    for grow in (1.0, 2.0, 4.0, 8.0):
        mx, my = (x1 - x0) * grow, (y1 - y0) * grow
        pa, pb = [], []
        for p in low:
            q = to_pixel(s["cams"][r], p, f, w, h)
            if q and x0 - mx < q[0] < x1 + mx and y0 - my < q[1] < y1 + my:
                u = to_pixel(s["cams"][t], p, f, w, h)
                if u:
                    pa.append(q); pb.append(u)
        if len(pa) >= 10:
            H, _ = cv2.findHomography(np.array(pa, np.float32), np.array(pb, np.float32), cv2.RANSAC, 1.5)
            if H is not None:
                return H
    raise RuntimeError("지울 물체 주변 바닥에 풀린 3D 점이 부족합니다 — 지우기는 무늬 있는 바닥 위 정지한 물체만 됩니다")


def object_move(s: dict, H, r: int, t: int, box: list):
    """서 있는 물체의 윤곽이 r → t 에서 움직이는 변환: 밑면 가운데를 따라가고 깊이만큼 크기가 변한다.
    윤곽이 가린 바닥과 물체는 다르게 움직인다(시차) — 윤곽을 바닥 변환으로 옮기면 물체가 삐져나온다"""
    import numpy as np
    w, h = s["w"], s["h"]
    f = h / 2 / math.tan(math.radians(s["vfov"]) / 2)
    bx, by = (box[0] + box[2]) / 2, box[3]
    q = H @ np.array([bx, by, 1.0])
    tx, ty = q[0] / q[2], q[1] / q[2]
    p = ground_hit(s["cams"][r], bx, by, f, w, h)
    k = height_unit(s["cams"][r], p, f, h) / height_unit(s["cams"][t], p, f, h) if p else 1.0
    return np.array([[k, 0, tx - k * bx], [0, k, ty - k * by]], np.float32)


def clean_patch(ec: str, video: Path, v: dict, s: dict, rem: dict, work: Path) -> Path:
    """바닥에 선 정지한 물체 지우기(클린 플레이트 패치) — 가리는 것이 없는 프레임 한 곳만 Content-Aware Fill 로 채우고,
    풀린 카메라로 그 화면을 프레임마다 옮겨 물체 자리에 붙인다. 프레임별로 다시 채우지 않아 깜빡이지 않고, 지나가는 인물을 채움 재료로 쓰지 않는다.
    움직이는 물체는 지원하지 않는다. 앞을 지나가는 물체는 cuts 층이 조각 위로 올라와 가린다."""
    import cv2
    import numpy as np
    d = work / "clean"
    d.mkdir(parents=True, exist_ok=True)
    out = d / "patch.mov"
    stamp = d / "clean.key"
    key = json.dumps([str(video), video.stat().st_mtime, rem], sort_keys=True, ensure_ascii=False)
    if out.exists() and stamp.exists() and stamp.read_text("utf-8") == key:
        return out                                  # 같은 영상 · 같은 획이면 다시 채우지 않는다
    n, fps = s["frames"], v["fps"]
    pieces = []
    for name, c in rem.items():
        r = int(c.get("frame", c["strokes"][0]["frame"]))
        e = min(n - 1, r + 5)
        dd = d / name
        dd.mkdir(exist_ok=True)
        proj = dd / "fill.ecproj"
        _script(ec, f"""var c=app.project.items.addComp('Live',{v['w']},{v['h']},1,{v['sec']:.3f},{fps:.3f});c.workAreaStart={r / fps:.4f};c.workAreaDuration={(e - r + 1) / fps:.4f};
var src=app.project.importFile(new ImportOptions(new File({_jstr(str(video))})));var h=c.layers.add(src);h.name='Holed';
var k=c.layers.add(src);k.name='Cut';k.property('Effects').addProperty('ec.matte.rotobrush');app.project.save(new File({_jstr(str(proj))}));""", dd, "지우기 프로젝트")
        st = [{"command": "comp.open", "params": {"comp": "Live"}}]
        st += [{"command": "roto.stroke", "params": {"layer": "Cut", "kind": x.get("kind", "fg"), "points": x["points"], "frame": x["frame"], "radius": x.get("radius", 20)}} for x in c["strokes"] if x["frame"] == r]
        st += [{"command": "roto.span", "params": {"layer": "Cut", "start": r, "end": e}}, {"command": "roto.propagate", "params": {"layer": "Cut", "direction": "forward", "wait": True}}]
        _run(ec, st, proj, dd, "지울 물체 분리")
        al = _alphas(ec, proj, "Cut", dd, n, fps)
        grow = int(c.get("grow", 3))
        keys = [contour(al[i], grow=grow) for i in range(r, e + 1)]
        if not all(len(q) >= 3 for q in keys):
            raise RuntimeError(f"{name}: 프레임 {r} 근처에서 물체를 분리하지 못했습니다 — 획을 고쳐 주세요")
        _script(ec, f"""var c=null;for(var i=1;i<=app.project.numItems;i++){{if(app.project.item(i).name=="Live")c=app.project.item(i);}}
var H=c.layer("Holed");var K={json.dumps(keys)};var m=H.property("Masks").addProperty("Mask");m.maskMode=MaskMode.SUBTRACT;var P=m.property("Mask Path");
for(var i=0;i<K.length;i++){{var S=new Shape();S.vertices=K[i];S.closed=true;P.setValueAtTime(({r}+i)/{fps:.3f},S);}}
c.layer("Cut").enabled=false;app.project.save();""", dd, "지우기 마스크", proj)
        fill = dd / "fill"
        fill.mkdir(exist_ok=True)
        _run(ec, [{"command": "comp.open", "params": {"comp": "Live"}},
                  {"command": "layer.newContentAwareFill", "params": {"layer": "Holed", "method": c.get("method", "object"), "range": "workArea", "alphaExpansion": 4, "lightingCorrection": "subtle", "outputDir": str(fill), "wait": True}}], proj, dd, "내용 채우기")
        fs = sorted(fill.glob("fill_*.png"))
        if not fs:
            raise RuntimeError(f"{name}: 채운 결과가 없습니다")
        patch = cv2.imread(str(fs[0]), cv2.IMREAD_UNCHANGED)[:, :, :3]
        raw = cv2.resize((al[r] > 96).astype(np.uint8) * 255, (v["w"], v["h"]), interpolation=cv2.INTER_LINEAR)
        m = cv2.dilate(raw, np.ones((grow * 8 + 1, grow * 8 + 1), np.uint8))
        m = cv2.GaussianBlur(m, (0, 0), 3)
        ys, xs = np.nonzero(raw)
        pieces.append((patch, m, r, [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]))
    seq = d / "seq"
    seq.mkdir(exist_ok=True)
    for t in range(n):
        rgba = np.zeros((v["h"], v["w"], 4), np.uint8)
        for patch, m, r, box in pieces:
            H = patch_homography(s, r, t, box)
            im = cv2.warpPerspective(patch, H, (v["w"], v["h"]), flags=cv2.INTER_CUBIC)       # 내용은 바닥을 따라가고
            am = cv2.warpAffine(m, object_move(s, H, r, t, box), (v["w"], v["h"]), flags=cv2.INTER_LINEAR)   # 구멍은 물체를 따라간다
            on = am > 0                      # 곧은 알파 — 색에 알파를 곱해 두면 가장자리가 어두워진다
            rgba[on, :3] = im[on]
            rgba[:, :, 3] = np.maximum(rgba[:, :, 3], am)
        cv2.imwrite(str(seq / f"p{t:05d}.png"), rgba)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(round(fps)), "-i", str(seq / "p%05d.png"), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"조각 영상 실패: {r.stderr[-300:]}")
    stamp.write_text(key, "utf-8")
    return out


def _jstr(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def render_item(it: dict, s: dict, solve_path: Path, work: Path) -> list:
    """3D 하나 → [그림자 .mov, 물체 .mov] (투명). 카메라 · 바닥이 맞춰진 두 패스"""
    from craft.adapters import blender as b
    w, h = s["w"], s["h"]
    fl = h / 2 / math.tan(math.radians(s["vfov"]) / 2)
    k = int(it.get("frame", 0))
    p = ground_hit(s["cams"][k], it["at"][0], it["at"][1], fl, w, h)
    if p is None:
        raise RuntimeError(f"{it['id']}: at 이 바닥 위 점이 아닙니다: {it['at']}")
    unit = height_unit(s["cams"][k], p, fl, h)
    fps = max(1, round(s["fps"]))
    out = []
    for name in (("shadow", "beauty") if it.get("shadow", True) else ("beauty",)):
        m = {"id": it["id"], "script": it["script"], "sec": s["frames"] / fps, "fps": fps, "width": w, "height": h, "quality": it.get("quality", "fast"), "transparent": True,
             "args": {**(it.get("args") or {}), "solve": str(solve_path), "at": p, "unit": unit, "height": it.get("height", 0.2), "pass": name, "light": it.get("light") or {}, "shadow": it.get("shadow_amount", 0.62)}}
        f = work / f"{it['id']}.{name}.png"
        info = b.model3d(m, f, work)
        out.append(f.with_suffix(info.get("file_suffix") or ".png"))
    return out


def compose(spec: dict, work: Path) -> dict:
    """실사 한 컷 합성 — 맨 아래부터: 영상 · 뒤 요소 · 잘라 낸 물체(앞 가림 · 색 바꿈) · 앞 요소. EffectCraft 프로젝트로 남아 refine 으로 고칠 수 있다.
    spec: {src, aov?, cuts: {이름: {strokes: [{frame, kind: fg|bg, points, radius?}], span?: [시작, 끝 프레임](물체가 보이는 구간), recolor?: {hue, sat, light}, remove?: true(정지한 물체, frame = 가리는 것 없는 프레임), grow?: 윤곽 넓히기(¼ 픽셀)}},
           items: [{id, kind: model3d|text|image, behind?: 이름, ...}]}
      model3d: script · at(바닥 픽셀) · frame · height(화면 높이 비율) · shadow · light{az, el, strength, color, soft}
      text: text · follow{at, frame, moving?} 또는 {cut: 이름, at: top|center} · offset · size · color · font
      image: file · follow · offset · scale
    strokes 의 points 는 이어진 한 획이다 — 점을 흩뿌리거나 둘레를 한 번에 돌면 물체를 가로지른다. 가장자리마다 획을 나눈다.
    결과의 cuts.check.png 로 매트를 보고 새면 그 프레임에 bg 획을 더한다."""
    from craft.materials import cli
    ec = str(cli("effectcraft"))
    work.mkdir(parents=True, exist_ok=True)
    video = Path(spec["src"]).resolve()
    sp = work / "solve" / "solve.json"
    key = f"{video}|{video.stat().st_mtime}|{spec.get('aov')}"
    s = json.loads(sp.read_text("utf-8")) if sp.exists() else {}
    if s.get("key") != key:                  # 같은 영상이면 카메라를 다시 풀지 않는다
        s = solve(video, work / "solve", spec.get("aov"))
        s["key"] = key
        sp.write_text(json.dumps(s), "utf-8")
    v = _probe(video)
    proj = work / "live.ecproj"
    cuts_all = spec.get("cuts") or {}
    rem = {k: c for k, c in cuts_all.items() if c.get("remove")}
    cuts = {k: c for k, c in cuts_all.items() if not c.get("remove")}
    n = s["frames"]
    patch = clean_patch(ec, video, v, s, rem, work) if rem else None
    js = [f"""var c=app.project.items.addComp('Live',{v['w']},{v['h']},1,{v['sec']:.3f},{v['fps']:.3f});
var src=app.project.importFile(new ImportOptions(new File({_jstr(str(video))})));
function clip(p){{var it=app.project.importFile(new ImportOptions(new File(p)));var l=c.layers.add(it);l.startTime=0;return l;}}
function pos(l,xs){{var P=l.property("Transform").property("Position");for(var i=0;i<xs.length;i++)P.setValueAtTime(i/{v['fps']:.3f},xs[i]);}}
function txt(name,body,size,fill,font){{var t=c.layers.addText(body);t.name=name;var P=t.property("Source Text");var d=P.value;d.font=font;d.fontSize=size;d.applyFill=true;d.fillColor=fill;d.justification=ParagraphJustification.CENTER_JUSTIFY;P.setValue(d);return t;}}
var pl=c.layers.add(src);pl.name='Plate';"""]
    if patch:
        js.append(f"(function(){{var l=clip({_jstr(str(patch))});l.name='Clean';}})();")
    items = spec.get("items") or []
    later = []                                   # 물체를 따라가는 2D — 분리가 끝나야 경로를 안다

    def add(it):
        if it["kind"] == "model3d":
            for f, nm in zip(render_item(it, s, sp, work), ("그림자", "") if it.get("shadow", True) else ("",)):
                js.append(f"(function(){{var l=clip({_jstr(str(f))});l.name={_jstr((it['id'] + ' ' + nm).strip())};}})();")
            return
        off = it.get("offset") or [0, 0]
        f = it["follow"]
        if f.get("cut"):
            later.append(it)
            path = [[v["w"] / 2, v["h"] / 2]]
        else:
            path = [[q[0] + off[0], q[1] + off[1]] for q in anchor_path(video, s, f)]
        if it["kind"] == "text":
            c = it.get("color", "#ffffff").lstrip("#")
            fill = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            js.append(f"pos(txt({_jstr(it['id'])},{_jstr(it['text'])},{it.get('size', 56)},{json.dumps(fill)},{_jstr(it.get('font', 'Pretendard-Bold'))}),{json.dumps(path)});")
        else:
            js.append(f"(function(){{var l=clip({_jstr(str(Path(it['file']).resolve()))});l.name={_jstr(it['id'])};var q={it.get('scale', 100)};l.property('Transform').property('Scale').setValue([q,q]);pos(l,{json.dumps(path)});}})();")

    for it in items:
        if it.get("behind"):
            add(it)
    for name, cc in cuts.items():
        js.append(f"var k=c.layers.add(src);k.name={_jstr('Cut ' + name)};k.property('Effects').addProperty('ec.matte.rotobrush');")
        if cc.get("span"):                     # 물체가 화면에 있는 구간만 — 나간 뒤 매트가 다른 물체를 붙잡지 않게
            a_, b_ = cc["span"]
            js.append(f"k.inPoint={a_ / v['fps']:.4f};k.outPoint={(b_ + 1) / v['fps']:.4f};")
        rc = cc.get("recolor")
        if rc:
            js.append(f"""var e=k.property('Effects').addProperty('ec.color.huesaturation');
e.property('Master Hue').setValue({rc.get('hue', 0)});e.property('Master Saturation').setValue({rc.get('sat', 0)});e.property('Master Lightness').setValue({rc.get('light', 0)});""")
    for it in items:
        if not it.get("behind"):
            add(it)
    js.append(f"app.project.save(new File({_jstr(str(proj))}));")
    _script(ec, "\n".join(js), work, "합성 프로젝트")
    steps = [{"command": "comp.open", "params": {"comp": "Live"}}]
    for name, cc in cuts.items():
        steps += _strokes(f"Cut {name}", cc, n)
    _run(ec, steps, proj, work, "물체 분리")
    memo: dict = {n_: _alphas(ec, proj, f"Cut {n_}", work, n, v["fps"]) for n_ in cuts}
    if cuts:
        cut_sheet(memo, work / "cuts.check.png")
    if later:
        js = ["""var c=null;for(var i=1;i<=app.project.numItems;i++){if(app.project.item(i).name=="Live")c=app.project.item(i);}"""]
        for it in later:
            f, off = it["follow"], it.get("offset") or [0, 0]
            path, seen = cut_path(memo[f["cut"]], f.get("at", "top"))
            path = [[q[0] + off[0], q[1] + off[1]] for q in path]
            js.append(f"""(function(){{var l=c.layer({_jstr(it['id'])});var P=l.property("Transform").property("Position");var O=l.property("Transform").property("Opacity");var X={json.dumps(path)};var S={json.dumps(seen)};
for(var i=0;i<X.length;i++){{var t=i/{v['fps']:.3f};P.setValueAtTime(t,X[i]);O.setValueAtTime(t,S[i]?100:0);}}}})();""")
        js.append("app.project.save();")
        _script(ec, "\n".join(js), work, "물체 따라가기", proj)
    out = work / "live.mp4"
    r = subprocess.run([ec, "render", "--project", str(proj), "--comp", "Live", "--out", str(out), "--format", "h264", "--audio", "off", "--fps", str(round(v["fps"]))], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"합성 렌더 실패: {(r.stderr or r.stdout)[-400:]}")
    return {"file": str(out), "project": str(proj), "follow_px": s["follow_px"], "aov": s["aov"], "check": str(work / "cuts.check.png") if cuts else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("solve"); a.add_argument("video"); a.add_argument("--out", required=True); a.add_argument("--aov", type=float)
    c = sub.add_parser("compose"); c.add_argument("spec"); c.add_argument("--out", required=True)
    x = ap.parse_args()
    if x.cmd == "compose":
        print(json.dumps(compose(json.loads(Path(x.spec).read_text("utf-8")), Path(x.out).resolve()), ensure_ascii=False, indent=1))
        return 0
    r = solve(Path(x.video).resolve(), Path(x.out).resolve(), x.aov)
    print(json.dumps({k: v for k, v in r.items() if k not in ("cams", "points")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
