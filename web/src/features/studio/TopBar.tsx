/* 영상 화면 머리 — 위치(홈 / 제목) · 진행 단계 · 검사 · 확인(의도 · 시안 관문) · 렌더(주 행동, 오른쪽 위 한 자리) */
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { FlumaBounce, FlumaStrain } from "../../ui/BrandIcons";
import { Button, Dot, IconButton, Menu, Popover, Progress, Segmented, Tip, composing, confirmDialog, cx } from "../../ui/kit";
import { useQuery } from "@tanstack/react-query";
import { api, errMsg } from "../../lib/api";
import { clock } from "../../lib/clock";
import { qc, qk, useHasAudio, useLint, useProjects } from "../../lib/queries";
import { cancelJob, startRender, useProjectJob } from "../../lib/jobs";
import { sendMessage, useAgentBusy } from "../../lib/agent";
import { useUi } from "../../lib/ui";
import type { Storyboard } from "../../lib/types";
import { BgJobs } from "./BgJobs";
import { useProjectFiles } from "./ProjectTree";
import { t } from "../../lib/i18n";
import { isHard, patchStoryboard, startsOf, useStudio } from "./store";

export const TopBar: React.FC<{ sb: Storyboard | null; projectId: string }> = ({ sb, projectId }) => {
  const nav = useNavigate();
  const del = async () => {
    if (!(await confirmDialog({ title: t("이 영상을 휴지통으로 옮길까요?"), body: t("콘티 · 화면 구성 · 음성 · 렌더 · 대화가 함께 옮겨지고, 홈 → 휴지통에서 되돌릴 수 있습니다."), ok: t("휴지통으로"), danger: true }))) return;
    try { const r = await api.deleteProject(projectId); qc.invalidateQueries({ queryKey: qk.projects }); useUi.getState().set({ lastProject: null }); nav("/");
      toast(t("휴지통으로 옮겼어요"), { action: { label: t("되돌리기"), onClick: () => api.restore(r.trash).then(() => { qc.invalidateQueries({ queryKey: qk.projects }); nav(`/p/${projectId}`); }) } });
    } catch (e) { toast.error(t("옮기지 못했어요"), { description: errMsg(e) }); }
  };
  return (
    <header className="topbar">
      <nav className="crumb" aria-label={t("위치")}><Link to="/videos">{t("영상")}</Link><Icon n="chevron" s={12} /><Title sb={sb} projectId={projectId} /></nav>
      <Stepper sb={sb} projectId={projectId} />
      <span className="grow" />
      <Menu trigger={<IconButton icon="more" label={t("영상 메뉴")} />} items={[
        { label: t("단축키 보기"), icon: "keyboard", kbd: "?", onSelect: () => useUi.getState().set({ shortcutsOpen: true }) },
        "sep",
        { label: t("휴지통으로"), icon: "trash", danger: true, onSelect: del },
      ]} />
      <RenderButton sb={sb} projectId={projectId} />
    </header>
  );
};

/** 렌더 — 최종 렌더 관문(의도 · 시안 확인)을 사용자가 이 자리에서 확인한다(누르는 사람 = 사용자). 확인할 게 없으면 바로 렌더 */
async function renderWithGate(projectId: string, sb: Storyboard) {
  let g: { intent: boolean; draft: boolean } | null = null;
  try { g = await api.gate(projectId); } catch { /* 관문 상태를 못 읽으면 서버(render.py)가 판단 */ }
  if (g && (!g.intent || !g.draft)) {
    const it = sb.intent;
    const body = [
      !g.intent && (it?.summary ? `${t("의도")}: ${it.summary}` : t("의도 카드가 아직 없어요 — 에이전트에게 정리를 맡길 수 있어요")),
      !g.draft && t("시안(장면 1~3)을 편집 화면에서 보고 괜찮으면 확인하세요"),
    ].filter(Boolean).join("\n");
    if (!(await confirmDialog({ title: t("이 방향으로 최종 렌더할까요?"), body, ok: t("확인하고 렌더") }))) return;
    try {
      if (!g.intent && it?.summary) await api.gateConfirm(projectId, "intent");
      if (!g.draft) await api.gateConfirm(projectId, "draft");
    } catch (e) { toast.error(t("확인하지 못했어요"), { description: errMsg(e) }); return; }
  }
  startRender(projectId, sb.title);
}

/* 확인(관문 — scripts/gate.py): 의도 카드를 사용자가 확인하고, 시안(장면 1~3)을 보고 '좋다'고 해야 최종 렌더가 풀린다.
   의도 · 시안이 흐린 채 전체를 만들고 고치면 공수가 든다 */
