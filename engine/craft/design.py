"""디자인 결정 — 움직임 · 소리 단계가 쓰는 '효과'를 한 곳에서 정한다(코드에 박힌 기본값 대신 영상마다).

정하는 순서(위가 이긴다):
  1. 사용자가 정한 값 — 콘티 direction 의 같은 칸(에이전트가 사용자 요청으로 적은 것, directions.py pick 으로 고른 시안)
  2. 레퍼런스에서 잰 값 — direct.py --write 가 X-ray(카메라 움직임 · 샷 길이 · 말/음악 비율)로 적은 칸(direction.design_from = "reference")
  3. 효과 없음 — 근거가 없으면 넣지 않는다(배경 움직임 · 등장 전환 · 글자 애니메이션 · 그림자 · 밀기 모두 끔). 화면 비율 · 쇼츠 음량(−14 LUFS)처럼
     규격인 것만 늘 켠다.

direction 칸(모두 선택):
  bg_preset   EffectCraft 내장 배경 id(blueprintGrid · bokehDrift · pulseRings · softGradientDrift …) 또는 null
  bg_motion   true 면 배경 움직임(프리셋이 없으면 옅은 그라데이션 · 빛) · 기본 false
  enter       재료 등장 전환 — 프리셋 id 하나, {재료 종류: id} 표, 또는 null(바로 보임)
  title_preset · sub_preset   글자 프리셋 id(bounceInWords · typewriter · fadeUpCharacters …) 또는 null
  text_pop    true 면 제목 · 자막이 나올 때 살짝 커짐(작은 '톡') · 기본 false
  cam_push    장면 내내 천천히 미는 배율(1.0 = 없음, 1.07 = 7%) · 기본 1.0
  frame       실제 화면(캡처 · 녹화) 액자 {"shadow": bool, "round": bool, "push": 배율} · 기본 모두 끔
  sound       {"voice_chain": "clean" | "light" | "none", "duck_db": 말할 때 배경음을 더 낮출 dB(기본 −5)} — clean = EQ · 컴프레서 · 치찰음, light = 저역만 정리
  layout      "full"(재료를 화면 가득) | "card"(단색 바탕 가운데 띠 — 실제 화면도 띠 안에, 그림자 · 둥근 모서리는 frame)
  subs · title  자막 · 제목 모양 {"box": bool, "bg": "#색", "fg": "#색", "hot": "#강조 낱말 색", "y": 0~1} — 화면 문법(grammar) 위에 덮는다
  methods     {재료 종류: 앱} — 같은 재료를 어느 앱으로 만들지(예: {"chart": "deckcraft"}) · materials.py 가 읽는다
"""
from __future__ import annotations

NONE = {
    "bg_preset": None, "bg_motion": False, "enter": None, "title_preset": None, "sub_preset": None, "text_pop": False,
    "cam_push": 1.0, "frame": {"shadow": False, "round": False, "push": 1.0},
    "sound": {"voice_chain": "light", "duck_db": -5},
    "methods": {},
}
KEYS = tuple(NONE)


def resolve(sb: dict) -> dict:
    """콘티 → 이번 렌더에 쓸 디자인 값(빠진 칸은 '효과 없음')"""
    d = sb.get("direction") or {}
    nullable = ("bg_preset", "enter", "title_preset", "sub_preset")   # null 을 적으면 '끔'이라는 뜻
    out = {}
    for k, v in NONE.items():
        if k not in d or (d[k] is None and k not in nullable):
            out[k] = v
        elif isinstance(v, dict) and isinstance(d[k], dict):
            out[k] = {**v, **d[k]}
        else:
            out[k] = d[k]
    return out


ART_NEED = ("palette", "rule", "avoid")        # 영상마다 정한다 — 없으면 고정 템플릿 모양 그대로 나온다


def art_problems(sb: dict) -> list:
    """아트 디렉션(direction.art) 검사 — 영상의 시각 언어: palette{bg, ink, accent} · rule(이 영상의 구도 원칙 한 문장) · avoid(이 영상에서 안 할 것)"""
    a = (sb.get("direction") or {}).get("art")
    if not isinstance(a, dict):
        return ["아트 디렉션이 없음"]
    out = [f"art.{k} 없음" for k in ART_NEED if not a.get(k)]
    p = a.get("palette") or {}
    out += [f"art.palette.{k} 없음" for k in ("bg", "ink", "accent") if not isinstance(p, dict) or not p.get(k)]
    return out


