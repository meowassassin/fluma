---
name: publish
description: 파이프라인 6단계 — 최종 렌더 → 유튜브 업로드(사용자가 올리라고 할 때만) → 영상 분석 → 기존 트렌드 분석을 거쳐 다음 1단계 추천으로 되먹임.
---

# 6단계 — 렌더링 → 업로드 → 분석

- **엔진 2개의 역할 규칙**:
  - 편집기로 넘긴 영상은 편집기에서 내보낸 것(`data/out/<id>-editor.mp4`)이 최종본입니다.
  - Craft는 그 전 단계 초안만 만들며, `publish.py final` 및 `publish.py upload`는 편집기 내보내기 영상을 우선 채택합니다.

0. 유튜브 제목 · 설명 · 해시태그 · 태그는 produce 가 완성 때 자동으로 만든다(콘티 `upload` — `python3 engine/publish/metadata.py <콘티> [--force]`로 다시). 화면 안 제목(`title`)과 별개이고, 업로드가 그대로 보낸다. 사용자가 고친 값(`upload.by: user`)은 다시 만들지 않는다.
1. `python3 engine/gen/publish.py final <id>` — 최종본 확인/렌더(`data/out/`).
2. 업로드는 **사용자가 명시적으로 올리라고 할 때만**: `publish.py upload <id> [--privacy private|unlisted|public] [--publish-at …]`(같은 영상 중복 업로드 방지). 작업 공간의 유튜브 화면에서 올려도 된다.
3. 약 2일 뒤(YouTube Analytics 지연) 작업 공간에서 그 영상 통계를 불러오면 `data/compositions/<id>/youtube.stats.json` 이 생긴다 → `publish.py feedback <id>` — 장면별 시청 지속 · 가장 많이 빠져나간 장면(역할 · 재료 · 대사)을 `data/public/trends/own/` 와 트렌드 목록('내 영상')에 남긴다.
4. 다음 기획의 `plan.py trends` 가 이 결과(own)를 추천 재료로 함께 보여 준다 — 이탈이 컸던 장면 유형을 피한다.
