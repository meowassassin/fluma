# PhotoCraft 참고 (v0.20.1)

> 한 줄 요약: Photoshop 류 이미지 편집기(Rust). 레이어 · 마스크 · 조정 레이어 · 레이어 스타일 · 글자 · 도형 · 필터 · PSD 를 **명령 954개**로 전부 창 없이 쓴다. 쇼츠에선 "실제 화면(캡처 · 기사 · 사진)을 9:16 장면 카드로 다듬는 곳" — 자르기 · 배경 흐림 채우기 · 스포트라이트 · 강조 박스 · 제목 글자 · 워터마크 지우기 · 레이어별 PNG 내보내기 · 데이터 세트(CSV)로 같은 틀 여러 장.

- CLI: `tools/crafts/photocraft/app/photocraft-0.20.1-linux-x86_64/bin/photocraft-cli` (아래 `$P`)
- 명령 목록 원본: 같은 폴더 `commands.json`(`$P commands --json`), 하나만 보기: `$P commands --json --filter type.create`

## 지금 Fluma 에서 쓰는 곳

- `scripts/craft/adapters/photocraft.py` — 재료 `type: photo`(기본 `materials.photo()` 를 덮어씀). 입력은 **위치 인자**(`photocraft-cli run <FILE> --cmd …`, `--in` 은 없다 — 예전 기본 어댑터가 이것 때문에 늘 실패했고 고쳤다).
  - `cutout`: `select.subject` → `layer.layerMask.revealSelection` → `select.deselect`. 고전 알고리즘이라 단순 배경에서만 쓸 만하다.
  - `clean: [[x,y,w,h]…]`: 상자마다 긴 변을 따라 `paint.remove` 한 획(여러 상자는 strokes 한 번). 큰 상자 · 복잡한 배경은 번짐이 남을 수 있다.
  - `alpha_text`: `layer.new.layerFromBackground` → `filter.other.colorToAlpha` → `image.trim`(기본).
  - `frame: "card"`: 9:16(또는 16:9 · 1:1) 장면 카드 PSD — Backdrop(같은 사진 흐림) · Backdrop Dim · Vignette · Photo(스마트 오브젝트, 벡터 마스크 둥근 모서리, 그림자, 흰 테두리) · Highlight(노란 둥근 상자, `spotlight` 면 밖을 어둡게) · Title(Noto Sans CJK KR 900, 고르게 줄 나눔). PSD 를 `work/<id>.psd` 에 남기고 PNG 로 바꾼다. 카드 하나 0.8~1.5초.
  - 사람이 PSD 를 고치면(기록 editable_hash 와 다름) 다시 짜지 않고 그 PSD 를 PNG 로(`edited_by_hand`). `materials.build` 열쇠에도 들어가 다시 만든다.
  - 기록: `size` · `cleaned` · 카드면 `frame` · `photo_box` · `highlight_box`(0~1) · `full_frame: true` · `as: image` · `editable`(.psd).
- `web/server.mjs` — 올린 png/jpg/webp 를 사진 자산(app: photocraft, 원본 형식 `.pcraft`)으로 보여 준다.
- `scripts/doctor.py` `CORE_CRAFTS` 에 들어 있다. `craft.json` `agent: true` → 홈 에이전트에 MCP(`photocraft-cli mcp --automation-read-root $ROOT --automation-write-root $WRITE`)로 붙는다.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(확인) | 안 된다 · 미확인 |
|---|---|
| 파일 열기 · `--new` 새 문서 · 명령 여러 개 순서대로 · 저장(png/jpg/psd/webp/tif…) | **ML 모델 없음**(문서 gaps G15): Select Subject/Sky · Object Finder 는 고전 알고리즘(GrabCut 계열). 사람 · 복잡한 배경 누끼는 품질 낮음(확인) |
| 레이어 · 조정 레이어 · 레이어 스타일 · 글자(한글 폰트) · 도형 · 필터 | Generative Fill/Expand · Neural Filters · Sky Replacement · Super Zoom 없음 |
| PSD 로 저장하면 레이어 유지, PNG 로 저장하면 평탄화(경고 출력) | 앱 화면 스크린샷(`photocraft --control` 데스크톱 앱 필요, 미확인) |
| `file.export.layersToFiles` 로 레이어마다 PNG | 타임라인 · 비디오 레이어(`timeline.*`, `file.export.renderVideo`) 미확인 |
| 데이터 세트(CSV) → 장마다 PNG | `.atn` 액션 재생 미확인 |
| `batch` 폴더 일괄 · `serve` JSON-lines 세션 · `mcp` | |
| 내용 인식 채우기 · Remove 툴(워터마크 · 로고 지우기) | |

