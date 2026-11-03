---
name: compose
description: (HyperFrames 엔진 전용 — 기본 엔진은 Craft 이고 그때는 produce 스킬) 영상마다 화면 · 움직임을 직접 짠다(템플릿 채우기 아님). compositions/<id>/scene.js 에 Fluma Kit 로 장면별 구성을 쓰고, 정지 화면으로 스스로 확인한다. 새 영상 · "너무 단순해" · "다른 스타일로" · 트렌드 참고 요청에 쓴다.
---

# 컴포지션 짜기 (영상마다 새로)

콘티(storyboards/<id>.json)는 **내용과 타이밍**, 컴포지션(compositions/<id>/scene.js)은 **화면과 움직임**. 템플릿 하나를 채우지 말고 영상마다 새로 짠다.

## 재료가 먼저 — 그래픽은 그 위에 (2026-11-02 "AI 티가 확 난다" 이후의 기본)
코드로 그린 카드 · 막대 · 글자만으로 채운 영상은 어떤 효과를 빼도 템플릿처럼 보인다. 장면마다 **보여 줄 재료의 역할**부터 정한다.
- **증거 = 실제 화면 녹화**: 사이트 · 앱 · 터미널은 정지 캡처 카드 대신 `webrec.py` 로 조작을 녹화해 `K.web`(커서 · 클릭 · 반응 · 확대)으로. 전 → 동작 → 후가 보이게. 화면은 폰 크기에서 읽히게 크게 자르고 확대한다(작은 카드 금지).
- **사람 · 현장 = 올린 영상 · 캐릭터**: 사람이 말하거나 무언가를 하는 장면은 사용자가 올린 영상(uploads)이나 캐릭터(character 스킬)로. 실사 영상 생성은 쓰지 않는다(2026-11-03 제품 방향).
- **보충 = B-roll**: 설명을 덮는 실사 · 생성 이미지 · 짤(권리는 사용자 판단).
- **그래픽 = 관계 설명**: 비교 · 순서 · 숫자처럼 재료만으로 안 보이는 '관계'일 때만. 등장이 아니라 **변화**를 연출한다 — 같은 물체가 상태를 바꾸며 이어지고(카드가 첨부가 되고, 막대가 늘고), 말한 단어(c.cue)에서 바뀐다.
- 검사: T25(그래픽 위주) · T26(실제 화면이 정지 캡처뿐) · L18(렌더 화면의 기울기 · 흐림 · 그라데이션 · 빛 · 같은 틀 — `look_check.py`).

## 배치는 숫자로 — 손으로 정하지 않는다
자막 위치 · 크기 · 한 줄 글자 수 · 상자, 고정 제목 자리, 화면 판(띠)은 콘티 `preset`(형식 프리셋) 또는 레퍼런스 채널 카드의 `layout` 숫자를 따른다.
`K.talk` 의 `SAFE` · `subs` · `title` 이 그 숫자를 읽는다 — 자막은 `k.subs(root)`, 제목은 `k.title(root, …)` 만 쓰고 y · 크기를 직접 넣지 않는다.
프리셋이 '자막 거의 없음'이면 subs 는 아무것도 그리지 않고, '고정 제목 없음'이면 title 도 그리지 않는다(look_check 의 '프리셋과 다른 배치'가 잰다).

## 순서

0. **참고 쇼츠가 있으면 먼저 본다** (콘티에 `"reference": ["<id>"]` — 편집기 타임라인에 참고 리듬으로 나온다): `python3 scripts/trend_analyze.py <id>` → 밀착 시트를 직접 열어 화면 구성을 본다.
1. **디자인 방향 정하기 (필수)**: `python3 scripts/direct.py storyboards/<id>.json --write`
   - 축마다(바탕 · 색 · 글자 · 배치 · 움직임 · 전환 · 자막 · 주인공 장치) 하나씩 정해 콘티 `direction` 에 적는다. 참고 쇼츠 패턴을 먼저 따르고, **최근 영상이 쓴 선택은 피한다**.
   - 장면은 모두 scene.js(HyperFrames)가 그린다. 장면마다 엔진을 바꾸지 않는다(엔진마다 화면 질감이 달라 한 영상이 이어 붙인 것처럼 보이고, 일부 엔진은 그림이 떨렸다 — 2026-10-29 실측). 다른 엔진의 장점은 **장면 안 레이어 요소**로만 쓴다(아래).
   - 지시서가 마음에 안 들면 `--reroll` 로 다시 뽑는다.
   - `direction` 값을 손으로 고치지 않는다(목록에 없는 값이 생김) — 바꾸려면 `--reroll N`. 공유 기억에서 싫다고 한 것(네온 · 굵은 테두리 자막 등)은 direct.py 가 알아서 뺀다.
