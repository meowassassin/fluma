# SoundCraft 참고 (v0.17.0)

> 한 줄 요약: Pro Tools 류 DAW. 나레이션 · 효과음 · 배경음악을 트랙으로 놓고 플러그인 · 자동화 · 센드를 걸어 `.scraft` 세션과 믹스 WAV 를 만든다. 창 없이 `soundcraft-cli run/script` 로 전부 된다. 바운스 결과에 **LUFS · true peak 가 같이 나온다**.

- CLI: `tools/crafts/soundcraft/app/soundcraft-0.17.0-linux-x86_64/bin/soundcraft-cli`
- 늘 `SOUNDCRAFT_NO_PREFS=1` 을 준다(설정 · 로그 파일 안 씀).

## 지금 Fluma 에서 쓰는 곳

- `engine/craft/audio.py` `mix()` — 세션을 2~4번 짧게 부른다(합쳐 0.5~0.6초).
  1. 짓기: Voice · SFX · Music · Master 트랙, **보이스 체인**(Voice 슬롯 0~2: `eq_7band` hpf 90Hz · 3.5kHz +2dB, `compressor` -22dB 3:1, `de_esser` 6.5kHz), 효과음은 `<id>.sfx.json` 표시마다 `file.import_audio at {"seconds": t}` 클립 하나씩(SFX 페이더 = tokens audio.sfx_volume dB), 덕킹은 `automation.write_range`(base) + 말 구간마다 duck 값 + `set_point` 경사(앞 0.2초 · 뒤 0.3초) → `--save`.
  2. `--in --in-place`: Music 클립을 영상 길이로 `edit.trim_clip`, `edit.fades_create`(in 0.05초 · out s-curve 1.5초, 길이는 샘플), `session.audio_health` → 바운스해 lufs 읽기.
  3. 목표(-14 LUFS)에서 0.5 LU 넘게 벗어나면 Master 1 maximizer 를 `mix.insert_params`(threshold · ceiling -1.5)로 다시 맞추고 바운스(최대 2번). 줄일 때는 리미터 뒤 Master 페이더(`mix.volume`).
- 말소리 · 음악이 없으면(효과음만) 키우지 않는다(`target_lufs: null`). 사람이 고친 세션(해시 다름)은 다시 짓지 않고 health + 바운스만.
- 기록(craft.json audio): `lufs` · `true_peak_db` · `target_lufs` · `edited`. FilmCraft 조립은 lufs 가 -15~-13 이거나 target_lufs 가 null 이면 다시 정규화하지 않는다.
- 안 쓰는 것: 스템 바운스, 리버브 센드.
- 실측: 리미터는 비선형 — 한 번에 안 맞으면 두 번째 조정. 자동화는 페이더를 덮어쓴다(더해지지 않음). Master 페이더는 리미터 뒤.
- `engine/craft/apps/soundcraft/craft.json` 의 `agent: true` → 홈 에이전트에 MCP(`soundcraft-cli mcp --automation-read-root $ROOT --automation-write-root $WRITE`)로 붙는다.

## 헤드리스로 되는 것 / 안 되는 것

| 된다(확인) | 안 된다 · 미확인 |
|---|---|
| 새 세션 · 기존 세션 열기 · 저장(`--in` `--save`) | 녹음(데스크톱 앱만) |
| 오디오 가져오기(wav/flac/mp3/ogg/m4a/mp4 음성…), 24 kHz 원본도 48 kHz 세션으로 자동 변환 | 사이드체인(키 입력) 컴프 — 플러그인에 키 입력 파라미터가 없음. 덕킹은 자동화로 |
| 플러그인 삽입 + 파라미터를 `mix.insert` 한 줄로 | 스크린샷(`ui.screenshot`)은 `soundcraft --control` 앱을 띄워야 함(미확인, 앱 띄우기 안 함) |
| 음량 · 팬 · 플러그인 파라미터 자동화(점 · 구간) | 플러그인 프리셋 목록(`engine.plugins` 에 presets 없음) |
| 버스 · Aux · 센드(리버브 공용) | CLAP/VST3 외부 플러그인(시스템에 없음, 미확인) |
| AudioSuite 오프라인 처리(reverse · time_stretch · normalize · 플러그인 굽기) | |
| Strip Silence(말 구간 자르기) · 페이드 · 클립 게인 | |
| 믹스 바운스(LUFS · peak · true peak 보고) · 스템 바운스 | |

`run` 은 `--keep-going` 을 받지 않는다(그건 `script` 만). 여러 줄이면 `script` 가 편하다.

