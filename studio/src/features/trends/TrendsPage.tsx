/* 트렌드 — 모은 쇼츠를 한눈에 보고 · 판별하고 · 분해한다. 유튜브로 나가지 않고 앱 안에서 재생.
   · 한눈: 위 '분포 막대'(훅 · 화풍 · 판별 — 무엇이 많은지 바로 보이고, 누르면 거름) + 요청 칩(지우기) + 작은 썸네일 모자이크.
     가로 스크롤 없음. 썸네일에 마우스를 올리면 그 자리에서 재생 · 판별 · 지우기
   · 피드: 한 편씩 크게. ↑↓ 넘기기 · 1 찜 · 2 보류 · 3 제외(누르면 다음으로) · X 분해 보기
   · 엑스레이(/trends/x/:id): 샷 · 누끼 · 배경판 · 글자 · 대사 · 박자 · 효과음으로 분해 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { FlumaBounce, FlumaStrain } from "../../ui/BrandIcons";
import { Button, EmptyState, IconButton, Kbd, Segmented, Skeleton, Tip, confirmDialog, cx } from "../../ui/kit";
import { fmtViews } from "../../ui/engines";
import { qc, qk } from "../../lib/queries";
import { typing, useUi } from "../../lib/ui";
import { t } from "../../lib/i18n";
import { AgentDock } from "../agent/AgentDock";
import { PICK, VIS, VIS_ORDER, setPick, src, stageT, startXray, usePicks, useTrendIndex, useXrayList, type Item, type Pick, type Req } from "./data";
import { ShortPlayer } from "./ShortPlayer";

type Mode = "glance" | "feed";
type PickF = "all" | "none" | Pick;
const HOOK_COLOR = ["#6a5cff", "#2dd4bf", "#f5a524", "#f472b6", "#38bdf8", "#a3e635", "#c084fc", "#fb7185"];
const PICK_LABEL: Record<string, string> = { keep: "찜", maybe: "보류", skip: "제외", none: "안 봄" };

async function dropRequest(r: Req) {
  if (!(await confirmDialog({ title: t("요청 “{label}”을(를) 지울까요?", { label: r.label }), body: t("이 요청으로 모은 쇼츠 {n}편도 목록에서 빠집니다.", { n: r.count }), ok: t("지우기"), danger: true }))) return;
  const res = await fetch(`/api/trends/requests/${r.id}`, { method: "DELETE", headers: { "x-fluma-client": "trends" } });
  if (res.ok) { qc.invalidateQueries({ queryKey: qk.trends }); toast.success(t("요청을 지웠어요")); } else toast.error(t("지우지 못했어요"));
}
export async function dropItem(x: Item, ask = true) {
  if (ask && !(await confirmDialog({ title: t("이 쇼츠를 목록에서 뺄까요?"), body: t("“{title}” — 썸네일 · 분석 · 분해 결과도 함께 지워집니다.", { title: x.title }), ok: t("빼기"), danger: true }))) return false;
  const res = await fetch(`/api/trends/items/${x.id}`, { method: "DELETE", headers: { "x-fluma-client": "trends" } });
  if (res.ok) { qc.invalidateQueries({ queryKey: qk.trends }); qc.invalidateQueries({ queryKey: ["xray-list"] }); toast.success(t("목록에서 뺐어요")); return true; }
  toast.error(t("빼지 못했어요")); return false;
}

export const TrendsPage: React.FC = () => {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const { data, isLoading } = useTrendIndex();
  const { data: picks = {} } = usePicks();
  const { data: xl } = useXrayList();
  const requests = data?.requests ?? [], all = data?.items ?? [];
  const xdone = useMemo(() => new Set(xl?.done ?? []), [xl]);
  const xrun = useMemo(() => new Map((xl?.running ?? []).map((r) => [r.id, r])), [xl]);

  const mode: Mode = sp.get("v") === "feed" ? "feed" : "glance";
  const setMode = (m: Mode) => setSp((p) => { p.set("v", m); return p; }, { replace: true });
  const [req, setReq] = useState<string | null>(null);
  const [hook, setHook] = useState<string | null>(null);
  const [vis, setVis] = useState<string | null>(null);
  const [pickF, setPickF] = useState<PickF>("all");
  const [q, setQ] = useState("");
  const [cur, setCur] = useState<string | null>(sp.get("s"));
  const [prefill, setPrefill] = useState<string | null>(null);

  const pickOf = (id: string): Pick | null => picks[id]?.pick ?? null;
  const pk = (x: Item) => pickOf(x.id) ?? "none";
  // 분포 막대는 '요청 · 검색'까지만 거른 집합으로 센다 → 막대를 눌러 거른 뒤에도 전체 모양이 보인다
  const base = useMemo(() => all.filter((x) => (!req || x.request === req)
    && (!q || `${x.title} ${x.tag} ${x.label}`.toLowerCase().includes(q.toLowerCase()))), [all, req, q]);
  const items = useMemo(() => base.filter((x) => (!hook || x.hook === hook) && (!vis || x.visual === vis)
    && (pickF === "all" ? pickOf(x.id) !== "skip" : pk(x) === pickF))
    .sort((a, b) => (b.views ?? 0) - (a.views ?? 0)), [base, hook, vis, pickF, picks]); // eslint-disable-line react-hooks/exhaustive-deps
  const dist = (key: (x: Item) => string) => { const m = new Map<string, number>(); base.forEach((x) => { const k = key(x); m.set(k, (m.get(k) || 0) + 1); }); return [...m].sort((a, b) => b[1] - a[1]); };
  const hooks = useMemo(() => dist((x) => x.hook), [base]); // eslint-disable-line react-hooks/exhaustive-deps
  const viss = useMemo(() => dist((x) => x.visual ?? "?").sort((a, b) => VIS_ORDER.indexOf(a[0]) - VIS_ORDER.indexOf(b[0])), [base]); // eslint-disable-line react-hooks/exhaustive-deps
  const pks = useMemo(() => ["keep", "maybe", "none", "skip"].map((k) => [k, base.filter((x) => pk(x) === k).length] as [string, number]).filter(([, n]) => n), [base, picks]); // eslint-disable-line react-hooks/exhaustive-deps
  const hookColor = useMemo(() => new Map(hooks.map(([h], i) => [h, HOOK_COLOR[i % HOOK_COLOR.length]])), [hooks]);
  const running = requests.find((r) => r.status === "running");
  const sel = items.find((x) => x.id === cur) ?? null;
  const ask = (s: string) => { useUi.getState().set({ agentOpen: true }); setPrefill(s); };
  const open = (id: string) => { setCur(id); setMode("feed"); };
  const filtered = !!(hook || vis || pickF !== "all");

  return (
    <div className="page trends">
      <div className="pg-main">
        <header className="page-head">
          <h1>{t("트렌드")}</h1>
          <Segmented aria-label={t("보기")} size="sm" value={mode} onChange={(v) => setMode(v as Mode)} options={[{ value: "glance", label: t("한눈") }, { value: "feed", label: t("피드") }]} />
          {running && <span className="pg-live"><FlumaBounce s={14} />{t("“{label}” 찾는 중 · {n}편", { label: running.label, n: running.count })}</span>}
          <span className="grow" />
          <label className="tr-search"><Icon n="search" s={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("제목 · 태그 찾기")} aria-label={t("쇼츠 찾기")} /></label>
          <span className="faint pg-meta">{t("{n}편", { n: items.length })}</span>
        </header>
        {/* 요청: 칩마다 지우기 */}
        <div className="tr-reqs" role="toolbar" aria-label={t("요청")}>
          <button className={cx("rq", !req && "on")} onClick={() => setReq(null)}>{t("모든 요청")} <em>{all.length}</em></button>
          {requests.map((r) => (
            <span key={r.id} className={cx("rq", req === r.id && "on", (r.status === "failed" || r.status === "stopped") && "bad")}>
              <button className="rq-b" title={r.text} onClick={() => setReq(req === r.id ? null : r.id)}>
                {r.status === "running" && <FlumaBounce s={11} />}{r.label} <em>{all.filter((x) => x.request === r.id).length}</em>
                {(r.status === "failed" || r.status === "stopped") && <span className="rq-x" title={r.error || t("중간에 끊김")}>{t("끊김")}</span>}
              </button>
              {r.status !== "running" && <button className="rq-del" aria-label={t("요청 {label} 지우기", { label: r.label })} onClick={() => dropRequest(r).then(() => { if (req === r.id) setReq(null); })}><Icon n="close" s={11} /></button>}
            </span>))}
          <span className="grow" />
        </div>
        {/* 분포 막대: 무엇이 많은지 한눈에, 누르면 거름 */}
        {mode === "glance" && base.length > 0 && (
          <div className="dists">
            <Dist title={t("훅")} rows={hooks} total={base.length} on={hook} onPick={(k) => setHook(hook === k ? null : k)} label={(k) => t(k)} color={(k) => hookColor.get(k)!} />
            <Dist title={t("화풍")} rows={viss} total={base.length} on={vis} onPick={(k) => setVis(vis === k ? null : k)} label={(k) => t(VIS[k] ?? "판별 전")} color={(k) => ({ "2d": "#6a5cff", pixel: "#c084fc", screen: "#38bdf8", live: "#f5a524", "3d": "#6e6e76" } as Record<string, string>)[k] ?? "#4a4a50"} />
            <Dist title={t("판별")} rows={pks} total={base.length} on={pickF === "all" ? null : pickF} onPick={(k) => setPickF(pickF === k ? "all" : (k as PickF))} label={(k) => t(PICK_LABEL[k])}
              color={(k) => ({ keep: "var(--primary)", maybe: "#f5a524", skip: "#6e6e76", none: "#3c3c42" } as Record<string, string>)[k]} />
            {filtered && <button className="dist-clear" onClick={() => { setHook(null); setVis(null); setPickF("all"); }}>{t("거르기 풀기")}</button>}
          </div>
        )}
        <main className="tr-main">
          {isLoading ? <div className="mosaic">{Array.from({ length: 24 }, (_, i) => <Skeleton key={i} h={0} className="tile-skel" r={10} />)}</div>
            : !items.length ? (
              <EmptyState icon="trend" title={all.length ? t("조건에 맞는 쇼츠가 없어요") : t("아직 모은 쇼츠가 없어요")}
                body={all.length ? t("위 막대나 요청을 다시 눌러 거르기를 풀어 보세요.") : t("오른쪽 에이전트에게 “IT 관련 애니메이션 쇼츠 찾아봐”처럼 말하면 결과가 생기는 대로 여기에 나타납니다.")}
                action={!all.length ? <Button variant="agent" icon="agent" onClick={() => ask(t("요즘 애니메이션 설명형 쇼츠 트렌드 찾아봐"))}>{t("애니메이션 트렌드 찾아 달라고 하기")}</Button> : undefined} />
            ) : mode === "glance" ? (
              <Mosaic items={items} pickOf={pickOf} xdone={xdone} xrun={xrun} hookColor={hookColor} onOpen={open} />
            ) : (
              <Feed items={items} cur={sel?.id ?? items[0]?.id} setCur={setCur} pickOf={pickOf} xdone={xdone} xrun={xrun}
                onXray={(id) => nav(`/trends/x/${id}`)}
                onMake={(x) => nav("/?prefill=" + encodeURIComponent(t("“{title}” 쇼츠의 {hook} 훅 · 구성 패턴을 참고해서 (베끼지 말고 패턴만), 내 주제로: ", { title: x.title, hook: t(x.hook) })))} />
            )}
        </main>
      </div>
      <AgentDock sessionId="_workspace" title={t("에이전트 · 트렌드")} context={{ menu: "trends", selection: sel ? t("트렌드 쇼츠 \"{title}\" ({url}, 조회 {views}, {src}, 훅 {hook})", { title: sel.title, url: sel.url, views: fmtViews(sel.views), src: src(sel), hook: t(sel.hook) }) : undefined }}
        chip={sel && mode === "feed" ? { label: t("쇼츠 “{title}”", { title: sel.title }), onClear: () => setCur(null) } : null}
        hints={[t("IT 관련 애니메이션 쇼츠 찾아봐"), t("찜한 쇼츠들의 공통 패턴 정리해 줘"), t("요즘 잘 되는 설명형 모션그래픽 쇼츠 찾아봐")]}
        placeholder={t("어떤 쇼츠를 찾아볼까요? 예: 개발 애니메이션 쇼츠 찾아봐")} prefill={prefill} onPrefillUsed={() => setPrefill(null)} />
    </div>
  );
};

