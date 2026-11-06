# VectorCraft 참고 (v0.21.0)

**한 줄 요약**: Illustrator 류 벡터 앱(순수 Rust, MIT/Apache-2.0). 명령은 911개이고 전부 헤드리스 CLI(`run`)와 MCP 로 부를 수 있다. 쇼츠에서는 **제목 카드 · 실제 화면 위 주석(화살표 · 박스) · 데이터 템플릿 일괄 생산 · 사진/스틸을 평면 그림으로 바꾸는 트레이스 · 아이콘 배지 · 레이어별 PNG** 를 맡는다. 지금 Fluma 는 이 중 `convert`(SVG → PNG/.vectorcraft) 하나만 쓴다.

- 실행 파일: `tools/crafts/vectorcraft/app/vectorcraft-0.21.0-linux-x86_64/bin/vectorcraft-cli`
  (에이전트는 `python3 scripts/crafts.py run vectorcraft <인자…>` 로 부른다)

---

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `scripts/craft/materials.py` `illustration()` · `icon` — `convert`(SVG → PNG · .vectorcraft).
- `scripts/craft/adapters/vectorcraft.py`:
  - `overlay`: 대상 재료 기록에서 크기를 읽고(mp4 면 첫 프레임) 같은 크기 문서에 마크마다 층(박스 · 화살표 · 설명 알약, clean · hand). 맨 아래에 대상 화면을 템플릿 층(잠김 · 내보내지 않음)으로. 층마다 투명 PNG → 알파 영역만 잘라 box(0~1) 기록. 알약 크기는 같은 글꼴 `text.create` 상자로 먼저 잰다. shape 기본 검은 1pt 선은 `paint.setStroke none` 으로 지운다. 1.0~1.2초.
  - `template_card`: CSV(또는 values) → `dataset.import` → `action.batch`(datasets → document.export png) 로 줄마다 카드. 틀이 없으면 기본 틀(960×720 흰 둥근 카드)을 만들어 남긴다. 머리글과 같은 이름의 변수가 하나도 없으면 오류.
- 글꼴: Pretendard 불가 → Noto Sans CJK KR. `text.addFontFiles` 는 앱 설정 폴더로 복사하므로 쓰지 않는다.

## 1. 헤드리스로 되는 것 / 안 되는 것

| 구분 | 내용 |
|---|---|
| 된다 (확인) | `run` 배치: 새 문서 → 명령 → PNG/SVG/PSD/.vectorcraft 내보내기. 도형 · 펜 경로 · 글자 · 그라데이션 · 라이브 효과(벡터 · 래스터) · 3D 돌출 · 블렌드 · 이미지 트레이스 · 다시 칠하기 · 그래프 · 변수/데이터 세트 일괄 · 레이어별 내보내기 · 파일 배치(place) |
| 된다 (확인) | `mcp --headless`: 도구 33개(`command_run` · `command_batch` · `render_preview` · `draw_path` · `draw_shape` · `apply_effect` · `create_graph` · `export` …) |
| 안 된다 | UI 전용 도구: `ui_inspect` · `ui_screenshot` · `type_text` · `answer_dialog` · `open_panel` (앱을 `vectorcraft --control 7979` 로 띄워야 함) |
| 안 된다 (확인) | `text.findFontFiles` 는 비동기라 `run` 한 번 안에서 검색이 끝나지 않는다. 검색 대상도 .ttf/.otf/.ttc/.otc 뿐이라 저장소의 `public/fonts/Pretendard-*.woff2` 는 찾지 못한다. Pretendard 를 쓸 방법은 **미확인**. 시스템 글꼴 `Noto Sans CJK KR`(Regular~Black) · `NanumGothic` 을 쓴다 |
| 주의 | 속도: 1080×1920 카드 한 장은 약 0.4초. 래스터 효과(watercolor 등)를 넣으면 약 2.5초. 트레이스는 1080×1920 에서 0.5초 |
| 주의 | 환경 변수 `VECTORCRAFT_NO_PREFS=1` 을 꼭 붙인다. 안 붙이면 `file.new` 크기가 앱 설정(Recent 프리셋)에 기록된다. 바이트까지 같은 결과가 필요하면 `SOURCE_DATE_EPOCH=<초>` 를 쓴다 |

