# DeckCraft 참고 (v0.15.0)

**한 줄 요약**: PowerPoint 류 발표 앱. 헤드리스 `deckcraft-cli run --cmd-file` 로 슬라이드를 만들고 `render` 로 PNG 를 뽑는다. 슬라이드 크기를 **540×960pt(= scale 2 에서 1080×1920 px)** 로 바꾸면 9:16 쇼츠 화면이 바로 나온다. 쇼츠에서는 **SmartArt 도식(단계 · 순환 · 피라미드 · 벤 등 45종)**, **비교 표**, **전환 효과 프레임(render-transition)** 이 쓸모 있다.

- 실행 파일: `tools/crafts/deckcraft/app/deckcraft-0.15.0-linux-x86_64/bin/deckcraft-cli`
- 명령 수: 약 330개 (`deckcraft-cli commands`, JSON 출력 옵션은 없음 — 한 줄에 `id — 이름: {params}`)
- 지금 Fluma 사용: **없음**. `crafts/deckcraft/craft.json` 에 `provides: diagram (pdf → png)` 만 있고 `scripts/craft/materials.py` 에 diagram 어댑터가 없다. `agent: false` 라 MCP 도 기본 꺼짐. (그리고 PDF 를 거칠 필요 없다 — `render` 가 PNG 를 직접 낸다.)

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `scripts/craft/adapters/deckcraft.py` — 재료 `diagram`. 540×960pt 덱(Nocturne 테마, Noto Sans CJK KR)에 제목 글상자 + SmartArt, `shape.setBounds` 로 화면에 맞춤, `slide.inspect` 로 칸을 재서 글자 크기.
- kind → 레이아웃: steps verticalProcess · compare hBulletList · cycle · hierarchy · pyramid · timeline · list blockList(verticalBoxList 는 머리 글자가 깨알). `layout` 으로 45종 직접.
- 빌드 애니메이션은 렌더되지 않는다 → 같은 슬라이드에서 다른 도형만 숨기고 투명 배경으로 내보내 **항목별 층**(위치 정확) + base(배경 + 제목). EffectCraft 가 base 위에 층을 cue 마다 얹는다.
- 주의: 피라미드 꼭대기는 4글자 이상이면 줄이 바뀐다(짧은 낱말). 비교(hBulletList)는 화면 위쪽 25% 높이로 작다. 밝은 테마는 미확인.

## 헤드리스로 되는 것 / 안 되는 것

| 된다 | 안 된다 / 미확인 |
|---|---|
| `run` : 모든 명령 순서 실행 → `--save` (.deckcraft/.pptx/.pdf/.md) | **애니메이션(빌드) 프레임 렌더 없음** — `animation.set` 은 저장만, PNG 엔 최종 상태만 |
| `render` 슬라이드 PNG (`--all`, `--scale`, `--transparent`) | MP4 내보내기 없음(gaps.md: "No video export") |
| `render-transition` 전환 효과를 t=0..1 프레임 PNG 로 | GIF 는 슬라이드당 1프레임, 전환 · 빌드 없음 |
| `convert` .pptx/.pdf/.md/.gif/.png | `run --export x.gif` 는 파일은 쓰였지만 프로세스가 끝나지 않음(시험, 2분 넘게 대기) → **GIF 는 `convert` 로** |
| `info` JSON, `describe <명령>` 파라미터 설명 | 차트 축 최소값 지정 명령 없음 |
| `mcp` (stdio, 헤드리스 또는 `--connect`) | 템플릿 6종은 16:9 고정(세로 버전 없음) |

명령이 실패하면 거기서 멈추고 아무것도 저장하지 않는다. `--print` 로 각 명령의 응답(삽입된 도형 id 등)을 본다.

## 기본 사용법

```sh
D=tools/crafts/deckcraft/app/deckcraft-0.15.0-linux-x86_64/bin/deckcraft-cli
$D run --cmd-file cmds.txt --print --save out.deckcraft   # 한 줄에 '명령id={JSON}'
$D render out.deckcraft --all out_png/                     # slide-01.png … (기본 scale 2)
$D render out.deckcraft --slide 0 --transparent s0.png     # 배경 빼고(겹치기용)
$D describe insert.smartArt                                # 파라미터 설명
```
- 좌표 단위는 pt, `rect = [x, y, w, h]`, 슬라이드 번호는 0부터.
- 도형을 넣는 명령은 그 도형을 선택한다 → 바로 뒤 `format.*` · `smartArt.*` · `picture.*` · `table.*` 가 그 도형에 적용.
- 세로 쇼츠 공통 머리말(시험함):
```
file.new={"theme":"Nocturne","size":[540,960],"blank":true}
design.fonts={"major":"Noto Sans CJK KR","minor":"Noto Sans CJK KR"}
slide.new={"layout":"blank"}
```
`blank:true` 면 슬라이드 0장으로 시작 → `slide.new` 필수. 크기는 이미 만든 덱이면 `design.slideSize={"w":540,"h":960}`.

