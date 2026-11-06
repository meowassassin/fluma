---
name: format-daily
description: 당일 시세 형식(15초). 상품 장면 + 가격 하나 크게 + 반응 한 줄. 템플릿 콘티에 데이터를 채워 매일 만든다.
order: 12
---

# 당일 시세 (daily)

- 길이 15초. 장면: hook(price_tag) → price×1~3 → mood → cta.
- **가격은 하나만 크게.** 표는 블로그로 보낸다 (분석: 시세표 572회 vs 가격 하나 48만회).
- 반응 한 줄이 숫자를 운반한다: 급락 "이러다 다 죽어요", 급등 "오늘은 참으세요", 보합 "평소 가격".
- 운영은 템플릿 콘티(`{{치환자}}`) + `data/<날짜>.json` → `python3 scripts/fill_template.py <템플릿> <데이터>`. 템플릿 콘티는 L 검사 대신 T00 이 나온다.
- 시세 값은 가상값을 쓰지 않는다. 데이터 파일이 없으면 사용자에게 묻는다.
- 참고: `storyboards/2026-10-26-client-cheongwoon-daily-04.json`(템플릿), `data/2026-10-30-cheongwoon.json`
- 가격 화면(Craft 엔진): 매일 같은 틀에 값만 바꾸면 `template_card` 재료 — `{"type": "template_card", "csv": "data/<날짜>-price.csv", "row": "<품목 name>"}` (틀은 `template` .vectorcraft, 없으면 기본 카드: 첫 열 제목 · 둘째 열 큰 값 · 셋째 열 반응). 상품 사진은 `photo_grade`(같은 look 이면 매일 같은 톤). 표가 아니라 카드 한 장에 가격 하나.
