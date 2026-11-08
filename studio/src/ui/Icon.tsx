import React, { useId } from "react";
import flumaIcon64 from "../assets/brand/fluma-64.png";
import flumaIcon192 from "../assets/brand/fluma-192.png";

/** 로고 언어 아이콘 (24 격자, 둥근 끝 선). 로고처럼 기울어진 '뒤 카드'(옅은 면)를 깔 수 있는 아이콘은 b 로 준다.
 *  이모지 · 글자 아이콘을 쓰지 않는다. 뒤 카드 색은 .ri-b (base.css) — 켜진 메뉴에서는 로고 보라. */
type Card = [x: number, y: number, w: number, h: number, r: number, rot: number];
type Def = { d: string; b?: Card; fill?: boolean; sw?: number };

/** 둥근 사각형 경로 */
const rr = (x: number, y: number, w: number, h: number, r: number) =>
  `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 -${r} ${r}h-${w - 2 * r}a${r} ${r} 0 0 1 -${r} -${r}v-${h - 2 * r}a${r} ${r} 0 0 1 ${r} -${r}z`;
const SPEAKER = "M4.5 9.5h3l4.5-4v13l-4.5-4h-3z";
const LENS = "M16.1 10.5a5.6 5.6 0 1 1-11.2 0 5.6 5.6 0 0 1 11.2 0zM15 15l5 5";

