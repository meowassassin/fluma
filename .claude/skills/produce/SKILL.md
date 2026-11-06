---
name: produce
description: 콘티를 영상으로 만든다(Craft 파이프라인 — 기본 엔진). 음성 → 장면 재료(차트 · 문서 인용 · 그림 · 사진 · 화면) → 검사 → 초안 렌더(EffectCraft → SoundCraft → FilmCraft) → 결과 확인. 홈의 '제작 시작', "만들어 줘", "초안 렌더" 요청에 쓴다.
order: 2
---

# 제작 (Craft 파이프라인)

엔진은 Craft 하나다(콘티 `engine: "craft"`). HyperFrames 화면 구성(compose 스킬 · `scene.js`)은 쓰지 않는다 — Craft 앱이 없는 환경에서만.
**색 · 배치는 레퍼런스에서**: 레퍼런스를 `ref_style.py` 로 분석했으면 `python3 scripts/direct.py storyboards/<id>.json --write` 로 콘티 `direction`(배경색 · 자막 위치 등)을 적는다. 안 했으면 엔진이 레퍼런스 장면 프레임에서 배경 톤을 잰다 — 어느 쪽이든 파란 기본색으로 두지 않는다.
화면은 '템플릿에 칸 채우기'가 아니라 **장면마다 무엇이 보여야 하는지(재료)** 를 정하는 것이다. 좌표 · 툴 이름은 쓰지 않는다.

**개발 · 기술 주제는 실제 화면으로**(2026-11-04 사용자: "이상한 효과보다 실제 화면 위주로 자세하게"): 꾸민 로그 · 도표 · 큰 숫자 대신
- 작은 예제 프로젝트를 `compositions/<id>/demo/<프로젝트>/` 에 쓰고, 실행 계획 `compositions/<id>/demo/demo.json`(실행 · 바꾼 버전 · 코드 발췌 · 공식 문서)을 적은 뒤
  **`python3 scripts/demo.py run <id>`** 한 줄 — 빌드(Java · Maven 은 공식 배포판을 스스로 받음) → 실행 → 터미널 녹화 · 코드 화면 · 문서 녹화 → 콘티에 붙일 `material=` 줄(형식은 scripts/demo.py 맨 위)
- 화면에 보이는 코드는 그 예제의 실제 파일 그대로, 공식 문서는 `webrec.py` 로 해당 절을 녹화(쿠키 창은 누르지 않고 숨겨진다)
- 말로 한 주장("EAGER 로 바꿔도 똑같다" 등)은 실제로 돌려 본 출력으로 보여 준다. 돌려 보니 다르면 대사를 고친다
- 나레이션이 없으면 재료 전환 시각을 materials `start`(초) · `holds`(상태별 초)로 정한다

## 한 줄로 돌리기(기본)
재료 칸(materials)까지 콘티에 적었으면 나머지는 **`python3 scripts/produce.py storyboards/<id>.json`** 한 줄 — 음성 → 검사 → 재료 · 초안 렌더 → 장면별 정지 화면 → 편집 밀도 · 템포를 정해진 순서로 돌린다(앞에서 한 번, timeout 10분).
- 종료 0 → media 줄(초안 + 장면별 정지 화면)을 채팅에 띄우고, 정지 화면을 Read 로 직접 보고 고칠 곳만 고쳐 다시 produce
- 종료 1 stage=lint → 걸린 규칙만 고쳐 다시 · stage=render → error 짧은 이유로 고쳐 다시
- 종료 10 → 사용자 녹화(L36) · 스톡 키(L38) 같은 것을 한 번에 부탁
- 장면 몇 개만 볼 때 `--scenes 1-3`, 대사를 안 바꿨으면 `--no-audio`
아래 단계는 produce.py 가 하는 일의 설명이자, 막혔을 때 한 단계씩 볼 때 쓴다.

