# EffectCraft 참고 (v0.21.0)

**한 줄 요약**: After Effects 류 합성 · 모션 그래픽 앱(Rust, MIT/Apache-2.0). 명령 743개 · 효과 308개 · 내장 프리셋 76개 · 템플릿 8개.
모든 메뉴 동작이 `명령 id + JSON params` 이고, CLI · JSX 스크립트 · MCP 어디서 불러도 같은 명령이 돈다. Fluma 에서는 **장면 움직임 단계**(콘티 → `.ecproj` → 무음 mp4)를 맡는다.

- CLI: `tools/crafts/effectcraft/app/effectcraft-0.21.0-linux-x86_64/bin/effectcraft-cli` (아래 `$EC`)
- 글꼴: 저장소 글꼴은 설치하지 않고 `EFFECTCRAFT_FONT_DIRS=<repo>/public/fonts` 로 넘긴다(어댑터 `_env()` 가 이미 그렇게 함). 이 변수가 없으면 `text.fonts {"query":"pretendard"}` 결과가 0개.

---

## 1. 헤드리스로 되는 것 / 안 되는 것

| 된다 (확인함) | 안 되거나 주의 |
|---|---|
| `run --commands steps.json` 로 프로젝트 생성 · 편집 · 저장 | `--empty` 를 빼면 **데모 프로젝트**가 열린다. 새로 만들 땐 꼭 `--empty` |
| `script file.jsx` (AE 스크립팅 객체 모델) + JSX 안에서 `app.run(id, params)` 로 엔진 명령 호출 | 스크립트는 프로젝트 폴더 밖 파일을 쓸 수 없음(환경설정 Allow Scripts to Write Files 가 꺼져 있을 때). `app.project.save(new File(..))` 는 현재 파이프라인에서 동작 중 |
| `render-frame` PNG (1080×1920 한 장 40~100ms) | UI 전용 명령(`ui_*`, `screenshot`)은 `--bridge` 로 앱 창이 떠 있어야 함 |
| `render` h264 · webm(알파) · prores · png 시퀀스 · gif, 오디오 레이어 포함 시 AAC 트랙 | CPU 렌더. 1080×1920 4초(격자 배경 + 그림자) = 25초. `--gpu` 는 이 기계에서 오히려 약간 느렸음(1초분 5.4s vs 4.1s) |
| 템플릿(.ectemplate) + values.json 으로 바로 렌더 | 내장 템플릿 8개 중 세로(1080×1920)는 `vertical-story` 하나 |
| Lottie 내보내기(지원 못 하는 기능을 warnings 로 알려줌) | Lottie 는 효과 · 레이어 스타일 · 표현식(옵션) 대부분 빠짐 |
| MCP 헤드리스(`mcp`) 도구 27개 | `--automation-read-root/--automation-write-root` 로 가두면 **`run_script` 등 스크립트가 거부**됨(craft.json 의 mcp 설정이 그렇게 가둔다) → 대화 중 에이전트는 `execute_command` / `batch` 위주로 |
| 모션 트래킹 · 워프 스태빌라이저 · 3D 카메라 트래커(`wait:true`) | 모션 트래킹 ✅(3-12), 나머지 미확인. Roto Brush · 얼굴 추적은 모델 내려받기 필요 → **금지 항목, 문서로만** |

공통 규칙
- 레이어는 id · `"#n"`(위에서 1번) · 이름으로 가리킨다. **만들 때 `name` 을 주면** 뒤 단계에서 이름으로 부를 수 있다.
- 속성 경로는 `props <comp> <layer> --flat` 으로 본다: `transform/position`, `effects/#1/center`, `contents/trim/end`, `text/animators/animator/selectors/rangeSelector/offset` …
- 시간: `prop.addKey` 는 기본이 레이어 시간. 장면 레이어가 오프셋돼 있으면 `"timeBase":"comp"` 를 같이 준다. JSX `setValueAtTime` 은 comp 시간.
- 프리셋(`anim.applyBuiltinPreset`, `layer.applyTextPreset`)은 **현재 시각(CTI)** 에 키를 놓는다 → 먼저 `time.set {"time": t}`.
- 알 수 없는 param 키는 거부되고 받는 키 목록을 알려준다(오타가 조용히 무시되지 않음).

---

## 2. 지금 Fluma 가 쓰는 방식

