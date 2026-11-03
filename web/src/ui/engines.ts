/** 엔진 색 — 타임라인 띠 · 프로젝트 목록의 캐스팅 막대 · 라이브러리에서 같은 색 */
import { t, useLang } from "../lib/i18n";

export const ENG_COLOR: Record<string, string> = { hyperframes: "#36d399", manim: "#58c4dd", blender: "#f5792a" };
export const engColor = (e: string) => ENG_COLOR[e] ?? "#888";
const LOCALE = { ko: "ko-KR", en: "en-US", zh: "zh-CN" } as const;
export const fmtViews = (v: number | null | undefined) => {
  if (v == null) return "–";
  const l = useLang.getState().lang;
  if (l !== "ko") return new Intl.NumberFormat(LOCALE[l], { notation: "compact", maximumFractionDigits: 1 }).format(v);
  return v >= 1e8 ? `${(v / 1e8).toFixed(1)}억` : v >= 1e4 ? `${Math.round(v / 1e4).toLocaleString()}만` : v.toLocaleString();
};
export const ago = (iso: string) => {
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  return m < 1 ? t("방금") : m < 60 ? t("{n}분 전", { n: Math.round(m) }) : m < 1440 ? t("{n}시간 전", { n: Math.round(m / 60) }) : m < 1440 * 7 ? t("{n}일 전", { n: Math.round(m / 1440) }) : new Date(iso).toLocaleDateString(LOCALE[useLang.getState().lang], { month: "short", day: "numeric" });
};
