#!/usr/bin/env python3
"""
파이프라인 한 명령: 주제(또는 콘티) → 결정·조사·생성·검사 → 증거 → 음성 → 렌더 → (업로드)

  python scripts/pipeline.py --topic "무료 TTS 사이트 3개 비교" [--audience "마케터"] [--duration 30]
  python scripts/pipeline.py --storyboard storyboards/<id>.json --template Overlay
  python scripts/pipeline.py --topic "..." --brief-format 광고 --brand "가게 이름" --upload --privacy private

단계는 각각 독립 스크립트라 실패한 단계부터 다시 돌릴 수 있다 (--from capture|audio|render|upload).
엔진·템플릿을 지정하지 않으면 콘티의 engine/template, 없으면 기본 엔진(HyperFrames)이 형식으로 고른다 (scripts/engines.py).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STEPS = ["storyboard", "capture", "audio", "render", "upload"]


def run(cmd, cwd=ROOT, env=None, check=True):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, text=True, capture_output=True)
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        if check:
            raise SystemExit(f"[실패] {cmd[1] if len(cmd) > 1 else cmd[0]} (exit {res.returncode})")
    return res


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--topic")
    g.add_argument("--storyboard", help="이미 있는 콘티 JSON 경로")
    ap.add_argument("--audience", default="", help="대상 시청자 (선택)")
    ap.add_argument("--duration", type=int, default=None, help="목표 길이(초, 선택)")
    ap.add_argument("--brand", default=None, help="하단 브랜드명 (선택)")
    ap.add_argument("--brief-format", default="", help="시안 형식 지정: 광고|감성|시세 등")
    ap.add_argument("--engine", default=None, help="렌더 엔진 (engines/<이름>, 기본: 콘티의 engine 또는 hyperframes)")
    ap.add_argument("--template", default=None, help="엔진의 템플릿 (기본: 형식으로 자동)")
    ap.add_argument("--from", dest="start", default="storyboard", choices=STEPS, help="이 단계부터 시작")
    ap.add_argument("--skip-audio", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--privacy", default="private")
    ap.add_argument("--publish-at", default=None)
    ap.add_argument("--force", action="store_true", help="L14(실측 음성 길이) 실패여도 렌더")
    ap.add_argument("--dry-run", action="store_true", help="결정층 결과만 보고 종료")
    args = ap.parse_args()

    start = STEPS.index(args.start)

    # 1) 콘티
    if args.storyboard:
        sb_path = Path(args.storyboard)
    else:
        if start > 0:
            raise SystemExit("--topic 으로 시작할 때는 --from storyboard 여야 합니다")
        cmd = [PY, "scripts/make_storyboard.py", "--topic", args.topic]
        if args.audience:
            cmd += ["--audience", args.audience]
        if args.duration:
            cmd += ["--duration", str(args.duration)]
        if args.brand:
            cmd += ["--brand", args.brand]
        if args.brief_format:
            cmd += ["--brief-format", args.brief_format]
        if args.dry_run:
            cmd += ["--dry-run"]
        res = run(cmd)
        if args.dry_run:
            return
        m = re.search(r"\[저장\] (\S+\.json)", res.stdout)
        if not m:
            raise SystemExit("콘티 저장 경로를 찾지 못함")
        sb_path = Path(m.group(1))
        if not sb_path.is_absolute():
            sb_path = ROOT / sb_path if not sb_path.exists() else sb_path

    sb = json.loads(sb_path.read_text(encoding="utf-8"))
    if "{{" in json.dumps(sb, ensure_ascii=False):
        raise SystemExit("템플릿 콘티입니다. scripts/fill_template.py 로 값을 먼저 채우세요.")
    sb_rel = os.path.relpath(sb_path, ROOT)
    print(f"\n[콘티] {sb_rel}  형식={sb['format']}  엔진={args.engine or sb.get('engine') or '기본'}  템플릿={args.template or sb.get('template') or '자동'}  룩={sb.get('look') or 'default'}")

    # 2) 증거(에셋 배치·캡처)
    if start <= STEPS.index("capture"):
        run([PY, "scripts/capture.py", sb_rel], check=False)

    # 3) 음성
    if start <= STEPS.index("audio") and not args.skip_audio:
        run([PY, "scripts/assemble_audio.py", sb_rel], check=False)
        res = run([PY, "scripts/lint.py", sb_rel], check=False)
        if "L14" in res.stdout and not args.force:
            raise SystemExit("[중단] L14: 나레이션이 장면보다 깁니다. 콘티를 고치고 --from audio 로 다시, 또는 --force")

    # 4) 렌더 (엔진 → 무음 영상 → 마무리: scripts/render.py)
    out_mp4 = None
    if start <= STEPS.index("render"):
        cmd = [PY, "scripts/render.py", sb_rel]
        if args.engine:
            cmd += ["--engine", args.engine]
        if args.template:
            cmd += ["--template", args.template]
        res = run(cmd)
        out_mp4 = Path(res.stdout.strip().splitlines()[-1])
        print(f"[렌더] {out_mp4}")

    # 5) 업로드
    if args.upload and start <= STEPS.index("upload"):
        if out_mp4 is None:
            raise SystemExit("업로드할 영상이 없습니다 (--from render 이전 단계부터)")
        cmd = [PY, "scripts/upload_youtube.py", sb_rel, str(out_mp4), "--privacy", args.privacy]
        if args.publish_at:
            cmd += ["--publish-at", args.publish_at]
        run(cmd)

    print("\n[완료]", sb["id"], "→", out_mp4.name if out_mp4 else "(렌더 안 함)")


if __name__ == "__main__":
    main()
