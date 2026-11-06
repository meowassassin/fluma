# MiniMax Hailuo (H3 · Hailuo 2.3 · Hailuo 02) — 프롬프트 카드

> 2026-11-06 기준. **최신은 MiniMax H3**(2026-07-31 공개, 웹 hailuoai.video · API `MiniMax-H3`). 이름에서 "Hailuo"가 빠졌지만 같은 제품군이다.
> Hailuo 02(2025-06) · Hailuo 2.3 은 레거시: 오디오가 없고 길이는 6 · 10초뿐이며, 글→영상에서 비율을 지정할 수 없다.

## 언제 이 모델을 고르나
- **9:16 세로 + 대사 · 효과음 · 음악까지 한 번에** 받고 싶을 때(H3, 4~15초, 24fps, 32kHz 스테레오).
- **한 클립 안에 여러 컷**이 필요할 때: `[Shot N] At 00:03.500` 컷 시각을 초 단위로 지정할 수 있다.
- **참조가 많을 때**: 그림 9장 · 영상 3개 · 오디오 3개를 넣고 라벨(`<Subject 1>` 등)로 역할을 정한다. 영상 편집 · 이어 찍기도 된다.
- 한국어 대사: H3 는 안정 지원 11개 언어에 한국어가 들어 있다(본문은 영어, 대사만 한국어).
- 싸게 시험할 때: H3-Lite 480P $0.025/초. 첫 · 끝 프레임 보간만 필요하고 소리가 필요 없으면 Hailuo-02 도 된다.
- Fluma 범위: 실사 생성은 제외한다. 화풍은 `2D-animated` · `3D CG` · `claymation` · `watercolor` 쪽으로 쓴다.

## 사양 (공식 API 문서)
| 항목 | H3 계열 (`/v2/video_generation`) | Hailuo-02 · 2.3 (레거시) |
|---|---|---|
| 모델 | `MiniMax-H3`(768P/2K) · `-Highspeed` · `-Lite` · `-Max`(480P/768P) | `MiniMax-Hailuo-02` · `-2.3` · `-2.3-Fast`(그림→영상만) |
| 길이 | 4~15 정수 초(Max 는 5~15) | 6 · 10초(1080P 는 6초만) |
| 비율 | `ratio`: 21:9 · 16:9 · 4:3 · 1:1 · 3:4 · **9:16** · adaptive. 글→영상은 필수이고 adaptive 는 안 됨. 그림→영상은 입력 그림 비율을 따름 | 비율 파라미터 없음. 그림→영상은 첫 프레임 비율(2:5~5:2) |
| 해상도 | 480P · 768P · 2K | 512P(02, 그림→영상만) · 768P · 1080P |
| fps | 24 (HF 모델 카드) | 문서에 없음 |
| 입력 | 글 / 첫 프레임 / 끝 프레임 / 첫+끝 / 참조(그림 ≤9 · 영상 ≤3 · 오디오 ≤3). 프레임 모드와 참조 모드는 섞을 수 없음 | 글 / 첫 프레임 / 첫+끝(02만) / 얼굴 참조는 별도 `S2V-01` |
| 프롬프트 한도 | 7000자 | 2000자 |
| 오디오 | 네이티브(켜고 끄는 파라미터 없음) | 없음 |
| 부정 프롬프트 · 시드 · 워터마크 파라미터 | 없음 | 없음(`prompt_optimizer` 는 있음) |

## 프롬프트 틀 (H3 공식 가이드)
본문은 **영어 문장**으로 쓴다. 대사 · 노래 · 화면 글자만 원어로 둔다. 필드 이름과 순서는 바꾸지 않는다.
```text
(그림 입력 시 정렬 지시문 한 줄)

integrated_multimodal_description: [Shot 1] <화풍>, <샷 크기> frames <대상 · 위치 · 장소>. The camera <움직임> with <폭> at <속도> as <행동>. <화자 묘사> (S1) says: <d>[Korean] 대사 원문</d> [Shot 2] At 00:04.000, the camera cuts to ...

overall_soundscape: <환경음 · 동작음 · 숨소리 1~4문장, 대사는 빼기>

non_diegetic_music: <악기 · 템포 · 강약 1~3문장 | N/A>
```
- 정렬 지시문(그대로 복사해 쓴다)
  - 첫 프레임: `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.`
  - 첫 + 끝: `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.`
  - 끝만: `... <Picture 1> (from [Shot N]) aligns with the S.SS-second mark ...` (S.SS 는 영상 길이, 소수 둘째 자리까지)
- 첫 프레임 모드는 그림에 있는 상태에서 시작해 행동이 시작되고, 이어지고, 결과로 끝나게 쓴다. 첫 + 끝 모드는 한 샷으로 두 그림 사이의 경로만 쓴다.
- 참조 모드는 6섹션이다: `subject_definitions` → `summary`([reference generation] 같은 접두어) → `retention_analysis` → `detailed_description`(350~500 단어) → `overall_soundscape` → `non_diegetic_music`.
- 카메라는 **종류 + 폭 + 속도**를 문장 안에 쓴다: Push In/Pull Out · Zoom In/Out · Pan · Truck · Tilt · Pedestal · Arc Shot · Tracking Shot · Static Shot · Shake Slightly/Strongly · POV · Roll. 폭은 `with small/large amplitude`, 속도는 `at slow/fast speed`.
- 컷을 넘길 때는 `the camera cuts to` · `the shot transitions to` 를 쓴다. dissolve · fade · wipe 는 요청이 있을 때만 쓴다.
- 대사: `(S1) says: <d>[Korean] ...</d>`. 둘이 함께 말하면 `(S1,S2)`. 내레이션은 `says in an off-screen voiceover:` 뒤에 `while his lips remain completely closed.` 를 붙인다. 컷을 넘는 대사는 `<scenetrans>`, 끝에서 끊기는 대사는 `<cutoff>` 로 표시한다.
- 화면 글자는 큰따옴표 안에 원문 그대로 쓴다: `A red neon sign reading "营业中"`.
- 레거시(02 · 2.3)는 문장 사이에 괄호 명령을 넣는다: `[Pan left,Pedestal up]`(동시, 최대 3개), `... [Push in], then ... [Pull out]`(차례로). 명령은 15종: Truck · Pan · Push in/Pull out · Pedestal · Tilt · Zoom · Shake · Tracking shot · Static shot.

