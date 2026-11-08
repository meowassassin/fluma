# FilmCraft 참고 (v0.17.0)

**한 줄 요약**: Premiere 같은 비선형 편집기(Rust, MIT/Apache-2.0). 명령 716개가 전부 `filmcraft-cli` 로 헤드리스에서 돈다. Fluma 에서는 조립 · 마무리 단계를 맡는다: 컷 · 줌 · 자막 · 소리 균형 · 색 · 최종 내보내기. 사람이 나중에 `.fcproj` 를 열어 조금 고친다.

- CLI: `tools/crafts/filmcraft/app/filmcraft-0.17.0-linux-x86_64/bin/filmcraft-cli`(아래에서는 `$FC`)
- 웹 빌드: `tools/crafts/filmcraft/web/filmcraft-web-0.17.0`(사람이 편집할 때 쓴다. 브라우저 wasm)

## 지금 Fluma 가 쓰는 범위

`engine/craft/edit.py`(`assemble` · `ensure`):
- `file.newSequence`(출력 크기) → `import` → `timeline.place`(V1 영상, A1 믹스) → 장면 경계마다 `markers.add`('1. 훅' · 대사 앞 28자 · 훅 rose / 끝 green / 나머지 blue).
- 내보내기는 **'YouTube Shorts 1080×1920' 프리셋**(-14 LUFS · -1 dBTP). `export --settings` 로 프리셋 위에 겹친다(시험함): `effects.loudness.enabled: false`(SoundCraft 가 이미 -14 근처이거나 일부러 안 키운 소리), 1080×1920 이 아니면 `frameSize` · 비트레이트.
- 저장하지 않는 `run` 으로 `markers.exportCsv` → `edit/<id>.markers.csv`, `file.exportFrame` → `edit/<id>.thumb.png`(훅 장면, primary 낱말 0.7초 뒤).
- 자막은 EffectCraft 가 그리고, SRT 는 업로드용으로 파이썬이 따로 쓴다.

`engine/craft/adapters/filmcraft.py` POST(`screen` · `video` · `web`): `zoom`(scale · position 키프레임, 프레임 경계 ticks, bezier, 0.3초 들고 나기), `blur`(gaussian_blur + 사각 `masks.add`, 원본 픽셀 좌표라 줌을 따라감), `speed`(`timeline.razor` → `clip.speedDuration` ripple). 'Match Source – Adaptive High Bitrate' 프리셋 `--no-audio` → `<id>.fc.mp4`, 편집 파일 `<id>.fcproj`.

실측 주의:
- **loudness 는 gain 만**(리미터 없음, -1 dBTP 에 막힘). -35.7 LUFS 믹스는 -19.2 까지만 오른다 → -14 는 SoundCraft 가 맞춘다.
- 속도를 바꾼 뒤 키프레임은 클립 안쪽 시각을 따라간다(조각마다 복사됨, 렌더 확인). 빨리 감은 구간 안의 줌은 같이 빨라진다 — 줌은 그 구간 밖에.
- 녹화 끝 20초 tpad 까지 다시 렌더해서 10초 녹화에 34~64초.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(시험함) | 안 된다 / 미확인 |
|---|---|
| 프로젝트 · 시퀀스 생성, 가져오기, 배치, 트림, 레이저 | 음성 인식 `transcript.generate` · `sequence.transcribe`: 모델이 없어 꺼져 있음(`transcript.models` → `available:false`). 내려받기는 금지라 미확인 |
| 효과 · 키프레임 · 마스크 · 전환 · 프리셋 · Lumetri 프리셋 | 자연스러운 TTS(Kokoro): 내려받기 필요. 기본 음성 `basic-female/male` 은 영어 전용이고 기계음이라 쓸모가 적다 |
| 그래픽 텍스트 · 도형 · 그래픽 템플릿(.fcgt) 적용과 저장 | UI 조작(`ui_*`)은 `--bridge` 와 데스크톱 앱이 있어야 한다. 헤드리스에서는 안 된다 |
| 자막 트랙 가져오기 · 스타일 · 번인 · SRT 사이드카 | Adobe `.mogrt` 는 거부된다(`.fcgt` 만) |
| Essential Sound(유형 · 프리셋 · 더킹 · 라우드니스 맞춤) | `masks.track`(마스크 추적)과 `warp_stabilizer` 는 미확인 |
| 트랜스크립트 직접 넣기 → 자막 만들기 · 군말 · 쉼 지우기 | `clip.remix`(음악 길이 리믹스)는 미확인 |
| 장면 컷 감지, 속도, 마커, 프레임 PNG, OTIO 내보내기 | |
| 한 프레임 렌더 `render --seconds S --out f.png --scale 0.25`(0.1~0.5초) | |

