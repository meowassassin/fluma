/* 에이전트 패널 — 모든 화면 오른쪽 같은 자리(도킹). 화면을 가리지 않는다.
   · 진행 중: 지금 하는 일 · 경과 시간 · 할 일 · 도구 단계 · 멈춤 · 추가 지시
   · 맥락 칩: 지금 고른 장면/요소가 자동으로 붙는다(× 로 뺄 수 있음)
   · 마지막 턴이 바꾼 파일은 한 번에 되돌릴 수 있다 */
import React, { createContext, memo, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { FlumaBounce, FlumaStrain, FlumaGlyph } from "../../ui/BrandIcons";
import { Button, IconButton, Menu, Spinner, Tip, composing, confirmDialog, cx } from "../../ui/kit";
import { connect, doing, resetSession, sendMessage, stopAgent, unqueueMessage, useSession, TOOL_KO, type LiveTurn } from "../../lib/agent";
import { api, errMsg, uploadFile } from "../../lib/api";
import { qc, qk, useActiveAgents, useProjects, useSkills } from "../../lib/queries";
import { useNavigate } from "react-router-dom";
import { useUi } from "../../lib/ui";
import type { ChatContext, ChatMessage, Todo } from "../../lib/types";
import { t } from "../../lib/i18n";

export interface AgentDockProps {
  sessionId: string;
  title?: string;
  /** 지금 화면 맥락 — 함수면 보내는 순간에 계산(재생 위치 등) */
  context?: ChatContext | (() => ChatContext);
  /** 지금 고른 것 — 칩으로 보이고 메시지에 맥락으로 붙는다 */
  chip?: { label: string; onClear: () => void } | null;
  hints?: string[];
  placeholder?: string;
  /** 한 번만 자동으로 보낼 메시지 (홈에서 시작) */
  autoSend?: { message: string; skill?: string | null } | null;
  onAutoSent?: () => void;
  /** 입력칸에 미리 넣을 글 */
  prefill?: string | null;
  onPrefillUsed?: () => void;
  /** dock = 오른쪽 도킹 창(접을 수 있음) · page = 화면 가운데 대화(홈) */
  layout?: "dock" | "page";
  /** 고른 스킬이 없을 때 쓰는 스킬 (홈 기획 대화 = plan) */
  defaultSkill?: string | null;
}

/* 답 안의 선택지 블록을 누르면 보낼 곳 */
const ChoiceCtx = createContext<((text: string) => void) | null>(null);
/* 답 안의 제목 · 설명 후보를 콘티(storyboards/<id>.json 의 title · caption · hashtags)에 바로 적용 */
const ApplyCtx = createContext<string | null>(null);
async function applyUpload(projectId: string, patch: { title?: string; caption?: string; hashtags?: string[] }) {
  try {
    const sb = await api.storyboard(projectId);
    await api.saveStoryboard(projectId, { ...sb, ...patch });
    qc.invalidateQueries({ queryKey: qk.storyboard(projectId) }); qc.invalidateQueries({ queryKey: qk.projects });
    toast.success(patch.title ? t("제목을 적용했어요") : t("설명을 적용했어요"));
  } catch (e) { toast.error(t("적용하지 못했어요"), { description: errMsg(e) }); }
}

const resolve = (c: AgentDockProps["context"]) => (typeof c === "function" ? c() : c);

export const AgentDock: React.FC<AgentDockProps> = (p) => {
  const open = useUi((s) => s.agentOpen);
  const setUi = useUi((s) => s.set);
  const s = useSession(p.sessionId);
  useEffect(() => connect(p.sessionId), [p.sessionId]);

  // 홈에서 넘어온 첫 메시지: 기록을 불러온 뒤, 진행 중 턴이 없을 때 한 번만
  const sent = useRef<object | null>(null);
  useEffect(() => {
    if (!p.autoSend || sent.current === p.autoSend || !s.loaded || s.live) return;
    sent.current = p.autoSend;
    sendMessage(p.sessionId, p.autoSend.message, { skill: p.autoSend.skill ?? null, context: resolve(p.context) });
    p.onAutoSent?.();
  }, [p.autoSend, s.loaded, s.live]); // eslint-disable-line react-hooks/exhaustive-deps

  const page = p.layout === "page";
  if (!open && !page) {
    // 접힘: 창이 있던 오른쪽 가장자리에 아이콘 손잡이만 남긴다(세로 글씨 없음). 레일의 '에이전트' 버튼 · Ctrl/⌘ J 와 같은 동작
    return (
      <aside className="dock-edge" aria-label={t("에이전트 (접힘)")}>
        <Tip label={t("에이전트 창 열기")} kbd="Mod+J" side="left">
          <button className="dock-edge-b" onClick={() => setUi({ agentOpen: true })} aria-label={t("에이전트 창 열기")}>
            <Icon n="sidebarR" s={16} />
            <span className="dock-edge-ic">{s.live ? <FlumaBounce s={18} tone="gray" /> : <Icon n="agent" s={16} />}</span>
          </button>
        </Tip>
      </aside>
    );
  }
  return (
    <aside className={cx("dock", page && "page-chat")} aria-label={t("에이전트")}>
      {!page && <header className="dock-h">
        <Icon n="agent" s={16} />
        <b>{p.title ?? t("에이전트")}</b>
        {s.live ? <span className="dock-state live"><FlumaBounce s={14} />{t("작업 중")}</span> : <span className="dock-state">{t("대기")}</span>}
        <span className="grow" />
        <Menu trigger={<IconButton icon="more" label={t("대화 메뉴")} size="sm" />} items={[
          { label: t("새 대화 시작"), icon: "plus", disabled: !!s.live, onSelect: async () => {
            if (!(await confirmDialog({ title: t("대화 기록을 지울까요?"), body: t("파일은 그대로 두고, 에이전트가 처음부터 다시 대화합니다."), ok: t("지우기"), danger: true }))) return;
            try { await resetSession(p.sessionId); } catch (e) { toast.error(errMsg(e)); }
          } },
        ]} />
        <IconButton icon="sidebarR" label={t("에이전트 창 닫기 (왼쪽 레일 ‘에이전트’로 다시 열기)")} kbd="Mod+J" size="sm" onClick={() => setUi({ agentOpen: false })} />
      </header>}
      <Elsewhere sessionId={p.sessionId} />
      <ApplyCtx.Provider value={p.sessionId.startsWith("_") ? null : p.sessionId}>
      <ChoiceCtx.Provider value={s.live ? null : (text) => sendMessage(p.sessionId, text, { skill: p.defaultSkill ?? null, context: resolve(p.context) })}>
        <Log sessionId={p.sessionId} messages={s.messages} live={s.live} loaded={s.loaded} hints={p.hints} context={p.context} defaultSkill={p.defaultSkill} />
      </ChoiceCtx.Provider>
      </ApplyCtx.Provider>
      {s.error && <div className="dock-err" role="alert"><Icon n="warn" s={14} />{s.error}</div>}
      <Composer {...p} live={!!s.live} sending={s.sending} stopping={s.stopping} />
    </aside>
  );
};

/* ---------- 다른 곳에서 일하는 에이전트 (이 창의 대화가 아닌 것) — 보고 · 멈출 수 있게 ---------- */
const Elsewhere: React.FC<{ sessionId: string }> = ({ sessionId }) => {
  const { data: active = [] } = useActiveAgents();
  const { data: projects = [] } = useProjects();
  const nav = useNavigate();
  const others = active.filter((a) => a.id !== sessionId);
  if (!others.length) return null;
  return (
    <div className="elsewhere" role="status">
      {others.map((a) => {
        const where = a.id.startsWith("_") ? t("작업 공간 (홈 · 트렌드 · 라이브러리)") : t("영상 “{title}”", { title: projects.find((x) => x.id === a.id)?.title ?? a.id });
        const now = a.tool ? doing([{ name: a.tool.name, input: a.tool.input }]) : null;
        return (
          <div key={a.id} className="elsewhere-r">
            {!a.id.startsWith("_") && a.skill !== "plan" ? <FlumaStrain s={14} /> : <FlumaBounce s={14} />}
            <span className="grow ellipsis" title={a.user}><b>{now ?? t("작업 중")}</b> <span className="faint">· {where}</span></span>
            <Button size="sm" variant="ghost" onClick={() => nav(a.id.startsWith("_") ? "/trends" : `/p/${a.id}`)}>{t("보기")}</Button>
            <Button size="sm" variant="danger" icon="stop" disabled={a.stopping} onClick={() => stopAgent(a.id)}>{a.stopping ? t("멈추는 중") : t("멈춤")}</Button>
          </div>
        );
      })}
    </div>
  );
};

/* ---------- 대화 기록 ---------- */
const Log: React.FC<{ sessionId: string; messages: ChatMessage[]; live: LiveTurn | null; loaded: boolean; hints?: string[]; context?: AgentDockProps["context"]; defaultSkill?: string | null }> = ({ sessionId, messages, live, loaded, hints, context, defaultSkill }) => {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  // 맨 아래를 보고 있을 때만 따라 내려간다
  useLayoutEffect(() => { const el = ref.current; if (el && stick.current) el.scrollTop = el.scrollHeight; }, [messages.length, live?.text.length, live?.tools.length, live?.todos]);
  const lastA = messages.reduce((a, m, i) => (m.role === "assistant" ? i : a), -1);
  // 진행 중인 턴의 사용자 메시지 · 추가 지시는 서버 기록에도 이미 들어 있다 → 진행 카드(Live)에서만 그린다(두 번 보이지 않게)
  const shown = live ? messages.slice(0, lastA + 1) : messages;
  return (
    <div className="dock-log" ref={ref} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48; }} aria-live="polite">
      {!loaded && <div className="dock-loading"><Spinner s={14} />{t("대화를 불러오는 중")}</div>}
      {loaded && shown.length === 0 && !live && (
        <div className="dock-empty">
          <p>{t("무엇이든 말로 시키세요. 지금 화면과 고른 것을 함께 봅니다.")}</p>
          {(hints ?? []).map((h) => <button key={h} className="hint" onClick={() => sendMessage(sessionId, h, { skill: defaultSkill ?? null, context: resolve(context) })}><Icon n="sparkle" s={13} />{h}</button>)}
        </div>
      )}
      {shown.map((m, i) => <Msg key={`${m.ts}-${i}`} m={m} sessionId={sessionId} canRevert={i === lastA && !live} />)}
      {live && <Live t={live} sessionId={sessionId} work={!sessionId.startsWith("_") && live.skill !== "plan"} />}
    </div>
  );
};

