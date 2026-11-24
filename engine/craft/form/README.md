# 형태(form) 작성법

형태는 **데이터로 빚는다** — 기본 도형을 놓고 녹여 붙이거나(smooth_union) 깎아 낸다(subtract). 화풍(flat · cel · sketch · clay · vector · render)은 형태와 따로, 재료 `style` 또는 영상 아트 디렉션(`direction.art.style`)이 정한다. 영상마다 새로 빚는다(부품을 쌓아 두지 않는다).

## 좌표
y 가 위, 바닥은 y = 0, 정면은 +z. 단위는 대략 "물체 높이 ≈ 1". 카메라는 자동으로 맞춘다.

## 형식
```json
{"materials": {"body": {"color": "#ffcf2e", "gloss": 0.45, "spec_power": 40, "shadow": "#f08a1c"}},
 "camera": {"azimuth": 35, "elevation": 20, "fov": 30, "frame": 1.5},
 "root": {"op": "smooth_union", "k": 0.05, "children": [ … ]}}
```
- 재질: `color` · `gloss`(0~1, 광택) · `spec_power`(하이라이트 날카로움) · `shadow`(그림자 색 — 카툰 · 플랫에서 쓰임, 없으면 자동)
- 도형(`prim`) — 모두 `pos` · `rot`(도) · `scale` · `mat` · `round`(부풀림) · `shell`(속 비움) · `mirror_x`(좌우 대칭 복사)
  - `sphere` r · `ellipsoid` radii[3] · `capsule` h(반 높이) r(세로) · `roundbox` size[3](반 크기) r · `roundcone` r1 r2 h · `torus` R r(xz 평면) · `cylinder` h r r_edge · `halfspace`(y<0 쪽)
- 연산(`op`) — `union` · `smooth_union`(k = 녹여 붙이는 반경) · `subtract`(첫째에서 나머지를 뺌) · `smooth_subtract` · `intersect` · `smooth_intersect`. `cut_mat: true` 면 깎인 면이 깎은 도형의 재질. 연산에도 pos · rot · scale 을 줄 수 있다(묶음 전체).

## 빚는 순서
1. 큰 덩어리(몸통) → 붙는 덩어리(머리 · 손잡이)를 `smooth_union` 으로(이음매 없이) → 작은 부품(눈 · 부리)은 `union`.
2. `python3 engine/craft/form_cli.py preview <형태.json>` — 540 크기로 약 1~2초. Read 로 보고 비례 · 위치를 고친다(2~3번).
3. `python3 engine/craft/form_cli.py styles <형태.json>` — 화풍을 한 장으로 비교(필요할 때만). 한 장만 크게: `form_cli.py render <형태.json> --out <파일.png> --style <화풍> [--bg "#hex"] [--res 1080]`.
4. 콘티: `{"type": "form", "scene": "$FILE:data/compositions/<id>/forms/<이름>.json", "view": {"azimuth": 30}}` — 장면마다 각도만 바꿔 같은 형태를 다시 쓴다.

예: `examples/duck.json`(고무 오리) · `examples/mug.json`(머그). 그대로 복사하지 말고 비례 · 재질 쓰는 법만 본다.
사람도 빚을 수 있다(2026-11-20 사용자 결정) — 재료에 `"person": true` 를 적는다. 실존 인물을 닮게 빚지 않는다(이름 · 얼굴 특징 · 상징물로 특정인을 떠올리게 하지 않는다).

