---
name: research
description: 주제의 사실을 출처 URL과 함께 모은다. 출처 없는 사실은 버리고, 5개 미만이면 그 주제는 만들지 않는다.
order: 2
---

# 조사 (Stage 0.5 — `material` 콘티 · `generate` 샷 계획 공통)

## 1. 사실 · 정보 조사 (`WebSearch` · `WebFetch`)
1. WebSearch 로 주제의 핵심 엔티티(툴·제품·기관·사건)와 구체적 수치를 찾는다. 공식 페이지(요금·약관·문서) > 신뢰할 만한 리뷰 > 블로그 순.
2. 필요한 페이지는 WebFetch 로 열어 수치를 직접 확인한다.
3. 저장 경로:
   - **생성 경로(`shotplan`)**: `data/research/<id>.json` (예: `data/research/2026-11-15-topic-01.json`) → 저장 뒤 `python3 engine/gen/plan.py research <id>` 로 샷 계획에 연결한다.
   - **실제 자료(`storyboard`)**: `data/research/<주제-슬러그>.json` (`lint.py` L56 검사).
   - 형식:
     - `facts[]`: `claim`, `value`, `entity`, `source`(http URL 필수), `checked`(오늘 날짜), `confidence`(high/medium/low)
     - `entities[]`: 핵심 대상 목록
     - `visual_entities[]`: 화면에 반드시 보여야 하는 구체적 사물·UI·장소 이름(예: `"Chrome tab strip"`, `"RAM DIMM slot"` — `Mute Test` 소품으로 직결)
     - `angle_candidates[]`(통념과 다른 각도 2~3개), `caveats[]`(가격·한도는 "변동 가능")
4. 비교 주제는 항목마다 같은 기준의 값 2개 이상.
5. `material` 콘티는 출처 있는 사실이 5개 미만이면 멈추고 알린다. `generate` 경로의 순수 창작·밈·감성 컷은 조사가 불필요한 이유를 `plan.py research <id> --skip "<사유>"` 로 남긴다.

## 2. 화풍 · 작품 · 캐릭터 · 실물 시각 레퍼런스 (`ref_image.py` / `analyze_ref.py`)
사용자가 특정 화풍("지브리풍"·"아케인 스타일" 등)·작품·캐릭터·실제 제품/화면을 언급했으면 기억으로 적지 말고 **실제 이미지나 영상을 찾아 눈으로 본 뒤** 쓴다:
- 이미지 검색: `python3 engine/research/ref_image.py search <id> "<영문 검색어>" --limit 6` (또는 URL/첨부가 있으면 `fetch`) → 생성된 `candidates_sheet.jpg` 를 **Read / `read_file` 로 직접 확인** → `python3 engine/research/ref_image.py pick <id> <번호...> --role style|character|prop|background --note "<관찰한 화풍·색·질감 요약>"`
- 유튜브 쇼츠 레퍼런스: `python3 engine/research/analyze_ref.py <링크>` → `python3 engine/look/look.py sheet <영상 id>` 를 Read 로 확인.
- 눈으로 본 색·질감·빛만 `shotplan.style` 과 `characters[].identity` 에 적는다.

광고 수치는 조사하지 않는다. 클라이언트가 준 값만 쓰고(`data/briefs/`), 없는 수치는 장면에 넣지 않는다.