const GateBar: React.FC<{ sb: Storyboard; projectId: string }> = ({ sb, projectId }) => {
  const job = useProjectJob(projectId);
  const dep = JSON.stringify([sb.intent ?? null, sb.scenes.slice(0, 3).map((s) => [s.visual, s.elements, s.screen, s.beat]), job?.status]);
  const { data: g, refetch } = useQuery({ queryKey: ["gate", projectId, dep], queryFn: ({ signal }) => api.gate(projectId, signal), staleTime: 10_000 });
  const [busy, setBusy] = useState<string | null>(null);
  if (!g) return null;
  const it = sb.intent;
  const confirm = async (kind: "intent" | "draft") => {
    setBusy(kind);
    try { await api.gateConfirm(projectId, kind); await refetch(); toast.success(kind === "intent" ? t("의도를 확인했어요") : t("시안을 승인했어요 — 최종 렌더 · 생성이 열렸어요")); }
    catch (e) { toast.error(t("확인하지 못했어요"), { description: errMsg(e) }); } finally { setBusy(null); }
  };
  return (
    <div className="gatebar" aria-label={t("제작 확인")}>
      <Popover width={360} trigger={<button className={cx("gate-chip", g.intent ? "ok" : "todo")}><Icon n={g.intent ? "check" : "info"} s={12} />{t("의도")}</button>}>
        <div className="lint-pop">
          <div className="lint-h">{g.intent ? t("의도 카드 · 확인됨") : t("의도 카드 · 확인 전")}</div>
          {it?.summary ? <>
            <p><b>{it.summary}</b></p>
            {it.reference_use && <p className="faint small">{t("레퍼런스: {v}", { v: it.reference_use })}</p>}
            {!!it.must?.length && <p className="small">{t("꼭: {v}", { v: it.must.join(" · ") })}</p>}
            {!!it.must_not?.length && <p className="small">{t("하지 말 것: {v}", { v: it.must_not.join(" · ") })}</p>}
            {!g.intent && <div className="row end"><Button size="sm" variant="primary" loading={busy === "intent"} onClick={() => confirm("intent")}>{t("이 의도가 맞아요")}</Button></div>}
          </> : <>
            <p className="faint small">{t("아직 의도 카드가 없어요. 누구에게 무엇을 어떤 느낌으로, 레퍼런스에서 무엇을 가져올지 에이전트가 정리해 보여 줍니다.")}</p>
            <div className="row end"><Button size="sm" variant="agent" icon="agent" onClick={() => sendMessage(projectId, t("이 영상의 의도 카드(콘티 intent: summary · reference_use · must · must_not)를 지금까지 대화와 내 지적을 바탕으로 채워서 보여 줘. 확인은 내가 할게."), { context: { menu: "studio" } })}>{t("에이전트에게 정리시키기")}</Button></div>
          </>}
        </div>
      </Popover>
      <Popover width={340} trigger={<button className={cx("gate-chip", g.draft ? "ok" : "todo")}><Icon n={g.draft ? "check" : "info"} s={12} />{t("시안")}</button>}>
        <div className="lint-pop">
          <div className="lint-h">{g.draft ? t("시안(장면 1~3) · 승인됨") : t("시안(장면 1~3) · 승인 전")}</div>
          <p className="faint small">{t("최종 렌더 전에 앞 장면 셋을 먼저 보고 방향을 확인합니다. 승인 뒤 장면 1~3 화면이 바뀌면 다시 확인합니다.")}</p>
          {!g.draft && <div className="row end">
            <Button size="sm" variant="ghost" onClick={() => startRender(projectId, sb.title, { draft13: true })}>{t("시안 렌더")}</Button>
            {job?.status === "done" && job.url && <Button size="sm" variant="ghost" icon="external" onClick={() => window.open(job.url, "_blank")}>{t("시안 보기")}</Button>}
            <Button size="sm" variant="primary" loading={busy === "draft"} onClick={() => confirm("draft")}>{t("시안 좋아요")}</Button>
          </div>}
        </div>
      </Popover>
    </div>
  );
};

const Title: React.FC<{ sb: Storyboard | null; projectId: string }> = ({ sb, projectId }) => {
  const [edit, setEdit] = useState(false);
  const { data: list } = useProjects();
  const title = sb?.title ?? list?.find((p) => p.id === projectId)?.title ?? t("새 영상");
  if (!edit || !sb) return <button className="title-btn" onClick={() => sb && setEdit(true)} title={sb ? t("제목 바꾸기") : undefined} disabled={!sb}><b className="ellipsis">{title}</b></button>;
  return <input className="in title-in" autoFocus defaultValue={title} aria-label={t("영상 제목")}
    onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== title) patchStoryboard({ title: v }); setEdit(false); }}
    onKeyDown={(e) => { if (e.key === "Enter" && !composing(e)) (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setEdit(false); }} />;
};

