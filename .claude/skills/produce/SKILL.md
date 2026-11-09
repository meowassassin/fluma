---
name: produce
description: 콘티를 영상으로 만든다(Craft 파이프라인 — 기본 엔진). 음성 → 장면 재료(차트 · 문서 인용 · 그림 · 사진 · 화면) → 검사 → 초안 렌더(EffectCraft → SoundCraft → FilmCraft) → 결과 확인. 기획에서 콘티가 검사를 통과하면 바로 이어서, 또는 "만들어 줘" · "초안 렌더" 요청에 쓴다.
order: 2
---

# 제작 (Craft 파이프라인)

엔진은 Craft 하나다(콘티 `engine: "craft"`). HyperFrames · Blender · Manim 은 2026-11-06 제거 — `scene.js` 는 쓰지 않는다.
**색 · 배치는 레퍼런스에서**: 레퍼런스를 `ref_style.py` 로 분석했으면 `python3 engine/story/direct.py data/storyboards/<id>.json --write` 로 콘티 `direction`(배경색 · 자막 위치 등)을 적는다. 안 했으면 엔진이 레퍼런스 장면 프레임에서 배경 톤을 잰다 — 어느 쪽이든 파란 기본색으로 두지 않는다.
화면은 '템플릿에 칸 채우기'가 아니라 **장면마다 무엇이 보여야 하는지(재료)** 를 정하는 것이다. 좌표 · 툴 이름은 쓰지 않는다.

**개발 · 기술 주제는 실제 화면으로**(2026-11-04 사용자: "이상한 효과보다 실제 화면 위주로 자세하게"): 꾸민 로그 · 도표 · 큰 숫자 대신
- 작은 예제 프로젝트를 `data/compositions/<id>/demo/<프로젝트>/` 에 쓰고, 실행 계획 `data/compositions/<id>/demo/demo.json`(실행 · 바꾼 버전 · 코드 발췌 · 공식 문서)을 적은 뒤
  **`python3 engine/capture/demo.py run <id>`** 한 줄 — 빌드(Java · Maven 은 공식 배포판을 스스로 받음) → 실행 → 터미널 녹화 · 코드 화면 · 문서 녹화 → 콘티에 붙일 `material=` 줄(형식은 engine/capture/demo.py 맨 위)
- 화면에 보이는 코드는 그 예제의 실제 파일 그대로, 공식 문서는 `webrec.py` 로 해당 절을 녹화(쿠키 창은 누르지 않고 숨겨진다)
- 말로 한 주장("EAGER 로 바꿔도 똑같다" 등)은 실제로 돌려 본 출력으로 보여 준다. 돌려 보니 다르면 대사를 고친다
- 나레이션이 없으면 재료 전환 시각을 materials `start`(초) · `holds`(상태별 초)로 정한다

## 한 줄로 돌리기(기본)
재료 칸(materials)까지 콘티에 적었으면 나머지는 **`python3 engine/produce.py data/storyboards/<id>.json`** 한 줄 — 음성 → 검사 → 재료 · 초안 렌더 → 장면별 정지 화면 → 편집 밀도 · 템포를 정해진 순서로 돌린다(앞에서 한 번, timeout 10분).
- 종료 0 → media 줄(초안 + 장면별 정지 화면)을 채팅에 띄우고, 정지 화면을 Read 로 직접 보고 고칠 곳만 고쳐 다시 produce
- 종료 1 stage=lint → 걸린 규칙만 고쳐 다시 · stage=render → error 짧은 이유로 고쳐 다시
- 종료 10 → 사용자 녹화(L36) · 스톡 키(L38) 같은 것을 한 번에 부탁
- 장면 몇 개만 볼 때 `--scenes 1-3`, 대사를 안 바꿨으면 `--no-audio`
아래 단계는 produce.py 가 하는 일의 설명이자, 막혔을 때 한 단계씩 볼 때 쓴다.