속도: 1080×1920 장면 카드 하나(배경 + 사진 배치 + 스타일 + 글자 + 도형) 0.5초 안팎.

## 기본 형태

```sh
P=tools/crafts/photocraft/app/photocraft-0.20.1-linux-x86_64/bin/photocraft-cli
$P run in.jpg --cmd ID --params '{JSON}' --cmd ID2 --out out.png   # 파일 열고 → 명령 → 저장
$P run --new '{"width":1080,"height":1920,"background":"#111418"}' --cmd ... --out card.psd
$P info file.psd --compact            # 크기 · 레이어 트리(id · 이름 · bounds) JSON
$P convert card.psd card.png          # 형식 변환(평탄화)
$P batch --actions steps.json --in DIR --out DIR --format png
$P serve --automation-read-root R --automation-write-root W   # stdin JSON-lines 세션
```

- 각 `--cmd` 결과가 한 줄 JSON(`{"command","result"}`)으로 나온다. 실패하면 `Error: ...` 하고 멈춘다(뒤 명령 안 돎).
- `--params` 는 바로 앞 `--cmd` 의 것. 경로 인자(`file.placeEmbedded.path`, `dir` 등)는 **절대 경로**로.
- `--out` 이 입력과 같으면 거부(`--in-place` 필요).
- 글자 `y` 는 **첫 줄 기준선**(baseline)이다. 위쪽 끝이 아니다. `type.create` 결과의 `bounds` 로 실제 자리를 확인.
- **레이어 id 는 저장 · 다시 열기에서 바뀐다(확인).** 새 문서에서 8번이던 Title 이 PSD 를 다시 열면 6번. 다시 연 뒤엔 `info` 나 `layer.list` 로 id 를 다시 읽는다. `image.variables.define` 의 `layer` 는 이름을 못 받고 숫자 id 만 받는다(확인).

## 쇼츠용 핵심 기능

### 1. 9:16 장면 카드 — 실제 화면을 세로 틀에 (확인)

캡처 · 기사 화면을 세로 배경 위에 얹고 그림자 · 테두리 · 제목을 붙인다. 결과 PSD 는 사람이 PhotoCraft 에서 바로 고친다.

```sh
$P run --new '{"width":1080,"height":1920,"background":"#111418","name":"card"}' \
 --cmd layer.newFillLayer.gradient --params '{"from":"#1b2a4a","to":"#0b0d12","angle":90,"style":"linear"}' \
 --cmd file.placeEmbedded --params '{"path":"/abs/a.jpg","scale":250,"center":[540,1080]}' \
 --cmd layer.layerStyle.dropShadow --params '{"color":"#000000","opacity":70,"distance":18,"size":40,"angle":90}' \
 --cmd layer.layerStyle.stroke --params '{"size":6,"position":"outside","color":"#ffffff","add":true}' \
 --cmd type.create --params '{"x":540,"y":300,"text":"교장이 5400만원을\n사비로 메웠다?","align":"center","font":"Noto Sans CJK KR","weight":900,"size":96,"color":"#ffffff","name":"Title"}' \
 --cmd layer.layerStyle.stroke --params '{"size":10,"position":"outside","color":"#000000"}' \
 --cmd shape.create --params '{"kind":"roundedRect","rect":[60,1290,960,190],"radii":24,"fill":null,"stroke":{"width":10,"color":"#ffd60a","align":"center"},"name":"Highlight"}' \
 --out card.psd
$P convert card.psd card.png
```

