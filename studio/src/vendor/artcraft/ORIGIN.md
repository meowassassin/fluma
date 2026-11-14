# ArtCraft 공용 부품 (vendored) — Phase 0 기반

Source: https://github.com/storytold/artcraft `main` @ **84a6a7d** — `frontend/libs/**`.
License: MIT OR Apache-2.0 at your option (LICENSE-MIT, LICENSE-APACHE, NOTICE in this folder).
The ArtCraft name, wordmark and logos are not covered by the license and are not used.
Fluma 변경은 소스에서 `fluma:` 주석(또는 `/* fluma */`)으로 표시한다. 스펙/테스트 파일(*.spec.*, *.test.*)은 가져오지 않았다.

## 폴더 ↔ 패키지 (각 폴더 = 원본 패키지 폴더, `src/` 배치 그대로 + package.json · README.md)
| 폴더 | 패키지 | 원본 경로 |
|---|---|---|
| common | @storyteller/common | libs/common |
| icons | @storyteller/icons | libs/icons |
| api-enums | @storyteller/api-enums | libs/api-enums |
| keybinds | @storyteller/keybinds | libs/components/keybinds |
| button | @storyteller/ui-button | libs/components/button |
| tooltip | @storyteller/ui-tooltip | libs/components/tooltip |
| popover | @storyteller/ui-popover | libs/components/popover |
| modal | @storyteller/ui-modal | libs/components/modal |
| button-icon-select | @storyteller/ui-button-icon-select | libs/components/button-icon-select |
| input | @storyteller/ui-input | libs/components/input |
| loading | @storyteller/ui-loading | libs/components/loading |
| loading-spinner | @storyteller/ui-loading-spinner | libs/components/loading-spinner |
| close-button | @storyteller/ui-close-button | libs/components/close-button |
| checkbox | @storyteller/ui-checkbox | libs/components/checkbox |
| label | @storyteller/ui-label | libs/components/label |
| tab-selector | @storyteller/ui-tab-selector | libs/components/tab-selector |
| badge | @storyteller/ui-badge | libs/components/badge |
| button-icon | @storyteller/ui-button-icon | libs/components/button-icon |
| button-dropdown | @storyteller/ui-button-dropdown | libs/components/button-dropdown |
| slider-v2 | @storyteller/ui-sliderv2 | libs/components/slider-v2 |
| select | @storyteller/ui-select | libs/components/select |
| action-reminder-modal | @storyteller/ui-action-reminder-modal | libs/components/action-reminder-modal |

`common/src/lib/assets/images/checkerboard.png` 는 저장소 안 MIT/Apache 자산(사운드 · 밈 · 스카이박스 · vmd · 캐릭터 gif 같은 별도 권리 자산은 가져오지 않음).

## 모듈 해석
- `studio/tsconfig.json` `compilerOptions.paths` 가 유일한 목록: `@storyteller/<이름>` → `src/vendor/artcraft/<폴더>/src/index.ts` 또는 `_shims/<이름>/…`.
- `studio/vite.config.ts` 는 그 paths 를 읽어 정확 일치 별칭(`^@storyteller/x$`)으로 바꾼다 — 다음 단계에서 라이브러리를 더할 때는 tsconfig paths 한 줄만 추가.
- 영상 편집기는 Phase 1 에서 `video-editor/` 로 다시 가져왔다(호스트는 `video-editor/src` 를 상대 경로로 import) — `video-editor/ORIGIN.md`.

## Fluma 심(_shims/) — ArtCraft 클라우드 · Tauri 대체 (모든 파일 머리에 `FLUMA SHIM` 주석)
| 패키지 | 내보내는 것 | 동작 |
|---|---|---|
| @storyteller/model-list | Model, ImageModel, CommonAspectRatio/Resolution/Quality, ModelCreator, ModelTag, FAMILY_ORDER, getModelFamilyName, getCreatorDisplayName, SizeIconOption, SizeOption, ModelConfig, ModelInfo, IMAGE_MODELS, IMAGE_MODELS_BY_ID, getCreatorIcon/getCreatorListIcon | 클래스 파일은 원본 그대로 복사(ImageModel 의 잘못된 `src/index.js` import 만 수정), 목록은 Fluma(Nano Banana Pro · Nano Banana — Antigravity). 아이콘은 null(브랜드 로고 미사용) |
| @storyteller/ui-model-selector | ModelPage, ModelList, useClassyModelSelectorStore, useSelectedModel/ImageModel/ProviderForModel, getSelectedImageModel, getSelectedProviderForModel, defaultModelForPage, useCanvas2d/Stage3d/TextToImage/ImageEditorPageModelList, ClassyModelSelector | 스토어 API 동일(zustand). 목록 = Fluma 목록. ClassyModelSelector = ui-popover PopoverMenu(richList) — 공급자 선택 없음 |
| @storyteller/ui-pricing-modal | useCostBreakdownModalStore, CostCalculatorButton(+Props) | 스토어 모양 동일, 버튼은 아무것도 그리지 않음(크레딧 없음) |
| @storyteller/ui-gallery-modal | GalleryItem, DragGhost(+State, 원본 그대로), gallery* 신호들, IMAGE_DROP_EVENT, emitImageDrop, onImageDrop, removeImageDropListener | 창 이벤트 드롭 버스 · 신호만. 갤러리 모달 자체는 없음 — Fluma 자산 브라우저가 emitImageDrop 으로 보냄 |
| @storyteller/ui-help-menu | HelpMenuButton(+Props), TutorialItem | 아무것도 그리지 않음 |
| @storyteller/ui-promptbox | RefImage, Prompt2DStore, usePrompt2DStore/usePromptStore, UploadImageFn, PromptBox2D(+Props), AspectRatioIcon, AutoIcon | 스토어 원본 그대로. PromptBox2D = Fluma 톤 최소 입력창(textarea + 생성 → onGenerateClick). AspectRatioIcon 원본 그대로 |
| @storyteller/api | ApiResponse, UploadMediaFn, UploadImageMedia, ApiManager, PromptsApi(pollJobSession, uploadSceneSnapshot), ARTCRAFT_CLOUD_DISABLED | 모든 호출이 `Error("ArtCraft cloud not used in Fluma: <name>")` |
| @storyteller/tauri-api | Provider(type), useImageModels(→Fluma 목록), useVideoModels(→[]), invokeTauri(throw) | 현재 닫힘 안에서 직접 import 없음 — 잘못 끌려오면 크게 실패 |
| @storyteller/tauri-utils | IsDesktopApp(→false), FetchProxy(→fetch) | 브라우저 전용 |

