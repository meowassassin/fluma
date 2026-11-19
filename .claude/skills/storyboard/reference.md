# 콘티 참고 (storyboard 스킬에서 필요할 때만 읽는다)

## 레퍼런스가 없으면 — 형식 프리셋(사람이 편집한 실제 쇼츠에서 잰 숫자)
링크가 없어도 손으로 정한 기본값(가운데 판 · 고정 자막 · 직접 그린 표)으로 짜지 않는다 — 그게 'AI 틀'이다.
1. `python3 engine/research/format_presets.py pick data/storyboards/<id>.json` — 주제 낱말로 형식(it-explainer · cooking · news · science · review)을 고르고 콘티 `preset` 에 숫자를 적는다. 맞지 않으면 `--format <형식>`.
2. 프리셋을 따른다: 장면 구성은 `preset.roles`(역할 비율) · `preset.screens`(화면 종류 비율), 컷 길이는 `preset.rhythm.shot_sec`, 말 주도인지 음악 주도인지는 `preset.lead`, 문장 끝은 `preset.tone.endings`.
3. 장면 `screen` 은 프리셋 화면 비율에 가깝게(T21 · T25). 그래픽(도표 · 글자 카드)은 프리셋에 그 비율이 있을 때만.
4. `direct.py --write` 는 프리셋에서 배치 · 바탕 · 자막 · 움직임을 정한다(무작위 아님). 검사 T27 = 프리셋 없음.

