/* 미리보기 — 영상 화면만 보여 준다. 편집은 채팅으로(손 편집 도구 없음 — 2026-11-02).
   · 화면을 누르면 그 자리(장면 · 시각 · 위치 · 그 요소 이름)를 에이전트에게 넘길 맥락으로 짚는다
   · 다시 빌드할 때는 새 iframe 을 숨겨 불러온 뒤 바꿔 끼운다(흰 화면 깜빡임 없음) */
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, EmptyState, Spinner } from "../../ui/kit";
import { FlumaStrain } from "../../ui/BrandIcons";
import { api, errMsg } from "../../lib/api";
import { clock, useClockSelect } from "../../lib/clock";
import { onFsEvent } from "../../lib/queries";
import { useAgentBusy, useSession, doing } from "../../lib/agent";
import type { EngineMeta, Storyboard } from "../../lib/types";
import { CharacterLayer } from "./CharacterLayer";
import { t } from "../../lib/i18n";
import { roleName, describe, frameDoc, sceneAt, seekFrame, setFrame, startsOf, useStudio } from "./store";

const W = 1080, H = 1920;

export const Preview: React.FC<{ sb: Storyboard | null; projectId: string; engine: EngineMeta | null; loading: boolean; missing: boolean }> = ({ sb, projectId, engine, loading, missing }) => {
  const wrap = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ w: 600, h: 800 });
  useLayoutEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const S = Math.max(0.08, Math.min((box.h - 40) / H, (box.w - 24) / W));
  const PW = Math.round(W * S), PH = Math.round(H * S);
  const busy = useAgentBusy(projectId);
  const guide = useStudio((s) => s.guide);

  return (
    <section className="canvas" ref={wrap} aria-label={t("미리보기")}>
      {!sb ? (
        <div className="canvas-empty">
          {loading ? <Spinner s={20} /> : busy ? <AgentMaking projectId={projectId} /> :
            <EmptyState icon="film" title={missing ? t("아직 콘티가 없어요") : t("콘티를 불러오지 못했어요")} body={missing ? t("오른쪽 에이전트에게 만들 영상을 말하면 조사 · 콘티 · 목소리 · 화면까지 이어서 만듭니다.") : undefined} />}
        </div>
      ) : engine?.preview === "html" ? (
        <div className="frame-wrap" style={{ width: PW }}>
          <SceneLabel sb={sb} />
          <div className="frame frame-deck" style={{ width: PW, height: PH }}>
            <FrameHost sb={sb} projectId={projectId} engine={engine} S={S} />
            <div className="vwin-in" style={{ left: 0, top: 0, width: PW, height: PH }}><CharacterLayer name={sb.character} projectId={projectId} S={S} /></div>
            <PointLayer sb={sb} S={S} />
            {guide && <SafeGuide S={S} />}
          </div>
          <p className="faint small pv-hint">{t("화면을 누르면 그 자리를 짚어 에이전트에게 넘깁니다 — \"이거 더 크게\", \"여기 다른 짤로\"처럼 말해 주세요.")}</p>
        </div>
      ) : (
        <DraftPreview projectId={projectId} engine={engine} PW={PW} PH={PH} />
      )}
    </section>
  );
};

const AgentMaking: React.FC<{ projectId: string }> = ({ projectId }) => {
  const s = useSession(projectId);
  return (
    <div className="making">
      <div className="making-poster"><span className="skel" /></div>
      <b>{t("에이전트가 영상을 만들고 있어요")}</b>
      <p className="muted"><FlumaStrain s={14} /> {s.live ? doing(s.live.tools) ?? s.live.status : t("준비 중")}</p>
      <p className="faint">{t("콘티가 생기면 여기에 바로 미리보기가 나옵니다. 진행 상황은 오른쪽 패널에서 볼 수 있어요.")}</p>
    </div>
  );
};

const SceneLabel: React.FC<{ sb: Storyboard }> = ({ sb }) => {
  const starts = startsOf(sb);
  const i = useClockSelect((t) => sceneAt(starts, sb, t));
  return <div className="frame-label"><b>{t("장면 {n}", { n: i + 1 })}</b><span>{roleName(sb.scenes[i]?.role)}</span><span className="faint">· 1080×1920</span></div>;
};

