---
name: storyboard
description: 브리프·주제로 콘티 JSON을 새로 만들거나 전체를 다시 쓴다. 형식 결정 → 조사 확인 → 칸 채우기 → 검사 반복.
order: 1
---

# 콘티 작성

> 구성(다섯 기둥 · 박자 지도 · 리듬 계단)과 샷마다 연출(시선 한 곳 · 카메라 이유 · 세 가지 구체 · 끝 그림)은 **director 스킬**대로 정한다(`direction.anchors`, 장면 `shot_fn`).
> **콘티를 쓴 뒤 각본가 · 감독 자리에서 한 번 더**: `python3 engine/story/review.py data/storyboards/<id>.json` — 레퍼런스 X-ray 수치(샷 중앙값 · 말 덩어리 · 초당 글자)와
> 견준 위반, 레퍼런스의 말 박자, 내 대본을 구절로 쪼갠 표가 한 장에 나온다. 이것만 보고 대사 · 화면 리듬을 고친다. lint 가 막는 것:
> **L50** 장면 안에서 화면이 레퍼런스 샷 중앙값의 2배 넘게 그대로(문장마다 cue 로 재료를 바꾸거나 장면을 쪼갠다 · 일부러 길게면 `long_take: "이유"`)
> · **L51** 한숨에 말하기 긴 구절 · **L52** 접속어로 시작하는 문장이 1/3 넘음(강의체) · **L53** 가상 앱 화면은 Astryx 장면(`ui_mock` 에 `"ui": "…/ui/<이름>.tsx"`).
> 나레이션은 장면마다 따로 쓰지 말고 콘티 맨 위 `script` 에 한 덩어리로(장면 경계만 ` / `) — 엔진이 장면에 나눠 넣는다(writer 0장). 나레이션 · 대사 · caption · 화면 글자는 **writer 스킬**의 규칙(훅 세 칸 · 말 밑의 행동 · AI 티 금지 · `[필요: 근거]`)으로 쓴다.

