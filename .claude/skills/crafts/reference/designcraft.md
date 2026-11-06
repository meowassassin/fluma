# DesignCraft 참고 (v0.17.0)

**한 줄 요약**: InDesign 같은 지면 레이아웃 앱(Rust, MIT/Apache-2.0). 명령 547개가 모두 `designcraft-cli` 로 헤드리스에서 돈다. Fluma 에서는 **정지 지면**을 맡는다: 썸네일 · 카드뉴스 · 정보 카드 · 수식 카드 · 데이터로 여러 장 찍어 내기. 결과는 PNG(장면 재료)와 `.designcraft`(사람이 나중에 열어 고침).

- CLI: `tools/crafts/designcraft/app/designcraft-0.17.0-linux-x86_64/bin/designcraft-cli`(아래에서는 `$DC`)
- 웹 빌드: `tools/crafts/designcraft/web/designcraft-web-0.17.0`(사람이 편집할 때. 웹에는 제어 채널이 없다)

## 지금 Fluma 가 쓰는 범위

- `scripts/craft/adapters/designcraft.py` — 재료 `info_card` · `thumbnail`.
- info_card: `script` 조판(머리말 · 제목 76→56pt 중 3줄에 드는 가장 큰 크기 · 짧은 선 · 본문 · 01/02 요점 · 출처) → 여러 장은 `data.merge`(칸 줄 수가 같은 줄끼리 한 틀로), 높이는 시리즈 최댓값. 낱말 경계에서 미리 끊어 U+2028 강제 줄바꿈. `frame: card` 는 카드만(둥근 모서리 투명 · 그림자는 PIL — **DesignCraft 는 투명 PNG 를 못 낸다**), `full` 은 1080×1920.
- thumbnail: 세로 1080×1920 + 가로 1280×720(`<id>.16x9.png`). Black 제목 + 강조 낱말 색(`text.select` UTF-8 바이트 범위) + 훅 알약 + 그림자, 사진은 아래 · 왼쪽을 그라디언트로 어둡게, 넓은 사진은 흐린 배경 위에 폭 맞춤. 칸이 비면 콘티 title · badge · hook_number · 앞 장면 사진.
- 글꼴은 Noto Sans CJK KR(Pretendard woff2 못 읽음).

## 헤드리스로 되는 것 / 안 되는 것

| 된다(시험함) | 안 된다 / 미확인 |
|---|---|
| 새 문서(아무 크기, 1080×1920 등), 프레임 · 텍스트 · 이미지 배치, 채우기 맞춤 | 한국어 글꼴 Pretendard: 시스템에 없어서 못 쓴다. `public/fonts/*.woff2` 를 읽게 하는 방법은 미확인 |
| 문자 서식(글꼴 · 크기 · 색), 단락 스타일 만들기 · 적용 | 웹 빌드(wasm)는 제어 채널이 없다 → 사람이 손으로만 고친다 |
| 선형 그라디언트(불투명도 스톱), 그림자 · 둥근 모서리, QR 코드 | 실행 중인 앱 조종(`app`, `--connect`)은 데스크톱 앱 필요. 헤드리스에서는 안 씀 |
| **데이터 병합**(CSV → 페이지 여러 장, 텍스트 · 이미지 필드) | 영상 · 움직임은 없다(정지 지면 전용). 움직임은 EffectCraft 가 맡는다 |
| LaTeX 수식 조판(`math.insert`), 이미지에서 색 5개 뽑기 | IDML · INDD 열기, EPUB, 인쇄는 쇼츠와 무관해 시험 안 함 |
| PNG(배율 지정) · PDF · PPTX · `.designcraft` 내보내기, 페이지별 PNG | `edit.pasteSvg`(VectorCraft SVG 붙이기)는 미확인 |

