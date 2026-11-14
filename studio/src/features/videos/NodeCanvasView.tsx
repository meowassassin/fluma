/* ArtCraft 스타일 자유 노드 캔버스 뷰 (Infinite Node Graph Canvas).
   - 무한 2D 팬(Pan) · 마우스 휠 줌(Zoom) · 개별 노드 자유 드래그 배치 · 자동 정렬(Auto-layout)
   - 노드 계보(Lineage):
     [기획 브리프] ──▶ [캐릭터 시트 노드] ──┐
                   ──▶ [3D 포즈/마스크 가이드] ─┼──▶ [샷별 키프레임 & 후보(c1,c2)] ──▶ [샷별 영상 & 테이크] ──▶ [초안/최종 영상]
   - 캔버스 노드 위에서 바로:
     · 3D 마네킹 포즈 / 2D 마스크 스튜디오 열기
     · 키프레임 다중 후보(2장) 생성 및 원하는 후보 채택(pick)
     · 샷별 키프레임 / 영상 승인 및 재생성 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import type { Pipeline, PipelineLive } from "../../lib/api";
import { t } from "../../lib/i18n";

const F = (rel: string | null | undefined) => (rel ? `/api/pipefiles/${rel}` : "");
const OUT = (id: string, name: string) => `/api/projects/${id}/studio-file?p=${encodeURIComponent(`data/out/${name}`)}`;

interface CanvasNode {
  id: string;
  kind: "brief" | "character" | "guide" | "keyframe" | "video" | "output";
  title: string;
  subtitle?: string;
  badge?: string;
  badgeTone?: "ok" | "wait" | "todo";
  defaultX: number;
  defaultY: number;
  width: number;
  shot?: number;
  charName?: string;
}

interface CanvasEdge {
  from: string;
  to: string;
  active?: boolean;
}

export interface NodeCanvasViewProps {
  id: string;
  pipeline: Pipeline;
  live: PipelineLive | null;
  busy: boolean;
  act: (
    step: string,
    action: string,
    body?: { name?: string; views?: string; shots?: string; say?: string; candidates?: number; candidate?: number },
  ) => void;
  onOpenStudio: (shot: number) => void;
  onOpenEditor?: () => void;
}

export const NodeCanvasView: React.FC<NodeCanvasViewProps> = ({
  id,
  pipeline,
  busy,
  act,
  onOpenStudio,
  onOpenEditor,
}) => {
  const storageKey = `fluma-node-pos:${id}`;
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) || "{}");
    } catch {
      return {};
    }
  });
  const [pan, setPan] = useState({ x: 28, y: 24 });
  const [zoom, setZoom] = useState(0.88);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const panDragRef = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const nodeDragRef = useRef<{ id: string; sx: number; sy: number; nx: number; ny: number } | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(positions));
    } catch {
      /* ignore quota */
    }
  }, [positions, storageKey]);

  const { nodes, edges } = useMemo(() => {
    const ns: CanvasNode[] = [];
    const es: CanvasEdge[] = [];

    const shots = pipeline.plan?.shots ?? [];
    const chars = pipeline.characters ?? [];
    const kfs = new Map(pipeline.keyframes.map((k) => [k.shot, k]));
    const clips = new Map(pipeline.clips.map((c) => [c.shot, c]));

    // 1. Brief node (Col 0)
    const briefY = Math.max(40, ((shots.length - 1) * 230) / 2);
    ns.push({
      id: "brief",
      kind: "brief",
      title: pipeline.plan?.topic || id,
      subtitle: `${shots.length}개 샷 · ${pipeline.plan?.aspect || "9:16"}`,
      badge: "기획",
      badgeTone: "ok",
      defaultX: 20,
      defaultY: briefY,
      width: 210,
    });

    // 2. Character nodes (Col 1)
    chars.forEach((c, idx) => {
      const nid = `char:${c.name}`;
      ns.push({
        id: nid,
        kind: "character",
        title: `캐릭터 · ${c.name}`,
        subtitle: `${Object.keys(c.files || {}).length}/4 방향`,
        badge: c.state,
        badgeTone: c.state === "승인" ? "ok" : "wait",
        defaultX: 280,
        defaultY: 30 + idx * 220,
        width: 220,
        charName: c.name,
      });
      es.push({ from: "brief", to: nid, active: c.state === "승인" });
    });

    // 3. Per-shot Guide + Keyframe + Video nodes
    shots.forEach((s, idx) => {
      const rowY = 24 + idx * 245;
      const kf = kfs.get(s.n);
      const clip = clips.get(s.n);
      const hasGuide = !!(kf?.has_stage || kf?.has_compose || kf?.has_mask);

      const guideId = `guide:${s.n}`;
      const kfId = `kf:${s.n}`;
      const vidId = `vid:${s.n}`;

      // Guide node (Col 2)
      ns.push({
        id: guideId,
        kind: "guide",
        title: `#${s.n} 3D 포즈 · 마스크`,
        subtitle: kf?.has_stage
          ? "3D 마네킹 스테이지"
          : kf?.has_compose
          ? "2D 레이어 배치"
          : kf?.has_mask
          ? "2D 마스크 인페인팅"
          : "가이드 없음 (클릭해 설정)",
        badge: hasGuide ? "가이드 적용됨" : "선택",
        badgeTone: hasGuide ? "ok" : "todo",
        defaultX: 550,
        defaultY: rowY,
        width: 195,
        shot: s.n,
      });

      // Connect characters or brief to guide/keyframe
      const shotChars = (s.characters ?? []).filter((cn) => chars.some((c) => c.name === cn));
      if (shotChars.length > 0) {
        for (const cn of shotChars) {
          es.push({ from: `char:${cn}`, to: guideId, active: true });
        }
      } else {
        es.push({ from: "brief", to: guideId, active: true });
      }

      // Keyframe node (Col 3)
      ns.push({
        id: kfId,
        kind: "keyframe",
        title: `#${s.n} 키 프레임 (${s.purpose})`,
        subtitle: `${s.shot_size} · ${s.angle}`,
        badge: kf?.state || "대기",
        badgeTone: kf?.state === "승인" ? "ok" : kf?.first ? "wait" : "todo",
        defaultX: 800,
        defaultY: rowY,
        width: 235,
        shot: s.n,
      });
      es.push({ from: guideId, to: kfId, active: !!kf?.first });

      // Video node (Col 4)
      ns.push({
        id: vidId,
        kind: "video",
        title: `#${s.n} 영상 (${s.final_sec}s/${s.gen_sec}s)`,
        subtitle: s.camera_move,
        badge: clip?.approved ? "승인" : clip?.clip_url ? "검토 대기" : "생성 전",
        badgeTone: clip?.approved ? "ok" : clip?.clip_url ? "wait" : "todo",
        defaultX: 1090,
        defaultY: rowY,
        width: 235,
        shot: s.n,
      });
      es.push({ from: kfId, to: vidId, active: !!clip?.clip_url });
      if (idx > 0) {
        // Continuity link from previous shot video
        es.push({ from: `vid:${shots[idx - 1].n}`, to: vidId, active: false });
      }
    });

    // 4. Final Output / Editor node (Col 5)
    const outId = "output";
    ns.push({
      id: outId,
      kind: "output",
      title: "타임라인 조립 · 최종본",
      subtitle: pipeline.edit?.final ? "최종 렌더 완료" : pipeline.edit?.draft ? "초안 준비됨" : "조립 대기",
      badge: pipeline.edit?.final ? "완료" : pipeline.edit?.draft ? "초안" : "대기",
      badgeTone: pipeline.edit?.final ? "ok" : pipeline.edit?.draft ? "wait" : "todo",
      defaultX: 1385,
      defaultY: briefY,
      width: 225,
    });
    for (const s of shots) {
      es.push({ from: `vid:${s.n}`, to: outId, active: !!(pipeline.edit?.draft || pipeline.edit?.final) });
    }

    return { nodes: ns, edges: es };
  }, [pipeline, id]);

  const posOf = (n: CanvasNode) => positions[n.id] ?? { x: n.defaultX, y: n.defaultY };
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Canvas Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
        <span style={{ color: "#999" }}>
          빈 공간을 드래그해 이동(Pan), 마우스 휠로 확대/축소, 각 노드를 원하는 위치로 자유롭게 배치하세요.
        </span>
        <div style={{ display: "flex", gap: 6, marginLeft: "auto", alignItems: "center" }}>
          <span className="pgx-count">{Math.round(zoom * 100)}%</span>
          <button type="button" className="pgx-btn is-xs" onClick={() => setZoom((z) => Math.max(0.45, Number((z - 0.12).toFixed(2))))}>
            − 축소
          </button>
          <button type="button" className="pgx-btn is-xs" onClick={() => setZoom((z) => Math.min(1.6, Number((z + 0.12).toFixed(2))))}>
            + 확대
          </button>
          <button
            type="button"
            className="pgx-btn is-xs"
            onClick={() => {
              setPan({ x: 28, y: 24 });
              setZoom(0.88);
            }}
          >
            화면 맞춤
          </button>
          <button
            type="button"
            className="pgx-btn is-xs"
            onClick={() => {
              setPositions({});
              localStorage.removeItem(storageKey);
            }}
          >
            노드 자동 정렬
          </button>
        </div>
      </div>

      {/* Infinite Canvas Viewport */}
      <div
        style={{
          position: "relative",
          width: "100%",
          height: 580,
          borderRadius: 10,
          border: "1px solid var(--line-2)",
          backgroundColor: "#0e1015",
          backgroundImage: "radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)",
          backgroundSize: `${Math.round(20 * zoom)}px ${Math.round(20 * zoom)}px`,
          backgroundPosition: `${pan.x}px ${pan.y}px`,
          overflow: "hidden",
          cursor: panDragRef.current ? "grabbing" : "grab",
          userSelect: "none",
        }}
        onMouseDown={(e) => {
          if (e.target !== e.currentTarget && !(e.target as HTMLElement).classList.contains("ncv-plane")) return;
          setSelectedId(null);
          panDragRef.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y };
        }}
        onMouseMove={(e) => {
          if (nodeDragRef.current) {
            const nd = nodeDragRef.current;
            const dx = (e.clientX - nd.sx) / zoom;
            const dy = (e.clientY - nd.sy) / zoom;
            setPositions((prev) => ({
              ...prev,
              [nd.id]: { x: Math.round(nd.nx + dx), y: Math.round(nd.ny + dy) },
            }));
            return;
          }
          if (panDragRef.current) {
            const pd = panDragRef.current;
            setPan({ x: pd.px + (e.clientX - pd.sx), y: pd.py + (e.clientY - pd.sy) });
          }
        }}
        onMouseUp={() => {
          panDragRef.current = null;
          nodeDragRef.current = null;
        }}
        onMouseLeave={() => {
          panDragRef.current = null;
          nodeDragRef.current = null;
        }}
        onWheel={(e) => {
          if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) > 0) {
            e.preventDefault();
            const factor = e.deltaY < 0 ? 1.08 : 0.92;
            setZoom((z) => Math.max(0.42, Math.min(1.65, Number((z * factor).toFixed(3)))));
          }
        }}
      >
        <div
          className="ncv-plane"
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            transformOrigin: "0 0",
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            width: 2000,
            height: 1600,
          }}
        >
          {/* Bezier Edges SVG */}
          <svg
            style={{ position: "absolute", inset: 0, width: 2400, height: 2000, pointerEvents: "none", overflow: "visible" }}
          >
            {edges.map((edge, idx) => {
              const fromNode = nodeMap.get(edge.from);
              const toNode = nodeMap.get(edge.to);
              if (!fromNode || !toNode) return null;
              const p1 = posOf(fromNode);
              const p2 = posOf(toNode);
              const x1 = p1.x + fromNode.width;
              const y1 = p1.y + 58;
              const x2 = p2.x;
              const y2 = p2.y + 58;
              const cx1 = x1 + Math.max(40, (x2 - x1) * 0.45);
              const cx2 = x2 - Math.max(40, (x2 - x1) * 0.45);
              const d = `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
              return (
                <g key={`${edge.from}->${edge.to}:${idx}`}>
                  <path
                    d={d}
                    fill="none"
                    stroke={edge.active ? "#6366f1" : "rgba(130, 140, 165, 0.32)"}
                    strokeWidth={edge.active ? 2.2 : 1.5}
                    strokeDasharray={edge.from.startsWith("vid:") && edge.to.startsWith("vid:") ? "4 4" : undefined}
                  />
                  <circle cx={x1} cy={y1} r={3.2} fill={edge.active ? "#6366f1" : "#4a5361"} />
                  <circle cx={x2} cy={y2} r={3.2} fill={edge.active ? "#6366f1" : "#4a5361"} />
                </g>
              );
            })}
          </svg>

          {/* Nodes */}
          {nodes.map((node) => {
            const pos = posOf(node);
            const isSel = selectedId === node.id;
            const kf = node.shot ? pipeline.keyframes.find((k) => k.shot === node.shot) : undefined;
            const clip = node.shot ? pipeline.clips.find((c) => c.shot === node.shot) : undefined;
            const charObj = node.charName ? pipeline.characters.find((c) => c.name === node.charName) : undefined;

            const badgeBg =
              node.badgeTone === "ok"
                ? "rgba(63, 185, 80, 0.2)"
                : node.badgeTone === "wait"
                ? "rgba(210, 153, 34, 0.22)"
                : "rgba(110, 118, 129, 0.2)";
            const badgeColor =
              node.badgeTone === "ok" ? "#3fb950" : node.badgeTone === "wait" ? "#d29922" : "#8b949e";

            return (
              <div
                key={node.id}
                onMouseDown={(e) => {
                  e.stopPropagation();
                  setSelectedId(node.id);
                  nodeDragRef.current = { id: node.id, sx: e.clientX, sy: e.clientY, nx: pos.x, ny: pos.y };
                }}
                style={{
                  position: "absolute",
                  left: pos.x,
                  top: pos.y,
                  width: node.width,
                  background: "#181a22",
                  border: `1.5px solid ${isSel ? "#6366f1" : "#2b2f3d"}`,
                  borderRadius: 10,
                  padding: 10,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  boxShadow: isSel ? "0 0 0 2px rgba(99,102,241,0.35), 0 12px 28px rgba(0,0,0,0.5)" : "0 8px 20px rgba(0,0,0,0.4)",
                  cursor: "grab",
                }}
              >
                {/* Node Header */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                  <b style={{ fontSize: 12.5, color: "#f0f2f8", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {node.title}
                  </b>
                  {node.badge && (
                    <span
                      style={{
                        fontSize: 10.5,
                        padding: "1px 6px",
                        borderRadius: 99,
                        background: badgeBg,
                        color: badgeColor,
                        fontWeight: 600,
                        flexShrink: 0,
                      }}
                    >
                      {node.badge}
                    </span>
                  )}
                </div>

                {node.subtitle && (
                  <div style={{ fontSize: 11, color: "#8b949e", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {node.subtitle}
                  </div>
                )}

                {/* Kind-specific Body */}
                {node.kind === "brief" && (
                  <div style={{ fontSize: 11.5, color: "#c9d1d9", lineHeight: 1.4, background: "#12141a", padding: 8, borderRadius: 6 }}>
                    <div>스타일: {(pipeline.plan?.style || "").slice(0, 68)}…</div>
                  </div>
                )}

                {node.kind === "character" && charObj && (
                  <>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 4 }}>
                      {["front", "left", "right", "back"].map((v) => {
                        const f = charObj.files?.[v];
                        return f ? (
                          <img key={v} src={F(f)} alt={v} title={v} style={{ width: "100%", aspectRatio: "1/1", objectFit: "cover", borderRadius: 4 }} />
                        ) : (
                          <div key={v} style={{ width: "100%", aspectRatio: "1/1", background: "#111319", borderRadius: 4 }} />
                        );
                      })}
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          act("character", "make", { name: charObj.name, views: "all" });
                        }}
                      >
                        시트 생성
                      </button>
                      {charObj.state !== "승인" && Object.keys(charObj.files || {}).length > 0 && (
                        <button
                          type="button"
                          className="pgx-btn is-primary is-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            act("character", "approve", { name: charObj.name });
                          }}
                        >
                          승인 ①
                        </button>
                      )}
                    </div>
                  </>
                )}

                {node.kind === "guide" && node.shot && (
                  <>
                    {kf?.stage_url || kf?.compose_url || kf?.mask_url ? (
                      <img
                        src={F(kf.stage_url || kf.compose_url || kf.mask_url)}
                        alt=""
                        style={{ width: "100%", height: 105, objectFit: "cover", borderRadius: 6, background: "#101218" }}
                      />
                    ) : (
                      <div
                        style={{
                          width: "100%",
                          height: 64,
                          borderRadius: 6,
                          background: "#12141c",
                          border: "1px dashed #2e3344",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 11,
                          color: "#7d8590",
                        }}
                      >
                        🧍 3D 마네킹 · 2D 마스크
                      </div>
                    )}
                    <button
                      type="button"
                      className="pgx-btn is-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenStudio(node.shot!);
                      }}
                    >
                      구도 · 마네킹 포즈 열기
                    </button>
                  </>
                )}

                {node.kind === "keyframe" && node.shot && (
                  <>
                    <div style={{ display: "flex", gap: 6 }}>
                      {kf?.first ? (
                        <img
                          src={F(kf.first)}
                          alt=""
                          style={{ width: kf.end ? "50%" : "100%", height: 124, objectFit: "cover", borderRadius: 6, background: "#101218" }}
                        />
                      ) : (
                        <div style={{ width: "100%", height: 100, borderRadius: 6, background: "#111319" }} />
                      )}
                      {kf?.end && (
                        <img
                          src={F(kf.end)}
                          alt="end"
                          title="끝 프레임"
                          style={{ width: "50%", height: 124, objectFit: "cover", borderRadius: 6, background: "#101218" }}
                        />
                      )}
                    </div>

                    {/* Candidates strip if multiple candidates exist */}
                    {kf?.candidates_files && kf.candidates_files.length > 0 && (
                      <div style={{ display: "flex", gap: 4, alignItems: "center", overflowX: "auto" }}>
                        {kf.candidates_files.map((cand) => (
                          <button
                            key={cand.name}
                            type="button"
                            title={`후보 #${cand.num} 채택하기`}
                            onClick={(e) => {
                              e.stopPropagation();
                              act("keyframe", "pick", { shots: String(node.shot), candidate: cand.num });
                            }}
                            style={{
                              padding: 0,
                              border: "1px solid #444",
                              borderRadius: 4,
                              overflow: "hidden",
                              width: 38,
                              height: 54,
                              cursor: "pointer",
                              background: "transparent",
                            }}
                          >
                            <img src={F(cand.url)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                          </button>
                        ))}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          act("keyframe", "make", { shots: String(node.shot) });
                        }}
                      >
                        생성
                      </button>
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        disabled={busy}
                        title="후보 2장을 동시에 뽑아 비교·선택합니다"
                        onClick={(e) => {
                          e.stopPropagation();
                          act("keyframe", "make", { shots: String(node.shot), candidates: 2 });
                        }}
                      >
                        후보 2장
                      </button>
                      {kf?.first && kf.state !== "승인" && (
                        <button
                          type="button"
                          className="pgx-btn is-primary is-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            act("keyframe", "approve", { shots: String(node.shot) });
                          }}
                        >
                          승인 ②
                        </button>
                      )}
                    </div>
                  </>
                )}

                {node.kind === "video" && node.shot && (
                  <>
                    {clip?.clip_url ? (
                      <video
                        src={F(clip.clip_url)}
                        muted
                        loop
                        playsInline
                        onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                        onMouseLeave={(e) => e.currentTarget.pause()}
                        style={{ width: "100%", height: 124, objectFit: "cover", borderRadius: 6, background: "#000" }}
                      />
                    ) : (
                      <div style={{ width: "100%", height: 100, borderRadius: 6, background: "#111319" }} />
                    )}
                    {clip?.takes && clip.takes.length > 1 && (
                      <div style={{ fontSize: 10.5, color: "#999" }}>보관된 테이크: {clip.takes.length}개</div>
                    )}
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          act("video", "run", { shots: String(node.shot) });
                        }}
                      >
                        {clip?.clip_url ? "재생성" : "영상 생성"}
                      </button>
                      {clip?.clip_url && !clip.approved && (
                        <button
                          type="button"
                          className="pgx-btn is-primary is-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            act("video", "approve", { shots: String(node.shot) });
                          }}
                        >
                          샷 승인
                        </button>
                      )}
                    </div>
                  </>
                )}

                {node.kind === "output" && (
                  <>
                    {(pipeline.edit?.final || pipeline.edit?.draft) && (
                      <video
                        src={OUT(id, (pipeline.edit.final || pipeline.edit.draft)!)}
                        controls
                        playsInline
                        style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 6, background: "#000" }}
                      />
                    )}
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="pgx-btn is-xs"
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          act("edit", "build");
                        }}
                      >
                        초안 조립
                      </button>
                      {onOpenEditor && (
                        <button
                          type="button"
                          className="pgx-btn is-primary is-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenEditor();
                          }}
                        >
                          {t("편집기 열기")}
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
