#!/usr/bin/env bash
# 트렌드 층 주간 작업. Claude Code 예약 작업 또는 cron 에서 호출.
#   bash engine/research/weekly_trend_job.sh
# 1) 최근 7일 쇼츠 수집 → 2) 자막 → 3) Claude Code 로 분석 → 4) 가중치 갱신(범위 내) + 제안 기록
set -euo pipefail
cd "$(dirname "$0")/.."

WEEK=$(date +%G-W%V)
KEYWORDS=("개발자 팁" "마케팅 꿀팁" "AI 툴 추천" "광고 효율" "데이터 분석")

echo "[1/4] 수집 ($WEEK)"
python3 engine/research/collect_references.py --keywords "${KEYWORDS[@]}" --days 7 --max 40

echo "[2/4] 자막"
python3 engine/research/fetch_transcripts.py "references/$WEEK"

echo "[3/4] 분석 (claude -p)"
# 대본 패턴 → engine/spec/rules/trends/<week>.json
{
  cat engine/story/prompts/analyze_scripts.md
  echo; echo "## 입력 데이터"; echo '```json'
  cat "references/$WEEK/transcripts/_index.json"
  echo '```'
  echo "## 자막 전문 (상위 30개)"
  ls "references/$WEEK/transcripts/"*.txt | head -30 | while read f; do echo "### $(basename "$f")"; cat "$f"; echo; done
} | claude -p --output-format text --model sonnet > "engine/spec/rules/trends/$WEEK.raw.txt"
python3 - "$WEEK" <<'EOF'
import json, re, sys
week = sys.argv[1]
raw = open(f"engine/spec/rules/trends/{week}.raw.txt", encoding="utf-8").read()
m = re.search(r"\{.*\}", raw, re.S)
data = json.loads(m.group(0)) if m else {"insufficient": True, "sample_size": 0}
data["week"] = week
json.dump(data, open(f"engine/spec/rules/trends/{week}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장:", f"engine/spec/rules/trends/{week}.json", "표본", data.get("sample_size"))
EOF
# 룩 분석(analyze_look.md)은 비전 모델이 필요해 별도 실행. 결과를 같은 JSON의 "look" 키에 합친다.

echo "[4/4] 갱신"
python3 engine/research/trend_update.py "engine/spec/rules/trends/$WEEK.json" || echo "갱신 건너뜀 (표본 부족 등)"

echo "완료. 확인할 것: engine/spec/tokens/trend_overrides.json (approved=false), engine/spec/rules/trends/proposals.md"
