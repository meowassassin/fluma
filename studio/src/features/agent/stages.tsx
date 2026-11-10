/* 에이전트 진행을 '단계'로 — 도구 호출(읽기 · 명령 · 고치기 …)을 사람이 알아듣는 제작 단계로 묶고, 결과는 칩으로.
 * 2026-11-10: 대화창에 파일 경로 · 명령 · '단계 75개'가 그대로 나와 무엇이 진행되는지 알기 어려웠다(데모 화면이 실제보다 나아 보였다).
 * 단계를 누르면 그 단계의 도구 호출(명령 · 경로)이 펼쳐진다. */
import React, { useEffect, useState } from "react";
import { Icon } from "../../ui/Icon";
import { FlumaBounce } from "../../ui/BrandIcons";
import { cx } from "../../ui/kit";
import { TOOL_KO } from "../../lib/agent";
import { t } from "../../lib/i18n";
import type { ChatTool } from "../../lib/types";

type Tool = ChatTool & { id: string; done?: boolean };
type StageKey = "ref" | "research" | "plan" | "story" | "voice" | "music" | "capture" | "scene" | "knob" | "draft" | "final" | "look";

const LABEL: Record<StageKey, string> = {
  ref: "레퍼런스 분석", research: "사실 조사", plan: "기획", story: "콘티", voice: "목소리", music: "음악", scene: "장면 만들기",
  capture: "화면 녹화", knob: "값 조정", draft: "초안 렌더", final: "최종 렌더", look: "확인 · 준비",
};

/** 도구 이름 · 입력(명령 · 경로)으로 단계를 가른다 — 순서가 중요(값 조정 → 렌더 · 제작 → 최종 렌더) */
export function stageOf(x: Pick<ChatTool, "name" | "input">): StageKey {
  const s = `${x.name} ${x.input || ""}`;
  if (/knob\.py/.test(s)) return "knob";
  if (x.name === "WebSearch" || x.name === "WebFetch" || /data\/research\//.test(s)) return "research";
  if (/analyze_ref|shorts_xray|ref_style|ref_channel|trends\.py|see\.py (ref|ask|cliches|moments)|\/xray\//.test(s)) return "ref";
  if (/music_pick|trend_music/.test(s)) return "music";
  if (/voice_match|assemble_audio|tts\.py|data\/audio\/|data\/public\/audio\/|\.timing\.json|\.words\.json/.test(s)) return "voice";
  if (/capture\/(demo|termrec|webrec|capture|clip|stock|meme)\.py|\/demo\/|\/web\/|uploads\//.test(s)) return "capture";
  if (/produce\.py|render\.py[^\n]*--draft/.test(s)) return "draft";
  if (/render\.py/.test(s)) return "final";
  if (/concepts\.py|feel\.py|decide\.py|gate\.py|data\/workspace\/(concepts|feel)\//.test(s)) return "plan";
  if (/data\/storyboards\/|lint\.py|script\.py|direct\.py/.test(s)) return "story";
  if (/\/art\/|\/src\/[^ ]*\.py|materials|crafts\.py|blender|craft_script|illustrat|\.svg|^mcp__/.test(s) || x.name.startsWith("mcp__")) return "scene";
  // 정지 화면 보기 · 엔진 코드 찾기 · 결과 파일 열기 · ls 같은 나머지는 '확인 · 준비' 한 줄(흐리게, 맨 뒤)
  return "look";
}

/** 결과 줄(server agent.mjs resultLines) → 칩 글 */
function chipsOf(tools: Tool[]): string[] {
  const out: string[] = [];
  for (const x of tools) for (const ln of x.out || []) {
    const m = ln.match(/^changed=(.+)$/);
    if (m) { out.push(m[1].replace(/\.adjust\./, " · ").replace(/: null → /, " → ")); continue; }
    const s2 = ln.match(/^sound=(.+)$/);
    if (s2) { out.push(s2[1]); continue; }
    if (/^\[(음악|음성)\]/.test(ln)) out.push(ln.replace(/^\[(음악|음성)\]\s*/, (_, k) => `${k === "음성" ? "목소리" : k} · `));
  }
  return [...new Set(out)].slice(0, 6);
}

const shortInput = (s: string) => { try { const o = JSON.parse(s); return o.command ?? o.file_path ?? o.pattern ?? o.query ?? o.url ?? s; } catch { return s; } };

export const Stages: React.FC<{ tools: Tool[]; live?: boolean }> = ({ tools, live }) => {
  const groups: { key: StageKey; tools: Tool[] }[] = [];
  for (const x of tools) {
    const k = stageOf(x);
    const g = groups.find((y) => y.key === k);
    if (g) g.tools.push(x); else groups.push({ key: k, tools: [x] });
  }
  // '확인 · 준비'(정지 화면 보기 · 코드 찾기 · ls …)는 맨 뒤 흐린 줄 하나로
  groups.sort((a, b) => (a.key === "look" ? 1 : 0) - (b.key === "look" ? 1 : 0));
  return <div className="stages">{groups.map((g) => <StageRow key={g.key} k={g.key} tools={g.tools} live={live} />)}</div>;
};

const StageRow: React.FC<{ k: StageKey; tools: Tool[]; live?: boolean }> = ({ k, tools, live }) => {
  const [open, setOpen] = useState(false);
  const running = !!live && tools.some((x) => !x.done);
  const err = tools.some((x) => x.error);
  const chips = chipsOf(tools);
  const t0 = Math.min(...tools.map((x) => x.t0 ?? Infinity));
  const last = tools[tools.length - 1];
  return (
    <div className={cx("stage", running && "run", err && "err", k === "look" && "faint-stage")}>
      <button className="stage-row" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="stage-i">{running ? <FlumaBounce s={13} label={t("진행 중")} /> : <Icon n="check" s={12} />}</span>
        <span className="stage-n">{t(LABEL[k])}</span>
        <span className="stage-c">{tools.length > 1 ? tools.length : ""}</span>
        {err && <span className="stage-w" title={t("이 단계에서 다시 시도한 호출이 있어요 — 펼쳐서 확인")}><Icon n="warn" s={11} /></span>}
        {running && Number.isFinite(t0) && <Ticker from={t0} />}
        {running && last?.input && <span className="stage-a ellipsis">{shortInput(last.input)}</span>}
        <span className={cx("stage-x", open && "open")}><Icon n="down" s={11} /></span>
      </button>
      {chips.length > 0 && <div className="stage-chips">{chips.map((c) => <span key={c} className="stage-chip">{c}</span>)}</div>}
      {open && (
        <div className="stage-detail">
          {tools.map((x, i) => (
            <div key={x.id ?? i} className={cx("stage-d", x.error && "err")}>
              <span className="stage-dn">{TOOL_KO[x.name] ? t(TOOL_KO[x.name]) : x.name}</span>
              <span className="stage-da">{shortInput(x.input)}</span>
            </div>))}
        </div>)}
    </div>
  );
};

const Ticker: React.FC<{ from: number }> = ({ from }) => {
  const [, tick] = useState(0);
  useEffect(() => { const h = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(h); }, []);
  const s = Math.max(0, Math.round((Date.now() - from) / 1000));
  return <span className="stage-t mono">{s < 60 ? t("{s}초", { s }) : t("{m}분 {s}초", { m: Math.floor(s / 60), s: s % 60 })}</span>;
};
