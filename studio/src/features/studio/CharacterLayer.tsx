/* 캐릭터(립싱크 진행자) 미리보기 — 최종 렌더의 마무리 단계(engine/core/character_overlay.py)와 같은 자리 · 흔들림 · 눈 깜빡임 · 입 모양.
   재생 시계를 구독해 DOM 만 바꾼다(재생 중 React 렌더 없음). */
import React, { useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { clock } from "../../lib/clock";
import { useCharacters, useHasAudio } from "../../lib/queries";
import { t } from "../../lib/i18n";

interface Char {
  name: string; title: string; base: string; eyes_closed: string; mouths: Record<string, string>; viewbox?: [number, number];
  placement?: { side?: "left" | "right"; width?: number; bottom?: number; margin?: number };
  idle?: { bob_px?: number; bob_period?: number; blink_every?: number; blink_len?: number };
}
type Word = { text: string; startMs: number; endMs: number };

// character_overlay.py 와 같은 규칙: 한글은 중성(모음)으로, 영문은 모음 글자로
const JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ";
const VCLASS: Record<string, string> = {};
for (const v of "ㅏㅑㅓㅕㅘ") VCLASS[v] = "a";
for (const v of "ㅐㅒㅔㅖㅙㅞㅚ") VCLASS[v] = "e";
for (const v of "ㅣㅟㅢㅡ") VCLASS[v] = "i";
for (const v of "ㅗㅛㅝ") VCLASS[v] = "o";
for (const v of "ㅜㅠ") VCLASS[v] = "u";
function shapes(text: string): string[] {
  const out: string[] = []; const w = text.trim();
  for (let i = 0; i < w.length; i++) {
    const ch = w[i], o = ch.charCodeAt(0);
    if (o >= 0xac00 && o <= 0xd7a3) out.push(VCLASS[JUNG[Math.floor((o - 0xac00) / 28) % 21]]);
    else if ("aeiouy".includes(ch.toLowerCase())) { out.push(ch.toLowerCase() === "y" ? "i" : ch.toLowerCase()); while (i + 1 < w.length && "aeiouy".includes(w[i + 1].toLowerCase())) i++; }
    else if (/\d/.test(ch)) out.push("a");
  }
  return out.length ? out : ["a"];
}
/** 시각(초) → 입 모양 구간 목록 */
function visemes(words: Word[]): { a: number; b: number; s: string }[] {
  const spans: { a: number; b: number; s: string }[] = [];
  for (const w of words) {
    const a = w.startMs / 1000, b = w.endMs / 1000, sh = shapes(w.text), step = (b - a) / sh.length;
    sh.forEach((s, k) => spans.push({ a: a + k * step, b: a + k * step + step * 0.8, s }));
  }
  return spans;
}

export const CharacterLayer: React.FC<{ name: string | null | undefined; projectId: string; S: number }> = ({ name, projectId, S }) => {
  const { data: chars = [] } = useCharacters();
  const c = (chars as unknown as Char[]).find((x) => x.name === name);
  const { data: audioVer } = useHasAudio(projectId);
  const { data: words = [] } = useQuery({
    queryKey: ["captions", projectId, audioVer], enabled: !!audioVer, staleTime: Infinity,
    queryFn: async ({ signal }) => { const r = await fetch(`/api/public/audio/${projectId}.captions.json`, { signal }); return r.ok ? (await r.json() as Word[]) : []; },
  });
  const spans = useMemo(() => visemes(words), [words]);
  const wrap = useRef<HTMLDivElement>(null);
  const mouths = useRef<Record<string, HTMLImageElement | null>>({});
  const blink = useRef<HTMLImageElement>(null);

  useEffect(() => {
    if (!c) return;
    const idle = c.idle ?? {};
    const draw = (t: number) => {
      const el = wrap.current; if (!el) return;
      el.style.transform = `translateY(${(idle.bob_px ?? 8) * Math.sin((2 * Math.PI * t) / (idle.bob_period ?? 2.4)) * S}px)`;
      const sp = spans.find((x) => t >= x.a && t < x.b);
      const cur = sp?.s ?? "closed";
      for (const [k, img] of Object.entries(mouths.current)) if (img) img.style.visibility = k === cur ? "visible" : "hidden";
      if (blink.current) blink.current.style.visibility = ((t + 0.7) % (idle.blink_every ?? 3.4)) < (idle.blink_len ?? 0.12) ? "visible" : "hidden";
    };
    draw(clock.t);
    return clock.subscribe(draw);
  }, [c, spans, S]);

  if (!c) return null;
  const P = c.placement ?? {}, vb = c.viewbox ?? [400, 480];
  const w = (P.width ?? 240) * S, h = (w * vb[1]) / vb[0];
  const side = P.side ?? "right", m = (P.margin ?? 36) * S, bottom = (P.bottom ?? 36) * S;
  return (
    <div ref={wrap} className="char-layer" style={{ width: w, height: h, bottom, [side]: m } as React.CSSProperties} aria-label={t("캐릭터 {name}", { name: c.title })} title={t("캐릭터 {name} — 최종 렌더에도 이 자리에 합성됩니다", { name: c.title })}>
      <img src={c.base} alt="" />
      {Object.entries(c.mouths).map(([k, u]) => <img key={k} ref={(el) => { mouths.current[k] = el; }} src={u} alt="" style={{ visibility: k === "closed" ? "visible" : "hidden" }} />)}
      <img ref={blink} src={c.eyes_closed} alt="" style={{ visibility: "hidden" }} />
    </div>
  );
};
