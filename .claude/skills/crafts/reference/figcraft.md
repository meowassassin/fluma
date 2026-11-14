# FigCraft 참고 (v0.15.0)

**한 줄 요약**: Figma 류 UI 디자인 앱. 헤드리스 `figcraft-cli run` 에 JSON 명령 스크립트를 넣으면 프레임 · 텍스트 · 이미지 · 오토레이아웃 · 그림자를 만들고, `export` 로 프레임/레이어 단위 PNG 를 뽑는다. 쇼츠에서는 **앱 · 웹 화면 목업(ui_mock)**, **실제 스크린샷을 폰 프레임에 넣은 장면**, **1080×1920 카드 여러 장 일괄 생성(data.fill)** 에 쓴다.

- 실행 파일: `tools/crafts/figcraft/app/figcraft-0.15.0-linux-x86_64/bin/figcraft-cli` (installed.json 의 `cli`)
- 명령 수: 635개 (`figcraft-cli commands --json`)
- 지금 Fluma 사용: **없음**. `engine/craft/apps/figcraft/craft.json` 에 `provides: ui_mock` 만 적혀 있고 `engine/craft/materials.py` 의 `ADAPTERS` 에 ui_mock 어댑터가 없다. `agent: false` 라 MCP 로도 기본은 안 붙는다(`studio/crafts.mjs` mcpServers).

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `engine/craft/adapters/figcraft.py` — 재료 `ui_mock`(`run` → `export --node Mock`). 실제 캡처를 iPhone 류 폰 틀(390×844 화면, 베젤 · 아일랜드 · 홈 표시줄 · 2단 그림자, 없으면 상태 표시줄 붙임) 또는 macOS 브라우저 창에 넣는다. device 를 안 주면 캡처 모양으로.
- 캡처가 없으면 `screen` 설명으로 iOS 문법 가상 화면 — 기록 `mock: true`, 콘티에도 `mock: true` 필수(검사 L39). 실제 서비스 설명에는 실제 캡처.
- **FigCraft 는 글자 단위로 줄을 바꾼다**('시험입/니다') → PIL 로 글자 폭을 재 낱말 경계에서 미리 끊는다. 공용 함수 `wrap` · `ellipsize` · `text_width` · `break_penalty`.
- 기록 `screen_box` · `item_boxes`(0~1) 는 overlay box 로 바로 쓸 수 있다.

## 헤드리스로 되는 것 / 안 되는 것

| 된다 (CLI) | 안 된다 / 미확인 |
|---|---|
| `run` 스크립트: 모든 문서 편집 명령(635개 중 편집 · 생성 · 스타일 계열) | 프로토타입 재생(`proto.present` / `proto.preview`)은 창이 필요 — 애니메이션 영상 출력 없음 |
| `export` PNG/JPG/WEBP/SVG/PDF, `--node` 로 레이어 하나, 폴더면 최상위 프레임마다 한 장 | 움직임(스마트 애니메이트)을 프레임으로 뽑는 명령 없음 → 움직임은 EffectCraft 몫 |
| `render` 페이지 전체(배경 포함) | `collab.*` · `plugin.directory.*` 는 `run` 에선 안 됨(네트워크 없음, `mcp` 헤드리스에선 됨) |
| `info --json` 으로 프레임 id · 크기 · 누락 폰트 | `font.download` 는 네트워크 — 시험 안 함(미확인) |
| `.fig` · `.sketch` · `.penpot` · `.svg` · REST JSON 열기(베스트 에포트) | `.fig` 가져오기 품질 미확인 |
| `mcp` (stdio, 헤드리스 또는 `--attach`) | |

스크립트는 **통째로 한 번에 성공하거나 전부 취소**된다. 한 단계라도 파라미터가 틀리면 `--out` 파일이 아예 안 써진다(시험에서 확인). 오류 문구에 허용 키 목록이 나오니 그걸 보고 고친다.

## 기본 사용법

```sh
F=tools/crafts/figcraft/app/figcraft-0.15.0-linux-x86_64/bin/figcraft-cli
$F run script.json [--in base.figcraft] --out result.figcraft   # 한 줄에 한 JSON 결과
$F export result.figcraft -o out.png --node "Shorts" --scale 1  # 레이어 이름 또는 id
$F export result.figcraft -o outdir/ --scale 2                   # 최상위 프레임마다 <이름>.png
$F info result.figcraft --json
$F commands --filter image.place                                # 파라미터 문서
```