2. **요소 준비**(콘티 `elements`): 재사용 먼저 → 없을 때만 새로.
   - 로고 · 아이콘: `python3 scripts/icons.py fetch <id> github githubactions …` → `"github.svg"` (없으면 일반 모양 SVG 를 직접 그림)
   - 3D 개체: `python3 scripts/element.py library` 에 있으면 `element.py reuse <이름> <id>` (다시 렌더하지 않음). 없으면 Blender 로 만들고 좋으면 `element.py save … --as <이름> --desc "…"` 로 라이브러리에 남긴다
   - 정밀 도표: `element.py manim <id> <이름> --scene N` (그 장면 나레이션 단어 시각이 SF_STYLE.words 로 들어감 → 스크립트에서 cue)
3. 지시서의 **모든 축을 지켜** `compositions/<id>/scene.js` 를 쓴다(아래 형식). 장면 수 = 콘티 장면 수.
   - **움직임은 음성 타이밍 기준**: 숫자로 박지 말고 `c.cue("S3")`(그 장면에서 나레이션이 'S3'를 말하는 장면 안 초)로 등장 · 이동 시각을 정한다.
     예) `const up = c.cue("업로드"); c.auto(K.draw(c.root, path, { at: up - 0.3, dur: 0.8 }))` — 음성을 다시 만들어도 말에 맞춰 따라간다. `c.words` 로 그 장면 단어 목록.
   - 개수 · 위치 · 크기 · 등장 순서는 영상마다 주제에 맞게 정한다(고정 배치 금지). 대신 아래 4번 검사로 잘림 · 겹침을 잡는다.
   - **색은 `K.T`(= direction 색 토큰: bg surface text muted accent)에서 가져온다.** 레이어 요소(Manim · Blender · 생성 그림)도 같은 색으로 만들어지므로 한 화면처럼 보인다. 색을 하드코딩하지 않는다.
4. 확인
   - `python3 scripts/overlap_check.py storyboards/<id>.json` — **화면 밖 잘림 · 글자 넘침 · 겹침 · 못 찾은 c.cue** 를 장면마다 잰다. ✗ 가 0 이 될 때까지 고친다.
   - `python3 scripts/look_check.py storyboards/<id>.json` — **'AI 티' 화면 검사**(부품 속 효과까지 렌더 화면에서). 실패면 고친다. 레퍼런스가 정말 그런 화면이면 `--allow blur,gradient …` 로 허용하고 이유를 말한다.
   - 초안을 렌더한 뒤 `python3 scripts/review_grid.py storyboards/<id>.json` → 격자(칸마다 그 순간 말하는 단어)를 **직접 열어 본다**: 장면마다 주인공 재료 · 말에 맞춘 변화 · 되풀이되는 틀 · 폰 크기 가독성 · 빈 화면. 고칠 곳을 적고 고친 뒤 다시. '다 됐다'는 본 뒤에만.
   - `python3 scripts/still.py storyboards/<id>.json <장면 중간 초 …>` → PNG 를 **직접 열어 본다**. 빈 화면 · 어색한 구도 · 흔들림을 고친다.
5. `python3 scripts/lint.py storyboards/<id>.json` — L15(화면 구성 없음) · L17(없는 요소)이 없어야 끝.
6. 끝나면 이번 방향(바탕 · 색 · 장치 · 쓴 레이어 요소)과 앞선 영상과 무엇이 다른지 두세 줄로 말한다. 렌더는 사람이 '렌더'를 누르거나 요청하면.

## 품질 기준 (유치하면 실패 · 매번 같아도 실패)

- **방향이 스타일을 정한다.** 한 가지 "좋은 스타일"(검은 무대 + 큰 숫자)로 수렴하지 않는다. 종이 · 색면 · 청사진 · 풍경 · 망점 · 신스웨이브 … 방향에 맞는 바탕을 `K.bg` 새 종류로 쓴다.
- **타이포 위계**: 장면마다 메시지 하나, 가장 큰 글자 하나. 굵기 · 크기 대비를 분명히(제목 대 라벨 3배 이상). 자간은 큰 글자일수록 좁게.
- **색 규칙은 방향의 palette 를 따른다**: mono-accent 면 강조 하나, duotone 이면 두 색 면, pop 이면 원색 대비 + 검정 테두리, reference 면 참고 쇼츠 색 그대로. 한 화면에 아무 이유 없는 색을 더하지 않는다.
- **움직임은 방향의 motion 을 따른다**: calm=지수 감속, bouncy=탄력, snappy=장면 안에서도 0.6~1초마다 화면이 바뀜, camera=큰 판을 카메라가 훑음, draw-on=선이 그려짐.
- **주인공 장치(device)를 장면마다 실제로 움직인다**: 사물 · 캐릭터 · 차트 · 화면 카드 · 지도 · 픽셀 · 콜라주 중 방향이 정한 것. 글자만 있는 장면은 훅 · 결론 말고는 피한다.
- **금지**: 의미 없는 이모지 · 장식 입자 남발 · 무지개색 · 글자 두꺼운 테두리 남발(pop 방향 제외) · 모든 장면이 같은 구도.
- 자막 자리는 방향의 captions 를 따르고, 화면 타이포와 겹치지 않게 y 를 조정한다.
- 참고 수준: Kurzgesagt(일러스트) · Vox(콜라주 · 지도) · 블룸버그(차트) · 애플 키노트(타이포) · MKBHD(제품) — 방향에 맞는 쪽을 떠올린다.