- 시험 결과: `out/card.png` 1080×1920. 한글 제목 + 검은 외곽선, 기사 캡처 + 그림자, 노란 강조 박스 모두 제대로 그려짐.
- `file.placeEmbedded`: `scale` 은 원본 크기 기준 %, `center` 는 캔버스 좌표. 기본은 스마트 오브젝트(나중에 `layer.smartObjects.replaceContents` 로 그림만 바꿈). 필터를 픽셀에 바로 걸려면 `"smartObject":false`.
- 쓸 수 있는 한글 폰트(`type.fonts`): `Noto Sans CJK KR`, `Noto Serif CJK KR`, `NanumGothic`. Pretendard 는 시스템 폰트에 없어 목록에 없다(저장소 `public/fonts/` 의 woff2 는 못 씀, 미확인).
- 강조 박스 · 화살표: `shape.create` `kind` = rect · roundedRect · ellipse · polygon · star · line(`arrowEnd:true`) · path.

### 2. 가로 사진 → 세로: 흐린 배경 채우기 + 스포트라이트 (확인)

```sh
$P run --new '{"width":1080,"height":1920,"background":"black"}' \
 --cmd file.placeEmbedded --params '{"path":"/abs/land.png","scale":240,"center":[540,960],"smartObject":false}' \
 --cmd filter.blur.gaussianBlur --params '{"radius":40}' \
 --cmd layer.newAdjustmentLayer.brightnessContrast --params '{"brightness":-60}' \
 --cmd file.placeEmbedded --params '{"path":"/abs/land.png","scale":90,"center":[540,960]}' \
 --cmd layer.layerStyle.dropShadow --params '{"opacity":60,"distance":0,"size":50}' \
 --cmd select.rect --params '{"x":480,"y":700,"width":420,"height":380,"feather":20}' --cmd select.inverse \
 --cmd layer.newAdjustmentLayer.hueSaturation --params '{"lightness":-55,"saturation":-60}' \
 --cmd select.deselect \
 --cmd layer.newAdjustmentLayer.colorLookup --params '{"lut":"tealOrange","opacity":0.6}' \
 --out vertical_spot.png
```

- 시험 결과: `out/vertical_spot.png`. 위아래가 같은 사진의 흐린 판으로 채워지고, 지정한 사각형 밖은 어둡고 채도가 빠져 그 부분만 눈에 띈다.
- 선택 영역이 있을 때 조정 레이어를 만들면 그 선택이 마스크가 된다. 스포트라이트 = `select.rect`(또는 `"ellipse":true`) → `select.inverse` → 조정 레이어.
- `select.rect` 는 `{"x","y","width","height"}`. `rect:[...]` 는 거부된다(확인).
- 움직이는 스포트라이트는 EffectCraft 쪽 일이다. 여기선 정지 카드나 레이어를 만든다.
- 내장 LUT(`colorLookup.lut`): warm · cool · tealOrange · bleachBypass · fadedFilm · dayForNight · monoContrast · crossProcess. `.cube/.3dl/.look` 파일도 `file` 로.

### 3. 워터마크 · 로고 · 개인정보 지우기 (확인)

```sh
# Remove 툴(붓질 경로) — 더 자연스러웠다
$P run in.jpg --cmd paint.remove --params '{"points":[[880,1550],[1060,1550]],"size":80}' --out clean.png
# 내용 인식 채우기(사각형 선택)
$P run in.jpg --cmd select.rect --params '{"x":860,"y":1505,"width":210,"height":90}' \
 --cmd edit.contentAwareFill --params '{}' --cmd select.deselect --out clean.png
```