- `engine/craft/renderer/adapter.py`: `effectcraft-cli script <job>.jsx` (300s) → `render --project P --comp Main --format h264 --audio off --fps N` (초안은 `--resolution half --quality draft`) → 확인용 `render-frame --time s`.
- `engine/craft/motion.py` `build_jsx()`: JSX 를 문자열로 만든다. 기본 기능(`addComp` · `addSolid` · `addText` · `addShape` · 효과 · 표현식 · 키프레임)에 더해 JSX 안 `app.run` 으로(실패하면 손 키프레임으로 대신):
  - 배경 프리셋(형식별 BG_PRESET, `prop.set` 으로 색 맞춤, 표현식 time 에 장면 시작을 더해 이어짐) · 재료 등장 프리셋(ENTER, `retimeKeys` 로 0.6초) · 퇴장 프리셋(재료 `exit`) · 글자 프리셋(훅 bounceInWords 0.5초, 감성 자막 fadeUpCharacters).
  - 실제 화면: `layer.addMask rounded` + `ADBE Drop Shadow` 효과(레이어 스타일보다 빠름).
  - 주석 층(overlay · DeckCraft 도식 layers): 대상 'Mat <id>' 레이어의 자식으로 cue 시각에.
- `craft-art` 스킬: 부품 SVG 를 관절 회전 표현식으로 인형처럼 흔든다.
- 안 쓰는 것: 행동 프리셋, 레이어 스타일, 트랙 매트, 3D 레이어 · 카메라, 오디오 반응 효과, 템플릿 · Essential Graphics, Lottie, 트래킹(시험만).
- 새 사실: JSX 의 `c.openInViewer()` 뒤에 `app.run` 명령은 그 comp 에 적용된다.

## 3. 쇼츠용 핵심 기능

표기: ✅ = 이 문서 작성 때 헤드리스로 돌려 결과 파일 · PNG 확인, ⚠ = 돌렸지만 결과가 기대와 다름, ❔ = 미확인(문서 · 명령 목록으로만)

### 3-1. 내장 배경 프리셋 23종 ✅ (높음)
단색 바탕 대신 '계속 움직이는' 배경. 표현식 기반이라 장면 길이와 상관없이 계속 움직인다(이음매 없는 루프는 아님).
```json
{"command":"layer.newSolid","params":{"name":"BG","color":"#101018"}},
{"command":"anim.applyBuiltinPreset","params":{"preset":"blueprintGrid","layers":["BG"]}}
```
- 기술 설명형: `blueprintGrid`, `scrollingStripes`, `checkerScroll`, `sweepingLight`, `grainyWash`
- 감성형: `bokehDrift`, `dawnSky`(6초 동안 밤→일출), `slowFog`, `cloudBank`, `softGradientDrift`, `auroraVeil`
- 광고형: `pulseRings`, `spotlightFloor`, `pastelPlasma`, `emberHaze`
- 목록: `exec anim.builtinPresets '{"category":"Backgrounds"}' --empty --json`
- 시험: t1(blueprintGrid) · s(bokehDrift, JSX 안 `app.run`) 렌더 PNG 확인. 반환 `{"effects":[…]}` = 붙은 효과 uid.
- 주의: 색은 프리셋 고정값. 브랜드 색이 필요하면 붙은 효과의 색 param 을 `prop.set` 으로 바꾼다(효과 경로는 `props … --flat`). blueprintGrid 는 Grid 효과 두 개라 프레임당 ~22ms.

### 3-2. 전환(등장 · 퇴장) 프리셋 23종 ✅ (높음)
화면 캡처 · 카드가 '그냥 나타나는' 컷을 없앤다.
```json
{"command":"time.set","params":{"time":1.5}},
{"command":"anim.applyBuiltinPreset","params":{"preset":"wipeInFromLeft","layers":["screen.png"]}}
```
- 등장: `fadeIn`, `wipeInFromLeft/Right/Top/Bottom`, `diagonalSweepIn`, `clockReveal`, `fanOpen`, `blindsOpen`, `slatsDown`, `pixelDissolveIn`, `mosaicFadeIn`, `cardFlipIn`, `gridDoorsIn`, `lensPopIn`, `lineSweepIn`, `jawsCloseIn`
- 퇴장: `fadeOut`, `wipeOutToRight`, `clockWipeOut`, `blindsClose`, `pixelDissolveOut`, `cardFlipOut`
- 시험: `time.set 1.5` 다음 `fadeIn` → Opacity 키 1.5s=0, 2.0s=100(Bezier) 확인. wipeInFromLeft 는 Linear Wipe 효과로 붙고 0.25s 프레임에서 왼쪽부터 드러나는 것 PNG 확인.
- 주의: 길이는 프리셋마다 다르다 — `fadeIn` 0.5초, **wipe 계열은 1초**(2026-11-05 실측, 문서의 '0.5초 고정'과 다름). Fluma 는 JSX 에서 붙은 키를 지우고 다시 놓아(`retimeKeys`) 0.6초로 맞춘다. 1080×1350 캡처 한 장에 Drop Shadow 효과 28ms, 레이어 스타일 33ms.

