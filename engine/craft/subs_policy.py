"""말 자막 정책 — 프리셋 chars(화면 띠)와 말 따라가는 자막을 분리한다."""
from __future__ import annotations

CLAUSE_FORMATS = frozenset({"concept", "fix", "compare", "mythbust", "daily", "ad", "series"})
WORD_FORMATS = frozenset({"clip", "ranking"})
SCREEN_CAPTION_ROLES = frozenset({"hook", "reveal", "outro", "cta", "verdict", "price"})


def subs_mode(sb: dict) -> str:
    """word = 2~4어절 톡톡(클립·반응), clause = 한 구절(설명형 한국어)"""
    mode = (sb.get("direction") or {}).get("subs", {}).get("mode")
    if mode in ("word", "tok", "clause"):
        return "word" if mode in ("word", "tok") else "clause"
    fmt = sb.get("format") or ""
    if fmt in WORD_FORMATS:
        return "word"
    lang = sb.get("language") or "ko"
    lead = (sb.get("preset") or {}).get("lead") or ""
    if lang == "ko" and (lead == "말" or fmt in CLAUSE_FORMATS):
        return "clause"
    return "word"


def subs_max_chars(sb: dict, gsubs: dict | None = None) -> int:
    gsubs = gsubs or {}
    if gsubs.get("max_chars"):
        return int(gsubs["max_chars"])
    cap = ((sb.get("preset") or {}).get("layout") or {}).get("captions") or {}
    if subs_mode(sb) == "clause":
        per = float(cap.get("chars") or 9)
        return max(18, min(34, int(per * 2.8)))
    return 13


def apply_preset_direction_subs(sb: dict) -> bool:
    """프리셋 pick / direct 시 direction.subs 를 채운다 — 이미 mode 가 있으면 건너뜀."""
    pr = sb.get("preset") or {}
    if not pr:
        return False
    d = sb.setdefault("direction", {})
    subs = dict(d.get("subs") or {})
    if subs.get("mode"):
        return False
    lang = sb.get("language") or "ko"
    lead = pr.get("lead") or ""
    cap = (pr.get("layout") or {}).get("captions") or {}
    box = (cap.get("box") or 0) >= 0.5
    if lang == "ko" and lead == "말":
        mode = "clause"
    elif sb.get("format") in WORD_FORMATS:
        mode = "word"
    else:
        mode = subs_mode({**sb, "direction": {**d, "subs": subs}})
    subs.update(
        {
            "mode": mode,
            "max_chars": subs_max_chars(sb, subs),
            "box": subs.get("box", box),
        }
    )
    d["subs"] = subs
    if mode == "clause" and d.get("text_pop") is True and "text_pop" in (d.get("_auto") or []):
        d.pop("text_pop", None)
        auto = set(d.get("_auto") or [])
        auto.discard("text_pop")
        d["_auto"] = sorted(auto)
    return True


def show_screen_caption_band(sc: dict, *, has_speech: bool, screen_text: bool) -> bool:
    """본문에 나레이션이 있으면 위 띠 caption 은 훅·맺음만 — 말 자막과 이중 노출 방지."""
    cap = str(sc.get("caption") or "").strip()
    if not cap or not screen_text:
        return False
    if sc.get("caption_dedicated") is True:
        return True
    if not has_speech:
        return True
    return sc.get("role") in SCREEN_CAPTION_ROLES