**공통 규칙**
- 시간 단위: 1초 = `254016000000` ticks. 대부분의 명령은 `seconds=` · `frame=` · `timecode=` 도 받는다.
- 키프레임 `time` 은 **시퀀스(타임라인) 시각**이다. 클립 안쪽 시각이 아니다. 렌더해서 확인함.
- 여러 단계는 `run script.jsonl` 로 한 번에 돌린다. 한 줄에 `{"id","params"}` 하나씩 쓰고, `#` 주석을 쓸 수 있다. `--save` 로 저장하고, `--keep-going` 이면 실패한 줄이 있어도 계속 간다.
- id 는 결과 JSON 에서 받는다(`import` → `items`, `timeline.place` → `clips`). `inspect sequence` 를 보면 트랙(`video[]` · `audio[]`) 아래 `items[].clip` 에 있다.
- 선택에 의존하는 명령도 `clips:[id]` · `clip:id` 를 주면 선택 없이 돈다.
- 한국어 글꼴: `fonts.list` 에 **Pretendard 가 없다**(시스템에 설치되지 않음). `"Noto Sans CJK KR"`(Black · Bold 등)은 바로 쓰인다. Pretendard 를 지정하면 다른 글꼴로 대체된다.

## 쇼츠용 핵심 기능

### 1. 세로 시퀀스 + 배치 (verified, 이미 쓰는 중)
```sh
$FC --compact --save-as p.fcproj exec file.newSequence '{"name":"t1","width":1080,"height":1920,"fps":30}'
$FC --compact --project p.fcproj --save import a.mp4 voice.wav music.wav      # → {"items":[8,9,10]}
```
```jsonl
{"id":"timeline.place","params":{"item":8,"track":"V1","seconds":0,"insert":false,"audio":false}}
{"id":"timeline.place","params":{"item":9,"track":"A1","seconds":0,"insert":false,"video":false}}
{"id":"timeline.place","params":{"item":10,"track":"A2","seconds":0,"insert":false,"video":false}}
```
`items:[...]` 를 주면 여러 클립을 이어 붙여 한 번에 놓는다. `sourceIn` · `duration` 으로 원본의 일부만 놓을 수 있다.

### 2. 가로 화면 녹화를 세로에 맞추고 펀치인 줌 (verified)
실제 화면(1920×1080 녹화)을 세로에 넣고, 설명하는 곳으로 확대한다.
```jsonl
{"id":"clip.fitToFrame","params":{"clips":[13]}}
{"id":"effects.setParam","params":{"clip":13,"effect":"motion","param":"scale","value":56.25,"time":1524096000000,"keyframe":true}}
{"id":"effects.setParam","params":{"clip":13,"effect":"motion","param":"scale","value":140,"time":2032128000000,"keyframe":true}}
{"id":"effects.setParam","params":{"clip":13,"effect":"motion","param":"position","value":[700,960],"time":2032128000000,"keyframe":true}}
```
- 결과: `fitToFrame` → `{"scale":56.25}`(위아래가 검은 레터박스). 6초에서 8초 사이에 140% 로 커지는 것을 렌더로 확인했다.
- `clip.fillFrame` 은 화면을 꽉 채운다(양옆이 잘림). 보간은 `effects.setInterpolation`(`easeIn|easeOut|bezier|hold`…)로 바꾼다.
- 키프레임 없이 클립 길이 동안 천천히 다가가기(켄 번스)는 `grow` 효과로 한다(verified). 반대는 `shrink`, 이동은 `move`.
```jsonl
{"id":"effects.apply","params":{"clips":[12],"effect":"grow"}}
{"id":"effects.setParam","params":{"clip":12,"effect":3,"param":"to","value":130}}
{"id":"effects.setParam","params":{"clip":12,"effect":3,"param":"easing","value":"Ease In and Out"}}
```
`effect` 는 클립 효과 목록의 번호다. 0 motion, 1 opacity, 2 time_remap 이 기본이라 새로 붙인 효과는 3번부터다. 정확한 번호는 `effects.apply` 결과의 `index` 를 쓴다.

