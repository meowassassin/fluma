/* 화면 언어(한국어 · English · 中文). 원문(한국어)이 곧 키다 — t("영상") 처럼 쓰고, 번역은 src/i18n/*.ts 의 { en, zh } 사전.
   사전에 없는 문장은 한국어 그대로 보인다(빠뜨려도 깨지지 않게). 자리표시는 {name}: t("영상 {n}개", { n: 3 }).
   언어를 바꾸면 main.tsx 가 화면 전체를 다시 그린다 — 그래서 컴포넌트마다 구독할 필요가 없다. 단, 모듈 맨 위 상수에서 t() 를 부르면
   처음 언어로 굳으니 렌더할 때 부른다(배열 상수는 원문만 두고 쓰는 자리에서 t(label)). */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Lang = "ko" | "en" | "zh";
export const LANGS: { value: Lang; label: string; agent: string }[] = [
  { value: "ko", label: "한국어", agent: "korean" },
  { value: "en", label: "English", agent: "english" },
  { value: "zh", label: "中文", agent: "chinese" },
];

type Dict = Record<string, string>;
const mods = import.meta.glob<{ en?: Dict; zh?: Dict }>("../i18n/*.ts", { eager: true });
const DICT: Record<Exclude<Lang, "ko">, Dict> = { en: {}, zh: {} };
for (const m of Object.values(mods)) {
  Object.assign(DICT.en, m.en || {});
  Object.assign(DICT.zh, m.zh || {});
}

const initial = (): Lang => {
  const n = (navigator.language || "ko").toLowerCase();
  return n.startsWith("zh") ? "zh" : n.startsWith("ko") ? "ko" : "en";
};

interface LangState { lang: Lang; setLang: (l: Lang) => void }
export const useLang = create<LangState>()(persist((set) => ({
  lang: initial(),
  setLang: (lang) => { document.documentElement.lang = lang; set({ lang }); },
}), { name: "fluma.lang" }));
document.documentElement.lang = useLang.getState().lang;

/** 원문(한국어) → 지금 언어 */
export function t(ko: string, vars?: Record<string, string | number>): string {
  const l = useLang.getState().lang;
  let s = l === "ko" ? ko : (DICT[l][ko] ?? ko);
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

/** 에이전트 답변 언어(설정 language 값) */
export const agentLang = (l: Lang) => LANGS.find((x) => x.value === l)!.agent;
export const langOfAgent = (a?: string): Lang | null => (LANGS.find((x) => x.agent === a)?.value ?? null);
