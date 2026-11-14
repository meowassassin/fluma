# ArtCraft 영상 편집기 (vendored) — Phase 1 재반입

Source: https://github.com/storytold/artcraft `main` @ **84a6a7d** — `frontend/libs/components/video-editor/src`
(패키지 `@storyteller/ui-video-editor`, 원래 OpenCut(MIT)에서 왔다). 예전 사본(`src/vendor/artcraft-video-editor`, a787c37 기준 — 편집기 코드는
84a6a7d 와 같음)을 지우고 원본을 새로 복사한 뒤, Fluma 추가분을 아래 패치 목록으로 다시 얹었다.
License: MIT OR Apache-2.0 (LICENSE-MIT, LICENSE-APACHE, NOTICE). ArtCraft 이름 · 로고는 라이선스 대상이 아니며 쓰지 않는다.

- 가져온 것: `src/**` 그대로(`src/lib/**/__tests__` 와 `*.spec.*` · `*.test.*` 제외), `package.json`.
- 가져온 직후 `node studio/scripts/artcraft-tw4-compat.mjs studio/src/vendor/artcraft/video-editor` 실행 — 18곳(`X!`→`!X` 15, `h-(--v)`→`h-[var(--v)]` 3).
  Tailwind 4 키(z-100 · z-200 · z-250 · z-9999 · shadow-xs · outline-hidden · bg-linear-to-* · spacing 4.5/6.5/18 …)는 `studio/tailwind.config.js` 가 맡는다 — 클래스는 손으로 고치지 않았다.
- `// @ts-nocheck` 없음. 원본은 strictNullChecks 를 끈 채 빌드한다 → 생긴 타입 오류만 최소로 고침(아래 "타입").
- 모든 변경은 소스에 `fluma:` 주석. Fluma 코드는 되도록 `src/lib/fluma/` 새 파일에 두고 원본에는 짧은 연결점만 둔다.
- 호스트: `studio/src/features/veditor/VEditorPage.tsx`(경로 `/veditor/:id`)가 `src/index.ts` 를 상대 경로로 가져온다.

## 원본으로 갱신하는 법
1. 새 커밋의 `video-editor/src` 를 이 폴더 `src/` 에 덮어쓰기 전, `grep -rn "fluma:" src/lib --include=*.ts*` 로 연결점 목록을 뽑는다(`src/lib/fluma/` 는 Fluma 전용이라 그대로 둔다).
2. 덮어쓴 뒤 tw4-compat 스크립트 실행 → `npx tsc --noEmit -p .` → 아래 표의 연결점을 다시 넣는다.

## 테마 · 색
- 스타일은 ArtCraft 공용 테마 하나: `../_theme/artcraft-fluma.css`(`@tailwind base/components/utilities`, 색 토큰, `:where()` 초기화)를
  `features/veditor/veditor.css` 가 `@import` 한다. 토큰 블록 선택자는 `:is(.ac-root, .ve-root)` — 편집기와 다른 ArtCraft 부품이 같은 값.
  (예전 veditor.css 는 따로 `@tailwind components/utilities` 를 내서 유틸리티가 두 번 생겼고, base 가 없어 `--tw-*` 변수가 빠져 translate · rotate · blur 가 무효였다.)
