---
name: refine
description: 초안 뒤 장면마다 디테일을 다듬는다 — 장면을 열고(show) 층별 계획(plan) → 앱의 전체 명령에서 골라 시도(try) → 전 · 후 렌더를 보고 고침 → 남김(keep). 어댑터 초벌은 시작점일 뿐, 전문가처럼 여러 앱을 넘나들며 깊게 쓴다. "디테일", "밋밋하다", "더 프로처럼", "이 장면 다듬어" 요청과 produce 의 초안 확인 뒤에 쓴다.
---

# 다듬기 (작업 세션)

고정 어댑터 · 움직임 JSX 는 **초벌**이다 — 앱 기능 몇 개만 쓴다. 디테일은 여기서 넣는다.
다듬은 것은 콘티에 기록으로 남고(`engine/craft/refine.py`), 제작할 때마다 초벌 위에 다시 적용된다 — 다시 만들어도 사라지지 않는다.

```
python3 engine/craft/session.py show <콘티> <장면>          # 재료 · 편집 파일 레이어 · 장면 컴프 레이어 · 기록 · 계획
python3 engine/craft/session.py plan <콘티> <장면> typo="…" light="…"
python3 engine/craft/session.py try  <콘티> <장면> --material <id> | --target motion|sound|edit  --pass pass.json [--at 1.2,2.5]
python3 engine/craft/session.py keep <콘티> <장면> (같은 인자)      # 검사(L40) 통과 시 콘티에 남김
python3 engine/craft/session.py drop <콘티> <장면> (대상) <번호>
python3 engine/craft/session.py coverage <콘티>                 # 앱 × 층 표 · 계획했는데 안 다듬은 층
```
장면 `0` = 영상 전체(소리 마스터 · 편집). 먼저 produce 로 초안을 한 번 만든다(편집 파일이 있어야 연다).

## 순서

1. **보기** — 초안 장면 정지 화면과 `show`. 레퍼런스 X-ray 의 같은 자리 장면과 나란히 놓고 무엇이 모자란지 층별로 적는다.
2. **계획** — `plan` 으로 층마다 한 줄(모든 층을 채울 필요 없다 — 이 장면에 필요한 것만). 근거 없는 효과는 넣지 않는다(디자인 방향 · 레퍼런스 · 사용자 요청).
3. **명령 찾기** — `python3 engine/craft/craft_catalog.py search "<하고 싶은 일>" --app <앱>`. 결과 아래 `↳ 시험:` 줄이 실제로 돌려 본 결과다
   (되는 상태 — 예: 픽셀 레이어에서만 · 필요한 인자 · 기본값 견본 그림 경로). 견본 그림은 Read 로 본다. 자세히는 `craft_catalog.py show <id> --app <앱>`.
   **효과 · 필터 · 프리셋을 고를 때는 견본 판부터 본다** — `.claude/skills/crafts/probe/<앱>.md` 의 판 목록(EffectCraft 효과 분류별 · 프리셋 세 시점 띠 · PhotoCraft 필터 메뉴별).
   문법은 `.claude/skills/crafts/reference/<앱>.md`.
4. **시도 → 보기 → 고치기** — `try` 가 전 · 후 PNG(소리는 WAV)를 준다. **반드시 열어서 본다.** 기본값 그대로의 효과는 대개 거칠다 — 세기 · 위치 · 타이밍(키프레임)을 고쳐 다시 `try`. 두세 번은 기본.
   움직임 · 타이밍은 정지 그림으로 안 보인다 — 보기(VL) 모델이 있으면 장면을 짧게 렌더해 `python3 engine/providers/see.py ask <장면 mp4> --q "등장 타이밍이 말과 맞나 · 거칠게 튀는 곳은?"` 로 움직임까지 본다. 어디를 다듬을지 모르겠으면 `see.py critique <콘티>` 의 issues 부터.
