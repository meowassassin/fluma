/* 영상 편집기 — 타임라인 NLE 편집과 AI 에이전트 Copilot 의 통합 화면.
   - 프로젝트 저장 위치: data/compositions/<id>/editor/project.json
   - 미디어 소스: 클립, 나레이션 음성, 효과음
   - 내보낸 MP4: data/compositions/<id>/editor/exported.mp4 및 data/out/<id>-editor.mp4 (최종본)
   - AI 에이전트: 타임라인 우측에 AgentDock 도킹 (Cmd+J 로 열기/닫기 토글) */

import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  VideoEditor,
  EditorCore,
  mediaTimeToSeconds,
  mediaTimeFromSeconds,
  type EditorExtraPanel,
  type TimelineElement,
} from "../../vendor/artcraft/video-editor/src";
import { createFlumaAdapters, flumaMediaUrl, flumaToast } from "./adapters/fluma-adapters";
import { createCraftEffectProvider } from "./craftFx";
import { AgentDock } from "../agent/AgentDock";
import { PipelineGraph } from "../videos/PipelineGraph";
import { onTurnEnd } from "../../lib/agent";
import { useUi } from "../../lib/ui";
import { FlumaGlyph } from "../../ui/BrandIcons";
import { t } from "../../lib/i18n";
import { startEditorTranslation } from "./editorI18n";
import "./veditor.css";

const KIND_KO: Record<string, string> = {
  video: "영상",
  image: "이미지",
  text: "자막·텍스트",
  audio: "오디오",
  sticker: "스티커",
  graphic: "도형",
  effect: "효과",
};

interface SelectedSummary {
  chipLabel: string;
  selectionText: string;
  detailNote: string;
}

function summarizeSelection(): SelectedSummary | null {
  const ed = EditorCore.getInstance();
  const refs = ed.selection.getSelectedElements();
  if (!refs.length) return null;
  const resolved = ed.timeline.getElementsWithTracks({ elements: refs });
  if (!resolved.length) return null;

  if (resolved.length === 1) {
    const { element, track } = resolved[0];
    const kind = KIND_KO[element.type] ?? element.type;
    const startSec = mediaTimeToSeconds({ time: element.startTime }).toFixed(2);
    const durSec = mediaTimeToSeconds({ time: element.duration }).toFixed(2);
    const params = ((element as unknown as { params?: Record<string, unknown> }).params ?? {});
    const textContent = typeof params.content === "string" ? params.content : "";
    const mediaId = (element as unknown as { mediaId?: string }).mediaId;
    const mediaSrc = mediaId ? flumaMediaUrl(mediaId) : null;
    const label = `${kind} · ${element.name} (${startSec}s~${(Number(startSec) + Number(durSec)).toFixed(2)}s)`;
    const extra = [
      `elementId=${element.id}`,
      `trackId=${track.id}`,
      `type=${element.type}`,
      `start=${startSec}s`,
      `duration=${durSec}s`,
      textContent ? `text=${JSON.stringify(textContent)}` : null,
      mediaSrc ? `mediaUrl=${mediaSrc}` : null,
    ].filter(Boolean).join(", ");
    return {
      chipLabel: label,
      selectionText: `${label} [${extra}]`,
      detailNote: `선택된 타임라인 요소: ${label} (${extra})`,
    };
  }

  const names = resolved.slice(0, 4).map(({ element }) => `${KIND_KO[element.type] ?? element.type}:${element.name}`).join(", ");
  const label = `${resolved.length}개 타임라인 요소 (${names}${resolved.length > 4 ? "…" : ""})`;
  const ids = resolved.map(({ element, track }) => `${track.id}/${element.id}(${element.type})`).join(", ");
  return {
    chipLabel: label,
    selectionText: `${label} [${ids}]`,
    detailNote: `선택된 타임라인 요소들: ${ids}`,
  };
}

/** 왼쪽 레일 '파이프라인' 아이콘 — 단계 셋이 이어진 모양 */
const PipeIcon = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="1" y="6" width="4" height="4" rx="1" /><rect x="11" y="2" width="4" height="4" rx="1" /><rect x="11" y="10" width="4" height="4" rx="1" />
    <path d="M5 8h3M8 4v8M8 4h3M8 12h3" />
  </svg>
);

