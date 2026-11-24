/* 홈 = 만들기. 한가운데 로고와 입력 하나만. 만든 영상은 '영상' 화면(/videos)에서.
   엔진 · 템플릿 같은 내부 사정은 여기 두지 않는다(설정으로). */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FlumaMark, Icon } from "../../ui/Icon";
import { Button, IconButton, Menu, Tip, composing, confirmDialog, cx } from "../../ui/kit";
import { FlumaGlyph } from "../../ui/BrandIcons";
import { errMsg } from "../../lib/api";
import { qc, useChats, useProducing, useStoryboard } from "../../lib/queries";
import { useUi } from "../../lib/ui";
import { AgentDock, Brief, lastBrief } from "../agent/AgentDock";
import { AttachChips, AttachMenu, attachNote, useAttachments } from "../agent/attachments";
import { BgJobs } from "../studio/BgJobs";
import { PipelineGraph } from "../videos/PipelineGraph";
import { resetSession, useSession } from "../../lib/agent";
import { FlumaBounce, FlumaStrain } from "../../ui/BrandIcons";
import { t } from "../../lib/i18n";


/* ---------- 홈 = 기획 대화 ----------
   처음: 로고 + 입력. 보내면 이 자리에서 대화가 열린다(편집기로 바로 가지 않음).
   대화: 왼쪽 대화 목록 · 가운데 기획 대화(plan 스킬: 선택지 · 기획 카드 · 훅 채점) · 오른쪽 콘티 보드(단계 · 기획 카드 · 장면).
   콘티가 검사를 통과하면 에이전트가 그대로 음성 · 화면을 만들고, 왼쪽 레일 '영상'에 제작 중인 수가 뜬다. */
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
  const [id, setId] = useState(newId);                 // 첨부를 올릴 곳이 있어야 해서 보내기 전에 정한다
  const att = useAttachments(id);
  const [drop, setDrop] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { ta.current?.focus(); }, []);
  useEffect(() => {
    const pre = params.get("prefill");
    if (pre) setText(pre);
    if (params.get("new")) { setText(""); att.clear(); setId(newId()); }   // 새 영상: 쓰던 글 · 첨부를 비운다(이미 홈이어도)
    if (params.get("new") || pre) { ta.current?.focus(); setParams({}, { replace: true }); }
  }, [params, setParams]);
  // 입력창 높이는 고정 — 글이 길어지면 창이 커지지 않고 안에서 스크롤(.prompt textarea)

  const start = () => {
    const msg = text.trim() || (att.ready.length ? "첨부한 파일로 영상을 기획해 줘" : ""); if (!msg || att.uploading) { ta.current?.focus(); return; }
    // 형식 · 길이는 기획 대화(plan 스킬)가 주제에서 정하고 선택지로 묻는다 — 첫 화면에서 고르게 하지 않음
    nav(`/?c=${id}`, { state: { autoSend: { message: `${attachNote(att.ready)}${msg}`, skill: "plan" } } });
  };

  return (
    <div className="page-body home">
      <section className="hero">
        <h1 className="hero-logo"><FlumaMark s={88} /><span className="sr-only">Fluma</span></h1>
        <div className={cx("prompt", drop && "drop")}
          onDragOver={(e) => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); setDrop(true); } }} onDragLeave={() => setDrop(false)}
          onDrop={(e) => { e.preventDefault(); setDrop(false); const f = [...e.dataTransfer.files].filter((x) => /^(image|video|audio)\//.test(x.type)); if (f.length) att.attach(f); }}>
          {att.atts.length > 0 && <div className="chips prompt-chips"><AttachChips atts={att.atts} onRemove={att.remove} /></div>}
          <textarea ref={ta} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("만들 영상 주제")}
            placeholder={t("어떤 영상을 만들까요? 주제만 말해도 기획부터 같이 짜요")}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !composing(e)) { e.preventDefault(); start(); } }} />
          <div className="prompt-bar">
            <AttachMenu attach={att.attach} />
            <span className="grow" />
            <Tip label={t("기획 시작")} kbd="Enter"><button className="btn btn-primary glyph-btn glyph-btn-lg" onClick={start} disabled={att.uploading || (!text.trim() && !att.ready.length)} aria-label={t("기획 시작")}><FlumaGlyph s={30} tone="onPrimary" /></button></Tip>
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
      <IconButton icon="plus" label={t("새 영상 기획")} tipSide="right" onClick={() => nav("/?new=1")} />
    </nav>
  );
  return (
    <nav className="chats" aria-label={t("영상 대화")}>
      <div className="chats-h">
        <button className="chats-new" onClick={() => nav("/?new=1")}><Icon n="plus" s={14} />{t("새 영상 기획")}</button>
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
          context={{ menu: produced ? "studio" : "plan", note: produced ? undefined : "홈 기획 대화 — plan 스킬(.claude/skills/plan/SKILL.md)을 따른다. 경로(material · clip)와 추천 선택지를 보여 주고 사용자 확인을 받아 진행한다." }}
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
  const s = useSession(id);
  const brief = useMemo(() => lastBrief([...s.messages.filter((m) => m.role === "assistant").map((m) => m.text || ""), s.live?.text ?? ""]), [s.messages, s.live?.text]);
  const open = useUi((u) => u.boardOpen);
  const setOpen = (v: boolean) => useUi.getState().set({ boardOpen: v });

  if (!open) return (
    <aside className="sboard closed" aria-label={t("진행 보드 (접힘)")}>
      <IconButton icon="sidebarR" label={t("진행 보드 펼치기")} tipSide="left" onClick={() => setOpen(true)} />
      {producing ? <FlumaStrain s={16} /> : null}
    </aside>
  );

  return (
    <aside className="sboard" aria-label={t("파이프라인 보드")}>
      <div className="sb-top">
        <b className="sb-title" style={{ fontSize: 13, fontWeight: 700 }}>{t("진행 상태 그래프")}</b>
        <span className="grow" />
        <IconButton icon="sidebarR" label={t("보드 접기")} size="sm" tipSide="left" onClick={() => setOpen(false)} />
      </div>
      <div className="sb-body">
        <BgJobs project={id} />
        {producing && <div className="sb-prod"><FlumaStrain s={16} /><span>{t("제작 중 — 음성 · 화면을 만들고 있어요")}</span></div>}
        <PipelineGraph
          id={id}
          variant="panel"
          orientation="vertical"
          onOpenEditor={() => { useUi.getState().set({ lastProject: id }); nav(`/p/${id}`); }}
        />
        {brief && <section className="sb-sec"><h4>{t("기획 카드")}</h4><Brief rows={brief} /></section>}
        {sb && (
          <section className="sb-sec">
            <h4>{t("콘티")} <span className="faint">{sb.title} · {t("{n}초", { n: sb.duration_sec })} · {t("{n}장면", { n: sb.scenes.length })}</span></h4>
            <ol className="sb-scenes">
              {sb.scenes.map((sc, k) => (
                <li key={k}>
                  <span className="sb-n mono">{k + 1}</span>
                  <div className="sb-b">
                    <div className="sb-h"><b>{ROLE_KO[sc.role] ? t(ROLE_KO[sc.role]) : sc.role}</b><span className="mono faint">{t("{n}초", { n: Math.round(sc.sec * 10) / 10 })}</span></div>
                    {sc.caption && <p className="sb-cap">{sc.caption}</p>}
                    {sc.narration && <p className="sb-nar">“{sc.narration}”</p>}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
      <div className="sb-acts">
        <Button variant="secondary" icon="external" onClick={() => { useUi.getState().set({ lastProject: id }); nav(`/p/${id}`); }}>{t("편집기에서 열기")}</Button>
      </div>
    </aside>
  );
};
const ROLE_KO: Record<string, string> = { hook: "훅", step: "단계", reveal: "공개", payoff: "결론", verdict: "결론", outro: "맺음", cta: "행동", problem: "고민", benefit: "이점", proof: "증거", compare: "비교", context: "맥락", item: "항목", explain: "설명", twist: "반전" };

