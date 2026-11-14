"""Craft 파이프라인 — 움직임 단계: 콘티 + 단어 타이밍 → EffectCraft 프로젝트(.ecproj).

설계: 볼트 02 Architecture/Craft 파이프라인 설계 — 제작 도구로 영상 만들기.md (3 · 5절)
결정적 생성기: 같은 입력이면 같은 프로젝트. 에이전트는 좌표 · 키프레임 숫자를 쓰지 않는다 — 콘티(장면 · 요소 · beats)와
장면 계획(data/scenes/<n>.plan.json, 있으면)만 쓰고, 이 생성기가 키프레임으로 바꾼다.

프로젝트 구조(사람이 EffectCraft 에서 열면 이렇게 보인다)
  Main                       1080×1920 전체, 장면 컴포지션을 시간순으로
  S01 훅 · S02 반전 …         장면마다 컴포지션 하나
     BG                      바탕(콘티 디자인 방향 색)
     Camera (null)           그림 층의 부모 — 장면 내내 천천히 밀고, beats 의 '확대' 에서 당긴다
     Art …                   data/compositions/<id>/craft/art/s<NN>*.png|svg (뒤 → 앞), 없으면 무엇이 들어갈지 적힌 자리표시
     Title · TitleBox …      '훅 제목' 요소: 노란 상자에 한 줄씩 쌓임(상자는 글자 크기를 따라감 — 사람이 글자를 고쳐도 맞음)
     Pill · PillText         '숫자 알약' 요소: 위쪽 가운데, 숫자가 아래에서 굴러 올라옴
     Sub 01 …                단어 자막(1~2어절씩, 화면 문법 grammar.subs 의 위치 · 크기)

화면 문법은 콘티 grammar(previz.py grammar 가 참고 쇼츠에서 잰 값)를 쓴다. 없으면 direction 의 기본값.

엔진 내장 기능(JSX 안 app.run — 실패하면 예전 손 키프레임으로 대신한다). 기본값은 옅게(재료가 주인공):
  배경        형식별 프리셋(BG_PRESET: 설명형 blueprintGrid · 감성 bokehDrift · 광고 pulseRings · 당일 softGradientDrift),
              색은 prop.set 으로 콘티 바탕 · 팔레트에. direction.bg_preset(id | false) 로 바꾸거나 끈다
  재료 등장   종류별 전환 프리셋(ENTER: 실제 화면 wipeInFromRight · 문서 wipeInFromTop), 0.6초로 줄임. 재료 enter · exit(id | false),
              direction.enter. 다음 화면이 가득 닦으며 들어오면 앞 화면은 그동안 그대로(바탕색 번쩍임 없음)
  글자        훅 제목 bounceInWords(0.5초) · 감성 형식 자막 fadeUpCharacters(자막 길이의 60%). direction.title_preset · sub_preset
  실제 화면   screen · web · video: 둥근 모서리 마스크 + 그림자 + 칸에 놓이면 느린 밀기(재료 push · shadow). 폰 녹화는 액자 없이 가득
  새 종류     앱 어댑터의 모르는 종류는 as(image|video) · 확장자로 배치, 화면 비율(9:16) 그림 · 영상은 화면을 덮음,
              overlay 는 대상 재료 레이어의 자식으로 차례 등장, doc_quote highlighted 면 가짜 형광펜 없음(focus 로 확대),
              layers + base(DeckCraft 도식)는 바탕 위에 항목 층을 차례로, document 는 focus 쪽으로 밀기, FilmCraft zoomed 녹화는 밀기 없음
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLE_KO = {"hook": "훅", "reveal": "반전", "setup": "의문", "step": "과정", "proof": "증거", "outro": "맺음", "contrast": "대비",
           "verdict": "결론", "payoff": "결론", "cta": "행동", "item": "항목", "benefit": "이점", "problem": "고민", "context": "맥락"}


def js(v) -> str:
    """파이썬 값 → JS 리터럴(문자열은 안전하게 이스케이프)"""
    return json.dumps(v, ensure_ascii=False)


def rgb(hexs: str, default=(0.06, 0.29, 0.49)) -> list[float]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (hexs or "").strip())
    if not m:
        return list(default)
    h = m.group(1)
    return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]


def chunks(words: list[dict], max_chars: int = 9, max_words: int = 2) -> list[dict]:
    """단어 자막 → 1~2어절 덩어리(레퍼런스: 말하는 1~3단어만 따라 바뀜)"""
    out, cur = [], []
    for w in words:
        t = (w.get("text") or "").strip()
        if not t:
            continue
        if cur and (len(cur) >= max_words or len("".join(x["text"].strip() for x in cur)) + len(t) > max_chars):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"text": " ".join(x["text"].strip() for x in c), "start": c[0]["startMs"] / 1000, "end": c[-1]["endMs"] / 1000} for c in out]


def clause_chunks(words: list[dict], max_chars: int = 30) -> list[dict]:
    """가로 영상 자막 — 문장을 통째로 보여 주고, 길면 쉼표나 가운데 어절에서 둘로 나눈다. 한 낱말만 남는 줄을 만들지 않는다.
    다음 자막까지 틈이 짧으면 이어 붙여 깜빡이지 않게 한다"""
    ws = [w for w in words if (w.get("text") or "").strip()]
    size = lambda c: sum(len(x["text"].strip()) + 1 for x in c)  # noqa: E731
    sents, cur = [], []
    for w in ws:
        cur.append(w)
        if re.search(r"[.?!]$", w["text"].strip()):
            sents.append(cur)
            cur = []
    if cur:
        sents.append(cur)

    def split(c):
        if size(c) <= max_chars or len(c) < 4:
            return [c]
        half = size(c) / 2
        cand = range(1, len(c))
        comma = [i for i in cand if c[i - 1]["text"].strip().endswith(",") and .3 < size(c[:i]) / size(c) < .7]
        i = min(comma or cand, key=lambda k: abs(size(c[:k]) - half))
        return split(c[:i]) + split(c[i:])
    out = [p_ for c in sents for p_ in split(c)]
    res = [{"text": " ".join(x["text"].strip() for x in c), "start": c[0]["startMs"] / 1000, "end": c[-1]["endMs"] / 1000} for c in out]
    for a, b in zip(res, res[1:]):
        if b["start"] - a["end"] < 0.45:
            a["end"] = b["start"]
    return res


def cue_time(cue: str | None, words: list[dict], start: float, end: float) -> float | None:
    """beats · 요소의 cue 낱말이 나오는 시각(장면 안 기준 초). 못 찾으면 None"""
    if not cue:
        return None
    key = re.sub(r"\s+", "", cue)
    for w in words:
        t = re.sub(r"\s+", "", w.get("text") or "")
        if t and (key in t or t in key) and start - 0.05 <= w["startMs"] / 1000 <= end:
            return round(w["startMs"] / 1000 - start, 3)
    return None


def beat_at(sc: dict, sec: float, *needles: str) -> float | None:
    """나레이션이 없는 장면: beats 의 hold(초)를 차례로 더해 각 박자의 시작 시각을 잡고, needles 가 든 박자의 시각을 돌려준다"""
    beats = [b for b in (sc.get("beats") or []) if isinstance(b, dict)]
    holds = [float(b.get("hold") or 1.0) for b in beats]
    tot = sum(holds) or 1.0
    k = sec / tot if tot > sec else 1.0
    starts = [sum(holds[:i]) * k for i in range(len(beats))]
    hits = [(b, t) for b, t in zip(beats, starts) if any(nd and str(nd) in f"{b.get('at', '')} {b.get('what', '')}" for nd in needles)]
    # 글자 · 표시 박자(숫자를 보여 주는 박자)를 먼저 — '1' 같은 짧은 숫자는 말풍선 박자에도 들어 있다
    pref = [t for b, t in hits if b.get("do") in ("글자", "표시")]
    return round(pref[0], 3) if pref else (round(hits[0][1], 3) if hits else None)


# 설치된 글꼴(engine/assets/fonts — EFFECTCRAFT_FONT_DIRS)의 PostScript 이름. direction.font_title · font_body 를 여기로 맞춘다
# 2026-11-09: 방향에 'Noto Serif CJK KR' 을 적었지만 어디서도 읽지 않아 늘 Pretendard-Black + 노란 상자가 나왔다
FONTS = {"sans": "Pretendard-Black", "sans-bold": "Pretendard-Bold", "sans-regular": "Pretendard-Regular", "serif": "GowunBatang-Bold",
         "serif-regular": "GowunBatang-Regular", "display-serif": "SongMyung-Regular", "latin": "Geist-Regular", "mono": "JetBrainsMono-ExtraBold",
         "hand": "NanumPen-Regular", "heavy": "BlackHanSans-Regular"}
_INSTALLED = set(FONTS.values()) | {"Pretendard-ExtraBold"}


def resolve_font(name: str | None, default: str) -> str:
    """'Noto Serif CJK KR' · '명조' · 'serif light' · 'SongMyung-Regular' → 설치된 글꼴. 모르는 이름은 계열(세리프 · 산세리프 · 손글씨)로 가깝게"""
    n = str(name or "").strip()
    if not n:
        return default
    if n in _INSTALLED:
        return n
    low = n.lower()
    if any(k in low for k in ("song", "송명", "display serif")):
        return FONTS["display-serif"]
    if any(k in low for k in ("serif", "batang", "바탕", "myeongjo", "명조", "garamond", "times", "didot")) and "sans" not in low:
        return FONTS["serif-regular"] if any(k in low for k in ("light", "regular", "thin", "가는")) else FONTS["serif"]
    if any(k in low for k in ("pen", "hand", "손글씨", "script")):
        return FONTS["hand"]
    if "mono" in low:
        return FONTS["mono"]
    if any(k in low for k in ("regular", "light", "thin", "medium")):
        return FONTS["sans-regular"]
    if "bold" in low and "black" not in low:
        return FONTS["sans-bold"]
    return default


def is_serif(font: str) -> bool:
    return font in (FONTS["serif"], FONTS["serif-regular"], FONTS["display-serif"])


def grammar(sb: dict) -> dict:
    g = dict(sb.get("grammar") or {})
    g.setdefault("subs", {"y": 0.76, "h": 0.024, "box": False, "fg": "#ffffff"})
    g.setdefault("pill", {"y": 0.09, "h": 0.03})
    d = sb.get("direction") or {}
    # 제목 모양: 방향이 세리프 · 절제(editorial)면 노란 상자 대신 상자 없는 큰 글자(방향 글자색), 아니면 예전 노란 상자
    editorial = d.get("title_style") == "editorial" or is_serif(resolve_font(d.get("font_title"), ""))
    g.setdefault("title", {"y": 0.24, "h": 0.04, "box": False, "fg": d.get("color_text") or "#ffffff", "editorial": True} if editorial
                 else {"y": 0.24, "h": 0.04, "box": True, "bg": "#ffd60a", "fg": "#111111"})
    for k in ("subs", "title"):                     # 디자인 방향(시안 · 사용자)이 자막 · 제목 모양을 바꾼다
        if isinstance(d.get(k), dict):
            g[k] = {**g[k], **d[k]}
    # 안전 영역(designer 스킬 2장 5): 위 8% 는 상태 표시줄 — 고정 제목 · 알약이 그 안에 그려졌다(2026-11-11 정지 화면 검토가 찾음)
    for k in ("pill", "title"):
        if isinstance(g.get(k), dict) and "y" in g[k]:
            g[k]["y"] = max(float(g[k]["y"]), 0.08 + float(g[k].get("h", 0.03)) * 0.6 + 0.01)
    if isinstance(g.get("subs"), dict) and "y" in g["subs"]:     # 아래 18% 는 쇼츠 제목 · 버튼
        g["subs"]["y"] = min(float(g["subs"]["y"]), 0.80)
    return g


def element(sc: dict, *names: str) -> dict | None:
    for e in sc.get("elements") or []:
        if any(n in (e.get("name") or "") for n in names):
            return e
    return None


def quoted(text: str) -> list[str]:
    """'AI가 / 지어낸 / 패키지' 처럼 따옴표 안을 / 로 나눈 줄들"""
    m = re.search(r"[‘'\"“]([^’'\"”]+)[’'\"”]", text or "")
    return [s.strip() for s in m.group(1).split("/") if s.strip()] if m else []


PILL_COLORS = {"분홍": [0.97, 0.15, 0.52], "보라": [0.55, 0.3, 0.95], "청록": [0.1, 0.72, 0.68], "주황": [1.0, 0.55, 0.1], "파랑": [0.2, 0.5, 1.0]}


def pill_color(what: str, k: int) -> list[float]:
    for name, c in PILL_COLORS.items():
        if name in what:
            return c
    return list(PILL_COLORS.values())[k % len(PILL_COLORS)]


POS_X = {"left": 0.26, "center": 0.5, "right": 0.74, "far_left": -0.2, "far_right": 1.2}


def puppet(J, sid: str, fig: dict, sec: float, words: list[dict], start: float, end: float, W: int, H: int, k: int,
           d: Path | None = None) -> bool:
    """그린 캐릭터(rig.json)를 부품 레이어 인형으로 조립하고 동작을 붙인다. 좌표는 장면 말(at · to · size)에서만 온다"""
    if d is None:
        return False
    rp = d / "rig.json"
    if not rp.exists():
        return False
    rig = json.loads(rp.read_text("utf-8"))
    cw, ch = rig["canvas"]
    size = float(fig.get("size", 0.3))
    s = size * H / ch * 100                                # 레이어 배율(%)
    gy = float(fig.get("ground", 0.8)) * H
    x0 = POS_X.get(fig.get("at", "center"), 0.5) * W
    x1 = POS_X.get(fig.get("to", fig.get("at", "center")), 0.5) * W
    ox, oy = rig["origin"]
    nm = f"Fig {fig.get('name')} {k}"
    J(f"var fg = c.layers.addNull(); fg.name = {js(nm)}; fg.property('Transform').property('Position').setValue([{x0:.1f}, {gy:.1f}]);")
    J("var L = {};")
    for ly in rig["layers"]:
        px, py = ly["pivot"]
        wx, wy = x0 + (px - ox) * s / 100, gy + (py - oy) * s / 100
        J(f"var f = app.project.importFile(new ImportOptions(new File({js(str(d / ly['file']))})));")
        J(f"var l = c.layers.add(f); l.name = {js(nm + ' · ' + ly['id'])};")
        J(f"l.property('Transform').property('Anchor Point').setValue([{px}, {py}]); l.property('Transform').property('Scale').setValue([{s:.3f}, {s:.3f}]); l.property('Transform').property('Position').setValue([{wx:.1f}, {wy:.1f}]);")
        J(f"L[{js(ly['id'])}] = l;")
    for ly in rig["layers"]:   # 부모는 모든 위치를 정한 뒤에(세계 좌표 유지)
        J(f"L[{js(ly['id'])}].parent = {('L[' + js(ly['parent']) + ']') if ly.get('parent') else 'fg'};")
    # 동작 — 원리를 표현식으로(사람이 EffectCraft 에서 숫자를 바꾸면 그대로 반영)
    act = fig.get("action", "idle")
    t0 = cue_time(fig.get("cue"), words, start, end) or 0.0
    roots = [ly for ly in rig["layers"] if not ly.get("parent") and ly.get("kind") == "body"]
    for ly in roots:   # 숨쉬기: 발 기준으로 늘었다 줄기(부피 보존)
        J(f"L[{js(ly['id'])}].property('Transform').property('Scale').expression = 'var a = Math.sin(time * Math.PI * 1.3); [value[0] * (1 - 0.018 * a), value[1] * (1 + 0.026 * a)]';")
    for ly in rig["layers"]:
        kind, lid = ly.get("kind"), js(ly["id"])
        ph = "Math.PI" if ly.get("mirror_of") else "0"
        if kind == "tail":   # 부속: 한 박자 늦게 따라 흔들림
            J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + 9 * Math.sin(time * 5.0 - 0.7)';")
        if act == "walk":
            if kind == "leg":
                J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + 24 * Math.sin(time * 9.0 + {ph})';")
            elif kind == "arm":
                J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value - 20 * Math.sin(time * 9.0 + {ph})';")
        if act == "wave" and kind == "arm" and not ly.get("mirror_of"):
            # 바깥쪽 위로 들어 올린다: 몸 왼쪽에 붙은 팔은 시계 방향(+), 오른쪽 팔은 반대
            body_x = roots[0]["pivot"][0] if roots else ly["pivot"][0]
            sign = 1 if ly["pivot"][0] < body_x else -1
            J(f"L[{lid}].property('Transform').property('Rotation').expression = 'value + {sign} * (14 + 16 * Math.sin(time * 10.0))';")   # 그린 자세에서 흔든다
    if act == "walk":
        for ly in roots:   # 걸음마다 몸이 위아래로
            J(f"L[{js(ly['id'])}].property('Transform').property('Position').expression = 'value - [0, {0.03 * size * H:.1f} * Math.abs(Math.sin(time * 9.0))]';")
        J(f"var fp = fg.property('Transform').property('Position'); fp.setValueAtTime({t0:.3f}, [{x0:.1f}, {gy:.1f}]); fp.setValueAtTime({sec:.3f}, [{x1:.1f}, {gy:.1f}]);")
    if act == "bounce":
        J(f"fg.property('Transform').property('Position').expression = 'value - [0, {0.08 * size * H:.1f} * Math.abs(Math.sin((time - {t0:.3f}) * 6.0))]';")
    return True


# ---------------------------------------------------------------- 재료(범용): 어떤 Craft 툴이 만든 재료든 같은 방식으로
PLACE = {"full": (0.5, 0.5, 1.0, 1.0), "center": (0.5, 0.47, 0.82, 0.5), "left": (0.3, 0.55, 0.5, 0.45),
         "right": (0.7, 0.55, 0.5, 0.45), "top": (0.5, 0.3, 0.86, 0.32), "bottom": (0.5, 0.66, 0.86, 0.32)}


KNOWN_TYPES = {"chart", "stat", "text", "illustration", "icon", "doc_quote", "image", "photo", "screen", "video", "web", "stock", "overlay"}
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
SCREENS = ("screen", "video", "web", "stock")      # 실제 화면(캡처 · 녹화)


def mat_kind(rec: dict) -> str:
    """배치 방식을 정하는 종류. 기본 종류는 그대로, 앱 어댑터가 만든 새 종류(diagram · ui_mock · model3d …)는
    기록의 as(image|video) 힌트 > 파일 확장자(.mp4 류 → video, 나머지 그림 → image)로 기본 종류처럼 배치한다"""
    typ = rec.get("type") or ""
    if typ == "chart" and rec.get("as") in ("image", "video"):     # 다른 앱이 그림으로 만든 차트(chart@deckcraft) — 그림처럼 놓는다
        return rec["as"]
    if typ in KNOWN_TYPES:
        return typ
    if rec.get("as") in ("image", "video"):
        return rec["as"]
    return "video" if Path(str(rec.get("file") or "")).suffix.lower() in VIDEO_EXT else "image"


def file_aspect(rec: dict) -> float | None:
    """재료 파일의 폭 / 높이 — 기록의 size · width/height, 없으면 파일을 열어 잰다(그림: PIL, 영상: ffprobe)"""
    sz = rec.get("size") if isinstance(rec.get("size"), list) and len(rec.get("size")) == 2 else None
    if not sz and rec.get("width") and rec.get("height") and rec.get("type") != "overlay":
        sz = [rec["width"], rec["height"]]
    try:
        if sz:
            return float(sz[0]) / float(sz[1])
        f = ROOT / str(rec.get("file") or "")
        if not rec.get("file") or not f.exists():
            return None
        if f.suffix.lower() in VIDEO_EXT:
            import subprocess
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(f)],
                               capture_output=True, text=True, timeout=30)
            w, h = [float(v) for v in r.stdout.strip().split(",")[:2]]
            return w / h
        from PIL import Image
        with Image.open(f) as im:
            return im.width / im.height
    except Exception:  # noqa: BLE001 — 못 재면 크기 맞춤 판단만 건너뛴다
        return None


def covers_frame(rec: dict, W: int, H: int) -> bool:
    """화면 비율 그대로 만든 그림 · 영상(PhotoCraft 장면 카드 full_frame, TextureCraft · SolidCraft 9:16 렌더 …)은 액자 없이 화면을 덮는다.
    실제 화면 캡처 · 녹화는 해당 없음(둥근 모서리 · 그림자 액자를 쓴다)"""
    if "_cover" not in rec:
        ar0 = file_aspect(rec) if rec.get("type") in ("video", "stock") else None
        if (rec.get("clip") or {}).get("fit") == "cover" or rec.get("fit") == "cover":
            rec["_cover"] = True              # 화면 비율로 잘라 둔 영상: 영화처럼 가득 — 액자 · 그림자 없이
        elif ar0 and abs(ar0 - W / H) < 0.03 * (W / H):
            rec["_cover"] = True              # 화면 비율(9:16)로 이미 맞춘 영상(리프레이밍한 클립 등) — 녹화 화면처럼 줄여 액자에 넣고 스크롤하지 않는다
        elif (rec.get("type") in SCREENS or mat_kind(rec) in ("icon", "doc_quote", "chart", "stat", "text")):
            rec["_cover"] = False
        elif rec.get("full_frame"):
            rec["_cover"] = True
        else:
            ar = file_aspect(rec)
            rec["_cover"] = bool(ar and abs(ar - W / H) < 0.03 * (W / H))
    return rec["_cover"]


def placement(rec: dict, layout: str = "card", W: int = 1080, H: int = 1920) -> str:
    """재료를 어디에 놓을지(full · center · left …) — 콘티가 정하지 않으면 레퍼런스 화면 문법(layout)을 따른다.
    'center' 는 사실상 기본값이라: 실제 화면 · 화면 비율 그림은 화면 가득, 레퍼런스가 화면 가득이면 사진 · 캡처도 화면 가득.
    left · right · top · bottom · card 처럼 뜻이 있는 배치만 지킨다"""
    kind = mat_kind(rec)
    place = (rec.get("spec") or {}).get("place") or "center"
    if place == "center" and layout != "band" and (kind in SCREENS or (kind in ("image", "photo", "illustration", "video") and covers_frame(rec, W, H))):
        place = "full"
    if layout == "full" and kind in ("image", "photo") and place == "center":
        place = "full"
    if place == "card":
        place = "center"
    if place == "full" and kind not in ("image", "photo", "illustration", *SCREENS):
        place = "center"
    return place


def is_full(rec: dict, layout: str = "card", W: int = 1080, H: int = 1920) -> bool:
    """material_jsx 가 이 재료를 화면 가득(full_still)으로 놓는가 — 다음 재료가 덮으며 들어올 때 앞 재료를 끝까지 둘지 정한다"""
    return placement(rec, layout, W, H) == "full"


# 재료 등장 프리셋(엔진 내장, PRESET_SEC 초) — 종류별 기본값. 콘티 재료 enter(프리셋 id 또는 false) > direction.enter > 이 표.
# 그림 · 사진 · 아이콘은 지금처럼 '살짝 커지며 나타나기'(프리셋 없음). 실제 화면은 다음 화면이 옆에서 밀려 들어오듯 부드러운 닦기
# 재료 등장 전환 — 예전 기본(종류별 닦기)은 이제 '시안' 하나일 뿐, 근거 없으면 바로 보인다(craft/design.py)
ENTER = {"screen": "wipeInFromRight", "web": "wipeInFromRight", "video": "wipeInFromRight", "stock": "fadeIn", "doc_quote": "wipeInFromTop"}
from . import design as _design  # noqa: E402
DZ: dict = _design.resolve({})     # build_jsx 가 콘티마다 다시 정한다
THEME: dict = {"panel": "[0.055, 0.063, 0.086]", "ink": "[1, 1, 1]", "dim": "[0, 0, 0]", "dim_op": 68, "accent": "[1, 0.84, 0.04]", "ink_stroke": "[0.02, 0.02, 0.05]", "label_stroke": "[0.02, 0.02, 0.05]"}   # 차트 패널 · 글자 색 — build_jsx 가 콘티 색(느낌 팔레트)으로 다시 정한다(2026-11-11: 크림 영상에 차트만 검은 판)
PRESET_SEC = 0.6     # 전환 프리셋 길이 — 엔진 값(fadeIn 0.5초 · 닦기 1초)을 이 안으로 줄인다


def enter_preset(rec: dict, direction: dict | None = None) -> str | None:
    sp = rec.get("spec") or {}
    if "enter" in sp:
        return sp["enter"] or None
    dz = _design.resolve({"direction": direction}) if direction else DZ
    return _design.enter_for(dz, mat_kind(rec))


# 배경 프리셋(엔진 내장, 표현식으로 계속 움직임) — 형식별 기본값. direction.bg_preset(id 또는 false) > 이 표 > 예전 dressBg.
# 기본은 절제: 격자 · 빛 · 고리 모두 옅게(재료가 주인공)
BG_PRESET = {"concept": "blueprintGrid", "mythbust": "blueprintGrid", "fix": "blueprintGrid", "compare": "blueprintGrid",
             "countdown": "blueprintGrid", "series": "blueprintGrid", "emotional": "bokehDrift", "ad": "pulseRings", "daily": "softGradientDrift"}


def fmt_name(sb: dict) -> str:
    """콘티 형식 — format 이 없으면 format 스킬 이름(format-ad 등)"""
    f = str(sb.get("format") or sb.get("format_skill") or sb.get("skill") or "")
    return f[7:] if f.startswith("format-") else f


def bg_preset(sb: dict) -> str | None:
    """배경 프리셋 — 콘티 direction(사용자 · 레퍼런스) 만. 형식별 표(BG_PRESET)는 시안 후보일 뿐(design.proposals)"""
    return _design.resolve(sb)["bg_preset"]


def _mix(a: list, b: list, t: float) -> list:
    return [round(x * (1 - t) + y * t, 4) for x, y in zip(a, b)]


def bg_tunes(preset: str, bg: list, pal: list) -> tuple[list, str | None, str | None]:
    """프리셋의 고정 색 · 세기 → 콘티 색으로: ([[효과 경로, 값] …], 표현식 바꿀 글자, 바꿀 값)"""
    light = 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2] > 0.5
    ink = [0.1, 0.11, 0.16] if light else [1.0, 1.0, 1.0]
    acc = pal[0] if pal else [1.0, 0.84, 0.04]
    if preset == "blueprintGrid":     # 판 = 바탕색, 격자 = 바탕 위 옅은 선(작은 격자는 거의 안 보이게)
        return [["effects/#1/color", bg], ["effects/#2/color", ink], ["effects/#2/opacity", 4],
                ["effects/#3/color", ink], ["effects/#3/opacity", 9 if light else 7], ["effects/#3/width", 108], ["effects/#3/height", 108]], None, None
    if preset == "bokehDrift":        # 판 = 바탕색, 빛망울 = 팔레트 색(옅게)
        t = [["effects/#1/color", bg]]
        for k in range(2, 8):
            t += [[f"effects/#{k}/color", pal[(k - 2) % len(pal)] if pal else [1, 1, 1]], [f"effects/#{k}/opacity", 14]]
        return t, None, None
    if preset == "pulseRings":        # 판 = 바탕색, 고리 = 강조색, 세기 100 → 26
        return [["effects/#1/color", bg]] + [[f"effects/#{k}/color", acc] for k in (2, 3, 4)], "100*Math.pow", "26*Math.pow"
    if preset == "softGradientDrift":  # 네 모서리 = 바탕색에 팔레트를 조금씩 섞은 색
        cs = [_mix(bg, pal[k % len(pal)] if pal else bg, 0.12 if k % 2 else 0.05) for k in range(4)]
        return [[f"effects/#1/positionsColors/color{k + 1}", cs[k]] for k in range(4)], None, None
    return [], None, None


# 글자 프리셋(엔진 내장 텍스트 애니메이터). 길이가 1.2~2초 고정이라 retimeKeys 로 줄인다
TITLE_PRESET = "bounceInWords"
SUB_PRESET = {"emotional": "fadeUpCharacters"}     # 형식별 자막 기본값 — 나머지는 지금의 짧은 '톡' 커지기(자막이 0.5초마다 바뀌어 단어 튀기기는 어지럽다)


def is_over(rec: dict, mats: list[dict]) -> bool:
    """이 재료를 앞 재료 위에 겹치나 — 지정(layer: over 또는 keep: true)"""
    sp = rec.get("spec") or {}
    return sp.get("layer") == "over" or bool(sp.get("keep")) or bool(rec.get("keep"))


def scene_materials(sid: str, n: int, sc: dict | None = None) -> list[dict]:
    """이 장면의 재료 기록 — 콘티에 지금 있는 재료만(지운 재료의 기록이 남아 있어도 그리지 않는다), 콘티 순서대로"""
    d = ROOT / "data" / "compositions" / sid / "craft" / "materials" / f"s{n:02d}"
    recs = [json.loads(f.read_text("utf-8")) for f in sorted(d.glob("*.json"))] if d.exists() else []
    recs = [r for r in recs if isinstance(r, dict) and r.get("type") and r.get("key") and not r.get("missing")]   # 재료 기록만(보조 파일 · 사용자 녹화 대기 제외)
    if sc is None:
        return recs
    order = [str(m.get("id") or f"m{i + 1}") for i, m in enumerate(sc.get("materials") or [])]
    by = {r["id"]: r for r in recs}
    return [by[i] for i in order if i in by]


def input_materials(mats: list[dict]) -> set:
    """화면에 내지 않을 재료 — 다른 재료의 입력이다: uses 로 가져다 쓰거나, 칸 안에 그 파일 경로가 적혀 있다(앱을 잇는 중간 단계)"""
    used = {v for r in mats for v in ((r.get("spec") or {}).get("uses") or {}).values()}
    for r in mats:
        text = json.dumps(r.get("spec") or {}, ensure_ascii=False)
        used |= {o.get("id") for o in mats if o is not r and o.get("id") and o.get("file") and f'/{Path(o["file"]).name}"' in text}
    return used


def palette_list(sid: str) -> list[list[float]]:
    """영상 팔레트(data/compositions/<id>/style.json 의 palette, 역할 순서) → 차트 · 강조 색. 없으면 기본"""
    f = ROOT / "data" / "compositions" / sid / "style.json"
    try:
        pal = (json.loads(f.read_text("utf-8")) if f.exists() else {}).get("palette") or {}
    except ValueError:
        pal = {}
    order = [pal.get(k) for k in ("accent", "accent2", "main", "main_dark", "light")] + ["#ffd60a", "#ff3d6b", "#14c6d0", "#52cc66"]
    return [rgb(c) for c in order if isinstance(c, str) and c.startswith("#")]


def adjust_jsx(mid: str, adj: dict, W: int, H: int) -> str:
    """재료 하나의 조정 값을 그 재료의 맨 위 레이어(부모 없는 것)에 얹는다 — 원래 배치 · 움직임(키프레임)은 그대로 두고 표현식으로 더한다.
    dx · dy: 화면 비율(0.1 = 폭 · 높이의 10%) · scale: 배수 · rot: 도 · opacity: 0~1 배수 · delay: 초(등장을 늦춤, 음수면 당김) · hide: 숨김
    (2026-11-10: 위치 · 크기 · 타이밍 조정마다 에이전트가 SVG 좌표 · 스크립트를 고치며 한 번에 수 분씩 들었다)"""
    dx, dy = float(adj.get("dx", 0)) * W, float(adj.get("dy", 0)) * H
    sc, rot, op = float(adj.get("scale", 1)), float(adj.get("rot", 0)), float(adj.get("opacity", 1))
    delay, hide = float(adj.get("delay", 0)), bool(adj.get("hide"))
    body = []
    if dx or dy:
        body.append(f"var P = T.property('Position'); if (!P.expression) P.expression = 'value + [{dx:.1f}, {dy:.1f}]';")
    if sc != 1:
        body.append(f"var S = T.property('Scale'); if (!S.expression) S.expression = '[value[0] * {sc:.4f}, value[1] * {sc:.4f}]';")
    if rot:
        body.append(f"var R = T.property('Rotation'); if (!R.expression) R.expression = 'value + {rot:.2f}';")
    if op != 1:
        body.append(f"var O = T.property('Opacity'); if (!O.expression) O.expression = 'value * {max(0.0, min(1.0, op)):.3f}';")
    if delay:
        body.append(f"L.startTime = L.startTime + {delay:.3f};")
    if hide:
        body.append("L.enabled = false;")
    if not body:
        return ""
    return (f"(function () {{ for (var i = 1; i <= c.numLayers; i++) {{ var L = c.layer(i); "
            f"if ((' ' + L.name + ' ').indexOf(' ' + {js(mid)} + ' ') < 0 || L.parent) continue; var T = L.property('Transform'); "
            + " ".join(body) + " } })();")


def _hex01(c, default):
    if isinstance(c, list) and len(c) >= 3:
        return [float(v) for v in c[:3]]
    if isinstance(c, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", c.strip()):
        h = c.strip().lstrip("#")
        return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return default


def spring_follow(targets: list, fps: int = 30, sec: float | None = None, stiffness: float = 60.0, damping: float = 0.75) -> list:
    """카메라를 목표에 스프링으로 매단다 — targets: [(초, x, y, 확대), …](그 시각부터 그 목표). 결과: 프레임마다 [x, y, 확대].
    stiffness: 단단함(클수록 빨리 붙음, 30~150) · damping: 1 이면 출렁임 없이 멈춤, 0.5 쯤이면 살짝 지나쳤다 돌아옴"""
    import math
    targets = sorted(targets, key=lambda t: t[0])
    sec = sec if sec is not None else targets[-1][0] + 1.5
    w0 = math.sqrt(stiffness)
    sub = 8
    dt = 1.0 / (fps * sub)
    pos = list(targets[0][1:4])
    vel = [0.0, 0.0, 0.0]
    out = []
    for f in range(int(round(sec * fps)) + 1):
        t = f / fps
        out.append([round(pos[0], 2), round(pos[1], 2), round(pos[2], 4)])
        goal = [v for tt, *v in targets if tt <= t + 1e-9][-1] if any(tt <= t + 1e-9 for tt, *_ in targets) else targets[0][1:4]
        for _ in range(sub):
            for k in range(3):
                a = w0 * w0 * (goal[k] - pos[k]) - 2 * damping * w0 * vel[k]
                vel[k] += a * dt
                pos[k] += vel[k] * dt
    return out


def camera_follow_jsx(J, sc: dict, mats: list[dict], slots: dict, words: list[dict], start: float, end: float, sec: float, fps: int, W: int, H: int, bottom: float) -> bool:
    """스프링 카메라: 장면 camera.follow 의 목표를 스프링으로 따라간다(늦게 붙고 부드럽게 멈춤). 목표 하나 =
    {"t": 초 | "at": "낱말", "x": 0.5, "y": 0.5, "zoom": 1.2}.
    camera.stiffness(단단함, 기본 60) · camera.damping(1 = 출렁임 없음, 기본 0.7). 정해 두면 '확대' · 천천히 밀기 대신 이것만 쓴다"""
    cf = (sc.get("camera") or {}) if isinstance(sc.get("camera"), dict) else {}
    follow = cf.get("follow")
    if not follow:
        return False
    pts = []        # (초, 화면 x px, y px, 확대) — 물체를 따라가는 구간은 프레임마다
    marks = []
    for e in follow:
        t = float(e["t"]) if isinstance(e.get("t"), (int, float)) else (cue_time(e.get("at"), words, start, end) if e.get("at") else 0.0)
        marks.append((0.0 if t is None else t, e))
    marks.sort(key=lambda m: m[0])
    for k, (t, e) in enumerate(marks):
        t_next = marks[k + 1][0] if k + 1 < len(marks) else sec
        z = float(e.get("zoom", 1.0))
        pts.append((t, float(e.get("x", 0.5)) * W, float(e.get("y", 0.5)) * H, z))
    if not pts:
        return False
    seq = spring_follow(pts, fps, sec, float(cf.get("stiffness", 60)), float(cf.get("damping", 0.7)))
    cx, cy = W / 2, H / 2
    flat = []
    for x, y, z in seq:
        flat += [round(cx - z * (x - cx), 1), round(cy - z * (y - cy), 1), round(z * 100, 2)]
    J(f"(function () {{ var d = {json.dumps(flat, separators=(',', ':'))}; var P = cam.property('Transform').property('Position'), S = cam.property('Transform').property('Scale'); "
      f"for (var i = 0; i < d.length / 3; i++) {{ var t = i / {fps}; P.setValueAtTime(t, [d[3 * i], d[3 * i + 1]]); S.setValueAtTime(t, [d[3 * i + 2], d[3 * i + 2]]); }} }})();")
    return True


def material_jsx(J, rec: dict, words: list[dict], start: float, end: float, sec: float, W: int, H: int, font: str, colors: list,
                 top: float = 0.0, bottom: float = 0.74, t_in: float | None = None, t_out: float | None = None, layout: str = "card",
                 direction: dict | None = None) -> None:
    """top · bottom: 재료가 쓸 세로 구간(화면 비율) — 제목 · 자막과 겹치지 않게"""
    sp = rec.get("spec") or {}
    t0 = cue_time(sp.get("cue"), words, start, end) if t_in is None else t_in
    t0 = 0.0 if t0 is None else t0
    mid = rec["id"]
    typ = rec["type"]
    if typ == "chart" and rec.get("as") != "image":
        # 막대 차트: 깨끗한 바탕(장면 배경 톤이 비치지 않게) · 옅은 눈금 · 기준선 · 항목 아이콘(Lucide) · 값 세기 · 배수 배지
        # 2026-11-04: 흐린 갈색 배경 위 막대만 있어 밋밋하다는 지적
        data = rec.get("data") or {}
        vals, labs, unit = data.get("values") or [], data.get("labels") or [], data.get("unit", "")
        icons = data.get("icons") or []
        n = max(1, len(vals))
        vmax = max(vals) if vals else 1
        title_h = 0.05 if data.get("title") else 0.0
        has_icon = any(icons)
        x0, x1 = 0.14 * W, 0.86 * W
        base = bottom * H - (250 if has_icon else 140)              # 아래: 아이콘 + 항목 이름 자리
        hmax = max(0.10 * H, base - (top + title_h) * H - 130)       # 위: 제목 + 값 글자 자리
        bw = min(260.0, (x1 - x0) / n * 0.58)
        best = vals.index(max(vals)) if vals else -1
        t_end = t_out if t_out is not None else sec
        tag = f" {mid}"
        J(f"var cpn = c.layers.addSolid({THEME['panel']}, {js('Panel' + tag)}, {W}, {H}, 1); var cpo = cpn.property('Transform').property('Opacity'); cpo.setValueAtTime({max(0.0, t0 - 0.12):.2f}, 0); cpo.setValueAtTime({t0 + 0.12:.2f}, 94);")
        for gi in range(1, 5):                                       # 옅은 눈금
            gy = base - hmax * gi / 4
            J(f"var gl = card(c, {js(f'Grid{tag} {gi}')}, {x1 - x0 + 60:.0f}, 2, {THEME['ink']}, 0); gl.property('Transform').property('Position').setValue([{W / 2}, {gy:.0f}]); gl.property('Transform').property('Opacity').setValueAtTime({t0:.2f}, 0); gl.property('Transform').property('Opacity').setValueAtTime({t0 + 0.3:.2f}, 7);")
        J(f"var bl = card(c, {js('Baseline' + tag)}, {x1 - x0 + 60:.0f}, 5, {THEME['ink']}, 2); bl.property('Transform').property('Position').setValue([{W / 2}, {base + 2:.0f}]); var blo = bl.property('Transform').property('Opacity'); blo.setValueAtTime({t0:.2f}, 0); blo.setValueAtTime({t0 + 0.2:.2f}, 40);")
        if data.get("title"):
            J(f"var ct = txt(c, {js('Chart title' + tag)}, {js(data['title'])}, {js(font)}, 64, {THEME['ink']}, null, 0, [{W / 2}, {(top + 0.035) * H:.0f}]); popIn(ct, {max(0.0, t0 - 0.05):.2f}, 0.18);")
        for i, (v, lab) in enumerate(zip(vals, labs)):
            cx = x0 + (x1 - x0) * (i + 0.5) / n
            hh = max(14.0, hmax * v / vmax)
            col = json.loads(THEME['accent']) if i == best else [0.42, 0.46, 0.56]      # 가장 큰 값만 콘티 강조색(느낌 팔레트) — 순서대로 고르다 청록이 됐다(2026-11-11), 나머지는 차분하게
            ti = t0 + 0.15 + i * 0.35
            J(f"var b = card(c, {js(f'Bar{tag} {i}')}, {bw:.0f}, {hh:.0f}, {js(col)}, 14); b.property('Transform').property('Anchor Point').setValue([0, {hh / 2:.0f}]); b.property('Transform').property('Position').setValue([{cx:.0f}, {base:.0f}]);")
            J(f"var bs = b.property('Transform').property('Scale'); bs.setValueAtTime({ti:.2f}, [100, 0]); bs.setValueAtTime({ti + 0.6:.2f}, [100, 100]); ease(bs, 85);")
            J(f"var vt = txt(c, {js(f'Value{tag} {i}')}, '0', {js(font)}, {96 if i == best else 70}, {js(json.loads(THEME['accent']) if i == best else json.loads(THEME['ink']))}, null, 0, [{cx:.0f}, {base - hh - 34:.0f}]);")
            J(f"vt.property('Source Text').expression = 'var v = linear(time, {ti:.2f}, {ti + 0.6:.2f}, 0, {v}); (Math.round(v * 10) / 10) + {js(unit)}';")
            J(f"vt.property('Transform').property('Opacity').setValueAtTime({max(0.0, ti - 0.01):.2f}, 0); vt.property('Transform').property('Opacity').setValueAtTime({ti + 0.1:.2f}, 100);")
            ly = base + 62
            if i < len(icons) and icons[i]:
                iy = base + 92
                J(f"var itl = c.layers.addShape(); itl.name = {js(f'IconTile{tag} {i}')}; var itg = itl.property('Contents').addProperty('ADBE Vector Group'); itg.property('Contents').addProperty('ADBE Vector Shape - Ellipse').property('Size').setValue([132, 132]); itg.property('Contents').addProperty('ADBE Vector Graphic - Fill').property('Color').setValue({js(col)}); itl.property('Transform').property('Position').setValue([{cx:.0f}, {iy:.0f}]); itl.property('Transform').property('Opacity').setValue(30);")
                J(f"var icf = app.project.importFile(new ImportOptions(new File({js(str(ROOT / icons[i]))}))); var icl = c.layers.add(icf); icl.name = {js(f'Icon{tag} {i}')}; var ick = 72 / icl.source.width * 100; icl.property('Transform').property('Scale').setValue([ick, ick]); icl.property('Transform').property('Position').setValue([{cx:.0f}, {iy:.0f}]);")
                for L in ("itl", "icl"):
                    J(f"var io_ = {L}.property('Transform').property('Opacity'); var iv_ = io_.value; io_.setValueAtTime({max(0.0, ti - 0.12):.2f}, 0); io_.setValueAtTime({ti + 0.08:.2f}, iv_);")
                J(f"var ics = icl.property('Transform').property('Scale'); ics.setValueAtTime({max(0.0, ti - 0.12):.2f}, [ick * 0.6, ick * 0.6]); ics.setValueAtTime({ti + 0.1:.2f}, [ick * 1.1, ick * 1.1]); ics.setValueAtTime({ti + 0.2:.2f}, [ick, ick]);")
                ly = base + 200
            J(f"var lb = txt(c, {js(f'Label{tag} {i}')}, {js(str(lab))}, {js(font)}, 48, {THEME['ink']}, null, 0, [{cx:.0f}, {ly:.0f}]); var lbo = lb.property('Transform').property('Opacity'); lbo.setValueAtTime({max(0.0, ti - 0.01):.2f}, 0); lbo.setValueAtTime({ti + 0.2:.2f}, 100);")
        # 배수 배지: 둘 이상 차이가 크면(5배 이상) 가장 큰 막대 옆에 '×100' — 숫자 차이를 한눈에
        pos = [v for v in vals if v > 0]
        if len(pos) >= 2 and vmax / min(pos) >= 5 and best >= 0:
            ratio = vmax / min(pos)
            rt = f"×{ratio:.0f}" if ratio >= 10 else f"×{ratio:.1f}".replace(".0", "")
            cxb = x0 + (x1 - x0) * (best + 0.5) / n
            hb_ = max(14.0, hmax)
            tb = t0 + 0.15 + best * 0.35 + 0.75
            side = -1 if best == n - 1 and n > 1 else 1
            bx_ = cxb + side * (bw / 2 + 20) - (0 if side > 0 else 0)
            J(f"var rb = txt(c, {js('Ratio' + tag)}, {js(rt)}, {js(font)}, 64, [0.07, 0.07, 0.09], null, 0, [{cxb - side * 0:.0f}, {base - hb_ * 0.5:.0f}]);")
            J(f"var rbb = fitBox(c, {js('RatioBox' + tag)}, {js('Ratio' + tag)}, [1, 0.84, 0.04], 40, 22, 40);")
            J(f"rb.property('Transform').property('Position').setValue([{cxb:.0f}, {base - hb_ * 0.5:.0f}]); var rbs = rb.property('Transform').property('Scale'); rbs.setValueAtTime({tb:.2f}, [0, 0]); rbs.setValueAtTime({tb + 0.14:.2f}, [118, 118]); rbs.setValueAtTime({tb + 0.24:.2f}, [100, 100]);")
            J(f"var rbo = rb.property('Transform').property('Opacity'); rbo.setValueAtTime({max(0.0, tb - 0.01):.2f}, 0); rbo.setValueAtTime({tb + 0.02:.2f}, 100);")
            J(f"var rbr = rb.property('Transform').property('Rotation'); rbr.setValue(-6);")
        if t_out is not None and t_out < sec - 0.05:   # 다음 재료가 나오면 차트 전체(바탕 · 막대 · 숫자 · 이름 · 제목 · 아이콘)가 비킨다
            J(f"for (var li = 1; li <= c.numLayers; li++) {{ var Lc = c.layer(li); if (/ {mid}( |$)/.test(Lc.name)) {{ var oc = Lc.property('Transform').property('Opacity'); var ov = oc.valueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, false); oc.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, ov); oc.setValueAtTime({t_out:.2f}, 0); }} }}")
        return
    if typ == "stat":
        # 숫자 덧씌우기(레퍼런스 문법): 카드 · 패널 없이 아래 재료 위에 바로 — 화면을 살짝 어둡게 하고 테두리 굵은 큰 숫자,
        # 위에 흰 설명 한 줄. 출처는 화면에 쓰지 않는다(설명란 '사용한 자료'로). 2026-11-03: 어두운 둥근 카드가 'AI 티'
        val = str(sp.get("value") or "")
        mnum = re.match(r"\s*([+\-]?)([\d.,]+)(.*)$", val)
        cy = (top + bottom) / 2 * H
        t1 = t_out if t_out is not None else sec
        # 덮개는 화면 전체 고정 — 이름에 재료 id 를 띄어 쓰면 adjust(위치 옮기기)가 덮개까지 옮겨 화면 위쪽을 덮었다(2026-11-11) · 색은 영상 바탕색(밝은 느낌이면 종이로 흐리게)
        J(f"var sd0 = c.layers.addSolid({THEME['dim']}, {js('Dim-' + mid)}, {W}, {H}, 1); var sdo = sd0.property('Transform').property('Opacity');")
        J(f"sdo.setValueAtTime(0, 0); sdo.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); sdo.setValueAtTime({t0 + 0.1:.2f}, {THEME['dim_op']}); sdo.setValueAtTime({max(t0 + 0.15, t1 - 0.15):.2f}, {THEME['dim_op']}); sdo.setValueAtTime({t1:.2f}, 0);")
        size = min(300, int(W * 1.0 / max(2.5, len(val))))
        J(f"var sv0 = txt(c, {js('Value ' + mid)}, {js(val)}, {js(font)}, {size}, {THEME['accent']}, {THEME['ink_stroke']}, {max(12, size // 9)}, [{W / 2}, {cy + size * 0.2:.0f}]);")
        # 등장: 크게 → 제자리(쿵) — 모든 재료가 같은 '살짝 커지기'로 나오지 않게
        J(f"var svs = sv0.property('Transform').property('Scale'); svs.setValueAtTime({max(0.0, t0 - 0.01):.2f}, [150, 150]); svs.setValueAtTime({t0 + 0.12:.2f}, [96, 96]); svs.setValueAtTime({t0 + 0.2:.2f}, [100, 100]);")
        if sp.get("label"):
            lab = str(sp["label"])
            lsz = max(44, min(72, int(W * 0.86 / max(1, len(lab)) * 1.1)))
            J(f"var sl0 = txt(c, {js('Label ' + mid)}, {js(lab)}, {js(font)}, {lsz}, {THEME['ink']}, {THEME['label_stroke']}, {0 if THEME['label_stroke'] == 'null' else max(6, lsz // 7)}, [{W / 2}, {cy - size * 0.55:.0f}]);")
            J(f"var sls = sl0.property('Transform').property('Position'); sls.setValueAtTime({t0:.2f}, [{W / 2 - 60}, {cy - size * 0.55:.0f}]); sls.setValueAtTime({t0 + 0.2:.2f}, [{W / 2}, {cy - size * 0.55:.0f}]); ease(sls, 80);")
        for L in ("sv0",) + (("sl0",) if sp.get("label") else ()):
            J(f"var lo_ = {L}.property('Transform').property('Opacity'); lo_.setValueAtTime(0, 0); lo_.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); lo_.setValueAtTime({t0 + 0.06:.2f}, 100); lo_.setValueAtTime({max(t0 + 0.1, t1 - 0.12):.2f}, 100); lo_.setValueAtTime({t1:.2f}, 0);")
        if mnum:
            sign, digits, rest = mnum.group(1), mnum.group(2).replace(",", ""), mnum.group(3)
            dec = len(digits.split(".")[1]) if "." in digits else 0
            try:
                target = float(digits)
                # 시작 값: 콘티 from(예: 101 → 1 로 떨어지는 숫자) — 없으면 0 에서 센다
                fm = re.match(r"\s*[+\-]?([\d.,]+)", str(sp.get("from") or ""))
                origin = float(fm.group(1).replace(",", "")) if fm else 0.0
                J(f"sv0.property('Source Text').expression = 'var v = linear(time, {t0:.2f}, {t0 + 0.5:.2f}, {origin}, {target}); {js(sign)} + v.toFixed({dec}) + {js(rest)}';")
            except ValueError:
                pass
        return
    # 관절 인형은 콘티에 동작(action)을 적은 캐릭터만 — 사물 · 자료(메뉴판 · 폰 · 문서)는 통째로 한 장(글자까지 그대로)
    if typ == "illustration" and rec.get("rig") and sp.get("action") and sp.get("action") != "still":
        # 부품 레이어 인형: 남은 세로 구간 안에 발을 붙이고 동작(idle · walk · wave · bounce)
        fig = {"name": mid, "at": sp.get("at", sp.get("place", "center")), "to": sp.get("to"), "action": sp.get("action", "idle"),
               "cue": sp.get("cue"), "size": round(max(0.3, (bottom - top) * float(sp.get("size", 0.9))), 3), "ground": bottom - 0.01}
        fig = {k2: v for k2, v in fig.items() if v is not None}
        if fig["at"] not in POS_X:
            fig["at"] = "center"
        puppet(J, "", fig, sec, words, start, end, W, H, 0, d=ROOT / rec["rig"])
        return
    f = rec.get("file")
    if not f:
        return
    path = ROOT / f
    kind = mat_kind(rec)
    pre_in = enter_preset(rec, direction) if t0 > 0.05 else None    # 0초에 시작하는 재료는 첫 프레임부터 보여야 한다
    J(f"var f = app.project.importFile(new ImportOptions(new File({js(str(path))}))); var ml = c.layers.add(f); ml.name = {js('Mat ' + mid)};")
    if path.suffix.lower() in VIDEO_EXT:
        J(f"try {{ ml.startTime = {t0:.2f}; }} catch (e) {{}}")   # 녹화는 등장하는 순간부터 재생
    if typ == "doc_quote":
        # 페이지를 화면 폭에 맞추고, 찾은 문장으로 확대해 들어가며 형광펜을 긋는다
        # 재료 단계가 진짜 형광펜(PdfCraft 주석)을 칠했으면(highlighted) 가짜 사각형은 그리지 않는다 — 확대만
        hl = rec.get("highlight") or []
        J("var r0 = ml.sourceRectAtTime(0, false);")
        J(f"var k0 = {W * 0.96} / r0.width * 100; ml.property('Transform').property('Scale').setValue([k0, k0]); ml.property('Transform').property('Anchor Point').setValue([0, 0]);")
        J(f"var px = {W * 0.02}, py = {top * H:.0f}; ml.property('Transform').property('Position').setValue([px, py]);")
        if pre_in:
            J(f"pre(c, ml, {js(pre_in)}, {t0:.2f}, {PRESET_SEC});")
        for k, (x, y, w, h) in enumerate([] if rec.get("highlighted") else hl):
            J(f"var hb = card(c, {js(f'Highlight {mid} {k}')}, {w:.1f}, {h * 1.1:.1f}, [1, 0.86, 0.1], 4); hb.property('Transform').property('Opacity').setValue(55);")
            J(f"hb.property('Transform').property('Anchor Point').setValue([{-w / 2:.1f}, 0]); hb.property('Transform').property('Position').setValue([px + {x:.1f} * k0 / 100, py + {y + h / 2:.1f} * k0 / 100]); hb.property('Transform').property('Scale').setValue([k0, k0]);")
            J(f"var hs = hb.property('Transform').property('Scale'); hs.setValueAtTime({t0 + 0.4 + k * 0.35:.2f}, [0, k0]); hs.setValueAtTime({t0 + 0.75 + k * 0.35:.2f}, [k0, k0]); ease(hs, 60);")
            J("hb.parent = ml;")
        if hl:
            # 편집자처럼: 찾은 줄의 글자가 화면에서 ~64px 이 되게 확대하고, 문장 가운데로 간다(옆이 잘려도 됨).
            # focus(문장 전체 상자, PdfCraft 어댑터)가 있으면 그 가운데로 — 줄이 끊긴 한국어 문장은 hl[0] 이 윗줄 끝 한 글자일 수 있다.
            # 문장 주변만 잘라 낸 그림(crop)은 이미 크다 → 문장 상자가 화면 폭 안에 들어오는 만큼만(최소 1배)
            x, y, w, h = hl[0]
            fx = rec.get("focus") if isinstance(rec.get("focus"), list) and len(rec.get("focus")) == 4 else None
            cxp, cyp = (fx[0] + fx[2] / 2, fx[1] + fx[3] / 2) if fx else (x + min(w, W * 0.9) / 2, y + h / 2)
            lo = 1.0 if rec.get("crop") else 1.4
            fit = f", {W * 0.92:.0f} / ({fx[2]:.1f} * k0 / 100)" if fx and rec.get("crop") else ""
            J(f"var zk = Math.max({lo}, Math.min(3.2, 64 / ({h:.1f} * k0 / 100){fit}));")
            J(f"var mp = ml.property('Transform').property('Position'), ms = ml.property('Transform').property('Scale');")
            J(f"mp.setValueAtTime({t0:.2f}, [px, py]); ms.setValueAtTime({t0:.2f}, [k0, k0]);")
            J(f"mp.setValueAtTime({t0 + 0.6:.2f}, [{W / 2} - {cxp:.1f} * k0 / 100 * zk, {(top + bottom) / 2 * H:.0f} - {cyp:.1f} * k0 / 100 * zk]); ms.setValueAtTime({t0 + 0.6:.2f}, [k0 * zk, k0 * zk]); ease(mp, 75); ease(ms, 75);")
        exit_jsx(J, "ml", rec, t0, t_out, sec)
        return
    # 배치(placement): 모르는 종류(앱 어댑터의 새 재료)는 kind(as 힌트 · 확장자)로 그림 · 영상처럼 놓는다
    place = placement(rec, layout, W, H)
    if place == "full":
        full_still(J, rec, words, start, end, sec, W, H, t0, t_out, bottom, font, pre_in=pre_in)
        return
    px, py, pw, ph = PLACE.get(place, PLACE["center"])
    if place != "full":                      # 남은 세로 구간 안으로
        py, ph = top + (bottom - top) * (py - 0.15) / 0.7, min(ph, (bottom - top) * 0.92)
    # 크기 · 기준점은 소스의 실제 픽셀 크기로(sourceRectAtTime 은 PNG 해상도 정보에 따라 달라 그림이 커졌다)
    J("var r1 = { left: 0, top: 0, width: ml.source.width, height: ml.source.height };")
    J("ml.property('Transform').property('Anchor Point').setValue([r1.width / 2, r1.height / 2]);")   # 기준점 = 가운데(안 하면 왼쪽 위에 붙음)
    fit = "Math.max" if place == "full" else "Math.min"
    if typ == "icon":                        # 로고는 작게(가운데 칸의 절반) — 흰 타일 위에
        pw, ph = pw * 0.5, ph * 0.5
    elif typ == "meme" and place == "center":   # 짤은 반응 박자 — 검은 바탕에 작게 툭 놓지 않고 화면을 크게(2026-11-09 git 영상)
        pw, ph = 0.96, min(0.66, (bottom - top) * 0.96)
    J(f"var k1 = {fit}({W * pw} / r1.width, {H * ph} / r1.height) * 100; ml.property('Transform').property('Scale').setValue([k1, k1]); ml.property('Transform').property('Position').setValue([{W * px:.0f}, {H * py:.0f}]);")
    if typ == "icon":
        # 흰 둥근 타일(앱 아이콘처럼): 로고 색이 배경에 묻히지 않게. 로고에 붙여(parent) 같이 커지고 움직인다
        J(f"var tl = card(c, {js('Tile ' + mid)}, r1.width * 1.6, r1.height * 1.6, [1, 1, 1], r1.width * 0.36); tl.moveAfter(ml); tl.parent = ml; tl.property('Transform').property('Scale').setValue([100, 100]); tl.property('Transform').property('Anchor Point').setValue([0, 0]); tl.property('Transform').property('Position').setValue([r1.width / 2, r1.height / 2]); tl.inPoint = {t0:.2f};")
        if t_out is not None:
            J(f"tl.outPoint = {t_out:.2f};")
    t_end = t_out if t_out is not None else sec
    if place != "full":
        screen = kind in SCREENS
        if screen:
            # 실제 화면(칸에 놓인 캡처 · 녹화): 둥근 모서리 + 그림자 + 장면 길이에 맞춘 느린 밀기(4%)
            if sp.get("shadow", DZ["frame"]["shadow"]) or sp.get("round", DZ["frame"]["round"]):
                J(f"roundShadow(ml, {js(bool(sp.get('shadow', DZ['frame']['shadow'])))}, {js(bool(sp.get('round', DZ['frame']['round'])))});")
        ms_keys = f"ms1.setValueAtTime({t0:.2f}, [k1 * 0.92, k1 * 0.92]); ms1.setValueAtTime({t0 + 0.25:.2f}, [k1, k1]);"
        if pre_in or screen or not DZ["text_pop"]:
            ms_keys = f"ms1.setValueAtTime({t0:.2f}, [k1, k1]);"     # 프리셋이 등장을 맡거나 · 화면이거나 · '톡' 을 끈 방향이면 크기는 밀기만
        push = float(sp.get("push", DZ["frame"]["push"] if screen else 1.0))
        if push != 1.0:
            ms_keys += f" ms1.setValueAtTime({max(t0 + 0.3, t_end):.2f}, [k1 * {push}, k1 * {push}]);"
        J(f"var ms1 = ml.property('Transform').property('Scale'); {ms_keys} ease(ms1, 45);")
        if pre_in:
            J(f"if (!pre(c, ml, {js(pre_in)}, {t0:.2f}, {PRESET_SEC})) {{ var mo1 = ml.property('Transform').property('Opacity'); mo1.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); mo1.setValueAtTime({t0 + 0.15:.2f}, 100); }}")
        elif t0 > 0.05:   # 0초에 시작하는 재료는 처음부터 보이게 — 첫 프레임이 비면 피드에서 바로 넘겨진다(템포 검사 L32)
            J(f"var mo1 = ml.property('Transform').property('Opacity'); mo1.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); mo1.setValueAtTime({t0 + 0.15:.2f}, 100);")
        if not screen and DZ["cam_push"] > 1.0:
            # 천천히 다가가기(밀기를 쓰는 방향에서만)
            J(f"ml.property('Transform').property('Position').expression = 'value + [0, -18 * Math.min(1, Math.max(0, (time - {t0:.2f}) / {max(1.0, t_end - t0):.2f}))]';")
    exit_jsx(J, "ml", rec, t0, t_out, sec)


def exit_jsx(J, var: str, rec: dict, t0: float, t_out: float | None, sec: float) -> None:
    """다음 재료가 나오면 비킨다: 다음 재료가 화면 가득 닦으며 덮으면(_hold_out) 그동안 그대로 있다가 사라지고,
    콘티 exit(퇴장 프리셋 id)가 있으면 그 프리셋, 아니면 짧게 흐려진다"""
    if t_out is None or t_out >= sec - 0.05:
        return
    ex = (rec.get("spec") or {}).get("exit")
    if rec.get("_hold_out"):
        J(f"{var}.outPoint = {min(sec, t_out + PRESET_SEC + 0.03):.2f};")
    elif ex:
        J(f"pre(c, {var}, {js(ex)}, {max(t0 + 0.2, t_out - PRESET_SEC):.2f}, {PRESET_SEC}); {var}.outPoint = {t_out:.2f};")
    else:
        J(f"var mo = {var}.property('Transform').property('Opacity'); mo.setValueAtTime({max(t0 + 0.2, t_out - 0.18):.2f}, 100); mo.setValueAtTime({t_out:.2f}, 0);")


def ov_target(rec: dict) -> str:
    return str((rec.get("spec") or {}).get("target") or rec.get("target") or "")


def overlay_jsx(J, rec: dict, target: dict | None, slot: tuple, words: list[dict], start: float, end: float, sec: float) -> None:
    """주석 오버레이(VectorCraft 박스 · 화살표 등 투명 PNG): 대상 재료 그림의 자식 레이어로 붙인다 — 대상이 확대 · 이동해도 같은 자리.
    기록 layers: [{file, box:[x, y, w, h](0~1, 대상 그림 기준), cue}] 를 차례로(cue 낱말 시각, 없으면 대상 등장 뒤 0.5초 간격) 띄운다"""
    sp = rec.get("spec") or {}
    tid = ov_target(rec)
    layers = list(rec.get("layers") or [])
    if not layers and rec.get("file"):
        layers = [{"file": rec["file"], "box": sp.get("box") or [0, 0, 1, 1], "cue": sp.get("cue")}]
    if not tid or not layers:
        return
    oid = str(rec.get("id"))
    if target is None:
        J(f"writeLn({js(f'오버레이 {oid}: 대상 재료 {tid} 가 이 장면에 없습니다')});")
        return
    t_in, t_out = slot
    t_in = 0.0 if t_in is None else float(t_in)
    end_t = sec if t_out is None or t_out >= sec - 0.05 else (t_out + PRESET_SEC if target.get("_hold_out") else t_out)
    base_dir = (ROOT / rec["file"]).parent if rec.get("file") else None     # 레이어 파일이 상대 경로면: 저장소 기준, 없으면 기록 파일 옆
    J(f"var tg = null; for (var li = 1; li <= c.numLayers; li++) {{ if (c.layer(li).name == {js('Mat ' + tid)}) tg = c.layer(li); }}")
    J(f"if (!tg) writeLn({js(f'오버레이 {oid}: 대상 레이어 Mat {tid} 가 없습니다(그림 파일이 없는 재료)')});")
    for i, ly in enumerate(layers):
        fp = Path(str(ly.get("file") or ""))
        if not fp.is_absolute():
            cand = ROOT / fp
            fp = cand if cand.exists() or base_dir is None else base_dir / fp
        x, y, w, h = [float(v) for v in (ly.get("box") or [0, 0, 1, 1])]
        tc = cue_time(ly.get("cue"), words, start, end)
        t = tc if tc is not None else t_in + PRESET_SEC * (i + 1)
        t = max(0.0, min(t, end_t - 0.3))
        nm = f"Overlay {oid} {i + 1}"
        J(f"if (tg) {{ var of = app.project.importFile(new ImportOptions(new File({js(str(fp))}))); var ol = c.layers.add(of); ol.name = {js(nm)}; ol.moveBefore(tg); ol.parent = tg;")
        J(f"  var ow = ol.source.width, oh = ol.source.height, tw = tg.source.width, th = tg.source.height; var ok = Math.min({w:.4f} * tw / ow, {h:.4f} * th / oh) * 100;")
        J(f"  ol.property('Transform').property('Anchor Point').setValue([ow / 2, oh / 2]); ol.property('Transform').property('Position').setValue([{x + w / 2:.4f} * tw, {y + h / 2:.4f} * th]);")
        J(f"  var os_ = ol.property('Transform').property('Scale'); os_.setValueAtTime({t:.2f}, [ok * 0.9, ok * 0.9]); os_.setValueAtTime({t + 0.2:.2f}, [ok, ok]); ease(os_, 70);")
        J(f"  var oo_ = ol.property('Transform').property('Opacity'); oo_.setValueAtTime({t:.2f}, 0); oo_.setValueAtTime({t + 0.12:.2f}, 100); ol.inPoint = {t:.2f}; ol.outPoint = {end_t:.2f}; }}")


def _norm(t: str) -> str:
    return re.sub(r"[\s,.!?·'\"’”“()]+", "", str(t)).lower()


def focus_events(rec: dict, words: list[dict], start: float, t0: float, t_out: float | None, sec: float) -> list[dict]:
    """나레이션이 캡처 속 글자(숫자 · 낱말)를 말하는 순간 → 그 글자 상자로 확대 · 동그라미.
    재료 단계가 남긴 글자 인식 결과(rec["ocr"]: [{text, box(0~1)}])와 단어 시각을 맞춘다. 재료 하나에 최대 3번"""
    ocr = [o for o in (rec.get("ocr") or []) if o.get("text") and o.get("box")]
    if not ocr:
        return []
    end_t = t_out if t_out is not None else sec
    out, used = [], set()
    for w in words:
        tw = w["startMs"] / 1000 - start
        if tw < t0 + 0.4 or tw > end_t - 0.6:
            continue
        key = _norm(w.get("text") or "")
        key = re.sub(r"(은|는|이|가|을|를|에|의|도|로|으로|요|죠|예요|이에요)$", "", key)
        if len(key) < 2 or not (re.search(r"\d", key) or len(key) >= 3):
            continue
        for k, o in enumerate(ocr):
            if k in used or key not in _norm(o["text"]):
                continue
            x, y, bw, bh = o["box"]
            if bw > 0.9 or bh > 0.3:          # 거의 전체 문단이면 짚을 의미가 없다
                continue
            used.add(k)
            out.append({"t": round(tw, 2), "box": [x, y, bw, bh], "text": o["text"]})
            break
        if len(out) >= 3:
            break
    # 너무 붙은 짚기는 하나만(1.2초 간격)
    keep = []
    for e in out:
        if not keep or e["t"] - keep[-1]["t"] >= 1.2:
            keep.append(e)
    return keep


def full_still(J, rec: dict, words: list[dict], start: float, end: float, sec: float, W: int, H: int, t0: float, t_out: float | None, bottom: float, font: str = "",
               pre_in: str | None = None) -> None:
    """화면 가득 문법(레퍼런스): 그림을 폭에 꽉 채우고, 남는 위아래는 같은 그림을 크게 흐리게 깔아 채운다.
    천천히 다가가고(정지 방지), 말이 캡처 속 글자를 짚으면 그곳으로 확대 + 노란 동그라미, 세로로 긴 캡처는 1.5초마다 아래로 훑는다"""
    mid = rec["id"]
    end_t = t_out if t_out is not None else sec
    # 흐린 그림 배경은 쓰지 않는다 — 재료마다 밝기가 달라 화면 전체가 번쩍였다(2026-11-03: 0.07초 사이 4 ↔ 82, 30초에 18번). 배경은 장면 내내 같은 어두운 그라데이션
    J("var r1 = { width: ml.source.width, height: ml.source.height }; ml.property('Transform').property('Anchor Point').setValue([r1.width / 2, r1.height / 2]);")
    # 폭에 꽉(조금 여백) — 세로로 너무 길면 화면 높이의 82% 까지만 보이고 나머지는 훑는다
    J(f"var k1 = {W * 0.96} / r1.width * 100; var hh = r1.height * k1 / 100; var cy = {H * 0.45:.0f};")
    kind = mat_kind(rec)
    phone = kind in SCREENS and (rec.get("mobile") or (rec.get("spec") or {}).get("mobile"))
    if phone:
        # 폰 화면 녹화: 세로 화면을 가득(레퍼런스처럼 액자 없이) — 자막 · 단계 꼬리표가 그 위에
        pb = float(rec.get("_pin_bottom") or 0.0)
        if W > H * 0.75:   # 가로 · 정사각 화면: 세로 녹화(대화창 · 터미널 · 폰 화면)는 높이에 맞춰 가운데에 — 옆은 바탕색
            J(f"k1 = Math.min({W * 0.92:.0f} / r1.width, {H * (0.97 - pb):.0f} / r1.height) * 100; hh = r1.height * k1 / 100; cy = {H * pb:.0f} + ({H * (1 - pb):.0f}) / 2;")
        elif pb:   # 위쪽 고정 제목이 있으면 녹화는 그 띠 아래에서 시작(제목이 말풍선 · 글자를 가리지 않게) — 아래는 넘치면 잘림
            J(f"k1 = Math.max({W} / r1.width, {H * (1 - pb):.0f} / r1.height) * 100; hh = r1.height * k1 / 100; cy = {H * pb:.0f} + hh / 2;")
        else:
            J(f"k1 = Math.max({W} / r1.width, {H} / r1.height) * 100; hh = r1.height * k1 / 100; cy = {H / 2};")
    cover = not phone and covers_frame(rec, W, H)
    if cover:   # 화면 비율 그대로 만든 그림 · 영상(장면 카드 · 3D 렌더): 액자 · 그림자 없이 화면을 덮는다
        J(f"k1 = Math.max({W} / r1.width, {H} / r1.height) * 100; hh = r1.height * k1 / 100; cy = {H / 2};")
    J("ml.property('Transform').property('Scale').setValue([k1, k1]); ml.property('Transform').property('Position').setValue([" + f"{W / 2}" + ", cy]);")
    if not phone and not cover:
        # 실제 화면(캡처 · 녹화)은 둥근 모서리 + 그림자, 그림 · 사진은 그림자만. 폰 화면 녹화는 레퍼런스처럼 액자 없이 가득
        spf = rec.get("spec") or {}
        if kind in SCREENS:
            if spf.get("shadow", DZ["frame"]["shadow"]) or spf.get("round", DZ["frame"]["round"]):
                J(f"roundShadow(ml, {js(bool(spf.get('shadow', DZ['frame']['shadow'])))}, {js(bool(spf.get('round', DZ['frame']['round'])))});")
        elif spf.get("shadow", DZ["frame"]["shadow"]):
            J("try { var dsh = ml.property('Effects').addProperty('ADBE Drop Shadow'); dsh.property('Opacity').setValue(70); dsh.property('Distance').setValue(18); dsh.property('Softness').setValue(60); dsh.property('Direction').setValue(180); } catch (e) {}")
    for k, stp in enumerate(rec.get("steps") or []):
        # 단계 꼬리표('1. 주소 입력'): 그 동작이 화면에 나오는 순간 — 아래쪽 보라 알약(레퍼런스 문법)
        ts = t0 + float(stp["t"])
        te_ = min(end_t, t0 + float(stp.get("t_end", stp["t"] + 1.2)))
        if not stp.get("label") or ts >= end_t - 0.2:
            continue
        J(f"var sp{k} = txt(c, {js(f'Step {mid} {k}')}, {js(str(stp['label']))}, {js(font)}, 64, [1, 1, 1], null, 0, [{W / 2}, {H * 0.64:.0f}]);")
        J(f"var sb{k} = fitBox(c, {js(f'StepBox {mid} {k}')}, {js(f'Step {mid} {k}')}, [0.42, 0.36, 0.95], 26, 34, 16);")
        for L in (f"sp{k}", f"sb{k}"):
            J(f"var so_ = {L}.property('Transform').property('Opacity'); so_.setValueAtTime(0, 0); so_.setValueAtTime({max(0.0, ts - 0.01):.2f}, 0); so_.setValueAtTime({ts + 0.08:.2f}, 100); so_.setValueAtTime({max(ts + 0.1, te_ - 0.08):.2f}, 100); so_.setValueAtTime({te_:.2f}, 0);")
    fade_in = f"var o_ = ml.property('Transform').property('Opacity'); o_.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); o_.setValueAtTime({t0 + 0.2:.2f}, 100);"
    if pre_in:      # 등장 프리셋(닦기 등) — 안 되면 예전처럼 흐려지며 나타나기
        J(f"if (!pre(c, ml, {js(pre_in)}, {t0:.2f}, {PRESET_SEC})) {{ {fade_in} }}")
    elif t0 > 0.05:
        J(fade_in)
    exit_jsx(J, "ml", rec, t0, t_out, sec)
    if phone and not rec.get("_subs", True):
        return            # 자막 · 단계 꼬리표가 없으면 그림자도 없다(2026-11-04: 나레이션 없는 영상 아래 1/3 이 빈 어두운 띠)
    if phone:
        # 자막 그림자: 밝은 화면 위 자막이 읽히게 아래쪽을 부드럽게 어둡게(가장자리는 흐림으로 풀어서)
        J(f"var shd = card(c, {js('Shade ' + mid)}, {W * 1.4:.0f}, {H * 0.36:.0f}, [0, 0, 0], 0); shd.property('Transform').property('Position').setValue([{W / 2}, {H * 0.9:.0f}]);")
        J("try { var sbl = shd.property('Effects').addProperty('ADBE Gaussian Blur 2'); sbl.property(1).setValue(120); } catch (e) {}")
        J(f"var sho = shd.property('Transform').property('Opacity'); sho.setValueAtTime(0, 0); sho.setValueAtTime({max(0.0, t0 - 0.01):.2f}, 0); sho.setValueAtTime({t0 + 0.2:.2f}, 62);")
        if t_out is not None and t_out < sec - 0.05:
            if rec.get("_hold_out"):
                J(f"shd.outPoint = {min(sec, t_out + PRESET_SEC + 0.03):.2f};")
            else:
                J(f"sho.setValueAtTime({max(t0 + 0.25, t_out - 0.2):.2f}, 62); sho.setValueAtTime({t_out:.2f}, 0);")
        return            # 폰 화면은 확대 · 훑기 없이 그대로(녹화 자체가 움직인다)
    # 주석 오버레이가 짚으면 동그라미는 안 그린다. 이미 짜인 화면(PhotoCraft 카드 등 full_frame)도 — 제목 글자에 동그라미 · 확대가 겹쳤다(2026-11-06)
    ev = [] if rec.get("_no_focus") or rec.get("full_frame") else focus_events(rec, words, start, t0, t_out, sec)
    hb0, ht0 = rec.get("highlight_box"), rec.get("highlight_t")
    if not ev and not words and isinstance(hb0, list) and len(hb0) == 4 and isinstance(ht0, (int, float)) and t0 + ht0 < (t_out if t_out is not None else sec) - 0.4:
        ev = [{"t": round(t0 + float(ht0), 2), "box": hb0}]       # 말이 없는 영상: 강조 줄이 찍히는 순간 그 줄로 다가간다(감독이 짚을 한 곳)
    J("var ps = ml.property('Transform').property('Position'), ss = ml.property('Transform').property('Scale');")
    J(f"ss.setValueAtTime({t0:.2f}, [k1, k1]); ps.setValueAtTime({t0:.2f}, [{W / 2}, cy]);")
    if cover and not ev:
        # 화면을 덮는 그림: 장면 길이 동안 느리게 밀기(5%). 강조 상자(highlight_box, 0~1)가 있으면 그쪽으로 조금(8%, 가장자리가 비지 않는 만큼만)
        hb = rec.get("highlight_box")
        z = 1.08 if hb else 1.05
        dx = dy = 0.0
        if isinstance(hb, list) and len(hb) == 4:
            lim_x, lim_y = (z - 1) * W / 2, (z - 1) * H / 2
            dx = max(-lim_x, min(lim_x, (0.5 - (hb[0] + hb[2] / 2)) * W * z))
            dy = max(-lim_y, min(lim_y, (0.5 - (hb[1] + hb[3] / 2)) * H * z))
        J(f"ss.setValueAtTime({max(t0 + 0.3, end_t):.2f}, [k1 * {z}, k1 * {z}]); ps.setValueAtTime({max(t0 + 0.3, end_t):.2f}, [{W / 2 + dx:.1f}, cy + {dy:.1f}]); ease(ss, 40); ease(ps, 40);")
        return
    if ev:
        for n, e in enumerate(ev):
            x, y, bw, bh = e["box"]
            tf = e["t"]
            # 짚을 글자 상자의 가운데를 화면 가운데(위쪽 45%)로, 상자 폭이 화면의 60% 가 되게(최대 2.6배)
            J(f"var bx = {x + bw / 2:.4f} * r1.width, by = {y + bh / 2:.4f} * r1.height, bwp = {bw:.4f} * r1.width;")
            J(f"var kz = Math.max(k1, Math.min(k1 * 2.6, {W * 0.6} / bwp * 100));")
            J(f"ss.setValueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, ss.valueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, false)); ps.setValueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, ps.valueAtTime({max(t0 + 0.05, tf - 0.15):.2f}, false));")
            J(f"ss.setValueAtTime({tf + 0.35:.2f}, [kz, kz]); ps.setValueAtTime({tf + 0.35:.2f}, [{W / 2} - (bx - r1.width / 2) * kz / 100, {H * 0.42:.0f} - (by - r1.height / 2) * kz / 100]);")
            # 노란 동그라미: 그림의 자식 레이어(그림 좌표) — 확대 · 이동을 같이 따라간다
            J(f"var rg = c.layers.addShape(); rg.name = {js(f'Ring {mid} {n}')}; var rgg = rg.property('Contents').addProperty('ADBE Vector Group');")
            J(f"var rge = rgg.property('Contents').addProperty('ADBE Vector Shape - Ellipse'); rge.property('Size').setValue([bwp * 1.25 + 30, {bh:.4f} * r1.height * 2.0 + 30]);")
            J("var rgs = rgg.property('Contents').addProperty('ADBE Vector Graphic - Stroke'); rgs.property('Color').setValue([1, 0.84, 0.04]); rgs.property('Stroke Width').setValue(10 * 100 / kz);")
            J("rg.parent = ml; rg.property('Transform').property('Position').setValue([bx, by]);")
            end_r = ev[n + 1]["t"] - 0.2 if n + 1 < len(ev) else end_t
            J(f"rg.inPoint = {tf + 0.25:.2f}; rg.outPoint = {max(tf + 0.6, end_r):.2f};")
            J(f"var rgsc = rg.property('Transform').property('Scale'); rgsc.setValueAtTime({tf + 0.25:.2f}, [40, 40]); rgsc.setValueAtTime({tf + 0.5:.2f}, [100, 100]); ease(rgsc, 70);")
        J("ease(ss, 80); ease(ps, 80);")
    elif not rec.get("_under_overlay") and len([o for o in (rec.get("ocr") or []) if o.get("box") and o["box"][2] < 0.95]) >= 3 and end_t - t0 >= 2.4:
        # 짚을 낱말이 없으면: 글자 줄을 1.5초마다 차례로 따라가며 확대(사람이 문서를 읽어 주듯) — 화면이 1~2초마다 바뀐다
        lines = [o for o in rec["ocr"] if o.get("box") and o["box"][2] < 0.95 and o["box"][3] < 0.2]
        n_st = max(1, min(len(lines), int((end_t - t0 - 0.6) // 1.5)))
        pick = [lines[round(k * (len(lines) - 1) / max(1, n_st - 1))] for k in range(n_st)] if n_st > 1 else lines[:1]
        for k, o in enumerate(pick):
            x, y, bw, bh = o["box"]
            tf = t0 + 0.6 + k * 1.5
            J(f"var bx = {x + bw / 2:.4f} * r1.width, by = {y + bh / 2:.4f} * r1.height;")
            J(f"var kz = Math.max(k1 * 1.25, Math.min(k1 * 1.9, {W * 0.9} / ({bw:.4f} * r1.width) * 100));")
            J(f"ss.setValueAtTime({tf:.2f}, ss.valueAtTime({tf:.2f}, false)); ps.setValueAtTime({tf:.2f}, ps.valueAtTime({tf:.2f}, false));")
            J(f"ss.setValueAtTime({tf + 0.4:.2f}, [kz, kz]); ps.setValueAtTime({tf + 0.4:.2f}, [{W / 2} - (bx - r1.width / 2) * kz / 100, {H * 0.43:.0f} - (by - r1.height / 2) * kz / 100]);")
        J("ease(ss, 80); ease(ps, 80);")
    else:
        # 짚을 글자가 없으면: 세로로 길면 1.5초마다 아래로 훑고, 아니면 천천히 다가간다
        J(f"var over = hh - {H * 0.82:.0f};")
        steps = max(1, int((end_t - t0) // 1.5))
        J(f"if (over > 40) {{ var y0 = cy + hh / 2 - {H * 0.41:.0f}; ps.setValueAtTime({t0:.2f}, [{W / 2}, y0]); for (var st = 1; st <= {steps}; st++) {{ var tt = {t0:.2f} + st * {(end_t - t0) / (steps + 1):.3f}; ps.setValueAtTime(tt - 0.01, [{W / 2}, y0 - over * (st - 1) / {steps}]); ps.setValueAtTime(tt + 0.45, [{W / 2}, y0 - over * st / {steps}]); }} ease(ps, 80); }}")
        if not rec.get("zoomed"):      # FilmCraft 가 이미 확대한 녹화(zoomed)는 카메라 밀기를 겹치지 않는다
            J(f"ss.setValueAtTime({end_t:.2f}, [k1 * 1.07, k1 * 1.07]);")


class Jsx:
    """JSX 문장 모음 — 사람이 읽을 수 있게 장면마다 주석을 남긴다"""

    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, s: str):
        self.lines.append(s)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


PRELUDE = r"""
function ease(prop, inf) { var e = new KeyframeEase(0, inf || 70); for (var k = 1; k <= prop.numKeys; k++) { var arr = []; for (var d = 0; d < (prop.value.length || 1); d++) arr.push(e); try { prop.setTemporalEaseAtKey(k, arr, arr); } catch (err) {} } }
function txt(comp, name, s, font, size, fill, stroke, strokeW, pos) {
  var t = comp.layers.addText(s); t.name = name;
  var d = t.property("Source Text").value;
  d.font = font; d.fontSize = size; d.applyFill = true; d.fillColor = fill; d.justification = ParagraphJustification.CENTER_JUSTIFY;
  if (stroke) { d.applyStroke = true; d.strokeColor = stroke; d.strokeWidth = strokeW; d.strokeOverFill = false; } else { d.applyStroke = false; }
  t.property("Source Text").setValue(d);
  t.property("Transform").property("Position").setValue(pos);
  return t;
}
// atT: 글자 애니메이터(단어 튀기기 등)가 도는 동안 상자가 출렁이지 않게, 그 시각 이후의 글자 크기로 잰다
function fitBox(comp, name, target, color, padX, padY, round, atT) {
  var b = comp.layers.addShape(); b.name = name;
  var g = b.property("Contents").addProperty("ADBE Vector Group");
  var r = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
  var tt = (atT === undefined || atT === null) ? "time" : "Math.max(time, " + atT + ")";
  r.property("Size").expression = "var q = thisComp.layer('" + target + "').sourceRectAtTime(" + tt + ", false); [q.width + " + padX + ", q.height + " + padY + "]";
  r.property("Position").expression = "var q = thisComp.layer('" + target + "').sourceRectAtTime(" + tt + ", false); [q.left + q.width / 2, q.top + q.height / 2]";
  r.property("Roundness").setValue(round);
  g.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  b.property("Transform").property("Position").expression = "thisComp.layer('" + target + "').transform.position";
  b.property("Transform").property("Scale").expression = "thisComp.layer('" + target + "').transform.scale";
  b.property("Transform").property("Opacity").expression = "thisComp.layer('" + target + "').transform.opacity";
  b.moveAfter(comp.layer(target));
  return b;
}
function card(comp, name, w, h, color, round) {
  var b = comp.layers.addShape(); b.name = name;
  var g = b.property("Contents").addProperty("ADBE Vector Group");
  var r = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
  r.property("Size").setValue([w, h]); r.property("Roundness").setValue(round);
  g.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  return b;
}
function glow(c, name, color, size, opa, x, y, sx, sy, sp, ph, off) {
  var g = c.layers.addShape(); g.name = name;
  var grp = g.property("Contents").addProperty("ADBE Vector Group");
  grp.property("Contents").addProperty("ADBE Vector Shape - Ellipse").property("Size").setValue([size, size]);
  grp.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(color);
  try { g.property("Effects").addProperty("ADBE Gaussian Blur 2").property(1).setValue(size * 0.35); } catch (e) {}
  g.property("Transform").property("Opacity").setValue(opa);
  g.property("Transform").property("Position").expression = "var T = time + " + off + "; [" + x + " + " + sx + " * Math.sin(T * " + sp + " + " + ph + "), " + y + " + " + sy + " * Math.cos(T * " + (sp * 0.8) + " + " + ph + ")]";
  g.property("Transform").property("Scale").expression = "var T = time + " + off + "; var s = 100 + 8 * Math.sin(T * " + (sp * 1.3) + " + " + ph + "); [s, s]";
  return g;
}
// 배경 움직임(엔진 기능): 바탕 그라데이션 + 천천히 떠다니는 빛 두 개 + 아주 옅은 질감. off = 장면 시작 시각(장면이 바뀌어도 빛이 이어 움직임)
function dressBg(c, bg, off, top, bottom, ga, gb) {
  try { var r = bg.property("Effects").addProperty("ADBE Ramp"); r.property(1).setValue([c.width / 2, 0]); r.property(2).setValue(top); r.property(3).setValue([c.width / 2, c.height]); r.property(4).setValue(bottom); } catch (e) {}
  var g1 = glow(c, "Glow A", ga, 900, 11, 180, 380, 90, 70, 0.18, 0.0, off);
  var g2 = glow(c, "Glow B", gb, 820, 8, 920, 1500, 80, 90, 0.15, 2.1, off);
  g1.moveBefore(bg); g2.moveBefore(bg);
  try { var t = c.layers.addSolid([0.5, 0.5, 0.5], "Texture noise", c.width, c.height, 1); var fn = t.property("Effects").addProperty("ADBE Fractal Noise");
        try { fn.property("Evolution").expression = "(time + " + off + ") * 60"; } catch (e) {}
        t.property("Transform").property("Opacity").setValue(3); t.moveBefore(bg); } catch (e) {}
}
function popIn(layer, t, dur) {
  var s = layer.property("Transform").property("Scale"), o = layer.property("Transform").property("Opacity");
  s.setValueAtTime(t, [60, 60]); s.setValueAtTime(t + dur, [108, 108]); s.setValueAtTime(t + dur * 1.6, [100, 100]); ease(s, 60);
  o.setValueAtTime(Math.max(0, t - 0.001), 0); o.setValueAtTime(t + dur * 0.5, 100);
}
// ---- 엔진 내장 프리셋(app.run 으로 엔진 명령을 부른다). 프리셋은 현재 시각(CTI)에 키를 놓으므로 time.set 먼저.
// 실패하면 false — 부른 쪽이 예전 방식(손 키프레임)으로 대신한다
function walkProps(g, fn, depth) { depth = depth || 0; if (depth > 9) return; for (var i = 1; i <= g.numProperties; i++) { var p = g.property(i); try { fn(p); } catch (e) {} try { if (p.numProperties > 0) walkProps(p, fn, depth + 1); } catch (e) {} } }
// 키 시간 줄이기: t0 기준으로 마지막 키가 t0 + dur 이 되게(글자 프리셋은 길이가 1.2~2초 고정 — 짧은 자막에 맞춘다)
function retimeKeys(g, t0, dur) {
  var props = [], last = 0;
  walkProps(g, function (p) { if (p.numKeys > 1) { props.push(p); last = Math.max(last, p.keyTime(p.numKeys) - t0); } });
  if (last <= dur || last <= 0) return 0;
  var f = dur / last;
  for (var n = 0; n < props.length; n++) {
    var p = props[n], ts = [], vs = [], ei = [], eo = [];
    for (var k = 1; k <= p.numKeys; k++) { ts.push(p.keyTime(k)); vs.push(p.keyValue(k)); try { ei.push(p.keyInTemporalEase(k)); eo.push(p.keyOutTemporalEase(k)); } catch (e) { ei.push(null); eo.push(null); } }
    for (var k = p.numKeys; k >= 1; k--) p.removeKey(k);
    for (var k = 0; k < ts.length; k++) { p.setValueAtTime(t0 + (ts[k] - t0) * f, vs[k]); }
    for (var k = 0; k < ts.length; k++) { if (ei[k] && eo[k]) { try { p.setTemporalEaseAtKey(k + 1, ei[k], eo[k]); } catch (e) {} } }
  }
  return props.length;
}
// 전환 프리셋: 엔진 길이가 프리셋마다 다르다(fadeIn 0.5초, 닦기 1초) → 효과 키를 dur 초 안으로 줄인다
function pre(c, L, preset, t, dur) {
  try { c.openInViewer(); app.run("time.set", {time: Math.max(0, t)}); app.run("anim.applyBuiltinPreset", {preset: preset, layers: [L.name]}); if (dur) retimeKeys(L.property("Effects"), t, dur); return true; } catch (e) { writeLn("프리셋 " + preset + " 실패(" + L.name + "): " + e); return false; }
}
function textPreset(c, L, preset, t, dur) {
  try { c.openInViewer(); app.run("time.set", {time: Math.max(0, t)}); app.run("layer.applyTextPreset", {layer: L.name, preset: preset}); if (dur) retimeKeys(L.property("Text"), t, dur); return true; } catch (e) { writeLn("글자 프리셋 " + preset + " 실패(" + L.name + "): " + e); return false; }
}
// 배경 프리셋: 바탕 Solid 에 붙이고, 표현식의 time 에 장면 시작 시각을 더해(장면이 바뀌어도 움직임이 이어짐), 색 · 세기를 콘티에 맞춘다
function bgPreset(c, bg, preset, off, tunes, exprFrom, exprTo) {
  try {
    c.openInViewer(); app.run("anim.applyBuiltinPreset", {preset: preset, layers: [bg.name]});
    walkProps(bg.property("Effects"), function (p) { if (p.expression) { var x = p.expression.replace(/\btime\b/g, "(time + " + off + ")"); if (exprFrom) x = x.split(exprFrom).join(exprTo); p.expression = x; } });
    for (var i = 0; i < tunes.length; i++) { try { app.run("prop.set", {layer: bg.name, path: tunes[i][0], value: tunes[i][1]}); } catch (e) {} }
    return true;
  } catch (e) { writeLn("배경 프리셋 " + preset + " 실패: " + e); return false; }
}
// 실제 화면 다듬기: 둥근 모서리(마스크, 레이어 좌표) + 부드러운 그림자(효과 — 레이어 스타일보다 프레임당 ~5ms 싸다)
function roundShadow(L, shadow, round) {
  if (round !== false) { try { var w = L.source.width, h = L.source.height; app.run("layer.addMask", {layer: L.name, shape: "rounded", rect: [0, 0, w, h]}); } catch (e) {} }
  if (shadow) { try { var dsh = L.property("Effects").addProperty("ADBE Drop Shadow"); dsh.property("Opacity").setValue(55); dsh.property("Distance").setValue(14); dsh.property("Softness").setValue(50); dsh.property("Direction").setValue(180); } catch (e) {} }
}
"""


NEUTRAL_BG = "#16151d"   # 레퍼런스가 없을 때(L30 예외) — 특정 색을 고르지 않은 어두운 중립


def ref_background(sb: dict) -> str | None:
    """콘티에 연결된 레퍼런스 쇼츠에서 배경 톤을 잰다.
    1) ref_style.py 카드(style/style.json)의 배경색이 있으면 그것
    2) 없으면 X-ray 가 남긴 장면 프레임(shots/*.jpg)의 위 · 아래 가장자리 색 중앙값 — 띠 배치(가운데 내용 · 위아래 단색)면 그 단색,
       화면 가득 영상이면 그 영상의 어두운 톤이 나온다"""
    import numpy as np
    from PIL import Image
    cols = []
    for rid in [r for r in (sb.get("reference") or []) if isinstance(r, str)]:
        d = ROOT / "data" / "public" / "trends" / "xray" / rid
        st = d / "style" / "style.json"
        if st.exists():
            try:
                bgc = (json.loads(st.read_text("utf-8")).get("layout") or {}).get("background")
                if isinstance(bgc, str) and bgc.startswith("#"):
                    return bgc
            except ValueError:
                pass
        for f in sorted((d / "shots").glob("*.jpg"))[:24]:
            try:
                a = np.asarray(Image.open(f).convert("RGB").resize((54, 96)), dtype=float)
            except OSError:
                continue
            edge = np.concatenate([a[:9].reshape(-1, 3), a[-9:].reshape(-1, 3)])
            cols.append(np.median(edge, axis=0))
    if not cols:
        return None
    c = np.median(np.array(cols), axis=0)
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


def ref_layout(sb: dict) -> str:
    """레퍼런스 화면 문법: 'full'(화면 가득 영상 · 캡처) 또는 'card'(단색 바탕 가운데 띠).
    스타일 카드(ref_style)의 띠 비율이 있으면 그것, 없으면 장면 프레임의 위 · 아래 가장자리가 단색인지(표준편차)로 본다"""
    import numpy as np
    from PIL import Image
    votes = []
    for rid in [r for r in (sb.get("reference") or []) if isinstance(r, str)]:
        d = ROOT / "data" / "public" / "trends" / "xray" / rid
        st = d / "style" / "style.json"
        if st.exists():
            try:
                lb = (json.loads(st.read_text("utf-8")).get("layout") or {}).get("letterbox_ratio")
                if lb is not None:
                    votes.append("card" if lb > 0.5 else "full")
                    continue
            except ValueError:
                pass
        for f in sorted((d / "shots").glob("*.jpg"))[:24]:
            try:
                a = np.asarray(Image.open(f).convert("L").resize((54, 96)), dtype=float)
            except OSError:
                continue
            edge = np.concatenate([a[:10].ravel(), a[-10:].ravel()])
            votes.append("card" if edge.std() < 14 else "full")
    if not votes:
        return "card"
    return "full" if votes.count("full") >= votes.count("card") else "card"


def build_jsx(sb: dict, captions: list[dict], scenes: list[dict], out_project: Path, *, width: int = 1080, height: int = 1920, fps: int = 30,
              font: str = "Pretendard-Black") -> str:
    """콘티 → JSX(EffectCraft 스크립트). 실행하면 out_project 에 .ecproj 가 저장된다"""
    sid = sb["id"]
    _design.apply_art(sb)             # 고른 느낌 · 디자인 팔레트를 색 칸에(정의만 있고 아무도 안 불렀다 — 2026-11-11 점검)
    global THEME
    _dd = sb.get("direction") or {}
    _pan = rgb(_dd.get("color_surface") or _dd.get("color_bg") or "#0e1016")
    _light = sum(_pan) / 3 > 0.5
    _v = lambda t: f"[{t[0]:.3f}, {t[1]:.3f}, {t[2]:.3f}]"
    _bgc = rgb(_dd.get("color_bg") or "#0e1016"); _bg_light = sum(_bgc) / 3 > 0.5
    THEME = {"panel": _v(_pan), "ink": _v(rgb(_dd.get("color_text") or ("#1E1A17" if _light else "#FFFFFF"))),
             "dim": _v(_bgc) if _bg_light else "[0, 0, 0]", "dim_op": 82 if _bg_light else 68,      # 밝은 느낌: 종이로 흐리게(검은 판이 무거웠다)
             "accent": _v(rgb(_dd.get("color_accent") or "#FFD60A")), "ink_stroke": "[1, 1, 1]" if _bg_light else "[0.02, 0.02, 0.05]",
             "label_stroke": "null" if _bg_light else "[0.02, 0.02, 0.05]"}
    g = grammar(sb)
    d = sb.get("direction") or {}
    global DZ
    DZ = _design.resolve(sb)          # 이번 영상의 효과 — 사용자 > 레퍼런스 > 효과 없음(craft/design.py)
    # 배경: 디자인 방향(direct.py) > 레퍼런스 쇼츠에서 잰 톤 > 중립 어두운색 (예전엔 늘 #0f4b7d 파랑이었다)
    bg = rgb(d.get("color_bg") or ref_background(sb) or NEUTRAL_BG)
    # 레퍼런스 화면 문법: full(화면 가득) · card(가운데 띠). 사용자가 방향에서 card 를 직접 고르면 'band' — 실제 화면도 띠 안에
    layout = ("band" if d.get("layout") == "card" else d.get("layout")) or ref_layout(sb)
    pal = palette_list(sid)
    bg_top = [round(v * 0.62, 4) for v in bg]                 # 배경 그라데이션: 위는 어둡게, 아래는 강조색을 조금 섞어
    bg_bot = [round(min(1.0, v * 0.85 + a * 0.15), 4) for v, a in zip(bg, pal[1] if len(pal) > 1 else bg)]
    glow_a, glow_b = (pal[1] if len(pal) > 1 else [1, 0.24, 0.42]), (pal[2] if len(pal) > 2 else [0.08, 0.78, 0.82])
    total = round(sum(float(s["sec"]) for s in sb["scenes"]), 3)
    W, H = width, height
    title_font = resolve_font(d.get("font_title"), font)       # 방향의 글꼴을 실제로 쓴다(설치된 것 중 가장 가까운 것)
    font = resolve_font(d.get("font_body"), font)
    J = Jsx()
    J(PRELUDE)
    J(f"var main = app.project.items.addComp('Main', {W}, {H}, 1, {total}, {fps});")
    pills: list[dict] = []
    # 제목 고정: 근거가 있을 때만 — pin_title: false 면 끔, 나레이션 없는 음악 주도 영상은 기본 끔(화면 글자는 재료 · elements 로)
    spoken = any((s.get("narration") or "").strip() for s in sb.get("scenes") or [])
    pin = None if d.get("pin_title") is False or sb.get("pin_title") is False else d.get("pin_title") or sb.get("pin_title") or (sb.get("title") if spoken and len(sb.get("title") or "") <= 24 else None)
    pin = pin if pin and d.get("pin", True) else None
    pin_bottom = 0.105 if pin else 0.0        # 위쪽 고정 제목 띠의 아래 끝(화면 비율) — 화면 가득 녹화는 이 아래에서 시작
    bgp = bg_preset(sb)
    title_preset = DZ["title_preset"]
    sub_preset = DZ["sub_preset"]
    allsc = sb.get("_all_scenes") or sb["scenes"]          # 원래 영상의 장면 전체(장면 일부만 렌더할 때도 이웃 장면을 알게)
    for k, (sc, tm) in enumerate(zip(sb["scenes"], scenes)):
        oi = int(tm.get("index", k))          # 원래 장면 번호(장면 일부만 렌더해도 재료 · 자막이 맞게)
        n = oi + 1
        start, end, sec = float(tm["start"]), float(tm["end"]), float(tm["sec"])
        words = [w for w in captions if w.get("scene") == oi] or [w for w in captions if start <= w["startMs"] / 1000 < end]
        name = f"S{n:02d} {ROLE_KO.get(sc.get('role'), sc.get('role') or '')}".strip()
        J(f"\n// ---------- 장면 {n}: {sc.get('beat', '')[:60]}")
        J(f"var c = app.project.items.addComp({js(name)}, {W}, {H}, 1, {sec}, {fps});")
        J(f"var bgL = c.layers.addSolid({js(bg)}, 'BG', {W}, {H}, 1);")
        if DZ["bg_motion"] or bgp:   # 배경 움직임 — 방향이 정했을 때만(기본은 단색)
            dress = f"dressBg(c, bgL, {start:.3f}, {js(bg_top)}, {js(bg_bot)}, {js(glow_a)}, {js(glow_b)});"
            if bgp:   # 형식별 내장 배경 프리셋(색은 콘티 바탕 · 팔레트로) — 안 되면 예전 그라데이션 + 빛
                tunes, ef, et = bg_tunes(bgp, bg, pal)
                J(f"if (!bgPreset(c, bgL, {js(bgp)}, {start:.3f}, {js(tunes)}, {js(ef)}, {js(et)})) {{ {dress} }}")
            else:
                J(dress)
        J("var cam = c.layers.addNull(); cam.name = 'Camera';")
        J(f"cam.property('Transform').property('Position').setValue([{W / 2}, {H / 2}]);")
        # 카메라: 장면 내내 천천히 밀기 + beats '확대' 에서 당기기
        zoom_at = None
        for b in sc.get("beats") or []:
            if b.get("do") == "확대":
                # 나레이션 낱말(at) 또는 장면 안 초(t) — 말이 없는 영상도 감독이 짚을 수 있게(2026-11-09: 무음 영상에서 강조가 하나도 없었다)
                zoom_at = float(b["t"]) if isinstance(b.get("t"), (int, float)) else cue_time(b.get("at"), words, start, end)
                break
        J("var zs = cam.property('Transform').property('Scale');")
        cam_follow = isinstance(sc.get("camera"), dict) and bool(sc["camera"].get("follow"))
        fn = str(sc.get("shot_fn") or "")                 # 감독 샷 기능(director 스킬 2장) → 카메라. 2026-11-11 점검: 적어도 아무도 안 읽었다
        if cam_follow:
            pass                                     # 스프링 카메라 — 재료를 그린 뒤 camera_follow_jsx 가 키를 넣는다
        elif zoom_at is None and (sc.get("visual") or {}).get("motion") in ("kenburns_in", "kenburns_out", "pan_left", "pan_right"):
            # 스틸 움직임(format-emotional: 장면마다 visual.motion 을 다르게) — 2026-11-11 점검: 스키마에만 있고 Craft 경로가 안 읽었다
            vm = sc["visual"]["motion"]
            if vm == "kenburns_in":
                J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({sec}, [109, 109]); ease(zs, 30);")
            elif vm == "kenburns_out":
                J(f"zs.setValueAtTime(0, [109, 109]); zs.setValueAtTime({sec}, [100, 100]); ease(zs, 30);")
            else:
                dxp = -1 if vm == "pan_left" else 1
                J(f"zs.setValue([106, 106]); var cps = cam.property('Transform').property('Position'); cps.setValueAtTime(0, [{W / 2 - dxp * W * 0.025:.0f}, {H / 2}]); cps.setValueAtTime({sec}, [{W / 2 + dxp * W * 0.025:.0f}, {H / 2}]); ease(cps, 30);")
        elif fn in ("여운", "끝", "자리 잡기"):
            pass                                     # 고정 — 무엇이 바뀌지 않으면 카메라도 움직이지 않는다(director 4장)
        elif zoom_at is None and fn in ("충격", "변화"):
            zp = round(sec * 0.35, 3)                 # 꺾임 순간 빠르게 당겨 들어가 멈춤
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({zp}, [100, 100]); zs.setValueAtTime({min(sec, zp + 0.18)}, [114, 114]); zs.setValueAtTime({sec}, [116, 116]); ease(zs, 85);")
        elif zoom_at is None and fn == "디테일":
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({sec}, [110, 110]); ease(zs, 40);")
        elif zoom_at is not None:
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({zoom_at}, [104, 104]); zs.setValueAtTime({min(sec, zoom_at + 0.6)}, [122, 122]); zs.setValueAtTime({sec}, [126, 126]); ease(zs, 75);")
        elif DZ["cam_push"] > 1.0:   # 장면 내내 천천히 밀기 — 방향이 정했을 때만
            J(f"zs.setValueAtTime(0, [100, 100]); zs.setValueAtTime({sec}, [{DZ['cam_push'] * 100:.1f}, {DZ['cam_push'] * 100:.1f}]); ease(zs, 40);")
        mats = scene_materials(sid, n, sc)
        ovs = [r for r in mats if r.get("type") == "overlay"]      # 주석 오버레이: 대상 재료 위에 차례로 — 대상을 다 그린 뒤에
        mats = [r for r in mats if r.get("type") != "overlay"]
        # 다른 재료가 uses 로 가져다 쓴 재료(3D 화면에 입힌 카드 등)는 입력일 뿐 — 화면에 따로 내지 않는다(spec.show 로 켬)
        used = input_materials(mats)
        mats = [r for r in mats if ((r.get("spec") or {}).get("show") is not False) and (r["id"] not in used or (r.get("spec") or {}).get("show"))]   # show: false = 레이어로만 쓰는 재료
        for r in mats:
            # 층으로 나뉜 재료(DeckCraft 도식 layers + base): 바탕(배경 + 제목)을 재료 그림으로 놓고, 항목 층을 주석처럼 차례로 얹는다
            if r.get("layers") and r.get("base") and (ROOT / str(r["base"])).exists():
                r["file"] = r["base"]
                ovs.append({"id": f"{r['id']}L", "type": "overlay", "target": r["id"], "layers": r["layers"], "file": r["base"], "spec": {"target": r["id"]}})
            # 문서 화면(WordCraft document · 9:16 쪽): 진짜 형광펜이 칠해져 있다 → 그 문장(focus, px)으로 천천히 다가간다
            fc, sz = r.get("focus"), r.get("size")
            if r.get("type") == "document" and not r.get("highlight_box") and isinstance(fc, list) and len(fc) == 4 and isinstance(sz, list) and len(sz) == 2 and sz[0] and sz[1]:
                r["highlight_box"] = [fc[0] / sz[0], fc[1] / sz[1], fc[2] / sz[0], fc[3] / sz[1]]
        slots = {}
        if mats:
            colors = palette_list(sid)
            te0 = element(sc, "훅 제목", "제목")
            nl = len(quoted(te0.get("what", ""))) if te0 else 0
            top = (g["title"]["y"] + nl * g["title"]["h"] * 1.6 * 1.25 + 0.02) if nl else 0.2
            # 한 장면에 보이는 재료가 여럿이면 겹치지 않게 차례로: 각자 cue 낱말 시각부터 다음 재료가 나올 때까지(cue 가 없으면 장면을 나눠)
            # 겹치기: layer "over" 는 앞 재료 위에 얹는다.
            over = [r for r in mats if is_over(r, mats)]
            seqs = [r for r in mats if r.get("type") not in ("text", "stat") and r not in over]   # 차트도 차례에 넣는다(안 넣으면 그림과 겹침) · 숫자(stat)는 덧씌우기
            for r in over:
                spv = r.get("spec") or {}
                t0 = cue_time(spv.get("cue"), words, start, end)
                slots[r["id"]] = (t0 if t0 is not None else float(spv.get("start") or 0.0), None)
            cues_all = sorted(t for t in (cue_time((r.get("spec") or {}).get("cue"), words, start, end) for r in mats) if t is not None)
            for r in mats:
                if r.get("type") == "stat":     # 덧씌우기: 그 낱말부터 다음 재료가 나올 때까지(최대 2.4초)
                    ti = cue_time((r.get("spec") or {}).get("cue"), words, start, end)
                    if ti is None and not (sc.get("narration") or "").strip():
                        # 나레이션이 없으면 낱말을 기다릴 수 없다 → 그 숫자를 말하는 박자에, 없으면 장면 끝 1.4초만(장면 내내 덮지 않게)
                        # 2026-11-04: 메신저 영상에서 큰 '101' 이 장면 내내 대화창을 가렸다
                        spv = r.get("spec") or {}
                        ti = beat_at(sc, sec, str(spv.get("value") or "") or None, spv.get("cue"))
                        ti = max(0.0, sec - 1.4) if ti is None else ti
                        slots[r["id"]] = (ti, min(sec, ti + 1.4))
                        continue
                    ti = ti or 0.0
                    nx = [t for t in cues_all if t > ti + 0.3]
                    slots[r["id"]] = (ti, min(ti + 2.4, nx[0]) if nx else sec)   # 마지막 덧씌우기는 장면 끝까지
            if len(seqs) == 1:   # 하나뿐이면 장면 처음부터 — 낱말을 기다리는 동안 화면이 비면 넘겨진다
                slots[seqs[0]["id"]] = (0.0, None)
            if len(seqs) > 1:
                # 시작 초: 나레이션 낱말(cue) > 콘티의 재료 start(나레이션 없는 영상에서 재료를 정확한 초에 바꿀 때) > 장면을 똑같이 나눠
                ts = [cue_time((r.get("spec") or {}).get("cue"), words, start, end) for r in seqs]
                ts = [t if t is not None or (r.get("spec") or {}).get("start") is None else float(r["spec"]["start"]) for t, r in zip(ts, seqs)]
                for k3, tt in enumerate(ts):
                    if tt is None:
                        ts[k3] = sec * k3 / len(seqs)
                ts[0] = min(ts[0], 0.0) if ts[0] is not None else 0.0
                order = sorted(range(len(seqs)), key=lambda k3: ts[k3])
                for o, k3 in enumerate(order):
                    nxt = ts[order[o + 1]] if o + 1 < len(order) else None
                    slots[seqs[k3]["id"]] = (ts[k3], nxt)
                    # 다음 재료가 화면 가득 닦으며 들어오면 앞 재료는 그동안 그대로(먼저 흐려지면 사이에 바탕색이 번쩍인다)
                    if o + 1 < len(order):
                        nr = seqs[order[o + 1]]
                        if nxt is not None and nxt > 0.05 and is_full(seqs[k3], layout, W, H) and is_full(nr, layout, W, H) and enter_preset(nr, d):
                            seqs[k3]["_hold_out"] = True
            if any(r.get("type") == "stat" for r in mats):
                for r in seqs:
                    r["_under_overlay"] = True      # 숫자를 덧씌우는 장면의 바탕 재료는 줄 따라 확대하지 않는다(어지러움)
            for ov in ovs:                          # 주석이 짚는 재료는 줄 따라 확대 · 글자 동그라미를 하지 않는다(주석이 대신)
                for r in seqs:
                    if r["id"] == ov_target(ov):
                        r["_under_overlay"] = r["_no_focus"] = True
            # 그리는 순서 = 나오는 순서(뒤에 나오는 재료가 위 — 닦으며 덮을 수 있게), 숫자 덧씌우기는 맨 나중(위)에
            draw = sorted(mats, key=lambda r: (r.get("type") == "stat", r in over, (slots.get(r["id"]) or (0.0, None))[0] or 0.0))
            for rec in draw:
                t_in, t_out = slots.get(rec["id"], (None, None))
                rec["_subs"] = bool(words) or bool(rec.get("steps"))     # 자막이 없으면 자막 그림자도 없다
                rec["_pin_bottom"] = pin_bottom
                material_jsx(J, rec, words, start, end, sec, W, H, font, colors, top=top, bottom=g["subs"]["y"] - 0.03, t_in=t_in, t_out=t_out, layout=layout, direction=d)
            if cam_follow:
                camera_follow_jsx(J, sc, mats, slots, words, start, end, sec, fps, W, H, g["subs"]["y"] - 0.03)
            by_id = {r["id"]: r for r in mats}
            for ov in ovs:
                overlay_jsx(J, ov, by_id.get(ov_target(ov)), slots.get(ov_target(ov), (None, None)), words, start, end, sec)
        else:
            # 재료가 없는 장면: 자리표시 상자 대신 이 장면의 핵심어로 화면을 짠다(목록이면 하나씩, 아니면 큰 낱말 하나)
            v = sc.get("visual") or {}
            items = [str(x) for x in (v.get("items") or []) if x][:4]
            key = str(v.get("primary") or "").strip() or (sc.get("caption") or "").split("\n")[0].strip()
            colors = palette_list(sid)
            if items:
                if key:
                    J(f"var kt = txt(c, 'Key', {js(key[:20])}, {js(font)}, 96, {js(colors[0])}, null, 0, [{W / 2}, {H * 0.3:.0f}]); popIn(kt, 0.1, 0.2); kt.parent = cam;")
                for k2, it in enumerate(items):
                    tk = cue_time(it, words, start, end)
                    tk = 0.35 + k2 * 0.45 if tk is None else tk
                    y = H * 0.42 + k2 * 150
                    J(f"var ib = card(c, {js(f'Item {k2 + 1}')}, {int(W * 0.72)}, 116, [1, 1, 1], 28); ib.property('Transform').property('Position').setValue([{W / 2}, {y:.0f}]); ib.property('Transform').property('Opacity').setValue(12); popIn(ib, {tk:.2f}, 0.18); ib.parent = cam;")
                    J(f"var it = txt(c, {js(f'Item text {k2 + 1}')}, {js(f'{k2 + 1}. {it}'[:24])}, {js(font)}, 60, [0.07, 0.09, 0.18], null, 0, [{W / 2}, {y + 20:.0f}]); popIn(it, {tk:.2f}, 0.18); it.parent = cam;")
            elif key:
                J(f"var kt = txt(c, 'Key', {js(key[:16])}, {js(font)}, 150, {js(colors[0])}, null, 0, [{W / 2}, {H * 0.45:.0f}]); popIn(kt, 0.1, 0.22); kt.parent = cam;")
        # 훅 제목 — 노란 상자에 한 줄씩 쌓임
        te = element(sc, "훅 제목", "제목")
        lines = quoted(te.get("what", "")) if te else []
        if lines:
            t0 = cue_time(te.get("cue"), words, start, end) or 0.05
            gt = g["title"]
            size = int(gt["h"] * H * 1.6)
            for i, line in enumerate(lines):
                y = gt["y"] * H + i * size * 1.25
                J(f"var tl = txt(c, 'Title {i + 1}', {js(line)}, {js(title_font)}, {size}, {js(rgb(gt.get('fg', '#111111')))}, null, 0, [{W / 2}, {y:.0f}]);")
                ti = t0 + i * 0.4
                if gt.get("editorial"):
                    # 절제된 등장: 0.7초에 걸쳐 살짝 떠오르며 나타남(튀거나 상자 없이) — 브랜드 필름 · 애플식 글자
                    J(f"var tlo = tl.property('Transform').property('Opacity'); tlo.setValueAtTime(0, 0); tlo.setValueAtTime({ti:.3f}, 0); tlo.setValueAtTime({ti + 0.7:.3f}, 100); ease(tlo, 60);"
                      f" var tlp = tl.property('Transform').property('Position'); tlp.setValueAtTime({ti:.3f}, [{W / 2}, {y + size * 0.35:.0f}]); tlp.setValueAtTime({ti + 0.8:.3f}, [{W / 2}, {y:.0f}]); ease(tlp, 80);")
                    J(f"tl.property('Transform').property('Opacity').setValueAtTime({max(0.0, sec - 0.35):.3f}, 100); tl.property('Transform').property('Opacity').setValueAtTime({sec:.3f}, 0);")
                    continue
                if gt.get("box", True):
                    J(f"fitBox(c, 'TitleBox {i + 1}', 'Title {i + 1}', {js(rgb(gt.get('bg', '#ffd60a')))}, 48, 28, 8{f', {ti + 0.55:.3f}' if title_preset else ''});")
                if title_preset:
                    # 단어가 튀어 오르며 나타남(엔진 글자 프리셋, 0.5초로 줄임) — 상자는 글자 층을 따라 짧게 '톡'
                    J(f"var tlo = tl.property('Transform').property('Opacity'); tlo.setValueAtTime({max(0.0, ti - 0.01):.3f}, 0); tlo.setValueAtTime({ti + 0.05:.3f}, 100);"
                      f" var tls = tl.property('Transform').property('Scale'); tls.setValueAtTime({ti:.3f}, [94, 94]); tls.setValueAtTime({ti + 0.16:.3f}, [100, 100]); ease(tls, 60);")
                    J(f"if (!textPreset(c, tl, {js(title_preset)}, {ti:.3f}, 0.5)) popIn(tl, {ti:.3f}, 0.18);")
                elif DZ["text_pop"]:
                    J(f"popIn(tl, {ti:.3f}, 0.18);")
                J(f"tl.property('Transform').property('Opacity').setValueAtTime({max(0.0, sec - 0.25):.3f}, 100); tl.property('Transform').property('Opacity').setValueAtTime({sec:.3f}, 0);")
        # 화면 글자(caption) — 나레이션이 없으면 자막이 말소리에서 나오지 않는다. 그래도 콘티에 적은 화면 글자는 보여야 한다
        # 2026-11-09: 음악 없이 효과음만 쓰는 브랜드 필름에서 '아이디어를,' · 슬로건이 전부 빠졌다(자막은 말에서만 만들었음)
        cap = str(sc.get("caption") or "").strip()
        if cap and (words or lines) and d.get("screen_text", True):
            # 훅 세 칸(writer 스킬)의 '화면 글자' — 말 자막과 따로, 위쪽 띠에 강조색으로. 2026-11-11 점검: 나레이션이 있으면 caption 을 아예 안 그려 화면 글자 칸이 사라졌다
            st_size = int(H * (0.05 if len(cap) <= 8 else 0.042 if len(cap) <= 14 else 0.034))
            st_y = float(d.get("screen_text_y", 0.17)) * H
            st_col = rgb(d.get("color_accent") or "#ff5a36")
            J(f"var stx = txt(c, 'Screen text', {js(cap)}, {js(title_font)}, {st_size}, {js(st_col)}, null, 0, [{W / 2}, {st_y:.0f}]);"
              f" var sto = stx.property('Transform').property('Opacity'); sto.setValueAtTime(0, 0); sto.setValueAtTime(0.15, 0); sto.setValueAtTime(0.45, 100);"
              f" sto.setValueAtTime({max(0.5, sec - 0.25):.3f}, 100); sto.setValueAtTime({sec:.3f}, 0); ease(sto, 60);")
        if cap and not words and not lines:
            gt = g["title"]
            ed = bool(gt.get("editorial"))
            parts = [x.strip() for x in re.split(r"\n|(?<=[,，])\s+", cap) if x.strip()] if len(cap) > 12 else [cap]
            card_like = "카드" in str(sc.get("screen") or "") or not any(is_full(r, layout, W, H) for r in mats)
            size = int(H * (0.05 if len(cap) <= 8 else 0.036 if len(cap) <= 16 else 0.03))
            mstarts = [float((m or {}).get("start") or 0) for m in sc.get("materials") or [] if isinstance(m, dict)]
            t0 = min(max(0.2, (max(mstarts) + 0.9) if card_like and mstarts and max(mstarts) > 0 else 0.25), max(0.2, sec - 1.4))
            has_screen = any(r.get("type") in ("web", "screen", "video") for r in mats)
            y0 = (0.70 if card_like else 0.875 if has_screen else g["subs"]["y"]) * H   # 화면 녹화가 가운데를 채우면 글자는 그 아래 띠에(내용 위에 겹치지 않게)
            fg = rgb(d.get("color_text") or gt.get("fg") or "#ffffff") if ed else [1, 1, 1]
            stroke = "null, 0" if card_like else f"[0.02, 0.02, 0.03], {max(4, size // 12)}"
            for i, line in enumerate(parts[:3]):
                y = y0 + i * size * 1.3
                ti = t0 + i * 0.25
                J(f"var ct = txt(c, {js(f'Caption {i + 1}')}, {js(line)}, {js(title_font if ed else font)}, {size}, {js(fg)}, {stroke}, [{W / 2}, {y:.0f}]);")
                J(f"var cto = ct.property('Transform').property('Opacity'); cto.setValueAtTime(0, 0); cto.setValueAtTime({ti:.3f}, 0); cto.setValueAtTime({ti + 0.6:.3f}, 100); ease(cto, 60);"
                  f" var ctp = ct.property('Transform').property('Position'); ctp.setValueAtTime({ti:.3f}, [{W / 2}, {y + size * 0.3:.0f}]); ctp.setValueAtTime({ti + 0.7:.3f}, [{W / 2}, {y:.0f}]); ease(ctp, 80);"
                  f" cto.setValueAtTime({max(ti + 0.7, sec - 0.3):.3f}, 100); cto.setValueAtTime({sec:.3f}, 0);")
        # 숫자 알약 — 레퍼런스 문법: 위쪽 가운데에 영상 내내 떠 있고 값만 굴러 바뀐다 → 장면이 아니라 Main 에 하나(아래에서 만듦)
        pe = element(sc, "숫자 알약", "알약")
        if pe:
            m = re.findall(r"[‘'\"“]([^’'\"”]+)[’'\"”]", pe.get("what", ""))
            num = m[-1] if m else None
            if num:
                t0 = cue_time(pe.get("cue"), words, start, end)
                pills.append({"t": round(start + (t0 if t0 is not None else 0.2), 3), "text": num, "color": pill_color(pe.get("what", ""), len(pills))})
        # 단어 자막
        # 숫자 펀치: 나레이션이 숫자를 말하는 순간 화면을 살짝 어둡게 하고 큰 숫자를 0.9초 — 장면마다 한 번(제목 상자에 같은 숫자가 있으면 건너뜀)
        title_txt = " ".join(quoted((element(sc, "훅 제목", "제목") or {}).get("what", "")))
        has_num_mat = any(m.get("type") in ("stat", "chart") for m in sc.get("materials") or [])
        _ban = " ".join(map(str, ((sb.get("intent") or {}).get("must_not") or []) + list(sb.get("constraints") or [])))
        _no_fx = "number_punch" in ((sb.get("intent") or {}).get("ban") or []) or bool(re.search(r"효과|배지|큰 숫자|숫자 펀치|덧씌우", _ban))      # 의도 · 제약이 효과를 막으면 엔진도 얹지 않는다(2026-11-11: 금지라고 적었는데 큰 숫자가 붙었다)
        if d.get("number_punch", not _no_fx) and not has_num_mat:     # 숫자 재료가 있는 장면은 그 재료가 숫자를 보여 준다
            cands = []
            shown_nums = set()
            for m in sc.get("materials") or []:
                if m.get("type") == "stat":
                    shown_nums.update(re.findall(r"\d[\d.,]*", str(m.get("value") or "")))
            for r in scene_materials(sb["id"], n, sc):
                if r.get("type") == "chart":
                    shown_nums.update(str(v).rstrip("0").rstrip(".") if "." in str(v) else str(v) for v in ((r.get("data") or {}).get("values") or []))
            for w in words:
                mnum = re.search(r"\d[\d.,]*\s*(%|퍼센트|초|배|개|명|원|만|억)?", w.get("text") or "")
                tw = w["startMs"] / 1000 - start
                if not mnum or tw < 0.3 or tw > sec - 1.0 or mnum.group(0).strip() in title_txt:
                    continue
                num = mnum.group(0).strip().replace("퍼센트", "%")
                if num.rstrip("%초배개명원만억") in shown_nums:      # 수치 카드 · 차트가 이미 그 숫자를 크게 보여 준다
                    continue
                unit = mnum.group(1) or ""
                rank = 0 if unit in ("%", "퍼센트") else 1 if unit in ("배", "개", "명", "원", "만", "억") else 2   # 퍼센트 > 배 · 개 > 초
                cands.append((rank, tw, num))
            if cands:
                _, tw, num = sorted(cands)[0]
                J(f"var dim = c.layers.addSolid([0, 0, 0], 'Punch dim', {W}, {H}, 1); dim.inPoint = {tw:.2f}; dim.outPoint = {tw + 0.95:.2f}; var dO = dim.property('Transform').property('Opacity'); dO.setValueAtTime({tw:.2f}, 0); dO.setValueAtTime({tw + 0.1:.2f}, 55); dO.setValueAtTime({tw + 0.8:.2f}, 55); dO.setValueAtTime({tw + 0.95:.2f}, 0);")
                J(f"var pn = txt(c, 'Punch', {js(num)}, {js(font)}, {min(300, int(W * 1.1 / max(2, len(num))))}, [1, 0.84, 0.04], [0.02, 0.02, 0.05], 14, [{W / 2}, {H * 0.47:.0f}]); pn.inPoint = {tw:.2f}; pn.outPoint = {tw + 0.95:.2f};")
                J(f"var pS = pn.property('Transform').property('Scale'); pS.setValueAtTime({tw:.2f}, [55, 55]); pS.setValueAtTime({tw + 0.12:.2f}, [112, 112]); pS.setValueAtTime({tw + 0.22:.2f}, [100, 100]); pS.setValueAtTime({tw + 0.95:.2f}, [104, 104]);")
                J(f"var pO = pn.property('Transform').property('Opacity'); pO.setValueAtTime({tw + 0.8:.2f}, 100); pO.setValueAtTime({tw + 0.95:.2f}, 0);")
        # 자막: 구절 단위(레퍼런스는 한 번에 한 구절을 크게) — 숫자 · 핵심어가 든 구절은 노란색
        gs = g["subs"]
        size = int(gs["h"] * H * 1.75)
        keys = [_norm(x) for x in re.findall(r"[가-힣A-Za-z0-9.%+]{2,}", str((sc.get("visual") or {}).get("primary") or ""))]
        sub_chunks = clause_chunks(words, int(gs.get("max_chars", 30))) if gs.get("mode") == "clause" else chunks(words, max_chars=13, max_words=4)
        for i, ch in enumerate(sub_chunks):
            a_, b_ = max(0.0, ch["start"] - start), min(sec, ch["end"] - start)
            if b_ <= a_:
                continue
            hot = bool(re.search(r"\d", ch["text"])) or any(k and k in _norm(ch["text"]) for k in keys)
            fg = rgb(gs.get("hot", "#ffd60a")) if hot else rgb(gs.get("fg", "#ffffff"))   # 강조 낱말 색(방향 subs.hot — 밝은 상자면 빨강 등)
            stroke = "null, 0" if gs.get("box") else f"[0.02, 0.02, 0.05], {max(6, size // 5)}"     # 상자가 있으면 외곽선 없이(뭉개짐)
            J(f"var s = txt(c, {js(f'Sub {i + 1:02d}')}, {js(ch['text'])}, {js(font)}, {size}, {js(fg)}, {stroke}, [{W / 2}, {gs['y'] * H:.0f}]);")
            pop = f"var sS = s.property('Transform').property('Scale'); sS.setValueAtTime({a_:.3f}, [88, 88]); sS.setValueAtTime({a_ + 0.09:.3f}, [100, 100]);"
            J(f"s.inPoint = {a_:.3f}; s.outPoint = {b_:.3f};")
            if gs.get("box"):   # 자막 상자(방향 subs.box) — 글자 뒤 반투명 판, 그 구절 동안만
                J(f"var sbx = fitBox(c, {js(f'SubBox {i + 1:02d}')}, {js(f'Sub {i + 1:02d}')}, {js(rgb(gs.get('bg', '#0b0d12')))}, 36, 18, 14); sbx.inPoint = {a_:.3f}; sbx.outPoint = {b_:.3f};")
            if sub_preset:   # 글자 프리셋 — 자막 길이의 60%(최대 0.45초) 안에 다 나오게
                J(f"if (!textPreset(c, s, {js(sub_preset)}, {a_:.3f}, {min(0.45, 0.6 * (b_ - a_)):.3f})) {{ {pop} }}")
            elif DZ["text_pop"]:
                J(pop)
        for m in sc.get("materials") or []:           # 조정 값(adjust) — 대화로 고칠 때 에이전트가 바꾸는 손잡이(knob.py). 배치가 끝난 뒤 위에 얹는다
            if isinstance(m, dict) and isinstance(m.get("adjust"), dict) and m.get("id"):
                J(adjust_jsx(str(m["id"]), m["adjust"], W, H))
        J(f"var sl = main.layers.add(c); sl.startTime = {start:.3f};")
        # 끝 장면이 영상 없이 그림 · 로고 · 글자만이면 멈춘 화면이 된다(2026-11-09: 로고 4초 정지) → 천천히 다가오며 나타남
        # 2026-11-11: 93→100 으로 키우니 화면이 줄어 네 가장자리에 검은 테두리가 생겼고, 감독이 '끝'(고정)으로 정한 것도 무시했다 → 고정 기능이면 그대로, 아니면 100→106 으로 다가감
        if oi == len(allsc) - 1 and str(sc.get("shot_fn") or "") not in ("끝", "여운", "자리 잡기") and not any((m or {}).get("type") in ("video", "web", "screen", "stock") for m in sc.get("materials") or [] if isinstance(m, dict)):
            J(f"var eS = sl.property('Transform').property('Scale'); eS.setValueAtTime({start:.3f}, [100, 100]); eS.setValueAtTime({start + sec:.3f}, [106, 106]); ease(eS, 50);")
        # 장면 사이 '들어가기' 전환(direction.transition: zoom · 장면 transition: zoom) — 앞 장면은 끝 0.35초에 화면 속으로 빨려 들고, 다음 장면은 크게 시작해 자리를 잡는다
        # 2026-11-09: 기획은 '화면 속으로 끊김 없이' 였는데 조립은 컷만 있어 클립이 툭툭 붙었다
        tr = str(sc.get("transition") or d.get("transition") or "")
        nxt = allsc[oi + 1] if oi + 1 < len(allsc) else None
        zp = sc.get("zoom_to") or [0.5, 0.5]
        if nxt is not None and "zoom" in tr and sec > 0.8:
            J(f"var zA = sl.property('Transform').property('Anchor Point'), zP = sl.property('Transform').property('Position'); zA.setValue([{W * float(zp[0]):.0f}, {H * float(zp[1]):.0f}]); zP.setValue([{W * float(zp[0]):.0f}, {H * float(zp[1]):.0f}]);")
            J(f"var zS = sl.property('Transform').property('Scale'); zS.setValueAtTime({start + sec - 0.35:.3f}, [100, 100]); zS.setValueAtTime({start + sec:.3f}, [240, 240]); ease(zS, 85);")
        prev = allsc[oi - 1] if 0 < oi <= len(allsc) else None
        if prev is not None and "zoom" in str(prev.get("transition") or d.get("transition") or "") and sec > 0.8:
            J(f"var zI = sl.property('Transform').property('Scale'); zI.setValueAtTime({start:.3f}, [135, 135]); zI.setValueAtTime({start + 0.4:.3f}, [100, 100]); ease(zI, 70);")
    # 위쪽 고정 주제 제목(레퍼런스: '컴퓨터 버그의 유래'처럼 영상 내내 위에 떠 있음) — 콘티 direction.pin_title > pin_title > 짧은 제목
    if pin:
        J("\n// ---------- 위쪽 고정 주제 제목(영상 전체)")
        psz = max(36, min(52, int(W * 0.84 / max(1, len(pin)))))   # 한 줄에 들어가게
        J(f"var pt = txt(main, 'PinTitle', {js(pin)}, {js(font)}, {psz}, [1, 1, 1], null, 0, [{W / 2}, {H * 0.062:.0f}]);")
        J("var pbx = fitBox(main, 'PinBox', 'PinTitle', [0.05, 0.05, 0.08], 56, 30, 18); pbx.property('Transform').property('Opacity').setValue(82);")
        g["pill"] = {**g["pill"], "y": max(g["pill"]["y"], 0.115)}      # 숫자 알약은 그 아래로
    if pills:
        gp = g["pill"]
        size = int(gp["h"] * H * 1.5)
        y = gp["y"] * H + size * 0.35
        J("\n// ---------- 숫자 알약(영상 전체): 값이 바뀔 때마다 아래에서 굴러 올라옴")
        J(f"var pl = txt(main, 'PillText', {js(pills[0]['text'])}, {js(font)}, {size}, [1, 1, 1], null, 0, [{W / 2}, {y:.0f}]);")
        J("var pb = fitBox(main, 'Pill', 'PillText', [0.97, 0.15, 0.52], 90, 44, 100);")
        J("var src = pl.property('Source Text'), pp = pl.property('Transform').property('Position'), pc = pb.property('Contents').property(1).property('Contents').property(2).property('Color');")
        J(f"var po = pl.property('Transform').property('Opacity'); po.setValueAtTime(0, 0); po.setValueAtTime({max(0.0, pills[0]['t'] - 0.001):.3f}, 0); po.setValueAtTime({pills[0]['t'] + 0.15:.3f}, 100);")
        for i, e in enumerate(pills):
            t = e["t"]
            if i:   # 바뀌기 직전까지는 제자리(사이 보간으로 천천히 내려가지 않게)
                J(f"pp.setValueAtTime({t - 0.001:.3f}, [{W / 2}, {y:.0f}]);")
            J(f"var d = src.value; d.text = {js(e['text'])}; src.setValueAtTime({t:.3f}, d);")
            J(f"pp.setValueAtTime({t:.3f}, [{W / 2}, {y + size * 1.2:.0f}]); pp.setValueAtTime({t + 0.35:.3f}, [{W / 2}, {y:.0f}]);")
            J(f"pc.setValueAtTime({t:.3f}, {js(e['color'])});")
        J("ease(pp, 80);")
        # 도착한 뒤는 다음 변화까지 그대로(같은 값 두 키 사이 이동 경로가 곡선으로 휘어 처지지 않게)
        J("var arrive = [" + ", ".join(f"{e['t'] + 0.35:.3f}" for e in pills) + "];")
        J("for (var a = 0; a < arrive.length; a++) { var ki = pp.nearestKeyIndex(arrive[a]); pp.setInterpolationTypeAtKey(ki, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.HOLD); }")
        J("for (var k = 1; k <= pc.numKeys; k++) pc.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);   // 색은 한 번에 바뀜")
    J(f"app.project.save(new File({js(str(out_project))}));")
    J("writeLn('saved ' + main.numLayers);")
    return J.text()
