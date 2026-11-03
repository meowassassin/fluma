/* 통합 편집기(IDE) — VS Code 처럼: 탐색기(영상 구성 트리) · 편집 탭 · 경로 표시줄 · 편집 영역 · 상태 표시줄.
   트리는 Craft 의 파일 구조가 아니라 영상의 구조(컷 편집 · 장면 · 장면의 화면 · 그림 · 자막 · 소리)를 보여 주고,
   항목을 열면 그 항목의 편집 툴(Craft 앱 자체)이 편집 영역에 뜬다. 앱은 Fluma 가 켜질 때 이미 떠 있고(lib/craftPool),
   영상에 들어오자마자 그 영상의 프로젝트를 미리 넣어 두므로 여는 순간 바로 보인다 */
import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Icon } from "../../ui/Icon";
import { AppGlyph, type GlyphKind } from "../../ui/AppGlyph";
import { PublishView } from "./PublishView";
import { cx } from "../../ui/kit";
import { t } from "../../lib/i18n";
import { qc } from "../../lib/queries";
import type { Storyboard } from "../../lib/types";

type Stage = { stage: string; app: string; edited: boolean; tracks?: string[]; comps?: number };
type Asset = { stage: string; type: string; app: string; file: string; scenes: number[] };
type Files = { stages: Stage[]; assets: Asset[] };
/** 편집 대상 — craft: Craft 앱으로 여는 것(단계 · 자산), preview: Fluma 미리보기, info: 앱이 없는 항목 */
export type Node = { key: string; label: string; glyph: GlyphKind; app?: string; stage?: string; kind: "craft" | "preview" | "info" | "publish"; scene?: number; path: string[]; meta?: string; detail?: string[] };
type Group = { key: string; label: string; glyph: GlyphKind; app: string; nodes: Node[] };

const APP: Record<string, string> = { filmcraft: "FilmCraft", effectcraft: "EffectCraft", soundcraft: "SoundCraft", vectorcraft: "VectorCraft", gridcraft: "GridCraft", pdfcraft: "PdfCraft", photocraft: "PhotoCraft" };
const base = (f: string) => f.split("/").pop() ?? f;

export const useProjectFiles = (projectId: string) => useQuery<Files>({ queryKey: ["craft-files", projectId], staleTime: 10_000,
  // FilmCraft 편집 프로젝트가 생기기 전(콘티 · 음성 · 렌더 중)에는 자주 다시 읽어 생기는 즉시 연다
  refetchInterval: 15_000,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/projects/${projectId}/crafts`, { signal }); return r.ok ? (await r.json() as Files) : { stages: [], assets: [] }; } });

/** 트리 — 장면이 아니라 영상을 이루는 툴 단위(편집 · 소리 · 그래픽 · 그림 · 사진 · 데이터). 장면은 편집 타임라인 위의 구간일 뿐 */
export const useTree = (projectId: string, sb: Storyboard | null) => {
  const { data } = useProjectFiles(projectId);
  useEffect(() => { const f = () => qc.invalidateQueries({ queryKey: ["craft-files", projectId] }); window.addEventListener("fluma:craft-saved", f); return () => window.removeEventListener("fluma:craft-saved", f); }, [projectId]);
  return useMemo(() => {
    const st = (s: string) => data?.stages.find((x) => x.stage === s);
    const title = sb?.title ?? "";
    const uses = (a: Asset) => (a.scenes.length ? t("장면 {n}", { n: a.scenes.join("·") }) : t("올린 파일"));
    const top: Node = { key: "edit", label: t("편집 · 미리보기"), glyph: "film", app: "filmcraft", stage: "edit", kind: "craft", path: [title, t("편집 · 미리보기")], meta: `${sb?.scenes.length ?? 0} ${t("장면")}` };
    const groups: Group[] = [];
    const au = st("audio") ?? { stage: "audio", app: "soundcraft", edited: false, tracks: ["Voice"] };
    {
      const TR: Record<string, { label: string; glyph: GlyphKind }> = { Voice: { label: "나레이션 · 자막", glyph: "voice" }, Music: { label: "음악", glyph: "music" }, SFX: { label: "효과음", glyph: "sfx" } };
      const tracks = au.tracks?.length ? au.tracks : ["Voice"];
      groups.push({ key: "g-sound", label: t("소리"), glyph: "sound", app: "soundcraft", nodes: tracks.map((tr) => {
        const m = TR[tr] ?? { label: tr, glyph: "sound" as GlyphKind };
        return { key: `audio#${tr}`, label: t(m.label), glyph: m.glyph, app: "soundcraft", stage: "audio", kind: "craft" as const, path: [title, t("소리"), t(m.label)],
          meta: tr === "Voice" ? `${sb?.scenes.length ?? 0} ${t("문장")}` : undefined };
      }) });
    }
    const mo = st("motion");
    if (mo) groups.push({ key: "g-motion", label: t("그래픽"), glyph: "motion", app: "effectcraft", nodes: [
      { key: "motion", label: t("화면 그래픽"), glyph: "motion", app: "effectcraft", stage: "motion", kind: "craft", path: [title, t("그래픽")], meta: mo.comps ? t("컴포지션 {n}", { n: mo.comps }) : undefined }] });
    const assetGroup = (key: string, label: string, glyph: GlyphKind, app: string, pick: (a: Asset) => boolean) => {
      const xs = (data?.assets ?? []).filter(pick);
      if (xs.length) groups.push({ key, label, glyph, app, nodes: xs.map((a) => ({ key: a.stage, label: base(a.file), glyph, app: a.app, stage: a.stage, kind: "craft" as const, path: [title, label, base(a.file)], meta: uses(a) })) });
    };
    assetGroup("g-vector", t("그림"), "vector", "vectorcraft", (a) => a.app === "vectorcraft");
    assetGroup("g-photo", t("사진"), "photo", "photocraft", (a) => a.app === "photocraft");
    assetGroup("g-data", t("데이터"), "grid", "gridcraft", (a) => a.app === "gridcraft");
    assetGroup("g-doc", t("문서"), "doc", "pdfcraft", (a) => a.app === "pdfcraft");
    const publish: Node = { key: "publish", label: t("게시 · 성과"), glyph: "stats", kind: "publish", path: [title, t("게시 · 성과")], meta: "YouTube" };
    const all = [top, ...groups.flatMap((g) => g.nodes), publish];
    return { top, groups, publish, all, edited: new Set((data?.stages ?? []).filter((s) => s.edited).map((s) => s.stage)) };
  }, [data, sb]);
};
type Tree = ReturnType<typeof useTree>;