`K.pro` = 에디토리얼 · 무대형 부품 { ACC INK DIM BG, ex io(감속), w(lt,at,dur,ease), stage, type, rule, label, card, big } — direction 이 stage · editorial · giant-number 일 때 쓴다. 다른 방향이면 K.bg · K.text · K.shape · K.draw 로 직접 짠다.
예시(서로 다른 방향): `compositions/2026-11-03-tts-pro-01`(무대 · 에디토리얼), `-pixel-01`(픽셀), `-flat-01`(플랫 우주), `-meme-01`(밈), `2026-10-28-wifi-wall-01`(흰 바탕 · 위 고정 제목). **그대로 베끼지 말고** 부품 쓰는 법만 본다.

## K.talk — 말로 끌고 가는 정보 쇼츠 문법 (direction.layout 이 "band" 이면 이것으로)
레퍼런스 카드가 '검정 바탕 · 화면 · 짤 · 컷'이면 효과를 만들지 말고 이 부품만 쓴다(웃음은 짤 타이밍과 말).
기본값이 쇼츠 안전 영역이다: 콘텐츠 판 x 72~936 · y 380~1300(`k.SAFE`), 제목 y 240, 자막 y 1340 — 오른쪽 버튼 줄 · 아래 채널명을 피한다(화면 검사가 침범을 실패로 잡음).
```js
const k = K.talk;                      // 색은 direction.color_caption_bg/fg 를 따른다
void ["elements/<id>/<녹화>"];          // 렌더 폴더 복사용: 하위 파일을 쓰는 요소 폴더는 이렇게 이름을 적어 둔다
// global: 고정 제목(기본 첫 장면만 — 끝까지면 { scope: "all" }) · 흰 글씨 자막(상자 · 효과 없음)
global({ root }) { const t = k.title(root, "<b>북한</b>이 바이낸스 턴 방법"); const sb = k.subs(root); return (tt) => { t.update(tt); sb.update(tt); }; },
// 장면
k.bg(c.root);
const s = k.shot(c.root, "elements/<id>/<녹화>/s002.png", [0, 0, 1280, 800]);   // 웹 녹화 한 장(판 폭에 맞춤)
const sp = k.spot(c.root, s, [x, y, w, h], c.cue("단어"));                         // 강조 = 스포트라이트(밖을 어둡게 + 살짝 당김). 빨간 네모는 기본에서 뺐다
const m = k.insert(c.root, "elements/<id>/meme-x", 610 / 1080, { at: c.cue("단어"), from: 1.6 });   // 반응 짤(판 안 비율 그대로)
const lg = k.logo(c.root, "elements/<id>/logo.png", 420);                          // 실제 로고 · 사진 한 장
const lb = k.label(c.root, "서비스 컨테이너", 1200, c.cue("단어"));                 // 작은 흰 글씨 — 꼭 필요한 한두 곳만
const n = k.note(c.root, X, Y, "← 인간용", c.cue("단어"));                          // 화살표 주석
const cp = k.cap(c.root, s.top, "(괄호 자막)", 0);                                   // 그림 위쪽 가장자리에 걸침
const cut = k.cuts([{ at: 0, items: [s] }, { at: c.cue("단어"), items: [m, lg] }]);   // 장면 안 컷(짤 프레임도 넘긴다)
return (lt) => { cut(lt); sp.update(lt); lb.update(lt); n.update(lt); cp.update(lt); };
```
- 화면은 이야기하는 **대상 자체**(사이트 · 앱 녹화, 실제 사진 · 로고)가 먼저다. 기사 캡처는 근거 한두 곳. 직접 그린 2D · 이모지 스티커는 'AI 티'라 쓰지 않는다(콘티 intent.must_not 확인).
- 펀치(짤)는 **그 말이 끝나는 순간**(c.cue 의 단어)에 컷으로. 튀기 · 날아오기 · 줌 · 도장은 쓰지 않는다(L18).

