---
name: storyboard
description: 브리프·주제로 콘티 JSON을 새로 만들거나 전체를 다시 쓴다. 형식 결정 → 조사 확인 → 칸 채우기 → 검사 반복.
order: 1
---

# 콘티 작성

## 순서
1. **형식 결정**: `python3 engine/story/decide.py "<주제>" [형식] [목표 초]` 로 형식 · 길이와 그 형식의 **흔한 구조**(JSON `scenes`)를 받는다. 흔한 구조는 뼈대가 아니라 뻔함 지도 후보다 — 장면 흐름은 고른 콘셉트(`concept.structure`)를 따른다. 형식(광고|감성|시세|compare …)과 길이를 사용자가 말했으면 넘긴다 (주제 문장 규칙보다 우선). 해당 형식 스킬(`format-*`)이 있으면 그 규칙도 따른다.
2. **조사 확인**: `data/research/` 에 이 주제의 사실이 있는지 본다. 없으면 `research` 스킬 순서대로 먼저 조사한다. 출처 있는 사실 5개 미만이면 멈추고 사용자에게 알린다.
3. **작성**: `data/storyboards/<프로젝트 id>.json` 을 쓴다. 스키마 `engine/spec/schema/storyboard.schema.json`, 예시 `data/storyboards/example.json`.
   - `id` 는 프로젝트 id 그대로, `version: 1`, `sources` 에 쓴 사실의 URL. 대상 시청자를 알면 `audience`, 하단에 보일 이름이 있으면 `brand`.
   - 장면 sec 합계 = `duration_sec`. hook 3초, 마지막 3초.
   - 본문 장면마다 숫자 또는 고유명사 하나 (L11). 툴·현장·광고 형식은 본문 절반 이상이 실제 화면 (L12: screenshot/still/footage/price_tag/audio_demo).
   - 자막 28자·2줄 이하, 명사형·구어체. 나레이션은 초당 4~7자(공백 제외) — 3초 장면이면 12~18자.
   - 마지막 장면이 훅의 핵심어를 다시 말한다 (L08 루프).
   - **분위기**(예: "전문적이고 세련된")는 장면 구성 · 움직임 · 색 선택의 기준으로 `constraints` 에 한 줄 남긴다 → direct.py · 움직임 단계가 따른다.
   - **엔진은 Craft 하나** — `engine: "craft"`. 장면에 보일 것은 아래 '장면 재료(materials)' 칸으로 적고, 제작은 produce 스킬이 한다(HyperFrames · Manim 은 제거).
   - **장면 설계 = 무엇을 어떤 순서로 보여 줄지**: 장면마다 필요한 재료를 주제에 맞게 설계한다(템플릿 고르기 아님). 로고는 `icon`(engine/capture/icons.py), 정밀 도표는 `chart` · `diagram`, 3D 제품은 `model3d`(곡면 · 캐릭터 · 영화 품질은 `"method": "blender"`, crafts 스킬). 실사 장면은 실제 자료(퍼온 클립 `clip.py` · 무료 스톡 `stock` · 자료 사진 `relic`)로.
     · `cue` 는 그 요소가 나타나거나 움직이는 **나레이션 단어**. 화면은 이 단어 시각에 맞춰 움직인다(음성이 기준).
4. **검사**: `python3 engine/checks/lint.py data/storyboards/<id>.json` → 실패한 칸만 고친다. 통과할 때까지.
5. **음성 길이**(선택): `python3 engine/voice/assemble_audio.py data/storyboards/<id>.json` 후 다시 lint (L14).