## 쇼츠용 핵심 기능

### 1. SmartArt 도식 — verified (가장 쓸모 있음)
단계 · 비교 항목을 글만 주면 도식이 나온다. 좌표 계산이 필요 없다("좌표로 그리지 않음" 원칙에 맞음).
```
insert.smartArt={"kind":"process","items":["URL 입력","분석 실행","점수 확인","개선 제안"]}
smartArt.layout={"kind":"verticalProcess"}
smartArt.style={"style":"polished"}
smartArt.colors={"colors":"colorful"}
```
→ 1080×1920 PNG, 세로로 4칸 + 화살표, 한글 정상(시험). `kind:"cycle"` 4항목 원형 순환도 확인.
- `insert.smartArt kind`: list · process · cycle · hierarchy · pyramid · matrix. `items` 앞에 탭(`\t`) = 하위 항목.
- `smartArt.layout kind` 45종: verticalProcess · chevron · stepUp · timeline · venn · target · funnel · gear · pyramid · invertedPyramid · titledMatrix · orgChart · radial · blockCycle … (세로 화면엔 verticalProcess · verticalBoxList · pyramid · funnel · timeline 이 맞음 — 세로 외 레이아웃은 verticalProcess · cycle 만 확인)
- `smartArt.style`: flat · subtle · intense · outline · polished · inset · cartoon · powder · brick
- `smartArt.colors`: colorful · range23..56 · accent1..6 · accent1Grad..
- `smartArt.setNodes {lines:[...]}` 로 글만 갈아 끼우기, `smartArt.toShapes` 로 낱개 도형화(따로 움직이고 싶을 때 — 미확인).
- 하나씩 등장시키기: 빌드 렌더가 없으므로 **항목 1개 → 2개 → … 로 늘린 슬라이드를 각각 render** 해서 움직임 단계에 넘긴다(방법 제안, 미확인).
- 기본 배치는 슬라이드 가운데 · 크기 자동. 위쪽에 자막 · 제목 공간이 남는다.

### 2. 비교 표 — verified
```
insert.table={"rows":4,"cols":3,"rect":[30,220,480,360]}
table.style={"style":"medium2-accent1"}
text.set={"cell":[0,0],"text":"항목"}
text.set={"cell":[0,1],"text":"무료"}
...
table.cellAlign={"anchor":"middle","align":"center"}
```
→ 표 + 한글 정상(시험). **주의**: Nocturne(어두운 테마) + `dark1-tx1` 은 본문 칸이 연회색에 흰 글씨라 거의 안 읽힌다(시험에서 봄). 어두운 테마엔 `medium2-accent1` 계열을 쓰고 렌더해서 대비를 눈으로 확인할 것.
- `table.cellFill {color, cells:[[r,c]]}` 로 이긴 칸 강조, `table.options {bandedRows, firstColumn}`, `table.borders`.
- 비교 형식(format-compare)의 "같은 기준의 값" 표를 만드는 데 맞다.

### 3. 전환 효과 프레임 — verified
```
transition.set={"kind":"morph","duration":800}     # 들어오는 슬라이드에 지정
```
`deckcraft-cli render-transition deck.deckcraft --slide 2 --t 0.3,0.7 --width 540 tr.png` → `tr-t0.300.png` 등. morph 확인(앞 슬라이드와 겹쳐 사라지며 등장).
- 30fps 프레임열: `--t` 에 0,0.033,…,1 을 넣고 FilmCraft/ffmpeg 로 이어 붙이면 장면 전환 클립이 된다(이어 붙이기는 미확인).
- `transition.list` 로 전체 목록(fade · push · wipe · split · reveal · cover · flash · shape …). PowerPoint 비디오 출력과 프레임 단위로 맞췄다고 문서에 있다(animation-parity.md).
- 쇼츠 전체 흐름엔 쓰지 말고 도식 → 도식 바꿈 정도에만.

### 4. 차트 — verified, 그러나 비추천
```
insert.chart={"type":"bar","rect":[30,200,480,560],"categories":["ChatGPT","Gemini","Claude"],"series":[{"name":"정답률","values":[71,68,80]}]}
chart.options={"title":"코딩 문제 정답률(%)","dataLabels":true,"gridlines":false,"legend":null}
```
렌더는 되지만 (1) **축이 60부터 시작해 차이를 과장**, 축 최소값 바꾸는 명령 없음 (2) bar 는 아래부터 거꾸로 (3) Slate 테마 blank 슬라이드는 흰 배경. → 차트 재료는 지금처럼 GridCraft 계산 + EffectCraft 그리기를 유지. DeckCraft 차트는 "엑셀 화면 그대로" 느낌이 필요할 때만.