## 'AI 티' 줄이기 — 사람이 편집한 영상처럼 (검사 T18 이 버릇을 센다)
하나하나는 괜찮지만 **겹치면** 자동 생성처럼 보인다. 매 영상 스스로 확인한다.
- **멈춤이 있다**: 화면 전체가 영상 내내 떠다니지 않는다(`camera.drift` 금지에 가깝게). 장면 안에서 0.5~1초는 아무것도 안 움직이는 순간을 둔다.
- **카메라는 이유가 있을 때만**: 펀치 줌 · 흔들림은 강조할 1~2컷에만. 컷마다 같은 줌은 티가 난다.
- **등장 방식을 섞는다**: 주인공 하나만 튀고(back · pop), 나머지는 컷으로 바로 있거나 담백한 power2. 모든 것이 통통 튀면 실패.
- **말에 맞춘다**: 같은 간격 차례 등장(i×0.1) 대신 `c.cue("단어")` 로 나레이션 단어에 맞춰 시각을 다르게.
- **전환은 대부분 컷**: glitch · flash · zoom · circle 은 의미가 바뀌는 곳 한두 번.
- **질감**: 빛번짐 그라데이션 · 글로우 · 메쉬 배경 대신 단색 · 종이 · 실사 바탕. 완벽한 대칭보다 살짝 비튼 배치.
- **부품 기본값이 담백하다**: `K.pro` 무대 · 카드 · 글자 · 큰 글자, `K.bg` 는 이제 단색 · 평평 · 짧은 등장이 기본이다. 빛번짐(`glow`) · 흐림(`blur`) · 원근 카드(`tilt`)는 레퍼런스가 그런 화면일 때만 옵션으로 켠다(look_check 가 잰다).
- **글자**: 모든 단어를 강조하지 않는다(자막 강조는 핵심어만). 이모지 · 반짝이 장식 금지.

## 형식

```js
(function () {
  const { T } = K;               // T = direction 색 (bg, surface, text, muted, accent, caption, good, bad)
  window.FLUMA_SCENE = {
    captions: { style: "highlight" | "box" | "top" | "pop" | "outline" | "none", y: 1400, size: 76, color: "#FFE14D" },
    transitions: ["wipe", "zoom", ...],      // 장면 i→i+1. cut fade wipe slide push zoom flash glitch circle
    trDur: 0.35, camera: K.camera.shake(at),   // 카메라는 이유 있을 때만 — punch · drift 를 영상 전체에 걸면 'AI 티'(아래 참고)
    scenes: [
      (c) => {                    // c.root(장면 판) c.scene(콘티 장면) c.sc{start,end,sec} c.i
        c.auto(K.bg(c.root, { type: "grid" }), K.text(c.root, "제목", { y: 400, anim: "pop" }));
        const x = c.auto(K.shape(c.root, { ... }));
        return (lt, p) => { /* 장면 안 시간 lt(초)로 추가 움직임 */ };
      },
    ],
  };
})();
```

## Kit 부품 (모두 { el, update(lt) }, 1080×1920 px 절대 좌표)

| 부품 | 쓰임 · 주요 옵션 |
| --- | --- |
| `K.bg(root,{type})` | solid gradient grid dots stripes rays paper pixel noise stars **mesh blueprint halftone topo split sky waves bokeh scan floor ink field** · a b c(색) size speed grain blobs seed · split: angle at · field: shape |
| `K.text(root,str,o)` | anim: rise type pop mask wave stamp blur slide glitch none · split char/word/line · x y w align size weight color font at dur stagger outAt · highlight:[단어] hlStyle color/bg/underline/box hlColor · stroke shadow |
| `K.counter(root,to,o)` | 숫자 카운트 · from prefix suffix decimals |
| `K.shape(root,o)` | 상자 · 원(r:"50%") · 알약 · anim pop grow slide none · fill stroke spin float html |
| `K.pixel(root,rows,o)` | 픽셀아트(문자 격자 + palette), frames 로 걷기 애니메이션 · px bob flip |
| `K.draw(root,d,o)` | SVG 선 그리기 — 화살표 · 밑줄 · 동그라미 · X 표 |
| `K.bars(root,items,o)` | 막대 비교 차트 |
| `K.ring(root,value,o)` | 퍼센트 링 |
| `K.versus(root,L,R,o)` | 좌우 대결 + VS 도장 |
| `K.list(root,items,o)` | 하나씩 등장하는 카드 목록(mark ○ × ★ 숫자) |
| `K.frame(root,o)` | browser/phone/terminal 창 · src(캡처) scroll · lines(타자 치는 코드) |
| `K.image(root,src,o)` | 사진 켄번스 |
| `K.particles(root,o)` | confetti spark dust rain |
| `K.actor(root,src,o)` | 캐릭터 그림 등장 · 흔들림 · react(초) |
| `K.seq(root,"elements/<id>/<이름>"\|"uploads/<id>/<이름>",o)` | **연속 이미지** — 레이어 요소(다른 엔진 · 생성 모델, `scripts/element.py`) · 사용자가 올린 실사 영상(프레임). x y w h at(시작 초) loop fit(contain/cover) radius **z(쌓는 순서)** under(배경판) · from/to(초, 영상 트림). 시간으로 프레임을 골라 렌더에서도 정확 |
| `K.web(root,"elements/<id>/<이름>",o)` | **웹 화면 녹화 재생** (`scripts/webrec.py`) — 브라우저 창 안에서 커서 이동 · 클릭 물결 · 입력 · 스크롤 · 확대 · 실제 녹화 구간. **times[k] = k번째 동작 시각(c.cue 로)** · x y w(기본 1000) at zoom(기본 1.25, false) maxZooms(기본 2 — 가까운 동작은 한 번 들어가 머문 채 따라감) labels(동작 label 을 단계 배지로) chrome z |
| `K.box/K.el/K.css` | 직접 DOM 만들기 (복잡한 장면은 이것으로 자유롭게) |
| `K.win(lt,at,dur,ease)` `K.E` `K.mix` `K.rand(seed)` | 시간 창 · 이징 · 색 섞기 · 결정적 난수 |