## 레퍼런스가 없으면 — 형식 프리셋(사람이 편집한 실제 쇼츠에서 잰 숫자)
링크가 없어도 손으로 정한 기본값(가운데 판 · 고정 자막 · 직접 그린 표)으로 짜지 않는다 — 그게 'AI 틀'이다.
1. `python3 engine/research/format_presets.py pick data/storyboards/<id>.json` — 주제 낱말로 형식(it-explainer · cooking · news · science · review)을 고르고 콘티 `preset` 에 숫자를 적는다. 맞지 않으면 `--format <형식>`.
2. 프리셋을 따른다: 장면 구성은 `preset.roles`(역할 비율) · `preset.screens`(화면 종류 비율), 컷 길이는 `preset.rhythm.shot_sec`, 말 주도인지 음악 주도인지는 `preset.lead`, 문장 끝은 `preset.tone.endings`.
3. 장면 `screen` 은 프리셋 화면 비율에 가깝게(T21 · T25). 그래픽(도표 · 글자 카드)은 프리셋에 그 비율이 있을 때만.
4. `direct.py --write` 는 프리셋에서 배치 · 바탕 · 자막 · 움직임을 정한다(무작위 아님). 검사 T27 = 프리셋 없음.

## 레퍼런스(참고 쇼츠 링크)가 있으면 — 구성 · 박자 · 말투는 레퍼런스 '채널', 내용은 사용자의 주제 (어떤 형식이든)
1. `python3 engine/research/analyze_ref.py <id> --n 5` — 분해 → 스타일 → 채널을 서버 작업으로 이어 돌린다(턴이 끝나도 계속 · 끝난 단계는 건너뜀).
   (채널 카드는 같은 채널 쇼츠 여러 편 — 한 편 통계보다 이쪽이 기준. 스크립트를 직접 백그라운드로 돌리지 않는다)