- 시험 결과: `out/wm_compare2.jpg`(Remove), `out/wm_compare.jpg`(채우기). 둘 다 글자는 없어졌다. Remove 는 주변 보케와 이어지고, 사각형 채우기는 경계가 네모나게 보였다.
- `paint.remove`: `strokes` 로 여러 획을 한 번에, `"newLayer":true` 면 원본을 두고 새 레이어에. 백그라운드 작업이지만 `run` 은 끝날 때까지 기다린다.
- 개인정보 가리기는 지우기보다 `select.rect` → `filter.pixelate.mosaic` 이나 `filter.blur.gaussianBlur` 가 안전하다(미확인 — 명령은 있음).

### 4. 캡처 글자를 투명 오버레이로: Color to Alpha (확인)

흰 배경 화면(기사 제목 · 문서 · 코드)의 글자만 남겨 영상 위에 얹는다.

```sh
$P run a.jpg --cmd image.crop --params '{"x":0,"y":300,"width":360,"height":60}' \
 --cmd layer.new.layerFromBackground --cmd filter.other.colorToAlpha --params '{"color":"#ffffff"}' --out title.png
```

- 시험 결과: `out/title_alpha_pink.jpg`. 일본어 기사 제목 글자만 남고 흰 배경이 투명해졌다. 글자 가장자리도 깨끗하다.
- Background 레이어는 투명을 못 가지므로 `layer.new.layerFromBackground` 를 먼저 쓴다.

### 5. 누끼(배경 없애기) — 쓸 수는 있지만 조심 (확인, 품질 낮음)

```sh
$P run in.jpg --cmd layer.removeBackground --params '{}' --cmd image.trim --out cut.png
# 대상 사각형을 알면
$P run in.jpg --cmd select.object --params '{"rect":[x,y,w,h]}' \
 --cmd select.refineEdge --params '{"smartRadius":true,"radius":4,"smooth":20,"output":"layerMask"}' --out cut.png
```

- 시험 결과: 캐릭터 그림(`out/bug_cutout_onpink.jpg`)은 렌즈 원 안의 배경까지 같이 남았다. 사진 속 사람(`out/woman_pink.jpg`)은 몸이 조각나 **쓸 수 없는** 수준이었다. 모델 없는 고전 알고리즘이라 그렇다(gaps G15).
- 대비가 크고 배경이 단순한 대상(흰 배경 제품, 단색 배경 로고)에만 쓴다. 단색 배경이면 `select.magicWand {"x","y","tolerance"}` 나 4번 Color to Alpha 가 더 낫다.
- 결과는 렌더해서 분홍 배경 위에 합쳐 보고 판단한다(투명 PNG 를 그냥 Read 하면 투명이 흰색으로 보인다).
- 사람 누끼가 꼭 필요하면 다른 도구를 쓴다(LightCraft 의 SAM 3 는 3.4 GB 다운로드가 필요해 금지, 문서만 확인).

### 6. 레이어별 PNG 내보내기 → 움직임 단계 재료 (확인)

```sh
$P run card.psd --cmd file.export.layersToFiles --params '{"dir":"/abs/out/layers","format":"png","prefix":"card","trim":true}'
```

- 결과: `card_0000_Highlight.png`, `card_0001_Title.png`, `card_0002_a.png`, `card_0003_Gradient Fill 1.png`, `card_0004_Background.png`. 위 레이어부터 번호가 붙는다. `trim:true` 면 내용 크기로 잘림(Title 800×227).
- 잘린 레이어의 원래 위치는 `info`/`layer.list` 의 `bounds` 로 받아 EffectCraft 배치에 쓴다.
- 한 레이어만: `layer.exportAs {"layer":id,"path":"/abs/x.png","scale":100}`.

### 7. 같은 틀 여러 장: 변수 + 데이터 세트(CSV) (확인)