## 뼈대로 빚기 — 사람 · 네 발 동물 (2026-11-20)
부품을 하나씩 좌표로 놓으면 발이 다리에서 떨어지고, 자세가 차렷으로 굳고, 얼굴이 머리를 따라 돌지 않는다. 사람 · 동물은 뼈대 노드로 빚는다 — 부품은 관절에 붙어 떨어질 수 없고, 자세는 관절 각도로 정한다.
```json
{"rig": "humanoid", "size": {"height": 1.7, "head": 0.14}, "pose": {"head": [8, 20, -6], "r_arm": [-10, 150, 0], "r_elbow": 30, "l_knee": 20},
 "mats": {"skin": "skin", "hair": "hair", "top": "shirt", "bottom": "pants", "shoe": "shoe", "eye": "eye", "mouth": "mouth"},
 "wear": {"sleeve": 0.3, "pants": 1.0, "hair": 0.4}}
{"rig": "quadruped", "size": {"height": 0.3, "body": 1.45, "head": 0.52}, "pose": {"neck": [15, 25], "tail": [60, 15, 80], "fl": [35, 0], "fl_knee": 40},
 "mats": {"fur": "fur", "nose": "nose", "eye": "eye"}}
```
- 비율(`size`)은 키에 대한 비 — 기본값은 engine/craft/form/skeleton.py 의 `DEFAULT` · `QUAD`. 그림체에 맞게 영상마다 정한다(정해진 표 없음).
- 자세(`pose`)는 도(°), 모든 관절에서 + 가 앞(숙이기 · 고개 숙이기 · 팔다리 앞으로 — 2026-11-21 등뼈 · 고개 부호를 바로잡음): 사람 `lean` · `spine`[앞, 옆, 비틀기](허리 40% · 가슴 60% 로 나눠 휜다) · `weight`(−1~1, 체중을 싣는 다리 — 기본 0.45, 0 이면 차렷) · `head`[끄덕, 돌리기, 갸웃] · `l_arm`/`r_arm`[앞, 벌리기, 비틀기] · `l_elbow` · `l_leg`/`r_leg`[앞, 벌리기] · `l_knee`, 동물 `spine` · `neck` · `head` · `tail`[들기, 옆, 말기] · `fl` `fr` `bl` `br`[앞, 벌리기] · `*_knee`.
- 발은 늘 바닥(y = 0)에 닿는다. 얼굴(눈 · 입 · 코 · 귀)과 머리카락은 머리 뼈에, 옷(소매 · 바지)은 팔다리 뼈에 붙는다.
- `form_cli preview` 가 몸과 떨어진 덩어리를 세어 알린다(△ 떨어진 덩어리 N개).
- 새: `{"rig": "bird", "pose": {"tilt", "neck": [굽힘, 돌리기], "head", "wings": [날갯짓, 펼침], "tail": [들기, 부채 0~1], "l_leg": [앞], "l_knee"}, "mats": {"body", "belly", "wing", "tail", "beak", "leg", "eye"}}`
- 사람 표정 `face`: `smile`(−1 찡그림 … 1 웃음) · `open`(입 벌림 0~1) · `brow`(1 화남 · −1 걱정) · `brow_y`(눈썹 높이) · `eyelid`(0 뜸 … 1 감음) · `blush`(mats 에 `blush` 재질이 있을 때) · `look`[x, y](눈동자)
- 머리 모양 `hair`: `top`(윗머리 볼륨) · `bangs`(앞머리) · `side`(옆머리) · `back`(뒷머리 길이) · `tail`(포니테일) · `bun`(올림머리) · `spikes`(뻗친 다발 수) · `part`(가르마 −1~1)
- 손: `"hands": "mitten"`(손바닥 + 엄지, 기본) · `"fingers"`(다섯 손가락) — 자세 `l_grip`/`r_grip`(0 펴기 … 1 주먹) · `l_spread`/`r_spread`(벌림 °)
- 클로즈업: 카메라 `"focus": [x, y, z], "radius": r` — 그 점을 가운데에 반지름만큼만(얼굴 · 손). 머리 위치는 `skeleton.joints(size, pose)["head"]`
- 움직임: `anim.tracks` 에서 뼈대 안쪽 값을 점 경로로 — `{"hero": {"pose.r_elbow": [[0, 15], [0.5, 70]], "face.eyelid": [[0.7, 0], [0.8, 1], [0.9, 0]]}}`(노드 `"name": "hero"`)

