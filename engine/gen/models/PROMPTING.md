# 생성 프롬프트 작성법 — 조사 요약(2026-11-09)

`engine/gen/shotplan.py` 의 `compile_image` · `compile_prompt` 가 이 규칙을 코드로 따른다. 에이전트는 재료 칸(아래)을 잘 채우는 일을 한다 — 문법은 코드가 모델마다 맞춘다.

## 출처
- 오픈소스 스킬 · 도구: [uniqaiapp/video-director](https://github.com/uniqaiapp/video-director)(MIT — 박자 · 카메라 · 물리 · 부정어 · 모델별 모양 · 글자 한도), [MichaelCao1/Videoprompt](https://github.com/MichaelCao1/Videoprompt)(Seedance 2.5 shot-memo), [jnMetaCode/ai-shortfilm-prompts](https://github.com/jnMetaCode/ai-shortfilm-prompts)(5단 구조), [zhflux/video-prompt-enhancer](https://github.com/zhflux/video-prompt-enhancer)(규칙형 다듬기 · 평가), [MaxKruse/ComfyUI-PromptEnhancer](https://github.com/MaxKruse/ComfyUI-PromptEnhancer)(Wan 2.2 공식 다듬기 지침 기반 프리셋)
- 공식: Google [Nano Banana 프롬프트 가이드](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana) · [DeepMind 이미지 프롬프트 가이드](https://deepmind.google/models/gemini-image/prompt-guide/), BytePlus [Seedream 이미지 API](https://docs.byteplus.com/en/docs/ModelArk/1541523) · Seedance 2.5 가이드(models/cards/seedance.json), 오픈라우터 영상 · 이미지 생성 문서
- 커뮤니티 이미지→영상 가이드(dev.to · 블로그 여럿) — 공통 조언만 채택

## 영상
1. **한 박자 = 한 사건.** "그리고"가 필요하면 나눈다. 3–5초는 1박, 6–10초는 2–3박.
2. **마지막 박자는 멈춤 · 끝 상태**(`end_state`). 새 동작으로 끝내면 모델이 프레임이 모자라 얼거나 지어낸다.
3. **카메라 움직임은 하나**, 끝점까지 말한다("…until the window fills the frame"). 겹친 움직임 · 360도 회전은 불안정.
4. **움직임 물리 한 문장**(`physics`, 비우면 코드가 피사체 · 동작에서 고름): 무게 이동 · 접촉 · 끌림 · 가라앉음(settles). "미끄러지지 않게" 보다 "발이 땅에 단단히 닿는다".
5. **부정어는 명사 목록으로 따로**(6~10개): `morphing, extra limbs, warped hands, flicker, text, watermark, logo, jump cuts, frame jitter` + 장면 위험(`avoid`). 문장 속 "no X" 는 X 로 읽힌다. Veo 는 negativePrompt 칸(대사가 있으면 subtitles · captions 추가 — 자막을 박는 버릇), Kling · Wan · Hailuo 는 따로 칸, Seedance · Omni 는 "Avoid:" 한 줄, Runway 는 무시하므로 긍정 문장만.
6. **이미지 → 영상은 바뀌는 것만.** 첫 프레임에 이미 보이는 겉모습을 다시 말하면 그림에서 벗어난다. 지킬 것(`invariants`)만 적는다. 카메라를 안 정했으면 고정.
7. **꼭 지킬 사실은 두 곳 이상에**(`must` — 한 번 보고 확인할 수 있는 문장). 한 번만 적은 사실은 빠지기 쉽다.
8. **실패 이름 붙이기**: "No opening freeze shot", "real-time speed", "mass has real weight, correct contact shadows".
9. **모델별 순서 · 한도**: Kling = 피사체 → 움직임 → 장소 → 카메라 → 빛 → 분위기(2,500자) · Veo = 촬영 → 피사체 → 동작 → 맥락 → 스타일, 한 테이크, 소리는 따로 한 문장(4/6/8초) · Wan = 간결 80–120단어(이미지→영상 50–100), 스타일 먼저, 하늘은 색 이름으로, 800자/부정 500자 · Seedance = shot memo(PACING · CAMERA · Shot N 시각 · PHYSICS · MUST · Avoid) · Runway = 카메라 먼저, 긍정만, 1,000자.
10. **대사는 짧게**(8단어 이하) — 립싱크가 길면 무너진다.

## 그림(키프레임)
1. **용도 · 매체 · 비율을 먼저**: "세로 9:16 쇼츠의 첫 프레임 — 사진 같은 …".
2. **피사체는 구체 명사 + 디테일 2~3개**, 빛은 출처까지(창문 · 가로등).
3. **Gemini(Nano Banana)는 있을 것으로 말하기**(positive framing): "빈 거리" 가 "차 없음" 보다 낫다. 편집은 작은 단계로, 지킬 것을 말한다.
4. **참조 그림은 번호와 역할로**(`ref_roles`): "Image 1 = 얼굴 · 정체성, Image 2 = 옷".
5. Midjourney 는 `--ar 9:16 --style raw --no …`, GPT Image 는 칸마다(Purpose · Subject · …), Seedream 은 짧은 문장 + 그림 안 글자는 큰따옴표.
6. 자막 자리: 아래 1/3 을 비워 둔다.

## 에이전트가 채우는 재료 칸(type video + gen)
`prompt`(무엇이 일어나는가, 영어 구체 명사) · `camera`(하나) · `framing` · `setting` · `physics` · `invariants`[] · `end_state` · `must`[] · `avoid`[](이 장면 특유의 실패) · `ref_roles`[] · `cast` · `line`(8단어 이하) · `people`.
결과가 틀리면 프롬프트 전체를 다시 쓰지 말고 칸 하나 둘만: 구도 · 움직임 → camera · framing, 떠다님 → physics, 밋밋함 → 느낌(feel) · style, 이상한 손 · 글자 → avoid, 속도 → 박자를 줄이고 end_state.
