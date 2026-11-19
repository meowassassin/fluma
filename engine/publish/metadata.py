#!/usr/bin/env python3
"""유튜브 업로드 정보 — 영상이 완성되면 마지막에 제목 · 설명 · 해시태그 · 태그를 만든다(콘티 upload 칸).

화면 안 고정 제목(콘티 title)과 따로 둔다: 검색 · 추천에 뜨는 제목은 검색어를 앞에, 40자 안팎이 좋고
화면 제목은 짧은 문구가 좋다(2026-11-19 사용자: '알고리즘에 잘 뜨도록 자동으로 · 업로드 때 같이 전송').
업로드(engine/publish/upload_youtube.py · 스튜디오 게시 화면)는 이 칸을 기본값으로 쓴다.

  python3 engine/publish/metadata.py data/storyboards/<id>.json [--force]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
from result import fail, ok  # noqa: E402

TITLE_MAX = 45          # 쇼츠 피드 · 검색에서 잘리지 않는 길이(한국어)
DESC_FIRST = 100        # 설명 첫 줄 — 검색 결과 · 추천 아래에 보이는 부분
TAGS_CHARS = 450        # 유튜브 태그 합계 500자 한도(여유)

RULES = """너는 한국어 유튜브 쇼츠의 검색 · 추천 최적화 담당이다. 영상 내용(아래)을 바탕으로 업로드 정보를 만든다.
규칙(유튜브 공식 도움말 · 쇼츠 상위 영상 관찰):
- 제목: 40자 안팎(최대 45자). 사람들이 실제로 검색할 핵심어를 앞쪽에. 호기심(질문 · 반전 · 구체 숫자)을 주되 영상 내용과 정확히 맞게 — 낚시 · 과장 · 영상에 없는 약속 금지. 제목에 #Shorts · 해시태그 넣지 않는다. 이모지는 0~1개.
- 후보 5개는 각도가 서로 달라야 한다(질문형 · 숫자형 · 반전형 · 결과 먼저 · 대상 호명 등). best 는 그중 하나.
- 설명 첫 줄(100자 안): 핵심 검색어를 넣어 영상이 무엇을 알려 주는지 한 문장. 그다음 2~3줄 요약(영상 대사를 그대로 옮기지 않는다). 사실은 아래 '조사 사실'에 있는 것만.
- 해시태그 3~5개: 첫 3개가 제목 위에 보인다 — 주제 핵심어 2~3개 + #Shorts. 띄어쓰기 없이, 너무 넓은 것(#유튜브 #추천) 금지.
- 태그 10~15개: 한국어 검색어 위주 + 영어 1~3개, 표기 변형(띄어쓰기 · 영문) 포함.
출력은 JSON 하나: {"titles": ["…" ×5], "best": "…", "description": "첫 줄\\n\\n요약 2~3줄", "hashtags": ["#…"], "tags": ["…"], "why": "고른 이유 한 줄"}"""


def _facts(sid: str, sb: dict) -> list[str]:
    out = []
    for f in [ROOT / "data" / "research" / f"{sid}.json"]:
        try:
            for x in json.loads(f.read_text("utf-8")).get("facts") or []:
                out.append(f"{x.get('claim')} ({x.get('value')}) — {x.get('source')}")
        except (OSError, ValueError):
            pass
    return out[:12]


def _refs(sb: dict) -> list[str]:
    """레퍼런스 쇼츠 제목 · 조회수 — 같은 주제에서 잘 된 제목의 말투 참고"""
    out = []
    idx = ROOT / "data" / "public" / "trends" / "index.json"
    try:
        items = {x.get("id"): x for x in json.loads(idx.read_text("utf-8")).get("items") or []}
    except (OSError, ValueError):
        items = {}
    for rid in sb.get("reference") or []:
        x = items.get(rid) or {}
        if x.get("title"):
            out.append(f"{x['title']} · 조회 {x.get('views') or '?'}")
    return out[:5]


def _own() -> list[str]:
    """내 채널에 올린 영상의 제목 · 평균 시청률(publish.py feedback 이 남긴 것)"""
    out = []
    for f in sorted((ROOT / "data" / "public" / "trends" / "own").glob("*.json"))[-5:]:
        try:
            o = json.loads(f.read_text("utf-8"))
            out.append(f"{o.get('topic')} · 평균 시청 {o.get('avg_view_pct')}% · 조회 {o.get('views')}")
        except (OSError, ValueError):
            pass
    return out


def inputs(sb: dict) -> dict:
    sid = sb["id"]
    return {"on_screen_title": sb.get("title"), "format": sb.get("format"), "audience": sb.get("audience"),
            "intent": (sb.get("intent") or {}).get("summary"), "concept": sb.get("concept"),
            "script": sb.get("script") or " / ".join(str(s.get("narration") or "") for s in sb.get("scenes") or []),
            "captions": [s.get("caption") for s in sb.get("scenes") or [] if s.get("caption")],
            "facts": _facts(sid, sb), "reference_titles": _refs(sb), "my_channel": _own(), "language": sb.get("language") or "ko"}


def _clean_tag(t: str) -> str:
    return re.sub(r"[<>,#]", "", str(t)).strip()


def tidy(r: dict, sb: dict) -> dict:
    """길이 · 형식 맞추기(모델이 규칙을 넘겨도 업로드가 거절되지 않게)"""
    titles = [re.sub(r"\s*#\S+", "", str(t)).strip()[:TITLE_MAX] for t in (r.get("titles") or []) if str(t).strip()]
    best = re.sub(r"\s*#\S+", "", str(r.get("best") or (titles[0] if titles else sb.get("title") or ""))).strip()[:TITLE_MAX]
    tags_h = []
    for h in r.get("hashtags") or []:
        h = "#" + re.sub(r"[\s#]+", "", str(h))
        if len(h) > 1 and h.lower() not in {x.lower() for x in tags_h}:
            tags_h.append(h)
    if "#shorts" not in {x.lower() for x in tags_h}:
        tags_h.append("#Shorts")
    tags_h = tags_h[:5]
    tags, total = [], 0
    for t in r.get("tags") or []:
        t = _clean_tag(t)
        if t and t not in tags and total + len(t) + 1 <= TAGS_CHARS:
            tags.append(t); total += len(t) + 1
    return {"title": best, "titles": titles[:5], "description": str(r.get("description") or "").strip()[:4000],
            "hashtags": tags_h, "tags": tags[:15], "why": str(r.get("why") or "")[:200]}


def full_description(sb: dict, up: dict) -> str:
    """업로드에 실제로 보내는 설명 — 생성한 본문 + 출처(조사 · 퍼온 클립) + 면책 + 해시태그"""
    from upload_youtube import DISCLAIMER, source_lines
    parts = [up.get("description") or ""]
    srcs = source_lines(sb)
    if srcs:
        parts.append("출처:\n" + "\n".join(srcs))
    d = DISCLAIMER.get(sb.get("format"))
    if d:
        parts.append(d)
    if up.get("hashtags"):
        parts.append(" ".join(up["hashtags"]))
    return "\n\n".join(p for p in parts if p).strip()[:5000]


def generate(sbp: Path, force: bool = False) -> dict:
    import sbio
    sb = json.loads(sbp.read_text("utf-8"))
    base = json.loads(json.dumps(sb))
    inp = inputs(sb)
    h = hashlib.sha1(json.dumps(inp, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    old = sb.get("upload") or {}
    if not force and old.get("hash") == h and old.get("title"):
        return {**old, "skipped": "영상 내용 그대로"}
    if old.get("by") == "user" and not force:          # 사용자가 고친 업로드 정보는 덮지 않는다
        return {**old, "skipped": "사용자가 고친 값"}
    from agent_cli import extract_json, run_agent
    try:
        txt, cost = run_agent(RULES, json.dumps(inp, ensure_ascii=False, indent=1), override_env="FLUMA_SKILL_RUNTIME", timeout=300)
        up = tidy(extract_json(txt), sb)
    except Exception as e:  # noqa: BLE001 - 모델이 없거나 실패하면 콘티에서 바로 만든다
        print(f"[업로드 정보] 모델 실패 — 콘티에서 만듦: {str(e)[:160]}", file=sys.stderr)
        up, cost = tidy({"titles": [sb.get("title") or sb["id"]], "description": (inp["intent"] or sb.get("title") or ""),
                         "hashtags": list(sb.get("hashtags") or []), "tags": []}, sb), 0.0
    up.update(hash=h, by="auto")
    up["full"] = full_description(sb, up)            # 업로드에 실제로 보내는 설명(본문 + 출처 + 면책 + 해시태그) — 게시 화면 · 서버가 그대로 쓴다
    sb["upload"] = up
    sbio.save(sbp, base, sb)
    return {**up, "cost_usd": round(cost or 0, 4)}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); return 2
    sbp = Path(args[0]); sbp = sbp if sbp.is_absolute() else ROOT / sbp
    try:
        r = generate(sbp, "--force" in sys.argv)
    except (OSError, ValueError, KeyError) as e:
        fail("metadata", stage="generate", error=str(e)[:300])
    ok("metadata", title=r.get("title", ""), hashtags=" ".join(r.get("hashtags") or []), tags=str(len(r.get("tags") or [])),
       skipped=r.get("skipped", ""), file=str(sbp.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
