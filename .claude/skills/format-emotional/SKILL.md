---
name: format-emotional
description: 감성 형식(20초). 현장 스틸 켄번스 + 14자 이하 짧은 문장, 숫자 최소, 음악 주도.
order: 11
---

# 감성 (emotional)

- 길이 20초(최대 30). 장면: hook(3) → mood×3~5 → cta(3). 훅 화면은 still.
- mood 자막은 14자 이하 (L13). 한 문장, 마침표 없이.
- 숫자 장면은 1개 이하. 나레이션은 없어도 된다 (L04 하한 없음). `music_cue` 로 흐름을 준다 (calm → up → drop).
- 모든 mood 장면에 `visual.motion`(kenburns_in/out, pan_left/right)을 다르게 준다 — 스틸만 있어도 움직이게.
- 시간·장소·손을 보여 준다: "새벽 4시", "선별장", "상차".
- 참고: 이 형식으로 만든 콘티 `storyboards/<id>.json`