def apply_art(sb: dict) -> dict:
    """색을 영상 전체에 편다: 배경 · 강조 자막 · 재료 강조색. 콘티에 직접 적은 값이 이긴다(읽을 때만 적용, 파일은 그대로)"""
    d = sb.get("direction")
    p = ((d or {}).get("art") or {}).get("palette") if isinstance(d, dict) else None
    if not isinstance(p, dict):
        return sb
    if p.get("bg"):
        d.setdefault("color_bg", p["bg"])
    if p.get("accent"):
        d["subs"] = {"hot": p["accent"], **(d.get("subs") or {})}
    for s in sb.get("scenes") or []:
        for m in s.get("materials") or []:
            if p.get("accent") and m.get("type") in ("info_card", "ui_mock", "template_card", "diagram", "chart"):
                m.setdefault("accent", p["accent"])
    return sb


def enter_for(design: dict, kind: str) -> str | None:
    e = design.get("enter")
    if isinstance(e, dict):
        return e.get(kind) or e.get("*")
    return e or None


# ---------------------------------------------------------------- 레퍼런스에서
def from_reference(look: dict, xrays: list[dict]) -> dict:
    """X-ray 에서 잰 값 → 디자인 칸(근거가 있는 것만). look = story/look.py look(sb)"""
    if not look:
        return {}
    out: dict = {}
    cams = look.get("camera_mix") or {}
    total = sum(cams.values()) or 1
    push_share = sum(v for k, v in cams.items() if "push-in" in k) / total
    shake_share = sum(v for k, v in cams.items() if "handheld" in k) / total
    if push_share >= 0.2:
        out["cam_push"] = 1.05
        out["frame"] = {"push": 1.04}
    shot = float(look.get("shot_sec") or 3)
    out["enter"] = None if shot < 2.2 else "fadeIn"          # 빠른 컷 = 전환 없이 바로(하드 컷), 느린 편집 = 짧은 페이드
    # 화면 글자가 자주 바뀌는 채널 → 자막 '톡'
    texts = sum(len(x.get("text") or []) for x in xrays)
    dur = sum(float((x.get("video") or {}).get("duration") or 0) for x in xrays) or 1
    if texts / dur > 0.4:
        out["text_pop"] = True
    # 말 위주 / 음악 위주 → 목소리 처리
    sp_share = []
    for x in xrays:
        d = float((x.get("video") or {}).get("duration") or 0)
        if d:
            sp_share.append(sum(float(s["end"]) - float(s["start"]) for s in x.get("speech") or []) / d)
    if sp_share:
        s = sum(sp_share) / len(sp_share)
        out["sound"] = {"voice_chain": "clean" if s >= 0.45 else "light", "duck_db": -7 if s >= 0.45 else -3}
    if shake_share >= 0.3:
        out["note_camera"] = "handheld"                         # 기록만(움직임 단계는 흔들림을 넣지 않는다)
    return out


def proposals(sb: dict, ref: dict) -> list[dict]:
    """시안 2~3개(directions.py): A 레퍼런스대로 · B 담백(효과 없음) · C 움직임 조금(형식에 맞는 배경 · 짧은 등장)"""
    fmt = str(sb.get("format") or "")
    bg_by_fmt = {"emotional": "bokehDrift", "ad": "pulseRings", "daily": "softGradientDrift"}
    out = []
    if ref:
        out.append({"name": "레퍼런스대로", "direction": {**ref, "design_from": "reference"}})
    out.append({"name": "담백하게(효과 없음)", "direction": {k: NONE[k] for k in ("bg_preset", "bg_motion", "enter", "title_preset", "sub_preset", "text_pop", "cam_push")}
                | {"frame": dict(NONE["frame"]), "layout": "card", "subs": {"box": False}, "title": {"box": False, "fg": "#ffffff"}, "design_from": "none"}})
    out.append({"name": "움직임 조금", "direction": {"bg_preset": bg_by_fmt.get(fmt, "blueprintGrid"), "bg_motion": True, "enter": "fadeIn",
                                                  "title_preset": "bounceInWords", "text_pop": True, "cam_push": 1.04, "layout": "full",
                                                  "subs": {"box": True, "bg": "#ffd60a", "fg": "#111111", "hot": "#d4002a"}, "title": {"box": True},
                                                  "frame": {"shadow": True, "round": True, "push": 1.04}, "design_from": "motion"}})
    return out[:3]
