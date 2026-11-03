#!/usr/bin/env python3
"""형식 프리셋 — 사람이 편집한 실제 쇼츠에서 잰 숫자를 형식별로 묶어, 레퍼런스 링크가 없어도 배치 · 리듬 · 말을 그 숫자로 짠다.

  python3 scripts/format_presets.py build                 # 측정해 둔 채널 카드(ref_channel.py) → presets/formats/<형식>.json
  python3 scripts/format_presets.py list
  python3 scripts/format_presets.py pick storyboards/<id>.json [--format news]   # 주제로 고르거나 지정 → 콘티 preset 칸에 숫자를 적는다

왜: 레퍼런스가 없을 때 엔진이 기대던 기본값(가운데 판 · 고정 자막 위치 · 직접 그린 표)이 그 자체로 'AI 틀'이었다(2026-11-02).
프리셋에는 숫자만 남긴다(자막 위치 · 크기 · 한 줄 글자 수 · 줄 수 · 상자 여부, 고정 제목, 화면 채움, 화면 종류 비율, 컷 길이 · 박자,
말 비율 · 속도 · 이어 말하기, 문장 끝 비율). 원본 영상 · 대사 · 그림은 저장하지 않는다. 출처는 채널 이름과 측정 날짜만.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CH = ROOT / "public" / "trends" / "channels"
OUT = ROOT / "presets" / "formats"

# 형식 → (설명, 측정에 쓴 레퍼런스 쇼츠 id 들, 주제 낱말)
FORMATS: dict[str, dict] = {
    "it-explainer": {"title": "IT · 개발 설명 — 말 주도, 실제 화면", "refs": ["GWxltQt5itU", "vdbMLgcSNRw"],
                     "keywords": ["개발", "코딩", "프로그램", "앱", "웹", "크롬", "깃허브", "github", "ai", "인공지능", "서버", "해킹", "보안", "유튜브", "컴퓨터", "단축키", "설정", "기능", "it"]},
    "cooking": {"title": "요리 · 레시피 — 과정 화면, 음악 · 말 섞임", "refs": ["SSbyRvzf1VQ", "foNAPZxCGV4"],
                "keywords": ["요리", "레시피", "음식", "자취", "라면", "밥", "반찬", "굽", "볶", "끓", "맛", "디저트", "베이킹"]},
    "news": {"title": "뉴스 · 시사 — 헤드라인 띠, 사실 위주", "refs": ["m51EAFu9sSY"],
             "keywords": ["뉴스", "정치", "경제", "사건", "정부", "대통령", "국회", "발표", "속보", "금리", "주가", "환율", "사고"]},
    "science": {"title": "과학 · 상식 — 이유를 풀어 주는 말 주도", "refs": ["R3mkHcGE1Dg"],
                "keywords": ["과학", "상식", "이유", "왜", "우주", "지구", "역사", "동물", "몸", "원리", "물리", "화학", "바다"]},
    "review": {"title": "제품 리뷰 · 추천 — 제품 화면, 비교 · 순위", "refs": ["taPZ388X7F0"],
               "keywords": ["리뷰", "추천", "제품", "구매", "가성비", "비교", "순위", "top", "언박싱", "후기", "써보", "써 보"]},
}


def cards_for(refs: list[str]) -> list[dict]:
    out = []
    for p in CH.glob("*/channel.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("ref") in refs:
            out.append(c)
    return out


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(float(np.median(xs)), 3) if xs else None


def merge(cards: list[dict]) -> dict:
    """여러 채널 카드 → 숫자만(중앙값 · 평균 비율)"""
    lay = [c.get("layout") or {} for c in cards]
    st = [c.get("structure") or {} for c in cards]
    vo = [c.get("voice") or {} for c in cards]
    to = [c.get("tone") or {} for c in cards if c.get("lang", "ko") == "ko"]
    pick = lambda group, key: [((g.get(group) or {}).get(key)) for g in lay]
    screens: dict[str, float] = {}
    for s in st:
        for k, v in (s.get("screens") or {}).items():
            screens[k] = screens.get(k, 0) + v / len(st)
    endings: dict[str, float] = {}
    for t in to:
        for k, v in (t.get("endings") or {}).items():
            endings[k] = endings.get(k, 0) + v / len(to)
    # 장면 구성: 뼈대의 첫 · 끝 역할과 역할 비율(말 주도일 때)
    roles: dict[str, int] = {}
    for c in cards:
        for v in c.get("videos") or []:
            for s in v.get("sentences") or []:
                roles[s.get("role", "?")] = roles.get(s.get("role", "?"), 0) + 1
    tot = sum(roles.values()) or 1
    return {
        "layout": {
            "captions": {k: med(pick("captions", k)) for k in ("share", "y", "height", "width", "chars", "lines", "box", "fg_light")},
            "title": {k: med(pick("title", k)) for k in ("share", "y", "height")},
            "fill": {k: med(pick("fill", k)) for k in ("letterbox", "band_top", "band_bottom")},
        },
        "rhythm": {"shot_sec": med([s.get("shot_sec") for s in st]), "bpm": med([s.get("bpm") for s in st]), "cut_on_beat": med([s.get("cut_on_beat") for s in st]),
                   "sentence_sec": med([s.get("sentence_sec") for s in st]), "cuts_per_sentence": med([s.get("cuts_per_sentence") for s in st])},
        "lead": max(set(s.get("lead", "말") for s in st), key=[s.get("lead", "말") for s in st].count) if st else "말",
        "speech_ratio": med([s.get("speech_ratio") for s in st]),
        "screens": {k: round(v, 2) for k, v in sorted(screens.items(), key=lambda x: -x[1])},
        "voice": {"cps": med([v.get("cps") for v in vo]), "continuous": sum(1 for v in vo if v.get("continuous")) >= len(vo) / 2 if vo else False,
                  "prosody": {k: med([(v.get("prosody") or {}).get(k) for v in vo]) for k in ("f0_median", "range_st", "end_drop_st", "energy_sd_db")}},
        "tone": {"endings": {k: round(v, 2) for k, v in sorted(endings.items(), key=lambda x: -x[1])[:8]}} if to else {},
        "roles": {k: round(v / tot, 2) for k, v in sorted(roles.items(), key=lambda x: -x[1])},
        "joke_rate_per_10s": med([c.get("joke_rate_per_10s") for c in cards]),
    }


def cap_txt(p: dict) -> str:
    c = p["layout"]["captions"]
    if (c.get("share") or 0) < 0.2:
        return "거의 없음"
    return f"y {c.get('y')} · 높이 {c.get('height')} · 한 줄 {c.get('chars')}자 · 상자 {c.get('box')}"


def cmd_build(_a):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, f in FORMATS.items():
        cards = cards_for(f["refs"])
        if not cards:
            print(f"[건너뜀] {name}: 측정한 채널 카드가 없음 — python3 scripts/ref_channel.py <{'|'.join(f['refs'])}> --n 2"); continue
        p = {"name": name, "title": f["title"], "keywords": f["keywords"], **merge(cards),
             "source": {"channels": [c.get("title") for c in cards], "videos": sum(len(c.get("videos") or []) for c in cards), "measured": time.strftime("%Y-%m-%d"),
                        "note": "숫자만 — 원본 영상 · 대사 · 그림은 저장하지 않음"}}
        (OUT / f"{name}.json").write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        rows.append(f"| {name} | {f['title']} | {', '.join(p['source']['channels'])} · {p['source']['videos']}편 | {p['lead']} | {cap_txt(p)} | {p['rhythm']['shot_sec']}초 |")
        print(f"[프리셋] {name}: {', '.join(p['source']['channels'])}")
    (OUT / "README.md").write_text("# 형식 프리셋\n\n사람이 편집한 실제 쇼츠에서 잰 숫자(scripts/format_presets.py build). 원본 영상 · 대사는 저장하지 않는다.\n\n"
                                  "| 형식 | 설명 | 측정 | 주도 | 자막 | 컷 |\n|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")


def load(name: str) -> dict:
    p = OUT / f"{name}.json"
    if not p.exists():
        sys.exit(f"프리셋이 없습니다: {name} — python3 scripts/format_presets.py build")
    return json.loads(p.read_text(encoding="utf-8"))


def choose(sb: dict) -> str:
    """주제 · 제목 · 나레이션의 낱말로 형식을 고른다(가장 많이 맞은 것). 아무것도 안 맞으면 과학 · 상식(설명형 기본)"""
    text = " ".join([str(sb.get("topic") or ""), str(sb.get("title") or "")] + [str(s.get("narration") or "") for s in sb.get("scenes", [])]).lower()
    have = [p.stem for p in OUT.glob("*.json")]
    score = {n: sum(text.count(k) for k in FORMATS[n]["keywords"]) for n in FORMATS if n in have}
    best = max(score, key=score.get) if score else None
    return best if best and score[best] > 0 else ("science" if "science" in have else (have[0] if have else ""))


def cmd_pick(a):
    sp = Path(a.storyboard)
    sb = json.loads(sp.read_text(encoding="utf-8"))
    name = a.format or choose(sb)
    if not name:
        sys.exit("프리셋이 하나도 없습니다 — build 먼저")
    p = load(name)
    sb["preset"] = {k: p[k] for k in ("name", "title", "layout", "rhythm", "lead", "speech_ratio", "screens", "voice", "tone", "roles", "joke_rate_per_10s") if k in p}
    sp.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[프리셋] {name} — {p['title']} (측정: {', '.join(p['source']['channels'])})")
    print(f"  자막: {cap_txt(p)}")
    print(f"  리듬: 컷 {p['rhythm']['shot_sec']}초 · {p['lead']} 주도 · 화면 {', '.join(f'{k} {int(v * 100)}%' for k, v in list(p['screens'].items())[:3])}")


def cmd_list(_a):
    for p in sorted(OUT.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        print(f"{d['name']:<14} {d['title']}  · {', '.join(d['source']['channels'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build"); sub.add_parser("list")
    pk = sub.add_parser("pick"); pk.add_argument("storyboard"); pk.add_argument("--format", choices=list(FORMATS))
    a = ap.parse_args()
    {"build": cmd_build, "list": cmd_list, "pick": cmd_pick}[a.cmd](a)


if __name__ == "__main__":
    main()
