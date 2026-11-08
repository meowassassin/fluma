import React, { Suspense, useEffect } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import { FlumaMark, Icon } from "../ui/Icon";
import { FlumaBounce, FlumaGlyph, FlumaStrain, RailIcon } from "../ui/BrandIcons";
import { Dialog, Kbd, Skeleton, Tip } from "../ui/kit";
import { t } from "../lib/i18n";

/** 화면 코드를 처음 받는 동안만 보인다. 이동은 startTransition 이라 그 뒤로는 이전 화면이 그대로 남는다 */
const PageLoading: React.FC = () => <div className="page-loading"><Skeleton w={220} h={18} /><Skeleton w={360} h={12} /><Skeleton w={300} h={12} /></div>;
import { typing, useUi } from "../lib/ui";
import { useActiveAgents, useConnection, useProducing, useProjects } from "../lib/queries";

export const AppShell: React.FC = () => {
  const ui = useUi();
  const loc = useLocation();
  const conn = useConnection();
  const inStudio = loc.pathname.startsWith("/p/");

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.code === "KeyK") { e.preventDefault(); useUi.getState().set({ paletteOpen: !useUi.getState().paletteOpen }); return; }
      if (mod && e.code === "KeyJ") { e.preventDefault(); useUi.getState().set({ agentOpen: !useUi.getState().agentOpen }); return; }
      if (!typing(e) && !mod && e.key === "?") { e.preventDefault(); useUi.getState().set({ shortcutsOpen: true }); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  return (
    <div className="app">
      <nav className="rail" aria-label={t("주 메뉴")}>
        <Link to="/" className="rail-logo" aria-label={t("Fluma 홈")}><FlumaMark s={28} /></Link>
        <RailLink to="/" icon="home" label={t("홈")} end />
        <VideosLink />
        <RailLink to="/trends" icon="trend" label={t("트렌드")} />
        <div className="rail-sep" />
        <AgentToggle />
        <div className="grow" />
        <Tip label={t("검색 · 명령")} kbd="Mod+K" side="right">
          <button className="rail-b" onClick={() => ui.set({ paletteOpen: true })} aria-label={t("검색 · 명령")}><RailIcon n="search" /></button>
        </Tip>
        <Tip label={t("단축키")} kbd="?" side="right">
          <button className="rail-b" onClick={() => ui.set({ shortcutsOpen: true })} aria-label={t("단축키")}><RailIcon n="keys" /></button>
        </Tip>
        <RailLink to="/settings/agent" icon="gear" label={t("설정")} match="/settings" />
      </nav>
      <div className={`main ${inStudio ? "is-studio" : ""}`}>
        {conn === "down" && (
          <div className="conn-banner" role="status"><Icon n="warn" s={14} />{t("서버와 연결이 끊겼어요. 다시 붙는 중… (편집한 내용은 연결되면 다시 불러옵니다)")}</div>
        )}
        <Suspense fallback={<PageLoading />}><Outlet /></Suspense>
      </div>
      <Palette />
      <Shortcuts />
    </div>
  );
};

/** 오른쪽 에이전트 창 열기/닫기 — 창과 같은 상태를 보여 준다(열림 = 켜짐, 일하는 중 = 점) */
const AgentToggle: React.FC = () => {
  const open = useUi((s) => s.agentOpen);
  const loc = useLocation();
  const { data: active = [] } = useActiveAgents();   // 서버 기준 — 창을 안 열어 둔 대화도 포함
  const busy = active.length > 0;
  // 영상 제작(음성 · 화면 · 렌더) 중이면 끙끙대는 아이콘, 대화 · 기획만 하면 통통 튀는 아이콘
  const producing = useProducing().length > 0 || active.some((a) => !a.id.startsWith("_") && a.skill !== "plan");
  const none = loc.pathname.startsWith("/settings");
  return (
    <Tip label={none ? t("설정 화면에는 에이전트 창이 없어요") : open ? t("에이전트 창 닫기") : t("에이전트 창 열기")} kbd={none ? undefined : "Mod+J"} side="right">
      <button className={`rail-b ${open && !none ? "on" : ""} ${none ? "disabled" : ""}`} aria-pressed={open && !none} aria-disabled={none}
        aria-label={t("에이전트 창")} onClick={() => !none && useUi.getState().set({ agentOpen: !open })}>
        <span className="rail-ic">{producing ? <FlumaStrain s={24} tone="gray" /> : busy ? <FlumaBounce s={24} tone="gray" /> : <FlumaGlyph s={26} tone="gray" />}</span>
      </button>
    </Tip>
  );
};

/** '영상' — 제작 중(음성 · 화면 · 렌더)인 영상 수를 숫자 알림으로 */
const VideosLink: React.FC = () => {
  const n = useProducing().length;
  return <RailLink to="/videos" icon="film" label={n ? t("영상 · 제작 중 {n}편", { n }) : t("영상")} match={["/videos", "/p/"]} badge={n} />;
};