### 3. 화면 일부 확대 · 가리기 (verified)
- **돋보기**(UI 버튼 · 숫자 강조). `center` 는 원본 픽셀 좌표다.
```jsonl
{"id":"effects.apply","params":{"clips":[13],"effect":"magnify"}}
{"id":"effects.setParam","params":{"clip":13,"effect":3,"param":"center","value":[1400,700]}}
{"id":"effects.setParam","params":{"clip":13,"effect":3,"param":"magnification","value":300}}
{"id":"effects.setParam","params":{"clip":13,"effect":3,"param":"size","value":260}}
```
- **개인정보 흐림**(이메일 · 키 · 계정명). 흐림 효과에 사각 마스크를 건다. `center` · `size` 는 원본 픽셀 좌표다.
```jsonl
{"id":"effects.apply","params":{"clips":[13],"effect":"gaussian_blur"}}
{"id":"effects.setParam","params":{"clip":13,"effect":3,"param":"blurriness","value":60}}
{"id":"masks.add","params":{"clip":13,"effect":3,"shape":"rectangle","center":[1500,300],"size":[500,200]}}
```
  모자이크로 가리려면 `mosaic` 를 쓴다. 집중 효과로는 `focus_blur`, 둥근 카드 모양의 화면은 `rounded_crop`(radius · border)이 있다.
- 내장 효과 프리셋 `Spotlight`(원 안을 밝게) · `Soft Vignette` · `PiP 35% Upper Right` 는 `presets.apply` 로 붙인다(PiP 는 미확인).

### 4. 훅 제목 · 강조 텍스트 (verified)
```jsonl
{"id":"graphics.newText","params":{"text":"이거 모르면 손해","position":[540,420],"size":110,"font":"Noto Sans CJK KR","fontStyle":"Black","seconds":3,"time":0}}
{"id":"graphics.set","params":{"clip":17,"layer":0,"props":{"align":"center","fill_color":"#ffffff","stroke":true,"stroke_color":"#000000","stroke_width":12,"background":true,"background_color":"#ff3b30","background_opacity":100,"background_size":24,"background_radius":20}}}
```
- 결과: 빨간 둥근 박스 안에 흰 글씨가 검은 외곽선과 함께 나온다(렌더 확인). `background_opacity` 를 주지 않으면 박스가 반투명이다.
- 점 텍스트는 줄바꿈을 하지 않아 긴 문장이 화면 밖으로 나간다. 긴 문장은 `box:[w,h]`(문단 텍스트)로 넣고 `graphics.list` 의 `overflow` 를 확인한다.
- 글자별 색(키워드만 노란색)은 `graphics.setCharStyle {"start","end","style":{"color":...}}` 로 한다(미확인).
- 등장 애니메이션: `graphics.set` 에 `keyframe:true` 와 `time` 을 주거나, 전환 `text_animator` · `typewriter` 를 쓴다(미확인).

