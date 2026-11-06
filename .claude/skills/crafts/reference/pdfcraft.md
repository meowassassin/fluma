# PdfCraft 참고 (v0.18.0)

**한 줄 요약**: Acrobat 같은 PDF 앱(Rust, MIT/Apache-2.0). 자동화 도구 183개와 CLI 하위 명령이 모두 헤드리스에서 돈다. Fluma 에서는 **근거 화면**을 맡는다: 논문 · 보고서 · 공문의 문장 찾기 → 진짜 형광펜 · 빨간 박스 → 필요한 부분만 잘라 고해상도 렌더. 화면 캡처에서 글자 위치 찾기(OCR)도 된다.

- CLI: `tools/crafts/pdfcraft/app/pdfcraft-0.18.0-linux-x86_64/bin/pdfcraft-cli`(아래에서는 `$PC`)
- 웹 빌드: `tools/crafts/pdfcraft/web/pdfcraft-web-0.18.0`

## 지금 Fluma 가 쓰는 범위

`scripts/craft/adapters/pdfcraft.py`(재료 `doc_quote`, 기본 어댑터를 덮어씀). 원본은 건드리지 않고 사본 `work/<id>.src.pdf` 에서:
1. `text_find`. 못 찾으면 `text_lines` 줄 글을 공백 없이 이어 찾고(줄 끝 하이픈 유지 → 제거 순), 걸친 줄마다 조각을 다시 찾아 정확한 사각형.
2. 렌더 픽셀의 잉크로 사각형을 맞춘다(폭 85% 미만이면 줄임, 24pt 이상 큰 글씨 위아래 보정).
3. `redact`: 정규식 → `redact_mark words` → `redact_apply`(글자도 실제로 지워짐). phone · email · rrn 은 한국식 정규식(내장 패턴은 '1. 조사 개요' 의 '1' 까지 지웠다).
4. 진짜 주석 `comment_add`: highlight(줄마다 quad) · underline · 상자(한 줄 rectangle, 여러 줄 polygon). `work/<id>.marked.pdf` 저장.
5. 위아래 `context` 줄까지 같은 단만 `page_set_box` 로 자르고 `doc_export_images`(폭 1080). 한 건 0.2~0.8초.
기록: `highlight`(px, 줄마다) · `focus`(문장 전체 상자 px) · `highlighted` · `crop` · `dpi` · `size` · `redacted` · `editable`. EffectCraft 는 highlighted 면 가짜 형광펜 없이 focus 로 확대만.
안 쓰는 것: 영어 OCR(스캔 PDF), 그림 원본 뽑기, `doc_compare`.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(시험함) | 안 된다 / 미확인 |
|---|---|
| 열기 · 문장 찾기(영어 · 한국어) · 렌더(PNG, 최대 600dpi) | OCR 은 **영어만**(`ocr_status` → languages: en). 한국어 화면 OCR 은 안 된다 |
| 형광펜 · 사각형 주석을 PDF 에 넣고 렌더에 그대로 나옴 | `doc_create {from:"text"}` 는 WinAnsi(서유럽 글자)만. 한글 텍스트로 PDF 만들기 안 됨 |
| 쪽 자르기(crop box) 후 그 부분만 내보내기 | `doc_compare`(두 판 비교)는 미확인 |
| 영역 글자 뽑기(표를 탭 구분으로) | `render_preview` 는 열린 문서용이라 한 줄 실행(`run <tool> path=…`)으로는 안 됨(`unknown argument "path"`) |
| 쪽 안 그림 원본 저장(`image_save`) | UI 조종(`ui --control`)은 데스크톱 앱 필요 |
| 이미지 → PDF + OCR(영어) → 글자 위치 찾기 | Office 내보내기 결과물의 품질은 열어 보지 않았다(파일만 확인) |
| 개인정보 가리기(이메일 패턴 → 검은 박스, 실제 삭제) | |

