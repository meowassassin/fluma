# TextureCraft 참고 (v0.3.0)

**한 줄 요약**: Substance Painter 류 3D 텍스처 페인팅 앱(순수 Rust, MIT/Apache-2.0, 저장소 `storytold/texturecraft`). 명령 162개를 헤드리스 CLI(`new` · `run` · `batch` · `bake` · `render` · `export`)와 MCP 로 부른다. 쇼츠에서는 **3D 개체에 실제 같은 재질(녹 · 금 · 나무 · 벗겨진 페인트 93종) 입히기 · 한글 로고 데칼 · 붓질이 묻는 과정 · 각도 돌려 찍기(턴테이블) · 경로 추적 렌더** 를 맡는다. 지금 Fluma 는 이 앱을 **전혀 쓰지 않는다**(craft.json `agent:false`, 부르는 곳 없음).

- 실행 파일: `tools/crafts/texturecraft/app/texturecraft-0.3.0-linux-x86_64/bin/texturecraft-cli`
  (에이전트는 `python3 engine/craft/crafts.py run texturecraft <인자…>` 로 부른다)

---

## 0. 지금 Fluma 에서 쓰는 곳 (2026-11-06)

- `engine/craft/adapters/texturecraft.py` — 재료 `model3d` 의 재질 · 로고 · 렌더. OBJ 를 Z 위 → Y 위로 돌리고(x, z, -y) 몸체마다 usemtl, 받침 원판(Stage) 추가 → batch(굽기 → 몸체별 재질 → 로고 데칼 `resource.text` · `resource.import` → `.tcraft`).
- 쉬운 재질 이름(metal · stainless · plastic · gold …)은 무늬 없는 PBR 칠하기로 — 회전체는 자동 UV 가 늘어나 결 무늬가 줄무늬로 깨진다. wood · oak 는 TextureCraft 재질, 나머지는 재질 id 그대로.
- 렌더: 헤드리스 MCP `viewport_render` 한 세션에서 **장당 0.3초**(CLI render 장당 2초). 정지 컷 경로 추적 samples 64. 카메라 거리는 직접 투영 계산(9:16 의 86% 안).
- 실측: 카메라 fov 는 세로 화각(도), 눈 = 대상 + d·(cos p sin y, sin p, cos p cos y). 배경은 불투명(투명 렌더 없음) → model3d 는 9:16 화면 전체 재료. 로고 데칼은 평면 투영이라 둥근 몸체에서 폭 60% 까지, 텍스처 1024.
- mcp 의 `--automation-read-root/--automation-write-root` 는 `--read-root/--write-root` 별칭으로 받는다(헬프 확인).

## 1. 헤드리스로 되는 것 / 안 되는 것

| 구분 | 내용 |
|---|---|
| 된다 (확인) | `new builtin:<id>` 또는 메시 파일(.glb .gltf .fbx .obj .stl .usd* .abc .ply .dae)로 프로젝트 만들기. UV 가 없으면 자동 펼침(“generated an automatic unwrap with 11 charts”) |
| 된다 (확인) | `batch` 한 파일에 열기 → 단계들 → 저장. 메시 맵 굽기(GPU) + 스마트 재질 적용이 1초 안쪽 |
| 된다 (확인) | `render` 540×960 래스터 0.3~1.8초, `--samples 32` GPU 경로 추적 2.3초(이 PC: Intel LNL GPU) |
| 된다 (확인) | `resource.text` (한글 · Noto Sans CJK KR) → `layer.add.decal` 로 표면에 글자 붙이기 |
| 된다 (확인) | `tool.stroke` 로 붓질(뷰포트 픽셀 좌표) |
| 된다 (확인) | `export` 로 엔진용 텍스처 PNG(glTF · Unreal · Unity · Blender · Godot 프리셋 10개) |
| 안 된다 | 앱 화면(레이어 스택 · 셸프 · 2D UV 뷰) 스크린샷은 데스크톱 앱 `texturecraft --control <port>` + `mcp --bridge` 가 필요(미확인) |
| 주의 (확인) | `batch` 는 한 단계라도 실패하면 **저장하지 않는다**. 결과 JSON 의 `failed.index` 로 어느 단계인지 본다 |
| 주의 (확인) | `resource.text` 가 만든 자원 이름은 `name` 그대로가 아니라 **`Text_<name>.png`** 다(`name:"logo"` → `"Text_logo.png"`). 결과의 `name` 을 받아 쓴다 |
| 주의 (확인) | `tool.material` 에 `channel` 을 안 주면 붓질이 칠해지지 않는다. `{"channel":"baseColor","color":"#ef4444"}` |
| 주의 (확인) | SolidCraft OBJ 는 Z 가 위라 TextureCraft(Y 위)에서 옆으로 누운다. 카메라 `pitch` 로 보정하거나 메시를 돌려 내보낸다(돌리는 방법 미확인) |
| 주의 (확인) | 기본 카메라는 9:16 에서 넓은 개체 양옆을 자른다. `camera.set {distance}` 로 물린다 |

