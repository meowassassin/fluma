#!/usr/bin/env python3
"""파이프라인 5단계 — 커스터마이징(fluma craft): 이펙트 · 편집 · 자막 · 장면 길이 + 나레이션(공급자 TTS — typecast 등).
4단계에서 샷 검토를 통과한 클립을 기존 Craft 편집 엔진의 콘티(data/storyboards/<id>.json)로 옮긴다.
그다음은 이미 있는 도구를 그대로 쓴다: 나레이션 음성(engine/voice/assemble_audio.py) → 초안 렌더(engine/render.py --draft)
→ 값으로 고치기(engine/story/knob.py) · 장면 다듬기(refine 스킬). 음악은 보류 — 자리만 둔다(music.use=false · hold).

  python3 engine/gen/assemble.py storyboard <plan id>      # 통과 클립 → 콘티(샷 = 장면, 생성 클립의 trim_in~+final_sec, 클립 소리 끔)
  python3 engine/gen/assemble.py build <plan id> [--no-voice]  # 콘티 → 나레이션 음성 → 초안 렌더
샷 계획의 칸을 고친 뒤(final_sec · trim_in · narration) storyboard 를 다시 부르면 콘티가 다시 만들어진다 — 콘티에서 손으로 고친 값(direction · subs 등)은 남긴다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).parent))
from result import fail, ok  # noqa: E402
import plan as planmod  # noqa: E402
import video as videomod  # noqa: E402

ROLE = {"hook": "hook", "build": "setup", "turn": "reveal", "payoff": "verdict", "cta": "cta"}
KEEP = ("direction", "subs", "voice", "grammar", "refine", "credits", "hashtags", "caption")   # 편집 단계에서 사람이 만진 칸은 다시 만들 때 남긴다


def block(out: str) -> dict:
    """스크립트 출력 끝의 결과 블록(FLUMA_…) → dict (produce.py 와 같은 규칙)"""
    import re
    lines = (out or "").strip().split("\n")
    at = max((i for i, ln in enumerate(lines) if ln.startswith("FLUMA_")), default=-1)
    b: dict = {"head": lines[at]} if at >= 0 else {}
    for ln in lines[at + 1:] if at >= 0 else []:
        m = re.match(r"^([a-z_]+)=(.*)$", ln)
        if m:
            b.setdefault(m.group(1), []).append(m.group(2))
    return b


def clip_len(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def split_narration(text: str, n: int) -> list[str]:
    """나레이션 → 샷별. 정식 경계는 ' / '. 개수가 안 맞으면 공백 없는 '/' · 줄바꿈 경계도 받아 본다(그래도 안 맞으면 부른 쪽이 멈춘다).
    '/' 를 늘 경계로 보지 않는 이유: 대사 안의 '24/7' · '1/4' 같은 글자를 자르지 않으려고"""
    import re
    text = text.strip()
    if not text:
        return []
    parts = [x.strip() for x in text.split(" / ")]
    if len(parts) != n:
        alt = [x.strip() for x in re.split(r"\s*/\s*|\n+", text) if x.strip()]
        if len(alt) == n:
            return alt
    return parts


def to_storyboard(pid: str) -> Path:
    import hashlib
    _, sb = planmod.load(pid)
    st = {r["shot"]: r for r in videomod.status(pid)}
    missing = [n for n, r in st.items() if not r["approved"]]
    if missing:
        fail("assemble", stage="assemble", error=f"샷 검토를 통과하지 않은 샷: {missing} — 4단계(video.py approve)부터")
    parts = split_narration(sb.get("narration") or "", len(sb["shots"]))
    if parts and len(parts) != len(sb["shots"]):
        fail("assemble", stage="assemble", error=f"나레이션 칸 {len(parts)}개 ≠ 샷 {len(sb['shots'])}개 — narration 의 ' / ' 를 샷 수에 맞춘다")
    # 이미 실측된 음성 타이밍(timing.json)이 있고 대본 해시가 같으면 그 장면 길이를 유지해 싱크 어긋남 방지
    timing_p = ROOT / "data" / "public" / "audio" / f"{pid}.timing.json"
    timing_rows = json.loads(timing_p.read_text("utf-8")) if timing_p.exists() else []
    scenes = []
    for i, s in enumerate(sb["shots"]):
        clip = Path(st[s["n"]]["clip"])
        dur = clip_len(clip)
        a = float(s.get("trim_in") or 0)
        narr = parts[i] if parts else ""
        if len(narr) > 60:
            fail("assemble", stage="assemble", error=f"샷 {s['n']}: 나레이션 {len(narr)}자 > 60자(편집 엔진 장면 한도) — 줄이거나 샷을 나눈다")
        th = hashlib.sha1(narr.strip().encode("utf-8")).hexdigest()[:8] if narr else ""
        want_sec = float(s["final_sec"])
        if i < len(timing_rows) and timing_rows[i].get("text_hash") == th:
            t_sec = round(float(timing_rows[i]["end"]) - float(timing_rows[i]["start"]), 2)
            if t_sec >= 2.0:
                want_sec = t_sec
        b = a + want_sec
        if (dur - a) < 2 - 1e-6 and want_sec < 2 - 1e-6:
            fail("assemble", stage="assemble", error=f"샷 {s['n']}: 쓸 구간 {b - a:.2f}초 < 2초(클립 {dur:.2f}초, trim_in {a}) — trim_in · final_sec 를 고친다")
        scenes.append({"role": ROLE[s["purpose"]], "sec": round(want_sec, 2), "caption": narr, "narration": narr, "beat": s.get("beat") or "",
                       "visual": {"kind": "footage"},
                       "materials": [{"id": f"s{s['n']:02d}clip", "type": "video", "src": str(clip.relative_to(ROOT)), "in": round(a, 2), "out": round(b, 2),
                                      "audio": True, "volume": 0.28, "full_frame": True, "what": f"생성 샷 {s['n']} — {s.get('beat') or s['action']}"}]})
    total = sum(x["sec"] for x in scenes)
    out = ROOT / "data" / "storyboards" / f"{pid}.json"
    old = json.loads(out.read_text("utf-8")) if out.exists() else {}
    title = (sb.get("title") or sb.get("logline") or sb["topic"])[:40]
    story = {"id": pid, "version": 1, "engine": "craft", "format": sb.get("format") or "concept", "aspect": sb["aspect"],
             "duration_sec": max(5, min(60, round(total))), "title": title, "topic": sb["topic"], "cta": (sb.get("cta") or "")[:20],
             "kind": "story", "language": "ko",
             "music": {"use": False, "hold": True, "why": "음악 기능 보류(사용자 결정 2026-11-12) — 자리만"},
             "meta": {"source": "shotplan", "shotplan": f"data/shotplans/{pid}.json", "pipeline": "fluma-shortform v2"},
             "scenes": scenes}
    if parts:
        story["script"] = " / ".join(parts)
    for k in KEEP:
        if k in old:
            story[k] = old[k]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(story, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return out


def _needs_craft_render(story: dict) -> bool:
    """콘티에 Craft 전용 다듬기(refine) · 특수 자막(subs) · 영상 외 재료가 있으면 전체 Craft 렌더를 탄다."""
    if story.get("refine") or story.get("subs"):
        return True
    for sc in story.get("scenes") or []:
        if (sc.get("visual") or {}).get("kind") != "footage" or sc.get("passes"):
            return True
        mats = sc.get("materials") or []
        if len(mats) != 1 or mats[0].get("type") != "video":
            return True
    return False


def _has_audio_stream(p: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, timeout=15)
    return bool(r.stdout.strip())


def _ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _write_draft_ass(ass_path: Path, pid: str, story: dict, W: int, H: int, total_dur: float) -> bool:
    """상단 고정 제목과 하단 구절 자막(captions.json 또는 장면 caption)을 ASS 자막 파일로 쓴다."""
    import editor_bridge as eb
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Sub,Pretendard,68,&H00FFFFFF,&H0000FFFF,&H55000000,&H99000000,-1,0,0,0,100,100,0,0,3,18,0,2,60,60,360,1",
        "Style: TopTitle,Pretendard,58,&H0000FFFF,&H00FFFFFF,&H55000000,&H99000000,-1,0,0,0,100,100,0,0,3,18,0,8,60,60,170,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    has_events = False
    title = str(story.get("title") or "").strip().replace("\n", "\\N")
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0.0)},{_ass_time(total_dur)},TopTitle,,0,0,0,,{title}")
        has_events = True

    cap_file = ROOT / "data" / "public" / "audio" / f"{pid}.captions.json"
    phrases = []
    if cap_file.is_file():
        try:
            words = json.loads(cap_file.read_text("utf-8"))
            phrases = eb.group_words_into_phrases(words)
        except Exception:
            phrases = []
    if phrases:
        for p in phrases:
            txt = str(p.get("text") or "").strip().replace("\n", "\\N")
            if txt:
                lines.append(f"Dialogue: 2,{_ass_time(p['startSec'])},{_ass_time(p['endSec'])},Sub,,0,0,0,,{txt}")
                has_events = True
    else:
        t_acc = 0.0
        for sc in story.get("scenes") or []:
            dur = float(sc.get("sec") or 3.0)
            txt = str(sc.get("caption") or sc.get("narration") or "").strip().replace("\n", "\\N")
            if txt:
                lines.append(f"Dialogue: 2,{_ass_time(t_acc)},{_ass_time(t_acc + dur)},Sub,,0,0,0,,{txt}")
                has_events = True
            t_acc += dur
    if not has_events:
        return False
    ass_path.write_text("\n".join(lines) + "\n", "utf-8")
    return True


def _fast_draft(pid: str, story: dict) -> Path | None:
    """통과 클립(원음 효과음 포함) + 나레이션 음성 + 상단 제목/하단 자막을 ffmpeg 고속 합치기로 초안 MP4 로 만든다."""
    import tempfile
    out_dir = ROOT / "data" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"{pid}-craft-draft.mp4"
    W, H = (1080, 1920) if story.get("aspect", "9:16") == "9:16" else ((1920, 1080) if story.get("aspect") == "16:9" else (1080, 1080))
    scenes = story.get("scenes") or []
    if not scenes:
        return None
    with tempfile.TemporaryDirectory(prefix="fluma_fast_") as td:
        td_p = Path(td)
        seg_files: list[Path] = []
        total_dur = 0.0
        for idx, sc in enumerate(scenes):
            mat = (sc.get("materials") or [{}])[0]
            src = ROOT / str(mat.get("src") or "")
            if not src.is_file():
                return None
            t_in = float(mat.get("in") or 0.0)
            dur = max(0.5, float(sc.get("sec") or (float(mat.get("out") or 3.0) - t_in)))
            total_dur += dur
            short = max(0.0, dur - (clip_len(src) - t_in))      # 클립이 장면보다 짧으면 마지막 프레임을 늘려 길이를 맞춘다(편집기와 같은 길이)
            pad = f",tpad=stop_mode=clone:stop_duration={short + 0.1:.3f}" if short > 0.01 else ""
            seg = td_p / f"seg_{idx:02d}.mp4"
            use_clip_audio = mat.get("audio", True) is not False and _has_audio_stream(src)
            vol = float(mat.get("volume", 0.28))
            if use_clip_audio:
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{t_in:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30{pad},format=yuv420p",
                    "-af", f"volume={vol:.2f},apad=whole_dur={dur:.3f},aresample=24000,pan=mono|c0=c0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-ar", "24000", "-ac", "1", str(seg),
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-ss", f"{t_in:.3f}", "-i", str(src),
                    "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{dur:.3f}",
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30{pad},format=yuv420p",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-ar", "24000", "-ac", "1", str(seg),
                ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0 or not seg.is_file():
                return None
            seg_files.append(seg)
        concat_txt = td_p / "concat.txt"
        concat_txt.write_text("".join(f"file '{s.as_posix()}'\n" for s in seg_files), "utf-8")
        joined_mp4 = td_p / "joined.mp4"
        r0 = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(joined_mp4)],
                            capture_output=True, text=True, timeout=120)
        if r0.returncode != 0 or not joined_mp4.is_file():
            return None

        ass_file = td_p / "subs.ass"
        has_ass = _write_draft_ass(ass_file, pid, story, W, H, total_dur)
        fonts_dir = (ROOT / "engine" / "assets" / "fonts").as_posix()
        vf_args = ["-vf", f"ass={ass_file.as_posix()}:fontsdir={fonts_dir}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22"] if has_ass else ["-c:v", "copy"]

        voice_wav = ROOT / "data" / "public" / "audio" / f"{pid}.wav"
        if not voice_wav.is_file():
            voice_wav = ROOT / "data" / "public" / "audio" / f"{pid}.voice.wav"
        if voice_wav.is_file():
            cmd = [
                "ffmpeg", "-y", "-i", str(joined_mp4), "-i", str(voice_wav),
                *vf_args,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0:weights='1 1.4'[aout]",
                "-map", "0:v:0", "-map", "[aout]",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(out_mp4),
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", str(joined_mp4),
                *vf_args,
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_mp4),
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and out_mp4.is_file() and out_mp4.stat().st_size > 1000:
            return out_mp4
    return None


def build(pid: str, voice: bool, full_craft: bool = False) -> dict:
    sbp = to_storyboard(pid)
    rel = str(sbp.relative_to(ROOT))
    story = json.loads(sbp.read_text("utf-8"))
    py = sys.executable
    if voice and story.get("script"):
        r = subprocess.run([py, "engine/voice/assemble_audio.py", rel], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        if r.returncode:
            fail("assemble", stage="voice", error=(r.stderr or r.stdout).strip()[-400:])
        # 음성 단계가 장면 길이(sec)를 말 길이에 맞춰 콘티에 다시 쓴다 — 다시 읽지 않으면 초안은 옛 길이로 붙고
        # 나레이션이 잘리며(-shortest), 새 길이로 만든 편집기 타임라인과 어긋난다(2026-11-14 USB 포코: 14.5초 vs 18초)
        story = json.loads(sbp.read_text("utf-8"))

    # VEditor(웹 편집기) 타임라인 project.json 즉시 생성/갱신
    subprocess.run([py, "engine/gen/editor_bridge.py", "convert", pid], cwd=ROOT, capture_output=True, text=True, timeout=120)

    if not full_craft and not _needs_craft_render(story):
        fast_out = _fast_draft(pid, story)
        if fast_out:
            return {"storyboard": rel, "draft": str(fast_out.relative_to(ROOT))}

    r = subprocess.run([py, "engine/render.py", rel, "--draft"], cwd=ROOT, capture_output=True, text=True, timeout=3600)
    b = block(r.stdout)
    if r.returncode or b.get("head") != "FLUMA_RESULT":
        fail("assemble", stage="render", error=(b.get("error") or [(r.stderr or r.stdout).strip()[-400:]])[0])
    return {"storyboard": rel, "draft": b["file"][0]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s1 = sp.add_parser("storyboard"); s1.add_argument("pid")
    s2 = sp.add_parser("build"); s2.add_argument("pid"); s2.add_argument("--no-voice", action="store_true"); s2.add_argument("--full-craft", action="store_true")
    a = ap.parse_args()
    if a.cmd == "storyboard":
        ok("assemble", storyboard=str(to_storyboard(a.pid).relative_to(ROOT)), next="assemble.py build — 나레이션 음성 · 초안 렌더"); return 0
    r = build(a.pid, not a.no_voice, full_craft=a.full_craft)
    mock = videomod.mock_shots(a.pid)
    if mock:
        ok("assemble", storyboard=r["storyboard"], file=r["draft"], mock=",".join(map(str, mock)),
           warning=f"샷 {mock} 은(는) 시험용 mock 클립(키 프레임을 늘린 정지 화면)이다 — 흐름 확인용일 뿐 실제 영상이 아니다. 사용자에게 이 사실을 먼저 알린다",
           next="실제 생성 경로(video.py run)로 해당 샷을 다시 만든 뒤 재조립 — mock 이 남아 있으면 최종 렌더 · 업로드는 막힌다")
        return 0
    ok("assemble", storyboard=r["storyboard"], file=r["draft"],
       next="초안을 보여 주고 웹 편집기(VEditor) 또는 값으로 고치기(knob.py) · 장면 다듬기(refine) — 끝나면 6단계 최종 렌더 · 업로드")
    return 0


if __name__ == "__main__":
    sys.exit(main())