**공통 규칙**
- 단위: `file.new` 에 `units` 를 주지 않으면 pt. 1080×1920pt 문서를 `--scale 1` 로 내보내면 1080×1920px. `script --export` 는 **기본 2배**(2160×3840)로 나온다.
- 좌표: `rect: [x0, y0, x1, y1]`, 스프레드 좌표(왼쪽 위 원점, y 아래로).
- 스크립트: 한 줄에 `command.id {json}`, `#` 주석 가능. `"$N.path"` 로 N번째(0부터, 주석 · 빈 줄 제외) 결과를 쓴다(`"$1.id"`, `"$4.story"`). `$last` 는 바로 앞 결과.
- 텍스트 안 `\n` 은 새 단락, ` ` 은 줄바꿈.
- 모르는 params 는 **조용히 무시**된다. 이름은 꼭 `$DC describe <id>` 로 확인할 것.
- 실행: `$DC script f.dcs --save out.designcraft --export out.png` / 이미 있는 문서: `$DC run --in f.designcraft --cmd 'id={json}' --scale 0.5 --export a.png`.
- `run --page N` 은 **0부터**(`--page 0` 이 첫 페이지). 시험에서 `--page 2` 가 셋째 페이지를 냈다.
- 한국어: `"fontFamily":"Noto Sans CJK SC"`(시스템 설치본, `fontStyle` Bold · Black 등)로 한글이 바로 렌더된다(시험함). 앱에는 Nanum Gothic · Noto Sans CJK SC 도 함께 들어 있다(share/doc 의 OFL 목록).

## 쇼츠용 핵심 기능

### 1. 세로 썸네일 / 표지 한 장 (verified)
배경 사진(또는 실제 화면 캡처) + 아래쪽 어둡게 + 큰 제목. 이 형태가 쇼츠 표지 · 첫 프레임 · 카드뉴스의 기본이다.
```text
file.new {"width":1080,"height":1920,"intent":"mobile","units":"points","margins":60,"pages":1}
frame.create {"rect":[0,0,1080,1920],"content":"graphic"}
file.place {"path":"bg.png","frame":"$1.id"}
object.fit {"mode":"fillProportionally","ids":["$1.id"]}
frame.create {"rect":[0,1000,1080,1920],"content":"unassigned"}
object.gradient {"kind":"linear","angle":-90,"stops":[{"location":0,"color":"#000000","opacity":0},{"location":100,"color":"#000000","opacity":90}],"ids":["$4.id"]}
frame.create {"rect":[60,1300,1020,1700],"content":"text","text":"무료 AI 툴\n5분 만에 끝"}
text.select {"story":"$6.story","anchor":0,"focus":40}
type.char {"attrs":{"fontFamily":"Noto Sans CJK SC","fontStyle":"Bold","size":130,"fill":"[Paper]"}}
```
```sh
$DC script t1.dcs --save t1.designcraft --export t1.png        # 2160×3840 (기본 2배)
$DC run --in t1.designcraft --scale 0.5 --export t1s.png       # 540×960, 0.4초
```
- 결과: 1280×640 가로 이미지가 세로 프레임을 꽉 채우게 잘리고(가운데 기준), 한글 제목이 흰색 Bold 로 나왔다. 그라디언트도 아래로 갈수록 어두워졌다.
- `file.place` 결과는 `{"asset":9,"id":8}`. 이미지 프레임 id 는 그대로다.
- 주의: `text.select` 의 `focus` 는 **UTF-8 바이트 위치**다(한글 한 자 = 3바이트). 전체를 잡으려면 넉넉한 큰 수를 주면 끝까지 잡힌다(40 으로 줬는데 전부 잡혔다).
- 주의: `fill` 은 견본(swatch) 이름이다(`[Paper]` = 흰색, `[Black]`). 다른 색은 `swatch.create {"name":"Yellow","color":"#FFD400"}` 을 먼저 만든 뒤 이름으로 쓴다(미확인: type.char 에 hex 직접 넣기).

