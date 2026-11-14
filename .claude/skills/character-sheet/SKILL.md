---
name: character-sheet
description: 파이프라인 2단계 — 캐릭터 시트 · 사용자 승인 ①. 샷 계획의 needs_character=true 일 때, 캐릭터마다 front · back · left · right 를 개별 파일로 나노 바나나(agy)로 만들고 사용자가 승인할 때까지 재생성한다.
---

# 2단계 — 캐릭터 시트 · 승인 ①

1단계 샷 계획(`data/shotplans/<id>.json`)이 `plan.py check` 를 통과했고 `needs_character: true` 일 때만. 아니면 3단계(키 프레임)로 건너뛴다.
목적: 영상 생성 엔진의 캐릭터 일관성 — 승인된 시트는 3단계 키 프레임의 참조가 되고, 캐릭터는 키 프레임 안에 그려져 4단계로 간다(4단계는 시작 프레임만 넘긴다 — 사용자 결정 2026-11-11).

> 작업 공간 화면 **/pipeline/<id>** 에서 사용자가 그림 · 클립을 보고 승인 · 재생성 버튼을 누를 수 있다 — 대화에서는 그 화면을 안내하고, 사용자가 대화로 승인을 말하면 명령으로 기록한다.

## 순서
1. `python3 engine/gen/character.py make <id> <이름>` — 정면을 먼저 만들고, 그 정면을 참조로 뒤 · 왼쪽 · 오른쪽을 한 장씩(동시에) 만든다. 한 장 약 1분.
   정면을 여러 장 보고 고르려면 `--views front --candidates 3` → `pick <id> <이름> <번호>` → `make … --views back,left,right`.
2. 승인용 그림 `data/compositions/<id>/characters/<이름>/sheet.png` 를 사용자에게 보여 준다. 확인할 것: 네 장이 같은 얼굴 · 머리 · 옷 · 색 · 화풍인가, **좌우가 맞는가**(left = 왼어깨가 카메라 쪽, right = 오른어깨), 발까지 보이는가, 글자가 없는가.
3. 선택지: 승인 / 특정 방향만 다시(`make … --views left`) / 정면부터 다시(정면을 바꾸면 나머지도 다시) / 설명 고치기(샷 계획 characters[].identity · wardrobe — 고치면 시트를 다시 만든다).
4. 사용자가 승인하면 `python3 engine/gen/character.py approve <id> <이름>`. 승인은 지금 그림 · 설명의 해시에 묶여, 바뀌면 자동으로 무효가 된다(`status` 로 확인).
5. 모든 캐릭터가 승인되면 3단계로 갈지 묻는다.

## 하지 않는 것
- 사용자 승인 없이 approve 하지 않는다. 2단계와 3단계를 합치지 않는다.
- 실패하면 자동으로 계속 다시 부르지 않는다 — 오류를 보고하고 사용자와 정한다.
- 한 장 시트를 만든 뒤 잘라 쓰지 않는다(얼굴이 작고 발이 잘림 — 조사).