스크립트 형식: `[{"command": id, "params": {...}, "as": "이름"}]`. 뒤 단계에서 `{"$ref": "이름"}` 이 앞 단계 결과의 `id` 로 바뀐다(`"field": "ids/0"` 로 다른 키). 새 문서의 첫 레이어 id 는 2.

파일 접근 제한: `--automation-read-root DIR --automation-write-root DIR` (Fluma MCP 설정과 같은 방식).

## 쇼츠용 핵심 기능

### 1. 실제 스크린샷을 폰 화면 프레임에 넣기 — verified
증거 화면을 소품처럼 보여 줄 때 쓸모 있다. 웹 캡처(webrec 결과 PNG)를 둥근 기기 프레임 + 그림자 + 제목과 함께 9:16 한 장으로.

```json
[
 {"command":"frame.create","as":"bg","params":{"x":0,"y":0,"width":1080,"height":1920,"name":"Shorts",
   "props":{"fills":[{"type":"linearGradient","stops":["#0F172A","#1E293B"]}]}}},
 {"command":"node.create","as":"phone","params":{"type":"frame","parent":{"$ref":"bg"},"x":140,"y":420,
   "width":800,"height":1300,"name":"Phone","props":{"fills":["#FFFFFF"],"cornerRadius":64,"clipsContent":true}}},
 {"command":"image.place","params":{"path":"shot.png","parent":{"$ref":"phone"},"x":0,"y":120,
   "width":800,"height":681,"name":"Screenshot","mode":"fill"}},
 {"command":"node.set","params":{"ids":[{"$ref":"phone"}],"props":{"effects":[
   {"type":"dropShadow","color":"#00000040","offset":[0,24],"radius":48}]}}},
 {"command":"node.create","params":{"type":"text","parent":{"$ref":"bg"},"x":80,"y":160,"width":920,
   "text":"점수 하나로 속도를 본다","name":"Title",
   "props":{"fontSize":84,"fontFamily":"Noto Sans CJK KR","fontWeight":900,"fills":["#FFFFFF"]}}}
]
```
`figcraft-cli export mock.figcraft -o mock.png --node Shorts` → 1080×1920 PNG 확인(제목 한글 · 스크린샷 · 둥근 모서리 정상).
- `image.place` `mode`: fill|fit|crop|tile. 결과에 원본 `width/height` 가 온다 → 비율 맞춰 높이 계산.
- 기본 `effect.add {type:"dropShadow"}` 는 radius 4 로 너무 약하다. `node.set props.effects` 로 직접 값 지정.
- 화면 일부 확대 · 동그라미 같은 움직임은 FigCraft 에서 하지 말고 PNG 를 넘겨 움직임 단계에서.

### 2. 시작 템플릿 8종 → 텍스트만 바꿔 실제 앱 같은 화면 — verified
`template.list` → `mobile-app`(390×844 화면 4장 + 컴포넌트), `landing-page`, `dashboard`(1440×960, 차트 · 표), `design-system`, `wireframe-kit`, `social-posts`(1080×1920 Story 포함 5크기), `slides`, `icon-set`.

```json
[{"command":"file.newFromTemplate","params":{"template":"mobile-app"}}]
```
그다음 텍스트 치환:
```json
[{"command":"edit.findReplace","params":{"find":"Popular this week","replace":"이번 주 인기 코스"}},
 {"command":"node.find","params":{"text":"Lantern"}},
 {"command":"text.set","params":{"id":105,"characters":"설악산 대청봉"}}]
```
`export mobile-ko.figcraft -o explore.png --node Explore --scale 2` → 780×1688 PNG, 한글 치환 정상(시험함).
- 템플릿 내용은 가상의 브랜드(Ridgeline Trails 등). 쇼츠에 그대로 쓰면 "가짜 앱" 이 된다 → **설명용 가상 화면**(예: "앱이 이런 식으로 보여요")에만. 실제 서비스 설명엔 1번(실제 캡처)을 쓴다.
- `edit.findReplace` 결과 `matches` 로 바뀐 레이어 id 확인. 못 찾으면 빈 배열(오류 아님).

