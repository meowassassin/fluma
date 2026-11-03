# 대본 패턴 분석 (트렌드 층 3단계-A)

Claude Code에서 실행. 입력은 `references/<week>/transcripts/_index.json` 과 `*.txt`.
출력은 `rules/trends/<week>.json` 의 대본 관련 필드.

---

당신은 숏폼 대본 분석가다. 아래 자막 파일들은 최근 7일 안에 올라와 구독자 대비 조회가 높았던 한국어 정보형 쇼츠다.
**특정 채널의 문체나 표현을 베끼기 위한 분석이 아니다. 여러 영상에 공통으로 나타나는 구조적 패턴만 뽑는다.**

## 할 일

1. 영상마다 아래를 표로 채운다.
   - 훅 유형: question(질문) / number(숫자 제시) / contrarian(통념 반박) / pain(불편 공감) / other
   - 형식: concept / mythbust / compare / countdown / fix / story / other
   - 첫 문장 글자 수
   - 초당 글자 수 (chars_per_sec)
   - 포인트 개수 (전달하려는 핵심 정보가 몇 개인가)
   - 마무리 방식: 질문 되묻기 / 요약 / CTA / 끊김
2. 표본 전체에서 집계한다.
   - 훅 유형 비율, 형식 비율, 첫 문장 글자 수 중앙값, 초당 글자 수 중앙값, 포인트 개수 분포
   - 성과 상위 20%와 하위 20%의 차이가 뚜렷한 항목
3. 이번 주 많이 다뤄진 주제 10개 (우리 채널에 맞는 것만: 개발·마케팅·AI 툴·데이터).
4. 새로 보이는 장치나 구조가 있으면 `proposals`에 적는다. 자동 반영하지 말고 제안만.

## 출력 형식 (JSON만, 설명 없이)

```json
{
  "week": "<week>",
  "sample_size": 0,
  "hook_styles": {"question": 0, "number": 0, "contrarian": 0, "pain": 0},
  "formats": {"concept": 0, "mythbust": 0, "compare": 0, "countdown": 0, "fix": 0, "series": 0},
  "first_line_chars_median": 0,
  "chars_per_sec_median": 0,
  "points_per_video_mode": 1,
  "ending_styles": {"loop_question": 0, "summary": 0, "cta": 0, "cut": 0},
  "top_vs_bottom": ["성과 상위와 하위를 가르는 관찰 1", "..."],
  "trending_topics": ["...", "..."],
  "proposals": ["..."]
}
```

비율은 합계 1.0. 표본이 30개 미만이면 `"insufficient": true`를 넣고 나머지는 채우되, 갱신에는 쓰지 않는다.
