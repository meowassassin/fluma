/* Craft 앱 — ArtCraft 의 오픈소스 Photoshop · Illustrator · After Effects 류 앱을 Fluma 에 붙인다.
   · 설치(릴리스 받기 · SHA256 확인)는 사용자가 누를 때만. 진행률은 작업 SSE 로
   · 브라우저 빌드는 /crafts/:name 에서 Fluma 화면 안에 띄우고, 데스크톱 앱은 이 컴퓨터에서 창으로
   · '에이전트' 가 켜진 앱은 에이전트가 MCP 로 직접 다룬다(쓰기는 compositions/ 만) */
import React, { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, IconButton, Skeleton, Tag, Tip, cx } from "../../ui/kit";
import { FlumaStrain } from "../../ui/BrandIcons";
import { errMsg } from "../../lib/api";
import { qc } from "../../lib/queries";
import { t, useLang } from "../../lib/i18n";

export interface Craft {
  name: string; title: string; repo: string; kind: string; use: string; kind_en?: string; use_en?: string; order?: number; license?: string; agent?: boolean;
  agentOn: boolean; installed: { version: string; cli: boolean; bin: boolean; web: boolean } | null;
}
const KEY = ["crafts"];
const useCrafts = () => useQuery({ queryKey: KEY, staleTime: 30_000, queryFn: async ({ signal }) => { const r = await fetch("/api/crafts", { signal }); return r.ok ? (await r.json() as Craft[]) : []; } });
const call = async (method: string, url: string, body?: unknown) => {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.error?.message ?? j?.message ?? `HTTP ${r.status}`);
  return j;
};

/** 설치 진행 — 앱 이름 → { 진행률, 단계 } (화면을 옮겨도 유지) */
const installing = new Map<string, { p: number; stage: string }>();
const listeners = new Set<() => void>();
const ping = () => listeners.forEach((f) => f());
function useInstalling() { const [, tick] = useState(0); useEffect(() => { const f = () => tick((x) => x + 1); listeners.add(f); return () => { listeners.delete(f); }; }, []); return installing; }

async function install(c: Craft) {
  try {
    const { jobId } = await call("POST", `/api/crafts/${c.name}/install`);
    installing.set(c.name, { p: 0, stage: t("대기 중") }); ping();
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    const end = (ok: boolean, msg?: string) => {
      es.close(); installing.delete(c.name); ping(); qc.invalidateQueries({ queryKey: KEY });
      if (ok) toast.success(t("{title} 설치됨", { title: c.title })); else toast.error(t("{title} 설치 실패", { title: c.title }), { description: msg });
    };
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data);
      if (ev.type === "progress") { installing.set(c.name, { p: ev.progress ?? 0, stage: ev.stage ?? "" }); ping(); }
      else if (ev.type === "done") end(true);
      else if (ev.type === "failed" || ev.type === "canceled") end(false, ev.error);
    };
    es.addEventListener("end", () => es.close());
  } catch (e) { toast.error(t("설치를 시작하지 못했어요"), { description: errMsg(e) }); }
}

