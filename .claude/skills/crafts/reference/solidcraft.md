# SolidCraft 참고 (v0.30.1)

**한 줄 요약**: Fusion/SolidWorks 류 파라메트릭 3D CAD(순수 Rust, MIT/Apache-2.0, 저장소 `tangency-labs/solidcraft`). 명령 570개를 전부 헤드리스 CLI(`run` · `snapshot` · `render` · `exec`)와 MCP 로 부를 수 있다. 쇼츠에서는 **제품 · 부품 3D 화면(스케치 → 돌출 → 모깎기가 쌓이는 과정) · 분해도 애니메이션 PNG 프레임 · 한글 각인 · 단면 보기 · 실사풍 제품 렌더** 를 맡는다. 지금 Fluma 는 이 앱을 **전혀 쓰지 않는다**(craft.json `agent:false`, 스크립트 · 스킬에서 부르는 곳 없음).

- 실행 파일: `tools/crafts/solidcraft/app/solidcraft-0.30.1-linux-x86_64/bin/solidcraft-cli`
  (에이전트는 `python3 engine/craft/crafts.py run solidcraft <인자…>` 로 부른다. 직접 경로를 부르면 승인에 걸린다)

---

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `engine/craft/adapters/solidcraft.py` — 재료 `model3d` 의 형태 · 분해도(재질 · 렌더는 texturecraft.py). 내장 형태 5종(case · phone · bottle · tumbler · puck, size mm) · 에이전트 명령 목록(`commands`) · `src`(STEP · IGES → `file.insert_step`, OBJ · STL · 3MF · glTF → `file.insert_mesh`).
- `.sc` 편집 파일을 남기고 OBJ 는 `file.export quality "fine"`(standard 는 둥근 테두리에 톱니). 사람이 고친 `.sc` 는 해시로 알아보고 원본으로 쓴다.
- 분해도: `component.from_bodies` + `explode.create` → `motion.export_animation` 프레임 → mp4(가장 벌어진 프레임이 poster). 헤드리스 렌더러라 재질 · 로고 없이 밝은 회색 배경 — 정지 컷 · turntable(어두운 스튜디오)과 톤이 다르다.
- 도면용: `file.export_view_dxf` 를 먼 거리 + 좁은 화각(fov 0.002)으로 부르면 거의 정투영(cadcraft.py 가 씀).
- 실측: SolidCraft yaw 는 TextureCraft yaw 와 부호가 반대. `appearance.assign pbr` 은 metallic · roughness · dielectric_ior 셋 다 필요. 같은 이름의 `explode.create` 를 두 번 만들면 움직이지 않는 분해도가 된다.
- craft.json mcp 줄의 `--automation-read-root/--automation-write-root` 는 SolidCraft mcp 정식 옵션이 아니다(에이전트 MCP 를 켤 때 확인).

## 1. 헤드리스로 되는 것 / 안 되는 것

| 구분 | 내용 |
|---|---|
| 된다 (확인) | `run` 스크립트 → `.sc` 저장 · STEP/STL/OBJ/3MF/glTF 내보내기. 0.1초 안쪽 |
| 된다 (확인) | `snapshot` 으로 GPU 뷰포트 PNG(1080×1920 도 0.9초). `--view iso` · `--camera` · `--no-grid` · `--no-axes` · `--body` 투명도 · `--section` 단면 |
| 된다 (확인) | `render` 로 제품 렌더 PNG. 기본(preview)은 0.3~0.7초, `--progressive --samples 32` 는 540×960 에 약 40초(CPU) |
| 된다 (확인) | `motion.export_animation` 으로 분해도 · 관절 · 모션 스터디를 PNG 프레임 폴더나 GIF 로 (21프레임 540×960 이 1.4초) |
| 된다 (확인) | `sketch.text` 에 `font:"Noto Sans CJK KR"` 로 한글 각인 · 양각 |
| 안 된다 | 앱 화면(리본 · 타임라인 · 브라우저 패널) 그대로의 스크린샷은 데스크톱 앱 + `mcp --connect` 브리지가 필요하다. 헤드리스 snapshot 에는 3D 뷰만 나온다 |
| 주의 (확인) | 기본 글꼴(Liberation Sans)에는 굵은 면이 없어 `bold:true` 를 주면 오류가 난다. 설치 글꼴 이름을 같이 준다 |
| 주의 (확인) | `--view iso` 를 9:16 에 쓰면 모델이 화면 밖으로 잘린다. 세로 화면에서는 `--camera` 의 `distance` 로 직접 맞춘다(아래 3.2) |
| 주의 (확인) | `sketch.create` 의 `plane` 을 `{origin}` 으로 주면 `x_dir` · `y_dir` 도 같이 줘야 한다 |
| 주의 | craft.json 의 MCP 인자 `--automation-read-root/--automation-write-root` 는 SolidCraft `mcp` 의 정식 옵션이 아니다. 시작은 되지만 파일 접근 범위에 반영되지 않는다(시작 로그에 recovery · 임시 폴더만 나옴). `data/compositions/` 에 저장하려면 문서상 `--allow-path <ROOT>/compositions` 를 써야 한다(무시되는 것은 시작 로그로 확인, `--allow-path` 동작은 미확인) |

