# LightCraft 참고 (v0.18.0)

> 한 줄 요약: Lightroom 류 사진 보정기 · RAW 현상기(Rust). 노출 · 톤 · 색 · 컬러 그레이딩 · 그레인 · 비네트 · 프리셋 41개 · 프로필 22개 · 로컬 마스크(방사형 · 선형 · 붓) · 잡티 지우기 · 자르기 · 워터마크를 **명령 380개 + 현상 슬라이더(controls)** 로 창 없이 쓴다. 쇼츠에선 "직접 찍은 사진 · 현장 스틸을 한 영상 안에서 같은 색감으로 맞추는 곳"(감성 · 광고 형식). 원본은 안 건드리고 설정만 바꿔 내보낸다(비파괴).

- CLI: `tools/crafts/lightcraft/app/lightcraft-0.18.0-linux-x86_64/bin/lightcraft-cli` (아래 `$L`)
- 명령 · 슬라이더 원본: 같은 폴더 `commands.json`(`$L commands --json`), `controls.txt`(`$L controls`)

## 지금 Fluma 에서 쓰는 곳

- `scripts/craft/adapters/lightcraft.py` — 재료 `photo_grade`. LightCraft 세션 한 번: `preset.apply`(세기) → (선택) 자동 보정 → `develop.set` → `crop.set` → `develop.get` → `app.export`(dontEnlarge=false).
- Fluma 룩 4개: warm(lc.warm-glow + 색온도 · 밝은 곳 따뜻하게 · 비네트) · film(lc.warm-film + 그림자 청색 · 비네트) · clean(lc.clean-studio + 채도 조금) · mono(lc.bw-soft + 대비). JPEG 에서는 프리셋만으로는 차이가 작아 슬라이더를 더했다.
- `develop.auto` 는 너무 세다(대비 +68) → 값만 읽어 40% 로 줄이고 상한을 둬 `develop.adjust`(clean 만 기본).
- 자르기 비율은 사진 크기로 직접 계산(`crop.aspect` 안 씀), `focus` 로 가운데 이동, 1~3px 어긋나면 1080×1920 으로 맞춤. `credit` 은 오른쪽 위 한글 워터마크.
- 편집 파일은 현상 설정 JSON(`<id>.lightcraft.json`) — `render --settings` 로 다시 내면 같은 결과(평균 픽셀 차 0.02). 한 장 0.3~0.5초.
- AI 마스크 · Denoise · 얼굴은 모델이 필요해 안 쓴다. RAW 처럼 PIL 이 못 여는 사진은 자르지 않는다.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(확인) | 안 된다 · 미확인 |
|---|---|
| `render` 한 줄: 파일 → 현상 → 내보내기(jpg/png/tif/webp/avif/jxl/psd/dng) | **AI 마스크(피사체 · 하늘 · 배경 · Object · Describe)** 는 SAM 3 모델(3.4 GB, Meta SAM License) 필요 → 다운로드 금지. `mask.add kind=sky` 가 모델 없이도 `ok` 를 돌려줘 실패가 안 보인다(확인). 쓰지 말 것 |
| 슬라이더 `--set`, 프리셋 `--preset`, 부분 설정 JSON `--settings` | AI Denoise(`denoise.*`) · 얼굴 찾기(`faces.detect`, YuNet) · 잡티 자동(`spot.findBlemishes`)은 모델 다운로드 필요 → 금지, 문서만 확인 |
| `run --import` 으로 여러 명령: 자동 보정 · 자르기 · 마스크 · 잡티 지우기 · 내보내기 | 슬라이드쇼 영상(`slideshow.export video`)은 AV1 · 소리 없음 · 팬/줌 없음(문서). 쇼츠엔 안 맞음, 시험 안 함 |
| 폴더 일괄: 선택 전체에 프리셋 → `app.export dir=` | HDR · 파노라마 합치기(`merge`)는 시험 안 함 |
| 내보낼 때 글자 워터마크(한글 · 한자 됨) | `--library` 영구 라이브러리는 시험 안 함(`--import` 는 임시 세션) |
| `snapshot`: 앱 UI 전체를 창 없이 PNG(1080×1920 가능) | |

