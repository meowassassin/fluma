---
name: produce
description: 콘티를 영상으로 만든다(Craft 파이프라인 — 기본 엔진). 음성 → 장면 재료(차트 · 문서 인용 · 그림 · 사진 · 화면) → 검사 → 초안 렌더(EffectCraft → SoundCraft → FilmCraft) → 결과 확인. 기획에서 콘티가 검사를 통과하면 바로 이어서, 또는 "만들어 줘" · "초안 렌더" 요청에 쓴다.
order: 2
---
# 제작 (Craft 파이프라인)

엔진은 Craft 하나(콘티 `engine: "craft"`). 화면은 장면마다 **무엇이 보여야 하는지(재료)** 를 정하는 일이다 — 좌표 · 툴 이름은 쓰지 않는다.
재료 종류표 · 소리 · 디자인 방향 · 검사 코드 · 하지 말 것은 **`.claude/skills/produce/reference.md`** — 막히거나 처음 쓰는 재료일 때만 읽는다.

## 속도 규칙(2026-11-11 실측: 턴 47번에 콘티 Edit 340번 · 엔진 소스 Read 30번이 시간 대부분)
- 콘티는 **한 번에 Write** 로 쓴다. 칸 하나씩 Edit 를 이어 붙이지 않는다. 쓴 뒤 lint 한 번 → 걸린 것을 모아 한 번에 고친다.
- 초안 뒤 고치기는 Edit 대신 `knob.py set`(여러 값을 한 줄에).
- 엔진 소스(`engine/**/*.py`)를 읽어 사용법을 찾지 않는다 — 스킬 · reference.md · `<명령> --help` 로. 거기 없으면 그때만.
- 정지 화면은 고친 장면만 본다. 초안 전체의 흐름 · 타이밍은 `python3 engine/look/look.py sheet <초안 mp4>` 로 보고, 기록이 필요하면 `look.py critique <id>`(data/workspace/critique/<id>.json).

## 한 줄로 돌리기
재료 칸(materials)까지 적었으면 **`python3 engine/produce.py data/storyboards/<id>.json`** — 레퍼런스 스타일 → **스킬 단계**(writer → director → designer, 검사가 막은 것은 담당 단계로 되먹임) → 음악 · 음성 → 검사 → **장면 구성** → 재료 · 초안 → **정지 화면 검토(designer review) · refine → 다시 렌더** → 장면별 정지 화면(timeout 30분). 스킬 단계 기록 `python3 engine/story/skill_pass.py status <콘티>` · 건너뛰기 `--no-skills`.
- 종료 0 → media 줄(초안 + 정지 화면)을 채팅에 띄우고, 정지 화면을 Read 로 보고 고칠 곳만 고쳐 다시
- 종료 1 stage=lint → 걸린 규칙만 고쳐 다시 · stage=render → error 짧은 이유로 고쳐 다시
- 종료 10 → 사용자 녹화(L36) · 스톡 키(L38)를 한 번에 부탁
- 장면 몇 개만 `--scenes 1-3`, 대사를 안 바꿨으면 `--no-audio`
- 최종 렌더는 사용자가 '좋아 · 완성'이라고 하면 바로 `python3 engine/render.py data/storyboards/<id>.json`(버튼 안내 · 관문 없음)

## 재료 고르기(요약 — 칸 · 예시는 storyboard 스킬, 표 전체는 reference.md)
문장(핵심 낱말)마다 재료 하나, 30초면 서로 다른 재료 10개 이상(L37), 같은 종류 네 번 연속 금지(T37).
숫자 하나 `stat`(바탕 재료 위 덧씌우기) · 비교 `chart` · 근거 문장 `doc_quote` · 실제 화면 `web` · `screen` · 짚기 `overlay` · 구조 `diagram` · 요점 `info_card` · 문서 `document` · 로고 `icon` · 짤 `meme` · 실사 `video`(clip.py) · `stock` · `photo` · 제품 `model3d`.
**사람/장면**은 실제 자료(퍼온 클립 · 자료 사진 · 스톡 · 짤)로. 그림 · 영상 생성 모델은 쓰지 않고, 손이나 코드로 인물 · 장면을 그리지 않는다.
설명형 영상은 실제 자료와 정교한 UI/데이터 목업 · 도표가 화면의 주인공이 된다. 실행 녹화(`engine/capture/demo.py run <id>` · `webrec.py`)는 증거가 필요할 때 쓰는 재료 중 하나.

## 대화로 고치기 — 값으로 (knob.py)
- 보기 `python3 engine/story/knob.py list <id>` · 바꾸기 `knob.py set <id> route2d.adjust.scale=*1.2 s4.sec=+1.5 voice.speed=0.95`
  - 모든 요소 공통 `adjust`: dx · dy(화면 비율) · scale · rot · opacity · delay · hide. 장면 칸 `s4.sec` · `s4.caption` · `s4.transition`, `script` · `voice.*` · `music.*`. 상대값 `*0.7` · `+0.5`, 지우기 `=null`
- 보여 주기 `knob.py preview <id> --scene <n>`(정지 약 2초) · 움직임은 `--clip`(약 8초)
- 애매하면 "s4 route2d 를 1.2배로"처럼 고칠 요소 id 를 한 줄로 밝히고 바로 진행
- 새 스크립트 재료는 바꿀 숫자를 콘티 `args` 에 둔다 → 다음 조정은 `knob.py set <id> <요소>.args.gap=*1.5`

## 초안 뒤
초안 · 레퍼런스 나란히(`data/compositions/<id>/craft/review/sheet.png`)를 직접 보고 director 스킬 감독 검사로 고친다. 장면 디테일은 refine 스킬.
