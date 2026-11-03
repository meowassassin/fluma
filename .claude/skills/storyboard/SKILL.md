---
name: storyboard
description: 브리프·주제로 콘티 JSON을 새로 만들거나 전체를 다시 쓴다. 형식 결정 → 조사 확인 → 칸 채우기 → 검사 반복.
order: 1
---

# 콘티 작성

## 순서
1. **형식 결정**: `python3 scripts/decide.py "<주제>" [형식] [목표 초]` 로 형식·길이·장면 뼈대(JSON)를 받는다. 형식(광고|감성|시세|compare …)과 길이를 사용자가 말했으면 넘긴다 (주제 문장 규칙보다 우선). 해당 형식 스킬(`format-*`)이 있으면 그 규칙도 따른다.
2. **조사 확인**: `research/` 에 이 주제의 사실이 있는지 본다. 없으면 `research` 스킬 순서대로 먼저 조사한다. 출처 있는 사실 5개 미만이면 멈추고 사용자에게 알린다.
3. **작성**: `storyboards/<프로젝트 id>.json` 을 쓴다. 스키마 `schema/storyboard.schema.json`, 예시 `storyboards/example.json`.
   - `id` 는 프로젝트 id 그대로, `version: 1`, `sources` 에 쓴 사실의 URL. 대상 시청자를 알면 `audience`, 하단에 보일 이름이 있으면 `brand`.
   - 장면 sec 합계 = `duration_sec`. hook 3초, 마지막 3초.
   - 본문 장면마다 숫자 또는 고유명사 하나 (L11). 툴·현장·광고 형식은 본문 절반 이상이 실제 화면 (L12: screenshot/still/footage/price_tag/audio_demo).
   - 자막 28자·2줄 이하, 명사형·구어체. 나레이션은 초당 4~7자(공백 제외) — 3초 장면이면 12~18자.
   - 마지막 장면이 훅의 핵심어를 다시 말한다 (L08 루프).
   - **분위기**(예: "전문적이고 세련된")는 장면 구성 · 움직임 · 색 선택의 기준으로 `constraints` 에 한 줄 남긴다 → direct.py · compose 가 따른다.
   - **엔진은 Craft(기본)** — `engine: "craft"`. 장면에 보일 것은 아래 '장면 재료(materials)' 칸으로 적고, 제작은 produce 스킬이 한다. 아래 `elements`(kit · icon · manim · blender) 설명은 HyperFrames 엔진 전용이다.
   - **장면 설계 = 무엇을 어떤 순서로 보여 줄지**: (HyperFrames 엔진일 때) 장면마다 `elements` 에 필요한 시각 요소를 적는다(템플릿을 고르는 게 아니라 주제에 맞게 설계).
     예) AWS 배포 30초: 장면 1(5초) GitHub 에 코드 올리기 — `{"name":"GitHub 로고","source":"icon","cue":"GitHub"}`, `{"name":"코드 창","source":"kit"}`, `{"name":"푸시 화살표","source":"kit","cue":"올리면"}` …
     장면 3(8초) 빌드 결과물이 S3 로 — `{"name":"S3 버킷","source":"icon"}`, `{"name":"데이터 입자","what":"선을 따라 S3 로 흐름","source":"kit","cue":"S3"}` …
     · 글자 · 도형 · 연결선 · 다이어그램 · UI 는 `kit`(HyperFrames). 로고는 `icon`(scripts/icons.py). 정밀 도표 · 수식은 `manim`.
     · 3D 는 **움직여야 사는 개체 하나만** `blender`(회전하는 서버 · 반도체 칩 · 걷는 동물). 이미 만든 것이 있으면 `library`(+ `reuse`: `python3 scripts/element.py library` 로 확인) — 새로 만드는 건 없을 때만.
     · `cue` 는 그 요소가 나타나거나 움직이는 **나레이션 단어**. 화면은 이 단어 시각에 맞춰 움직인다(음성이 기준).
4. **검사**: `python3 scripts/lint.py storyboards/<id>.json` → 실패한 칸만 고친다. 통과할 때까지.
5. **음성 길이**(선택): `python3 scripts/assemble_audio.py storyboards/<id>.json` 후 다시 lint (L14).