당일 시세(format-daily) · 순위 · 비교처럼 틀은 같고 글자 · 그림만 바뀌는 카드.

```sh
printf 'name,title\nd1,오늘 금값 1돈 52만원\nd2,오늘 은값 1돈 7천원\n' > ds.csv
$P run card.psd \
 --cmd image.variables.define --params '{"defs":[{"name":"title","layer":6,"type":"textReplacement"}]}' \
 --cmd file.import.variableDataSets --params '{"path":"/abs/ds.csv"}' \
 --cmd file.export.dataSetsAsFiles --params '{"dir":"/abs/out/ds","format":"png","naming":"{name}"}' \
 --out card_tpl.psd
```

- 시험 결과: `Data_Set_1.png`, `Data_Set_2.png` 두 장. 제목이 CSV 값으로 바뀌고 외곽선 스타일도 그대로였다(`out/ds1_top.jpg`).
- `layer` 는 숫자 id 만(위 주의). `type`: `visibility` · `textReplacement` · `pixelReplacement`(그림 바꾸기, `method: fit|fill|asIs|conform`).
- `naming:"{name}"` 을 줘도 CSV 첫 열 이름이 아닌 `Data_Set_N` 으로 나왔다. 첫 열 머리글 규칙은 미확인. 순서로 짝을 맞춘다.
- 한 장만 바꿀 땐 `image.applyDataSet {name|index}` 다음 `--out`.

### 8. 사진 자동 보정 · 크기 맞추기 일괄 (확인)

```sh
echo '[["image.autoTone",{}],["file.automate.fitImage",{"width":1080,"height":1920}],["filter.sharpen.unsharpMask",{"amount":60,"radius":1,"threshold":0}]]' > grade.json
$P batch --actions grade.json --in DIR --out OUT --format png
```

- 결과: 두 장 다 ok. `fitImage` 는 기본으로 작은 그림도 키운다(360×574 → 1080×1722). 키우지 않으려면 `"dontEnlarge":true`.
- 그 밖에 `image.autoContrast` · `image.autoColor` · `image.adjustments.shadowsHighlights`. 색 보정을 제대로 하려면 LightCraft 가 낫다(lightcraft.md).

### 9. 얼굴 찾기 → 자르기 · 가리기 기준 (확인)

```sh
$P run in.jpg --cmd image.detectFaces --params '{"minScore":0.3}'
```

- 결과: `faces:[{score, rect:[x,y,w,h], landmarks:{leftEye,rightEye,nose,mouthLeft,mouthRight}}]`. 고개 숙인 기자회견 사진에서도 얼굴 여러 개를 찾았다. 모델 다운로드 없이 된다.
- 쓰임: 9:16 자를 때 얼굴이 가운데 오게 `image.crop`, 일반인 얼굴 모자이크(`select.rect` → `filter.pixelate.mosaic`).

### 10. serve — 한 세션에서 여러 문서 (확인)

```sh
printf '%s\n' '{"id":1,"method":"doc.open","params":{"path":"/abs/land.png"}}' \
 '{"id":2,"method":"engine.execute","params":{"command":"image.autoTone","params":{}}}' \
 '{"id":3,"method":"doc.save","params":{"path":"/abs/out/x.png"}}' \
 | $P serve --automation-read-root /abs --automation-write-root /abs/out
```

- 메서드: engine.execute · engine.commands · doc.open/new/place/replaceSmartObject/save/exportLayers/exportDataSets/importDataSets/inspect/render/select/close · session.list · batch · jobs.list/cancel · methods.
- `doc.render` 로 미리보기 PNG 를 받아 에이전트가 직접 본다(미확인 — 메서드만 확인).

### 그 밖에 쓸 만한 것 (미확인 — 명령 · params 만 확인)