## 2. 기본 문법 (run 배치)

```sh
VECTORCRAFT_NO_PREFS=1 vectorcraft-cli run [--in 입력파일] --commands steps.json --export out.png [--export out.vectorcraft] [--scale 2]
```
- `steps.json` 형식: `[{"command": ID, "params": {...}}, …]`(JSON Lines 도 받음). 결과는 단계마다 JSON 한 줄씩 나온다.
- **앞 단계 결과 참조**: `"$1.id"` · `"$6.ids"`(배열 그대로) · `"$0.ids.0"` · `"$last.id"`. 단계 번호는 0부터 센다. `--cmd` · `--export` 도 단계로 센다.
- 좌표는 pt 단위이고 y 는 아래로 커진다. 원점은 첫 아트보드의 왼쪽 위. `file.new {"units":"Pixels"}` 로 만들면 1pt = 1px 이라 `--scale 1` 에서 1080×1920 PNG 가 나온다.
- `--in` 을 주지 않으면 첫 단계에서 `file.new` 를 부른다. `--in` 은 svg · pdf · ai · psd · png · jpg · eps · afdesign 등 40여 형식을 연다.
- 잘못된 키를 넣으면 오류가 나고 가장 가까운 키를 알려 준다(`widht` → `width`?). 키가 틀린 채로 조용히 무시되지는 않는다.
- 명령 목록과 params 설명: `vectorcraft-cli commands`(JSON, 911개, 약 540KB). 필요한 것만 python 으로 걸러 본다.
- 목록 조회 명령: `effect.list`(효과 130개, 기본값 포함) · `imageTrace.presets` · `gradient.presets.list`(55개) · `text.fontList` · `file.newPresets` · `document.formats`.

## 3. 쇼츠용 핵심 기능

### 3.1 제목 · 훅 카드 (그라데이션 배경 + 휜 글자 + 그림자) — 확인함 (t1)
```json
[{"command":"file.new","params":{"width":1080,"height":1920,"units":"Pixels"}},
 {"command":"shape.rectangle","params":{"x":0,"y":0,"width":1080,"height":1920}},
 {"command":"paint.setFill","params":{"id":"$1.id","gradient":{"kind":"linear","angle":90,"stops":[{"offset":0,"color":"#1b1446"},{"offset":1,"color":"#e8573f"}]}}},
 {"command":"paint.setStroke","params":{"id":"$1.id","none":true}},
 {"command":"text.create","params":{"x":540,"y":700,"text":"무료 AI 툴 3개","size":120,"font":"Noto Sans CJK KR","style":"Bold","color":"#ffffff","justify":"center"}},
 {"command":"effect.apply","params":{"id":"$4.id","effect":"warp.arc","params":{"bend":25}}},
 {"command":"effect.apply","params":{"id":"$4.id","effect":"stylize.dropShadow","params":{"x":0,"y":12,"blur":18,"opacity":60}}}]
```
- 시험 결과: 1080×1920 PNG 를 0.44초에 만들었다. 한글이 휘고 그림자가 들어간 것을 PNG 로 확인했다.
- 주의
  - `angle: 90` 이면 offset 0 이 아래, 1 이 위다.
  - `justify:"center"` 를 주면 x 가 가운데 기준이 된다.
  - 결과의 `bounds` 로 글자 상자를 받아 다음 요소를 배치한다.
  - 넓이에 맞추려면 `text.create {area:{width,height,fit:"shrinkText"}}` 나 `text.fitHeadline` 을 쓴다(미확인).
- 다른 휘기: `warp.flag` · `warp.wave` · `warp.bulge` · `warp.rise` · `warp.fisheye` 등 15종. 같은 효과를 envelope 로 걸려면 `object.envelope.makeWithWarp`.