속도: 1200×800 한 장 `render` 0.1~0.4초.

## 기본 형태

```sh
L=tools/crafts/lightcraft/app/lightcraft-0.18.0-linux-x86_64/bin/lightcraft-cli
$L render in.jpg -o out.png --preset lc.warm-film --set light.exposure=0.3 --size 1920
$L run --import /abs/in.jpg develop.auto app.export path=/abs/out.jpg longEdge=1920
$L controls        # 슬라이더 id · 범위 · 기본값
$L commands --json # 명령 id · params
```

- `run` 문법: `=` 없는 낱말이 새 명령을 시작하고, `key=value` 는 그 명령의 params. 값은 JSON 으로 읽힌다(`rect='[0.45,0,0.825,1]'`, `values='{"exposure":-1}'`). 명령마다 한 줄 JSON `{"command","ok","result","ms"}`. 실패하면 멈춘다(`--keep-going` 으로 계속).
- 좌표는 거의 다 **0~1 정규화**(자르기 `rect`, 마스크 `center`, 잡티 `points`).
- **내보내기는 기본으로 키우지 않는다**(`dontEnlarge` 기본 true, 확인). 작은 그림을 1920 으로 키우려면 `app.export ... height=1920 dontEnlarge=false`. `render --size` 도 같다(미확인 — `--opt dontEnlarge=false` 로 줄 것).
- `render` 는 크기 옵션이 없으면 원본 크기(잘린 크기)로 쓴다. `app.export` 는 기본 긴 변 3000.

## 쇼츠용 핵심 기능

### 1. 프리셋 한 줄로 룩 맞추기 (확인)

```sh
$L render in.png -o out.jpg --preset lc.cinematic --set effects.clarity=20 --set vignette.amount=-30 --size 1080
$L render in.png -o bw.jpg --preset lc.bw-high-contrast
```

- 시험 결과: `out/cmp2.jpg` 왼쪽(흑백 고대비), `out/cmp1.jpg` 가운데(cinematic). 프리셋 위에 `--set` 을 덧붙일 수 있다.
- 내장 프리셋 41개(`presets.list`):
  - Color: `lc.warm-glow` `lc.cool-morning` `lc.teal-orange` `lc.vivid-pop` `lc.soft-pastel`
  - Film: `lc.faded-matte` `lc.warm-film` `lc.muted-film` · Vintage: `lc.instant-70s` `lc.cross-process` `lc.bleach-bypass`
  - B&W: `lc.bw-high-contrast` `lc.bw-soft` `lc.bw-selenium` `lc.bw-sepia`
  - Style: `lc.moody` `lc.cinematic` · Urban: `lc.gritty-street` `lc.neon-night` `lc.concrete-cool` `lc.faded-urban`
  - Portrait: `lc.soft-skin` `lc.bright-airy` `lc.moody-portrait` `lc.golden-glow` `lc.clean-studio`
  - Landscape: `lc.crisp-landscape` `lc.golden-hour` `lc.blue-hour` `lc.crisp-vista` `lc.deep-sky` `lc.lush-greens` `lc.desert-warmth` `lc.misty-morning`
  - Food: `lc.fresh-bright` `lc.warm-table` `lc.dark-moody-food` · Seasons: `lc.autumn-gold` `lc.winter-blue` `lc.spring-fresh` `lc.summer-haze`
- 형식별 추천(판단): 감성 → `lc.warm-film` · `lc.faded-matte` · `lc.soft-pastel`, 광고(음식 · 매장) → `lc.fresh-bright` · `lc.warm-table`, 기술 · 뉴스 → 프리셋 없이 `develop.auto` 정도만.
- JPEG/PNG 에선 효과가 RAW 보다 약하다. 시험한 저해상도 jpg 에서 cinematic 은 차이가 작았다(평균 픽셀 차 7~10).

### 2. 슬라이더 직접: 컬러 그레이딩 · 그레인 · 비네트 (확인)