## 캐릭터는 움직인다 (2026-11-20 — 정지 그림 한 장으로 쓰지 않는다)
부품에 `name` 을 붙이고 `anim` 에 시간별 값을 적으면 프레임 묶음으로 그려 장면에서 반복 재생한다(12fps · 1~2초 · 약 13초/18장).
- 관절은 **이름 붙은 그룹**으로: `{"name": "tail", "op": "union", "pos": [붙는 자리], "rot": [0,0,0], "children": [그 자리 기준으로 놓은 도형]}` — 그룹의 `rot` 이 붙는 자리를 축으로 돈다. 몸 전체를 들썩이려면 전체를 그룹 하나(`"name": "all"`)로 감싼다.
- `"anim": {"dur": 1.5, "tracks": {"tail": {"rot": [[0, [0,0,-15]], [0.75, [0,0,25]]]}, "eyes": {"radii": [[0, [0.034,0.042,0.02]], [0.6, …같음], [0.7, [0.036,0.006,0.02]], [0.8, …같음]]}, "all": {"pos": [[0,[0,0,0]], [0.375,[0,0.03,0]]]}}}`
  키는 `[초, 값]` — 그 칸(pos · rot · scale · radii · r · h …)의 **값 그대로**, 사이는 부드럽게, 마지막 뒤는 처음으로 돌아가 반복. 눈 깜빡임은 radii 세로를 0.1초 줄였다 펴기.
- 비율 · 표정 · 동작은 정해진 표가 없다 — 사용자 요청 · 레퍼런스 · 아트 디렉션의 느낌을 보고 영상마다 정한다.
- 그리기: `python3 engine/craft/form_cli.py anim <형태.json> --out-dir data/compositions/<id>/forms/<이름>.anim` → `…/f000.png` 와 확인 시트. 장면 코드에서 `K.image('…/f000.png', x, y, 배율)` 이면 반복 재생된다. 콘티 재료(type form)에 anim 이 있으면 엔진이 알아서 묶음으로 그린다.

## 캐릭터가 세상에서 움직인다 — 걷기 · 뛰기 · 계단 · 소품 (2026-11-20)
캐릭터만 서 있지 않는다. 같은 형태 장면에 바닥 · 계단 · 경사로 · 탈것 같은 형태를 함께 놓고, 뼈대 노드에 이동 · 소품을 적는다(engine/craft/form/world.py).
동작을 하나씩 만들지 않는다 — 지형 높이 재기 · 걸음새 계산 · IK · 소품 붙이기의 조합이다.
```json
{"rig": "humanoid", "name": "hero",
 "move": {"path": [[0, -1.2], [0, 1.0], [0, 3.6]], "speed": 1.0, "gait": "walk"},
 "hold": {"r": {"prop": {…캐리어 형태…}, "grip": [0, 0.91, 0], "mode": "drag", "ground": [0, 0, 0]}}}
```
- `move`: 경로(x, z 점들) · `speed`(m/s) · `gait` walk | run — 보폭 `stride` · 들썩임 `bob` · 팔 흔들기 `arm_swing` · 팔꿈치 `elbow` · 기울기 `lean` · 발 들기 `swing_h` 로 걸음새를 바꾼다(지친 걸음 · 신난 뜀 …). `t0` 시작 초. 경로 끝에서 멈춘다.
- 발은 같은 장면 형태의 윗면을 디딘다(계단이면 단마다). 골반 높이 · 팔 흔들기는 걸음에 맞춰 계산된다.
- 서 있을 때는 `"at": [x, z], "facing": 도` — 그 자리 지형 위에 선다. `"ik": {"r_hand": [x, y, z]}`(세상 좌표)로 손 · 발을 물건에 댄다(문고리 · 손잡이 · 난간).
- `hold`: 아무 형태를 손에 — `grip` 은 그 형태에서 손이 쥐는 점. `carry` 는 손을 따라, `drag` 는 쥔 점은 손 · `ground` 점은 지면에 닿게 기울인다(캐리어 · 수레).
- 관절은 사람 가동 범위 안에서만 움직인다(`skeleton.LIMITS` — 무릎 · 팔꿈치 0~150° 등).
- 카메라: 기본은 세상에 고정(처음 · 가운데 · 끝 자세가 모두 들어오게). `"anim": {"camera": "follow", "radius": 0.8}` 이면 움직이는 캐릭터를 따라간다(키 × radius). `anim.tracks.camera` 로 카메라 값(azimuth · focus …)을 직접 움직일 수도 있다.
- 장면 전체가 하나의 움직이는 그림(12fps 프레임 묶음)이 된다 — 400px 기준 한 장 약 0.5~1.5초.