### 3.2 실제 화면 위 주석 오버레이 (점선 박스 · 곡선 화살표 · 설명) — 확인함 (t2)
기술 설명 쇼츠의 핵심이다. 스크린샷은 그대로 두고 주석만 벡터로 그린다.
```json
[{"command":"file.new","params":{"width":1080,"height":1920,"units":"Pixels"}},
 {"command":"file.place","params":{"path":"<절대경로>/psi.png","rect":[0,500,1080,920]}},
 {"command":"shape.rectangle","params":{"x":60,"y":700,"width":500,"height":260,"radius":24}},
 {"command":"paint.setFill","params":{"id":"$2.id","none":true}},
 {"command":"paint.setStroke","params":{"id":"$2.id","color":"#ff2d55"}},
 {"command":"stroke.set","params":{"id":"$2.id","weight":10,"dash":[28,14],"cap":"round"}},
 {"command":"path.create","params":{"anchors":[{"x":800,"y":1650},{"x":700,"y":1300,"in":[820,1450]},{"x":450,"y":980}]}},
 {"command":"paint.setStroke","params":{"id":"$6.id","color":"#ff2d55"}},
 {"command":"stroke.set","params":{"id":"$6.id","weight":14,"cap":"round","endArrow":"Triangle","profile":"taperStart"}},
 {"command":"text.create","params":{"x":540,"y":1780,"text":"여기 점수 보세요","size":80,"font":"Noto Sans CJK KR","style":"Black","color":"#111111","justify":"center"}},
 {"command":"object.setProps","params":{"id":2,"visible":false}},
 {"command":"file.export","params":{"path":"overlay.png","background":"transparent"}}]
```
- 시험 결과
  - 합성본(t2.png)과 주석만 담은 투명 오버레이(RGBA 1080×1920)가 둘 다 나왔다.
  - 오버레이는 EffectCraft 에서 스크린샷 위에 따로 등장시킬 수 있다(박스 먼저, 화살표 다음).
- 주의
  - `file.place` 결과의 `ids` 가 그림 id 다. id 1 은 레이어라서 숨기면 전부 숨는다.
  - 문서 배경이 `backgroundContents:"white"` 이면 RGB 로 나오므로 투명 오버레이는 기본값(transparent)으로 만든다.
  - 화살표 머리는 40여 종이다(`Arrow` · `Triangle` · `Chevron` · `Circle` …). 끝 굵기는 `profile` 로 바꾼다(`taperStart` · `lens` · `teardrop` …).
  - 박스 + 화살표 + 설명 레이어를 따로 내보내려면 레이어를 나눈 뒤 3.7 을 쓴다.
  - 원래 크기가 72ppi 이므로 rect 로 크기를 지정한다.

### 3.3 데이터 템플릿 일괄 생산 (변수 + 데이터 세트 + action.batch) — 확인함 (t5)
format-daily(당일 시세) · 비교 카드를 CSV 한 장으로 여러 장 만든다.
```json
[… 디자인 단계 …,
 {"command":"text.create","params":{"x":540,"y":800,"text":"품목", …}},
 {"command":"text.create","params":{"x":540,"y":1050,"text":"0원", …}},
 {"command":"variable.define","params":{"name":"item","kind":"text"}},
 {"command":"variable.bind","params":{"variable":"item","ids":["$1.id"]}},
 {"command":"variable.define","params":{"name":"price","kind":"text"}},
 {"command":"variable.bind","params":{"variable":"price","ids":["$3.id"]}},
 {"command":"dataset.import","params":{"path":"<절대경로>/ds.csv"}},
 {"command":"action.batch","params":{"source":"datasets","destination":"folder","destinationFolder":"<절대경로>/out","datasetFileNaming":"dataSetName",
   "commands":[{"command":"document.export","params":{"path":"<절대경로>/out/x.png","format":"png"}}]}}]
```
CSV: `name,item,price` / `day1,배추 1포기,"4,980원"` …
- 시험 결과: 3행이 `day1.png` · `day2.png` · `day3.png` 로 나왔다. 글자가 바뀐 것을 확인했다.
- 주의
  - export 단계에 `"format":"png"` 가 **꼭 있어야 한다**. 없으면 `.vectorcraft` 로 저장된다(시험에서 겪음).
  - 헤더 접두사로 변수 종류를 정한다. `#이름` 은 보이기/숨기기 변수(예: "상승/하락 배지"), `@이름` 은 이미지 변수(상품 사진 교체)다. `@` 는 미확인.
  - 그래프 변수는 `variable.makeGraphDynamic` 으로 만든다(미확인).
  - 한도: 데이터 세트 500개, 단계 256개.
  - 글자가 상자를 넘치면 `dataset.select` 결과에 `overflow` 로 알려 준다.

