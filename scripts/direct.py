#!/usr/bin/env python3
"""디자인 방향(direction) 정하기 — 영상마다 다른 화면이 나오게 하는 Fluma 의 연출 지시서.

축마다(바탕 · 색 · 글자 · 배치 · 움직임 · 전환 · 자막 · 주인공 장치) 하나씩 고르되,
  1) 참고 쇼츠 분석(public/trends/analysis/<id>.json)이 있으면 그 패턴(색 · 글자 자리 · 컷 리듬 · 움직임)을 먼저 따르고
  2) 최근 영상들이 쓴 선택은 피한다(같은 바탕 · 같은 팔레트가 연달아 나오지 않게)
  3) 장면마다 어울리는 렌더 엔진을 캐스팅한다(수식 · 도표 → Manim, 사진 · 실사 → MoviePy …) — HyperFrames 하나로 몰지 않는다.

  python3 scripts/direct.py storyboards/<id>.json            # 지시서 출력 (콘티는 그대로)
  python3 scripts/direct.py storyboards/<id>.json --write    # 콘티에 direction + 장면 engine 기록
  python3 scripts/direct.py storyboards/<id>.json --write --reroll   # 다른 조합으로 다시
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ---------- 축 (각 선택지: 이름, 설명, Kit 힌트) ----------
# 'AI 룩' 바탕(그라데이션 메시 · 흐린 빛망울 · 원근 격자 바닥 · 빛번짐 무대)은 무작위 후보에서 뺐다 — 2026-11-02 "AI 티가 확 난다".
# 레퍼런스(스타일 · 채널 카드)가 그런 화면일 때만 scene.js 에서 직접 쓰고, look_check.py --allow 로 허용한다.
AXES: dict[str, list[tuple[str, str, str]]] = {
    "background": [
        ("paper", "밝은 종이 질감 · 손으로 만든 느낌", 'K.bg(root,{type:"paper"}) 또는 "ink"'),
        ("field", "대담한 단색 색면 + 거대한 도형 하나", 'K.bg(root,{type:"field", shape:"circle"|"square"})'),
        ("blueprint", "청사진 격자 · 설계도 느낌", 'K.bg(root,{type:"blueprint"})'),
        ("topo", "등고선 · 지형도 선", 'K.bg(root,{type:"topo"})'),
        ("split", "사선으로 나뉜 두 색", 'K.bg(root,{type:"split", angle:118})'),
        ("sky", "겹친 언덕 · 해 · 일러스트 풍경", 'K.bg(root,{type:"sky"})'),
        ("waves", "아래에서 쌓이는 물결 띠", 'K.bg(root,{type:"waves"})'),
        ("scan", "브라운관 주사선 · 레트로 화면", 'K.bg(root,{type:"scan"})'),
        ("halftone", "망점 · 인쇄물 · 만화 칸", 'K.bg(root,{type:"halftone"})'),
        ("photo", "실제 사진 · 캡처를 화면 가득(어둡게 눌러서)", "K.image(root, src, {...}) + 위에 반투명 색"),
        ("solid", "단색 바탕 — 화면 · 사진이 주인공일 때 기본", 'K.bg(root,{type:"solid"})'),
        ("stage", "깊은 검정 단색 무대(빛 없음)", "K.pro.stage(c)"),
    ],
    "palette": [
        ("mono-accent", "흑백 + 강조색 하나", "바탕 · 글자 무채색, 강조 하나만"),
        ("duotone", "보색 두 색이 화면을 나눔", "두 색을 면으로 크게"),
        ("pastel", "파스텔 3색 · 부드럽게", "채도 낮은 3색, 글자는 진한 남색"),
        ("pop", "고채도 팝 · 원색 대비", "노랑 · 빨강 · 파랑 같은 강한 대비, 테두리 검정"),
        ("earth", "흙 · 올리브 · 크림 · 차분한 자연색", "따뜻한 저채도"),
        ("neon", "어두운 바탕 + 형광 두 색", "#0b0b1a 위 시안 · 마젠타"),
        ("paper-ink", "종이색 + 먹색 + 빨간 도장", "크림 바탕, 검정 글자, 빨강 포인트"),
        ("reference", "참고 쇼츠 색을 그대로 옮김", "분석의 palette 상위 3~4색"),
    ],
    "type": [
        ("giant-number", "화면을 가득 채우는 숫자 · 단어 (400px+)", "K.pro.big / K.counter size 300+"),
        ("editorial", "작은 라벨 + 굵기 대비가 큰 제목, 왼쪽 정렬", "K.pro.label + K.pro.type, align left"),
        ("kinetic", "단어가 하나씩 튀어나오는 키네틱 타이포", 'K.text(..., {anim:"pop"|"stamp", split:"word"})'),
        ("boxed", "글자마다 색 상자 라벨(뉴스 · 밈 자막)", 'K.text(..., {highlight:[..], hlStyle:"box"})'),
        ("typewriter", "타자기 · 터미널 글자", 'K.text(..., {anim:"type"}) 또는 K.frame terminal'),
        ("handwritten", "손글씨 느낌 · 밑줄 · 동그라미 그리기", "K.draw 로 밑줄 · 동그라미 + 기울인 글자"),
    ],
    "layout": [
        ("center", "가운데 한 점에 집중", "주인공 하나를 화면 중앙"),
        ("top-title", "위 고정 제목 + 아래 그림판", "제목 y≈220 고정, 장면마다 아래만 바뀜"),
        ("left-editorial", "왼쪽 정렬 잡지 칸", "x=90 정렬, 오른쪽 여백"),
        ("split-screen", "위아래 또는 좌우 분할 비교", "두 판을 나란히"),
        ("card-stack", "카드가 쌓이고 넘어감", "K.list / 카드 여러 장 겹침"),
        ("diagram", "선으로 이어진 도식 · 지도", "K.draw 화살표 + 상자"),
        ("full-bleed", "사진 · 화면이 꽉 차고 글자는 띠로", "K.image 전체 + 하단 띠"),
    ],
    "motion": [
        ("calm", "지수 감속 · 차분", "K.pro.ex, 움직임 작게"),
        ("bouncy", "탄력 · 통통 튐", 'anim:"pop", E.back / E.elastic'),
        ("snappy", "짧은 컷 · 빠른 리듬(장면 안에서도 컷)", "장면 안 0.6~1초마다 화면 교체"),
        ("camera", "긴 캔버스를 카메라가 훑음", "K.camera.drift / 큰 판을 translate"),
        ("draw-on", "선이 그려지며 나타남", "K.draw, stroke 애니메이션"),
    ],
    "transition": [
        ("cuts", "컷 위주(가장 빠름)", 'transitions: ["cut", ...]'),
        ("wipe", "와이프 · 밀기", '["wipe","push",...]'),
        ("zoom", "확대 전환", '["zoom",...]'),
        ("match", "같은 도형이 다음 장면으로 이어짐(매치 컷)", "앞 장면 마지막 도형 = 다음 장면 첫 도형"),
        ("glitch", "글리치 · 플래시", '["glitch","flash"]'),
        ("circle", "원형 열림", '["circle",...]'),
    ],
    "captions": [
        ("highlight", "말하는 단어 노란 강조", 'captions:{style:"highlight"}'),
        ("box", "단어 상자", 'captions:{style:"box"}'),
        ("top", "위쪽 자막", 'captions:{style:"top"}'),
        ("pop", "한 단어씩 크게", 'captions:{style:"pop"}'),
        ("outline", "작은 외곽선 자막", 'captions:{style:"outline", size:52, y:1560}'),
        ("none", "자막 대신 화면 타이포가 말함", 'captions:{style:"none"}'),
    ],
    "device": [
        ("character", "캐릭터 · 의인화(사물이 얼굴을 가짐)", "K.actor / 직접 그린 SVG 얼굴"),
        ("object", "실물 사물 일러스트(폰 · 벽 · 기계)", "K.box/K.shape 로 사물을 그림"),
        ("chart", "데이터 차트 · 막대 · 링", "K.bars / K.ring / K.counter"),
        ("ui", "실제 앱 · 웹 화면(캡처) 카드", "K.frame browser/phone + captures/"),
        ("map", "지도 · 경로 · 이동", "K.draw 경로 + 점"),
        ("pixel", "픽셀아트", "K.pixel"),
        ("collage", "사진 오려 붙인 콜라주", "K.image 여러 장 기울여 겹침"),
    ],
}

# 주제 낱말 → 어울리는 선택(가중치)
HINTS = {
    "게임": {"device": ["pixel", "character"], "background": ["scan", "solid"], "palette": ["neon", "pop"]},
    "우주": {"background": ["sky", "solid"], "palette": ["neon", "duotone"]},
    "역사": {"background": ["paper", "halftone"], "palette": ["paper-ink", "earth"], "type": ["editorial"]},
    "돈": {"device": ["chart"], "type": ["giant-number"]},
    "가격": {"device": ["chart"], "type": ["giant-number"]},
    "속도": {"device": ["chart"], "motion": ["snappy"]},
    "코드": {"type": ["typewriter"], "device": ["ui"], "background": ["blueprint", "scan"]},
    "개발": {"type": ["typewriter"], "device": ["ui"], "background": ["blueprint"]},
    "와이파이": {"device": ["object", "map"], "layout": ["diagram"]},
    "음식": {"background": ["photo", "solid"], "palette": ["earth"], "device": ["collage"]},
    "여행": {"background": ["photo", "sky"], "device": ["map"]},
    "밈": {"type": ["boxed", "kinetic"], "palette": ["pop"], "device": ["collage"]},
}

# 공유 기억에서 "싫다 · 별로 · 금지"와 함께 나온 낱말 → 그 선택은 뽑지 않는다
AVOID_WORDS = {
    ("palette", "neon"): ["네온", "형광색"], ("palette", "pop"): ["원색"], ("device", "pixel"): ["픽셀"],
    ("background", "stage"): ["검은 무대", "검정 무대", "어두운 무대", "검은 바탕"], ("background", "scan"): ["주사선", "브라운관"],
    ("motion", "bouncy"): ["통통", "탄력"],
    ("captions", "highlight"): ["굵은 테두리 자막", "검은 테두리", "두꺼운 테두리", "외곽선 자막"], ("captions", "pop"): ["한 단어씩"],
    ("type", "boxed"): ["상자 라벨", "색 상자"], ("transition", "glitch"): ["글리치"], ("device", "character"): ["캐릭터"],
}
NEG = ["싫", "별로", "금지", "빼 ", "빼고", "티가", "티 나", "말 것", "말라", "피하", "유치", "촌스", "어색"]


def memory_avoid() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    pages = ROOT / "workspace" / "memory" / "pages"
    for p in pages.glob("*.md") if pages.exists() else []:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "status: superseded" in txt or "status: deleted" in txt:
            continue
        import re
        for sent in re.split(r"(?<=[.!?。])\s+|\n", txt):
            if not any(n in sent for n in NEG):
                continue
            for (ax, opt), words in AVOID_WORDS.items():
                if any(w in sent for w in words):
                    out.setdefault(ax, set()).add(opt)
    return out


def _recent(exclude: str, n: int = 6) -> list[dict]:
    items = []
    for p in (ROOT / "storyboards").glob("*.json"):
        if p.stem == exclude:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d.get("direction"), dict):
            items.append((p.stat().st_mtime, d["direction"]))
    # 직접 짠 컴포지션에서 쓴 배경 종류도 센다(방향 기록이 없던 옛 영상)
    for c in (ROOT / "compositions").glob("*/scene.js"):
        if c.parent.name == exclude:
            continue
        txt = c.read_text(encoding="utf-8", errors="ignore")
        bgs = [k for k, *_ in AXES["background"] if f'type: "{k}"' in txt or f"type:'{k}'" in txt or f'type:"{k}"' in txt]
        if "K.pro.stage" in txt:
            bgs.append("stage")
        if bgs:
            items.append((c.stat().st_mtime, {"background": bgs[0]}))
    items.sort(key=lambda x: -x[0])
    return [d for _, d in items[:n]]


def _reference(sb: dict) -> dict | None:
    for rid in sb.get("reference") or []:
        p = ROOT / "public" / "trends" / "analysis" / f"{rid}.json"
        if p.exists():
            try:
                a = json.loads(p.read_text(encoding="utf-8"))
                a["id"] = rid
                return a
            except Exception:
                pass
    return None


def choose(sb: dict, reroll: int = 0) -> dict:
    sid = sb.get("id", "x")
    text = " ".join([sb.get("title", ""), sb.get("topic", "") or "", *(s.get("caption", "") for s in sb.get("scenes", []))])
    recent = _recent(sid)
    ref = _reference(sb)
    seed = int(hashlib.sha1(f"{sid}:{reroll}".encode()).hexdigest(), 16)

    want: dict[str, list[str]] = {}
    for word, h in HINTS.items():
        if word in text:
            for ax, opts in h.items():
                want.setdefault(ax, []).extend(opts)
    why: dict[str, str] = {}
    if ref:
        rhythm = ref.get("avg_shot_sec") or 3
        want.setdefault("motion", []).insert(0, "snappy" if rhythm < 1.6 else "calm" if rhythm > 3.5 else "camera")
        want.setdefault("transition", []).insert(0, "cuts" if rhythm < 1.6 else "wipe")
        zone = ref.get("text_zone", "")
        want.setdefault("layout", []).insert(0, "top-title" if zone.startswith("위") else "center")
        want.setdefault("palette", []).insert(0, "reference")
        bright = ref.get("brightness") or 100
        if bright > 150:
            want.setdefault("background", []).insert(0, "paper")
        why["reference"] = f"참고 쇼츠 {ref['id']}: 평균 샷 {ref.get('avg_shot_sec')}초 · 글자 {zone} · 밝기 {bright}"

    used = {ax: [r.get(ax) for r in recent if r.get(ax)] for ax in AXES}
    avoid = memory_avoid()
    if avoid:
        why["memory"] = "기억한 취향으로 뺀 것: " + ", ".join(f"{ax}:{'/'.join(sorted(v))}" for ax, v in avoid.items())
    pick: dict[str, str] = {}
    for i, (ax, opts) in enumerate(AXES.items()):
        names = [o[0] for o in opts if o[0] not in avoid.get(ax, set())] or [o[0] for o in opts]
        # 1순위: 힌트 중 최근 3편에 안 쓴 것, 2순위: 최근 6편에 가장 적게 쓴 것(시드로 섞음)
        recent3 = set(used[ax][:3])
        cand = [n for n in want.get(ax, []) if n in names and n not in recent3]
        if cand and reroll == 0:
            pick[ax] = cand[0]
            continue
        counts = {n: used[ax].count(n) for n in names}
        rot = (seed >> (i * 5)) % len(names)
        order = names[rot:] + names[:rot]
        order = [n for n in order if not (ax == "palette" and n == "reference" and not ref)]
        order = [n for n in order if not (ax == "background" and n == "photo" and not sb.get("scenes"))]
        pick[ax] = min(order, key=lambda n: (n in recent3, counts[n]))
    if not ref and pick["palette"] == "reference":
        pick["palette"] = "duotone"
    return {"pick": pick, "recent": recent, "ref": ref, "why": why}


# 팔레트 → 실제 색(bg surface text muted accent caption). 같은 팔레트도 시드로 몇 가지 중 하나
PALETTES = {
    "mono-accent": [("#0E0E10", "#1A1A1E", "#F4F4F5", "#8B8B93", "#FF5A36"), ("#F5F4F0", "#E8E6E0", "#111111", "#6B6B6B", "#2F5BFF")],
    "duotone": [("#1B1F6B", "#2A2F8F", "#FFFFFF", "#B9BCF5", "#FF6B4A"), ("#0F4C3A", "#14614A", "#F3FFF8", "#9FD9C2", "#FFC93C")],
    "pastel": [("#FFF4EC", "#FFE3D3", "#2B2D42", "#7A7D99", "#7BB7F0"), ("#EEF6FF", "#DCEBFF", "#22304A", "#71809B", "#FF8FB1")],
    "pop": [("#FFE14D", "#FFFFFF", "#111111", "#444444", "#FF3D57"), ("#2D6BFF", "#FFFFFF", "#FFFFFF", "#DDE6FF", "#FFE14D")],
    "earth": [("#EDE6D6", "#DED3BC", "#2E2A22", "#7C7363", "#B5562E"), ("#26302A", "#323E36", "#EFE9DA", "#A9B3A2", "#D9A441")],
    "neon": [("#0B0B1A", "#151530", "#F2F2FF", "#8C8CB3", "#22F0FF"), ("#120818", "#1E0F28", "#FFF0FB", "#B08AA8", "#FF2BD6")],
    "paper-ink": [("#F3EEE3", "#E7E0D0", "#1A1A1A", "#6A645A", "#D2342B")],
}


def _hexlum(h: str) -> float:
    try:
        n = int(h.lstrip("#")[:6], 16)
    except ValueError:
        return .5
    r, g, b = (n >> 16) & 255, (n >> 8) & 255, n & 255
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _sat(h: str) -> float:
    n = int(h.lstrip("#")[:6], 16)
    r, g, b = ((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255
    mx, mn = max(r, g, b), min(r, g, b)
    return 0 if mx == 0 else (mx - mn) / mx


def colors(pick: dict, ref: dict | None, seed: int) -> dict:
    if pick["palette"] == "reference" and ref:
        pal = [c["hex"] if isinstance(c, dict) else c for c in (ref.get("palette") or [])]
        pal = [p for p in pal if isinstance(p, str) and p.startswith("#")]
        if len(pal) >= 2:
            light = (ref.get("brightness") or 100) > 128
            bg = max(pal, key=_hexlum) if light else min(pal, key=_hexlum)
            text = "#111111" if light else "#F5F5F5"
            rest = [p for p in pal if p != bg]
            good = [c for c in rest if _sat(c) >= .45 and .25 <= _hexlum(c) <= .8]
            acc = max(good, key=_sat) if good else ("#E8590C" if light else "#FFD23F")
            return {"color_bg": bg, "color_surface": rest[0], "color_text": text, "color_muted": "#6B6B6B" if light else "#A0A0A0", "color_accent": acc}
    opts = PALETTES.get(pick["palette"]) or PALETTES["duotone"]
    bg, surface, text, muted, acc = opts[seed % len(opts)]
    return {"color_bg": bg, "color_surface": surface, "color_text": text, "color_muted": muted, "color_accent": acc}


# 화면 내내 고정 요소(위 제목 · 자막판 · 분할)가 있는 배치는 다른 엔진 장면과 이어지기 어렵다 → 엔진이 확실히 나은 장면만
PERSISTENT = {"top-title", "left-editorial", "split-screen"}
STRONG = {"chart", "diff", "code", "footage", "still"}


def brief(sb: dict, res: dict, engines: list[str | None]) -> str:
    p = res["pick"]
    lines = ["# 디자인 방향 (direction)", f"영상: {sb.get('title', sb.get('id'))}", ""]
    for ax, label in [("background", "바탕"), ("palette", "색"), ("type", "글자"), ("layout", "배치"), ("motion", "움직임"), ("transition", "전환"), ("captions", "자막"), ("device", "주인공 장치")]:
        opt = next((o for o in AXES[ax] if o[0] == p[ax]), (p[ax], "형식 프리셋 숫자에서(사람이 편집한 실제 쇼츠)", "K.talk — SAFE · subs · title 이 콘티 preset 을 읽는다"))
        lines.append(f"- {label}: **{opt[0]}** — {opt[1]}  ·  Kit: {opt[2]}")
    if res["ref"]:
        pal = [c["hex"] if isinstance(c, dict) else c for c in (res["ref"].get("palette") or [])][:4]
        lines.append(f"- 참고 쇼츠 색: {' '.join(pal)}")
    for k, v in res["why"].items():
        lines.append(f"- 근거: {v}")
    if res["recent"]:
        lines.append(f"- 최근 영상이 쓴 바탕: {', '.join(r.get('background', '?') for r in res['recent'][:5])} → 이번엔 피함")
    seed = int(hashlib.sha1(f"{sb.get('id')}:0".encode()).hexdigest(), 16)
    col = colors(p, res["ref"], seed)
    lines.append("- 색 토큰(모든 엔진 공통, scene.js 는 K.T 로 받음): " + " · ".join(f"{k[6:]} {v}" for k, v in col.items()))
    lines += ["", "## 장면 구성", "- 모든 장면을 scene.js(HyperFrames)가 합성한다. 정밀 도표는 Manim, 움직이는 사물 · 동물 · 사람 하나는 Blender, 배경판 · 질감은 생성 모델 — 모두 장면 안 레이어 요소(scripts/element.py)로 겹친다.",
              "", "규칙: 위 축을 모두 지킨다. 바꾸고 싶으면 `--reroll` 로 다시 뽑거나 사용자에게 묻는다."]
    return "\n".join(lines)


def voice_from_card(card: dict) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    import tts
    v = card.get("voice", {})
    cps = float(v.get("chars_per_sec") or 6.6)
    speed = round(max(0.9, min(1.5, cps / 6.6)), 2)   # 우리 엔진 기본 속도 ≈ 초당 6.6자(공백 제외)
    ends = ", ".join(f"~{k}" for k in list(v.get("endings", {}))[:4])
    style = f"레퍼런스처럼 빠르고 가볍게, 컷이 바뀌어도 말이 이어지듯 수다 떠는 구어체 ({ends}). speaking rapidly, casual"
    st = tts._settings()
    mine = st.get("voice_engine") or ""
    if mine not in ("", "edge", "silent", "gemini") and tts.engine_available(mine):   # 사용자가 고른 엔진 — 말 속도 · 이어 말하기만 카드에서
        out = {"engine": mine, "speed": speed, "continuous": bool(v.get("continuous"))}
        return {**out, "id": st["voice_id"]} if st.get("voice_id") else out
    if tts.engine_available("gemini"):
        return {"engine": "gemini", "id": "Puck", "speed": 1.0, "style": style, "continuous": bool(v.get("continuous"))}
    return {"engine": "edge", "id": "ko-KR-HyunsuMultilingualNeural", "speed": speed, "continuous": bool(v.get("continuous"))}


def style_card(sb: dict) -> dict | None:
    """콘티 reference 의 첫 스타일 카드(scripts/ref_style.py 결과). 채널 카드(ref_channel.py)가 달려 있으면
    말 속도 · 이어 말하기는 채널(여러 편) 값으로 덮고, card["channel_card"] 에 채널 카드를 붙인다"""
    for rid in sb.get("reference") or []:
        p = ROOT / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        if p.exists():
            card = json.loads(p.read_text(encoding="utf-8"))
            cp = ROOT / "public" / "trends" / "channels" / str(card.get("channel")) / "channel.json" if card.get("channel") else None
            if cp and cp.exists():
                ch = json.loads(cp.read_text(encoding="utf-8"))
                cv = ch.get("voice") or {}
                card["voice"] = {**card.get("voice", {}), "chars_per_sec": cv.get("cps") or card.get("voice", {}).get("chars_per_sec"),
                                 "continuous": cv.get("continuous", card.get("voice", {}).get("continuous")), "prosody": cv.get("prosody")}
                card["channel_card"] = ch
            return card
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--reroll", type=int, nargs="?", const=1, default=0)
    ap.add_argument("--no-cast", action="store_true", help="(예전 옵션 · 무시) 장면 단위 엔진 캐스팅은 없어졌다")
    a = ap.parse_args()
    path = Path(a.storyboard)
    sb = json.loads(path.read_text(encoding="utf-8"))
    # 레퍼런스 스타일 카드가 있으면 무작위로 고르지 않는다 — 카드의 방향(바탕 · 배치 · 자막 · 움직임 · 전환)을 그대로
    card = style_card(sb)
    if card and not a.reroll:
        d = card["direction"]
        col = {"color_bg": d.get("color_bg", "#000000"), "color_surface": "#111111", "color_text": "#ffffff", "color_muted": "#9a9a9a",
               "color_accent": "#ff2d2d", "color_caption_bg": d.get("caption_bg"), "color_caption_fg": d.get("caption_fg")}
        print(Path(ROOT / "public" / "trends" / "xray" / card["id"] / "style" / "style.md").read_text(encoding="utf-8"))
        if card.get("channel_card"):   # 구성 · 말투는 채널(여러 편) 카드가 기준 — 한 편 통계보다 먼저
            print(Path(ROOT / "public" / "trends" / "channels" / card["channel"] / "channel.md").read_text(encoding="utf-8").split("## 영상별 대사")[0])
            print(f"(영상별 대사 · 대사 시트: public/trends/channels/{card['channel']}/channel.md)")
        if a.write:
            sb["direction"] = {**{k: v for k, v in d.items() if not k.startswith("caption_")}, **col, "style_card": f"public/trends/xray/{card['id']}/style/style.json",
                               **({"channel_card": f"public/trends/channels/{card['channel']}/channel.json"} if card.get("channel_card") else {})}
            if not sb.get("voice"):   # 목소리도 카드에서: 가장 자연스러운 엔진 · 레퍼런스 말 속도 · 이어 말하기 · 말투 지시
                sb["voice"] = voice_from_card(card)
                print(f"[기록] 목소리: {sb['voice']}")
            sb["template"] = "Composed"
            sb.pop("engine", None)
            path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"\n[기록] {path} 에 레퍼런스 {card['id']} 의 방향을 적었습니다 (무작위 아님 — 바꾸려면 --reroll)")
        return
    # 레퍼런스가 없으면 형식 프리셋(사람이 편집한 실제 쇼츠에서 잰 숫자) — 무작위 방향보다 먼저
    if not sb.get("preset"):
        import subprocess as _sp
        _sp.run([sys.executable, str(ROOT / "scripts" / "format_presets.py"), "pick", str(path)], check=False)
        sb = json.loads(path.read_text(encoding="utf-8"))
    res = choose(sb, a.reroll)
    pr = sb.get("preset")
    if pr:
        lay, rh = pr.get("layout", {}), pr.get("rhythm", {})
        cap = lay.get("captions", {})
        shot = rh.get("shot_sec") or 3
        over = {"background": "solid", "layout": "band" if (lay.get("fill", {}).get("letterbox") or 0) > 0.5 else "full",
                "captions": "none" if (cap.get("share") or 0) < 0.2 else ("box" if (cap.get("box") or 0) >= 0.5 else "plain"),
                "motion": "dynamic" if shot < 1.5 else "minimal" if shot >= 3 else "moderate", "transition": "cuts"}
        res["pick"].update(over)
        print(f"[프리셋] {pr.get('name')} — 배치 · 바탕 · 자막 · 움직임은 프리셋 숫자에서(무작위 아님): {over}")
    # 장면은 모두 HyperFrames 가 합성한다. Manim · Blender · 생성 모델은 장면 안 레이어 요소(scripts/element.py)로만 쓴다
    engines = [None] * len(sb.get("scenes", []))
    print(brief(sb, res, engines))
    if a.write:
        seed = int(hashlib.sha1(f"{sb.get('id')}:{a.reroll}".encode()).hexdigest(), 16)
        sb["direction"] = {**res["pick"], "reference": (res["ref"] or {}).get("id"), **colors(res["pick"], res["ref"], seed)}
        sb["template"] = "Composed"
        sb.pop("engine", None)
        for s in sb.get("scenes", []):
            s.pop("engine", None)
            s.pop("template", None)
        path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n[기록] {path} 에 direction 을 적었습니다.")


if __name__ == "__main__":
    main()