/** 유기적 연결 — 재료 쪽(소리 · 그래픽 · 그림 · 사진 · 데이터)을 저장하면 그 결과를 쓰는 단계를 다시 만들고(초안 렌더: 재료 → 그래픽 → 믹스 → 편집),
    끝나면 목록을 새로 읽는다 → 바뀐 프로젝트가 앱들에 다시 들어간다(usePreload 가 해시로 알아챔). 편집(FilmCraft)을 저장하면 그대로 최종 */
export const useOrganic = (projectId: string) => {
  const [busy, setBusy] = useState<null | "running" | "failed">(null);
  useEffect(() => {
    let alive = true;
    const f = async (e: Event) => {
      const d = (e as CustomEvent<{ stage: string; project: string }>).detail;
      if (d.project !== projectId || d.stage === "edit") return;
      setBusy("running");
      try {
        const r = await fetch(`/api/projects/${projectId}/draft`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        if (!r.ok) throw new Error(String(r.status));
        if (alive) setBusy(null);
      } catch { if (alive) setBusy("failed"); }
      qc.invalidateQueries({ queryKey: ["craft-files", projectId] });
    };
    window.addEventListener("fluma:craft-saved", f);
    return () => { alive = false; window.removeEventListener("fluma:craft-saved", f); };
  }, [projectId]);
  return busy;
};

/* ---------------- 탐색기 ---------------- */
export const Explorer: React.FC<{ sb: Storyboard; tree: Tree; active: string; onOpen: (n: Node) => void }> = ({ sb, tree, active, onOpen }) => {
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
  const [rootOpen, setRootOpen] = useState(true);
  const toggle = (k: string) => setClosed((c) => { const x = new Set(c); x.has(k) ? x.delete(k) : x.add(k); return x; });
  const Row: React.FC<{ n: Node; depth: number }> = ({ n, depth }) => (
    <div role="treeitem" aria-selected={active === n.key} className={cx("ex-row", active === n.key && "on")} style={{ ["--d" as string]: depth }} onClick={() => onOpen(n)} title={n.app ? `${n.label} — ${APP[n.app] ?? n.app}` : n.label}>
      <Guides depth={depth} /><span className="ex-tw" /><AppGlyph k={n.glyph} s={16} />
      <span className="ex-l">{n.label}</span>
      {n.stage && tree.edited.has(n.stage) && <span className="ex-m" title={t("사람이 고침")}>M</span>}
      {n.meta && <span className="ex-d">{n.meta}</span>}
    </div>
  );
  // 폭 조절(오른쪽 가장자리를 끌기) — 이 브라우저에 기억
  const [w, setW] = useState(() => { try { return Number(localStorage.getItem("fluma.explorerW")) || 264; } catch { return 264; } });
  const drag = (e: React.PointerEvent) => {
    e.preventDefault();
    const x0 = e.clientX, w0 = w;
    const move = (ev: PointerEvent) => setW(Math.max(180, Math.min(520, w0 + ev.clientX - x0)));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); document.body.classList.remove("ex-resizing");
      setW((v) => { try { localStorage.setItem("fluma.explorerW", String(v)); } catch { /* 저장 못 해도 동작 */ } return v; }); };
    document.body.classList.add("ex-resizing");
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  return (
    <aside className="explorer" aria-label={t("탐색기")} style={{ width: w }}>
      <div className="ex-resize" role="separator" aria-orientation="vertical" aria-label={t("탐색기 폭 조절")} onPointerDown={drag} onDoubleClick={() => setW(264)} />
      <div className="ex-title">{t("탐색기")}</div>
      <div className="ex-sec" role="button" onClick={() => setRootOpen((v) => !v)}><Icon n="chevron" s={12} className={cx("ex-chev", rootOpen && "open")} /><b title={sb.title}>{sb.title}</b></div>
      {rootOpen && <div role="tree" className="ex-tree">
        <Row n={tree.top} depth={0} />
        {tree.groups.map((g) => (
          <React.Fragment key={g.key}>
            <div role="treeitem" aria-expanded={!closed.has(g.key)} className="ex-row ex-folder" style={{ ["--d" as string]: 0 }} onClick={() => toggle(g.key)} title={APP[g.app]}>
              <span className="ex-tw"><Icon n="chevron" s={12} className={cx("ex-chev", !closed.has(g.key) && "open")} /></span>
              <AppGlyph k={g.glyph} s={16} /><span className="ex-l">{g.label}</span><span className="ex-d">{APP[g.app]}</span>
            </div>
            {!closed.has(g.key) && g.nodes.map((n) => <Row key={n.key} n={n} depth={1} />)}
          </React.Fragment>
        ))}
        <Row n={tree.publish} depth={0} />
      </div>}
    </aside>
  );
};
const Guides: React.FC<{ depth: number }> = ({ depth }) => <>{Array.from({ length: depth }, (_, i) => <i key={i} className="ex-g" style={{ left: 16 + i * 16 }} />)}</>;

