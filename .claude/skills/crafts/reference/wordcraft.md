# WordCraft 참고 (v0.15.0)

> 한 줄 요약: Word 류 문서 앱. docx · odt · rtf · html · md · txt 를 읽고 쓰며, 창 없이 문서를 만들고 고쳐 **페이지를 PNG/PDF 로 렌더**한다. 쇼츠에선 "실제 문서 화면"(약관 · 공지 · 대본 · 변경 내역)을 9:16 그대로 그려 장면 재료로 쓰는 게 핵심이다.

- CLI: `tools/crafts/wordcraft/app/wordcraft-0.15.0-linux-x86_64/bin/wordcraft-cli`
- `WORDCRAFT_REGION=ko-KR` 를 주면 기계마다 같은 결과(종이 기본값이 지역을 따라감). 페이지 크기는 아래처럼 직접 정하는 게 확실.

## 지금 Fluma 에서 쓰는 곳

- `engine/craft/adapters/wordcraft.py` — 재료 `document`. 원문(src: docx · md · odt · rtf · html · txt, 또는 title + text)을 9:16 쪽(360×640pt)으로 다시 배치해 렌더(`WORDCRAFT_REGION=ko-KR`).
- 변경 추적: 고친 판을 따로 만들고(`edit.replaceAll`) `review.compare(path, formatting=false)` → '~~7일~~ 14일 이내'. 실패하면 변경 추적을 켜고 바로 바꾸기.
- 형광펜은 진짜 `format.highlight`(못 찾으면 오류). 메모가 있으면 쪽을 360×1024pt 로 바꾸고 `file.exportPng markup` → 정확히 1080×1920.
- 글자 크기: 한 쪽이면 높이 86% 안에 드는 데까지 `design.scaleFontSizes`, 여러 쪽이면 +30% 로 하고 형광펜이 있는 쪽을 고른다. 형광펜 글자 경계 1px 이음선은 픽셀로 메운다.
- 기록: `highlighted` · `highlight`(px, 덩어리마다) · `focus` · `changes` · `comments` · `editable`(.docx). EffectCraft 는 focus 쪽으로 천천히 민다. 한 건 1.5~1.8초.
- 주의: 메모 구간은 연보라 바탕이 남는다. 말풍선 판은 문서 폭이 화면의 62%.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(확인) | 안 된다 · 미확인 |
|---|---|
| 새 문서 · 파일 열기 → 명령 실행 → docx/pdf/png 저장(`run`) | 읽어 주기(readAloud)는 앱 재생 — 오디오 파일 출력 없음(미확인) |
| 페이지 PNG 렌더(크기 · 배율 지정, 1080×1920 정확히) | 앱 스크린샷(`--connect` 로 앱 필요, 시험 안 함) |
| 하이라이트 · 굵게 · 색 · 글꼴 · 스타일 · 글자 크기 일괄 확대 | Pretendard 는 시스템에 없음(fc-list 0개) — 내장 CJK 글꼴로 그려짐 |
| 변경 내용 추적(삽입 밑줄 · 삭제 취소선) 렌더 | 차트 · SmartArt · WordArt 렌더 품질(미확인) |
| 메모 말풍선 포함 렌더(`--markup`) | Zotero 명령(Zotero 앱 필요) |
| 페이지 배경색(다크) | |
| md → docx/pdf/png, docx → md/txt/json 변환 · 텍스트 추출 · 구조 JSON | |

## 기본 형태

```sh
W=tools/crafts/wordcraft/app/wordcraft-0.15.0-linux-x86_64/bin/wordcraft-cli
export WORDCRAFT_REGION=ko-KR
$W run --script s.json --print                 # JSON 스크립트(아래). --print 면 명령마다 결과 줄
$W run --file a.docx --cmd 'id={json}' --cmd ... --save b.docx [--author 이름] [--print]
$W render a.docx out.png --page 1 --scale 3    # → {"width":1080,"height":1920,...}
$W convert a.docx out.png --markup             # 메모 말풍선 · 변경 표시까지
$W convert in.md out.docx | out.pdf            # 확장자로 형식 결정
$W info a.docx ; $W text a.docx ; $W inspect a.docx
$W commands --json                             # 651개 명령, id · label · params · mutates
```
스크립트 JSON: `{"file"?, "template"?, "commands":[{"command":id,"params":{...}} | id, ...], "save":["x.docx","x.pdf"]}` — 상대 경로는 스크립트 폴더 기준, 한 번에 docx 와 pdf 둘 다 저장 가능.

## 쇼츠용 핵심 기능