자산 경로: `"captures/…png"`, `"characters/<이름>/parts/base.svg"` 처럼 문자열로 쓰면 렌더 폴더에 복사된다. 컴포지션 폴더에 둔 png/svg 는 파일 이름만으로.

## 규칙

- 결정적: Math.random · Date 금지(K.rand). 네트워크 금지.
- 화면 위 1/8(진행 표시 · 제목), 가운데(주인공 그림), 자막 자리(아래)를 나눈다. 글자는 화면 폭 안(w 지정).
- 장면마다 **움직이는 주인공 하나**(픽셀 캐릭터 · 행성 · 창 · 차트 · 도장). 글자만 있는 장면은 피한다.
- 남의 캐릭터 · 로고 · 글꼴을 베끼지 않는다. 트렌드에서는 구조와 리듬만.
- 예시: compositions/2026-11-03-tts-pixel-01 · -flat-01 · -meme-01 (같은 콘티, 세 스타일).
- **이름 붙이기**: 에디터 레이어 목록에 그대로 보인다. 부품 옵션에 `name: "제목"` 을 주거나, 직접 만든 묶음은 `K.name(el, "키보드 두 쪽")` 으로 이름을 단다. "도형" 같은 이름만 남기지 않는다.
- **손 수정 보존**: `compositions/<id>/overrides.json` 은 사용자가 에디터에서 손으로 고친 값(위치 · 크기 · 회전 · 키프레임 `kf`)이다. 절대 지우거나 덮어쓰지 않는다. 키는 `"장면:자식 순서.손자 순서"` 라서, 장면 안 요소의 **만드는 순서를 바꾸면** 손 수정이 다른 요소로 옮겨 간다 — 고칠 때는 새 요소를 맨 뒤에 추가하고, 기존 순서는 유지한다.

## 레이어 요소 — 한 장면 안에서 엔진 · 생성 모델 섞기

scene.js(HyperFrames)가 **합성기**다. 다른 엔진 · 모델은 `scripts/element.py` 로 '요소'(PNG 연속 이미지 + meta.json)를 만들고,
scene.js 가 `K.seq` 로 같은 시간축 위에 겹친다. 장면을 엔진별로 나눠 이어 붙이지 않는다 — 한 장면 안에서 층으로 쌓는다.
예: `compositions/layermix-01/scene.js` (Wan 2.2 배경판 + Manim 도표 + FLUX 마스코트 + 글자 · 자막, 한 장면).

### 층과 역할 (먼저 판단)

| 층 | z | 누가 | 쓰임 |
| --- | --- | --- | --- |
| 배경판 | 1 (`under: true`) | 생성 영상(Wan · LTX) · 켄번스 | 분위기 · 장소. 움직임이 작은 것. 글자 대비용 덮개(z 2)를 꼭 위에 |
| 정보 요소 | 3~6 | **Manim**(투명) | 막대 · 그래프 · 수식 · 알고리즘 — 숫자와 판정이 정확해야 하는 것 |
| 움직이는 개체 하나 | 5~8 | **Blender**(투명) | 걷는 동물 · 사람, 굴러가는 공, 열리는 상자 — 3D 로 움직여야 사는 것 **하나만**. 장면 전체를 3D 로 그리지 않는다 |
| 캐릭터 · 사물(평면) | 5~8 | 생성 그림/영상 + 배경 제거, ToonCrafter | 마스코트 · 소품. 움직임은 HyperFrames 로 더함(등장 · 숨쉬기 · 폴짝) |
| 글자 · 숫자 · 자막 | 10~ | HyperFrames(K.text · K.counter · P.*) | **글자 · 숫자는 언제나 이 층**. 생성 모델에 글자를 시키지 않는다 |

- 시각은 음성 단어 타이밍(`public/audio/<id>.captions.json`)에 맞춘다. 판정 · 강조 시각 하나를 상수로 두고 Manim 스크립트와 scene.js 가 같은 값을 쓴다.
- 색은 direction 에서: element.py 가 그림 설명에 direction 색을 붙이고, Manim · Blender 스크립트는 SF_STYLE · ctx.colors 로 같은 색을 받는다.
- 요소가 글자 · 자막과 겹치면 실패 → 겹침 검사(아래). 배경판 위 정보 요소는 흐린 받침(`backdropFilter: blur`)으로 분리.

### 만들기