### 3-3. 동작(Behaviors) 프리셋 22종 ✅ (중간)
강조 배지 · 아이콘 · 숫자에 생명감. 표현식으로 붙는다(키 없음).
- `pulse`, `heartbeat`, `breathe`, `floatUpDown`, `sway`, `wobble`, `shake`, `wiggleSoft`, `bouncingBall`, `pendulum`, `orbit`, `figureEight`, `spinSlow/Fast`, `rubberBand`, `jitterScale`, `blink`, `strobe`, `flicker`, `fadePulse`, `driftRight`, `driftDiagonal`
- 시험: `heartbeat` → Scale 에 `var t = time % 1; … [value[0]*k, value[1]*k]` 표현식 확인.
- 주의: `shake` · `strobe` · `flicker` 는 짧게만(눈 피로). 사람이 앱에서 숫자를 고치기 쉽게 표현식 그대로 둔다.

### 3-4. 텍스트 애니메이터 프리셋 8종 ✅ (높음)
훅 제목 · 코드 · 자막 등장. 글자/단어 단위 애니메이션을 직접 짜지 않아도 된다.
```json
{"command":"layer.newText","params":{"name":"Title","text":"배포 3초 컷","position":[540,300],"font":"Pretendard","style":"Black","size":120,"fill":"#ffffff","stroke":"#000000","applyStroke":true,"strokeWidth":10,"justify":"center"}},
{"command":"layer.applyTextPreset","params":{"layer":"Title","preset":"bounceInWords"}}
```
- `typewriter`(코드 · 터미널 명령), `bounceInWords`(훅), `fadeUpCharacters`(감성), `trackingIn`(광고 로고 문구), `scramble`(해커 · 보안 주제), `blurIn`, `dropInLines`(목록), `jitter`(지속 떨림)
- 시험: bounceInWords → 애니메이터 2개, Range Offset 키 0s=-100 → 1.2s=100. 0.25s 에 '배 포' 일부만 보이고 2.5s 에 완성 PNG 확인. typewriter 0.25s 에 'gi' 만 보임 확인. JSX 에서 `app.run('layer.applyTextPreset', {...})` 도 동작.
- 주의: 실제 길이는 bounceInWords 1.5초(애니메이터 키 1→2.2초 · 1.15→2.5초), typewriter 2초. 짧게 하려면 JSX 에서 키를 지우고 다시 놓는다(Fluma 0.5초). bounceInWords 는 시작 키 전에도 글자 일부가 보이는 버그가 있어 투명도 키 · inPoint 로 가린다. 한글은 글자 단위로 잘 나뉨(bounceInWords 는 단어 단위).
- 더 세밀하게: `layer.addTextAnimator {properties:[opacity,scale,blur,fillColor…]}` + `layer.addTextSelector {kind: range|wiggly|expression}` — 속성 28종(`text.animatorProperties`). ❔