const D: Record<string, Def> = {
  // 메뉴
  home: { b: [3, 8.5, 13, 12, 3, -10], d: "M5 11.4 12 5.3l7 6.1v6.6a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 18zM12 15.6v2.4" },
  film: { b: [3.2, 7.5, 12, 12, 3, -12], d: `${rr(8.6, 3.8, 12, 12, 3)}M13.4 7.6 17 9.8l-3.6 2.2z` },
  trend: { b: [3, 5, 14, 14, 3.5, -10], d: "M5 16.5 9.5 12l3 3L19 8.5M15 8.5h4v4" },
  library: { b: [3.2, 6.5, 11, 14, 2.8, -14], d: `${rr(9.4, 4.2, 10.4, 14.4, 2.8)}M12.6 8.8h4.4M12.4 12h3.6` },
  search: { b: [4.2, 4.2, 11.5, 11.5, 3.2, -18], d: LENS },
  keyboard: { b: [3, 8.2, 17, 11, 3, -7], d: `${rr(3.5, 6.5, 17, 11, 3)}M7.5 10.2h0M10.5 10.2h0M13.5 10.2h0M16.5 10.2h0M8.5 13.8h7` },
  gear: { b: [5.6, 5.6, 12.8, 12.8, 3.2, 45], d: `${rr(5.6, 5.6, 12.8, 12.8, 3.2)}M14.7 12a2.7 2.7 0 1 1-5.4 0 2.7 2.7 0 0 1 5.4 0z` },
  // 기본 동작
  plus: { d: "M12 6v12M6 12h12" },
  close: { d: "M7 7l10 10M17 7 7 17" },
  check: { d: "M6 12.5l4 4 8-9" },
  chevron: { d: "M10 7l5 5-5 5" },
  down: { d: "M7 10l5 5 5-5" },
  arrowUp: { d: "M12 18.5V6M7 11l5-5 5 5" },
  more: { d: "M6 12h.01M12 12h.01M18 12h.01", sw: 3 },
  dot: { d: "M12 12h.01", sw: 6 },
  undo: { d: "M9 7 5 11l4 4M5 11h9.5a4.5 4.5 0 0 1 0 9H12" },
  history: { b: [5, 5, 12, 12, 3.2, -12], d: "M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 5v4h4M12 8.5V12l2.5 2" },
  stepBack: { d: "M14.5 7 9.5 12l5 5" },
  stepFwd: { d: "M9.5 7l5 5-5 5" },
  skipBack: { d: "M6.5 6v12M18 6.8v10.4a.8.8 0 0 1-1.2.7L9.5 12.7a.8.8 0 0 1 0-1.4l7.3-5.2a.8.8 0 0 1 1.2.7z" },
  skipFwd: { d: "M17.5 6v12M6 6.8v10.4a.8.8 0 0 0 1.2.7l7.3-5.2a.8.8 0 0 0 0-1.4L7.2 6.1a.8.8 0 0 0-1.2.7z" },
  play: { d: "M8 5.6v12.8a1 1 0 0 0 1.5.9l10-6.4a1 1 0 0 0 0-1.8l-10-6.4A1 1 0 0 0 8 5.6z", fill: true },
  pause: { d: `${rr(6.5, 5, 4, 14, 1.6)}${rr(13.5, 5, 4, 14, 1.6)}`, fill: true },
  stop: { d: rr(6, 6, 12, 12, 3), fill: true },
  zoomIn: { b: [4.2, 4.2, 11.5, 11.5, 3.2, -18], d: `${LENS}M10.5 8v5M8 10.5h5` },
  zoomOut: { b: [4.2, 4.2, 11.5, 11.5, 3.2, -18], d: `${LENS}M8 10.5h5` },
  // 상태 · 알림
  warn: { d: "M10.3 4.9 3.6 16.6a2 2 0 0 0 1.7 3h13.4a2 2 0 0 0 1.7-3L13.7 4.9a2 2 0 0 0-3.4 0zM12 10v3.5M12 16.6h.01" },
  info: { b: [3.5, 5, 14, 14, 3.5, -10], d: `${rr(5, 4, 15, 15, 4)}M12.5 11v4.5M12.5 8h.01` },
  lock: { b: [3.5, 11, 14, 10, 3, -8], d: `${rr(5, 10.5, 14, 9.5, 3)}M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5` },
  eye: { d: "M2.8 12s3.4-6 9.2-6 9.2 6 9.2 6-3.4 6-9.2 6-9.2-6-9.2-6zM14.5 12a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z" },
  eyeOff: { d: "M2.8 12s3.4-6 9.2-6 9.2 6 9.2 6-3.4 6-9.2 6-9.2-6-9.2-6zM14.5 12a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM4.5 4.5l15 15" },
  // 만들기 · 편집
  sparkle: { d: "M11 4.5c.6 3.4 2.2 5 5.5 5.6-3.3.6-4.9 2.2-5.5 5.6-.6-3.4-2.2-5-5.5-5.6 3.3-.6 4.9-2.2 5.5-5.6zM17.5 14.5c.3 1.6 1 2.3 2.5 2.6-1.5.3-2.2 1-2.5 2.6-.3-1.6-1-2.3-2.5-2.6 1.5-.3 2.2-1 2.5-2.6z" },
  wand: { d: "M5 19 15 9M13 7l4 4M17.5 3.5v2.5M16.25 4.75h2.5M20.5 9v2M19.5 10h2M8.5 4v2M7.5 5h2" },
  cursor: { d: "M6 4.5l12.5 6.3-5.4 1.7-2.4 5.4z" },
  comment: { b: [3, 7, 14, 11, 3, -8], d: `${rr(5.5, 4.5, 15, 11.5, 3.5)}M10 16l-2.5 4 5-4` },
  text: { d: "M6 7V5h12v2M12 5v14M9.5 19h5" },
  shape: { d: `${rr(4, 10, 10, 10, 2.5)}M20.5 9a5 5 0 1 1-10 0 5 5 0 0 1 10 0z` },
  diamond: { d: "M12 4.2 19.8 12 12 19.8 4.2 12z" },
  pen: { d: "M4.5 19.5c3-1 4.2-4.2 6.5-6.5s5.5-2.4 7.5-6.5M15.5 5.5l3 3" },
  camera: { b: [2.8, 8.5, 12, 10, 3, -8], d: `${rr(4.5, 7.5, 11, 10, 3)}M15.5 11l4.5-2.5v7l-4.5-2.5` },
  circle: { d: "M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0z" },
  square: { d: rr(5, 5, 14, 14, 3) },
  proxy: { d: "M5 8V5h3M16 5h3v3M19 16v3h-3M8 19H5v-3M9.5 12h5" },
  sketch: { d: "M4 18.5c2.5-.2 3.8-2 5-4.5s2.3-6 4.5-6 2 3.6 3.6 3.6S19.5 9 20 7.5M4 21h16" },
  layers: { b: [3.2, 8.6, 13, 11, 3, -10], d: `${rr(7.5, 4.5, 13, 11, 3)}M10.5 9h7` },
  scene: { b: [3.2, 7, 12, 13, 3, -12], d: `${rr(8, 4, 12, 15, 3)}M11 9h6M11 12.5h4` },
  grid: { d: `${rr(4, 4, 7, 7, 2)}${rr(13, 4, 7, 7, 2)}${rr(4, 13, 7, 7, 2)}${rr(13, 13, 7, 7, 2)}` },
  list: { d: "M9 7h10M9 12h10M9 17h10M5 7h.01M5 12h.01M5 17h.01" },
  safe: { d: `${rr(4.5, 3.5, 15, 17, 3.5)}${rr(7.5, 7, 9, 10, 2)}` },
  palette: { b: [3.2, 6, 13, 13, 3.5, -12], d: "M12 4a8 8 0 1 0 0 16c1.2 0 1.8-.8 1.8-1.7 0-1.2-1-1.6-1-2.6 0-.9.7-1.4 1.6-1.4H17a3 3 0 0 0 3-3C20 7.4 16.4 4 12 4zM8 11h.01M10.5 7.6h.01M15 8h.01" },
  // 미디어 · 파일
  image: { b: [3, 7, 14, 12, 3, -9], d: `${rr(6, 4.5, 15, 13, 3.5)}M6.5 14.5l4-4 3.5 3.5 2.2-2.2 4.3 4.3M16.5 8.5h.01` },
  video: { b: [3, 8.5, 12, 11, 3, -8], d: `${rr(4, 6.5, 12, 11, 3)}M16 10.5l4.5-2.7v8.4L16 13.5` },
  render: { b: [3.2, 7.5, 12, 12, 3, -12], d: `${rr(8.4, 4, 12, 12, 3)}M12.4 7.7 16.6 10l-4.2 2.3z` },
  mic: { d: `${rr(9, 3.5, 6, 10.5, 3)}M6 11.5a6 6 0 0 0 12 0M12 17.5v3M9 20.5h6` },
  volume: { d: `${SPEAKER}M15.8 9a4.2 4.2 0 0 1 0 6M18.4 6.5a7.6 7.6 0 0 1 0 11` },
  mute: { d: `${SPEAKER}M15.5 9.5l5 5M20.5 9.5l-5 5` },
  folder: { b: [3, 8, 15, 11, 3, -7], d: "M4.5 8a3 3 0 0 1 3-3H10l2 2.5h4.5a3 3 0 0 1 3 3V16a3 3 0 0 1-3 3h-9a3 3 0 0 1-3-3z" },
  copy: { b: [3.5, 4, 11, 11, 3, -8], d: rr(8.5, 8.5, 11.5, 11.5, 3) },
  upload: { d: "M12 15V5M7.5 9.5 12 5l4.5 4.5M5.5 19h13" },
  download: { d: "M12 5v10M7.5 10.5 12 15l4.5-4.5M5.5 19h13" },
  export: { d: "M10.5 13.5 19 5M14 5h5v5M17 13.5V16a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-6a3 3 0 0 1 3-3h2.5" },
  external: { d: "M10.5 13.5 19 5M14 5h5v5M17 13.5V16a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3v-6a3 3 0 0 1 3-3h2.5" },
  link: { d: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" },
  trash: { d: "M5 7h14M10 4h4M7 7l.8 11a2 2 0 0 0 2 1.9h4.4a2 2 0 0 0 2-1.9L17 7M10.5 11v5M13.5 11v5" },
  // 화면 구성
  panel: { d: `${rr(4, 5, 16, 14, 3)}M15 5v14` },
  sidebarL: { d: `${rr(4, 5, 16, 14, 3)}M9.5 5v14` },
  sidebarR: { d: `${rr(4, 5, 16, 14, 3)}M14.5 5v14` },
  // 사람 · 설정
  user: { b: [4, 11, 14, 10, 3.5, -8], d: "M15.5 8a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0zM5.5 19.5c.8-3.2 3.4-5 6.5-5s5.7 1.8 6.5 5" },
  engine: { b: [4, 6, 12, 12, 3, -10], d: `${rr(6.5, 6.5, 11, 11, 3)}M9.5 3.5v3M14.5 3.5v3M9.5 17.5v3M14.5 17.5v3M3.5 9.5h3M3.5 14.5h3M17.5 9.5h3M17.5 14.5h3` },
  memory: { b: [3.5, 6, 12, 14, 3, -10], d: `${rr(6.5, 3.5, 12, 17, 3.5)}M10 3.5v6l2.5-1.8 2.5 1.8v-6` },
};
D.studio = D.film;
D.keys = D.keyboard;

/** 로고를 한 색으로: 뒤 카드(옅게) + 앞 카드(진하게, 눈은 뚫림). 에이전트 · 브랜드 자리에 쓴다 */
const MonoGlyph: React.FC<{ s: number; className?: string }> = ({ s, className }) => {
  const id = useId().replace(/:/g, "");
  return (
    <svg className={`ic ${className ?? ""}`} width={s} height={s} viewBox="0 0 24 24" aria-hidden>
      <defs><mask id={`m${id}`}><rect width="24" height="24" fill="#fff" />
        <rect x="14.6" y="10.7" width="1.3" height="3.1" rx=".65" fill="#000" transform="rotate(-6 15.25 12.25)" />
        <rect x="16.9" y="10.55" width="1.3" height="3.1" rx=".65" fill="#000" transform="rotate(-6 17.55 12.1)" /></mask></defs>
      <rect className="ri-b" x="3.6" y="7.6" width="11" height="13" rx="2.9" fill="currentColor" transform="rotate(-32 9.1 14.1)" />
      <rect x="8.7" y="4.6" width="11.6" height="12.6" rx="2.9" fill="currentColor" mask={`url(#m${id})`} transform="rotate(36 14.5 10.9)" />
    </svg>
  );
};

export const Icon: React.FC<{ n: string; s?: number; className?: string }> = ({ n, s = 16, className }) => {
  if (n === "agent" || n === "brand") return <MonoGlyph s={s} className={className} />;
  const def = D[n] ?? D.dot;
  const card = def.b;
  return (
    <svg className={`ic ${className ?? ""}`} width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={def.sw ?? 2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {card && <rect className="ri-b" x={card[0]} y={card[1]} width={card[2]} height={card[3]} rx={card[4]}
        transform={`rotate(${card[5]} ${card[0] + card[2] / 2} ${card[1] + card[3] / 2})`} />}
      <path d={def.d} fill={def.fill ? "currentColor" : undefined} />
    </svg>
  );
};

/** Fluma 마스코트 아이콘 (보라 · 크림 두 장이 접힌 얼굴). 작은 크기는 64px, 큰 크기는 192px 원본에서 줄인다 */
export const FlumaMark: React.FC<{ s?: number }> = ({ s = 18 }) => (
  <img src={s > 40 ? flumaIcon192 : flumaIcon64} width={s} height={s} alt="" aria-hidden draggable={false} style={{ display: "block" }} />
);

/** 9:16 썸네일 자리: 룩 색으로 그린 자리 표시 (실제 정지 화면이 있으면 그것) */
export const Poster: React.FC<{ url?: string | null; bg?: string; accent?: string; title?: string }> = ({ url, bg = "#252526", accent = "#5850f8", title }) => (
  url ? <img className="poster" src={url} alt="" />
    : <div className="poster ph" style={{ background: `radial-gradient(120% 70% at 30% 20%, ${accent}33, transparent 60%), ${bg}` }}>{title && <span>{title}</span>}</div>
);
