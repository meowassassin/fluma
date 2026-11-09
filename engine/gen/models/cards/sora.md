# Sora 2 / Sora 2 Pro (OpenAI) — 프롬프트 카드

> 2026-11-06 기준. **서비스 종료됨.** Sora 앱 · 웹은 2026-04-26에 끝났고, Videos API(`sora-2` · `sora-2-pro`와 모든 스냅샷)는 2026-09-24에 끝났다. 공식 대체 모델은 없다.
> 지금은 새 클립을 만들 수 없다. 이 카드는 예전에 Sora로 만든 클립을 다루거나, 다른 모델 카드와 비교할 때 참고용으로 남긴다.

## 언제 이 모델을 고르나
- **지금은 고르지 않는다.** 새 클립이 필요하면 다른 엔진 카드(Veo · Kling · Runway 등)로 간다.
- 운영하던 시절의 강점은 이랬다.
  - 네이티브 오디오(대사 · 립싱크 · 효과음)를 영상과 함께 만들었다.
  - 물리감 있는 짧은 실사풍 컷을 잘 만들었다.
  - 9:16 세로 출력을 지원했다(720x1280, pro는 1080x1920).
- Fluma 범위 참고: 실사 생성은 Fluma 범위 밖이다. 이 모델을 쓰더라도 애니메이션 · 스타일 컷이나 소품 · 풍경 컷에 맞았다.

## 사양 (API 기준, 종료 전)
| 항목 | 값 |
|---|---|
| 모델 | `sora-2`(빠름) · `sora-2-pro`(고품질 · 비쌈) |
| 길이 `seconds` | 4 · 8 · 12 · 16 · 20 (기본 4). extensions로 20초씩 최대 6번, 합계 120초 |
| 크기 `size` | 720x1280 · 1280x720. pro는 1024x1792 · 1792x1024 · 1080x1920 · 1920x1080도 가능 |
| fps | 문서에 없음 |
| 입력 | 글→영상, 첫 프레임 이미지(`input_reference`, `size`와 같은 해상도, 사람 얼굴은 거부) |
| 인물 참조 | Characters API: 2~4초 MP4로 캐릭터 ID 생성, 영상당 최대 2명, 프롬프트에 이름을 그대로 써야 함 |
| 영상→영상 | `edits`(한 가지씩 수정) · `extensions`(이어 붙이기) · remix(폐지 예정이었음) |
| 마지막 프레임 · 여러 장 참조 · 시드 · 부정 프롬프트 · 카메라 파라미터 | 없음 (공식 문서에 없음) |
| 가격 | sora-2 $0.10/초. pro는 해상도에 따라 $0.30 · $0.50 · $0.70/초 |

길이 · 해상도는 **파라미터로만** 바뀐다. 프롬프트에 "더 길게"라고 써도 무시된다.

## 프롬프트 틀 (공식 쿡북 구조)
```
Style: [한 줄 — 예: 1970s film, 16mm black-and-white, hand-painted animation]

[장면 산문: 인물 · 의상 · 장소 · 날씨 · 중요한 소품만]

Cinematography:
Camera shot: [프레이밍 · 앵글 · 움직임 1개]
Lens: [35mm, shallow depth of field 등]
Lighting: [soft window light, cool rim 등 + 팔레트 색 3~5개]
Mood: [톤]

Actions:
- [박자 1: 구체적 동작, 걸음 수 · 멈춤까지]
- [박자 2]

Dialogue:
Name: "짧은 대사"

Background Sound:
[소리 단서 1~2개]
```
- 문장형 산문과 라벨 붙은 키워드 블록을 섞는다.
- 지원 언어는 공식 확인이 안 됐다. 예시는 모두 영어이므로 **영어로 쓴다.**
- 멀티샷은 정해진 문법이 없다. 샷마다 블록을 나누고, 블록마다 카메라 1 · 동작 1 · 조명 1개로 쓴다.
- 공식 상세 예시는 샷 목록에 `0.00-2.40 — ...`처럼 초 구간을 적었다. 다만 그 구간을 정확히 따른다는 보장은 문서에 없다.