## 2. 기본 문법

```sh
solidcraft-cli run script.json [--in base.sc] --save out.sc --out out.step [--results]
solidcraft-cli snapshot <script|design> [--in base.sc] --out shot.png --width 1080 --height 1920 \
    [--view iso|front|top|… | --camera '{"target":[x,y,z],"yaw":r,"pitch":r,"distance":mm,"fov":r}'] \
    [--no-grid] [--no-axes] [--body Body1:opacity=0.3,color=#rrggbb] [--section z=15]
solidcraft-cli render <design.sc|script> --out img.png [--setup 이름] [--width W --height H] [--transparent] \
    [--progressive --samples N] [--exposure EV] [--tone-map aces_fitted]
solidcraft-cli exec <command> '<json>'      # 명령 하나(조회용)
solidcraft-cli commands                     # 명령 570개 JSON(약 330KB) — python 으로 걸러 본다
```
- 스크립트 형식: `{"commands":[{"command":ID,"params":{...}}, …]}`. 단위는 mm, 각도는 라디안(카메라) · 도(스케치).
- 값에 식을 쓸 수 있다: `parameters.add {"name":"W","value":"80 mm"}` 뒤 `"p1":["W",50]`. 파라미터 하나 바꿔 다시 찍으면 같은 모형의 변형이 나온다.
- 실패한 단계가 있으면 아무것도 쓰지 않고 `error: step N (id): …` 를 낸다. `--allow-errors` 는 그래도 쓴다. `--param-check warn|strict` 로 키 오타를 잡는다.
- `--in` 과 스크립트를 같이 주면 기존 설계 위에 스크립트를 더 돌린다(분해 애니메이션 · 렌더 설정을 나중에 얹을 때 쓴다).

## 3. 쇼츠용 핵심 기능

### 3.1 제품 모형 만들기 (스케치 → 돌출 → 껍데기 → 색) — 확인함 (t1)
```json
{"commands":[
 {"command":"parameters.add","params":{"name":"W","value":"80 mm"}},
 {"command":"sketch.create","params":{"plane":"XY"}},
 {"command":"sketch.rectangle.rounded","params":{"p0":[0,0],"p1":["W",50],"radius":8}},
 {"command":"solid.extrude","params":{"distance":30}},
 {"command":"solid.shell","params":{"faces":[[40,25,30]],"thickness":2}},
 {"command":"appearance.assign","params":{"bodies":["Body1"],"color":"#3b82f6"}}
]}
```
- 시험 결과: `run` 0.07초, `snapshot` 1080×1920 0.9초. 둥근 상자 그릇이 파란색으로 나왔다.
- 면 · 모서리는 **그 위의 점 좌표**로 고른다(`faces:[[40,25,30]]` = 윗면). 이름보다 안정적이다.
- 쇼츠 활용: "3D 프린터로 ○○ 만들기" · "제품 구조 설명" 장면. 단계마다 `snapshot` 을 찍으면(스크립트를 앞에서부터 1, 2, … 단계까지 자른 것) **모형이 쌓이는 과정** 프레임이 된다(미확인: 단계별 자르기는 해 보지 않음. 단일 스크립트 snapshot 은 확인).

### 3.2 세로 화면 카메라 — 확인함 (t1b · frames2 · t5)
```sh
solidcraft-cli snapshot t1.json --out a.png --width 1080 --height 1920 --no-grid --no-axes \
  --camera '{"target":[40,25,15],"yaw":0.8,"pitch":0.5,"distance":320}'
```
- `distance` 는 모델 크기의 약 3~4배(80mm 상자 → 250~320). 너무 크면 작게 나온다(420 이면 화면의 1/4).
- `yaw` 를 0 → 2π 로 바꿔 여러 장 찍으면 **턴테이블** 이 된다(장당 0.2~0.9초. 연속 촬영은 미확인이지만 단일 촬영은 확인).
- 렌더(`render`)는 `--camera` 를 받지 않는다. 렌더 설정에 카메라를 저장하고 `--setup` 으로 부른다:
```json
{"commands":[{"command":"render.settings.set","params":{"name":"tall","set":{
  "camera":{"target":[40,25,20],"yaw":0.7,"pitch":0.45,"distance":380,"fov":0.6},"width":540,"height":960}}}]}
```
```sh
solidcraft-cli run t5.json --in t2.sc --save t5.sc
solidcraft-cli render t5.sc --setup tall --out t5r.png     # 0.7초
```
- `render` 에 `--in` 은 없다(오류 `unknown render option: --in`). 설정을 넣은 `.sc` 를 먼저 저장한다.

