#!/usr/bin/env python3
"""능력별 모델 목록 · 고른 모델 · 비용 관문 — 설정 → 모델 화면과 엔진이 같이 쓴다.

능력(capability): 코드는 모델 이름을 박지 않는다. 사용자가 능력마다 고르고(설정 → 모델), 영상마다 콘티 direction.models 로 바꿀 수 있다.
  see.video   보기 · 영상 이해(VL)      — 레퍼런스 · 초안 영상. 기본 켬(키가 있으면)
  make.image  그리기 · 이미지 생성       — 느낌 시안 · 키프레임
  edit.image  고치기 · 이미지 편집       — 세로 확장 · 지우기 · 부분 수정
  make.video  찍기 · 영상 생성           — 고른 키프레임 → 영상
  voice.tts   말하기 · 음성
  voice.stt   듣기 · 받아쓰기
  make.sound  소리 · 음악
  embed       찾기 · 임베딩
키가 없거나 '무료 · 로컬'을 고르면 지금의 로컬 경로(측정 X-ray · Edge/로컬 TTS · whisper · 프롬프트만)를 쓴다.

비용 관문: 돈이 드는 호출은 guard()(예상 → 영상당 상한 안이면 통과, 넘거나 예상 불가면 사용자 승인 필요) → record()(장부 data/workspace/spend.jsonl).

  python3 engine/providers/catalog.py caps [--json]                   # 능력마다 고른 모델 · 로컬 대체 · 키 있음
  python3 engine/providers/catalog.py list make.video [--refresh] [--json]
  python3 engine/providers/catalog.py spend [<콘티 id>]                # 쓴 돈
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401

CACHE = ROOT / "data" / "cache" / "providers" / "models.json"
SETTINGS = ROOT / "data" / "workspace" / "settings.json"
LEDGER = ROOT / "data" / "workspace" / "spend.jsonl"
TTL = 24 * 3600
DEFAULT_CAP_USD = 3.0

CAPS = {
    "see.video": {"title": "보기 · 영상 이해(VL)", "src": "models", "local": "측정 X-ray + 프레임 시트(에이전트가 봄)", "default_on": True},
    "make.image": {"title": "그리기 · 이미지 생성", "src": "images/models", "local": "프롬프트만(내 도구로 만들어 올림)"},
    "edit.image": {"title": "고치기 · 이미지 편집 · 세로 확장", "src": "images/models", "local": "가운데 띠 + 흐린 배경 · PhotoCraft"},
    "make.video": {"title": "찍기 · 영상 생성", "src": "videos/models", "local": "프롬프트만(내 도구로 만들어 올림)"},
    "voice.tts": {"title": "말하기 · 음성", "src": "models?output_modalities=speech", "local": "Edge TTS · 로컬 TTS(설정 → 미디어 → 음성)"},
    "voice.stt": {"title": "듣기 · 받아쓰기", "src": "models?output_modalities=transcription", "local": "faster-whisper(로컬)"},
    "make.sound": {"title": "소리 · 음악", "src": "models?output_modalities=audio", "local": "끔(쇼츠 라이브러리 곡 안내 · SoundCraft)"},
    "embed": {"title": "찾기 · 임베딩", "src": "embeddings/models", "local": "글자 겹침 비교"},
}
# 키가 있는데 사용자가 아직 안 고른 '기본 켬' 능력의 첫 후보(목록에 있는 것 중 앞 순서) — 설정에서 언제든 바꾼다
DEFAULT_PICK = {"see.video": ["google/gemini-4-argon", "qwen/qwen3.8-omni-flash", "google/gemini-omni-1.2-flash"]}


# ---------------------------------------------------------------- 목록(공개 API, 하루 한 번)
def _fetch_all() -> dict:
    import openrouter as OR
    out = {"at": time.time()}
    for src in sorted({c["src"] for c in CAPS.values()}):
        path, _, q = src.partition("?")
        params = dict(x.split("=", 1) for x in q.split("&")) if q else None
        out[src] = OR.public(path, params).get("data") or []
    return out


def raw(refresh: bool = False) -> dict:
    old = None
    if CACHE.exists():
        try:
            old = json.loads(CACHE.read_text("utf-8"))
        except ValueError:
            old = None
    if old and not refresh and time.time() - float(old.get("at") or 0) < TTL:
        return old
    try:
        new = _fetch_all()
    except Exception as e:  # noqa: BLE001 — 인터넷이 없으면 예전 목록이라도
        if old:
            print(f"[모델 목록] 새로 받지 못해 예전 목록을 씁니다: {e}", file=sys.stderr)
            return old
        raise
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(new, ensure_ascii=False), "utf-8")
    return new


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def per_second(m: dict) -> dict:
    """영상 모델의 '출력 초당' 가격(USD)만 — 단위가 이름에 있다: cents_* 는 센트, reference · long · continuation · input 은 다른 과금"""
    out = {}
    for k, v in (m.get("pricing_skus") or {}).items():
        x = _f(v)
        if x is None or "second" not in k or any(w in k for w in ("reference", "long_", "continuation", "input")):
            continue
        out[k] = x / 100 if k.startswith("cents") else x
    return out


def _video_row(m: dict) -> dict:
    skus = {k: _f(v) for k, v in (m.get("pricing_skus") or {}).items() if _f(v) is not None}
    per_sec = per_second(m)
    lab = ""
    if per_sec:
        p720 = next((v for k, v in per_sec.items() if "720p" in k), None) or min(per_sec.values())
        lab = f"초당 ${p720:.3f}~" if p720 else ""
    elif skus:
        lab = "영상 토큰 단위(초 환산은 공식 문서)"
    sup = []
    if "9:16" in (m.get("supported_aspect_ratios") or []):
        sup.append("9:16")
    if "first_frame" in (m.get("supported_frame_images") or []):
        sup.append("시작 이미지")
    if m.get("generate_audio"):
        sup.append("소리")
    d = m.get("supported_durations") or []
    if d:
        sup.append(f"{min(d)}–{max(d)}초")
    return {"price": skus, "price_label": lab, "supports": sup, "ok": "9:16" in (m.get("supported_aspect_ratios") or [])}


def _image_row(m: dict, edit: bool) -> dict:
    sp = m.get("supported_parameters") or {}
    asp = (sp.get("aspect_ratio") or {}).get("values") or []
    refs = sp.get("input_references") or {}
    sup = []
    if "9:16" in asp:
        sup.append("9:16")
    if refs:
        sup.append(f"참조 그림 {refs.get('max', '')}장".strip())
    if "transparent" in ((sp.get("background") or {}).get("values") or []):
        sup.append("투명 배경")
    takes_image = "image" in ((m.get("architecture") or {}).get("input_modalities") or [])
    ok = ("9:16" in asp or not asp) and (takes_image or bool(refs)) if edit else ("9:16" in asp or not asp)
    return {"price": {}, "price_label": "고르면 가격 확인", "supports": sup, "ok": ok}


def _chat_row(m: dict, unit: str) -> dict:
    p = m.get("pricing") or {}
    pr, co = _f(p.get("prompt")), _f(p.get("completion"))
    if unit == "tokens":
        lab = f"입력 100만 토큰 ${pr * 1e6:.2f}" if pr is not None else ""
    else:
        lab = f"단가 ${pr:g}" if pr else (f"출력 단가 ${co:g}" if co else "")
    ctx = m.get("context_length")
    return {"price": {"prompt": pr, "completion": co}, "price_label": lab, "supports": [f"문맥 {ctx // 1000}k"] if ctx else [], "ok": True}


def models(cap: str, refresh: bool = False) -> list[dict]:
    """능력에 맞는 모델 — [{id, name, free, price_label, supports, ok}] (ok = Fluma 에 쓸 수 있음: 9:16 등)"""
    c = CAPS[cap]
    data = raw(refresh).get(c["src"]) or []
    rows = []
    for m in data:
        mods = (m.get("architecture") or {}).get("input_modalities") or []
        if cap == "see.video" and "video" not in mods:
            continue
        if cap == "make.video":
            r = _video_row(m)
        elif cap in ("make.image", "edit.image"):
            r = _image_row(m, cap == "edit.image")
        elif cap == "see.video":
            r = _chat_row(m, "tokens")
        else:
            r = _chat_row(m, "unit")
        if cap == "embed" and "image" in mods:
            r["supports"] = [*r["supports"], "그림도(화면 종류 판별)"]
        free = m["id"].endswith(":free") or (bool(r["price"]) and all((v or 0) == 0 for v in r["price"].values()))
        rows.append({"id": m["id"], "name": m.get("name") or m["id"], "free": free, **r})
    rows.sort(key=lambda r: (not r["ok"], r["id"]))
    return rows


# ---------------------------------------------------------------- 고른 모델
def settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def has_key() -> bool:
    import openrouter as OR
    return OR.has_key()


def chosen(cap: str, sb: dict | None = None) -> str | None:
    """이 능력에 쓸 모델 id — 콘티 direction.models > 설정 models > (기본 켬 능력이면) 첫 후보. None = 로컬 경로.
    'local' 로 고르면 키가 있어도 로컬"""
    if not has_key():
        return None
    per = ((sb or {}).get("direction") or {}).get("models") or {}
    pick = per.get(cap) or (settings().get("models") or {}).get(cap)
    if pick == "local":
        return None
    if pick:
        return pick
    if CAPS[cap].get("default_on"):
        try:
            ids = {m["id"] for m in models(cap)}
        except Exception:  # noqa: BLE001
            ids = set()
        return next((x for x in DEFAULT_PICK.get(cap, []) if x in ids), None)
    return None


def caps_summary() -> list[dict]:
    st = settings().get("models") or {}
    key = has_key()
    return [{"cap": k, "title": v["title"], "local": v["local"], "chosen": chosen(k) if key else None, "set": st.get(k),
             "default_on": bool(v.get("default_on")), "key": key} for k, v in CAPS.items()]


# ---------------------------------------------------------------- 비용 관문
class NeedApproval(RuntimeError):
    """상한을 넘거나 예상할 수 없는 유료 호출 — 사용자에게 금액을 보여 주고 승인받은 뒤 --approve 로 다시"""


def cap_usd() -> float:
    b = settings().get("budget") or {}
    v = _f(b.get("per_video"))
    return DEFAULT_CAP_USD if v is None else v


def spent(sid: str | None = None, month: str | None = None) -> float:
    tot = 0.0
    if not LEDGER.exists():
        return 0.0
    for line in LEDGER.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if sid and r.get("sid") != sid:
            continue
        if month and not str(r.get("at", "")).startswith(month):
            continue
        tot += float(r.get("usd") or 0)
    return round(tot, 4)


def estimate_video(model: str, seconds: float, resolution: str = "720p", audio: bool = True) -> float | None:
    m = next((x for x in raw().get("videos/models") or [] if x["id"] == model), None)
    if not m:
        return None
    skus = per_second(m)
    if not skus:
        return None                                   # 영상 토큰 단위 — 예상 불가(승인 필요)
    def score(k):
        return (resolution in k) * 2 + (("with_audio" in k) == audio) + ("without" not in k and not audio and "audio" in k) * -1
    k = min(skus, key=lambda k: (-score(k), skus[k]))       # 해상도 · 소리가 맞는 것 중 가장 싼 것
    return round(skus[k] * seconds, 4)


def estimate_image(model: str, n: int = 1) -> float | None:
    """그림 한 장 값 — 그 모델 공급자 기록의 output_image 단가(장 단위일 때만)"""
    import openrouter as OR
    try:
        js = OR.public(f"images/models/{model}/endpoints")
    except Exception:  # noqa: BLE001
        return None
    best = None
    for ep in js.get("endpoints") or (js.get("data") or {}).get("endpoints") or []:
        for p in ep.get("pricing") or []:
            if p.get("billable") == "output_image" and p.get("unit") == "image" and not p.get("variant"):
                c = _f(p.get("cost_usd"))
                best = c if best is None or (c is not None and c < best) else best
    return round(best * n, 4) if best is not None else None


def guard(sid: str, cap: str, model: str, est: float | None, what: str, approve: bool = False) -> None:
    """상한 안이면 통과. 넘거나 예상 불가면 승인(approve=True — 사용자가 금액을 보고 '예' 한 뒤에만) 없이는 막는다"""
    if approve:
        return
    lim, used = cap_usd(), spent(sid)
    if est is None:
        raise NeedApproval(f"{what}: {model} 의 비용을 미리 계산할 수 없습니다(가격 단위가 다름) — 사용자에게 모델 페이지 가격을 보여 주고 승인받은 뒤 --approve")
    if used + est > lim + 1e-9:
        raise NeedApproval(f"{what}: 예상 ${est:.3f} — 이 영상에 쓴 돈 ${used:.3f} + 예상이 상한 ${lim:.2f} 을 넘습니다. 사용자 승인 뒤 --approve(또는 설정에서 상한 조정)")


def record(sid: str, cap: str, model: str, usd: float | None, what: str, est: float | None = None, extra: dict | None = None) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": dt.datetime.now().isoformat(timespec="seconds"), "sid": sid, "cap": cap, "model": model,
           "usd": usd if usd is not None else est, "estimated": usd is None, "what": what, **(extra or {})}
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("caps"); c.add_argument("--json", action="store_true")
    li = sub.add_parser("list"); li.add_argument("cap", choices=list(CAPS)); li.add_argument("--refresh", action="store_true"); li.add_argument("--json", action="store_true")
    sp = sub.add_parser("spend"); sp.add_argument("sid", nargs="?")
    a = ap.parse_args()
    if a.cmd == "caps":
        rows = caps_summary()
        if a.json:
            print(json.dumps({"caps": rows, "key": has_key(), "cap_usd": cap_usd(), "month": spent(month=dt.date.today().strftime("%Y-%m"))}, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['title']:22} {r['chosen'] or '(무료 · 로컬) ' + r['local']}")
        return 0
    if a.cmd == "list":
        rows = models(a.cap, a.refresh)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{'✓' if r['ok'] else '·'} {r['id']:48} {r['price_label']:28} {' · '.join(r['supports'])}")
        return 0
    m = dt.date.today().strftime("%Y-%m")
    print(json.dumps({"sid": a.sid, "video": spent(a.sid) if a.sid else None, "month": spent(month=m), "cap_usd": cap_usd()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
