import React, { useState, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, Dialog, IconButton, Skeleton, cx } from "../../ui/kit";
import { t } from "../../lib/i18n";
import type { PresetItem } from "../library/LibraryPage";
import "./automation.css";

interface VerifyResult {
  requestedCount: number;
  maxViable: number;
  feasible: boolean;
  breakdown: {
    antigravityTokens?: { needed: number; available: number; ok: boolean };
    veoCredits?: { needed: number; available: number; ok: boolean };
    youtubeDailyQuota?: {
      neededUnits: number;
      dailyLimit: number;
      costPerVideo: number;
      maxVideosPerDay: number;
      ok: boolean;
    };
    hasYouTubeToken?: boolean;
  };
  warnings?: string[];
}

interface AutomationHistoryItem {
  id?: string;
  batchId?: string;
  triggeredAt?: string;
  date?: string;
  presetId?: string;
  videoCount?: number;
  topicsCount?: number;
  topics?: string[];
  schedule?: {
    startDate?: string;
    interval?: string;
    publishTime?: string;
    autoPublish?: boolean;
  };
  status?: string;
}

type NodeType = "trigger" | "preset" | "ai" | "veo" | "timeline" | "youtube";

interface WorkflowNodeDef {
  id: NodeType;
  step: string;
  shortLabel: string;
  title: string;
  category: string;
  subtitle: string;
  icon: string;
  badgeColor: string;
  x: number;
  y: number;
}

const NODE_W = 196;
const NODE_H = 92;

const NODES: WorkflowNodeDef[] = [
  { id: "trigger", step: "01", shortLabel: "트리거", title: "스케줄 & 주제", category: "Trigger", subtitle: "주기 · 주제 대기열 설정", icon: "clock", badgeColor: "#f59e0b", x: 24, y: 36 },
  { id: "preset", step: "02", shortLabel: "프리셋", title: "시리즈 프리셋", category: "Assets", subtitle: "캐릭터 · 화풍 바인딩", icon: "library", badgeColor: "#8b5cf6", x: 264, y: 36 },
  { id: "ai", step: "03", shortLabel: "샷 기획", title: "4박자 샷 기획", category: "Planning", subtitle: "Hook-Build-Turn-Payoff", icon: "sparkle", badgeColor: "#06b6d4", x: 504, y: 36 },
  { id: "veo", step: "04", shortLabel: "영상 생성", title: "키프레임 & Veo 영상", category: "Generation", subtitle: "캐릭터 시트 · Veo 3.1 I2V", icon: "video", badgeColor: "#ec4899", x: 24, y: 184 },
  { id: "timeline", step: "05", shortLabel: "타임라인", title: "타임라인 · 자막 합성", category: "Assembly", subtitle: "TTS · SFX 믹스 · 상단 타이틀", icon: "render", badgeColor: "#3b82f6", x: 264, y: 184 },
  { id: "youtube", step: "06", shortLabel: "예약 배포", title: "YouTube 예약 발행", category: "Publish", subtitle: "publishAt 순차 예약", icon: "upload", badgeColor: "#ef4444", x: 504, y: 184 },
];