**공통 규칙**
- 좌표: **pt, 왼쪽 위 원점, y 아래로**. 72dpi 로 렌더하면 1pt = 1px. 다른 dpi 는 `× dpi/72`.
- 사각형: `text_find` 의 `rects` 는 `[x0, y0, x1, y1]`(줄마다 하나, 여러 줄이면 여러 개). `doc_compare` 만 원점이 왼쪽 아래라고 문서에 적혀 있다.
- 스크립트: JSON 배열 `[{"tool":"…","args":{…}}, …]`. `doc` id 는 연 순서대로 1, 2, …(앞 결과 참조 문법은 없다 — 순서로 정해진다).
- `--report` 는 전체 결과를 JSON 하나로(`steps[].result` · `status`). `--root DIR` 은 상대 경로의 기준이자 접근 허용 폴더.
- 한 도구만: `$PC run <tool> key=value … --root DIR [--out image.png]`. 도구 목록과 JSON 스키마: `$PC tools`.
- 모두 빠르다: 15쪽 논문 열기 · 찾기 · 주석 · 저장이 1초 안, OCR 한 쪽 0.4초, 렌더 한 쪽 10~20ms.

## 쇼츠용 핵심 기능

### 1. 진짜 형광펜을 PDF 에 긋고 렌더 (verified)
지금은 EffectCraft 가 사각형 위에 형광펜을 그리지만, PdfCraft 가 **글자 모양에 딱 맞는 Acrobat 형광펜**을 긋는다. 두 줄에 걸친 문장도 줄마다 정확히 칠해진다. 실제 화면 느낌이 더 진짜다.
```json
[{"tool":"doc_open","args":{"path":"dl/attn.pdf"}},
 {"tool":"text_find","args":{"doc":1,"query":"dispensing with recurrence and convolutions entirely","limit":1}},
 {"tool":"comment_add","args":{"doc":1,"page":1,"type":"highlight","find":"dispensing with recurrence and convolutions entirely","color":"yellow"}},
 {"tool":"doc_save","args":{"doc":1,"path":"hl.pdf"}}]
```
```sh
$PC run --script s1.json --report --root . > s1.out
$PC render hl.pdf --page 1 --dpi 200 --out hl1.png
```
- 결과: `text_find` → `page:1`, `rects` 두 줄(`[295.1,456.6,468.1,466.6]`, `[143.9,467.5,174.9,477.5]`). 형광펜이 두 줄에 걸쳐 노랗게 렌더됐다.
- `comment_add` 형식: highlight · underline · strikeout · squiggly 는 `find`(그 쪽 안 글자, `all:true` 면 전부) 또는 `quads`. 색은 `#RRGGBB` 또는 yellow · red · orange · green · blue · purple · pink 등.
- 움직임(형광펜이 그어지는 효과)이 필요하면: 형광펜 없는 렌더 + 있는 렌더 두 장을 EffectCraft 에서 왼쪽→오른쪽 와이프로 섞는다(미확인 아이디어). 또는 지금처럼 `rects` 만 넘긴다.

### 2. 빨간 박스 + 그 부분만 잘라 내기 (verified)
표 · 그래프 · 결론 단락처럼 "여기 보세요" 장면. 쪽 전체를 확대하는 것보다 글자가 훨씬 선명하다.
```json
[{"tool":"doc_open","args":{"path":"dl/attn.pdf"}},
 {"tool":"comment_add","args":{"doc":1,"page":8,"type":"rectangle","rect":[100,90,520,260],"color":"red","width":3}},
 {"tool":"page_set_box","args":{"doc":1,"pages":[8],"rect":[90,80,530,270]}},
 {"tool":"doc_export_images","args":{"doc":1,"pages":[8],"dpi":150,"folder":"exp"}}]
```
- 결과: 8쪽 크기가 `[440,190]` pt 로 바뀌고, `exp/attn_page_8.png` 에 BLEU 표만 빨간 테두리와 함께 나왔다.
- 세로 쇼츠용 해상도: 폭 1080px 에 맞추려면 `dpi = 1080 / (잘라 낸 폭 pt) × 72`(440pt → 약 177dpi). 최대 600(page_render) · 1200(doc_export_images).
- `page_set_box` 는 문서를 바꾼다(되돌리기 가능). 원본 쪽도 필요하면 자르기 전에 렌더하거나 `page_duplicate` 후 자른다.
- 박스 위치는 `text_find` 의 `rects` 를 넉넉히 감싸 정하면 사람 조정이 거의 없다.
- 그 밖의 주석 모양: `oval`, `textbox`(`contents` 글), `arrow`/`line`(`from`, `to`, `endings`), `stamp`(approved · confidential 등), `note`.

