---
name: produce
description: 콘티를 영상으로 만든다(Craft 파이프라인 — 기본 엔진). 음성 → 재료 → 검사 → 납품 해상도 1회 렌더 → 결과 확인. 사용자에게 명령을 시키지 않고 에이전트가 produce.py 를 실행한다.
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

## 두 단계로 만들기
**두 단계로 만든다(2026-11-17 — 한 줄로 차례차례 돌면 15분을 넘겼다)**: ① 대본(제목 · 장면별 narration · caption · sec 대략, 재료는 비워도 됨)을 Write → ② `python3 engine/produce.py data/storyboards/<id>.json --prep --bg`(이해 관문 · 음성을 뒤에서 — 바로 돌아온다) → ③ 그동안 장면 재료(2D 는 craft-2d 예시 복사, 시각은 `$CUE:낱말`)를 콘티에 넣는다 — **첫 장면 재료를 넣은 뒤 `produce.py <콘티> --prep-status` 로 확인**: 막혔으면(이해 관문 · 구조) 재료보다 대본을 먼저 고치고 ②를 다시. **prep 을 기다리지 않는다**(until · tail -F · Monitor 로 지켜보지 않는다 — ④의 produce 가 알아서 기다린다). prep 의 각본가가 대사를 다듬어도 `$CUE` 는 가장 닮은 낱말을 찾아가므로 낱말 맞추기로 콘티를 고치지 않는다 — **narration · caption · title 은 바꾸지 않는다**(바꾸면 대본 단계를 다시 한다) → ④ `python3 engine/produce.py data/storyboards/<id>.json`(prep 이 아직 돌면 기다렸다가 연출 · 디자인 · 렌더). 대본 단계 전에 lint 를 돌리지 않는다(재료가 비어 걸린다).

## 한 줄로 돌리기
재료 칸까지 적었으면 **네가** `python3 engine/produce.py data/storyboards/<id>.json` — 레퍼런스 스타일 → 스킬(채팅에서 이미 통과했으면 엔진이 생략) → 음성 → 검사 → **납품 해상도 1회 렌더** → 장면별 정지 화면. DEEP_REVIEW 는 기본 생략(막힌 장면만 채팅에서 refine). `timeout` · `&` 로 감싸지 않는다 — produce 가 스스로 뒤에서 돌고 기다리며, 종료 11(`FLUMA_RUNNING`)이면 같은 명령을 그대로 다시 부른다(이어서 기다림).
- **produce = 오븐**: `production_ready` + lint L=0 이면 엔진 skill_pass **생략**(품질은 채팅에서 이미). lint 실패 시 **걸린 담당만**(L08→writer 등). 기존 `materials[].ui` 는 Agent 없이 `build.mjs`만 · 병렬 `ui_warm`.
- produce **전** 채팅: 콘티 + ui `.tsx` 필요 장면은 채팅에서 작성. 엔진이 produce 때 writer·director·designer + 렌더 뒤 review·refine 을 **기본 실행**(끄기: `--fast` / `--no-skills` / `FLUMA_PRODUCE_SKILLS=0` / `FLUMA_DEEP_REVIEW=0`).
- 제작 중 같은 프로젝트 plan 턴은 스튜디오가 막음(`produce.lock`).
- 종료 0 → media 로 완성 영상을 보여 주고, **'초안 · 레퍼런스 나란히' 시트 한 장만** Read 로 본다(장면별 그림을 하나씩 열거나 `preview.py` 를 따로 돌리지 않는다 — 2026-11-16: 그림 10여 장 · 미리보기 두 번에 6분). 고칠 장면이 있으면 그 장면만 `produce.py --scenes N --no-audio` 로 다시 만들고 그 장면 그림만 본다. 일부 장면만 `knob.py preview`
- 종료 1 stage=lint → 걸린 규칙만 고쳐 다시 · stage=render → error 짧은 이유로 고쳐 다시
- 종료 10 → 사용자 녹화(L36) · 스톡 키(L38)를 한 번에 부탁
- 장면 몇 개만 `--scenes 1-3`, 대사를 안 바꿨으면 `--no-audio`
- 별도 `render.py` 최종 패스는 기본 없음 — produce 한 번이 완성본이다.

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
