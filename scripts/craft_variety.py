#!/usr/bin/env python3
"""영상마다 다른 형태 · 디자인이 나오게 — 레시피(검증된 Craft 명령 조합) 고르기 · 최근 영상과 겹침 검사 · 레시피 쌓기.
에이전트가 익숙한 조합만 되풀이하는 편향을 막는다(기능 목록 · 검색은 scripts/craft_catalog.py).

  python3 scripts/craft_variety.py suggest "<장면 용도>" [--id <영상 id>] [--n 6]   # 최근에 안 쓴 레시피 먼저 + 안 써 본 기능
  python3 scripts/craft_variety.py check storyboards/<id>.json [--recent 5]          # 겹침 · 반복 경고(V 규칙, 권고)
  python3 scripts/craft_variety.py history [--recent 5]                               # 최근 영상들이 쓴 재료 종류 · 레시피 · 기능
  python3 scripts/craft_variety.py save <영상 id> <재료 id> --name <이름> --purpose a,b --look x,y [--desc "…"]
  python3 scripts/craft_variety.py list                                                # 레시피 목록

레시피: .claude/skills/crafts/recipes/<이름>.json — {name, app, desc, purpose[], look[], features[], slots[], material{type:"craft",…}, preview}
콘티에서 레시피를 쓰려면 재료에 "recipe": "<이름>" 과 바꿀 칸(slots 의 at → 값)을 "fill" 로 준다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / ".claude" / "skills" / "crafts" / "recipes"
sys.path.insert(0, str(ROOT / "scripts"))


def recipes() -> list[dict]:
    out = []
    for f in sorted(REC.glob("*.json")):
        try:
            out.append(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    return out


def _sb(p: Path) -> dict:
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def signature(sb: dict) -> dict:
    """콘티 하나가 쓰는 것 — 재료 종류 · 레시피 · craft 명령 · 형식 · 느낌(레시피 look)"""
    by_name = {r["name"]: r for r in recipes()}
    types, recs, feats, looks, seq = set(), set(), set(), set(), []
    for sc in sb.get("scenes") or []:
        row = []
        for m in sc.get("materials") or []:
            t = m.get("type") or "?"
            types.add(t)
            r = m.get("recipe")
            if r:
                recs.add(r)
                looks.update((by_name.get(r) or {}).get("look") or [])
                feats.update(f"{(by_name.get(r) or {}).get('app')}:{x}" for x in (by_name.get(r) or {}).get("features") or [])
            if t == "craft":
                feats.update(f"{m.get('app')}:{s.get('id')}" for s in m.get("steps") or [] if isinstance(s, dict))
            row.append(r or t)
        seq.append(tuple(row))
    # 렌더된 영상이면 실제로 쓴 기능도(재료 · 단계 기록)
    sid = sb.get("id")
    if sid and (ROOT / "compositions" / sid).exists():
        import craft_catalog as cc
        cc.COVER_GLOB = f"compositions/{sid}/craft/**/*.json"
        for app, fs in cc.used().items():
            feats.update(f"{app}:{k}" for k in fs)
    return {"id": sid, "format": sb.get("format") or "", "types": types, "recipes": recs, "features": feats, "looks": looks, "seq": seq}


def recent(exclude: str | None = None, k: int = 5) -> list[dict]:
    fs = sorted((ROOT / "storyboards").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in fs:
        sb = _sb(f)
        if not sb.get("scenes") or sb.get("id") == exclude or f.stem == exclude:
            continue
        out.append(signature(sb))
        if len(out) >= k:
            break
    return out


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def check(sb: dict, k: int = 5) -> list[tuple[str, str]]:
    """권고만(실패 아님) — 같은 것만 되풀이하는 영상을 미리 알린다"""
    me, rows = signature(sb), []
    scenes = sb.get("scenes") or []
    # V41 한 영상 안 다양성: 장면 5개 이상인데 재료 종류 3가지 미만
    if len(scenes) >= 5 and len(me["types"] - {"text", "stat"}) < 3:
        rows.append(("V41", f"재료 종류가 {len(me['types'] - {'text', 'stat'})}가지뿐입니다({', '.join(sorted(me['types']))}) — craft_variety.py suggest 로 다른 형태(구조도 · 목업 · 주석 · 3D · 문서 …)를 섞으세요"))
    # V42 이어지는 장면이 같은 재료 구성
    for i in range(1, len(me["seq"])):
        if me["seq"][i] and me["seq"][i] == me["seq"][i - 1]:
            rows.append(("V42", f"{i}·{i + 1}장면이 같은 구성({', '.join(me['seq'][i])})입니다 — 둘 중 하나는 다른 레시피 · 배치로"))
    past = recent(me["id"], k)
    sig = me["types"] | me["recipes"] | me["features"]
    # V43 최근 영상과 너무 비슷
    for p in past:
        j = _jac(sig, p["types"] | p["recipes"] | p["features"])
        if j >= 0.7 and len(sig) >= 4:
            rows.append(("V43", f"최근 영상 {p['id']} 와 구성이 {int(j * 100)}% 겹칩니다 — 레시피 · 효과 · 배경 · 글자 움직임을 바꾸세요"))
    # V44 새로 쓰는 것 없음
    seen = set().union(*[p["recipes"] | p["features"] for p in past]) if past else set()
    fresh = (me["recipes"] | me["features"]) - seen
    if past and not fresh:
        rows.append(("V44", "최근 영상들이 안 쓴 레시피 · 기능이 하나도 없습니다 — 적어도 한 장면은 새 레시피나 craft_catalog.py search 로 찾은 새 기능으로"))
    # V45 느낌 반복
    if past and me["looks"] and me["looks"] <= set().union(*[p["looks"] for p in past[:2]]):
        rows.append(("V45", f"느낌({', '.join(sorted(me['looks']))})이 바로 전 영상들과 같습니다 — 다른 look 의 레시피를 섞어 보세요"))
    return rows


def suggest(purpose: str, sid: str | None, n: int = 6) -> tuple[list[tuple[float, dict]], list[tuple[float, dict]]]:
    words = [w.lower() for w in re.findall(r"[\w가-힣]+", purpose)]
    past = recent(sid, 5)
    used_r = {r for p in past for r in p["recipes"]}
    used_f = {f for p in past for f in p["features"]}
    scored = []
    for r in recipes():
        text = " ".join([r["name"], r.get("desc", ""), *r.get("purpose", []), *r.get("look", [])]).lower()
        s = sum(2.0 if w in r.get("purpose", []) else 1.0 for w in words if w in text)
        if not s:
            continue
        s += 0 if r["name"] in used_r else 1.5          # 최근에 안 쓴 것 먼저
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    import craft_catalog as cc
    explore = [(s, row) for s, row in cc.search(purpose, n=40) if f"{row['app']}:{row['id']}" not in used_f][:n]
    return scored[:n], explore


def save(sid: str, mid: str, name: str, purpose: list[str], look: list[str], desc: str) -> Path:
    mats = list((ROOT / "compositions" / sid / "craft" / "materials").glob(f"s*/{mid}.json"))
    if not mats:
        raise SystemExit(f"재료 기록이 없습니다: compositions/{sid}/craft/materials/sNN/{mid}.json (렌더 뒤에)")
    rec = json.loads(mats[0].read_text("utf-8"))
    spec = dict(rec.get("spec") or {})
    if spec.get("type") != "craft":
        raise SystemExit("craft 재료만 레시피로 저장합니다(고정 재료 종류는 이미 이름이 있다)")
    spec.pop("id", None)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", name):
        raise SystemExit("이름은 영어 소문자 · 숫자 · - 만")
    REC.mkdir(parents=True, exist_ok=True)
    out = {"name": name, "app": spec.get("app"), "desc": desc, "purpose": purpose, "look": look,
           "features": [s.get("id") for s in spec.get("steps") or []], "slots": [], "tested": sid, "material": spec}
    f = ROOT / rec["file"] if rec.get("file") else None
    if f and f.exists():
        pv = REC / f"{name}.jpg"
        args = ["ffmpeg", "-v", "error", "-y"] + (["-ss", "1"] if f.suffix == ".mp4" else []) + ["-i", str(f), "-frames:v", "1", "-vf", "scale=270:-2", "-q:v", "5", str(pv)]
        if subprocess.run(args, capture_output=True).returncode == 0:
            out["preview"] = pv.name
    p = REC / f"{name}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("purpose"); s.add_argument("--id"); s.add_argument("--n", type=int, default=6)
    c = sub.add_parser("check"); c.add_argument("storyboard"); c.add_argument("--recent", type=int, default=5)
    h = sub.add_parser("history"); h.add_argument("--recent", type=int, default=5)
    sv = sub.add_parser("save"); sv.add_argument("id"); sv.add_argument("mid"); sv.add_argument("--name", required=True)
    sv.add_argument("--purpose", default=""); sv.add_argument("--look", default=""); sv.add_argument("--desc", default="")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "list":
        for r in recipes():
            print(f"{r['name']:28s} {r['app']:12s} {','.join(r.get('purpose', [])):28s} {r.get('desc', '')[:60]}")
        return 0
    if a.cmd == "history":
        for p in recent(None, a.recent):
            print(f"{p['id']}  종류 {sorted(p['types'])}  레시피 {sorted(p['recipes']) or '-'}  기능 {len(p['features'])}개")
        return 0
    if a.cmd == "suggest":
        rs, ex = suggest(a.purpose, a.id, a.n)
        print("레시피(검증됨 · ★ = 최근 5편에 안 씀):")
        used = {r for p in recent(a.id, 5) for r in p["recipes"]}
        for _, r in rs:
            print(f"  {'★' if r['name'] not in used else ' '} {r['name']:26s} {r['app']:12s} {r.get('desc', '')[:70]}  미리보기: .claude/skills/crafts/recipes/{r.get('preview', '-')}")
        print("안 써 본 기능(검색 · type:craft 로 직접 짜기 — reference/<앱>.md 확인):")
        for _, row in ex:
            print(f"    {row['app']:12s} {row['id']:36s} {row['label'][:40]}")
        return 0
    if a.cmd == "check":
        sp = Path(a.storyboard)
        sb = _sb(sp if sp.is_absolute() else ROOT / sp)
        if not sb:
            print(f"콘티를 읽지 못했습니다: {a.storyboard}")
            return 1
        rows = check(sb, a.recent)
        for code, msg in rows:
            print(f"  {code} {msg}")
        print("다양성: 문제 없음" if not rows else f"다양성 권고 {len(rows)}개(실패 아님)")
        return 0
    p = save(a.id, a.mid, a.name, [x for x in a.purpose.split(",") if x], [x for x in a.look.split(",") if x], a.desc)
    print(f"레시피 저장: {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
