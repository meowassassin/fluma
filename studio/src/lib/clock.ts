/* 재생 시계 — 재생 위치(t)를 React 상태 밖에 둔다.
   예전에는 매 프레임 setT 로 편집기 전체가 다시 그려져 버벅였다(초당 60번 전체 렌더).
   지금은 rAF 한 개가 t 를 바꾸고, 구독자(미리보기 iframe · 재생 막대 · 시간 표시)만 직접 갱신된다.
   React 컴포넌트는 useClockSelect 로 '바뀔 때만' 다시 그린다(예: 지금 장면 번호). */
import { useCallback, useRef, useSyncExternalStore } from "react";

type Sub = (t: number) => void;

class Clock {
  t = 0;
  duration = 0;
  playing = false;
  loop = true;
  private raf = 0;
  private from = 0;
  private start = 0;
  private subs = new Set<Sub>();
  private stateSubs = new Set<() => void>();
  audio: HTMLAudioElement | null = null;

  subscribe = (f: Sub) => { this.subs.add(f); return () => { this.subs.delete(f); }; };
  subscribeState = (f: () => void) => { this.stateSubs.add(f); return () => { this.stateSubs.delete(f); }; };
  private emit() { for (const f of this.subs) f(this.t); }
  private emitState() { for (const f of this.stateSubs) f(); }

  setDuration(d: number) { this.duration = Math.max(0, d); if (this.t > this.duration) this.seek(this.duration); this.emitState(); }
  seek = (x: number) => {
    this.t = Math.max(0, Math.min(this.duration, x));
    this.from = this.t; this.start = performance.now();
    if (this.audio) { try { this.audio.currentTime = this.t; } catch { /* 아직 안 불림 */ } }
    this.emit(); this.emitState();
  };
  step = (frames: number, fps = 30) => { this.pause(); this.seek(Math.round(this.t * fps + frames) / fps); };
  play = () => {
    if (this.playing || this.duration <= 0) return;
    if (this.t >= this.duration - 0.03) this.t = 0;
    this.playing = true; this.from = this.t; this.start = performance.now();
    if (this.audio) { try { this.audio.currentTime = this.t; } catch { /* */ } this.audio.play().catch(() => {}); }
    const tick = () => {
      if (!this.playing) return;
      let x = this.from + (performance.now() - this.start) / 1000;
      // 소리가 있으면 소리 시각을 기준으로 맞춘다(끊김 · 밀림 방지)
      if (this.audio && !this.audio.paused && Math.abs(this.audio.currentTime - x) > 0.12) { x = this.audio.currentTime; this.from = x; this.start = performance.now(); }
      if (x >= this.duration) {
        if (this.loop) { x = 0; this.from = 0; this.start = performance.now(); if (this.audio) this.audio.currentTime = 0; }
        else { this.t = this.duration; this.pause(); this.emit(); return; }
      }
      this.t = x; this.emit();
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
    this.emitState();
  };
  pause = () => {
    if (!this.playing) return;
    this.playing = false; cancelAnimationFrame(this.raf); this.audio?.pause();
    this.emitState(); this.emit();
  };
  toggle = () => (this.playing ? this.pause() : this.play());
  reset() { this.pause(); this.t = 0; this.duration = 0; this.audio = null; this.emit(); this.emitState(); }
}

export const clock = new Clock();

/** 재생 중인지 (바뀔 때만 다시 그림) */
export const usePlaying = () => useSyncExternalStore(clock.subscribeState, () => clock.playing);

/** t 에서 뽑은 값이 바뀔 때만 다시 그림 — 예: useClockSelect(t => sceneIndexAt(t)) */
export function useClockSelect<T>(sel: (t: number) => T, eq: (a: T, b: T) => boolean = Object.is): T {
  const selRef = useRef(sel); selRef.current = sel;
  const last = useRef<{ v: T } | null>(null);
  const get = useCallback(() => {
    const v = selRef.current(clock.t);
    if (last.current && eq(last.current.v, v)) return last.current.v;
    last.current = { v }; return v;
  }, [eq]);
  const sub = useCallback((f: () => void) => { const a = clock.subscribe(f); const b = clock.subscribeState(f); return () => { a(); b(); }; }, []);
  return useSyncExternalStore(sub, get);
}

/** DOM 을 직접 바꾸는 구독(React 렌더 없이) — 재생 막대 · 시간 글자 */
export function useClockEffect(ref: React.RefObject<HTMLElement>, write: (el: HTMLElement, t: number) => void) {
  const w = useRef(write); w.current = write;
  const attach = useCallback((el: HTMLElement | null) => {
    if (!el) return;
    w.current(el, clock.t);
    return clock.subscribe((t) => w.current(el, t));
  }, []);
  return attach;
}

export const fmtTime = (t: number) => {
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
};
