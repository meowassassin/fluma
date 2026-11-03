---
name: research
description: 주제의 사실을 출처 URL과 함께 모은다. 출처 없는 사실은 버리고, 5개 미만이면 그 주제는 만들지 않는다.
order: 2
---

# 조사

1. WebSearch 로 주제의 핵심 엔티티(툴·제품·기관)와 수치를 찾는다. 공식 페이지(요금·약관·문서) > 신뢰할 만한 리뷰 > 블로그 순.
2. 필요한 페이지는 WebFetch 로 열어 수치를 직접 확인한다.
3. `research/<주제-슬러그>.json` 에 저장한다. 형식은 기존 파일(`research/무료-TTS-사이트-3개-비교.json`)과 같다:
   - `facts[]`: `claim`, `value`, `entity`, `source`(URL), `checked`(오늘 날짜), `confidence`(high/medium/low)
   - `entities[]`, `angle_candidates[]`(통념과 다른 각도 2~3개), `caveats[]`(가격·한도는 "변동 가능")
4. 비교 주제는 항목마다 같은 기준의 값 2개 이상.
5. 출처 있는 사실이 5개 미만이면 콘티를 만들지 말고 무엇이 부족한지 사용자에게 알린다.

광고 수치는 조사하지 않는다. 클라이언트가 준 값만 쓰고(`briefs/`), 없는 수치는 장면에 넣지 않는다.