```sh
$L render in.png -o graded.jpg \
 --set grading.shadows.hue=210 --set grading.shadows.sat=60 \
 --set grading.highlights.hue=40 --set grading.highlights.sat=45 \
 --set grain.amount=35 --set vignette.amount=-50 --set effects.clarity=-20
```

- 시험 결과: `out/cmp4.jpg` 왼쪽. 그림자는 푸르고 밝은 곳은 따뜻해졌다. 그레인과 비네트도 보인다.
- 자주 쓸 슬라이더(`controls`, 전체 약 140개):
  - 빛: `light.exposure`(-5~5) `light.contrast` `light.highlights` `light.shadows` `light.whites` `light.blacks`(-100~100)
  - 색: `wb.temp`(2000~50000) `wb.tint` `color.vibrance` `color.saturation`, `mixer.<red|orange|yellow|green|aqua|blue|purple|magenta>.<hue|sat|lum>`
  - 그레이딩: `grading.<shadows|midtones|highlights|global>.<hue 0~360|sat 0~100|lum>`, `grading.blending` `grading.balance`
  - 효과: `effects.texture` `effects.clarity` `effects.dehaze`, `vignette.amount` `vignette.midpoint` `vignette.feather`, `grain.amount` `grain.size` `grain.roughness`
  - 선명 · 노이즈: `detail.sharpenAmount`(0~150) `detail.nrLuminance` `detail.nrColor`
  - 기하: `geometry.vertical` `geometry.horizontal` `geometry.rotate` `crop.angle`(수평 맞추기)
- 상대 조정은 `develop.adjust control=light.exposure delta=0.3`.

### 3. 자동 보정 (확인)

```sh
$L run --import /abs/in.png develop.auto app.export path=/abs/out.jpg longEdge=1920
```

- 결과(`develop.auto` 가 돌려준 값): `exposure -0.74, contrast 68, highlights -66, shadows 52, vibrance 30`. 밝은 실내 사진이 꽤 어두워졌다(`out/land_9x16.jpg`). 자동값을 그대로 믿지 말고 렌더를 보고 `develop.adjust` 로 다듬는다.
- 흰색 맞추기: `develop.wb mode=auto`(또는 daylight · cloudy · tungsten …), 회색 점 찍기 `develop.wbPick x=.. y=..`.

### 4. 9:16 자르기 (확인)

```sh
# 1200×800 가로 사진에서 세로 9:16: 폭 비율 = 800*9/16/1200 = 0.375
$L run --import /abs/land.png crop.set rect='[0.45,0,0.825,1]' \
 app.export path=/abs/c916.jpg height=1920 dontEnlarge=false
# render 로는 설정 JSON 으로
echo '{"crop":{"geometry":{"rect":{"x0":0.45,"x1":0.825,"y0":0,"y1":1}}}}' > crop916.json
$L render land.png -o c916.jpg --settings crop916.json --preset lc.teal-orange
```

- 시험 결과: 450×800(정확히 9:16), `dontEnlarge=false` 를 주면 1080×1920.
- `crop.aspect aspect='[9,16]'` 은 비율만 잠그고, 그 뒤 `crop.set rect` 가 비율을 덮어쓴다(확인: 384×800 이 나옴). 비율은 rect 를 직접 계산해 준다.
- `--settings` 의 crop 스키마는 `{"crop":{"geometry":{"rect":{x0,x1,y0,y1}}}}`. `{"crop":{"rect":[...]}}` 은 조용히 무시된다(확인).
- 얼굴 기준 자르기는 모델이 필요(`faces.detect`) → PhotoCraft `image.detectFaces`(모델 없이 됨)로 좌표를 받아 여기 rect 로 넘긴다.

### 5. 로컬 마스크: 방사형 스포트라이트 · 선형 그라데이션 (확인)

```sh
$L run --import /abs/land.png \
 mask.add kind=radial center='[0.5,0.45]' rx=0.2 ry=0.3 feather=50 name=spot \
 mask.invert mask.adjust values='{"exposure":-2}' \
 app.export path=/abs/radial.jpg longEdge=1200
```