/* ---------- 분포 막대: 한 줄 = 한 기준. 칸 너비 = 비율. 누르면 그 칸만 ---------- */
const Dist: React.FC<{ title: string; rows: [string, number][]; total: number; on: string | null; onPick: (k: string) => void; color: (k: string) => string; label?: (k: string) => string }> = ({ title, rows, total, on, onPick, color, label = (k) => k }) => (
  <div className="dist">
    <span className="dist-t">{title}</span>
    <div className="dist-bar" role="group" aria-label={t("{title} 분포", { title })}>
      {rows.map(([k, n]) => (
        <button key={k} className={cx("dist-seg", on === k && "on", on && on !== k && "dim")} style={{ flexGrow: n, background: color(k) }} title={t("{label} {n}편 ({p}%)", { label: label(k), n, p: Math.round((n / total) * 100) })} onClick={() => onPick(k)}>
          <span>{label(k)} <em>{n}</em></span>
        </button>))}
    </div>
  </div>
);

/* ---------- 모자이크: 작은 썸네일을 빽빽하게 (가로 스크롤 없음) ---------- */
const Mosaic: React.FC<{ items: Item[]; pickOf: (id: string) => Pick | null; xdone: Set<string>; xrun: Map<string, unknown>; hookColor: Map<string, string>; onOpen: (id: string) => void }> = ({ items, pickOf, xdone, xrun, hookColor, onOpen }) => {
  const [hot, setHot] = useState<string | null>(null);
  return (
    <div className="mosaic">
      {items.map((x, i) => <Tile key={x.id} x={x} rank={i + 1} pick={pickOf(x.id)} xray={xdone.has(x.id) ? "done" : xrun.has(x.id) ? "run" : null}
        hook={hookColor.get(x.hook)} hot={hot === x.id} setHot={setHot} onOpen={() => onOpen(x.id)} />)}
    </div>
  );
};