## 2. 기본 문법

```sh
texturecraft-cli new <mesh|builtin:id> out.tcraft [--resolution 1024] [--sample]
texturecraft-cli info <project|mesh|builtin:id>                       # 텍스처 세트 · 레이어 · UV 보고 JSON
texturecraft-cli run <input> <command-id> ['{json}'] [-o out.tcraft]   # 명령 하나
texturecraft-cli batch script.json                                    # 여러 단계
texturecraft-cli bake <input> [-o out] [--resolution px] [--maps id,id]
texturecraft-cli render <input> out.png [--size WxH] [--view 3d|2d] [--camera 이름] [--yaw 도] [--pitch 도] [--samples N] [--bounces N] [--cpu]
texturecraft-cli export <input> <dir> [--preset 이름] [--format png|…] [--size px]
texturecraft-cli commands [--filter 글자]                              # 162개, 표 형식 텍스트
```
- `batch` 형식: `{"open": <input>, "steps":[{"id":…,"params":{…}}, …], "save": "out.tcraft"}` (또는 단계 배열만).
- builtin: `material_ball` · `sphere` · `cube` · `rounded_cube` · `cylinder` · `torus` · `plane` · `crate` · `udim_plane`.
- `render --yaw/--pitch` 는 도 단위. `camera.set` 도 도 단위(`{yaw, pitch, distance, fov, target, ortho}`).

## 3. 쇼츠용 핵심 기능

### 3.1 스마트 재질 한 번에 입히기 — 확인함 (b1 → rust.png)
```json
{"open":"builtin:material_ball","steps":[
 {"id":"bake.run","params":{"ts":"all","resolution":512}},
 {"id":"material.apply","params":{"material":"iron_rusted"}},
 {"id":"camera.set","params":{"yaw":30,"pitch":10}}
],"save":"rust.tcraft"}
```
```sh
texturecraft-cli batch b1.json                                   # 1.1초
texturecraft-cli render rust.tcraft rust.png --size 540x960      # 1.4초
texturecraft-cli render rust.tcraft rust_pt.png --size 540x960 --samples 32   # 2.3초, GPU 경로 추적
```
- 결과: 녹슨 쇠 공이 받침대 위에. 경로 추적판은 그림자 · 반사가 더 부드럽다.
- **스마트 재질(`*`)은 메시 맵(곡률 · AO)을 쓰므로 `bake.run` 을 먼저** 한다. 안 구우면 모서리 마모가 안 생긴다(미확인이지만 문서 설명).
- 재질 목록 `material.list`(93개). 스마트 21개: `steel_painted_worn` · `steel_painted_rust` · `military_paint` · `iron_rusted` · `aluminium_scratched` · `copper_patina` · `bronze_statue` · `brass_tarnished` · `gold_dirty` · `chrome_smudged` · `wood_weathered` · `wood_chipped_paint` · `concrete_dirty` · `brick_mossy` · `plastic_dusty` · `plastic_scuffed` · `leather_worn` · `stone_mossy` · `paint_sun_faded` · `steel_water_stained` · `plastic_grimy`.
- 일반 72개: 금속(steel · copper · brass · gold_polished · chrome · titanium …) · 나무(oak · walnut · bamboo …) · 돌(concrete · marble · granite · brick …) · 플라스틱 · 천(denim · leather · velvet …) · glass · ice · car_paint · skin · paper · snow 등.
- 쇼츠 활용: "같은 물건, 재질만 바꾸면?" 비교 컷(재질 이름만 바꿔 여러 장) · 광고의 제품 질감 클로즈업.

