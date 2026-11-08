#!/usr/bin/env python3
"""업로드 안내 — 쇼츠를 올릴 때 사람이 할 일을 한 장에(제목 · 설명란 · 해시태그 · 쇼츠 편집기에서 붙일 곡).

  python3 engine/publish/upload_guide.py data/storyboards/<id>.json [<영상.mp4>]   → data/out/<id>.upload.md

곡(music_library): 영상 파일에는 넣지 않는다 — 유튜브 쇼츠 편집기의 오디오 라이브러리에서 붙이면 유튜브가 가진 라이선스로 쓰여 수익 문제가 없다.
(공식 API 로는 라이브러리 곡을 붙일 수 없다 — 이 단계만 사람이 30초. 데스크톱 스튜디오에서 되는지는 첫 업로드 때 확인)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())
sys.path.insert(0, str(ROOT / "engine" / "publish"))


def guide(sb: dict, video: str | None) -> str:
    from upload_youtube import build_description
    ml = sb.get("music_library") or {}
    sid = sb["id"]
    vid = video or f"data/out/{sid}-craft-Scenes.mp4"
    L = [f"# 업로드 안내 — {sb.get('title', sid)}", "",
         f"- 영상: `{vid}`(배경음악 없음 · 클립 원음만)", f"- 제목: {sb.get('title', '')}", "",
         "## 설명란(그대로 붙여 넣기)", "```", build_description(sb), "```", ""]
    if ml:
        L += ["## 곡 붙이기(쇼츠 편집기 · 약 30초)",
              "1. 유튜브 앱에서 업로드(또는 올린 뒤 해당 쇼츠 → 편집) → **사운드 추가**",
              f"2. 검색: **{ml['track']}**",
              f"3. 시작 지점: {ml.get('start_hint') or '처음부터'}",
              "4. 음량: 원음이 들리게 배경음 50~60% 정도",
              f"- 같은 곡을 쓴 쇼츠(조회수 높은 순): " + ", ".join(f"https://www.youtube.com/shorts/{x}" for x in ml.get("examples") or []),
              f"- 고른 이유: {ml.get('why', '')}", ""]
    return "\n".join(L)


def main() -> int:
    sbp = Path(sys.argv[1]); sb = json.loads(sbp.read_text("utf-8"))
    out = ROOT / "data" / "out" / f"{sb['id']}.upload.md"
    out.write_text(guide(sb, sys.argv[2] if len(sys.argv) > 2 else None), "utf-8")
    print(out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
