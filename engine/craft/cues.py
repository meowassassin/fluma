"""말과 맞추기 — Craft 명령의 시각 자리에 나레이션 낱말을 쓴다(2026-11-16).

  "$CUE:404"        그 장면 나레이션에서 '404'를 말하기 시작하는 순간
  "$CUE:404+0.3"    그 0.3초 뒤 (빼기도 된다: "$CUE:성공-0.2")
  "$CUE:404@end"    그 낱말을 다 말한 순간

재료(type: craft)에서는 장면 기준 초, 장면 다듬기(refine)에서는 영상 전체 기준 초로 바뀐다.
음성(data/audio/<id>.timing.json · .captions.json)이 있어야 한다 — produce 는 음성 뒤에 재료를 만든다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
CUE = re.compile(r"\$CUE:([^$+\-@\"]+?)(@end)?([+-]\d+(?:\.\d+)?)?(?=$|[^\w가-힣.])")
_norm = lambda s: re.sub(r"[\W_]", "", str(s))   # noqa: E731


def scene_words(sb: dict, i: int) -> tuple[list[dict], float]:
    """i번째 장면(0부터)의 단어 [{text, start, end}](장면 기준 초)와 장면 시작(영상 기준 초)"""
    a = ROOT / "data" / "audio"
    try:
        timing = json.loads((a / f"{sb['id']}.timing.json").read_text("utf-8"))
        caps = json.loads((a / f"{sb['id']}.captions.json").read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"$CUE 는 음성을 만든 뒤에 쓸 수 있습니다 — 음성 기록이 없습니다({e})") from e
    if not 0 <= i < len(timing):
        raise RuntimeError(f"$CUE: {i + 1}번 장면의 음성 기록이 없습니다")
    s0, s1 = float(timing[i]["start"]), float(timing[i]["end"])
    ws = [{"text": w["text"], "start": round(w["startMs"] / 1000 - s0, 3), "end": round(w["endMs"] / 1000 - s0, 3)}
          for w in caps if s0 * 1000 - 50 <= w.get("startMs", -1) < s1 * 1000]
    return ws, s0


def find(words: list[dict], word: str, end: bool = False, strict: bool = True) -> float | None:
    """정확히 같은 낱말 → 없으면 가장 닮은 낱말(각본가가 '떠요'를 '뜹니다'로 고쳐도 따라간다, 2026-11-17: 낱말이 어긋나 콘티를 23번 고쳤다)"""
    import difflib
    k = _norm(word)
    for w in words:                       # 1) 같은 낱말
        if k and _norm(w["text"]) == k:
            return w["end"] if end else w["start"]
    for w in words:                       # 2) 낱말을 품은 어절('6주' → '6주예요'). 어절이 낱말의 일부인 경우는 충분히 길 때만
        t = _norm(w["text"])               #    2026-11-24: '이번에' 가 앞의 한 글자 어절 '이' 에 걸려 0.6초 일찍 움직였다
        if k and t and (k in t or (t in k and len(t) >= max(2, 0.6 * len(k)))):
            return w["end"] if end else w["start"]
    best, score = None, 0.0
    for w in words:
        t = _norm(w["text"])
        if not t or not k:
            continue
        r = difflib.SequenceMatcher(None, k, t).ratio()
        if t[:1] == k[:1]:
            r += 0.1                      # 첫 글자가 같으면(어간이 같을 가능성) 조금 더
        if r > score:
            best, score = w, r
    if best is not None and score >= 0.55:
        print(f"[cue] '{word}' 정확히 없음 → 가장 닮은 '{best['text'].strip()}'({score:.2f})", flush=True)
        return best["end"] if end else best["start"]
    if not strict:
        return None
    said = " ".join(w["text"] for w in words)
    raise RuntimeError(f"$CUE:{word} — 이 장면 나레이션에 그 낱말이 없습니다(들리는 말: {said[:120]})")


# ---------- 대사가 바뀌어 낱말이 사라졌을 때: 지난번 자리로 다시 잇기 (2026-11-17) ----------
# 대사를 줄이거나 고치면 $CUE 낱말이 사라져 에이전트가 콘티를 수십 번 고쳤다(한 영상에서 cue 수정만 80회).
# 성공할 때마다 그 낱말이 '대사 몇 % 지점'(글자 기준)에 있었는지 적어 두고, 사라지면 새 대사의 같은 지점 낱말로 잇는다.
def _map_path(sb: dict) -> Path:
    return ROOT / "data" / "workspace" / "tmp" / str(sb.get("id")) / "cue_map.json"


def _load_map(sb: dict) -> dict:
    try:
        return json.loads(_map_path(sb).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_map(sb: dict, m: dict):
    p = _map_path(sb)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), "utf-8")


def _char_frac(words: list[dict], w_hit: dict) -> float:
    """낱말이 장면 대사에서 몇 % 지점(글자 수 기준)에 있는가"""
    total = sum(len(_norm(w["text"])) for w in words) or 1
    before = 0
    for w in words:
        if w is w_hit:
            break
        before += len(_norm(w["text"]))
    return round(before / total, 4)


def _at_frac(words: list[dict], frac: float) -> dict | None:
    """새 대사에서 같은 % 지점의 낱말"""
    if not words:
        return None
    total = sum(len(_norm(w["text"])) for w in words) or 1
    acc = 0
    for w in words:
        n = len(_norm(w["text"]))
        if (acc + n / 2) / total >= frac:
            return w
        acc += n
    return words[-1]


def _hit(words: list[dict], word: str) -> dict | None:
    t_ = find(words, word, False, strict=False)
    return next((w for w in words if w["start"] == t_), None) if t_ is not None else None


def resolve(o, sb: dict, i: int, absolute: bool = False):
    """o 안의 "$CUE:…" 를 초(숫자)로 바꾼다. 문자열 전체가 $CUE 면 숫자로, 코드 안에 섞여 있으면 글자로 바꿔 넣는다"""
    if not _has(o):
        return o
    words, s0 = scene_words(sb, i)
    base = s0 if absolute else 0.0
    cmap = _load_map(sb)
    dirty = [False]

    def sec(m: re.Match) -> float:
        word, end = m.group(1).strip(), bool(m.group(2))
        key = f"{i + 1}|{word}"
        w = _hit(words, word)
        if w is not None:
            fr = _char_frac(words, w)
            if cmap.get(key) != fr:
                cmap[key] = fr
                dirty[0] = True
        elif key in cmap and words:
            w = _at_frac(words, float(cmap[key]))
            print(f"[cue] {i + 1}장면 '{word}' 이 바뀐 대사에 없음 → 지난번과 같은 자리({cmap[key]:.0%})의 '{w['text'].strip()}' 에 맞춤", flush=True)
        else:
            find(words, word, end)        # 처음부터 없던 낱말 — 지금처럼 이유와 함께 멈춘다
        t = (w["end"] if end else w["start"]) + float(m.group(3) or 0)
        return round(max(0.0, t) + base, 3)

    def walk(x):
        if isinstance(x, str):
            full = CUE.fullmatch(x.strip())
            return sec(full) if full else CUE.sub(lambda m: str(sec(m)), x)
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    out = walk(o)
    if dirty[0]:
        _save_map(sb, cmap)
    return out


def _has(o) -> bool:
    if isinstance(o, str):
        return "$CUE:" in o
    if isinstance(o, dict):
        return any(_has(v) for v in o.values())
    if isinstance(o, list):
        return any(_has(v) for v in o)
    return False
