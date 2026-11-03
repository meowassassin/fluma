/* 라이브러리 — 영상에 넣는 부품: 캐릭터(립싱크 진행자) · 3D 모델(Blender 개체 요소로 움직이는 동물 · 사람 · 사물).
   탭은 주소(/library/:tab). 카드를 고르면 옆 시트에 자세히 · 쓰기와 고치기는 에이전트에게(입력칸에 미리 채움).
   룩 · 브랜드 키트는 2026-10-29 제거 — 색은 영상마다 디자인 방향이 정한다. */
import React, { useEffect, useState } from "react";
import { NavLink, Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "../../ui/Icon";
import { Button, EmptyState, IconButton, Skeleton, Tag, cx } from "../../ui/kit";
import { useCharacters } from "../../lib/queries";
import { useUi } from "../../lib/ui";
import { AgentDock } from "../agent/AgentDock";
import { t } from "../../lib/i18n";

type Tab = "characters" | "models";
interface Char { name: string; title: string; summary?: string; personality?: string; catchphrases?: string[]; base: string; eyes_closed: string; mouths: Record<string, string> }
interface Model3D { name: string; title: string; kind: string; actions: string[]; license: string; commercial: string; credit: string; source: string }
type Pick = { k: "char"; name: string } | { k: "model"; name: string } | null;

const MOUTH_KO: Record<string, string> = { closed: "닫힘", a: "아", e: "에", i: "이", o: "오", u: "우" };
const KIND_KO: Record<string, string> = { animal: "동물", person: "사람", object: "사물", vehicle: "탈것" };

export const LibraryPage: React.FC = () => {
  const raw = useParams().tab;
  const tab: Tab = raw === "models" ? "models" : "characters";
  const { data: chars = [], isLoading: cLoading } = useCharacters();
  const { data: cat, isLoading: mLoading } = useQuery({ queryKey: ["assets3d"], staleTime: 5 * 60_000,
    queryFn: async ({ signal }) => { const r = await fetch("/api/assets3d", { signal }); return r.ok ? (await r.json() as { models: Model3D[]; more?: string }) : { models: [] }; } });
  const models = cat?.models ?? [];
  const [pick, setPick] = useState<Pick>(null);
  const [prefill, setPrefill] = useState<string | null>(null);
  useEffect(() => setPick(null), [tab]);
  if (raw && raw !== tab) return <Navigate to="/library/characters" replace />;
  const ask = (s: string) => { useUi.getState().set({ agentOpen: true }); setPrefill(s); };

  const selChar = pick?.k === "char" ? (chars as unknown as Char[]).find((c) => c.name === pick.name) : undefined;
  const selModel = pick?.k === "model" ? models.find((m) => m.name === pick.name) : undefined;
  const TABS: [Tab, string, string, number][] = [["characters", "캐릭터", "user", chars.length], ["models", "3D 모델", "video", models.length]];
  const loading = tab === "characters" ? cLoading : mLoading;

  return (
    <div className="page">
      <div className="pg-main">
        <header className="page-head">
          <h1>{t("라이브러리")}</h1>
          <nav className="tabs" aria-label={t("부품 종류")}>
            {TABS.map(([k, l, ic, n]) => <NavLink key={k} to={`/library/${k}`} className={({ isActive }) => cx("tab", isActive && "on")}><Icon n={ic} s={14} />{t(l)}<em>{n}</em></NavLink>)}
          </nav>
          <span className="grow" />
          {tab === "characters" && <Button size="sm" variant="agent" icon="agent" onClick={() => ask(t("새 캐릭터를 그려 줘. 생김새 · 성격: "))}>{t("새 캐릭터")}</Button>}
        </header>
        <div className="pg-split">
          <div className="pg-scroll">
            <p className="pg-intro muted">{tab === "characters"
              ? t("캐릭터는 화면 구석에서 나레이션에 맞춰 립싱크하는 진행자예요. 영상 편집기 → 속성 → 캐릭터에서 고릅니다.")
              : t("3D 모델은 장면 안에 개체 하나로 들어갑니다(걷는 동물 · 사람 등). 배경 · 글자는 2D 그대로, 움직여야 사는 것 하나만 Blender 로 렌더해 겹칩니다.")}</p>
            {loading ? <div className="lgrid">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} h={0} r={12} className="lk-skel" />)}</div> : tab === "characters" ? (
              !chars.length ? <EmptyState icon="user" title={t("캐릭터가 없어요")} body={t("화면 구석에서 나레이션에 맞춰 립싱크하는 진행자를 만들 수 있어요.")} action={<Button variant="agent" icon="agent" onClick={() => ask(t("새 캐릭터를 그려 줘. 생김새 · 성격: "))}>{t("캐릭터 만들기")}</Button>} /> :
                <div className="lgrid">{(chars as unknown as Char[]).map((c) => (
                  <button key={c.name} className={cx("lcard", pick?.k === "char" && pick.name === c.name && "on")} onClick={() => setPick({ k: "char", name: c.name })}>
                    <div className="ccard-im"><CharFace c={c} /></div>
                    <b>{c.title}</b><span>{c.personality ?? c.summary}</span>
                  </button>))}</div>
            ) : (
              !models.length ? <EmptyState icon="video" title={t("3D 모델 카탈로그가 비었어요")} body={t("assets3d/catalog.json 에 라이선스와 함께 모델을 적어 두면 여기에 나타납니다.")} /> :
                <>
                  <div className="lgrid wide">{models.map((m) => (
                    <button key={m.name} className={cx("lcard", pick?.k === "model" && pick.name === m.name && "on")} onClick={() => setPick({ k: "model", name: m.name })}>
                      <div className="mcard-im"><Icon n="video" s={28} /><span>{KIND_KO[m.kind] ? t(KIND_KO[m.kind]) : m.kind}</span></div>
                      <b>{m.title}</b><span>{t("동작 {v}", { v: m.actions.map((a) => (a === "*" ? t("기본 동작") : a)).join(" · ") })}</span>
                    </button>))}</div>
                  {cat?.more && <p className="field-h mt">{cat.more}</p>}
                </>
            )}
          </div>
          {pick && (
            <aside className="sheet" aria-label={t("고른 부품")}>
              <div className="sheet-h"><b>{selChar ? t("캐릭터") : t("3D 모델")}</b><span className="grow" /><IconButton icon="close" label={t("닫기")} size="sm" onClick={() => setPick(null)} /></div>
              <div className="sheet-b">
                {selChar && <CharDetail c={selChar} />}
                {selModel && <ModelDetail m={selModel} />}
              </div>
              <div className="sheet-f">
                {selChar && <Button variant="agent" icon="agent" onClick={() => ask(t("캐릭터 {name}({title})을 이렇게 고쳐 줘: ", { name: selChar.name, title: selChar.title }))}>{t("에이전트로 고치기")}</Button>}
                {selModel && <Button variant="agent" icon="agent" onClick={() => ask(t("지금 만드는 영상의 장면 _ 에 {title} 모델({name})을 Blender 개체 요소로 넣어 줘. 동작: {action}. ", { title: selModel.title, name: selModel.name, action: selModel.actions[0] }))}>{t("영상에 넣어 달라고 하기")}</Button>}
              </div>
            </aside>
          )}
        </div>
      </div>
      <AgentDock sessionId="_workspace" title={t("에이전트 · 라이브러리")} context={{ menu: "character", selection: selChar ? t("캐릭터 {name}", { name: selChar.name }) : selModel ? t("3D 모델 {name}", { name: selModel.name }) : undefined }}
        chip={selChar ? { label: t("캐릭터 {name}", { name: selChar.title }), onClear: () => setPick(null) } : selModel ? { label: t("3D 모델 {name}", { name: selModel.title }), onClear: () => setPick(null) } : null}
        hints={tab === "characters" ? [t("IT 설명 채널에 맞는 진행자 캐릭터 하나 그려 줘")] : [t("걷는 고양이 같은 CC0 동물 모델을 찾아서 카탈로그에 추가해 줘")]}
        placeholder={tab === "characters" ? t("예: 캐릭터 눈을 더 크게") : t("예: 이 모델로 장면 2에 걸어가는 여우를 넣어 줘")} prefill={prefill} onPrefillUsed={() => setPrefill(null)} />
    </div>
  );
};

