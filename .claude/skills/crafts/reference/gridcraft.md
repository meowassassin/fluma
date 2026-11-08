# GridCraft 참고 (v0.16.0)

**한 줄 요약**: Excel 같은 스프레드시트(Rust, MIT/Apache-2.0). 명령 372개 + 함수 515개가 `gridcraft-cli` 로 헤드리스에서 돈다. Fluma 에서는 **숫자 근거**를 맡는다: 원자료 읽기 · 계산(비율 · 합계 · 순위) · 정렬 · 피벗 집계. 그림(차트)은 그리지 않고 숫자만 넘긴다. 사람이 나중에 `.xlsx` 를 열어 숫자를 확인 · 수정한다.

- CLI: `tools/crafts/gridcraft/app/gridcraft-0.16.0-linux-x86_64/bin/gridcraft-cli`(아래에서는 `$GC`)
- 웹 빌드: `tools/crafts/gridcraft/web/gridcraft-web-0.16.0`

## 지금 Fluma 가 쓰는 범위

`engine/craft/materials.py` 의 `chart()` 어댑터 하나뿐이다.
- `$GC cat <csv|xlsx> --range A1:B20 --csv` 로 표를 읽고,
- `percent: true` 이면 값마다 `$GC eval "=A{k}/SUM(A2:A{n})*100" --in tmp.csv` 를 **값 개수만큼 따로** 돌려 비율을 낸다.
- 차트 그림은 EffectCraft 가 화풍 팔레트로 그린다("엑셀 기본 차트는 쇼츠 화풍과 안 맞고 한글이 깨져서" — 아래 시험으로 한글 깨짐 확인).
- `studio/server.mjs` 는 `.csv` · `.xlsx` 자산을 GridCraft 로 열게 연결한다(`ASSET_APP`, `NATIVE: .xlsx`). `engine/doctor.py` · `ci_render_smoke.py` 는 설치 확인만.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(시험함) | 안 된다 / 미확인 |
|---|---|
| CSV · JSON · XLSX 열기, 셀 · 수식 입력, 채우기, 정렬 | **PDF 내보내기에서 한글이 빠진다**(머리글 · 차트 제목 빈칸). `home.fontName "Noto Sans CJK KR"` 을 줘도 마찬가지 |
| 함수 515개(`eval` 한 줄 계산, XLOOKUP · TEXT · ROUND 등) | Python 셀(`python.set`)은 `#BLOCKED!`. 헤드리스에서 안 돈다 |
| 표(서식 있는 Table) · 조건부 서식 · 차트 만들기 · 색 · 데이터 레이블 | 창 스크린샷(MCP `screenshot`)은 실행 중인 앱(Remote)에서만 |
| 피벗(행 · 값 · 합계 대비 비율), 차트 추천 | HTML 내보내기는 글자 크기 · 열 너비가 거의 반영되지 않는 것으로 보였다(덜 확인) |
| xlsx · csv · tsv · json · html · pdf 변환 | 목표값 찾기 · 해 찾기(`data.goalSeek` · `data.solver`)는 미확인 |

**공통 규칙**
- `run` 형식: `$GC run [--in FILE | --sample budget|sales|grades] --cmd 'id={json}' … [--script s.jsonl] --out out.xlsx --print A1:D5|used [--quiet]`. 단계마다 결과가 JSON 한 줄로 찍힌다. 첫 실패에서 멈춘다(0 아닌 종료 코드).
- 스크립트 한 줄: `id={json}` 또는 `{"command":"id","params":{…}}`. `#` · `//` 주석 가능. DesignCraft 와 달리 **앞 결과 참조(`$N`)가 없다**.
- 수식은 영어 함수 이름, 인자 구분은 `,`.
- 차트 id 는 파일을 다시 열면 바뀐다(만들 때 2 → 다시 열면 1). 차트가 하나면 `chart` 를 빼면 된다. 아니면 `$GC info f.xlsx --json` 의 `charts[].id` 를 읽는다.
- CSV 를 열면 시트 이름은 파일 이름(`tools.csv` → `tools`).

## 쇼츠용 핵심 기능