## 연출 — 시선 · 카메라 (2026-11-20)
연출을 장면마다 만들지 않는다 — 시선과 카메라를 값으로 움직인다.
- 시선 `look`: `"camera"`(시청자) · `"이름.관절"`(다른 캐릭터의 `head` · `l_hand` …) · `[x, y, z]`. 고개(±80) → 남는 만큼 상체 비틀기(±40) → 눈동자 순으로 돈다. `look_w`(0~1)로 정도 — 움직이면 천천히 돌아본다.
- 카메라 초점: `"focus": "hero.head"` 처럼 관절 이름 — 프레임마다 그 관절 위치. `"focus_to"` + `"focus_mix"`(0~1)로 두 초점 사이를 옮긴다(몸 → 얼굴). `radius`(작을수록 가깝게) · `azimuth` · `elevation` 도 `anim.tracks.camera` 로 움직인다.
- 예: 돌아보며 다가가기 — `"look": "camera"`, tracks `{"hero": {"look_w": [[0.6, 0], [1.2, 1]]}, "camera": {"focus_mix": [[0.9, 0], [1.8, 1]], "radius": [[0.9, 1.0], [1.8, 0.2]]}}`. 같은 장치로 따라가기 · 밀기 · 훑기 · 두 인물 사이 시선 옮기기를 짠다.
- 반복 재생이므로 마지막에 멈춘 값을 유지하려면 끝 시각에도 같은 키를 둔다.

## 벡터 마감 — 화풍 `vector` (2026-11-20)
렌더가 아는 부위 영역(재질) · 그림자 경계를 매끈한 베지어 경로로 바꿔 VectorCraft 로 다시 그린다(면 · 그림자 면 · 부위 경계 가는 선 · 실루엣 굵은 선, engine/craft/form/vector.py). 래스터 렌더의 거친 가장자리 대신 벡터 일러스트로 마감되고, 같은 이름의 `.vectorcraft` 편집 파일이 남는다. 재료 `"style": "vector"`, 움직임 프레임에도 쓴다(장당 마감 약 0.1~0.3초).

## 바닥은 그리지 않는다 — `"floor": true` (2026-11-20)
받침판 · 원판 무대(얇은 상자 바닥)는 화면 가장자리에서 직선으로 잘리고, 모든 장면을 같은 디오라마로 만든다(AI 티). 바닥 형태에 `"floor": true` 를 주면 발이 딛는 높이 · 그림자에만 쓰이고 그려지지 않는다 — 그림자만 장면 바탕 위에 떨어진다. 계단 · 단상처럼 보여야 하는 지형은 그대로 두되 화면 안에서 닫는다. 미리보기 · anim 은 형태가 가장자리에서 잘리면 △ 로 알린다.