### 5. 스크린샷 넣기 + 사진 스타일 — verified
```
insert.picture={"path":"shot.png","rect":[40,300,460,392]}
picture.style={"style":"dropShadowRectangle"}
```
→ 그림자 액자 확인. `picture.styles` 28종(simpleFrameWhite · softEdgeRectangle · perspectiveShadowWhite · rotatedWhite …), `picture.crop {left,top,right,bottom 0..1}`, `picture.removeBackground {tolerance}`(미확인), `picture.recolor`, `picture.artisticEffect`(미확인). 폰 목업은 FigCraft 가 더 자유롭다.

### 6. 투명 배경 렌더 — verified
`render --transparent` → 배경 없는 PNG. 도식만 떼어 실제 화면 위에 겹칠 때. (흰 글씨 · 흰 아이콘은 밝은 배경에서 안 보이니 합성 결과로 확인.) `insert.icon={"name":"check","rect":[...]}` 은 오류 없이 들어갔지만 투명 렌더에서 보이지 않았다 — 테마 글자색(흰색)으로 그려졌을 가능성, 미확인.

### 7. 테마 · 디자인 아이디어 — 일부 verified
- `design.themes`: 테마 8종(DeckCraft · Harbor · Ember · Meadow · Nocturne · Paper · Coral Reef · Slate), 색 13종, 폰트 9종, 효과 6종. `design.colors {colors:{accent1:"#..."}}` 로 브랜드 색.
- `design.ideas` → 슬라이드별 레이아웃 제안(titleColumn · centred · titleBottom), `design.applyIdea {id}` (적용 결과 미확인).
- `file.templates`: Briefing · Lesson · Pitch · Field Notes · Quarterly · Evening Talk (각 5장, 960×540 가로).

### 8. pptx / pdf / md 내보내기 — verified(pptx · gif)
`convert deck.deckcraft deck.pptx` · `.pdf` · `.md`(개요) · `.gif`. 사람이 PowerPoint 로 고치고 싶을 때 pptx 를 넘긴다.

## 전체 명령 분류 (약 330개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| format | 47 | `format.size` · `format.bold` · `format.fill` 류(글 · 도형 서식) |
| shape | 37 | `shape.insert {preset, rect, text}` · `shape.connect` · `shape.freeform` · `shape.merge` |
| slide | 22 | `slide.new {layout,title,body}` · `slide.inspect` · `slide.layout` · `slide.colorAt` |
| table | 21 | `table.style` · `table.cellFill` · `table.merge` · `table.cellAlign` |
| file | 19 | `file.new {theme,template,size,blank}` · `file.export` · `file.render` · `file.templates` |
| insert | 18 | `insert.smartArt` · `insert.chart` · `insert.table` · `insert.picture` · `insert.icon` · `insert.video` · `insert.photoAlbum` |
| text | 17 | `text.set {id?, cell?, text}` · `text.find` |
| arrange | 15 | 정렬 · 순서 |
| design | 14 | `design.theme` · `design.colors` · `design.fonts` · `design.slideSize` · `design.background` · `design.ideas` |
| smartArt | 13 | `smartArt.layout` · `smartArt.style` · `smartArt.colors` · `smartArt.setNodes` · `smartArt.toShapes` |
| review · comment | 12 · 7 | 맞춤법 · 메모 |
| picture | 12 | `picture.style` · `picture.crop` · `picture.removeBackground` · `picture.recolor` |
| edit | 12 | 복사 · 붙여넣기 · 선택 |
| animation | 11 | `animation.set/add/timing` (저장만, 렌더 안 됨) |
| media | 9 | `insert.video` 재생 옵션 |
| transition | 6 | `transition.set` · `transition.list` |
| master · section · view · show · guide · font | 6 · 5 · 4 · 4 · 4 · 4 | 마스터 · 구역 · 쇼 |
| chart | 3 | `chart.type` · `chart.data` · `chart.options` |
| 기타 | — | selection · notes · handout · draw · document · window · commands |

## Fluma 에 붙일 때 제안(코드 미수정, 제안만)
- `diagram` 어댑터: 콘티 `{type:"diagram", kind:"process", items:[...]}` → 머리말 3줄 + 1번 → `render --scale 2 [--transparent]` → PNG. craft.json 의 `out: "pdf → png"` 은 `png` 로 충분.
- 표 재료(`table`)도 같은 방식으로 추가 가능.

## 공식 문서
- 저장소: https://github.com/storytold/deckcraft
- README: https://github.com/storytold/deckcraft/blob/main/README.md
- MCP: https://github.com/storytold/deckcraft/blob/main/docs/mcp.md
- 빠진 기능(비디오 출력 없음 등): https://github.com/storytold/deckcraft/blob/main/docs/gaps.md
- 애니메이션 · 전환 비교: https://github.com/storytold/deckcraft/blob/main/docs/animation-parity.md
- CLI 도움말: `deckcraft-cli help run` · `deckcraft-cli describe <명령>` (저장소에 cli.md 없음)
- 홈페이지: https://getartcraft.com/apps/deckcraft (README 의 앱 링크 형식으로 추정, 미확인)