### 1. 9:16 "실제 문서" 화면 만들기 — 확인 (우선순위 높음)
약관 · 공지 · 공문 · 정책 문구를 사실 그대로 문서 모양으로 보여 주는 장면(정보 · 광고 형식의 "증거" 컷).
```json
{"commands":[
 {"command":"layout.size","params":{"width":360,"height":640}},
 {"command":"layout.margins","params":{"top":36,"bottom":36,"left":28,"right":28}},
 {"command":"styles.apply","params":{"style":"Heading 1"}},
 {"command":"text.insert","params":{"text":"이용약관 제7조 (환불)"}},
 {"command":"text.newParagraph"},
 {"command":"styles.apply","params":{"style":"Normal"}},
 {"command":"text.insert","params":{"text":"구독 시작 후 7일 이내에는 전액 환불됩니다.\n7일이 지나면 ...\n단, 프로모션 요금제는 환불되지 않습니다.","paragraphs":true}},
 {"command":"select.text","params":{"text":"프로모션 요금제는 환불되지 않습니다"}},
 {"command":"format.highlight","params":{"color":"yellow"}},
 {"command":"format.bold","params":{"value":true}}
],"save":["s1.docx","s1.pdf"]}
```
`render s1.docx s1.png --scale 3` → **1080×1920 PNG**(360pt×640pt × 3). 한글 제목(파란 Heading 1) · 본문 · 노란 형광펜 굵게 정상 확인. 0.08초.
- 글자가 작으면 `design.scaleFontSizes {"percent":40}` 로 문서 전체 글자를 한 번에 키운다(확인 — 본문 줄바꿈이 다시 계산됨).
- 강조 단계를 PNG 여러 장(강조 전 / 후)으로 렌더해 EffectCraft 에서 차례로 보이면 "형광펜이 칠해지는" 컷이 된다(렌더는 확인, 이어 붙이기는 미확인).
- 원본 문서가 docx 로 있으면 `--file 원본.docx` 로 열어 `select.text` + `format.highlight` 만 하고 렌더 — 문구를 다시 타이핑하지 않아 사실이 바뀌지 않는다.

### 2. 변경 내역(전/후) 화면 — 확인
"약관이 이렇게 바뀌었다", "AI 가 이 문장을 고쳤다" 같은 비교 장면.
```sh
$W run --file s1.docx --author "편집자" \
  --cmd 'review.trackChanges={"value":true}' \
  --cmd 'edit.replaceAll={"text":"7일 이내","with":"14일 이내"}' \
  --cmd 'review.changes={}' --save s2.docx --print
$W render s2.docx s2.png --scale 3
```
- 결과: `edit.replaceAll: {"replaced":1}`, `review.changes` 에 insert "14일 이내" · delete "7일 이내"(작성자 편집자). 렌더에 **새 글은 자홍 밑줄, 지운 글은 자홍 취소선**, 왼쪽 여백에 변경 막대.
- 주의: `edit.replace`(단수)는 먼저 찾은 선택이 없으면 **아무것도 안 하고 오류도 없다**. `edit.replaceAll` 을 쓸 것.
- `review.compare {"path":"수정본.docx"}` 또는 `{"text":"수정된 전체 글"}` 로 두 판의 차이를 변경 추적으로 만들 수 있다(미확인).
- 정리본은 `review.acceptAll {"stopTracking":true}`(확인).

### 3. 메모 말풍선이 붙은 화면 — 확인
```
select.text {"text":"전액 환불"}
review.newComment {"text":"여기가 핵심"}
```
`convert s1.docx s1m.png --markup` → 오른쪽에 "WordCraft User / 여기가 핵심" 말풍선과 점선 지시선. 작성자는 `run --author 이름` 또는 `file.setAuthor`.
- 주의: `--markup` 렌더는 폭이 넓어진다(시험 1158×1263, 9:16 아님) → 잘라 쓰거나 일반 렌더 사용.
- 주의: 메모를 단 구간은 일반 `render` 에서도 **연보라 바탕**이 남는다. 강조만 원하면 메모 대신 하이라이트.

### 4. 다크 문서 화면 — 확인(가독성 주의)
```
design.pageColor {"color":"111418"}
select.all {}
format.color {"color":"F2F2F2"}
```
- 배경 · 글자색 바뀜 확인. 단 노란 하이라이트 위 흰 글자는 거의 안 읽힌다 → 다크면 하이라이트 구간 글자색을 `000000` 으로 따로 주거나 `format.shading` 사용.
- 하이라이트에 글자 경계마다 얇은 세로 이음선이 보인다(배율 3에서) — 큰 화면에선 눈에 띌 수 있음.

### 5. 대본 · 기획서 문서(사람 검토용) — 확인
콘티/대본을 사람이 Word 에서 고치게 넘길 때.
```sh
$W convert brief.md brief.docx     # 제목 · 소제목 · 굵게 · 글머리표 · 표 그대로
$W convert brief.md brief.pdf
$W convert s1.docx s1.md           # 사람이 고친 docx → md 로 되읽기(형광펜은 **굵게**만 남음)
$W text a.docx                     # 사용자가 준 docx 브리프에서 글만
$W inspect a.docx                  # 문단별 style · text · 메모 위치 JSON
```
- 주의: `inspect` · 명령 결과의 `off`/`len` 은 **UTF-8 바이트** 단위(한글 1자 = 3). 글자 수로 계산하지 말 것.

