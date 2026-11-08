# Fluma 에 기여하기

[English](CONTRIBUTING.md) · **한국어**

**있는 그대로 오세요.** 포크하고, 고치고, 부수고, 내 것으로 만드세요. PR · 새 기능 · 엉뚱한 실험 · 작은 수정 · 오타 ·
번역 · 버그 제보 · 덜 익은 아이디어 모두 환영합니다 — 먼저 물어볼 필요 없어요.

Fluma 는 Apache-2.0 이라 상업용이든 아니든 내 프로젝트에 자유롭게 쓰고 고칠 수 있습니다.

## 시작하는 방법

- 🐛 **이상한 걸 찾았나요?** 이슈를 열어 주세요 — "헷갈렸다"도 도움이 됩니다.
- 💡 **아이디어가 있나요?** 이슈나 초안 PR 을 보내 주세요. 거칠어도 괜찮아요, 같이 다듬으면 됩니다.
- 🔧 **뭔가 만들고 싶나요?** 무엇이든. 쉬운 입구 몇 개:

| 아이디어 | 위치 |
|---|---|
| 다른 Craft 앱(또는 아무 툴)을 재료 만드는 곳으로 연결 | `engine/craft/apps/<앱>/craft.json`(`provides`) + `engine/craft/materials.py` 의 어댑터 |
| 재료 종류별 움직임 개선 | `engine/craft/motion.py`(`material_jsx`) |
| 새 음성 엔진 | `engine/voice/engines/<이름>/` — `voice.json` + `adapter.py` |
| 좋아하는 쇼츠에서 잰 형식 프리셋 | `engine/research/ref_channel.py` → `engine/research/format_presets.py build` |
| 더 똑똑한 검사 | `engine/checks/lint.py`, `engine/checks/tempo_check.py`, `engine/checks/edit_density.py` |
| YouTube 통계 더하기 | `studio/youtube.mjs`, `studio/src/features/studio/PublishView.tsx` |
| 화면에 내 언어 | `studio/src/i18n/*.ts`(한국어 문장이 키) |
| 문서 · 예시 · 데모 쇼츠 | 어디든 — README, `docs/`, 새 폴더, 마음대로 |

## PR 보내기

언제든 여세요 — 초안 PR 도 좋습니다. 시간이 되면 먼저 돌려 주면 도움이 돼요:

```bash
python -m pytest tests
npx tsc --noEmit -p web
```

실패하는데 이유를 모르겠으면 그냥 보내고 그렇다고 적어 주세요. 같이 찾아봐요.

## 우리가 아끼는 것(규칙이 아니라 취향)

- 만들기 전에 실제 쇼츠를 분석하기 — 손으로 정한 숫자보다 실제 쇼츠에서 잰 숫자.
- 생성한 추측보다 실제 재료 — 화면의 사실은 출처가 있으면 좋아요.
- 뭔가 이상하면 결과 하나를 땜질하기보다 엔진이나 검사를 고치는 게 대개 더 낫습니다.
- '됐다'고 하기 전에 렌더해서 화면을 직접 보기.
- API 키 · OAuth 토큰 · 개인 데이터(콘티 · 업로드 · 통계)는 커밋 · 로그에 넣지 말아 주세요.

와 주셔서 고마워요. 💜
