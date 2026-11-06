#!/usr/bin/env python3
"""생성 영상 클립(Dreamina 등 — 사용자가 밖에서 만들어 올린 AI 영상)을 쇼츠에 넣기.

콘티 재료(장면의 materials):
  {"id": "walk", "type": "video", "gen": "dreamina",
   "prompt": "…영어 프롬프트…", "cast": ["mina"], "camera": "slow dolly in", "gen_sec": 5,
   "in": 0.4, "out": 4.6,            # 클립에서 쓸 구간(초) — 생략하면 전체
   "dialogue": true,                 # 클립 속 대사를 살린다 → 그 장면의 목소리 · 자막이 된다(나레이션 대신)
   "fit": "cover",                   # cover(기본 · 화면 비율로 가운데 자르기) | contain(그대로 · 빈 곳은 배경)
   "end": "slow"}                    # 장면보다 짧을 때: slow(0.8배까지 늦추고 남으면 멈춤 · 기본) | freeze(마지막 프레임) | loop
콘티 최상위(선택) "cast": [{"name": "mina", "look": "20대 여성, 짧은 단발, 파란 티셔츠 …", "ref": "public/uploads/<id>/mina.png"}]
  → 장면마다 같은 인물이 나오도록 프롬프트에 같은 외모 설명 · 기준 이미지를 붙인다.

  python3 scripts/genclip.py prompts storyboards/<id>.json      # 생성할 클립 목록(프롬프트 · 길이 · 비율 · 기준 이미지) → compositions/<id>/gen/prompts.md
  python3 scripts/genclip.py status storyboards/<id>.json       # 올라온 클립 / 아직 없는 클립

올리는 곳: 영상 편집기에 올리거나 public/uploads/<id>/ 에 이름에 재료 id 가 든 파일(예: walk.mp4).
생성 클립이 든 영상은 업로드 때 'AI 생성 · 합성 콘텐츠' 표시가 자동으로 켜진다(upload_youtube.py).
워터마크는 지우지 않는다 — 서비스 약관상 워터마크 없는 내보내기(유료 플랜)를 쓴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def gen_materials(sb: dict) -> list[tuple[int, dict]]:
    """(장면 번호 0부터, 재료) — 생성 클립 재료만"""
    out = []
    for i, sc in enumerate(sb.get("scenes") or []):
        for k, m in enumerate(sc.get("materials") or []):
            if isinstance(m, dict) and m.get("type") == "video" and m.get("gen"):
                out.append((i, {"id": m.get("id") or f"m{k + 1}", **m}))
    return out


def has_generated(sb: dict) -> bool:
    return bool(gen_materials(sb)) or any(isinstance(m, dict) and m.get("gen") for sc in sb.get("scenes") or [] for m in sc.get("materials") or [])


def clip_file(sid: str, m: dict) -> Path | None:
    from craft.materials import find_upload
    return find_upload(sid, {**m, "type": "video"})


def probe(f: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(f)],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        d = {}
    v = next((s for s in d.get("streams") or [] if s.get("codec_type") == "video"), {})
    return {"dur": float((d.get("format") or {}).get("duration") or 0), "w": v.get("width") or 0, "h": v.get("height") or 0,
            "audio": any(s.get("codec_type") == "audio" for s in d.get("streams") or [])}


def span(m: dict, dur: float) -> tuple[float, float]:
    a = max(0.0, float(m.get("in") or 0))
    b = float(m["out"]) if m.get("out") is not None else dur
    b = min(b, dur) if dur else b
    if b <= a:
        raise RuntimeError(f"{m.get('id')}: in({a}) 이 out({b}) 보다 뒤입니다")
    return a, b


def dialogue_scene(sb: dict, i: int) -> dict | None:
    """그 장면에서 대사를 살릴 생성 클립 재료(첫 번째)"""
    sc = (sb.get("scenes") or [])[i]
    for k, m in enumerate(sc.get("materials") or []):
        if isinstance(m, dict) and m.get("type") == "video" and m.get("dialogue"):
            return {"id": m.get("id") or f"m{k + 1}", **m}
    return None


def audio_pcm(f: Path, a: float, b: float, sr: int) -> bytes:
    """클립 소리(구간) → 모노 16비트 PCM. 소리가 없으면 무음"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(f), "-vn", "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    pcm = r.stdout if r.returncode == 0 else b""
    want = int(round((b - a) * sr)) * 2
    return (pcm + b"\x00\x00" * max(0, (want - len(pcm)) // 2))[:want]


def words(f: Path, a: float, b: float, work: Path, prompt: str | None = None) -> list[dict]:
    """클립 대사 받아쓰기 → [{text, startMs, endMs}] (구간 시작 기준). 결과는 work 에 캐시"""
    work.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{f.stat().st_size}:{f.stat().st_mtime_ns}:{a}:{b}".encode()).hexdigest()[:12]
    cache = work / f"{f.stem}.{key}.words.json"
    if cache.exists():
        return json.loads(cache.read_text("utf-8"))
    wav = work / f"{f.stem}.{key}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(f), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    out = []
    try:
        from shorts_xray import speech
        for s in speech(wav, "base", prompt=prompt):
            for w in s.get("words") or []:
                if w.get("w"):
                    out.append({"text": w["w"], "startMs": int(w["s"] * 1000), "endMs": int(w["e"] * 1000)})
    except Exception as e:  # noqa: BLE001  (받아쓰기 모델 없음 등) — 자막 없이 소리만
        print(f"[생성 클립] {f.name} 받아쓰기 실패 — 자막 없이 진행: {e}")
    cache.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    wav.unlink(missing_ok=True)
    return out


def prompts(sb: dict, model: str | None = None, n_variants: int = 3) -> str:
    """사용자가 생성 서비스에 그대로 붙여 넣을 클립 목록 — 모델 문법에 맞춘 프롬프트(카드: genmodels/cards) 샷마다 여러 안.
    샷 설계(레퍼런스에서 잰 카메라 · 구도 · 색 · 빛, 편집 여유, 자막 자리, 이어 붙이기)는 scripts/shotplan.py"""
    import shotplan
    lk = shotplan.look(sb)
    specs = shotplan.specs(sb)
    cast = {c.get("name"): c for c in sb.get("cast") or [] if isinstance(c, dict)}
    rows = [f"# 생성할 클립 — {sb.get('title') or sb['id']}", "",
            f"- 파일 이름에 클립 id 를 넣어 올린다(예: `{specs[0]['id'] if specs else 'walk'}.mp4`) — 영상 편집기의 올리기 또는 `public/uploads/{sb['id']}/`",
            "- 워터마크 없는 내보내기 · 가장 높은 해상도. 올린 뒤 `python3 scripts/shotplan.py check storyboards/" + sb["id"] + ".json` 이 설계와 맞는지 보고 고칠 문구를 준다", ""]
    if lk:
        rows += ["## 레퍼런스에서 잰 값(프롬프트에 반영됨)", "",
                 f"- 레퍼런스 {', '.join(lk['refs'])} · 샷 평균 {lk['shot_sec']}초({lk['pace']}) · 카메라 " + ", ".join(f"{k} {v}" for k, v in list(lk['camera_mix'].items())[:3]),
                 f"- 색 {lk['color']} · {lk['key']} · {lk['temperature']}" + (f" · 음악 {lk['bpm']:.0f} BPM" if lk.get("bpm") else ""), ""]
    if cast:
        rows += ["## 등장인물 — 모든 클립에 같은 문구 · 같은 기준 그림", ""]
        for nm, c in cast.items():
            rows.append(f"- **{nm}**: {c.get('look') or ''}" + (f" — 기준 그림 `{c['ref']}`" if c.get("ref") else ""))
        rows.append("")
    for sp in specs:
        mdl = model or sp.get("gen") or "seedance"
        sc = sb["scenes"][sp["scene"]]
        rows += [f"## {sp['scene'] + 1}장면 · `{sp['id']}` · 쓸 길이 {sp['duration']:g}초(앞뒤 여유 포함 {sp['request_sec']:g}초)", ""]
        if sp.get("first_frame"):
            rows.append(f"- 첫 프레임: `{sp['first_frame']}` (앞 클립 끝에서 이어 시작)")
        if (sc.get("narration") or "").strip():
            rows.append(f"- 나레이션(화면 밖 목소리, 클립에는 넣지 않음): {sc['narration'].strip()[:120]}")
        rows.append("")
        for k in range(max(1, n_variants)):
            r = shotplan.compile_prompt(sp, mdl, k, lk)
            if r.get("error"):
                rows += [f"> ⚠ {r['error']}", ""]
                break
            st = r["settings"]
            rows += [f"### 안 {k + 1} — {r['variant']} · {r.get('title') or r['model']}",
                     f"설정: {st['duration']:g}초 · {st['aspect']}" + (" · 소리 켜기" if st.get("audio") and sp.get("dialogue") else ""), "",
                     "```", r["prompt"], "```"]
            if r.get("negative"):
                rows += ["부정 프롬프트 칸:", "```", r["negative"], "```"]
            if r.get("references"):
                rows.append("올릴 참조: " + ", ".join(f"`{x}`" for x in r["references"]))
            for nt in r.get("notes") or []:
                rows.append(f"- ⚠ {nt}")
            rows.append("")
    return "\n".join(rows)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("prompts", "status"):
        s = sub.add_parser(n); s.add_argument("storyboard")
        if n == "prompts":
            s.add_argument("--model", help="seedance(dreamina) · kling · veo · omni · hailuo · runway · wan — 생략하면 재료의 gen")
            s.add_argument("--variants", type=int, default=3)
    a = ap.parse_args()
    sp = Path(a.storyboard)
    sb = json.loads((sp if sp.is_absolute() else ROOT / sp).read_text("utf-8"))
    gm = gen_materials(sb)
    if not gm:
        print("생성 클립 재료가 없습니다(type: video + gen)")
        return 1
    if a.cmd == "prompts":
        out = ROOT / "compositions" / sb["id"] / "gen" / "prompts.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompts(sb, a.model, a.variants), "utf-8")
        print(f"{len(gm)}개 클립 → {out.relative_to(ROOT)}")
        return 0
    miss = 0
    for i, m in gm:
        f = clip_file(sb["id"], m)
        if f:
            p = probe(f)
            print(f"  ✓ {i + 1}장면 {m['id']}: {f.relative_to(ROOT)} · {p['dur']:.1f}초 · {p['w']}×{p['h']}" + (" · 소리 있음" if p["audio"] else ""))
        else:
            miss += 1
            print(f"  · {i + 1}장면 {m['id']}: 아직 없음")
    print(f"올라온 클립 {len(gm) - miss}/{len(gm)}")
    return 0 if not miss else 10


if __name__ == "__main__":
    sys.exit(main())
