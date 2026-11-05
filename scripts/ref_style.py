#!/usr/bin/env python3
"""레퍼런스 스타일 카드 — 참고 쇼츠의 '느낌'을 내 주제로 옮길 수 있게 형식 · 박자 · 말투를 뽑는다(내용은 옮기지 않는다).

  python3 scripts/ref_style.py <xray id> [--langs korean,en]      # 먼저 shorts_xray.py 로 분해되어 있어야 한다

범용: 형식을 가정하지 않는다 — 화면 종류는 CLIP 제로샷(vision_tags.py: 실제 화면 · 기사 · 사람 · 실사 · 제품 · 음식 · 짤 ·
일러스트 · 글자 카드 · 도표 · 게임 · 3D), 움직임 · 전환 · 배치는 분해도 수치(카메라 고정 비율 · 컷 길이 · 띠)에서, 말이 없으면 음악 · 컷 박자로.
결과: public/trends/xray/<id>/style/
  style.json   기계가 쓰는 카드: 화면 배치(가운데 띠) · 자막 양식(색 · 위치 · 괄호/인용) · 컷 리듬 · 말 속도 · 이어 말하기 ·
               박자표(샷마다 화면 종류 · 박자 역할 · 겹치는 대사 · 자막) · 디자인 방향 기본값
  style.md     사람 · 에이전트가 읽는 요약 + "내 주제로 옮기는 법"
  sheet-*.jpg  2초 간격 밀착 시트(시각 표시) — 에이전트가 직접 보고 박자 역할을 다듬는다
원본의 그림 · 대사 · 자막 글은 '말투 예시'로만 남긴다. 콘티 · 화면은 사용자의 주제로 새로 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
XR = ROOT / "public" / "trends" / "xray"


def say(p, stage):
    print(f"@progress {p:.2f} {stage}", flush=True)


def frame_at(src: Path, t: float, dst: Path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)], check=True)
    return dst


def band_of(img: np.ndarray) -> tuple[float, float, str]:
    """검정(또는 단색) 바탕 위 내용 띠: 위 · 아래(0~1) · 바탕색"""
    g = img.mean(axis=2)
    H = g.shape[0]
    edge = np.concatenate([img[: max(2, H // 40)].reshape(-1, 3), img[-max(2, H // 40):].reshape(-1, 3)])
    bgc = np.median(edge, axis=0)
    diff = np.abs(img.astype(float) - bgc).mean(axis=(1, 2))
    rows = np.where(diff > 18)[0]
    if not len(rows):
        return 0.0, 1.0, "#%02x%02x%02x" % tuple(int(x) for x in bgc)
    return round(rows.min() / H, 3), round(rows.max() / H, 3), "#%02x%02x%02x" % tuple(int(x) for x in bgc)


# 화면 종류 → 박자 역할(범용 기본값 — 에이전트가 밀착 시트를 보고 고친다)
ROLE_BY_KIND = {"실제 화면": "증거 — 실제 화면을 보여 주며 사실", "기사": "근거 — 기사 · 출처", "사람": "화자 — 사람이 직접 말함 · 반응",
                "실사 영상": "보여 주기 — 현장 · 대상 자체", "제품": "보여 주기 — 제품 · 디테일", "음식": "보여 주기 — 과정 · 결과",
                "카드(글자)": "글자 카드 — 한 줄 메시지 · 인용", "도표": "설명 — 도표 · 숫자", "애니메이션 · 일러스트": "설명 — 그림으로",
                "게임 화면": "보여 주기 — 플레이 장면", "3D 그래픽": "보여 주기 — 3D 연출", "짤": "펀치 — 반응 짤"}

ENDINGS = ["는데", "고요", "거든요", "대요", "네요", "어요", "아요", "예요", "에요", "습니다", "죠", "잖아요", "더라고요", "ㅋㅋ"]


def tone_of(texts: list[str]) -> dict:
    """말투: 문장 끝 · 이음말 빈도(원문은 남기지 않고 통계만)"""
    joined = " ".join(texts)
    ends = {e: len(re.findall(re.escape(e) + r"[\s.,?!]", joined + " ")) for e in ENDINGS}
    links = {w: joined.count(w) for w in ["근데", "그래서", "그리고", "아무튼", "심지어", "막", "되게", "그냥", "진짜", "약간", "이제"]}
    return {"endings": {k: v for k, v in sorted(ends.items(), key=lambda x: -x[1]) if v}, "connectives": {k: v for k, v in sorted(links.items(), key=lambda x: -x[1]) if v}}


def _lum(h: str) -> float:
    return sum(int(h[i:i + 2], 16) for i in (1, 3, 5)) / 3


def is_overlay(o: dict) -> bool:
    t = o["text"].strip()
    marked = t[:1] in "(\"'“‘[" or bool(re.search(r"[←→↑↓▼▲]", t))
    contrast = abs(_lum(o["bg"]) - _lum(o["fg"])) > 150
    big = o["box"][3] >= 0.022
    short = len(t) <= 30
    return short and (marked or (big and contrast))


def cap_style(o: dict) -> str:
    t = o["text"]
    light = lambda h: sum(int(h[i:i + 2], 16) for i in (1, 3, 5)) > 450
    box = "흰 상자 · 검정 글씨" if light(o["bg"]) and not light(o["fg"]) else "검정 바탕 · 흰 글씨" if not light(o["bg"]) and light(o["fg"]) else f"{o['bg']} 바탕 · {o['fg']} 글씨"
    kind = "괄호" if t.startswith("(") else "인용" if t[:1] in "\"'“‘" else "화살표 주석" if re.search(r"[←→↑↓▼▲]", t) else "글"
    return f"{kind} · {box}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--langs", default="korean,en")
    a = ap.parse_args()
    d = XR / a.id
    xp, src = d / "xray.json", d / "src.mp4"
    if not xp.exists() or not src.exists():
        sys.exit("분해도 · 원본이 없습니다 — 먼저 python3 scripts/shorts_xray.py <id> (원본은 분석 동안만 보관)")
    x = json.loads(xp.read_text(encoding="utf-8"))
    out = d / "style"; out.mkdir(exist_ok=True)
    tmp = out / "_f"; tmp.mkdir(exist_ok=True)
    dur = float(x["video"]["duration"])
    import ocr
    import vision_tags

    # 1) 2초 간격 밀착 시트 + 화면 배치(띠)
    say(0.05, "밀착 시트")
    ts = [round(t * 0.5, 2) for t in range(int(dur * 2))]
    bands, thumbs = [], []
    for t, arr in ocr.frames(src, 0.01, 0.5, len(ts)):
        im = Image.fromarray(arr)
        bands.append(band_of(arr))
        th = im.copy(); th.thumbnail((180, 320))
        dr = ImageDraw.Draw(th); dr.rectangle([0, 0, 46, 16], fill=(0, 0, 0)); dr.text((3, 2), f"{t:.1f}s", fill=(255, 255, 0))
        thumbs.append(th)
    per = 24
    sheets = []
    for k in range(0, len(thumbs), per):
        grp = thumbs[k:k + per]; w, h = grp[0].size
        sh = Image.new("RGB", (w * 8, h * ((len(grp) + 7) // 8)), (40, 40, 40))
        for i, th in enumerate(grp):
            sh.paste(th, ((i % 8) * w, (i // 8) * h))
        p = out / f"sheet-{k // per + 1}.jpg"; sh.save(p, quality=85); sheets.append(str(p.relative_to(ROOT)))
    tops = [b[0] for b in bands if b[1] - b[0] < 0.95]; bots = [b[1] for b in bands if b[1] - b[0] < 0.95]
    letterbox = len(tops) / max(1, len(bands))
    bg = max(set(b[2] for b in bands), key=[b[2] for b in bands].count)
    layout = {"letterbox_ratio": round(letterbox, 2), "band_top": round(float(np.median(tops)), 3) if tops else 0.0,
              "band_bottom": round(float(np.median(bots)), 3) if bots else 1.0, "background": bg,
              "summary": (f"단색 바탕({bg}) 가운데 띠에 내용 — 띠 높이 화면의 약 {round((np.median(bots) - np.median(tops)) * 100)}%, 폭 가득" if letterbox > 0.5 and tops else "화면 가득 채움")}

    # 2) 샷마다 대표 프레임 OCR → 화면 종류
    say(0.25, "샷 글자 읽기")
    langs = ocr.order_langs(a.langs.split(","), " ".join(sg.get("text", "") for sg in x.get("speech", [])))
    shots = []
    for i, s in enumerate(x.get("shots", [])):
        mid = (s["start"] + s["end"]) / 2
        f = frame_at(src, mid, tmp / f"shot{i:02d}.jpg")
        lines = ocr.read(str(f), langs)
        n_txt = len(lines)
        vt = vision_tags.classify(str(f), lines)
        kind = vt["kind"]
        shots.append({"i": i, "start": s["start"], "end": s["end"], "sec": round(s["end"] - s["start"], 2), "kind": kind, "kind_top": vt["top"],
                      "camera": (s.get("camera") or {}).get("kind"), "text_lines": n_txt})
        say(0.25 + 0.35 * (i + 1) / max(1, len(x["shots"])), f"샷 {i + 1}/{len(x['shots'])}")

    # 3) 자막: 1초마다 OCR → 편집자가 얹은 자막만 골라, 같은 글이 이어지면 한 번으로 묶는다(등장 · 사라짐 시각)
    say(0.62, "자막 읽기")
    caps, open_ = [], {}
    n = int(dur)
    caps_frames = ocr.frames(src, 0.5, 1.0, n + 1)
    for k, (t, f) in enumerate(caps_frames):
        t = min(dur - 0.3, t)
        seen = set()
        for o in ocr.read(f, langs):
            if not is_overlay(o):
                continue
            key = re.sub(r"\s+", "", o["text"])[:24]
            seen.add(key)
            if key in open_:
                open_[key]["end"] = t + 0.5
            else:
                bx, by, bw, bh = o["box"]
                band = ("위" if by < 0.33 else "가운데 위" if by < 0.45 else "가운데" if by < 0.55 else "가운데 아래" if by < 0.67 else "아래")
                open_[key] = {"start": max(0, t - 0.5), "end": t + 0.5, "band": band, "y": round(by, 3), "h": round(bh, 3), "text_example": o["text"], "style": cap_style(o), "bg": o["bg"], "fg": o["fg"]}
        for key in [k_ for k_ in open_ if k_ not in seen]:
            caps.append(open_.pop(key))
        say(0.62 + 0.2 * (k + 1) / len(caps_frames), f"자막 {k + 1}/{len(caps_frames)}초")
    caps += list(open_.values())
    caps.sort(key=lambda c: c["start"])
    style_counts = {}
    for c in caps:
        style_counts[c["style"]] = style_counts.get(c["style"], 0) + 1

    # 4) 말: 속도 · 이어 말하기 · 말투
    say(0.85, "말투")
    segs = x.get("speech", [])
    chars = sum(len(re.sub(r"\s", "", s["text"])) for s in segs)
    talk = sum(s["end"] - s["start"] for s in segs) or 1
    gaps = [round(b["start"] - a_["end"], 2) for a_, b in zip(segs, segs[1:])]
    voice = {"chars_per_sec": round(chars / talk, 1), "speech_ratio": round(talk / dur, 2), "median_gap": round(float(np.median(gaps)), 2) if gaps else 0,
             "continuous": bool(gaps) and float(np.median(gaps)) < 0.35, **tone_of([s["text"] for s in segs])}
    # 목소리 특징(높이 · 억양 폭 · 말끝 · 세기 변화) — voice_match.py 가 후보 목소리를 이 값에 맞춘다(복제 아님)
    if (d / "vocals.m4a").exists() and segs:
        import voice_profile
        voice["prosody"] = voice_profile.profile(d / "vocals.m4a", segs)

    # 5) 박자표: 샷마다 겹치는 대사 · 자막 → 역할(추상)
    beats = []
    for k, s in enumerate(shots):
        said = [g["text"] for g in segs if g["start"] < s["end"] and g["end"] > s["start"]]
        cs = [c for c in caps if c["start"] < s["end"] and c["end"] > s["start"]]
        prev_said = [g for g in segs if g["end"] <= s["start"] + 0.4]
        kd = s["kind"]
        if k == 0:
            role = "훅 — 첫 장면이 반응 짤이면 '놀라운 한 줄 + 짤'" if kd == "짤" else f"훅 — 첫 화면({kd})으로 주제를 한 번에"
        elif k == len(shots) - 1:
            role = "맺음 — 반응 · 한마디로 끝냄"
        elif kd == "짤" and s["sec"] <= 4.5:
            role = "펀치 — 직전 말 · 장면에 반응 짤"
        elif any(re.search(r"근데|하지만|다만|아쉬|\bbut\b|\bhowever\b", t, re.I) for t in said):
            role = "반전 · 한계 — 단점 · 뒤집기"
        else:
            role = ROLE_BY_KIND.get(kd, "보여 주기")
        beats.append({"t": [s["start"], s["end"]], "sec": s["sec"], "visual": s["kind"], "role": role,
                      "captions": [{"style": c["style"], "example": c["text_example"]} for c in cs][:3],
                      "speech_example": " / ".join(said)[:120], "after_line": bool(prev_said) and "짤" in s["kind"]})

    avg_sec = sum(s["sec"] for s in shots) / max(1, len(shots))
    static = sum(1 for s in shots if s["camera"] == "고정") / max(1, len(shots))
    # 움직임: 카메라가 거의 고정 · 컷이 느긋하면 담담(minimal), 컷이 빠르거나 카메라가 많이 움직이면 역동(dynamic)
    motion = "minimal" if static >= 0.8 and avg_sec >= 2.5 else "dynamic" if avg_sec < 1.3 or static < 0.5 else "moderate"
    direction = {"background": "solid" if layout["letterbox_ratio"] > 0.5 else "footage", "color_bg": layout["background"],
                 "layout": "band" if layout["letterbox_ratio"] > 0.5 else "full",
                 "captions": ("bracket-box" if any(c["style"].startswith("괄호") for c in caps) else "box") if caps else "none", "motion": motion, "transition": "cuts",
                 "caption_bg": (max(caps, key=lambda c: style_counts[c["style"]])["bg"] if caps else "#ffffff"),
                 "caption_fg": (max(caps, key=lambda c: style_counts[c["style"]])["fg"] if caps else "#000000"),
                 "reference": a.id, "note": "레퍼런스 스타일 카드(ref_style.py)에서 — 무작위로 고르지 않음"}
    avg = round(sum(s["sec"] for s in shots) / max(1, len(shots)), 2)
    snd = x.get("sound") or {}
    beats_t = snd.get("beats") or []
    cuts_t = [s["start"] for s in shots[1:]]
    on_beat = round(sum(1 for c in cuts_t if beats_t and min(abs(c - b) for b in beats_t) <= 0.08) / len(cuts_t), 2) if cuts_t and beats_t else None
    lead = "말" if voice["speech_ratio"] >= 0.5 else "음악 · 화면" if voice["speech_ratio"] < 0.2 else "말 + 음악"
    kinds_count = {}
    for s_ in shots:
        kinds_count[s_["kind"]] = kinds_count.get(s_["kind"], 0) + s_["sec"]
    main_kinds = [k for k, _ in sorted(kinds_count.items(), key=lambda x: -x[1])[:2]]
    genre = f"{lead} 주도 · {' + '.join(main_kinds)} 위주 · 컷 평균 {round(avg_sec, 1)}초 · 움직임 {motion}" + (f" · 컷이 음악 박자에 맞음 {int(on_beat * 100)}%" if on_beat is not None else "")
    card = {"id": a.id, "url": x.get("url"), "duration": dur, "layout": layout,
            "genre": genre,
            "rhythm": {"shots": len(shots), "avg_shot_sec": avg, "bpm": snd.get("bpm"), "cut_on_beat": on_beat, "lead": lead, "first_shot_sec": shots[0]["sec"] if shots else None,
                       "kinds": {k: sum(1 for s in shots if s["kind"] == k) for k in sorted(set(s["kind"] for s in shots))},
                       "camera_static_ratio": round(sum(1 for s in shots if s["camera"] == "고정") / max(1, len(shots)), 2)},
            "captions": {"count": len(caps), "styles": style_counts, "bands": sorted(set(c["band"] for c in caps if c.get("band"))), "items": caps},
            "voice": voice, "beats": beats, "direction": direction, "sheets": sheets}
    old = out / "style.json"
    if old.exists():   # 채널 카드 연결(ref_channel.py 가 단 것)은 다시 만들어도 남긴다
        ch = json.loads(old.read_text(encoding="utf-8")).get("channel")
        if ch:
            card["channel"] = ch
    old.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [f"# 레퍼런스 스타일 카드 — {a.id}", f"{x.get('url', '')} · {dur:.0f}초", "",
          f"**형식**: {genre}", "",
          "## 옮기는 법", "내용은 **사용자의 주제**로 새로 쓴다. 아래의 형식 · 박자 · 말투만 따른다. 원본 대사 · 자막은 말투 예시일 뿐 그대로 쓰지 않는다.", "",
          "## 화면", f"- {layout['summary']}", f"- 컷 {len(shots)}개 · 평균 {avg}초 · 첫 컷 {card['rhythm']['first_shot_sec']}초 · 카메라 고정 {int(card['rhythm']['camera_static_ratio'] * 100)}%",
          f"- 화면 종류: " + ", ".join(f"{k} {v}" for k, v in card["rhythm"]["kinds"].items()), "",
          "## 자막", f"- {len(caps)}번 · 위치 {', '.join(card['captions']['bands'])}", *[f"- {k}: {v}번" for k, v in style_counts.items()],
          "- 자막 예시: " + (" · ".join(list(dict.fromkeys(c["text_example"] for c in caps if len(c["text_example"]) > 2))[:8]) or "없음"), "",
          *(["## 말", f"- 초당 {voice['chars_per_sec']}자 · 말 비율 {int(voice['speech_ratio'] * 100)}% · 문장 사이 쉼 {voice['median_gap']}초 → {'이어 말함(컷이 바뀌어도 말은 계속)' if voice['continuous'] else '문장마다 끊음'}",
             "- 문장 끝: " + (", ".join(f"~{k} {v}" for k, v in list(voice["endings"].items())[:8]) or "-"),
             "- 이음말: " + (", ".join(f"{k} {v}" for k, v in list(voice["connectives"].items())[:8]) or "-"),
             "- 목소리: " + (" · ".join(f"{k} {v}" for k, v in (voice.get("prosody") or {}).items() if k in ("f0_median", "range_st", "end_drop_st", "energy_sd_db")) or "-") + " (voice_match.py 가 맞춘다)",
             "- 말투 · 구성은 한 편 통계라 표본이 작다 — 채널 카드(ref_channel.py, 여러 편)가 있으면 그쪽이 기준", ""]
            if voice["speech_ratio"] >= 0.2 else
            ["## 말 · 소리", f"- 말이 거의 없다(말 비율 {int(voice['speech_ratio'] * 100)}%) — 음악 · 화면 · 자막이 끌고 간다. 나레이션을 넣지 말거나 아주 짧게",
             f"- 음악 {snd.get('bpm') or '?'} BPM · 컷이 박자에 맞음 {int((on_beat or 0) * 100)}% — 화면 전환을 음악 박에 맞춘다", ""]),
          "## 박자표 (내 주제의 장면을 이 순서 · 역할로)", *[f"{i + 1}. {b['t'][0]:.1f}~{b['t'][1]:.1f}초 · {b['visual']} · **{b['role']}**" + (f" · 자막 {b['captions'][0]['style']}" if b['captions'] else "") for i, b in enumerate(beats)], "",
          "## 디자인 방향(direct.py 가 그대로 쓴다)", "```json", json.dumps(direction, ensure_ascii=False), "```", "",
          "밀착 시트: " + ", ".join(sheets) + " — 직접 보고 박자 역할이 틀렸으면 이 파일의 박자표를 고쳐 쓴다."]
    (out / "style.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    say(1.0, "끝")
    print(json.dumps({"ok": True, "card": str((out / "style.json").relative_to(ROOT)), "beats": len(beats), "captions": len(caps)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
