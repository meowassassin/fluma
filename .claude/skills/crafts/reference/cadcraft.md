# CADCraft 참고 (v0.17.0)

**한 줄 요약**: AutoCAD 류 2D 제도 앱(순수 Rust, MIT/Apache-2.0, 저장소 `storytold/cadcraft`). 명령 451개(AutoCAD 명령 이름 그대로: `line` · `rectang` · `hatch` · `dimlinear` · `mleader` · `plot` …)를 헤드리스 CLI(`run --cmd`)와 MCP 로 부른다. 쇼츠에서는 **평면도 · 설계 도면 화면 재료(어두운 CAD 화면 또는 흰 종이 출력) · 치수가 붙은 설명 도면 · DWG/DXF 실제 파일 미리보기** 를 맡는다. 지금 Fluma 는 이 앱을 **전혀 쓰지 않는다**(craft.json `agent:false`, 부르는 곳 없음).

- 실행 파일: `tools/crafts/cadcraft/app/cadcraft-0.17.0-linux-x86_64/bin/cadcraft-cli`
  (에이전트는 `python3 engine/craft/crafts.py run cadcraft <인자…>` 로 부른다)

---

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `engine/craft/adapters/cadcraft.py` — 재료 `drawing`. 원본은 `src`(DXF · DWG) · `cmd`(CADCraft 명령) · `model`(model3d 칸 또는 같은 장면 앞선 model3d id → SolidCraft `file.export_view_dxf` 보기별 DXF).
- model 도면: `run` 의 import 로 3각법 배치(평면도는 정면도 위, 측면도는 옆, 등각도는 맨 위) + `dimlinear` 전체 치수 3개(0.1mm 반올림) + 보기 이름 · 제목 → `.dxf` 편집 파일.
- 화면: `paper: dark`(기본) — MCP `render` 에 9:16 창 → 1080×1920 CAD 화면. `white` — `plot`(A4 세로)을 단색 펜처럼 후처리(**plot 에 단색 펜 옵션 없음**: 노랑 · 하늘색 글자 → 검정, 빨간 표시만 남김) 후 9:16 흰 바탕 가운데.
- `mark` → 빨간 `revcloud`. 어두운 화면(MCP render)은 lineweight 가 반영되지 않아 구름이 가늘다. 숫자 · 영문은 CAD 선 글꼴, 한글은 고딕.
- 사람이 고친 `.dxf` 는 해시로 알아보고 다시 그리지 않는다.

## 1. 헤드리스로 되는 것 / 안 되는 것

| 구분 | 내용 |
|---|---|
| 된다 (확인) | `run --metric --cmd '<id> {json}' … --save x.dxf --export x.png` : 새 도면 → 명령 → 저장/내보내기. 10개 명령이 0.07초 |
| 된다 (확인) | `convert in.dxf out.png|svg|pdf|dwg` · `info x.dxf`(요약 JSON) · `sample floorplan|bracket out.dxf` |
| 된다 (확인) | `plot {device:"CADCraft PNG", paper:"ISO A4 …", landscape:false}` 로 **세로 흰 종이 출력**(2480×3508) |
| 된다 (확인) | 한글 TEXT 가 나온다(글꼴 대체로 한글은 고딕, 숫자 · 영문은 CAD 선 글꼴 `txt` 모양) |
| 된다 | `--script 'CIRCLE 22,3 1\n'` 로 AutoCAD 명령줄 그대로, `--script-file x.scr`, AutoLISP(`lisp`) (README 기준, 미확인) |
| 안 된다 (확인) | CLI `--export` PNG 크기는 **2400×1600 고정**(가로). 9:16 은 MCP `render {width:1080,height:1920}`(확인, 3.5) 이나 `plot` 세로 용지 뒤 자르기 |
| 안 된다 | 앱 UI(리본 · 명령줄 · 속성 창) 화면은 데스크톱 앱 + `mcp --connect` 의 `screenshot` 이 필요하다 |
| 주의 (확인) | 치수 · 지시선 글자 크기는 `DIMSCALE` 를 따른다. 기본값이면 mm 도면(수천 단위)에서 **글자가 안 보일 만큼 작다**. 치수를 만들기 **전에** `setvar {"name":"DIMSCALE","value":80}` |
| 주의 (확인) | `mleader` 글자는 DIMSCALE 80 을 줘도 보이지 않았다. 지시선 글자는 `mleaderstyle` 의 크기 · 축척을 따로 맞춰야 한다(미확인). 당장은 `line` + `text` 로 그린다 |
| 주의 | 실행 한 번에 `--export` 는 하나. 단계별 프레임은 같은 도면을 여러 번 `run` 하거나 `--cmd export {"path":…}` 를 중간에 넣는다(미확인) |

