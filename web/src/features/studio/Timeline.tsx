/* 타임라인 — 단위는 초(프레임은 표시만). 장면 · 목소리(파형 + 단어). 보고 오가기만 한다 — 고치는 건 채팅으로.
   재생 위치 · 지금 단어 강조 · 시간 글자는 재생 시계를 구독해 DOM 만 바꾼다(재생 중 React 렌더 0). */
import React, { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { FlumaGlyph } from "../../ui/BrandIcons";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "../../ui/Icon";
import { Tip, cx } from "../../ui/kit";
import { clock, fmtTime, usePlaying } from "../../lib/clock";
import { api } from "../../lib/api";
import { useHasAudio } from "../../lib/queries";
import type { Storyboard } from "../../lib/types";
import { t } from "../../lib/i18n";
import { roleName, startsOf, totalOf, useStudio } from "./store";


export const Timeline: React.FC<{ sb: Storyboard; projectId: string }> = ({ sb, projectId }) => {
  const starts = useMemo(() => startsOf(sb), [sb]);
  const total = totalOf(sb) || 1;
  const lanes = useRef<HTMLDivElement>(null);
  const [lw, setLw] = useState(800);
  useLayoutEffect(() => { const el = lanes.current; if (!el) return; const ro = new ResizeObserver(() => setLw(el.clientWidth)); ro.observe(el); return () => ro.disconnect(); }, []);
  const pct = (x: number) => `${(x / total) * 100}%`;

  // 끌어서 위치 옮기기
  const scrub = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const r = lanes.current!.getBoundingClientRect();
    const at = (x: number) => clock.seek(Math.max(0, Math.min(total, ((x - r.left) / r.width) * total)));
    clock.pause(); at(e.clientX);
    const mv = (ev: PointerEvent) => at(ev.clientX);
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  };

  return (
    <div className="tl">
      <Transport total={total} />
      <div className="tl-body">
        <div className="tl-labels" aria-hidden>
          <span className="tl-l ruler-l" /><span className="tl-l">{t("장면")}</span><span className="tl-l voice-l">{t("목소리")}</span>
        </div>
        <div className="tl-hscroll">
        <div className="tl-lanes" ref={lanes} onPointerDown={scrub}>
          <Ruler total={total} width={lw} />
          <div className="lane scenes">
            {sb.scenes.map((s, i) => (
              <SceneClip key={i} i={i} s={s} left={pct(starts[i])} width={`calc(${pct(s.sec)} - 2px)`} start={starts[i]} />
            ))}
          </div>
          <VoiceLane projectId={projectId} total={total} width={lw} />
          <Playhead total={total} />
        </div>
        </div>
      </div>
    </div>
  );
};

/* ---------- 재생 막대: 재생 / 멈춤 · 시간만 (편집 도구 없음) ---------- */
const Transport: React.FC<{ total: number }> = ({ total }) => {
  const playing = usePlaying();
  const time = useRef<HTMLSpanElement>(null);
  useEffect(() => clock.subscribe((t) => { if (time.current) time.current.textContent = fmtTime(t); }), []);
  useEffect(() => { if (time.current) time.current.textContent = fmtTime(clock.t); }, []);
  return (
    <div className="transport">
      <span className="tc mono"><span ref={time}>0:00.00</span><span className="faint"> / {fmtTime(total)}</span></span>
      <div className="transport-mid">
        <Tip label={playing ? t("멈춤") : t("재생")} kbd="Space"><button className="play-btn" onClick={clock.toggle} aria-label={playing ? t("멈춤") : t("재생")}><Icon n={playing ? "pause" : "play"} s={16} /></button></Tip>
      </div>
      <span className="tc-r" />
    </div>
  );
};

const Ruler: React.FC<{ total: number; width: number }> = memo(({ total, width }) => {
  const pxPerSec = width / total;
  const step = pxPerSec > 70 ? 1 : pxPerSec > 30 ? 2 : pxPerSec > 14 ? 5 : 10;
  const ticks = [];
  for (let s = 0; s <= total + 1e-6; s += step) ticks.push(s);
  return (
    <div className="ruler">
      {ticks.map((s) => <span key={s} className={s / total > 0.97 ? "end" : undefined} style={{ left: `${(s / total) * 100}%` }}>{s}s</span>)}
      {pxPerSec > 40 && Array.from({ length: Math.floor(total) + 1 }, (_, s) => <i key={s} style={{ left: `${(s / total) * 100}%` }} />)}
    </div>
  );
});
Ruler.displayName = "Ruler";

const Playhead: React.FC<{ total: number }> = ({ total }) => {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => clock.subscribe((t) => { if (ref.current) ref.current.style.left = `${(t / total) * 100}%`; }), [total]);
  useEffect(() => { if (ref.current) ref.current.style.left = `${(clock.t / total) * 100}%`; }, [total]);
  return <div className="playhead" ref={ref} aria-hidden><b className="playhead-head"><FlumaGlyph s={20} tone="color" /></b></div>;
};

const SceneClip: React.FC<{ i: number; s: Storyboard["scenes"][number]; left: string; width: string; start: number }> = memo(({ i, s, left, width, start }) => {
  const on = useStudio((st) => st.scene === i);
  return (
    <button className={cx("clip", on && "on")} style={{ left, width }} title={`${i + 1}. ${s.caption.replace(/\n/g, " ")} · ${t("{s}초", { s: s.sec.toFixed(1) })}`}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={() => { useStudio.getState().set({ scene: i, pick: null }); clock.pause(); clock.seek(start + Math.min(1, s.sec * 0.4)); }}>
      <span className="clip-n mono">{String(i + 1).padStart(2, "0")}</span>
      <span className="clip-t">{roleName(s.role)} · {s.caption.split("\n")[0]}</span>
    </button>
  );
});
SceneClip.displayName = "SceneClip";

