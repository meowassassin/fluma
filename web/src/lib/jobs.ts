/* 오래 걸리는 작업(렌더 등) 상태 — 어느 화면에서 봐도 같은 진행률. 끝나면 토스트로 알리고 결과로 바로 이동.
   서버: POST /api/render → {jobId}, SSE /api/jobs/:id/events (log · progress · done · failed · canceled), DELETE /api/jobs/:id */
import { create } from "zustand";
import { toast } from "sonner";
import { type RenderOpts, api, errMsg } from "./api";
import { qc, qk } from "./queries";
import { useUi } from "./ui";
import type { Job, JobEvent } from "./types";
import { t } from "./i18n";

export interface JobView { id: string; project: string; type: string; status: Job["status"]; progress: number | null; stage: string; url?: string; error?: string; started: number; log: string[] }
interface JobsState { byProject: Record<string, JobView | undefined>; set: (p: string, j: JobView | undefined) => void }
export const useJobs = create<JobsState>((set) => ({
  byProject: {},
  set: (p, j) => set((s) => ({ byProject: { ...s.byProject, [p]: j } })),
}));
export const useProjectJob = (p: string) => useJobs((s) => s.byProject[p]);

const streams = new Map<string, EventSource>();

function follow(project: string, jobId: string, title?: string) {
  if (streams.has(jobId)) return;
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  streams.set(jobId, es);
  const upd = (p: Partial<JobView>) => { const cur = useJobs.getState().byProject[project]; if (cur && cur.id === jobId) useJobs.getState().set(project, { ...cur, ...p }); };
  const close = () => { es.close(); streams.delete(jobId); };
  es.onmessage = (m) => {
    let ev: JobEvent; try { ev = JSON.parse(m.data); } catch { return; }
    const cur = useJobs.getState().byProject[project];
    if (ev.type === "log") upd({ log: [...(cur?.log ?? []).slice(-199), ev.line], status: "running" });
    else if (ev.type === "progress") upd({ progress: ev.progress, stage: ev.stage || cur?.stage || "", status: "running" });
    else if (ev.type === "done") {
      upd({ status: "done", progress: 1, url: ev.url, stage: t("완료") }); close();
      qc.invalidateQueries({ queryKey: qk.projects });
      toast.success(title ? t("렌더 완료 · {title}", { title }) : t("렌더 완료"), { action: ev.url ? { label: t("열기"), onClick: () => window.open(ev.url, "_blank") } : undefined, duration: 10000 });
    } else if (ev.type === "failed") {
      upd({ status: "failed", error: ev.error || t("렌더 실패") }); close();
      toast.error(t("렌더 실패"), { description: (ev.error || "").slice(0, 200) });
    } else if (ev.type === "canceled") { upd({ status: "canceled", stage: t("취소됨") }); close(); }
  };
  es.addEventListener("end", close);
  es.onerror = () => {
    // 서버가 다시 켜지면 작업 상태를 다시 물어 본다
    if (es.readyState === EventSource.CLOSED) { close(); api.jobs(project).then((js) => { const j = js.find((x) => x.id === jobId); if (!j) upd({ status: "failed", error: t("서버가 다시 시작돼 작업을 잃었습니다") }); }).catch(() => {}); }
  };
}

export async function startRender(project: string, title?: string, extra: Partial<RenderOpts> = {}) {
  try {
    const { jobId } = await api.render(project, { ...useUi.getState().renderOpts, ...extra });
    useJobs.getState().set(project, { id: jobId, project, type: "render", status: "queued", progress: null, stage: t("대기 중"), started: Date.now(), log: [] });
    follow(project, jobId, title);
  } catch (e) { toast.error(t("렌더를 시작하지 못했습니다"), { description: errMsg(e) }); }
}
export async function cancelJob(project: string) {
  const j = useJobs.getState().byProject[project]; if (!j) return;
  try { await api.cancelJob(j.id); } catch (e) { toast.error(t("취소하지 못했습니다"), { description: errMsg(e) }); }
}
/** 편집기를 열 때 이미 돌고 있는 작업에 다시 붙는다 */
export async function attachJobs(project: string) {
  try {
    const js = await api.jobs(project);
    const run = js.filter((j) => j.type === "render" && (j.status === "running" || j.status === "queued")).pop();
    if (run) { useJobs.getState().set(project, { id: run.id, project, type: run.type, status: run.status, progress: run.progress, stage: run.stage || "", started: Date.now(), log: [] }); follow(project, run.id); }
  } catch { /* 작업 목록이 없어도 편집은 된다 */ }
}