### 3.2 한글 로고 · 문구 데칼 — 확인함 (b3 → gold.png)
```json
{"open":"builtin:material_ball","steps":[
 {"id":"bake.run","params":{"ts":"all","resolution":512}},
 {"id":"material.apply","params":{"material":"gold_dirty"}},
 {"id":"camera.set","params":{"yaw":0,"pitch":5}},
 {"id":"resource.text","params":{"text":"플루마","font":"Noto Sans CJK KR","style":"Black","size":256,"color":"#ff3b30","name":"logo"}},
 {"id":"layer.add.decal","params":{"image":"Text_logo.png","viewport":[540,960],"size":0.6}}
],"save":"gold.tcraft"}
```
- 결과: 금 공 표면에 빨간 "플루마" 가 곡면을 따라 붙었다. 위치는 화면 가운데 기준이라 약간 왼쪽으로 치우쳤다 → `x` · `y`(뷰포트 픽셀) 나 `position`/`normal`(월드) 로 맞춘다.
- `size` 는 월드 단위 높이(기본: 메시의 1/4). `rotation` · `depth` 도 있다.
- 이미지 로고는 `resource.import {"path":"/절대/logo.png"}` 뒤 같은 방법(미확인).
- 글꼴 목록: `text.fonts`.

### 3.3 붓질 과정 (칠해지는 장면) — 확인함 (b4 → paint.png)
```json
{"open":"builtin:sphere","steps":[
 {"id":"layer.add.fill","params":{"color":"#e5e7eb","roughness":0.5}},
 {"id":"layer.add.paint","params":{"name":"strokes"}},
 {"id":"tool.paint","params":{}},
 {"id":"tool.material","params":{"channel":"baseColor","color":"#ef4444"}},
 {"id":"tool.brush","params":{"size":40,"hardness":80}},
 {"id":"tool.stroke","params":{"points":[[150,350],[250,450],[350,500],[400,550]],"viewport":[540,960]}}
],"save":"paint.tcraft"}
```
- 결과: 흰 공에 빨간 붓 자국(도장 18개). 기본 해상도가 낮아 붓 가장자리에 점 무늬가 보인다 → `new … --resolution 2048` 이나 `textureSet.resolution` 을 올린다.
- 점 목록을 잘라 여러 번 저장 · 렌더하면 **붓질이 진행되는 프레임**이 된다(미확인).
- 대칭 `symmetryX` · 방사 대칭 `symmetryRadial`, 브러시 모양 `alpha`(67종), 입자 브러시 `particles` 가 있다(미확인).
- UV 좌표로 칠하기: `tool.strokeUv {points:[[u,v]…]}`. 경로 채우기: `tool.path`.

### 3.4 다른 앱의 3D 모형에 재질 입히기 (SolidCraft → TextureCraft) — 확인함 (b2 → box_*.png)
```sh
solidcraft-cli run --in t1.sc --out box.obj                       # SolidCraft 상자 → OBJ
texturecraft-cli info box.obj                                     # 2956 삼각형, UV 자동 펼침
texturecraft-cli batch b2.json      # open box.obj → bake.run(1024) → material.apply wood_chipped_paint → save
for y in 0 60 120; do texturecraft-cli render box.tcraft box_$y.png --size 540x960 --yaw $y --pitch 25; done   # 장당 1.7초
```
- 결과: CAD 상자가 청록 페인트가 벗겨진 나무 상자가 됐다. 세 각도 모두 렌더됨.
- 주의: 축이 달라 상자가 옆으로 누웠다(Z 위 → Y 위). yaw 0 에서는 너비가 화면 밖으로 잘렸다.
- **턴테이블**: `--yaw` 를 0~360 으로 나눠 반복하면 된다(장당 0.3~1.8초).

