/* 영상 편집기 화면 번역 — ArtCraft 원본(영어)을 고치지 않고 화면 글자를 한국어(또는 앱 언어)로 바꾼다.
   방식: 편집기가 떠 있는 동안 MutationObserver 로 새로 그려진 글(텍스트 노드 · title · aria-label · placeholder)을
   editorKo.ts 사전과 맞춰 제자리에서 바꾼다. React 는 자기가 기억하는 값과 비교해 바뀔 때만 DOM 을 쓰므로
   글자만 바꾸는 것(노드 교체 아님)은 안전하다 — 다음 렌더에서 원문이 다시 오면 또 번역된다.
   - 범위: .ve-page 안 + body 직속 포털(메뉴 · 대화상자 · 툴팁, #root 밖) + 알림(sonner). AI 에이전트 영역과
     translate="no" 표시 아래(사용자 글)는 건너뛴다.
   - 언어: ko → 사전 한국어, en → 원문 그대로, zh → 사전 한국어를 앱 사전 t() 로 한 번 더(없으면 한국어).
     Fluma 가 쓴 부분(한국어 원문)은 en/zh 에서 t() 로 옮긴다. */
import { t, useLang } from "../../lib/i18n";
import { EDITOR_KO, EDITOR_KO_PATTERNS } from "./editorKo";

const ATTRS = ["title", "aria-label", "placeholder"] as const;
const HANGUL = /[가-힣]/;

function toKorean(src: string): string | null {
  const hit = EDITOR_KO[src];
  if (hit !== undefined) return hit;
  for (const [re, ko] of EDITOR_KO_PATTERNS) {
    const m = src.match(re);
    if (m) return ko.replace(/\$(\d)/g, (_, i: string) => {
      const part = m[Number(i)] ?? "";
      return EDITOR_KO[part] ?? part;
    });
  }
  return null;
}

/** 원문 → 지금 언어. 바꿀 것이 없으면 null */
export function translateEditorText(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed || trimmed.length > 400) return null;
  const lang = useLang.getState().lang;
  if (/[A-Za-z]/.test(trimmed) && !HANGUL.test(trimmed)) {
    if (lang === "en") return null;
    const ko = toKorean(trimmed);
    if (ko === null) return null;
    const out = lang === "ko" ? ko : t(ko);
    return out === trimmed ? null : raw.replace(trimmed, out);
  }
  if (lang !== "ko" && HANGUL.test(trimmed)) {
    const out = t(trimmed);
    return out === trimmed ? null : raw.replace(trimmed, out);
  }
  return null;
}

// 통째로 건너뛰는 곳(사용자 글 · 에이전트). 입력칸(input · textarea)은 글자는 두고 placeholder · title 만 바꾼다
const SKIP = '[translate="no"], [data-ve-no-tr], [contenteditable="true"], script, style, canvas, video';
const FIELD = "input, textarea";

function inScope(el: Element | null, attrsOnly = false): boolean {
  if (!el) return false;
  if (el.closest(attrsOnly ? "[data-ve-no-tr]" : SKIP)) return false;
  if (el.closest(".ve-page, [data-sonner-toaster]")) return true;
  // body 직속 포털(Radix · createPortal) — 앱 루트(#root) 밖
  let top: Element = el;
  while (top.parentElement && top.parentElement !== document.body) top = top.parentElement;
  return top.parentElement === document.body && top.id !== "root";
}

function translateAttrs(el: Element) {
  for (const a of ATTRS) {
    const v = el.getAttribute(a);
    if (!v) continue;
    const next = translateEditorText(v);
    if (next !== null && next !== v) el.setAttribute(a, next);
  }
}

/** 범위 안이라고 확인된 요소 아래를 모두 번역(건너뛸 곳은 통째로 건너뜀) */
function walk(root: Element) {
  translateAttrs(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
    acceptNode: (n) => {
      if (n.nodeType !== Node.ELEMENT_NODE) return NodeFilter.FILTER_ACCEPT;
      const e = n as Element;
      if (e.matches("[data-ve-no-tr]")) return NodeFilter.FILTER_REJECT;
      if (e.matches(SKIP) || e.matches(FIELD)) { translateAttrs(e); return NodeFilter.FILTER_REJECT; } // 글은 두고 title 등만
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  for (let cur = walker.nextNode(); cur; cur = walker.nextNode()) {
    if (cur.nodeType === Node.TEXT_NODE) {
      const next = translateEditorText(cur.nodeValue ?? "");
      if (next !== null && next !== cur.nodeValue) cur.nodeValue = next;
    } else translateAttrs(cur as Element);
  }
}

function translateNode(node: Node) {
  if (node.nodeType === Node.TEXT_NODE) {
    if (!inScope(node.parentElement) || node.parentElement?.closest(FIELD)) return;
    const next = translateEditorText(node.nodeValue ?? "");
    if (next !== null && next !== node.nodeValue) node.nodeValue = next;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  const el = node as Element;
  if (inScope(el)) walk(el);
  else if (inScope(el, true) && el.matches(`${SKIP}, ${FIELD}`)) translateAttrs(el); // 입력칸 · 건너뛸 곳: 이름표만
  else el.querySelectorAll(".ve-page").forEach((page) => walk(page)); // 편집기를 품은 앱 쪽 노드가 붙은 경우
}

/** 편집기가 떠 있는 동안 화면 번역을 켠다. 돌려준 함수로 끈다. */
export function startEditorTranslation(): () => void {
  for (const child of Array.from(document.body.children)) translateNode(child);
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === "characterData") translateNode(r.target);
      else if (r.type === "attributes") {
        const el = r.target as Element;
        if (inScope(el, true)) translateAttrs(el);
      } else r.addedNodes.forEach(translateNode);
    }
  });
  obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: [...ATTRS] });
  // 언어를 바꾸면 main.tsx 가 화면을 다시 그린다 — 새로 그려진 글은 위 관찰자가 맡는다
  return () => obs.disconnect();
}