## 순서
1. **형식 결정**: `python3 engine/story/decide.py "<주제>" [형식] [목표 초]` 로 형식 · 길이와 그 형식의 **흔한 구조**(JSON `scenes`)를 받는다. 흔한 구조는 뼈대가 아니라 뻔함 지도 후보다 — 장면 흐름은 고른 콘셉트(`concept.structure`)를 따른다. 형식(광고|감성|시세|compare …)과 길이를 사용자가 말했으면 넘긴다 (주제 문장 규칙보다 우선). 해당 형식 스킬(`format-*`)이 있으면 그 규칙도 따른다.
2. **조사 확인**: `data/research/` 에 이 주제의 사실이 있는지 본다. 없으면 `research` 스킬 순서대로 먼저 조사한다. 출처 있는 사실 5개 미만이면 멈추고 사용자에게 알린다.
3. **영상마다 다르게 — 쓰기 전에 정한다**(검사 L66 · L67 · L68 이 막는다): `concept` 에 `angle`(각도) · `breaks`(이 주제 쇼츠가 다들 하는 것 중 깨는 것) · `structure`(장면 흐름 한 줄 — 최근 영상과 다른 흐름: 사건 재구성 · 질문→실험→반전 · 저울 비교 · 시간 순 · 오해→진실 …), `direction.art` 에 `palette{bg, ink, accent}` · `rule` · `avoid` · `style`(그림 화풍: flat · cel · sketch · clay — 최근 영상과 다르게). `hook → item × N → outro` 는 최근에 너무 많이 썼다.
   **작성**: `data/storyboards/<프로젝트 id>.json` 을 쓴다. 스키마 `engine/spec/schema/storyboard.schema.json`, 예시 `engine/spec/examples/storyboard.example.json`. **스키마 · 엔진 코드를 열어 칸을 찾지 않는다** — 예시를 복사해 고치고, 모르는 칸은 lint 메시지가 알려 준다(2026-11-16: 스키마 · 코드 찾기에 3분).
   **한 영상에 요점 하나 — 40초 이하(비교 · 순위 45초) · 장면 9개 이하**(L70, produce 가 대본 단계 전에 막는다). 곁가지(두 번째 언어 · 설정법 · 도구)는 다음 영상으로.
   사용자가 **길어도 된다**고 했으면 억지로 줄이지 말고 콘티에 `"allow_long": true`(90초 · 12장면까지) — 설명이 빠지면 이해가 깨진다(2026-11-17).
   **콘티는 한 번에 통째로 Write** 한다 — 같은 콘티를 Edit 로 여러 번 나눠 고치지 않는다(2026-11-17: Edit 17번 연달아 ≈ 10분). 고칠 곳이 여러 장면이면 전체를 다시 쓴다.
   2D 장면은 `screen: "애니메이션 · 일러스트"` + `visual.kind`(compare · list · number · diff · code · text …) + 재료 `type: craft`(craft-2d 예시). 실제 화면을 쓰는 장면만 `screen: "실제 화면"` + 증거 재료(web · screen · doc_quote). 감독 다섯 기둥은 `direction.anchors`, 고른 2D 표현은 `direction.explainer`.
   - `id` 는 프로젝트 id 그대로, `version: 1`, `sources` 에 쓴 사실의 URL. 대상 시청자를 알면 `audience`, 하단에 보일 이름이 있으면 `brand`.
   - 장면 sec 합계 = `duration_sec`. hook 3초, 마지막 3초.
   - 본문 장면마다 숫자 또는 고유명사 하나 (L11). 툴·현장·광고 형식은 본문 절반 이상이 실제 화면 (L12: screenshot/still/footage/price_tag/audio_demo).
   - 자막 28자·2줄 이하, 명사형·구어체. 나레이션은 초당 4~7자(공백 제외) — 3초 장면이면 12~18자.
   - 마지막 장면이 훅의 핵심어를 다시 말한다 (L08 루프).
   - **개념 사다리**(writer 0.3): 콘티 맨 위 `concepts_order` 에 시청자가 모르는 개념을 나오는 순서대로 적고, 장면마다 새 개념은 하나만 소개한 뒤 쓴다. 제작 때 시청자 시뮬레이션이 대상 시청자로 따라가 보고, 장면을 더해야 풀리는 문제가 있으면 제작을 멈춘다.
   - **증거 재료(L59~L63)**: 본문 장면은 카드·도표·mock 목업만으로 채우지 않는다 — `web` · `screen` · `photo` · `icon`(icons.py) · `doc_quote` 중 최소 하나. 장면에 `info_card`+`diagram` 동시 금지(L60). `screen: 실제 화면`이면 증거 재료 필수(L61). mock `ui_mock` 단독 금지(L62). produce 전 `material_evidence.py`가 브랜드 로고를 자동 보강할 수 있으나 web/캡처는 콘티에 써 둔다.
   - **분위기**(예: "전문적이고 세련된")는 `constraints` 에 한 줄 남긴다(사람 · 비평용 — 엔진은 글을 해석하지 않는다). **엔진이 꼭 지켜야 하는 금지**는 `intent.ban` 에 값으로: `number_punch`(숫자 크게 덧씌우기) · `sfx` · `music` · `bg_motion`.
   - 화면 글자 `caption` 은 나레이션이 있어도 위쪽 띠에 강조색으로 따로 나온다(훅 세 칸의 '화면 글자' — 말을 받아 적지 않는다). 끄려면 `direction.screen_text: false`.
   - **엔진은 Craft 하나** — `engine: "craft"`. 장면에 보일 것은 아래 '장면 재료(materials)' 칸으로 적고, 제작은 produce 스킬이 한다(HyperFrames · Manim 은 제거).
   - **장면 설계 = 무엇을 어떤 순서로 보여 줄지**: 장면마다 필요한 재료를 주제에 맞게 설계한다(템플릿 고르기 아님). 로고는 `icon`(engine/capture/icons.py), 정밀 도표는 `chart` · `diagram`, 3D 제품은 `model3d`(SolidCraft 제품 형태 — crafts 스킬). 실사 장면은 실제 자료(퍼온 클립 `clip.py` · 무료 스톡 `stock` · 자료 사진 `relic`)로.
     · `cue` 는 그 요소가 나타나거나 움직이는 **나레이션 단어**. 화면은 이 단어 시각에 맞춰 움직인다(음성이 기준).
