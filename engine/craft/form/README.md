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