## 좋은 예 (공식 Case 1, 글→영상)
```text
integrated_multimodal_description: [Shot 1] Live-action, cinematic, a medium-wide shot frames a baker opening the shutters of a small street bakery before sunrise. The camera pushes in with small amplitude at slow speed as the middle-aged baker with a calm, slightly raspy voice (S1) places a fresh loaf on the wooden counter and says: <d>[English] First batch of the morning.</d> [Shot 2] At 00:05.000, the camera cuts to a close-up of steam rising from the sliced bread while the baker's final words carry over from the previous shot.

overall_soundscape: Wooden shutters scrape open over a quiet street as trays clink softly inside the bakery. The doorbell rings once, followed by light footsteps and the crisp sound of bread being sliced.

non_diegetic_music: A soft acoustic-guitar pattern at a moderate tempo, joined by sparse upright-bass notes and a gentle fade at the end.
```
Fluma 용으로 바꿔 쓰려면 `Live-action, cinematic` 을 `2D-animated` 같은 화풍으로 바꾸고, API 에 `ratio: "9:16"` 을 준다.

## 나쁜 예 → 고친 예
- ✗ `beautiful cinematic bakery, 4k, masterpiece, slow zoom` (키워드 나열, 추상어, 라벨을 끝에 붙임)
  ✓ 장면 · 행동 · 카메라를 한 문장에 쓴다: `The camera pushes in with small amplitude at slow speed toward ...`
- ✗ `[Shot 1] 0-3s ... [Shot 2] 3s-6s ...` (구간 표기, Shot 1 에 시각을 붙임)
  ✓ `[Shot 1] ... [Shot 2] At 00:03.000, the camera cuts to ...`
- ✗ `She says "안녕하세요"` (따옴표 대사, 화자 ID 없음)
  ✓ `The cheerful young woman with a bright, fast voice (S1) says: <d>[Korean] 안녕하세요.</d>`
- ✗ 6초 영상에 `[Shot 3] At 00:07.000` (시각이 영상 길이를 넘음)
- ✗ `non_diegetic_music: emotional, uplifting mood` → ✓ 악기 · 템포 · 강약으로 쓴다
- ✗ 대사를 `overall_soundscape` 에 한 번 더 씀, 보이스오버 뒤에 입술 문장을 빠뜨림(입이 움직인다)
- ✗ 거리만 조금 바뀌는데 컷을 나눔 → 카메라 움직임으로 처리한다

## 일관성 · 정책 · 비용
- 일관성: 시드 파라미터가 없다. 참조 그림 · 영상 · 오디오에 붙인 `<Subject N>` 라벨과 화자 ID `(S1)` 을 모든 섹션 · 컷에서 같게 쓴다. 목소리를 고정하려면 `<Audio N>` 을 음색 참조로 넣는다.
- 화면 글자: H3 공식 블로그는 "정확한 글자 · 브랜드 렌더링"을 주장하지만 독립 검증은 없다. Fluma 에서는 자막 · 글자를 후반에 넣는 쪽이 안전하다.
- 정책: 자동 검열이 불법 · 음란 · 제3자 권리 침해 의심 콘텐츠를 막고, 오탐도 있다. 민감한 프롬프트는 오류 1026 으로 거절된다. 허가 없는 실제 브랜드 마크는 공식 스킬 범위 밖이다.
- 가격(API 종량제): H3 2K $0.13/초 · 768P $0.08/초, Lite 480P $0.025/초. 02 · 2.3 768P 6초 $0.28. 웹 크레딧 단가 · 상업 이용 · 워터마크 조건은 확인하지 못했다(비공식: 무료 계정은 워터마크가 붙는다).
- 공개 가중치: MiniMax H3 Community License. 출력은 768p 이고, 2K 재생성 모듈은 아직 공개되지 않았다.

## 출처
- 공식 API(H3): https://platform.minimax.io/docs/api-reference/video-generation-v2-create · https://platform.minimax.io/docs/guides/video-generation
- 공식 프롬프트 가이드: https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md · https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md
- 공식 스킬: https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills
- 모델 카드 · 블로그: https://huggingface.co/MiniMaxAI/MiniMax-H3 · https://www.minimax.io/blog/minimax-h3
- 가격: https://platform.minimax.io/docs/guides/pricing-paygo
- 레거시 API: https://platform.minimax.io/docs/api-reference/video-generation-t2v · …-i2v · …-fl2v · …-s2v
- Hailuo 02 발표: https://www.minimax.io/news/minimax-hailuo-02
- (비공식) ComfyUI H3 가이드 요약: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-prompt-guide
