/* 홈 = 만들기. 한가운데 로고와 입력 하나만. 만든 영상은 '영상' 화면(/videos)에서.
   엔진 · 템플릿 같은 내부 사정은 여기 두지 않는다(설정으로). */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { FlumaMark, Icon } from "../../ui/Icon";
import { Button, EmptyState, IconButton, Menu, Segmented, Skeleton, Tag, Tip, composing, confirmDialog, cx } from "../../ui/kit";
import { FlumaGlyph } from "../../ui/BrandIcons";
import { api, errMsg } from "../../lib/api";
import { qc, qk, useChats, useLint, useProducing, useProjects, useStoryboard } from "../../lib/queries";
import { useUi } from "../../lib/ui";
import { AgentDock, Brief, lastBrief } from "../agent/AgentDock";
import { BgJobs } from "../studio/BgJobs";
import { resetSession, sendMessage, useSession } from "../../lib/agent";
import { FlumaBounce, FlumaStrain } from "../../ui/BrandIcons";
import type { ProjectSummary } from "../../lib/types";
import { t, useLang } from "../../lib/i18n";

const FORMAT_KO: Record<string, string> = { compare: "비교", concept: "개념", ad: "광고", emotional: "감성", daily: "시세", countdown: "순위", mythbust: "오해 풀기", fix: "해결", series: "시리즈" };

/* ---------- 홈 = 기획 대화 ----------
   처음: 로고 + 입력. 보내면 이 자리에서 대화가 열린다(편집기로 바로 가지 않음).
   대화: 왼쪽 대화 목록 · 가운데 기획 대화(plan 스킬: 선택지 · 기획 카드 · 훅 채점) · 오른쪽 콘티 보드(단계 · 기획 카드 · 장면).
   '제작 시작'을 누르면 음성 · 화면을 만들기 시작하고, 왼쪽 레일 '영상'에 제작 중인 수가 뜬다. */
export const HomePage: React.FC = () => {
  const [params] = useSearchParams();
  const c = params.get("c");
  return (
    <div className="page home-page">
      <ChatList cur={c} />
      {c ? <HomeChat key={c} id={c} /> : <HomeStart />}
    </div>
  );
};

const newId = () => {
  const d = new Date();
  const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `${date}-s${Date.now().toString(36).slice(-6)}-01`;
};

const HomeStart: React.FC = () => {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { ta.current?.focus(); }, []);
  useEffect(() => {
    const pre = params.get("prefill");
    if (pre) setText(pre);
    if (params.get("new") || pre) { ta.current?.focus(); setParams({}, { replace: true }); }
  }, [params, setParams]);
  // 입력창 높이는 고정 — 글이 길어지면 창이 커지지 않고 안에서 스크롤(.prompt textarea)

  const start = () => {
    const msg = text.trim(); if (!msg) { ta.current?.focus(); return; }
    // 형식 · 길이는 기획 대화(plan 스킬)가 주제에서 정하고 선택지로 묻는다 — 첫 화면에서 고르게 하지 않음
    nav(`/?c=${newId()}`, { state: { autoSend: { message: msg, skill: "plan" } } });
  };

  return (
    <div className="page-body home">
      <section className="hero">
        <h1 className="hero-logo"><FlumaMark s={88} /><span className="sr-only">Fluma</span></h1>
        <div className="prompt">
          <textarea ref={ta} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("만들 영상 주제")}
            placeholder={t("어떤 영상을 만들까요? 주제만 말해도 기획부터 같이 짜요")}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !composing(e)) { e.preventDefault(); start(); } }} />
          <div className="prompt-bar">
            <span className="grow" />
            <Tip label={t("기획 시작")} kbd="Enter"><button className="btn btn-primary glyph-btn glyph-btn-lg" onClick={start} disabled={!text.trim()} aria-label={t("기획 시작")}><FlumaGlyph s={30} tone="onPrimary" /></button></Tip>
          </div>
        </div>
      </section>
    </div>
  );
};

