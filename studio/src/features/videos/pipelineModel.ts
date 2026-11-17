/* 파이프라인 상태 모델 — 영상 목록 · 파이프라인 그래프 · 편집기 옆 패널이 같이 쓴다.
   경로(생성 · 클립 재편집 · 실제 자료)마다 단계 노드와 연결을 만들고, 실시간 상태(/live: 작업 · 에이전트)를 겹친다.
   글자는 최소 — 단계 이름(짧게)과 상태 · 모델만. 자세한 말은 title(마우스를 올리면)로. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Pipeline, type PipelineLive } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { GlyphKind } from "../../ui/AppGlyph";

export type State = "done" | "running" | "waiting" | "error" | "todo";
/** tile: 앱 아이콘처럼 칸을 꽉 채우는 그림 · dark: 어두운 바탕에 · planned: 아직 안 한 단계 — 지금 설정대로라면 쓸 모델(흐리게) */
export interface Model { name: string; id?: string; src?: string | null; glyph?: GlyphKind; tile?: boolean; dark?: boolean; planned?: boolean; unknown?: boolean }
export interface Step { key: string; name: string; col: number; row: number; state: State; models: Model[]; tip: string; progress?: number | null }
export type Edge = [string, string];

const I = (f: string) => `/api/engine-icons/${f}`;
const RUNTIME: Record<string, Model> = {
  claude: { name: "Claude Code", id: "claude", src: I("agent-claude.svg") },
  cursor: { name: "Cursor Agent", id: "cursor", src: I("agent-cursor.svg") },
  codex: { name: "Codex", id: "codex", src: I("agent-codex.svg") },
  antigravity: { name: "Antigravity", id: "antigravity", src: I("antigravity.svg") },
};
const VOICE: Record<string, string> = {
  edge: "Edge TTS", typecast: "Typecast", elevenlabs: "ElevenLabs", melotts: "MeloTTS", xtts: "XTTS", cosyvoice: "CosyVoice",
  chatterbox: "Chatterbox", supertonic: "Supertonic", espeak: "eSpeak", silent: "무음",
};
const BACKEND: Record<string, string> = { flow: "Google Flow", gflow: "Google Flow", antigravity: "Antigravity", mock: "모의 생성" };
/** veo_3_1_lite → Veo 3.1 Lite */
export const prettyModel = (m: string) => m.split(/[_\s-]+/).reduce<string[]>((a, w) => {
  if (/^\d+$/.test(w) && a.length && /\d$/.test(a[a.length - 1])) a[a.length - 1] += `.${w}`; else a.push(w.charAt(0).toUpperCase() + w.slice(1));
  return a;
}, []).join(" ");

const JOB_STEP: Record<string, string> = {
  "캐릭터 시트 만들기": "character", "키 프레임 만들기": "keyframe", "영상 생성": "video", "편집 초안": "draft",
  "클립 재편집 초안": "draft", "실제 자료 초안": "draft", "최종 렌더": "publish",
};
const jobStep = (j: PipelineLive["jobs"][number]) => (j.label && JOB_STEP[j.label]) || ({ voice: "voice", upload: "publish", draft: "draft", render: "publish" } as Record<string, string>)[j.type] || null;