const Tile: React.FC<{ x: Item; rank: number; pick: Pick | null; xray: "done" | "run" | null; hook?: string; hot: boolean; setHot: (id: string | null) => void; onOpen: () => void }> = ({ x, rank, pick, xray, hook, hot, setHot, onOpen }) => {
  const timer = useRef(0);
  return (
    <div className={cx("tile", pick && `pk-${pick}`, hot && "hot")} style={{ ["--hook" as string]: hook }}
      onMouseEnter={() => { timer.current = window.setTimeout(() => setHot(x.id), 500); }} onMouseLeave={() => { clearTimeout(timer.current); setHot(null); }}>
      <button className="tile-im" onClick={onOpen} aria-label={t("{title} 크게 보기", { title: x.title })} title={`${x.title}\n${fmtViews(x.views)} · ${t(x.hook)}`}>
        {x.thumb ? <img src={`/api/public/${x.thumb}`} alt="" loading="lazy" /> : <span className="tw-noimg"><Icon n="video" s={16} /></span>}
        {hot && <ShortPlayer vid={x.id} muted mini />}
        <span className="tile-rank mono">{rank}</span>
        <span className="tile-views mono">{fmtViews(x.views)}</span>
        {xray && <span className={cx("tile-x", xray)} title={xray === "run" ? t("분해 중") : t("분해됨")}><Icon n="layers" s={10} /></span>}
        <span className="tile-t">{x.title}</span>
      </button>
      <div className="tile-acts" role="group" aria-label={t("판별")}>
        {(Object.keys(PICK) as Pick[]).map((p) => (
          <button key={p} className={cx("reel-a", p, pick === p && "on")} aria-pressed={pick === p} title={`${t(PICK[p].label)} (${PICK[p].key})`} onClick={() => setPick(x.id, pick === p ? null : p)}><Icon n={PICK[p].icon} s={12} /></button>))}
        <button className="reel-a del" title={t("목록에서 빼기")} aria-label={t("목록에서 빼기")} onClick={() => dropItem(x)}><Icon n="trash" s={12} /></button>
      </div>
    </div>
  );
};

