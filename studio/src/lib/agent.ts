/* 에이전트 대화 저장소 — 세션(영상 id 또는 _workspace)마다 SSE 하나, 상태는 여기 한 곳.
   화면은 필요한 값만 골라 구독한다(예전 무한 렌더 루프의 원인이던 콜백 → effect → setState 고리를 없앰). */
import { create } from "zustand";
import { api, errMsg } from "./api";
import { qc, qk } from "./queries";
import { t } from "./i18n";
import type { AgentEvent, ChatContext, ChatMessage, ChatTool, MemoryRef, Todo } from "./types";

export interface LiveTurn {
  user: string; skill: string | null; scene: number | null; started: number;
  text: string; status: string; tools: (ChatTool & { id: string; done: boolean })[]; steers: string[]; queued?: string[]; todos: Todo[] | null; memories?: MemoryRef[];
}
interface Session { messages: ChatMessage[]; live: LiveTurn | null; loaded: boolean; error: string | null; sending: boolean; stopping: boolean }
interface AgentState {
  sessions: Record<string, Session>;
  patch: (id: string, p: Partial<Session> | ((s: Session) => Partial<Session>)) => void;
}
const blank: Session = { messages: [], live: null, loaded: false, error: null, sending: false, stopping: false };

export const useAgentStore = create<AgentState>((set) => ({
  sessions: {},
  patch: (id, p) => set((st) => {
    const cur = st.sessions[id] ?? blank;
    const next = typeof p === "function" ? p(cur) : p;
    return { sessions: { ...st.sessions, [id]: { ...cur, ...next } } };
  }),
}));
export const useSession = (id: string) => useAgentStore((s) => s.sessions[id] ?? blank);
export const useAgentBusy = (id: string) => useAgentStore((s) => !!s.sessions[id]?.live);

function apply(cur: LiveTurn | null, ev: AgentEvent): LiveTurn | null {
  // 시작 시각은 서버 기준 — 화면을 옮겨 다시 붙으면 서버가 지난 이벤트를 다시 보내는데, 그때 시계가 0초로 돌아가지 않게
  if (ev.type === "start") return { user: ev.user, skill: ev.skill, scene: ev.scene, started: ev.at ?? Date.now(), text: "", status: t("시작"), tools: [], steers: [], todos: null, memories: ev.memories };
  if (!cur) return cur;
  switch (ev.type) {
    case "status": return { ...cur, status: t(ev.label) };
    case "text": return { ...cur, text: cur.text + ev.text, status: t("답을 쓰는 중") };
    case "tool_start": return { ...cur, tools: [...cur.tools, { id: ev.id, name: ev.name, input: "", done: false, t0: Date.now() }] };
    case "tool_use": return { ...cur, tools: cur.tools.map((t) => (t.id === ev.id ? { ...t, input: ev.input } : t)) };
    case "tool_result": return { ...cur, tools: cur.tools.map((t) => (t.id === ev.id ? { ...t, done: true, error: ev.error, out: ev.out ?? t.out } : t)) };
    case "todos": return { ...cur, todos: ev.todos };
    case "steer": return { ...cur, steers: [...cur.steers, ev.text] };
    case "queued": return { ...cur, queued: [...(cur.queued ?? []), ev.text] };
    case "unqueued": return { ...cur, queued: (cur.queued ?? []).filter((_, i) => i !== ev.index) };
    case "result": return { ...cur, status: ev.ok ? t("마무리하는 중") : t("실패") };
    default: return cur;
  }
}

/* ---------- 연결 (참조 수 세기: 여러 화면이 같은 세션을 봐도 SSE 는 하나) ---------- */
const conns = new Map<string, { es: EventSource; refs: number }>();
const endSubs = new Set<(id: string, files: { path: string; kind: string }[]) => void>();
export const onTurnEnd = (f: (id: string, files: { path: string; kind: string }[]) => void) => { endSubs.add(f); return () => { endSubs.delete(f); }; };

/** 기록을 다시 읽고 '작업 중' 여부를 서버 상태에 맞춘다 — 연결이 끊긴 사이 턴이 끝났거나(끝 신호를 못 받음) 서버가 다시 켜졌을 때 */
async function reload(id: string) {
  const { patch } = useAgentStore.getState();
  try {
    const h = await api.chat(id);
    patch(id, (s) => {
      if (!h.running) return { messages: h.messages, loaded: true, error: null, live: null, stopping: false };
      // 서버는 일하는데 시작 신호를 못 받은 경우: 마지막 사용자 메시지로 진행 중 표시를 세운다(이벤트가 오면 이어 채워짐)
      const lastUser = [...h.messages].reverse().find((m) => m.role === "user" && !m.steer);
      const live = s.live ?? { user: lastUser?.text ?? "", skill: null, scene: null, started: lastUser?.ts ?? Date.now(), text: "", status: t("작업 중"), tools: [], steers: [], todos: null };
      return { messages: h.messages, loaded: true, error: null, live: { ...live, queued: h.queued ?? live.queued } };
    });
  } catch (e) { patch(id, { loaded: true, error: errMsg(e) }); }
}