### 3.4 이미지 트레이스 (스틸 · 사진 · 로고 → 평면 벡터 그림) — 확인함 (t3)
```sh
vectorcraft-cli run --in still.png --cmd select.all --cmd imageTrace.makeAndExpand --params '{"preset":"6 Colors"}' --export tr.svg --export tr.png
```
- 프리셋 15개: `Default` · `Auto Color` · `High Fidelity Photo` · `Low Fidelity Photo` · `3 Colors` · `6 Colors` · `16 Colors` · `Shades of Gray` · `Black and White Logo` · `Sketched Art` · `Silhouettes` · `Line Art` · `Technical Drawing` · `Outline` · `Flat Logo`
- 세부 params
  - `mode`(color/grayscale/blackAndWhite/logo) · `colors`(2~256) · `paths` · `corners` · `noise` · `ignoreWhite` · `gradients` · `shapes`
  - `palette:"documentLibrary"` 를 주면 문서 견본 색으로만 그린다. 팔레트를 맞출 때 쓴다(미확인).
- 시험 결과
  - 1080×1920 스틸을 `6 Colors` 로 트레이스: 0.47초, 경로 67개, 6색. 원본과 거의 같았고 그림자 · 미세 톤은 빠졌다.
  - `Silhouettes`: 경로 5개 1색. 실루엣 썸네일로 쓸 만하다.
- 쓰임
  - 감성 형식: 사용자 현장 사진을 평면 일러스트 톤으로 만든다.
  - 로고 · 사용자 PNG 를 벡터화해 확대해도 깨지지 않게 한다.
  - illustrate 스킬에서 레퍼런스 실루엣을 뽑는다.
  - 실사 생성이 아니라 사용자 소재의 양식화다.
- 주의
  - 1500px 이 넘으면 느리다는 경고가 나온다(그래도 처리된다).
  - `makeAndExpand` 로 하면 경로로 확정된다. 보기 방식을 바꾸려면 `imageTrace.make` + `imageTrace.setView` 를 쓴다.

### 3.5 다시 칠하기 (팔레트 교체) — 확인함 (t6)
```sh
vectorcraft-cli run --in art.vectorcraft --cmd select.all --cmd recolor.colors --cmd recolor.apply --params '{"map":{"#ffd23f":"#3fd2ff","#e8573f":"#12a150"}}' --export out.png
```
- `recolor.colors` 로 그림에 쓰인 색 목록(hex · 개수)을 받고, `recolor.apply` 의 map 으로 바꾼다. 그라데이션 정지점도 바뀐다.
- 다른 방식: `method:"hueShift"|"preserveTints"`, 전체 조정 `globalAdjust:{saturation,brightness,temperature}`, 색 수 줄이기 `recolor.reduce {colors:3}`.
- 시험 결과: 그라데이션 아래쪽 색과 별 색이 바뀐 것을 확인했다.
- **주의**: 외부 광선(outerGlow) · 그림자 같은 효과 params 의 색은 바뀌지 않는다(시험에서 노란 광선이 남았다). 효과 색은 `effect.setParams` 로 따로 바꾼다.
- 쓰임: 한 영상의 그림 · 아이콘을 `styles/<이름>/STYLE.md` 팔레트로 통일한다. 같은 일러스트를 장면마다 색만 바꿔 다시 쓴다.

### 3.6 아이콘 배지 · SVG 배치 — 확인함 (t7)
```json
{"command":"file.place","params":{"path":"<절대경로>/lucide-shopping-cart-ffffff-2.svg","rect":[440,1610,200,200]}}
```
- SVG 는 편집할 수 있는 그룹으로 들어온다(`linked:false`). 비율은 유지된다.
- 결과 `ids` 에 효과를 바로 걸 수 있다: `{"ids":"$6.ids","effect":"stylize.dropShadow"}`.
- 현재 materials.py 는 아이콘을 `convert --scale 8` 로 PNG 로만 바꾼다. 원 배경 · 그림자 · 색을 넣은 배지 한 장으로 만들면 차트 항목 아이콘이 덜 밋밋해진다.

