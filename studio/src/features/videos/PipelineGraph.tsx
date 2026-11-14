/* 파이프라인 뷰 — GitHub Actions 워크플로 그래프처럼 가로로 흐르는 2D 단계 상자.
   상자에는 상태 아이콘 · 짧은 단계 이름 · 그 단계 모델 아이콘만(작업 중이면 아이콘에 회전 고리). 나머지 말은 마우스를 올리면(title).
   상자를 누르면 아래에 그 단계의 결과물 · 승인 · 실행 버튼.
   variant="full"  영상 목록 펼침(가로) · variant="panel" 편집기 옆 패널(세로 목록) */
import React, { useMemo, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, type Pipeline, type PipelineLive } from "../../lib/api";
import { t } from "../../lib/i18n";
import { EngineIcon } from "../../ui/EngineIcon";
import { AppGlyph } from "../../ui/AppGlyph";
import { buildSteps, prettyModel, STATE_TX, usePipeline, type Model, type State, type Step } from "./pipelineModel";
import { KeyframeStudioModal } from "./KeyframeStudioModal";
import "./pipeline-graph.css";

const F = (rel: string | null | undefined) => (rel ? `/api/pipefiles/${rel}` : "");
const OUT = (id: string, name: string) => `/api/projects/${id}/studio-file?p=${encodeURIComponent(`data/out/${name}`)}`;

