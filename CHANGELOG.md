# Changelog


## Unreleased

- 제작 자동: '제작 시작' 버튼을 없애고 콘티가 검사를 통과하면 같은 턴에 초안까지, 고르기를 기다리던 단계는 추천안으로 진행 · 에이전트 쓰기 권한이 막히던 문제 / Auto production: no "start" button, recommended options without waiting, fixed blocked agent writes
- 배경 음악 자동: 넣을지 정하고(레퍼런스 음악 · 나레이션 · 형식) 요즘 쓰이는 곡 중 맞는 무료 곡을 박자 · 힘 있는 구간으로 고름, 상업 유행곡은 업로드 때 붙일 곡으로 안내(설정에서 직접 넣기 가능) · YouTube Data API 키 선택 / Automatic background music from free libraries, trending commercial songs suggested for upload
- 효과음: 음악이 깔리면 기본으로 빼고, 고음질 CC0 녹음(48kHz 스테레오)으로 교체 / Sound effects: off under music by default, high-quality CC0 recordings
- 음성: 설정을 한곳(미디어 → 음성)으로 합치고 '자동'(기본) — 엔진을 가로질러 레퍼런스 화자와 닮은 목소리 · 말 속도 / Voice: one settings place, Auto picks the closest voice and pace across engines
- 대사: 대본을 한 덩어리(`script`, 장면 경계 ` / `)로 쓰고 엔진이 장면에 나눔 · 이어 말하기 기본 · 한국어 AI 문체 규칙(humanizer-ko) / Narration written as one script and synthesized in one pass; Korean AI-style rules
- 완전 로컬: 그림 · 영상 생성 경로(실사 생성 컷 · 그림 시안 · 세로 확장)를 없앴습니다 — 화면은 퍼온 클립 · 스톡 · 사진 · 화면 녹화 · Craft 그림으로 / Fully local: removed the image and video generation route (generated shots, image drafts, vertical extend)
- 감독 스킬(다섯 기둥 · 리듬 계단 · 시선 한 곳 · 세 가지 구체)과 작가 스킬(훅 세 칸 · 대사 · AI 티 금지) / Director and writer skills
- 나레이션 없는 영상의 화면 글자(caption) 표시 · 초 단위 확대 · 감독 없음 검사(L41) / Captions without narration, timed zoom, no-direction lint
- 레퍼런스 분석 빨라짐(빠른 분해 기본 · VL 과 스타일 카드 병렬 · 두 편씩 동시) · 기준점(anchor) · 초안 뒤 VL 비평 자동 / Faster reference analysis, anchor matching, automatic draft critique
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