### 3-5. 실제 화면(스크린샷 · 녹화) 다듬기 ✅ (높음)
"실제 화면 > 효과" 원칙에 가장 직접 도움. 캡처를 넣고, 둥근 모서리 · 그림자 · 기울기 · 카메라 밀기 · 빛 쓸기.
```json
{"command":"file.import","params":{"paths":["/abs/screen.png","/abs/voice.wav"]}},
{"command":"layer.addItem","params":{"item":"screen.png","position":[540,960]}},
{"command":"layer.addMask","params":{"layer":"screen.png","shape":"rounded","rect":[40,40,1000,1270]}},
{"command":"layer.style.add","params":{"style":"dropShadow","layers":["screen.png"]}},
{"command":"effect.apply","params":{"effect":"CC Light Sweep","layers":["screen.png"]}},
{"command":"layer.setSwitch","params":{"layers":["screen.png"],"switch":"threeD","value":true}},
{"command":"layer.newCamera","params":{"name":"Cam","type":"oneNode","preset":"35mm"}}
```
이어서 키:
```sh
$EC run t4.ecproj \
 prop.addKey '{"layer":"Cam","path":"transform/position","time":0,"timeBase":"comp","value":[540,960,-2100]}' \
 prop.addKey '{"layer":"Cam","path":"transform/position","time":2.5,"timeBase":"comp","value":[540,700,-1100]}' \
 prop.addKey '{"layer":"screen.png","path":"transform/rotationY","time":0,"timeBase":"comp","value":25}' \
 prop.addKey '{"layer":"screen.png","path":"transform/rotationY","time":1.5,"timeBase":"comp","value":0}' \
 prop.addKey '{"layer":"screen.png","path":"effects/#1/center","time":0,"timeBase":"comp","value":[-200,675]}' \
 prop.addKey '{"layer":"screen.png","path":"effects/#1/center","time":1.2,"timeBase":"comp","value":[1300,675]}' --save
```
- 시험(t4): 0.2s 기울어진 창 + 빛 줄, 2.5s 정면 · 확대 · 둥근 모서리 PNG 확인. 기본 카메라 위치 `[540,960,-1500]`, zoom 1050.
- 스위치 이름은 `threeD` (`three_d` 는 거부). 마스크 rect 는 레이어 좌표.
- 그림자(layer style)는 프레임당 ~40ms 로 가장 비쌈(bench). 장면마다 꼭 필요할 때만.
- 영상 녹화(.mp4)도 같은 `file.import` → `layer.addItem`. `layer.addItem {in, out}` 으로 구간만 쓰기. ❔(mp4 footage 는 이번에 안 돌려 봄)

### 3-6. 화면 속 한 줄 짚기 (마스크 · 트랙 매트 · Magnify) (중간)
- 어두운 덮개 + 구멍: 검은 Solid(불투명도 60) 에 `layer.addMask {shape:"rounded", rect:[…]}` 후 마스크 모드를 빼기로 → 짚는 줄만 밝게. ❔
- `layer.setTrackMatte {layer, matte, kind: alpha|luma…}` 로 화면 안에 글자 모양 구멍 등. ❔
- `Magnify`(ec.distort.magnify; center · magnification · size · feather) ⚠: t3 에서 center [300,330] · 220% · size 160 으로 붙였는데 확대 원이 보이지 않고 그 자리 글자만 잘려 보였다. 쓰려면 render-frame 으로 꼭 확인하거나, 대신 '같은 캡처를 한 번 더 올리고 마스크 + 스케일' 로 돋보기를 만든다.

### 3-7. 밑줄 그리기 · 선 드로잉 (Trim Paths) ✅ (중간)
```json
{"command":"layer.newShape","params":{"name":"Underline","kind":"rect","size":[600,14],"fill":"#ffd60a","position":[540,1620]}},
{"command":"layer.addShapeItem","params":{"layer":"Underline","kind":"trim"}}
```
```json
{"command":"prop.addKey","params":{"layer":"Underline","path":"contents/trim/end","time":0.5,"timeBase":"comp","value":0}},
{"command":"prop.addKey","params":{"layer":"Underline","path":"contents/trim/end","time":1.0,"timeBase":"comp","value":100}}
```
- 시험(t3): 0.75s 에 반쯤 그려진 줄, 2.0s 에 완성 확인.
- 주의: 채운 사각형에 trim 을 걸면 둘레를 따라 잘려 **쐐기 모양**으로 자라난다. 깔끔한 밑줄은 `shape.newPath {vertices:[[x0,y],[x1,y]], stroke, strokeWidth, fill:false}` + trim(❔), 또는 사각형 Scale X 키로.
- `shape.stroke.taper`(붓 끝 가늘게), `shape.dashes.add`(점선), 리피터 · 지그재그 · 웨이브 등 셰이프 연산자 20종: `layer.addShapeItem {kind: repeater|zigzag|wiggle|round|offset…}`. ❔