```bash
# Blender 개체 하나: 모델 받기 → compositions/<id>/blender/<이름>.py 에 def build(ctx) → 정지 화면 확인 → 본 렌더
python3 scripts/asset3d.py list                      # 움직이는 동물 · 사람 모델(라이선스 · 동작 이름)
python3 scripts/asset3d.py fetch fox <id>            # → compositions/<id>/blender/assets/fox.glb (+ CREDITS.txt 출처)
python3 scripts/element.py blender <id> fox --sec <장면 길이> --still 0.5,2 --size 720x720   # 빠른 확인 → PNG Read
python3 scripts/element.py blender <id> fox --sec <장면 길이> --size 1080x1080 --bg         # 본 렌더는 백그라운드(--bg): 바로 돌아오니 기다리지 말고 K.seq 를 넣고 다른 장면을 계속 짠다. 진행률은 화면에 따로 뜬다
# Manim 투명 요소: compositions/<id>/manim/<이름>.py 에 class Main(Scene) (SF_STYLE 로 direction 색) → 렌더 몇 초
python3 scripts/element.py manim <id> chart --sec <장면 길이> --size 1080x1080
# 생성 배경판: 첫 프레임 그림(FLUX) → 영상(Wan 2.2 → LTX-2.3 → LTX-Video → 켄번스 순으로 시도). 영어 설명 권장
python3 scripts/element.py gen <id> studio --image-prompt "장소 · 사물, 위쪽 절반은 비운 구도" --prompt "작은 움직임" --sec 4 --pingpong --role plate
# 캐릭터 · 사물 그림 한 장 + 배경 제거 (평면 2D 는 u2net 기본, 셀 애니 인물은 --cutout isnet-anime)
python3 scripts/element.py image <id> mascot --image-prompt "…, full body, centered, plain white background" --cutout
# 만화 동작 사이 그림 (키 그림 두 장, ToonCrafter — 상업 이용 불명확)
python3 scripts/element.py interp <id> wave --image a.png --image2 b.png --prompt "waving hand" --cutout
python3 scripts/element.py list <id>          # 만든 요소 · 엔진 · 모델 · 상업 이용 여부
python3 scripts/genvideo.py list              # 생성 모델 · 라이선스 · HF 토큰 상태
```
출력 마지막 줄의 `K.seq(...)` 를 scene.js 에 넣고 x y w h z 를 정한다. 그림 한 장 요소는 바깥 상자(K.box)에 넣고 상자를 움직인다(예의 마스코트).

- **Blender 개체 스크립트**(예: `compositions/layermix-01/blender/fox.py`): `import fluma3d as F` →
  `m = F.import_model(ctx.assets + "/fox.glb", size=2.2, ground=True)` (발을 바닥에) · `F.play(m, "walk", speed=1.0)` (동작 반복) ·
  `F.key(m, "location", 초, (x, y, z), "LINEAR")` (이동 — 보폭과 속도를 맞춰 발이 미끄러지지 않게) · 발밑 그림자는 Blender 에서 그리지 않는다(`F.floor(shadow_only=True)` 는 Cycles 로 바뀌어 프레임당 30초) — `F.anchor(m, "feet", …)` 로 발 위치를 내보내고 scene.js 에서 `pins` 로 2D 타원 그림자를 붙인다 ·
  `F.studio_lights(rim=ctx.colors["accent"])` · `F.camera(...)`. 배경은 투명으로 두고(장면 바탕은 HyperFrames), 3D 물체 하나만 그린다.
  모델이 없는 것(새 사물)은 F.rounded_box · sphere · cylinder · text3d 로 직접 만든다. CC-BY 모델은 CREDITS.txt 문구를 영상 설명에 넣는다.
- **무료 쿼터**: 생성 모델은 Hugging Face ZeroGPU(무료). 토큰 없으면 하루 몇 분 → 쿼터 초과면 다음 모델 → 끝은 켄번스(늘 됨). 결과는 캐시돼 같은 입력은 다시 안 부른다. 그림 생성(t2i)은 대체가 없으니 실패하면 사용자에게 HF_TOKEN 을 부탁하거나 캡처 · 올린 사진을 쓴다.
- **라이선스**: 요소 meta 에 모델 · 상업 이용이 남는다. 상업 '불명확' · '조건부' 모델(ToonCrafter · LTX)은 발행 영상에 쓰기 전에 사용자에게 알린다.
- 생성 영상은 16~24fps · 480p 안팎이다 → 화면 전체 배경판(덮개 + 흐림)이나 작은 요소로 쓰고, 정보는 Manim · HyperFrames 층이 맡는다.
- **겹침 검사(필수)**: `python3 scripts/overlap_check.py storyboards/<id>.json` → 요소(보이는 부분) ↔ 글자 · 자막 띠 · 부품 겹침을 실제 화면에서 잰다.
  ✗ 가 있으면 제안 자리(K.seq 값)로 옮기거나 글자를 옮기고 다시 검사. `workspace/tmp/overlap/<id>-<초>.png` 를 Read 로 보면 빨강(요소) · 노랑(글자) · 파랑(자막) · 초록(제안 자리).