/* 진행 단계: 무엇이 끝났고 무엇이 남았는지 한눈에 */
const Stepper: React.FC<{ sb: Storyboard | null; projectId: string }> = ({ sb, projectId }) => {
  const { data: lint } = useLint(projectId, !!sb);
  const { data: audio } = useHasAudio(projectId);
  const { data: list } = useProjects();
  const job = useProjectJob(projectId);
  const busy = useAgentBusy(projectId);
  const sum = list?.find((p) => p.id === projectId);
  const hard = (lint?.lint ?? []).filter(isHard);
  const { data: files } = useProjectFiles(projectId);
  const craft = (sb?.engine ?? "craft") === "craft";
  const motion = !!files?.stages.some((x) => x.stage === "motion");
  const steps: { n: string; st: "done" | "warn" | "todo"; tip: string; extra?: React.ReactNode }[] = [
    { n: t("콘티"), st: sb ? "done" : "todo", tip: sb ? t("{n}장면", { n: sb.scenes.length }) : t("에이전트가 조사 후 장면을 나눕니다") },
    { n: t("검사"), st: !sb ? "todo" : hard.length ? "warn" : "done", tip: !sb ? t("규칙 검사") : hard.length ? t("걸린 규칙 {n}개 — 눌러서 보기", { n: hard.length }) : t("통과"), extra: sb && <LintPop projectId={projectId} sb={sb} n={hard.length} /> },
    { n: t("목소리"), st: audio ? "done" : "todo", tip: audio ? t("나레이션 · 단어 자막") : t("음성을 만들고 장면 길이를 맞춥니다") },
    craft
      ? { n: t("화면"), st: motion ? "done" : sb ? "todo" : "todo", tip: motion ? t("그래픽(EffectCraft) 준비됨") : t("초안을 렌더하면 장면 그래픽이 만들어집니다") }
      : { n: t("화면"), st: sb?.template === "Composed" ? "done" : sb ? "warn" : "todo", tip: sb?.template === "Composed" ? t("이 영상 전용 화면 구성") : sb ? t("템플릿 화면") : t("장면마다 화면을 짭니다") },
    { n: "렌더", st: (sum?.renders?.final ?? 0) > 0 || job?.status === "done" ? "done" : "todo", tip: (sum?.renders?.final ?? 0) > 0 ? t("최종 {n}개", { n: sum!.renders!.final }) : t("오른쪽 위 ‘렌더’") },
  ];
  return (
    <>
    <ol className="stepper" aria-label={t("진행 단계")}>
      {busy && <li className="step-agent"><FlumaStrain s={14} />{t("에이전트 작업 중")}</li>}
      {steps.map((s) => (
        <li key={s.n} className={cx("stp", s.st)}>
          {s.extra ?? <Tip label={s.tip}><span className="stp-in"><i />{s.n}</span></Tip>}
        </li>
      ))}
    </ol>
    <BgJobs project={projectId} compact />
    </>
  );
};

const LintPop: React.FC<{ projectId: string; sb: Storyboard; n: number }> = ({ projectId, sb, n }) => {
  const { data } = useLint(projectId);
  const busy = useAgentBusy(projectId);
  const [open, setOpen] = useState(false);
  const items = data?.lint ?? [];
  const hard = items.filter(isHard), soft = items.filter((l) => !isHard(l) && l.message !== "통과");
  const starts = startsOf(sb);
  const go = (scene: number | null) => { if (scene == null) return; useStudio.getState().set({ scene, pick: null }); clock.pause(); clock.seek(starts[scene] + 0.3); setOpen(false); };
  return (
    <Popover open={open} onOpenChange={setOpen} width={380} trigger={<button className="stp-in" aria-label={n ? t("검사 {n}개 걸림", { n }) : t("검사 통과")}><i />{t("검사")}{n > 0 && <b className="stp-n">{n}</b>}</button>}>
      <div className="lint-pop">
        <div className="lint-h">{n ? t("고쳐야 할 것 {n}개", { n }) : t("검사 통과")}</div>
        {[...hard, ...soft].map((l, k) => (
          <button key={k} className={cx("lint-r", isHard(l) ? "hard" : "soft")} onClick={() => go(l.scene)} disabled={l.scene == null}>
            <Icon n={isHard(l) ? "warn" : "info"} s={13} /><span className="mono">{l.code}</span><span className="grow">{l.message}</span>{l.scene != null && <span className="faint">{t("장면 {n}", { n: l.scene + 1 })}</span>}
          </button>
        ))}
        {!items.length && <p className="faint">{t("걸린 규칙이 없어요.")}</p>}
        {n > 0 && (
          <div className="row end">
            <Button size="sm" variant="agent" icon="agent" disabled={busy} onClick={async () => {
              const list = hard.map((l) => `- ${l.code}${l.scene != null ? ` (${t("장면 {n}", { n: l.scene + 1 })})` : ""}: ${l.message}`).join("\n");
              if (await sendMessage(projectId, `${t("검사에 걸린 {n}개를 고쳐 줘. 고친 뒤 lint 를 다시 돌려 통과할 때까지.", { n })}\n${list}`, { context: { menu: "studio" } })) { useUi.getState().set({ agentOpen: true }); setOpen(false); toast.success(t("에이전트에게 맡겼어요")); }
            }}>{busy ? t("에이전트 작업 중") : t("에이전트에게 고치게 하기")}</Button>
          </div>
        )}
      </div>
    </Popover>
  );
};