/** GitHub 식 상태 아이콘 */
export const StateIcon: React.FC<{ s: State; size?: number }> = ({ s, size = 16 }) => (
  <span className={`pgx-si s-${s}`} style={{ width: size, height: size }} title={t(STATE_TX[s])} aria-label={t(STATE_TX[s])}>
    {s === "done" && <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="8" /><path d="M4.6 8.3l2.2 2.2 4.6-4.8" /></svg>}
    {s === "error" && <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="8" /><path d="M5.4 5.4l5.2 5.2M10.6 5.4l-5.2 5.2" /></svg>}
    {s === "waiting" && <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" /><path d="M8 4.6V8l2.3 1.4" /></svg>}
    {s === "todo" && <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" /></svg>}
    {s === "running" && <svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5" className="trk" /><path d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5" className="arc" /></svg>}
  </span>
);

export const ModelIcon: React.FC<{ m: Model; size?: number; spin?: boolean }> = ({ m, size = 18, spin }) => (
  <span className={`pgx-mi ${spin ? "is-spin" : ""} ${m.dark ? "is-dark" : ""} ${m.planned ? "is-planned" : ""}`} title={m.planned ? `${t("예정")} · ${m.name}` : t(m.name)}>
    {m.unknown ? <span className="pgx-unk" style={{ width: size, height: size }}>?</span>
      : m.tile && m.src ? <img className="pgx-tile" src={m.src} alt="" style={{ width: size, height: size }} />
      : m.glyph ? <span className="pgx-glyph" style={{ width: size, height: size }}><AppGlyph k={m.glyph} s={Math.round(size * 0.66)} /></span>
      : <EngineIcon id={m.id || m.name} src={m.src ?? undefined} title={m.name} size={size} />}
  </span>
);

const tipOf = (s: Step) => [t(STATE_TX[s.state]), s.models.map((m) => m.name).join(" · "), s.tip].filter(Boolean).join(" — ");

/* ---------- 가로/세로 2D 그래프 ---------- */
const Graph: React.FC<{
  steps: Step[];
  edges: [string, string][];
  sel: string | null;
  onSel: (k: string) => void;
  orientation?: "horizontal" | "vertical";
}> = ({ steps, edges, sel, onSel, orientation = "horizontal" }) => {
  const isVert = orientation === "vertical";
  const by = new Map(steps.map((s) => [s.key, s]));

  if (isVert) {
    const laneCount = Math.max(...steps.map((s) => s.row)) + 1;
    const levelCount = Math.max(...steps.map((s) => s.col)) + 1;
    const BW = 136, BH = 38, VG = 30, HG = 22, PAD = 14;
    const W = PAD * 2 + laneCount * BW + (laneCount - 1) * HG;
    const H = PAD * 2 + levelCount * BH + (levelCount - 1) * VG;
    const pos = (s: Step) => ({ x: PAD + s.row * (BW + HG), y: PAD + s.col * (BH + VG) });

    return (
      <div className="pgx-scroll pgx-scroll-vert">
        <div className="pgx-graph pgx-graph-vert" style={{ width: W, height: H }}>
          <svg className="pgx-edges" width={W} height={H}>
            {edges.map(([a, b]) => {
              const A = by.get(a), B = by.get(b); if (!A || !B) return null;
              const p = pos(A), q = pos(B);
              const x1 = p.x + BW / 2, y1 = p.y + BH;
              const x2 = q.x + BW / 2, y2 = q.y;
              const my = y1 + (y2 - y1) / 2;
              const r = Math.min(8, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2);
              const d = x1 === x2 ? `M${x1} ${y1}V${y2}`
                : `M${x1} ${y1}V${my - r}Q${x1} ${my} ${x1 + Math.sign(x2 - x1) * r} ${my}H${x2 - Math.sign(x2 - x1) * r}Q${x2} ${my} ${x2} ${my + r}V${y2}`;
              const cls = B.state === "running" ? "is-flow" : A.state === "done" ? "is-done" : "";
              return (
                <g key={`${a}-${b}`} className={`pgx-edge ${cls}`}>
                  <path d={d} />
                  <circle cx={x1} cy={y1} r="3" />
                  <circle cx={x2} cy={y2} r="3" />
                </g>
              );
            })}
          </svg>
          {steps.map((s) => {
            const P = pos(s);
            return (
              <button key={s.key} type="button" className={`pgx-job s-${s.state} ${sel === s.key ? "is-sel" : ""}`}
                style={{ left: P.x, top: P.y, width: BW, height: BH }}
                title={tipOf(s)} onClick={() => onSel(s.key)}>
                <StateIcon s={s.state} />
                <span className="pgx-name">{s.name}</span>
                <span className="pgx-models">{s.models.slice(0, 2).map((m, i) => <ModelIcon key={i} m={m} size={18} spin={s.state === "running" && i === 0} />)}</span>
                {s.state === "running" && s.progress != null && <i className="pgx-prog" style={{ width: `${Math.round(s.progress * 100)}%` }} />}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // 가로 모드 (기본)
  const cols = Math.max(...steps.map((s) => s.col)) + 1, rows = Math.max(...steps.map((s) => s.row)) + 1;
  const BW = 132, BH = 38, CG = 44, RG = 16, PAD = 16;
  const W = PAD * 2 + cols * BW + (cols - 1) * CG, H = PAD * 2 + rows * BH + (rows - 1) * RG;
  const pos = (s: Step) => ({ x: PAD + s.col * (BW + CG), y: PAD + s.row * (BH + RG) });

  return (
    <div className="pgx-scroll">
      <div className="pgx-graph" style={{ width: W, height: H }}>
        <svg className="pgx-edges" width={W} height={H}>
          {edges.map(([a, b]) => {
            const A = by.get(a), B = by.get(b); if (!A || !B) return null;
            const p = pos(A), q = pos(B);
            const x1 = p.x + BW, y1 = p.y + BH / 2, x2 = q.x, y2 = q.y + BH / 2, mx = x1 + CG / 2, r = Math.min(8, Math.abs(y2 - y1) / 2);
            const d = y1 === y2 ? `M${x1} ${y1}H${x2}`
              : `M${x1} ${y1}H${mx - r}Q${mx} ${y1} ${mx} ${y1 + Math.sign(y2 - y1) * r}V${y2 - Math.sign(y2 - y1) * r}Q${mx} ${y2} ${mx + r} ${y2}H${x2}`;
            const cls = B.state === "running" ? "is-flow" : A.state === "done" ? "is-done" : "";
            return <g key={`${a}-${b}`} className={`pgx-edge ${cls}`}><path d={d} /><circle cx={x1} cy={y1} r="3" /><circle cx={x2} cy={y2} r="3" /></g>;
          })}
        </svg>
        {steps.map((s) => {
          const P = pos(s);
          return (
            <button key={s.key} type="button" className={`pgx-job s-${s.state} ${sel === s.key ? "is-sel" : ""}`} style={{ left: P.x, top: P.y, width: BW, height: BH }}
              title={tipOf(s)} onClick={() => onSel(s.key)}>
              <StateIcon s={s.state} />
              <span className="pgx-name">{s.name}</span>
              <span className="pgx-models">{s.models.slice(0, 2).map((m, i) => <ModelIcon key={i} m={m} size={18} spin={s.state === "running" && i === 0} />)}</span>
              {s.state === "running" && s.progress != null && <i className="pgx-prog" style={{ width: `${Math.round(s.progress * 100)}%` }} />}
            </button>
          );
        })}
      </div>
    </div>
  );
};

/* ---------- 세로 목록(편집기 옆 패널) ---------- */
const List: React.FC<{ steps: Step[]; sel: string | null; onSel: (k: string) => void }> = ({ steps, sel, onSel }) => (
  <ol className="pgx-list">
    {[...steps].sort((a, b) => a.col - b.col || a.row - b.row).map((s) => (
      <li key={s.key}>
        <button type="button" className={`pgx-li s-${s.state} ${sel === s.key ? "is-sel" : ""}`} title={tipOf(s)} onClick={() => onSel(s.key)}>
          <StateIcon s={s.state} />
          <span className="pgx-name">{s.name}</span>
          <span className="pgx-models">{s.models.slice(0, 2).map((m, i) => <ModelIcon key={i} m={m} size={18} spin={s.state === "running" && i === 0} />)}</span>
        </button>
      </li>
    ))}
  </ol>
);

export interface PipelineGraphProps { id: string; variant?: "full" | "panel"; orientation?: "horizontal" | "vertical"; onOpenEditor?: () => void }

export const PipelineGraph: React.FC<PipelineGraphProps> = ({ id, variant = "full", orientation, onOpenEditor }) => {
  const { data, live, error, reload } = usePipeline(id);
  const [sel, setSel] = useState<string | null>(null);
  const [studioShot, setStudioShot] = useState<number | null>(null);
  const g = useMemo(() => (data ? buildSteps(data, live) : null), [data, live]);
  const act = async (step: string, action: string, body: { name?: string; views?: string; shots?: string; say?: string; candidates?: number; candidate?: number } = {}) => {
    try { await api.pipelineAct(id, step, action, body); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  const isVert = orientation === "vertical" || variant === "panel";

  if (!g || !data) {
    return <div className={`pgx pgx-${variant} ${isVert ? "pgx-vert" : ""}`}>{error ? <div className="pgx-err">{error}</div> : <div className="pgx-loading"><StateIcon s="running" /></div>}</div>;
  }
  const done = g.steps.filter((s) => s.state === "done").length;
  const running = g.steps.filter((s) => s.state === "running");
  const selected = sel ? g.steps.find((s) => s.key === sel) ?? null : null;
  return (
    <div className={`pgx pgx-${variant} ${isVert ? "pgx-vert" : ""}`}>
      <div className="pgx-bar">
        <span className="pgx-meter" title={t("{a}/{b} 단계 완료", { a: done, b: g.steps.length })}>
          {g.steps.map((s) => <i key={s.key} className={`s-${s.state}`} />)}
        </span>
        <span className="pgx-count">{done}/{g.steps.length}</span>
        {running.map((s) => <ModelIcon key={s.key} m={s.models[0]} size={18} spin />)}
      </div>
      <Graph steps={g.steps} edges={g.edges} sel={sel} onSel={(k) => setSel(sel === k ? null : k)} orientation={isVert ? "vertical" : "horizontal"} />
      {selected && (
        <Detail
          id={id}
          s={selected}
          p={data}
          live={live}
          act={act}
          onOpenStudio={(sh) => setStudioShot(sh)}
          onOpenEditor={onOpenEditor}
          onClose={() => setSel(null)}
        />
      )}
      {studioShot !== null && (
        <KeyframeStudioModal
          id={id}
          shot={studioShot}
          pipeline={data}
          onClose={() => setStudioShot(null)}
          onUpdated={reload}
        />
      )}
    </div>
  );
};

/* ---------- 단계 상세: 결과물 · 버튼만 ---------- */
const Detail: React.FC<{
  id: string; s: Step; p: Pipeline; live: PipelineLive | null; onClose: () => void; onOpenEditor?: () => void; onOpenStudio: (shot: number) => void;
  act: (step: string, action: string, body?: { name?: string; views?: string; shots?: string; say?: string; candidates?: number; candidate?: number }) => void;
}> = ({ id, s, p, live, act, onOpenStudio, onOpenEditor, onClose }) => {
  const route = p.route || "generate";
  const draftStep = route === "clip" ? ["dub", "build"] : route === "material" ? ["material", "produce"] : ["edit", "build"];
  const busy = s.state === "running";
  return (
    <section className="pgx-detail">
      <header>
        <StateIcon s={s.state} />
        <b>{s.name}</b>
        {s.models.map((m, i) => <span key={i} className="pgx-mtag"><ModelIcon m={m} size={16} />{m.name}</span>)}
        <span className="pgx-sp" />
        <button type="button" className="pgx-x" onClick={onClose} aria-label={t("닫기")}>✕</button>
      </header>
      {s.state === "error" && s.tip && <p className="pgx-errline">{s.tip}</p>}

      {s.key === "plan" && !!p.plan?.shots?.length && (
        <ol className="pgx-shots">{p.plan.shots.map((x) => <li key={x.n} title={`${x.shot_size} · ${x.camera_move}`}><b>{x.n}</b>{x.purpose}<em>{x.final_sec}s</em></li>)}</ol>
      )}
      {s.key === "character" && p.characters.map((c) => (
        <div key={c.name} className="pgx-row">
          <div className="pgx-thumbs">{Object.entries(c.files || {}).map(([v, f]) => <img key={v} src={F(f)} alt={v} title={v} />)}</div>
          <div className="pgx-btns">
            <button className="pgx-btn" disabled={busy} onClick={() => act("character", "make", { name: c.name, views: "all" })}>{t("다시 만들기")}</button>
            <button className="pgx-btn is-primary" disabled={c.state === "승인" || !Object.keys(c.files || {}).length} onClick={() => act("character", "approve", { name: c.name })}>{t("승인")}</button>
          </div>
        </div>
      ))}
      {s.key === "keyframe" && (
        <div className="pgx-row">
          <div className="pgx-thumbs is-tall">{p.keyframes.map((k) => (
            <figure key={k.shot} title={`${k.shot} · ${k.state}`}>
              {k.first ? <img src={F(k.first)} alt="" /> : <span className="pgx-ph" />}
              <div style={{ display: "flex", gap: 3, flexWrap: "wrap", justifyContent: "center" }}>
                <button type="button" className="pgx-btn is-xs is-primary" onClick={() => onOpenStudio(k.shot)}>
                  {k.has_stage ? t("3D무대 ✓") : k.has_compose ? t("2D합성 ✓") : t("3D 무대 연출")}
                </button>
                {(k.first || k.has_stage || k.has_compose) && k.state !== "승인" && (
                  <button type="button" className="pgx-btn is-xs" onClick={() => act("keyframe", "approve", { shots: String(k.shot) })}>
                    {t("승인")}
                  </button>
                )}
              </div>
            </figure>
          ))}</div>
          <div className="pgx-btns">
            <button className="pgx-btn" disabled={busy} onClick={() => act("keyframe", "make")}>{t("키프레임 생성")}</button>
            <button className="pgx-btn is-primary" disabled={!p.keyframes.some((k) => (k.first || k.has_stage) && k.state !== "승인")} onClick={() => act("keyframe", "approve")}>{t("구도 승인")}</button>
          </div>
        </div>
      )}
      {s.key === "video" && (
        <div className="pgx-row">
          <div className="pgx-thumbs is-tall">{p.clips.map((c) => (
            <figure key={c.shot} title={`${c.shot} · ${c.state}`}>
              {c.clip_url ? <video src={F(c.clip_url)} muted loop playsInline onMouseEnter={(e) => e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} /> : <span className="pgx-ph" />}
              {c.clip_url && !c.approved && <button className="pgx-btn is-primary is-xs" onClick={() => act("video", "approve", { shots: String(c.shot) })}>{t("승인")}</button>}
              {c.clip_url && !c.approved && <Revise onSay={(say) => act("video", "revise", { shots: String(c.shot), say })} />}
            </figure>
          ))}</div>
          <div className="pgx-btns">
            <span className="pgx-faint">{prettyModel(p.videogen?.model || live?.models.video || "")}</span>
            <button className="pgx-btn" disabled={busy} onClick={() => act("video", "run")}>{t("생성")}</button>
          </div>
        </div>
      )}
      {s.key === "draft" && (
        <div className="pgx-row">
          {p.edit?.draft && <video className="pgx-preview" src={OUT(id, p.edit.draft)} controls playsInline />}
          <div className="pgx-btns"><button className="pgx-btn is-primary" disabled={busy} onClick={() => act(draftStep[0], draftStep[1])}>{p.edit?.draft ? t("다시 만들기") : t("초안 만들기")}</button></div>
        </div>
      )}
      {s.key === "editor" && onOpenEditor && (
        <div className="pgx-btns"><button className="pgx-btn is-primary" onClick={onOpenEditor}>{t("편집기 열기")}</button></div>
      )}
      {s.key === "publish" && (
        <div className="pgx-row">
          {p.edit?.final && <video className="pgx-preview" src={OUT(id, p.edit.final)} controls playsInline />}
          {!live?.editor.exported && <div className="pgx-btns"><button className="pgx-btn" disabled={busy} onClick={() => act("publish", "final")}>{t("최종 렌더")}</button></div>}
        </div>
      )}
    </section>
  );
};

/** 말로 고치기 — 고칠 점(영어)을 그 샷 프롬프트에 붙인다. 다음 '생성'에 반영(한국어는 AI 에이전트에게 말로) */
const Revise: React.FC<{ onSay: (say: string) => void }> = ({ onSay }) => {
  const [v, setV] = useState("");
  const send = () => {
    const s = v.trim(); if (!s) return;
    if (/[가-힣]/.test(s)) { toast.error(t("고칠 점은 영어로 적어 주세요 — 한국어는 AI 에이전트에게 말하면 옮겨 줍니다")); return; }
    onSay(s); setV("");
  };
  return (
    <form className="pgx-revise" onSubmit={(e) => { e.preventDefault(); send(); }}>
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="Make the text bigger" aria-label={t("고칠 점")} />
      <button type="submit" className="pgx-btn is-xs" disabled={!v.trim()} title={t("고칠 점을 붙이고 다음 생성에 반영")}>{t("고치기")}</button>
    </form>
  );
};