/* 왼쪽: 대화 목록 */
const ChatList: React.FC<{ cur: string | null }> = ({ cur }) => {
  const { data: chats = [] } = useChats();
  const producing = useProducing();
  const nav = useNavigate();
  const open = useUi((s) => s.chatsOpen);
  const toggle = () => useUi.getState().set({ chatsOpen: !open });
  const del = async (c: { id: string; title: string; storyboard: boolean }) => {
    if (!(await confirmDialog({ title: t("“{title}” 대화 기록을 지울까요?", { title: c.title }), ok: t("지우기"), danger: true,
      body: c.storyboard ? t("대화만 지워지고 콘티 · 화면 · 영상은 그대로 남습니다(‘영상’에서 볼 수 있어요).") : t("아직 콘티가 없는 기획 대화라 대화와 함께 사라집니다.") }))) return;
    try {
      await resetSession(c.id);
      qc.invalidateQueries({ queryKey: ["chats"] });
      if (cur === c.id) nav("/");
      toast.success(t("대화 기록을 지웠어요"));
    } catch (e) { toast.error(t("지우지 못했어요"), { description: errMsg(e) }); }
  };
  if (!open) return (
    <nav className="chats closed" aria-label={t("영상 대화 (접힘)")}>
      <IconButton icon="sidebarL" label={t("대화 목록 펼치기")} tipSide="right" onClick={toggle} />
      <IconButton icon="plus" label={t("새 영상 기획")} tipSide="right" onClick={() => nav("/")} />
    </nav>
  );
  return (
    <nav className="chats" aria-label={t("영상 대화")}>
      <div className="chats-h">
        <button className="chats-new" onClick={() => nav("/")}><Icon n="plus" s={14} />{t("새 영상 기획")}</button>
        <IconButton icon="sidebarL" label={t("대화 목록 접기")} tipSide="right" onClick={toggle} />
      </div>
      <div className="chats-l">
        {chats.map((c) => {
          const st = producing.includes(c.id) ? "제작 중" : c.running ? "답하는 중" : c.composed ? "완성" : c.storyboard ? "콘티" : "기획";
          return (
            <div key={c.id} className={cx("chat-i", cur === c.id && "on")} role="button" tabIndex={0} onClick={() => nav(`/?c=${c.id}`)}
              onKeyDown={(e) => { if (e.key === "Enter") nav(`/?c=${c.id}`); }}>
              <span className="chat-row"><span className="ellipsis grow">{c.title}</span>
                <span onClick={(e) => e.stopPropagation()}><Menu side="right" align="start" trigger={<IconButton className="chat-more" icon="more" label={t("대화 메뉴")} size="sm" tipSide="right" />} items={[
                  ...(c.storyboard ? [{ label: t("편집기에서 열기"), icon: "film", onSelect: () => nav(`/p/${c.id}`) }] : []),
                  { label: t("대화 기록 지우기"), icon: "trash", danger: true, disabled: c.running, onSelect: () => del(c) },
                ]} /></span></span>
              <span className={cx("chat-st", st === "제작 중" && "prod", st === "완성" && "done")}>{st === "제작 중" ? <FlumaStrain s={11} /> : st === "답하는 중" ? <FlumaBounce s={11} /> : null}{t(st)}</span>
            </div>
          );
        })}
        {!chats.length && <p className="faint small chats-empty">{t("아직 대화가 없어요. 가운데에 주제를 적어 보세요.")}</p>}
      </div>
    </nav>
  );
};

const PRODUCE = "제작 시작: produce 스킬대로 지금 콘티를 Craft 파이프라인으로 만들어 줘 — 음성(assemble_audio) → 장면 재료(materials: 숫자는 chart, 근거는 doc_quote, 인물 · 사물은 illustrate 스킬로 새로 그린 SVG) → lint → 초안 렌더(render.py --draft) → 정지 화면 확인. 콘티 내용은 바꾸지 말고, 막히면 멈추고 알려 줘.";

