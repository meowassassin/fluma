#!/usr/bin/env python3
"""
템플릿 콘티의 {{치환자}}를 당일 값으로 채운다 (daily 형식 운영용).

  python engine/story/fill_template.py data/storyboards/2026-10-26-client-cheongwoon-daily-04.json data/2026-10-30-cheongwoon.json

data 예:
{
  "DATE": "10/30", "ITEM_1": "감자", "UNIT_1": "20kg 한 박스", "PRICE_1": "18,000원",
  "TREND_1": "어제보다 3천 원 내렸어요", "TREND_EMPHASIS_1": "good",
  "ITEM_2": "양파", "UNIT_2": "15kg", "PRICE_2": "12,000원",
  "REACTION": "이 가격이면 사장님이 웁니다", "REACTION_NARRATION": "이 가격이면 사장님이 울어요."
}
REACTION 은 비어 있으면 등락(TREND_EMPHASIS_1)에 따라 자동 선택한다.
결과는 data/storyboards/<원본id>-<DATE>.json 으로 저장하고 검사한다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "engine" / "paths.py").exists())  # 저장소 루트(engine/paths.py 가 있는 곳)
sys.path.insert(0, str(ROOT / "engine")); import paths  # noqa: E402,F401  engine 아래 묶음들을 import 경로에
from lint import lint  # noqa: E402
AUTO_REACTION = {
    "good": ("이 가격이면\n사장님이 웁니다", "이 가격이면 사장님이 울어요."),       # 급락·저렴
    "bad": ("오늘은 참으세요\n내일 다시 올게요", "오늘은 참으세요. 내일 다시 올게요."),  # 급등
    "neutral": ("평소 가격,\n걱정 없어요", "평소 가격이에요. 걱정 없어요."),
}


def main():
    tpl_path, data_path = Path(sys.argv[1]), Path(sys.argv[2])
    text = tpl_path.read_text(encoding="utf-8")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if not data.get("REACTION"):
        cap, nar = AUTO_REACTION.get(data.get("TREND_EMPHASIS_1", "neutral"), AUTO_REACTION["neutral"])
        data["REACTION"], data["REACTION_NARRATION"] = cap, nar

    def sub(m):
        key = m.group(1)
        if key not in data:
            raise KeyError(f"치환값 없음: {key}")
        return json.dumps(data[key], ensure_ascii=False)[1:-1]   # 줄바꿈 등 이스케이프 유지

    filled = re.sub(r"\{\{(\w+)\}\}", sub, text)
    sb = json.loads(filled)
    date_slug = data.get("DATE", "today").replace("/", "")
    sb["id"] = re.sub(r"-(\d{2})$", lambda m: f"-{date_slug}-{m.group(1)}", sb["id"])
    # hook_number 는 6자 제한: "18,000원" 같은 값은 숫자만
    if sb.get("hook_number") and len(sb["hook_number"]) > 6:
        sb["hook_number"] = re.sub(r"[^0-9,만천]", "", sb["hook_number"])[:6]
    out = ROOT / "data" / "storyboards" / f"{sb['id']}.json"
    out.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    fails = lint(sb)
    print(f"저장: {out}")
    for code, idx, msg in fails:
        print(f"  {code} scene={idx} {msg}")
    print("통과" if not fails else f"실패 {len(fails)}건 — 자막·나레이션 길이를 data 값에서 줄이세요")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
