#!/usr/bin/env python3
"""
장면 설계도(scenes/<id>.scene.json) — 영상 한 편의 유일한 진실. 에이전트들과 사용자가 같은 파일을 고친다.

  python3 scripts/scene_graph.py init <id>                    # 콘티로 설계도를 만든다(scene.js 가 있으면 장면마다 code 노드)
  python3 scripts/scene_graph.py show <id>                    # 장면 · 노드 요약
  python3 scripts/scene_graph.py validate <id>                # 스키마 검사 (schema/scene.schema.json)
  python3 scripts/scene_graph.py patch <id> <ops.json|-> --actor previs   # JSON Patch(add · replace · remove) + 소유권 · 잠금 검사
  python3 scripts/scene_graph.py compile <id>                 # → compositions/<id>/graph.js (미리보기 · 렌더가 읽음)

칸 소유권(고칠 수 있는 역할) — 다른 역할이 바꾸려 하면 거절된다. locked 노드는 user 만:
  keys · box · camera · start · end · layer · path      → previs · user · director
  gen/spec                                              → prompt · user · director
  gen/candidates · gen/chosen · gen/keyframe             → gen · user (chosen 은 critic 도)
  gen/review                                            → critic · user
  그 밖(장면 구조 · 노드 추가/삭제 · 글자 · 에셋)          → director · user
고칠 때마다 version 이 1 오르고, 직전 판은 scenes/<id>.history/v<n>.json 에 남는다(최근 20개). compile 은 patch 뒤 자동으로 한다.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / "scenes"
SCHEMA = ROOT / "schema" / "scene.schema.json"
KEEP = 20

FIELD_OWNERS = [   # (경로 조각 정규식, 고칠 수 있는 역할)
    (re.compile(r"/nodes/\d+/(keys|box|start|end|layer|path)(/|$)|/camera(/|$)"), {"previs", "user", "director"}),
    (re.compile(r"/gen/spec(/|$)"), {"prompt", "user", "director"}),
    (re.compile(r"/gen/chosen(/|$)"), {"gen", "critic", "user"}),
    (re.compile(r"/gen/(candidates|keyframe|model)(/|$)"), {"gen", "user"}),
    (re.compile(r"/gen/review(/|$)"), {"critic", "user"}),
]
STRUCTURE = {"director", "user"}
ACTORS = {"director", "previs", "prompt", "gen", "critic", "user"}


def path_of(sid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", sid):
        raise SystemExit(f"id 가 올바르지 않습니다: {sid}")
    return SCENES / f"{sid}.scene.json"


def load(sid: str) -> dict:
    p = path_of(sid)
    if not p.exists():
        raise SystemExit(f"설계도가 없습니다: {p.relative_to(ROOT)} — 먼저 init")
    return json.loads(p.read_text(encoding="utf-8"))


def validate(g: dict) -> list[str]:
    import jsonschema
    v = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '(맨 위)'}: {e.message}" for e in v.iter_errors(g)]
    ids = set()
    for si, s in enumerate(g.get("scenes", [])):
        for n in s.get("nodes", []):
            k = (si, n.get("id"))
            if k in ids:
                errs.append(f"scenes/{si}: 노드 id 중복 {n.get('id')}")
            ids.add(k)
            if n.get("asset") and n["asset"] not in (g.get("assets") or {}):
                errs.append(f"scenes/{si}/{n.get('id')}: 없는 에셋 {n['asset']}")
    return errs


def save(sid: str, g: dict, bump: bool = True):
    errs = validate(g)
    if errs:
        raise SystemExit("설계도 검사 실패:\n  " + "\n  ".join(errs[:20]))
    p = path_of(sid)
    if p.exists() and bump:   # 직전 판 보관
        h = SCENES / f"{sid}.history"
        h.mkdir(parents=True, exist_ok=True)
        old = json.loads(p.read_text(encoding="utf-8"))
        (h / f"v{old.get('version', 1)}.json").write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
        for f in sorted(h.glob("v*.json"), key=lambda x: int(x.stem[1:]))[:-KEEP]:
            f.unlink()
        g["version"] = int(old.get("version", 1)) + 1
    g["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    SCENES.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------- init
def cmd_init(a):
    sbp = ROOT / "storyboards" / f"{a.id}.json"
    if not sbp.exists():
        raise SystemExit(f"콘티가 없습니다: {sbp.relative_to(ROOT)}")
    if path_of(a.id).exists() and not a.force:
        raise SystemExit("설계도가 이미 있습니다 (--force 로 새로)")
    sb = json.loads(sbp.read_text(encoding="utf-8"))
    has_code = (ROOT / "compositions" / a.id / "scene.js").exists()
    t, scenes = 0.0, []
    for i, sc in enumerate(sb.get("scenes", [])):
        sec = float(sc.get("sec", 0))
        nodes = [{"id": "code", "kind": "code", "label": "화면 구성(scene.js)", "ref": f"compositions/{a.id}/scene.js#{i}", "owner": "director"}] if has_code else []
        scenes.append({"id": f"s{i + 1}", "role": sc.get("role", ""), "start": round(t, 3), "end": round(t + sec, 3), "narration": sc.get("narration", ""), "nodes": nodes})
        t += sec
    g = {"id": a.id, "version": 1, "fps": 30, "size": [1080, 1920], "fidelity": "final", "assets": {}, "scenes": scenes}
    save(a.id, g, bump=False)
    compile_graph(a.id)
    print(f"설계도 {path_of(a.id).relative_to(ROOT)} · 장면 {len(scenes)}개{' · scene.js 를 code 노드로' if has_code else ''}")


# ---------------------------------------------------------------- patch
def _ptr(path: str) -> list[str]:
    if not path.startswith("/"):
        raise ValueError(f"경로는 / 로 시작: {path}")
    return [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]


def _get(doc, parts):
    for p in parts:
        doc = doc[int(p)] if isinstance(doc, list) else doc[p]
    return doc


def apply_ops(g: dict, ops: list[dict]) -> dict:
    """JSON Patch 의 add · replace · remove (RFC 6902 일부). 실패하면 아무것도 바꾸지 않는다"""
    d = copy.deepcopy(g)
    for op in ops:
        parts = _ptr(op["path"]); parent = _get(d, parts[:-1]); last = parts[-1]
        kind = op["op"]
        if isinstance(parent, list):
            i = len(parent) if last == "-" else int(last)
            if kind == "add":
                parent.insert(i, op["value"])
            elif kind == "replace":
                parent[i] = op["value"]
            elif kind == "remove":
                parent.pop(i)
            else:
                raise ValueError(f"지원하지 않는 op: {kind}")
        else:
            if kind in ("add", "replace"):
                if kind == "replace" and last not in parent:
                    raise ValueError(f"없는 칸을 replace: {op['path']}")
                parent[last] = op["value"]
            elif kind == "remove":
                del parent[last]
            else:
                raise ValueError(f"지원하지 않는 op: {kind}")
    return d


def check_rights(g: dict, ops: list[dict], actor: str) -> list[str]:
    """소유권 · 잠금 — 거절 사유 목록"""
    bad = []
    for op in ops:
        path = op["path"]
        m = re.match(r"^/scenes/(\d+)/nodes/(\d+)", path)
        if m and actor != "user":
            try:
                node = g["scenes"][int(m.group(1))]["nodes"][int(m.group(2))]
            except (IndexError, KeyError):
                node = None
            if node and node.get("locked"):
                bad.append(f"{path}: 사용자가 잠근 노드({node.get('id')}) — user 만 고칠 수 있음")
                continue
        if re.search(r"/locked$", path) and actor != "user":
            bad.append(f"{path}: 잠금은 user 만")
            continue
        allowed = next((who for rx, who in FIELD_OWNERS if rx.search(path)), STRUCTURE)
        if actor not in allowed:
            bad.append(f"{path}: {actor} 는 이 칸을 고칠 수 없음 (가능: {', '.join(sorted(allowed))})")
    return bad


def cmd_patch(a):
    if a.actor not in ACTORS:
        raise SystemExit(f"actor 는 {', '.join(sorted(ACTORS))}")
    g = load(a.id)
    ops = json.loads(sys.stdin.read() if a.ops == "-" else Path(a.ops).read_text(encoding="utf-8"))
    if isinstance(ops, dict):
        ops = ops.get("ops", [ops])
    if a.base is not None and a.base != g.get("version"):
        raise SystemExit(f"설계도가 그사이 바뀌었습니다(지금 v{g.get('version')}, 보낸 쪽 v{a.base}) — 다시 읽고 고치세요")
    bad = check_rights(g, ops, a.actor)
    if bad:
        raise SystemExit("거절:\n  " + "\n  ".join(bad))
    try:
        ng = apply_ops(g, ops)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise SystemExit(f"패치를 적용할 수 없습니다: {e}")
    save(a.id, ng)
    compile_graph(a.id)
    print(json.dumps({"ok": True, "version": ng["version"]}, ensure_ascii=False))


# ---------------------------------------------------------------- compile
def compile_graph(sid: str) -> Path | None:
    """미리보기 · 렌더용: compositions/<id>/graph.js 에 데이터 노드만 담는다(code 노드는 scene.js 가 그린다).
    파일 이름이 scene.js 보다 앞(g < s)이라 어댑터가 먼저 붙인다."""
    g = load(sid)
    data_scenes = [[n for n in s.get("nodes", []) if n.get("kind") != "code"] for s in g["scenes"]]
    cams = [s.get("camera") if (s.get("camera") or {}).get("keys") else None for s in g["scenes"]]
    out = ROOT / "compositions" / sid / "graph.js"
    if not any(data_scenes) and not any(cams):
        if out.exists():
            out.unlink()
        return None
    assets = g.get("assets") or {}
    for nodes in data_scenes:   # 에셋 열쇠 → 경로 (런타임은 src 만 본다)
        for n in nodes:
            if n.get("asset") and not n.get("src"):
                n["src"] = assets[n["asset"]]["src"]
    payload = {"version": g["version"], "fidelity": g.get("fidelity", "final"), "scenes": [{"nodes": ns, **({"camera": cm} if cm else {})} for ns, cm in zip(data_scenes, cams)]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("/* 자동 생성: scripts/scene_graph.py compile — 직접 고치지 말 것 (scenes/<id>.scene.json 을 고친다) */\n"
                   f"window.FLUMA_GRAPH = {json.dumps(payload, ensure_ascii=False)};\n", encoding="utf-8")
    return out


def cmd_compile(a):
    p = compile_graph(a.id)
    print(p.relative_to(ROOT) if p else "데이터 노드 없음 — graph.js 없음(scene.js 만)")


def cmd_validate(a):
    errs = validate(load(a.id))
    print("통과" if not errs else "\n".join(errs))
    sys.exit(1 if errs else 0)


def cmd_show(a):
    g = load(a.id)
    print(f"{g['id']} v{g['version']} · {g.get('fidelity')} · 에셋 {len(g.get('assets') or {})}")
    for s in g["scenes"]:
        print(f"  {s['id']} {s.get('start')}~{s.get('end')}초 {s.get('role', '')}: " + ", ".join(f"{n['id']}({n['kind']}{'·잠금' if n.get('locked') else ''})" for n in s.get("nodes", [])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("init"); i.add_argument("id"); i.add_argument("--force", action="store_true"); i.set_defaults(fn=cmd_init)
    for n, fn in (("show", cmd_show), ("validate", cmd_validate), ("compile", cmd_compile)):
        x = sp.add_parser(n); x.add_argument("id"); x.set_defaults(fn=fn)
    p = sp.add_parser("patch"); p.add_argument("id"); p.add_argument("ops"); p.add_argument("--actor", required=True)
    p.add_argument("--base", type=int, help="고치기 시작한 판 번호 — 그사이 바뀌었으면 거절(덮어쓰기 방지)"); p.set_defaults(fn=cmd_patch)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