### 3-8. 나레이션 파형 (Audio Waveform / Audio Spectrum) ✅ (중간)
말하는 동안 화면 아래 파형 — 정지 화면이 덜 정지해 보인다(감성 · 정보 형식).
```json
{"command":"layer.addItem","params":{"item":"voice.wav"}},
{"command":"layer.newSolid","params":{"name":"Wave","color":"#000000"}},
{"command":"effect.apply","params":{"effect":"Audio Waveform","layers":["Wave"]}}
```
```sh
$EC run t3.ecproj prop.set '{"layer":"Wave","path":"effects/#1/audioLayer","value":4}' \
  prop.set '{"layer":"Wave","path":"effects/#1/startPoint","value":[140,1780]}' \
  prop.set '{"layer":"Wave","path":"effects/#1/endPoint","value":[940,1780]}' \
  prop.set '{"layer":"Wave","path":"effects/#1/maximumHeight","value":220}' \
  prop.set '{"layer":"Wave","path":"effects/#1/thickness","value":6}' \
  prop.set '{"layer":"Wave","path":"effects/#1/insideColor","value":"#ffd60a"}' --save
```
- `audioLayer` 값 = 오디오 레이어 **id**(addItem 결과의 `layer`).
- 시험(t3): 합성 음성 wav 로 0.75s · 2.0s 파형 모양이 소리 크기 따라 다른 것 확인.
- Solid 는 `compositeOnOriginal:false` 기본이라 Solid 색은 안 보이고 파형만 그려진다. 레이어 블렌드는 그대로 위에 얹으면 됨.
- `Audio Spectrum`(주파수 막대, `frequencyBands`, `usePolarPath` 원형)도 같은 방식. ❔
- 오디오 레이어가 있는 comp 를 `render --audio on` 하면 AAC 트랙이 들어간다(t4.mp4 ffprobe 확인). 현 파이프라인은 `--audio off` 후 SoundCraft 로 섞으니 파형용 오디오 레이어는 소리를 꺼도(`layer.setSwitch switch:"audio" value:false`, ❔) 파형은 그려지는지 확인 필요.

### 3-9. Essential Graphics 템플릿 → 값만 바꿔 렌더 ✅ (높음 — 반복 형식)
format-daily(당일 시세) · format-ad 처럼 매번 같은 틀에 값만 바뀌는 영상에 맞다. 사람이 앱에서 틀을 한 번 다듬어 두면 에이전트는 JSON 만 쓴다.
```sh
$EC run templates.create '{"id":"vertical-story","projectPath":"/abs/vs.ecproj"}' --empty --save-as /abs/vs.ecproj
$EC exec essential.list '{"comp":1}' --project vs.ecproj --json            # 컨트롤 이름 확인
$EC exec essential.exportTemplate '{"comp":1,"path":"/abs/vs.ectemplate"}' --project vs.ecproj
echo '{"Headline":"무료 AI 툴 3개","Call to Action":"팔로우하고 더 보기"}' > vals.json
$EC render-frame --template vs.ectemplate --values vals.json --time 3 --out vs_3.png
$EC render --template vs.ectemplate --values vals.json --out out.mp4 --format h264   # 영상(❔, 같은 옵션)
```
- 시험: 한글 값으로 렌더 PNG 확인.
- 주의: **글자 자동 맞춤 없음** — '무료 AI 툴 3개' 가 화면 밖으로 넘쳤다. 자체 템플릿을 만들 땐 크기를 `sourceRectAtTime` 표현식으로 맞추거나 짧은 값만 넣게 검사. 기본 글꼴이 Pretendard 가 아니다(대체 글꼴). 
- 자체 템플릿 만들기: `essential.addProperty {comp, layer, path:"text/sourceText", name:"Price"}` · 색 · 미디어(`essential.addMedia {layer, name}` → values 에 파일 경로) → `essential.exportTemplate`. ❔
- 내장 템플릿 8종: lower-third, title-card, logo-reveal, kinetic-type, social-square(1080²), **vertical-story(1080×1920)**, slideshow, text-orbit-3d. 나머지는 16:9.