const Msg = memo<{ m: ChatMessage; sessionId: string; canRevert: boolean }>(({ m, sessionId, canRevert }) => {
  const [reverted, setReverted] = useState(false);
  if (m.role === "user") return <div className={cx("m-user", m.steer && "steer")}>{m.steer && <span className="m-tag">{t("추가 지시")}</span>}{m.skill && m.skill !== "plan" && <span className="m-tag">/{m.skill}</span>}<div className="m-bubble">{m.text}</div></div>;
  const tools = (m.tools ?? []).filter((x) => x.name !== "TodoWrite");
  const revert = async () => {
    if (!m.files?.length) return;
    if (!(await confirmDialog({ title: t("이 턴의 변경을 되돌릴까요?"), body: t("{n}개 파일을 턴 전 상태로 돌립니다. 그 뒤에 직접 고친 파일은 건드리지 않습니다.", { n: m.files.length }), ok: t("되돌리기") }))) return;
    try {
      const r = await api.revert(sessionId, m.files.map((f) => f.path));
      setReverted(true);
      if (r.conflicts?.length) toast.warning(t("{n}개 파일은 그 뒤에 바뀌어 그대로 두었어요", { n: r.conflicts.length }));
      else toast.success(t("되돌렸어요"));
    } catch (e) { toast.error(t("되돌리지 못했어요"), { description: errMsg(e) }); }
  };
  return (
    <div className="m-ai">
      {!!m.todos?.length && <Todos todos={m.todos} done />}
      {tools.length > 0 && <Steps tools={tools.map((x, k) => ({ ...x, id: String(k), done: true }))} />}
      {m.text && <div className="md"><Md text={m.text} /></div>}
      {m.error && <div className="m-err"><Icon n="warn" s={13} />{m.error}</div>}
      {m.stopped && <div className="m-meta">{t("멈춤")}</div>}
      {!!m.files?.length && (
        <div className="m-files">
          {m.files.slice(0, 8).map((f) => <span key={f.path} className={cx("file-chip", f.kind)} title={f.path}>{f.kind === "added" ? "+" : f.kind === "deleted" ? "−" : "✎"} {f.path}</span>)}
          {m.files.length > 8 && <span className="file-chip">+{m.files.length - 8}</span>}
          {canRevert && !reverted && <Button size="sm" variant="ghost" icon="undo" onClick={revert}>{t("이 턴 되돌리기")}</Button>}
          {reverted && <span className="m-meta">{t("되돌림")}</span>}
        </div>
      )}
      {m.durationMs != null && <div className="m-meta" title={m.cost != null ? t("비용 약 ${cost}", { cost: m.cost.toFixed(2) }) : undefined}>{fmtDur(m.durationMs)}</div>}
    </div>
  );
});
Msg.displayName = "Msg";

