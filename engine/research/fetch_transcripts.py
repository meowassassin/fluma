#!/usr/bin/env python3
"""
트렌드 층 2단계: shorts.csv 의 영상 자막을 받아 텍스트로 저장한다.

출력: references/<week>/transcripts/<video_id>.txt
      references/<week>/transcripts/_index.json  (video_id → 길이, 첫 문장, 글자수)

자막이 없는 영상은 건너뛴다 (자동 자막 포함해 시도).
"""
import csv
import json
import sys
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    sys.exit("pip install -r engine/requirements-full.txt 먼저 실행하세요.")

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
def latest_week_dir() -> Path:
    refs = sorted((ROOT / "references").glob("*-W*"))
    if not refs:
        sys.exit("references/ 에 수집 폴더가 없습니다. collect_references.py 먼저.")
    return refs[-1]


def main():
    week = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_week_dir()
    csv_path = week / "shorts.csv"
    out_dir = week / "transcripts"
    out_dir.mkdir(exist_ok=True)

    api = YouTubeTranscriptApi()
    index = {}
    ok = skip = 0
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vid = row["video_id"]
            try:
                tr = api.fetch(vid, languages=["ko", "en"])
                segs = [s.text.strip() for s in tr if s.text.strip()]
            except Exception:
                skip += 1
                continue
            text = " ".join(segs)
            (out_dir / f"{vid}.txt").write_text(text, encoding="utf-8")
            first = segs[0] if segs else ""
            index[vid] = {
                "title": row["title"],
                "duration_sec": int(row["duration_sec"]),
                "chars": len(text),
                "chars_per_sec": round(len(text) / max(int(row["duration_sec"]), 1), 2),
                "first_line": first,
                "views_per_sub": float(row["views_per_sub"]),
            }
            ok += 1
    (out_dir / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"자막 {ok}개 저장, {skip}개 없음 → {out_dir}")


if __name__ == "__main__":
    main()
