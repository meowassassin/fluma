/* 영상 화면: 위 머리 · 가운데 미리보기 · 아래 타임라인 · 오른쪽 에이전트(채팅).
   편집은 채팅으로 통일했다(2026-11-02) — 화면을 눌러 자리를 짚거나 타임라인에서 장면을 고르면 그 맥락이 채팅에 붙는다. */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { PanelBoundary } from "../../shell/ErrorBoundary";
import { AgentDock } from "../agent/AgentDock";
import { Icon } from "../../ui/Icon";
import { clock } from "../../lib/clock";
import { qc, qk, useEngines, useHasAudio, useStoryboard } from "../../lib/queries";
import { onTurnEnd } from "../../lib/agent";
import { attachJobs, startRender } from "../../lib/jobs";
import { typing, useUi } from "../../lib/ui";
import type { ChatContext } from "../../lib/types";
import { TopBar } from "./TopBar";
import { t } from "../../lib/i18n";
import { Preview } from "./Preview";
import { EditorArea, Explorer, StatusBar, useOrganic, useTree, type Node } from "./ProjectTree";
import { sceneAt, startsOf, totalOf, uploadAll, useStudio } from "./store";

export const StudioPage: React.FC = () => {
  const { id = "" } = useParams();
  const loc = useLocation();
  const nav = useNavigate();
  const [autoSend, setAutoSend] = useState<{ message: string; skill?: string | null } | null>(() => (loc.state as { autoSend?: { message: string; skill?: string } } | null)?.autoSend ?? null);
  useEffect(() => { if (loc.state) nav(loc.pathname, { replace: true, state: null }); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    useStudio.getState().reset(id); clock.reset(); useUi.getState().set({ lastProject: id }); attachJobs(id);
    return () => clock.pause();
  }, [id]);

  const sbQ = useStoryboard(id);
  const sb = sbQ.data ?? null;
  const missing = (sbQ.error as { status?: number } | null)?.status === 404;
  const { data: engines = [] } = useEngines();
  const engineName = sb?.engine || "hyperframes";
  const engine = engines.find((e) => e.name === engineName) ?? (engines.length ? null : { name: "hyperframes", preview: "html" as const, available: true, templates: [] });
  const starts = useMemo(() => startsOf(sb), [sb]);
  useEffect(() => { clock.setDuration(totalOf(sb)); }, [sb]);

  // 소리: 재생 시계가 소리를 기준으로 맞춘다
  const { data: audioVer } = useHasAudio(id);
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => { clock.audio = audio.current; return () => { clock.audio = null; }; }, [audioVer]);

  // 에이전트가 이 영상 파일을 고치고 턴을 마치면 다시 읽는다
  useEffect(() => onTurnEnd((sid) => {
    if (sid !== id) return;
    for (const k of [qk.storyboard(id), qk.lint(id), qk.audio(id), qk.elements(id), qk.uploads(id)]) qc.invalidateQueries({ queryKey: k });
    qc.invalidateQueries({ queryKey: ["gate", id] });
  }), [id]);

  // 단축키 — 보기 · 오가기만(편집은 채팅). 키 위치(e.code) 기준이라 한글 입력 상태에서도 동작
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e)) return;
      if (e.code === "Space" && (e.target as HTMLElement | null)?.closest?.("button, [role=button]")) { e.preventDefault(); clock.toggle(); return; }
      const fps = 30, total = clock.duration;
      switch (e.code) {
        case "Space": e.preventDefault(); clock.toggle(); break;
        case "ArrowLeft": e.preventDefault(); e.shiftKey ? (clock.pause(), clock.seek(clock.t - 1)) : clock.step(-1, fps); break;
        case "ArrowRight": e.preventDefault(); e.shiftKey ? (clock.pause(), clock.seek(clock.t + 1)) : clock.step(1, fps); break;
        case "Home": e.preventDefault(); clock.seek(0); break;
        case "End": e.preventDefault(); clock.seek(total - 0.02); break;
        case "BracketLeft": case "BracketRight": {
          if (!sb) break; const i = sceneAt(starts, sb, clock.t); const j = Math.max(0, Math.min(sb.scenes.length - 1, i + (e.code === "BracketLeft" ? -1 : 1)));
          clock.pause(); clock.seek(starts[j] + 0.05); useStudio.getState().set({ scene: j, pick: null }); break;
        }
        case "KeyG": useStudio.getState().set({ guide: !useStudio.getState().guide }); break;
        case "KeyR": if (sb) startRender(id, sb.title); break;
        case "Escape": useStudio.getState().set({ pick: null, scene: null }); break;
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [id, sb, starts]);

  // 짚은 자리 · 고른 장면 → 에이전트 맥락
  const pick = useStudio((s) => s.pick), scene = useStudio((s) => s.scene);
  const chip = pick ? { label: `${t("장면 {n} · {s}초", { n: pick.scene + 1, s: pick.t.toFixed(1) })} · (${pick.x}, ${pick.y})${pick.label ? ` · ${pick.label}` : ""}`, onClear: () => useStudio.getState().set({ pick: null }) }
    : scene != null && sb?.scenes[scene] ? { label: `${t("장면 {n}", { n: scene + 1 })} · ${sb.scenes[scene].caption.split("\n")[0]}`, onClear: () => useStudio.getState().set({ scene: null }) } : null;
  const context = (): ChatContext => ({ menu: "studio", selection: [chip?.label, active && active.kind !== "preview" ? `편집 대상: ${active.label}${active.app ? ` (${active.app}${active.stage ? ` · ${active.stage}` : ""})` : ""}` : null].filter(Boolean).join(" · ") || undefined,
    note: sb ? `재생 위치 ${clock.t.toFixed(1)}초${pick ? ` · 사용자가 화면의 (${pick.x}, ${pick.y}) / 1080×1920 을 짚음${pick.label ? ` — 그 자리 요소 "${pick.label}"` : ""}` : ""}${sb.template === "Composed" ? ` · 화면 구성 compositions/${sb.id}/scene.js` : ""} · 편집은 채팅으로만(손 편집 도구 없음): 요청을 반영하고 그 시각 정지 화면으로 확인` : "새 영상" });

  const [drop, setDrop] = useState(false);
  // 통합 편집기: 트리에서 고른 항목 → 가운데 편집 툴. 기본은 컷 편집(FilmCraft)이 있으면 그것, 없으면 Fluma 미리보기
  const tree = useTree(id, sb);
  const rebuilding = useOrganic(id);
  // 탐색기 접기(VS Code 처럼 Ctrl+B) — 편집 툴을 넓게
  const [explorerOpen, setExplorerOpen] = useState(true);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.code === "KeyB" && !typing(e)) { e.preventDefault(); setExplorerOpen((v) => !v); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  // 열린 편집 탭(VS Code 처럼) — 처음엔 컷 편집(없으면 미리보기) 하나
  const [tabKeys, setTabKeys] = useState<string[]>([]);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  useEffect(() => { setTabKeys([]); setActiveKey(null); }, [id]);
  const first: Node | null = tree.top ?? null;
  const tabs = (tabKeys.length ? tabKeys : first ? [first.key] : []).map((k) => tree.all.find((n) => n.key === k)).filter(Boolean) as Node[];
  const active: Node | null = tabs.find((n) => n.key === activeKey) ?? tabs[0] ?? null;
  const openNode = (n: Node) => {
    setTabKeys((ks) => { const base = ks.length ? ks : first ? [first.key] : []; return base.includes(n.key) ? base : [...base, n.key]; });
    setActiveKey(n.key); if (n.scene != null) useStudio.getState().set({ scene: n.scene, pick: null });
  };
  const closeTab = (n: Node) => {
    const ks = tabs.map((x) => x.key).filter((k) => k !== n.key);
    setTabKeys(ks); if (active?.key === n.key) setActiveKey(ks[ks.length - 1] ?? null);
  };
  return (
    <div className={`studio ${sb ? "" : "no-sb"}`}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDrop(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDrop(false); }}
      onDrop={(e) => { e.preventDefault(); setDrop(false); const fs = [...e.dataTransfer.files].filter((f) => /^(image|video)\//.test(f.type)); if (fs.length) uploadAll(id, fs); }}>
      <TopBar sb={sb} projectId={id} />
      <div className="studio-body">
        {sb && explorerOpen && <PanelBoundary name="탐색기"><Explorer sb={sb} tree={tree} active={active?.key ?? ""} onOpen={openNode} /></PanelBoundary>}
        <div className="studio-work">
          {sb ? <EditorArea projectId={id} sb={sb} tabs={tabs} active={active} onOpen={openNode} onClose={closeTab}
            preview={<PanelBoundary name="미리보기"><Preview sb={sb} projectId={id} engine={engine as never} loading={sbQ.isLoading} missing={missing} /></PanelBoundary>} />
            : <div className="studio-mid"><PanelBoundary name="미리보기"><Preview sb={sb} projectId={id} engine={engine as never} loading={sbQ.isLoading} missing={missing} /></PanelBoundary></div>}
        </div>
        <PanelBoundary name="에이전트">
          <AgentDock sessionId={id} chip={chip} context={context}
            autoSend={autoSend} onAutoSent={() => setAutoSend(null)}
            hints={sb ? [t("검사 통과할 때까지 고쳐 줘"), t("짚은 거 더 크게"), t("장면 2 말투만 바꿔 줘")] : [t("무료 TTS 3개 비교, 25초. 조사부터 해 줘")]}
            placeholder={sb ? t("예: 이 장면 짤 바꿔 줘 · 자막 크게 · 말투만 더 담담하게") : t("만들 영상을 말해 주세요")} />
        </PanelBoundary>
      </div>
      {sb && <StatusBar sb={sb} tree={tree} active={active} rebuilding={rebuilding} explorerOpen={explorerOpen} onToggleExplorer={() => setExplorerOpen((v) => !v)} />}
      {audioVer && <audio ref={audio} src={`/api/public/audio/${id}.wav?v=${encodeURIComponent(String(audioVer))}`} preload="auto" />}
      {drop && <div className="drop-veil"><div><Icon n="upload" s={22} /><b>{t("여기에 놓으면 이 영상의 에셋으로 올라갑니다")}</b><span className="faint">{t("사진 · 실사 영상 — 채팅으로 어디에 쓸지 말해 주세요")}</span></div></div>}
    </div>
  );
};