export const AutomationPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialPreset = searchParams.get("preset") || "pin-daily-curiosity";
  const qc = useQueryClient();
  const canvasRef = useRef<HTMLDivElement>(null);

  const [selectedNodeId, setSelectedNodeId] = useState<NodeType | null>("trigger");
  const [showHistoryDrawer, setShowHistoryDrawer] = useState(false);
  const [showN8nConfigModal, setShowN8nConfigModal] = useState(false);
  const [executingStep, setExecutingStep] = useState<number>(-1);

  // Form State
  const [selectedPresetId, setSelectedPresetId] = useState<string>(initialPreset);
  const [topicMode, setTopicMode] = useState<"theme" | "list">("theme");
  const [themeInput, setThemeInput] = useState("");
  const [listInput, setListInput] = useState("");
  const [videoCount, setVideoCount] = useState<number>(3);

  // Scheduling State
  const todayStr = new Date().toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState(todayStr);
  const [scheduleInterval, setScheduleInterval] = useState<string>("1h");
  const [publishTime, setPublishTime] = useState("18:00");
  const [autoPublish, setAutoPublish] = useState(false);

  // n8n Connection Config State
  const [n8nHost, setN8nHost] = useState("http://localhost:5678");
  const [n8nApiKey, setN8nApiKey] = useState("");
  const [n8nWorkflowId, setN8nWorkflowId] = useState("");

  // Feasibility Check
  const [verifyData, setVerifyData] = useState<VerifyResult | null>(null);

  // 1. n8n Status Query
  const { data: n8nStatus, refetch: refetchN8nStatus } = useQuery({
    queryKey: ["n8n-status"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/n8n/status");
        if (!res.ok) return { connected: false };
        return res.json();
      } catch {
        return { connected: false };
      }
    },
    refetchInterval: 8000,
  });

  // 2. n8n Config Query
  useQuery({
    queryKey: ["n8n-config"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/n8n/config");
        if (!res.ok) return {};
        const data = await res.json();
        if (data.host) setN8nHost(data.host);
        if (data.workflowId) setN8nWorkflowId(data.workflowId);
        if (data.schedule) {
          if (data.schedule.interval) setScheduleInterval(data.schedule.interval);
          if (data.schedule.publishTime) setPublishTime(data.schedule.publishTime);
          if (typeof data.schedule.autoPublish === "boolean") setAutoPublish(data.schedule.autoPublish);
          if (data.schedule.videoCount) setVideoCount(Number(data.schedule.videoCount));
          if (data.schedule.presetId !== undefined) setSelectedPresetId(data.schedule.presetId);
        }
        return data;
      } catch {
        return {};
      }
    },
  });

  // 3. Presets Query
  const { data: presetData } = useQuery<any>({
    queryKey: ["library-presets"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/library/presets");
        if (!res.ok) return { presets: [] };
        return res.json();
      } catch {
        return { presets: [] };
      }
    },
  });

  // 4. History Query
  const { data: historyData, isLoading: loadingHistory } = useQuery<any>({
    queryKey: ["automation-history"],
    queryFn: async () => {
      try {
        const res = await fetch("/api/automation/history");
        if (!res.ok) return { history: [] };
        return res.json();
      } catch {
        return { history: [] };
      }
    },
    refetchInterval: 5000,
  });

  const presets: PresetItem[] = Array.isArray(presetData) ? presetData : (presetData?.presets ?? []);
  const history: AutomationHistoryItem[] = Array.isArray(historyData) ? historyData : (historyData?.history ?? []);
  const currentPreset = presets.find((p) => p.id === selectedPresetId);

  const isConnected = !!n8nStatus?.connected;
  const isWorkflowActive = !!n8nStatus?.active;

  // Verify Resource Quota
  const runVerify = async (count: number) => {
    try {
      const res = await fetch("/api/automation/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count }),
      });
      if (!res.ok) throw new Error("검증 실패");
      const data = await res.json();
      if (data && data.breakdown) {
        setVerifyData(data);
      }
    } catch {
      setVerifyData({
        requestedCount: count,
        maxViable: Math.min(count, 6),
        feasible: count <= 6,
        breakdown: {
          veoCredits: { needed: count * 4, available: 100, ok: true },
          antigravityTokens: { needed: count * 15000, available: 1000000, ok: true },
          youtubeDailyQuota: {
            neededUnits: count * 1600,
            dailyLimit: 10000,
            costPerVideo: 1600,
            maxVideosPerDay: 6,
            ok: count <= 6,
          },
        },
        warnings: count > 6 ? ["유튜브 일일 업로드 쿼터(10,000점) 제한으로 안전한 생성 권장 편수는 최대 6편입니다."] : [],
      });
    }
  };

  useEffect(() => {
    runVerify(videoCount);
  }, [videoCount]);

  // Sync to n8n Mutation
  const syncMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        workflowId: n8nWorkflowId || n8nStatus?.workflow?.id,
        schedule: {
          startDate,
          interval: scheduleInterval,
          publishTime,
          autoPublish,
          topics: topicMode === "theme" ? [themeInput].filter(Boolean) : listInput.split("\n").filter(Boolean),
          videoCount,
          presetId: selectedPresetId,
        },
      };
      const res = await fetch("/api/n8n/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "동기화 실패");
      return data;
    },
    onSuccess: (data) => {
      if (data.localOnly) {
        toast.success(t("워크플로 설정이 저장되었습니다."));
      } else {
        toast.success(t("n8n 워크플로 노드 설정이 실시간 동기화되었습니다."));
      }
      refetchN8nStatus();
    },
    onError: (err: any) => {
      toast.error(err.message || "동기화 실패");
    },
  });

  // Activate / Deactivate Toggle Mutation
  const toggleActiveMutation = useMutation({
    mutationFn: async (active: boolean) => {
      const res = await fetch("/api/n8n/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active }),
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "상태 변경 실패");
      return data;
    },
    onSuccess: (data) => {
      toast.success(data.active ? t("자동화 스케줄러가 활성화(Active)되었습니다.") : t("자동화 스케줄러가 비활성화(Inactive)되었습니다."));
      refetchN8nStatus();
    },
    onError: (err: any) => {
      toast.error(err.message);
    },
  });

  // One-Click Deploy to n8n Mutation
  const deployMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/n8n/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflowName: "Phantasos 유튜브 쇼츠 자동화 파이프라인" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "배포 실패");
      return data;
    },
    onSuccess: (data) => {
      setN8nWorkflowId(data.workflowId);
      toast.success(t("n8n에 Phantasos 공식 워크플로가 설치되었습니다. (ID: {id})", { id: data.workflowId }));
      refetchN8nStatus();
      setShowN8nConfigModal(false);
    },
    onError: (err: any) => {
      toast.error(err.message);
    },
  });

  // Clear History Mutation
  const clearHistoryMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/automation/history", { method: "DELETE" });
      if (!res.ok) throw new Error("기록 삭제 실패");
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["automation-history"] });
      toast.success(t("자동화 실행 기록을 비웠습니다."));
    },
  });

  // Execute Workflow Mutation
  const triggerMutation = useMutation({
    mutationFn: async () => {
      let finalTopics: string[] = [];
      if (topicMode === "theme") {
        if (!themeInput.trim()) throw new Error("메인 테마 주제를 입력해 주세요.");
        finalTopics = [themeInput.trim()];
      } else {
        finalTopics = listInput
          .split("\n")
          .map((s) => s.trim().replace(/^\d+[\.\)]\s*/, ""))
          .filter(Boolean);
        if (finalTopics.length === 0) throw new Error("하나 이상의 소주제를 입력해 주세요.");
      }

      setExecutingStep(0);
      for (let i = 1; i <= 5; i++) {
        await new Promise((r) => setTimeout(r, 380));
        setExecutingStep(i);
      }

      const payload = {
        n8nWebhookUrl: `${n8nHost}/webhook/phantasos-automation`,
        presetId: selectedPresetId || undefined,
        presetName: currentPreset?.name || "자유 주제",
        characterId: (currentPreset as any)?.character || currentPreset?.characterId,
        style: currentPreset?.style,
        topics: finalTopics,
        count: topicMode === "list" ? finalTopics.length : videoCount,
        schedule: {
          startDate,
          interval: scheduleInterval,
          publishTime,
          autoPublish,
        },
      };

      const res = await fetch("/api/automation/trigger-n8n", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const resData = await res.json();
      if (!res.ok) throw new Error(resData.error || "트리거 실패");
      return resData;
    },
    onSuccess: (data) => {
      toast.success(t("자동화 파이프라인이 실행 대기열에 등록되었습니다. (배치 ID: {id})", { id: data.batchId }));
      qc.invalidateQueries({ queryKey: ["automation-history"] });
      setTimeout(() => setExecutingStep(-1), 2000);
    },
    onError: (err: any) => {
      toast.error(err.message || "실행 오류");
      setExecutingStep(-1);
    },
  });

  const getIntervalLabel = (val: string) => {
    switch (val) {
      case "30m": return t("30분 간격");
      case "1h": return t("1시간 간격");
      case "2h": return t("2시간 간격");
      case "3h": return t("3시간 간격");
      case "6h": return t("6시간 간격");
      case "12h": return t("12시간 간격");
      case "1d": return t("매일 1회");
      case "2d": return t("2일 간격");
      case "3d": return t("3일 간격");
      case "7d": return t("주 1회");
      default: return val;
    }
  };

  const finalCount = useMemo(() => {
    if (topicMode === "list") {
      const n = listInput.split("\n").filter((s) => s.trim().length > 0).length;
      return n > 0 ? n : videoCount;
    }
    return videoCount;
  }, [topicMode, listInput, videoCount]);

  const nodeSubtitles: Record<NodeType, string> = useMemo(() => {
    const presetChar = (currentPreset as any)?.character || currentPreset?.characterId;
    return {
      trigger: `${getIntervalLabel(scheduleInterval)} · ${publishTime} (${finalCount}편)`,
      preset: currentPreset ? `${currentPreset.name}${presetChar ? ` · ${presetChar}` : ""}` : t("프리셋 없음 (자유 생성)"),
      ai: `4박자 인과 구성 · 무음 검증 (${(finalCount * 15000).toLocaleString()} 토큰)`,
      veo: `Veo 3.1 Lite 9:16 · ${finalCount}편 (${finalCount * 40} 크레딧)`,
      timeline: `TTS · Veo SFX 믹스 · 상단 훅 & 하단 자막`,
      youtube: autoPublish ? t("완전 자동 publishAt 예약 등록") : t("초안 검토 후 수동 승인"),
    };
  }, [scheduleInterval, publishTime, finalCount, currentPreset, autoPublish]);

  const selectedIdx = NODES.findIndex((n) => n.id === selectedNodeId);
  const selectedNode = selectedIdx >= 0 ? NODES[selectedIdx] : null;

  return (
    <div className="n8n-wrapper">
      {/* 1. Clean Top Header Bar */}
      <header className="n8n-header">
        <div className="n8n-brand-area">
          <div className="n8n-tag" title="n8n Pipeline">
            <Icon n="n8n" s={15} />
            <span>n8n</span>
          </div>

          <h1 className="n8n-title">{t("쇼츠 자동 제작 & 예약 배포 파이프라인")}</h1>

          <button
            type="button"
            className={cx("n8n-conn-badge", isConnected ? "connected" : "disconnected")}
            onClick={() => setShowN8nConfigModal(true)}
            title={t("n8n 서버 연결 및 API 설정")}
          >
            <i className="status-dot" />
            <span>{isConnected ? t("n8n 연결됨") : t("로컬 모드 (n8n 설정)")}</span>
            <Icon n="gear" s={12} />
          </button>

          <button
            type="button"
            className={cx("toggle-pill", isWorkflowActive ? "is-active" : "is-inactive")}
            onClick={() => toggleActiveMutation.mutate(!isWorkflowActive)}
            title={t("스케줄러 활성화 / 비활성화 전환")}
          >
            <i className="status-indicator" />
            <span>{isWorkflowActive ? t("스케줄러 켜짐") : t("스케줄러 꺼짐")}</span>
          </button>
        </div>

        <div className="n8n-actions">
          <Button
            variant="ghost"
            size="sm"
            icon="history"
            onClick={() => setShowHistoryDrawer(!showHistoryDrawer)}
          >
            {t("실행 내역")}{history.length > 0 ? ` (${history.length})` : ""}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            icon="external"
            onClick={() => window.open(n8nHost, "_blank")}
            title={t("n8n 웹 콘솔 열기")}
          >
            {t("n8n 콘솔")}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            icon="refresh"
            loading={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
            title={t("현재 파라미터를 저장 및 n8n 워크플로에 동기화")}
          >
            {t("설정 동기화")}
          </Button>

          <Button
            variant="primary"
            icon="play"
            size="sm"
            loading={triggerMutation.isPending}
            onClick={() => triggerMutation.mutate()}
            className="n8n-run-btn"
          >
            {t("워크플로 실행")}
          </Button>
        </div>
      </header>

      {/* 2. Main Workspace */}
      <div className="n8n-workspace">
        {/* Canvas Area */}
        <div className="n8n-canvas" ref={canvasRef}>
          {/* Top Canvas HUD Bar: Instructions + Live Resource Quota Chips */}
          <div className="n8n-canvas-hud">
            <div className="canvas-badge">
              <Icon n="sparkle" s={13} />
              <span>{t("노드를 선택해 단계별 옵션을 설정하세요.")}</span>
            </div>

            <div className="n8n-quota-chips">
              <div className="n8n-chip" title={t("예상 AI 기획 토큰")}>
                <Icon n="sparkle" s={12} />
                <span className="chip-label">{t("AI 토큰")}</span>
                <b className="mono">{(verifyData?.breakdown?.antigravityTokens?.needed ?? (finalCount * 15000)).toLocaleString()}</b>
              </div>
              <div className="n8n-chip" title={t("예상 Veo 비디오 생성 크레딧 (샷당 10 크레딧 × 4샷)")}>
                <Icon n="video" s={12} />
                <span className="chip-label">{t("Veo 크레딧")}</span>
                <b className="mono">{finalCount * 40}</b>
              </div>
              <div className={cx("n8n-chip", "yt-chip", finalCount > 6 && "is-warn")} title={t("YouTube Data API v3 일일 업로드 쿼터")}>
                <Icon n="upload" s={12} />
                <span className="chip-label">{t("YT 일일 쿼터")}</span>
                <b className="mono">{(verifyData?.breakdown?.youtubeDailyQuota?.neededUnits ?? (finalCount * 1600)).toLocaleString()}/10,000</b>
                <span className={cx("chip-status", finalCount <= 6 ? "ok" : "warn")}>
                  {finalCount <= 6 ? t("안전") : t("초과 주의")}
                </span>
              </div>
            </div>
          </div>

          {/* Centered 2x3 Pipeline Board */}
          <div className="n8n-canvas-stage">
            <div className="n8n-board">
              <svg className="n8n-connections-svg" viewBox="0 0 724 312">
                <defs>
                  <linearGradient id="n8n-line-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#ff6d5a" />
                  </linearGradient>
                </defs>

                {NODES.map((node, idx) => {
                  if (idx === NODES.length - 1) return null;
                  const nextNode = NODES[idx + 1];
                  let d = "";

                  if (idx === 2) {
                    // Row 1 Col 3 bottom center -> Row 2 Col 1 top center
                    const x1 = node.x + NODE_W / 2;
                    const y1 = node.y + NODE_H;
                    const x2 = nextNode.x + NODE_W / 2;
                    const y2 = nextNode.y;
                    const midY = (y1 + y2) / 2;
                    d = `M ${x1} ${y1} C ${x1} ${midY + 12}, ${x2} ${midY - 12}, ${x2} ${y2}`;
                  } else {
                    const x1 = node.x + NODE_W;
                    const y1 = node.y + NODE_H / 2;
                    const x2 = nextNode.x;
                    const y2 = nextNode.y + NODE_H / 2;
                    const cx1 = x1 + (x2 - x1) * 0.5;
                    const cx2 = x2 - (x2 - x1) * 0.5;
                    d = `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
                  }

                  const isFlowing = executingStep >= idx;
                  return (
                    <g key={`edge-${node.id}-${nextNode.id}`}>
                      <path d={d} className="n8n-wire-back" />
                      <path d={d} className={cx("n8n-wire-front", isFlowing && "flowing")} />
                    </g>
                  );
                })}
              </svg>

              <div className="n8n-nodes-layer">
                {NODES.map((node, idx) => {
                  const isSelected = selectedNodeId === node.id;
                  const isExecuting = executingStep === idx;
                  const isDone = executingStep > idx;

                  return (
                    <div
                      key={node.id}
                      className={cx(
                        "n8n-node-card",
                        isSelected && "selected",
                        isExecuting && "running",
                        isDone && "success"
                      )}
                      style={{ left: node.x, top: node.y, width: NODE_W, height: NODE_H }}
                      onClick={() => setSelectedNodeId(node.id)}
                    >
                      {idx > 0 && idx !== 3 && <span className="n8n-port port-in" />}
                      {idx === 3 && <span className="n8n-port port-in-top" />}

                      <div className="node-head">
                        <div
                          className="node-icon-box"
                          style={{ background: `${node.badgeColor}1f`, color: node.badgeColor }}
                        >
                          <Icon n={node.icon} s={15} />
                        </div>
                        <div className="node-meta">
                          <div className="node-meta-top">
                            <span className="node-step">STEP {node.step}</span>
                            <span className="node-category">{node.category}</span>
                          </div>
                          <h4 className="node-title">{node.title}</h4>
                        </div>
                        {isExecuting && <span className="node-status-spin" />}
                        {isDone && (
                          <span className="node-status-check">
                            <Icon n="check" s={12} />
                          </span>
                        )}
                      </div>

                      <div className="node-body">
                        <p className="node-subtitle">{nodeSubtitles[node.id] || node.subtitle}</p>
                      </div>

                      {idx < NODES.length - 1 && idx !== 2 && <span className="n8n-port port-out" />}
                      {idx === 2 && <span className="n8n-port port-out-bottom" />}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* 3. Right Node Inspector Panel */}
        {selectedNode && (
          <aside className="n8n-side-panel">
            <div className="panel-header">
              <div className="panel-title-group">
                <span className="panel-cat">
                  STEP {selectedNode.step} · {selectedNode.category}
                </span>
                <h3>{selectedNode.title}</h3>
              </div>
              <IconButton
                icon="close"
                label={t("패널 닫기")}
                size="sm"
                onClick={() => setSelectedNodeId(null)}
              />
            </div>

            {/* Quick Step Selector Strip */}
            <div className="panel-step-strip">
              {NODES.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  className={cx("step-pill-btn", selectedNodeId === n.id && "active")}
                  onClick={() => setSelectedNodeId(n.id)}
                >
                  <span className="step-num">{n.step}</span>
                  <span>{n.shortLabel}</span>
                </button>
              ))}
            </div>

            <div className="panel-content">
              {/* 1. Trigger & Schedule Settings */}
              {selectedNodeId === "trigger" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="clock" s={13} />
                      <span>{t("업로드 주기 간격")}</span>
                    </label>
                    <select
                      className="param-select"
                      value={scheduleInterval}
                      onChange={(e) => setScheduleInterval(e.target.value)}
                    >
                      <optgroup label={t("당일 반복 (시간 단위)")}>
                        <option value="30m">{t("30분 간격 (초고속 생성 · 쿼터 주의)")}</option>
                        <option value="1h">{t("1시간 간격 (매시 정각)")}</option>
                        <option value="2h">{t("2시간 간격")}</option>
                        <option value="3h">{t("3시간 간격")}</option>
                        <option value="6h">{t("6시간 간격 (하루 4편)")}</option>
                        <option value="12h">{t("12시간 간격 (하루 2편)")}</option>
                      </optgroup>
                      <optgroup label={t("일자 단위 반복")}>
                        <option value="1d">{t("매일 1편씩 (1일 간격)")}</option>
                        <option value="2d">{t("2일에 1편씩")}</option>
                        <option value="3d">{t("3일에 1편씩 (주 2회)")}</option>
                        <option value="7d">{t("일주일에 1편씩 (주 1회)")}</option>
                      </optgroup>
                    </select>
                    <span className="param-hint">
                      {scheduleInterval.includes("m") || scheduleInterval.includes("h")
                        ? t("당일 반복 시 하루 6편을 초과하면 YouTube 일일 업로드 쿼터(10,000점)가 소진될 수 있습니다.")
                        : t("지정된 일자 간격에 맞춰 순차적으로 예약 발행(publishAt)됩니다.")}
                    </span>
                  </div>

                  <div className="param-divider" />

                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="calendar" s={13} />
                      <span>{t("첫 발행 기준 일시")}</span>
                    </label>
                    <div className="param-two-col">
                      <div>
                        <span className="param-sublabel">{t("시작 날짜")}</span>
                        <input
                          type="date"
                          className="param-input"
                          value={startDate}
                          onChange={(e) => setStartDate(e.target.value)}
                        />
                      </div>
                      <div>
                        <span className="param-sublabel">{t("기준 시각 (KST)")}</span>
                        <input
                          type="time"
                          className="param-input"
                          value={publishTime}
                          onChange={(e) => setPublishTime(e.target.value)}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="param-divider" />

                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="sparkle" s={13} />
                      <span>{t("주제 입력 방식")}</span>
                    </label>
                    <div className="param-tabs">
                      <button
                        type="button"
                        className={cx("param-tab", topicMode === "theme" && "active")}
                        onClick={() => setTopicMode("theme")}
                      >
                        {t("단일 메인 테마")}
                      </button>
                      <button
                        type="button"
                        className={cx("param-tab", topicMode === "list" && "active")}
                        onClick={() => setTopicMode("list")}
                      >
                        {t("소주제 목록 직접 입력")}
                      </button>
                    </div>
                  </div>

                  {topicMode === "theme" ? (
                    <>
                      <div className="param-group">
                        <label className="param-label">{t("메인 테마 (AI가 편수만큼 소주제로 분할)")}</label>
                        <input
                          className="param-input"
                          value={themeInput}
                          onChange={(e) => setThemeInput(e.target.value)}
                          placeholder={t("예: 일상 속 IT 기기들이 몰래 일하는 원리")}
                        />
                      </div>

                      <div className="param-group">
                        <div className="param-row-between">
                          <label className="param-label">{t("배치 생성 편수")}</label>
                          <b className="param-val mono">{videoCount}{t("편")}</b>
                        </div>
                        <input
                          type="range"
                          min={1}
                          max={10}
                          value={videoCount}
                          onChange={(e) => setVideoCount(Number(e.target.value))}
                          className="param-range"
                        />
                        <div className="param-range-labels">
                          <span>1편</span>
                          <span>6편 (권장 상한)</span>
                          <span>10편</span>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="param-group">
                      <label className="param-label">{t("소주제 목록 (한 줄에 1편)")}</label>
                      <textarea
                        className="param-textarea"
                        rows={5}
                        value={listInput}
                        onChange={(e) => {
                          setListInput(e.target.value);
                          const lines = e.target.value.split("\n").filter((s) => s.trim().length > 0);
                          if (lines.length > 0) setVideoCount(lines.length);
                        }}
                        placeholder={"1. 와이파이 공유기 안테나가 신호를 쏘는 법\n2. 노트북 쿨링팬이 갑자기 바빠지는 순간\n3. 스마트폰 배터리가 겨울에 빨리 닳는 이유"}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* 2. Preset Settings */}
              {selectedNodeId === "preset" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="library" s={13} />
                      <span>{t("시리즈 프리셋 선택")}</span>
                    </label>
                    <div className="preset-radio-list">
                      <div
                        className={cx("preset-card-opt", !selectedPresetId && "selected")}
                        onClick={() => setSelectedPresetId("")}
                      >
                        <span className="opt-title">{t("프리셋 없음 (자유 기획)")}</span>
                        <p className="opt-desc">{t("주제에 맞는 캐릭터와 스타일을 매 편 새로 기획합니다.")}</p>
                      </div>

                      {presets.map((pr) => {
                        const charName = (pr as any).character || pr.characterId;
                        return (
                          <div
                            key={pr.id}
                            className={cx("preset-card-opt", selectedPresetId === pr.id && "selected")}
                            onClick={() => setSelectedPresetId(pr.id)}
                          >
                            <div className="opt-radio-row">
                              <span className="opt-title">{pr.name}</span>
                              <span className="opt-tag mono">{pr.id}</span>
                            </div>
                            <p className="opt-desc">{pr.description || pr.style}</p>
                            {charName && (
                              <div className="opt-bound-pill">
                                <Icon n="check" s={11} />
                                <span>{t("고정 캐릭터: {c}", { c: charName })}</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {currentPreset?.style && (
                    <div className="param-group">
                      <label className="param-label">{t("적용될 3D 화풍 프롬프트")}</label>
                      <div className="param-box mono">{currentPreset.style}</div>
                    </div>
                  )}
                </div>
              )}

              {/* 3. AI Planning */}
              {selectedNodeId === "ai" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="sparkle" s={13} />
                      <span>{t("샷 계획 & 검증 규칙 (engine/gen/plan.py)")}</span>
                    </label>
                    <div className="param-box">
                      <b>4박자 인과 아크 (Hook → Build → Turn → Payoff)</b>
                      <p className="param-subtext">
                        {t("무음 테스트(구체적 3D 소품 필수 · 추상 구체 금지), 인접 샷 구도 다양성, 대사 음절 길이(초당 5.8음절 이하)를 자동 검증합니다.")}
                      </p>
                    </div>
                  </div>

                  <div className="param-group">
                    <label className="param-label">{t("예상 토큰 예산")}</label>
                    <div className="param-metric-box">
                      <span>{t("기획 · 검증 토큰")}</span>
                      <b className="mono">{(finalCount * 15000).toLocaleString()} Tokens</b>
                    </div>
                  </div>
                </div>
              )}

              {/* 4. Veo 3D Video */}
              {selectedNodeId === "veo" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="video" s={13} />
                      <span>{t("캐릭터 시트 · 키프레임 · Veo I2V")}</span>
                    </label>
                    <div className="param-box">
                      <b>Veo 3.1 Lite (9:16 세로형 I2V)</b>
                      <p className="param-subtext">
                        {t("4면 턴어라운드 캐릭터 시트(front/back/left/right) 참조로 키프레임을 생성한 뒤, 시작 프레임 기반으로 클립을 렌더링합니다.")}
                      </p>
                    </div>
                  </div>

                  <div className="param-group">
                    <label className="param-label">{t("크레딧 예산 현황")}</label>
                    <div className="param-metric-box">
                      <span>{t("예상 소비 크레딧 (샷당 10 × 4샷)")}</span>
                      <b className="mono">{finalCount * 40} Credits</b>
                    </div>
                  </div>
                </div>
              )}

              {/* 5. Timeline Assembly */}
              {selectedNodeId === "timeline" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="render" s={13} />
                      <span>{t("오디오 · 자막 · 타임라인 합성 (assemble.py)")}</span>
                    </label>
                    <div className="param-box">
                      <b>TTS 내레이션 + Veo SFX 믹싱 + ASS 자막 번인</b>
                      <p className="param-subtext">
                        {t("실제 음성 발화 길이에 맞춰 샷을 정렬하고, 클립 자체 효과음(28%)과 내레이션을 믹싱하며 상단 훅 타이틀과 하단 자막을 합성합니다.")}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* 6. YouTube Upload */}
              {selectedNodeId === "youtube" && (
                <div className="param-section">
                  <div className="param-group">
                    <label className="param-label">
                      <Icon n="upload" s={13} />
                      <span>{t("배포 방식 (Publish Mode)")}</span>
                    </label>
                    <div className="param-toggle-card">
                      <div className="toggle-info">
                        <b>{t("완전 자동 예약 업로드 (Hands-free)")}</b>
                        <p>{t("비활성화 시 최종 초안 완성 후 Studio에서 검토 뒤 승인합니다.")}</p>
                      </div>
                      <label className="n8n-switch">
                        <input
                          type="checkbox"
                          checked={autoPublish}
                          onChange={(e) => setAutoPublish(e.target.checked)}
                        />
                        <span className="n8n-slider" />
                      </label>
                    </div>
                  </div>

                  <div className="param-group">
                    <label className="param-label">{t("YouTube Data API v3 쿼터 진단")}</label>
                    <div className={cx("quota-alert-card", finalCount <= 6 ? "safe" : "danger")}>
                      <div className="alert-top">
                        <Icon n={finalCount <= 6 ? "check" : "warn"} s={15} />
                        <b>{finalCount <= 6 ? t("일일 쿼터 안전 범위") : t("일일 쿼터 초과 경고")}</b>
                      </div>
                      <p>
                        {t("일일 10,000점 중 {pts}점 소모 예정 (편당 1,600점). 하루 권장 최대 편수는 6편입니다.", {
                          pts: (finalCount * 1600).toLocaleString(),
                        })}
                      </p>
                      {finalCount > 6 && (
                        <button
                          type="button"
                          className="adjust-quota-btn"
                          onClick={() => setVideoCount(6)}
                        >
                          {t("권장 수량(6편)으로 조정")}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Step Navigation Footer */}
            <div className="panel-footer">
              <Button
                variant="ghost"
                size="sm"
                disabled={selectedIdx <= 0}
                onClick={() => selectedIdx > 0 && setSelectedNodeId(NODES[selectedIdx - 1].id)}
              >
                {t("이전 단계")}
              </Button>
              <span className="panel-step-counter mono">
                {selectedIdx + 1} / {NODES.length}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={selectedIdx >= NODES.length - 1}
                onClick={() => selectedIdx < NODES.length - 1 && setSelectedNodeId(NODES[selectedIdx + 1].id)}
              >
                {t("다음 단계")}
              </Button>
            </div>
          </aside>
        )}
      </div>

      {/* 4. Bottom Collapsible Execution Logs Drawer */}
      {showHistoryDrawer && (
        <div className={cx("n8n-history-drawer", !selectedNode && "full-width")}>
          <div className="drawer-header">
            <div className="drawer-title-group">
              <Icon n="history" s={15} />
              <h4>{t("자동화 실행 내역")}</h4>
            </div>
            <div className="drawer-actions">
              {history.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  icon="trash"
                  loading={clearHistoryMutation.isPending}
                  onClick={() => clearHistoryMutation.mutate()}
                >
                  {t("기록 비우기")}
                </Button>
              )}
              <IconButton
                icon="close"
                label={t("닫기")}
                size="sm"
                onClick={() => setShowHistoryDrawer(false)}
              />
            </div>
          </div>

          <div className="drawer-content">
            {loadingHistory ? (
              <div className="drawer-skel">
                <Skeleton h={40} r={6} />
                <Skeleton h={40} r={6} />
              </div>
            ) : history.length === 0 ? (
              <div className="drawer-empty">
                {t("실행된 자동화 기록이 없습니다. 주제를 입력하고 상단의 [워크플로 실행] 버튼을 눌러보세요.")}
              </div>
            ) : (
              <div className="drawer-hist-table">
                <div className="hist-th">
                  <span>{t("배치 ID")}</span>
                  <span>{t("상태")}</span>
                  <span>{t("편수")}</span>
                  <span>{t("주제 요약")}</span>
                  <span>{t("실행 일시")}</span>
                </div>
                {history.map((item, i) => {
                  const rowId = item.id || item.batchId || `row-${i}`;
                  const count = item.videoCount ?? item.topicsCount ?? 1;
                  const ts = item.triggeredAt || item.date;
                  const isRunning = item.status === "in_progress" || item.status === "running";
                  return (
                    <div key={rowId} className="hist-tr">
                      <span className="mono hist-id">{rowId}</span>
                      <span className={cx("hist-badge", isRunning ? "running" : "done")}>
                        {isRunning ? t("실행 중") : t("대기열 등록")}
                      </span>
                      <span className="hist-count mono">{count}{t("편")}</span>
                      <span className="hist-topics faint">
                        {(item.topics || []).length > 0
                          ? (item.topics || []).slice(0, 2).join(", ") + ((item.topics || []).length > 2 ? ` 외 ${(item.topics || []).length - 2}건` : "")
                          : item.presetId || "-"}
                      </span>
                      <span className="hist-time mono faint">
                        {ts ? new Date(ts).toLocaleString() : "-"}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 5. n8n Connection & Sync Settings Modal */}
      <N8nConfigDialog
        open={showN8nConfigModal}
        host={n8nHost}
        apiKey={n8nApiKey}
        workflowId={n8nWorkflowId}
        isConnected={isConnected}
        onClose={() => setShowN8nConfigModal(false)}
        onSave={async (newHost, newKey, newId) => {
          await fetch("/api/n8n/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ host: newHost, apiKey: newKey, workflowId: newId }),
          });
          setN8nHost(newHost);
          setN8nApiKey(newKey);
          setN8nWorkflowId(newId);
          toast.success(t("n8n 연결 설정이 저장되었습니다."));
          refetchN8nStatus();
        }}
        onDeploy={() => deployMutation.mutate()}
        deploying={deployMutation.isPending}
      />
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* n8n Connection & Sync Configuration Dialog                                 */
/* -------------------------------------------------------------------------- */
const N8nConfigDialog: React.FC<{
  open: boolean;
  host: string;
  apiKey: string;
  workflowId: string;
  isConnected: boolean;
  onClose: () => void;
  onSave: (host: string, key: string, wid: string) => Promise<void>;
  onDeploy: () => void;
  deploying: boolean;
}> = ({ open, host, apiKey, workflowId, isConnected, onClose, onSave, onDeploy, deploying }) => {
  const [h, setH] = useState(host);
  const [k, setK] = useState(apiKey);
  const [w, setW] = useState(workflowId);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setH(host);
    setK(apiKey);
    setW(workflowId);
  }, [host, apiKey, workflowId, open]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()} title={t("n8n 서버 API 연동 & 워크플로 배포")} width={520}>
      <div className="n8n-dialog-body">
        <div className="n8n-dialog-status">
          <div className="dialog-status-icon">
            <Icon n="n8n" s={22} />
          </div>
          <div>
            <b>{isConnected ? t("n8n 인스턴스에 정상 연결되어 있습니다") : t("로컬 단독 모드 (n8n 서버 미연결)")}</b>
            <p className="faint">{t("외부 n8n 서버를 연결하면 백그라운드 크론 트리거와 웹훅 파이프라인을 양방향으로 동기화합니다.")}</p>
          </div>
        </div>

        <div className="param-group">
          <label className="param-label">{t("n8n 호스트 주소 (Host URL)")}</label>
          <input
            className="param-input mono"
            placeholder="http://localhost:5678"
            value={h}
            onChange={(e) => setH(e.target.value)}
          />
        </div>

        <div className="param-group">
          <label className="param-label">{t("n8n API Key (n8n Settings > API 에서 발급)")}</label>
          <input
            type="password"
            className="param-input mono"
            placeholder="n8n_api_key_..."
            value={k}
            onChange={(e) => setK(e.target.value)}
          />
          <span className="param-hint">{t("API Key를 입력하면 원클릭 워크플로 배포 및 스케줄러 제어가 활성화됩니다.")}</span>
        </div>

        <div className="param-group">
          <label className="param-label">{t("연동할 n8n 워크플로 ID")}</label>
          <div className="param-input-with-btn">
            <input
              className="param-input mono"
              placeholder="예: 1 또는 Wx8k2..."
              value={w}
              onChange={(e) => setW(e.target.value)}
            />
            <Button
              variant="secondary"
              size="sm"
              icon="sparkle"
              loading={deploying}
              onClick={onDeploy}
            >
              {t("워크플로 자동 생성")}
            </Button>
          </div>
        </div>

        <div className="n8n-dialog-actions">
          <Button variant="ghost" onClick={onClose}>{t("취소")}</Button>
          <Button
            variant="primary"
            loading={saving}
            onClick={async () => {
              setSaving(true);
              await onSave(h, k, w);
              setSaving(false);
              onClose();
            }}
          >
            {t("설정 저장")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
};
