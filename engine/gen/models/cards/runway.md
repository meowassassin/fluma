# Runway — Gen-4.5 · Gen-4 Turbo · Aleph 2.0

2026-11-06 기준. 기계용 카드는 `runway.json`. 근거는 API 문서(docs.dev.runwayml.com)와 공식 아카데미 프롬프트 가이드. 커뮤니티 출처는 **(비공식)** 으로 표시.

## 버전 한눈에

| 모델 (API id) | 용도 | 입력 | 길이 | 9:16 | 값(API) |
|---|---|---|---|---|---|
| Gen-4.5 (`gen4.5`) | 최상위 생성 | 글→영상, 첫 프레임 그림→영상 | 2~10초 | 720x1280 | 12 크레딧/초 = $0.12 |
| Gen-4 Turbo (`gen4_turbo`) | 빠르고 싼 시안 | 첫 프레임 그림→영상만 | 2~10초 | 720x1280 | 5 크레딧/초 = $0.05 |
| Aleph 2.0 (`aleph2`) | 기존 영상 편집 | 영상(2~30초, 30fps 이하) + 키프레임 그림 최대 5장 | 입력 길이 그대로 | 입력 유지 또는 `targetAspectRatio: 9:16` 로 확장 | 28 크레딧/초(최소 56) |

- Gen-4 Aleph(`gen4_aleph`)는 API 에서 2026-07-30 종료됐고 Aleph 2.0 으로 대체됐다. 기본 Gen-4 는 웹에 '이전 세대'로만 남아 있다.
- 마지막 프레임 지정, 참조 이미지 여러 장, 카메라 제어 파라미터, 부정 프롬프트는 셋 다 **없다**. 해상도는 720p 급이다.
- 오디오: API 출력은 무음이다. 웹 Gen-4.5 에 네이티브 오디오 · 대사 · 1분 멀티샷이 생겼다는 보도(TechCrunch 2025-12-11)는 있지만 공식 체인지로그에서는 확인하지 못했다.

## 언제 Runway 를 고르나

- **이미 있는 장면 그림을 움직일 때**: Fluma 가 만든 9:16 첫 프레임에 카메라 움직임만 입힌다. Gen-4.5 가 카메라 지시를 잘 따른다.
- **찍어 둔 클립을 고칠 때(Aleph 2.0)**: 옷 색 · 소품 교체, 배경 · 조명 · 계절 바꾸기, 거슬리는 로고 · 사람 지우기, 16:9 영상을 9:16 으로 확장. 나머지는 그대로 유지된다.
- **싸게 여러 번 시험할 때**: Gen-4 Turbo 로 움직임을 맞춘 뒤 Gen-4.5 로 최종본을 뽑는다.
- **고르지 말아야 할 때**: 대사 · 립싱크 · 효과음이 한 번에 필요할 때(Veo · Kling · Seedance 쪽), 10초 넘는 한 컷이 필요할 때, 화면 속 글자가 중요할 때(글자는 Fluma 가 편집에서 얹는다).

## 프롬프트 틀 (공식)

언어는 **영어**(한국어 · 중국어 지원 여부는 공식 확인 못 함), 문장형, **최대 1000자**. 짧게 시작해 한 번에 한 요소씩 더한다. 여러 문단으로 과하게 지정하면 결과가 부자연스러워진다.

**글→영상** (Gen-4.5)
```
[Camera] shot of [a subject/object] [action] in [environment]. [Supporting component descriptions]
```
화면 묘사(누가 · 어디서 · 빛 · 구도 · 스타일)와 움직임 묘사(피사체 · 환경 · 카메라 · 속도와 방향)를 둘 다 넣는다.

**그림→영상** (Gen-4.5 / Gen-4 Turbo)
```
The camera [motion description] as the subject [action]. [Additional descriptions]
```
그림이 이미 구도 · 인물 · 조명 · 스타일을 정하므로 **움직임만** 쓴다. 그림 속 대상은 `the subject`, `the man` 처럼 일반어로 부른다. 새 요소 등장, 큰 변화, 변형, 둘 이상의 상호작용이 있을 때만 화면을 묘사한다.

**영상→영상** (Aleph 2.0): 짧고 구체적인 편집 지시를 쓴다. 키프레임 그림을 주면 프롬프트는 대개 필요 없다.

**시간 순서**(공식): `X occurs, then Y occurs. Finally, Z occurs.` 또는 `[00:01] X occurs. [00:03] Y occurs. [00:04] Z occurs.` 사건 수는 고른 길이에 맞춘다.

**멀티샷**: 전용 문법은 없다. 한 클립 안에서 `Whip pan to …. Whip pan back to …` 처럼 카메라 전환으로 표현한다. 원치 않는 컷이 생기면 길이를 늘리고 `Continuous, seamless shot.` 을 덧붙인다.

**정지 · 루프**(공식 문구 그대로)
- `The locked-off camera remains perfectly still.` / `Minimal subject motion only.`
- `The camera must start and end on the exact same frame to create a perfect loop.`

## 알아듣는 용어

- 카메라(공식 예시에 나온 것): locked-off, handheld, natural camera shake, slowly pushes in, slowly zooms out, crash zoom, whip pan, sweeping horizontal arc around the subject, orbiting, close-up shot, behind view, high angle looking down. 아카데미 카메라 절 제목에는 dolly · pan · tracking · crane/jib 이 있다.
- 속도 · 강도: slowly, aggressive, extremely rapid, subtle. 붙이지 않으면 평범한 속도가 된다 (비공식).
- 조명: natural lighting (공식). soft window light, golden hour side lighting (비공식).
- 스타일: handheld documentary film style, raw indie film aesthetic, low budget realism, observational feel, cinematic, photorealistic, stylized.

