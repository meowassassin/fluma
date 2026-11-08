# data/

실행 중에 생기는 것만 둔다(git 에 올리지 않음). 지워도 코드는 그대로다.

| 폴더 | 무엇 |
|---|---|
| `storyboards/` | 콘티(영상 한 편의 정본) |
| `compositions/<id>/` | 제작 파일 — Craft 재료 · EffectCraft · SoundCraft · FilmCraft 프로젝트 |
| `audio/` | 나레이션 · 장면 타이밍 |
| `out/` | 렌더한 영상 |
| `public/` | 웹이 보여 주는 결과물 — 업로드 · 웹/터미널 녹화 · 트렌드 분석 · 음성 |
| `research/` · `briefs/` · `characters/` · `scenes/` | 조사 · 기획 카드 · 캐릭터 · 장면 설계도 |
| `workspace/` | 대화 · 렌더 캐시 · 기억 · 임시 파일 |
| `queue.md` | 매일 작업 대기열 |

Docker 는 이 폴더들을 볼륨으로 붙인다(`docker/docker-compose.yml`).