### 3.5 렌더 · 카메라
- `camera.set {yaw, pitch, distance, fov, target, ortho}` → `camera.add {name}` 로 저장 → `render --camera 이름`(미확인: 저장 카메라 렌더).
- `viewport.view {mode: material|uvChecker|mask|<채널>|map:<메시맵>}` : 재질 대신 **AO · 곡률 · 노멀 맵**을 보여 주는 기술 설명 컷(미확인).
- `render --view 2d` : UV 펼친 텍스처 화면(미확인).
- `viewport.focusAt {x,y}` : 피사계 심도 초점(미확인).

### 3.6 텍스처 내보내기 — 확인함 (gx/)
```sh
texturecraft-cli export gold.tcraft gx --preset "glTF PBR Metal Roughness" --size 512
```
- 결과: 텍스처 세트(Ball · Base)마다 `BaseColor` · `Normal` · `OcclusionRoughnessMetallic` PNG.
- 프리셋 10개: Document channels + Normal + AO · glTF PBR Metal Roughness · Unreal Engine (Packed) · Unity HDRP (Mask Map) · Unity Standard · Blender (Principled BSDF) · Godot 4 (ORM) · OpenPBR · Separate maps · Mesh maps.
- 쇼츠 활용은 적다(“게임 에셋 만드는 법” 기술 설명에서 결과 파일 화면 정도).

## 4. 전체 명령 분류 요약 (162개)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| layer | 26 | `layer.add.paint` · `layer.add.fill` · `layer.add.image` · `layer.add.decal` · `layer.add.group` · 순서 · 혼합 · 불투명도 |
| tool | 19 | `tool.paint` · `tool.brush` · `tool.material` · `tool.stroke` · `tool.strokeUv` · `tool.path` · `tool.fillMode` · 지우개 · 복제 · 번짐 |
| effect | 15 | `effect.add.generator`(edgeWear · dirt · curvature · AO …) · `effect.add.filter`(31종) · `effect.add.levels` · `effect.add.fill` |
| textureSet | 15 | `textureSet.list/inspect` · `textureSet.resolution` · 채널 · UDIM |
| bake | 12 | `bake.run` · `bake.settings` · 하이폴리 · 케이지 |
| viewport · camera | 11 · 8 | `viewport.view` · `viewport.frame` · `camera.set/add/select` |
| file · project · edit | 11 · 5 · 3 | 열기 · 저장 · 실행 취소 |
| mask | 10 | `mask.add.white/black` · `mask.smart.apply`(18종: edge_wear · rust_leaks · scratches · fingerprints · moss_top …) |
| material | 8 | `material.apply` · `material.list` · `material.save/load` · MaterialCraft 연결(`material.link.*`) |
| export · resource | 5 · 4 | `export.plan/presets`, `resource.import` · `resource.text` |
| 기타 | 9 | brush(4) · path(2) · alpha · display · filter · text |

조회 명령: `material.list` · `mask.smart.list` · `filter.list` · `export.presets` · `text.fonts` · `textureSet.list` · `camera.list`.

## 5. 파이프라인 연결 제안

1. 3D 개체가 필요한 장면: SolidCraft(형태) → OBJ → TextureCraft(질감 · 로고) → `render` 9:16 → EffectCraft 레이어.
2. 간단한 소품은 builtin(`crate` · `rounded_cube` · `cylinder`)에 재질만 입혀도 된다.
3. 재질 비교 컷은 같은 프로젝트에서 `material.apply` 만 바꿔 여러 번 batch.
4. 무거운 시험은 피한다: 해상도 2048 이상 굽기 · `--samples` 128 이상은 시간이 늘어난다(이번 시험 최대 2.3초라 여유는 있음).

## 6. 공식 문서

- 저장소: https://github.com/storytold/texturecraft (README)
- 홈페이지: https://getartcraft.com/apps/texturecraft
- 기능 전체: `docs/features.md` · 앱 제어 · `serve` 프로토콜: `docs/control-protocol.md` · 구조: `docs/architecture.md` · 다른 앱과 비교: `docs/parity.md`