### 3.7 레이어별 PNG (움직임 단계용 분리 재료) — 확인함 (t9)
```json
{"command":"document.exportForScreens","params":{"folder":"<절대경로>/scr","layers":[1,"$5.id","$8.id"],"formats":[{"format":"png","scale":1}]}}
```
- 시험 결과
  - `bg.png`(1080×1920 RGB), `hero.png`(636×1030 RGBA), `title.png`(739×159 RGBA) 가 레이어 이름으로 나왔다.
  - `--export x.psd` 로 레이어가 유지된 PSD(1080×1920)도 나왔다.
- **주의**: 레이어 PNG 는 **레이어 내용 크기로 잘린다**(아트보드 전체가 아니다). 위치가 필요하면 `document.inspect` 의 bounds 를 함께 저장한다. 전체 프레임 크기가 필요하면 다른 레이어를 숨기고(`layer.setProps visible:false` 또는 `object.setProps`) 일반 export 를 레이어마다 돌린다.
- 다른 단위: `selection:"each"`(선택한 개체마다 한 장) · `assets:[…]`(`assets.add` 로 등록한 자산만).
- 쓰임: 배경 · 주인공 · 제목을 EffectCraft 에서 패럴랙스 · 시차 등장으로 움직인다(장면 내 엔진 혼합).

### 3.8 3D 돌출 글자 · 블렌드 — 확인함 (t7)
- 3D 글자: `{"command":"effect.apply","params":{"id":"$1.id","effect":"threeD.extrude","params":{"depth":40}}}`. 한글 "3D 제목" 이 입체로 렌더된 것을 확인했다.
  - 다른 3D 효과: `threeD.revolve` · `threeD.inflate` · `threeD.rotate`.
  - 조명 프리셋: `effect.lightingPreset`(미확인).
- 블렌드: `object.blend.make {"ids":[원,별],"steps":6}`. 원이 별로 바뀌는 중간 단계 6개가 나왔다.
  - `easingType`(easeIn/Out) · `colorShift` 를 쓸 수 있다.
  - 쓰임: 모양이 바뀌는 과정을 한 장에 보여 주는 설명 그림. 한 단계씩 PNG 로 뽑아 프레임 애니로 쓰는 것도 생각해 볼 수 있다(미확인).
- **주의**: `shape.*` 로 만든 도형에는 기본 검은 1pt 선이 붙는다. 면만 원하면 `paint.setStroke {"none":true}` 를 넣는다.

### 3.9 손맛 · 질감 효과 (그림체 보정) — 확인함 (t1, t10)
- 벡터 효과(편집 가능)
  - `distort.roughen`(외곽 흔들기; size 3 은 시험에서 너무 셌다, 1~2 권장)
  - `stylize.scribble`(기본값은 사선 해칭)
  - `distort.zigZag` · `distort.puckerBloat` · `stylize.roundCorners` · `path.offsetPath`
- 래스터 효과(rasterEffectsPpi 기준; 기본 72, `file.new {"rasterEffectsPpi":150}` 을 권장하지만 미확인)
  - `artistic.watercolor`(종이 질감 · 살짝 번짐) · `texture.grain` · `artistic.filmGrain` · `sketch.halftonePattern` · `addon.color.halftone` · `pixelate.colorHalftone` · `artistic.cutout` · `blur.gaussian` · `stylize.outerGlow` · `stylize.innerGlow` · `stylize.feather`
- 시험 결과: scribble 은 그림 전체를 줄무늬 해칭으로 바꿨다(글자도 깨짐). watercolor 는 은은한 질감이 들어갔고, 1080 정사각 두 장에 2.5초 걸렸다.
- 주의
  - 글자에는 질감 효과를 걸지 않는다.
  - 효과 params 기본값은 `effect.list` 의 `defaults` 로 확인한다.
  - 효과를 확정하려면 `effect.expandAppearance` 를 쓴다.
  - "AI 티 · 싼티" 보정은 `grain` 이나 `roughen` 을 약하게 거는 정도로만 한다(그림 교훈: 디테일 빼기).