5. **남기기** — `keep`(layer · why 필수). 다음 장면으로. 끝나면 `coverage` 로 앱 · 층이 한쪽에 몰리지 않았는지 본다.
6. 전체 초안 다시(produce) → 이어 보기에서 장면 사이가 튀지 않는지.

## 검증된 레시피부터(직접 짜기 전에)

`python3 engine/craft/recipes.py list [--layer typo]` — 층별로 실제로 돌려 보고(시험 견본 전 · 후) 값을 다듬은 기법들. `show <id>` 로 언제 쓰나(when) · 쓰면 안 될 때(avoid) 를 먼저 읽는다.
```
python3 engine/craft/session.py try  <콘티> 6 --target motion --recipe light-sweep-once --vars MAT="Mat card" T0=0.4
python3 engine/craft/session.py keep <콘티> 6 --target motion --recipe light-sweep-once --vars MAT="Mat card" T0=0.4 --why "레퍼런스 결론 컷의 빛 한 번"
python3 engine/craft/session.py try  <콘티> 6 --material card --recipe material-warm-grain --vars PIXEL=Backdrop TOP="Title 2"
```
- 레시피를 그대로 쓰지 말고 장면에 맞게 값(T0 · DUR · PUSH · FROM …)을 바꿔 `try` 로 본다. 펼친 pass 가 콘티에 남는다(레시피 파일이 바뀌어도 이미 만든 영상은 그대로).
- 레시피 효과는 EffectCraft `script.run`(After Effects 식 JSX — 글자 애니메이터 · 키프레임 이징 · 3D 카메라 · 조정 레이어)이다. 새 기법도 이 방식으로 짜서 `recipes/` 에 넣고 `recipes.py verify <id>` 로 판을 보고 고친다.
- 판: `data/workspace/probe/recipes/sheet-<층>.png`(위: 전 · 아래: 후). verify 에서 배운 것 — 카메라 거리는 줌 값(-zoom)에 맞춰야 원래 크기, 깊이에 둔 배경은 그만큼 키운다 · Glow 문턱이 낮으면 밝은 카드 전체가 하얗게 날아간다 · 자간 시작값이 크면 첫 프레임이 화면 밖으로 넘친다 · Photo Filter 농도 20 이상은 화면이 주황으로 물든다.

## pass 형식

```json
{"layer": "color", "app": "photocraft", "why": "레퍼런스 결론 컷이 따뜻한 톤 · 진한 대비",
 "steps": [{"id": "layer.select", "params": {"name": "Backdrop"}},
           {"id": "filter.gallery.filmGrain", "params": {"grain": 3, "intensity": 6}},
           {"id": "layer.newAdjustmentLayer.colorLookup", "params": {"lut": "warm"}},
           {"id": "layer.newAdjustmentLayer.curves", "params": {"points": [[0,10],[64,52],[192,206],[255,250]]}}]}
```
- **재료**(`--material`): `app` 이 재료를 만든 앱이면 그 편집 파일(.psd · .vectorcraft …)을 이어서, 다른 앱이면 결과 그림을 열어 다듬는다 → 앱을 넘나든다(VectorCraft 그림 → PhotoCraft 질감 → …). 앞 pass 결과가 다음 pass 입력.
- **움직임**(`--target motion`): 장면 컴프(`S06 반전`)를 자동으로 연다. 레이어는 `show` 의 이름(`Mat <재료 id>` · `Sub 01` · `Title 1` · `SubBox 01` · `Overlay …` · `Camera` · `BG`). 시간은 장면 안 초.
- **소리 · 편집**: params 에 `"$START"` `"$END"` `"$MID"`(초) · `"$START_SMP"` `"$END_SMP"`(SoundCraft 샘플) · `"$START_TICKS"` `"$END_TICKS"`(FilmCraft) 자리표시자.

## 층 → 앱 · 기능 (시작점 — 여기 없는 기능도 catalog 에서 찾아 쓴다)

