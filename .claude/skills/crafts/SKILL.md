---
name: crafts
description: 어떤 재료 · 장면에 어느 Craft 앱의 어떤 기능을 쓸지 고르는 지도 — 에이전트가 장면 재료를 만들거나 마감할 때 먼저 읽는다.
---

# Craft 앱 지도

Fluma 는 Craft 앱 16개를 단계별로 쓴다. 이 문서는 **고르는 표**다. 정확한 명령 · params · 시험 결과는 앱별 `reference/<이름>.md` 를 연다.
부르는 법은 모두 같다: `python3 engine/craft/crafts.py run <앱> <인자…>` (실행 파일은 `tools/crafts/<앱>/app/…/bin/<앱>-cli`).

기본 흐름: 재료(각 앱) → **EffectCraft**(움직임 · 합성) → **SoundCraft**(소리) → **FilmCraft**(조립 · 마감).

## 0. 먼저 — 기능을 넓게 쓰고, 영상마다 다르게 (편향 금지)
앱 16개에 명령 · 효과 · 프리셋이 9,000개 넘게 있다. 아는 몇 가지만 되풀이하지 않는다.
1. 장면마다 `python3 engine/craft/craft_variety.py suggest "<장면 용도>"` — 검증된 레시피(★ = 최근 5편에 안 씀)와 안 써 본 기능이 나온다. ★ 를 먼저 고른다.
2. 고정 재료 종류(아래 표)로 안 되는 화면은 `python3 engine/craft/craft_catalog.py search "<하고 싶은 일>"` 로 명령을 찾아 `type: craft` 로 직접 짠다:
   `{"type":"craft","id":"m2","app":"vectorcraft","steps":[{"id":"shape.rectangle","params":{…}}, …],"export":{"format":"png"}}`
   params 는 `craft_catalog.py show <앱> <id>` 와 reference/<앱>.md 의 시험된 예를 따른다. 앞 결과 참조 `"$N.키"`, 작업 폴더 `$WORK/…`, 프레임 `$FRAMES`.
3. 레시피 쓰기: `{"recipe":"hook-title-arc","fill":{"/steps/3/params/text":"새 제목"}}` — 바꿀 칸은 recipes/<이름>.json 의 slots.
4. 잘 나온 craft 재료는 레시피로 남긴다: `python3 engine/craft/craft_variety.py save <영상 id> <재료 id> --name <영어-이름> --purpose a,b --look x,y --desc "…"`
5. 영상마다 최소 한 장면은 최근 영상들이 안 쓴 레시피 · 기능으로(V44). 이어지는 장면은 구성을 바꾸고(V42), 재료 종류는 3가지 이상(V41). produce.py 가 V 권고를 보여 준다 — `craft_variety.py check data/storyboards/<id>.json`.
6. 많이 쓰는 것과 효과 남발은 다르다 — 장면의 말을 더 잘 보여 주는 기능만. 결과는 정지 화면을 보고 판단(실제 화면 > 효과).
7. **다양성은 사용자의 선택으로**: 모양 · 효과의 큰 방향은 시안(engine/story/directions.py)으로 보여 주고 사용자가 고른다. '안 써 본 것'을 이유로 사용자가 원하지 않는 효과를 넣지 않는다. 같은 재료를 다른 앱으로 만들 수 있으면(`method`) 그 차이도 시안에 쓴다.

## 1. 재료 · 작업 → 앱 → 핵심 기능