### 1. 한 줄 계산 `eval` (verified, 일부 이미 씀)
숫자를 손으로 계산하지 않는다는 storyboard 규칙의 바탕.
```sh
$GC eval '=XLOOKUP("Claude",A2:A5,D2:D5)' --in s1.xlsx      # 240
$GC eval '=TEXT(1234567,"#,##0")'                            # 1,234,567  (자막용 천 단위 쉼표)
$GC eval '=ROUND(AVERAGE(B2:B5),1)' --in s1.xlsx --json      # 12.5
```
- 개선 여지: 지금 `chart()` 는 비율을 값마다 프로세스 하나씩 돌린다. 아래 2번처럼 `run` 한 번에 열을 채우고 `--print` 로 받으면 한 번에 끝난다.
- 쇼츠에 바로 쓰는 함수 예: `RANK.EQ`(순위), `PERCENTRANK`, `GROWTH` · `TREND`(추세), `XLOOKUP`, `TEXT`(표시 형식), `DATEDIF`(기간), `PMT`(월 납입금 — 금융 정보 쇼츠), `SORTBY` · `FILTER` · `UNIQUE`(동적 배열). 분류: Statistical 110 · MathTrig 80 · Financial 55 · Engineering 54 · Text 48 · Lookup 36 · DateTime 25 · Logical 19 등.
- 함수 찾기: `$GC functions --search lookup`, `--category Financial`.

### 2. 표 정리 + 계산 열 + 정렬을 한 번에 (verified)
비교 형식(format-compare)의 "같은 기준의 값" 표를 만든다.
```jsonl
file.open={"path":"tools.csv"}
cell.set={"cell":"D1","input":"연 요금"}
cell.set={"cell":"D2","input":"=B2*12"}
edit.fillDown={"range":"D2:D5"}
home.bold={"range":"A1:D1"}
insert.table={"range":"A1:D5","style":"TableStyleMedium2","name":"T"}
home.conditionalFormat={"range":"D2:D5","rule":{"type":"top10","rank":1}}
```
```sh
$GC run --script s1.jsonl --out s1.xlsx --print A1:D5
$GC run --in s1.xlsx --cmd 'data.sort={"range":"A1:D5","header":true,"keys":[{"column":"C","order":"desc"}]}' --print A1:D5 --quiet
```
- 결과: `--print` 가 정렬된 표를 바로 찍는다(한글 머리글 정상). `D` 열은 수식으로 채워졌다(240 · 240 · 0 · 120). 정렬도 "무료 한도" 내림차순으로 맞았다.
- 결과를 기계가 읽으려면 `--print` 대신 `$GC cat s1.xlsx --range A1:D5 --csv` 또는 `$GC convert s1.xlsx s1.json`(셀 · 수식 · 스타일 전체 JSON, 16KB).
- `.xlsx` 를 남겨 두면 사람이 GridCraft 웹에서 숫자를 고치고, 다음 렌더가 그 파일을 다시 읽는다(수식이 살아 있으므로 파생값도 따라 바뀐다).