/* ---------------- 편집 탭 · 경로 · 편집 영역 ---------------- */
export const EditorArea: React.FC<{ projectId: string; sb: Storyboard; tabs: Node[]; active: Node | null; onOpen: (n: Node) => void; onClose: (n: Node) => void; preview: React.ReactNode }> = ({ projectId, sb, tabs, active, onOpen, onClose, preview }) => (
  <section className="editor">
    <div className="ed-tabs" role="tablist">
      {tabs.map((n) => (
        <div key={n.key} role="tab" aria-selected={active?.key === n.key} className={cx("ed-tab", active?.key === n.key && "on")} onClick={() => onOpen(n)} onAuxClick={(e) => { if (e.button === 1) onClose(n); }}>
          <AppGlyph k={n.glyph} s={15} /><span>{n.label}</span>
          <button className="ed-x" aria-label={t("닫기")} onClick={(e) => { e.stopPropagation(); onClose(n); }}><Icon n="close" s={12} /></button>
        </div>
      ))}
      <span className="grow" />
    </div>
    {active && <div className="ed-crumbs">{active.path.map((p, i) => <React.Fragment key={i}>{i > 0 && <Icon n="chevron" s={11} />}<span className={i === active.path.length - 1 ? "on" : ""}>{p}</span></React.Fragment>)}
      {active.app && <span className="ed-app">{APP[active.app] ?? active.app}</span>}</div>}
    <div className="ed-body">
      <div className="studio-mid" hidden={active?.kind !== "preview"}>{preview}</div>
      {active?.kind === "craft" && active.stage && <ResultView projectId={projectId} node={active} sb={sb} />}
      {active?.kind === "publish" && <PublishView projectId={projectId} sb={sb} />}
      {active?.kind === "info" && (
        <div className="einfo">
          <h3><AppGlyph k={active.glyph} s={18} />{active.label}</h3>
          {active.detail?.filter(Boolean).map((d, i) => <p key={i} className={i ? "faint" : ""}>{d}</p>)}
          <p className="faint small">{t("이 항목은 오른쪽 에이전트에게 말로 고치세요 — 고른 항목을 에이전트가 알고 있습니다.")}</p>
        </div>
      )}
      {!active && <div className="einfo faint">{t("왼쪽 탐색기에서 항목을 여세요")}</div>}
    </div>
  </section>
);