### 3. data.fill — 한 프레임으로 장면 카드 여러 장 일괄 export — verified
쇼츠 장면마다 같은 레이아웃 카드(훅 · 증거 · CTA)를 데이터만 바꿔 뽑는다. 행의 키 = 복사본 안 레이어 이름.

```json
[
 {"command":"object.rename","params":{"ids":[46],"name":"Headline"}},
 {"command":"data.fill","params":{"id":38,"dir":"/abs/out/cards","scale":1,"rows":[
   {"name":"01-hook","Kicker":"무료 AI 툴 3가지",
    "Headline":{"text":"이 사이트 하나면 디자인 끝납니다","fit":{"maxLines":3}},"CTA":"저장해 두세요"},
   {"name":"02-proof","Headline":{"text":"5분 만에 로고 · 배너 · 썸네일","fit":{"maxLines":3}}}
 ]}}
]
```
결과 `{"files":[".../01-hook.png", ...], "ids":[...], "missing":[]}` — 1080×1920 PNG 2장 확인.
- 값: 문자열(텍스트) 또는 `{text?, fill?, visible?, fit?}`. `missing` 에 이름 못 찾은 키가 나온다.
- `formats:[{name,width,height}]` 로 같은 행을 여러 크기로(오토레이아웃 프레임일 때만 재배치).
- `text.fit {ids, maxLines, minSize}` : 줄 수에 맞게 글자 크기 자동 축소(키우지는 않음).
- **주의(시험에서 봄)**: 한글은 글자 단위로 줄이 바뀐다("디/자인"). 제목은 `\n` 으로 직접 끊거나 폭을 넉넉히.
- `dir` 은 절대경로가 안전(상대경로는 실행 cwd 기준 — 미확인).

### 4. 오토레이아웃 카드(체크리스트 · 단계 목록) — verified
```json
[
 {"command":"frame.create","as":"list","params":{"x":0,"y":0,"width":900,"height":100,"name":"Checklist",
   "props":{"fills":["#FFFFFF"],"cornerRadius":32}}},
 {"command":"node.set","params":{"ids":[{"$ref":"list"}],"props":{"layout":"vertical","gap":24,"padding":48,"sizingV":"hug"}}},
 {"command":"node.create","params":{"type":"text","parent":{"$ref":"list"},"text":"1. 캐시 비우기",
   "props":{"fontSize":56,"fontFamily":"Noto Sans CJK KR"}}}
]
```
- `node.set` 의 `layout` 은 문자열(`vertical`)로, `gap` · `padding` 은 따로. `layout` 에 객체를 넘기면 다른 값이 기본값으로 덮인다(가로로 바뀌는 것 시험에서 봄). `padding` 을 객체 안에 쓰면 `[t,r,b,l]` 배열이어야 한다.
- 텍스트를 넣을 때마다 프레임이 자라므로 항목 개수만 바꾸면 레이아웃이 따라온다.
- `layout.add {ids, direction}` 도 있다.

### 5. 레이어 단위 export (움직임 단계용 조각) — verified
`export file -o card.png --node <id|이름> --scale 3` 로 레이어 하나만 투명 배경 PNG. 장면을 레이어로 나눠 EffectCraft 에서 따로 등장시키려면 이름을 붙여 두고 이름으로 뽑는다.
- `render` 는 페이지 배경(회색)까지 그리고 그림자가 잘릴 수 있다 → 재료는 `export --node` 를 쓴다.
- 폴더 export 파일명은 프레임 이름 그대로(`Story · 1080 × 1920.png` 처럼 공백 · 특수문자 포함) → 스크립트에선 `--node` + 고정 파일명이 낫다.

### 6. SVG 가져오기 · 내보내기 — verified
`file.import {path:"icon.svg", x, y}` → 편집 가능한 프레임(시험: Lucide 스타일 체크 아이콘 정상). `export --node X -o x.svg` 로 SVG 출력(VectorCraft · EffectCraft 로 넘기기).