const Live: React.FC<{ t: LiveTurn; sessionId: string; work?: boolean }> = ({ t: turn, sessionId, work }) => {
  const now = doing(turn.tools);
  const tools = turn.tools.filter((x) => x.name !== "TodoWrite");
  return (
    <>
      <div className="m-user"><div className="m-bubble">{turn.user}</div></div>
      {turn.steers.map((s, i) => <div key={i} className="m-user steer"><span className="m-tag">{t("추가 지시")}</span><div className="m-bubble">{s}</div></div>)}
      {(turn.queued ?? []).map((s, i) => (
        <div key={`q${i}-${s.slice(0, 12)}`} className="m-user queued">
          <span className="m-tag">{t("다음 차례 — 지금 일이 끝나면 보냄")}<button className="q-x" onClick={() => unqueueMessage(sessionId, i)}><Icon n="close" s={11} />{t("보내기 취소")}</button></span>
          <div className="m-bubble">{s}</div>
        </div>))}
      <div className="m-ai live">
        <div className="live-h">{work ? <FlumaStrain s={18} /> : <FlumaBounce s={18} />}<b>{now ?? turn.status}</b><Elapsed from={turn.started} />{tools.length > 0 && <span className="faint">· {t("단계 {n}", { n: tools.length })}</span>}</div>
        {!!turn.memories?.length && <div className="m-meta" title={turn.memories.map((m) => `[${m.scope}] ${m.title}`).join("\n")}>{t("기억 {n}개를 참고하는 중", { n: turn.memories.length })}</div>}
        {turn.todos && <Todos todos={turn.todos} />}
        {tools.length > 0 && <Steps tools={tools} live />}
        {turn.text && <div className="md"><Md text={turn.text} /></div>}
      </div>
    </>
  );
};