## 사람 그림 구조 (2026-11-21)
- 관절 이음: 부위 묶음을 관절 둘레에서만 녹여 붙인다(`joint_union` — at · reach · k). 어깨 · 엉덩이는 매끈하고, 두 허벅지 · 팔과 옆구리 · 손가락은 녹지 않는다.
- 이목구비는 3D 형태가 아니라 얼굴 위 '획'(눈: 흰자 → 홍채 · 동공 → 반사점 → 눈꺼풀, 눈썹 붓 획, 끝이 가는 입선) — 렌더 뒤 화면에 투영해 그리고 가려지면 지운다. 벡터 마감도 같은 획.
- 피부는 부위 크기만큼 뭉갠 둥근 면으로 명암(남의 그림자 안 받음), 머리카락은 다발 + 하이라이트 띠 획.
- 서 있으면 체중을 한 다리에 싣고(weight), 이동 · 카메라가 있는 움직임은 24fps.

## 주기 움직임 · 날기 · 전환 운반자 (2026-11-21)
- 트랙 값에 `{"osc": [기준, 진폭, 횟수/초, 위상]}` — 날갯짓 · 꼬리 흔들기 · 숨쉬기처럼 빠르게 되풀이되는 움직임(값이 목록이면 칸마다). 반복 길이(dur)×횟수가 정수면 이음매 없이 돈다.
- 공중에 뜬 것은 장면에 `"ground": false`(땅 그림자 없음).
- 이런 형태 anim 을 콘티 장면의 `carry`(감독 스킬 다섯 기둥 · 모티프)로 쓰면 다음 장면으로 날아가며 화면을 바꾼다(engine/craft/motion.py carry_jsx).

## 3D 렌더 화풍 — `render` (2026-11-23)
그림 화풍 대신 재질 · 주변 빛으로 3D 렌더처럼 그린다. 형태 · 뼈대 · 움직임은 그대로 쓰고, 재질과 장면 칸만 더한다.
- 재질 `kind`: `plastic`(기본) · `metal` · `liquid` · `glass` · `fuzz`(털 · 솜) · `wood` · `matte`. `rough`(0 매끈 … 1 거침, 없으면 1 − gloss) · `bump`(표면 굴곡 세기) · `bump_scale`(굴곡 촘촘함). 액체 · 유리 · 금속은 굴곡 없이 매끈하다.
- 빛 `env`: `sky` · `horizon` · `ground`(주변 색) · `key` · `key_power`(주광) · `fill` · `rim`(뒤에서 오는 빛) · `bokeh`(먼 배경 빛 망울 수) · `bokeh_colors` · `seed`.
- 판(plate) — 배경까지 그린 한 장: 장면에 `"backdrop": true`(또는 `camera.aspect`). 바닥은 `floor`: `color` · `color2` · `texture`(`wood`) · `scale` · `reflect`(비침). 초점 흐림 `camera.dof`(판 기본 0.6) · `focus_depth`.
- 층(layer) — 같은 카메라로 형태만 투명하게: `"layer": true`(배경 없음, 초점 흐림 0). 바닥이 아닌 곳에 얹을 층은 `"shadow": false`(바닥 그림자 없음). 판 위에 따로 움직일 인물 · 소품을 이렇게 뽑는다.
- 카메라: `focus` · `radius` · `azimuth` · `elevation` · `fov` · `aspect`(세로 ÷ 가로 — 9:16 화면이면 1920/1080). 결과는 폭 `res` px, 높이 `res × aspect`.
- 화면 좌표: `craft.form.render.project(scene, [[x, y, z], …], res)` 가 3D 점을 판의 px 로 바꾼다(`camera.focus` 가 있어야 함). 글자 · 2D 층 · 장면 코드 `K.image` 자리를 판과 맞출 때 쓴다.
- 흐름: 한 세계(같은 빛 · 바닥 · 재질)를 정하고 장면마다 카메라와 소품만 바꿔 판 한 장 + 층 몇 장을 그린 뒤, 장면 코드(`scenes/sNN.jsx`)에서 판을 깔고 층을 `K.image` 로 얹어 움직인다. 렌더 정보는 `data/workspace/cache/form/` 에 캐시된다(최대 `FLUMA_FORM_CACHE_GB`, 기본 12GB — 넘으면 오래 안 쓴 것부터 지움).