### 5. 그래픽 템플릿(.fcgt): 한 번 만들고 값만 바꿔 재사용 (verified)
```jsonl
{"id":"graphics.template.export","params":{"clip":17,"name":"Hook Title KR","category":"Fluma","controls":[{"layer":0,"param":"text","name":"Hook"},{"layer":0,"param":"background_color","name":"Box"}],"path":"/abs/hook.fcgt"}}
{"id":"graphics.template.apply","params":{"template":"/abs/hook.fcgt","values":{"hook":"AWS 요금 폭탄 피하기","box":"#0a84ff"},"time":0}}
```
- 결과: 파란 박스에 새 문구가 들어간 것을 확인했다. 값을 바꿀 때는 `graphics.template.set {"clip","values":{...}}`.
- 컨트롤 id 는 이름을 소문자로 바꾼 것이다(`Hook` → `hook`).
- 내장 템플릿 8종(`graphics.template.list`): lower-third-slab · lower-third-rule · title-centered · title-boxed · end-credits-roll · callout-pointer · callout-tag · ticker-crawl. **모두 1920×1080 용이라** 세로에서는 작게 왼쪽에 붙는다(callout-tag 로 확인). 세로용은 위처럼 직접 만들어 `.fcgt` 로 저장해 두는 편이 낫다.

### 6. 자막: 가져오기 · 스타일 · 번인 (verified)
```jsonl
{"id":"captions.import","params":{"path":"/abs/subs.srt","name":"KO"}}
{"id":"captions.setStyle","params":{"track":"C1","font":"Noto Sans CJK KR","fontStyle":"Bold","size":72,"color":"#ffffff","background":false,"outline":8,"outlineColor":"#000000","align":"center","anchor":"bottom","margin":0.22}}
```
- 번인과 SRT 사이드카를 함께 내보낸다.
```sh
$FC --compact --project p.fcproj exec file.exportMedia '{"path":"/abs/out.mp4","preset":"YouTube Shorts 1080×1920","burnCaptions":true,"captionSidecar":"srt","wait":true}'
```
  결과: 한국어 자막이 하단 22% 높이에 흰 글씨와 검은 외곽선으로 그려지고, 너비에 맞춰 자동으로 줄바꿈된다. `out.srt` 도 함께 생긴다.
- 주의: **번인은 느리다**. 3초에 9.4초가 걸렸다(번인 없이는 1.1초). 60초짜리 쇼츠면 3분쯤 걸린다.
- 자막 편집 명령: `captions.setText` · `setTimes` · `split` · `merge` · `list` · `export {"path":"x.srt"}`. 내보내기 형식은 srt · vtt · scc · ttml 등이다.
- 기본 엔진에서는 EffectCraft 가 이미 자막을 그리므로 번인하면 두 번 겹친다. 번인은 자막 없는 재료(실제 녹화)를 쓸 때나, 사람이 SRT 를 고쳐 다시 내보낼 때만 쓴다.

### 7. 트랜스크립트로 편집: 우리 단어 시각을 넣고 자막 · 군말 · 쉼 정리 (verified)
Whisper 없이도 된다. Fluma 의 `data/public/audio/<id>.captions.json` 단어 시각을 그대로 넣는다(media ticks).
```jsonl
{"id":"transcript.set","params":{"item":10,"transcript":{"language":"ko","speakers":[{"name":"나레이터"}],"words":[{"text":"이거","start":50803200000,"end":152409600000,"speaker":0}]}}}
{"id":"transcript.removeFillers","params":{"fillers":["음","어"]}}
{"id":"transcript.removePauses","params":{"minSeconds":0.6,"keepSeconds":0.15}}
{"id":"transcript.createCaptions","params":{"maxChars":12,"lines":1,"minSeconds":0.6,"maxSeconds":2.5,"name":"auto"}}
```
- 결과: 군말 1개(0.3초)와 쉼 1개(1.67초)가 지워지고, 모든 대상 트랙(V1 · A1 · A2)이 함께 앞으로 당겨졌다(리플 삭제). `createCaptions` 는 12자 단위로 자막 4개를 만들었다.
- 주의: **자막은 컷을 다 한 뒤에 만든다.** 먼저 만들었더니 지운 군말 "음"이 자막에 남았다. `transcript.search {"query":"설정"}` 은 단어 번호를 돌려주고, `transcript.extract {"from":5,"to":7}` 은 그 구간만 리플로 잘라낸다.
- 실제 화면 녹화(사람 말소리)에서 군말을 없애는 데 특히 좋다. 단, 단어 시각을 얻으려면 다른 STT 결과가 필요하다(내장 Whisper 는 모델을 내려받아야 해 미확인).