/* ---------- iframe: 빌드 · 이중 버퍼 ---------- */
const FrameHost: React.FC<{ sb: Storyboard; projectId: string; engine: EngineMeta; S: number }> = ({ sb, projectId, engine, S }) => {
  const [comp, setComp] = useState(0);
  const [frames, setFrames] = useState<{ url: string; ready: boolean }[]>([]);
  const [state, setState] = useState<{ busy: boolean; err: string | null }>({ busy: true, err: null });
  // 에이전트가 화면 구성 · 음성 · 요소를 바꾸면 다시 빌드
  useEffect(() => onFsEvent((e) => { if (e.id === projectId && (e.kind === "composition" || e.kind === "audio" || e.kind === "elements")) setComp((c) => c + 1); }), [projectId]);
  const key = JSON.stringify(sb) + ":" + comp + ":" + engine.name;
  useEffect(() => {
    const ac = new AbortController();
    setState((s) => ({ ...s, busy: true }));
    const h = setTimeout(() => {
      api.build(projectId, engine.name, sb.template ?? null, ac.signal)
        .then((r) => setFrames((fs) => [...fs.filter((f) => f.ready).slice(-1), { url: r.url, ready: false }]))
        .catch((e) => { if (e?.name !== "AbortError") setState({ busy: false, err: errMsg(e) }); });
    }, 300);
    return () => { clearTimeout(h); ac.abort(); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const onLoad = (url: string, el: HTMLIFrameElement) => {
    setFrame(el);
    setFrames((fs) => fs.filter((f) => f.url === url).map((f) => ({ ...f, ready: true })));
    setState({ busy: false, err: null });
    seekFrame(clock.t);
  };
  // 재생 시계 → iframe (React 렌더 없음)
  useEffect(() => clock.subscribe((t) => seekFrame(t)), []);

  return (
    <>
      {frames.map((f) => (
        <iframe key={f.url} src={f.url} title={t("미리보기")} tabIndex={-1} className={f.ready ? "pv-frame" : "pv-frame loading"}
          sandbox="allow-scripts allow-same-origin" style={{ transform: `scale(${S})`, width: W, height: H }}
          onLoad={(e) => onLoad(f.url, e.currentTarget)} />
      ))}
      {state.busy && <div className="pv-busy"><Spinner s={12} />{frames.some((f) => f.ready) ? t("갱신 중") : t("미리보기 준비 중")}</div>}
      {state.err && <div className="pv-err" role="alert"><Icon n="warn" s={14} /><span>{state.err}</span><Button size="sm" onClick={() => setComp((c) => c + 1)}>{t("다시 시도")}</Button></div>}
    </>
  );
};

/** 그 점에서 실제로 보이는 맨 위 요소(숨김 · 투명은 건너뜀) */
const visibleAt = (X: number, Y: number): HTMLElement | null => {
  const doc = frameDoc(); if (!doc) return null;
  const win = doc.defaultView!;
  for (const e of doc.elementsFromPoint(X, Y) as HTMLElement[]) {
    let a = 1, ok = true;
    for (let c: HTMLElement | null = e; c && c !== doc.body; c = c.parentElement) {
      const cs = win.getComputedStyle(c);
      if (cs.visibility === "hidden" || cs.display === "none") { ok = false; break; }
      a *= parseFloat(cs.opacity || "1"); if (a < 0.05) { ok = false; break; }
    }
    if (ok && e.id !== "root") return e;
  }
  return null;
};

/** 짚기 겹: 누른 자리 → 에이전트 맥락(장면 · 시각 · 위치 · 요소 이름). 화면을 바꾸지는 않는다 */
const PointLayer: React.FC<{ sb: Storyboard; S: number }> = ({ sb, S }) => {
  const pick = useStudio((s) => s.pick);
  const onDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.round((e.clientX - r.left) / S), y = Math.round((e.clientY - r.top) / S);
    clock.pause();
    const at = clock.t, scene = sceneAt(startsOf(sb), sb, at);
    const el = visibleAt(x, y);
    const label = el ? describe(el) : "";
    useStudio.getState().set({ pick: { t: at, scene, x, y, label }, scene });
    toast(label ? t("짚었어요 · 장면 {n} · {s}초 · “{label}”", { n: scene + 1, s: at.toFixed(1), label }) : t("짚었어요 · 장면 {n} · {s}초", { n: scene + 1, s: at.toFixed(1) }), { description: t("오른쪽 채팅에 어떻게 바꿀지 말해 주세요") });
  };
  return (
    <div className="ovl" onPointerDown={onDown} style={{ cursor: "crosshair" }}>
      {pick && <span className="pick-dot" style={{ left: pick.x * S, top: pick.y * S }} aria-hidden />}
    </div>
  );
};

/** 쇼츠 화면 가이드: 유튜브 쇼츠 · 릴스 UI가 덮는 곳(K.talk SAFE 와 같은 값) */
const SafeGuide: React.FC<{ S: number }> = ({ S }) => {
  const zones = [{ x: 0, y: 0, w: 1080, h: 220, t: "상단 바" }, { x: 936, y: 880, w: 144, h: 660, t: "버튼" }, { x: 0, y: 1540, w: 1080, h: 380, t: "채널 · 제목 · 설명" }];
  return <>{zones.map((z) => <div key={z.t} className="zone" style={{ left: z.x * S, top: z.y * S, width: z.w * S, height: z.h * S }}><span>{t(z.t)}</span></div>)}
    <div className="safe" style={{ left: 72 * S, top: 220 * S, width: 864 * S, height: 1320 * S }}><span>{t("안전 영역")}</span></div></>;
};

/* ---------- HTML 이 아닌 엔진: 초안 영상 ---------- */
const DraftPreview: React.FC<{ projectId: string; engine: EngineMeta | null; PW: number; PH: number }> = ({ projectId, engine, PW, PH }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { const r = await fetch(`/api/projects/${projectId}/draft`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ engine: engine?.name }) }); const d = await r.json(); if (!r.ok) throw new Error(d?.error?.message ?? t("초안 렌더 실패")); setUrl(d.url); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="frame-wrap" style={{ width: PW }}>
      <div className="frame frame-deck" style={{ width: PW, height: PH }}>
        {url ? <video src={url} controls loop playsInline style={{ width: PW, height: PH }} /> :
          <EmptyState icon="video" title={engine?.title ?? engine?.name ? t("{name}은 렌더해서 미리 봅니다", { name: (engine?.title ?? engine?.name)! }) : t("이 엔진은 렌더해서 미리 봅니다")} body={t("초안(540×960)을 빠르게 렌더해 보여 줍니다.")}
            action={<Button variant="primary" loading={busy} onClick={run}>{t("초안 렌더")}</Button>} />}
      </div>
    </div>
  );
};
