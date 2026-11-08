/* 백그라운드 작업(3D 렌더) 진행 — 에이전트 대화와 따로, 영상마다. 끝나면 사라지고 실패하면 한동안 남는다 */
import React from "react";
import { FlumaStrain } from "../../ui/BrandIcons";
import { IconButton, Tip, cx } from "../../ui/kit";
import { api } from "../../lib/api";
import { useBgJobs } from "../../lib/queries";
import { t } from "../../lib/i18n";

export const BgJobs: React.FC<{ project: string; compact?: boolean }> = ({ project, compact }) => {
  const { data = [] } = useBgJobs(project);
  const recent = Date.now() - 10 * 60_000;
  // 실패는 10분 동안만, 그리고 같은 작업을 다시 해서 성공했으면 숨김
  const ok = new Set(data.filter((j) => j.status === "done").map((j) => j.label));
  const shown = data.filter((j) => j.status === "running" || j.status === "queued" || (j.status === "failed" && !ok.has(j.label) && ((j as { ended?: number }).ended ?? 0) > recent));
  if (!shown.length) return null;
  return (
    <div className={cx("bgjobs", compact && "compact")} role="status" aria-label={t("백그라운드 작업")}>
      {shown.map((j) => (
        <div key={j.id} className={cx("bgjob", j.status)}>
          {j.status === "failed" ? <span className="bgjob-x">!</span> : <FlumaStrain s={14} label={j.label} />}
          <Tip label={j.status === "failed" ? (j.error || t("실패")) : j.stage}><span className="bgjob-t ellipsis">{j.status === "queued" ? t("{label} · 대기", { label: j.label }) : j.status === "failed" ? t("{label} · 실패", { label: j.label }) : j.stage || j.label}</span></Tip>
          {j.status !== "failed" && <span className="bgjob-bar"><i style={{ width: `${Math.round((j.progress ?? 0) * 100)}%` }} /></span>}
          {j.status !== "failed" && <span className="mono faint">{Math.round((j.progress ?? 0) * 100)}%</span>}
          {j.status !== "failed" && <IconButton icon="stop" label={t("이 작업 취소")} size="sm" onClick={() => api.cancelJob(j.id).catch(() => {})} />}
        </div>))}
    </div>
  );
};