const RailLink: React.FC<{ to: string; icon: string; label: string; end?: boolean; match?: string | string[]; disabled?: boolean; tip?: string; badge?: number }> = ({ to, icon, label, end, match, disabled, tip, badge }) => {
  const loc = useLocation();
  // 툴팁(asChild)이 className 함수를 망가뜨리므로 활성 여부를 직접 계산해 문자열로 넘긴다
  const active = match ? [match].flat().some((m) => loc.pathname.startsWith(m)) : end ? loc.pathname === to : loc.pathname.startsWith(to);
  const el = disabled
    ? <span className="rail-b disabled" aria-disabled="true" aria-label={label} tabIndex={0}><RailIcon n={icon} /></span>
    : <Link to={to} className={`rail-b ${active ? "on" : ""}`} aria-label={label} aria-current={active ? "page" : undefined}><span className="rail-ic"><RailIcon n={icon} />{!!badge && <b className="rail-badge mono">{badge > 9 ? "9+" : badge}</b>}</span></Link>;
  return <Tip label={tip ?? label} side="right">{el}</Tip>;
};

/* ---------- 명령 팔레트 (Ctrl/⌘ K) ---------- */
const Palette: React.FC = () => {
  const { paletteOpen, set } = useUi();
  const nav = useNavigate();
  const { data: projects = [] } = useProjects();
  const go = (to: string) => { set({ paletteOpen: false }); nav(to); };
  const list = projects.filter((p) => !p.id.startsWith("_")).sort((a, b) => (a.updated < b.updated ? 1 : -1));
  return (
    <Dialog open={paletteOpen} onOpenChange={(v) => set({ paletteOpen: v })} title={t("검색 · 명령")} width={560}>
      <Command className="cmdk" label={t("검색 · 명령")} loop>
        <div className="cmdk-in"><Icon n="search" s={16} /><Command.Input autoFocus placeholder={t("영상 · 화면 · 명령 찾기")} /></div>
        <Command.List className="cmdk-list">
          <Command.Empty className="cmdk-empty">{t("찾는 것이 없어요")}</Command.Empty>
          <Command.Group heading={t("만들기")}>
            <Command.Item onSelect={() => go("/?new=1")}><Icon n="plus" s={15} />{t("새 영상 만들기")}</Command.Item>
          </Command.Group>
          <Command.Group heading={t("이동")}>
            <Command.Item onSelect={() => go("/")}><Icon n="home" s={15} />{t("홈")}</Command.Item>
            <Command.Item onSelect={() => go("/trends")}><Icon n="trend" s={15} />{t("트렌드")}</Command.Item>
            <Command.Item onSelect={() => go("/crafts")}><Icon n="palette" s={15} />{t("Craft 앱 (Photoshop · Illustrator · After Effects 류)")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/agent")}><Icon n="agent" s={15} />{t("설정 · 에이전트")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/agent")}><Icon n="agent" s={15} />{t("설정 · 모델 · 공급자")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/voice")}><Icon n="mic" s={15} />{t("설정 · 미디어 · 음성")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/gen")}><Icon n="sparkle" s={15} />{t("설정 · 미디어 · 이미지 · 영상 생성")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/render")}><Icon n="engine" s={15} />{t("설정 · 미디어 · 렌더 엔진")}</Command.Item>
            <Command.Item onSelect={() => go("/settings/memory")}><Icon n="memory" s={15} />{t("설정 · 기억")}</Command.Item>
            <Command.Item onSelect={() => { set({ paletteOpen: false, shortcutsOpen: true }); }}><Icon n="keyboard" s={15} />{t("단축키 보기")}</Command.Item>
          </Command.Group>
          {list.length > 0 && (
            <Command.Group heading={t("영상")}>
              {list.slice(0, 50).map((p) => (
                <Command.Item key={p.id} value={`${p.title} ${p.id}`} onSelect={() => go(`/p/${p.id}`)}><Icon n="film" s={15} /><span className="ellipsis">{p.title || t("제목 없음")}</span></Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </Dialog>
  );
};

/* ---------- 단축키 표 (?) ---------- */
const SHORTCUTS: [string, [string, string][]][] = [
  ["어디서나", [["Mod+K", "검색 · 명령"], ["Mod+J", "에이전트 패널 열기/닫기"], ["?", "단축키 보기"]]],
  ["영상 · 재생", [["Space", "재생 / 멈춤"], ["←", "한 프레임 뒤"], ["→", "한 프레임 앞"], ["Shift+←", "1초 뒤"], ["Shift+→", "1초 앞"], ["Home", "처음으로"], ["End", "끝으로"], ["[", "이전 장면"], ["]", "다음 장면"]]],
  ["영상 · 보기", [["클릭", "화면의 그 자리를 짚어 에이전트에게 넘기기"], ["G", "쇼츠 안전 영역"], ["Esc", "짚은 자리 · 고른 장면 해제"]]],
  ["영상 · 기타", [["Enter", "에이전트에게 보내기 (입력칸에서)"], ["Shift+Enter", "입력칸 줄바꿈"], ["R", "렌더"]]],
];
const Shortcuts: React.FC = () => {
  const { shortcutsOpen, set } = useUi();
  return (
    <Dialog open={shortcutsOpen} onOpenChange={(v) => set({ shortcutsOpen: v })} title={t("단축키")} width={620}>
      <div className="sc-grid">
        {SHORTCUTS.map(([g, rows]) => (
          <div key={g} className="sc-g"><h4>{t(g)}</h4>{rows.map(([k, d]) => <div key={k} className="sc-r"><span>{t(d)}</span><Kbd k={k === "클릭" ? t(k) : k} /></div>)}</div>
        ))}
      </div>
      <p className="sc-note">{t("한글 입력 상태에서도 단축키가 동작합니다(키 위치 기준).")}</p>
    </Dialog>
  );
};
