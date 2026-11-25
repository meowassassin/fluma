/* DN GENEX 로고(앞으로 겹쳐 나아가는 재생 화살 — 빨강 → 주황 그라데이션)로 만든 아이콘.
 * - FlumaGlyph: 로고 심볼을 SVG 로 옮긴 것(원본 경로 그대로). tone 으로 색만 바꾼다 (원래 그라데이션 · 회색 · 주 행동 버튼 위 흰색).
 * - RailIcon: 왼쪽 메뉴 아이콘 (Icon 과 같은 선 언어). 켜진 메뉴는 뒤 면이 브랜드 빨강으로 바뀐다(shell.css).
 * - FlumaBounce: 답하는 중 — 화살이 앞으로 나아갔다 돌아오고 빛줄기가 지나간다(base.css). (이름은 코드 호환을 위해 그대로) */
import React, { useId } from "react";
import { Icon } from "./Icon";
import { GENEX_PARTS, GENEX_VIEWBOX } from "./genexPaths";
import { t } from "../lib/i18n";

type Tone = "color" | "gray" | "onPrimary";
/** 심볼의 다섯 조각(190×199 격자) — 원본 genex-symbol.svg 와 같은 순서 · 같은 그라데이션 */
const PARTS = GENEX_PARTS;
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
    <svg className={className} width={s} height={s} viewBox={GENEX_VIEWBOX} aria-hidden>
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

/** 답하는 중: 화살이 앞으로 살짝 나아갔다 돌아오고, 빛줄기가 심볼 위를 지나간다(base.css fnudge · fshine). 움직임 줄이기면 멈춘 심볼만 */
export const FlumaBounce: React.FC<{ s?: number; tone?: Tone; label?: string; className?: string }> = ({ s = 16, tone = "color", label = t("에이전트 작업 중"), className }) => (
  <span className={`fbounce ${className ?? ""}`} style={{ width: s, height: s }} role="status" aria-label={label}>
    <i className="fbounce-sh" />
    <span className="fbounce-g"><FlumaGlyph s={s} tone={tone} /></span>
  </span>
);

/** 제작 중(음성 · 화면 · 렌더): 빨리 감기 — 앞으로 힘 있게 밀려 나가고 뒤로 그라데이션 속도선이 흐른다(base.css fff · fstreak) */
export const FlumaStrain: React.FC<{ s?: number; tone?: Tone; label?: string; className?: string }> = ({ s = 16, tone = "color", label = t("영상 만드는 중"), className }) => (
  <span className={`fstrain ${className ?? ""}`} style={{ width: s, height: s }} role="status" aria-label={label}>
    <i className="fstrain-sh" />
    <span className="fstrain-g"><span className="fstrain-t"><FlumaGlyph s={s} tone={tone} /></span></span>
    <i className="fstrain-sw" /><i className="fstrain-sw b" />
  </span>
);
