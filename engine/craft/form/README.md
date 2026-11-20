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
0. **참고 그림부터 본다(기억으로 빚지 않는다 — 2026-11-20)** — 따라 그리는 게 아니라 어울리는 특징만 가져온다.
   - 검색어는 3~5개를 따로: 그 장르가 태어난 언어(극화 → 劇画 · 일본 만화 → 漫画, 미국 만화 → comic book), 눈에 보이는 묘사(선 · 명암 · 색 — 예: heavy ink crosshatching), 대표 작가 · 작품 이름(검색 결과가 알려 주면 그 이름으로 다시), 그리고 대상 자체(실제 사진 — 몸 구조). 사용자가 말한 낱말을 그대로 옮기지 않는다.
   - 찾은 페이지 8~15개를 `python3 engine/research/ref_images.py "<이름>" --id <영상 id> --pages <URL> …` → 시트 한 장(15~24장)을 Read.
   - 주제 · 톤 · 시청자에 어울리는 것만 고르고(관계없는 사진 · 광고 · 글 그림은 버림) 가져올 특징을 적는다: 비례 · 실루엣 · 과장 정도 · 선 · 명암 · 색. 영상에는 넣지 않는다(보기만).
1. 큰 덩어리(몸통) → 붙는 덩어리(머리 · 손잡이)를 `smooth_union` 으로(이음매 없이) → 작은 부품(눈 · 부리)은 `union`.
2. `python3 engine/craft/form_cli.py preview <형태.json> --ref <참고 NN.jpg>` — 참고 그림과 나란히(약 1~4초). Read 로 견주어 비례 · 실루엣을 고친다(2~3번).
3. `python3 engine/craft/form_cli.py styles <형태.json>` — 네 화풍을 한 장으로 비교(필요할 때만).
4. 콘티: `{"type": "form", "scene": "$FILE:data/compositions/<id>/forms/<이름>.json", "view": {"azimuth": 30}}` — 장면마다 각도만 바꿔 같은 형태를 다시 쓴다.

예: `examples/duck.json`(고무 오리) · `examples/mug.json`(머그). 그대로 복사하지 말고 비례 · 재질 쓰는 법만 본다.
사람은 그리지 않는다(실제 자료만 — 사람 형태는 빚지 않는다).

## 캐릭터는 움직인다 (2026-11-20 — 정지 그림 한 장으로 쓰지 않는다)
부품에 `name` 을 붙이고 `anim` 에 시간별 값을 적으면 프레임 묶음으로 그려 장면에서 반복 재생한다(12fps · 1~2초 · 약 13초/18장).
- 관절은 **이름 붙은 그룹**으로: `{"name": "tail", "op": "union", "pos": [붙는 자리], "rot": [0,0,0], "children": [그 자리 기준으로 놓은 도형]}` — 그룹의 `rot` 이 붙는 자리를 축으로 돈다. 몸 전체를 들썩이려면 전체를 그룹 하나(`"name": "all"`)로 감싼다.
- `"anim": {"dur": 1.5, "tracks": {"tail": {"rot": [[0, [0,0,-15]], [0.75, [0,0,25]]]}, "eyes": {"radii": [[0, [0.034,0.042,0.02]], [0.6, …같음], [0.7, [0.036,0.006,0.02]], [0.8, …같음]]}, "all": {"pos": [[0,[0,0,0]], [0.375,[0,0.03,0]]]}}}`
  키는 `[초, 값]` — 그 칸(pos · rot · scale · radii · r · h …)의 **값 그대로**, 사이는 부드럽게, 마지막 뒤는 처음으로 돌아가 반복. 눈 깜빡임은 radii 세로를 0.1초 줄였다 펴기.
- 비율 · 표정 · 동작은 정해진 표가 없다 — 사용자 요청 · 레퍼런스 · 아트 디렉션의 느낌을 보고 영상마다 정한다.
- 그리기: `python3 engine/craft/form_cli.py anim <형태.json> --out-dir data/compositions/<id>/forms/<이름>.anim` → `…/f000.png` 와 확인 시트. 장면 코드에서 `K.image('…/f000.png', x, y, 배율)` 이면 반복 재생된다. 콘티 재료(type form)에 anim 이 있으면 엔진이 알아서 묶음으로 그린다.

## 화풍 값 (`look`) — 이름 화풍(flat · cel · sketch · clay) 대신 축의 값으로 (2026-11-20)
**그림체는 형태부터 다르다** — look 은 겉칠일 뿐이다. 같은 고양이도 실사 · 극화는 작은 머리 · 긴 목 · 근육 덩어리, 카툰은 큰 머리 · 고무 팔다리 · 큰 발, 데포르메는 머리 = 몸, 미니멀은 기하 도형 몇 개로 **형태를 새로 빚는다**(참고 그림의 비례 · 구성을 보고). 같은 형태에 look 만 바꾸지 않는다.
그림체는 몇 개 축의 조합이다. 참고 그림을 보고 축마다 값을 정한다(화풍 이름별 정답표는 없다 — 영상마다 새로).
재료: `{"type": "form", "scene": …, "look": {…}}` · 도구: `form_cli preview <형태> --look '{…}'`. 한 장 0.1~0.5초(형태 계산은 캐시).
| 축 | 값 |
|---|---|
| `bands` 명암 단계 | 0 부드럽게 · 1 없음(평면) · 2~4 단계 |
| `shadow` 그림자 깊이 · `light` 밝은 면 하양 · `rim` 테두리 빛 | 0~1 |
| `highlight` | "dot" · "soft" · null |
| `line` 바깥선 · `inner` 안쪽 선 굵기(px, 0 없음) · `weight` 그림자 쪽 굵게 · `jitter` 손떨림 | 숫자 |
| `ink` 선 · 먹색 | "#hex" |
| `solid` 먹칠(이만큼 넘게 어두운 곳을 먹색으로) | 0~1 |
| `hatch` 해칭 간격(px) · `hatch_angle` · `cross` 교차 | 숫자 · 도 · bool |
| `tone` 스크린톤 점 간격 · `halftone` 망점 간격(어두울수록 큰 점) | px |
| `mono` 흑백 · `saturation` 채도 배율 · `tint` 색 기울기 · `colors` 색 수 제한 | bool · 숫자 · "#hex" · 정수 |
| `wash` 수채 번짐 · `paper` 종이 · 크레용 결 | 0~1 |
| `pixel` 픽셀 크기(+`colors`) | px |
| `ground` 바닥 그림자 | bool |