## 말투만 고쳐 달라고 하면 — 내용은 잠근다
"말투만 · 어미만 · 톤만" 요청은 문장을 새로 쓰지 않는다. 바꿀 글을 json(`{"4": "…"}`)으로 써서
`python3 engine/story/tone_edit.py data/storyboards/<id>.json <json>` → 내용 낱말이 바뀌면 거절된다(어미 · 이음말 · 문장부호만 통과).
통과하면 `--apply`, 출력되는 전 · 후 표를 그대로 보여 준다. 사용자가 문장을 직접 불러 줬으면 `--apply --user-text`.

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
| illustration | src(.svg — 아이콘 · 단순 도형) · place | VectorCraft |
| photo | src · cutout | PhotoCraft(누끼) |
| screen · video · image | src | 그대로 |
| web | src(data/public/elements/<id>/<이름> — webrec.py · termrec.py 녹화) · holds(상태별 초) · start(나레이션 없을 때 시작 초) | 그대로(실제 화면) |
| stock | query(영어 검색어) · min_sec · pick · trim | Pexels → Pixabay 무료 스톡 영상(실제 촬영) — 일상 · 감성 · 광고의 바탕. 키는 설정 → API 키. |
| overlay | target(같은 장면의 **앞선** 그림 · 화면 재료 id) · marks[{kind: box·arrow·label, box:[x,y,w,h] 0~1(대상 기준), from/to(화살표), text, cue}] · style(clean·hand) · color | VectorCraft(투명 주석 층) → 대상 위 제자리에 cue 마다 하나씩 |
| ui_mock | src(실제 캡처) · device(phone·browser, 생략하면 모양으로) · url. 캡처가 없을 때만 screen{…} + **mock: true** | FigCraft(폰 · 브라우저 틀 + 그림자) |
| diagram | kind(steps·compare·cycle·hierarchy·pyramid·timeline·list) · items(탭=하위) · title · cues(항목별 낱말) | DeckCraft(SmartArt, 항목 층이 차례로 등장) |
| document | src(.docx·.md·.txt …) 또는 title + text · highlight[문장] · track{from,to}(바뀐 부분) · comments[{at,text}] | WordCraft(9:16 문서 화면 · 진짜 형광펜 · 변경 추적) |
| photo_grade | src · look(warm·film·clean·mono) · crop(9:16) · focus[x,y] · credit | LightCraft(현상 · 톤 통일 · 세로 자르기) |
| info_card | kicker · title · body · points[] · source (또는 rows[] · csv + row) · frame(card·full) · theme | DesignCraft(정보 카드, 여러 장 병합) |
| template_card | template(.vectorcraft, 없으면 기본 틀) · csv 또는 values{머리글: 값} · row | VectorCraft(변수 + CSV 일괄 — 매일 같은 틀) |
| thumbnail | (비우면 콘티 title · badge · hook_number) · title · hook · emphasis · src(false 면 글자만) | DesignCraft(세로 1080×1920 + 가로 1280×720). **영상 화면이 아니라 표지용** — 마지막 장면에 두고 화면에는 거의 안 보이게 |
| model3d | shape(case·phone·bottle·tumbler·puck) + size(mm) 또는 commands 또는 src(.step·.stl·.obj …) · material(metal·plastic·wood·#색·{부품:재질}) · color · logo · turntable 또는 exploded · sec | SolidCraft(형태 · 분해도) + TextureCraft(재질 · 로고 · 렌더) — 9:16 화면 전체(배경 포함) |
| live | src(실사 영상) · cuts{이름: {strokes[{frame, kind: fg\|bg, points(이어진 한 획), radius}], span, recolor{hue, sat, light}, remove, frame, grow}} · items[{id, kind: text(text · follow · offset · size · color · behind)\|image(file · follow · offset · scale · behind)}] — follow 는 {at, frame}(장면 고정) · {at, frame, moving}(움직이는 무늬) · {cut, at: top\|center}(분리한 물체). 끝나면 `cuts.check.png` 로 매트를 본다 — 완전히 가려지면 분리가 끊기므로 가려졌다 나오는 물체는 나온 직후 프레임에 획을 더한다. |
| archive | 실제 사진 · 그림 — `title`("File:…", `engine/capture/commons.py search` 로 찾아 보고 고른다) · fit(cover\|contain). 출처는 자동으로 sources 에 들어간다. 실제 자료가 있는 사실은 재현하지 말고 진짜를 쓴다 |
| relic | 실제 유물 · 조각 자체가 이야기일 때만 — 그래픽 장면 위 인물 대용으로 쓰지 않는다(사진이 겉돈다). — 실제 조각 · 흉상 · 도기 사진을 오린 컷아웃. `src`(archive 로 받은 파일) · `crop` · `cut`(matte · shard: PhotoCraft 작업, 레이어 PSD 가 남음 / ink 도기 안료 / none) · `matte:"ai"`(배경이 복잡해 Select Subject 가 옆 인물까지 잡을 때) · `keep` · `erase` · `jaw`(poly: 수염 · 턱 결을 따라 / mouth: 입술 틈 / hinge) · `width` · `show: false`. 말하는 인물은 id 하나에 `jaw` 를 적고 motion-relic 레시피(S0 · S1 말 구간, 경첩 · 목 px)로 놓는다. 그림 확대 격자로 poly 를 잡고 렌더해서 본다. 말하지 않는 인물은 `<인물>_<자세><번호>` 로 motion-cast |
| drawing | src(.dxf·.dwg) 또는 cmd[…] 또는 model(앞선 model3d id 또는 형태 칸) · views · title · paper(dark·white) · mark[[x0,y0,x1,y1]](빨간 구름) | CADCraft(투영도 · 치수 · 평면도) — 9:16 화면 전체 |

### 다양한 화면 — 레시피 · craft 재료 (편향 금지)
- 장면마다 `python3 engine/craft/craft_variety.py suggest "<장면 용도>"` 로 고른다(★ = 최근 영상에 안 쓴 것 먼저). 자세한 규칙: crafts 스킬 0절.
- 고정 종류로 안 되면 `{"type":"craft","app":…,"steps":[…]}` — 명령은 `python3 engine/craft/craft_catalog.py search "<하고 싶은 일>"`.
- 레시피: `{"id":"m1","recipe":"vertical-process","fill":{…}}`. 다 쓰면 `craft_variety.py check data/storyboards/<id>.json` 로 반복을 본다.

- 다른 브랜드 광고 · 영상의 장면 · 문구를 그대로 따라 쓰지 않는다 — 구성 · 리듬만 빌린다.

