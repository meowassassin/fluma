/* 설정 = 갈아 끼우는 기반(에이전트 · 렌더 엔진 · 음성 · 스톡 영상)과 기억. 구역은 주소(/settings/:section).
   바꾸면 바로 저장하고, 머리줄에 저장 상태를 보여 준다(실패하면 토스트). 지우기 · 설치는 확인을 받는다. */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { EngineIcon, modelIconSrc } from "../../ui/EngineIcon";
import { Button, EmptyState, Field, Popover, Segmented, Select, Skeleton, Spinner, Switch, Tag, confirmDialog, cx } from "../../ui/kit";
import { api, errMsg } from "../../lib/api";
import { qc, qk, useEngines, useSettings } from "../../lib/queries";
import type { EngineMeta, Settings } from "../../lib/types";
import { McpSec } from "./McpSec";
import { YoutubeSec } from "./YoutubeSec";
import { LANGS, agentLang, t, useLang, type Lang } from "../../lib/i18n";
import { sapi, type AgentInfo, type GenKey, type Mem, type Voice } from "./api";

type Sec = "agent" | "videogen" | "media" | "youtube" | "memory" | "mcp" | "about";
type MediaTab = "voice" | "music" | "stock";
interface AgentCfg { cli: string; claudeModel: string; codexModel: string; agyModel?: string; effort: string }
type Save = "idle" | "saving" | "saved" | "failed";

const EFFORT = [{ value: "", label: "기본" }, { value: "low", label: "낮음" }, { value: "medium", label: "보통" }, { value: "high", label: "높음" }, { value: "xhigh", label: "매우 높음" }, { value: "max", label: "최대" }];
const SCOPE: Record<string, string> = { global: "공통", trends: "트렌드", brand: "브랜드", character: "캐릭터", look: "룩", studio: "영상" };
const AGENT_ICON: Record<string, string> = { claude: "agent-claude", codex: "agent-codex", antigravity: "antigravity" };
const commTone = (c: string) => (c.startsWith("가능") ? "ok" : c.startsWith("불가") ? "danger" : "warn") as "ok" | "danger" | "warn";
const availTag = (a: boolean | null | undefined, off = "설치 필요") => a === null || a === undefined ? <Tag>{t("확인 중")}</Tag> : a ? <Tag tone="ok">{t("사용 가능")}</Tag> : <Tag tone="warn">{t(off)}</Tag>;
/** 번역문의 {이름} 자리에 JSX 를 끼운다(굵은 글씨 등) */
const rich = (s: string, parts: Record<string, React.ReactNode>): React.ReactNode =>
  s.split(/\{(\w+)\}/).map((x, i) => (i % 2 ? <React.Fragment key={i}>{parts[x] ?? `{${x}}`}</React.Fragment> : x));
const DATE_LOCALE: Record<Lang, string> = { ko: "ko-KR", en: "en-US", zh: "zh-CN" };

export const SettingsPage: React.FC = () => {
  const raw = useParams().section ?? "agent";
  // 예전 주소(/settings/voice · render)는 미디어의 그 탭으로
  const sec = (["voice", "render"].includes(raw) ? "media" : raw) as Sec;
  const { data: remote, isLoading, error } = useSettings();
  const [s, setS] = useState<Settings | null>(null);
  const [save, setSave] = useState<Save>("idle");
  useEffect(() => { if (remote && save !== "saving") setS(remote); }, [remote]); // eslint-disable-line react-hooks/exhaustive-deps
  const timer = useRef(0);
  const set = (p: Partial<Settings>) => {
    if (!s) return;
    const n = { ...s, ...p }; setS(n); setSave("saving");
    clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try { await api.saveSettings(n); qc.setQueryData(qk.settings, n); setSave("saved"); qc.invalidateQueries({ queryKey: qk.agents }); }
      catch (e) { setSave("failed"); toast.error(t("설정을 저장하지 못했어요"), { description: errMsg(e) }); qc.invalidateQueries({ queryKey: qk.settings }); }
    }, 350);
  };

  const { data: engines = [] } = useEngines();
  const { data: voices = [] } = useQuery({ queryKey: qk.voices, queryFn: ({ signal }) => sapi.voices(signal) });
  const { data: keys } = useQuery({ queryKey: ["gen-keys"], queryFn: ({ signal }) => sapi.genKeys(signal) });
  const { data: mem = [] } = useQuery({ queryKey: qk.memory, queryFn: ({ signal }) => sapi.memory(signal) });
  const activeMem = mem.filter((m) => m.status === "active");

  // open-design 처럼 두 덩어리: 글을 쓰는 모델(에이전트) · 소리와 화면 재료(음성 · 스톡 영상 · 렌더 엔진)
  const NAV: [Sec, string, string, string][] = [
    ["agent", "agent", t("에이전트"), t("Claude · Antigravity · Codex")],
    ["videogen", "sparkle", t("AI 생성 (영상 · 이미지)"), t("Google Flow · Antigravity 모델 및 경로")],
    ["media", "image", t("미디어"), t("음성 · 스톡 영상")],
    ["youtube", "video", t("YouTube"), t("채널 연결 · 업로드 · 통계")],
    ["memory", "memory", t("기억"), t("{n}개", { n: activeMem.length })],
    ["mcp", "link", t("MCP 서버"), t("에이전트가 쓸 외부 도구")],
    ["about", "info", t("정보"), t("저장 위치 · 확장")],
  ];
  const cur = NAV.find((n) => n[0] === sec) ?? NAV[0];

  return (
    <div className="page settings">
      <nav className="set-nav" aria-label={t("설정 구역")}>
        <h1>{t("설정")}</h1>
        {NAV.map(([k, ic, label]) => (
          <NavLink key={k} to={`/settings/${k}`} className={() => cx("set-item", k === sec && "on")}>
            <Icon n={ic} s={16} /><span><b>{label}</b></span>
          </NavLink>))}
      </nav>
      <div className="set-main">
        <header className="page-head">
          <span className="crumb"><span>{t("설정")}</span><Icon n="chevron" s={12} /><b>{cur[2]}</b></span>
          <span className="grow" />
          <SaveState s={save} />
        </header>
        <div className="set-body">
          {isLoading || !s ? (error ? <EmptyState icon="warn" title={t("설정을 불러오지 못했어요")} body={errMsg(error)} action={<Button onClick={() => qc.invalidateQueries({ queryKey: qk.settings })}>{t("다시 시도")}</Button>} />
            : <div className="col"><Skeleton w={240} h={22} /><Skeleton h={64} /><Skeleton h={64} /></div>) : <>
            {sec === "agent" && <AgentSec s={s} set={set} />}
            {sec === "videogen" && <VideoGenSec s={s} set={set} />}
            {sec === "media" && <MediaSec s={s} set={set} engines={engines} voices={voices} keys={keys} />}
            {sec === "youtube" && <YoutubeSec />}
            {sec === "memory" && <MemorySec mem={activeMem} />}
            {sec === "mcp" && <McpSec />}
            {sec === "about" && <AboutSec />}
          </>}
        </div>
      </div>
    </div>
  );
};

