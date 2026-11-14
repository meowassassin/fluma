---
name: plan
description: 파이프라인 1단계 — 기획. 먼저 영상 생성이 필요한지 판단해 경로(생성 · 클립 재편집 · 실제 자료 편집)를 고르고, 생성이면 기존 트렌드 분석으로 추천 선택지를 보여 주고, 사용자 설명 · 선택으로 카메라 · 배경 · 동작까지 확정한 뒤 8초 이하 샷 목록(data/shotplans/<id>.json)을 쓴다. 캐릭터 · 레퍼런스 이미지가 필요한지(2단계 여부)도 여기서 정한다.
order: 0
---

# 1단계 — 기획: 프롬프트 · 플롯 작성

흐름 전체(1 기획 → 2 캐릭터 시트 · 승인 ① → 3 키 프레임 · 승인 ② → 4 영상 생성 → 5 craft → 6 렌더 · 업로드 · 분석)에서 이 스킬은 1단계만 한다.
**수동(검토) 모드**: 정할 것은 사용자에게 선택지로 보여 주고 고르게 한다. 고르기 전에 다음 단계로 넘어가지 않는다.
오케스트레이터(Claude Code · Codex · Antigravity)가 누구든 같은 명령만 쓴다 — `engine/gen/plan.py`.

## 0. 경로부터 — 에이전트가 추천하고 사용자가 고른다 (매 영상, 기획 전에)
생성은 크레딧 · 시간 · 승인 두 번이 든다. 실제 자료로 충분하면 생성을 추천하지 않는다.
- 요청 전체(주제 · 링크 · 레퍼런스 화풍 · 필요한 장면)를 보고 추천 경로와 이유 한 줄을 정한다:
  - **generate**(생성): 세상에 없는 장면 · 캐릭터 연기 · 상상 · 이야기가 중심 → 아래 1~6 순서.
  - **clip**(클립 재편집): 원본 영상 하나를 다시 엮는 밈 · 반응 · 더빙 자막 → asset-edit 스킬.
  - **material**(실제 자료 편집): 설명 · 뉴스 · 비교 · 순위 · 사용법 · 광고처럼 화면 녹화 · 사진 · 스톡 · 퍼온 클립 · 차트 · 문서로 충분 → storyboard · produce 스킬.
- 세 경로를 ```choices``` 로 보여 준다 — 추천을 첫째에 이유와 함께, 나머지는 무엇이 달라지는지(비용 · 시간 · 느낌) 한 줄씩. **사용자가 고른 뒤** `python3 engine/gen/route.py set <id> <경로> --why "<이유>" --topic "<주제>"`.
  사용자가 '알아서'라고 하면 추천대로 `--by default`.
- 섞기: 실제 자료 영상에 '없는 장면' 한두 컷만 필요하면 material 을 추천하고, 그 컷만 생성 경로 샷으로 따로 만들어 재료로 넣는 것을 선택지에 함께 적는다.

## 순서 (generate 경로)
1. **트렌드 → 추천 선택지**: 기존 트렌드 분석을 읽는다(새로 분석 기능을 만들지 않는다).
   `python3 engine/gen/plan.py trends [--request <rid>] [--label <이름>]` — 훅 유형 빈도 · 화풍 · 조회수 상위 · X-ray recipe.
   결과가 없으면 trends 스킬(`engine/research/trends.py search`)로 먼저 찾는다.
   이 재료로 **추천 선택지 2~4개**(훅 · 플롯 한 줄 · 화풍 · 길이, 근거 쇼츠 id)를 ```choices``` 로 보여 준다. **추천 선택지 중 최소 1개는 반드시 3D 캐릭터/3D 무대 연출 스타일(예: 3D 말랑한 비닐토이/피규어 소동물 애니메이션, 3D 소품 기믹 연출)**을 포함하여 디자인 및 형태의 다양성을 확보한다. 사용자가 고르거나 직접 설명한다.
2. **디테일 확정**: 영상 생성이 한 번에 끝나도록 샷마다 카메라 워킹 · 배경 · 동작을 정한다. 모르는 칸은 짐작하지 말고 선택지로 묻는다(한 턴에 질문 하나).
3. **샷 분할**: 장면을 샷으로 나눈다. 한 샷 = 한 순간(동작이 둘이면 샷을 나눈다). 생성 길이는 모델마다 — Veo 4 · 6 · 8 · Omni Flash 4~10 · Omni 1.2 Flash 3~15초.
   **모션그래픽**(키네틱 타이포 · 콜라주 · 도해 · 그래픽 전환)은 `kind: "motion"` — 키 프레임 없이 `style_ref`(레퍼런스 쇼츠 id) 대표 프레임을 매번 그림 레퍼런스로 붙여 생성한다.
   칸: action(무엇이 나타나 어떻게 움직이나) · on_screen_text(6단어 이하, 정확히) · transition_out · sfx · music_mood. `style` 은 레퍼런스 이해의 `motion_design.style_en` 을 바탕으로(움직임 · hex 색 · 타이포).
