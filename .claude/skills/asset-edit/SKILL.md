---
name: asset-edit
description: 실제 에셋 경로 — 퍼온 클립을 다시 편집하는 밈 · 반응 · 더빙 자막 쇼츠. 생성 경로의 2~4단계(캐릭터 시트 · 키 프레임 · 영상 생성)를 건너뛰고 1 기획 → 더빙 계획 → 5 Craft 편집 → 6 렌더 · 업로드. "이 영상으로 밈", "실제 클립으로", "더빙 자막" 요청에 쓴다.
---

# 실제 에셋 경로 (클립 재편집)

화면 · 자막은 Craft 도구가 맡는다: 클립 · 끼워 넣기 · 검은 화면 = 장면(FilmCraft), 두 줄 제목 = `typo-headline`, 더빙 자막 = `typo-dub-at`(EffectCraft 레시피), 삐 = 효과음 `bleep`.

## 순서
1. **레퍼런스 문법**: 사용자가 준 레퍼런스를 `engine/research/analyze_ref.py <링크>` 로 재고(창 크기 · 제목 · 자막 위치 · 컷 리듬 · 끊어 넣기 장치), 형식을 베끼지 말고 장치만 빌린다.
2. **클립**: 사용자가 준 원본(또는 `engine/capture/clip.py search`) → `clip.py fetch <id> c1 <주소> --in --out --subs [--max 60]`(원래 말을 단어 시각으로 받아씀). 권리는 사용자가 판단, 출처는 meta.json 에 남는다(`clip.py credits`). 방송 · 스포츠 영상은 신고 위험을 알린다.
3. **끊을 자리**: `python3 engine/capture/cutaway.py <id>/c1` — 빔(박수 · 웃음) · 반복 · 질문 · 욕 · 말 막힘 후보.
4. **더빙 계획** `data/compositions/<id>/dub.json`(칸 설명: `engine/gen/dub.py` 맨 위): 구간(clip · insert · black, 각 2초 이상) + 자막(구간 기준 시각 · 크기 S/M/L/XL · 위치 · hot=노랑).
   - 자막은 원래 말을 옮기지 않고 **한국어 구어 더빙 말투**로(writer 스킬), 한 번에 한 덩어리 · 강조어는 크게, 욕은 기호로(ㅆ@ · ㄷ#@) 가리고 `bleep`.
   - 끊어 넣기(insert)는 무료 · 출처 있는 그림 · 영상(스톡 키가 있으면 stock, 없으면 Commons 공유 저작물), `credit` 을 적는다.
5. `python3 engine/gen/dub.py check <id>` → `build <id>`(콘티 → 소리 → 초안). 정지 화면을 보고 dub.json 을 고쳐 다시 build. 화면 세부(창 크기 · 색 · 빛)는 콘티 adjust · `knob.py` · refine.
6. 사용자가 '좋아'면 6단계(`engine/gen/publish.py final` · 업로드는 요청 때만).

> 자막 · 글자 값은 `python3 engine/gen/subs.py get <id>` / `put <id> <파일.json>` 으로 읽고 쓴다 — 작업 공간 '자막 · 글자 편집' 화면과 같은 모양 · 같은 파일이라, 사람이 화면에서 고친 값과 에이전트가 고친 값이 섞이지 않고 이어진다. 저장할 때마다 앞 판이 data/compositions/<id>/edits/ 에 남는다. 확정 미리보기는 정지 화면(약 2초), 영상 반영은 초안 다시 만들기.

## 하지 않는 것
- 특정 영상을 그대로 재현하지 않는다(장치만 빌림). 영상 생성 단계를 부르지 않는다.