### 2. 데이터 병합으로 카드 여러 장 (verified)
CSV 한 줄 = 카드 한 장. "팁 5개" · "순위 TOP 5" · 비교 카드처럼 같은 틀에 내용만 바뀌는 장면을 한 번에 찍는다. 사람이 고칠 때도 틀(`tpl.designcraft`) 하나만 고치면 된다.
```text
# cards.csv:  title,num,@img   (@ 로 시작하는 열은 이미지 경로. 필드 이름은 @ 를 뺀 img)
file.new {"width":1080,"height":1920,"intent":"mobile","margins":60}
data.source.select {"path":"cards.csv","name":"cards.csv"}
style.paragraph.create {"name":"Head","para":{"align":"left"},"chars":{"fontFamily":"Noto Sans CJK SC","fontStyle":"Bold","size":110}}
frame.create {"rect":[0,0,1080,1080],"content":"graphic"}
data.placeholder.add {"field":"img","role":"image","item":"$3.id"}
frame.create {"rect":[60,1200,1020,1500],"content":"text"}
data.placeholder.add {"field":"title","story":"$5.story","at":0}
text.select {"story":"$5.story","anchor":0,"focus":50}
style.paragraph.apply {"name":"Head"}
object.qrCode {"content":"https://example.com","rect":[780,1580,1020,1820]}
```
```sh
$DC script tpl.dcs --save tpl.designcraft
echo 'data.merge {"fitting":"fillProportionally"}' | $DC script - --in tpl.designcraft --save merged.designcraft
$DC run --in merged.designcraft --scale 1 --all-pages cards/          # cards/page-001.png …
```
- 결과: `{"records":3,"pages":3,"missingImages":[],"oversetStories":0}`. 세 장 모두 제목 · 사진 · QR 이 제자리에 나왔다(페이지당 수 ms).
- 순서가 중요: **`data.source.select` 를 먼저** 해야 `data.placeholder.add` 가 된다(안 하면 `select a data source` 오류).
- `data.placeholder.add` 는 `at` 위치에 필드를 **끼워 넣는다**. 프레임에 원래 글자가 있으면 그대로 남는다("무료 툴 1위T" 처럼). 빈 텍스트 프레임에 넣을 것.
- 필드 글꼴은 그 자리 서식을 따른다. 스타일을 안 주면 12pt 기본 글꼴로 아주 작게 나온다 → 위처럼 단락 스타일을 적용.
- `data.merge` 는 **새 문서**를 만들고 틀은 그대로 둔다. `oversetStories` 가 0 이 아니면 글이 넘친 것 → 글자 크기 줄이거나 프레임을 키운다.
- 인라인 데이터도 된다: `data.merge {"csv":"title\n하나\n둘"}` 또는 `{"rows":[...]}`(미확인: rows 모양).

### 3. 수식 카드 (verified)
기술 설명 쇼츠에서 공식을 진짜 조판으로 보여 준다.
```text
file.new {"width":1080,"height":600,"intent":"mobile"}
math.insert {"latex":"\\mathrm{Attention}(Q,K,V)=\\mathrm{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V","size":44,"x":40,"y":200}
```
- 결과: 분수 · 루트 · 첨자가 제대로 조판됐다(세리프 수식 글꼴).
- 배치하지 않고 SVG 만 받기: `math.svg {"latex":"…","size":44}` → `{svg,width,height}`. VectorCraft · EffectCraft 로 넘겨 움직일 수 있다(SVG 넘기기는 미확인).

### 4. 사진에서 팔레트 뽑기 (verified)
배경 사진 색에 맞춰 제목 · 강조색을 정할 때. 사람 손 조정을 줄인다.
```sh
$DC run --in t1.designcraft --cmd 'color.extractTheme={"id":8}' ...
# → {"colors":["#14131b","#1b192f","#25213d","#b3a8f1","#d7cfcd"],"from":8}
$DC run --in t1.designcraft --cmd 'swatch.addColorTheme={"colors":["#b3a8f1","#d7cfcd"],"name":"bg"}' ...   # 견본 그룹으로(미확인)
```
- 1600만 화소 이하 래스터만. PDF · SVG 그래픽은 안 된다.

### 5. 효과 · 모양 (verified)
```text
object.dropShadow {"on":true,"distance":8,"size":12,"opacity":80,"ids":[11]}      # 글자 그림자(밝은 배경 위 자막 가독성)
object.cornerOptions {"shape":"rounded","size":40,"ids":[8]}                       # 사진 둥근 모서리(카드형)
object.qrCode {"content":"https://…","rect":[780,1580,1020,1820]}                 # 광고 형식 CTA
```
- 결과: 모두 `{"changed":1}` 이고 렌더에 반영됐다.
- 그 밖(시험 안 함): `object.outerGlow` · `innerShadow` · `bevel` · `satin` · `feather` · `gradientFeather`(가장자리 부드럽게), `object.opacity {opacity, blend}`(곱하기 등 합성 모드), `object.effects`(한 번에 여러 효과).

### 6. 내보내기 (verified)
```sh
$DC run --in m2.designcraft --page 2 --scale 0.25 --export p.png --export m2.pdf --cmd 'file.exportPptx={"path":"m2.pptx"}'
```
- 확장자로 형식 결정: `.png`/`.jpg`(한 페이지), `.pdf`, `.designcraft`, `.idml`, `.epub`, `.html`, `.txt`/`.rtf`. 확장자 없으면 PNG.
- `--all-pages DIR` → `DIR/page-001.png …`.
- PPTX: 3장 · 9KB, 경고 `fonts not embedded: Noto Sans CJK SC Bold (not a TrueType font)`. DeckCraft 로 넘길 때 글꼴이 대체될 수 있다.
- `--scale` 은 그 뒤에 오는 `--export` 에만 적용된다. 한 번 실행으로 여러 크기를 낼 수 있다.