2. **채널 카드** `data/public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다. 형식을 가정하지 않는다 — 카드 맨 위 **형식** 줄(말 주도 / 음악 · 화면 주도, 주된 화면 종류, 컷 길이, 음악 박자)이 기준이다: 구성 · 구조(문장마다 역할[화면] 뼈대, 화면 종류 비율, 문장당 컷) ·
   문장 끝 비율 · 이음말 · 첫 · 끝 문장 · 영상별 대사. 대사 시트(`lines-<영상>.jpg`, #번호 = 대사 번호)를 **직접 보고**
   화면을 말로 비트는 농담 줄을 골라 `python3 engine/research/ref_channel.py note <채널> --jokes <json>` 으로 카드에 확정한다
   (`[{"video": "<id>", "n": 12, "line": "…", "why": "화면의 컨테이너선을 말로 비틂"}]`).
3. **의도 카드부터**(콘티 `intent`): summary(누구에게 무엇을 어떤 느낌으로) · reference_use(레퍼런스에서 가져올 것 / 안 가져올 것) ·
   must · must_not · locked. 사용자에게 표로 보여 주고 '좋다'를 받으면 `python3 engine/checks/gate.py intent <id>`.
   **사용자 지적이 나올 때마다 must / must_not 에 한 줄씩 더한다**(기억이 아니라 이 영상의 규칙). 예: "직접 그린 2D · 이모지 금지(AI 티)", "강조는 빨간 네모 말고 스포트라이트".
4. 콘티 `reference: ["<id>"]`. 장면은 채널 뼈대의 **역할 순서**로 짜고 장면마다 `beat`(역할) · `screen`(화면 종류)을 적는다.
   - `screen` 은 채널 카드와 같은 갈래(실제 화면 · 기사 · 사람 · 실사 영상 · 제품 · 음식 · 짤 · 애니메이션 · 일러스트 · 카드(글자) · 도표 · 게임 화면 · 3D 그래픽)로 적고, 채널의 화면 비율에 가깝게(T21). 이야기하는 **대상 자체**가 먼저, 기사 캡처는 근거 한두 곳(L21).
   - 음악 · 화면 주도 채널이면 나레이션을 빼거나 아주 짧게, 컷을 채널의 컷 길이 · 음악 박자(BPM)에 맞춘다(T24).
   - 농담 박자(`beat: "joke"`)는 말 주도 · 한국어 채널에서 채널 빈도만큼 — 화면에 나온 그림을 말로 살짝 비틀거나 시청자에게 툭 던지는 한마디(T22).
   - 내용(사실 · 화면 · 짤)은 사용자의 주제로 새로. 레퍼런스의 대사 · 자막 · 그림을 베끼지 않는다.
   - 나레이션은 채널의 문장 끝 **비율대로 섞어**(한 어미로 몰지 않는다, T19) 이어 말하듯. 장면 = 문장이 아니어도 된다.
5. `python3 engine/story/direct.py data/storyboards/<id>.json --write` — 카드의 방향 · 목소리(엔진 · 채널 말 속도 · 이어 말하기)를 적는다.
6. 검사: L21(기사 캡처 위주) · L18(움직임 minimal 인데 튀는 연출)은 실패, T19 · T21 · T22 는 권고 — 고칠지 판단해 알린다.
7. **시안 먼저(관문)**: 장면 1~3 만 짜서 `python3 engine/render.py data/storyboards/<id>.json --draft --scenes 1-3` → 보여 주고
   '좋다'를 받으면 `python3 engine/checks/gate.py draft <id>`. 의도 · 시안 확인 없이는 최종 렌더 이 막힌다(gate.py check).
   사용자가 확인하지 않았는데 gate.py intent · draft 를 스스로 부르지 않는다.

## 화면 글(고정 제목 · 자막 · 말풍선 · 카드 글) — 사람이 실제로 쓰는 말로
2026-11-04: "내 API가 느린 이유, 반복문 안에 있다" · "해결은 셋" · "주문 1번 + 회원 100번 = 쿼리 101번" 이 어색하다는 지적.
- 번역투 · 신문 제목투를 쓰지 않는다: "~하는 이유, ~에 있다" · "~의 정체" 대신 시청자가 검색 · 공감할 말(예: "JPA N+1, 쿼리가 101번 나간 이유")
- 말풍선은 그 사람이 메신저에 실제로 칠 문장으로: 명사로 끊지 않고("해결은 셋" ✗ → "고치는 방법은 세 가지야"), 수식 기호(= · + · →)를 문장 대신 쓰지 않는다
- 기술 낱말은 실무자가 부르는 이름 그대로(member · getMember() · fetch join), 풀이는 괄호로 한 번만
- 다 쓰면 화면 글만 모아 소리 내 읽어 본다 — 한 줄이라도 사람이 안 할 말이면 고친다. 고정 제목은 24자 이내

## 말투만 고쳐 달라고 하면 — 내용은 잠근다
"말투만 · 어미만 · 톤만" 요청은 문장을 새로 쓰지 않는다. 바꿀 글을 json(`{"4": "…"}`)으로 써서
`python3 engine/story/tone_edit.py data/storyboards/<id>.json <json>` → 내용 낱말이 바뀌면 거절된다(어미 · 이음말 · 문장부호만 통과).
통과하면 `--apply`, 출력되는 전 · 후 표를 그대로 보여 준다. 사용자가 문장을 직접 불러 줬으면 `--apply --user-text`.

## 좋은 콘티의 기준 (engine/spec/rules/rulebook.md 4-2)
- 현장이 증거다. 숫자는 하나, 크게. 감정이 숫자를 운반한다. 제품이 스스로 증명하게.
- 한 편에 포인트 하나.

## 끝나면
바꾼 내용 한 줄 + 검사 결과 + 남은 결정(에셋 없음, 수치 미확인)을 질문 하나로.

## 화면은 영상마다 새로 (필수 — 콘티만 쓰고 끝내지 않는다)

콘티가 검사를 통과하면 **같은 턴에서 바로** produce 스킬로 이어간다:
1. `python3 engine/story/direct.py data/storyboards/<id>.json --write` — 디자인 방향(최근 영상과 다르게 · 레퍼런스 톤).
2. `python3 engine/produce.py data/storyboards/<id>.json` — 음성 → 검사 → 초안 → 장면별 정지 화면. 정지 화면을 보고 고칠 곳만 고친다.

## 사용자가 올린 사진 · 영상이 있으면

<FLUMA_CONTEXT> 의 '올린 파일'을 먼저 본다. 실사 영상 · 사진이 있으면 그것을 증거 장면(L12)으로 쓴다: visual `kind: footage|still`, `asset: uploads/<id>/<파일>`, 영상은 `clip_start`(초)로 쓸 구간. 재료(`video` · `photo` · `image`, 이름에 재료 id)로 넣는다.

## 마무리 — 유튜브 제목 · 설명 후보
콘티를 다 쓰고 검사를 통과하면, 답 끝에 화면이 버튼으로 바꿔 주는 두 블록을 붙인다(사용자가 눌러 콘티의 title · caption · hashtags 에 적용):
```titles 안에 제목 3안(서로 다른 아이디어 — `concept.cliches` 의 제목 패턴을 피하고 이 영상의 한 방이 보이게, 40자 이하, 해시태그 없이, 과장 금지) · ```desc 안에 설명(300자 이하, 첫 줄 한 줄 요약, 끝 줄 해시태그 3~5개).

## 장면 재료(materials) — Craft 엔진
장면에 '무엇이 필요한가'만 적는다. 툴 이름 · 좌표는 쓰지 않는다. 어느 Craft 앱이 만들지는 `engine/craft/apps/*/craft.json` 의 provides 로 엔진이 정한다(`engine/craft/materials.py`).
| type | 필드 | 만드는 앱 |
|---|---|---|
| chart | labels · values 또는 csv/xlsx(+range) · percent · kind(bar·line·pie) · title | GridCraft(데이터 · 계산) → 움직임 단계가 화풍 팔레트로 그림 |
| doc_quote | pdf · find(찾을 문장) | PdfCraft(문장 위치 + 페이지) → 확대 · 형광펜 |
| illustration | src(.svg — illustrate 스킬로 그린 것) · place | VectorCraft |
| photo | src · cutout | PhotoCraft(누끼) |
| screen · video · image | src | 그대로 |
| web | src(data/public/elements/<id>/<이름> — webrec.py · termrec.py 녹화) · holds(상태별 초) · start(나레이션 없을 때 시작 초) | 그대로(실제 화면) |
| stock | query(영어 검색어) · min_sec · pick · trim | Pexels → Pixabay 무료 스톡 영상(실제 촬영) — 일상 · 감성 · 광고의 바탕. 키는 설정 → API 키. 기술 설명에는 쓰지 않는다(실제 화면 우선) |
| overlay | target(같은 장면의 **앞선** 그림 · 화면 재료 id) · marks[{kind: box·arrow·label, box:[x,y,w,h] 0~1(대상 기준), from/to(화살표), text, cue}] · style(clean·hand) · color | VectorCraft(투명 주석 층) → 대상 위 제자리에 cue 마다 하나씩 |
| ui_mock | src(실제 캡처) · device(phone·browser, 생략하면 모양으로) · url. 캡처가 없을 때만 screen{…} + **mock: true** | FigCraft(폰 · 브라우저 틀 + 그림자) |
| diagram | kind(steps·compare·cycle·hierarchy·pyramid·timeline·list) · items(탭=하위) · title · cues(항목별 낱말) | DeckCraft(SmartArt, 항목 층이 차례로 등장) |
| document | src(.docx·.md·.txt …) 또는 title + text · highlight[문장] · track{from,to}(바뀐 부분) · comments[{at,text}] | WordCraft(9:16 문서 화면 · 진짜 형광펜 · 변경 추적) |
| photo_grade | src · look(warm·film·clean·mono) · crop(9:16) · focus[x,y] · credit | LightCraft(현상 · 톤 통일 · 세로 자르기) |
| info_card | kicker · title · body · points[] · source (또는 rows[] · csv + row) · frame(card·full) · theme | DesignCraft(정보 카드, 여러 장 병합) |
| template_card | template(.vectorcraft, 없으면 기본 틀) · csv 또는 values{머리글: 값} · row | VectorCraft(변수 + CSV 일괄 — 매일 같은 틀) |
| thumbnail | (비우면 콘티 title · badge · hook_number) · title · hook · emphasis · src(false 면 글자만) | DesignCraft(세로 1080×1920 + 가로 1280×720). **영상 화면이 아니라 표지용** — 마지막 장면에 두고 화면에는 거의 안 보이게 |
| model3d | shape(case·phone·bottle·tumbler·puck) + size(mm) 또는 commands 또는 src(.step·.stl·.obj …) · material(metal·plastic·wood·#색·{부품:재질}) · color · logo · turntable 또는 exploded · sec | SolidCraft(형태 · 분해도) + TextureCraft(재질 · 로고 · 렌더) — 9:16 화면 전체(배경 포함) |
| live | src(실사 영상) · cuts{이름: {strokes[{frame, kind: fg\|bg, points(이어진 한 획), radius}], span, recolor{hue, sat, light}, remove, frame, grow}} · items[{id, kind: model3d(script · at · frame · height · shadow · light · behind)\|text(text · follow · offset · size · color · behind)\|image(file · follow · offset · scale · behind)}] — follow 는 {at, frame}(장면 고정) · {at, frame, moving}(움직이는 무늬) · {cut, at: top\|center}(분리한 물체). 3D 스크립트는 `L = F.live(ctx)` 로 시작하고 `L["at"]` · `ctx.args["height"] * L["unit"]` 로 놓는다. 끝나면 `cuts.check.png` 로 매트를 본다 — 완전히 가려지면 분리가 끊기므로 가려졌다 나오는 물체는 나온 직후 프레임에 획을 더한다. |
| form | 화면 형식 라이브러리 — `form`: parchment(title · body) · atlas(bbox · route · marks · mountains, 실제 지형) · gridchart(bars · max) · comic(panels 2~4) · sunset(stops) · halftone(image · scale · dy). 영상마다 그림 코드를 쓰지 않는다 |
| archive | 실제 사진 · 그림 — `title`("File:…", `engine/capture/commons.py search` 로 찾아 보고 고른다) · fit(cover\|contain). 출처는 자동으로 sources 에 들어간다. 실제 자료가 있는 사실은 재현하지 말고 진짜를 쓴다 |
| video + gen | 실사 생성 컷(사용자가 plan 0.5턴에서 고른 경우만): `gen`(영상 모델 seedance · kling · veo · omni · hailuo · runway · wan) · `image_model`(키프레임: seedream · nanobanana · gptimage · midjourney) · `prompt`(영어, 무엇이 일어나는가) · camera · framing · setting · cast · line · people · gen_sec | 프롬프트만 — 사용자가 그림 → 영상을 만들어 올림(engine/gen/genclip.py). 콘티 최상위 `cast` 로 인물 일관성 |
| figure | **인물의 기본 경로** — Blender 인체(근육 · 손 · 발)에 자세 · 복장을 입혀 화풍으로 한 획씩 그린다. `kit`(고대: hoplite · messenger · elder · pan / 현대: office · scientist · worker · casual / 또는 복장 목록: shirt · tshirt · jacket · coat · trousers · shoes · shorthair · glasses · tunic · cuirass · helmet · horns · goatlegs …) · `hands`({"L","R"}: open · relax · loose · grip · point — 생략하면 자세에 맞게) · `hair_tone`(머리 밝기) · `pose`(thrust · stand · point · collapse · 조준 사전) · `anim`(still · sketch_in · run) · `style`(engrave · sketch · woodcut · wash · blackfigure · inkline(잡지 삽화 선화) · pop(망점 팝), 생략하면 주제 · 장면 · 이력으로 고른다) · `style_params`(density · line · contrast · angle · ink · paper · tint · fill · dot: 화풍을 자유롭게 변주) · `show:false`. `on_screen`(화면 높이 px — 작으면 가는 화풍은 사라지므로 굵은 화풍 · 선으로 바꾼다) · **화풍은 영상마다, 필요하면 장면마다 다르게 고른다** — 주제의 시대 · 감정, 장면 형식과 어울리는 것을 정하고 `direction.art.figure` 또는 재료 `style` 로 적는다. 화면에는 motion-figure |
| relic | 실제 유물 · 조각 자체가 이야기일 때만 — 그래픽 장면 위 인물 대용으로 쓰지 않는다(사진이 겉돈다). — 실제 조각 · 흉상 · 도기 사진을 오린 컷아웃. `src`(archive 로 받은 파일) · `crop` · `cut`(matte · shard: PhotoCraft 작업, 레이어 PSD 가 남음 / ink 도기 안료 / none) · `matte:"ai"`(배경이 복잡해 Select Subject 가 옆 인물까지 잡을 때) · `keep` · `erase` · `jaw`(poly: 수염 · 턱 결을 따라 / mouth: 입술 틈 / hinge) · `width` · `show: false`. 말하는 인물은 id 하나에 `jaw` 를 적고 motion-relic 레시피(S0 · S1 말 구간, 경첩 · 목 px)로 놓는다. 그림 확대 격자로 poly 를 잡고 렌더해서 본다. 말하지 않는 인물은 `<인물>_<자세><번호>` 로 motion-cast |
| art | 직접 그린 인물 · 소품 — `svg`(illustrate 스킬로 그린 파일) · `hide`(지울 표정 그룹) · `show: false`. 표정마다 재료 하나, id 는 `<인물>_<자세><번호>`. 화면에는 motion-cast 레시피 |
| silhouette | 작은 전신 달리기(도기풍 검은 실루엣 8칸) — 지도 위 · 먼 풍경 |
| cast | 실험 — 주인공에 쓰지 않는다. 사양 조립 인물은 어색하고 복장이 틀린다. 인물은 illustrate 스킬로 직접 그린다. 멀리 있는 군중 · 작은 실루엣에만 |
| drawing | src(.dxf·.dwg) 또는 cmd[…] 또는 model(앞선 model3d id 또는 형태 칸) · views · title · paper(dark·white) · mark[[x0,y0,x1,y1]](빨간 구름) | CADCraft(투영도 · 치수 · 평면도) — 9:16 화면 전체 |

**언제 무엇을** (실제 화면 > 효과 — 꾸민 그래픽보다 진짜 화면 · 진짜 문서가 먼저):
- **기술 설명**: 실제 화면(web · screen) + 짚을 곳은 `overlay`(박스 · 화살표 · 한 줄 설명). 근거 문장은 `doc_quote`(진짜 형광펜 · 개인정보 가림), 약관 · 공지 · 바뀐 문구는 `document`. 캡처를 기기에 넣어 보여 줄 때 `ui_mock`(실제 캡처로 — 가상 화면은 mock: true 를 적고 설명용으로만). 순서 · 구조는 `diagram`(한 장면에 하나, 꾸밈 대신 단계 수만큼).
- **제품**: 실물 사진이 없으면 `model3d`(정지 컷 · 짧은 turntable · 분해도), 치수 · 구조는 `drawing`. 실제 제품이면 STEP 원본(src)이 내장 형태보다 낫다.
- **감성 · 광고**: 사용자 사진을 `photo_grade` 로 같은 톤에, 기사 · 캡처 한 장을 화면 카드로 세울 때 `photo` + `frame: "card"`(제목 · 강조 상자 · 로고 지우기 clean).
- **반복 형식(daily · series)**: 같은 틀에 값만 바꿀 때 `template_card`(가격 · 수치 한 줄), 요점 정리는 `info_card`.
- **썸네일**: `thumbnail` 하나 — 조립 단계도 훅 장면 프레임을 `edit/<id>.thumb.png` 로 따로 뽑는다.
- 화면 녹화 다듬기(screen · video · web 공통 칸): `zoom[{t, box, dur}]`(펀치인) · `blur[[x,y,w,h]]`(개인정보) · `speed[{from, to, x}]`(빨리 감기) — FilmCraft. 시각은 녹화 시각, 줌은 빨리 감기 구간 밖에.
- 움직임 칸(모든 재료): `enter`(등장 프리셋 id · false) · `exit` · `shadow` · `push`. 콘티 `direction.bg_preset` · `title_preset` · `sub_preset` · `enter`(기본은 형식별, false 면 끔).
- 소리: 콘티 `music{src, gain_db, duck_db, fade_in, fade_out}` — 사용자가 준 파일만. -14 LUFS 는 SoundCraft 가 맞춘다.

예시(그대로 고쳐 쓴다):
```json
{"id": "m1", "type": "web", "src": "data/public/elements/<id>/run-n1", "holds": [0.5, 3]},
{"id": "m2", "type": "overlay", "target": "m1", "marks": [{"kind": "box", "box": [0.04, 0.42, 0.92, 0.08], "text": "쿼리 101번", "cue": "101번"}]},
{"id": "m3", "type": "doc_quote", "pdf": "data/research/report.pdf", "find": "이용자의 43.7%는 AI가 제시한 정보를", "mark": "highlight", "redact": ["email", "phone"]},
{"id": "m4", "type": "diagram", "kind": "steps", "title": "fetch join 으로 고치기", "items": ["연관 엔티티 확인", "JOIN FETCH 추가", "쿼리 1번 확인"], "cues": ["확인", "추가", "한 번"]},
{"id": "m5", "type": "ui_mock", "src": "data/compositions/<id>/craft/src/settings.png", "device": "phone"},
{"id": "m6", "type": "document", "title": "이용약관 제7조", "text": "① 구독 시작 후 7일 이내에 …", "highlight": ["프로모션 요금제는 환불되지 않습니다"], "track": {"from": "7일 이내", "to": "14일 이내"}},
{"id": "m7", "type": "photo_grade", "src": "data/public/uploads/<id>/shop.jpg", "look": "warm", "credit": "사진: 직접 촬영"},
{"id": "m8", "type": "photo", "src": "data/public/uploads/<id>/news.jpg", "frame": "card", "title": "교장이 5400만원을\n사비로 메웠다?", "highlight": [0, 0.535, 1, 0.09], "clean": [[0.02, 0.02, 0.15, 0.08]]},
{"id": "m9", "type": "info_card", "kicker": "알아두기", "title": "N+1 은 지연 로딩의 기본 동작", "points": ["목록 1번 + 항목마다 1번", "fetch join · batch size 로 묶기"], "source": "Hibernate 문서"},
{"id": "m10", "type": "template_card", "values": {"품목": "배추 1포기", "가격": "4,980원", "반응": "평소 가격"}},
{"id": "m11", "type": "model3d", "shape": "tumbler", "material": "stainless", "logo": "FLUMA", "turntable": true, "sec": 3},
{"id": "m12", "type": "drawing", "model": "m11", "views": ["front", "top"], "title": "텀블러 외형도 (mm)", "paper": "white"},
{"id": "m13", "type": "thumbnail", "emphasis": "101번"}
```
검사 L39 가 칸을 본다: 필수 칸 · overlay 대상이 같은 장면 앞에 있는지 · drawing 의 model id · 가상 ui_mock 의 mock · id 에 '.' 금지. 앱 쪽 주의는 crafts 스킬.
공통: `id`, `cue`(등장할 낱말), `place`(full · center · left · right · top · bottom). 재료는 제목 아래 · 자막 위 구간에 놓인다.
숫자는 손으로 계산하지 말고 csv + percent 로 GridCraft 가 계산하게 한다.
**화면 비율**: 콘티 `aspect`(9:16 기본 · 16:9 · 1:1) 또는 `render.py --aspect`. 세로 녹화(대화창 · 폰 화면)는 가로 화면에서 가운데에 작게 놓이니, 가로 영상이면 녹화도 가로(viewport)로 한다.
**여러 버전 비교**: 훅 · 첫 장면 · 제목이 정해지지 않으면 콘티 `variants` 에 바꿀 칸만 적은 2~3개를 넣고 `python3 engine/story/variants.py render data/storyboards/<id>.json` → 나란히 비교 영상을 media 블록으로 보여 주고 고르게 한다(고른 것을 원본에 옮기는 건 확인받고)

### 다양한 화면 — 레시피 · craft 재료 (편향 금지)
- 장면마다 `python3 engine/craft/craft_variety.py suggest "<장면 용도>"` 로 고른다(★ = 최근 영상에 안 쓴 것 먼저). 자세한 규칙: crafts 스킬 0절.
- 고정 종류로 안 되면 `{"type":"craft","app":…,"steps":[…]}` — 명령은 `python3 engine/craft/craft_catalog.py search "<하고 싶은 일>"`.
- 레시피: `{"id":"m1","recipe":"vertical-process","fill":{…}}`. 다 쓰면 `craft_variety.py check data/storyboards/<id>.json` 로 반복을 본다.

- 다른 브랜드 광고 · 영상의 장면 · 문구를 그대로 따라 쓰지 않는다 — 구성 · 리듬만 빌린다.
