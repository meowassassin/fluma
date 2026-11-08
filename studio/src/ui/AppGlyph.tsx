/* 편집기 탐색기 · 탭의 아이콘 — 툴 · 재료마다 고유한 색 글리프(VS Code 파일 아이콘 문법: 작은 크기에서도 모양 · 색으로 바로 구분).
   선 아이콘이 아니라 면 + 한 가지 상징: 필름(컷 편집) · 키프레임(그래픽) · 파형(소리) · 펜촉(그림) · 조리개(사진) · 표(데이터) · 문서 · 자막 */
import React from "react";

export type GlyphKind = "stats" | "film" | "motion" | "sound" | "voice" | "caption" | "music" | "sfx" | "vector" | "photo" | "grid" | "doc" | "video" | "scene" | "project";

const C: Record<GlyphKind, string> = {
  stats: "#ff5c8a", project: "#8b80ff", film: "#8b80ff", scene: "#8b80ff", motion: "#f2b84b", sound: "#3ec7a3", voice: "#3ec7a3", caption: "#5aa9ff", music: "#3ec7a3", sfx: "#3ec7a3",
  vector: "#ff8f4d", photo: "#ff6b9a", grid: "#4fc05a", doc: "#ff5f56", video: "#8b80ff",
};

export const AppGlyph: React.FC<{ k: GlyphKind; s?: number }> = ({ k, s = 16 }) => {
  const c = C[k];
  const P: Record<GlyphKind, React.ReactNode> = {
    stats: <><rect x="2" y="9" width="3" height="5" rx="1" fill={c} /><rect x="6.5" y="6" width="3" height="8" rx="1" fill={c} /><rect x="11" y="2.5" width="3" height="11.5" rx="1" fill={c} /></>,
    project: <><rect x="2" y="3" width="12" height="10" rx="2.5" fill={c} /><path d="M6.6 5.8v4.4L10.4 8z" fill="#1e1e1e" /></>,
    film: <><rect x="1.5" y="3" width="13" height="10" rx="2" fill={c} />{[3.4, 6.4, 9.4, 12.4].map((x) => <React.Fragment key={x}><rect x={x - 0.7} y="4" width="1.4" height="1.4" rx=".4" fill="#1e1e1e" /><rect x={x - 0.7} y="10.6" width="1.4" height="1.4" rx=".4" fill="#1e1e1e" /></React.Fragment>)}<rect x="3" y="6.4" width="10" height="3.2" rx=".8" fill="#1e1e1e" opacity=".35" /></>,
    scene: <><rect x="2" y="4" width="12" height="8" rx="1.6" fill="none" stroke={c} strokeWidth="1.4" /><rect x="4.5" y="6.5" width="3" height="3" rx=".6" fill={c} /></>,
    motion: <><path d="M8 1.8 14.2 8 8 14.2 1.8 8z" fill={c} /><path d="M8 5.2 10.8 8 8 10.8 5.2 8z" fill="#1e1e1e" opacity=".55" /></>,
    sound: <>{[[2.5, 6, 10], [5.5, 3.5, 12.5], [8.5, 2, 14], [11.5, 4.5, 11.5], [14, 6.5, 9.5]].map(([x, a, b]) => <rect key={x} x={x - 1} y={a} width="2" height={b - a} rx="1" fill={c} />)}</>,
    voice: <><rect x="5.5" y="1.8" width="5" height="8.4" rx="2.5" fill={c} /><path d="M3.5 7.6a4.5 4.5 0 0 0 9 0" fill="none" stroke={c} strokeWidth="1.4" strokeLinecap="round" /><rect x="7.3" y="12" width="1.4" height="2.4" rx=".7" fill={c} /></>,
    caption: <><rect x="1.5" y="3" width="13" height="10" rx="2.2" fill={c} /><path d="M7 6.4a2 2 0 1 0 0 3.2M12 6.4a2 2 0 1 0 0 3.2" fill="none" stroke="#1e1e1e" strokeWidth="1.4" strokeLinecap="round" /></>,
    music: <><path d="M6 11.5V3.4l7-1.6v8.2" fill="none" stroke={c} strokeWidth="1.6" strokeLinejoin="round" /><circle cx="4.4" cy="11.7" r="2.2" fill={c} /><circle cx="11.4" cy="10.2" r="2.2" fill={c} /></>,
    sfx: <><path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill={c} /><path d="M11 5.2a4 4 0 0 1 0 5.6M12.8 3.4a6.5 6.5 0 0 1 0 9.2" fill="none" stroke={c} strokeWidth="1.4" strokeLinecap="round" /></>,
    vector: <><path d="M8 1.6 12.6 8.2 8 14.4 3.4 8.2z" fill={c} /><circle cx="8" cy="8.6" r="1.4" fill="#1e1e1e" /><path d="M8 1.6v5.6" stroke="#1e1e1e" strokeWidth="1" /></>,
    photo: <><circle cx="8" cy="8" r="6.4" fill={c} />{[0, 60, 120, 180, 240, 300].map((a) => <path key={a} d="M8 8 8 2.4" stroke="#1e1e1e" strokeWidth="1.1" opacity=".5" transform={`rotate(${a + 20} 8 8)`} />)}<circle cx="8" cy="8" r="2.2" fill="#1e1e1e" opacity=".7" /></>,
    grid: <><rect x="2" y="2.5" width="12" height="11" rx="2" fill={c} /><path d="M2 6.2h12M2 9.8h12M6.2 2.5v11" stroke="#1e1e1e" strokeWidth="1.1" opacity=".55" /></>,
    doc: <><path d="M3.5 1.8h6l3 3v9.4h-9z" fill={c} /><path d="M9.5 1.8v3h3" fill="#1e1e1e" opacity=".35" /><path d="M5.5 8h5M5.5 10.4h5" stroke="#1e1e1e" strokeWidth="1.1" opacity=".55" /></>,
    video: <><rect x="1.5" y="3.5" width="9.5" height="9" rx="2" fill={c} /><path d="M11.6 6.8 14.5 5v6l-2.9-1.8z" fill={c} /></>,
  };
  return <svg width={s} height={s} viewBox="0 0 16 16" aria-hidden className="glyph">{P[k]}</svg>;
};
