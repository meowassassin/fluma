#!/usr/bin/env python3
"""
마무리 단계 (엔진 무관): 무음 영상 + 음성(public/audio/<id>.wav) + 단어 자막 → 최종 MP4.

- 단어 자막은 템플릿 meta.json 의 captions 가 "finish" 일 때만 ASS(libass)로 입힌다.
  지금 말하는 단어만 강조색 + 살짝 크게 (TikTok 식). 페이지는 장면 경계에서 끊고, combine_ms 안의 단어를 묶는다.
- 글꼴은 public/fonts 의 OTF (libass 는 woff2 를 못 읽는다).

  python3 scripts/finish.py <무음.mp4> storyboards/<id>.json <출력.mp4> [--captions]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engines import PUBLIC, ROOT, look_tokens  # noqa: E402
from character_overlay import overlay_graph, resolve  # noqa: E402

FONTS = PUBLIC / "fonts"


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ts(ms: float) -> str:
    cs = int(round(ms / 10))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def pages(captions: list, combine_ms: int) -> list[list[dict]]:
    """createTikTokStyleCaptions 와 같은 규칙: combine_ms 안의 단어를 한 페이지로, 장면이 바뀌면 끊는다."""
    out, cur = [], []
    for c in captions:
        if cur and (c.get("scene") != cur[0].get("scene") or c["startMs"] - cur[0]["startMs"] >= combine_ms):
            out.append(cur); cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return out


def build_ass(captions: list, tokens: dict, width: int, height: int) -> str:
    cap = tokens.get("captions", {}) or {}
    scale = width / 1080
    size = int(cap.get("size", 76) * scale)
    y_top = int(cap.get("y", 1330) * height / 1920)
    margin_v = max(0, height - (y_top + int(size * 1.35)))
    color = cap.get("color") or tokens["color"].get("caption") or "#FFFFFF"
    hl = cap.get("highlight") or tokens["color"]["accent"]
    stroke = max(2, int(cap.get("stroke", 16) * scale * 0.55))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,Pretendard Black,{size},{ass_color(color)},{ass_color(color)},&H1A000000,&H00000000,0,0,0,0,100,100,-1,0,1,{stroke},0,2,{int(60*scale)},{int(60*scale)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    combine = int(cap.get("combineMs", 900))
    pg = pages(captions, combine)
    for pi, p in enumerate(pg):
        nxt = pg[pi + 1][0]["startMs"] if pi + 1 < len(pg) else None
        page_end = min(nxt, p[-1]["endMs"] + 400) if nxt is not None else p[-1]["endMs"] + 400
        # 단어마다 한 줄: 그 시간 동안 그 단어만 강조
        for wi, w in enumerate(p):
            start = w["startMs"] if wi > 0 else p[0]["startMs"]
            end = p[wi + 1]["startMs"] if wi + 1 < len(p) else page_end
            if end <= start:
                continue
            parts = []
            for wj, x in enumerate(p):
                t = x["text"].strip().replace("{", "(").replace("}", ")")
                if wj == wi:
                    parts.append(f"{{\\c{ass_color(hl)}\\fscx108\\fscy108}}{t}{{\\r}}")
                else:
                    parts.append(t)
            pop = "{\\fad(60,0)}" if wi == 0 else ""
            # 굵은 외곽선이 띄어쓰기를 먹으므로 고정폭 공백(\\h)을 하나 더 둔다
            sep = " \\h" if float(stroke) >= 6 else " "
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Word,,0,0,0,,{pop}{sep.join(parts)}")
    return head + "\n".join(lines) + "\n"


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], text=True, capture_output=True)
    return float(r.stdout.strip() or 0)


def fpath(p) -> str:
    """ffmpeg 필터 안의 경로: Windows 는 역슬래시 → 슬래시, 드라이브 콜론(C:) 이스케이프"""
    return str(p).replace("\\", "/").replace(":", "\\:")


def mix_music(sb: dict, voice: Path | None, dur: float, offset: float, work: Path) -> Path | None:
    """콘티 music(배경음악)을 나레이션 밑에 깐 소리 파일을 만든다 — 없으면 None(나레이션 그대로).
    곡이 짧으면 반복, 시작은 music.start 초부터, 말할 때 음악을 줄이고(sidechain 덕킹) 앞뒤는 페이드.
    권리는 사용자 판단(2026-11-03) — 엔진은 사용자가 콘티에 지정한 파일만 섞고 음악을 받아 오지 않는다"""
    m = sb.get("music") or {}
    if not m.get("src"):
        return None
    src = (ROOT / m["src"]) if not Path(m["src"]).is_absolute() else Path(m["src"])
    if not src.exists():
        print(f"[음악] 파일이 없어 건너뜀: {m['src']}", file=sys.stderr)
        return None
    gain, start = float(m.get("gain_db", -14)), float(m.get("start", 0)) + offset
    fi, fo = float(m.get("fade_in", 0.3)), float(m.get("fade_out", 1.2))
    out = work / f"{sb['id']}-mix.wav"
    mus = (f"[m]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={gain}dB,afade=t=in:d={fi},afade=t=out:st={max(0.0, dur - fo):.3f}:d={fo},"
           f"aformat=sample_rates=48000:channel_layouts=stereo[mus]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{start:.3f}", "-i", str(src)]
    if voice and voice.exists():
        cmd += (["-ss", f"{offset:.3f}"] if offset else []) + ["-i", str(voice)]
        vo = "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:%.3f" % dur
        if m.get("duck", True):
            # 말할 때 음악을 줄인다: 나레이션을 신호로 쓰는 압축(-36dB 넘으면 1/10). 느슨하게 잡았더니 1~2dB 밖에 안 줄었다(2026-11-03 측정)
            g = [mus.replace("[m]", "[0:a]"), vo + ",asplit=2[v1][v2]",
                 "[mus][v1]sidechaincompress=threshold=0.015:ratio=10:attack=15:release=400:makeup=1[ducked]",
                 "[ducked][v2]amix=inputs=2:duration=first:normalize=0[a]"]
        else:
            g = [mus.replace("[m]", "[0:a]"), vo + "[v2]", "[mus][v2]amix=inputs=2:duration=first:normalize=0[a]"]
    else:
        g = [mus.replace("[m]", "[0:a]").replace("[mus]", "[a]")]
    cmd += ["-filter_complex", ";".join(g), "-map", "[a]", "-t", f"{dur:.3f}", str(out)]
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != 0:
        print(f"[음악] 섞기 실패 — 나레이션만: {r.stderr[-400:]}", file=sys.stderr)
        return None
    return out


def finish(video: Path, sb: dict, out: Path, burn_captions: bool, tokens: dict | None = None,
           burn_ranges: list[tuple[float, float]] | None = None, offset: float = 0.0, scenes: list[int] | None = None) -> Path:
    """burn_ranges: 자막을 입힐 구간(초). 장면마다 엔진을 섞을 때, 템플릿이 자막을 직접 그리는 구간은 빼고 입힌다.
    offset/scenes: 장면 일부만 렌더한 영상이면 음성을 offset 초부터 잘라 쓰고, 그 장면들의 자막만 offset 만큼 당겨 입힌다."""
    char = resolve(sb)
    tokens = tokens or look_tokens(sb)
    sid = sb["id"]
    audio = PUBLIC / "audio" / f"{sid}.wav"
    caps_p = PUBLIC / "audio" / f"{sid}.captions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = probe_duration(video)
    w, h = (int(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                             "-of", "csv=p=0:s=x", str(video)], text=True, capture_output=True).stdout.strip().split("x"))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)]
    mixed = mix_music(sb, audio if audio.exists() else None, dur, offset, out.parent)
    if mixed:   # 배경음악을 나레이션 밑에 섞은 소리(이미 offset 을 반영했다)
        audio, offset_a = mixed, 0.0
    else:
        offset_a = offset
    if audio.exists():
        cmd += (["-ss", f"{offset_a:.3f}"] if offset_a else []) + ["-i", str(audio)]
    # 이 영상 구간의 단어 타이밍 (립싱크는 자막을 입히든 말든 전부 쓴다)
    words = json.loads(caps_p.read_text(encoding="utf-8")) if caps_p.exists() else []
    if scenes is not None:
        words = [c for c in words if c.get("scene") in scenes]
    if offset:
        ms = offset * 1000
        words = [{**c, "startMs": c["startMs"] - ms, "endMs": c["endMs"] - ms} for c in words]
    graph, last = [], "0:v"
    if burn_captions and words:
        caps = words if burn_ranges is None else [c for c in words if any(a * 1000 <= c["startMs"] < b * 1000 for a, b in burn_ranges)]
        if caps:
            ass = out.with_suffix(".ass")
            ass.write_text(build_ass(caps, tokens, w, h), encoding="utf-8")
            graph.append(f"[0:v]ass={fpath(ass)}:fontsdir={fpath(FONTS)}[base]")
            last = "base"
    if last != "base":
        graph.append("[0:v]null[base]")
    ins, more, last = overlay_graph(char, words, w, h, first_input=2 if audio.exists() else 1)
    cmd += ins
    graph += more
    # 출력 크기: 렌더 크기와 다르면(720 은 1080 에서 줄임) 마지막에 lanczos 로 맞춘다
    out_h = int(os.environ.get("FLUMA_OUT_H") or 0)
    if out_h and out_h != h:
        graph.append(f"[{last}]scale=-2:{out_h}:flags=lanczos[sized]"); last = "sized"
    cmd += ["-filter_complex", ";".join(graph), "-map", f"[{last}]"] + (["-map", "1:a:0"] if audio.exists() else [])
    cmd += ["-c:v", "libx264", "-preset", "slow" if int(os.environ.get("FLUMA_CRF") or 19) <= 15 else "medium", "-crf", os.environ.get("FLUMA_CRF") or "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if audio.exists():
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", f"{dur:.3f}", str(out)]
    r = subprocess.run(cmd, text=True, capture_output=True)
    if mixed:
        mixed.unlink(missing_ok=True)
    if r.returncode != 0:
        raise SystemExit(f"[마무리 실패]\n{r.stderr[-2000:]}")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        sys.exit(__doc__)
    sb = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    print(finish(Path(args[0]), sb, Path(args[2]), "--captions" in sys.argv))