## 일관성

1. `gen4_image` 에 인물 · 소품 참조를 최대 3장 넣고(각각 `@tag`) 같은 인물이 나오는 9:16 정지 컷을 만든다.
2. 그 컷을 Gen-4.5 그림→영상의 첫 프레임으로 쓴다.
3. 길게 이을 때는 앞 클립의 마지막 프레임을 다음 클립의 첫 프레임으로 쓰고, 편집에서 겹친 한 프레임을 잘라낸다(공식).
4. `seed` 를 고정하면 비슷한 결과가 나온다(완전히 같지는 않다).

입력 그림은 고화질이어야 한다. 흐린 손 · 얼굴은 영상에서 더 나빠진다.

## 좋은 예 / 나쁜 예

**좋음: 글→영상, 공식 예시 그대로**
> A raccoon in a plain room in zero gravity trying to steal the garbage from a silver trash can. The garbage floats out in zero gravity. Handheld documentary film style. Natural camera shake. Raw indie film aesthetic. Natural lighting. Unpolished, authentic look. Low budget realism. Observational feel.

**좋음: 그림→영상, 공식 예시 그대로**
> The camera executes an aggressive, sweeping horizontal arc around the subject, followed by an extremely rapid, aggressive crash zoom that concludes with a sharp focus on the subject's eyes.

**좋음: 그림→영상, 공식 틀에 맞춘 Fluma 용 예(9:16 · 5초)**
> The camera slowly pushes in as the subject lifts the coffee cup and smiles. Steam rises from the cup. Continuous, seamless shot.

**나쁨**
> A beautiful cafe with a woman in a beige coat holding a white cup, no blur, don't move the camera, 귀여운 느낌, 자막 "오늘의 커피"

- 그림에 이미 보이는 것을 다시 묘사했다.
- 부정형(`no`, `don't`)을 썼는데, 부정 프롬프트는 지원되지 않는다.
- 한국어가 섞였다.
- 화면 속 글자를 요구했다.
- 카메라 지시가 없다.

고친 문장: `The locked-off camera remains perfectly still. The subject raises the cup slowly and smiles.`

**나쁨 (비공식 Runware 예)**: 앉아서 연주하는 그림에 `abruptly stands up … walks out of frame to the right`. 그림에 근거가 없는 동작은 잘 되지 않는다.

## 자주 생기는 실패

- **원치 않는 움직임**: 입력 그림의 모션 블러 · 먼지 · 동작 중 자세 · 방향선이 원인이다. 그림에서 먼저 지운다.
- **원치 않는 컷**: 길이를 늘리고 seamless 문구를 넣는다.
- **물리 이상**(공식이 인정한 한계): 결과가 원인보다 먼저 나오고, 물체가 생겼다 사라지고, 동작이 지나치게 잘 성공한다.

## 비용 · 권리 · 정책

- **API**: 1 크레딧 = $0.01. 10초 9:16 기준 Gen-4.5 는 $1.20, Turbo 는 $0.50. 검열(SAFETY.INPUT)에 걸린 요청은 환불되지 않는다.
- **웹 요금제**: Free 125 크레딧(일회성), Standard $15/월 625 크레딧(워터마크 없음), Pro $35/월 2,250 크레딧, Max $95/월 9,500 크레딧.
- **상업 이용**: 공식 도움말은 "비상업 제한 없음"이라고 한다. 무료 플랜의 워터마크 · 상업 범위는 공식으로 확인하지 못했다.
- **정책**: 입력과 출력을 모두 검열한다. 공인 얼굴은 기본으로 막히고, API 의 `publicFigureThreshold: low` 로 완화할 수 있다. 참조 인물은 묘사 권한이 있어야 한다. 검열에 반복해서 걸리면 계정이 정지된다.

## 출처

- API 레퍼런스: https://docs.dev.runwayml.com/api.md · 모델 https://docs.dev.runwayml.com/guides/models.md · 가격 https://docs.dev.runwayml.com/guides/pricing.md · 전체 문서(체인지로그 · 입력 규격 · 검열) https://docs.dev.runwayml.com/llms-full.txt
- 공식 프롬프트 가이드(Gen-4.5): https://academy.runwayml.com/prompt-guide
- Gen-4.5 발표: https://runway.com/research/introducing-runway-gen-4.5 · Aleph: https://runway.com/research/introducing-runway-aleph · Aleph 2.0: https://runway.com/news/introducing-aleph-2-and-edit-studio
- 체인지로그: https://runway.com/changelog · 요금: https://runway.com/pricing
- 도움말(본문 직접 열람 불가, 검색 요약으로만 확인): Aleph 2.0 가이드 https://help.runwayml.com/hc/en-us/articles/52150503729171 · 상업 이용 https://help.runwayml.com/hc/en-us/articles/21668707517587
- 보도: TechCrunch 2025-12-11 https://techcrunch.com/2025/12/11/runway-releases-its-first-world-model-adds-native-audio-to-latest-video-model/
- (비공식) Runware Gen-4.5 모션 가이드: https://runware.ai/docs/models/runway-gen-4-5/guides/directing-motion.md