| 재료 · 작업 | 앱 | 핵심 기능 (지금 쓰는지) |
|---|---|---|
| 장면 움직임 · 합성 (`motion`) | EffectCraft | 쓰는 중: JSX `script` + `render`, 배경 프리셋(형식별 blueprintGrid · bokehDrift · pulseRings · softGradientDrift, `direction.bg_preset`), 재료 등장 · 퇴장 프리셋(닦기 · fadeIn 0.6초, 재료 `enter` · `exit`), 글자 프리셋(훅 bounceInWords · 감성 자막 fadeUpCharacters), 실제 화면 둥근 마스크 + Drop Shadow, overlay 주석 층 배치, 모르는 종류 as · 확장자 배치(9:16 은 화면 덮기). 시험만: 트래킹(`track.motion` → `analyze` → `apply`, 정확). 안 쓰는 것: 행동 프리셋(pulse · heartbeat), 3D 카메라, Trim Paths 밑줄, Audio Waveform, 알파 webm |
| 소리 (`audio`) | SoundCraft | 쓰는 중: 보이스 체인(eq_7band · compressor · de_esser), LUFS 읽고 maximizer 로 다시 바운스(-14 LUFS · -1.5 dBTP), SFX 클립 배치(`at:{seconds}`), `automation.write_range` 덕킹, 음악 trim + s-curve 페이드, `audio_health`. 안 쓰는 것: 스템 바운스, 리버브 센드 |
| 조립 · 마감 (`edit`) | FilmCraft | 쓰는 중: newSequence · import · place, Shorts 프리셋 내보내기(이미 -14 면 loudness 끔, 크기 · 비트레이트 덮기), 장면 마커 + `markers.exportCsv`, 썸네일 `file.exportFrame`. 화면 녹화 다듬기(`screen` · `video` · `web` POST): 펀치인 줌 키프레임 · 흐림 마스크 · razor + speedDuration 빨리 감기. 안 쓰는 것: 트랜스크립트 쉼 · 군말 삭제(모델 필요), 전환, 자막 번인 |
| 차트 데이터 (`chart`) | GridCraft | `cat --csv` · `eval`(쓰는 중). 안 쓰는 것: `run --script` 로 계산 열 한 번에, 피벗, 차트 추천. **차트 그림은 EffectCraft** (GridCraft PDF 는 한글이 빠짐) |
| 문서 인용 (`doc_quote`) | PdfCraft | 쓰는 중(adapters/pdfcraft.py): 사본에서 `text_find`(못 찾으면 줄 이어 찾기 · 하이픈 처리) → 잉크로 사각형 맞춤 → 진짜 `comment_add highlight` · underline · 빨간 상자, `redact_mark` + `redact_apply`(한국식 email · phone · rrn), `page_set_box` 로 문장 주변만 잘라 1080 폭. 기록 `highlighted` · `focus`. 안 쓰는 것: 영어 OCR(스캔 PDF), 그림 원본, `doc_compare` |
| 그림 (`illustration` · `icon`) | VectorCraft | `convert`(쓰는 중). 안 쓰는 것: 훅 카드, 레이어별 PNG · PSD, 트레이스, 다시 칠하기 |
| 주석 오버레이 (`overlay`) | VectorCraft | 쓰는 중(adapters/vectorcraft.py): 대상 크기 문서에 마크마다 층(박스 · 화살표 · 설명 알약, clean · hand 스타일) → 층별 투명 PNG + box(0~1) → EffectCraft 가 대상 위에 cue 마다 |
| 반복 카드 (`template_card`) | VectorCraft | 쓰는 중: 틀(.vectorcraft, 없으면 기본 틀) + `dataset.import` + `action.batch` 로 CSV 줄마다 카드 |
| 사진 · 캡처 (`photo`) | PhotoCraft | 쓰는 중(adapters/photocraft.py): 위치 인자 `run`, 누끼 `select.subject`, `paint.remove` 로고 지우기(`clean`), `colorToAlpha` 글자 오버레이(`alpha_text`), 9:16 장면 카드 PSD(`frame: card` — 흐린 배경 · 둥근 사진 · 노란 강조 상자 · 스포트라이트 · 제목). 안 쓰는 것: `layersToFiles`, `detectFaces`, Generative Fill(모델) |
| 사진 현상 (`photo_grade`) | LightCraft | 쓰는 중(adapters/lightcraft.py): Fluma 룩 4개(warm · film · clean · mono, 프리셋 + 슬라이더) · 약하게 줄인 자동 보정 · 9:16 자르기(focus) · 출처 워터마크 · 현상 설정 JSON(다시 렌더 가능). 안 쓰는 것: AI 마스크 · Denoise(모델) |
| 폰 · 브라우저 목업 (`ui_mock`) | FigCraft | 쓰는 중(adapters/figcraft.py): 실제 캡처 + 폰(베젤 · 아일랜드 · 상태 표시줄) 또는 브라우저 틀 + 그림자, 투명 PNG + .figcraft. 캡처가 없으면 iOS 문법 가상 화면(`mock: true` 필수). 한글 낱말 줄바꿈 함수(`wrap`) 공용 |
| 정보 카드 · 썸네일 (`info_card` · `thumbnail`) | DesignCraft | 쓰는 중(adapters/designcraft.py): `script` 조판 + `data.merge` 여러 장, 카드 투명 모서리 · 그림자(PIL 후처리), 썸네일 세로 1080×1920 + 가로 1280×720(강조 낱말 색 · 훅 알약 · 사진 어둡게). 안 쓰는 것: LaTeX 수식, 팔레트 추출, QR |
| 도식 (`diagram`) | DeckCraft | 쓰는 중(adapters/deckcraft.py): 540×960pt 덱에 SmartArt(steps · compare · cycle · hierarchy · pyramid · timeline · list) + `setBounds`, 항목마다 투명 층(빌드 애니메이션 대신) + base. 안 쓰는 것: 표 스타일, `render-transition` |
| 문서 화면 (`document`) | WordCraft | 쓰는 중(adapters/wordcraft.py): 9:16 쪽으로 다시 배치 · 글자 일괄 확대, 진짜 `format.highlight`, 변경 추적(`review.compare`), 메모 말풍선. 안 쓰는 것: 대본 md ↔ docx |
| 웹 · 터미널 실제 화면 (후보 `web-screen` 등) | craft-anything | 연결 없음. `web-walkthrough-record`(360×640@3x), `web_site_capture`, 터미널 기록. `--deep --allow-run` 필요. 기존 `web`(webrec.py) 재료와 겹치는지 먼저 본다 |
| 곡면 · 유기적 3D · 캐릭터 · 고품질 렌더 (`model3d` + `"method": "blender"`) | Blender | `script` = data/compositions/<id>/src/*.py 에 `def build(ctx)` · `import fluma3d as F`(engine/craft/blender/fluma3d.py). `F.ring` + `F.loft`(단면을 이어 곡면) · `F.melt`(겹친 조각을 하나로 녹임) · `F.mirror_pair`(좌우 한 쌍은 반드시 이것으로 — 메시 하나 · 값 하나, 따로 만들면 어긋난다) · `F.world_hdri` · `F.area_light` · `F.key` · Cycles(`F.use_cycles`, 잡티 제거 포함). 모양이 레퍼런스를 따르면 먼저 정지 화면으로: `python3 engine/craft/adapters/blender.py <스크립트> --still 0 --opaque` → `refmatch.py pair` 로 나란히 본다. 렌더 CPU 기준 720×1280 프레임당 10초 안팎 — 컷 전체는 모양 확정 뒤에 |
| 정밀 부품 + 고품질 화면 — 세 앱 잇기 (`model3d` + `method: blender` + `"bridge": "…/asm.json"`) | SolidCraft → TextureCraft → Blender | engine/craft/bridge3d.py: SolidCraft 모양 · 관절 동작(`motion.study`) → TextureCraft 재질 · 로고 → GLB + 단계별 부품 위치. 스크립트에서 `asm = F.import_assembly(ctx.args["asm"])` · `F.play_assembly(asm, 0, 1, start, end)`. 곡면 부품은 Blender 로 만들어 `F.attach(obj, asm, "부품")` 로 CAD 동작에 붙인다. 부품은 SolidCraft 에서 component 로 나눈다. 스마트 재질을 쓰면 사양에 `"bake": true`(Intel GPU 는 끊길 수 있음) |
| 실사 · 생성 영상 합성(`live`) | EffectCraft + Blender | 카메라를 풀어(시야각 자동 탐색, 독립 오차 `follow_px`) 3D 를 바닥에 놓고 그림자를 만든다. 인물 뒤로 지나가기(`behind`) · 물체 따라가기(`follow`) · 색 바꾸기(`recolor`) · 바닥에 선 정지 물체 지우기(`remove`). 카메라가 움직이는 영상만 풀린다 |
| 3D 기본(`model3d`) | SolidCraft → Blender | 스크립트가 없으면 `shape` · `commands` · `src` 를 SolidCraft 가 모양으로 만들고 Blender 기본 제품 컷(재질 · 조명 · 받침 · 자동 구도 · turntable · 글자 logo)으로 렌더. 분해도(`exploded`)와 정밀 도면은 SolidCraft |
| 3D — 예전 방식(`"method": "solidcraft"`) | SolidCraft + TextureCraft | 쓰는 중(adapters/solidcraft.py · texturecraft.py): 내장 형태 5종(case · phone · bottle · tumbler · puck) · 명령 목록 · STEP/STL 불러오기 → fine OBJ → TextureCraft 재질(쉬운 이름 → PBR) · 로고 데칼 · MCP `viewport_render`(장당 0.3초) 정지 컷 · turntable mp4, 분해도는 SolidCraft `explode.create` + `motion.export_animation` |
| 도면 (`drawing`) | CADCraft (+ SolidCraft `file.export_view_dxf`) | 쓰는 중(adapters/cadcraft.py): DXF · 명령 · 3D 모형 → 3각법 투영도 + 치수 3개, MCP `render` 9:16 어두운 CAD 화면 또는 흰 종이(plot 단색 후처리), 빨간 구름 `revcloud` |

## 앱 섞기 — 한 장면에서 함께 쓰기
- **겹치기:** 재료 `"layer": "over"` 는 앞 재료 위에 얹는다(`cue` · `start` 로 나오는 때). 투명 배경 Blender 재료는 재료가 둘 이상이면 저절로 겹친다.
- **다른 앱 → Blender:** `"uses": {"screen": "<앞 재료 id>"}` → 스크립트의 `ctx.args["uses"]["screen"]`(파일 경로) · `F.image_plane` · `F.mat_media`. 입력으로 쓴 재료는 화면에 따로 나오지 않는다(`"show": true` 로 켬).
- **Blender → 소리:** `F.event("swoosh", 초)` 가 효과음을 맞춘다(pop · swoosh · tick · stamp · ding · hit · error · glitch — CC0 녹음, engine/assets/sfx).
- **SolidCraft · TextureCraft → Blender:** `"bridge"`.

## 2. 장면 종류별로 고르기

- **기술 설명(실제 화면)**: 캡처 · 녹화(`web` · `screen`) → 필요하면 `ui_mock`(FigCraft 폰 · 브라우저 틀) → `overlay`(VectorCraft 박스 · 화살표 · 한 줄) → EffectCraft 등장 프리셋 · 느린 밀기. 화면 녹화면 FilmCraft `zoom` · `blur` · `speed`. 순서 · 구조는 `diagram`(DeckCraft).
- **문서 · 약관 · 논문 근거**: PDF 는 `doc_quote`(PdfCraft 진짜 형광펜 · 박스 · 잘라내기 · 개인정보 가림), docx · 직접 쓴 문구는 `document`(WordCraft), 바뀐 부분은 `track`(변경 추적).
- **비교 · 수치**: 계산은 GridCraft, 그림은 EffectCraft. 표는 DeckCraft, 단계 · 순환은 DeckCraft SmartArt.
- **감성 · 광고 스틸**: `photo_grade`(LightCraft 룩)로 톤 통일 → EffectCraft 느린 밀기. 기사 · 캡처 한 장은 `photo` + `frame: card`(PhotoCraft 장면 카드).
- **제품**: `model3d`(정지 컷 · turntable · 분해도) + `drawing`(치수 · 투영도). 실제 제품이면 STEP 원본.
- **매일 반복(format-daily)**: `template_card`(VectorCraft 변수 + CSV) 또는 `info_card`(DesignCraft `data.merge`) 중 하나만 고른다.
- **훅 · 표지**: `thumbnail`(DesignCraft 세로 · 가로), 조립 때 FilmCraft `file.exportFrame` 이 훅 장면 프레임을 `edit/<id>.thumb.png` 로도 뽑는다.

## 3. 앱별 참고 문서

| 앱 | 명령 수 | 참고 |
|---|---|---|
| FilmCraft | 716 | [reference/filmcraft.md](reference/filmcraft.md) |
| EffectCraft | 743 | [reference/effectcraft.md](reference/effectcraft.md) |
| SoundCraft | 483 | [reference/soundcraft.md](reference/soundcraft.md) |
| WordCraft | 651 | [reference/wordcraft.md](reference/wordcraft.md) |
| VectorCraft | 911 | [reference/vectorcraft.md](reference/vectorcraft.md) |
| PhotoCraft | 954 | [reference/photocraft.md](reference/photocraft.md) |
| LightCraft | 380 | [reference/lightcraft.md](reference/lightcraft.md) |
| FigCraft | 635 | [reference/figcraft.md](reference/figcraft.md) |
| DeckCraft | 330 | [reference/deckcraft.md](reference/deckcraft.md) |
| DesignCraft | 547 | [reference/designcraft.md](reference/designcraft.md) |
| GridCraft | 372 (+함수 515) | [reference/gridcraft.md](reference/gridcraft.md) |
| PdfCraft | 183 | [reference/pdfcraft.md](reference/pdfcraft.md) |
| SolidCraft | 570 | [reference/solidcraft.md](reference/solidcraft.md) |
| CADCraft | 451 | [reference/cadcraft.md](reference/cadcraft.md) |
| TextureCraft | 162 | [reference/texturecraft.md](reference/texturecraft.md) |
| craft-anything | 315 | [reference/craft-anything.md](reference/craft-anything.md) |

## 4. 헤드리스 한계

- **모델 내려받기 금지라 못 쓰는 것**: FilmCraft Whisper 음성 인식 · Kokoro TTS, EffectCraft 로토 · 얼굴 · SAM, LightCraft AI 마스크 · Denoise · 얼굴, PhotoCraft Generative Fill · Neural Filters(누끼는 고전 알고리즘이라 단순 배경만).
- **앱 창이 있어야 하는 것**: 모든 앱의 UI 스크린샷 · `ui_*` 조작(`--bridge` · `--control` · `--connect`), SoundCraft 녹음, FigCraft 프로토타입 재생. 단 LightCraft `snapshot` 은 창 없이 앱 화면 PNG 를 낸다.
- **움직임이 없는 앱**: DesignCraft · FigCraft · DeckCraft(빌드 애니메이션 렌더 없음) · WordCraft 는 정지 PNG 만. 움직임은 EffectCraft 에 넘긴다.
- **느린 것**: EffectCraft CPU 렌더(1080×1920 4초에 25초), FilmCraft 자막 번인(3초에 9.4초), SolidCraft progressive(40초).
- **OCR**: PdfCraft 는 영어만. 한국어 UI 화면의 글자 좌표는 못 얻는다.
- **craft-anything**: 기본 clean room 이라 `--deep --allow-run` 없이는 웹 · 실행 도구가 거부된다.

## 5. 공통 주의

1. **글꼴**: Pretendard 는 시스템 글꼴이 아니다. EffectCraft 만 `EFFECTCRAFT_FONT_DIRS=<repo>/public/fonts` 로 Pretendard 를 쓴다. 나머지는 `Noto Sans CJK KR`(DesignCraft 는 `Noto Sans CJK SC`). 자막 글꼴과 섞이면 앞 단계 재료의 글자를 줄인다.
2. **조용히 무시되는 params**: WordCraft `edit.replace`(→ `replaceAll`), DesignCraft 모르는 키, SoundCraft `audiosuite` 틀린 키, LightCraft `--settings` 틀린 스키마, LightCraft `mask.add kind=sky`(모델 없이 ok). 결과를 `info` · `inspect` · 렌더로 꼭 확인한다.
3. **시간 단위가 앱마다 다르다**: FilmCraft 1초 = `254016000000` ticks(키프레임 time 은 시퀀스 시각), SoundCraft 자동화 · 페이드 length 는 샘플(48 kHz), EffectCraft 는 초.
4. **id 가 바뀐다**: PhotoCraft 레이어 id, GridCraft 차트 id 는 다시 열면 바뀐다. FilmCraft 효과 번호는 `effects.apply` 결과로 확인. 이름 · 라벨로 찾는 길을 쓴다.
5. **오프셋은 UTF-8 바이트**: WordCraft `inspect`, DesignCraft `text.select`.
6. **PhotoCraft `run` 은 입력을 위치 인자로** 받는다(`run <FILE> --cmd …`, `--in` 은 없다). 예전 `materials.py photo()` 의 `--in` 호출은 고쳤고, 보통은 `adapters/photocraft.py` 가 photo 를 맡는다.
7. **자막 겹침**: 기본 엔진은 EffectCraft 가 자막을 그린다. FilmCraft 자막 번인 · `createCaptions` 를 같이 쓰면 두 번 나온다.
8. **세로 화면**: FilmCraft 내장 그래픽 템플릿 · DeckCraft 템플릿은 16:9 용, CADCraft CLI PNG 는 2400×1600 고정(9:16 은 MCP `render`), SolidCraft `--view iso` 는 9:16 에서 잘린다.
9. **편집 파일을 남긴다**: 사람이 고칠 수 있게 PNG 와 함께 `.ecproj` · `.scraft` · `.fcproj` · `.vectorcraft` · `.psd` · `.designcraft` 등을 둔다. PNG 저장은 평탄화된다.
   재료 기록에 `editable` + `editable_hash` 가 있으면(illustration · photo 카드 · 화면 다듬기 · model3d · drawing) `materials.build` 가 고친 파일을 알아보고 그 파일로 다시 만든다. lightcraft · wordcraft · deckcraft · figcraft · designcraft · template_card 의 편집 파일은 아직 다시 반영되지 않는다(콘티를 고쳐 다시 만들면 덮어씀).
10. **경로는 절대 경로**. VectorCraft 는 `VECTORCRAFT_NO_PREFS=1` 을 붙인다.
11. **verified=false 기능은 먼저 시험**: EffectCraft Magnify(원이 안 보임) · 트래킹, FilmCraft auto_reframe, WordCraft `review.compare`, PdfCraft `doc_compare`, DesignCraft flex · 변형본 등은 참고 문서의 "미확인" 표시를 보고 렌더로 확인한 뒤 쓴다.
12. **가상 내용 주의**: FigCraft · DeckCraft 템플릿은 가상 브랜드다. 실제 서비스 설명에는 실제 캡처를 쓴다.
13. **앱 어댑터 꽂기**: `engine/craft/adapters/<앱>.py` 의 `ADAPTERS = {재료 종류: fn(m, out, work) -> info}` · `POST = {종류: fn(m, file, work, info)}`. 기록에 `as`(image · video) · `size` · `full_frame` · `highlight_box`(0~1)를 넣으면 움직임 단계 배치가 정확해진다. 층으로 나뉜 그림은 `layers[{file, box, cue}]`(+ `base`), 같은 장면의 다른 재료를 읽으면 `materials._depends` 에 더한다(열쇠에 대상 기록이 들어가게).
14. **글꼴이 섞인다**: 카드 · 주석 · 도식 · 썸네일 글자는 Noto Sans CJK KR(앱이 Pretendard woff2 를 못 읽음), 자막은 Pretendard.

## 실제로 돌려 본 결과(engine/craft/probe.py)
앱마다 기능 목록 전체를 견본 문서에서 실행해 기록했다 — `.claude/skills/crafts/probe/<앱>.jsonl`(명령마다 되는 상태 · 실행 결과 · 오류 문구 · 견본 그림), 요약 `<앱>.md`(분류별 수 · 견본 판).
`craft_catalog.py search` 결과에 자동으로 붙는다. 기록이 낡았으면(앱 업데이트) `python3 engine/craft/probe.py <앱>` 로 다시 돌린다(앱 설정은 임시 HOME 이라 바뀌지 않음).

## 제품 · 툴 소개 영상(쇼케이스) — 에이전트 · MCP 도구 소개 페이지 데모처럼
`python3 engine/capture/showcase.py make <계획.json> <출력 폴더> [--aspect 16:9|9:16] [--music auto]` — 실제 앱을 대본(클릭 · 입력 · 짚기 · 이동)대로 2배 해상도로 녹화하고,
동작 대상 상자로 카메라가 줌 인 · 아웃(멀면 빠졌다 들어감), 짚는 곳만 선명 · 나머지 흐림, 입력은 실제 한 자씩, 글자 줄은 한 자씩, 기다림은 빨리 감기, 맞는 무료 곡까지.
계획 형식은 파일 맨 위 설명. 예: data/public/showcase/fluma-demo.json(Fluma 자체 소개). 보내기(Enter) 같은 실제 동작은 대본에 넣지 않으면 일어나지 않는다.

## 물리로 움직이기(MuJoCo) — 떨어짐 · 부딪힘 · 튕김 · 쌓임 · 넘어짐
손으로 키프레임을 짜면 딱딱해지는 움직임(무너지는 블록 · 도미노 · 굴러가는 꾸러미 · 튕기는 아이콘 · 흔들리다 넘어지는 랙)은 물리로 계산한다.
1. 장면을 MJCF 로 쓴다 — `data/compositions/<id>/src/<이름>.mjcf.xml`. 물체마다 `<body name="…"><freejoint/><geom …/></body>`, 바닥은 plane.
   마찰 · 높이 · 미는 속도 같은 숫자는 `{{이름}}` 으로 두고 콘티 재료 `args` 에 값을 적는다(대화로 고칠 때 `knob.py set <id> <요소>.args.friction=0.4`).
   처음 속도는 `<keyframe><key qvel="…"/></keyframe>`(freejoint 하나에 6칸: 직선 3 + 회전 3).
2. Blender 스크립트에서 같은 이름의 물체를 만들고 `F.physics(ctx.args["physics"], {"이름": 물체, …})` — 프레임마다 위치 · 회전 키가 들어간다(축 같음: Z 위, 미터).
3. 재료: `{"type": "model3d", "method": "blender", "script": "…/<이름>.py", "physics": "…/<이름>.mjcf.xml", "args": {…}, "sec": 4}` — 렌더 전에 자동으로 계산(1초 안쪽).
빠른 확인: `python3 engine/craft/physics.py check <장면>` · `python3 engine/craft/adapters/blender.py <스크립트> --physics <장면> --args '{…}' --anim --sec 3.5`(짧은 영상).
예: `engine/craft/examples/physics/dominoes.*`(공이 도미노 13개를 넘어뜨림 — 재료로 쓸 때는 data/compositions/<id>/src/ 로 복사). 물리가 어울리는 비유가 있는 장면에만 — 모든 움직임을 물리로 하지 않는다.

## 앱 · 대시보드 화면은 Astryx 컴포넌트로 — 손으로 그린 표 · 버튼 대신
영상 속 '실제 같은' 관리 화면 · 대시보드 · 설정 창 · 채팅 앱 · 표(예: DB 테이블, 주문 목록, 결제 화면)는 HTML 을 손으로 짜지 않고
Astryx(Meta 디자인 시스템, 컴포넌트 174개 — Table · Card · Badge · SideNav · TopNav · ChatMessage · CommandPalette · Stepper · ProgressBar …)로 만든다.
손으로 그린 화면은 '진짜 앱' 느낌이 안 나고(2026-11-10 DB 영상) 고치는 데 오래 걸린다.
1. 컴포넌트 문서를 먼저 읽는다 — 속성 이름을 추측하지 않는다(Badge 는 children 이 아니라 `label`, Stack 간격은 숫자 `gap={4}`):
   `npm --prefix tools/ui-scenes run -s astryx -- component --list` · `… component Table`
2. 장면 파일 하나: `data/compositions/<id>/ui/<이름>.tsx` — `export default function Scene()` (React 19, 데이터는 파일 안에).
3. 짓기: `node tools/ui-scenes/build.mjs data/compositions/<id>/ui/<이름>.tsx data/compositions/<id>/ui/<이름> --mode dark --png 1080x1920`
   타입 검사가 먼저 돌아 잘못된 속성을 렌더 전에 알려 준다. `--png` 로 정지 화면 확인.
4. 영상에 넣기: webrec 계획의 `"start": "file:///app/data/compositions/<id>/ui/<이름>/index.html"`(로컬은 저장소 절대 경로) →
   `webrec.py run` 으로 클릭 · 입력 · 스크롤을 단계 캡처 → 재료 `web`. 움직임이 필요하면 페이지 안 React 상태로 직접.
화면 하나하나는 그 영상에 맞게 새로 짠다 — 장면 파일을 부품 · 템플릿으로 모아 재사용하지 않는다. 예: `tools/ui-scenes/examples/db-table.tsx`.