## 순서
0. **레퍼런스 먼저(건너뛰지 않는다 — 검사 L30)**: 콘티에 `reference` 가 없으면 만들기 전에
   - trends 스킬로 같은 주제 · 형식의 실제 쇼츠를 찾는다: `python3 scripts/trends.py search --queries "<주제 검색어 2~3개>" --label "<주제>" --limit 8`
   - 조회수 높은 2~3편을 분해: `python3 scripts/analyze_ref.py <영상 id> --n 4`(서버 작업 · 끝난 단계는 건너뜀) → `public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다
   - 거기서 가져온다: **문장 끝 비율 · 이음말 · 첫 문장 방식**(대사), **컷 길이 · 문장당 화면 수**(리듬), **화면 종류 비율 · 배경 · 자막 위치**(화면). 내용 · 대사 · 그림은 베끼지 않는다
   - 콘티 `reference: ["<id>", …]` 에 걸고, 대사를 그 채널 말투로 다시 쓴다(storyboard 스킬 '레퍼런스가 있으면' 절). 사용자가 레퍼런스 없이 하라고 했을 때만 `reference_skip: "<사용자 말>"`
   - 대사는 소리 내어 읽듯: 명사로 끊지 않고(…쓴 말. ✗ → …썼대요 ✓), 존댓말 · 반말을 섞지 않는다(검사 L31)
1. **음성**: `python3 scripts/assemble_audio.py storyboards/<id>.json` → `python3 scripts/lint.py storyboards/<id>.json` (L14 장면 길이 · L05 훅 3초). 걸리면 문장을 줄인다(내용 · 숫자는 그대로).
2. **장면 재료**(콘티 장면마다 `materials`): **문장(또는 핵심 낱말)마다 하나** — 30초면 서로 다른 재료 10개 이상(검사 L37), 같은 종류가 네 번 연속되지 않게(T37).
   먼저 **에셋 후보를 넓게 모은다**(웹 캡처만 쓰지 않는다):
   | 출처 | 명령 | 재료 |
   |---|---|---|
   | 짤 · 반응(커뮤니티 인기글) | `python3 scripts/meme.py search --query "<주제어>"` → `meme.py fetch <id> <이름> <밈 id>` | `meme` · `src: public/elements/<id>/<이름>` (권리는 사용자 판단 — 고른 것을 보여 주고 확인) |
   | 사이트를 실제로 쓰는 장면 | `python3 scripts/webrec.py run <id> compositions/<id>/web/<이름>.json` — 계획에 **`"mobile": true`**(폰 화면), 동작마다 `label`("1. 주소 넣기") | `web` · `src: public/elements/<id>/<이름>` — 세로 화면 가득 + 단계 꼬리표. `hold` 초, 쿠키 안내 등은 `crop: [x, y, w, h]` 로 잘라낸다(동의 버튼은 누르지 않는다) |
   | 서비스 · 브랜드 로고 | `python3 scripts/icons.py fetch <id> <이름>` | `icon` · `src: compositions/<id>/<이름>.svg` (흰 타일 위) |
   | 인물 · 상황 그림 | illustrate 스킬(VectorCraft) · `genvideo.py run --task t2i`(그림체만, 실사 금지) | `illustration` · `image` |
   | 사용자만 찍을 수 있는 화면 | `screen` + `ask` | 아래 L36 |
   그다음 장면마다 말하는 것을 **눈으로 증명하는 것**을 고른다.
   | 장면이 말하는 것 | 재료 | 만드는 앱(엔진이 고름) |
   |---|---|---|
   | 핵심 숫자 하나(훅 · 결론) | `stat` — `value`("+8.4%"), `label`(무엇의 숫자인지, 한국어, 짧게), `source`(설명란용 — 화면엔 안 씀), `cue`. **카드가 아니라 덧씌우기**: 그 장면의 바탕 재료(캡처 · 화면 · 차트) 위에 화면을 어둡게 하고 큰 숫자. 그래서 바탕 재료가 꼭 같이 있어야 한다 | 엔진 |
   | 숫자 여러 개 비교 | `chart` — 원자료는 `compositions/<id>/src/*.csv`. `percent: true` 는 **합계 대비 비율로 바꾸기**(값이 이미 % 면 쓰지 말 것). 가장 큰 값이 노란색 | GridCraft |
   | 논문 · 보고서 · 기사 근거 | `doc_quote` — `pdf` + `find`(그 문장). 진짜 PDF 형광펜(`mark`: highlight · box · both) · 문장 주변만 잘라 1080 폭 · `redact`(email · phone) | PdfCraft |
   | 인물 · 캐릭터 · 사물 | `illustration` — **illustrate 스킬로 이 영상만의 SVG 를 새로 그린다**. 기본은 통째로 한 장(글자 포함). 캐릭터를 움직이려면 `action`(idle · walk · wave · bounce) + 부품 이름 그룹 | VectorCraft |
   | 사용자 사진 · 캡처 | `photo` — 기사 · 캡처 한 장을 화면 카드로 세울 때 `frame: "card"` + `title` · `highlight`([x,y,w,h]) · `clean`(로고 · 워터마크 지우기). `cutout` 누끼는 단순 배경만 | PhotoCraft |
   | 실제 화면 녹화 · 영상 | `screen` · `video` — 웹 녹화 `src`. **자동 브라우저로 못 찍는 화면**(로그인 · 측정 결과 · 앱)은 `ask`("무엇을 · 몇 초")만 적는다 → 사용자에게 부탁(아래 L36) | 그대로 |
   | 실제 화면의 짚을 곳(버튼 · 줄 · 숫자) | `overlay` — `target`(같은 장면 앞 재료) + `marks`[{kind: box·arrow·label, box(0~1), text, cue}]. 효과(번쩍임 · 큰 배지) 대신 주석 | VectorCraft |
   | 화면 녹화의 확대 · 가림 · 건너뛰기 | screen · video · web 에 `zoom`[{t, box, dur}] · `blur`[[x,y,w,h]] · `speed`[{from, to, x}] | FilmCraft |
   | 캡처를 폰 · 브라우저에 넣어 | `ui_mock` — `src`(실제 캡처) · `device`. 캡처가 없어 그린 화면이면 `screen` + `mock: true`(설명용 가상 UI) | FigCraft |
   | 단계 · 구조 · 비교 | `diagram` — `kind` + `items` + `cues`(항목이 그 낱말에 하나씩) | DeckCraft |
   | 약관 · 공지 · 바뀐 문구 | `document` — `src` 또는 `text`, `highlight`[문장], `track`{from, to}, `comments` | WordCraft |
   | 요점 정리 · 반복 카드 | `info_card`(kicker · title · body · points · source) · `template_card`(틀 + csv · values) | DesignCraft · VectorCraft |
   | 제품(실물 사진이 없을 때) | `model3d` — `shape`+`size` · `commands` · `src`(STEP) · `material` · `logo` · `turntable` · `exploded`. 치수는 `drawing`(`model`: 앞 model3d id) | SolidCraft · TextureCraft · CADCraft |
   | 감성 · 광고 사진 톤 | `photo_grade` — `look`(warm · film · clean · mono) · `crop` 9:16 · `credit` | LightCraft |
   | 썸네일 | `thumbnail`(마지막 장면, 비우면 콘티 제목 · 훅) — 결과 media 에 세로 · 가로 판 | DesignCraft |
   칸 · 예시 JSON 은 storyboard 스킬 '장면 재료' 절. 어느 앱의 무엇을 쓰는지 · 주의는 crafts 스킬. 렌더 전에 검사 L39 가 칸을 본다.
   - 재료가 없는 장면은 엔진이 그 장면의 핵심어(`visual.primary`) · 목록(`visual.items`)으로 화면을 짠다 — 그래서 `visual` 을 꼭 채운다.
   - 공통 칸: `id`, `cue`(등장할 나레이션 낱말), `place`(center · left · right · top · bottom · full).
   - 같은 캐릭터를 여러 장면에 쓰면 같은 `src` — 한 번 고치면 모든 장면이 바뀐다.
3. **검사**: `python3 scripts/lint.py storyboards/<id>.json` — 실패 0 이 될 때까지. T25(그래픽 위주)는 권고. 재료를 만든 뒤 시청자 기준 검사:
   - L33 같은 재료를 세 장면 이상 반복 ✗ · L34 재료 절반 넘게 글자 빽빽한 문서 캡처 ✗(핵심 수치는 `stat` · `chart`, 근거는 `doc_quote` 로 문장 하나만) · L35 20초 이상인데 재료 종류 3가지 미만 ✗ · T35 영어 캡처가 1/3 이상(권고)
   - L36 사용자 녹화 대기: 초안은 그 재료 없이 렌더된다. 사용자에게 **무엇을 · 몇 초 · 파일 이름에 재료 id 를 넣어 편집기에 올려 달라고** 한 줄로 부탁하고 턴을 끝낸다(올리면 `public/uploads/<id>/` 에서 이름으로 찾아 쓴다). 녹화가 장면보다 짧아도 마지막 화면에서 멈춰 있다
   - 훅(L05): 훅 제목이 3초 안에 뜨면 나레이션은 4.6초까지 괜찮다(T05). 3초를 맞추려 문장을 자르거나 배속을 올리지 않는다
4. **초안 렌더**: `python3 scripts/render.py storyboards/<id>.json --draft` → `out/<id>-craft-Scenes-draft.mp4`
   제작 파일: `compositions/<id>/craft/` (`motion/*.ecproj` · `audio/*.scraft` · `edit/*.fcproj` · `materials/`). 사람이 Craft 에서 고친 파일은 해시로 알아채 덮어쓰지 않는다(재료: .vectorcraft · 카드 .psd · .fcproj · .sc · .dxf).
   조립 결과: `edit/<id>.thumb.png`(훅 장면 썸네일 후보) · `edit/<id>.markers.csv`(장면 마커) — produce 결과 media 에 같이 나온다. 소리는 SoundCraft 가 -14 LUFS 로 맞추고(craft.json audio.lufs) FilmCraft 는 다시 정규화하지 않는다.
5. **확인**: `python3 scripts/still.py storyboards/<id>.json <초> …` → PNG 를 Read 로 직접 본다. 글자 겹침 · 잘림 · 빈 화면 · 재료가 말과 맞는지. 고칠 게 있으면 재료 · 콘티를 고치고 4로.
6. **최종 렌더는 하지 않는다** — 사용자가 편집기의 '렌더'를 눌러 의도 · 시안을 확인한다(관문).

## 다양성 (V 권고)
produce.py 결과의 warn 에 V41~V45 가 있으면 무시하지 말고 한 장면 이상 바꿔 본다 — `craft_variety.py suggest` 의 ★ 레시피 또는 `craft_catalog.py search` 로 찾은 기능을 `type: craft` 로. 잘 나온 craft 재료는 `craft_variety.py save` 로 레시피에 남긴다(crafts 스킬 0절).

## 생성 클립(Dreamina 등)이 있는 콘티
produce.py 가 '사용자 녹화 대기'(L36)로 멈추면 생성 클립이 아직 없다는 뜻 — `python3 scripts/genclip.py prompts storyboards/<id>.json` 의 목록을 사용자에게 주고 올려 달라고 한다. 받은 뒤 다시 produce. 클립 끝이 어색하면 `in` · `out` · `end`(slow · loop · freeze)를 고친다(storyboard 스킬 '생성 영상 클립').

## 하지 말 것
- compose 스킬 · `compositions/<id>/scene.js` · `direct.py --write` (HyperFrames 경로)
- 이전 영상의 그림 재사용(사용자가 원할 때만) · 레퍼런스 그림 베끼기
- 숫자를 재료 없이 글자만으로 보여 주기(`stat` · `chart` 재료로)
- 어두운 둥근 카드 · 패널 · 추상 배경만 있는 화면(AI 티) — 숫자는 실제 재료 위에 덧씌운다
- 영어 원문 캡처로 핵심 수치 보여 주기 — 출처 확인용으로 한 장면만, 숫자는 한국어 `stat` · `chart` 로 다시 그린다
