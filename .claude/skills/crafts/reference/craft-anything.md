# Craft Anything 참고 (v0.3.0)

**한 줄 요약**: 소프트웨어 · 웹사이트 · 앱 동작 분석(리버스 엔지니어링) 도구(Rust, MIT/Apache-2.0, 저장소 `storytold/craft-anything`). 도구 315개(17 toolset: core · browser · native · formats · adb · android · apple · runtime · javascript · projects …)를 CLI 하위 명령과 MCP 로 부른다. 쇼츠에서는 **실제 웹사이트를 폰 크기(9:16)로 찍기 · 클릭 순서대로 화면 찍기 · 사이트 디자인 토큰(글꼴 · 색) 뽑기 · 터미널 실행 기록 · 연결된 안드로이드 폰 화면 찍기** 를 맡는다. 지금 Fluma 는 이 앱을 **전혀 쓰지 않는다**(craft.json `agent:false`, 부르는 곳 없음).

- 실행 파일: `tools/crafts/craft-anything/app/craft-anything-0.3.0-linux-x86_64/bin/craft-anything-cli`
  (에이전트는 `python3 engine/craft/crafts.py run craft-anything <인자…>` 로 부른다)

---

## 1. 헤드리스로 되는 것 / 안 되는 것

| 구분 | 내용 |
|---|---|
| 된다 (확인) | `web-walkthrough-record`: 브라우저(이 PC: `/usr/bin/google-chrome`)를 띄워 goto · click · fill · wait 순서를 돌리고 **단계마다 PNG**. 360×640 @3x → 1080×1920, 390×693 @2x → 780×1386 (각 3초 안쪽) |
| 된다 (확인) | MCP `web_site_open` → `web_site_capture`: 전체 페이지 PNG · HTML · 디자인 토큰(capture.json · README.md) |
| 된다 (확인) | `runtime-walkthrough-record`: 프로그램을 가상 터미널에서 돌리고 입력을 시간표대로 넣어 **최종 화면 줄 목록**을 JSON 으로 |
| 된다 (확인) | `capabilities` · `adb-devices-find`(지금 연결된 폰 0대) · `commands` |
| 안 된다 (확인) | 기본은 **Clean room** 모드라 웹 · 실행 도구가 거부된다(`feature_missing: clean_room`). `--deep` 를 붙여야 한다 |
| 안 된다 (확인) | 실행 · 기기 변경 도구는 동의가 필요하다(`consent_required`). 헤드리스에서는 `--allow-run` 을 붙인다 |
| 안 된다 (확인) | `web-site-open` 과 `web-site-capture` 는 **같은 세션**이어야 한다. CLI 는 명령마다 새 프로세스라 이어지지 않는다 → MCP 로 한 세션에서 부른다 |
| 안 된다 | `runtime-walkthrough-record` 는 글자만 준다(PNG 없음). 터미널 화면 그림은 WordCraft/VectorCraft 등으로 다시 그려야 한다 |
| 금지 | `assets-image-generate` · `assets-model-generate`(fal.ai 유료) · `engines-install` · `setup-apply`(다른 앱 설정 변경) · `adb-app-install/remove` 는 쓰지 않는다 |
| 주의 | 로그인 · 쿠키(`storage`)를 넣으면 비밀값으로 가려지지만, Fluma 에서는 넣지 않는다. 공개 페이지만 찍는다 |

## 2. 기본 문법

```sh
craft-anything-cli [--deep] [--allow-run] [--project /절대/lab.cany] <tool-id-대시> [--옵션 값 …] [@params.json | --json '{…}' | -]
craft-anything-cli <tool> --help        # 그 도구의 옵션 · 입력 구조
craft-anything-cli commands             # 315개 JSON: command · tool · toolset · summary · needs_target
craft-anything-cli capabilities         # 엔진(chromium · adb · gdb …) 유무, 모드
craft-anything-cli mcp [--all-tools] [--deep] [--allow-run] [--project …]   # 기본은 Essentials + 켠 toolset(37개)
```
- 결과는 "증거(evidence)" JSON: `{id, operation, result, limitations, coverage …}`. 스크린샷은 `result` 안에 **base64** 로 들어 있다.
- 출력 형식: 앞쪽 `--format json|jsonl|md|text|csv|tsv`.
- `--project` 폴더(`*.cany`)에 증거 · 기록이 쌓인다. 시험마다 scratchpad 안에 둔다.

## 3. 쇼츠용 핵심 기능

