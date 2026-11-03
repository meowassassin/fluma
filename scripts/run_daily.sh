#!/usr/bin/env bash
# 매일 작업: 대기열에서 주제 N개를 꺼내 콘티→증거→음성→렌더(→업로드)까지 돌린다.
#   bash scripts/run_daily.sh [편수] [--upload]
# 실패한 주제는 건너뛰고 다음 줄로 (호출 상한은 make_storyboard.py 안에 있음).
# 큐 형식: "- 주제" 또는 "- 형식 | 주제" (형식: 광고|감성|시세|compare|concept …). "#done" 으로 시작하면 끝난 줄.
set -uo pipefail
cd "$(dirname "$0")/.."
N=${1:-2}
UPLOAD_FLAG=""
[ "${2:-}" = "--upload" ] && UPLOAD_FLAG="--upload"
made=0

while IFS= read -r line; do
  [ "$made" -ge "$N" ] && break
  body=$(echo "${line#- }" | xargs)
  if [[ "$body" == *"|"* ]]; then fmt=$(echo "${body%%|*}" | xargs); topic=$(echo "${body#*|}" | xargs); else fmt=""; topic="$body"; fi
  echo "=== ${fmt:+[$fmt] }$topic"
  if python3 scripts/pipeline.py --topic "$topic" ${fmt:+--brief-format "$fmt"} $UPLOAD_FLAG; then
    made=$((made+1))
    python3 - "$line" <<'PY'
import sys
target = sys.argv[1]
p = "scripts/queue.md"; lines = open(p, encoding="utf-8").read().splitlines()
for i, l in enumerate(lines):
    if l == target:
        lines[i] = f"#done {l}"; break
open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  else
    echo "건너뜀: $topic"
  fi
done < <(grep -E '^- ' scripts/queue.md)

echo "오늘 $made편. 영상: out/"