### 3-10. 효과 308종 중 쇼츠에 쓸 만한 것 (효과 id · 주요 param)
`effect.apply {effect: 이름|id, layers}` 또는 MCP `add_effect {layer, effect, values}`(✅ Glow threshold 40 · radius 40 · intensity 1.5 한 번에 적용 확인).
| 쓰임 | 효과(id) | 주요 param |
|---|---|---|
| 강조 빛 | Glow (`ec.stylize.glow`) | threshold, radius, intensity |
| 화면 반짝 | CC Light Sweep (`ec.generate.cclightsweep`) ✅ | center, direction, width, sweepIntensity |
| 장면 전환 | Linear Wipe · Radial Wipe · Iris Wipe · Venetian Blinds · Block Dissolve · Card Wipe · Gradient Wipe | completion(0→100 키) |
| 속도감 | Directional Blur · Radial Blur · Motion Tile(흔들림 가장자리 채움) · Echo | length / amount |
| 숫자 | Numbers (`ec.text.numbers`) | format/value, decimalPlaces — 지금의 `linear()` 표현식 숫자 세기 대안 |
| 질감 · 감성 | Add Grain · Noise · Fractal Noise · Lumetri Color · Curves · Tint | |
| 날씨 · 입자 | CC Rainfall · CC Snowfall · CC Particle World | drops / flakes / birthRate |
| 손그림 느낌 | Write-on · Stroke(마스크 따라 그리기) · Scribble · Cartoon · Turbulent Displace | |
| 표현식 조절기 | Slider · Checkbox · Color · Point Control | 사람이 나중에 숫자 하나로 조정 |
전체: `exec effect.list --empty --json` (params 에 id · 기본값 · 범위 · 팝업 옵션). 위 표 중 ✅ 표시 외는 ❔.

### 3-11. 한 번에 여러 명령 · 결과 참조 ✅
- CLI: `run --commands steps.json` (JSON 배열, 실패 단계는 `(step N)` 로 알려줌). t1 은 14단계, t3 은 13단계를 한 번에.
- MCP `batch {steps, atomic}`: `"$1.layer"` 처럼 앞 단계 결과를 다음 params 에 쓸 수 있고 실패하면 전체 되돌림. ❔(CLI `engine.batch` 와 같음)
- JSX 와 섞기: 기존 `build_jsx()` 안에서 `app.run('anim.applyBuiltinPreset', {...})` 처럼 바로 부르면 생성기 구조를 안 바꾸고 프리셋을 쓸 수 있다 ✅.

### 3-12. 기타 (미확인 ❔, 트래킹만 ✅)
- `motion.sketch {layer, points:[[t,x,y]…]}`: 경로 점으로 움직임 기록 — 커서 따라가기 연출.
- ✅ `track.motion` → `track.setPoint` → `track.analyze {"wait":true}` → `track.apply`: JSX `app.run` 으로 돌려 위 레이어(널) Position 에 프레임마다 키. 2초 합성 영상에서 위치 오차 0.5px, 57프레임 분석 0.16초(2026-11-05). 화면 녹화 속 버튼을 따라가는 말풍선 · 동그라미에 쓸 수 있다(파이프라인에는 아직 없음).
- `paths.tracePath {layer, path}`: 경로를 따라 움직이는 널(화살표 이동).
- `puppet.addPin / recordPin / follow`: 그림 인형의 핀 변형(craft-art 의 회전 표현식보다 자연스러울 수 있음).
- `file.exportLottie {comp, path, includeExpressions, textAsShapes}` ✅(t1 → 29KB json, warnings 5개: 표현식 · Linear Wipe · 레이어 스타일 · Grid 효과 제외 안내). 웹 미리보기용. `file.importLottie` 로 LottieFiles 아이콘 애니를 장면에 넣기 ❔(권리 확인 필요).
- `layer.sequence {layers, overlap, duration, transition: crossDissolve}`: 레이어 이어 붙이기.
- `layer.precompose`, `comp.settings {preserveFrameRate}`, `layer.timing {layers, start}`.
- `render --format webm --channels rgba` ✅(1초분 3.5초) — 알파 있는 장면 레이어를 FilmCraft 위에 겹치는 '장면 내 엔진 혼합' 에 쓸 수 있다.

---

## 4. 전체 명령 분류 요약 (743개, `commands --json`)

| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| layer | 122 | newText · newShape · newSolid · newNull · newCamera · newLight · addItem · addMask · setTrackMatte · applyTextPreset · addTextAnimator · style.add · setSwitch · timing · sequence · precompose |
| view | 78 | res.full/half · 3D 뷰 · 가이드 (대부분 UI) |
| file | 64 | import · saveAs · exportLottie · importLottie · interpretFootage · replaceFootage · importAep · exportTimeline |
| keys | 37 | select · move · velocity · copy/paste · quickOffset |
| comp | 33 | new · settings · info · saveFrameAs |
| edit | 27 | undo · copy · paste · clear |
| track | 22 | motion · stabilize · analyze · apply · mask · camera · warpStabilizer |
| essential | 22 | addProperty · addMedia · set · exportTemplate · importTemplate · list |
| effect | 21 | apply · list · remove · reorder · copy/paste · pickColor |
| camera | 20 | orbit · pan · dolly · createFromSolve · exportBlender |
| renderQueue | 20 | add · render · setOutput |
| prop | 18 | get · set · addKey · setExpression · pickWhip · convertExpressionToKeyframes |
| mask | 17 | interpolate · set · 모드 |
| time | 17 | set · nextKey · 작업 영역 |
| roto 14 · text 14 · project 13 · help 13 · app 12 · footage 12 · puppet 10 · anim 9 · window 9 · shape 8 · scriptui 7 · shortcuts 7 · mediaBrowser 7 · path 6 · playback 6 · paint 6 · face 5 · markers 5 · objectMatte 5 · prefs 5 · learn 5 · templates 5 · render 4 · material 4 · script 4 · light 3 · paths 3 · warp 3 · jobs 3 · storage 3 · 기타 1~2개 그룹 14 | | anim.applyBuiltinPreset · anim.builtinPresets · templates.list/create · text.presets · text.fonts · shape.newPath · markers.set · expr.errors · engine.batch |

- 효과 308개: Color Correction 40 · Distort 39 · Generate 26 · Stylize 25 · Simulation 18 · Transition 17 · Blur & Sharpen 16 · Audio 13 · Channel 13 · Noise & Grain 13 · Immersive Video 12 · Keying 12 · Perspective 10 · 3D Channel 9 · Expression Controls 9 · Utility 9 · Time 8 · Matte 7 · Text 2 · Paint 1 · Obsolete 9
- 프리셋: Transitions 23 · Backgrounds 23 · Behaviors 22 (`anim.builtinPresets`) + 텍스트 8 (`text.presets`). 사용자 프리셋은 `.ecpreset` (`anim.savePreset` / `anim.applyPreset {path}`) — 자주 쓰는 Fluma 연출을 프리셋 파일로 저장해 재사용 가능 ❔.
- MCP 도구 27개: list_commands · describe_command · execute_command · run_script · get_project · get_comp · get_layer · get_property · set_property · add_keyframe · add_effect · list_effects · list_fonts · get_state · render_frame · open_project · save_project · undo · redo · history · script_ui · batch · command_list · command_run · render_preview · command_batch · doc_inspect (✅ tools/list · open_project · add_effect · save_project 호출 확인)

## 5. 빠른 확인 명령
```sh
EC=tools/crafts/effectcraft/app/effectcraft-0.21.0-linux-x86_64/bin/effectcraft-cli
export EFFECTCRAFT_FONT_DIRS=$PWD/public/fonts
$EC commands --filter preset --empty            # 명령 찾기
$EC exec --list --schemas --json --empty        # 모든 명령 + JSON Schema
$EC props Main '#1' --project p.ecproj --flat   # 속성 경로
$EC exec expr.errors '{}' --project p.ecproj --json   # 표현식 오류 검사(렌더 전)
$EC render-frame --project p.ecproj --time 1.5 --max-side 960 --out f.png
$EC bench --project p.ecproj --comp Main --time 1 --n 3   # 레이어 · 효과별 ms (느린 장면 찾기)
```

## 6. 공식 문서
- 저장소: https://github.com/storytold/effectcraft (README 는 앱 안 `share/doc/effectcraft/README.md` 에도 있음)
- 에이전트 사용: https://github.com/storytold/effectcraft/blob/main/docs/agents.md — CLI · MCP 도구 · 쿡북 · 트래킹 · 템플릿 · 함정(레이어 시간 vs comp 시간)
- MCP 규약 · 파일 접근 가두기: https://github.com/storytold/effectcraft/blob/main/docs/mcp.md
- 효과 목록: https://github.com/storytold/effectcraft/blob/main/docs/effects.md
- 알려진 한계: https://github.com/storytold/effectcraft/blob/main/docs/gaps.md (프리셋 76 vs AE 621, 텍스트 레이아웃 이슈 #316 문단 정렬 · CJK 대체 글꼴)
- 제어 채널(앱 창 조작): https://github.com/storytold/effectcraft/blob/main/docs/control-protocol.md
- 사용자 안내: https://github.com/storytold/effectcraft/tree/main/docs/user
- 홈페이지: https://getartcraft.com/apps/effectcraft (미확인 — 이번에 읽지 않음)
