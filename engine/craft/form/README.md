# 형태(form) 작성법

형태는 **데이터로 빚는다** — 기본 도형을 놓고 녹여 붙이거나(smooth_union) 깎아 낸다(subtract). 화풍(flat · cel · sketch · clay)은 형태와 따로, 영상 아트 디렉션(`direction.art.style`)이 정한다. 영상마다 새로 빚는다(부품을 쌓아 두지 않는다).

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
3. `python3 engine/craft/form_cli.py styles <형태.json>` — 네 화풍을 한 장으로 비교(필요할 때만).
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
- 자세(`pose`)는 도(°): 사람 `lean` · `spine`[앞, 옆, 비틀기] · `head`[끄덕, 돌리기, 갸웃] · `l_arm`/`r_arm`[앞, 벌리기, 비틀기] · `l_elbow` · `l_leg`/`r_leg`[앞, 벌리기] · `l_knee`, 동물 `spine` · `neck` · `head` · `tail`[들기, 옆, 말기] · `fl` `fr` `bl` `br`[앞, 벌리기] · `*_knee`.
- 발은 늘 바닥(y = 0)에 닿는다. 얼굴(눈 · 입 · 코 · 귀)과 머리카락은 머리 뼈에, 옷(소매 · 바지)은 팔다리 뼈에 붙는다.
- `form_cli preview` 가 몸과 떨어진 덩어리를 세어 알린다(△ 떨어진 덩어리 N개).
- 새: `{"rig": "bird", "pose": {"tilt", "neck": [굽힘, 돌리기], "head", "wings": [날갯짓, 펼침], "tail": [들기, 부채 0~1], "l_leg": [앞], "l_knee"}, "mats": {"body", "belly", "wing", "tail", "beak", "leg", "eye"}}`
- 사람 표정 `face`: `smile`(−1 찡그림 … 1 웃음) · `open`(입 벌림 0~1) · `brow`(1 화남 · −1 걱정) · `brow_y`(눈썹 높이) · `eyelid`(0 뜸 … 1 감음) · `blush`(mats 에 `blush` 재질이 있을 때) · `look`[x, y](눈동자)
- 머리 모양 `hair`: `top`(윗머리 볼륨) · `bangs`(앞머리) · `side`(옆머리) · `back`(뒷머리 길이) · `tail`(포니테일) · `bun`(올림머리) · `spikes`(뻗친 다발 수) · `part`(가르마 −1~1)
- 손: `"hands": "mitten"`(손바닥 + 엄지, 기본) · `"fingers"`(다섯 손가락) — 자세 `l_grip`/`r_grip`(0 펴기 … 1 주먹) · `l_spread`/`r_spread`(벌림 °)
- 클로즈업: 카메라 `"focus": [x, y, z], "radius": r` — 그 점을 가운데에 반지름만큼만(얼굴 · 손). 머리 위치는 `skeleton.joints(size, pose)["head"]`
- 움직임: `anim.tracks` 에서 뼈대 안쪽 값을 점 경로로 — `{"hero": {"pose.r_elbow": [[0, 15], [0.5, 70]], "face.eyelid": [[0.7, 0], [0.8, 1], [0.9, 0]]}}`(노드 `"name": "hero"`)
사람은 그리지 않는다(실제 자료만 — 사람 형태는 빚지 않는다).

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
- 서 있을 때는 `"at": [x, z], "face": 도` — 그 자리 지형 위에 선다. `"ik": {"r_hand": [x, y, z]}`(세상 좌표)로 손 · 발을 물건에 댄다(문고리 · 손잡이 · 난간).
- `hold`: 아무 형태를 손에 — `grip` 은 그 형태에서 손이 쥐는 점. `carry` 는 손을 따라, `drag` 는 쥔 점은 손 · `ground` 점은 지면에 닿게 기울인다(캐리어 · 수레).
- 관절은 사람 가동 범위 안에서만 움직인다(`skeleton.LIMITS` — 무릎 · 팔꿈치 0~150° 등).
- 카메라: 기본은 세상에 고정(처음 · 가운데 · 끝 자세가 모두 들어오게). `"anim": {"camera": "follow", "radius": 0.8}` 이면 움직이는 캐릭터를 따라간다(키 × radius). `anim.tracks.camera` 로 카메라 값(azimuth · focus …)을 직접 움직일 수도 있다.
- 장면 전체가 하나의 움직이는 그림(12fps 프레임 묶음)이 된다 — 400px 기준 한 장 약 0.5~1.5초.