/* ---------- 실제 기록 → 모델 아이콘 ---------- */
const UNKNOWN: Model = { name: "기록 없음", unknown: true };
const CRAFT_ICON: Record<string, string> = {
  filmcraft: "craft-filmcraft.svg",
  effectcraft: "craft-effectcraft.svg",
  soundcraft: "craft-soundcraft.svg",
  vectorcraft: "craft-vectorcraft.svg",
  photocraft: "craft-photocraft.svg",
  figcraft: "craft-figcraft.svg",
  solidcraft: "craft-solidcraft.png",
  cadcraft: "craft-cadcraft.png",
  deckcraft: "craft-deckcraft.svg",
  gridcraft: "craft-gridcraft.svg",
  pdfcraft: "craft-pdfcraft.svg",
  wordcraft: "craft-wordcraft.svg",
  lightcraft: "craft-lightcraft.svg",
  texturecraft: "craft-texturecraft.svg",
  designcraft: "craft-designcraft.svg",
  "craft-anything": "craft-craft-anything.svg",
};
/** 서버가 알려 준 도구 id(status.py material_tool) → 아이콘. Craft 앱이 아닌 출처(화면 녹화 · 스톡 · 파일)도 같은 자리 */
const TOOL: Record<string, Model> = {
  "capture:terminal": { name: "터미널 녹화", glyph: "doc" },
  "capture:web": { name: "웹 화면 녹화", glyph: "scene" },
  "capture:file": { name: "캡처 · 파일", glyph: "photo" },
  stock: { name: "스톡 영상(Pexels · Pixabay)", src: I("pexels.svg") },
};
const craftModel = (app: string): Model => {
  const k = app.toLowerCase();
  if (TOOL[k]) return { ...TOOL[k], name: t(TOOL[k].name) };
  return CRAFT_ICON[k]
    ? { name: k.replace(/craft$/, "Craft").replace(/^./, (c) => c.toUpperCase()), src: I(CRAFT_ICON[k]), tile: true }
    : { name: app, glyph: "film" };
};
/** 이미지 · 영상 모델 이름 → 아이콘(Google 모델은 DeepMind/Veo/Flow 마크, Nano Banana 는 제 마크) */
function genModel(name: string | null | undefined, via?: string | null): Model {
  const n = String(name || "");
  if (!n) return UNKNOWN;
  if (/mock/i.test(n)) return { name: t("모의 생성"), glyph: "video" };
  const label = `${/^[a-z0-9_]+$/.test(n) ? prettyModel(n) : n}${via ? ` · ${via.startsWith("agy") || via === "antigravity" ? "Antigravity" : BACKEND[via] || via}` : ""}`;
  if (/veo/i.test(n)) return { name: label, src: I("veo.svg") };
  if (/flow/i.test(via || "") || /flow/i.test(n)) return { name: label, src: I("flow.svg") };
  if (/antigravity|agy/i.test(via || "") || /antigravity/i.test(n)) return { name: label, src: I("antigravity.svg") };
  if (/nano|banana/i.test(n)) return { name: label, src: I("nanobanana.svg"), dark: true };
  if (/gemini|flash|pro/i.test(n)) return { name: label, src: I("gemini.svg") };
  if (/omni|imagen|google/i.test(n)) return { name: label, src: I("deepmind.svg") };
  return { name: label, glyph: "photo" };
}
function recorded(p: Pipeline): Record<string, Model[]> {
  const pv = p.provenance || {};
  const r: Record<string, Model[]> = {};
  if (pv.plan?.runtime) {
    const a = RUNTIME[pv.plan.runtime] || { name: pv.plan.runtime, glyph: "doc" as GlyphKind };
    r.plan = [{ ...a, name: pv.plan.model ? `${a.name} · ${pv.plan.model}` : a.name }];
    r.cut = r.research = r.storyboard = r.plan;
  }
  if (pv.character?.length) r.character = pv.character.map((x) => genModel(x.model, x.via));
  if (pv.keyframe?.length) r.keyframe = pv.keyframe.map((x) => genModel(x.model, x.via));
  if (pv.video?.length) r.video = pv.video.map((x) => genModel(x.model, x.backend));
  if (pv.voice) r.voice = pv.voice.engine ? [{ name: VOICE[pv.voice.engine] || pv.voice.engine, id: pv.voice.engine }] : [{ name: t("나레이션 없음"), glyph: "sound" }];
  // 재료와 초안은 따로 — 재료는 장면 재료를 만든 도구, 초안은 조립 단계 앱(예전엔 둘을 합쳐 두 칸에 똑같이 붙였다)
  if (pv.materials?.length) r.materials = pv.materials.map(craftModel);
  if (pv.draft?.length) r.draft = pv.draft.map(craftModel);
  return r;
}
/** 단계 그 자체가 정하는 것(기록과 설정이 같다) */
const INHERENT = new Set(["source", "editor", "publish"]);