/* 가운데 대화 + 오른쪽 콘티 보드 */
const HomeChat: React.FC<{ id: string }> = ({ id }) => {
  const nav = useNavigate();
  const loc = useLocation();
  const [autoSend, setAutoSend] = useState<{ message: string; skill?: string | null } | null>(() => (loc.state as { autoSend?: { message: string; skill?: string } } | null)?.autoSend ?? null);
  const { data: chats = [] } = useChats();
  const producing = useProducing().includes(id);
  const sum = chats.find((c) => c.id === id);
  const produced = producing || !!sum?.audio || !!sum?.composed;
  return (
    <>
      <div className="home-chat">
        <AgentDock layout="page" sessionId={id} defaultSkill={produced ? null : "plan"}
          context={{ menu: produced ? "studio" : "plan", note: produced ? undefined : "홈 기획 대화 — plan 스킬. 콘티 초안까지만, 음성 · 화면은 사용자가 '제작 시작'을 누른 뒤" }}
          autoSend={autoSend} onAutoSent={() => { setAutoSend(null); nav(`/?c=${id}`, { replace: true, state: null }); }}
          placeholder={produced ? t("영상에 대해 더 말해 주세요 — 편집기에서 장면별로 고칠 수도 있어요") : t("답하거나 선택지를 누르세요. 예: 훅은 B안, 20초로")} />
      </div>
      <StoryBoard id={id} produced={produced} producing={producing} />
    </>
  );
};