### 3.3 분해도 애니메이션 (뚜껑이 열리는 장면) — 확인함 (t2 · t3)
```json
// t2: 몸통 + 뚜껑 + 한글 양각 → 부품 두 개 → 분해도 "open"
{"command":"sketch.create","params":{"plane":{"origin":[0,0,30],"x_dir":[1,0,0],"y_dir":[0,1,0]}}},
{"command":"sketch.rectangle.rounded","params":{"p0":[0,0],"p1":[80,50],"radius":8}},
{"command":"solid.extrude","params":{"distance":4,"operation":"new_body"}},
{"command":"sketch.create","params":{"plane":{"origin":[0,0,34],"x_dir":[1,0,0],"y_dir":[0,1,0]}}},
{"command":"sketch.text","params":{"text":"플루마","at":[40,20],"height":10,"align":"center","font":"Noto Sans CJK KR","bold":true}},
{"command":"solid.extrude","params":{"distance":1.5,"operation":"join"}},
{"command":"appearance.assign","params":{"bodies":["Body2"],"color":"#f97316"}},
{"command":"component.from_bodies","params":{"bodies":["Body1","Body2"]}},
{"command":"explode.create","params":{"name":"open","moves":[{"occurrence":"Body2","translate":[0,0,40]}]}}
```
```json
// t3: --in t2.sc 위에서 프레임 뽑기
{"commands":[{"command":"motion.export_animation","params":{"view":"open","back":true,"samples":21,
  "path":"/절대/경로/frames","width":540,"height":960,"fps":20,"grid":false,"axes":false,
  "camera":{"target":[40,25,40],"yaw":0.7,"pitch":0.45,"distance":300}}}]}
```
- 시험 결과: `frames/frame-0001.png … frame-0021.png` 21장을 1.4초에. `back:true` 면 열렸다가 다시 닫힌다.
- `path` 는 `.gif` 파일이거나 **이미 있는 폴더**여야 한다(아니면 오류).
- 결과 프레임은 EffectCraft/FilmCraft 에 이미지 시퀀스로 넘긴다(넘기는 방법은 그쪽 참고 문서).
- 같은 명령으로 `joint` + `from`/`to` 를 주면 관절 회전, `study` 를 주면 모션 스터디가 된다(미확인: 조인트 만들기는 해 보지 않음).

### 3.4 단면 · 투명 보기 (속 구조 설명) — 부분 확인
- `snapshot … --section z=15` : 모델을 z=15 평면으로 잘라 속을 보인다. `XY` · `XZ` · `YZ` 나 `,flip` 도 된다(미확인: 옵션 목록만 확인).
- `snapshot … --body Body1:opacity=0.3` : 바깥 껍데기를 반투명하게(미확인).
- `--tool 이름` : 그 부품만 진하게, 나머지는 투명하게(미확인).
- 쇼츠 활용: "이 안에 뭐가 들었나" · "나사가 어디 들어가나" 기술 설명.

### 3.5 재질 · 외관 — 확인함(색) / 미확인(라이브러리)
- `appearance.assign {"bodies":[…],"color":"#rrggbb","pbr":{"metallic":0.9,"roughness":0.3}}` — 색은 확인.
- `appearance.library` (조회 확인): 시작 레시피 40개(`starter.wood.oak-honey` · `starter.metal.brass-champagne` · `starter.plastic.pla-coral` · `starter.glass.smoky-neutral` …) + 옛 외관 20개. `appearance` 에 ID 를 넣는다(렌더 결과는 미확인).
- 스튜디오 조명 프리셋: `render.preset.apply {"id":"NATIVE-STUDIO-001"…}` (001~025, `expected_revision` 필요 — 미확인).
- 더 사실적인 표면(녹 · 때 · 페인트 벗겨짐)은 **TextureCraft** 로 넘긴다: `run --in t1.sc --out box.obj` → texturecraft (texturecraft.md 3.4, 확인함).

