---
name: voice
description: 나레이션 음성을 만들고 장면 길이에 맞춘다. 실측 길이 검사(L14)를 통과할 때까지 문장을 다듬는다.
order: 4
---

# 음성 맞추기

1. `python3 scripts/assemble_audio.py storyboards/<id>.json` — 장면별 TTS 합성(캐시: 제공자·목소리·문장 해시), 길면 최대 1.25배 빠르게, 그래도 길면 잘린다.
2. `python3 scripts/lint.py storyboards/<id>.json` — L14 가 실측 길이 > sec × 1.15 인 장면을 알려 준다. 메시지의 "약 N자 줄이기"를 따른다.
3. 줄일 때는 뜻을 유지하고 조사·부사부터 뺀다. 핵심어(훅과 이어지는 단어, L08)는 남긴다.
4. 다시 1~2. 모든 장면이 1.15배 이내가 될 때까지.

제공자는 환경변수 `TTS_PROVIDER` (기본 edge). Typecast·ElevenLabs 는 키가 있을 때만.
- Typecast: 키는 사용자가 설정 → 생성 · 음성 API 키에 넣는다(`TYPECAST_API_KEY`, 에이전트는 키 파일을 못 읽고 묻지도 않는다). 단어 시각을 API 가 직접 준다(추정 아님). `voice.style` 에 감정 프리셋 `normal · happy · sad · angry · whisper · toneup · tonedown` 중 하나를 쓰면 그 감정, 비우면 문맥으로 고르는 smart. 목소리 id 는 `tc_…`(목록: `python3 scripts/tts.py --voices typecast`). 쓴 글자만큼 유료 크레딧이 빠지니 시험은 짧은 문장으로. 결과 파일 `audio/<id>.wav`, `audio/<id>.timing.json`.

## 레퍼런스 목소리에 맞추기 — 감이 아니라 숫자로 (목소리 복제 아님)
레퍼런스(채널 카드 > 스타일 카드)의 높이 · 억양 폭 · 말끝 처리 · 세기 변화 · 속도에 가까운 목소리와 조절 값을 고른다.
1. `python3 scripts/voice_match.py pick storyboards/<id>.json` — 같은 짧은 샘플 문장으로 후보 목소리를 재서 순위(이미 잰 목소리는 공짜, 새로 재는 건 --max-chars 안에서)
2. `python3 scripts/voice_match.py tune storyboards/<id>.json` — 1위 목소리로 감정(normal · tonedown) × 강도(1 · 0.6) × 말끝(keep · period) 조합, 음높이 · 속도는 레퍼런스에 맞춰 계산
3. `python3 scripts/voice_match.py apply storyboards/<id>.json` → 콘티 voice 에 engine · id · speed · style · intensity · pitch · ending 을 적는다
4. `python3 scripts/assemble_audio.py storyboards/<id>.json` → `python3 scripts/voice_match.py verify storyboards/<id>.json` — **실제로 들어간 전체 나레이션**을 재서 표로 보여 준다
- 사용자가 "더 평평하게 · 낮게 · 딱딱하게"라고 하면 verify 표에서 그 항목을 보고 조절 값(intensity ↓ · pitch ↓ · ending: period)을 바꾼다. 문장(콘티 글)은 건드리지 않는다.
- 조절 값: `voice.ending` = keep · period(합성할 때만 쉼표를 마침표로 — 말끝이 떨어짐, 자막은 그대로) · `voice.intensity` 0~2 · `voice.pitch` 반음(typecast).
- 유료 엔진은 시험마다 크레딧이 든다: 대본 전체를 다시 합성하지 말고 pick · tune 의 샘플(캐시됨)로 고른 뒤 한 번만 전체 합성.

## 음성 엔진 (렌더 엔진처럼 갈아 끼움)
- 엔진 목록 · 라이선스: `voices/<엔진>/voice.json` (edge · supertonic · espeak · melotts · chatterbox · cosyvoice · xtts · typecast · elevenlabs · silent). 설치 여부는 설정 화면 또는 `python3 -c "import sys;sys.path.insert(0,'scripts');import tts;print({n:tts.engine_available(n) for n in tts.list_voice_engines()})"`.
- 기본은 설정(workspace/settings.json 의 voice_engine · voice_id). 영상마다 바꾸려면 콘티에 `"voice": {"engine": "supertonic", "id": "F2"}` 를 적고 `assemble_audio.py` 를 다시 돌린다(엔진 · 목소리가 캐시 키라 자동으로 다시 합성).
- **상업 이용 '불가'(XTTS-v2 등) 엔진은 발행용 영상에 쓰지 않는다.** 사용자가 고르면 라이선스를 한 줄로 알린다.
- edge · typecast 는 단어 타이밍을 정확히 준다. 다른 엔진은 글자 수로 추정하므로 단어 자막이 조금 어긋날 수 있다 — 자막 강조가 중요한 영상이면 알린다.

## 어느 목소리로 읽나(우선순위)
설정(설정 → 미디어 → 음성)에서 고른 목소리가 기본이다. 도구(direct.py · voice_match.py)가 콘티에 적은 목소리는 설정이 있으면 쓰이지 않는다(말 속도 · 감정 값만 쓰인다).
사용자가 채팅으로 "이 영상은 ○○ 목소리로"라고 **직접** 정했을 때만 콘티 `voice` 에 `"source": "user"` 를 함께 적는다 — 그래야 설정보다 앞선다.