const StoryBoard: React.FC<{ id: string; produced: boolean; producing: boolean }> = ({ id, produced, producing }) => {
  const nav = useNavigate();
  const { data: sb } = useStoryboard(id);
  const { data: lint } = useLint(id, !!sb);
  const { data: chats = [] } = useChats();
  const s = useSession(id);
  const sum = chats.find((c) => c.id === id);
  const brief = useMemo(() => lastBrief([...s.messages.filter((m) => m.role === "assistant").map((m) => m.text || ""), s.live?.text ?? ""]), [s.messages, s.live?.text]);
  const hard = (lint?.lint ?? []).filter((l) => l.code && !l.code.startsWith("T") && l.message !== "통과").length;
  const steps: [string, boolean][] = [["기획", !!brief || !!sb], ["콘티", !!sb], ["검사", !!sb && hard === 0], ["목소리", !!sum?.audio], ["화면", !!sum?.composed]];
  const open = useUi((u) => u.boardOpen);
  const setOpen = (v: boolean) => useUi.getState().set({ boardOpen: v });
  const start = async () => {
    if (await sendMessage(id, PRODUCE, { skill: "produce", context: { menu: "studio" } })) toast.success(t("제작을 시작했어요"), { description: t("왼쪽 ‘영상’ 아이콘에 진행 중인 수가 떠요. 여기서 계속 대화해도 됩니다.") });
  };
  if (!open) return (
    // 접힘: 오른쪽 가장자리 손잡이 — 진행 단계 점과 제작 중 표시만
    <aside className="sboard closed" aria-label={t("콘티 보드 (접힘)")}>
      <IconButton icon="sidebarR" label={t("콘티 보드 펼치기")} tipSide="left" onClick={() => setOpen(true)} />
      {producing ? <FlumaStrain s={16} /> : null}
      <ol className="sb-dots">{steps.map(([n, ok]) => <li key={n} className={cx(ok && "ok")} title={t(n)} />)}</ol>
    </aside>
  );
  return (
    <aside className="sboard" aria-label={t("콘티 보드")}>
      <div className="sb-top">
        <ol className="sb-steps">{steps.map(([n, ok], k) => <li key={n} className={cx(ok && "ok", !ok && steps.slice(0, k).every((x) => x[1]) && "now")}><i />{t(n)}</li>)}</ol>
        <IconButton icon="sidebarR" label={t("콘티 보드 접기")} size="sm" tipSide="left" onClick={() => setOpen(false)} />
      </div>
      <div className="sb-body">
      <BgJobs project={id} />
      {producing && <div className="sb-prod"><FlumaStrain s={16} /><span>{t("제작 중 — 음성 · 화면을 만들고 있어요")}</span></div>}
      {brief && <section className="sb-sec"><h4>{t("기획 카드")}</h4><Brief rows={brief} /></section>}
      {sb ? (
        <section className="sb-sec">
          <h4>{t("콘티")} <span className="faint">{sb.title} · {t("{n}초", { n: sb.duration_sec })} · {t("{n}장면", { n: sb.scenes.length })} · {hard ? t("검사 {n}개 걸림", { n: hard }) : t("검사 통과")}</span></h4>
          <ol className="sb-scenes">
            {sb.scenes.map((sc, k) => (
              <li key={k}>
                <span className="sb-n mono">{k + 1}</span>
                <div className="sb-b">
                  <div className="sb-h"><b>{ROLE_KO[sc.role] ? t(ROLE_KO[sc.role]) : sc.role}</b><span className="mono faint">{t("{n}초", { n: Math.round(sc.sec * 10) / 10 })}</span></div>
                  {sc.caption && <p className="sb-cap">{sc.caption}</p>}
                  {sc.narration && <p className="sb-nar">“{sc.narration}”</p>}
                </div>
              </li>))}
          </ol>
        </section>
      ) : !brief && <EmptyState compact icon="list" title={t("콘티가 여기 생겨요")} body={t("대화로 훅 · 길이 · 장면을 정하면 이 자리에 장면 카드가 채워집니다.")} />}
      {sb && (
        <section className="sb-sec">
          <h4>{t("업로드 정보")} <span className="faint">{t("유튜브 · 쇼츠")}</span></h4>
          <dl className="brief sb-up">
            <dt>{t("제목")}</dt><dd>{sb.title || <span className="faint">{t("아직")}</span>} <button className="sb-copy" aria-label={t("제목 복사")} onClick={() => navigator.clipboard.writeText(sb.title || "").then(() => toast.success(t("복사했어요")))}><Icon n="copy" s={12} /></button></dd>
            <dt>{t("설명")}</dt><dd>{sb.caption ? <span className="sb-cap2">{sb.caption}</span> : <span className="faint">{t("아직")}</span>}</dd>
            {!!sb.hashtags?.length && <><dt>{t("태그")}</dt><dd>{sb.hashtags.join(" ")}</dd></>}
          </dl>
          <div className="row end">
            {(sb.caption || sb.title) && <Button size="sm" variant="ghost" icon="copy" onClick={() => navigator.clipboard.writeText(`${sb.title}\n\n${sb.caption ?? ""}\n${(sb.hashtags ?? []).join(" ")}`).then(() => toast.success(t("제목 · 설명을 복사했어요")))}>{t("모두 복사")}</Button>}
            <Button size="sm" variant="secondary" icon="sparkle" disabled={!!s.live} onClick={() => sendMessage(id, "이 영상의 유튜브 제목 후보 3개와 설명 · 해시태그를 titles · desc 블록으로 줘.", { skill: produced ? null : "plan", context: { menu: produced ? "studio" : "plan" } })}>{t("제목 · 설명 후보 받기")}</Button>
          </div>
        </section>
      )}
      </div>
      <div className="sb-acts">
        {sb && !produced && <Button variant="primary" icon="render" disabled={!!s.live || hard > 0} onClick={start} title={hard ? t("검사에 걸린 것을 먼저 고쳐요") : undefined}>{t("제작 시작")}</Button>}
        {sb && <Button variant="secondary" icon="external" onClick={() => { useUi.getState().set({ lastProject: id }); nav(`/p/${id}`); }}>{t("편집기에서 열기")}</Button>}
      </div>
    </aside>
  );
};
const ROLE_KO: Record<string, string> = { hook: "훅", step: "단계", reveal: "공개", payoff: "결론", verdict: "결론", outro: "맺음", cta: "행동", problem: "고민", benefit: "이점", proof: "증거", compare: "비교", context: "맥락", item: "항목", explain: "설명", twist: "반전" };