const RenderButton: React.FC<{ sb: Storyboard | null; projectId: string }> = ({ sb, projectId }) => {
  const job = useProjectJob(projectId);
  const running = job && (job.status === "running" || job.status === "queued");
  if (running) {
    return (
      <div className="render-chip" role="status">
        <FlumaStrain s={18} label={t("렌더 중")} />
        <div className="render-chip-t"><b>{job!.status === "queued" ? t("렌더 대기") : t("렌더 중")}</b><span className="faint ellipsis">{job!.stage}</span></div>
        <Progress value={job!.progress} />
        <IconButton icon="stop" label={t("렌더 취소")} size="sm" tone="danger" onClick={async () => { if (await confirmDialog({ title: t("렌더를 취소할까요?"), ok: t("취소하기"), cancel: t("계속"), danger: true })) cancelJob(projectId); }} />
      </div>
    );
  }
  return (
    <div className="row tight">
      {job?.status === "done" && job.url && <Button size="md" variant="ghost" icon="external" onClick={() => window.open(job.url, "_blank")}>{t("결과 보기")}</Button>}
      <Tip label={t("영상을 MP4 로 만듭니다 (보통 30초~2분)")} kbd="R">
        <Button variant="primary" icon="export" disabled={!sb} onClick={() => sb && renderWithGate(projectId, sb)}>{t("렌더")}</Button>
      </Tip>
      <RenderOptions />
    </div>
  );
};

/* 렌더 출력 설정 — 해상도(9:16 세로 기준) · 화질 · 초당 프레임. 브라우저에 기억 */
const SIZES = [{ value: "720", label: "720p", title: "720×1280 — 가볍게 미리 공유" }, { value: "1080", label: "1080p", title: "1080×1920 — 쇼츠 · 릴스 표준" },
  { value: "1440", label: "2K", title: "1440×2560 — 화면을 크게 그려 글자 · 도형이 더 선명" }, { value: "2160", label: "4K", title: "2160×3840 — 가장 선명, 렌더가 2~4배 오래 걸림" }];
const RenderOptions: React.FC = () => {
  const o = useUi((s) => s.renderOpts);
  const set = (p: Partial<typeof o>) => useUi.getState().set({ renderOpts: { ...o, ...p } });
  const [open, setOpen] = useState(false);
  const label = `${SIZES.find((x) => x.value === o.size)?.label ?? "1080p"} · ${o.fps ?? 30}fps`;
  return (
    <Popover open={open} onOpenChange={setOpen} width={340} trigger={<button className="render-opt" aria-label={t("렌더 설정: {v}", { v: label })}><span className="mono">{label}</span><Icon n="down" s={12} /></button>}>
      <div className="ropt">
        <div className="ropt-t">{t("렌더 설정")} <span className="faint">{t("다음 렌더부터")}</span></div>
        <label className="ropt-r"><span>{t("해상도")}</span><Segmented aria-label={t("해상도")} size="sm" value={o.size ?? "1080"} onChange={(v) => set({ size: v as typeof o.size })} options={SIZES.map((x) => ({ ...x, title: t(x.title) }))} /></label>
        <label className="ropt-r"><span>{t("화질")}</span><Segmented aria-label={t("화질")} size="sm" value={o.quality ?? "high"} onChange={(v) => set({ quality: v as typeof o.quality })}
          options={[{ value: "standard", label: t("보통"), title: t("CRF 21 — 용량 작게") }, { value: "high", label: t("높음"), title: t("CRF 18 — 권장") }, { value: "max", label: t("최고"), title: t("CRF 15 — 용량 큼") }]} /></label>
        <label className="ropt-r"><span>{t("프레임")}</span><Segmented aria-label={t("초당 프레임")} size="sm" value={String(o.fps ?? 30)} onChange={(v) => set({ fps: Number(v) as 30 | 60 })}
          options={[{ value: "30", label: "30fps" }, { value: "60", label: "60fps", title: t("움직임이 더 부드럽고 렌더는 2배 걸림") }]} /></label>
        <p className="faint small">{t("2K · 4K 는 화면을 그 크기로 그려서 뽑아 글자 · 선이 실제로 선명해집니다(사진 · 올린 영상은 원본 화질까지).")}</p>
      </div>
    </Popover>
  );
};