### 3.1 실제 웹페이지를 폰 화면으로 찍기 (단계별) — 확인함 (w1 → w1_0.png)
```json
{"actions":[{"kind":"goto","url":"https://example.com","step_id":"open"},{"kind":"wait","ms":800}],
 "environment":{"width":390,"height":693,"device_scale_factor":2,"locale":"ko-KR","color_scheme":"dark"},
 "screenshot_each_step":true,"headless":true,"timeout_secs":60}
```
```sh
craft-anything-cli --deep --allow-run --project $LAB/lab.cany web-walkthrough-record @w1.json > w1.out
python3 -c "import json,base64;d=json.load(open('w1.out'))
for s in d['result']['steps']:
  sc=s.get('screenshot')
  if sc: open('w1_%d.png'%s['index'],'wb').write(base64.b64decode(sc['base64']))"
```
- 결과: 780×1386 PNG(9:16), 다크 모드 적용. 실행 2.8초. 네트워크 요청 목록(`result.network`)도 같이 나온다.
- 주의(확인): 기록(`web-walkthrough-record`)은 단계 배열을 **`actions`** 로 받고, 검사(`web-walkthrough-check`)는 같은 배열을 **`script`** 로 받는다(`{"script":[…]}` → `valid:true`). 브라우저 없이 먼저 검사하고 돌린다.
- 주의(확인): 오른쪽에 **스크롤바**가 찍힌다. 잘라 내거나 페이지가 짧으면 높이를 늘린다.
- **1080×1920 그대로**: `width:360, height:640, device_scale_factor:3` → 1080×1920 PNG (확인, w2.out).
- 단계: goto · click · fill · press · select · wait. 요소는 CSS 선택자 · `test_id` · 역할 + 접근 이름으로 고른다. 클릭 단계마다 PNG 를 받으면 **"이렇게 누르면 됩니다" 튜토리얼 컷**이 된다(클릭 단계는 미확인).
- `environment.reduced_motion` 은 기본 켜짐(애니메이션 없는 안정 화면), `timezone` 기본 UTC.
- 쇼츠 활용: 무료 AI 툴 소개 · 비교(format-compare) · 서비스 사용법 · 공식 문서 페이지 인용.

### 3.2 사이트 한 장 전체 + 디자인 토큰 — 확인함 (MCP, cap1/)
MCP 한 세션에서:
```text
tools/call web_site_open    {"url":"https://example.com","width":390,"height":844}
tools/call web_site_capture {"output_directory":"/절대/새폴더","widths":[390]}
tools/call web_site_close   {}
```
- 결과 폴더: `screenshot-390.png`(390×935 전체 페이지, 1배율) · `page.html` · `capture.json`(글꼴 · 글자 크기 · 색 · 배경 · 모서리 · 간격 · 레이아웃 윤곽 · 제목 · 링크 · 보이는 글자) · `README.md`(요약).
- `output_directory` 는 **아직 없는 폴더**여야 한다. `max_height` 기본 12000px, `widths` 1~4개(320~3840).
- 1배율이라 9:16 화면 재료로는 3.1(배율 지정)이 낫다. 대신 **긴 페이지 스크롤 장면**(위에서 아래로 훑기)과 **그 사이트 색 · 글꼴로 자막 맞추기**에 쓴다.
- `web_page_states_capture {output_directory, max_states:4, width}` : 메뉴 · 탭 · 접힌 부분을 하나씩 열어 찍는다(미확인).
- `web_pixels_compare` : 두 PNG 차이(전/후 비교 장면의 근거, 미확인).

### 3.3 터미널 실행 기록 (실제 실행 로그) — 확인함 (r1)
```json
{"executable":"bash","arguments":["--norc","-i"],"terminal":{"columns":40,"rows":20},
 "events":[{"at_ms":300,"type":"input","data":"echo hello fluma; seq 1 3\n"},
           {"at_ms":900,"type":"input","data":"exit\n"}],"timeout_ms":5000}
```
```sh
craft-anything-cli --deep --allow-run --project $LAB/lab.cany runtime-walkthrough-record @r1.json > r1.out
```
- 결과 `result.terminal.lines`: `["bash-5.3$ echo hello fluma; seq 1 3","hello fluma","1","2","3","bash-5.3$ exit","exit",…]` · `cursor_row` · `columns`/`rows` · `exit`.
- 이벤트 키는 `type` · `at_ms` · `data`(확인). `sensitive:true` 면 기록에서 가린다.
- 터미널 크기를 **세로형(예: 40열 × 30줄)** 으로 주면 9:16 화면에 그대로 옮기기 좋다.
- PNG 는 안 나온다 → 줄 목록을 WordCraft/VectorCraft 의 터미널 카드에 넣어 그린다. 실제 실행 결과라 "실제 로그" 원칙에 맞다.
- `normalization`(pid · 포트 · 경로 가리기)과 `watched-paths`(바뀐 파일 목록)도 있다(미확인).