## 레퍼런스가 없으면 — 형식 프리셋(사람이 편집한 실제 쇼츠에서 잰 숫자)
링크가 없어도 손으로 정한 기본값(가운데 판 · 고정 자막 · 직접 그린 표)으로 짜지 않는다 — 그게 'AI 틀'이다.
1. `python3 scripts/format_presets.py pick storyboards/<id>.json` — 주제 낱말로 형식(it-explainer · cooking · news · science · review)을 고르고 콘티 `preset` 에 숫자를 적는다. 맞지 않으면 `--format <형식>`.
2. 프리셋을 따른다: 장면 구성은 `preset.roles`(역할 비율) · `preset.screens`(화면 종류 비율), 컷 길이는 `preset.rhythm.shot_sec`, 말 주도인지 음악 주도인지는 `preset.lead`, 문장 끝은 `preset.tone.endings`.
3. 장면 `screen` 은 프리셋 화면 비율에 가깝게(T21 · T25). 그래픽(도표 · 글자 카드)은 프리셋에 그 비율이 있을 때만.
4. `direct.py --write` 는 프리셋에서 배치 · 바탕 · 자막 · 움직임을 정한다(무작위 아님). 검사 T27 = 프리셋 없음.

## 레퍼런스(참고 쇼츠 링크)가 있으면 — 구성 · 박자 · 말투는 레퍼런스 '채널', 내용은 사용자의 주제 (어떤 형식이든)
1. `python3 scripts/shorts_xray.py <id>` → `python3 scripts/ref_style.py <id>` → `python3 scripts/ref_channel.py <id> --n 5`
   (화면에서 분해하면 셋이 자동으로 이어 돈다. 채널 카드는 같은 채널 쇼츠 여러 편 — 한 편 통계보다 이쪽이 기준)