### 6. 그 밖의 재료 후보(미확인)
- `insert.picture {"path":..., "width":pt}` — 실제 스크린샷을 문서 안에 넣은 "보고서" 화면
- `insert.table {"rows":3,"cols":2}` + 텍스트 — 비교 형식 표(GridCraft 가 더 맞을 수 있음)
- `insert.chart {"type":"bar","data":{"categories":[...],"series":[{"name":..,"values":[..]}]}}`
- `insert.icon {"query":"check"}` — 목록만 확인(`{"icons":[...check...]}`), 삽입은 `{"id":"check"}`
- `design.watermark {"text":"초안"}` · `insert.equation {"latex":"..."}`(수식 설명 쇼츠)
- `file.exportPng {"path":..,"page":n,"scale":s}` — 스크립트 안에서 렌더

## 주의 (실측)

- 결과 줄은 `run --print` 를 줘야 명령마다 나온다. 없으면 `wrote x.docx` 만.
- 틀린 명령이 조용히 무시될 수 있다(edit.replace) → 끝에 `review.changes` · `document.text` · `info` 로 확인.
- 문단 나누기: `text.insert` 에 `"paragraphs":true` + `\n`. 스타일은 이름(`"Heading 1"`)으로 적용됨.
- 실행 시간: 생성 · 렌더 모두 1초 안쪽.
- 쉘에서 `ls -la` 가 이상하게 멈춘 적이 있다(이 쉘의 ls 별칭 문제로 보임, WordCraft 와 무관). `/usr/bin/ls` 사용.

## 전체 명령 분류 (651개, 바꾸는 명령 406개, `wordcraft-cli commands --json`)

| 그룹 | 개수 | 대표 |
|---|---|---|
| para | 50 | 정렬 · 들여쓰기 · 줄간격 · 문단 간격 |
| table | 48 | 행/열 추가 · 병합 · 테두리 · 스타일 |
| insert | 44 | picture · table · chart · icon · shape · textBox · header/footer · pageNumber · equation · coverPage · link |
| view | 41 | 보기 모드 · 줌 · 다크(헤드리스엔 의미 적음) |
| format | 40 | bold · highlight · color · font · size · shading · textEffects · set(CharProps) |
| review | 35 | trackChanges · acceptAll · changes · newComment · compare · combine · spelling · wordCount |
| edit | 31 | find · replaceAll(정규식 · 와일드카드) · undo · paste(html/rtf) |
| file | 30 | new(blank/sample/letter/resume/report) · open · save · exportPdf · exportPng · properties · protect |
| outline | 26 | 개요 수준 · 이동 |
| references | 25 | 각주 · 목차 · 인용 · 캡션 |
| text | 23 | insert · newParagraph · pageBreak · 기호 |
| mailings | 23 | 메일 머지(같은 틀에 데이터 채워 여러 장 — 당일 시세 형식에 응용 가능, 미확인) |
| equation | 21 | 수식 |
| layout | 18 | size · margins · orientation · columns · break |
| caret · select | 16 · 14 | 커서 이동 · select.text · select.all · select.range |
| styles · design | 16 · 12 | apply · modify · theme · styleSet · scaleFontSizes · pageColor · watermark |
| draw · arrange · shape · canvas | 16 · 15 · 9 · 4 | 도형 · 정렬 |
| developer · tools | 16 · 11 | 콘텐츠 컨트롤 · 매크로 |
| picture | 14 | size · crop · corrections · color · removeBackground · style |
| fields · smartArt · readAloud | 8 · 8 · 7 | 필드 · SmartArt · 읽어 주기(앱 재생) |
| document · chart · font · wordArt | 6 · 5 · 4 · 4 | inspect · text · setText · editData |
| list · proof · hf · link · object | 3 · 3 · 3 · 1 · 1 | |

## MCP

`wordcraft-cli mcp --automation-read-root DIR --automation-write-root DIR` — 도구: `list_commands` · `execute` · `batch` · `new_document` · `open_document/save_document` · `type_text` · `select_text` · `get_text/inspect_document` · `render_page`(PNG) · `parity`. 변경 추적 작성자는 `--author`. (MCP 직접 구동은 시험 안 함 — 미확인)

## 공식 문서

- 저장소: https://github.com/storytold/wordcraft (README "For agents: CLI and MCP")
- MCP · 스크립트 · CharProps/ParaProps 표: https://github.com/storytold/wordcraft/blob/main/docs/mcp.md
- 빠진 기능: https://github.com/storytold/wordcraft/blob/main/docs/gaps.md
- 제어 프로토콜: https://github.com/storytold/wordcraft/blob/main/docs/control-protocol.md
- 홈페이지: https://getartcraft.com/apps/wordcraft