## 2. 기본 문법

```sh
cadcraft-cli run [FILE…] [--metric | --sample] \
   --cmd 'rectang {"p1":[0,0],"p2":[3600,6400]}' --cmd 'hatch {…}' … \
   [--save out.dxf] [--export out.png|svg|pdf] [--window x0,y0,x1,y1 | --view extents|current]
cadcraft-cli convert in.dwg out.png [--window x0,y0,x1,y1]
cadcraft-cli info drawing.dxf [--compact]
cadcraft-cli commands            # 명령 451개 JSON(약 150KB): id · aliases · menu · params
```
- `--cmd` 는 순서대로 돌고 결과가 한 줄 JSON 으로 나온다(`{"handle":"100"}`).
- **앞 결과 참조**: 파라미터 값이 정확히 `"{last}"` 이면 앞 `--cmd` 가 돌려준 마지막 핸들로 바뀐다(`"handles":["{last}"]`).
- 좌표는 도면 단위. `--metric` 이면 mm. y 는 위로 커진다(CAD 관례).
- 음수로 시작하는 값은 `=` 로: `--window=-10,0,10,5`.
- 종료 코드: 0 성공, 1 명령 실패, 2 사용법 오류.

## 3. 쇼츠용 핵심 기능

### 3.1 설명용 평면도 그리기 (벽 · 해치 · 실 이름 · 치수) — 확인함 (room)
```sh
cadcraft-cli run --metric \
 --cmd 'rectang {"p1":[0,0],"p2":[3600,6400]}' \
 --cmd 'rectang {"p1":[200,200],"p2":[3400,6200]}' \
 --cmd 'line {"points":[[200,3200],[3400,3200]]}' \
 --cmd 'hatch {"points":[[100,100]],"pattern":"ANSI31","scale":20}' \
 --cmd 'text {"at":[1800,4700],"text":"거실 18㎡","height":250,"justify":"MC"}' \
 --cmd 'text {"at":[1800,1700],"text":"침실 12㎡","height":250,"justify":"MC"}' \
 --cmd 'setvar {"name":"DIMSCALE","value":80}' \
 --cmd 'dimlinear {"p1":[0,0],"p2":[3600,0],"at":[1800,-500]}' \
 --cmd 'lwdisplay {"on":true}' \
 --save room.dxf --export room.png
```
- 시험 결과: 0.07초. 어두운 배경(#212830) 위 흰 선, 벽 사이 빗금 해치, 한글 실 이름. DIMSCALE 을 준 뒤의 치수 `3600` 은 크게 보였다.
- `hatch.points` 는 **닫힌 영역 안의 점**. 두 사각형 사이(벽 두께)를 찍으면 벽만 채워진다.
- 쇼츠 활용: "이 집 구조의 문제" · "평수 계산" · "가구 배치" 정보 쇼츠. 실제 도면처럼 보이는 것이 핵심이라 효과 없이 그대로 쓴다.

### 3.2 세로(9:16) 흰 종이 출력 — 확인함 (plotA4)
```sh
cadcraft-cli run room.dxf --cmd 'plot {"path":"/절대/plotA4.png","device":"CADCraft PNG",
  "paper":"ISO A4 (210.00 x 297.00 MM)","landscape":false,"fit":true,"lineweights":true}'
```
- 결과: 2480×3508 흰 배경 · 검은 선 PNG. 9:16 으로 쓰려면 위아래를 잘라 1080×1920 에 맞춘다.
- 용지 이름은 정확히 써야 한다. 틀리면 오류 메시지에 쓸 수 있는 용지 목록이 다 나온다(ISO A0~A6, B0~ …).
- `device` 는 `CADCraft PDF` · `CADCraft PNG` · `CADCraft SVG`. `window:[[x1,y1],[x2,y2]]` + `plotArea:"window"` 로 일부만(미확인).
- 9:16 사용자 용지는 `plottermanager` 로 만들 수 있을 것 같다(미확인).

### 3.3 기존 DWG/DXF 를 화면 재료로 — 확인함 (convert · info)
```sh
cadcraft-cli convert 실제도면.dwg detail.png --window 0,0,20000,15000
cadcraft-cli run 실제도면.dwg --cmd 'select {"window":[[0,0],[20000,15000]]}' --cmd 'zoom {"mode":"object"}' --export sel.png
cadcraft-cli info 실제도면.dxf --compact      # 레이어 · 블록 · 개체 수 · 범위(extents)
```
- 샘플 `floorplan` 으로 확인: PNG · SVG · info 모두 나온다. 원본 DWG 는 시험하지 않음(미확인).
- `info.extents` 로 범위를 받아 `--window` 를 계산하면 **부분 확대 컷**(줌 인 연출)을 여러 장 만들 수 있다.
- 쇼츠 활용: 사용자가 준 도면 파일을 실제 화면 그대로 보여 주기(“실제 화면 > 효과” 원칙에 맞음).

### 3.4 줌 · 강조 연출 — 부분 확인
- `--window` 를 점점 좁혀 여러 장 내보내면 카메라 줌 프레임이 된다(옵션 확인, 연속 프레임은 미확인).
- 강조: `revcloud {"p1":[…],"p2":[…]}`(구름 표시) · `color {"color":"red"}` 뒤 그리기 · `layer` 별 색. 한 단계씩 추가해 내보내면 "여기가 문제" 장면(미확인).
- 레이어 끄기: `layoff` · `layiso` 로 일부만 보이기(미확인).

### 3.5 MCP 로 1080×1920 바로 받기 — 확인함 (mcp916.png)
MCP 서버(`cadcraft-cli mcp`, 헤드리스)의 `render` 는 크기를 받는다. 9:16 화면 재료는 이 길이 가장 깔끔하다.
```text
tools/call open   {"path":"/절대/room.dxf"}            → {"entities":9,"index":1,"warnings":[]}
tools/call render {"width":1080,"height":1920}          → image/png (base64) 1080×1920, 어두운 CAD 배경
```
- 도구 12개: `command_line` · `script` · `execute` · `list_commands` · `inspect_drawing` · `query_entities` · `render` · `find_text` · `new_drawing` · `open` · `save` · `cancel`.
- `render` 에 `window:[[x0,y0],[x1,y1]]` 를 주면 일부 확대(미확인). 흰 배경 여부 옵션은 없다(흰 종이는 `plot`).
- 에이전트 실행에서는 studio/mcp.mjs 가 craft.json 의 `"mcp":["mcp"]` 로 붙인다. 다만 지금 `agent:false` 라 켜야 붙는다.

### 3.6 수치 근거 (면적 · 개수) — 미확인
- `area` · `massprop` · `measuregeom` · `shapes`(닫힌 도형의 면적 · 둘레) · `count` · `dataextraction` 으로 도면에서 숫자를 뽑는다. 자막의 근거로 쓸 수 있다.
- `table {"at":[x,y],"rows":3,"cols":2,"cells":[[…]]}` 으로 도면 안에 표를 넣는다.

## 4. 전체 명령 분류 요약 (451개)

명령 id 는 AutoCAD 명령 이름이고(대부분 그룹 하나에 1개), 메뉴 기준으로 나누면 다음과 같다.

| 분류 | 대략 개수 | 대표 명령 |
|---|---|---|
| 그리기 | 약 35 | `line` · `pline` · `rectang` · `polygon` · `circle`(6) · `arc`(11) · `ellipse` · `spline` · `text` · `mtext` · `hatch` · `gradient` · `revcloud` · `table` · `helix` |
| 치수 · 주석 | 약 55 | `dimlinear` · `dimaligned` · `dimradius` · `dimangular` · `qdim` · `mleader` · `leader` · `dimstyle`(8) · `dimtedit`(6) · `tolerance` · `centermark` |
| 수정 | 약 45 | `move` · `copy` · `rotate` · `scale` · `mirror` · `offset` · `trim` · `extend` · `fillet` · `chamfer` · `array*` · `stretch` · `explode` · `join` |
| 블록 · 참조 | 약 30 | `block` · `insert` · `attdef` · `bedit` · `xattach` · `xref` · `wblock` · `blocks`(7) |
| 레이어 · 속성 | 약 30 | `layer` · `layiso` · `layoff` · `laymrg` · `color` · `linetype` · `lweight` · `matchprop` · `properties` |
| 배치 · 출력 | 약 25 | `layout`(8) · `mview` · `vports`(7) · `plot` · `exportpdf` · `export` · `publish` · `pagesetup` · `plottermanager` |
| 보기 | 약 25 | `zoom`(10) · `pan`(5) · `view` · `3dorbit` · `regen` · `draworder`(5) · `texttofront`(5) |
| 조회 | 약 20 | `info` 류 `list` · `dist` · `area` · `massprop` · `entities` · `shapes` · `loops` · `texts` · `count` · `find` |
| 구속 | 약 30 | `geomconstraint` · `gc*` · `dimconstraint` · `dc*` · `autoconstrain` · `parameters` |
| 파일 · 편집 | 약 40 | `new` · `open` · `qsave` · `saveas` · `recover` · `audit` · `undo` · `copyclip` · `compare`(3) · `purge` |
| 설정 · 기타 | 약 60 | `setvar` · `getvar` · `sysvars` · `osnap` · `grid` · `snap` · `units` · `cal` · `lisp` · `appload` · `script` |

MCP 도구(문서): `command_line {text}` · `script {text}` · `execute {command, params}` · `list_commands` · `inspect_drawing` · `query_entities` · `find_text` · `render {width?, height?, fit?, window?}`(PNG 크기 지정 — 3.5 에서 1080×1920 확인) · `new_drawing` · `open` · `save`, 앱 연결 때만 `screenshot` · `ui_click`.

## 5. 파이프라인 연결 제안

1. 콘티에 "도면" 장면이 있으면 에이전트가 `--cmd` 목록을 쓴다(벽 · 실 이름 · 치수). 수치는 콘티의 사실에서 온다.
2. 화면 톤: 기술 설명 → `--export`(어두운 CAD 화면), 정보 · 광고 → `plot` 흰 종이.
3. 9:16 맞추기: plot A4 세로 → 1080×1920 자르기, 또는 SVG → VectorCraft `file.place` 로 카드 위에 배치(vectorcraft.md 3.2).
4. SolidCraft 3D 모형의 도면은 `file.export_view_dxf` → `cadcraft-cli convert`(미확인).

## 6. 공식 문서

- 저장소: https://github.com/storytold/cadcraft (README 의 "Drive it from agents, MCP and the CLI")
- CLI 규칙: `docs/cli.md` · MCP: `docs/mcp.md` · 스크립트 · LISP: `docs/customization.md` · `docs/autolisp.md`
- 출력: `docs/plotters.md` · `docs/plot-styles.md` · 앱 제어: `docs/control-protocol.md`
- 빠진 기능: `docs/gaps.md` · `docs/parity-checklist.md` · `docs/roadmap.md`