- 시험 결과: `out/land_radial.jpg`. 가운데 원 밖이 어두워졌다(효과는 은은한 편).
- `mask.adjust values`: exposure · contrast · highlights · shadows · whites · blacks · temp · tint · texture · clarity · dehaze · hue · saturation · sharpness · noise · amount.
- 선형: `mask.add kind=linear start='[0.5,0]' end='[0.5,0.4]'`(위쪽 하늘 어둡게). 시험에서 `ok` 는 나왔지만 원래 검은 영역이라 눈으로 확인은 못 함(미확인).
- 모델 없이 되는 종류: `brush` `linear` `radial` `luminanceRange` `colorRange`. 안 되는 종류: `sky` `subject` `background` `object` `prompt`.
- 마스크 효과를 프리셋처럼 저장 · 재사용: `mask.saveEffect` · `mask.applyEffect`(미확인).

### 6. 잡티 · 작은 로고 지우기 (확인, 부분)

```sh
$L run --import /abs/b.jpg spot.add mode=remove points='[[0.88,0.81],[0.97,0.81]]' size=0.04 \
 app.export path=/abs/b_clean.jpg longEdge=1920
```

- 시험 결과: `out/cmp3.jpg` 오른쪽. 워터마크 글자는 대부분 지워졌지만 `size` 가 작아 로고 일부가 남았다. `size` 는 긴 변 대비 비율.
- `mode`: remove · heal · clone · fill. 큰 영역은 PhotoCraft `paint.remove` 가 낫다(photocraft.md 3번).
- 센서 먼지 자동: `spot.findDust`(모델 필요 없음, 미확인).

### 7. 여러 장을 같은 룩으로 일괄 (확인)

```sh
$L run --import /abs/photos library.selectAll preset.apply id=lc.warm-film app.export dir=/abs/out longEdge=1080
```

- 시험 결과: 폴더의 2장 모두 프리셋이 걸려 `out/<이름>.jpg` 로 나왔다(평탄 렌더와 비교해 둘 다 달라짐).
- 한 장에서 만든 설정을 나머지에: `develop.copy` → `library.selectAll` → `develop.paste`, 또는 `develop.sync`(미확인).
- 노출을 장끼리 맞추기: `develop.matchExposure`(EXIF 노출 정보가 있는 사진만, 미확인).
- 감성 형식(켄번스 스틸 여러 장)에서 컷마다 색이 튀지 않게 하는 데 가장 효과가 크다.

### 8. 출처 워터마크 (확인)

```sh
$L render in.png -o out.jpg --opt 'watermark={"text":"출처: 朝日新聞","anchor":"bottomRight","size":0.04}'
```

- 시험 결과: `out/wm_crop.jpg`. 한글 · 한자 모두 그림자 있는 흰 글자로 오른쪽 아래에 나왔다.
- 옵션: `size`(짧은 변 대비 0.005~0.5) `opacity` `anchor` `inset` `rotation` `color [r,g,b]` `shadow` `vertical`(세로쓰기) `image`(그림 로고).
- 영상 자막과 겹치지 않게 9:16 에선 `anchor:"topRight"` 등으로 자막 · UI 영역을 피한다.

### 9. snapshot — LightCraft 화면 자체를 실제 화면 재료로 (확인)

"이 사진을 이렇게 보정했다" 식 설명 쇼츠에서 보정 앱 화면을 그대로 보여 줄 때.

```sh
echo '{"method":"ui.set","params":{"view":"detail"}}
{"method":"ui.settle","params":{"timeoutMs":5000}}' > snap.jsonl
$L snapshot /abs/land.png --script snap.jsonl -o /abs/ui.png --size 1080x1920
```

- 시험 결과: `out/ui.png` 1080×1920. 사진 · 히스토그램 · Light 패널 슬라이더가 진짜 앱 그대로 그려졌다(0.17초, GPU 없이).
- 스크립트에서 `{"method":"ui.screenshot"}` 를 여러 번 부르면 `OUT-2.png`, `OUT-3.png`… 연속 화면(보정 전후 단계별)이 된다(미확인). 쓸 수 있는 메서드는 docs/control-protocol.md 를 본다.

