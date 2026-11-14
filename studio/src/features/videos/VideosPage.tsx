/* 영상 — 만든 영상 목록(글자 최소: 제목 · 경로 색 점 · 작업 중 표시). 줄을 누르면 아래로 그 영상의 파이프라인 뷰(가로 워크플로 그래프 · 실시간)가 열린다.
   주소 ?open=<id> 로 펼친 영상을 기억한다(예전 /pipeline/:id 주소도 여기로 온다). */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "../../lib/api";
import { t } from "../../lib/i18n";
import { qc, qk } from "../../lib/queries";
import { useUi } from "../../lib/ui";
import { ago } from "../home/HomePage";
import { Icon } from "../../ui/Icon";
import { Button, EmptyState, Segmented, confirmDialog } from "../../ui/kit";
import { PipelineGraph, StateIcon } from "./PipelineGraph";
import "./videos.css";

type Row = { id: string; topic: string; shots: number; updated: number; thumb?: string | null; style?: string; route?: string };
type TrashRow = { name: string; id: string; title: string; deletedAt: string; files: string[] };
type Route = "all" | "generate" | "clip" | "material" | "trash";
const ROUTE_TX: Record<string, string> = { generate: "생성", clip: "클립 재편집", material: "실제 자료", trash: "휴지통" };
const F = (rel: string | null | undefined) => (rel ? `/api/pipefiles/${rel}` : "");