### 8. 소리 균형: Essential Sound (verified)
```jsonl
{"id":"essentialSound.setType","params":{"clips":[14],"type":"dialogue"}}
{"id":"essentialSound.setType","params":{"clips":[15],"type":"music"}}
{"id":"essentialSound.applyPreset","params":{"clips":[14],"preset":"Podcast Voice","type":"dialogue"}}
{"id":"essentialSound.set","params":{"clips":[15],"key":"ducking.reduceDb","value":-18}}
{"id":"essentialSound.generateDucking","params":{"clips":[15]}}
{"id":"essentialSound.autoMatch","params":{"clips":[14,15]}}
```
- 결과: 더킹 키프레임이 나레이션 구간에 -18dB 로 생기고, 0.8초에 걸쳐 원래 크기로 돌아온다. `autoMatch` 의 기본 목표는 대사 -23 / 음악 -25 LUFS(방송 기준)다. 쇼츠는 `target` 을 주거나, 내보낼 때 정규화한다(아래).
- 대사 프리셋: Balanced Voice · Clean Up Noisy Dialogue · Podcast Voice · Dry Up a Roomy Voice · Phone Call. EQ 프리셋은 Radio Voice · Telephone 등 8종이다.
- SoundCraft 가 이미 믹스했다면 이 단계는 겹친다. 실제 녹화의 현장음 · 사람 말소리를 다듬을 때 쓴다.

### 9. 쇼츠용 내보내기 프리셋 + 라우드니스 (verified)
- `export --list-presets` 에 42종이 있다. 세로용은 `YouTube Shorts 1080×1920` · `TikTok 1080×1920` · `Instagram Reels 1080×1920` · `Social Vertical 1080×1920` 이다.
- `YouTube Shorts` 프리셋은 H.264 12Mbps, 화면을 채우는 스케일, **-14 LUFS 정규화 · 트루피크 -1dBTP** 가 들어 있다. ebur128 로 재 보니 Integrated **-14.0 LUFS** 였다.
```sh
$FC --compact --project p.fcproj export out.mp4 --preset "YouTube Shorts 1080×1920"
$FC --compact --project p.fcproj export out.mp4 --format h264 --start 0 --end 4     # 구간만
```
- 주의: CLI `export --settings` 에는 `loudnessLufs` 같은 평평한 키를 넣을 수 없다(`unknown key` 오류). 평평한 키는 `exec file.exportMedia '{...,"loudnessLufs":-14,"wait":true}'` 로 준다.
- 속도: 효과 없는 3초 h264 는 1.1~1.7초(GPU auto/off 비슷), 효과 · 그래픽이 있는 3초는 3.7초가 걸렸다.

### 10. 장면 전환 (verified)
```jsonl
{"id":"sequence.applyVideoTransition","params":{"clip":13,"effect":"whip","frames":10,"edge":"in","align":"center"}}
```
- 결과: 5.95초에 휩 팬(모션 블러)이 걸린 것을 렌더로 확인했다. 쇼츠에 맞는 것: `whip` · `cross_zoom` · `zoom_blur` · `flash` · `glitch` · `push` · `slide` · `light_leak` · `dip_to_white`.
- 전체 목록은 `effects.list kind=VideoTransition`(전환 120개, 레거시 포함). 오디오 전환은 `sequence.applyAudioTransition`(constant_power 등).
- 내장 효과 프리셋(`presets.list`) 9종: Fade In/Out · Blur In/Out · Mosaic In · Soft Vignette · Spotlight · Warm Tint · PiP. `presets.apply {"preset":"Fade In","clips":[12]}` 로 붙였다(verified).

