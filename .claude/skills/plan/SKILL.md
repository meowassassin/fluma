---
name: plan
description: 파이프라인 1단계 — 기획. 경로(실제 자료 편집 · 클립 재편집)를 고르고, 트렌드 · 레퍼런스 · 자료조사로 추천 선택지를 보여 준 뒤 기획 기록(data/shotplans/<id>.json)을 남기고 storyboard · asset-edit 로 넘긴다.
order: 0
---

# 1단계 — 기획

흐름: 1 기획 → (material) 콘티 · produce / (clip) 더빙 계획 · dub → 편집기 → 업로드 · 성과 분석. 이 스킬은 1단계만 한다.
정할 것은 사용자에게 선택지로 보여 주고 고르게 한다. 명령은 오케스트레이터(Claude Code · Codex · Antigravity)가 누구든 같다 — `engine/gen/plan.py` · `engine/gen/route.py`.
영상 · 이미지 생성 모델(Veo · 나노 바나나)은 쓰지 않는다(2026-11-19 제거). 세상에 없는 장면은 그림 · 도식 · 짤 · 비유로 연출한다.

## 0. 경로 — 에이전트가 추천하고 사용자가 고른다
- **material**(실제 자료 편집 — 기본): 설명 · 뉴스 · 비교 · 순위 · 사용법 · 광고. 화면 녹화 · 원문 문서 · 출처 있는 숫자 · 사진 · 스톡 · 퍼온 클립 여러 개 · 차트, 그리고 Craft 2D(VectorCraft 그림 → EffectCraft 움직임 · 도식 · 모션그래픽) → storyboard · produce 스킬.
- **clip**(클립 재편집): 원본 영상 하나를 다시 엮는 밈 · 반응 · 더빙 자막 → asset-edit 스킬.
- 두 경로를 ```choices``` 로(추천을 첫째에 이유와 함께). **고른 뒤** `python3 engine/gen/route.py set <id> <material|clip> --why "<이유>" --topic "<주제>"`. '알아서'면 `--by default`.
- **자동 진행**(<FLUMA_CONTEXT> 에 "진행 방식: 자동 진행"): 선택지를 띄우지 않는다 — 추천안(vet 통과)을 골라 한 줄로 알리고 `route.py set … --by default` → storyboard → produce 까지 이어 간다.
- **묻지 않고 바로 가는 경우**: 추천이 material 이고 '완성까지' · '만들어 줘' 처럼 끝까지 하라는 뜻이면 `--by default` 로 정하고 한 줄로 알린 뒤 storyboard · produce 까지 이어 간다.
- 사용자가 AI 생성 영상을 원하면: 이 도구는 생성 모델을 쓰지 않는다고 알리고, 같은 장면을 실제 자료 · 2D 로 어떻게 연출할지 제안한다.

## 1. 자료조사 · 레퍼런스 (기획 전에)
- **사실 조사**: 설명 · 제품 · 사건 · 개념 주제면 `WebSearch`/`WebFetch` 로 사실을 모아 `data/research/<id>.json`(`facts[]` + `source` URL + `visual_entities[]`) → `python3 engine/gen/plan.py research <id>`(순수 밈 · 감성만 `--skip "<사유>"`).
- **눈으로 확인**: 특정 화풍 · 작품 · 실제 제품/화면을 말했으면 기억으로 쓰지 않는다 — `python3 engine/research/ref_image.py search <id> "<영문 검색어>" --limit 6` → `candidates_sheet.jpg` 를 Read → `ref_image.py pick <id> <번호…> --role style|prop|background --note "<관찰>"`.
- **트렌드 → 추천 선택지**: `python3 engine/gen/plan.py trends --query "<사용자 주제 낱말>" [--request <rid>]`. `topic_matched=false` 면 trends 스킬(`trends.py search "<주제>"`)로 먼저 찾는다.
  **선택지는 매번 달라야 한다**(같은 요청에 10번 모두 git 실수 · 금요일 배포 · DNS 가 나왔다): 3개 모두 `angles` 중 서로 다른 각도, 결과의 `already_offered`(이미 보여 준 선택지 · 만든 주제)와 같은 소재 금지.
  보여 주기 전에 `python3 engine/gen/plan.py vet "<선택지1>" "<선택지2>" "<선택지3>"` — ✗ 는 다른 각도 · 다른 소재로 바꿔 다시 vet.
  레퍼런스는 이 순서로 한 번씩: `trends.py search` → `python3 engine/research/ref_pick.py --request <rid>`(표 + 썸네일 시트 한 장만 Read) → 2~3편을 `analyze_ref.py <id1> <id2> <id3>` 한 명령 → 필요한 편만 `look.py sheet <id>`.
  `xray.json` 의 `understanding`(훅 · 반전 · 편집 문법 · 빌릴 것 · 베끼면 안 되는 것)을 읽고 **추천 선택지 2~4개**(훅 · 플롯 한 줄 · 화면 재료 · 길이, 근거 쇼츠 id)를 ```choices``` 로.

## 빠른 길(기본)
`python3 engine/story/prepare.py <id> "<주제>"` 한 번이 경로 기록 · 레퍼런스 찾기 · 분석 · 이미 보여 준 선택지를 다 한다(아래 단계를 하나씩 부르지 말 것). 그 요약을 보고 사실 조사(WebSearch) · 각도가 다른 선택지만 네가 한다. 레퍼런스가 엉뚱하면 `--queries "검색어"` 또는 `--refs a b c`.

## 여러 편 요청
"○○ 주제로 N개"면 주제 N개(각도가 서로 다르게, vet 통과)를 뽑아 보여 주고 `python3 engine/core/batch.py start "주제 1" …` 로 넘긴다 — 주제마다 새 영상 대화가 자동 진행으로 완성까지. 이 대화에서 직접 만들지 않는다. 답에 ```batch 블록(묶음 id).

## 2. 기록 · 넘기기
- `python3 engine/gen/plan.py new <id> --topic "<주제>"`(route.py set 이 먼저 만들었으면 생략) → `python3 engine/gen/plan.py check <id>` 가 실패 없이 통과할 때까지.
- material → storyboard 스킬로 콘티를 쓰고 produce. clip → asset-edit 스킬.

## 화면 블록
- ```choices``` — 답 끝에 하나, 2~4개, 그대로 보내도 말이 되는 지시.
- ```brief``` — 정해진 것을 `키: 값`(주제 · 경로 · 고른 선택지 · 레퍼런스 · 근거 사실 수 · 남은 결정).

## 하지 않는 것
- 사용자가 고르기 전에 다음 단계로 넘어가지 않는다(위 '바로 가는 경우' 제외).
- 확정된 결정을 바꾸지 않는다. 스펙에 없는 설계 결정이 필요하면 사용자에게 묻는다.