### 3.4 안드로이드 폰 실제 화면 — 미확인(기기 없음)
```sh
craft-anything-cli adb-devices-find                                   # 확인: 0대
craft-anything-cli --allow-run adb-screenshot-take --output-directory /절대/새폴더   # screen.png
```
- adb 는 설치돼 있다(Android SDK platform-tools 의 `adb`). 폰을 USB 디버깅으로 연결하면 앱 실제 화면을 9:16 그대로 받는다.
- `adb-app-launch` · `adb-activity-open` 은 기기를 바꾸므로 사용자 확인 뒤에만.

### 3.5 Electron · 웹 앱 화면 — 미확인
- `js-electron-walkthrough-record` : Electron 앱(VS Code 류)을 개인 프로필로 띄워 짧은 스크립트를 돌리고 기록.
- `native-window-capture` : 프로그램 창 사진(Windows · macOS 만 — 이 PC(Linux)에서는 안 됨).

## 4. 전체 명령 분류 요약 (315개)

| toolset | 개수 | 대표 명령 |
|---|---|---|
| native | 55 | `native-function-study` · `native-layout-show` · `native-gdb-*` · `native-rizin-*` |
| formats | 36 | `web-recording-show`(HAR) · `packets-capture-show` · `formats-wasm-module-show` · `game-unity-list` · `firmware-regions-list` |
| core | 35 | `core-target-open` · `core-target-triage` · `core-evidence-show` · `core-report-write` · `core-finding-record` |
| projects | 27 | `rebuild-start` · `project-list` · `project-preview` · `project-pin-*` |
| adb | 24 | `adb-devices-find` · `adb-screenshot-take` · `adb-log-read` · `adb-app-launch` |
| browser | 22 | `web-walkthrough-record` · `web-site-open/capture/close` · `web-page-screenshot-take` · `web-page-states-capture` · `web-pixels-compare` |
| application | 17 | `app-feature-follow` · `js-function-explain` · `app-graphs-compare` |
| setup | 16 | `engines-list` · `settings-show/set` · `plugins-*` · `setup-plan/apply` |
| runtime | 14 | `runtime-walkthrough-record` · `runtime-ui-read` · `native-window-capture` |
| apple · android | 14 · 14 | iOS/macOS · APK 분석 |
| javascript | 11 | `js-app-map` · `js-sources-restore` · `js-electron-walkthrough-record` |
| frida · managed · java · build · database | 9 · 8 · 6 · 6 · 1 | 실행 추적, .NET, Java, 빌드 파일, SQLite |

CLI 전용 명령: `triage <파일>`(첫 살펴보기) · `report`(Markdown/HTML 조사 보고서) · `chat`(AI 백엔드 필요) · `rebuild`(코딩 에이전트로 다시 만들기) · `doctor`.

## 5. 파이프라인 연결 제안

1. **research 스킬의 출처 URL → 3.1 로 그 페이지를 폰 화면으로 찍기** → 장면의 "실제 화면" 재료. 출처와 화면이 같은 페이지라 사실 확인도 된다.
2. 툴 비교(format-compare): 툴마다 같은 단계 스크립트(goto → 입력 → 결과 대기)를 돌려 같은 크기 PNG 를 나란히.
3. 기술 설명: 3.3 으로 실제 명령 실행 결과를 받아 터미널 카드로.
4. MCP 로 붙일 때는 `["mcp","--deep","--allow-run","--project","<ROOT>/compositions/<id>/lab.cany"]` 처럼 모드 · 동의를 인자로 줘야 웹 도구가 돈다(craft.json 의 지금 값 `["mcp"]` 로는 clean room 이라 거부된다 — CLI 에서 확인).

## 6. 공식 문서

- 저장소: https://github.com/storytold/craft-anything (README)
- 도구 전체 목록: `docs/tools.md` · 도구 id: `docs/tool-ids.md` · 상태: `docs/tool-status.md` · `docs/STATUS.md`
- 에이전트 연결: `docs/claude-code.md` · `docs/codex.md` · `docs/opencode.md` · 함정: `docs/pitfalls.md`
- 확장: `docs/extending.md` · 입력 형식: `docs/file-formats.md` · 스키마: `docs/schemas/`