- 확인: `python3 scripts/still.py storyboards/<id>.json <초…>` 로 판정 전 · 후를 찍어 Read 로 본다 — 층이 가려지면(z) 바로 보인다.

## 웹 화면 녹화 — 사이트를 실제로 돌아다니는 장면

콘솔 사용법 · 저장소 소개 · 설정 따라 하기처럼 '화면에서 이렇게 누른다'를 보여 줄 때 쓴다. 동작마다 화면과 대상 위치를 남기고(단계 캡처) 연출은 `K.web` 이 그리므로 흔들림이 없고 클릭을 나레이션 단어에 맞출 수 있다.

```bash
# 1) 누를 수 있는 요소 · 선택자 보기 (번호표 스크린샷: workspace/tmp/webrec-probe.png 를 Read)
python3 scripts/webrec.py probe https://github.com/aws/agent-toolkit-for-aws
# 2) 녹화 계획을 compositions/<id>/web/<이름>.json 에 쓴다 (probe 의 선택자를 그대로)
# 3) 녹화 → public/elements/<id>/<이름>/ (화면 · 동작 목록 meta.json). 중간에 멈추면 meta.error 에 몇 번째 동작인지 남는다
python3 scripts/webrec.py run <id> compositions/<id>/web/<이름>.json
```

녹화 계획:
```json
{ "start": "https://…", "viewport": [1280, 800], "scale": 2,
  "steps": [
    {"do": "hover",  "target": "[data-testid=\"star-button\"]", "label": "별 3.3천 개"},
    {"do": "scroll", "by": 700},
    {"do": "click",  "target": "role=button[name=\"Code\"]", "label": "1. Code 버튼"},
    {"do": "type",   "target": "role=combobox[name=\"Go to file\"]", "text": "skills"},
    {"do": "press",  "key": "Enter"},
    {"do": "goto",   "url": "https://…"},
    {"do": "record", "sec": 3, "steps": [ … ]}   ← 로딩 · 펼쳐지는 메뉴처럼 실제 움직임이 필요한 구간만
  ] }
```
- `meta.actions` 순서대로 `times` 를 준다. 대상이 화면 밖이면 녹화기가 **자동 스크롤 동작을 끼워 넣으므로**(auto: true) 동작 수는 meta 에서 확인한다(출력 첫 줄).
- `K.web(c.root, "elements/<id>/repo", { x: 40, y: 560, w: 1000, labels: true, times: [c.cue("별"), c.cue("README"), …] })` — 클릭은 그 단어를 말하는 순간.
- 화면 속 이메일 · AWS 계정 번호 · ARN · 액세스 키는 자동으로 흐리게 가려진다. 더 가릴 것은 `"mask": ["css"]`, `"mask_text": ["정규식"]`.
- **로그인이 필요한 사이트**(AWS 콘솔 등)는 사람이 만든 로그인 프로필로만: `python3 scripts/webrec.py profiles` 로 확인하고 계획에 `"profile": "이름"`. 없으면 사용자에게 `python3 scripts/webrec.py login <이름> --hosts console.aws.amazon.com,signin.aws.amazon.com` 실행을 부탁한다(에이전트는 실행하지 않는다).
  프로필은 허용한 사이트 밖으로 이동하지 않고, 사용자가 쓰기를 허락하지 않았다면 생성 · 삭제 · 결제 같은 버튼과 Enter 는 실제로 누르지 않는다(meta 에 blocked — 화면에서는 커서만 누르는 것처럼 보임). 실제 계정의 리소스를 만들거나 지우는 계획은 쓰지 않는다.
- 웹 화면은 출처 표기 대상이다. meta.sources 의 주소를 영상 설명란 '사용한 자료'에 넣는다.

## 밈 · 짤 — 커뮤니티 최신 짤을 설명의 소재로

```bash
python3 scripts/meme.py search --query "aws"              # Reddit(r/ProgrammerHumor 등 검색) + 디시 실시간 베스트(싱갤) + 루리웹 유머 베스트
python3 scripts/meme.py search --source reddit --sub ProgrammerHumor,sysadmin   # 이번 주 인기
python3 scripts/meme.py list --query "서버"                # 모아 둔 것에서 찾기 → public/memes/thumbs/<id>.jpg 를 Read 로 보고 고른다
python3 scripts/meme.py fetch <id> <이름> <밈 id> [--pick 1] [--sec 4]   # → elements/<id>/<이름> (GIF · 영상은 프레임으로) → K.seq
python3 scripts/meme.py credits <id>                      # 영상 설명란 '사용한 자료' (짤 · 웹 녹화 출처 모음)
```
- 짤은 **설명의 소재로 짧게** 쓴다. 통째로 길게 틀지 말고 잘라 · 확대하고 그 위에 우리 글자 · 화살표 주석을 얹는다(인용 범위). 출처는 meta 에 남고 `credits` 로 모은다.
- 목록에 `얼굴!` 이 붙은 짤(실존 인물 사진일 수 있음)은 fetch 가 거절한다. 꼭 필요하면 썸네일을 사용자에게 보여 주고 허락을 받은 뒤 `--allow-face`.
- 정치 · 사건 · 혐오 · 선정적인 글은 고르지 않는다. 디시는 기본으로 싱갤만 본다(`--boards all` 은 쓰지 않는다).
- 에펨코리아(fmk)는 자동 접근을 막는다. 막혔다고 나오면 우회하지 말고 다른 출처를 쓴다.