### 3.6 렌더 품질 단계 — 확인함 (t1r0 · t1r)
| 방식 | 명령 | 540×960 시간 | 모습 |
|---|---|---|---|
| snapshot | `snapshot` | 0.2초 | 모서리 선 · 그라데이션 바닥. CAD 화면 느낌 |
| render 기본 | `render x.sc --out` | 0.3초 | 선 없이 매끈한 음영 |
| render 점진 | `--progressive --samples 32` | 약 40초(CPU) | 반사 · 그림자. 제품 광고 컷 |
- `--samples` 는 `--progressive` 없이 쓰면 오류(`sampling controls require progressive rendering`).
- `--transparent` 로 배경을 빼면 다른 레이어 위에 얹을 수 있다(미확인).
- GPU 정책: `solidcraft-cli gpu` 로 어댑터를 본다. 이 PC 는 snapshot 이 `renderer:"gpu"` 였다.

### 3.7 모형 수치 (정보 쇼츠의 근거) — 확인함
- `run … --results` 마지막 결과와 `eval` 에 부피(`volume_mm3`) · 질량 · 무게중심 · 경계 상자가 나온다. t5 에서 `volume_mm3: 37425.6` 확인.
- `material.assign {"bodies":[…],"material":"ABS Plastic"}` 뒤 질량을 읽으면 "이 케이스는 ○○g" 같은 자막의 근거가 된다(질량 값은 미확인).

## 4. 전체 명령 분류 요약 (570개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| sketch | 126 | `sketch.create` · `sketch.rectangle.rounded` · `sketch.circle.center` · `sketch.text` · `sketch.dimension` · `sketch.constraint.*` |
| render | 60 | `render.settings.set` · `render.camera.set/fit` · `render.preset.apply` · `render.library.*` · `render.start/status/export` |
| view | 40 | `view.apply` · `view.save` · `view.visual_style` · `view.render_frame`(9:16 안내선) · `view.perspective` |
| solid | 36 | `solid.extrude` · `revolve` · `sweep` · `loft` · `fillet` · `chamfer` · `shell` · `hole` · `pattern` · `combine` |
| component | 32 | `component.create` · `component.from_bodies` · `component.insert_design` |
| timeline | 22 | 기능 기록 되감기 · 편집 |
| construct · surface | 20 · 19 | 기준면 · 축, 곡면 |
| inspect | 19 | `inspect.section` · 간섭 · 측정 |
| joint · motion · explode · contact | 18 · 11 · 4 · 7 | 조립 관절, `motion.study` · `motion.export_animation`, `explode.create/show` |
| file | 16 | `file.export`(stl/obj/step/3mf/urdf) · `file.insert_step` · `file.insert_mesh` · `file.export_view_dxf` |
| sheet · plastic | 13 · 7 | 판금(플랜지 · 펼치기), 플라스틱 케이스 기능 |
| parameters · config | 13 · 8 | 파라미터 · 설정표(같은 모형의 크기 변형) |
| appearance · material | 10 · 8 | 색 · PBR · 재질 · 밀도 |
| 기타 | 약 60 | settings · browser · canvas · document · edit · pointcloud · frame · parts · select · diagnostics · library … |

조회 명령: `appearance.library` · `material.list` · `render.library.list {kind}` · `view.list` · `motion.list` · `explode.list` · `render.backends`.

## 5. 파이프라인 연결 제안

1. **에이전트가 스크립트 JSON 을 쓴다**(좌표가 아니라 치수 · 파라미터로) → `run` 으로 검증 → `snapshot` 으로 보고 고친다.
2. 장면 재료: `snapshot`(CAD 화면) · `render`(제품 컷) · `motion.export_animation`(분해 프레임) · 턴테이블(yaw 여러 장).
3. 표면을 더 입히려면 OBJ 로 내보내 TextureCraft 로(축 방향 주의: SolidCraft 는 Z 위, TextureCraft 는 Y 위라 상자가 옆으로 눕는다 — 확인함).
4. 도면이 필요하면 `file.export_view_dxf` → CADCraft 로 PNG(미확인).

## 6. 공식 문서

- 저장소: https://github.com/tangency-labs/solidcraft (README · `docs/`)
- 홈페이지 · 문서: https://solidcraft.io · https://docs.solidcraft.io/ · 브라우저판 https://solidcraft.io/app
- 스크립트: `docs/scripts.md` · MCP: `docs/mcp.md`(파일 접근 범위 · `--allow-path` · 렌더 잡) · 기능 목록: `docs/features.md` · `docs/capabilities.md`
- 렌더: `docs/render-jobs.md` · `docs/render-settings.md` · `docs/render-shot-scene.md` · `docs/render-studio-lighting.md`
- 예제 모음: `docs/showcase.md`
