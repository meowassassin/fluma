---
name: trends
description: 트렌드 쇼츠를 찾아 트렌드 화면에 바로 띄운다. "트렌드 더 찾아봐", "AWS 관련 쇼츠 찾아줘" 같은 말을 검색어(구체 주제) · 해시태그(넓은 분야 · 스타일)로 바꿔 engine/research/trends.py 를 부른다.
---

# 트렌드 찾기

사용자 말 → 검색어 2~5개(+ 필요하면 해시태그) → `python3 engine/research/trends.py search ...` → 결과 요약. 화면은 `data/public/trends/index.json` 이 바뀔 때마다 저절로 갱신된다(검색어 · 해시태그 하나 끝날 때마다).

## 검색어 먼저 (구체적인 주제)

- **주제 · 제품 · 기술 · 브랜드 · 사람 이름이 있으면 반드시 `--queries`**. YouTube 검색(쇼츠 필터, 관련도순)이라 사용자가 youtube.com 에서 검색해 보는 것과 같다.
  해시태그 페이지(`#aws`)는 그 태그를 단 아무 영상(게임 · 일상)이나 나와서 관련 없는 것이 섞인다.
- 검색어는 사용자 말의 핵심어 + 하위 주제로 넓힌다. 한국어 · 영어를 섞는다.
  예: "AWS 관련 쇼츠" → `--queries "aws,aws build,aws 아키텍처,aws lambda,aws 자격증"`
  예: "노션 팁" → `--queries "notion tips,노션 꿀팁,notion template"` / "아이폰 17 리뷰" → `--queries "iphone 17 review,아이폰 17 리뷰"`
- 스타일까지 말하면 검색어에 붙인다: "AWS 2D 애니메이션" → `"aws explained animation,aws animated explainer,aws 2d animation"` (+ `--want` 자동).
- 결과가 적거나 엉뚱하면 검색어를 바꿔 다시 (핵심어를 앞에, 더 구체적으로). 결과를 보고 주제와 무관한 제목이 많으면 그 검색어는 버린다.

## 해시태그 (넓은 분야 · 스타일 탐색)

- 한국어 · 영어를 섞는다(한국 쇼츠 + 세계 쇼츠). 예: IT → `코딩,개발자,테크리뷰,gadgets,techtok,programming`
- **넓은 태그 하나만 쓰지 않는다.** `#IT` `#tech` 는 고양이 · 연예 영상이 섞인다 → 구체적인 태그(기기 · 직업 · 행동)를 같이.
- **2D · 3D 는 나누지 않는다**(2026-11-06): 3D 쇼츠도 X-ray 로 분해해 화면 문법(`engine/story/look.py`)으로 쓰면 된다. 분야 요청이 오면 그 분야의 애니메이션 · 모션그래픽 태그를 하나 이상 섞는다(2D · 3D 모두).
  예: 과학 → `과학,science,sciencefacts,2danimation,explainer` / 게임 → `게임,gaming,2danimation,pixelart`
- 스타일 요청: 2D → `2danimation,motiongraphics,애니메이션,animation` · 설명형 → `explainer,kurzgesagt,motiongraphics`
- **2D 요청에 분야 태그를 그냥 섞지 않는다.** `게임` `gaming` `개발자` `코딩` `programming` 같은 분야 태그는 대부분 실사(사람 · 게임 플레이 화면)다. 분야는 **애니메이션 태그와 붙인 형태**로 쓴다:
  게임 2D → `gameanimation,pixelart,pixelartanimation,indiegameart,2dgameart,도트` / IT 2D → `techanimation,codinganimation,explaineranimation,developeranimation,motiongraphics,2danimation` / 과학 2D → `scienceanimation,animatedexplainer,kurzgesagt,2danimation`
- **화풍 판별**: `trends.py search` 가 썸네일을 이미지 모델(CLIP)로 보고 2D · 픽셀 · 3D · 실사 · 화면녹화를 표시한다(트렌드 화면의 '화풍' 막대). 거르기는 최소로 — 아무 말이 없으면 거르지 않고, 애니메이션(2D · 3D · 픽셀 · 모션그래픽)을 말하면 2D · 3D · 픽셀을 한 묶음으로 남기고, "실사" · "화면 녹화"를 콕 집어 말할 때만 그것으로 거른다. 직접 정하려면 `--want 2d,3d,pixel` / `--want live` / `--want any`. 결과에 "화풍이 달라 뺀 것 n편"이 많으면 그 태그는 다음부터 쓰지 않는다.
- 이미 모은 것 다시 판별: `python3 engine/research/trends.py classify` (`--prune` 이면 요청과 맞지 않는 것을 지움 — 사용자가 원할 때만)
- "더 찾아봐"(분야 없음) → 지난 요청(`python3 engine/research/trends.py list`)과 겹치지 않는 태그로, 애니메이션 · 모션그래픽(2D · 3D) 쪽을 우선.

## 부르기

```
python3 engine/research/trends.py search --queries "<검색어들>" [--tags "<태그들>"] --label "<화면 이름, 짧게>" --category "<2D 애니메이션|모션그래픽|과학|테크|게임|예능|광고|요리|기타>" --limit 8 --request "<사용자 말 원문>"
```

- `--limit` 기본 8. "많이" → 12, "조금" → 4.
- 지우기: `python3 engine/research/trends.py remove --request <rid>`

## 답하기

- 짧게: 몇 편 찾았는지(검색어별), 주제와 무관한 것이 섞였으면 솔직히 말하고 지우기(`remove`) · 다시 찾기 제안, 조회수 상위 3편의 **패턴**(훅 유형 · 길이감 · 화풍), Fluma 로 만들 때 어떻게 쌓을지 한 줄(Craft 재료 · 실제 화면 · 퍼온 클립 — X-ray 를 화면 문법으로).
- 훅 유형은 제목으로 어림한 것(`hook` 필드)이라 "추정"이라고 말한다.
- 영상 · 캐릭터 · 글꼴을 베끼자고 하지 않는다. 패턴만.

## 실제로 보고 분석 (패턴 분석 · "이 쇼츠처럼")

- 제목 · 썸네일로 짐작하지 말고 `python3 engine/research/trend_analyze.py <영상 id …>` 로 **영상을 직접 본다**(받아서 재고 바로 지움 — 패턴만 남김).
- 편집 요소까지 나눠 봐야 하면(샷 · 누끼 · 배경판 · 화면 글자 · 대사 · 박자 · 효과음) `python3 engine/research/analyze_ref.py <영상 id> --no-channel` — 결과 data/public/trends/xray/<id>/xray.json 의 `recipe` 를 읽고, 사용자에게는 트렌드 화면의 '분해도'(/trends/x/<id>)를 열어 보라고 한다. 누끼 · 배경판은 참고용이라 영상에 쓰지 않는다.
- 출력의 컷 수 · 평균 샷 길이 · 첫 컷 · 글자 자리 · 움직임 · 색을 쓰고, **밀착 시트 `data/public/trends/analysis/<id>.jpg` 를 Read 로 열어** 화면 구성(무엇이 크게, 어디에, 어떤 순서로)을 직접 확인한다.
- 분석 결과는 트렌드 카드에 표시된다. 새 영상으로 이어갈 때는 storyboard · produce 스킬에서 이 리듬 · 글자 자리 · 색 관계를 옮긴다(내용 · 인물 · 로고는 베끼지 않음).