### 7. 그 밖에 쇼츠에 쓸 만한 것 (미확인)
- `frame.grid {rect, cols, rows, gutter}`: 격자 프레임 한 번에(전후 비교 · 2×2 정보 카드).
- `flex.add` / `flex.set {direction, justify, align, gap…}`: 웹 Flex 같은 자동 배치. 글 길이가 바뀌어도 칸이 밀린다 → 사람 조정 줄이기 좋다.
- `layout.createAlternate {name, width, height}`: 같은 디자인을 다른 크기로 복제(9:16 → 1:1 · 16:9 썸네일). Liquid 규칙(`liquid.pageRule`)과 함께 쓴다.
- `type.onPath`(곡선 위 글자), `type.createOutlines`(글자를 패스로), `object.pathfinder`(도형 합치기).
- `object.label {label}` · `object.findByLabel`: 틀 안 요소에 이름표를 붙여 두면 다음 실행에서 id 대신 이름으로 찾는다.
- `library.*`(오브젝트 라이브러리) · `snippet.export/place`: 자주 쓰는 배지 · 자막 박스를 조각으로 저장해 다시 쓴다.
- `edit.pasteSvg {svg, at}`: VectorCraft · FigCraft 가 만든 SVG 를 편집 가능한 패스로 붙인다.

## 전체 명령 분류 요약 (547개, `$DC commands` 의 JSON)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| object | 60 | fill · stroke · gradient · dropShadow · fit · cornerOptions · qrCode · pathfinder · label |
| type | 43 | char · para · align · changeCase · onPath · createOutlines · openType · tabs.* |
| table | 41 | insert · setCell · merge · sortRows · get(표 카드) |
| file | 37 | new · open · place · save · exportPdf · exportPptx · exportHtml · exportIdml · package |
| layout | 28 | pages.insert · documentSetup · pageSize · createAlternate · parents.* |
| style | 28 | paragraph.* · character.* · object.* · table.* · cell.* |
| edit | 18 | undo · duplicate · stepAndRepeat · pasteSvg · preview |
| text | 17 | select · insert · thread · selectWord |
| path | 15 | create · setAnchor · join · split |
| swatch | 13 | create · load(.ase) · addColorTheme |
| transform | 10 | move · rotate · scale · set · flip |
| book · guide · xml · data | 각 10 | data.source.select · data.placeholder.add · data.merge · data.preview |
| note · story · layer | 각 9 | layer.new · layer.set |
| library · select | 각 8 | library.add · library.place |
| 나머지 40여 그룹 | 1~7 | variables · flex(5) · color(5: extractTheme · convert) · states(5) · math(2) · media(2) · page.transition · preflight · script.run |

실제 목록은 `$DC commands [필터]`, 한 명령의 params 는 `$DC describe <id>`.

## MCP

`designcraft-cli mcp --automation-read-root $ROOT --automation-write-root $WRITE`(craft.json 의 `mcp` 줄). 페이지 PNG 가 MCP 내용으로 돌아온다.
읽기 · 쓰기 루트를 꼭 준다(빠진 쪽은 접근 0). 이 루트는 `--connect` 와 함께 쓸 수 없다. Fluma 에서 MCP 로 붙인 곳은 아직 없다(`web/mcp.mjs` 는 외부 MCP 서버 설정용).

## 공식 문서

- 저장소: https://github.com/storytold/designcraft (README: 기능 · 헤드리스 `run --sample --all-pages out/`)
- 에이전트 · 스크립트: https://github.com/storytold/designcraft/blob/main/docs/agents.md (스크립트 문법 · `$N` 참조 · 데이터 병합 · 색 테마)
- MCP: https://github.com/storytold/designcraft/blob/main/docs/mcp.md
- 제어 채널: https://github.com/storytold/designcraft/blob/main/docs/control-protocol.md
- 한중일 조판: https://github.com/storytold/designcraft/blob/main/docs/cjk-typography.md
- 홈페이지: https://getartcraft.com/apps/designcraft