export function connect(id: string) {
  const c = conns.get(id);
  if (c) { c.refs++; return () => release(id); }
  const { patch } = useAgentStore.getState();
  reload(id);
  const es = new EventSource(`/api/projects/${id}/chat/events`);
  let frame = 0; let pending: AgentEvent[] = [];
  // 글자 조각이 많이 와도 한 프레임에 한 번만 상태를 바꾼다(스트리밍 중 버벅임 방지)
  const flush = () => {
    frame = 0; const evs = pending; pending = [];
    let ended: AgentEvent | null = null;
    patch(id, (s) => { let live = s.live; for (const ev of evs) { if (ev.type === "end") { ended = ev; live = null; } else live = apply(live, ev); } return ended && !live ? { live: null, stopping: false } : { live }; });
    if (ended) {
      const files = (ended as Extract<AgentEvent, { type: "end" }>).files ?? [];
      reload(id);
      qc.invalidateQueries({ queryKey: qk.projects });
      endSubs.forEach((f) => f(id, files));
    }
  };
  es.onmessage = (m) => {
    let ev: AgentEvent; try { ev = JSON.parse(m.data); } catch { return; }
    pending.push(ev);
    if (ev.type === "start" || ev.type === "end") { cancelAnimationFrame(frame); flush(); }
    else if (!frame) frame = requestAnimationFrame(flush);
  };
  // 자동 재연결. 다시 붙으면 서버가 진행 중 턴을 이어 보내지만, 끊긴 사이에 끝난 턴은 기록을 다시 읽어야 안다
  let dropped = false;
  es.onerror = () => { dropped = true; };
  es.onopen = () => { if (dropped) { dropped = false; reload(id); } };
  conns.set(id, { es, refs: 1 });
  return () => release(id);
}
function release(id: string) {
  const c = conns.get(id); if (!c) return;
  // 아무 화면도 안 보면 연결을 닫고 진행 중 표시도 비운다(옛 상태가 남지 않게). 다시 보면 reload 가 서버 상태로 맞춘다
  if (--c.refs <= 0) { c.es.close(); conns.delete(id); useAgentStore.getState().patch(id, { live: null, stopping: false }); }
}

/** interrupt: 작업 중이면 지금 턴을 멈추고 이 말을 바로 보낸다(Ctrl/⌘+Enter) */
export async function sendMessage(id: string, message: string, opts: { skill?: string | null; scene?: number | null; context?: ChatContext; interrupt?: boolean } = {}) {
  const { patch } = useAgentStore.getState();
  const s = useAgentStore.getState().sessions[id] ?? blank;
  if (!message.trim() || s.sending) return false;
  patch(id, { sending: true, error: null });
  try {
    await api.send(id, { message: message.trim(), skill: opts.skill ?? null, scene: opts.scene ?? null, steer: !!s.live, interrupt: !!s.live && !!opts.interrupt, context: opts.context });
    return true;
  } catch (e) { patch(id, { error: errMsg(e) }); return false; }
  finally { patch(id, { sending: false }); }
}
/** 멈춤: 누르면 바로 '멈추는 중'. 서버에 멈출 것이 없으면(이미 끝남) 화면을 서버 상태로 맞추고 false */
export async function stopAgent(id: string): Promise<boolean> {
  const { patch } = useAgentStore.getState();
  patch(id, { stopping: true });
  try {
    const r = await api.stop(id);
    if (!r.ok) { await reload(id); patch(id, { stopping: false }); }
    qc.invalidateQueries({ queryKey: qk.agentActive });
    return r.ok;
  } catch (e) { patch(id, { stopping: false, error: errMsg(e) }); return false; }
}
/** 줄 서 있던 추가 지시 하나를 보내기 취소 */
export async function unqueueMessage(id: string, index: number) {
  try { const r = await api.unqueue(id, index); if (!r.ok) await reload(id); return r.ok; }
  catch (e) { useAgentStore.getState().patch(id, { error: errMsg(e) }); return false; }
}
export async function resetSession(id: string) { await api.resetChat(id); useAgentStore.getState().patch(id, { messages: [], live: null, error: null }); await reload(id); }

/** 마지막 도구 호출을 사람 말로 */
export function doing(tools: (ChatTool & { done?: boolean })[]): string | null {
  const last = [...tools].reverse().find((x) => x.name !== "TodoWrite");
  if (!last) return null;
  const i = last.input || "";
  const rules: [RegExp, string][] = [
    [/trends\.py search/, "트렌드 쇼츠 찾는 중"], [/trend_analyze/, "쇼츠를 직접 보고 분석하는 중"], 
    [/research/, "자료 조사 중"], [/lint\.py/, "콘티 검사 중"], [/tts\.py|assemble_audio|voice/, "목소리 만드는 중"],
    [/produce\.py/, "영상 제작 중"], [/demo\.py|webrec|termrec/, "실제 화면 녹화 중"], [/still\.py/, "정지 화면으로 확인하는 중"], [/render\.py/, "영상 렌더 중"],
    [/capture\.py/, "화면 캡처 중"], [/memory\.py/, "기억 정리 중"], 
    [/compositions\//, "화면 · 움직임 짜는 중"], [/storyboards\//, "콘티 쓰는 중"], [/characters\//, "캐릭터 그리는 중"],
  ];
  for (const [re, label] of rules) if (re.test(i)) return t(label);
  if (last.name === "WebSearch" || last.name === "WebFetch") return t("웹에서 찾아보는 중");
  if (last.name === "Read" || last.name === "Grep" || last.name === "Glob") return t("파일 살펴보는 중");
  if (last.name === "Write" || last.name === "Edit") return t("파일 고치는 중");
  return t("작업 중");
}
/** 도구 이름(원문 한국어 — 화면에서 t() 로 감싼다) */
export const TOOL_KO: Record<string, string> = { Read: "읽기", Write: "쓰기", Edit: "고치기", Bash: "명령", Grep: "찾기", Glob: "파일 찾기", WebSearch: "웹 검색", WebFetch: "웹 읽기", TodoWrite: "할 일" };