### 그 밖에 (미확인 — 명령 · params 만 확인)

- `develop.targeted target=hue x=.. y=..` — 화면의 한 점을 찍어 그 색 띠만 조정.
- `profile.import paths=[.cube]` — 3D LUT 를 프로필로. PhotoCraft 와 같은 LUT 를 공유할 수 있다.
- 프로필 22개(`profiles.list`): `lc.cine.teal-amber` `lc.cine.night-blue` `lc.cine.neon-dusk` `lc.film.warm-print` `lc.muted.pastel-haze` `lc.bw.mono-rich` 등. `develop.profile id=.. amount=0~200` 은 시험에서 `ok` 였고 결과도 나왔다(`out/cmp4.jpg` 오른쪽, 차이는 작음).
- `geometry.upright mode=auto` — 건물 · 간판 사진 기울기 자동 보정.
- `beforeAfter.*` + snapshot — 보정 전후 나란히 화면.
- `preset.create` / `preset.export path=x.lcpreset` — Fluma 전용 룩을 파일로 두고 `render --settings x.lcpreset` 로 재사용.

## 전체 명령 분류 요약 (380개 + 슬라이더 약 140개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| library | 47 | selectAll · select · browse · buildPreviews · autoImport |
| photo | 44 | rate · flag · label · analyze · convertToDng · allMetadata |
| mask | 31 | add · addComponent · adjust · invert · brushStroke · refine · saveEffect · applyEffect |
| develop | 29 | set · adjust · auto · wb · curve · profile · copy/paste · sync · matchExposure · get · reset |
| keyword | 23 | create · edit · import/export |
| faces | 21 | detect · models.download(금지) · index |
| print | 20 | cell.* · 인쇄 레이아웃 |
| denoise | 16 | models.*(다운로드 금지) · queue · status |
| album · slideshow · stack | 15 · 15 · 11 | create / export · preview · layout · templates / auto · group |
| preset · presets | 9 · 1 | apply · create · export · import(.lcpreset · XMP · .lrtemplate · Luminar) / list |
| crop · curve · export · metadata · spot | 7씩 | set · aspect · autoStraighten / applyPreset / presets · contactSheet / applyPreset / add · findDust |
| folder · label · beforeAfter · history · version | 6 · 6 · 5 · 5 · 5 | |
| filter · merge · segment | 4씩 | merge.hdr · panorama / segment.model.*(SAM 3, 다운로드 금지) |
| app · profile · redeye | 3씩 | app.export · app.gpu / profile.import |
| 기타(activity · catalog · edit · geometry · pointColor · profiles · albums · focus · journal) | 14 | geometry.upright · pointColor.pick |

CLI 하위 명령: `run` · `render` · `snapshot` · `mcp`(`--compact` · `--demo` · `--library` · `--connect`) · `merge` · `synth-merge` · `denoise-serve` · `commands` · `controls` · `calibrate`.

## 공식 문서

- 저장소: https://github.com/storytold/lightcraft (README "Built for agents")
- 홈페이지: https://getartcraft.com/apps/lightcraft
- MCP · `run`: https://github.com/storytold/lightcraft/blob/main/docs/mcp.md
- 제어 프로토콜(snapshot 스크립트 · ui.*): https://github.com/storytold/lightcraft/blob/main/docs/control-protocol.md
- AI 마스크(SAM 3): https://github.com/storytold/lightcraft/blob/main/docs/ai-masks.md
- 슬라이드쇼: https://github.com/storytold/lightcraft/blob/main/docs/slideshow.md
- 세로 워터마크: https://github.com/storytold/lightcraft/blob/main/docs/vertical-watermarks.md
- 빠진 기능: https://github.com/storytold/lightcraft/blob/main/docs/gaps.md
- 사용자 문서: https://github.com/storytold/lightcraft/tree/main/docs/user
