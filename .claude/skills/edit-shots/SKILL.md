---
name: edit-shots
description: 파이프라인 5단계 — 커스터마이징(fluma craft). 샷 검토를 통과한 생성 클립을 Craft 편집 엔진으로 옮겨 이펙트 · 편집 · 자막 · 장면 길이 · 나레이션(공급자 TTS)을 다듬는다. 음악은 보류.
---

# 5단계 — 커스터마이징(fluma craft)

조건: 4단계 모든 샷이 검토 통과(`video.py status` 의 approved).
1. `python3 engine/gen/assemble.py build <id>` — 통과 클립을 콘티(`data/storyboards/<id>.json`, 샷 = 장면, 생성 클립에서 `trim_in` 부터 `final_sec` 만큼, 클립 소리는 끔)로 옮기고 → 나레이션 음성(샷 계획 `narration`, 공급자 TTS: 설정의 음성 엔진 — typecast 등) → 초안 렌더.
2. 초안 정지 화면을 직접 보고 사용자와 다듬는다:
   - 장면 길이 · 쓸 구간: 샷 계획의 `final_sec` · `trim_in` 을 고치고 `assemble.py build` 다시(콘티를 다시 만들어도 direction · subs 같은 편집 값은 남는다).
   - 자막 · 제목 · 색 · 효과: `python3 engine/story/knob.py set <id> <경로>=<값>` → `knob.py preview <id> --scene <n>`(값으로 고치기).
   - 장면 디테일(빛 · 질감 · 움직임 · 전환): refine 스킬(`engine/craft/session.py`).
3. 음악은 넣지 않는다(보류 — `music.use=false`, 자리만).
4. **엔진 2개의 역할 규칙**:
   - Craft는 초안(draft)만 만듭니다.
   - 편집 화면이나 파이프라인 화면에서 "편집기로 넘기기"를 눌러 타임라인 편집기(`/veditor/<id>`)로 이동합니다.
   - 편집기로 넘긴 영상은 타임라인 편집기에서 내보낸 것(`data/compositions/<id>/editor/exported.mp4` / `data/out/<id>-editor.mp4`)이 최종본입니다.
5. 편집기에서 내보내기가 완료되면 6단계(배포 · 업로드)로 이어집니다.

## 사용자 명령 구분 — 어디서 고칠 것인가 (먼저 판단하고, 무엇을 할지 한 줄로 알린다)
| 요청 | 어디서 | 방법 |
|---|---|---|
| 자막 · 제목 · 글자 · 위치 · 크기 · 색 · 효과 · 전환 · 장면 길이 · 컷 순서 · 소리 크기 · 나레이션 문장 | **5단계 Craft 편집** | `knob.py set` → `preview` · refine 스킬(`session.py`) · Craft MCP 도구 · 샷 계획 `final_sec` · `trim_in` · `narration` → `assemble.py build` |
| 클립 **안의 내용**: 인물 동작 · 표정 · 시선 · 카메라 움직임 · 배경 속 사건 | **4단계 재생성** | 그 샷만. 사용자에게 "샷 N 을 다시 생성(남은 n회 · 크레딧 예상)"을 묻고, 1단계 샷 칸(action · camera_move · end_state …)을 고친 뒤 `video.py run --shots N` |
| 캐릭터 외형(얼굴 · 머리 · 옷)이나 화풍 · 배경 장소 | **2 · 3단계부터** | 캐릭터 설명 · style · background 를 고치면 승인 ① · ② 가 풀린다 — 시트 · 키 프레임 · 그 샷들 영상을 다시. 비용과 범위를 먼저 알린다 |
| 둘 다 걸치면 | 나눠서 | 층 편집은 바로 하고, 재생성이 필요한 부분만 따로 묻는다 |
Craft 로 클립 안의 내용을 흉내 내지 않는다(예: 표정을 그림으로 덧칠). 사용자가 Craft 파일을 직접 고친 단계는 해시로 보호된다 — 그 단계를 다시 만들어야 하면 먼저 묻는다.

하지 않는 것: 생성 클립 안에 글자를 다시 만들지 않는다(글자 · 자막은 여기서 얹는다). 클립을 손으로 다시 생성하지 않는다(4단계 재생성으로).

> 자막 · 글자 값은 `python3 engine/gen/subs.py get <id>` / `put <id> <파일.json>` 으로 읽고 쓴다 — 작업 공간 '자막 · 글자 편집' 화면과 같은 모양 · 같은 파일이라, 사람이 화면에서 고친 값과 에이전트가 고친 값이 섞이지 않고 이어진다. 저장할 때마다 앞 판이 data/compositions/<id>/edits/ 에 남는다. 확정 미리보기는 정지 화면(약 2초), 영상 반영은 초안 다시 만들기.
