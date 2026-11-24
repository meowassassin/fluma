# Changelog


## Unreleased

- 형태(form): 캐릭터 · 동물 · 사물을 도형 데이터(SDF)로 빚고 화풍(flat · cel · sketch · clay · vector)으로 그림 — 뼈대(사람 · 네 발 · 새) · 표정 · 머리 · 손, 걷기 · 뛰기 · 계단 · 소품 · IK, 시선 · 카메라 연출, 반복 프레임 움직임. 사람은 실제 자료 또는 형태(실존 인물 닮게 금지) / Form: characters, animals and props built from shape data, with rigs, motion in a world, gaze and camera directing
- 3D 렌더 화풍 `render`: 재질(plastic · metal · liquid · glass · fuzz · wood · matte) · 스튜디오 주변 빛 · 배경 · 바닥 · 초점 흐림, 같은 카메라의 투명 층 · 3D→화면 좌표 / 'render' style: materials, studio environment light, backdrop and floor, depth of field, transparent layers, 3D-to-screen projection
- 제작 순서: 대본 먼저(`bundle.py script` → `apply`), 렌더 전 정지 화면 검토가 막을 것을 찾으면 렌더하지 않고 멈춤, 화면 AI 티 검사(`visual_tell.py`) · 품질 관문 / Script first; produce stops at the pre-render review when it finds blocking problems; visual AI-tell check and quality gate
- 일괄 제작(`batch.py` — 주제마다 새 영상이 자동 진행으로 완성까지) · 자동 진행 스위치 · 서버 재시작 뒤 이어서 · 연출 모드(쇼츠 · 애니메이션 · 만화 · 영화) · 모티프가 컷을 잇는 전환(`carry`) · 한국어 OFL 글꼴 40종 · YouTube 여러 계정과 업로드 제목 · 설명 자동 · 실제 그림 검색(`ref_image.py`, Google · Brave 키 선택) / Batch production, autopilot, direction modes, motif transitions, Korean fonts, multiple YouTube accounts, reference image search
- 속도: 바뀐 구간을 남은 메모리 안에서 병렬 렌더(`FLUMA_SEG_JOBS`) · 검토 정지 화면 3장씩(`FLUMA_STILL_JOBS`) · 형태 층은 한 번만 그림 · 형태 캐시 압축 + 상한(`FLUMA_FORM_CACHE_GB`, 기본 12) · 구간 캐시는 파일 내용 · 렌더러 · 글꼴 기준 / Parallel segment renders within free memory, faster form layers, capped form cache
- 고침: 두 번째 carry 전환이 검게 나오던 문제 · 어떤 음성 실패든(Edge 403 포함) 다음 엔진으로 · 장면 코드 색에 `'#hex'` 글자 허용 · 콘티의 형식에 없는 칸은 빼고 알림 · L08 이 다시 쓸 훅 낱말을 알려 줌 · 획만 준 도형은 속이 빈 채로 · 단계 시간 초과 때 프로세스 묶음째 종료 · 제작 잠금 · Wikimedia 429 · HTTPS 인증서 오류 · 설정의 agent.maxConcurrent 유지 / Fixes: black second carry transition, TTS fallback on any failure, '#hex' colours in scene code, unknown storyboard fields dropped, L08 names hook words, and more
- 기획 · 경로(`engine/gen/`): 기획 기록 → 경로 고르기(실제 자료 편집 · 클립 재편집) → Craft 초안 → 타임라인 편집기 최종본 → 게시 · 분석 되먹임 / Plan record, route choice (material editing or clip re-edit), Craft draft → editor final, publish and feedback
- 자동화(시리즈 · n8n) · 라이브러리 탭 제거 / Removed the Automation and Library tabs
- 오픈라우터 제거: 오픈라우터 키 · 보기(VL 영상 이해 · 초안 비평 · 순간 찾기 · 기준점) · 듣기(원격 받아쓰기) · 찾기(임베딩) · 비용 관문을 없앰. 초안 검토는 수치 검사 + 에이전트가 프레임 모음을 직접 보기, 받아쓰기는 로컬 faster-whisper, 화면 분류는 로컬 CLIP. 음성(Typecast · ElevenLabs) · 스톡(Pexels · Pixabay) · 음악 찾기(YouTube Data API) 키는 그대로 / Removed OpenRouter: the key, VL see/critique/moments/anchor, remote transcription, embeddings and the cost gate; voice, stock and music-search keys are unchanged
- 그리기 · 생성 정리: 인물 · 장면을 직접 그리는 경로(vcdraw · vectorize · 장면 그림 · illustrate · character · scene-art 스킬)와 Blender 스킬 팩을 지우고, 영상 생성 재료(gen_video · make.video)를 없앰 — 화면은 실제 자료 · 목업 · 도표 / Removed drawing paths, Blender skills and video-generation materials
- 영상 디자이너 스킬(`designer`): 그림 대신 레이아웃 · 자막 타이포 · 색 · 안전 영역 · 실제 화면 앉히기를 레퍼런스 실측(쇼츠 28편)으로 정한다 · 감독 · 작가와 함께 늘 적용 / Designer skill grounded in measured reference shorts
- 속도: 스킬 본문을 핵심만 남기고 상세는 필요할 때 읽는 reference.md 로(매 턴 프롬프트 약 40% 줄임) · 콘티는 한 번에 쓰고 값은 knob 으로 / Leaner per-turn skill prompts
- Blender · MuJoCo(물리) 제거 — 2D(실제 화면 · 그림 · 디자인 · 실제 자료)에 집중: 3D 장면 스크립트 · 에셋 라이브러리 · 모캡 · 물리 계산 · Blender 스킬 팩을 빼고, 3D 제품(`model3d`)은 SolidCraft · TextureCraft 로, 실사 합성(`live`)은 글자 · 그림만 / Removed Blender and MuJoCo physics to focus on 2D; `model3d` now renders via SolidCraft + TextureCraft, `live` overlays text and images only
- 대화창: 도구 호출을 제작 단계(레퍼런스 분석 · 사실 조사 · 기획 · 콘티 · 목소리 · 음악 · 장면 · 값 조정 · 초안 · 최종 렌더)로 묶고, 결과(값 조정 · 음악 · 목소리 · 소리)는 칩으로 · 누르면 명령 · 경로 펼침 / Chat groups tool calls into production stages with result chips
- 고침: 바뀐 조립 프로젝트를 '사람이 고친 것'으로 계속 써서 화면이 검게 · 멈춰 나오던 문제(백업하고 다시 지음, 잠그려면 edit.keep) · 이어 말하기가 숫자 읽기 · 문장부호 차이로 장면 경계를 밀던 문제(다음 장면 첫 낱말 · 쉼으로 경계, 어긋나면 장면별 합성) · 에이전트의 `cd … && …` 명령이 막히던 문제 / Fixed stale FilmCraft reuse (black/frozen output), continuous-voice scene split drift, blocked `cd` in agent commands
- 실제 화면 기반 UI 애니메이션(`engine/capture/uianim.py`): 디자인으로 다시 그린 화면을 시간표대로 프레임마다 그려 데모 영상 · GIF / UI animation renderer for product demos
- 대화로 고치기 — 값으로: 에이전트가 코드 · 좌표 · 전체 렌더 대신 요소의 값(조정 adjust · 스크립트 args · 장면 칸)을 바꾸고 바뀐 부분만 다시 지어 바로 보여 줌(`engine/story/knob.py`). 실측(카톡 영상): 값 바꾸기 + 정지 화면 1.6초 · 장면 하나 영상 7.5초(예전 한 번 고치는 데 4~17분) / Edit by values: change knobs, rebuild only what changed, preview in ~2 s (scene clip ~8 s)
- 에이전트 대화 갈아타기: 몇 턴마다 새 대화로 시작하고 상태(콘티 값 · 사용자 지시 그대로 · 직전 답)는 코드가 넘김 — 턴 비용이 쌓여 커지지 않게 / Agent conversations rotate with a code-built state brief so per-turn cost stays flat
- 남은 승인 · 관문 · '렌더 버튼' 안내 삭제 — '좋아'면 에이전트가 바로 최종 렌더 · 화풍 거리(최근 영상과 너무 닮으면 알림, 로컬 CLIP) / Removed leftover approvals, auto final render, style-distance warning
- 장면 일부 렌더(`--scenes`)가 이웃 장면을 몰라 멈추던 문제 · 배치만 바꿔도 재료를 다시 만들던 문제(adjust 등은 재료 열쇠에서 뺌) / Fixed partial-scene render crash; placement-only fields no longer rebuild materials
- 제품 소개 · 데모 영상(`engine/capture/showcase.py`): 실제 앱을 대본대로 녹화 → 소개 영상(오려 띄우기 · 3D 기울기 · 글자 카드) 또는 데모 GIF(자동 줌 · 빨리 감기) / Showcase & demo GIF capture
- 제작 자동: '제작 시작' 버튼을 없애고 콘티가 검사를 통과하면 같은 턴에 초안까지, 고르기를 기다리던 단계는 추천안으로 진행 · 에이전트 쓰기 권한이 막히던 문제 / Auto production: no "start" button, recommended options without waiting, fixed blocked agent writes
- 배경 음악 자동: 넣을지 정하고(레퍼런스 음악 · 나레이션 · 형식) 요즘 쓰이는 곡 중 맞는 무료 곡을 박자 · 힘 있는 구간으로 고름, 상업 유행곡은 업로드 때 붙일 곡으로 안내(설정에서 직접 넣기 가능) · YouTube Data API 키 선택 / Automatic background music from free libraries, trending commercial songs suggested for upload
- 효과음: 음악이 깔리면 기본으로 빼고, 고음질 CC0 녹음(48kHz 스테레오)으로 교체 / Sound effects: off under music by default, high-quality CC0 recordings
- 음성: 설정을 한곳(미디어 → 음성)으로 합치고 '자동'(기본) — 엔진을 가로질러 레퍼런스 화자와 닮은 목소리 · 말 속도 / Voice: one settings place, Auto picks the closest voice and pace across engines
- 대사: 대본을 한 덩어리(`script`, 장면 경계 ` / `)로 쓰고 엔진이 장면에 나눔 · 이어 말하기 기본 · 한국어 AI 문체 규칙(humanizer-ko) / Narration written as one script and synthesized in one pass; Korean AI-style rules
- 완전 로컬: 그림 · 영상 생성 경로(실사 생성 컷 · 그림 시안 · 세로 확장)를 없앴습니다 — 화면은 퍼온 클립 · 스톡 · 사진 · 화면 녹화 · Craft 그림으로 / Fully local: removed the image and video generation route (generated shots, image drafts, vertical extend)
- 감독 스킬(다섯 기둥 · 리듬 계단 · 시선 한 곳 · 세 가지 구체)과 작가 스킬(훅 세 칸 · 대사 · AI 티 금지) / Director and writer skills
- 나레이션 없는 영상의 화면 글자(caption) 표시 · 초 단위 확대 · 감독 없음 검사(L41) / Captions without narration, timed zoom, no-direction lint
- 레퍼런스 분석 빨라짐(빠른 분해 기본 · 여러 편 동시) · 기준점(anchor) / Faster reference analysis, anchor matching
- 대화창 그림 크게 보기 · 다시 그린 그림이 옛 그림으로 뜨던 문제 / Chat image lightbox and stale-image fix