export const VEditorPage: React.FC = () => {
  const { id = "test-char-01" } = useParams<{ id: string }>();
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loadingMsg, setLoadingMsg] = useState("타임라인을 준비하는 중…");
  const [selectedSummary, setSelectedSummary] = useState<SelectedSummary | null>(null);
  const agentOpen = useUi((s) => s.agentOpen);

  const adapters = useMemo(() => createFlumaAdapters(id), [id]);
  const effectProvider = useMemo(() => createCraftEffectProvider(id), [id]);
  const extraPanels = useMemo<EditorExtraPanel[]>(() => [
    {
      id: "fluma-pipeline",
      label: t("파이프라인"),
      icon: <PipeIcon />,
      render: () => <div className="ve-pipe-panel"><PipelineGraph id={id} variant="panel" /></div>,
    },
  ], [id]);

  useEffect(() => {
    document.body.classList.add("ve-root");
    let active = true;
    setReady(false); setFailed(null);

    async function init() {
      try {
        EditorCore.reset();
        EditorCore.initialize({ adapters });
        const ed = EditorCore.getInstance();
        setLoadingMsg("프로젝트 및 미디어를 불러오는 중…");
        // 서버는 편집기 프로젝트가 없으면 Craft 초안에서 만들어 준다 — 그래서 '없음'은 곧 실패.
        // 실패했을 때 빈 프로젝트를 띄우면 자동 저장이 진짜 프로젝트를 덮어쓴다(2026-11-12 실제로 일어남) → 오류 화면 + 다시 시도
        const loaded = await ed.project.openProject({ id });
        if (!active) return;
        if (!loaded) {
          ed.save.stop();
          setFailed("프로젝트를 불러오지 못했습니다. 저장된 파일은 그대로 있습니다.");
          return;
        }
        setReady(true);
      } catch (err) {
        console.error("VEditor init error:", err);
        if (active) setFailed(err instanceof Error ? err.message : String(err));
      }
    }

    init();

    return () => {
      active = false;
      document.body.classList.remove("ve-root");
    };
  }, [id, adapters, attempt]);

  useEffect(() => {
    if (!ready) return;
    const ed = EditorCore.getInstance();
    const syncSelection = () => {
      setSelectedSummary(summarizeSelection());
    };
    syncSelection();
    const unsubSel = ed.selection.subscribe(syncSelection);
    const unsubTl = ed.timeline.subscribe(syncSelection);
    return () => {
      unsubSel();
      unsubTl();
    };
  }, [ready]);

  // 에이전트 턴이 끝났을 때 타임라인/클립/오디오 관련 파일이 바뀌었으면 편집기 프로젝트를 즉시 다시 불러와 반영
  useEffect(() => {
    if (!ready) return;
    return onTurnEnd((turnSessionId, files) => {
      if (turnSessionId !== id || !files.length) return;
      const shouldReload = files.some((f) =>
        f.path.includes(`compositions/${id}/editor/project.json`) ||
        f.path.includes(`compositions/${id}/clips/`) ||
        f.path.includes(`compositions/${id}/keyframes/`) ||
        f.path.includes(`compositions/${id}/craft/`) ||
        f.path.includes(`audio/${id}`) ||
        f.path.includes(`storyboards/${id}.json`),
      );
      if (!shouldReload) return;
      const ed = EditorCore.getInstance();
      const prevTime = ed.playback.getCurrentTime();
      void ed.project.openProject({ id }).then((ok) => {
        if (ok) {
          ed.playback.seek({ time: prevTime });
          flumaToast.info(t("에이전트의 편집 내역을 타임라인에 반영했습니다"));
        }
      });
    });
  }, [id, ready]);

  // 편집기 화면 글(ArtCraft 영어 원문) → 한국어 · 앱 언어 (editorI18n.ts)
  useEffect(() => startEditorTranslation(), []);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.code === "KeyJ") {
        e.preventDefault();
        useUi.getState().set({ agentOpen: !useUi.getState().agentOpen });
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  if (failed) {
    return (
      <div className="ve-page ve-loading" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#111", color: "#eee", fontFamily: "Pretendard, sans-serif" }}>
        <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
          <div style={{ fontSize: "1.05rem" }}>{failed}</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => setAttempt((n) => n + 1)} style={{ height: 32, padding: "0 14px", borderRadius: 8, border: 0, background: "#5850f8", color: "#fff", cursor: "pointer" }}>{t("다시 시도")}</button>
            <a href="/videos" style={{ height: 32, lineHeight: "32px", padding: "0 14px", borderRadius: 8, background: "#2d2d2d", color: "#eee", textDecoration: "none" }}>{t("영상 목록")}</a>
          </div>
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="ve-page ve-loading" style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", background: "#111", color: "#eee", fontFamily: "Pretendard, sans-serif" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "1.2rem", marginBottom: "0.5rem" }}>{loadingMsg}</div>
          <div style={{ fontSize: "0.85rem", opacity: 0.6 }}>Fluma 영상 편집기</div>
        </div>
      </div>
    );
  }

  return (
    <div className="ve-page">
      <div className="flex-1 min-w-0 h-full relative flex flex-col">
        <VideoEditor
          adapters={adapters}
          effectProvider={effectProvider}
          exitTo="/videos"
          extraPanels={extraPanels}
          headerEndSlot={<AgentToggle />}
        />
      </div>
      {agentOpen && (
        <div data-ve-no-tr style={{ display: "contents" }}>{/* 에이전트 대화는 번역하지 않는다 */}
        <AgentDock
          sessionId={id}
          layout="dock"
          title={t("AI 에이전트")}
          chip={
            selectedSummary
              ? {
                  label: selectedSummary.chipLabel,
                  onClear: () => EditorCore.getInstance().selection.clearSelection(),
                }
              : null
          }
          context={() => {
            const ed = EditorCore.getInstance();
            const playheadSec = mediaTimeToSeconds({ time: ed.playback.getCurrentTime() }).toFixed(2);
            const totalSec = mediaTimeToSeconds({ time: ed.timeline.getTotalDuration() }).toFixed(2);
            const curSel = summarizeSelection();
            return {
              menu: "studio",
              selection: curSel?.selectionText,
              note: [
                `사용자가 영상 편집기(VEditor)에서 프로젝트 '${id}'를 편집 중입니다.`,
                `현재 재생 헤드 위치: ${playheadSec}s / 전체 길이 ${totalSec}s.`,
                curSel ? curSel.detailNote : "현재 선택된 타임라인 클립/자막 없음.",
                "클립 자르기, 자막 수정, 나레이션 오디오 조정 및 샷 재생성 지시를 처리할 수 있습니다.",
              ].join(" "),
            };
          }}
          hints={[
            t("자막 폰트 및 스타일 변경해줘"),
            t("나레이션 볼륨 키우고 BGM 줄여줘"),
            t("2번 샷 클립 재생성해줘"),
            t("앞부분 2초 잘라내줘"),
          ]}
        />
        </div>
      )}
    </div>
  );
};

/** 머리줄 오른쪽: AI 에이전트 패널 켜고 끄기(⌘J) — 닫은 상태가 저장되므로 다시 여는 버튼이 늘 보여야 한다 */
const AgentToggle: React.FC = () => {
  const open = useUi((s) => s.agentOpen);
  return (
    <button type="button" onClick={() => useUi.getState().set({ agentOpen: !open })} aria-pressed={open}
      title={open ? t("AI 에이전트 패널 닫기 (⌘J)") : t("AI 에이전트 패널 열기 (⌘J)")}
      className={`flex items-center gap-1.5 h-8 px-2.5 rounded-md text-xs font-semibold border ${open ? "bg-primary/15 border-primary/50 text-foreground" : "bg-muted border-border text-muted-foreground hover:text-foreground"}`}>
      <FlumaGlyph s={16} tone="color" />
      <span>{t("AI 에이전트")}</span>
    </button>
  );
};