### 11. 색: Lumetri 프리셋 · 룩 LUT (verified: 프리셋 적용)
```jsonl
{"id":"lumetri.applyPreset","params":{"name":"Boost Vibrance","clips":[12]}}
```
- 프리셋 18종: Teal Shadows Warm Skin · Golden Dusk · Steel Blue · Hard Sun · Faded Print · Warm Negative · Neutral Mono · Lift Shadows · Protect Highlights · Boost Vibrance 등.
- 룩 LUT 는 `lumetri.setLook {"clip","lut":"builtin:look-teal-orange"}` 로 건다(미확인). 카메라 로그 LUT 12종도 있다.
- 장면 사이 색 맞추기는 `lumetri.applyMatch` 로 한다(미확인).
- 실제 화면(UI 캡처)은 색을 건드리지 않는 것이 원칙이다. 현장 사진 · 영상(감성 · 광고 형식)에만 쓴다.

### 12. 기타 쓸 만한 것 (verified)
- **장면 컷 감지**: 녹화본의 화면 전환 지점에서 자른다. `clip.sceneEditDetection {"clips":[17],"applyCuts":true,"generateMarkers":true,"wait":true}` 결과 → `cuts:[2s,4s]`(정확).
- **속도**: `clip.speedDuration {"clips":[13],"speed":200,"ripple":true}`. 긴 설치 과정을 빨리 감을 때 쓴다. 클립 속도는 2.0 이 됐지만 시퀀스 길이는 그대로였다(다른 트랙 때문으로 보임).
- **자동 리프레임**: `effects.apply effect=auto_reframe`. params: `aspect`(Vertical 9:16) · `zoom` · `offset` · `preset`. 적용은 됐지만 화면이 어떻게 바뀌는지는 미확인.
- **마커 = 사람에게 남기는 메모**: `markers.add {"target":"program","seconds":3,"name":"훅 끝","comment":"여기서 화면 전환","color":"rose"}` 를 남기고, `markers.exportCsv` 로 목록을 뽑는다. 에이전트가 "확인 필요" 지점을 표시해 두면 사람이 고칠 곳만 보면 된다.
- **썸네일**: `file.exportFrame {"path":"/abs/thumb.png","format":"png","time":ticks}` → 1080×1920 PNG.
- **교환 형식**: `file.exportInterchange {"format":"otio","path":...}`(fcpxml · xml · edl · aaf 도 된다). 다른 편집기로 넘길 때 쓴다.
- **효과 묶음 저장**: `presets.save {"clip","name"}` 와 `presets.export`. Fluma 고유의 "줌 + 흐림" 같은 묶음을 재사용할 수 있다(미확인).

## 추천 조립 순서 (edit.py 확장안, 미구현)
1. 시퀀스 · 배치(지금과 같음)
2. 실제 녹화 클립: `fitToFrame`/`fillFrame` → 설명 시점에 줌 키프레임, 돋보기, 개인정보 흐림
3. 장면 경계에 `whip` 같은 전환
4. 녹화에 사람 말소리가 있으면: `transcript.set` → `removeFillers` / `removePauses` → `createCaptions`
5. 확인이 필요한 곳에 마커
6. `YouTube Shorts 1080×1920` 프리셋으로 내보내기(-14 LUFS)와 `file.exportFrame` 썸네일