/* ---------- 피드: 한 편씩 크게 ---------- */
const Feed: React.FC<{ items: Item[]; cur?: string; setCur: (id: string) => void; pickOf: (id: string) => Pick | null; xdone: Set<string>; xrun: Map<string, { progress: number | null; stage: string }>;
  onXray: (id: string) => void; onMake: (x: Item) => void }> = ({ items, cur, setCur, pickOf, xdone, xrun, onXray, onMake }) => {
  const i = Math.max(0, items.findIndex((x) => x.id === cur));
  const x = items[i];
  const [muted, setMuted] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const go = (d: number) => { const n = items[Math.min(items.length - 1, Math.max(0, i + d))]; if (n) setCur(n.id); };
  const judge = (p: Pick) => { const same = pickOf(x.id) === p; setPick(x.id, same ? null : p); if (!same) go(1); };
  useEffect(() => { listRef.current?.querySelector(".fq.on")?.scrollIntoView({ block: "nearest" }); }, [x?.id]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); go(1); }
      else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); go(-1); }
      else if (e.key === "1") judge("keep"); else if (e.key === "2") judge("maybe"); else if (e.key === "3") judge("skip");
      else if (e.key === "m") setMuted((v) => !v);
      else if (e.key === "x") { if (xdone.has(x.id)) onXray(x.id); else startXray(x.id); }
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  });
  if (!x) return null;
  const pick = pickOf(x.id); const xr = xrun.get(x.id);
  return (
    <div className="feed">
      <div className="feed-q" ref={listRef} aria-label={t("다음 쇼츠")}>
        {items.map((y, k) => (
          <button key={y.id} className={cx("fq", y.id === x.id && "on", pickOf(y.id) && `pk-${pickOf(y.id)}`)} onClick={() => setCur(y.id)}>
            <span className="fq-n mono">{k + 1}</span>
            {y.thumb ? <img src={`/api/public/${y.thumb}`} alt="" loading="lazy" /> : <span className="fq-ph" />}
            <span className="fq-t"><b className="ellipsis2">{y.title}</b><span className="faint mono">{fmtViews(y.views)}</span></span>
            {pickOf(y.id) && <span className={cx("pick-dot", pickOf(y.id)!)} />}
          </button>))}
      </div>
      <div className="feed-stage">
        <div className="feed-card">
          <div className="feed-player"><ShortPlayer key={x.id} vid={x.id} muted={muted} local={xdone.has(x.id)} /></div>
        </div>
        <div className="feed-nav">
          <IconButton icon="arrowUp" label={t("이전 (↑)")} onClick={() => go(-1)} disabled={i === 0} />
          <span className="mono faint">{i + 1} / {items.length}</span>
          <IconButton icon="down" label={t("다음 (↓)")} onClick={() => go(1)} disabled={i === items.length - 1} />
          <IconButton icon={muted ? "mute" : "volume"} label={muted ? t("소리 켜기 (M)") : t("소리 끄기 (M)")} onClick={() => setMuted(!muted)} />
        </div>
      </div>
      <aside className="feed-info" aria-label={t("고른 쇼츠")}>
        <b className="feed-t">{x.title || t("제목 없음")}</b>
        <dl className="kv">
          <dt>{t("조회")}</dt><dd className="mono">{fmtViews(x.views)}</dd>
          <dt>{t("훅")}</dt><dd>{t(x.hook)} <span className="faint">{t("(제목으로 추정)")}</span></dd>
          <dt>{t("화풍")}</dt><dd>{VIS[x.visual ?? ""] ? t(VIS[x.visual ?? ""]) : "–"}</dd>
          <dt>{t("찾은 곳")}</dt><dd>{src(x)} · {x.label}</dd>
        </dl>
        <div className="judge" role="group" aria-label={t("판별")}>
          {(Object.keys(PICK) as Pick[]).map((p) => (
            <button key={p} className={cx("judge-b", p, pick === p && "on")} aria-pressed={pick === p} onClick={() => judge(p)}>
              <Icon n={PICK[p].icon} s={15} /><b>{t(PICK[p].label)}</b><Kbd k={PICK[p].key} />
            </button>))}
        </div>
        <section className="xcall">
          <div className="xcall-h"><b>{t("분해 보기")}</b><Kbd k="X" /></div>
          {xdone.has(x.id) ? (
            <>
              <p className="faint small">{t("샷 · 누끼 · 배경판 · 글자 · 대사 · 박자 · 효과음으로 나눠 두었어요.")}</p>
              <Button variant="primary" icon="layers" onClick={() => onXray(x.id)}>{t("분해도 열기")}</Button>
            </>
          ) : xr ? (
            <div className="xcall-run"><FlumaStrain s={16} /><span className="grow">{stageT(xr.stage)}</span><span className="mono faint">{Math.round((xr.progress ?? 0) * 100)}%</span></div>
          ) : (
            <>
              <p className="faint small">{t("영상을 저화질로 받아 편집 요소 단위로 나눕니다. 1~2분 걸리고, 받은 영상은 분해도에서 지울 수 있어요.")}</p>
              <Button variant="secondary" icon="layers" onClick={() => startXray(x.id)}>{t("분해 시작")}</Button>
            </>
          )}
        </section>
        <span className="grow" />
        <div className="feed-f">
          <Button variant="ghost" icon="trash" onClick={async () => { const nxt = items[i + 1] ?? items[i - 1]; if (await dropItem(x)) { if (nxt) setCur(nxt.id); } }}>{t("목록에서 빼기")}</Button>
          <Button variant="primary" icon="sparkle" onClick={() => onMake(x)}>{t("이 패턴으로 만들기")}</Button>
        </div>
        <p className="faint small">{t("키: ↑↓ 넘기기 · 1 찜 · 2 보류 · 3 제외 · M 소리 · X 분해")}</p>
      </aside>
    </div>
  );
};