| 층 | 앱 · 명령 예 |
|---|---|
| composition 구도 | VectorCraft `object.align` · `object.distributeSpacing` · PhotoCraft 자르기 · EffectCraft `prop.set`(Position · Scale · Anchor) |
| typo 타이포 | EffectCraft `text.animatorProperties`(글자마다 시차 · 투명도 · 위치) · `text.animatorFontAxes` · `layer.enablePerChar3D` · PhotoCraft `type.setStyle` · `type.characterStyle.apply` · VectorCraft `type.pathOptions` · `stroke.widthPoint.set` |
| color 색 | EffectCraft `effect.apply` Curves · Lumetri Color · Tint · PhotoCraft `layer.newAdjustmentLayer.curves` · `…colorLookup`(warm · tealOrange · fadedFilm …) · `…selectiveColor` · FilmCraft `lumetri` |
| light 빛 | EffectCraft CC Light Sweep · CC Light Rays · Glow · Lens Flare · `layer.style.add`(outerGlow · innerGlow) · PhotoCraft `filter.render.lightingEffects` · `filter.render.lensFlare` · SolidCraft `render.preset.resolve`(스튜디오 조명) |
| texture 질감 | EffectCraft Add Grain · Fractal Noise · PhotoCraft `filter.gallery.filmGrain` · `filter.noise.addNoise` · `layer.layerStyle.patternOverlay` · TextureCraft 재질 |
| motion 움직임 | EffectCraft `keys.velocity`(이징) · `anim.addKeyframe` · `camera.orbit` · Depth of Field · `layer.mask.motionBlur` · 레이어 3D 스위치로 2.5D 시차 · SolidCraft `motion.study`(관절 애니메이션) |
| transition 전환 | FilmCraft `sequence.applyVideoTransition`(cross_dissolve …) · EffectCraft `layer.setTrackMatte`(매트 닦기) · 마스크 키프레임 |
| sound 소리 | SoundCraft 리버브 · EQ · 팬 자동화(`edit.automation_glide_pan`) · 볼륨 자동화 · 효과음 클립 |

## 배운 것 (시험에서)

- PhotoCraft 필터는 **픽셀 레이어**에만 — 글자 · 조정 레이어가 선택돼 있으면 거부된다. `layer.select {"name": …}` 를 먼저(레이어 이름 · 종류는 `show`).
- PhotoCraft 조정 레이어는 위의 모든 레이어가 아니라 **아래 전체**에 걸린다 — 맨 위 레이어를 고른 뒤 만들면 문서 전체 그레이드.
- EffectCraft `effect.apply` 기본값(CC Light Sweep 등)은 거칠다 — `prop.set` 으로 세기 · 폭을 낮추고 키프레임으로 한 번 지나가게.
- 명령이 틀리면 몇 번째 step 이 왜 틀렸는지 오류에 나온다 — 그대로 고쳐 다시 `try`.

## 하지 않는 것

- 한 장면에 층을 전부 넣기 — 필요한 2~4층만 깊게. 효과 과잉은 초벌보다 나쁘다.
- 보지 않고 keep — `try` 의 전 · 후 그림을 열어 보지 않은 pass 는 남기지 않는다.
- 디자인 방향(`direction`)과 반대되는 다듬기(담백 시안을 골랐는데 빛 번짐 · 그레인) — 사용자가 고른 것이 이긴다.

## 새 레시피 (실제 영상에서 검증)
`motion-speed-ramp` 결정적 순간 슬로모션(길이 유지) · `color-act-shift` 막마다 색온도 · `transition-pan-smear` 카메라 이동 번짐 · `light-impact-flash` 충돌 순간 빛 · `composition-slow-push` 끝말로 다가가기 · `typo-source-credit` 끝 출처.
앱을 잇는 재료는 콘티에 `craft` 재료로 차례로 적는다(VectorCraft → PhotoCraft · DesignCraft → PhotoCraft → Blender `uses`). 다른 재료의 입력이 된 재료는 화면에 저절로 나오지 않는다.
`session try` 는 마지막으로 만든 프로젝트를 쓴다 — 재료 구성을 바꿨으면 먼저 `render.py --draft` 로 다시 만들고 본다.