const Elapsed: React.FC<{ from: number }> = ({ from }) => {
  const [, tick] = useState(0);
  useEffect(() => { const h = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(h); }, []);
  return <span className="faint mono">{fmtDur(Date.now() - from)}</span>;
};
const fmtDur = (ms: number) => { const s = Math.round(ms / 1000); return s < 60 ? t("{s}초", { s }) : t("{m}분 {s}초", { m: Math.floor(s / 60), s: s % 60 }); };

const Todos: React.FC<{ todos: Todo[]; done?: boolean }> = ({ todos, done }) => {
  const n = todos.filter((x) => x.status === "completed").length;
  return (
    <div className="todos">
      <div className="todos-h">{t("할 일")} <span className="faint">{n}/{todos.length}</span></div>
      {todos.map((x, i) => (
        <div key={i} className={cx("todo", x.status)}>
          <span className="todo-c">{x.status === "completed" ? <Icon n="check" s={12} /> : x.status === "in_progress" && !done ? <FlumaBounce s={12} label={t("진행 중")} /> : null}</span>
          <span>{x.status === "in_progress" && x.activeForm ? x.activeForm : x.content}</span>
        </div>
      ))}
    </div>
  );
};

const Steps: React.FC<{ tools: (LiveTurn["tools"][number])[]; live?: boolean }> = ({ tools, live }) => {
  const [open, setOpen] = useState(false);
  const shown = open ? tools : tools.slice(-3);
  return (
    <div className="steps">
      {tools.length > 3 && <button className="steps-more" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? t("접기") : t("단계 {n}개 모두 보기", { n: tools.length })}</button>}
      {shown.map((x) => <Step key={x.id} x={x} live={live} />)}
    </div>
  );
};
/** 한 단계 — 누르면 명령 · 경로 전체를 줄바꿈해서 펼친다(긴 명령이 잘려 안 보이던 문제) */
const Step: React.FC<{ x: LiveTurn["tools"][number]; live?: boolean }> = ({ x, live }) => {
  const [open, setOpen] = useState(false);
  const full = shortInput(x.input);
  return (
    <div className={cx("step", x.error && "err", !x.done && live && "run", open && "open")}>
      <button className="step-row" onClick={() => setOpen(!open)} aria-expanded={open} disabled={!full}>
        <span className="step-i">{!x.done && live ? <FlumaBounce s={12} label={t("진행 중")} /> : x.error ? <Icon n="close" s={11} /> : <Icon n="check" s={11} />}</span>
        <span className="step-n">{TOOL_KO[x.name] ? t(TOOL_KO[x.name]) : x.name}</span>
        {!open && <span className="step-a ellipsis">{full}</span>}
      </button>
      {open && <pre className="step-full">{full}</pre>}
    </div>
  );
};
const shortInput = (s: string) => {
  try { const o = JSON.parse(s); return o.command ?? o.file_path ?? o.pattern ?? o.query ?? o.url ?? s; } catch { return s; }
};