2. **채널 카드** `public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다. 형식을 가정하지 않는다 — 카드 맨 위 **형식** 줄(말 주도 / 음악 · 화면 주도, 주된 화면 종류, 컷 길이, 음악 박자)이 기준이다: 구성 · 구조(문장마다 역할[화면] 뼈대, 화면 종류 비율, 문장당 컷) ·
   문장 끝 비율 · 이음말 · 첫 · 끝 문장 · 영상별 대사. 대사 시트(`lines-<영상>.jpg`, #번호 = 대사 번호)를 **직접 보고**
   화면을 말로 비트는 농담 줄을 골라 `python3 scripts/ref_channel.py note <채널> --jokes <json>` 으로 카드에 확정한다
   (`[{"video": "<id>", "n": 12, "line": "…", "why": "화면의 컨테이너선을 말로 비틂"}]`).
3. **의도 카드부터**(콘티 `intent`): summary(누구에게 무엇을 어떤 느낌으로) · reference_use(레퍼런스에서 가져올 것 / 안 가져올 것) ·
   must · must_not · locked. 사용자에게 표로 보여 주고 '좋다'를 받으면 `python3 scripts/gate.py intent <id>`.
   **사용자 지적이 나올 때마다 must / must_not 에 한 줄씩 더한다**(기억이 아니라 이 영상의 규칙). 예: "직접 그린 2D · 이모지 금지(AI 티)", "강조는 빨간 네모 말고 스포트라이트".
4. 콘티 `reference: ["<id>"]`. 장면은 채널 뼈대의 **역할 순서**로 짜고 장면마다 `beat`(역할) · `screen`(화면 종류)을 적는다.
   - `screen` 은 채널 카드와 같은 갈래(실제 화면 · 기사 · 사람 · 실사 영상 · 제품 · 음식 · 짤 · 애니메이션 · 일러스트 · 카드(글자) · 도표 · 게임 화면 · 3D 그래픽 · 생성 영상)로 적고, 채널의 화면 비율에 가깝게(T21). 이야기하는 **대상 자체**가 먼저, 기사 캡처는 근거 한두 곳(L21).
   - 음악 · 화면 주도 채널이면 나레이션을 빼거나 아주 짧게, 컷을 채널의 컷 길이 · 음악 박자(BPM)에 맞춘다(T24).
   - 농담 박자(`beat: "joke"`)는 말 주도 · 한국어 채널에서 채널 빈도만큼 — 화면에 나온 그림을 말로 살짝 비틀거나 시청자에게 툭 던지는 한마디(T22).
   - 내용(사실 · 화면 · 짤)은 사용자의 주제로 새로. 레퍼런스의 대사 · 자막 · 그림을 베끼지 않는다.
   - 나레이션은 채널의 문장 끝 **비율대로 섞어**(한 어미로 몰지 않는다, T19) 이어 말하듯. 장면 = 문장이 아니어도 된다.
5. `python3 scripts/direct.py storyboards/<id>.json --write` — 카드의 방향 · 목소리(엔진 · 채널 말 속도 · 이어 말하기)를 적는다.
6. 검사: L21(기사 캡처 위주) · L18(움직임 minimal 인데 튀는 연출)은 실패, T19 · T21 · T22 는 권고 — 고칠지 판단해 알린다.
7. **시안 먼저(관문)**: 장면 1~3 만 짜서 `python3 scripts/render.py storyboards/<id>.json --draft --scenes 1-3` → 보여 주고
   '좋다'를 받으면 `python3 scripts/gate.py draft <id>`. 의도 · 시안 확인 없이는 최종 렌더 · 유료 생성이 막힌다(gate.py check).
   사용자가 확인하지 않았는데 gate.py intent · draft 를 스스로 부르지 않는다.

## 말투만 고쳐 달라고 하면 — 내용은 잠근다
"말투만 · 어미만 · 톤만" 요청은 문장을 새로 쓰지 않는다. 바꿀 글을 json(`{"4": "…"}`)으로 써서
`python3 scripts/tone_edit.py storyboards/<id>.json <json>` → 내용 낱말이 바뀌면 거절된다(어미 · 이음말 · 문장부호만 통과).
통과하면 `--apply`, 출력되는 전 · 후 표를 그대로 보여 준다. 사용자가 문장을 직접 불러 줬으면 `--apply --user-text`.

## 좋은 콘티의 기준 (rules/rulebook.md 4-2)
- 현장이 증거다. 숫자는 하나, 크게. 감정이 숫자를 운반한다. 제품이 스스로 증명하게.
- 한 편에 포인트 하나.

## 끝나면
바꾼 내용 한 줄 + 검사 결과 + 남은 결정(에셋 없음, 수치 미확인)을 질문 하나로.

## 화면은 영상마다 새로 (필수 — 콘티만 쓰고 끝내지 않는다)

콘티가 검사 · 음성까지 통과하면 **같은 턴에서 바로** compose 스킬(.claude/skills/compose/SKILL.md)로 이어간다:
1. `python3 scripts/direct.py storyboards/<id>.json --write` — 디자인 방향(최근 영상과 다르게). 장면은 모두 scene.js 가 그리고, 다른 엔진은 레이어 요소로만.
2. 그 방향대로 `compositions/<id>/scene.js` 를 짜고 정지 화면으로 확인.
3. `python3 scripts/lint.py` 에 L15(화면 구성 없음)가 남아 있으면 끝난 것이 아니다.

## 사용자가 올린 사진 · 영상이 있으면

<FLUMA_CONTEXT> 의 '올린 파일'을 먼저 본다. 실사 영상 · 사진이 있으면 그것을 증거 장면(L12)으로 쓴다: visual `kind: footage|still`, `asset: uploads/<id>/<파일>`, 영상은 `clip_start`(초)로 쓸 구간. 화면 구성(compose)에서 K.seq · K.image 로 편집한다.

## 마무리 — 유튜브 제목 · 설명 후보
콘티를 다 쓰고 검사를 통과하면, 답 끝에 화면이 버튼으로 바꿔 주는 두 블록을 붙인다(사용자가 눌러 콘티의 title · caption · hashtags 에 적용):
```titles 안에 제목 3안(서로 다른 훅 유형, 40자 이하, 해시태그 없이, 과장 금지) · ```desc 안에 설명(300자 이하, 첫 줄 한 줄 요약, 끝 줄 해시태그 3~5개).

## 장면 재료(materials) — Craft 엔진
장면에 '무엇이 필요한가'만 적는다. 툴 이름 · 좌표는 쓰지 않는다. 어느 Craft 앱이 만들지는 `crafts/*/craft.json` 의 provides 로 엔진이 정한다(`scripts/craft/materials.py`).
| type | 필드 | 만드는 앱 |
|---|---|---|
| chart | labels · values 또는 csv/xlsx(+range) · percent · kind(bar·line·pie) · title | GridCraft(데이터 · 계산) → 움직임 단계가 화풍 팔레트로 그림 |
| doc_quote | pdf · find(찾을 문장) | PdfCraft(문장 위치 + 페이지) → 확대 · 형광펜 |
| illustration | src(.svg — illustrate 스킬로 그린 것) · place | VectorCraft |
| photo | src · cutout | PhotoCraft(누끼) |
| screen · video · image | src | 그대로 |
공통: `id`, `cue`(등장할 낱말), `place`(full · center · left · right · top · bottom). 재료는 제목 아래 · 자막 위 구간에 놓인다.
숫자는 손으로 계산하지 말고 csv + percent 로 GridCraft 가 계산하게 한다.
