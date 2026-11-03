---
name: craft-art
description: 그림 · 카툰 장면을 '구조로 그리기'로 만든다. 좌표를 쓰지 않고 형태(부품 · 관계 · 비율)와 화풍 카드만 쓰면, 그리기 엔진이 외곽선 · 명암 · 손맛을 계산하고 Craft 엔진(EffectCraft)이 부품 인형으로 움직인다. "카툰풍" · "캐릭터" · "그림체가 다르다" · "AI 티" · "싼티" 요청에 쓴다.
---

# 구조로 그리기 (그리기 엔진 + Craft 엔진) — 실험 기능

> 2026-11-03: 캐릭터 · 장면 디자인은 **illustrate 스킬**(에이전트가 디자이너처럼 VectorCraft 로 그리고 렌더해서 보고 고침)로 한다.
> 이 스킬의 규칙 엔진(형태 · 몸 설계도)은 결과가 유치해서 기본 경로에서 뺐다. 화풍 측정(style_card) · 비평 루브릭 · 마감 검사만 보조로 쓴다.

**좌표로 그리지 않는다.** 2026-11-03 쿠르츠게작트풍 영상에서 SVG 점을 직접 찍었더니 네 번 갈아엎고도 "부끄러울 정도"였다.
에이전트는 **무엇을 · 어떤 비율로 · 어디에 붙여서**만 말한다. 점 · 곡선 · 명암 · 관절 · 움직임은 엔진이 계산한다.
설계: 볼트 `02 Architecture/그리기 엔진 설계 — 구조로 그리기` · `Craft 파이프라인 설계`.

## 1. 화풍 시스템 — 레퍼런스에서 잰다 (open-design 의 DESIGN.md 처럼)
```
python3 scripts/style_card.py <참고 영상 id> [<id> …] --name <이름>    # → styles/<이름>/STYLE.md + style.json
```
영상의 `compositions/<id>/style.json` 은 `{ "system": "<이름>" }` 한 줄. 팔레트 · 명도 구조 · 외곽선 · 명암 단계를 손으로 정하지 않는다.
부품은 역할(`main` · `main_dark` · `accent` · `accent2` · `light` · `dark` · `white` · `black`)로만 색을 받는다. 형태의 `palette` 로 역할 색을 바꿀 때도 STYLE.md 의 측정한 색 무리에서 고른다.
보편 규칙은 `rules/illustration/`(도형 언어 · 매력 · 색/명도 · 움직임 · 초딩 티 목록) — 형태를 짓기 전에 읽는다.

## 2. 형태 — `compositions/<id>/forms/<이름>.form.json`
몸 설계도(`library/archetypes/`)에서 시작해 바꿀 것만 쓴다.
`biped` · `quadruped` · `bird` · `blob_creature` · `prop` · `plant` · `building` · `vehicle` · `icon`
```json
{ "archetype": "blob_creature", "view": "3/4", "facing": "right",
  "remove": ["antenna"],
  "parts": [
    { "id": "body", "role": "accent", "size": { "h": 1.3, "w": 1.0 } },
    { "id": "hood", "shape": "blob", "size": { "h": 0.8, "w": 1.1 }, "attach": { "to": "body", "at": "top", "inset": 0.3 }, "role": "dark" },
    { "id": "mask", "shape": "box", "size": { "h": 0.14, "w": 0.6 }, "round": 0.07, "attach": { "to": "body", "v": 0.3, "az": -10, "inset": 0.2 }, "role": "black", "decal": true }
  ] }
```
- 붙이기: `attach.to` + `v`(위 0 ~ 아래 1) + `az`(둘레 각도: 음수 = 보는 쪽, 0 정면, ±90 옆) 또는 `u`(가로 −1~1, 납작한 물체) + `inset`(파고들기).
- 팔다리 · 꼬리(`capsule` · `sweep`): `dir`(0 아래 · 90 앞 · 180 위), `splay`(몸 바깥으로 벌림 — 대칭 부품은 저절로 반대로).
- `mirror`: 좌우 대칭 복사. `decal`: 표면 무늬(눈 · 배 · 창문) — 뒤쪽 면이면 저절로 숨는다. `ground`: 발.
- 시점은 `view` 하나로: 같은 형태가 정면 · 3/4 · 옆으로 그려진다(먼 쪽 팔은 몸 뒤로 저절로).
- **좌표(x · y · points) 를 쓰면 거절된다.** 못 풀면 이유가 말로 온다("hat: 'body' 에 닿지 않고 0.15 단위 떠 있음") — 관계를 고친다.

확인:
```
python3 scripts/draw.py check  compositions/<id>/forms/<이름>.form.json
python3 scripts/draw.py render compositions/<id>/forms/<이름>.form.json --style compositions/<id>/style.json --out workspace/tmp/<이름>.svg --png workspace/tmp/<이름>.png
```

## 3. 장면에 세우기 — 콘티 장면의 `figures`
```json
"figures": [ { "name": "hacker", "action": "walk", "at": "far_left", "to": "center", "size": 0.32, "cue": "해커가" } ]
```
- `action`: `idle`(숨쉬기) · `walk`(다리 반대 위상 · 팔 반대 · 몸 들썩 · 이동) · `wave` · `bounce`. 부속(꼬리 · 더듬이)은 한 박자 늦게 따라 흔들린다.
- 자리는 말로: `left` · `center` · `right` · `far_left` · `far_right`. 크기는 화면 높이 비율.
- Craft 엔진이 부품 레이어를 관절에 회전축을 둔 인형으로 조립한다(EffectCraft 프로젝트에서 사람이 그대로 열어 고칠 수 있음).
- 렌더: `python3 scripts/render.py storyboards/<id>.json --engine craft --draft`

## 4. 그림 lint + 비평 고리 (내보내기 전에 스스로)
```
python3 scripts/draw.py check    <form> --style <style.json> --bg <배경색>        # lint: P0 는 그리기 거절
python3 scripts/draw.py critique <form> --style <style.json> --ref <참고 영상 id>  # 비평용 한 장 · lint · 숫자 · 빈 평가지
python3 scripts/draw.py critique <form> --style <style.json> --score <채운 평가지>  # 회차 기록 · 멈춤 여부
```
1. 비평용 한 장(컬러 · 실루엣 · 흑백 · 엄지손톱 · 레퍼런스)을 **실제로 보고**, `rules/illustration/critique.md` 루브릭대로 다섯 기준(화풍 · 실루엣 · 매력 · 디테일 · 명도)에 0–10점 + 근거.
2. `changes` 를 형태의 관계 · 비율 · 역할 색으로만 고친다 → 다시 critique. 고친 곳이 다른 곳을 망치면 점수를 내린다(정직하게).
3. 멈춤: 모든 기준 7 이상 + lint 깨끗, 또는 3회. 3회 뒤 7 미만이면 회차별 점수와 원인(엔진 한계면 무엇이 필요한지)을 사용자에게 그대로 말한다.
4. 사용자에게 보여 줄 때는 비평용 한 장 + 회차별 점수표를 함께.

## 하지 말 것
- SVG 경로 · 좌표 · 키프레임 숫자를 직접 쓰기(scene.js 에 도형 그리기 포함).
- 레퍼런스 캐릭터 · 그림을 베끼거나 트레이스하기 — 화풍 카드의 숫자와 그림 문법만 가져온다.
- 그림체가 안 맞는데 "비슷해졌다"고 말하기 — 숫자로 말한다.