## 대사 · 소리
- 대사는 산문과 분리해 `Dialogue:` 블록에 쓴다. 화자 이름을 고정하고 따옴표로 감싸며, 번갈아 말하게 한다.
- 4초 클립에는 대사 1~2줄, 8초에는 몇 줄 더 들어간다. 긴 독백은 립싱크가 어긋난다.
- 효과음 · 앰비언스는 `Background Sound:`에 1~2개만 쓴다. 저작권 음악은 거부된다.

## 좋은 예 / 나쁜 예
**좋은 예** (공식 템플릿 형식에 맞춘 예, 720x1280 · 4초)
```
Style: 1970s film, warm grain, soft halation.
A barista in a cream apron pours latte art in a narrow walnut-wood cafe at early morning; steam rises, window light falls across the counter.
Cinematography:
Camera shot: medium close-up, eye level, slow push-in
Lens: 35mm, shallow depth of field
Lighting: soft window light from left, warm lamp fill
Palette: amber, cream, walnut brown
Actions:
- She tilts the cup and pours in one steady stream.
- A leaf pattern forms; she pauses and looks up at the camera.
Dialogue:
Barista: "Morning. Same as always?"
Background Sound: espresso machine hiss, quiet cafe murmur.
```
좋은 이유: 카메라 · 동작 · 조명이 각각 하나다. 동작은 박자로 나눴고 대사는 짧다. 팔레트도 고정했다.

**나쁜 예**
```
A beautiful cafe, camera flies around and zooms and pans, people move quickly,
neon sign says "FLUMA COFFEE", make it 20 seconds and 4K, cinematic, no blur.
```
나쁜 이유:
- "beautiful", "move quickly"처럼 모호하다.
- 카메라 이동이 여러 개다.
- 화면 속 글자와 브랜드를 요구한다.
- 길이 · 해상도를 프롬프트 글로 요구한다(파라미터로만 바뀜).
- 부정 프롬프트처럼 "no blur"를 썼다.

## 자주 생기는 실패와 피하는 법
- 적지 않은 요소(시간대 · 의상 · 나이 · 앵글)는 모델이 임의로 채운다. 중요한 것만 적고 나머지는 열어 둔다.
- 길고 제약이 많은 프롬프트는 일부를 무시한다. 통제가 필요하면 4초 컷 여러 개로 나눠 이어 붙인다.
- 문구가 조금만 달라도 인물이 바뀐다. 샷 사이에 같은 묘사 문장을 그대로 반복한다.
- `edits`에서 한꺼번에 여러 개를 바꾸면 통제가 안 된다. "same shot, switch to 85 mm"처럼 하나씩 바꾼다.
- 화면 속 글자: 공식 평가가 없다(unknown). 간판 · 브랜드를 피하라는 공식 예시가 있다. **글자는 Fluma 편집 단계 자막으로 넣는다.**

## 정책 · 워터마크
- 18세 미만에게 적합한 콘텐츠만 만들 수 있다.
- 실존 인물(공인 포함)은 만들 수 없다.
- 저작권 캐릭터 · 음악은 거부된다.
- 얼굴이 든 입력 이미지는 거부된다.
- 사람을 닮은 캐릭터 업로드는 기본으로 차단된다.
- 워터마크: 출시 때 "모든 출력에 보이는 워터마크 + C2PA"라고 공식 발표했다. 독립 테스트(비공식, LessWrong)는 일부 다운로드에 C2PA가 없었다고 보고했다.
- 상업 이용 조건: Sora 전용 조항은 확인하지 못했다.

## 출처
- 공식 프롬프트 가이드(쿡북): https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide
- API 가이드(종료 표기 보존본): https://developers.openai.com/api/docs/guides/video-generation
- 모델 페이지 · 가격: https://developers.openai.com/api/docs/models/sora-2
- 지원 종료 공지: https://developers.openai.com/api/docs/deprecations
- 앱 종료 도움말: https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation
- 안전 · 워터마크: https://openai.com/index/launching-sora-responsibly/ · https://openai.com/index/creating-with-sora-safely
- (비공식) 워터마크 독립 테스트: https://www.lesswrong.com/posts/kSvrmiyyN7CDyh3NN/openai-does-not-appear-to-be-applying-watermarks-honestly