## 대화로 고치기 — 값으로, 바로 보여 주기 (knob.py)
초안 뒤 사용자의 지적은 **값을 바꿔** 고친다. 코드 · 좌표를 다시 짜지 않고, 영상 전체를 다시 렌더하지 않는다(2026-11-09 영상: 한 번 고치는 데 4~17분 · 전체 렌더 32번).
- 지금 값 보기: `python3 engine/story/knob.py list <id>` — 장면 · 요소(id) · 조정 값 · 스크립트 값(args)
- 바꾸기(여러 개 한 번에): `knob.py set <id> route2d.adjust.scale=*1.2 route2d.adjust.dy=-0.03 s4.sec=+1.5 voice.speed=0.95`
  - **모든 요소 공통 조정 값 `adjust`**: dx · dy(화면 비율) · scale(배수) · rot(도) · opacity(0~1) · delay(초) · hide — 원래 배치 · 움직임 위에 얹힌다(재료를 다시 만들지 않음)
  - 장면 칸: `s4.sec` · `s4.caption` · `s4.transition` · 대본은 `script` · 목소리 `voice.*` · 음악 `music.*`
  - 상대값 `*0.7` · `+0.5`, 지우기 `=null`. 기록은 data/workspace/render/<id>/knobs.jsonl
- 보여 주기: `knob.py preview <id> --scene <n>`(정지 화면 약 2초, 결과 media 줄을 그대로) · 움직임 · 속도는 `--clip`(그 장면만 약 8초)
- 어디를 말하는지 애매하면 바꾸기 전에 "s4 route2d 를 1.2배로" 처럼 **고칠 요소 id 를 한 줄로 밝히고** 바로 진행(기다리지 않음)
- **새로 만드는 요소는 바꿀 값을 args 로 밝혀 둔다** — Blender 스크립트는 `ctx.args["gap"]` 처럼 읽고 콘티 `args` 에 기본값을 적는다.
  경로 간격 · 속도 · 크기 · 색 같은 숫자를 코드 안에 박지 않는다(박으면 다음 조정이 다시 코드 수정이 된다). 그러면 다음 조정은 `knob.py set <id> <요소>.args.gap=*1.5`.
- 사용자가 '좋아 · 완성' → 최종 렌더 한 번(위 6).

## 소리 — 음악 · 효과음 · 목소리(produce.py 가 음성 전에 자동으로)
- **음악**: `engine/craft/music_pick.py auto` 가 넣을지 정하고(레퍼런스 음악 비율 · 붙인 곡 · 나레이션 · 형식) 요즘 쓰이는 곡 중 맞는 **무료 곡**을 받아 콘티 `music` 에 적는다(가장 힘 있는 구간 `start` · 페이드 · 말할 때 내림).
  상업 유행곡은 `music.upload_sound` — 결과의 sound 줄을 사용자에게 그대로 알린다("업로드 때 쇼츠 편집기 '사운드 추가'로 붙일 곡"). 분위기를 바꾸려면 `music_pick.py pick <콘티> --mood "..." [--bpm 90]`, 빼려면 콘티 `music: {"use": false}`.
- **효과음**: 음악이 깔리면 기본으로 뺀다. 꼭 필요한 사건 소리(꺾임의 쿵 하나)만 `{"name": "stamp", "at": 2.1, "keep": true}`. 음악이 없을 때도 장면당 하나, 화면에서 실제로 일어난 일에만.
- **목소리**: 설정이 '자동'(기본)이면 `voice_match.py auto` 가 쓸 수 있는 모든 엔진에서 레퍼런스 화자와 가장 닮은 목소리 · 레퍼런스 말 속도를 골라 콘티 `voice` 에(source: auto). 사용자가 채팅으로 목소리를 정하면 `"source": "user"`.

