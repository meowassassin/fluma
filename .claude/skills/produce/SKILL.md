---
name: produce
description: 콘티를 영상으로 만든다(Craft 파이프라인 — 기본 엔진). 음성 → 장면 재료(차트 · 문서 인용 · 그림 · 사진 · 화면) → 검사 → 초안 렌더(EffectCraft → SoundCraft → FilmCraft) → 결과 확인. 홈의 '제작 시작', "만들어 줘", "초안 렌더" 요청에 쓴다.
order: 2
---

# 제작 (Craft 파이프라인)

엔진은 Craft 하나다(콘티 `engine: "craft"`). HyperFrames 화면 구성(compose 스킬 · `scene.js`)은 쓰지 않는다 — Craft 앱이 없는 환경에서만.
**색 · 배치는 레퍼런스에서**: 레퍼런스를 `ref_style.py` 로 분석했으면 `python3 scripts/direct.py storyboards/<id>.json --write` 로 콘티 `direction`(배경색 · 자막 위치 등)을 적는다. 안 했으면 엔진이 레퍼런스 장면 프레임에서 배경 톤을 잰다 — 어느 쪽이든 파란 기본색으로 두지 않는다.
화면은 '템플릿에 칸 채우기'가 아니라 **장면마다 무엇이 보여야 하는지(재료)** 를 정하는 것이다. 좌표 · 툴 이름은 쓰지 않는다.

## 순서
0. **레퍼런스 먼저(건너뛰지 않는다 — 검사 L30)**: 콘티에 `reference` 가 없으면 만들기 전에
   - trends 스킬로 같은 주제 · 형식의 실제 쇼츠를 찾는다: `python3 scripts/trends.py search --queries "<주제 검색어 2~3개>" --label "<주제>" --limit 8`
   - 조회수 높은 2~3편을 분해: `python3 scripts/shorts_xray.py <영상 id>` → `python3 scripts/ref_channel.py <영상 id> --n 4` → `public/trends/channels/<채널>/channel.md` 를 끝까지 읽는다
   - 거기서 가져온다: **문장 끝 비율 · 이음말 · 첫 문장 방식**(대사), **컷 길이 · 문장당 화면 수**(리듬), **화면 종류 비율 · 배경 · 자막 위치**(화면). 내용 · 대사 · 그림은 베끼지 않는다
   - 콘티 `reference: ["<id>", …]` 에 걸고, 대사를 그 채널 말투로 다시 쓴다(storyboard 스킬 '레퍼런스가 있으면' 절). 사용자가 레퍼런스 없이 하라고 했을 때만 `reference_skip: "<사용자 말>"`
   - 대사는 소리 내어 읽듯: 명사로 끊지 않고(…쓴 말. ✗ → …썼대요 ✓), 존댓말 · 반말을 섞지 않는다(검사 L31)
1. **음성**: `python3 scripts/assemble_audio.py storyboards/<id>.json` → `python3 scripts/lint.py storyboards/<id>.json` (L14 장면 길이 · L05 훅 3초). 걸리면 문장을 줄인다(내용 · 숫자는 그대로).
2. **장면 재료**(콘티 장면마다 `materials`): 그 장면이 말하는 것을 **눈으로 증명하는 것** 하나를 고른다.
   | 장면이 말하는 것 | 재료 | 만드는 앱(엔진이 고름) |
   |---|---|---|
   | 숫자 · 비율 · 비교 | `chart` — 원자료는 `compositions/<id>/src/*.csv`, 비율은 `percent: true`(손 계산 금지) | GridCraft |
   | 논문 · 보고서 · 기사 근거 | `doc_quote` — `pdf` + `find`(그 문장) | PdfCraft |
   | 인물 · 캐릭터 · 사물 | `illustration` — **illustrate 스킬로 이 영상만의 SVG 를 새로 그린다**. 기본은 통째로 한 장(글자 포함). 캐릭터를 움직이려면 `action`(idle · walk · wave · bounce) + 부품 이름 그룹 | VectorCraft |
   | 사용자 사진 · 캡처 | `photo` (`cutout: true` 면 누끼) | PhotoCraft |
   | 실제 화면 녹화 · 영상 | `screen` · `video` | 그대로 |
   - 재료가 없는 장면은 엔진이 그 장면의 핵심어(`visual.primary`) · 목록(`visual.items`)으로 화면을 짠다 — 그래서 `visual` 을 꼭 채운다.
   - 공통 칸: `id`, `cue`(등장할 나레이션 낱말), `place`(center · left · right · top · bottom · full).
   - 같은 캐릭터를 여러 장면에 쓰면 같은 `src` — 한 번 고치면 모든 장면이 바뀐다.
3. **검사**: `python3 scripts/lint.py storyboards/<id>.json` — 실패 0 이 될 때까지. T25(그래픽 위주)는 권고.
4. **초안 렌더**: `python3 scripts/render.py storyboards/<id>.json --draft` → `out/<id>-craft-Scenes-draft.mp4`
   제작 파일: `compositions/<id>/craft/` (`motion/*.ecproj` · `audio/*.scraft` · `edit/*.fcproj` · `materials/`). 사람이 Craft 에서 고친 파일은 해시로 알아채 덮어쓰지 않는다.
5. **확인**: `python3 scripts/still.py storyboards/<id>.json <초> …` → PNG 를 Read 로 직접 본다. 글자 겹침 · 잘림 · 빈 화면 · 재료가 말과 맞는지. 고칠 게 있으면 재료 · 콘티를 고치고 4로.
6. **최종 렌더는 하지 않는다** — 사용자가 편집기의 '렌더'를 눌러 의도 · 시안을 확인한다(관문).

## 하지 말 것
- compose 스킬 · `compositions/<id>/scene.js` · `direct.py --write` (HyperFrames 경로)
- 이전 영상의 그림 재사용(사용자가 원할 때만) · 레퍼런스 그림 베끼기
- 숫자를 재료 없이 글자만으로 보여 주기(차트 재료로)