3-1. **레퍼런스가 있으면 먼저 이해한다** — `python3 engine/research/analyze_ref.py <링크>`(수치 분해 · 스타일 카드 · 레퍼런스 이해까지 서버 작업으로) 뒤 `xray.json` 의 `understanding`(훅 · 반전 · 편집 문법 · 빌릴 것 · 베끼면 안 되는 것)을 읽는다. 감성 기준을 말했으면 `engine/look/anchor.py set`, 여러 편이면 `engine/look/look.py cliches <id>` 로 뻔함 지도 초안.
4. **D1 — 캐릭터 · 레퍼런스 이미지가 필요한가**: 여러 샷에 같은 인물 · 생물 · 마스코트가 나오면 `needs_character: true` 와 `characters[]`(바뀌지 않는 특징: 체형 · 나이 · 머리 · 얼굴 · 눈 · 표식 · 옷, 대사가 있으면 voice). 아니면 false → 2단계를 건너뛴다.
5. **쓰기 · 검사**: `python3 engine/gen/plan.py new <id> --topic "<주제>"` → `data/shotplans/<id>.json` 을 채운다(칸 설명: `engine/spec/schema/shotplan.schema.json`) → `python3 engine/gen/plan.py check <id>` 가 실패 없이 통과할 때까지. △ 권고도 읽고 고칠 수 있으면 고친다.
6. **보여 주기**: 샷 표 | # | 목적 | 생성/편집 초 | 크기 · 앵글 · 움직임 | 시작 → 동작 → 끝 | 배경 | 소리 | 와 `plan.py prompts <id>` 의 조립된 프롬프트를 보여 주고, 다음 단계(2 또는 3)로 갈지 선택지로 묻는다.

## 샷 칸 쓰는 법 — 프롬프트는 통째로 쓰지 않는다
칸을 채우면 `plan.py` 가 조사된 규칙대로 글로 조립한다(`plan.py guide` · 근거와 출처 수: 볼트 `02 Architecture/숏폼 생성 파이프라인 — 프롬프트 · 구조 조사 (2026-11-11)`).
- **무음 직관성 규칙 (Mute Test — 가장 중요)**:
  - 소리를 끄고 정지 화면 한 장만 봐도 **무슨 주제(예: 크롬 브라우저 탭 과부하, RAM 메모리 슬롯, USB 방향, 배포 버튼 등)인지 1초 만에 알아볼 수 있어야** 한다.
  - **추상적 은유 절대 금지**: 데이터 · 탭 · 메모리 · 작업량 · 트래픽을 뜻 모를 구슬(`glowing spheres` · `orbs` · `energy balls`)이나 빛덩이로 바꾸지 않는다(`plan.py check` 에서 즉시 실패 처리됨).
  - **글자 없는 구체적 3D 사물(Iconic Props)**: 글자(`text`)를 쓰지 않고도 형태와 색만으로 주제가 직관적으로 보이는 3D 사물을 매 샷의 `start_state` · `action` · `background` 에 정확히 적는다:
    - 브라우저 창/탭 → `translucent floating browser window panels with red-yellow-green top corner dots and colored tab headers`
    - 클릭/사용자 조작 → `giant white 3D mouse cursor arrow clicking downward`
    - 컴퓨터/RAM → `pastel green motherboard with glowing gold-pinned RAM stick slots and spinning cooling fan blades`
    - 렉/과부하/멈춤 → `glowing blue 3D circular loading spinner ring floating above the head` + `flashing coral-red warning beacon`
    - 해결/창 닫기 → `chunky red 3D close button block with a raised X icon`