/* ---------- 영상 목록 ---------- */
type Filter = "all" | "working" | "rendered" | "trash";
export const Projects: React.FC = () => {
  const { data, isLoading, error } = useProjects();
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const list = useMemo(() => (data ?? []).filter((p) => !p.id.startsWith("_"))
    .filter((p) => !q || `${p.title} ${p.id}`.toLowerCase().includes(q.toLowerCase()))
    .filter((p) => filter === "all" || (filter === "rendered" ? (p.renders?.final ?? 0) > 0 : filter === "working" ? !(p.renders?.final) : true))
    .sort((a, b) => (a.updated < b.updated ? 1 : -1)), [data, q, filter]);
  const counts = useMemo(() => {
    const ps = (data ?? []).filter((p) => !p.id.startsWith("_"));
    return { all: ps.length, rendered: ps.filter((p) => (p.renders?.final ?? 0) > 0).length, working: ps.filter((p) => !p.renders?.final).length };
  }, [data]);
  return (
    <section className="home-sec">
      <div className="home-sec-h">
        <h2>{t("내 영상")}</h2>
        <Segmented aria-label={t("영상 거르기")} size="sm" value={filter} onChange={(v) => setFilter(v as Filter)} options={[
          { value: "all", label: t("전체 {n}", { n: counts.all }) }, { value: "working", label: t("작업 중 {n}", { n: counts.working }) },
          { value: "rendered", label: t("렌더됨 {n}", { n: counts.rendered }) }, { value: "trash", label: t("휴지통") }]} />
        <span className="grow" />
        {filter !== "trash" && <label className="search"><Icon n="search" s={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("제목 찾기")} aria-label={t("영상 제목 찾기")} /></label>}
      </div>
      {filter === "trash" ? <Trash /> : isLoading ? (
        <div className="cards">{[0, 1, 2, 3].map((i) => <div key={i} className="pcard"><Skeleton h="100%" r={10} className="pcard-skel" /></div>)}</div>
      ) : error ? <EmptyState icon="warn" title={t("영상 목록을 불러오지 못했어요")} body={errMsg(error)} action={<Button onClick={() => qc.invalidateQueries({ queryKey: qk.projects })}>{t("다시 시도")}</Button>} />
        : !list.length ? <EmptyState icon="film" title={q ? t("맞는 영상이 없어요") : t("아직 만든 영상이 없어요")} body={q ? t("다른 낱말로 찾아보세요.") : t("홈에서 주제를 쓰고 만들기를 누르면 첫 영상이 시작됩니다.")} />
          : <div className="cards">{list.map((p) => <ProjectCard key={p.id} p={p} />)}</div>}
    </section>
  );
};

const ProjectCard: React.FC<{ p: ProjectSummary }> = ({ p }) => {
  const nav = useNavigate();
  const rendered = (p.renders?.final ?? 0) > 0;
  const producing = useProducing().includes(p.id) || !!p.draft;
  const stage = rendered ? 3 : p.composed ? 2 : 1;
  const [img, setImg] = useState(rendered);
  const open = () => { useUi.getState().set({ lastProject: p.id }); nav(`/p/${p.id}`); };
  const del = async () => {
    if (!(await confirmDialog({ title: t("“{title}”을(를) 휴지통으로 옮길까요?", { title: p.title || p.id }), body: t("콘티 · 화면 구성 · 음성 · 렌더 · 대화가 함께 옮겨지고, 휴지통에서 되돌릴 수 있습니다."), ok: t("휴지통으로"), danger: true }))) return;
    try {
      const r = await api.deleteProject(p.id);
      qc.invalidateQueries({ queryKey: qk.projects });
      if (useUi.getState().lastProject === p.id) useUi.getState().set({ lastProject: null });
      toast(t("휴지통으로 옮겼어요"), { action: { label: t("되돌리기"), onClick: () => api.restore(r.trash).then(() => qc.invalidateQueries({ queryKey: qk.projects })).catch((e) => toast.error(errMsg(e))) } });
    } catch (e) { toast.error(t("옮기지 못했어요"), { description: errMsg(e) }); }
  };
  return (
    <article className="pcard">
      <button className="pcard-hit" onClick={open} aria-label={t("{title} 열기", { title: p.title || t("제목 없음") })}>
        <div className="pcard-poster">
          {img ? <img src={`/api/projects/${p.id}/cover`} alt="" loading="lazy" onError={() => setImg(false)} /> : <span className="pcard-ph">{p.title || t("새 영상")}</span>}
          {rendered && <span className="pcard-done" title={t("최종 영상 있음")}><Icon n="play" s={12} /></span>}
          {p.duration_sec > 0 && <span className="pcard-dur mono">{t("{n}초", { n: Math.round(p.duration_sec) })}</span>}
          {/* 진행: 콘티 · 화면 · 완성 세 칸 — 포스터 아래 가장자리에 얇게 */}
          <span className="pcard-pips" aria-label={t("진행 {n}/3", { n: stage })}>{[0, 1, 2].map((k) => <i key={k} className={k < stage ? "on" : undefined} />)}</span>
        </div>
        <div className="pcard-b">
          <b className="pcard-t">{p.title || t("제목 없음")}</b>
          <span className="pcard-m">{producing ? <span className="pcard-prod"><FlumaStrain s={12} />{t("만드는 중")}</span> : <span className={cx("pcard-stage", rendered && "done")}>{rendered ? t("완성") : p.composed ? t("화면까지") : t("콘티")}</span>}
            <span>{[FORMAT_KO[p.format] ? t(FORMAT_KO[p.format]) : p.format, ago(p.updated)].filter(Boolean).join(" · ")}</span></span>
        </div>
      </button>
      <Menu trigger={<IconButton className="pcard-more" icon="more" label={t("영상 메뉴")} size="sm" />} items={[
        { label: t("열기"), icon: "film", onSelect: open },
        "sep",
        { label: t("휴지통으로"), icon: "trash", danger: true, onSelect: del },
      ]} />
    </article>
  );
};

