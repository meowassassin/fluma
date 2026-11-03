#!/usr/bin/env python3
"""렌더 직후 템포 검사 — 쇼츠는 피드에서 '넘기지 않고 본 비율'이 핵심 신호라(YouTube 공식), 첫 1초 · 멈춤 · 말 끊김을 렌더 결과에서 잰다.
ffmpeg 만 쓴다(새 의존성 없음): 장면 전환 scdet · 화면 멈춤 freezedetect · 무음 silencedetect · 첫 1초 프레임 비교.

  python3 scripts/tempo_check.py out/<id>-….mp4 [--sb storyboards/<id>.json] [--json]

결과: workspace/render/<id>/tempo.json — lint 가 읽는다(L32 첫 1초 · T32 멈춤 · T33 말 끊김 · T34 컷 밀도)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _ff(args: list[str]) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True)
    return r.stderr


def duration(f: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def frames(f: Path, times: list[float], w: int = 90, h: int = 160) -> list[np.ndarray]:
    out = []
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(f), "-frames:v", "1", "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                           capture_output=True)
        out.append(np.frombuffer(r.stdout, np.uint8).reshape(h, w).astype(float) if len(r.stdout) == w * h else np.zeros((h, w)))
    return out


def check(f: Path) -> dict:
    dur = duration(f)
    # 장면 전환(컷)
    cuts = [float(x) for x in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", _ff(["-i", str(f), "-vf", "scdet=threshold=12,metadata=print", "-an", "-f", "null", "-"]))]
    # 화면 멈춤(1.2초 이상 거의 같은 화면)
    fz = _ff(["-i", str(f), "-vf", "freezedetect=n=0.002:d=1.2", "-an", "-f", "null", "-"])
    freezes = [(float(a), float(b)) for a, b in zip(re.findall(r"freeze_start: ([\d.]+)", fz), re.findall(r"freeze_end: ([\d.]+)", fz))]
    # 말 끊김(0.7초 이상 무음)
    sl = _ff(["-i", str(f), "-af", "silencedetect=noise=-38dB:d=0.7", "-vn", "-f", "null", "-"])
    silences = [(float(a), float(b)) for a, b in zip(re.findall(r"silence_start: ([\d.]+)", sl), re.findall(r"silence_end: ([\d.]+)", sl))]
    # 첫 1초: 빈 화면(거의 단색)인지, 그 사이 변화가 있는지
    f0 = frames(f, [0.05, 0.35, 0.7, 1.0])
    empty0 = float(f0[0].std()) < 6.0
    change1 = max(float(np.abs(f0[i] - f0[0]).mean()) for i in range(1, len(f0)))
    return {
        "file": str(f.relative_to(ROOT)) if f.is_absolute() and ROOT in f.parents else str(f), "duration": round(dur, 2),
        "cuts": [round(c, 2) for c in cuts], "first_cut": round(cuts[0], 2) if cuts else None,
        "cuts_per_10s": round(len(cuts) / max(dur, 0.1) * 10, 2),
        "freezes": [[round(a, 2), round(b, 2)] for a, b in freezes], "longest_freeze": round(max((b - a for a, b in freezes), default=0.0), 2),
        "silences": [[round(a, 2), round(b, 2)] for a, b in silences if a > 0.3 and b < dur - 0.3],
        "first_frame_empty": empty0, "first_second_change": round(change1, 2),
    }


def problems(t: dict) -> list[tuple[str, str]]:
    """(규칙, 메시지) — lint 와 렌더 끝 요약이 같은 기준을 쓴다"""
    out = []
    if t["first_frame_empty"]:
        out.append(("L32", "첫 프레임이 빈 화면 — 피드에서 바로 넘겨진다. 첫 장면 재료 · 제목이 0초부터 보여야 함"))
    elif t["first_second_change"] < 2.0 and (t["first_cut"] is None or t["first_cut"] > 1.0):
        out.append(("L32", f"첫 1초에 화면 변화가 거의 없음(변화 {t['first_second_change']}) — 0~1초 안에 움직임 · 글자 등장 · 컷이 하나는 있어야 함"))
    if t["longest_freeze"] >= 2.5:
        a, b = max(t["freezes"], key=lambda x: x[1] - x[0])
        out.append(("T32", f"화면이 {t['longest_freeze']}초 멈춤({a}~{b}초) — 그 구간에 컷 · 확대 · 강조를 넣기"))
    for a, b in t["silences"]:
        if b - a >= 1.0:
            out.append(("T33", f"말이 {round(b - a, 1)}초 끊김({a}~{b}초) — 장면 사이 숨이 길다"))
    if t["cuts_per_10s"] < 3:
        out.append(("T34", f"컷이 10초에 {t['cuts_per_10s']}번 — 잘 되는 설명 쇼츠는 보통 1~2초마다 화면이 바뀐다(레퍼런스 X-ray 참고)"))
    return out


def save(sid: str, t: dict) -> Path:
    p = ROOT / "workspace" / "render" / sid / "tempo.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(t, ensure_ascii=False, indent=1), "utf-8")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--sb")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    f = Path(a.video).resolve()
    t = check(f)
    sid = json.loads(Path(a.sb).read_text("utf-8"))["id"] if a.sb else re.sub(r"-(craft|hyperframes|manim|blender)-.*$", "", f.stem)
    t["id"] = sid
    save(sid, t)
    if a.json:
        print(json.dumps(t, ensure_ascii=False))
        return
    print(f"[템포] 첫 컷 {t['first_cut']}초 · 컷 {t['cuts_per_10s']}/10초 · 최장 멈춤 {t['longest_freeze']}초 · 첫 1초 변화 {t['first_second_change']}")
    for code, msg in problems(t):
        print(f"   {'✗' if code.startswith('L') else '△'} {code} {msg}")


if __name__ == "__main__":
    main()