### 7. 이미지 보정 프리셋 — 미확인(목록만 확인)
`image.presets` → vivid · muted · warm · cool · blackAndWhite · fade · reset. `image.adjust {ids, preset:"vivid"}` 또는 `filters:{exposure,contrast,saturation,temperature,tint,highlights,shadows}`. 렌더 결과는 안 봤다.

### 8. 효과 — 일부 verified
`effect.add type`: dropShadow · innerShadow · layerBlur · backgroundBlur · noise · texture · glass. 점진 블러: `{"type":"layerBlur","blurType":"progressive","startRadius":0,"radius":24,"startOffset":[0.5,0],"endOffset":[0.5,1]}` (문서). dropShadow 만 렌더 확인, 나머지 미확인.

## 폰트 주의
- 시스템 폰트를 쓴다. 이 컴퓨터엔 `Noto Sans CJK KR` 이 있고, 폰트를 안 정해도 한글은 대체 글꼴로 나온다(템플릿 Inter + 한글 대체 확인).
- `--no-system-fonts` 를 주면 내장 폰트만 → 한글이 깨질 수 있다(미확인). 쓰지 말 것.
- Pretendard 는 `engine/assets/fonts/*.woff2` 로만 있어 시스템 폰트가 아니다 → FigCraft 에서 미사용(설치하면 될지 미확인).

## 전체 명령 분류 (635개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| text | 58 | `text.create` · `text.set` · `text.fit` · `text.edit.*` |
| view | 49 | 화면 확대 · 패널(헤드리스 의미 적음) |
| vector | 42 | `vector.create {path}` · 펜 편집 |
| tool | 29 | 도구 선택(UI) |
| object | 28 | `object.rename` · `object.group` · `object.mask` · `object.rasterize` |
| file | 24 | `file.newFromTemplate` · `file.import` · `file.export` · `file.exportLayers` |
| select / edit | 21 / 16 | `edit.findReplace` · `edit.duplicate` |
| component / instance | 21 / 8 | `component.create` · `instance.create` · `instance.setProperties` |
| proto | 21 | `proto.interaction.add` · `proto.flow.add` (재생은 창 필요) |
| collab · branch · version · comment | 21 · 7 · 8 · 15 | 협업(쇼츠엔 불필요) |
| board | 21 | 화이트보드(스티키 노트 · 커넥터) |
| variable · style · library | 19 · 10 · 19 | 라이트/다크 모드 변수 |
| pref · plugin · widget · dev · codeConnect | 17 · 11 · 6 · 4 · 4 | 설정 · 개발자 핸드오프 |
| arrange · align · distribute · transform | 10 · 6 · 2 · 9 | 정렬 |
| image | 7 | `image.place` · `image.replace` · `image.adjust` · `image.crop` |
| fill · stroke · effect | 7 · 8 · 6 | `fill.set` · `effect.add` |
| layout · grid | 5 · 3 | `layout.add` · `layout.setTrack` |
| node | 6 | `node.create` · `node.set` · `node.get {outline}` · `node.find` |
| 기타 | — | `template.list` · `data.fill` · `frame.presets` · `paint.documentColors` · `shapeBuilder.*` · `bool.*` |

`frame.presets` 에 `Instagram story 1080×1920`, iPhone 16/17 계열, Android, MacBook, YouTube thumbnail 등이 있다 → `frame.create {preset:"iPhone 16"}`.

## Fluma 에 붙일 때 제안(코드 미수정, 제안만)
- `ui_mock` 어댑터: 콘티 `{type:"ui_mock", src:"캡처.png", title:"..."}` → 위 1번 스크립트 → `export --node Shorts`.
- 카드형 장면(훅 · CTA)은 3번 data.fill 로 한 번에.
- 결과 PNG 는 기존 재료처럼 `data/compositions/<id>/craft/materials/sNN/<id>.png` 로.

## 공식 문서
- 저장소: https://github.com/storytold/figcraft
- CLI: https://github.com/storytold/figcraft/blob/main/docs/cli.md
- MCP(명령 규칙 · 템플릿 · data.fill · 효과): https://github.com/storytold/figcraft/blob/main/docs/mcp.md
- 빠진 기능: https://github.com/storytold/figcraft/blob/main/docs/gaps.md
- 홈페이지: https://getartcraft.com/apps/figcraft
