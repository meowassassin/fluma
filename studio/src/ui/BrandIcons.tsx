/* 로고(기울어진 둥근 카드 두 장 + 눈)의 디자인 언어로 만든 아이콘.
 * - FlumaGlyph: 로고를 SVG 로 옮긴 것. tone 으로 색만 바꾼다 (원래 색 · 회색 · 보라 버튼 위).
 * - RailIcon: 왼쪽 메뉴 아이콘 (Icon 과 같은 로고 언어). 켜진 메뉴는 뒤 카드가 로고 보라로 바뀐다(shell.css).
 * - FlumaBounce: 에이전트 진행 표시 — 로고가 통통 튄다. */
import React from "react";
import { Icon } from "./Icon";
import { t } from "../lib/i18n";

type Tone = "color" | "gray" | "onPrimary";
const TONES: Record<Tone, { back: string; front: string; eye: string; fold: string }> = {
  color: { back: "#5d55f8", front: "#f8f0e8", eye: "#202038", fold: "#2a2380" },
  gray: { back: "var(--glyph-back, #6e6e75)", front: "var(--glyph-front, #c9c9cc)", eye: "var(--glyph-eye, #252526)", fold: "var(--glyph-fold, #4a4a50)" },
  onPrimary: { back: "rgba(255,255,255,.34)", front: "#f8f0e8", eye: "#202038", fold: "rgba(32,24,104,.45)" },
};

/** 로고: 뒤 카드(왼쪽 아래로 기울어짐) + 앞 카드(오른쪽 위로 기울어짐, 눈 두 개). 24 격자 */
export const FlumaGlyph: React.FC<{ s?: number; tone?: Tone; className?: string }> = ({ s = 20, tone = "color", className }) => {
  const c = TONES[tone];
  return (
    <svg className={className} width={s} height={s} viewBox="0 0 24 24" aria-hidden>
      <rect x="3.6" y="7.6" width="11" height="13" rx="2.9" fill={c.back} transform="rotate(-32 9.1 14.1)" />
      <rect x="8.7" y="4.6" width="11.6" height="12.6" rx="2.9" fill={c.fold} opacity=".55" transform="rotate(36 14.5 10.9) translate(-.6 1.2)" />
      <rect x="8.7" y="4.6" width="11.6" height="12.6" rx="2.9" fill={c.front} transform="rotate(36 14.5 10.9)" />
      <rect x="14.6" y="10.7" width="1.3" height="3.1" rx=".65" fill={c.eye} transform="rotate(-6 15.25 12.25)" />
      <rect x="16.9" y="10.55" width="1.3" height="3.1" rx=".65" fill={c.eye} transform="rotate(-6 17.55 12.1)" />
    </svg>
  );
};

/** 왼쪽 메뉴 아이콘 = 같은 로고 언어 아이콘(Icon)을 크게 */
export const RailIcon: React.FC<{ n: string; s?: number }> = ({ n, s = 22 }) => <Icon n={n} s={s} className="ri" />;

/** 에이전트가 일하는 중: 로고가 통통 튄다 (바닥에서 찌그러지고 · 떠오르며 기울고 · 그림자가 작아짐).
 *  움직임 줄이기 설정이면 멈춘 로고만 보인다. */
export const FlumaBounce: React.FC<{ s?: number; tone?: Tone; label?: string; className?: string }> = ({ s = 16, tone = "color", label = t("에이전트 작업 중"), className }) => (
  <span className={`fbounce ${className ?? ""}`} style={{ width: s, height: s }} role="status" aria-label={label}>
    <i className="fbounce-sh" />
    <span className="fbounce-g"><FlumaGlyph s={s} tone={tone} /></span>
  </span>
);

/** 영상 제작 중(음성 · 화면 · 렌더): 로고가 무거운 걸 미는 것처럼 낮게 웅크렸다 버티고, 바들바들 떨고, 땀방울이 튄다.
 *  대화(답 쓰는 중)는 FlumaBounce(통통), 제작은 이것(끙끙) */
export const FlumaStrain: React.FC<{ s?: number; tone?: Tone; label?: string; className?: string }> = ({ s = 16, tone = "color", label = t("영상 만드는 중"), className }) => (
  <span className={`fstrain ${className ?? ""}`} style={{ width: s, height: s }} role="status" aria-label={label}>
    <i className="fstrain-sh" />
    <span className="fstrain-g"><span className="fstrain-t"><FlumaGlyph s={s} tone={tone} /></span></span>
    <i className="fstrain-sw" /><i className="fstrain-sw b" />
  </span>
);