## 전체 명령 분류 (716개, `commands --json`)
| 그룹 | 개수 | 대표 명령 |
|---|---|---|
| graphics | 83 | newText · set · setCharStyle · template.apply/export · align* · setRoll |
| file | 57 | newSequence · import · exportMedia · exportFrame · exportInterchange · save · newColorMatte · newAdjustmentLayer |
| clip | 57 | fitToFrame · fillFrame · speedDuration · sceneEditDetection · frameHold · audioGain · nest · remix |
| timeline | 57 | place · move · trim · razor · roll · slip · slide · delete · setTrack |
| sequence | 51 | settings · applyVideoTransition · addTracks · closeGap · simplify · transcribe · inspect |
| project | 40 | inspect · items · moveToBin · freeform.* (패널 표시) |
| edit | 39 | undo/redo · pasteAttributes · rippleDelete · find · label.* |
| multicam | 35 | 멀티캠 앵글 전환 |
| markers | 33 | add · addRange · addChapter · edit · exportCsv · markIn/Out |
| trim | 24 | 트림 모드 · 편집점 선택 |
| captions | 23 | import · export · setStyle · add · setText · setTimes · list |
| mixer | 20 | setStrip · addInsert · addSend · writeAutomation |
| export | 19 | presets.list/get/save · queue.* · quick · resolve · formats |
| media | 17 | relink · replaceFootage · createProxies · status |
| effects | 16 | apply · setParam · addKeyframe · setInterpolation · list |
| shortcuts 16 · playhead 14 · transcript 14 · masks 12 · mediaBrowser 10 · essentialSound 9 | | transcript.set/removePauses · masks.add/track · essentialSound.autoMatch |
| source 7 · lumetri 7 · presets 7 · tts 7 · audio 5 | | lumetri.applyPreset/setLook/applyMatch · tts.create |
| 나머지(prefs · labels · clipMixer · lut · history · colors · jobs · mediaCache · events · metadata · perf · command · state · color · fonts · scopes · help) | 32 | lut.list · fonts.list · scopes.read · jobs.list · events.list |

효과 카탈로그(`effects.list`): 304개. 비디오 효과 약 150개(Transform 13 · Distort 9 · Blur 9 · Keying 6 · Lights & Glows 8 등), 오디오 효과 약 58개(denoise · speech_enhance · dynamics · mastering 등), 비디오 전환 120개, 오디오 전환 3개. 파라미터 상세는 `effects.list kind=Video detail=true` 의 `paramInfo`(기본값 · 범위 · 선택지)에 있다.

## 그 밖의 주의
- 같은 프로젝트를 `--save` 로 저장하는 실행은 잠금 파일(`.<이름>.lock`)로 차례를 지킨다. 병렬로 돌려도 편집이 사라지지 않는다.
- 없는 미디어는 대체 화면으로 렌더되고 exit 1 이 난다(`--allow-offline` 로 허용). 경로는 절대경로로 준다.
- 명령 하나가 지금 켜져 있는지는 `describe <id>` 의 `enabled` 로 본다. 열린 시퀀스가 없으면 대부분 false 다.
- MCP: `filmcraft-cli mcp --project p.fcproj`(헤드리스) 또는 `--bridge 127.0.0.1:PORT`(실행 중인 앱). 도구는 command_run · command_batch · render_frame · doc_inspect 등이다. 이번에는 MCP 를 돌려 보지 않았다(미확인).
- 웹 빌드는 mp4 안의 AAC 를 못 읽는다(edit.py 주석). 그래서 사람 편집용 프로젝트에는 영상과 소리를 나눠 넣는다.

## 공식 문서
- 저장소: https://github.com/storytold/filmcraft (README · ROADMAP)
- 에이전트 · CLI · MCP: https://github.com/storytold/filmcraft/blob/main/docs/agents.md
- 제어 채널(bridge): docs/control-protocol.md
- 자막: docs/captions.md
- 그래픽 · 템플릿: docs/graphics.md
- 트랜스크립트 편집: docs/transcripts.md
- 프로젝트 파일 형식: docs/project-files.md
- 웹 빌드: docs/web.md
- 미구현 목록: docs/gaps.md
- 홈페이지: https://getartcraft.com/apps/filmcraft (소개 · 다운로드뿐, 자동화 설명 없음)
- 위키: 따로 내용 없음(미확인)