- **4막 인과관계 규칙 (기승전결 — 같은 상황 반복 · 시간 역전 금지)**:
  1. `hook`(원인 · 사건 시작, 편집 3.0초 이하): 시청자의 시선을 멈추는 **사건의 시작 트리거**와 핵심 사물이 등장(예: 거대한 마우스 커서가 연달아 클릭할 때마다 하늘에서 브라우저 창 패널들이 우르르 떨어져 캐릭터가 첫 창들을 떠받침). *주의: 1번 샷에서 이미 완전히 파묻혀 기절한 결말 상태를 먼저 보여준 뒤 2번 샷에서 다시 멀쩡히 서서 일하는 식의 시간 역전을 절대 금한다.*
  2. `build`(작동 원리 · 고군분투): 캐릭터가 주제 환경에서 구체적 도구를 다루며 문제를 감당하려 애쓰는 과정(예: RAM 슬롯 사이를 뛰어다니며 창 패널들을 꽂아 넣지만 슬롯이 포화되고 쿨링팬이 과열됨).
  3. `turn`(임계점 돌파 · 위기 · 반전): 과부하 · 멈춤 · 오류가 극에 달해 앞 샷과 **조명 · 카메라 앵글 · 상태가 확연히 달라지는 절정**(예: 붉은 경고등이 켜지고 끝없이 밀려든 창 패널들에 밀려 앞 유리에 볼이 납작하게 눌린 채 머리 위에 버퍼링 로딩 링이 도는 프리징 순간).
  4. `payoff`(해결 트리거 · 해방): 문제를 해결하는 명확한 행동 하나(예: 거대한 마우스 커서가 빨간 X 닫기 블록을 딸깍 누름)와 그로 인한 즉각적인 해소 · 평화.
- **샷마다 시점 변화**: 연속된 두 샷에 똑같은 `shot_size` + `angle` 조합을 반복하지 않는다(예: `close-up` → `medium wide shot` → `medium close-up high-angle` → `wide shot`).
- **나레이션 호흡 · 화면 동기화**:
  - `narration` 은 `' / '` 로 샷 수만큼 나누며, 각 샷의 나레이션 글자 수(공백 제외)는 **`final_sec × 5.8자` 이하**여야 한다(예: 3.0초 훅은 공백 제외 17자 / 공백 포함 약 22자 이내). 이보다 길면 음성이 다음 샷으로 넘쳐 화면과 싱크가 깨진다(`plan.py check` 가 검사함).
  - 나레이션에서 말하는 대상("크롬 탭을 열 때마다", "창만 닫아 줘도")과 그 순간 화면에 보이는 사물 · 행동이 1:1로 일치해야 한다.
- 샷마다: `purpose`(hook · build · turn · payoff · cta) · `gen_sec`(4 · 6 · 8) · `final_sec`(편집에서 쓸 길이, 첫 샷 3초 이하) · `shot_size` · `angle` · `camera_move`(하나, 정해진 목록) · `camera_intent` · `subject_pos`(9:16 화면 안 위치 · 시선) · `start_state`(= 키 프레임 모습) · `action`(동작 하나와 속도) · `env_motion` · `end_state` · `background` · `lighting` · `ambient`(침묵이라도) · `sfx` · `avoid`(명사).
- 영어로 쓴다(생성 모델 입력). 한 샷에 동작 하나 — 'then' 이 들어가면 샷을 나눈다.
- 캐릭터: `identity`(정체 표식을 하나씩 — 머리 · 얼굴 · 표식) · `wardrobe`(옷 한 줄, 모든 프롬프트에 글자 그대로). 이름은 영어 한 단어.
- 생성 영상은 대사 · 음악 없이(조립이 'No dialogue. No music.'). 나레이션은 `narration` → 5단계 TTS. 대사가 꼭 필요할 때만 `dialogue`(8초에 20단어 이하, 따옴표 없이).
- 쓰지 않는다: cinematic · 35mm · IMAX · film grain(레터박스), 4k · masterpiece 같은 꾸밈말, 영상 칸의 나이 단어, 간판 · 포스터 · 메뉴처럼 글자를 품은 물건(글자는 편집에서).
- 피할 장면: 인물 교차 · 작은 물건 쥔 손 · 거울 · 샷 안 조명 변화 · 군중 동작 · 얼굴 가리는 부감.
- `end_frame: true` 는 구도가 정확히 끝나야 하는 샷만(시작 · 끝 구도가 가깝고 바뀌는 것 하나).

## 화면 블록
- ```choices``` — 답 끝에 하나, 2~4개, 그대로 보내도 말이 되는 지시.
- ```brief``` — 정해진 것을 `키: 값`(주제 · 고른 선택지 · 화풍 · 샷 수 · 총 길이 · 캐릭터 · 남은 결정).

## 하지 않는 것
- 이 단계에서 이미지 · 영상을 생성하지 않는다(2 · 3 · 4단계).
- 사용자가 고르기 전에 다음 단계로 넘어가지 않는다.
- 확정된 결정(fluma 숏폼 파이프라인 스펙)을 바꾸지 않는다. 스펙에 없는 설계 결정이 필요하면 사용자에게 묻는다.