/** 결과물 보기 — 편집 툴 화면 대신 그 항목이 만든 결과(영상 · 음원 · 그림 · 표 · 문서). 다시 렌더되면 자동으로 새로 읽는다 */
type Result = { kind: "video" | "audio" | "image" | "table" | "pdf" | "none"; url?: string; rows?: string[][]; name?: string; note?: string; updated?: number };
const ResultView: React.FC<{ projectId: string; node: Node; sb: Storyboard }> = ({ projectId, node, sb }) => {
  const { data: r } = useQuery<Result>({ queryKey: ["result", projectId, node.stage], refetchInterval: 5_000,
    queryFn: async ({ signal }) => { const x = await fetch(`/api/projects/${projectId}/result/${encodeURIComponent(node.stage!)}`, { signal }); return x.ok ? x.json() : { kind: "none", note: t("결과를 읽지 못했어요") }; } });
  const voice = node.key === "audio#Voice";
  return (
    <div className="result">
      <div className="rs-stage">
        {!r ? <span className="faint small">{t("불러오는 중…")}</span>
          : r.kind === "video" ? <video key={r.url} src={r.url} controls playsInline className="rs-video" />
          : r.kind === "audio" ? <div className="rs-audio"><AppGlyph k={node.glyph} s={40} /><audio key={r.url} src={r.url} controls /></div>
          : r.kind === "image" ? <img key={r.url} src={r.url} alt={node.label} className="rs-img" />
          : r.kind === "pdf" ? <iframe key={r.url} src={r.url} title={node.label} className="rs-pdf" />
          : r.kind === "table" ? <table className="rs-table"><tbody>{(r.rows ?? []).map((row, i) => <tr key={i}>{row.map((c, j) => i ? <td key={j}>{c}</td> : <th key={j}>{c}</th>)}</tr>)}</tbody></table>
          : <span className="faint">{t(r.note ?? "아직 결과가 없어요")}</span>}
      </div>
      {voice && (
        <ol className="rs-lines">{sb.scenes.map((sc, i) => <li key={i}><b>{t("장면 {n}", { n: i + 1 })}</b><span>{sc.narration}</span><em>{sc.caption.replace(/\n/g, " / ")}</em></li>)}</ol>
      )}
      {r?.name && <div className="rs-meta faint small">{r.name}{r.updated ? ` · ${new Date(r.updated).toLocaleTimeString()}` : ""} · {t("고치려면 오른쪽 에이전트에게 말하세요")}</div>}
    </div>
  );
};

/* ---------------- 상태 표시줄 ---------------- */
export const StatusBar: React.FC<{ sb: Storyboard; tree: Tree; active: Node | null; rebuilding?: null | "running" | "failed"; explorerOpen: boolean; onToggleExplorer: () => void }> = ({ sb, tree, active, rebuilding, explorerOpen, onToggleExplorer }) => {
  const total = sb.scenes.reduce((a, s) => a + s.sec, 0);
  return (
    <footer className="statusbar">
      <button className="sb-b" onClick={onToggleExplorer} title={`${explorerOpen ? t("탐색기 접기") : t("탐색기 펴기")} (Ctrl+B)`}><Icon n="sidebarL" s={12} /></button>
      <span><Icon n="engine" s={12} />{sb.engine || "hyperframes"}</span>
      <span>{t("장면 {n}", { n: sb.scenes.length })} · {Math.round(total * 10) / 10}{t("초")}</span>
      {tree.edited.size > 0 && <span className="sb-m">M {tree.edited.size} · {t("사람이 고침")}</span>}
      {rebuilding === "running" && <span><Icon n="history" s={12} />{t("고친 재료로 다시 만드는 중 — 끝나면 편집에 반영됩니다")}</span>}
      {rebuilding === "failed" && <span className="sb-m"><Icon n="warn" s={12} />{t("다시 만들지 못했어요 — 에이전트에게 물어보세요")}</span>}
      <span className="grow" />
      {active?.app && <span>{APP[active.app] ?? active.app}</span>}
    </footer>
  );
};
