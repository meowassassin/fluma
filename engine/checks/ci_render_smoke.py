#!/usr/bin/env python3
"""끝까지 렌더 시험(계정 · 키 없이) — 무음 음성 → 장면 재료(차트) → EffectCraft → SoundCraft → FilmCraft → mp4.
CI(여러 운영체제)와 로컬에서 같은 것을 돌린다. 필요한 Craft 앱: effectcraft · soundcraft · filmcraft · gridcraft

  python3 engine/checks/ci_render_smoke.py [--keep]

통과하면 0, 실패하면 이유를 출력하고 1. --keep 이 없으면 만든 콘티 · 제작 파일 · 결과를 지운다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):   # Windows 콘솔 · 파이프에서 한글이 깨지지 않게
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
SID = "ci-smoke-01"


def storyboard() -> dict:
    src = f"data/compositions/{SID}/src/"
    return {
        "id": SID, "version": 1, "format": "concept", "language": "ko", "engine": "craft", "title": "렌더 시험",
        "duration_sec": 6, "voice": {"engine": "silent", "source": "user"}, "reference_skip": "CI 렌더 시험",
        "scenes": [
            {"role": "hook", "sec": 3, "caption": "다섯 개 중\n하나는 가짜", "narration": "다섯 개 중 하나는 가짜래요.",
             "visual": {"kind": "number", "primary": "20%"}, "elements": [{"name": "훅 제목", "what": "\"5개 중 1개\"", "source": "kit"}],
             "materials": [{"id": "chart", "type": "chart", "csv": src + "data.csv", "range": "A1:B3", "percent": True, "title": "시험 차트"}]},
            {"role": "outro", "sec": 3, "caption": "확인부터\n하세요", "narration": "설치 전엔 확인부터 하세요.",
             "visual": {"kind": "list", "primary": "확인", "items": ["이름", "다운로드 수"]}},
        ],
        "cta": "확인부터",
    }


def run(args: list[str]) -> str:
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print((r.stdout + r.stderr)[-3000:])
        raise SystemExit(f"실패: {' '.join(args)}")
    return r.stdout


def probe(f: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(f)], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    sb_p = ROOT / "data" / "storyboards" / f"{SID}.json"
    comp = ROOT / "data" / "compositions" / SID
    (comp / "src").mkdir(parents=True, exist_ok=True)
    (comp / "src" / "data.csv").write_text("항목,값\n실제,4\n가짜,1\n", "utf-8")
    sb_p.parent.mkdir(parents=True, exist_ok=True)
    sb_p.write_text(json.dumps(storyboard(), ensure_ascii=False, indent=1), "utf-8")
    out = ROOT / "data" / "out" / f"{SID}-craft-Scenes-draft.mp4"
    try:
        print("· 음성(무음 엔진)"); run(["engine/voice/assemble_audio.py", str(sb_p)])
        print("· 초안 렌더(Craft)"); log = run(["engine/render.py", str(sb_p), "--draft"])
        print("\n".join(l for l in log.splitlines() if l.startswith(("[엔진]", "[소리]", "[조립]", "[완료]", "[템포]"))))
        if not out.exists():
            raise SystemExit(f"결과 영상이 없습니다: {out}")
        p = probe(out)
        kinds = sorted({s.get("codec_type") for s in p.get("streams", [])})
        dur = float(p.get("format", {}).get("duration", 0))
        man = json.loads((comp / "craft" / "craft.json").read_text("utf-8"))
        print(f"· 결과: {dur:.2f}초 · 트랙 {kinds} · 제작 파일 {sorted(man)}")
        assert "video" in kinds, "영상 트랙 없음"
        assert "audio" in kinds, "소리 트랙 없음"
        want = sum(x["sec"] for x in json.loads(sb_p.read_text("utf-8"))["scenes"])   # 음성 단계가 실측으로 고친 길이
        assert abs(dur - want) <= 1.0, f"길이가 콘티({want}초)와 다름: {dur}"
        assert {"motion", "audio", "edit"} <= set(man), f"제작 파일이 모자람: {sorted(man)}"
        print("통과")
    finally:
        if not a.keep:
            sb_p.unlink(missing_ok=True)
            shutil.rmtree(comp, ignore_errors=True)
            shutil.rmtree(ROOT / "data" / "workspace" / "render" / SID, ignore_errors=True)
            for f in list((ROOT / "data" / "out").glob(f"{SID}*")) + list((ROOT / "data" / "audio").glob(f"{SID}*")) + list((ROOT / "data" / "public" / "audio").glob(f"{SID}*")):
                if f.is_dir():
                    shutil.rmtree(f, ignore_errors=True)
                else:
                    f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