## 원본에서 바꾼 곳 (Fluma 톤 · 빌드)
- popover/src/lib/popover.tsx: `NodeJS.Timeout` → `ReturnType<typeof setTimeout>` (studio tsconfig 는 node 타입을 싣지 않음); 패널 머리 mono 대문자 라벨 → Fluma 라벨.
- button/src/lib/button.tsx: primary = `bg-primary`(#5850f8) 흰 글자(원본 흰 바탕 검은 글자), 기본 글꼴 mono 대문자 → Pretendard 13px, 모서리 6px.
- checkbox: 체크 상태 보라(원본 흰색). tab-selector: 표시 막대 보라 · 선택 글자 흰색. select: 포커스 행 `bg-primary/20`(원본 흰 바탕).
- slider-v2: 진행 막대 · 링 보라(primary-400), 툴팁 글자 `text-base-fg`(원본 검정 — 어두운 바탕 위 버그).
- badge · label · tooltip: mono 대문자 → Fluma 글꼴/크기, 모서리 4–6px, 툴팁 그림자.
- close-button · modal 닫기: hover 흰 바탕 → `bg-white/15`. modal 패널: 각진 모서리 → 12px + shadow-modal.
- input: 아이콘 위치(`pl-3 pt-3` 패딩이 border-box svg 를 찌그러뜨림 → 세로 중앙 배치), 6px 모서리, 포커스 테두리 보라.

## 스타일 시스템 (하나의 범위)
- `studio/tailwind.config.js`: content 에 `src/vendor/artcraft/**` 포함, `important: ":is(.ac-root, .ve-root)"`, preflight 끔.
  원본 `apps/artcraft/tailwind.config.ts` 의 키(ui.*, base-fg, primary/brand-*/secondary/action 단계, danger/success, 타임라인 색,
  shadcn 토큰, 글꼴 display/mono/sans, fadeIn/shimmer/marquee)를 같은 이름으로, 값은 Fluma 로. Tailwind 4 키(z-100/200/250/9999,
  spacing 4.5/6.5/18, shadow-xs, rounded-xs, opacity 8 등, outline-hidden · bg-linear-to-* · text-shadow-* 플러그인)도 추가.
- `_theme/artcraft-fluma.css`: 원본 base.css/tailwind.css 의 클래스(.glass, .hud-label, .filter-tab, .promptbox-scrollbar, .animate-shimmer,
  .bg-dots, 스크롤바, 조작 요소 모서리, .bg-ui-modal 등)를 `.ac-root` 범위로 옮김. 값은 Fluma 토큰. 요소 초기화는 `:where()` 특이도 0.
  `@tailwind base` 는 preflight 없이 Tailwind 기본 변수(--tw-translate-* 등)만 낸다 — 없으면 translate/rotate/blur 유틸리티가 무효.
- **호스트 적용법**: ArtCraft 부품을 띄우는 화면은 `useArtcraftRoot()`(`_theme/useArtcraftRoot.ts`, CSS 도 함께 불러옴)를 호출해
  떠 있는 동안 `document.body` 에 `ac-root` 를 단다 — Radix · headless UI 포털과 `createPortal(document.body)` 메뉴/툴팁/모달이 범위 안에 들어온다.
  화면 루트에도 `className="ac-root"` 를 둔다. 영상 편집기는 body 에 `ve-root` — 색 토큰 · `:where()` 초기화는 Phase 1 부터 `:is(.ac-root, .ve-root)` 공통
  (features/veditor/veditor.css 가 이 테마를 `@import` 하고 편집기만의 글꼴 · 화면 틀만 더한다).

## Tailwind 4 문법 호환 스크립트
`node studio/scripts/artcraft-tw4-compat.mjs [--check] <폴더|파일>…` — `X!` → `!X`, `h-(--v)` → `h-[var(--v)]`.
Phase 0 에서 이 폴더 전체에 실행(바뀐 곳 0). 원본 video-editor 에는 18곳(`--check` 로 확인) — Phase 1 재반입 때 실행할 것.
다음 단계에서 moodboard/pagedraw/pagescene/viewer-3d 를 가져온 직후에도 같은 명령을 실행하고 여기 기록한다.