const Trash: React.FC = () => {
  const { data = [], isLoading, refetch } = useQuery({ queryKey: ["trash"], queryFn: () => api.trash() });
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast.success(ok); refetch(); qc.invalidateQueries({ queryKey: qk.projects }); } catch (e) { toast.error(errMsg(e)); } };
  if (isLoading) return <Skeleton h={120} />;
  if (!data.length) return <EmptyState icon="trash" title={t("휴지통이 비었어요")} body={t("지운 영상은 여기로 옮겨지고, 되돌릴 수 있어요.")} />;
  return (
    <div className="trash">
      {data.map((x) => (
        <div key={x.name} className="trash-r">
          <Icon n="film" s={14} /><b className="ellipsis">{x.title || x.id}</b><span className="faint">{ago(x.deletedAt)} · {t("파일 {n}개", { n: x.files.length })}</span>
          <span className="grow" />
          <Button size="sm" icon="undo" onClick={() => act(() => api.restore(x.name), t("되돌렸어요"))}>{t("되돌리기")}</Button>
          <Button size="sm" variant="danger" onClick={async () => {
            if (await confirmDialog({ title: t("“{title}”을(를) 완전히 지울까요?", { title: x.title || x.id }), body: t("되돌릴 수 없습니다."), ok: t("완전히 지우기"), danger: true })) act(() => api.purge(x.name), t("지웠어요"));
          }}>{t("완전히 지우기")}</Button>
        </div>
      ))}
    </div>
  );
};

const LOCALE = { ko: "ko-KR", en: "en-US", zh: "zh-CN" } as const;
export const fmtViews = (v: number | null | undefined) => {
  if (v == null) return "–";
  // 영어는 K · M(천 단위), 한국어 · 중국어는 만 · 억(万 · 亿)
  if (useLang.getState().lang === "en") return v >= 1e3 ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v) : v.toLocaleString("en-US");
  return v >= 1e8 ? t("{n}억", { n: (v / 1e8).toFixed(1) }) : v >= 1e4 ? t("{n}만", { n: Math.round(v / 1e4).toLocaleString() }) : v.toLocaleString();
};
export const ago = (iso: string) => {
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  return m < 1 ? t("방금") : m < 60 ? t("{n}분 전", { n: Math.round(m) }) : m < 1440 ? t("{n}시간 전", { n: Math.round(m / 60) }) : m < 1440 * 7 ? t("{n}일 전", { n: Math.round(m / 1440) }) : new Date(iso).toLocaleDateString(LOCALE[useLang.getState().lang], { month: "short", day: "numeric" });
};