### 3. 표 · 영역 글자 뽑기 → GridCraft (verified)
논문 표 숫자를 손으로 옮겨 적지 않는다.
```json
[{"tool":"doc_open","args":{"path":"dl/attn.pdf"}},
 {"tool":"text_extract","args":{"doc":1,"pages":[8],"rect":[90,90,530,260]}}]
```
- 결과: 한 줄 = 한 행, 칸은 탭. 예 `"Transformer (big)\t28.4 41.8\t2.3 · 1019"`.
- 주의: **위첨자가 납작해진다**(10¹⁹ → `1019`). 칸 일부는 탭이 아니라 공백으로 붙는다. 숫자는 꼭 원문 렌더와 대조하고, 정리된 값은 GridCraft `.csv` 로 남긴다.
- 쪽 전체 글: `text_extract {doc, pages}`, 파일로: `doc_export_text {doc, path}`. CLI 한 줄: `$PC text f.pdf --page 3`.

### 4. 논문 그림 원본 꺼내기 (verified)
Figure 를 쪽 렌더가 아니라 **원본 해상도 이미지**로 꺼내 장면 재료(photo · image)로 쓴다.
```json
[{"tool":"doc_open","args":{"path":"dl/attn.pdf"}},
 {"tool":"page_images","args":{"doc":1,"page":3}},
 {"tool":"image_save","args":{"doc":1,"page":3,"image":1,"path":"fig1.png"}}]
```
- 결과: `page_images` → `{"image":1,"pixels":[1520,2239],"rect":[196.56,72.0,415.44,394.42]}`, `fig1.png` 1520×2239(트랜스포머 구조도).
- 벡터로 그린 그림(Form)은 `image_save` 가 거부한다 → 그때는 `rect` 로 `page_set_box` 해서 렌더(2번).
- 쪽 안 모든 그림 한꺼번에: `doc_export_all_images {doc, folder, min_size}`(미확인).

### 5. 화면 캡처 OCR → 글자 위치 (verified, 영어만)
실제 앱 · 웹 화면(screen 재료) 녹화에서 "이 버튼" "이 메뉴" 의 위치를 찾아 확대 · 강조할 좌표를 얻는다. 손으로 좌표를 찍지 않는다.
```json
[{"tool":"doc_create","args":{"from":"images","paths":["shot.png"],"dpi":72}},
 {"tool":"ocr_recognize","args":{"doc":1,"language":"en"}},
 {"tool":"text_find","args":{"doc":1,"query":"Reference Shorts"}}]
```
- 결과: 0.36초. OCR 31단어, `text_find` → `rects [[514.0,406.7,686.0,434.6]]`. `dpi:72` 로 만들었으므로 **pt = 원본 픽셀**이다.
- 모델은 릴리스에 들어 있다(`ocr_status` → `available:true`, 경로 `…/bin/../share/pdfcraft/models`). 내려받기 필요 없음.
- 한국어 UI 화면은 안 된다(언어 en 하나). 굵은 아이콘 글자는 잘못 읽는다("O Reference" 처럼 앞에 잡음).

### 6. 개인정보 가리기 (verified)
사용자가 올린 보고서 · 영수증 화면에 이메일 · 전화번호가 있을 때.
```json
{"tool":"redact_mark","args":{"doc":1,"pattern":"email","pages":[1]}},
{"tool":"redact_apply","args":{"doc":1,"pages":[1]}}
```
- 결과: 1쪽 이메일 8개 표시 → 적용(`applied: 8`). 글자가 실제로 지워진다(검은 박스). `pattern`: phone · email · credit-card · ssn · date(미국식 패턴이라 한국 전화번호는 미확인). `words:[…]` 로 이름 목록도 된다.