## 기본 형태

```sh
S=tools/crafts/soundcraft/app/soundcraft-0.17.0-linux-x86_64/bin/soundcraft-cli
export SOUNDCRAFT_NO_PREFS=1
$S run --cmd 'track.new={"kind":"audio","format":"stereo","name":"Voice"}' \
       --cmd 'file.import_audio={"path":"/abs/voice.wav","track":"Voice","at":0,"new_tracks":false}' \
       --bounce mix.wav --end 30 --save s.scraft
$S script steps.txt --in s.scraft --keep-going --bounce mix.wav --save s2.scraft   # 한 줄에 `ID JSON`
$S describe mix.insert --compact      # 명령 하나의 params
$S run --cmd engine.plugins           # 플러그인 30종과 파라미터 id · 범위 · 기본값(JSON)
$S info s.scraft                      # 세션 요약(트랙 · 클립 시작/끝 시각 표)
```

시각 지정(`at` · `start` · `end`): 샘플 수(48 kHz 세션이면 1초=48000) · `{"seconds": 1.38}` · `"0:08.500"` 모두 받는다(셋 다 확인). 지금 `audio.py` 는 샘플로 넣는다.
트랙은 이름이나 id, 클립은 id(`file.import_audio` 결과의 `clip`). 새 마스터 트랙은 이름을 받지 않고 `Master 1` 로 생긴다.

## 쇼츠용 핵심 기능

### 1. 나레이션 보이스 체인 (EQ → 컴프 → 디에서) — 확인
쇼츠는 폰 스피커로 듣는다. 저음 웅웅 제거 + 명료도 + 일정한 크기가 체감 품질을 제일 많이 올린다.
```
mix.insert {"track":"Voice","plugin":"eq_7band","params":{"hpf_on":1,"hpf_freq":90,"high_mid_freq":3500,"high_mid_gain":2.5}}
mix.insert {"track":"Voice","plugin":"compressor","params":{"threshold":-22,"ratio":3,"attack":5,"release":80,"makeup":4}}
mix.insert {"track":"Voice","plugin":"de_esser","params":{"freq":6500,"threshold":-28}}
```
- 결과: 슬롯 0·1·2 에 순서대로 들어감(`{"plugin":"compressor","slot":1,"track":1}`).
- 한 번에 다 하려면 `channel_strip`(gate · comp · 3밴드 EQ · HPF 를 on 토글로).
- 주의: 알 수 없는 파라미터 id 는 `mix.insert_params` 에선 오류, `audiosuite.process` 의 params 에선 **조용히 무시**된다(아래 4).

### 2. 라우드니스 맞추기(쇼츠 −14 LUFS 근처) — 확인
바운스 결과 줄에 측정값이 나온다:
```
{"bytes":8640104,"lufs":-10.27,"path":"t1.wav","peak_db":-1.0,"seconds":30.0,"true_peak_db":-0.93}
```
- ffmpeg ebur128 로 잰 값(−10.3 LUFS)과 일치.
- 맞추는 법: 한 번 바운스 → `lufs` 를 읽고 → 마스터 리미터 threshold 나 `mix.volume` 로 조정 → 다시 바운스. 시험: maximizer threshold −6→−2 로 −10.3 → −13.6 LUFS.
```
mix.insert {"track":"Master 1","plugin":"maximizer","params":{"threshold":-6,"ceiling":-1}}
mix.insert_params {"track":"Master 1","slot":0,"params":{"threshold":-2,"ceiling":-1}}
```
- `ceiling −1` 이면 true peak 가 −1 dBTP 아래로 유지됨(시험값 −0.8~−0.9 dBTP: ceiling 은 샘플 peak 기준이라 true peak 는 살짝 넘을 수 있음 → 여유 있게 −1.5 권장).
- 지금 `audio.py` 는 maximizer 기본값(threshold 0, ceiling −0.3)이라 라우드니스가 들쭉날쭉하다.

### 3. 효과음을 단어 타이밍에 정확히 놓기 — 확인
assemble_audio 가 섞은 SFX 덩어리 대신, 효과음마다 클립으로 놓으면 사람이 SoundCraft 에서 하나씩 밀고 당길 수 있다.
```
track.new {"kind":"audio","format":"stereo","name":"SFX"}
file.import_audio {"path":"/abs/pop.wav","track":"SFX","at":{"seconds":1.38},"new_tracks":false}
file.import_audio {"path":"/abs/swoosh.wav","track":"SFX","at":"0:05.000","new_tracks":false}
clip.gain {"clips":[10,14],"db":-3}
```
- 시각은 `captions.json` 의 `startMs/1000` 을 그대로.
- 결과 `info` 표에 클립 시작 시각이 나와 검증 가능.

