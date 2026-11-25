/* DN GENEX 로고(앞으로 겹쳐 나아가는 재생 화살 — 빨강 → 주황 그라데이션)로 만든 아이콘.
 * - FlumaGlyph: 로고 심볼을 SVG 로 옮긴 것(원본 경로 그대로). tone 으로 색만 바꾼다 (원래 그라데이션 · 회색 · 주 행동 버튼 위 흰색).
 * - RailIcon: 왼쪽 메뉴 아이콘 (Icon 과 같은 선 언어). 켜진 메뉴는 뒤 면이 브랜드 빨강으로 바뀐다(shell.css).
 * - FlumaBounce: 에이전트 진행 표시 — 로고가 통통 튄다. (이름은 코드 호환을 위해 그대로) */
import React, { useId } from "react";
import { Icon } from "./Icon";
import { t } from "../lib/i18n";

type Tone = "color" | "gray" | "onPrimary";
/** 심볼의 다섯 조각(190×199 격자) — 원본 genex-symbol.svg 와 같은 순서 · 같은 그라데이션 */
const PARTS = [
  "M56.0846 133.646C57.7125 134.586 59.7186 134.586 61.3465 133.646L96.3647 113.428L53.4536 88.6537V129.089C53.4537 130.969 54.4567 132.706 56.0846 133.646Z",
  "M55.623 197.84C56.9222 198.556 58.5095 198.5 59.755 197.694L184.286 117.165L149.877 97.2988L55.6185 160.675C54.5857 161.369 53.9347 162.499 53.8465 163.731L53.8364 163.979L53.5373 194.271C53.5227 195.754 54.324 197.125 55.623 197.84Z",
  "M8.24109 167.578C4.68347 169.823 0.0435921 167.267 0.0435921 163.053L0.0076486 57.7963L36.3828 78.7975L36.702 149.122C36.7136 150.975 35.7695 152.691 34.2037 153.681L8.24109 167.578Z",
  "M59.7405 0.622055C58.4817 -0.1721 56.8869 -0.208427 55.5939 0.528734C54.3009 1.26598 53.5199 2.65681 53.5622 4.14465L54.4257 34.4706C54.4637 35.8072 55.1629 37.0381 56.291 37.756L149.877 97.2993L184.286 117.165L187.749 114.926C188.987 114.125 189.665 112.73 189.58 111.303L189.797 84.9562C189.809 83.5614 189.098 82.259 187.919 81.5146L59.7405 0.622055Z",
  "M115.31 93.3772L61.3465 62.2215L33.8953 46.2207L8.08236 30.8043C4.51323 28.6744 0 31.2534 0 35.3982L0.0076486 57.7963L36.3828 78.7975L53.4536 88.6533L96.3647 113.428L115.31 102.49C116.937 101.55 117.941 99.8128 117.941 97.9331C117.94 96.0537 116.937 94.3171 115.31 93.3772Z",
];
const GRAD: [x1: number, y1: number, x2: number, y2: number, stops: [number, string][]][] = [
  [90.4, 99, 57.6, 134.7, [[0, "#DF1F2B"], [0.2, "#E8402A"], [0.6, "#F37322"], [1, "#F9A23B"]]],
  [248.7, 125.5, 196.8, 209.9, [[0.3, "#CB431A"], [0.4, "#EE5A26"], [0.66, "#E8402A"], [1, "#DF1F2B"]]],
  [58.1, 35.1, -21.3, 172.1, [[0.3, "#CB431A"], [0.4, "#EE5A26"], [0.66, "#E8402A"], [1, "#DF1F2B"]]],
  [53.6, 22.5, 190.4, 85.3, [[0, "#FFB257"], [1, "#ED6927"]]],
  [0, 46.1, 109.4, 107.1, [[0, "#FFB257"], [1, "#EA4929"]]],
];
const FLAT: Record<Exclude<Tone, "color">, string[]> = {
  gray: ["var(--glyph-front, #c9c6c3)", "var(--glyph-back, #77736f)", "var(--glyph-back, #77736f)", "var(--glyph-front, #c9c6c3)", "var(--glyph-fold, #a19d99)"],
  onPrimary: ["#ffffff", "rgba(255,255,255,.78)", "rgba(255,255,255,.78)", "#ffffff", "rgba(255,255,255,.9)"],
};

/** 로고 심볼. 정사각 상자(s) 가운데에 비율 그대로 */
export const FlumaGlyph: React.FC<{ s?: number; tone?: Tone; className?: string }> = ({ s = 20, tone = "color", className }) => {
  const id = useId().replace(/[^A-Za-z0-9_-]/g, "");
  return (
    <svg className={className} width={s} height={s} viewBox="-5 0 200 199" aria-hidden>
      {tone === "color" && (
        <defs>
          {GRAD.map(([x1, y1, x2, y2, st], i) => (
            <linearGradient key={i} id={`g${id}${i}`} x1={x1} y1={y1} x2={x2} y2={y2} gradientUnits="userSpaceOnUse">
              {st.map(([o, c]) => <stop key={o} offset={o} stopColor={c} />)}
            </linearGradient>
          ))}
        </defs>
      )}
      {PARTS.map((d, i) => <path key={i} d={d} fill={tone === "color" ? `url(#g${id}${i})` : FLAT[tone][i]} />)}
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