- **`--primary` = Fluma `--primary` #5850f8 (hsl 243 92% 64%)**, 글자 흰색. 버튼 · 선택 막대 · 슬라이더 · 체크 모두 이 색 하나. 예전 편집기만 쓰던 연보라(246 100% 75%)는 버림 —
  흰 글자 대비가 3:1 아래였다. 어두운 바탕 위 작은 글자 강조는 `text-primary-400`(#8b80ff, Fluma `--brand`).

## 화면 글(한국어)
원본 화면 글은 영어 그대로 둔다. 호스트가 번역한다 — `features/veditor/editorI18n.ts`(MutationObserver 로 글자 · title · aria-label · placeholder 를 제자리에서 바꿈)
+ `features/veditor/editorKo.ts`(영어 → 한국어 사전 · 패턴). ko=한국어, en=원문, zh=한국어를 앱 사전 `t()` 로 한 번 더. AI 에이전트 영역 · `translate="no"` · 입력칸은 건너뛴다.
`src/lib/fluma/` 의 Fluma 화면 글은 한국어 원문(Fluma 규칙 — en/zh 는 같은 번역기가 `t()` 로).

## 패치 목록 (파일 — 무엇 · 왜)
### Fluma 전용 새 파일 `src/lib/fluma/`
| 파일 | 내용 |
|---|---|
| extra-panels.tsx | `EditorExtraPanel`, `ExtraPanelsScope` · `useExtraPanels`, 왼쪽 레일 버튼 `ExtraPanelTabButtons` (호스트 '파이프라인' 패널) |
| effect-provider.tsx | `EffectProvider` 연결(Craft 효과 — **보류**: 연결만 유지, 확장 안 함). `ProvidedEffectBrowser`, `ProviderEffects` |
| fonts/catalog.ts | 글꼴 124종(한글 약 40) — 원본 atlas 목록(스프라이트 자산이 배포되지 않음) 대신 |
| fonts/loader.ts | `ensureFontStylesheet` · `requestFontsForRender`(미리보기 — 한글 unicode-range 조각까지) · `ensureFontsReady`(내보내기 전 대기) · 글꼴 판 번호 · `collectFontRequests` |
| fonts/font-picker.tsx | 검색 · 분류 · 최근 사용 · 줄마다 그 글꼴로 미리보기 |
| text-params.ts | 숫자 굵기(100–900), `skewX`, `stroke.*`, `shadow.*`, Pretendard 기본, 텍스트 속성 묶음(TEXT_PARAM_GROUPS) |
| text-draw.ts | 외곽선 · 그림자 · 기울기 그리기(미리보기와 내보내기가 같은 함수) |
| param-controls.tsx | 좁은 범위 숫자에 슬라이더, 글자 크기를 실제 px + 쇼츠 자막 크기 목록으로 |
| properties-extras.tsx | 텍스트 속성 묶음 탭, 영상 · 이미지 배치 탭의 '화면에 맞춤 / 채우기 / 원본 픽셀'(실제 미디어 크기로 계산) · 여백 · 테두리 |
| text-view.tsx | 텍스트 탭: '텍스트 추가' + 스타일 프리셋 8종 |
| captions-view.tsx | 자막 탭: 자막 목록(시간순, 누르면 이동 · 선택, 제자리 고치기, 스타일 맞추기) — 원본 "coming soon" 대신 |
| media-filter.tsx | 미디어 탭 종류 필터(전체 · 영상 · 오디오 · 이미지) + 이름 검색 |
| timeline-collapse.tsx | 타임라인 접기(Alt+T · 도구줄 버튼 · 접힌 막대) — react-resizable-panels 의 collapsible 사용, 원본 배치 유지 |
| exit-button.tsx | 머리줄 '영상 목록으로 나가기' 버튼 |

### 원본 파일의 연결점
| 파일 | 변경 | 이유 |
|---|---|---|
| src/index.ts | 호스트 확장 · 글꼴 API 내보내기 | VEditorPage · craftFx 가 씀 |
| lib/VideoEditor.tsx | props `extraPanels` · `effectProvider`, 두 Scope, 타임라인 패널에 collapsible props, 접힌 막대 | 호스트 확장 · 타임라인 접기 |
| lib/components/editor/editor-header.tsx | `exitTo` 기본값 `/videos`, 나가기 버튼, 프로젝트 메뉴 아이콘(빈 흰 네모 → 메뉴 아이콘) | Fluma 경로 · 나가기 찾기 쉬움 |
| lib/panels/assets/index.tsx | 호스트 패널 표시, 텍스트 · 자막 탭을 Fluma 화면으로 | |
| lib/panels/assets/tabbar.tsx | `<ExtraPanelTabButtons />` | |
| lib/panels/assets/assets-panel-store.tsx | `activeTab` 타입을 호스트 패널 id 까지 | |
| lib/panels/assets/views/assets.tsx | 미디어 필터 3줄, 갤러리 · 가져오기 버튼을 아이콘만 | 버튼 글이 패널 제목을 한 글자씩 세로로 찌그러뜨림 |
| lib/panels/properties/registry.tsx | 텍스트 탭 = 묶음 탭, 배치 탭을 `VisualTransformExtras` 로 감쌈 | |
| lib/panels/properties/components/element-params-tab.tsx | `ElementParamField` · `buildValues` · `isVisible` export | 묶음 탭이 재사용 |
| lib/panels/properties/components/property-param-field.tsx | font → 카탈로그 FontPicker(원본은 맨 input), fontSize → px 필드, 좁은 범위 숫자 → 슬라이더 | |
| lib/params/registry.ts | 텍스트 속성에 `withFlumaTextParams` | 굵기 · 기울기 · 외곽선 · 그림자 · 기본 글꼴 |
| lib/text/primitives.ts | `TextFontWeight` 숫자 허용, 굵기 그대로 통과, 외곽선 · 그림자 그리기 | |
| lib/text/measure-element.ts | 숫자 굵기 읽기, 기본 글꼴 Pretendard | |
| lib/services/renderer/nodes/text-node.ts | 기울기 · 외곽선 · 그림자 값 읽어 그리기 | |
| lib/preview/components/text-edit-overlay.tsx | 숫자 굵기 | 글 고칠 때 굵기가 맞게 |
| lib/services/renderer/resolve.ts | 텍스트마다 `requestFontsForRender` | 웹 글꼴이 늦게 와도 다시 그림 |
| lib/services/renderer/compositor/frame-descriptor.ts | `effect_pass_groups` 를 같이 보냄, 텍스트 해시에 글꼴 판 번호 | opencut-wasm 이 sceneEffect 필드를 snake_case 로 읽음("missing field effect_pass_groups"로 미리보기 · 내보내기 실패) |
| lib/services/renderer/compositor/types.ts | `effect_pass_groups?` | 위와 같음 |
| lib/preview/components/index.tsx | 글꼴 판 번호가 바뀌면 다시 그림 | |
| lib/core/managers/renderer-manager.ts | 내보내기 전 `ensureFontsReady` | MP4 가 시스템 글꼴로 나가지 않게 |
| lib/fonts/system-fonts.ts | Pretendard · Black Han Sans · Geist · Geist Mono · system-ui | 호스트가 싣는 글꼴(veditor.css @font-face) |
| lib/timeline/defaults.ts, lib/masks/builtin/definitions/text.ts | 기본 글꼴 Pretendard | |
| lib/masks/components/masks-tab.tsx | 글자 마스크도 카탈로그 FontPicker | 원본 atlas 자산 없음 |
| lib/effects/components/assets-view.tsx | 공급자가 있으면 `ProviderEffects` | Craft 효과(보류) |
| lib/timeline/components/timeline-toolbar.tsx | 실행 취소 · 다시 실행 버튼, 타임라인 접기 버튼, `ToolbarButton` 에 aria-label | 찾기 쉬움 · 접근성(아이콘만 있는 버튼에 이름) |
| lib/VideoEditor.tsx (위와 같은 파일) | 타임라인이 접혔을 때 위 패널 `maxSize` 85 → 100 | 85 이면 아래 패널이 15% 밑으로 못 줄어 접기가 반쯤만 됐다 |
| lib/masks/builtin/definitions/index.ts | 마스크 아이콘을 실제 hugeicons 로(원본 `icon: null`) | **원본 버그**: '마스크 추가' 메뉴를 열면 `currentIcon is not iterable` 로 편집기 전체가 오류 화면으로 떨어졌다 |
| lib/masks/builtin/definitions/split.ts | 이름 "Split" → "Split screen" | 타임라인 '자르기(Split)'와 한국어 번역이 겹쳐서 |
| lib/timeline/bookmarks/components/bookmarks.tsx | 북마크 표시를 `<button>` → `<div role="button" tabIndex=0>` | **원본 버그**: 눈금자 `<button>` 안의 `<button>`(잘못된 HTML, React 콘솔 오류) |
| lib/actions/shortcuts-dialog.tsx | 키 버튼에 `translate="no"` | 키 이름(Delete · Enter)이 낱말로 번역되지 않게 |

### 타입(strictNullChecks) — 동작 변화 없음
`project.getActive()!` (프로젝트가 열린 동안만 그려지는 곳): actions/use-editor-actions.ts ×2, masks/components/masks-tab.tsx, masks/use-mask-handles.ts,
panels/assets/views/settings/background.tsx · index.tsx, preview/components/index.tsx(+ `usePreviewSize` 의 `as number`), preview/components/text-edit-overlay.tsx · toolbar.tsx,
preview/hooks/use-preview-interaction.ts · use-transform-handles.ts, timeline/components/timeline-playhead.tsx.
components/section.tsx: `process.env.NODE_ENV` → `import.meta.env.DEV`. `String.replaceAll` 은 studio tsconfig lib 에 `ES2021.String` 추가로 해결(원본 수정 없음).

### 가져오지 않은 예전 변경(의도적으로 버림)
color-picker · number-field 모양 변경, 버튼 · 탭 · 카드의 손 변환 Tailwind 4 클래스(`outline-hidden`→`outline-none`, `bg-linear-to-*`→`bg-gradient-to-*` 등 — 설정이 맡음),
속성 패널 탭 모양(가로 글자 탭) · 미디어 카드 꾸밈 · 재생 막대 꾸밈 · 스티커 줄 → 격자, 영상 · 이미지에서 클립 효과 탭을 뺀 것(원본대로 둠), 원본 파일 곳곳의 한국어 직접 치환(번역기로 대체).

## 호스트 쪽(같은 단계에서 고친 것)
- `features/veditor/adapters/fluma-adapters.ts`: 저장할 때 타임라인 요소가 가리키는데 미디어 목록에서 빠진 항목을 불러온 원본으로 되살림(아래 버그).
- `studio/server.mjs` GET `/api/projects/:id/editor` + `engine/gen/editor_bridge.py media <id>`: 이미 잃어버린 항목은 변환기가 아는 항목으로 채워서 보냄(파일은 안 고침).
- 버그 'Insert 7(달 사진)이 비어 보임' 원인: 편집기는 불러오기에 실패한 미디어를 미디어함에서 빼고, 다음 자동 저장이 그 항목을 `media` 목록에서 지운다 →
  요소는 `media_insert_7` 을 가리키는데 목록에 없음 → scene-builder 가 건너뜀(빈 화면). 같은 일이 2026-11-05-craftshow-01 의 media_video_1–8 에도 있었다.