### 7. 한국어 PDF 찾기 (verified)
DesignCraft 가 만든 한국어 PDF 에서 `text_find {"query":"마지막 정리"}` → 3쪽, 사각형 1개. (2026-11-05 다시 확인) '프레임 폭' 은 재현되지 않았다 — 60pt 시작은 실제 글자 위치였다. 실제 문제는 둘: ① 큰 글씨(110pt)에서 사각형이 글자보다 약 8% 아래로 밀린다 ② 낱말 가운데서 줄이 바뀐 한국어 문장('이\n용자의')은 `text_find` 가 못 찾는다. 둘 다 어댑터가 잉크 맞춤 · 줄 이어 찾기로 처리한다.

### 8. 그 밖에 쓸 만한 것 (미확인)
- `text_styles {doc}`: 글자 크기 · 글꼴별 줄 수와 첫 줄. 큰 글씨 = 제목을 찾아 "이 논문의 절 제목" 장면을 만든다(시험에서 제목 "Attention Is All You Need" 17.2pt, "Abstract" 12pt 로 나옴 — 목록 자체는 verified).
- `doc_compare {doc, other, visual}` · `doc_compare_mark`: 약관 · 정책 개정 전후 차이를 주석으로 표시 → "바뀐 부분" 쇼츠.
- `doc_export_office {doc, path:".pptx"|".docx"|".html"}`: 15쪽 → pptx 502KB 생성 확인(내용 품질 미확인).
- `doc_combine {paths, out}`: 사진 · 캡처 여러 장을 PDF 한 권으로(이미지 입력 가능).
- `bookmark_list`: 목차 → 긴 보고서에서 장 찾기.
- `page_enhance_camera {corners}`: 폰으로 찍은 문서 사진을 반듯하게 펴기.
- `$PC batch <dir> --steps convert,ocr,optimize --out-dir out`: 폴더 단위 일괄 처리.

## 전체 도구 분류 요약 (183개, `$PC tools`)

| 묶음 | 개수 | 대표 도구 |
|---|---|---|
| doc | 39 | doc_open · doc_info · doc_save · doc_create · doc_combine · doc_export_images · doc_export_office · doc_compare · doc_watermark · doc_header_footer |
| accessibility | 18 | accessibility_check · autotag · set_alt |
| page | 17 | page_render · page_set_box · page_images · page_extract · page_rotate · page_enhance_camera |
| form | 15 | form_fields · form_fill · form_add_field · form_detect_fields |
| text | 12 | text_find · text_extract · text_lines · text_paragraphs · text_styles · text_edit |
| bookmark · comment | 9 · 9(+comments 2) | comment_add(형광펜 · 박스 · 화살표 · 도장) · comment_list · bookmark_list |
| measure | 8 | measure_distance · measure_area(도면) |
| sign | 6 | sign_document · sign_list |
| link · links | 5 · 2 | link_add · links_from_urls |
| content · image · ocr · redact | 4 · 3 · 3 · 3 | page_add_text · image_save · ocr_recognize · redact_mark |
| 나머지 | 1~4 | js_run · pdfa_* · action_run(Action Wizard) · command_run · command_batch · render_preview |

CLI 하위 명령: `info` · `render` · `text` · `edit`(회전 · 삭제 · 이동) · `combine` · `extract` · `split` · `check` · `audit` · `batch` · `tools` · `run` · `mcp` · `ui`.

## MCP

`pdfcraft-cli mcp --automation-read-root $ROOT --automation-write-root $WRITE`(craft.json 의 `mcp` 줄). `--compact` 는 핵심 도구 + `tool_search` · `tool_call` 만 보인다(도구가 183개라 에이전트 문맥 절약에 좋다). Fluma 에서 MCP 로 붙인 곳은 없다.

## 공식 문서

- 저장소: https://github.com/storytold/pdfcraft (README "Built for agents, too")
- MCP: https://github.com/storytold/pdfcraft/blob/main/docs/mcp.md
- 일괄 변환 · OCR: https://github.com/storytold/pdfcraft/blob/main/docs/cli-batch.md
- 쪽 표시: https://github.com/storytold/pdfcraft/blob/main/docs/page-display.md
- 기존 글 고치기: https://github.com/storytold/pdfcraft/blob/main/docs/editing-existing-text.md
- 홈페이지: https://getartcraft.com/apps/pdfcraft