- `filter.blurGallery.tiltShift {"blur":15,"centerY":0.5,"focus":0.1}` — 미니어처 느낌 감성 컷.
- `type.warpText {"style":"arc|flag|wave|bulge…","bend":50}` — 썸네일 제목 휘기.
- `layer.layerStyle.outerGlow` · `gradientOverlay` · `colorOverlay` — 네온 · 그라데이션 글자.
- `layer.newAdjustmentLayer.gradientMap {"stops":[[0,"#1b1b3a"],[1,"#ffd60a"]]}` — 두 색(듀오톤) 룩.
- `filter.gallery.halftonePattern` · `filter.pixelate.colorHalftone` · `filter.stylize.oilPaint` — 인쇄물 · 만화 느낌.
- `edit.contentAwareScale` · `image.crop {"contentAware":true}` — 가로 → 세로로 늘릴 때 빈 곳 채우기.
- `layer.new.artboard` + `file.export.artboardsToFiles` — 한 문서에 장면 여러 개.
- `file.automate.contactSheetII` — 여러 캡처를 한 장 격자로(비교 형식).

## 전체 명령 분류 요약 (954개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| layer | 224 | new.layer · duplicate · setProps · newAdjustmentLayer.* (16종) · layerStyle.* (10종) · layerMask.* · vectorMask.* · smartObjects.* · smartFilter.* · align/distribute · removeBackground · exportAs |
| filter | 124 | blur.* · blurGallery.* · sharpen.* · noise.* · distort.* · pixelate.* · stylize.* · render.* · gallery.* (35종) · other.colorToAlpha · liquify |
| edit | 79 | fill · stroke · transform(scale/rotate/quad/matrix) · warp · puppetWarp · contentAwareFill · contentAwareScale · copy/paste · preferences.* |
| type | 69 | create · edit · setStyle · fonts · warpText · attachToPath · characterStyle.* · paragraphStyle.* · openType.* |
| image | 66 | crop · trim · imageSize · canvasSize · adjustments.* · autoTone/Contrast/Color · detectFaces · variables.define · applyDataSet · mode.* |
| file | 58 | new · placeEmbedded · placeLinked · export.layersToFiles · export.artboardsToFiles · export.dataSetsAsFiles · automate.* · scripts.imageProcessor |
| select | 35 | rect · lasso · magicWand · colorRange · quick · object · subject · sky · focusArea · refineEdge · modify.* · inverse |
| view | 31 | guides · colorSamplers · proofSetup |
| paint | 28 | stroke · remove · spotHealing · cloneStamp · patch · contentAwareMove · dodge/burn · gradient · bucket |
| path | 25 | list · set · transform · toSelection · stroke · fill |
| channel | 22 | new · split · merge · target |
| actions | 19 | load · play · record · list |
| brush | 18 | presets.* · defineFromSelection |
| layerComp / history | 14 / 14 | layerComp.new/apply · file.export.layerCompsToFiles / history.newSnapshot |
| tools · gradient · swatches · document · pattern · shape | 13 · 12 · 12 · 11 · 10 · 9 | setColors / fill.* / list / inspect / list / create · info |
| style · count · slice · timeline | 7씩 | presets.apply / add / new / create |
| 기타(cloneSource · plugin · notes · prefs · jobs …) | 30 | |

## 공식 문서

- 저장소: https://github.com/storytold/photocraft (README: 기능 · PSD · Built for agents)
- 홈페이지: https://getartcraft.com/apps/photocraft
- MCP: https://github.com/storytold/photocraft/blob/main/docs/mcp.md
- 제어 프로토콜(serve · `--control`): https://github.com/storytold/photocraft/blob/main/docs/control-protocol.md
- 빠진 기능 목록(AI 기능 없음 G15 등): https://github.com/storytold/photocraft/blob/main/docs/gaps.md
- 자동화 책: https://github.com/storytold/photocraft/tree/main/book/src/automation (cli · mcp · control-protocol · security-model)
- 사용자 문서: https://github.com/storytold/photocraft/tree/main/docs/user