const ModelDetail: React.FC<{ m: Model3D }> = ({ m }) => (
  <>
    <div className="sheet-sec"><h4>{m.title}</h4><p className="muted">{KIND_KO[m.kind] ? t(KIND_KO[m.kind]) : m.kind} · {t("투명 배경으로 렌더해 2D 장면 위에 겹칩니다.")}</p></div>
    <div className="sheet-sec"><h4>{t("동작")}</h4><div className="chips-row">{m.actions.map((a) => <Tag key={a}>{a === "*" ? t("기본 동작") : a}</Tag>)}</div></div>
    <div className="sheet-sec"><h4>{t("라이선스")}</h4>
      <p className="muted">{m.license}</p>
      <div className="chips-row mt"><Tag tone={m.commercial.startsWith("가능") ? "ok" : "warn"}>{t("상업 {v}", { v: m.commercial })}</Tag></div>
      <div className="field-l mt">{t("영상 설명에 넣을 출처")}</div><p className="muted mono small">{m.credit}</p>
      <a className="link mt" href={m.source} target="_blank" rel="noreferrer"><Icon n="external" s={11} />{t("원본")}</a>
    </div>
  </>
);

const CharDetail: React.FC<{ c: Char }> = ({ c }) => (
  <>
    <div className="sheet-hero char"><CharFace c={c} /></div>
    <div className="sheet-sec"><h4>{c.title}</h4><p className="muted">{c.summary}</p>{c.personality && <p className="muted">{t("성격: {v}", { v: c.personality })}</p>}</div>
    {!!c.catchphrases?.length && <div className="sheet-sec"><h4>{t("입버릇")}</h4><div className="chips-row">{c.catchphrases.map((p) => <Tag key={p}>{p}</Tag>)}</div></div>}
    <div className="sheet-sec"><h4>{t("입 모양")} <span className="faint">{t("{n}개 · 한글 모음으로 립싱크", { n: Object.keys(c.mouths).length })}</span></h4>
      <div className="mouths">{Object.entries(c.mouths).map(([k, u]) => <span key={k} className="mouth"><span className="mouth-face"><img src={c.base} alt="" /><img src={u} alt="" /></span><em>{MOUTH_KO[k] ? t(MOUTH_KO[k]) : k}</em></span>)}</div></div>
  </>
);

/** 말하는 캐릭터: 입 모양을 차례로 돌리고 가끔 눈을 감는다. 움직임 줄이기 설정이면 멈춘 그림 */
export const CharFace: React.FC<{ c: Char }> = ({ c }) => {
  const seq = ["a", "closed", "e", "i", "closed", "o", "u", "closed"];
  const [k, setK] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const h = setInterval(() => setK((x) => x + 1), 170); return () => clearInterval(h);
  }, []);
  const m = c.mouths[seq[k % seq.length]] ?? c.mouths.closed;
  return (
    <div className="charface" role="img" aria-label={t("{name} 캐릭터", { name: c.title })}>
      <img src={c.base} alt="" />{m && <img src={m} alt="" />}{k % 22 === 0 && <img src={c.eyes_closed} alt="" />}
    </div>
  );
};