- **사용자가 올린 파일**: <FLUMA_CONTEXT> 의 '올린 파일' 줄. 사진 → `K.image(c.root, "uploads/<id>/<파일>", {...})`, 실사 영상 → `K.seq(c.root, "uploads/<id>/<파일 이름(확장자 없이)>", { fit: "cover", from, to })`. 영상은 필요한 구간만(from/to) 쓰고 그 위에 글자 · 도형을 얹어 편집한다(자르기 · 확대 · 색 덮기 · 분할 화면).

## 장면 설계도 (scenes/<id>.scene.json) — 데이터 개체 · 사용자가 손으로 고치는 층
scene.js(코드 연출) 위에 **데이터 노드**(글자 · 도형 · 사진 · 올린 영상 · 레이어 요소 · 대역 상자)를 키프레임으로 올린다. 사용자가 편집기에서 직접 옮기고 고칠 개체는 코드가 아니라 여기에 둔다.
```bash
python3 scripts/scene_graph.py init <id>            # 콘티로 설계도 (scene.js 는 장면마다 code 노드)
python3 scripts/scene_graph.py show <id>
python3 scripts/scene_graph.py patch <id> ops.json --actor director   # JSON Patch — 저장되면 compositions/<id>/graph.js 로 자동 컴파일
```
- 설계도 파일을 직접 쓰지 않는다(쓰기 권한 없음). **patch 로만**: 스키마 검사(schema/scene.schema.json) · 칸 소유권 · 사용자 잠금(`locked`) · 판 번호(`--base`).
- 너는 보통 `director`(구조 · 글자 · 노드 추가)다. 위치 · 키프레임은 `previs`, 생성 명세는 `prompt` 칸. **사용자가 잠근 노드는 고치지 말고, 바꿔야 하면 사용자에게 말한다.**
- 노드: `{id, kind: text|rect|ellipse|image|footage|element|gen-clip|3d|proxy, box:{x,y,w,h}, style, layer, start, end, keys:[{t, x, y, scale, rot, opacity, ease}]}` — 키의 x · y 는 box 기준 이동, ease 는 GSAP 이름(power2.out · back.out · sine.inOut …).
- 에셋은 `assets` 에 `rights`(own · licensed · cc0 · cc-by · generated · reference-only · unknown)와 함께 등록하고 노드는 `asset` 열쇠로 가리킨다. 분해도 누끼 같은 참고 자료는 `reference-only`.
- `fidelity: "sketch"` 면 데이터 노드가 이름표 붙은 대역 상자로 보인다(배치 확인용).
- 장면 카메라: `scenes[i].camera.keys` (x · y = 카메라 위치, scale = 확대, rot = 기울기) — 장면 칸 전체(코드 연출 + 노드)를 움직인다. 자막은 안 움직인다.
- 편집은 채팅으로만 한다(손 편집 도구는 2026-11-02 에 뺐다). 예전에 사용자가 넣은 노드(owner user) · 잠긴 노드 · overrides.json 은 사용자의 연출이니 그대로 두고 그 둘레에 맞춰 짠다. 사용자가 미리보기를 눌러 짚은 자리는 채팅 맥락(장면 · 시각 · 1080×1920 좌표 · 요소 이름)으로 온다 — 그 요소를 scene.js 에서 찾아 고친다.

## 레퍼런스 형식 옮기기 · 실사 주인공 따라가기
```bash
python3 scripts/xray_to_graph.py <분해도 id> <id>            # 미리 보기 — 샷 리듬 · 주인공 자리 · 글자 자리 · 카메라
python3 scripts/xray_to_graph.py <분해도 id> <id> --apply    # 설계도에 넣기 (원본 그림 · 말 · 글은 옮기지 않음)
python3 scripts/footage_track.py <id> <footage 노드> --bx 0.4 --by 0.5 --lt 1.2 --mode reframe            # 가로 영상 → 세로, 주인공 가운데
python3 scripts/footage_track.py <id> <footage 노드> --bx … --by … --lt … --mode follow --target <노드>   # 이름표를 주인공 머리 위에
```
- 분해도에서 온 주인공 자리는 참고 그림(reference-only)이 달린 대역이다 — 스케치(애니메틱)용. 최종 전에 직접 찍은 영상 · 생성 · 그린 화면으로 바꾼다(렌더가 막아 준다).
- bx · by 는 영상 개체 상자 안 비율(키 이동 전), lt 는 장면 안 시각. 따라가기는 1초에 6장, 5초면 1~2분.