/* ---------- 입력 ---------- */
interface Att { key: string; name: string; kind: "video" | "image" | "audio"; status: "up" | "ok" | "err"; rel?: string; seq?: string; thumb?: string; error?: string }
const Composer: React.FC<AgentDockProps & { live: boolean; sending: boolean; stopping: boolean }> = ({ sessionId, context, chip, placeholder, prefill, onPrefillUsed, live, sending, stopping, defaultSkill }) => {
  const [text, setText] = useState("");
  const [skill, setSkill] = useState<string | null>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const { data: skills = [] } = useSkills();
  // 첨부: 사용자가 찍은 영상 · 사진을 이 영상(프로젝트)의 uploads 로 올리고, 보낼 때 정확한 경로를 메시지에 붙인다
  const canAttach = !sessionId.startsWith("_");
  const [atts, setAtts] = useState<Att[]>([]);
  const vidIn = useRef<HTMLInputElement>(null), imgIn = useRef<HTMLInputElement>(null), audIn = useRef<HTMLInputElement>(null);
  const attach = async (files: File[]) => {
    for (const f of files) {
      const key = `${f.name}-${f.size}-${Date.now()}`;
      setAtts((a) => [...a, { key, name: f.name, kind: f.type.startsWith("video") ? "video" : f.type.startsWith("audio") || /\.(mp3|m4a|wav|ogg|aac|flac)$/i.test(f.name) ? "audio" : "image", status: "up", thumb: f.type.startsWith("image") ? URL.createObjectURL(f) : undefined }]);
      try {
        const r = await uploadFile(sessionId, f) as { files: { name: string; kind: "image" | "video"; rel: string; seq?: string }[] };
        const hit = r.files.find((x) => x.name === f.name) ?? r.files.find((x) => x.name.endsWith(f.name.replace(/[^\w.가-힣-]/g, "_")));
        setAtts((a) => a.map((x) => (x.key === key ? { ...x, status: hit ? "ok" : "err", rel: hit?.rel, seq: hit?.seq, name: hit?.name ?? x.name } : x)));
        qc.invalidateQueries({ queryKey: qk.uploads(sessionId) });
      } catch (e) { setAtts((a) => a.map((x) => (x.key === key ? { ...x, status: "err", error: errMsg(e) } : x))); }
    }
  };
  const uploading = atts.some((a) => a.status === "up");
  useEffect(() => {
    if (!prefill) return;
    setText(prefill); onPrefillUsed?.();
    requestAnimationFrame(() => { ta.current?.focus(); ta.current?.setSelectionRange(prefill.length, prefill.length); });
  }, [prefill]); // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => { const el = ta.current; if (el) { el.style.height = "auto"; el.style.height = Math.min(220, el.scrollHeight) + "px"; } }, [text]);
  const send = async (interrupt = false) => {
    const ready = atts.filter((a) => a.status === "ok" && a.rel);
    const msg = text.trim() || (ready.length ? "첨부한 파일을 영상에 써 줘" : ""); if (!msg || uploading) return;
    const att = ready.length ? `[첨부 ${ready.length}개 — 이번 요청은 이 파일들로]\n${ready.map((a) => a.kind === "video"
      ? `- ${a.rel} (직접 찍은 영상 · 프레임: K.seq "${a.seq}" — 영상은 프레임으로 푸는 중일 수 있으니 meta.json 이 생긴 뒤에 쓴다)`
      : a.kind === "audio" ? `- ${a.rel} (배경음악 — 콘티 music: { "src": "public/${a.rel}" } · 시작 지점 start · 음량 gain_db)`
      : `- ${a.rel} (사진 · K.image)`).join("\n")}\n` : "";
    const ok = await sendMessage(sessionId, `${chip ? `[선택: ${chip.label}]\n` : ""}${att}${msg}`, { skill: skill ?? defaultSkill ?? null, context: resolve(context), interrupt });
    if (ok) { setText(""); setSkill(null); setAtts([]); }
  };
  return (
    <div className="composer">
      {(chip || skill || atts.length > 0) && (
        <div className="chips">
          {atts.map((a) => (
            <span key={a.key} className={cx("att-chip", a.status)} title={a.error ?? a.rel ?? a.name}>
              <span className="att-th">{a.thumb ? <img src={a.thumb} alt="" /> : <Icon n={a.kind === "video" ? "video" : a.kind === "audio" ? "volume" : "image"} s={13} />}</span>
              <span className="ellipsis">{a.name}</span>
              {a.status === "up" ? <FlumaBounce s={12} label={t("올리는 중")} /> : a.status === "err" ? <Icon n="warn" s={12} /> : null}
              <button aria-label={t("첨부 빼기")} onClick={() => setAtts((x) => x.filter((y) => y.key !== a.key))}><Icon n="close" s={11} /></button>
            </span>))}
          {chip && <span className="ctx-chip" title={t("메시지에 함께 보냄")}><Icon n="cursor" s={12} /><span className="ellipsis">{chip.label}</span><button aria-label={t("선택 빼기")} onClick={chip.onClear}><Icon n="close" s={11} /></button></span>}
          {skill && <span className="ctx-chip skill">/{skill}<button aria-label={t("스킬 빼기")} onClick={() => setSkill(null)}><Icon n="close" s={11} /></button></span>}
        </div>
      )}
      <div className={cx("composer-box", live && "live")}>
        <textarea ref={ta} rows={1} value={text} onChange={(e) => setText(e.target.value)} aria-label={t("에이전트에게 보낼 메시지")}
          placeholder={live ? t("Enter 추가 지시 · Ctrl+Enter 지금 하던 일 멈추고 바로 물어보기") : placeholder ?? t("무엇을 할까요?")}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !composing(e)) { e.preventDefault(); send(live && (e.ctrlKey || e.metaKey)); } }} />
        <div className="composer-bar">
          {canAttach && <>
            <Menu side="top" align="start" trigger={<IconButton icon="plus" label={t("첨부")} size="sm" />} items={[
              { label: t("동영상 첨부"), icon: "video", onSelect: () => vidIn.current?.click() },
              { label: t("이미지 첨부"), icon: "image", onSelect: () => imgIn.current?.click() },
              { label: t("음악 첨부"), icon: "volume", onSelect: () => audIn.current?.click() },
            ]} />
            <input ref={vidIn} type="file" multiple accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.m4v" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
            <input ref={imgIn} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
            <input ref={audIn} type="file" accept="audio/*,.mp3,.m4a,.wav,.ogg,.aac,.flac" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
          </>}
          <Menu align="start" trigger={<Button size="sm" variant="ghost" icon="wand" aria-label={t("스킬 고르기")}>{t("스킬")}</Button>} items={skills.length ? skills.map((k) => ({ label: `/${k.name}`, onSelect: () => setSkill(k.name) })) : [{ label: t("스킬 없음"), disabled: true, onSelect: () => {} }]} />
          <span className="grow" />
          <span className="composer-hint faint">{live ? t("Ctrl+Enter 끼어들기") : t("Enter 보내기 · Shift+Enter 줄바꿈")}</span>
          {live && text.trim() && <Tip label={t("지금 하던 일을 멈추고 이 말을 바로 보내기")} kbd="Mod+Enter"><Button size="sm" variant="secondary" icon="skipFwd" disabled={sending || uploading} onClick={() => send(true)}>{t("끼어들기")}</Button></Tip>}
          {live && <Button size="sm" variant="danger" icon="stop" disabled={stopping} onClick={async () => { if (!(await stopAgent(sessionId))) toast.info(t("이미 끝난 작업이에요")); }}>{stopping ? t("멈추는 중") : t("멈춤")}</Button>}
          <Tip label={live ? t("추가 지시 보내기") : t("보내기")} kbd="Enter">
            <button className={cx("btn", live ? "btn-agent" : "btn-primary", "glyph-btn")} disabled={(!text.trim() && !atts.some((a) => a.status === "ok")) || sending || uploading} onClick={() => send()} aria-label={live ? t("추가 지시 보내기") : t("보내기")}>
              {sending ? <FlumaBounce s={18} tone="onPrimary" label={t("보내는 중")} /> : <FlumaGlyph s={22} tone="onPrimary" />}
            </button>
          </Tip>
        </div>
      </div>
    </div>
  );
};