## 순서
0. **레퍼런스 먼저(건너뛰지 않는다 — 검사 L30)**: 콘티에 `reference` 가 없으면 만들기 전에
   - trends 스킬로 같은 주제 · 형식의 실제 쇼츠를 찾는다: `python3 engine/research/trends.py search --queries "<주제 검색어 2~3개>" --label "<주제>" --limit 8`
   - 조회수 높은 2~3편을 분해: `python3 engine/research/analyze_ref.py <영상 id> --channel 3`(서버 작업 · 끝난 단계는 건너뜀) → `data/public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다
   - 거기서 가져온다: **문장 끝 비율 · 이음말 · 첫 문장 방식**(대사), **컷 길이 · 문장당 화면 수**(리듬), **화면 종류 비율 · 배경 · 자막 위치**(화면). 내용 · 대사 · 그림은 베끼지 않는다
   - 콘티 `reference: ["<id>", …]` 에 걸고, 대사를 그 채널 말투로 다시 쓴다(storyboard 스킬 '레퍼런스가 있으면' 절). 사용자가 레퍼런스 없이 하라고 했을 때만 `reference_skip: "<사용자 말>"`
   - 대사는 소리 내어 읽듯: 명사로 끊지 않고(…쓴 말. ✗ → …썼대요 ✓), 존댓말 · 반말을 섞지 않는다(검사 L31)
1. **음성**: `python3 engine/voice/assemble_audio.py data/storyboards/<id>.json` → `python3 engine/checks/lint.py data/storyboards/<id>.json` (L14 장면 길이 · L05 훅 3초). 걸리면 문장을 줄인다(내용 · 숫자는 그대로).
2. **장면 재료**(콘티 장면마다 `materials`): **문장(또는 핵심 낱말)마다 하나** — 30초면 서로 다른 재료 10개 이상(검사 L37), 같은 종류가 네 번 연속되지 않게(T37).
   먼저 **에셋 후보를 넓게 모은다**(웹 캡처만 쓰지 않는다):
   | 출처 | 명령 | 재료 |
   |---|---|---|
   | 짤 · 반응(커뮤니티 인기글) | `python3 engine/capture/meme.py search --query "<주제어>"` → `meme.py fetch <id> <이름> <밈 id>` | `meme` · `src: data/public/elements/<id>/<이름>` (권리는 사용자 판단 — 고른 것을 보여 주고 확인) |
   | 사이트를 실제로 쓰는 장면 | `python3 engine/capture/webrec.py run <id> data/compositions/<id>/web/<이름>.json` — 계획에 **`"mobile": true`**(폰 화면), 동작마다 `label`("1. 주소 넣기") | `web` · `src: data/public/elements/<id>/<이름>` — 세로 화면 가득 + 단계 꼬리표. `hold` 초, 쿠키 안내 등은 `crop: [x, y, w, h]` 로 잘라낸다(동의 버튼은 누르지 않는다) |
   | 서비스 · 브랜드 로고 | `python3 engine/capture/icons.py fetch <id> <이름>` | `icon` · `src: data/compositions/<id>/<이름>.svg` (흰 타일 위) |
   | 인물 · 상황 그림 | illustrate 스킬(VectorCraft) | `illustration` · `image` |
   | 사용자만 찍을 수 있는 화면 | `screen` + `ask` | 아래 L36 |
   그다음 장면마다 말하는 것을 **눈으로 증명하는 것**을 고른다.
   | 장면이 말하는 것 | 재료 | 만드는 앱(엔진이 고름) |
   |---|---|---|
   | 핵심 숫자 하나(훅 · 결론) | `stat` — `value`("+8.4%"), `label`(무엇의 숫자인지, 한국어, 짧게), `source`(설명란용 — 화면엔 안 씀), `cue`. **카드가 아니라 덧씌우기**: 그 장면의 바탕 재료(캡처 · 화면 · 차트) 위에 화면을 어둡게 하고 큰 숫자. 그래서 바탕 재료가 꼭 같이 있어야 한다 | 엔진 |
   | 숫자 여러 개 비교 | `chart` — 원자료는 `data/compositions/<id>/src/*.csv`. `percent: true` 는 **합계 대비 비율로 바꾸기**(값이 이미 % 면 쓰지 말 것). 가장 큰 값이 노란색 | GridCraft |
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
3. **검사**: `python3 engine/checks/lint.py data/storyboards/<id>.json` — 실패 0 이 될 때까지. T25(그래픽 위주)는 권고. 재료를 만든 뒤 시청자 기준 검사:
   - L33 같은 재료를 세 장면 이상 반복 ✗ · L34 재료 절반 넘게 글자 빽빽한 문서 캡처 ✗(핵심 수치는 `stat` · `chart`, 근거는 `doc_quote` 로 문장 하나만) · L35 20초 이상인데 재료 종류 3가지 미만 ✗ · T35 영어 캡처가 1/3 이상(권고)
   - L36 사용자 녹화 대기: 초안은 그 재료 없이 렌더된다. 사용자에게 **무엇을 · 몇 초 · 파일 이름에 재료 id 를 넣어 편집기에 올려 달라고** 한 줄로 부탁하고 턴을 끝낸다(올리면 `data/public/uploads/<id>/` 에서 이름으로 찾아 쓴다). 녹화가 장면보다 짧아도 마지막 화면에서 멈춰 있다
   - 훅(L05): 훅 제목이 3초 안에 뜨면 나레이션은 4.6초까지 괜찮다(T05). 3초를 맞추려 문장을 자르거나 배속을 올리지 않는다
3-1. **아트 디렉션** (콘티 `direction.art`, 재료를 만들기 전에): 이 영상의 시각 언어를 정한다 — `palette{bg, ink, accent}`(콘셉트 소재에서 뽑은 색. 기본 보라 금지) · `rule`(구도 원칙 한 문장: 예 "주인공은 언제나 화면의 절반 이상, 글자는 사물 위에") · `avoid`(이 영상에서 안 할 것: 예 "흰 카드 · 가운데 정렬 · 단색 배경"). 색은 자동으로 펴지지만 rule · avoid 는 네가 지킨다.
   **글꼴도 영상마다 고른다.** 기본 고딕으로 두지 않는다: 지면 · 신뢰 Gowun Batang · Song Myung(명조) / 강한 제목 Black Han Sans / 사람 손 · 마무리 Nanum Pen / 기계 · 게임 Gugi. Pretendard 는 정보 UI 를 흉내 낼 때만. 앱에서는 fontFamily 로 바로 쓴다(engine/core/fonts.py 가 설치).
   **숫자 · 사실은 기사 원문을 읽고 쓴다.** 검색 요약은 여러 자료가 섞인다. 화면에 넣기 전에 원문에서 그 숫자를 찾는다.
   **글자를 화면에 띄우기 전에, 세계 안에 놓을 수 있는지 먼저 생각한다**(신문 · 영수증 · 간판 · 도장 · 손글씨). 3D 조명은 긴 공간이면 해 하나로(영역 조명 여럿은 경계가 잘려 지면에 밝은 도형이 생긴다).
   **시청을 붙잡는 구조(모든 영상, `engine/checks/retention.py` 가 잰다):**
   - 장면마다 형식이 다르다. 같은 형식이 이어지면 안 된다(R01 · R02).
   - 사람이 나오고 한 명이 아니다. 인물은 말하고 놀라고 반응한다(R03 · R07). **인물은 `figure` 재료로 만든다(3D 인체 + 화풍 획). 좌표로 인물을 쓰지 않는다. 화풍은 영상 주제 · 구성에 맞춰 고르고 장면마다 바꿔도 된다.**
   - 사실 영상에는 진짜 사진 · 그림 · 문서가 들어간다(R06).
   - 영상의 '황당한 사실'을 찾아 장면 `surprise` 에 적는다. 사실 나열이 아니라 그 사실로 가는 이야기를 쓴다(R09).
   - 8초 안에 새 일이 일어난다(R04). 효과음은 장면 `sfx` 칸에.
   - 다듬기는 콘티에 `{"recipe": 이름, "vars": {…}, "why": …}` 로 적는다. 영상 전용 코드를 만들지 않는다 — 필요한 것이 없으면 엔진(forms · cast · 레시피)에 더한다.
   - 자막은 가로 영상이면 `direction.subs.mode: "clause"`, 대본의 숫자는 숫자로 적는다. 왼쪽으로 가는 인물은 왼쪽을 본다.
   - 재현한 것과 실제 자료를 화면에서 구분한다. 지어낸 대사는 말풍선으로, 사실은 나레이션으로.
   **어댑터는 초벌이다.** 훅과 핵심 장면은 카드 템플릿으로 끝내지 말고 앱을 직접 써서 디자인한다(refine 스킬).
4. **초안 렌더**: `python3 engine/render.py data/storyboards/<id>.json --draft` → `data/out/<id>-craft-Scenes-draft.mp4`. 결과의 D10~D15 는 렌더를 재서 나온 값이다(빈 화면 · 멈춘 장면 · 작은 주인공 · 같은 구도 · 기본 보라 · 어두움). `depth` 는 앱을 쓴 깊이. 걸린 장면부터 refine 으로 고친다. 최종 렌더는 아트 디렉션 · 다듬기 없이는 멈춘다.
   제작 파일: `data/compositions/<id>/craft/` (`motion/*.ecproj` · `audio/*.scraft` · `edit/*.fcproj` · `materials/`). 사람이 Craft 에서 고친 파일은 해시로 알아채 덮어쓰지 않는다(재료: .vectorcraft · 카드 .psd · .fcproj · .sc · .dxf).
   조립 결과: `edit/<id>.thumb.png`(훅 장면 썸네일 후보) · `edit/<id>.markers.csv`(장면 마커) — produce 결과 media 에 같이 나온다. 소리는 SoundCraft 가 -14 LUFS 로 맞추고(craft.json audio.lufs) FilmCraft 는 다시 정규화하지 않는다.
5. **확인**: `python3 engine/core/still.py data/storyboards/<id>.json <초> …` → PNG 를 Read 로 직접 본다. 글자 겹침 · 잘림 · 빈 화면 · 재료가 말과 맞는지. 고칠 게 있으면 재료 · 콘티를 고치고 4로.
6. **최종 렌더는 사용자가 '좋아 · 완성'이라고 할 때 에이전트가 바로** — `python3 engine/render.py data/storyboards/<id>.json`. 버튼을 누르라고 안내하지 않고, 관문(gate.py) 기록 · 시안 다시 만들기도 없다.

## 디자인 방향(기다리지 않는다)
1. `python3 engine/story/direct.py data/storyboards/<id>.json --write` — 레퍼런스 X-ray 에서 잰 값만 방향에 채운다(근거가 없으면 효과 없음).
2. 시안 비교(`directions.py propose`)는 사용자가 보고 싶다고 할 때만 — 기본은 바로 1번(레퍼런스대로, 없으면 담백하게)으로 `directions.py pick data/storyboards/<id>.json 1` 하고 전체 produce.
3. 사용자가 나중에 다른 방향을 말하면 그때 바꾼다.
4. 사용자가 말로 바꾸면("자막에 노란 상자", "효과 빼 줘") direction 칸을 직접 고치고 `locked: true` — 칸 설명은 engine/craft/design.py 맨 위. 지금 값 보기: `directions.py show`.
- **효과는 근거가 있을 때만**: 배경 움직임 · 등장 전환 · 글자 애니메이션 · 그림자 · 밀기는 기본으로 꺼져 있다. 레퍼런스 · 사용자 요청 없이 켜지 않는다. produce 결과의 D01 은 '사용자가 아직 고르지 않음'.
- **같은 재료, 다른 앱**: 재료에 `"method": "<앱>"`(또는 direction.methods) — 예: 차트를 DeckCraft 차트 엔진으로 `{"type": "chart", "method": "deckcraft", "kind": "pie", …}`. 가능한 앱은 `materials.methods()` · lint L39 가 알려 준다. DeckCraft 막대 차트는 세로축이 0 부터가 아닐 수 있어 기준선이 중요한 비교는 기본 방법.

## 느낌(룩) — 실사 재료에 같은 색 · 질감
- 콘티 `direction.feel`(plan 0.5턴에서 사용자가 시안을 보고 고른 것)이 있으면 실제 재료(영상 · 스톡 · 사진)에 같은 grade 가 자동으로 입혀진다(materials.py → engine/story/feel.py). 글자 · 그래픽에는 입히지 않는다.
- 아직 안 골랐으면 제작 전에 `feel.py preview` 시안을 보여 주고 고르게 한다(에이전트가 정하지 않는다).

## 초안 비평(VL) — 렌더 검사가 못 보는 것
- 초안을 본 뒤 고칠 때는 **director 스킬**의 감독 검사(같은 구도 연속 · 빈 화면 · 약속한 증거 · 반전의 멈춤 · 시선 한 곳)로 본다. 나레이션이 없으면 강조가 저절로 생기지 않는다(L41) — 장면마다 `beats [{"do": "확대", "t": 초}]` 나 재료 `zoom` 으로 짚는다.
- 초안 렌더(render.py --draft)가 끝나면 보기 모델이 **자동으로** 초안을 본다([VL 비평] 줄 · 다시 보려면 `python3 engine/providers/see.py critique <id>`) → 보기 모델이 초안 전체를 보고 의도 · 콘셉트 · 레퍼런스 문법과 대조해 "몇 초에 무엇이 왜 어색한지 · 어떻게 고칠지"(`data/workspace/critique/<id>.json`). high 부터 고치고 다시 렌더 → 다시 비평. 템포 · 편집 밀도 검사(숫자)는 그대로 같이.
- 특정 장면만 궁금하면 `see.py ask data/out/<id>-craft-Scenes.mp4 --q "8~11초 자막이 말보다 늦나?"` 처럼 직접.

## 디테일 다듬기(초안 뒤 — refine 스킬)
초안은 어댑터 초벌이다(앱 기능 몇 개). 장면 정지 화면을 본 뒤 **refine 스킬**로 장면마다 층별 계획 → 앱의 전체 명령에서 골라 시도 → 전 · 후를 보고 고침 → 남김:
`python3 engine/craft/session.py show data/storyboards/<id>.json <장면>` · `plan` · `try` · `keep` · `coverage`. 남긴 다듬기는 콘티 기록이라 다시 제작해도 적용된다.
produce 결과의 D02 = 다듬기 없음 · 계획했는데 안 다듬은 층.

## 3D 렌더 시간 — 영상 한 편 10분 이내가 기준
Blender 재료는 `"quality"` 또는 `direction.render_quality` 로 고른다. 기본은 `fast`(EEVEE 8샘플, 프레임당 약 1.2초 — 15초 영상 약 7분). `balanced`(Cycles, 약 50분) · `best`(약 3시간 40분)는 사용자가 분명히 원할 때만, 시간을 먼저 알리고. 8코어 CPU 기준.

## 레퍼런스 대조(D03)
레퍼런스 모양을 따르는 재료에는 `"ref": {"video": "<id>", "at": [초], "me": [내 재료 초]}` 를 적는다. 제작 뒤 `python3 engine/checks/refmatch.py sheet <콘티> <재료>` 로 나란히 본 뒤 `refmatch.py ok <콘티> <재료> --diff "남은 차이"`. 재료가 바뀌면 다시. 만드는 중에는 `refmatch.py pair <영상> <초> <내 그림>`. produce 결과의 D03 = 대조 안 함.

## 다양성 (V 권고)
produce.py 결과의 warn 에 V41~V45 가 있으면 무시하지 말고 한 장면 이상 바꿔 본다 — `craft_variety.py suggest` 의 ★ 레시피 또는 `craft_catalog.py search` 로 찾은 기능을 `type: craft` 로. 잘 나온 craft 재료는 `craft_variety.py save` 로 레시피에 남긴다(crafts 스킬 0절).

## 하지 말 것
- `data/compositions/<id>/scene.js` 쓰기(예전 HyperFrames 경로 — 엔진이 없다)
- 이전 영상의 그림 재사용(사용자가 원할 때만) · 레퍼런스 그림 베끼기
- 숫자를 재료 없이 글자만으로 보여 주기(`stat` · `chart` 재료로)
- 어두운 둥근 카드 · 패널 · 추상 배경만 있는 화면(AI 티) — 숫자는 실제 재료 위에 덧씌운다
- 영어 원문 캡처로 핵심 수치 보여 주기 — 출처 확인용으로 한 장면만, 숫자는 한국어 `stat` · `chart` 로 다시 그린다