### 3.10 벡터 그래프 — 확인함 (t4), 우선순위 낮음
```json
{"command":"graph.create","params":{"type":"column","x":90,"y":500,"width":900,"height":900,"csv":",점유율\nChatGPT,62\nGemini,18\nClaude,12\n기타,8\n"}},
{"command":"graph.setType","params":{"id":"$1.id","legend":false,"suffix":"%","axisMin":0,"axisMax":80,"ticks":4,"columnWidth":70}}
```
- 종류: column · stackedColumn · bar · stackedBar · line · area · scatter · pie · radar.
- 시험 결과: 막대가 정확히 그려졌다. 다만 기본은 검은 막대에 작은 라벨이라 쇼츠에 바로 쓰기엔 밋밋하다. 색은 `select`(그룹 선택) + `paint.setFill` 이나 `graph.design`(막대 디자인을 그림으로)으로 칠해야 하는데, 이 부분은 미확인이다.
- Fluma 차트는 GridCraft 수치와 움직임 단계 렌더로 이미 만든다. 그래프는 "정적인 인포그래픽 한 장"이 필요할 때만 쓴다.

### 3.11 현재 쓰는 것 (유지)
- `convert a.svg b.png --scale N`: illustration · 아이콘 PNG (`scripts/craft/materials.py` `illustration()`, `chart()` 아이콘).
- `convert a.svg b.vectorcraft`: 사람이 고칠 편집 파일. 해시로 사람이 고쳤는지 감지해, 고쳤으면 그 파일을 SVG 로 다시 바꿔 원본으로 쓴다.
- rig 분리 (`scripts/craft/rig.py`): VectorCraft 가 전체를 `Layer_1` 로 감싸므로 그 안의 부품 그룹을 본다.
- illustrate 스킬의 "렌더해서 보기"는 `convert --scale 1`, MCP 로 붙어 있으면 `render_preview`.
- 확인할 만한 것: `vectorcraft-cli info FILE`(아트보드 · 개체 수 · 글꼴 · 가져오기 경고 JSON). 사용자가 넘긴 .ai/.svg 를 검사할 때 쓴다(미확인).

## 4. 전체 명령 분류 요약 (911개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| object | 151 | transform · align · distribute · group · pathfinder.* · clippingMask.make · blend.make · envelope.makeWithWarp · mesh.create · rasterize · textWrap.make · vectorHalftone |
| addon | 59 | arrange.grid · cleanup.* · color.* · pathtools.* · pen.* |
| select | 53 | all · set · same.fillColor · object.textObjects · magicWand |
| document | 35 | inspect · find · json · export · exportForScreens · exportPdf · formats |
| path | 34 | create · join · knife · freehand · blob · smoothRegion · mirrorCut |
| text | 33 | create · setText · setStyle · setRangeStyle · createInPath · fitHeadline · fontList · thread.* |
| edit | 30 | undo/redo · copy/paste · colors.invert/saturate/toGrayscale · findReplace |
| file | 28 | new · open · place · save · saveAs · export · exportForScreens · package · newPresets |
| layer | 26 | new · setProps · merge · releaseToLayers(Build) · hideOthers |
| perspective | 25 | grid.set · grid.preset · attach · draw |
| swatch | 23 | new · list · library.* |
| type | 23 | createOutlines · convertToAreaType · changeCase · fitHeadline |
| symbol | 23 | new · place · spray · replace · libraries |
| paint | 22 | setFill · setStroke · setGradientGeom · freeform.* |
| view | 19 | 미리보기 · 안내선 · 슬라이스 표시 |
| graphicStyle | 18 | new · apply · list · library |
| brush | 18 | list · apply · new · freehand · libraries |
| transparency | 17 | set(불투명도 · 블렌드 모드) · makeOpacityMask |
| appearance | 16 | addFill · addStroke · addEffect · moveItem · copyFrom |
| library | 16 | create · add · use · export/import |
| variable / dataset | 14 / 12 | define · bind · makeTextDynamic / new · import · select · export |
| artboard | 13 | new · setProps · fitToArt · rearrange · duplicate |
| clipboard | 12 | exportSvg · importSvg · exportPng |
| links | 11 | check · relink · embed |
| shape | 10 | rectangle · ellipse · polygon · star · flare · line · spiral · arc · rectangularGrid · polarGrid |
| stroke | 10 | set(굵기 · 점선 · 화살표 · 굵기 프로필) · widthPoint.set |
| charStyle / paraStyle | 10 / 9 | 문자 · 문단 스타일 |
| print | 9 | setup · preview · presets |
| effect | 8 | apply · list · setParams · remove · expandAppearance · lightingPreset (효과 카탈로그 130종) |
| livePaint / imageTrace | 8 / 8 | make · fill / make · makeAndExpand · presets · setView |
| plugin | 7 | list · run · install |
| 나머지 | ~70 | color(6) · graph(6) · guide(6) · flattener(6) · svgInteractivity(6) · assets(6) · gradient(5) · shaper(5) · pdf(5) · recolor(4) · pattern(4) · prefs(4) · colorTheme(4) · webExport(4) · dimension(3) · css(3) · 기타 |

