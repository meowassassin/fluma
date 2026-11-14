#!/usr/bin/env python3
"""기준점(앵커) — 사용자가 "애플 감성"처럼 기준을 말하면, 그 광고의 실제 프레임을 고정하고 모든 시안을 거기에 맞대 본다.

2026-11-09: '애플 감성'을 요청했는데 방향이 열 번 넘게 흘러가(샤넬 → 흰 스튜디오 → … → 회전초밥) 스톡 영상 같은 결과가 나왔다.
애플 광고를 분석해 놓고도 우리 안이 그 문법과 맞는지 재는 단계가 없었다. 이제:
  1) set   — 기준 영상(분해해 둔 레퍼런스)의 샷 프레임을 골라 data/compositions/<id>/anchor/ 에 두고,
             지금 설정된 에이전트(Claude Code · Codex · Antigravity)가 그 프레임들을 보고 '시각 문법'(배경 · 빛 · 색 · 피사체 배치 · 카메라 · 글자 · 속도 · 피할 것)과
             요약을 뽑아 콘티 direction.anchor 에 적는다
  2) 그 뒤 콘티 · 방향(배경색 · 글자 · 리듬)은 이 문법을 따르고, 초안 비평은 기준 프레임과 같은 세계인지 점수를 낸다(완전 로컬 — 생성 없음)
  3) match — 느낌 시안 · 키프레임 · 초안 프레임을 기준 프레임과 나란히 놓고 0~10 점 + 맞은 것 · 다른 것 · 고칠 영어 문구.
             6점 미만은 사용자에게 보여 주기 전에 고친다(보여 줄 때는 점수를 같이)

  python3 engine/look/anchor.py set <콘티 id> <레퍼런스 id ...> --words "애플 감성 — 제품 하나, 여백, 정밀한 빛"
  python3 engine/look/anchor.py match <콘티 id> <그림 ...>
  python3 engine/look/anchor.py show <콘티 id>
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))

XRAY = ROOT / "data" / "public" / "trends" / "xray"
PASS = 6.0          # 이 점수 미만은 기준과 멀다 — 보여 주기 전에 고친다

RULES_Q = """이 프레임들은 사용자가 '{words}' 의 기준으로 고른 실제 광고 영상들의 장면이다(영상 id: {refs}).
우리 영상(주제는 다르다)이 이 느낌을 내려면 무엇을 지켜야 하는지, 내용이 아니라 '시각 문법'만 뽑아라. 프레임에서 실제로 보이는 것만, 구체적으로(색은 hex 근사, 빛은 방향 · 질).
JSON:
{{
 "summary": "한 문장 — 이 기준의 핵심 감각",
 "background": "배경 · 공간(예: 이음매 없는 흰 무한 배경, 깊은 검정)",
 "palette": ["#hex 이름", "…"],
 "light": "빛의 방향 · 질 · 대비",
 "subject": "피사체 배치 · 개수 · 여백(화면에서 차지하는 비율)",
 "camera": "구도 · 렌즈 느낌 · 움직임",
 "materials": "표면 · 재질 · 마감",
 "typography": "화면 글자(서체 계열 · 크기 · 위치 · 등장 방식) — 없으면 없음",
 "pacing": "컷 길이 · 전환",
 "avoid": ["이 기준에서 절대 안 나오는 것(예: 스톡 사진 같은 군중, 따뜻한 카페 조명, 하트 라테아트)"],
 "avoid_en": ["위 avoid 를 영어 명사구로(부정 칸용, 3~6개, 예: busy crowd, warm cafe lighting, latte art)"],
 "prompt_en": "그림 · 영상 생성 프롬프트 앞에 그대로 붙일 영어 한 문단(60~90 단어): 배경 · 빛 · 색 · 배치 · 재질 · 카메라 · 마감. 브랜드 이름 · 로고 · 실제 제품명은 쓰지 않는다",
 "checklist": ["시안이 기준에 맞는지 예/아니오로 볼 항목 6~10개(한국어)"]
}}"""

MATCH_Q = """처음 {n_anchor}장은 기준(사용자가 고른 '{words}' 광고의 실제 프레임)이다. 그 뒤 {n_cand}장은 우리 시안이다(순서대로 #1 … #{n_cand}).
기준의 시각 문법: {rules}
체크리스트: {checklist}
각 시안을 기준과 나란히 보고 깐깐하게 채점하라 — 내용(주제)이 다른 건 괜찮고, 배경 · 빛 · 색 · 배치 · 재질 · 카메라 · 마감 · 글자 감각이 같은 세계인지 본다. 스톡 사진 · 흔한 광고 같으면 낮게.
JSON: {{"items": [{{"i": 1, "score": 0~10, "hits": ["맞은 것"], "misses": ["기준과 다른 것 — 구체적으로"], "fix_en": "다시 그릴 때 프롬프트에 넣을 영어 문구"}}], "best": 시안 번호}}"""


def _sb_path(sid: str) -> Path:
    p = Path(sid)
    return p if p.suffix == ".json" and p.exists() else ROOT / "data" / "storyboards" / f"{sid}.json"


def get(sb: dict) -> dict:
    a = (sb.get("direction") or {}).get("anchor")
    return a if isinstance(a, dict) else {}


def _pick_frames(rid: str, k: int) -> list[Path]:
    """분해해 둔 샷 키프레임에서 고르게 k 장(길게 머문 샷 먼저)"""
    d = XRAY / rid
    x = json.loads((d / "xray.json").read_text("utf-8")) if (d / "xray.json").exists() else {}
    shots = [s for s in x.get("shots") or [] if s.get("frame")]
    shots.sort(key=lambda s: -(float(s.get("end", 0)) - float(s.get("start", 0))))
    pick = sorted(shots[:max(k * 2, k)], key=lambda s: float(s.get("start", 0)))
    step = max(1, len(pick) // k) if pick else 1
    out = [ROOT / "data" / "public" / s["frame"] for s in pick[::step]][:k]
    if not out:
        out = sorted((d / "shots").glob("*.jpg"))[:k] if (d / "shots").exists() else []
    return [p for p in out if p.exists()]


def _pick_clips(rid: str, k: int) -> list[Path]:
    """분해해 둔 원본 영상(video.mp4)이 있으면 대표 샷 구간을 .mp4 클립으로 잘라 돌려주고, 없으면 _pick_frames 로 내린다"""
    d = XRAY / rid
    vid = d / "video.mp4"
    if not vid.exists():
        return _pick_frames(rid, k)
    x = json.loads((d / "xray.json").read_text("utf-8")) if (d / "xray.json").exists() else {}
    shots = [s for s in x.get("shots") or [] if s.get("end", 0) > s.get("start", 0)]
    if not shots:
        return [vid]
    shots.sort(key=lambda s: -(float(s.get("end", 0)) - float(s.get("start", 0))))
    pick = sorted(shots[:max(k * 2, k)], key=lambda s: float(s.get("start", 0)))
    step = max(1, len(pick) // k) if pick else 1
    cdir = d / "clips"
    cdir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for idx, s in enumerate(pick[::step][:k], start=1):
        st = float(s.get("start", 0))
        dur = min(6.0, max(1.0, float(s.get("end", st + 2)) - st))
        cp = cdir / f"shot_{idx:02d}_{int(st * 10):04d}.mp4"
        if not cp.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", str(st), "-i", str(vid), "-t", str(dur), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(cp)],
                capture_output=True,
                check=False,
            )
        if cp.exists():
            out.append(cp)
    return out or _pick_frames(rid, k)


def set_anchor(sid: str, refs: list[str], words: str, per: int = 4) -> dict:
    import eyes
    p = _sb_path(sid)
    sb = json.loads(p.read_text("utf-8"))
    dst = ROOT / "data" / "compositions" / sb["id"] / "anchor"
    dst.mkdir(parents=True, exist_ok=True)
    frames: list[str] = []
    per = max(2, min(per, 12 // max(1, len(refs))))
    for rid in refs:
        got = _pick_frames(rid, per)
        if not got:
            raise SystemExit(f"{rid}: 분해한 프레임이 없습니다 — 먼저 python3 engine/research/analyze_ref.py {rid}")
        for f in got:
            c = dst / f"{rid}-{f.name}"
            shutil.copy2(f, c)
            frames.append(c.relative_to(ROOT).as_posix())
    r = eyes.ask_images([ROOT / f for f in frames], RULES_Q.format(words=words, refs=", ".join(refs)), json_mode=True)
    rules = r.get("json") or {}
    if not (rules.get("summary") or rules.get("background")):
        raise SystemExit(f"{r.get('runtime')} 가 기준 문법을 내지 못했습니다: {str(r.get('text'))[:300]}")
    a = {"words": words, "refs": refs, "frames": frames, "rules": rules, "runtime": r.get("runtime"), "model": r.get("model")}
    sb.setdefault("direction", {})["anchor"] = a
    p.write_text(json.dumps(sb, ensure_ascii=False, indent=1), "utf-8")
    return a


def match(sid_or_sb, images: list[str]) -> dict | None:
    """시안들을 기준 프레임과 견준다 → {"items": [{i, score, hits, misses, fix_en, file}], "best"}. 기준점이 없으면 None"""
    import eyes
    sb = sid_or_sb if isinstance(sid_or_sb, dict) else json.loads(_sb_path(sid_or_sb).read_text("utf-8"))
    a = get(sb)
    if not a.get("frames") or not images:
        return None
    anchors = [f for f in a["frames"] if (ROOT / f).exists()][:6]
    rules = {k: v for k, v in (a.get("rules") or {}).items() if k not in ("checklist", "prompt_en")}
    q = MATCH_Q.format(n_anchor=len(anchors), n_cand=len(images), words=a.get("words", ""),
                       rules=json.dumps(rules, ensure_ascii=False), checklist=json.dumps((a.get("rules") or {}).get("checklist") or [], ensure_ascii=False))
    r = eyes.ask_images([ROOT / f for f in anchors] + [Path(x) if Path(x).is_absolute() else ROOT / x for x in images], q, json_mode=True)
    d = r.get("json") or {}
    items = d.get("items") or []
    for it in items:
        try:
            it["file"] = str(images[int(it.get("i", 0)) - 1])
        except (ValueError, IndexError):
            pass
    return {"items": items, "best": d.get("best"), "pass": PASS}


def report(m: dict | None) -> list[str]:
    """match 결과 → 사람이 읽을 줄(에이전트가 그대로 보여 준다)"""
    if not m:
        return []
    out = []
    for it in sorted(m["items"], key=lambda x: -float(x.get("score") or 0)):
        sc = float(it.get("score") or 0)
        mark = "✓" if sc >= PASS else "✗"
        out.append(f"{mark} {Path(it.get('file', '?')).name} 기준점 {sc:g}/10 — 다른 점: {' · '.join(it.get('misses') or []) or '없음'}"
                   + (f" | 고칠 문구: {it['fix_en']}" if sc < PASS and it.get("fix_en") else ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s_ = sub.add_parser("set"); s_.add_argument("sid"); s_.add_argument("refs", nargs="+"); s_.add_argument("--words", required=True); s_.add_argument("--per", type=int, default=4)
    m_ = sub.add_parser("match"); m_.add_argument("sid"); m_.add_argument("images", nargs="+")
    w_ = sub.add_parser("show"); w_.add_argument("sid")
    a = ap.parse_args()
    if True:
        if a.cmd == "set":
            r = set_anchor(a.sid, a.refs, a.words, a.per)
            print(json.dumps(r["rules"], ensure_ascii=False, indent=1))
            print("```media\n" + "\n".join(f"{f} | 기준 {Path(f).name.split('-')[0]}" for f in r["frames"]) + "\n```")
        elif a.cmd == "match":
            m = match(a.sid, a.images)
            if m is None:
                print("기준점이 없습니다 — 먼저 anchor.py set"); return 10
            print("\n".join(report(m)))
            print(json.dumps(m, ensure_ascii=False, indent=1))
        else:
            an = get(json.loads(_sb_path(a.sid).read_text("utf-8")))
            if not an:
                print("기준점 없음"); return 10
            print(json.dumps(an.get("rules"), ensure_ascii=False, indent=1))
            print("```media\n" + "\n".join(f"{f} | 기준" for f in an.get("frames") or []) + "\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