/* ---------- 목소리: 파형(캔버스, 한 번만 그림) + 단어 ---------- */
type Word = { text: string; startMs: number; endMs: number };
const VoiceLane: React.FC<{ projectId: string; total: number; width: number }> = ({ projectId, total, width }) => {
  const { data: audioVer } = useHasAudio(projectId);
  const { data: peaks } = useQuery({
    queryKey: ["peaks", projectId, audioVer], enabled: !!audioVer, staleTime: Infinity,
    queryFn: async ({ signal }) => {
      const buf = await (await fetch(`/api/public/audio/${projectId}.wav?v=${encodeURIComponent(String(audioVer))}`, { signal })).arrayBuffer();
      const ctx = new OfflineAudioContext(1, 1, 22050);
      const a = await ctx.decodeAudioData(buf);
      const d = a.getChannelData(0), n = 800, step = Math.max(1, Math.floor(d.length / n)), out = new Float32Array(n);
      for (let i = 0; i < n; i++) { let m = 0; for (let k = i * step; k < Math.min(d.length, (i + 1) * step); k += 16) m = Math.max(m, Math.abs(d[k])); out[i] = m; }
      return { peaks: out, dur: a.duration };
    },
  });
  const { data: words = [] } = useQuery({
    queryKey: ["captions", projectId, audioVer], enabled: !!audioVer, staleTime: Infinity,
    queryFn: async ({ signal }) => { const r = await fetch(`/api/public/audio/${projectId}.captions.json`, { signal }); return r.ok ? (await r.json() as Word[]) : []; },
  });
  const cv = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = cv.current; if (!c || !peaks) return;
    const dpr = window.devicePixelRatio || 1, w = width, h = 34;
    c.width = w * dpr; c.height = h * dpr; c.style.width = `${w}px`; c.style.height = `${h}px`;
    const g = c.getContext("2d")!; g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
    g.fillStyle = "rgba(180,180,190,0.55)";
    const span = Math.min(1, peaks.dur / total), n = peaks.peaks.length;
    for (let i = 0; i < n; i++) { const x = (i / n) * w * span, ph = Math.max(1.5, peaks.peaks[i] * (h - 4)); g.fillRect(x, (h - ph) / 2, Math.max(1, (w * span) / n - 0.5), ph); }
  }, [peaks, width, total]);
  // 지금 단어 강조 — DOM 클래스만 바꾼다
  const wordEls = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    let last = -1;
    return clock.subscribe((t) => {
      const ms = t * 1000; let k = -1;
      for (let i = 0; i < words.length; i++) if (ms >= words[i].startMs && ms < words[i].endMs) { k = i; break; }
      if (k === last) return;
      if (last >= 0) wordEls.current[last]?.classList.remove("on");
      if (k >= 0) wordEls.current[k]?.classList.add("on");
      last = k;
    });
  }, [words]);
  if (!audioVer) return <div className="lane voice empty"><span>{t("목소리가 아직 없어요 — 에이전트에게 \"목소리 넣어 줘\"라고 말하세요")}</span></div>;
  const silent = !!peaks && peaks.peaks.every((x) => x < 0.004);
  return (
    <div className="lane voice">
      {silent && <span className="voice-silent">{t("시험용 무음 목소리예요 — 에이전트에게 \"타입캐스트로 목소리 넣어 줘\"처럼 말하세요")}</span>}
      <canvas ref={cv} className="wave" aria-hidden />
      <div className="words">
        {words.map((w, k) => {
          const wpx = ((w.endMs - w.startMs) / 1000 / total) * width;
          return (
            <button key={k} ref={(el) => { wordEls.current[k] = el; }} style={{ left: `${(w.startMs / 1000 / total) * 100}%`, width: `${((w.endMs - w.startMs) / 1000 / total) * 100}%` }}
              onPointerDown={(e) => e.stopPropagation()} onClick={() => { clock.pause(); clock.seek(w.startMs / 1000 + 0.01); }} title={w.text.trim()}>
              {wpx >= w.text.trim().length * 9 + 6 ? w.text.trim() : ""}
            </button>
          );
        })}
      </div>
    </div>
  );
};

/** 장면 썸네일(엔진 정지 화면) — 콘티가 바뀐 뒤 잠깐 기다렸다 한 번만 */
export function useThumbs(sb: Storyboard | null, projectId: string, engineName: string) {
  const key = sb ? JSON.stringify(sb.scenes.map((s) => [s.sec, s.caption, s.visual])) + JSON.stringify(sb.direction ?? {}) + (sb.template ?? "") : "";
  return useQuery({
    queryKey: ["thumbs", projectId, key], enabled: !!sb, staleTime: Infinity, gcTime: 10 * 60_000,
    queryFn: async ({ signal }) => {
      await new Promise((r) => setTimeout(r, 1500));
      if (signal.aborted || !sb) return {};
      const starts = startsOf(sb);
      const groups = new Map<string, number[]>();
      sb.scenes.forEach((s, i) => { const e = s.engine || engineName; groups.set(e, [...(groups.get(e) || []), i]); });
      const out: Record<number, string> = {};
      for (const [eng, idx] of groups) {
        const tpl = eng === engineName ? sb.template ?? null : sb.scenes[idx[0]].template ?? null;
        const r = await api.still(projectId, idx.map((i) => +(starts[i] + Math.min(sb.scenes[i].sec * 0.6, sb.scenes[i].sec - 0.2)).toFixed(2)), eng, tpl, signal).catch(() => null);
        r?.stills.forEach((x, k) => { out[idx[k]] = x.url; });
      }
      return out;
    },
  });
}
