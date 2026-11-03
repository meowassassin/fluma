# 그림 규칙집 (illustration craft)

화풍과 상관없이 잘 그린 그림이 지키는 규칙이다. open-design 의 `craft/` 를 그림에 옮겼다.
화풍마다 다른 것(색 · 비율 · 둥글기)은 `styles/<이름>/STYLE.md` 가 정하고, 여기는 **어느 화풍에서나 참인 것**만 다룬다.

| 파일 | 다루는 것 | 엔진이 막는 것(lint) |
|---|---|---|
| [shape-language.md](shape-language.md) | 도형 언어 · 크기 대비 · 실루엣 · 접선 | I03 크기 위계 · I04 실루엣 · I09 접선 |
| [appeal.md](appeal.md) | 매력 비율 · 표정 · 몸짓(동세선) | I07 굳은 자세 · I08 표정 없음 |
| [color-value.md](color-value.md) | 팔레트 · 60/30/10 · 명도 구조 · 그림자 색 | I01 기본 팔레트 · I02 회색 그림자 · I05 색 비율 · I06 명도 대비 |
| [motion.md](motion.md) | 애니메이션 원칙(예비 동작 · 따라오기 · 늘었다 줄기 · 겹침) | 엔진 동작(`figures.action`)이 기본으로 넣는다 |
| [anti-slop.md](anti-slop.md) | '초딩 티 · AI 티' 목록 | P0 는 그리기 거절 |

lint 실행: `python3 scripts/draw.py check <form.json> --style <style.json>` — P0 가 있으면 그리지 않는다.