4. **쓰기 + 검사는 한 번에(2026-11-19 속도)**: 콘티 · 형태(`forms/*.json`, 움직임은 미리 anim) · 조사 사실을 묶음 JSON 하나로 써서 `python3 engine/story/bundle.py apply <묶음.json> --write-scenes` — 저장 → 장면 코드(`scenes/sNN.jsx`)를 장면마다 동시에 작성(장면마다 `bg` · `visual.primary`(무엇을 어떻게 보여 줄지 구체적으로) · `shot_fn` · 필요하면 `carry` 를 적어 둔다) → 모든 검사(L · 화면 AI 티 V · 형태)를 음성 전에 돌려 막힘을 한꺼번에 보여 준다. 막힌 장면만 `scenes.py write <id> --scenes N --note "…"`. 막힘을 모두 고쳐 묶음을 다시 apply(한 칸씩 고치고 검사 반복 금지). 따로 쓸 때는 `python3 engine/checks/lint.py data/storyboards/<id>.json` → L 규칙 없을 때까지. 통과 시 `production_ready: true` 가 콘티에 찍힌다(lint가 기록 · 또는 `python3 engine/story/production_ready.py data/storyboards/<id>.json`).
5. **오븐 전 마무리**: ui_mock 에 `ui: data/compositions/<id>/ui/….tsx` 가 있으면 채팅에서 TSX를 쓰고 build는 produce가 병렬로 — produce 안 designer Astryx Agent 는 **ui 없거나 L53일 때만**.
6. **음성 길이**(선택): `python3 engine/voice/assemble_audio.py data/storyboards/<id>.json` 후 다시 lint (L14).

## 레퍼런스(참고 쇼츠 링크)가 있으면 — 구성 · 박자 · 말투는 레퍼런스 '채널', 내용은 사용자의 주제 (어떤 형식이든)
1. `python3 engine/research/analyze_ref.py <id1> <id2> <id3>` — **여러 편은 한 명령에 모두 넘긴다(동시에 돈다 · 한 편씩 반복해 부르지 말 것)**. 빠른 분해 → 스타일을 서버 작업으로 이어 돌린다(편당 1분 안팎 · 턴이 끝나도 계속 · 끝난 단계는 건너뜀). 채널 말투 카드가 필요할 때만 `--channel 3`.
   (채널 카드는 같은 채널 쇼츠 여러 편 — 한 편 통계보다 이쪽이 기준. 스크립트를 직접 백그라운드로 돌리지 않는다)