/* ---------- 작은 마크다운 (한 번 파싱해 기억) ---------- */
const inline = (body: string) => body.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g).map((p, k) => {
  if (p.startsWith("**")) return <strong key={k}>{p.slice(2, -2)}</strong>;
  if (p.startsWith("`")) return <code key={k}>{p.slice(1, -1)}</code>;
  const m = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(p);
  if (m) return <a key={k} href={m[2]} target="_blank" rel="noreferrer">{m[1]}</a>;
  return p;
});
export const Md = memo<{ text: string }>(({ text }) => {
  const lines = text.replace(/\n{3,}/g, "\n\n").split("\n");
  const out: React.ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*\|.*\|\s*$/.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { const c = lines[i].trim().slice(1, -1).split("|").map((x) => x.trim()); if (!c.every((x) => /^:?-{2,}:?$/.test(x))) rows.push(c); i++; }
      i--;
      out.push(<div key={i} className="md-tw"><table><tbody>{rows.map((r, k) => <tr key={k}>{r.map((c, n) => k === 0 ? <th key={n}>{inline(c)}</th> : <td key={n}>{inline(c)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^```/.test(line)) {
      const lang = line.slice(3).trim(); const buf: string[] = []; i++; while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      if (lang === "choices") { out.push(<Choices key={i} items={buf.map((b) => b.replace(/^\s*[-*•]\s*/, "").trim()).filter(Boolean)} />); continue; }
      if (lang === "brief") { out.push(<Brief key={i} rows={parseBrief(buf.join("\n"))} />); continue; }
      if (lang === "titles") { out.push(<Titles key={i} items={buf.map((b) => b.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim()).filter(Boolean)} />); continue; }
      if (lang === "desc") { out.push(<Desc key={i} text={buf.join("\n").trim()} />); continue; }
      out.push(<pre key={i}><code>{buf.join("\n")}</code></pre>); continue;
    }
    if (!line.trim()) { out.push(<div key={i} className="md-gap" />); continue; }
    const h = /^#{1,4}\s+(.*)/.exec(line);
    if (h) { out.push(<div key={i} className="md-h">{inline(h[1])}</div>); continue; }
    const li = /^(\s*)[-*•]\s+(.*)/.exec(line);
    if (li) { out.push(<div key={i} className="md-li" style={{ paddingLeft: 14 + li[1].length * 6 }}>{inline(li[2])}</div>); continue; }
    const ol = /^\s*(\d+)[.)]\s+(.*)/.exec(line);
    if (ol) { out.push(<div key={i} className="md-li ol" data-n={ol[1]}>{inline(ol[2])}</div>); continue; }
    out.push(<p key={i}>{inline(line)}</p>);
  }
  return <>{out}</>;
});
Md.displayName = "Md";

/* ---------- 기획 대화 블록: 선택지 · 기획 카드 ---------- */
/** 선택지 + 맨 아래 '직접 입력'(other) — 보기에 없는 요구는 그 자리에서 글로 써서 보낸다 */
const Choices: React.FC<{ items: string[] }> = ({ items }) => {
  const choose = useContext(ChoiceCtx);
  const [other, setOther] = useState<string | null>(null);
  const send = () => { const v = (other ?? "").trim(); if (v && choose) { choose(v); setOther(null); } };
  return (
    <div className="choices" role="group" aria-label={t("선택지")}>
      {items.map((it) => <button key={it} className="choice" disabled={!choose} onClick={() => choose?.(it)}><Icon n="chevron" s={12} />{inline(it)}</button>)}
      {other == null
        ? <button className="choice choice-other" disabled={!choose} onClick={() => setOther("")}><Icon n="pen" s={12} />{t("직접 입력 — 다른 요구사항 쓰기")}</button>
        : <div className="choice-in">
            <textarea autoFocus rows={2} className="in ta" value={other} onChange={(e) => setOther(e.target.value)} placeholder={t("원하는 것을 직접 써 주세요")} aria-label={t("다른 요구사항")}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !composing(e)) { e.preventDefault(); send(); } if (e.key === "Escape") setOther(null); }} />
            <div className="row end"><Button size="sm" variant="ghost" onClick={() => setOther(null)}>{t("취소")}</Button><Button size="sm" variant="primary" disabled={!other.trim() || !choose} onClick={send}>{t("보내기")}</Button></div>
          </div>}
    </div>
  );
};
export const parseBrief = (txt: string): [string, string][] => txt.split("\n").map((l) => { const k = l.indexOf(":"); return k > 0 ? [l.slice(0, k).trim(), l.slice(k + 1).trim()] as [string, string] : null; }).filter((x): x is [string, string] => !!x && !!x[0]);
export const Brief: React.FC<{ rows: [string, string][] }> = ({ rows }) => (
  <dl className="brief">{rows.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd className={v === "?" ? "faint" : undefined}>{v === "?" ? t("아직") : inline(v)}</dd></React.Fragment>)}</dl>
);
/** 대화에서 마지막 기획 카드 */
export const lastBrief = (texts: string[]): [string, string][] | null => {
  for (let i = texts.length - 1; i >= 0; i--) { const m = /```brief\n([\s\S]*?)```/.exec(texts[i] || ""); if (m) return parseBrief(m[1]); }
  return null;
};

/* ---------- 유튜브 제목 후보 · 설명 ---------- */
const Titles: React.FC<{ items: string[] }> = ({ items }) => {
  const pid = useContext(ApplyCtx);
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <div className="ytbox">
      <div className="ytbox-h"><Icon n="text" s={13} />{t("제목 후보")} <span className="faint">{t("누르면 이 영상 제목으로")}</span></div>
      {items.map((it) => (
        <button key={it} className={cx("yt-title", picked === it && "on")} disabled={!pid} onClick={async () => { if (!pid) return; await applyUpload(pid, { title: it.slice(0, 40) }); setPicked(it); }}>
          <span className="grow">{it}</span><span className="mono faint">{t("{n}자", { n: it.length })}</span>{picked === it && <Icon n="check" s={13} />}
        </button>))}
    </div>
  );
};
const Desc: React.FC<{ text: string }> = ({ text }) => {
  const pid = useContext(ApplyCtx);
  const tags = [...new Set(text.match(/#[^\s#]+/g) ?? [])].slice(0, 10);
  const body = text.replace(/(^|\s)#[^\s#]+/g, "").trim();
  return (
    <div className="ytbox">
      <div className="ytbox-h"><Icon n="list" s={13} />{t("설명")} <span className="faint">{t("{n}자", { n: body.length })}{tags.length ? ` · ${t("해시태그 {n}", { n: tags.length })}` : ""}</span></div>
      <p className="yt-desc">{body}</p>
      {tags.length > 0 && <div className="yt-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
      <div className="row end">
        <Button size="sm" variant="ghost" icon="copy" onClick={() => navigator.clipboard.writeText(text).then(() => toast.success(t("복사했어요")))}>{t("복사")}</Button>
        <Button size="sm" variant="secondary" icon="check" disabled={!pid} onClick={() => pid && applyUpload(pid, { caption: body.slice(0, 300), hashtags: tags })}>{t("이 영상에 적용")}</Button>
      </div>
    </div>
  );
};