### 3. 원자료 집계: 피벗 (verified)
"지역별 매출 비중" 같은 원자료 → 요약을 사람이 계산하지 않게.
```jsonl
data.getData={"path":"sales.json"}
insert.pivotTable={"destination":"new"}
pivot.addField={"field":"지역","area":"rows"}
pivot.addField={"field":"매출","area":"values","func":"sum"}
pivot.valueSettings={"index":0,"showAs":"percentOfGrandTotal"}
```
- 결과: 서울 53.47% · 부산 34.65% · 대구 11.88% · 합계 100%(새 시트 `Sheet2`, `A3` 부터).
- `data.getData` 는 CSV/TSV/**JSON 객체 배열**을 새 시트의 표로 넣는다(웹에서 받은 JSON 을 바로).
- 주의: `pivot.sort {"field":"지역","order":"desc"}` 는 **값이 아니라 이름**으로 정렬됐다. 값 순서가 필요하면 결과를 `data.sort` 하거나 `cat --csv` 받은 뒤 정렬.
- 그 밖: `pivot.group {by: years|quarters|months}`(날짜 묶기), `pivot.filter`, `insert.recommendedPivotTables`(미확인).

### 4. 차트 종류 추천 (verified)
콘티의 `kind` 를 에이전트가 고를 때 근거로.
```sh
$GC run --in s1.xlsx --cmd 'insert.chartRecommendations={"range":"A1:C5"}'
# → [{"type":"column","label":"Clustered Column"},{"type":"bar"},{"type":"column","subtype":"stacked"},{"type":"line","subtype":"markers"},…]
```

### 5. 엑셀 차트 자체 (verified — 쓰지 말 것, 이유 기록)
```sh
$GC run --in s1.xlsx --cmd 'pageLayout.orientation={"orientation":"landscape"}' --cmd 'pageLayout.scaleToFit={"width":1,"height":1}' \
  --cmd 'chart.set={"title":"월 요금(달러)","dataLabels":true}' --cmd 'chart.changeColors={"colors":["#FFD400"]}' --out s2.xlsx --quiet
$GC convert s2.xlsx s2.pdf && pdfcraft-cli render s2.pdf --page 1 --dpi 100 --out s2.png
```
- 결과: 노란 막대 · 데이터 레이블 · 한 페이지 맞춤은 됐다. 그러나 **한글(머리글 "툴 · 월 요금", 차트 제목 "월 요금")이 전부 빈칸**이고 괄호만 남았다. 차트는 `D1` 에 놓여 D 열을 가린다.
- 결론: 차트 그림은 지금처럼 EffectCraft 가 그린다. 영어 · 숫자만 있는 "실제 엑셀 화면" 느낌이 필요할 때만 쓰고, 그때도 `chart.move {"at":"F2"}` 로 표를 피한다.
- 차트 17종: column · bar · line · pie · doughnut · area · scatter · bubble · radar · combo · histogram · waterfall · funnel · treemap · sunburst · boxWhisker · stock. `insert.sparkline` 도 있다.

### 6. 표를 실제 화면처럼 보이기 (부분 verified)
- `$GC convert s.xlsx s.html` → 한글이 나오는 HTML 표. 헤드리스 Chrome(`google-chrome --headless=new --screenshot`)으로 찍으면 한글은 나오지만 기본 Calibri 계열 작은 글씨 표다. 쇼츠 화면으로는 밋밋하다.
- 더 나은 길(미확인): `cat --csv` 결과를 DesignCraft `file.place`(`.xlsx` 를 표로 배치) 또는 `table.*` 로 넣어 세로 카드로 만든다.

### 7. 숫자 검증 `check` (미확인)
`$GC check book.xlsx --json`: 파일에 저장된 값과 GridCraft 재계산을 비교한다. 사용자가 올린 엑셀의 숫자를 영상에 쓰기 전에 오류가 없는지 확인하는 데 쓸 수 있다.

## 전체 명령 분류 요약 (372개, `$GC commands --json`)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| home | 64 | bold · fontColor · fillColor · numberFormat · conditionalFormat · formatAsTable · columnWidth |
| data | 41 | sort · filterBy · removeDuplicates · getData · fromTextCsv · subtotal · goalSeek · solver |
| formulas | 32 | evaluate · autoSum · defineName · tracePrecedents · calculationOptions |
| view | 27 | freezePanes · zoom · gridlines · pageBreakPreview(화면 표시) |
| edit | 26 | fillDown · fillSeries · flashFill · find · replace · pasteSpecial |
| pivot | 22 | addField · valueSettings · group · filter · layout · refresh |
| review | 21 | newNote · newComment · protectSheet · workbookStatistics |
| insert | 17 | table · chart · chartRecommendations · sparkline · picture · shape · icons · equation · pivotTable |
| pageLayout | 16 | orientation · scaleToFit · printArea · theme |
| table | 14 | totalRow · style · resize |
| file | 13 | open · save · saveAs(.pdf/.html/.json) · exportCsv |
| chart | 12 | set · addElement · changeColors · selectData · changeType · move |
| sheet | 10 | read · rename · move |
| 나머지 | 1~9 | macro · automate(스크립트 저장 · 실행) · slicer · python(2, 막힘) · cell(set · get) · range(setValues · fill) |

CLI 하위 명령: `info` · `convert` · `eval` · `cat` · `check` · `run` · `commands` · `functions` · `mcp` · `send` · `version`.

## MCP

`gridcraft-cli mcp [--in FILE | --sample NAME]`(craft.json 의 `mcp` 줄). 읽기/쓰기 루트 옵션이 없다(craft.json 에 `sandbox:false`).
`screenshot` 도구는 실행 중인 앱(Remote)에서만 된다. Fluma 에서 MCP 로 붙인 곳은 없다.

## 공식 문서

- 저장소: https://github.com/storytold/gridcraft
- CLI: https://github.com/storytold/gridcraft/blob/main/docs/cli.md (`run` · `check` 설명)
- MCP: https://github.com/storytold/gridcraft/blob/main/docs/mcp.md
- 차트 대응표: https://github.com/storytold/gridcraft/blob/main/docs/chart-parity.md
- 함수 대응표: https://github.com/storytold/gridcraft/blob/main/docs/function-parity.md
- 매크로: https://github.com/storytold/gridcraft/blob/main/docs/macros.md
- 홈페이지: https://getartcraft.com/apps/gridcraft
