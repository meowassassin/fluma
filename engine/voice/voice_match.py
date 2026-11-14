#!/usr/bin/env python3
"""레퍼런스 화자의 '높이 · 억양 폭 · 말끝 · 세기 변화 · 속도'에 가까운 목소리와 조절 값을 숫자로 고른다(복제 아님).

  python3 engine/voice/voice_match.py ref    data/storyboards/<id>.json                 # 레퍼런스 목소리 특징(채널 카드 > 스타일 카드)
  python3 engine/voice/voice_match.py pick   data/storyboards/<id>.json [--n 6] [--max-chars 400]   # 1) 짧은 문장으로 후보 목소리 비교
  python3 engine/voice/voice_match.py tune   data/storyboards/<id>.json [--voice tc_…] [--max-chars 500]  # 2) 1위 목소리로 감정 · 강도 · 말끝 · 음높이 조합 비교
  python3 engine/voice/voice_match.py apply  data/storyboards/<id>.json                 # 3) 조율 1위를 콘티 voice 에 적는다(속도 포함)
  python3 engine/voice/voice_match.py verify data/storyboards/<id>.json                 # 4) 합성된 '전체' 나레이션을 재서 레퍼런스와 견준다
  python3 engine/voice/voice_match.py auto   data/storyboards/<id>.json [--max-chars 400]  # 한 번에: 쓸 수 있는 모든 엔진에서 목소리 · 말 속도를 골라 콘티에(produce 가 부른다)

순서: pick → tune → apply → assemble_audio.py → verify. 결과는 data/workspace/render/<id>/voice-match.json · voice-check.json.
샘플은 늘 같은 문장(SAMPLE)이라 목소리 · 조합마다 한 번만 합성하고 data/workspace/cache/voice-samples/ 에 남긴다(다음 영상은 공짜).
유료 엔진(typecast · elevenlabs)은 --max-chars 안에서만 새로 합성한다(글자 수만큼 크레딧).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
import tts  # noqa: E402
import voice_profile as vp  # noqa: E402

SAMPLE = "이번엔 노트북 하나가 뚫렸고요, 거기서 서버 안쪽까지 들어간 거예요. 근데 이게 끝이 아니었다고 하더라고요."
CACHE = ROOT / "data" / "workspace" / "cache" / "voice-samples"


def load_sb(p: str) -> tuple[Path, dict]:
    sp = Path(p) if p.endswith(".json") else ROOT / "data" / "storyboards" / f"{p}.json"
    return sp, json.loads(sp.read_text(encoding="utf-8"))


def ref_profile(sb: dict) -> tuple[dict | None, str]:
    """레퍼런스 화자 특징: 채널 카드(여러 편 중앙값) > 스타일 카드 voice.prosody > 분해도 vocals 를 바로 잰다"""
    for rid in sb.get("reference") or []:
        sp = ROOT / "data" / "public" / "trends" / "xray" / str(rid) / "style" / "style.json"
        card = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
        ch = card.get("channel")
        cp = ROOT / "data" / "public" / "trends" / "channels" / str(ch) / "channel.json" if ch else None
        if cp and cp.exists():
            pr = (json.loads(cp.read_text(encoding="utf-8")).get("voice") or {}).get("prosody")
            if pr and pr.get("f0_median"):
                return pr, f"채널 {ch} 여러 편"
        if (card.get("voice") or {}).get("prosody", {}).get("f0_median"):
            return card["voice"]["prosody"], f"스타일 카드 {rid}"
        xp = ROOT / "data" / "public" / "trends" / "xray" / str(rid)
        if (xp / "vocals.m4a").exists() and (xp / "xray.json").exists():
            return vp.profile(xp / "vocals.m4a", json.loads((xp / "xray.json").read_text(encoding="utf-8")).get("speech")), f"분해도 {rid}"
    return None, ""


def sample(engine: str, voice: str, speed=1.0, style=None, opts=None, budget: dict | None = None) -> dict | None:
    """SAMPLE 을 합성(캐시)하고 특징을 잰다. budget={'left': 글자} 를 넘으면 None"""
    opts = {k: v for k, v in (opts or {}).items() if v not in (None, "", "keep")}
    key = hashlib.sha1(json.dumps([engine, voice, speed, style, opts, SAMPLE], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    d = CACHE / engine; d.mkdir(parents=True, exist_ok=True)
    wav, meta = d / f"{key}.wav", d / f"{key}.json"
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    if budget is not None and engine in ("typecast", "elevenlabs"):
        if budget["left"] < len(SAMPLE):
            return None
        budget["left"] -= len(SAMPLE); budget["spent"] = budget.get("spent", 0) + len(SAMPLE)
    tts.synth(SAMPLE, wav, voice, engine, speed=speed, style=style, opts=opts)
    pr = vp.profile(wav, vp.segs_from_words(tts.read_words(wav), SAMPLE))
    m = {"engine": engine, "voice": voice, "speed": speed, "style": style, "opts": opts, "profile": pr, "wav": str(wav.relative_to(ROOT))}
    meta.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def out_dir(sb: dict) -> Path:
    d = ROOT / "data" / "workspace" / "render" / sb["id"]; d.mkdir(parents=True, exist_ok=True)
    return d


def read_match(sb: dict) -> dict:
    p = out_dir(sb) / "voice-match.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_match(sb: dict, m: dict):
    (out_dir(sb) / "voice-match.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def candidates(engine: str, ref: dict) -> list[dict]:
    if engine == "typecast":
        vs = tts.typecast_voices()
        g = "M" if ref["f0_median"] < 165 else "F"
        vs = [v for v in vs if v["gender"] == g and v["id"].startswith("tc_") and any(m in v["models"] for m in ("ssfm-v31", "ssfm-v30"))]
        # 청년 · 중년 먼저(설명 쇼츠 화자), 어린이 · 노년은 뒤로
        order = lambda v: (0 if ("청년" in v["title"] or "중년" in v["title"]) else 1)
        return sorted(vs, key=order)
    meta = tts.voice_meta(engine)
    return [{"id": v["id"], "title": v.get("title", v["id"])} for v in meta.get("voices") or []] or [{"id": None, "title": "기본"}]


def cmd_pick(sb, a):
    ref, src = ref_profile(sb)
    if not ref:
        sys.exit("레퍼런스 목소리 특징이 없습니다 — 콘티 reference 에 분해한 쇼츠 id 를 넣고 ref_style.py · ref_channel.py 를 먼저")
    eng = a.engine or (sb.get("voice") or {}).get("engine") or tts.resolve(sb)[0]
    budget = {"left": a.max_chars}
    rows = []
    cands = candidates(eng, ref)
    # 이미 잰 목소리는 공짜 — 모두 넣고, 새로 잴 것은 예산 안에서 n 개까지
    fresh = 0
    for v in cands:
        m = sample(eng, v["id"], budget=None) if (CACHE / eng).exists() and _cached(eng, v["id"]) else None
        if m is None:
            if fresh >= a.n:
                continue
            m = sample(eng, v["id"], budget=budget)
            if m is None:
                break
            fresh += 1
        rows.append({"voice": v["id"], "title": v["title"], "distance": vp.distance(ref, m["profile"]), "profile": m["profile"]})
    rows.sort(key=lambda r: r["distance"])
    m = read_match(sb); m.update({"ref": ref, "ref_source": src, "engine": eng, "pick": rows[:10]}); write_match(sb, m)
    print(f"레퍼런스({src}): {fmt(ref)}")
    for r in rows[:8]:
        print(f"  {r['distance']:5.2f}  {r['title']} ({r['voice']})  {fmt(r['profile'])}")
    print(json.dumps({"engine": eng, "best": rows[0]["voice"] if rows else None, "measured": len(rows), "new_chars": budget.get("spent", 0)}, ensure_ascii=False))


def _cached(engine: str, voice) -> bool:
    key = hashlib.sha1(json.dumps([engine, voice, 1.0, None, {}, SAMPLE], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return (CACHE / engine / f"{key}.json").exists()


def fmt(p: dict) -> str:
    return " · ".join(f"{k} {p[k]}" for k in ("f0_median", "range_st", "end_drop_st", "energy_sd_db", "cps") if p.get(k) is not None)


def cmd_tune(sb, a):
    m = read_match(sb)
    ref = m.get("ref") or ref_profile(sb)[0]
    eng = m.get("engine") or a.engine or tts.resolve(sb)[0]
    voice = a.voice or ((m.get("pick") or [{}])[0].get("voice"))
    if not ref or not voice:
        sys.exit("먼저 pick 으로 목소리를 고르세요(또는 --voice)")
    base = sample(eng, voice) or {}
    bp = base.get("profile") or {}
    # 음높이: 레퍼런스 높이로 옮기는 반음(±4 안). 속도: 레퍼런스 초당 글자에 맞춤
    shift = int(max(-4, min(4, round(12 * math.log2(ref["f0_median"] / bp["f0_median"]))))) if bp.get("f0_median") else 0
    speed = round(max(0.8, min(1.6, ref["cps"] / bp["cps"])), 2) if ref.get("cps") and bp.get("cps") else 1.0
    combos = []
    styles = ["normal", "tonedown"] if eng == "typecast" else [None]
    for st in styles:
        for inten in ([1.0, 0.6] if eng == "typecast" else [None]):
            for end in ("keep", "period"):
                combos.append({"style": st, "opts": {"intensity": inten if inten != 1.0 else None, "ending": end, "pitch": shift if eng == "typecast" and shift else None}})
    budget = {"left": a.max_chars}
    rows = []
    for c in combos:
        r = sample(eng, voice, speed, c["style"], c["opts"], budget=budget)
        if r is None:
            print(f"[예산] --max-chars {a.max_chars} 를 다 써서 나머지 조합은 건너뜀", file=sys.stderr)
            break
        rows.append({**c, "speed": speed, "distance": vp.distance(ref, r["profile"]), "profile": r["profile"], "wav": r["wav"]})
    rows.sort(key=lambda r: r["distance"])
    m.update({"ref": ref, "engine": eng, "voice": voice, "tune": rows}); write_match(sb, m)
    print(f"레퍼런스: {fmt(ref)}  · 음높이 보정 {shift:+d}반음 · 속도 {speed}")
    for r in rows:
        print(f"  {r['distance']:5.2f}  감정 {r['style']} · 강도 {r['opts'].get('intensity') or 1.0} · 말끝 {r['opts']['ending']}  {fmt(r['profile'])}")
    print(json.dumps({"best": rows[0] if rows else None, "new_chars": budget.get("spent", 0)}, ensure_ascii=False)[:600])


def cmd_apply(sb_path: Path, sb: dict, a):
    m = read_match(sb)
    best = (m.get("tune") or [None])[0]
    if not best:
        sys.exit("먼저 tune")
    v = dict(sb.get("voice") or {})
    v.update({"engine": m["engine"], "id": m["voice"], "speed": best["speed"]})
    if best.get("style"):
        v["style"] = best["style"]
    else:
        v.pop("style", None)   # 엔진이 바뀌면 이전 엔진의 감정 · 말투 지시는 뜻이 다르다
    for k in ("intensity", "pitch", "ending"):
        val = best["opts"].get(k)
        if val in (None, "", "keep"):
            v.pop(k, None)
        else:
            v[k] = val
    sb["voice"] = v
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "voice": v}, ensure_ascii=False))


def cmd_verify(sb, a):
    """최종 나레이션 '전체'를 잰다 — 한 문장 샘플이 아니라 실제로 들어간 음성"""
    ref, src = ref_profile(sb)
    work = ROOT / "data" / "audio" / sb["id"]
    tj = ROOT / "data" / "audio" / f"{sb['id']}.timing.json"
    wav = ROOT / "data" / "audio" / f"{sb['id']}.wav"
    if not wav.exists():
        sys.exit("나레이션이 아직 없습니다 — assemble_audio.py 먼저")
    # 이어 말하기면 대본 전체 합성본(가장 최근 all-*.wav)의 단어 시각, 아니면 장면 합성본을 묶어 잰다
    alls = sorted(work.glob("all-*.wav"), key=lambda p: p.stat().st_mtime)
    if alls and alls[-1].stat().st_mtime >= wav.stat().st_mtime - 600:
        full = " ".join((sc.get("narration") or "").strip() for sc in sb["scenes"])
        src_wav, segs = alls[-1], vp.segs_from_words(tts.read_words(alls[-1]), full)
    else:
        src_wav, segs = wav, None
        if tj.exists():
            t = json.loads(tj.read_text(encoding="utf-8"))
            segs = [{"start": s["start"], "end": s["end"], "text": s.get("narration", "")} for s in (t.get("scenes") if isinstance(t, dict) else t) or [] if s.get("narration")] or None
    got = vp.profile(src_wav, segs)
    rows = vp.compare(ref, got) if ref else []
    res = {"ref": ref, "ref_source": src, "got": got, "audio": str(src_wav.relative_to(ROOT)), "distance": vp.distance(ref, got) if ref else None, "rows": rows}
    (out_dir(sb) / "voice-check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"| 항목 | 레퍼런스({src}) | 지금 나레이션 | 판정 |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r['item']} | {r['ref']} | {r['got']} | {r['verdict']} |")
    print(json.dumps({"distance": res["distance"], "off": [r["item"] for r in rows if r["verdict"] != "비슷"]}, ensure_ascii=False))



# ---------- 자동(엔진을 가로질러) ----------
# 한국어 품질 순 — 쓸 수 있는(키 · 설치) 엔진만 후보. silent · espeak 은 나레이션 후보가 아니다
ENGINE_ORDER = ["typecast", "elevenlabs", "supertonic", "cosyvoice", "melotts", "xtts", "chatterbox", "edge"]
TARGET_CPS = {"emotional": 5.6, "ad": 6.6, "daily": 7.0}            # 레퍼런스가 없을 때 말 속도(초당 글자) — 쇼츠 설명형 7.0


def _voices_of(eng: str, gender: str | None) -> list[dict]:
    if eng == "typecast":
        vs = candidates(eng, {"f0_median": 120 if gender == "M" else 220})
    else:
        vs = [{"id": v["id"], "title": v.get("title", v["id"]), "gender": v.get("gender")} for v in tts.voice_meta(eng).get("voices") or []] or [{"id": None, "title": "기본"}]
        if gender:
            vs = [v for v in vs if v.get("gender") in (gender, None, "-")] or vs
    return vs


def cmd_auto(sb_path: Path, sb: dict, a):
    v = sb.get("voice") or {}
    st = tts._settings()
    if v.get("source") == "user":
        print("[음성] 사용자가 정한 목소리 — 그대로"); return
    if st.get("voice_auto") is False:
        print(f"[음성] 설정에서 고정한 목소리({st.get('voice_engine')}) — 자동 선택 안 함"); return
    ref, src = ref_profile(sb)
    engines = [e for e in ENGINE_ORDER if e in tts.list_voice_engines() and tts.engine_available(e) and tts.voice_meta(e).get("korean", True)]
    if not engines:
        engines = ["edge"]
    gender = None
    if ref and ref.get("f0_median"):
        gender = "M" if ref["f0_median"] < 165 else "F"
    budget = {"left": a.max_chars}
    rows = []
    for eng in engines[:4] if ref else engines[:1]:      # 레퍼런스가 없으면 비교할 기준이 없다 — 가장 좋은 엔진의 첫 목소리
        fresh = 0
        for c in _voices_of(eng, gender)[: (5 if ref else 1)]:
            cached = _cached(eng, c["id"])
            if not cached and fresh >= 3:
                continue
            try:
                m = sample(eng, c["id"], budget=budget)
            except Exception as e:  # noqa: BLE001  엔진 하나가 실패해도 다른 엔진으로
                print(f"[음성] {eng} {c['id']} 샘플 실패: {str(e)[:80]}", file=sys.stderr); break
            if m is None:
                break
            fresh += 0 if cached else 1
            d = vp.distance(ref, m["profile"]) if ref else 0.0
            rows.append({"engine": eng, "voice": c["id"], "title": c["title"], "distance": round(d, 2), "profile": m["profile"],
                         "rank": ENGINE_ORDER.index(eng)})
    if not rows:
        print("[음성] 후보를 재지 못함 — 설정의 기본 목소리로"); return
    # 거리(레퍼런스와 닮음)가 비슷하면(0.3 안) 품질 좋은 엔진 쪽
    rows.sort(key=lambda r: (round(r["distance"] / 0.3), r["rank"], r["distance"]))
    best = rows[0]
    cps = (best["profile"] or {}).get("cps") or 0
    fmt = str(sb.get("format") or "").replace("format-", "")
    want = (ref or {}).get("cps") or TARGET_CPS.get(fmt, 7.0)
    speed = round(min(1.3, max(0.85, want / cps)), 2) if cps else 1.0
    nv = {k: val for k, val in v.items() if k in ("intensity", "pitch", "ending") and v.get("engine") == best["engine"]}
    nv.update({"engine": best["engine"], "id": best["voice"], "speed": speed, "source": "auto",
               "why": (f"레퍼런스({src}) 화자와 가장 닮음(거리 {best['distance']})" if ref else "레퍼런스 없음 — 쓸 수 있는 엔진 중 한국어 품질 1순위") +
                      f" · 말 속도 {want:.1f}자/초에 맞춰 ×{speed}"})
    sb["voice"] = nv
    sb_path.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m = read_match(sb); m.update({"auto": rows[:8], "ref": ref, "ref_source": src}); write_match(sb, m)
    print(f"[음성] {best['engine']} · {best['title']} ({best['voice']}) · ×{speed} — {nv['why']}" + (f" · 새로 합성 {budget.get('spent', 0)}자" if budget.get("spent") else ""))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["ref", "pick", "tune", "apply", "verify", "auto"])
    ap.add_argument("storyboard")
    ap.add_argument("--engine")
    ap.add_argument("--voice")
    ap.add_argument("--n", type=int, default=6, help="pick: 새로 잴 후보 수(이미 잰 목소리는 늘 포함)")
    ap.add_argument("--max-chars", type=int, default=None, help="새로 합성할 글자 수 한도(유료 엔진 크레딧). 기본 pick 400 · tune 500")
    a = ap.parse_args()
    if a.max_chars is None:
        a.max_chars = 400 if a.cmd in ("pick", "auto") else 500
    sp, sb = load_sb(a.storyboard)
    if a.cmd == "ref":
        r, src = ref_profile(sb); print(json.dumps({"source": src, "ref": r}, ensure_ascii=False))
    elif a.cmd == "pick":
        cmd_pick(sb, a)
    elif a.cmd == "tune":
        cmd_tune(sb, a)
    elif a.cmd == "apply":
        cmd_apply(sp, sb, a)
    elif a.cmd == "auto":
        cmd_auto(sp, sb, a)
    else:
        cmd_verify(sb, a)


if __name__ == "__main__":
    main()