2. **채널 카드** `data/public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다. 형식을 가정하지 않는다 — 카드 맨 위 **형식** 줄(말 주도 / 음악 · 화면 주도, 주된 화면 종류, 컷 길이, 음악 박자)이 기준이다: 구성 · 구조(문장마다 역할[화면] 뼈대, 화면 종류 비율, 문장당 컷) ·
   문장 끝 비율 · 이음말 · 첫 · 끝 문장 · 영상별 대사. 대사 시트(`lines-<영상>.jpg`, #번호 = 대사 번호)를 **직접 보고**
   화면을 말로 비트는 농담 줄을 골라 `python3 engine/research/ref_channel.py note <채널> --jokes <json>` 으로 카드에 확정한다
   (`[{"video": "<id>", "n": 12, "line": "…", "why": "화면의 컨테이너선을 말로 비틂"}]`).
3. **의도 카드부터**(콘티 `intent`): summary(누구에게 무엇을 어떤 느낌으로) · reference_use(레퍼런스에서 가져올 것 / 안 가져올 것) ·
   must · must_not · locked. 사용자에게 표로 보여 주고 바로 진행한다(확인을 기다리지 않음).
   **사용자 지적이 나올 때마다 must / must_not 에 한 줄씩 더한다**(기억이 아니라 이 영상의 규칙). 예: "직접 그린 2D · 이모지 금지(AI 티)", "강조는 빨간 네모 말고 스포트라이트".
4. 콘티 `reference: ["<id>"]`. 장면은 채널 뼈대의 **역할 순서**로 짜고 장면마다 `beat`(역할) · `screen`(화면 종류)을 적는다.
   - `screen` 은 채널 카드와 같은 갈래(실제 화면 · 기사 · 사람 · 실사 영상 · 제품 · 음식 · 짤 · 애니메이션 · 일러스트 · 카드(글자) · 도표 · 게임 화면 · 3D 그래픽)로 적고, 채널의 화면 비율에 가깝게(T21). 이야기하는 **대상 자체**가 먼저, 기사 캡처는 근거 한두 곳(L21).
   - 음악 · 화면 주도 채널이면 나레이션을 빼거나 아주 짧게, 컷을 채널의 컷 길이 · 음악 박자(BPM)에 맞춘다(T24).
   - 농담 박자(`beat: "joke"`)는 말 주도 · 한국어 채널에서 채널 빈도만큼 — 화면에 나온 그림을 말로 살짝 비틀거나 시청자에게 툭 던지는 한마디(T22).
   - 내용(사실 · 화면 · 짤)은 사용자의 주제로 새로. 레퍼런스의 대사 · 자막 · 그림을 베끼지 않는다.
   - 나레이션은 채널의 문장 끝 **비율대로 섞어**(한 어미로 몰지 않는다, T19) 이어 말하듯. 장면 = 문장이 아니어도 된다.
5. `python3 engine/story/direct.py data/storyboards/<id>.json --write` — 카드의 방향 · 목소리(엔진 · 채널 말 속도 · 이어 말하기)를 적는다.
6. 검사: L21(기사 캡처 위주) · L18(움직임 minimal 인데 튀는 연출)은 실패, T19 · T21 · T22 는 권고 — 고칠지 판단해 알린다.
7. **바로 제작**: 검사를 통과하면 produce 스킬로 초안까지 이어서 만든다. 그 뒤 고치는 것은 값으로(`knob.py`) — 승인 · 관문 기록은 없다.

## 화면 글(고정 제목 · 자막 · 말풍선 · 카드 글) — 사람이 실제로 쓰는 말로
2026-11-04: "내 API가 느린 이유, 반복문 안에 있다" · "해결은 셋" · "주문 1번 + 회원 100번 = 쿼리 101번" 이 어색하다는 지적.
- 번역투 · 신문 제목투를 쓰지 않는다: "~하는 이유, ~에 있다" · "~의 정체" 대신 시청자가 검색 · 공감할 말(예: "JPA N+1, 쿼리가 101번 나간 이유")
- 말풍선은 그 사람이 메신저에 실제로 칠 문장으로: 명사로 끊지 않고("해결은 셋" ✗ → "고치는 방법은 세 가지야"), 수식 기호(= · + · →)를 문장 대신 쓰지 않는다
- 기술 낱말은 실무자가 부르는 이름 그대로(member · getMember() · fetch join), 풀이는 괄호로 한 번만
- 다 쓰면 화면 글만 모아 소리 내 읽어 본다 — 한 줄이라도 사람이 안 할 말이면 고친다. 고정 제목은 24자 이내

## 좋은 콘티의 기준 (engine/spec/rules/rulebook.md 4-2)
- 현장이 증거다. 숫자는 하나, 크게. 감정이 숫자를 운반한다. 제품이 스스로 증명하게.
- 한 편에 포인트 하나.

## 끝나면
바꾼 내용 한 줄 + 검사 결과 + 남은 결정(에셋 없음, 수치 미확인)을 질문 하나로.

## 더 보기(필요할 때만 읽는다)
`.claude/skills/storyboard/reference.md` — **장면 재료(materials) 칸 · 예시 JSON**(재료를 처음 쓰거나 칸이 헷갈릴 때), 레퍼런스가 없을 때 형식 프리셋, 말투만 고치기, 사용자 사진 · 영상, 유튜브 제목 · 설명.