export const CraftsPage: React.FC = () => {
  const { data = [], isLoading } = useCrafts();
  const busy = useInstalling();
  const nav = useNavigate();
  const ko = useLang((s) => s.lang) === "ko";   // 앱 설명은 한국어 · 영어 두 벌(craft.json kind / kind_en)
  const toggle = async (c: Craft) => { try { await call("PUT", `/api/crafts/${c.name}`, { agent: !c.agentOn }); qc.invalidateQueries({ queryKey: KEY }); } catch (e) { toast.error(errMsg(e)); } };
  const open = async (c: Craft) => { try { await call("POST", `/api/crafts/${c.name}/open`); toast.success(t("{title} 창을 열었어요", { title: c.title })); } catch (e) { toast.error(errMsg(e)); } };
  const missing = data.filter((c) => !c.installed && !busy.has(c.name));
  return (
    <div className="page">
      <div className="pg-main">
        <header className="page-head">
          <h1>{t("Craft 앱")}</h1>
          <span className="faint small">{t("ArtCraft 의 오픈소스 제작 도구 · MIT / Apache-2.0")}</span>
          <span className="grow" />
          {missing.length > 1 && <Button size="sm" variant="secondary" icon="download" onClick={() => missing.forEach((c) => install(c))}>{t("모두 설치 ({n}개)", { n: missing.length })}</Button>}
        </header>
        <div className="pg-scroll">
          <p className="pg-intro muted">{t("벡터 그림 · 모션 그래픽 · 이미지 · 영상 · 소리를 진짜 제작 도구로 다룹니다. 화면 안(브라우저 빌드)이나 데스크톱 창으로 직접 고칠 수 있고, ‘에이전트’를 켠 앱은 에이전트가 MCP 로 직접 그리고 내보냅니다(쓰기는 compositions 폴더만).")}</p>
          {isLoading ? <div className="crgrid">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} h={150} r={12} />)}</div> : (
            <div className="crgrid">
              {data.map((c) => {
                const b = busy.get(c.name);
                return (
                  <article key={c.name} className={cx("crcard", c.installed && "on")}>
                    <div className="cr-h">
                      <b>{c.title}</b>
                      {c.installed ? <Tag tone="ok">{c.installed.version}</Tag> : <Tag>{t("설치 안 됨")}</Tag>}
                      <span className="grow" />
                      <a className="cr-gh" href={`https://github.com/${c.repo}`} target="_blank" rel="noreferrer" aria-label="GitHub"><Icon n="external" s={13} /></a>
                    </div>
                    <p className="cr-kind">{ko ? c.kind : c.kind_en ?? c.kind}</p>
                    <p className="cr-use faint">{ko ? c.use : c.use_en ?? c.use}</p>
                    {b ? (
                      <div className="cr-prog"><FlumaStrain s={14} /><span className="grow ellipsis">{b.stage}</span><span className="mono faint">{Math.round(b.p * 100)}%</span></div>
                    ) : (
                      <div className="cr-acts">
                        {!c.installed && <Button size="sm" variant="primary" icon="download" onClick={() => install(c)}>{t("설치")}</Button>}
                        {c.installed?.web && <Button size="sm" variant="secondary" icon="panel" onClick={() => nav(`/crafts/${c.name}`)}>{t("화면 안에서 열기")}</Button>}
                        {c.installed?.bin && <Button size="sm" variant="ghost" icon="external" onClick={() => open(c)}>{t("데스크톱 앱")}</Button>}
                        <span className="grow" />
                        {c.installed?.cli && (
                          <Tip label={c.agentOn ? t("에이전트가 이 앱을 씀 (누르면 끔)") : t("에이전트에 붙이기")}>
                            <button className={cx("cr-agent", c.agentOn && "on")} aria-pressed={c.agentOn} onClick={() => toggle(c)}><Icon n="agent" s={13} />{t("에이전트")}</button>
                          </Tip>)}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/** 브라우저 빌드를 Fluma 화면 안에 띄운다 */
export const CraftViewPage: React.FC = () => {
  const name = useParams().name ?? "";
  const { data = [] } = useCrafts();
  const c = data.find((x) => x.name === name);
  const src = `/api/crafts-web/${name}/index.html`;
  return (
    <div className="craft-view">
      <header className="craft-bar">
        <Link to="/crafts" className="craft-back"><Icon n="stepBack" s={14} />{t("Craft 앱")}</Link>
        <b>{c?.title ?? name}</b>{c?.installed && <span className="faint mono small">{c.installed.version}</span>}
        <span className="grow" />
        <IconButton icon="external" label={t("새 탭에서 열기")} size="sm" onClick={() => window.open(src, "_blank")} />
      </header>
      {c && !c.installed?.web
        ? <div className="craft-empty faint">{t("브라우저 빌드가 설치되지 않았어요.")} <Link to="/crafts">{t("설치하러 가기")}</Link></div>
        : <iframe className="craft-frame" src={src} title={c?.title ?? name} allow="clipboard-read; clipboard-write; fullscreen" />}
    </div>
  );
};
