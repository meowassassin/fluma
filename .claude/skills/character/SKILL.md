---
name: character
description: 사용자마다 맞는 캐릭터(마스코트 · 진행자)를 만든다. SVG 부품(몸 · 눈 감김 · 입 6종)을 직접 그려 characters/<이름>/ 에 두면, 어느 엔진으로 렌더해도 화면 구석에서 나레이션에 맞춰 립싱크한다.
---

# 캐릭터 만들기

결과: `characters/<이름>/character.json` + `parts/*.svg`. 콘티에 `"character": "<이름>"`→ 마무리 단계가 화면 위에 입힌다.

## 부품 (모두 같은 캔버스, 기본 viewBox 0 0 400 480)

| 파일 | 내용 |
| --- | --- |
| `parts/base.svg` | 몸 + 뜬 눈 + 볼. **입 없음**. 바닥 그림자 |
| `parts/eyes_closed.svg` | 눈 자리를 몸 색으로 덮고 감은 눈 선 |
| `parts/mouth_closed.svg` `mouth_a/e/i/o/u.svg` | 입 자리를 몸 색 패치로 덮고 그 위에 입 모양 |

- 덮는 패치가 몸과 이어져 보이도록 **그라데이션은 `gradientUnits="userSpaceOnUse"` 로 모든 파일에 같은 좌표**(base 의 하이라이트도 같이).
- 입 모양: a 크게 벌림(혀) · e 옆으로 벌림(윗니) · i 옆으로 좁게(이) · o 둥글게 · u 작게 오므림 · closed 미소 선.
- 2D 벡터 위주(Fluma 는 2D 우선). 단순한 도형 몇 개 + 큰 눈이 작은 크기에서도 잘 읽힌다.
- 남의 캐릭터 · 로고를 베끼지 않는다.

## character.json

```json
{ "name": "<이름>", "title": "<표시 이름>", "summary": "...", "personality": "...", "catchphrases": ["..."],
  "voice": { "provider": "edge", "voice": "ko-KR-SunHiNeural", "rate": "+5%", "pitch": "+12Hz" },
  "style": "2d-vector", "viewbox": [400, 480],
  "parts": { "base": "parts/base.svg", "eyes_closed": "parts/eyes_closed.svg",
             "mouth": { "closed": "parts/mouth_closed.svg", "a": "parts/mouth_a.svg", "e": "parts/mouth_e.svg", "i": "parts/mouth_i.svg", "o": "parts/mouth_o.svg", "u": "parts/mouth_u.svg" } },
  "placement": { "side": "right", "width": 240, "bottom": 36, "margin": 36 },
  "idle": { "bob_px": 8, "bob_period": 2.4, "blink_every": 3.4, "blink_len": 0.12 } }
```

## 확인

1. 부품 미리보기: `inkscape characters/<이름>/parts/base.svg --export-type=png --export-filename=/tmp/c.png -w 300` 를 열어 본다(입 · 눈 부품도 base 위에 겹쳐서).
2. 립싱크 구간: `python3 scripts/character_overlay.py visemes storyboards/<id>.json`
3. 빠른 렌더: `python3 scripts/render.py storyboards/<id>.json --draft` → 오른쪽 아래 캐릭터 확인.