**효과 카탈로그(130종) 분류**
- threeD 4
- convertToShape 3
- distort 6 (벡터) + 3 (래스터)
- path 3
- stylize: 벡터 2 + 래스터 4 + glowingEdges
- blur 3
- artistic 15
- brushStrokes 8
- sketch 14
- pixelate 4
- texture 6
- adjust 6
- warp 15
- pathfinder 13
- addon.color 5
- addon.path 9
- video 2
- rasterize · cropMarks

## 5. MCP (에이전트 직결)
- craft.json 의 실행: `vectorcraft-cli mcp --automation-read-root $ROOT --automation-write-root $WRITE`. 루트를 주면 headless 로 동작하고, 루트 밖 파일 읽기 · 쓰기는 거부된다. 설정도 남기지 않는다.
- 도구 33개를 확인했다. 쇼츠 제작에 쓸 것:
  - `command_batch`: 최대 256단계, `atomic` 옵션, `"$N.id"` 참조.
  - `render_preview`: 인라인 PNG, `max_side` 기본 1024. 에이전트가 그리면서 바로 보는 데 쓴다.
  - `draw_path` · `draw_shape`: `fill` · `stroke` · `effects` 를 한 번에 지정.
  - 그 밖에 `apply_effect` · `create_graph` · `export`.
- 앱을 띄워 사람이 실시간으로 보게 하려면 `vectorcraft --control 7979` + `mcp --connect 127.0.0.1:7979` 를 쓴다(미확인).

## 6. 위험 · 주의 정리
- 글꼴: Pretendard 를 불러오지 못한다(woff2 검색 대상 아님, 비동기 검색). 자막 글꼴과 맞추려면 Noto Sans CJK KR 을 쓰거나 Pretendard .otf 를 따로 받아 시험해야 한다(미확인).
- 기본 선: `shape.*` 에 검은 1pt 선이 붙는다.
- 내보내기: export 형식은 확장자로 정해지지만, `action.batch` 의 overrideExport 는 `format` 을 명시해야 PNG 가 된다.
- 효과 색: recolor 가 효과 색을 바꾸지 않는다.
- 레이어 내보내기: 레이어별 PNG 는 내용 크기로 잘린다.
- 버전: 활발히 개발 중(v0.21.0)이라 params 가 바뀔 수 있다. 업데이트 뒤에는 `vectorcraft-cli commands` 로 다시 확인한다.

## 7. 공식 문서
- 저장소: https://github.com/storytold/vectorcraft (README · `examples/*.vectorcraft`: neon-drive · still-life · feature-sheet 등은 명령 API 로 만든 예시)
- MCP · 헤드리스 CLI · 파라미터 규칙: https://github.com/storytold/vectorcraft/blob/main/docs/mcp.md (약 7,000줄; Headless batch CLI · Parameter keys · Symbols/variables/Image Trace · Recolor 절)
- 제어 프로토콜: https://github.com/storytold/vectorcraft/blob/main/docs/control-protocol.md
- 효과 대응표: https://github.com/storytold/vectorcraft/blob/main/docs/effects-parity.md
- 이미지 트레이스 품질: https://github.com/storytold/vectorcraft/blob/main/docs/image-trace-quality.md
- 3D: https://github.com/storytold/vectorcraft/blob/main/docs/three-d.md
- 부족한 점: https://github.com/storytold/vectorcraft/blob/main/docs/gaps.md
- 홈페이지: https://getartcraft.com/apps/vectorcraft
