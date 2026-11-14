#!/usr/bin/env python3
"""보기 — 영상 · 그림을 직접 보고 말로(예전 engine/providers/see.py 의 자리, OpenRouter 없이). 보는 눈은 지금 설정된 에이전트(eyes.py).
판단은 늘 에이전트가 한다 — 여기서는 본 것을 시각 근거와 함께 받아 파일로 남긴다.

**에이전트가 대화 중이면 먼저 직접 본다(빠르고 공짜)**:
  python3 engine/look/look.py sheet <영상|유튜브 id> [--from 초 --to 초]   → 시각이 적힌 프레임 모음 그림 경로 + 대사. 그 그림을 열어 본다.
**따로 맡길 때(긴 영상 · 서버 작업 · 구조화된 기록이 필요할 때)**:
  ask <영상|그림|유튜브 id ...> --q "질문" [--json] [--from --to]   무엇이든 묻기
  ref <쇼츠 id ...> [--force]       레퍼런스 이해 → xray.json 의 understanding(장면 · 훅 · 반전 · 편집 문법 · 자막 말투 · 소리 · 붙잡는 장치 · 뻔한 것 · 빌릴 것)
  cliches <콘티 id>                 레퍼런스 이해들 → 뻔함 지도 초안(data/workspace/concepts/<id>.cliches-draft.json, 에이전트가 고쳐 concepts 에)
  moments <영상|유튜브> --want "…" [--sec 3.5]   원하는 순간 → [{start, end, why, score}]
  critique <콘티 id> [--video 경로]  초안 비평 → data/workspace/critique/<id>.json
  clip <콘티> <재료 id>              퍼온 · 생성 클립이 장면 의도와 맞나
  image <그림> --want "…"           그림이 원하는 것과 맞나
보는 에이전트: 설정(에이전트) 그대로 — Claude Code · Codex · Antigravity. 바꾸려면 FLUMA_LOOK_RUNTIME=claude|codex|antigravity.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
import eyes  # noqa: E402

XRAY = eyes.XRAY

REF_Q = """이 쇼츠를 편집자 눈으로 처음부터 끝까지 보고 아래 JSON 으로 답하라. 측정값(아래)과 다르게 보이면 본 것을 우선하고 notes 에 적어라.
측정값: {measured}
{{
 "summary": "한 문장 — 무엇을 어떻게 보여 주는 영상인가",
 "format": "형식(순위 모음 · 정보 · 광고 · 브이로그 · 반응 · 시연 · 스토리 …)과 근거",
 "hook": {{"t": [시작, 끝], "device": "첫 3초에 붙잡는 장치", "why": "왜 넘기지 않게 되나"}},
 "beats": [{{"t": [시작, 끝], "what": "화면에서 일어나는 일", "camera": "구도 · 움직임", "text_on_screen": "화면 글자 그대로", "sound": "말 · 음악 · 효과음", "emotion": "시청자 감정"}}],
 "turns": [{{"t": 초, "kind": "반전 · 웃음 · 정보 · 감정", "how": "어떻게 터지나(타이밍 · 대비 · 자막 · 소리)"}}],
 "editing": {{"pace": "컷 리듬", "cuts": "컷 · 전환 방식", "zoom_motion": "확대 · 흔들림 · 속도 변화", "captions": {{"position": "위치", "style": "모양 · 색 · 크기", "tone": "말투(예: 동물 속마음 · ㅋㅋ · 반말)", "timing": "말 · 동작과 언제 맞물리나"}}}},
 "audio": {{"music": "곡 느낌 · 박자 · 컷과 맞물림(측정값 BPM 참고)", "sfx": "효과음과 쓰인 순간", "voice": "나레이션 · 원음 · 말투"}},
 "motion_design": {{"animation_style": "2D · 3D · 키네틱 타이포 · 플랫 · 콜라주 · 실사 컷아웃 등", "movement": "속도 · 이징 · 바운스 · 부드러운지 스냅감 있는지", "transitions": "컷 · 와이프 · 모핑 · 줌 등 실제로 쓴 것과 시각",
   "palette": ["#hex 이름(배경 · 강조 · 글자)"], "background": "배경 질감 · 색", "typography": "굵기 · 크기 · 위치 · 등장 애니메이션", "camera": "고정 · 줌 · 팬 · 흔들림",
   "pacing": "빠름 · 차분 · 드라마틱과 근거", "sound_feel": "휘익 · 클릭 · 베이스 히트 · 음악 느낌",
   "style_en": "이 시각 스타일을 영상 생성 프롬프트에 넣을 영어 한 문단(40~70단어) — 내용 · 인물 · 브랜드 이름 없이 움직임 · 색(hex) · 타이포 · 질감 · 전환만"}},
 "retention": ["끝까지 보게 하는 장치들(시각 포함)"],
 "loop_or_end": "끝 처리(루프 · 질문 · 반전 · CTA)",
 "cliches": ["이 분야에서 흔히 보이는 것 중 이 영상이 한 것"],
 "fresh": ["이 영상만의 다른 점"],
 "borrow": ["우리 영상에 빌릴 문법(내용 말고 리듬 · 장치)"],
 "do_not_copy": ["베끼면 안 되는 것(내용 · 대사 · 고유 캐릭터)"],
 "notes": "그 밖에 편집자가 알아야 할 것"
}}"""


def _stamp(r: dict) -> dict:
    return {"_runtime": r.get("runtime"), "_model": r.get("model"), "_at": dt.datetime.now().isoformat(timespec="seconds")}


def _measured(x: dict) -> str:
    shots = x.get("shots") or []
    cuts = [round(float(s.get("start", 0)), 2) for s in shots]
    tx = " / ".join(sorted({str(t.get("text", "")) for t in (x.get("text") or [])[:40]}))[:400]
    return json.dumps({"길이초": (x.get("video") or {}).get("duration"), "컷 시작": cuts[:40], "화면 글자": tx,
                       "BPM": (x.get("sound") or {}).get("bpm"), "편집 레시피": x.get("recipe")}, ensure_ascii=False)[:4000]


def ref(rid: str, force: bool = False) -> dict:
    f = XRAY / rid / "xray.json"
    x = json.loads(f.read_text("utf-8")) if f.exists() else {}
    if x.get("understanding") and not force:
        return x["understanding"]
    r = eyes.ask([rid], REF_Q.format(measured=_measured(x) if x else "(측정 없음)"), json_mode=True, tag=f"ref-{rid}")
    u = {**(r.get("json") or {"raw": r["text"]}), **_stamp(r)}
    if f.exists():
        x = json.loads(f.read_text("utf-8"))            # 보는 동안 다른 단계가 고쳤을 수 있다 — 다시 읽고 이 칸만
        x["understanding"] = u
        f.write_text(json.dumps(x, ensure_ascii=False, indent=1), "utf-8")
    else:
        (XRAY / rid).mkdir(parents=True, exist_ok=True)
        (XRAY / rid / "understanding.json").write_text(json.dumps(u, ensure_ascii=False, indent=1), "utf-8")
    return u


def understanding(rid: str) -> dict | None:
    f = XRAY / rid / "xray.json"
    if f.exists():
        u = json.loads(f.read_text("utf-8")).get("understanding")
        if u:
            return u
    g = XRAY / rid / "understanding.json"
    return json.loads(g.read_text("utf-8")) if g.exists() else None


def _sb(sid_or_path: str) -> dict:
    p = Path(sid_or_path)
    if not p.suffix:
        p = ROOT / "data" / "storyboards" / f"{sid_or_path}.json"
    elif not p.is_absolute():
        p = ROOT / p
    return json.loads(p.read_text("utf-8"))


def cliches(sid: str) -> dict:
    """레퍼런스 이해들 → 뻔함 지도 초안(코드가 판정하지 않는다 — 본 것을 묶고, 에이전트가 고친다). 그림 없이 글로만"""
    sb = _sb(sid)
    us = {r: understanding(r) for r in sb.get("reference") or []}
    us = {k: v for k, v in us.items() if v}
    if not us:
        raise SystemExit("레퍼런스 이해가 없습니다 — 먼저 look.py ref <쇼츠 id>")
    q = ("아래는 같은 분야 쇼츠들을 본 기록이다. '이 분야에서 다들 하는 것(뻔한 것)'을 묶어라 — 구조 · 첫장면 · 제목 · 화면 · 말투 · 소리 종류마다. "
         "각각 실제로 한 영상 id 를 seen_in 에. 그리고 아무도 안 한 빈자리(기회)도 적어라.\n"
         'JSON: {"cliches": [{"kind": "구조|첫장면|제목|화면|말투|소리", "what": "…", "seen_in": ["id"]}], "gaps": ["…"]}\n\n'
         + json.dumps(us, ensure_ascii=False)[:60000])
    r = eyes.ask_images([], q, json_mode=True)
    d = {**(r.get("json") or {"raw": r["text"]}), **_stamp(r)}
    out = ROOT / "data" / "workspace" / "concepts" / f"{sid}.cliches-draft.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    return d


def moments(src: str, want: str, sec: float | None = None, t0: float = 0.0, t1: float | None = None) -> list[dict]:
    q = (f"이 영상에서 다음에 맞는 순간을 모두 찾아라: {want}\n"
         + (f"각 구간은 {sec:g}초 안팎으로. " if sec else "")
         + "프레임 칸의 시각과 대사 시각을 근거로 초 단위로 답한다.\n"
         + 'JSON: {"moments": [{"start": 초, "end": 초, "why": "무엇이 보이고 들리나", "score": 0~1}]} — score 높은 순.')
    r = eyes.ask([src], q, json_mode=True, t0=t0, t1=t1, tag="moments")
    return ((r.get("json") or {}).get("moments")) or []


def critique(sid: str, video: str | None = None) -> dict:
    sb = _sb(sid)
    sid = sb["id"]
    outs = [ROOT / "data" / "out" / n for n in (f"{sid}-editor.mp4", f"{sid}-craft-Scenes.mp4", f"{sid}-craft-Scenes-draft.mp4", f"{sid}.mp4", f"{sid}-draft.mp4")]
    v = Path(video) if video else max((o for o in outs if o.exists()), key=lambda o: o.stat().st_mtime, default=None)   # 가장 최근 렌더(초안 포함)
    if not v or not Path(v).exists():
        raise SystemExit("초안 영상이 없습니다 — 먼저 render.py --draft (또는 --video 경로)")
    refs = {r: understanding(r) for r in sb.get("reference") or []}
    dr = sb.get("direction") or {}
    ctx = {"intent": sb.get("intent"), "concept": sb.get("concept"), "feel": (dr.get("feel") or {}).get("name") if isinstance(dr.get("feel"), dict) else dr.get("feel"),
           "planned_direction": {k: dr.get(k) for k in ("note", "transition", "motion", "font_title", "color_bg", "color_text") if dr.get(k)},
           "scenes": [{"i": i + 1, "sec": s.get("sec"), "beat": s.get("beat"), "narration": s.get("narration"), "caption": s.get("caption"),
                       "screen": s.get("screen"), "on_screen_text": s.get("hook_text") or s.get("text") or s.get("title"),
                       "materials": [{k: m.get(k) for k in ("type", "id", "role", "prompt", "note", "text") if m.get(k)} for m in s.get("materials") or [] if isinstance(m, dict)]}
                      for i, s in enumerate(sb.get("scenes") or [])],
           "reference_understanding": {k: {kk: (u or {}).get(kk) for kk in ("hook", "editing", "turns", "retention", "borrow")} for k, u in refs.items()}}
    q = ("이 초안 쇼츠를 깐깐한 편집자로 보고 비평하라. 의도 · 콘셉트 · 레퍼런스에서 빌리기로 한 문법과 대조한다. "
         "먼저 계획(planned_direction.note · 장면 materials · 화면 글자)이 화면에 실제로 나왔는지 장면마다 확인하고, 빠진 것(예: 계획한 전환 · 글자 · 연출이 없음)은 severity high 로 적는다. "
         "가공 없이 붙인 웹 화면(브라우저 머리띠 · 주소 · 사업자 정보 · 흰 바닥글 · 빈 여백), 톤이 안 맞는 컷, 정지된 로고도 짚는다. "
         "넘기게 되는 순간, 어색한 타이밍(자막 · 말 · 컷 · 소리), 안 보이거나 읽기 어려운 글자, 화면이 멈춘 곳, 뻔한 곳, 느낌이 섞인 곳을 시각과 함께.\n"
         'JSON: {"overall": "한 문단", "watch_through": "끝까지 볼 확률과 이유", "issues": [{"t": [시작, 끝], "scene": 장면 번호, "what": "무엇이", '
         '"why": "왜 문제", "fix": "어떻게 고치나(구체적으로)", "severity": "high|mid|low"}], "keep": ["좋아서 남길 것"]}\n\n'
         + json.dumps(ctx, ensure_ascii=False)[:20000])
    an = dr.get("anchor") if isinstance(dr.get("anchor"), dict) else {}
    frames = [f for f in an.get("frames") or [] if (ROOT / f).exists()][:4]
    if frames:      # 기준점: 사용자가 고른 기준 프레임과 같은 세계인지도 본다
        q += ("\n\n프레임 모음 뒤에 붙은 그림들은 사용자가 '" + str(an.get("words") or "") + "' 의 기준으로 고른 실제 영상 프레임이다. "
              "초안이 그 시각 문법(" + json.dumps({k: (an.get("rules") or {}).get(k) for k in ("background", "light", "palette", "subject", "typography")}, ensure_ascii=False)
              + ")과 얼마나 같은 세계인지 JSON 에 \"anchor\": {\"score\": 0~10, \"misses\": [\"기준과 다른 것\"]} 로 더하라. 6 미만이면 그 차이를 issues 에 high 로.")
    r = eyes.ask([str(v), *frames], q, json_mode=True, tag=f"critique-{sid}")
    d = {**(r.get("json") or {"raw": r["text"]}), **_stamp(r),
         "_video": Path(v).resolve().relative_to(ROOT).as_posix() if Path(v).resolve().is_relative_to(ROOT) else str(v)}
    out = ROOT / "data" / "workspace" / "critique" / f"{sid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    return d


def check_clip(sb: dict, mid: str) -> dict:
    m = next((dict(m) for sc in sb.get("scenes") or [] for m in sc.get("materials") or [] if isinstance(m, dict) and m.get("id") == mid), None)
    if not m:
        raise SystemExit(f"재료 {mid} 가 콘티에 없습니다")
    from craft.materials import find_upload
    f = find_upload(sb["id"], {**m, "type": "video"}) or (ROOT / m["src"] if m.get("src") else None)
    if not f or not Path(f).exists():
        raise SystemExit(f"{mid}: 클립이 아직 없습니다")
    spec = {k: m.get(k) for k in ("what", "want", "in", "out", "query") if m.get(k)}
    q = ("이 클립(퍼온 클립 · 스톡 · 녹화 · 생성)이 장면 의도와 맞는지 보라. 의도: " + json.dumps(spec, ensure_ascii=False)
         + '\nJSON: {"match": 0~1, "issues": [{"t": 초, "what": "다른 점 · 어색함 · 잘림 · 글자", "fix": "어느 구간을 쓰거나 무엇으로 바꿀지"}], "usable": [시작, 끝]}')
    return eyes.ask([str(f)], q, json_mode=True, tag=f"clip-{mid}").get("json") or {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s_ = sub.add_parser("sheet"); s_.add_argument("item")
    a_ = sub.add_parser("ask"); a_.add_argument("items", nargs="+"); a_.add_argument("--q", required=True); a_.add_argument("--json", action="store_true")
    r_ = sub.add_parser("ref"); r_.add_argument("ids", nargs="+"); r_.add_argument("--force", action="store_true")
    c_ = sub.add_parser("cliches"); c_.add_argument("sid")
    m_ = sub.add_parser("moments"); m_.add_argument("src"); m_.add_argument("--want", required=True); m_.add_argument("--sec", type=float)
    k_ = sub.add_parser("critique"); k_.add_argument("sid"); k_.add_argument("--video")
    l_ = sub.add_parser("clip"); l_.add_argument("storyboard"); l_.add_argument("mid")
    i_ = sub.add_parser("image"); i_.add_argument("image"); i_.add_argument("--want", required=True)
    for x in (s_, a_, m_):
        x.add_argument("--from", dest="t0", type=float, default=0.0); x.add_argument("--to", dest="t1", type=float)
    a = ap.parse_args()
    if a.cmd == "sheet":
        d = eyes.WORK / "sheet" / (eyes._yt(a.item) or Path(a.item).stem)
        imgs, extra = eyes.resolve([a.item], d, a.t0, a.t1)
        print("\n".join(i.relative_to(ROOT).as_posix() if i.is_relative_to(ROOT) else str(i) for i in imgs))
        print(json.dumps(extra, ensure_ascii=False))
        print("→ 위 그림을 열어 본다(칸 왼쪽 위 = 시각). 대사는 시각과 함께 위 JSON.")
    elif a.cmd == "ask":
        r = eyes.ask(a.items, a.q, a.json, a.t0, a.t1)
        print(json.dumps(r.get("json"), ensure_ascii=False, indent=1) if a.json and r.get("json") is not None else r["text"])
        print(f"[보기] {r['runtime']} · {r['model']}", file=sys.stderr)
    elif a.cmd == "ref":
        for i in a.ids:
            u = ref(i, a.force)
            print(json.dumps({"id": i, "summary": u.get("summary"), "hook": u.get("hook"), "borrow": u.get("borrow"), "runtime": u.get("_runtime")}, ensure_ascii=False))
    elif a.cmd == "cliches":
        print(json.dumps(cliches(a.sid), ensure_ascii=False, indent=1))
    elif a.cmd == "moments":
        print(json.dumps(moments(a.src, a.want, a.sec, a.t0, a.t1), ensure_ascii=False, indent=1))
    elif a.cmd == "critique":
        d = critique(a.sid, a.video)
        for it in d.get("issues") or []:
            print(f"[{it.get('severity', '?')}] {it.get('t')} 장면 {it.get('scene')}: {it.get('what')} — {it.get('fix')}")
        print(f"→ data/workspace/critique/{_sb(a.sid)['id']}.json")
    elif a.cmd == "clip":
        print(json.dumps(check_clip(_sb(a.storyboard), a.mid), ensure_ascii=False, indent=1))
    elif a.cmd == "image":
        q = f"이 그림이 다음과 맞는지 보라: {a.want}\n" + 'JSON: {"match": 0~1, "hits": ["맞은 것"], "misses": ["다른 것 — 구체적으로"], "fix": "고칠 점"}'
        r = eyes.ask([a.image], q, json_mode=True, tag="image")
        print(json.dumps(r.get("json") or {"raw": r["text"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