export const VideosPage: React.FC = () => {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [trash, setTrash] = useState<TrashRow[]>([]);
  const [q, setQ] = useState("");
  const [route, setRoute] = useState<Route>("all");
  const [busy, setBusy] = useState<Record<string, string>>({});   // 영상 id → 지금 도는 일
  const [sp, setSp] = useSearchParams();
  const open = sp.get("open");
  const nav = useNavigate();

  const load = useCallback(() => {
    api.pipelines().then(setRows).catch((e) => { toast.error(errMsg(e)); setRows([]); });
    api.trash().then(setTrash).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  // 목록 실시간: 어느 영상에서 작업 · 에이전트가 도는지
  useEffect(() => {
    let stop = false, timer = 0;
    const tick = async () => {
      try {
        const [jobs, act] = await Promise.all([api.jobs(), fetch("/api/agent/active").then((r) => (r.ok ? r.json() : [])) as Promise<{ id: string }[]>]);
        if (stop) return;
        const m: Record<string, string> = {};
        for (const a of act) m[a.id] = t("에이전트 작업 중");
        for (const j of jobs) if (j.project && (j.status === "running" || j.status === "queued")) m[j.project] = (j as { label?: string }).label || t("작업 중");
        setBusy(m);
      } catch { /* 다음에 */ }
      if (!stop) timer = window.setTimeout(tick, 4000);
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: rows?.length ?? 0, trash: trash.length };
    for (const r of rows ?? []) c[r.route || "generate"] = (c[r.route || "generate"] ?? 0) + 1;
    return c;
  }, [rows, trash]);
  const list = useMemo(() => (rows ?? [])
    .filter((r) => route === "all" || (r.route || "generate") === route)
    .filter((r) => !q || `${r.topic} ${r.id} ${r.style || ""}`.toLowerCase().includes(q.toLowerCase())), [rows, q, route]);

  const toggle = (id: string) => setSp((p) => { const n = new URLSearchParams(p); if (n.get("open") === id) n.delete("open"); else n.set("open", id); return n; }, { replace: true });

  const delVideo = async (r: Row) => {
    const ok = await confirmDialog({
      title: t("“{title}”을(를) 휴지통으로 옮길까요?", { title: r.topic || r.id }),
      body: t("콘티 · 키프레임 · 클립 · 음성 · 편집본이 함께 옮겨지고, 휴지통에서 되돌릴 수 있습니다."),
      ok: t("휴지통으로"),
      danger: true,
    });
    if (!ok) return;
    try {
      const res = await api.deleteProject(r.id);
      setRows((prev) => (prev ?? []).filter((x) => x.id !== r.id));
      if (open === r.id) setSp((p) => { const n = new URLSearchParams(p); n.delete("open"); return n; }, { replace: true });
      if (useUi.getState().lastProject === r.id) useUi.getState().set({ lastProject: null });
      qc.invalidateQueries({ queryKey: qk.projects });
      api.trash().then(setTrash).catch(() => {});
      toast(t("휴지통으로 옮겼어요"), {
        action: {
          label: t("되돌리기"),
          onClick: () => api.restore(res.trash).then(() => { load(); qc.invalidateQueries({ queryKey: qk.projects }); }).catch((e) => toast.error(errMsg(e))),
        },
      });
    } catch (e) {
      toast.error(t("옮기지 못했어요"), { description: errMsg(e) });
    }
  };

  return (
    <div className="page vids">
      <div className="pg-main">
        <header className="page-head">
          <div className="vids-title">
            <h1>{t("영상")}</h1>
            {rows && <span className="faint small">{t("{n}개", { n: rows.length })}</span>}
          </div>
          <Segmented
            size="sm"
            aria-label={t("경로")}
            value={route}
            onChange={(v) => setRoute(v as Route)}
            options={(["all", "generate", "clip", "material", "trash"] as Route[]).map((k) => ({
              value: k,
              label: (
                <span className="vids-seg-item">
                  {k === "all" ? t("전체") : t(ROUTE_TX[k])}
                  <em className="vids-seg-cnt">{counts[k] ?? 0}</em>
                </span>
              ),
            }))}
          />
          <span className="grow" />
          {route !== "trash" && (
            <label className="vids-search">
              <Icon n="search" s={14} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("제목 · 주제 찾기")} aria-label={t("영상 검색")} />
            </label>
          )}
        </header>

        <div className="pg-scroll">
          <div className="vids-container">
            {route === "trash" ? (
              trash.length === 0 ? (
                <EmptyState icon="trash" title={t("휴지통이 비었어요")} body={t("지운 영상은 여기로 옮겨지고, 되돌릴 수 있어요.")} />
              ) : (
                <ul className="vids-list">
                  {trash.map((x) => (
                    <li key={x.name} className="vids-item">
                      <div className="vids-row" style={{ cursor: "default" }}>
                        <div className="vids-thumb"><Icon n="trash" s={16} /></div>
                        <div className="vids-name">{x.title || x.id}</div>
                        <span className="faint small">{ago(x.deletedAt)} · {t("파일 {n}개", { n: x.files.length })}</span>
                        <div className="vids-acts">
                          <Button size="sm" icon="undo" onClick={() => api.restore(x.name).then(() => { toast.success(t("되돌렸어요")); load(); qc.invalidateQueries({ queryKey: qk.projects }); }).catch((e) => toast.error(errMsg(e)))}>
                            {t("되돌리기")}
                          </Button>
                          <Button size="sm" variant="danger" onClick={async () => {
                            if (!(await confirmDialog({ title: t("“{title}”을(를) 완전히 지울까요?", { title: x.title || x.id }), body: t("되돌릴 수 없습니다."), ok: t("완전히 지우기"), danger: true }))) return;
                            api.purge(x.name).then(() => { toast.success(t("지웠어요")); load(); }).catch((e) => toast.error(errMsg(e)));
                          }}>
                            {t("완전히 지우기")}
                          </Button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )
            ) : rows === null ? (
              <div className="vids-empty"><StateIcon s="running" /></div>
            ) : list.length === 0 ? (
              <div className="vids-empty is-box"><Icon n="film" s={28} /><p>{q || route !== "all" ? t("조건에 맞는 영상이 없습니다.") : t("아직 만든 영상이 없습니다. 홈에서 주제를 말하면 시작합니다.")}</p></div>
            ) : (
              <ul className="vids-list">
                {list.map((r) => {
                  const isOpen = open === r.id, run = busy[r.id];
                  return (
                    <li key={r.id} className={`vids-item ${isOpen ? "is-open" : ""} ${run ? "is-busy" : ""}`}>
                      <div className="vids-row" role="button" tabIndex={0} aria-expanded={isOpen}
                        onClick={() => toggle(r.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(r.id); } }}>
                        <div className="vids-thumb">{r.thumb ? <img src={F(r.thumb)} alt="" loading="lazy" /> : <Icon n="film" s={16} />}</div>
                        <div className="vids-name" title={`${r.id}${r.updated ? ` · ${ago(new Date(r.updated * 1000).toISOString())}` : ""}`}>{r.topic}</div>
                        <span className={`vids-route r-${r.route || "generate"}`} title={t(ROUTE_TX[r.route || "generate"])} />
                        {run && <span className="vids-live" title={run}><StateIcon s="running" /></span>}
                        <div className="vids-acts" onClick={(e) => e.stopPropagation()}>
                          <button type="button" className="vids-edit" onClick={() => nav(`/veditor/${r.id}`)} title={t("편집기에서 열기")} aria-label={t("편집기에서 열기")}>
                            <Icon n="pen" s={14} />
                          </button>
                          <button type="button" className="vids-del" onClick={() => delVideo(r)} title={t("휴지통으로")} aria-label={t("휴지통으로")}>
                            <Icon n="trash" s={14} />
                          </button>
                          <button type="button" className="vids-chev" onClick={() => toggle(r.id)} aria-label={isOpen ? t("파이프라인 접기") : t("파이프라인 펼치기")}>
                            <svg width="14" height="14" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                          </button>
                        </div>
                      </div>
                      {isOpen && (
                        <div className="vids-drop">
                          <PipelineGraph id={r.id} variant="full" onOpenEditor={() => nav(`/veditor/${r.id}`)} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
