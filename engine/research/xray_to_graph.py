#!/usr/bin/env python3
"""분해도(트렌드 쇼츠 엑스레이) → 내 영상의 장면 설계도 초안. 형식(리듬 · 구도 · 카메라)만 옮기고 내용(그림 · 말 · 글)은 옮기지 않는다.

  python3 engine/research/xray_to_graph.py <xray-id> <project-id>            # 무엇을 넣을지 미리 보기(바꾸지 않음)
  python3 engine/research/xray_to_graph.py <xray-id> <project-id> --apply    # 설계도에 넣기 (actor director)

옮기는 것
· 샷마다 주인공 자리 → 대역 상자(proxy). 참고 샷 화면은 '참고 그림'(구도 확인용)으로만 달고 쓸 권리는 reference-only
  → 스케치(애니메틱)에서는 연필 선으로 보이고, 최종 렌더는 그 자리를 실사 · 생성 · 직접 만든 화면으로 바꿀 때까지 막힌다.
· 글자가 뜨는 자리 · 시각 → 글자 자리(text, '글자 N' — 원본 글은 옮기지 않음)
· 카메라 움직임(광류: 팬 · 줌) → 장면 카메라 키
· 시간은 참고 영상 길이를 내 영상 길이에 비례로 맞춘다(장면 길이는 나레이션이 정하므로 바꾸지 않음)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
W, H = 1080, 1920
ANALYSIS_FPS, ANALYSIS_W = 4, 270   # shorts_xray.small_frames — 광류를 잰 프레임


def text_box(bx: float, by: float, bw: float) -> dict:
    """분해도 글자 상자(왼쪽 위 x · y · 폭, 0~1) → 같은 가운데 · 최소 폭 360px 의 글자 자리"""
    w = max(360, round(bw * W)); cx = (bx + bw / 2) * W
    return {"x": int(max(0, min(W - w, round(cx - w / 2)))), "y": round(by * H), "w": w}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xray"); ap.add_argument("id")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-text", action="store_true", help="글자 자리는 넣지 않기")
    a = ap.parse_args()
    xp = ROOT / "data" / "public" / "trends" / "xray" / a.xray / "xray.json"
    if not xp.exists():
        sys.exit(f"분해도 없음: {xp.relative_to(ROOT)} — 트렌드 화면에서 '분해'부터")
    x = json.loads(xp.read_text(encoding="utf-8"))
    sb = json.loads((ROOT / "data" / "storyboards" / f"{a.id}.json").read_text(encoding="utf-8"))
    secs = [float(s.get("sec", 0)) for s in sb.get("scenes", [])]
    starts = [sum(secs[:i]) for i in range(len(secs))]
    total, ref = sum(secs), float(x["video"]["duration"]) or 1.0
    k = total / ref

    def where(t_ref: float):
        """참고 영상 시각 → (장면 번호, 장면 안 시각)"""
        t = t_ref * k
        for i in range(len(secs) - 1, -1, -1):
            if t >= starts[i] - 1e-6:
                return i, round(min(secs[i], t - starts[i]), 2)
        return 0, 0.0

    nodes = {i: [] for i in range(len(secs))}
    cams = {i: [] for i in range(len(secs))}
    assets = {}
    for s in x.get("shots", []):
        si, t0 = where(s["start"]); sj, t1 = where(s["end"])
        if sj != si:
            t1 = secs[si]   # 장면 경계를 넘는 샷은 그 장면 끝까지만
        sub = s.get("subject") or {}
        if sub.get("bbox"):
            bx, by, bw, bh = sub["bbox"]
            key = f"ref-{a.xray}-{s['i']}"
            assets[key] = {"kind": "image", "src": s["frame"], "rights": {"status": "reference-only", "note": f"참고 쇼츠 {x.get('url', a.xray)} 샷 {s['i'] + 1} — 구도 확인용, 영상에 쓰지 않음"}}
            nodes[si].append({"id": f"ref{s['i']}", "kind": "proxy", "label": f"참고 샷 {s['i'] + 1} 주인공 자리", "owner": "director", "asset": key,
                              "box": {"x": round(bx * W), "y": round(by * H), "w": max(80, round(bw * W)), "h": max(80, round(bh * H))},
                              "layer": 3, "start": t0, "end": round(max(t0 + 0.2, t1), 2), "gen": {"keyframe": s["frame"]}})
        cam = s.get("camera") or {}
        if cam.get("kind", "고정") not in ("고정", "흔들림") and t1 - t0 >= 0.4:
            dur_ref = max(0.25, s["end"] - s["start"])
            # 광류: 화면 내용이 프레임마다 (dx, dy)px(폭 270 기준) 움직임 → 카메라는 반대로. 줌은 프레임마다 확대 비율(%)
            px = W / ANALYSIS_W
            vx, vy = -cam["pan"][0] * px * ANALYSIS_FPS, -cam["pan"][1] * px * ANALYSIS_FPS
            zs = max(0.5, min(2.0, 1 + cam.get("zoom", 0) / 100 * ANALYSIS_FPS * dur_ref))
            cams[si] += [{"t": t0, "x": 0, "y": 0, "scale": 1, "rot": 0},
                         {"t": round(t1, 2), "x": round(max(-400, min(400, vx * dur_ref))), "y": round(max(-600, min(600, vy * dur_ref))), "scale": round(zs, 3), "rot": 0, "ease": "sine.inOut"}]
    if not a.no_text:
        for n, tx in enumerate(x.get("text", [])):
            si, t0 = where(tx["start"]); _, t1 = where(tx["end"])
            bx, by, bw, bh = tx["box"]
            nodes[si].append({"id": f"reftext{n}", "kind": "text", "label": f"글자 자리 {n + 1} ({tx.get('band', '')})", "text": f"글자 {n + 1}", "owner": "director",
                              "box": text_box(bx, by, bw),
                              "style": {"size": max(36, min(120, round(bh * H * 0.8))), "weight": 900}, "layer": 12, "start": t0, "end": round(max(t0 + 0.3, t1), 2)})

    n_nodes = sum(len(v) for v in nodes.values()); n_cam = sum(1 for v in cams.values() if v)
    print(f"참고 {a.xray} ({ref:.1f}초, 샷 {len(x.get('shots', []))}개) → {a.id} ({total:.1f}초 · ×{k:.2f}): 개체 {n_nodes}개 · 카메라 장면 {n_cam}개 · 참고 그림 {len(assets)}장(reference-only)")
    for si in range(len(secs)):
        if nodes[si] or cams[si]:
            print(f"  장면 {si + 1}: " + ", ".join(f"{n['label']} {n.get('start', 0)}~{n.get('end', '')}초" for n in nodes[si]) + (f" · 카메라 키 {len(cams[si])}" if cams[si] else ""))
    if not a.apply:
        print("미리 보기만 했습니다 — 넣으려면 --apply")
        return

    gp = ROOT / "data" / "scenes" / f"{a.id}.scene.json"
    if not gp.exists():
        subprocess.run([sys.executable, str(ROOT / "engine" / "core" / "scene_graph.py"), "init", a.id], check=True)
    g = json.loads(gp.read_text(encoding="utf-8"))
    ops = []
    if "assets" not in g:
        ops.append({"op": "add", "path": "/assets", "value": {}})
    for key, v in assets.items():
        if key not in (g.get("assets") or {}):
            ops.append({"op": "add", "path": f"/assets/{key}", "value": v})
    for si in range(min(len(secs), len(g["scenes"]))):
        have = {n["id"] for n in g["scenes"][si].get("nodes", [])}
        for n in nodes[si]:
            if n["id"] not in have:   # 다시 돌려도 겹치지 않게
                ops.append({"op": "add", "path": f"/scenes/{si}/nodes/-", "value": n})
        if cams[si] and not (g["scenes"][si].get("camera") or {}).get("keys"):
            ops.append({"op": "add", "path": f"/scenes/{si}/camera", "value": {"keys": sorted(cams[si], key=lambda q: q["t"])}})
    if not ops:
        print("넣을 것이 없습니다(이미 들어가 있음)")
        return
    tmp = ROOT / "data" / "workspace" / "tmp" / f"xray2graph-{a.id}.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(ops, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "core" / "scene_graph.py"), "patch", a.id, str(tmp), "--actor", "director"], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        sys.exit(f"설계도에 넣지 못했습니다: {r.stderr.strip() or r.stdout.strip()}")
    print(f"넣었습니다 ({len(ops)}개 고치기) — 편집기에서 S(스케치)로 애니메틱을 보세요. 참고 그림 자리는 최종 렌더 전에 바꿔야 합니다")


if __name__ == "__main__":
    main()