/** produce.py 단계 이름 → 화면 문구 */
const STAGE_TX: Record<string, string> = {
  start: "제작 시작", script: "대본 정리", skills: "각본 · 연출 · 디자인 다듬기", comprehension: "시청자 이해 확인", direction: "연출 값 기록",
  materials: "재료 근거 확인", music: "음악 고르기", voice: "목소리 고르기", audio: "음성 합성", lint: "검사", ui_warm: "앱 화면 빌드",
  render: "재료 · 장면 렌더", stills: "정지 화면",
};
export const STATE_TX: Record<State, string> = { done: "완료", running: "실행 중", waiting: "확인 대기", error: "오류", todo: "시작 전" };

export function buildSteps(p: Pipeline, live: PipelineLive | null): { steps: Step[]; edges: Edge[] } {
  const rec = recorded(p);
  const route = p.route || "generate";
  const plan = p.plan;
  const agent = (live?.agent.runtime && RUNTIME[live.agent.runtime]) || RUNTIME.claude;
  const agentM: Model = { ...agent, name: live?.agent.model ? `${agent.name} · ${live.agent.model}` : agent.name };
  const voiceId = live?.models.voice || "edge";
  const voiceM: Model = { name: VOICE[voiceId] || voiceId, id: voiceId };
  const stageM: Model = { name: "ArtCraft 3D 무대", src: I("craft-solidcraft.png"), tile: true };
  const editorM: Model = { name: "Fluma 편집기", src: I("fluma.svg"), dark: true };
  const ytM: Model = { name: "YouTube", src: I("youtube.svg") };
  const imgBackend = (p as any).imagegen?.backend || "gflow";
  const imgModel = (p as any).imagegen?.model || "nano-pro";
  const nanoSrc = imgBackend === "agy" ? I("antigravity.svg") : /nano/i.test(imgModel) ? I("nanobanana.svg") : I("flow.svg");
  const nanoM: Model = { name: `${prettyModel(imgModel)} · ${BACKEND[imgBackend] || imgBackend}`, src: nanoSrc, dark: true };
  const backend = p.clips.find((c) => c.backend)?.backend || (p.videogen as any)?.backend || "flow";
  const vm = p.videogen?.model || live?.models.video || "veo_3_1_lite";
  const veoSrc = /antigravity/i.test(backend) ? I("antigravity.svg") : /mock/i.test(backend) ? undefined : /veo/i.test(vm) ? I("veo.svg") : I("flow.svg");
  const veoM: Model = { name: `${prettyModel(vm)} · ${BACKEND[backend] || backend}`, src: veoSrc, glyph: /mock/i.test(backend) ? "video" : undefined };

  const hasDraft = !!p.edit?.draft, hasSb = !!p.edit?.storyboard, ed = live?.editor;
  const S = (key: string, name: string, col: number, row: number, state: State, models: Model[], tip: string): Step => ({ key, name, col, row, state, models, tip });
  const steps: Step[] = [], edges: Edge[] = [];
  const planErr = !!p.check?.errors?.length;
  const planDone = route === "generate" ? !!plan?.shots?.length && !planErr : !!plan;
  steps.push(S("plan", t("기획"), 0, 0, planErr ? "error" : planDone ? "done" : "todo", [agentM],
    planErr ? p.check.errors.join(" · ") : route === "generate" ? t("샷 {n}개", { n: plan?.shots?.length ?? 0 }) : ""));

  if (route === "generate") {
    const chars = p.characters || [], kfs = p.keyframes || [], clips = p.clips || [];
    let prev = "plan", c = 1;
    if (plan?.needs_character) {
      const ok = chars.filter((x) => x.state === "승인").length;
      steps.push(S("character", t("캐릭터"), c, 0, chars.length && ok === chars.length ? "done" : chars.some((x) => Object.keys(x.files || {}).length) ? "waiting" : "todo",
        [nanoM], t("승인 {a}/{b}", { a: ok, b: chars.length })));
      edges.push(["plan", "character"]); prev = "character"; c++;
    }
    const kOk = kfs.filter((k) => k.state === "승인" || k.has_stage || k.has_compose).length;
    const kWaiting = kfs.some((k) => k.has_stage || k.has_compose || k.first);
    steps.push(S("keyframe", t("3D 무대 연출"), c, 0, kfs.length && kOk === kfs.length ? "done" : kWaiting ? "waiting" : "todo", [stageM], t("구도 확정 {a}/{b}", { a: kOk, b: kfs.length })));
    edges.push([prev, "keyframe"]); c++;
    const cOk = clips.filter((x) => x.approved).length;
    steps.push(S("video", t("영상"), c, 0, clips.length && cOk === clips.length ? "done" : clips.some((x) => x.clip_url) ? "waiting" : "todo", [veoM], t("샷 검토 {a}/{b}", { a: cOk, b: clips.length })));
    edges.push(["keyframe", "video"]); c++;
    steps.push(S("voice", t("음성"), 1, 1, hasDraft ? "done" : "todo", [voiceM], ""));
    const draftModels = rec.draft?.length ? rec.draft : (p.planned?.draft || []).map(craftModel);
    steps.push(S("draft", t("초안"), c, 0, hasDraft ? "done" : "todo", draftModels, ""));
    edges.push(["plan", "voice"], ["video", "draft"], ["voice", "draft"]);
  } else if (route === "clip") {
    steps.push(S("source", t("클립"), 1, 0, hasSb || hasDraft ? "done" : "todo", [{ name: "yt-dlp", glyph: "video" }], ""));
    steps.push(S("cut", t("더빙"), 2, 0, hasSb ? "done" : "todo", [agentM], ""));
    steps.push(S("voice", t("소리"), 1, 1, hasDraft ? "done" : "todo", [voiceM], ""));
    const draftModels = rec.draft?.length ? rec.draft : (p.planned?.draft || []).map(craftModel);
    steps.push(S("draft", t("초안"), 3, 0, hasDraft ? "done" : "todo", draftModels, ""));
    edges.push(["plan", "source"], ["source", "cut"], ["cut", "draft"], ["plan", "voice"], ["voice", "draft"]);
  } else {
    // 상태는 결과 파일로(조사 기록 · 콘티 · 음성 · 재료 수 · 초안) — 초안이 나와야 한꺼번에 '완료'가 되던 것을 고침(2026-11-16)
    const af = p.artifacts, [mDone, mAll] = af?.materials || [0, 0];
    const planned = p.planned || {};
    steps.push(S("research", t("조사"), 1, 0, af?.research || hasSb ? "done" : "todo", [agentM], ""));
    steps.push(S("storyboard", t("콘티"), 2, 0, hasSb ? "done" : "todo", [agentM], ""));
    steps.push(S("materials", t("재료"), 3, 0, hasDraft || (mAll > 0 && mDone >= mAll) ? "done" : "todo",
      (planned.materials || []).map(craftModel), mAll ? t("{a}/{b}", { a: mDone, b: mAll }) : ""));
    steps.push(S("voice", t("음성"), 1, 1, af?.audio || hasDraft ? "done" : "todo", [voiceM], ""));
    steps.push(S("draft", t("초안"), 4, 0, hasDraft ? "done" : "todo", (planned.draft || []).map(craftModel), ""));
    edges.push(["plan", "research"], ["research", "storyboard"], ["storyboard", "materials"], ["materials", "draft"], ["plan", "voice"], ["voice", "draft"]);
  }
  const dc = steps.find((x) => x.key === "draft")!.col;
  const edState: State = ed?.exported ? "done" : (hasDraft && ed?.project) ? "waiting" : "todo";
  const edTip = ed?.exported ? t("내보냄") : (hasDraft && ed?.project) ? t("편집 중") : "";
  steps.push(S("editor", t("편집"), dc + 1, 0, edState, [editorM], edTip));
  steps.push(S("publish", t("업로드"), dc + 2, 0, p.edit?.final ? "done" : "todo", [ytM], ""));
  edges.push(["draft", "editor"], ["editor", "publish"]);

  const now = Date.now();
  for (const j of live?.jobs ?? []) {
    const k = jobStep(j); const s = k && steps.find((x) => x.key === k); if (!s) continue;
    if (j.status === "running" || j.status === "queued") { s.state = "running"; s.progress = j.progress; s.tip = j.stage || s.tip; }
    else if (j.status === "failed" && s.state !== "done" && j.ended && now - Number(j.ended) < 15 * 60e3) { s.state = "error"; s.tip = j.error || t("실패"); }
  }
  // 도는 단계는 추측하지 않는다: ① produce.py 진행 기록의 단계 ② 에이전트가 쓰는 스킬 ③ 둘 다 없으면 아무 칸도 칠하지 않고 위 막대에만 '에이전트 작업 중'
  const pr = live?.produce;
  if (pr?.running && pr.stage && !steps.some((x) => x.state === "running")) {
    const st = pr.stage;
    const [mDone, mAll] = p.artifacts?.materials || [0, 0];
    const key = /^(audio|voice|music)$/.test(st) ? "voice"
      : /^render$/.test(st) ? (mAll && mDone < mAll ? "materials" : "draft")
      : /^(materials|ui_warm)$/.test(st) ? "materials"
      : /^(stills)$/.test(st) ? "draft"
      : route === "material" ? "storyboard" : "plan";      // 스킬(각본가 · 감독 · 디자이너) · 이해 관문 · 검사 · 방향 = 콘티 다듬기
    const s = steps.find((x) => x.key === key);
    if (s) { s.state = "running"; s.tip = STAGE_TX[st.replace(/:.*/, "")] ? t(STAGE_TX[st.replace(/:.*/, "")]) : st; }
  }
  if (live?.agent.busy && !pr?.running && !steps.some((x) => x.state === "running")) {
    const sk = live.agent.skill || "";
    const key = /research|trends/.test(sk) ? "research" : /storyboard|writer|director|designer/.test(sk) ? "storyboard" : /plan/.test(sk) ? "plan"
      : /produce/.test(sk) ? "materials" : /character/.test(sk) ? "character" : /keyframe/.test(sk) ? "keyframe" : /video-gen/.test(sk) ? "video" : null;
    const s = key ? steps.find((x) => x.key === key) : null;
    if (s) { s.state = "running"; s.tip = live.agent.tool ? t("에이전트 · {tool}", { tool: live.agent.tool }) : t("에이전트 작업 중"); }
  }
  // 끝난 · 확인 대기 · 오류 단계는 '실제로 만든 기록'만 보여 준다(설정을 바꿔도 과거는 그대로). 도는 단계는 지금 쓰는 것, 아직 안 한 단계는 '예정'(흐리게)
  for (const s of steps) {
    if (INHERENT.has(s.key) || s.state === "running") continue;
    if (s.state === "todo") s.models = s.models.map((m) => ({ ...m, planned: true }));
    else s.models = rec[s.key] ?? [UNKNOWN];
  }
  return { steps, edges };
}

/** 한 영상의 파이프라인 — 전체 상태(python, 가끔) + 실시간(/live, 2초 · 6초). 작업이 끝나면 전체를 다시 읽는다 */
export function usePipeline(id: string) {
  const [data, setData] = useState<Pipeline | null>(null);
  const [live, setLive] = useState<PipelineLive | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sig = useRef("");
  const reload = useCallback(async () => {
    try { setData(await api.pipeline(id)); setError(null); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [id]);
  useEffect(() => { setData(null); setLive(null); reload(); }, [reload]);
  useEffect(() => {
    let stop = false, timer = 0;
    sig.current = "";
    const tick = async () => {
      try {
        const l = await api.pipelineLive(id); if (stop) return;
        setLive(l);
        const s = l.jobs.map((j) => `${j.id}:${j.status}`).join("|") + `|${l.editor.project}|${l.editor.exported}|${l.agent.busy}`;
        if (sig.current && s !== sig.current) reload();
        sig.current = s;
        timer = window.setTimeout(tick, l.agent.busy || l.jobs.some((j) => j.status === "running" || j.status === "queued") ? 2000 : 6000);
      } catch { if (!stop) timer = window.setTimeout(tick, 8000); }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [id, reload]);
  return { data, live, error, reload };
}
