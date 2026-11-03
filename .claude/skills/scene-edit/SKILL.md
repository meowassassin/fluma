---
name: scene-edit
description: 지정한 장면 하나만 고친다. 다른 장면과 sec 합계는 그대로. 장면 코멘트(💬)로 들어온 요청에 쓴다.
order: 3
---

# 장면 하나 고치기

- **시각으로 말한 요청**("12초부터 나오는 서버가 너무 작아, 데이터 이동도 빠르게"): 먼저 `python3 scripts/frame_at.py storyboards/<id>.json 12` → 그 시각의 장면 · 나레이션 단어 시각 · 보이는 요소(scene.js 의 name · 위치 · 크기 · 손 수정 키). 그 요소만 고친다.
  - 크기: 그 요소의 w · h · size(또는 scale). 속도: 그 움직임의 dur 를 줄이거나 시작을 `c.cue("…")` 단어에 맞춤. 다른 요소 · 장면은 그대로.
  - 3D 개체(Blender 요소)를 키우는 건 다시 렌더하지 않고 K.seq 의 w · h 로. 움직임 자체를 바꿔야 할 때만 스크립트를 고쳐 다시 렌더.
  - 고친 뒤 `frame_at.py … 12 --png` 로 그 순간을 다시 보고, `overlap_check.py` 로 잘림 · 겹침 확인.
- 요청에 `[장면 N 코멘트]` 가 있으면 **scenes[N] 만** 수정한다. 다른 장면, `duration_sec`, 장면 수는 바꾸지 않는다.
- sec 를 바꿔야 하면 그 장면과 바로 옆 장면 사이에서만 주고받아 합계를 유지하고, 그렇게 했다고 말한다.
- 정지 화면 경로가 같이 오면 Read 로 먼저 보고 고친다.
- 고친 뒤 `python3 scripts/lint.py storyboards/<id>.json`. 다른 장면의 기존 실패는 범위 밖이면 그대로 두고 알려만 준다.
- 화면이 바뀌는 수정(자막 길이, 큰 값)은 `python3 scripts/still.py storyboards/<id>.json <그 장면 중간 초>` 로 한 장 찍어 확인한다.
- **말투 · 어미 · 톤만 고쳐 달라는 요청**: 문장을 새로 쓰지 않는다. `python3 scripts/tone_edit.py storyboards/<id>.json <바꿀 글 json>` 으로 확인 → 통과하면 `--apply`, 전 · 후 표를 그대로 보여 준다. 내용 낱말이 바뀌면 도구가 거절한다. 사용자가 문장을 직접 불러 줬으면 `--user-text`.
- 사용자 지적은 이 영상의 규칙으로 콘티 `intent.must` / `must_not` 에 한 줄 더한다(기억 말고) — 다음 장면 · 다음 수정에서 같은 지적이 다시 나오지 않게.
- 장면 1~3 의 화면(visual · elements · screen · beat)을 바꾸면 시안 승인이 풀린다 — 시안을 다시 보여 주고 `gate.py draft` 를 사용자 확인 뒤에.