### 4. AudioSuite: 역재생 라이저 · 길이 맞춤 · 정규화 — 확인
```
audiosuite.process {"process":"reverse","clips":[12]}                         # swoosh → 역 swoosh(전환 직전 빨려 들어가는 소리)
audiosuite.process {"process":"time_stretch","clips":[6],"params":{"ratio":0.8}}  # 음악 30초 → 24초(clip length 1440000→1152000 확인)
audiosuite.process {"process":"normalize","clips":[3]}
```
- 처리 결과는 새 오디오 파일(`swoosh-reve.wav`, `music-timestre.wav`)로 세션 `Audio Files/` 에 생긴다.
- 주의: time_stretch 는 `ratio` 만 먹는다. `factor` · `length` 같은 틀린 키는 오류 없이 무시되고 길이 그대로 → 처리 후 `--inspect` 로 클립 length 를 꼭 확인.
- `pitch_shift` · `varispeed` · `speed_ramp` · 플러그인 id(예: `lofi`)도 process 로 굽기 가능(파라미터 이름은 미확인, `pitch_shifter` 플러그인 삽입이 확실).

### 5. 배경음악 구간 자동화 · 페이드 — 확인
점 찍기 대신 구간을 한 번에:
```
automation.write_range {"track":"Music","param":"volume","start":{"seconds":10},"end":{"seconds":20},"value":-24}
edit.fades_create {"clip":6,"side":"in","length":24000}                     # 0.5초 페이드 인(length 는 샘플)
edit.fades_create {"clip":6,"side":"out","length":96000,"shape":"s-curve"}  # 끝 2초 페이드 아웃
```
- 시험(Music 스템 mean): 3~8초 −46.7 dB, 12~18초 −56.8 dB(−10 dB 내려감), 마지막 1.5초 −54 dB(페이드).
- 자동화 param: `volume | pan | mute | send_a_level | plugin:a:<id>` — 플러그인 파라미터도 자동화(예: 마지막 장면에 리버브 mix 올리기, 미확인).

### 6. 리버브 버스 · 센드(효과음 · 강조 단어에 공간감) — 확인
```
mix.new_bus {"name":"Verb"}
track.new {"kind":"aux","format":"stereo","name":"VerbAux"}
mix.insert {"track":"VerbAux","plugin":"plate_reverb","params":{"mix":100,"decay":1.8}}
track.input {"tracks":["VerbAux"],"input":"Verb"}
mix.send {"track":"SFX","bus":"Verb","level_db":-8}
```
- 주의: `track.input` 은 `{"input": ...}` 키(“bus” 아님). 틀리면 `bad parameters for track.route: input required`.

### 7. 말 구간 찾기 · 무음 자르기(Strip Silence) — 확인
단어 타이밍이 없을 때(사용자가 녹음 파일만 준 경우) 말 구간을 얻는 방법, 또는 긴 쉼 정리.
```
edit.select {"tracks":["Voice"],"start":0,"end":{"seconds":30}}
edit.strip_silence {"threshold_db":-45,"min_length_ms":250,"pad_before_ms":40,"pad_after_ms":80}
```
- 결과 `{"clips":5}` — 30초 나레이션이 5개 말 구간 클립으로 나뉨(위치는 그대로, 무음만 빠짐). `info` 로 시작/끝 시각 표를 읽어 덕킹 · 컷 포인트에 쓸 수 있다.
- 주의: 간격을 당기지는 않는다(Shuffle 모드 `edit.mode` 로 당기기는 미확인). 당기면 자막 타이밍이 어긋나므로 쓰지 말 것.
- `mode:"separate"` 는 지우지 않고 경계에서 자르기만.

### 8. 스템 바운스(사람이 뒤에서 고치기 쉬움) — 확인
```sh
$S run --in t3.scraft --cmd 'file.bounce_stems={"dir":"/abs/stems","end":{"seconds":30}}'
# → "t3 - Voice.wav", "t3 - Music.wav", "t3 - SFX.wav"
```
- 트랙 페이더 · 자동화 · 페이드가 반영된 트랙별 파일. Aux(리버브) 리턴은 스템에 안 들어간다.
- FilmCraft 에 나레이션 · 음악을 따로 놓고 싶을 때.