## v1.0.0 — 2026-11-09

첫 정식 배포 / First stable release.

**만들기 · Making**
- 레퍼런스 먼저: 쇼츠 X-ray(컷 · 카메라 · 색 · 말 · 화면 글자) + VL 이해(장면 · 훅 · 반전 · 편집 문법 · 자막 말투), 레퍼런스 최소 3편 / References first: measured X-ray plus VL understanding, at least 3 references
- 뻔함 지도 → 그것을 일부러 깨는 콘셉트 6~8안, 형식 스킬엔 정해진 장면 순서 없음 / Cliché map → concepts that break it; no fixed scene order in formats
- 느낌(룩) 2~4안 시안 · 실사 생성 여부를 에이전트가 판단, 고르는 건 사용자 / Feel previews and live-action decision, user picks
- Craft 앱 16개 + Blender 로 장면 재료 · 움직임 · 소리 · 컷, 전부 열어 고칠 수 있는 프로젝트 파일 / 16 Craft apps + Blender, editable project files
- 클립 재활용: 다시 본 구간 · VL 순간 찾기 · 주인공 추적 세로 리프레이밍 · 원음 · 유행 곡 안내 / Clip reuse with moment finding, reframing and trending-song guide
- 실사 컷은 그림 시안 → 사용자가 고름 → 그 그림으로 영상, 모델마다 조사 기반 프롬프트 문법 / Image drafts → pick → video, research-based per-model prompts
- 가로 사진 세로 확장(원본은 가운데 그대로) / Vertical extend for landscape photos

**모델 · Models**
- 판단은 내 Claude Code · Codex, 보기 · 만들기 · 말하기는 오픈라우터 키 하나 — 능력마다 모델을 설정에서 고름(VL · 그림 · 편집 · 영상 · 음성 · 받아쓰기 · 음악 · 임베딩) / Your own agent thinks; one OpenRouter key for see · make · speak
- 비용 관문: 영상 한 편 상한 안이면 그대로, 넘으면 승인 · 장부 / Cost gate with per-video cap and ledger
- 키가 없어도 처음부터 끝까지 무료 · 로컬 경로 / Fully usable free and local without a key

**운영 · Ops**
- Linux · macOS · Windows, Intel · AMD · ARM — CI 6개, amd64 · arm64 Docker 이미지, GPU 자동 연결 시작 스크립트 / CI on 6 targets, multi-arch image, start scripts