const SaveState: React.FC<{ s: Save }> = ({ s }) => (
  <span className={cx("save-state", s)} role="status" aria-live="polite">
    {s === "saving" && <><Spinner s={12} />{t("저장 중")}</>}
    {s === "saved" && <><Icon n="check" s={13} />{t("저장됨 · 다음 작업부터 적용")}</>}
    {s === "failed" && <><Icon n="warn" s={13} />{t("저장 실패")}</>}
    {s === "idle" && <span className="faint">{t("바꾸면 바로 저장됩니다")}</span>}
  </span>
);
const Head: React.FC<{ t: string; d: React.ReactNode; right?: React.ReactNode }> = ({ t, d, right }) => (
  <div className="set-h"><div><h2>{t}</h2><p>{d}</p></div>{right}</div>
);
const Row: React.FC<{ t: string; d: React.ReactNode; children: React.ReactNode }> = ({ t, d, children }) => (
  <div className="set-row"><div className="set-row-t"><b>{t}</b><p>{d}</p></div><div className="set-row-c">{children}</div></div>
);

/* ---------- 설치 버튼 (작업 진행 줄) ---------- */
const InstallButton: React.FC<{ kind: "engines" | "voices"; name: string; title: string; size?: string; note?: string; onDone: () => void }> = ({ kind, name, title, size, note, onDone }) => {
  const [job, setJob] = useState<string | null>(null);
  const [st, setSt] = useState<{ status: "run" | "done" | "fail"; lines: string[]; secs: number } | null>(null);
  useEffect(() => {
    if (!job) return;
    let alive = true, tm = 0; const ac = new AbortController();
    const poll = async () => {
      try {
        const d = await sapi.installStatus(job, ac.signal); if (!alive) return; setSt(d);
        if (d.status === "run") tm = window.setTimeout(poll, 1500);
        else if (d.status === "done") { toast.success(t("{name} 설치 완료", { name: title })); onDone(); }
        else toast.error(t("{name} 설치 실패", { name: title }), { description: d.lines.filter(Boolean).slice(-1)[0] });
      } catch { if (alive) tm = window.setTimeout(poll, 3000); }
    };
    poll();
    return () => { alive = false; clearTimeout(tm); ac.abort(); };
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async () => {
    const body = [size && t("용량: {size}", { size: t(size) }), note && t(note), t("이 컴퓨터(운영체제)에 맞는 방법으로 설치합니다.")].filter(Boolean).join("\n");
    if (!(await confirmDialog({ title: t("{name}을(를) 설치할까요?", { name: title }), body, ok: t("설치") }))) return;
    try { const r = await sapi.install(kind, name); setJob(r.jobId ?? r.job); setSt({ status: "run", lines: [], secs: 0 }); }
    catch (e) { toast.error(t("설치를 시작하지 못했어요"), { description: errMsg(e) }); }
  };
  const run = st?.status === "run";
  const tail = (st?.lines ?? []).filter((l) => l.trim()).slice(-2);
  return (
    <div className="install">
      {st?.status === "done" ? <Tag tone="ok">{t("설치됨")}</Tag> :
        <Button size="sm" variant={st?.status === "fail" ? "danger" : "secondary"} icon={run ? undefined : "download"} loading={run} onClick={go}>
          {run ? t("설치 중 {n}초", { n: st?.secs ?? 0 }) : st?.status === "fail" ? t("다시 시도") : size ? t("설치 · {size}", { size: t(size) }) : t("설치")}
        </Button>}
      {tail.length > 0 && <div className={cx("install-log mono", st?.status === "fail" && "bad")}>{tail.map((l, i) => <span key={i}>{l.trim()}</span>)}</div>}
    </div>
  );
};

/* ---------- 에이전트 ---------- */
const AgentSec: React.FC<{ s: Settings; set: (p: Partial<Settings>) => void }> = ({ s, set }) => {
  const { data: info, isLoading, error, refetch } = useQuery({ queryKey: qk.agents, queryFn: ({ signal }) => sapi.agents(signal) });
  const a: AgentCfg = { cli: "claude", claudeModel: s.model || "", codexModel: "", agyModel: "", effort: s.effort || "", ...((s.agent || {}) as Partial<AgentCfg>) };
  const setA = (p: Partial<AgentCfg>) => set({ agent: { ...a, ...p } });
  if (isLoading) return <div className="col"><Skeleton w={200} h={22} /><Skeleton h={72} /><Skeleton h={72} /></div>;
  if (error || !info) return <EmptyState icon="warn" title={t("에이전트 정보를 불러오지 못했어요")} body={errMsg(error)} action={<Button onClick={() => refetch()}>{t("다시 시도")}</Button>} />;

  return <>
    <Head t={t("에이전트")} d={t("영상을 만드는 에이전트와 모델입니다. 이 컴퓨터에 설치된 에이전트 CLI(Claude Code · Antigravity · Codex)를 직접 사용합니다.")} />
    <div className={cx("activebar", info.problem && "bad")}><Icon n={info.problem ? "warn" : "check"} s={14} />{info.problem ? info.problem : t("지금 쓰는 에이전트: {name}", { name: info.active ?? t("확인 중") })}</div>

    <div className="ecards">{info.agents.map((x: AgentInfo) => {
      const on = a.cli === x.id; const usable = !!x.installed && x.runs;
      const ms = x.id === "claude" ? info.models.claude : x.id === "codex" ? info.models.codex : x.id === "antigravity" ? (info.models.antigravity ?? []) : [];
      const curM = x.id === "claude" ? a.claudeModel : x.id === "antigravity" ? (a.agyModel ?? "") : a.codexModel;
      return (
        <div key={x.id} className={cx("ecard", on && "on", !usable && "dim")}>
          <button className="ecard-pick" role="radio" aria-checked={on} aria-label={t("{name} 쓰기", { name: x.title })} disabled={!usable} onClick={() => setA({ cli: x.id })}><i /></button>
          <EngineIcon id={x.id} src={AGENT_ICON[x.id] ? `/api/engine-icons/${AGENT_ICON[x.id]}.svg` : null} title={x.title} />
          <div className="ecard-b">
            <b>{x.title}<small>{x.vendor}</small></b>
            <p>{t(x.tagline)}</p>
            <div className="tags">
              {x.installed === null ? <Tag>{t("확인 중")}</Tag> : x.installed ? <Tag tone="ok">{t("설치됨")}{x.version ? ` · ${x.version.replace(/\(.*\)/, "").trim()}` : ""}</Tag> : <Tag tone="warn">{t("설치 안 됨")}</Tag>}
              {x.auth && (/not logged in/i.test(x.auth)
                ? <Tag tone="warn">{t("로그인 필요")}</Tag>
                : <Tag>{x.auth.replace("Logged in using", t("로그인:"))}</Tag>)}
              {x.installed && !x.runs && <Tag tone="warn">{t("연결 준비 중")}</Tag>}
            </div>
          </div>
          {usable && ms.length > 0 && (
            <div className="ecard-act">
              <div className="model-pick">
                {modelIconSrc(curM || (x.id === "codex" ? "gpt" : x.id === "antigravity" ? "gemini" : "claude")) && <img className="model-ic" src={modelIconSrc(curM || (x.id === "codex" ? "gpt" : x.id === "antigravity" ? "gemini" : "claude"))!} alt="" />}
                <Select size="sm" aria-label={t("{name} 모델", { name: x.title })} value={curM} onChange={(v) => setA(x.id === "claude" ? { claudeModel: v, cli: "claude" } : x.id === "antigravity" ? { agyModel: v, cli: "antigravity" } : { codexModel: v, cli: "codex" })}
                  options={ms.map((m) => ({ value: m.id, label: t(m.label) }))} />
              </div>
            </div>)}
        </div>);
    })}</div>

    <Row t={t("생각 깊이")} d={t("높을수록 오래 생각합니다. 화면 구성 · 긴 영상은 ‘높음’ 이상을 권합니다.")}>
      <Segmented aria-label={t("생각 깊이")} size="sm" value={a.effort} onChange={(v) => setA({ effort: v })} options={EFFORT.map((o) => ({ ...o, label: t(o.label) }))} />
    </Row>
    <Row t={t("언어")} d={t("화면과 에이전트 답변 언어를 함께 바꿉니다. 영상의 나레이션 · 자막 언어는 영상마다 따로 정합니다.")}>
      <LangSwitch s={s} />
    </Row>
  </>;
};

/** 언어: 설정(에이전트 답변 언어)을 먼저 저장한 뒤 화면 언어를 바꾼다 — 화면이 다시 그려지면서 미뤄 둔 저장이 사라지지 않게 */
const LangSwitch: React.FC<{ s: Settings }> = ({ s }) => {
  const lang = useLang((x) => x.lang);
  const pick = async (v: string) => {
    const l = v as Lang;
    try { const n = { ...s, language: agentLang(l) }; await api.saveSettings(n); qc.setQueryData(qk.settings, n); }
    catch (e) { toast.error(t("설정을 저장하지 못했어요"), { description: errMsg(e) }); return; }
    useLang.getState().setLang(l);
  };
  return <Segmented aria-label={t("언어")} size="sm" value={lang} onChange={pick} options={LANGS.map((x) => ({ value: x.value, label: x.label }))} />;
};

/* ---------- 렌더 · 요소 엔진 ---------- */
const ROLE_TXT: Record<string, string> = { craft: "장면 합성 · 소리 · 조립(모든 장면)" };
const RenderSec: React.FC<{ engines: EngineMeta[] }> = ({ engines }) => {
  const order = ["craft"];
  const list = [...engines].sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
  const [sel, setSel] = useState<string | null>(null);
  if (!list.length) return <><Head t={t("렌더 엔진")} d={t("불러오는 중")} /><Skeleton h={120} /></>;
  const e = list.find((x) => x.name === sel) ?? list[0];
  return <>
    <Head t={t("렌더 엔진")} d={t("모든 장면은 Craft 파이프라인(EffectCraft 움직임 → SoundCraft 소리 → FilmCraft 조립)이 만듭니다. 장면 재료를 만드는 앱은 Craft 앱 화면에서 관리합니다.")}
      right={<Button size="sm" variant="ghost" icon="render" onClick={() => sapi.refreshRegistry().then(() => toast(t("엔진 상태를 다시 확인하는 중이에요"))).catch((er) => toast.error(errMsg(er)))}>{t("상태 다시 확인")}</Button>} />
    <div className="gk-chips" role="tablist" aria-label={t("렌더 엔진")}>
      {list.map((x) => (
        <button key={x.name} role="tab" aria-selected={x.name === e.name} className={cx("gk-chip", x.name === e.name && "on")} onClick={() => setSel(x.name)}>
          {x.icon ? <img className="gk-ic" src={x.icon} alt="" /> : <Icon n="engine" s={14} />}{x.title ?? x.name}
          <i className={cx("gk-dot", x.available && "ok")} aria-label={x.available ? t("사용 가능") : t("설치 필요")} />
        </button>))}
    </div>
    <div className="gk-card" role="tabpanel" aria-label={e.title ?? e.name}>
      <div className="gk-card-h">
        <EngineIcon id={e.name} src={e.icon} title={e.title ?? e.name} size={40} />
        <div className="gk-t"><b>{e.title ?? e.name}</b><small>{t(ROLE_TXT[e.name] ?? "렌더 엔진")} · {e.summary ? t(e.summary) : ""}</small></div>
        <span className="gk-caps">{e.available ? t("사용 가능") : e.available === false ? t("설치 필요") : t("확인 중")}</span>
      </div>
      <p className="gk-facts">{e.license ? t("라이선스 {name}", { name: e.license }) : ""} · {t("제작 파일을 앱에서 열어 고칠 수 있음")}</p>
      {e.available === false && <InstallButton kind="engines" name={e.name} title={e.title ?? e.name} note={e.install} onDone={() => qc.invalidateQueries({ queryKey: qk.engines })} />}
    </div>
  </>;
};

/* ---------- API 키(음성 · 스톡 영상) ---------- */
/** 음성 · 스톡 영상 API 키 — open-design 의 Media providers 구성을 따름(REA 로 실행 화면 확인, 2026-11-02):
 *  공급자 칩(설정된 것은 초록 점) → 고른 공급자 하나만 상세 카드(기능 배지 · 키 보기/가리기 · 키 발급 · 연결 시험 · 문서 · 지우기).
 *  모델 이름은 고르지 않는다 — 키가 있는 공급자 중에서 에이전트가 장면에 맞게 고른다 */
const GenKeys: React.FC<{ keys?: GenKey[]; title: string; desc: string }> = ({ keys, title, desc }) => {
  const [sel, setSel] = useState<string | null>(null);
  const [val, setVal] = useState("");
  const [show, setShow] = useState(false);
  const [test, setTest] = useState<Record<string, { busy?: boolean; ok?: boolean | null; msg: string }>>({});
  if (!keys) return <><Head t={title} d={t("불러오는 중")} /><Skeleton h={160} /></>;
  const all = keys;
  if (!all.length) return null;
  const cur = all.find((k) => k.id === (sel ?? all.find((k) => k.hasKey)?.id ?? all[0].id))!;
  const pick = (id: string) => { setSel(id); setVal(""); setShow(false); };
  const refresh = () => { for (const q of [["gen-keys"], qk.voices]) qc.invalidateQueries({ queryKey: q }); };
  const save = async (v: string) => {
    try {
      await sapi.saveGenKey(cur.id, v);
      setVal(""); toast.success(v ? t("{name} 키를 저장했어요", { name: t(cur.title) }) : t("{name} 키를 지웠어요", { name: t(cur.title) })); refresh();
    } catch (e) { toast.error(t("키를 저장하지 못했어요"), { description: errMsg(e) }); }
  };
  const runTest = async () => {
    setTest((o) => ({ ...o, [cur.id]: { busy: true, msg: t("연결 시험 중") } }));
    try { const r = await sapi.testGenKey(cur.id); setTest((o) => ({ ...o, [cur.id]: { ok: r.ok, msg: t(r.msg) } })); }
    catch (e) { setTest((o) => ({ ...o, [cur.id]: { ok: false, msg: errMsg(e) } })); }
  };
  const tr = test[cur.id];
  return <>
    <Head t={title} d={desc}
      right={<Button size="sm" variant="ghost" icon="history" onClick={refresh}>{t("새로 고침")}</Button>} />
    <div className="gk-chips" role="tablist" aria-label={t("공급자")}>
      {all.map((k) => (
        <button key={k.id} role="tab" aria-selected={k.id === cur.id} className={cx("gk-chip", k.id === cur.id && "on")} onClick={() => pick(k.id)} title={t(k.what)}>
          {k.icon ? <img className="gk-ic" src={k.icon} alt="" /> : <Icon n="link" s={14} />}{t(k.title)}{!k.ready && <small className="gk-soon">{t("준비 중")}</small>}
          <i className={cx("gk-dot", k.hasKey && "ok")} aria-label={k.hasKey ? t("연결됨") : t("연결 안 됨")} />
        </button>))}
    </div>
    <div className="gk-card" role="tabpanel" aria-label={t(cur.title)}>
      <div className="gk-card-h">
        <EngineIcon id={cur.id} src={cur.icon ?? null} title={t(cur.title)} size={40} />
        <div className="gk-t"><b>{t(cur.title)}</b><small>{t(cur.what)}</small></div>
        <span className="gk-caps">{[...cur.caps.map((c) => t(c)), cur.paid ? t("유료") : t("무료")].join(" · ")}</span>
      </div>
      {!cur.ready && <p className="gk-facts"><Icon n="info" s={12} /> {t("Fluma 연결은 준비 중이에요 — 키를 저장해 두면 연결되는 대로 에이전트가 씁니다.")}</p>}
      <Field label={t("API 키")} htmlFor="gk-key" hint={cur.hasKey
        ? t("{where} — 이 컴퓨터에만 저장되고 에이전트는 읽을 수 없습니다", { where: `${cur.source === "env.local" ? t(".env.local 에 있음") : cur.source === "env" ? t("환경 변수에 있음") : t("저장됨")}${cur.keyMasked ? ` (${cur.keyMasked})` : ""}` })
        : t("이 컴퓨터에만 저장되고 에이전트는 읽을 수 없습니다")}>
        <div className="row">
          <div className="gk-key">
            <input id="gk-key" className="in" type={show ? "text" : "password"} autoComplete="off" value={val} onChange={(e) => setVal(e.target.value)}
              placeholder={cur.hasKey ? t("바꾸려면 새 키 입력") : t(cur.keyHint)} />
            <button className="gk-eye" type="button" onClick={() => setShow((v) => !v)} aria-label={show ? t("키 가리기") : t("키 보기")}>{show ? t("가리기") : t("보기")}</button>
          </div>
          <a className="btn btn-ghost btn-sm" href={cur.console} target="_blank" rel="noreferrer">{t("키 발급")} <Icon n="external" s={12} /></a>
        </div>
      </Field>
      <div className="row">
        <Button size="sm" variant="primary" disabled={!val.trim()} onClick={() => save(val.trim())}>{t("저장")}</Button>
        <Button size="sm" icon="link" disabled={!cur.hasKey || !cur.testable} loading={tr?.busy} onClick={runTest}>{cur.testable ? t("연결 시험") : t("연결 시험 미지원")}</Button>
        {tr && !tr.busy && <span className={cx("test-msg", tr.ok ? "ok" : tr.ok === false ? "bad" : undefined)}>{tr.msg}</span>}
        <span className="grow" />
        {cur.hasKey && cur.source === "saved" && <Button size="sm" variant="ghost" onClick={async () => { if (await confirmDialog({ title: t("{name} 키를 지울까요?", { name: t(cur.title) }), ok: t("지우기"), danger: true })) save(""); }}>{t("설정 지우기")}</Button>}
      </div>
      {cur.docs && <div className="gk-docs"><span><b>{t("문서")}</b><small>{t("이 공급자의 설정 방법 · 요금")}</small></span><a className="btn btn-ghost btn-sm" href={cur.docs} target="_blank" rel="noreferrer">{t("문서 보기")} <Icon n="external" s={12} /></a></div>}
    </div>
  </>;
};

/** 미디어: 음성 · 스톡 영상을 한 칸에서 */
const MediaSec: React.FC<{ s: Settings; set: (p: Partial<Settings>) => void; engines: EngineMeta[]; voices: Voice[]; keys?: GenKey[] }> = ({ s, set, voices, keys }) => {
  const raw = useParams().section ?? "media";
  const [tab, setTab] = useState<MediaTab>(() => (["voice", "music", "stock"].includes(raw) ? raw : "voice") as MediaTab);
  const sk = keys?.filter((k) => k.caps.includes("스톡 영상"));
  const vk = keys?.filter((k) => k.caps.includes("음성"));
  const mk = keys?.filter((k) => k.caps.includes("음악"));
  return <>
    <div className="media-tabs">
      <Segmented aria-label={t("미디어 종류")} value={tab} onChange={(v) => setTab(v as MediaTab)} options={[
        { value: "voice", label: t("음성 · {n}개 사용 가능", { n: voices.filter((v) => v.available).length }) },
        { value: "music", label: t("음악") },
        { value: "stock", label: t("스톡 영상 · {n}개 연결", { n: (sk ?? []).filter((k) => k.hasKey).length }) }]} />
    </div>
    {tab === "voice" && <><VoiceSec s={s} set={set} voices={voices} /><GenKeys keys={vk} title={t("음성 API 키")} desc={t("유료 · 클라우드 음성(Typecast · ElevenLabs)을 연결하면 위 목록에서 '사용 가능'이 됩니다.")} /></>}
    {tab === "music" && <MusicSec s={s} set={set} keys={mk} />}
    {tab === "stock" && <GenKeys keys={sk} title={t("스톡 영상 API 키")} desc={t("무료 스톡 영상(Pexels · Pixabay) — 일상 · 감성 · 광고 장면의 바탕(B-roll). 출처는 설명란에 자동으로 붙습니다.")} />}
  </>;
};

/* ---------- 영상 및 이미지 생성 설정(videogen & imagegen) ---------- */
const VIDEOGEN_BACKENDS = [
  { value: "gflow", label: "Google Flow (Veo 기반 · 권장)", icon: "/api/engine-icons/flow.svg" },
  { value: "antigravity", label: "Antigravity Chat (Gemini)", icon: "/api/engine-icons/antigravity.svg" },
  { value: "mock", label: "Mock (테스트용)", icon: null },
];

const GFLOW_VIDEO_MODELS = [
  { value: "veo_3_1_lite", label: "Veo 3.1 Lite (기본 · 10 크레딧 · 빠른 속도)", icon: "/api/engine-icons/veo.svg" },
  { value: "veo_3_1_fast", label: "Veo 3.1 Fast (20 크레딧 · 더 빠른 속도)", icon: "/api/engine-icons/veo.svg" },
  { value: "veo_3_1_quality", label: "Veo 3.1 Quality (100 크레딧 · 최고 화질)", icon: "/api/engine-icons/veo.svg" },
  { value: "omni_1_2_flash", label: "Omni 1.2 Flash (초당 3 크레딧 · 옴니)", icon: "/api/engine-icons/deepmind.svg" },
];

const AGY_VIDEO_MODELS = [
  { value: "gemini", label: "Gemini Video (Antigravity Chat · 기본)", icon: "/api/engine-icons/gemini.svg" },
  { value: "veo", label: "Veo Video (Antigravity Chat)", icon: "/api/engine-icons/veo.svg" },
];

const MOCK_VIDEO_MODELS = [
  { value: "mock", label: "Mock (빠른 더미 비디오)", icon: null },
];

const IMAGEGEN_BACKENDS = [
  { value: "gflow", label: "Google Flow (Imagen / Nano Banana · 기본)", icon: "/api/engine-icons/flow.svg" },
  { value: "agy", label: "Antigravity Chat / CLI (Gemini image-generator)", icon: "/api/engine-icons/antigravity.svg" },
  { value: "mock", label: "Mock (테스트용 빠른 더미)", icon: null },
];

const GFLOW_IMAGE_MODELS = [
  { value: "nano-pro", label: "Nano Banana Pro (기본 · 고품질)", icon: "/api/engine-icons/nanobanana.svg" },
  { value: "nano2", label: "Nano Banana 2 (빠른 생성)", icon: "/api/engine-icons/nanobanana.svg" },
  { value: "nano2-lite", label: "Nano Banana 2 Lite (경량)", icon: "/api/engine-icons/nanobanana.svg" },
  { value: "image4", label: "Imagen 4 (Google 최고 화질)", icon: "/api/engine-icons/flow.svg" },
];

const AGY_IMAGE_MODELS = [
  { value: "flash", label: "Gemini Flash (기본 · 빠른 속도)", icon: "/api/engine-icons/gemini.svg" },
  { value: "pro", label: "Gemini Pro (고품질)", icon: "/api/engine-icons/gemini.svg" },
  { value: "flash_lite", label: "Gemini Flash Lite (초경량)", icon: "/api/engine-icons/gemini.svg" },
];

const VideoGenSec: React.FC<{ s: Settings; set: (p: Partial<Settings>) => void }> = ({ s, set }) => {
  const vg = s.videogen || { backend: "gflow", model: "veo_3_1_lite", max_attempts: 3 };
  const updateVg = (p: Partial<typeof vg>) => set({ videogen: { ...vg, ...p } });

  const ig = s.imagegen || { backend: "gflow", model: "nano-pro" };
  const updateIg = (p: Partial<typeof ig>) => set({ imagegen: { ...ig, ...p } });

  const currentVideoBackend = vg.backend || "gflow";
  const videoModels =
    currentVideoBackend === "antigravity"
      ? AGY_VIDEO_MODELS
      : currentVideoBackend === "mock"
      ? MOCK_VIDEO_MODELS
      : GFLOW_VIDEO_MODELS;

  const currentImageBackend = ig.backend || "gflow";
  const imageModels =
    currentImageBackend === "agy"
      ? AGY_IMAGE_MODELS
      : currentImageBackend === "mock"
      ? [{ value: "mock", label: "Mock 기본", icon: null }]
      : GFLOW_IMAGE_MODELS;

  // 선택된 비디오 아이콘
  const curVb = VIDEOGEN_BACKENDS.find((b) => b.value === currentVideoBackend);
  const curVm = videoModels.find((m) => m.value === (vg.model || videoModels[0]?.value));

  // 선택된 이미지 아이콘
  const curIb = IMAGEGEN_BACKENDS.find((b) => b.value === currentImageBackend);
  const curIm = imageModels.find((m) => m.value === (ig.model || imageModels[0]?.value));

  const { data: gfStatus, refetch: refetchGf, isFetching: gfFetching } = useQuery({
    queryKey: ["gflow-status"],
    queryFn: ({ signal }) => sapi.gflowStatus(signal),
  });
  const [loggingIn, setLoggingIn] = useState(false);
  const handleGflowLogin = async () => {
    setLoggingIn(true);
    try {
      toast.info(t("Google 로그인 창을 엽니다... 로그인을 완료해주세요."));
      const res = await sapi.gflowLogin();
      if (res.ok) {
        toast.success(t("Google Flow 로그인이 완료되었습니다."));
      } else {
        toast.error(t("Google Flow 로그인 실패"), { description: res.error ?? "" });
      }
    } catch (e) {
      toast.error(t("로그인 실행 중 오류"), { description: errMsg(e) });
    } finally {
      setLoggingIn(false);
      refetchGf();
    }
  };

  return (
    <>
      <Head
        t={t("Google Flow 서비스 연동")}
        d={t("Google 공식 Flow(Veo 비디오 및 Imagen/Nano 이미지) 생성을 위한 계정 세션 연동 상태입니다.")}
      />
      <div className="gk-card" style={{ marginBottom: 24, padding: "18px 20px" }}>
        <div className="gk-card-h" style={{ alignItems: "center" }}>
          <EngineIcon id="flow" src="/api/engine-icons/flow.svg" title="Google Flow" size={44} />
          <div className="gk-t" style={{ marginLeft: 12 }}>
            <b style={{ fontSize: 16 }}>Google Flow</b>
            <small style={{ color: "var(--fg-faint)", marginTop: 2 }}>
              {t("Google Veo 비디오 및 Imagen 이미지 생성 엔진 · flow.google.com 계정 연동")}
            </small>
          </div>
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
            {gfStatus?.available ? (
              <Tag tone="ok">{t("계정 로그인됨")}</Tag>
            ) : (
              <Tag tone="warn">{t("로그인 필요")}</Tag>
            )}
            <Button
              size="sm"
              variant={gfStatus?.available ? "secondary" : "primary"}
              icon="link"
              loading={loggingIn || gfFetching}
              onClick={handleGflowLogin}
            >
              {gfStatus?.available ? t("다시 로그인") : t("브라우저로 로그인")}
            </Button>
          </span>
        </div>
        <p className="gk-facts" style={{ marginTop: 12, marginBottom: 0 }}>
          <Icon n="info" s={13} />{" "}
          {t("Google Flow 세션이 연결되면 샷 생성 시 Veo 및 Imagen 모델을 고속으로 사용할 수 있습니다. 만료 시 자동으로 로그인 창을 호출합니다.")}
        </p>
      </div>

      <Head
        t={t("영상 생성 설정 (4단계)")}
        d={t("숏폼 생성 파이프라인 4단계(video.py)에서 사용할 영상 생성 경로와 모델, 샷당 재시도 상한을 설정합니다.")}
      />
      <Row
        t={t("영상 생성 경로 (백엔드)")}
        d={t("Google Flow(Veo 기반 공식 파이프라인)를 쓸지, Antigravity Chat CLI(Gemini)를 쓸지 선택합니다.")}
      >
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          {curVb?.icon ? (
            <img src={curVb.icon} alt="" style={{ width: 22, height: 22, objectFit: "contain", flex: "none" }} />
          ) : (
            <Icon n="video" s={20} />
          )}
          <Select
            aria-label={t("영상 생성 경로")}
            value={currentVideoBackend}
            onChange={(b) => {
              const defM = b === "antigravity" ? "gemini" : b === "mock" ? "mock" : "veo_3_1_lite";
              updateVg({ backend: b, model: defM });
            }}
            options={VIDEOGEN_BACKENDS.map((b) => ({ value: b.value, label: b.label }))}
          />
        </div>
      </Row>
      <Row
        t={t("영상 생성 모델")}
        d={t("선택한 경로에서 실제 비디오 렌더링에 사용할 모델입니다.")}
      >
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          {curVm?.icon ? (
            <img src={curVm.icon} alt="" style={{ width: 22, height: 22, objectFit: "contain", flex: "none" }} />
          ) : (
            <Icon n="video" s={20} />
          )}
          <Select
            aria-label={t("영상 생성 모델")}
            value={vg.model || videoModels[0]?.value}
            onChange={(m) => updateVg({ model: m })}
            options={videoModels.map((m) => ({ value: m.value, label: m.label }))}
          />
        </div>
      </Row>
      <Row
        t={t("샷당 최대 시도 횟수")}
        d={t("한 샷당 무한 생성을 방지하기 위한 최대 시도 상한입니다 (기본 3회).")}
      >
        <Segmented
          aria-label={t("최대 시도 횟수")}
          value={String(vg.max_attempts || 3)}
          onChange={(v) => updateVg({ max_attempts: Number(v) })}
          options={[
            { value: "1", label: "1회" },
            { value: "2", label: "2회" },
            { value: "3", label: "3회 (권장)" },
            { value: "5", label: "5회" },
          ]}
        />
      </Row>

      <Head
        t={t("이미지 생성 설정 (2·3단계)")}
        d={t("캐릭터 시트 및 키 프레임 생성(image.py)에 사용할 생성 경로(Google Flow 또는 Antigravity Chat)와 모델을 선택합니다.")}
      />
      <Row
        t={t("이미지 생성 경로 (백엔드)")}
        d={t("Google Flow Imagen/Nano Banana를 쓸지, Antigravity Chat CLI(Gemini)를 쓸지 선택합니다.")}
      >
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          {curIb?.icon ? (
            <img src={curIb.icon} alt="" style={{ width: 22, height: 22, objectFit: "contain", flex: "none" }} />
          ) : (
            <Icon n="image" s={20} />
          )}
          <Select
            aria-label={t("이미지 생성 경로")}
            value={currentImageBackend}
            onChange={(b) => {
              const defM = b === "agy" ? "flash" : b === "gflow" ? "nano-pro" : "mock";
              updateIg({ backend: b, model: defM });
            }}
            options={IMAGEGEN_BACKENDS.map((b) => ({ value: b.value, label: b.label }))}
          />
        </div>
      </Row>
      <Row
        t={t("이미지 생성 모델")}
        d={t("선택한 경로에서 실제 이미지 생성에 사용할 모델입니다.")}
      >
        <div className="row" style={{ alignItems: "center", gap: 10 }}>
          {curIm?.icon ? (
            <img src={curIm.icon} alt="" style={{ width: 22, height: 22, objectFit: "contain", flex: "none" }} />
          ) : (
            <Icon n="image" s={20} />
          )}
          <Select
            aria-label={t("이미지 생성 모델")}
            value={ig.model || imageModels[0]?.value}
            onChange={(m) => updateIg({ model: m })}
            options={imageModels.map((m) => ({ value: m.value, label: m.label }))}
          />
        </div>
      </Row>
    </>
  );
};

/* ---------- 음성 ---------- */
const VoiceSec: React.FC<{ s: Settings; set: (p: Partial<Settings>) => void; voices: Voice[] }> = ({ s, set, voices }) => {
  const [busy, setBusy] = useState("");
  const [vid, setVid] = useState<Record<string, string>>({});
  const audio = useRef<HTMLAudioElement | null>(null);
  const [last, setLast] = useState<{ name: string; url: string } | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  const play = async (v: Voice) => {
    const id = vid[v.name] ?? (s.voice_engine === v.name ? s.voice_id : "") ?? "";
    setBusy(v.name);
    try {
      const d = await sapi.previewVoice(v.name, id);
      audio.current?.pause(); audio.current = new Audio(d.url); setLast({ name: v.name, url: d.url });
      await audio.current.play().catch((e) => toast.info(t("소리를 바로 틀지 못했어요 — 아래 재생 단추를 눌러 들어 보세요"), { description: String(e?.name || e) }));
    }
    catch (e) { toast.error(t("{name} 미리 듣기 실패", { name: t(v.title) }), { description: errMsg(e) }); }
    finally { setBusy(""); }
  };
  const [sel, setSel] = useState<string | null>(null);
  const auto = s.voice_auto !== false;
  if (!voices.length) return <><Head t={t("음성")} d={t("불러오는 중")} /><Skeleton h={120} /></>;
  const showAuto = sel === "auto" || (sel === null && auto);
  const cur = voices.find((v) => v.name === (sel && sel !== "auto" ? sel : s.voice_engine)) ?? voices[0];
  const def = voices.find((v) => v.name === s.voice_engine);
  const on = s.voice_engine === cur.name;
  const voiceId = vid[cur.name] ?? (on ? s.voice_id : "") ?? "";
  const kindTxt = cur.kind === "local" ? t("내 컴퓨터 · 무료") : cur.kind === "cloud" ? t("온라인 · 무료") : t("API · 유료");
  const curTitle = t(cur.title);
  return <>
    <Head t={t("음성")} d={rich(t("나레이션 목소리입니다. 지금 기본: {voice}. 레퍼런스가 있으면 에이전트가 그 화자에 맞춰 고릅니다."), { voice: <><b>{def ? t(def.title) : s.voice_engine}</b>{s.voice_id ? ` · ${s.voice_id}` : ""}</> })} />
    <div className="gk-chips" role="tablist" aria-label={t("음성 엔진")}>
      <button role="tab" aria-selected={showAuto} className={cx("gk-chip", showAuto && "on")} onClick={() => setSel("auto")} title={t("영상마다 알맞은 목소리를 고름")}>
        <Icon n="sparkle" s={14} />{t("자동")}{auto ? <Icon n="check" s={13} /> : <i className="gk-dot ok" />}
      </button>
      {voices.map((v) => (
        <button key={v.name} role="tab" aria-selected={v.name === cur.name} className={cx("gk-chip", v.name === cur.name && "on")} onClick={() => setSel(v.name)} title={t(v.summary)}>
          {v.icon ? <img className="gk-ic" src={v.icon} alt="" /> : <Icon n="mic" s={14} />}{t(v.title).replace(/\s*[(（].*[)）]$/, "")}
          {!auto && s.voice_engine === v.name ? <Icon n="check" s={13} /> : <i className={cx("gk-dot", v.available && "ok")} aria-label={v.available ? t("사용 가능") : t("준비 안 됨")} />}
        </button>))}
    </div>
    {showAuto ? <div className="gk-card" role="tabpanel" aria-label={t("자동")}>
      <div className="gk-card-h"><Icon n="sparkle" s={28} /><div className="gk-t"><b>{t("자동 — 영상마다 알맞은 목소리")}</b>
        <small>{t("쓸 수 있는 엔진(키 · 설치된 것) 전체에서 고릅니다")}</small></div>{auto && <span className="gk-caps">{t("기본 음성")}</span>}</div>
      <p className="gk-facts">{t("레퍼런스가 있으면 그 화자의 높이 · 억양 · 말끝 · 세기에 가장 닮은 목소리와, 레퍼런스 말 속도(초당 글자)에 맞춘 배속. 레퍼런스가 없으면 한국어 품질이 가장 좋은 엔진과 형식에 맞는 속도(설명형 초당 7자 · 감성 5.6자).")}</p>
      <div className="row"><span className="grow" />{!auto && <Button size="sm" variant="primary" onClick={() => set({ voice_auto: true })}>{t("자동으로 쓰기")}</Button>}</div>
    </div> :
    <div className="gk-card" role="tabpanel" aria-label={curTitle}>
      <div className="gk-card-h">
        <EngineIcon id={cur.name} src={cur.icon} title={curTitle} size={40} />
        <div className="gk-t"><b>{curTitle}</b><small>{t(cur.vendor)} · {t(cur.summary)}</small></div>
        {on && <span className="gk-caps">{t("기본 음성")}</span>}
      </div>
      <p className="gk-facts">{kindTxt} · {t("상업 {v}", { v: t(cur.license.commercial) })} · {cur.words ? t("단어 타이밍 정확") : t("단어 타이밍 추정")}{cur.korean ? ` · ${t("한국어")}` : ""}</p>
      {cur.available ? <div className="row">
        {!!cur.voices?.length && <Select size="sm" aria-label={t("{name} 목소리", { name: curTitle })} value={voiceId}
          onChange={(x) => { setVid((o) => ({ ...o, [cur.name]: x })); if (on) set({ voice_id: x }); }}
          options={[{ value: "", label: t("기본 목소리") }, ...cur.voices.map((x) => ({ value: x.id, label: x.gender && x.gender !== "-" ? t(x.gender === "F" ? "{name} (여)" : "{name} (남)", { name: t(x.title) }) : t(x.title) }))]} />}
        <Button size="sm" variant="ghost" icon="volume" loading={busy === cur.name} disabled={!!busy && busy !== cur.name} onClick={() => play(cur)}>{t("들어 보기")}</Button>
        {last?.name === cur.name && <audio key={last.url} src={last.url} controls preload="auto" style={{ height: 30, maxWidth: 220 }} />}
        <span className="grow" />
        {(!on || auto) && <Button size="sm" variant="primary" onClick={() => set({ voice_engine: cur.name, voice_id: voiceId, voice_auto: false })}>{t("이 목소리로 고정")}</Button>}
      </div> : cur.kind === "api"
        ? <p className="faint small"><Icon n="info" s={12} /> {t("아래 '음성 API 키'에 {name} 키를 넣으면 쓸 수 있어요.", { name: cur.title.split(" ")[0] })}</p>
        : cur.available === false ? <InstallButton kind="voices" name={cur.name} title={curTitle} size={cur.size} note={cur.license.commercial === "불가" ? t("상업 이용 불가: {note}", { note: t(cur.license.note) }) : cur.license.note} onDone={() => qc.invalidateQueries({ queryKey: qk.voices })} />
        : <Skeleton h={32} />}
      <p className="lic-note">{t(cur.license.note)}{cur.license.url && <> · <a className="link" href={cur.license.url} target="_blank" rel="noreferrer">{t("출처")}</a></>}</p>
    </div>}
  </>;
};

/* ---------- 음악 ---------- */
/** 배경 음악: 영상마다 넣을지 정하고 요즘 쓰이는 곡 중 맞는 무료 곡을 고른다(engine/craft/music_pick.py). 여기서는 찾는 키와 상업 곡 정책만 */
const MusicSec: React.FC<{ s: Settings; set: (p: Partial<Settings>) => void; keys?: GenKey[] }> = ({ s, set, keys }) => <>
  <Head t={t("배경 음악")} d={t("영상마다 에이전트가 음악을 넣을지 정합니다 — 레퍼런스에 음악이 깔렸는지 · 나레이션이 있는지 · 형식을 보고. 넣으면 레퍼런스가 붙인 곡 · 비슷한 쇼츠들이 요즘 붙이는 곡 · 인기 차트를 찾아, 같은 곡의 무료 판이나 박자 · 분위기가 비슷한 무료 곡을 넣습니다. 음악이 깔리면 효과음은 빼는 게 기본입니다.")} />
  <Row t={t("상업 유행곡도 영상에 직접 넣기")} d={t("끄면(기본) 상업 곡은 '업로드 때 쇼츠 편집기에서 붙일 곡'으로만 알려 줍니다 — 유튜브가 라이선스를 가진 방법. 켜면 상업 곡을 영상에 바로 넣습니다: Content ID 로 수익이 권리자에게 가거나 소리가 꺼질 수 있어요.")}>
    <Switch on={!!s.music_any_license} onChange={(v) => set({ music_any_license: v })} label={t("상업 유행곡도 영상에 직접 넣기")} />
  </Row>
  <GenKeys keys={keys} title={t("음악 찾기 키")} desc={t("YouTube Data API 키가 있으면 음악 인기 차트(KR) · 최근 1년 조회수 순으로 더 정확히 찾습니다. 없어도 웹 검색으로 찾습니다.")} />
</>;

/* ---------- 기억 ---------- */
const MemorySec: React.FC<{ mem: Mem[] }> = ({ mem }) => {
  const [q, setQ] = useState("");
  const [scope, setScope] = useState("");
  const scopes = useMemo(() => [...new Set(mem.map((m) => m.scope.split(":")[0]))], [mem]);
  const list = useMemo(() => [...mem].reverse().filter((m) => (!scope || m.scope.split(":")[0] === scope) && (!q || `${m.title} ${m.body}`.toLowerCase().includes(q.toLowerCase()))), [mem, q, scope]);
  const forget = async (m: Mem) => {
    if (!(await confirmDialog({ title: t("“{title}”을(를) 잊을까요?", { title: m.title }), body: t("지운 기억은 되돌릴 수 없습니다. 에이전트가 다음 작업부터 이 내용을 참고하지 않습니다."), ok: t("잊기"), danger: true }))) return;
    try { await sapi.forget(m.id); toast.success(t("잊었어요")); qc.invalidateQueries({ queryKey: qk.memory }); }
    catch (e) { toast.error(t("지우지 못했어요"), { description: errMsg(e) }); }
  };
  return <>
    <Head t={t("기억")} d={t("어느 화면에서든 “앞으로 2D 위주로”, “네온은 싫어” 같은 말을 하면 에이전트가 기억하고, 영상의 디자인 방향을 정할 때 반영합니다.")} />
    <div className="mem-bar">
      <label className="search"><Icon n="search" s={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("기억 찾기")} aria-label={t("기억 찾기")} /></label>
      <Segmented aria-label={t("범위")} size="sm" value={scope} onChange={setScope} options={[{ value: "", label: t("전체 {n}", { n: mem.length }) }, ...scopes.map((x) => ({ value: x, label: SCOPE[x] ? t(SCOPE[x]) : x }))]} />
    </div>
    {!list.length ? <EmptyState icon="memory" title={mem.length ? t("맞는 기억이 없어요") : t("아직 기억이 없어요")} body={mem.length ? undefined : t("에이전트에게 취향이나 규칙을 말하면 여기에 쌓입니다.")} /> :
      <ul className="mem-list">{list.map((m) => (
        <li key={m.id} className="mem-r">
          <Tag tone="select">{SCOPE[m.scope.split(":")[0]] ? t(SCOPE[m.scope.split(":")[0]]) : m.scope}</Tag>
          <div className="mem-b"><b>{m.title}</b><p>{m.body}</p>
            <small className="faint">{m.provenance?.menu ? t("{menu} 화면에서", { menu: SCOPE[m.provenance.menu] ? t(SCOPE[m.provenance.menu]) : m.provenance.menu }) : t("직접 기억")} · {t("참고 {n}회", { n: m.stats?.recallCount ?? 0 })}{m.created ? ` · ${new Date(m.created).toLocaleDateString(DATE_LOCALE[useLang.getState().lang])}` : ""}</small></div>
          <Button size="sm" variant="ghost" icon="trash" onClick={() => forget(m)}>{t("잊기")}</Button>
        </li>))}</ul>}
  </>;
};

/* ---------- 정보 ---------- */
const AboutSec: React.FC = () => <>
  <Head t={t("정보")} d={t("Fluma — 에이전트가 2D 설명형 쇼츠를 만들고, 렌더 · 음성 엔진은 갈아 끼웁니다.")} />
  <Row t={t("저장 위치")} d={t("콘티 storyboards/ · 화면 구성 compositions/ · 음성 public/audio/ · 렌더 결과 out/ · 설정 workspace/settings.json")}><span /></Row>
  <Row t={t("엔진 · 모델 추가")} d={t("렌더 엔진은 engines/<이름>/, 음성은 engine/voice/engines/<이름>/ 폴더만 두면 여기에 나타납니다.")}><span /></Row>
  <Row t={t("단축키")} d={t("어디서나 ? 를 누르면 단축키 표가 열립니다. Ctrl/⌘ K 로 화면 이동 · 명령을 찾을 수 있어요.")}><span /></Row>
</>;