### 9. 세션 점검 — 확인
```
session.audio_health {}            # {"healthy":true,"issue_count":0,...} 빠진 미디어 · 클립 범위
session.inspect {"detail":"summary"}   # 트랙 · 클립 · 플러그인 · 자동화 JSON (--inspect --compact 로 끝에 출력)
```

### 그 밖에 쓸 만한 플러그인(파라미터는 `engine.plugins`)
- `lofi`(bits · sample_rate) — 전화 · 무전 · 옛날 라디오 톤 인용 음성
- `pitch_shifter`(semitones) — 짤 · 효과음 변조
- `expander_gate` — 녹음 잡음 정리
- `saturator` · `chorus` · `mod_delay` — 감성 형식 음악 색
- `drum_synth` · `subtractive_synth` · `sampler` — MIDI 로 간단한 비트/효과음 합성(미확인, 쇼츠엔 우선순위 낮음)

## 주의(실측에서 나온 것)

- 자동화 `at` 을 숫자로 주면 **샘플**이다(초 아님). 초로 주려면 `{"seconds":x}`.
- `edit.fades_create` 의 `length` 는 샘플.
- `file.import_audio` 는 `new_tracks:false` 와 `track` 을 같이 줘야 그 트랙에 들어간다(기본은 새 트랙).
- 같은 파일을 두 번 가져오면 소스가 두 개 생긴다(세션 크기 늘어남).
- `--save` 는 세션 옆 `Audio Files/` 에 오디오를 복사한다. 다른 이름으로 같은 폴더에 저장하면 공유됨.
- `run` 에 없는 플래그(`--keep-going`)는 사용 오류(exit 2).
- 출력: 명령마다 `ID: JSON` 한 줄 → 바운스 결과 JSON 한 줄 → 저장 결과 한 줄 순서.

## 전체 명령 분류 (483개, `soundcraft-cli commands`)

| 그룹 | 개수 | 대표 |
|---|---|---|
| view | 97 | 창 · 줌 · 표시(헤드리스엔 의미 적음) |
| edit | 94 | select · strip_silence · fades_create · separate · heal · consolidate · duplicate · repeat · insert_silence · nudge · copy/paste_clip_effects |
| track | 66 | new · rename · color · freeze · bounce · input/output · playlist_* · save_preset/load_preset · elastic |
| event | 35 | tempo · meter · transpose · quantize · beat_detective · identify_beat |
| options | 35 | 환경 설정 토글 |
| clip | 33 | gain · rename · loop · effects_set · effects_render · conform_to_tempo · inspect |
| mix | 29 | volume · pan · mute · solo · insert · insert_params · send · new_bus · instrument · sampler_load |
| setup | 20 | session · hardware · io(헤드리스엔 대부분 무관) |
| file | 17 | import_audio/midi/video · bounce_mix · bounce_stems · export_clips · export_session_text |
| transport | 13 | play · stop · locate(헤드리스 무관) |
| session | 11 | new · open · save · inspect · audio_health · format_time |
| automation | 10 | set_point · write_range · clear · thin · volume_to_clip_gain |
| engine | 6 | commands · plugins · history · parity · clap_plugins · vst3_plugins |
| markers | 6 | add · edit · recall |
| midi | 6 | new_clip · note_add · notes |
| video | 3 | online · offset · list |
| app · audiosuite | 1 · 1 | quit · process |

플러그인 30종: EQ 2 · 다이내믹스 5(compressor · expander_gate · de_esser · maximizer · channel_strip) · 리버브 2 · 딜레이 1 · 모듈레이션 5 · 하모닉 4 · 피치 1 · 기타 7 · 디더 1 · 악기 3.

## MCP (에이전트가 직접 부를 때)

도구: `list_commands` · `execute` · `batch`(최대 1000개, `keep_going`) · `inspect_session` · `new_session/open_session/save_session` · `import_audio` · `bounce_mix`(peak · LUFS 반환) · `parity`. 경로는 `--automation-read-root/--automation-write-root` 밖이면 거절된다. (MCP 서버 직접 구동은 이번에 시험 안 함 — 미확인)

## 공식 문서

- 저장소: https://github.com/storytold/soundcraft (README: 기능 · 에이전트 사용 예)
- CLI: https://github.com/storytold/soundcraft/blob/main/docs/cli.md
- MCP: https://github.com/storytold/soundcraft/blob/main/docs/mcp.md
- 제어 프로토콜(앱 띄워 스크린샷): https://github.com/storytold/soundcraft/blob/main/docs/control-protocol.md
- 빠진 기능 목록: https://github.com/storytold/soundcraft/blob/main/docs/gaps.md
- 홈페이지: https://getartcraft.com/apps/soundcraft
