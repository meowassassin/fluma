// 에이전트 실행기 — 프로젝트(영상 1편)마다 Claude Code 를 저장소 루트에서 실행하고 대화를 이어 간다.
//
// 호출 방식은 OpenDesign 데몬(apps/daemon/src/runtimes/defs/claude.ts)을 따른다:
//   - 프롬프트는 argv 가 아니라 stdin JSONL (`--input-format stream-json`). 실행 중인 턴에 지시를 더 쓸 수 있다.
//   - 세션 id 는 서버가 만든다. 첫 턴 `--session-id`, 이후 `--resume`.
//   - 산출 파일은 도구 이벤트가 아니라 턴 전후 파일 diff 로 정한다.
// 다른 점: 권한을 bypass 하지 않고 허용 목록으로 제한한다 (쓰기는 콘텐츠 폴더만).
import { spawn, execFile } from "node:child_process";
import { randomUUID, createHash } from "node:crypto";
import { promises as fs, existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { resolveRuntime, codexArgs, codexPrompt, makeCodexParser } from "./runtimes.mjs";
import { pythonCmd, spawnTarget } from "./platform.mjs";
import { atomicWrite, killTree, HttpError } from "./lib.mjs";
import { runConfig as mcpRunConfig } from "./mcp.mjs";
import { createCrafts } from "./crafts.mjs";

// 쓰기 가능: 콘티 · 화면 구성(scene.js · manim/ · blender/ 요소 스크립트 · assets) · 캐릭터 · 조사 · 메모. 엔진 템플릿은 사람이 관리(에이전트는 영상마다 scene.js 를 새로 짠다)
const WRITABLE = ["storyboards", "compositions", "characters", "workspace/tmp", "research", "briefs", "rules/trends/proposals.md"];
const TOOLS = [
  "Read", "Glob", "Grep", "WebSearch", "WebFetch", "TodoWrite", "Skill",
  ...WRITABLE.flatMap((p) => {
    const pat = p.endsWith(".md") ? `./${p}` : `./${p}/**`;
    return [`Edit(${pat})`, `Write(${pat})`];
  }),
  // 정지 화면(still.py)·템플릿 검사(check_templates.py)도 scripts/ 래퍼로 실행한다
  "Bash(python3 scripts/*)",
];
// 키·인증 파일은 읽지도 못하게
const DENY = ["Read(./.env)", "Read(./.env.*)", "Read(~/.shortsforge/**)", "Edit(~/.claude/**)", "Write(~/.claude/**)", "Read(~/.claude/**)",
  // 홈의 비밀 · 인증 파일 (조사 중 웹 내용에 섞인 지시로 읽어 내보내는 일 방지)
  "Read(~/.ssh/**)", "Read(~/.cache/huggingface/**)", "Read(~/.codex/**)", "Read(~/.config/**)", "Read(~/.aws/**)", "Read(~/.gnupg/**)", "Read(~/.netrc)", "Read(~/.git-credentials)"];
// 턴 전후 비교·되돌리기 대상 (WRITABLE 과 같은 범위)
// 장면 설계도(scenes/)는 쓰기 허용 목록에 없다 — 에이전트는 scripts/scene_graph.py patch(소유권 · 잠금 검사)로만 고친다. 되돌리기 대상에는 넣는다
const TRACKED = [...WRITABLE.filter((p) => !p.startsWith("workspace/tmp")), "scenes"];  // 임시 폴더는 변경 목록에 안 띄움

// Craft 앱이 설치되어 있으면 기본 엔진은 Craft(scripts/engines.py DEFAULT_ENGINE 과 같은 판단)
const CRAFT = existsSync(new URL("../tools/crafts/effectcraft/installed.json", import.meta.url));
const autoChain = new Map();   // 프로젝트 → 사용자 말 이후 자동 이어가기를 몇 번 연속으로 했나

/** 에이전트가 사용자 답을 기다리며 턴을 끝냈나 — 선택지 블록이 있거나, 마지막 문장이 질문 */
export function waitsForUser(text) {
  const t = String(text || "").trim();
  if (!t) return false;
  if (/```choices/.test(t.slice(-1500))) return true;
  const last = t.replace(/```[\s\S]*?```/g, "").trim().split("\n").map((l) => l.trim()).filter(Boolean).pop() || "";
  return /[?？]\s*[)*_]*$/.test(last) || /(할까요|될까요|주실 수 있을까요|주시겠어요|어느 쪽으로 갈까요)[.!]?$/.test(last);
}

// 설치 규칙: 빠진 도구 때문에 사용자에게 "설치해 주세요" 를 부탁하지 않는다(2026-11-04: OpenCV 가 없어 설치를 세 번 부탁하고 멈춤)
const IN_DOCKER = process.env.FLUMA_IN_DOCKER === "1" || existsSync("/.dockerenv");
const SETUP_RULES = `## 설치는 스스로
빠진 패키지 · 앱 때문에 사용자에게 설치를 부탁하지 않는다. 직접 설치하고 하던 일을 이어 간다:
- 파이썬 패키지(OpenCV · Whisper · OCR · onnxruntime …): 스크립트가 import 할 때 자동 설치된다(scripts/autodeps.py). 그래도 없다고 나오면 \`python3 scripts/doctor.py --fix --profile analysis\` (누끼 · 유튜브는 full)
- Craft 앱: \`python3 scripts/crafts.py install <앱>\` · Chromium: \`python3 scripts/doctor.py --fix\`
- pip · npm · apt 를 직접 부르지 않는다(승인 창이 사용자에게 가지 않아 거부된다) — 위 스크립트를 쓴다
- 위로도 안 되는 것(ffmpeg 같은 시스템 프로그램)만 사용자에게, 그 사람의 운영체제에 맞는 한 줄로` + (IN_DOCKER
  ? "\n- 지금 Docker 컨테이너 안에서 돈다: 경로(/app …)는 사용자 컴퓨터에 없다. 사용자에게 명령을 안내해야 하면 docker-compose.yml 이 있는 폴더에서 `docker compose exec fluma …` 로"
  : "");

export function createAgent({ ROOT, env, onState = () => {} }) {
  const PY = pythonCmd(ROOT);
  const SESS = path.join(ROOT, "workspace", "sessions");
  const runs = new Map();      // project -> run
  const autoTimers = new Map();   // 자동 이어가기 예약 (멈추면 · 새 메시지면 취소)
  const queued = new Map();       // project -> [{ message, opts }] 작업 중이라 끼워 넣지 못한 말 — 턴이 끝나면 차례로 보냄
  const lastTurn = new Map();  // project -> { before: Map<rel, string|null> }

  // ---------- 기록 ----------
  // 쓰기는 영상마다 한 줄로 세우고(동시에 읽고-고치고-쓰다 덮어쓰는 일 없음), 임시 파일 → rename 으로 원자적으로.
  // 읽다가 깨져 있으면 기록을 비우지 않는다: 직전 정상본(.prev)으로, 그것도 없으면 깨진 파일을 .corrupt-<시각> 으로 보관하고 새로 시작.
  const sessFile = (id) => path.join(SESS, `${id}.json`);
  const writeChain = new Map();
  async function load(id) {
    const f = sessFile(id);
    if (!existsSync(f)) return { sessionId: null, messages: [] };
    try { return JSON.parse(await fs.readFile(f, "utf8")); } catch { /* 깨짐 */ }
    try { const prev = JSON.parse(await fs.readFile(`${f}.prev`, "utf8")); console.error(`[agent] ${id} 기록이 깨져 직전 정상본으로 읽음`); return prev; } catch { /* 없음 */ }
    await fs.rename(f, `${f}.corrupt-${Date.now()}`).catch(() => {});
    console.error(`[agent] ${id} 기록이 깨져 보관하고 새로 시작`);
    return { sessionId: null, messages: [] };
  }
  async function writeNow(id, s) {
    const f = sessFile(id);
    if (existsSync(f)) await fs.copyFile(f, `${f}.prev`).catch(() => {});
    await atomicWrite(f, JSON.stringify(s, null, 2));
  }
  /** 읽고-고치고-쓰기를 영상마다 차례로 */
  function mutate(id, fn) {
    const prev = writeChain.get(id) || Promise.resolve();
    const next = prev.catch(() => {}).then(async () => { const s = await load(id); const r = await fn(s); await writeNow(id, s); return r ?? s; });
    writeChain.set(id, next);
    next.finally(() => { if (writeChain.get(id) === next) writeChain.delete(id); }).catch(() => {});
    return next;
  }

  // ---------- 스냅샷 (턴 전후 diff, 되돌리기) ----------
  async function walk(rel, out) {
    const abs = path.join(ROOT, rel);
    if (!existsSync(abs)) return;
    const st = await fs.stat(abs);
    if (st.isFile()) { out.set(rel, await fs.readFile(abs)); return; }
    for (const name of await fs.readdir(abs)) {
      if (name === "node_modules" || name.startsWith(".")) continue;
      const r = path.join(rel, name);
      const s = await fs.stat(path.join(ROOT, r));
      if (s.isDirectory()) await walk(r, out);
      else if (s.size < 2_000_000) out.set(r, await fs.readFile(path.join(ROOT, r)));
    }
  }
  async function snapshot() {
    const m = new Map();
    for (const rel of TRACKED) await walk(rel, m);
    return m;
  }
  const hash = (b) => (b ? createHash("sha1").update(b).digest("hex") : null);
  /** 되돌리기용: 바뀐 파일의 턴 전 내용을 workspace/sessions/<id>.snap/ 에 (직전 턴 하나만) */
  async function persistTurn(project, before, after, files) {
    const dir = path.join(SESS, `${project}.snap`);
    await fs.rm(dir, { recursive: true, force: true });
    await fs.mkdir(path.join(dir, "blobs"), { recursive: true });
    const manifest = [];
    for (const f of files) {
      const b = before.get(f.path) ?? null, a = after.get(f.path) ?? null;
      let blob = null;
      if (b) { blob = hash(b); await fs.writeFile(path.join(dir, "blobs", blob), b); }
      manifest.push({ path: f.path, kind: f.kind, before: blob, after: hash(a) });
    }
    await atomicWrite(path.join(dir, "manifest.json"), JSON.stringify({ at: Date.now(), files: manifest }, null, 1));
  }
  function diff(before, after) {
    const changed = [];
    for (const [k, v] of after) if (!before.has(k)) changed.push({ path: k, kind: "added" }); else if (!before.get(k).equals(v)) changed.push({ path: k, kind: "modified" });
    for (const k of before.keys()) if (!after.has(k)) changed.push({ path: k, kind: "deleted" });
    return changed;
  }

  // ---------- 시스템 프롬프트 (OpenDesign 순서: 기본 → DESIGN.md → SKILL.md → 현재 작업) ----------
  function readIf(p) { try { return readFileSync(p, "utf8"); } catch { return null; } }
  function readSettings() { try { return JSON.parse(readFileSync(path.join(ROOT, "workspace", "settings.json"), "utf8")); } catch { return {}; } }
  function systemPrompt({ project, look, template, skill, scene }) {
    const parts = [];
    parts.push(readIf(path.join(ROOT, "workspace", "system.md")) ?? "");
    parts.push(STYLE_RULES, MEMORY_RULES, SETUP_RULES);
    // 붙어 있는 Craft 앱(MCP) — 그림 · 움직임을 SVG 코드로 직접 짜기 전에 진짜 제작 도구를 먼저 쓴다
    const cr = createCrafts(ROOT).list().filter((c) => c.agentOn && c.installed?.cli);
    if (cr.length) parts.push(`## 제작 도구 (Craft 앱, MCP: ${cr.map((c) => `mcp__${c.name}`).join(" · ")})\n` +
      cr.map((c) => `- ${c.title} — ${c.kind}: ${c.use}`).join("\n") +
      "\n캐릭터 · 장면 그림은 illustrate 스킬(.claude/skills/illustrate/SKILL.md)대로 디자이너처럼 그린다: 레퍼런스 그림 문법 연구 → 실루엣 썸네일 3개 → 고르기 → VectorCraft 로 그리고 매 회차 렌더해서 보고 고치기 → 이름 붙은 레이어로 저장. 디테일은 적게, 큰 형태와 보색으로. 렌더는 Craft 엔진(render.py --engine craft) — EffectCraft 장면 · SoundCraft 소리 · FilmCraft 조립 파일이 남는다. 앱은 다듬기에만 MCP 로 쓰고, 결과는 compositions/<영상 id>/ 아래에만 쓴다.");
    if (skill) {
      const body = readIf(path.join(ROOT, ".claude", "skills", skill, "SKILL.md"));
      if (body) parts.push(`## 활성 스킬: ${skill} (.claude/skills/${skill}/SKILL.md)\n\n${body.replace(/^---[\s\S]*?---\n/, "")}`);
    }
    // 새 영상(콘티 스킬 · 형식 스킬 · 작업 공간)에서는 제작 스킬도 함께 — 콘티만 쓰고 끝내지 않게.
    // 기본 엔진은 Craft → produce 스킬. HyperFrames(Craft 앱이 없거나 콘티가 hyperframes)일 때만 compose
    const sbNow = readIf(path.join(ROOT, "storyboards", `${project}.json`));
    let engineNow = CRAFT ? "craft" : "hyperframes";
    try { if (sbNow) engineNow = JSON.parse(sbNow).engine || engineNow; } catch { /* 깨진 콘티는 기본 */ }
    const companion = engineNow === "craft" ? "produce" : "compose";
    if (skill !== companion && skill !== "plan" && (!skill || skill === "storyboard" || skill.startsWith("format-") || project.startsWith("_"))) {
      const body = readIf(path.join(ROOT, ".claude", "skills", companion, "SKILL.md"));
      if (body) parts.push(`## 함께 쓰는 스킬: ${companion} (.claude/skills/${companion}/SKILL.md)\n\n${body.replace(/^---[\s\S]*?---\n/, "")}`);
    }
    // 이미 콘티가 있는 영상: 부분 수정(시각 · 장면 · 요소 단위) 규칙도 함께 — "12초 서버 키워 줘"를 그 요소만 고치게
    // 기획 대화(홈): 콘티 작성 규칙만 함께 — 화면 구성 · 부분 수정 스킬은 '제작 시작' 뒤에
    if (skill === "plan") {
      const body = readIf(path.join(ROOT, ".claude", "skills", "storyboard", "SKILL.md"));
      if (body) parts.push(`## 함께 쓰는 스킬: storyboard (작성 규칙만 — 음성 · 화면 단계는 하지 않는다)\n\n${body.replace(/^---[\s\S]*?---\n/, "")}`);
    }
    if (!project.startsWith("_") && skill !== "scene-edit" && skill !== "plan" && existsSync(path.join(ROOT, "storyboards", `${project}.json`))) {
      const body = readIf(path.join(ROOT, ".claude", "skills", "scene-edit", "SKILL.md"));
      if (body) parts.push(`## 함께 쓰는 스킬: scene-edit (.claude/skills/scene-edit/SKILL.md)\n\n${body.replace(/^---[\s\S]*?---\n/, "")}`);
    }
    if (project.startsWith("_")) {
      const body = (n) => (readIf(path.join(ROOT, ".claude", "skills", n, "SKILL.md")) || "").replace(/^---[\s\S]*?---\n/, "");
      parts.push(`## 활성 스킬: trends\n\n${body("trends")}`);
      parts.push([
        "## 현재 작업 (작업 공간 대화 — 특정 영상이 아님)",
        "- 사용자가 지금 보는 화면은 매 메시지의 <FLUMA_CONTEXT> 의 '화면' 줄. 그 화면에서 결과가 보이게 일한다:",
        "  · 트렌드 → `scripts/trends.py search --queries '…'` (구체 주제는 검색어, 결과가 트렌드 화면에 바로 나타남)",
        "  · 라이브러리 → 캐릭터(.claude/skills/character)",
        "  · 영상을 만들어 달라고 하면 **어느 화면에서든 바로 만든다**: 새 id(YYYY-MM-DD-<영문짧은이름>-01)로 storyboards/<id>.json 을 쓰고 storyboard 스킬 순서(조사 → 콘티 → 검사) 다음 **같은 턴에서** produce 스킬(음성 → 장면 재료 → 검사 → 초안 렌더 → 정지 화면 확인)까지. 콘티에 engine: craft. 끝나면 '홈의 프로젝트 표에서 <제목>'을 열면 된다고 한 줄로 알린다. 홈으로 돌려보내지 않는다.",
        "- 사용자가 선택한 것(선택: …)이 있으면 그것에 대해 말하는 것으로 본다.",
      ].join("\n"));
      return parts.join("\n\n---\n\n");
    }
    const sbRel = `storyboards/${project}.json`;
    parts.push([
      "## 현재 작업",
      `- 프로젝트 id: ${project}`,
      `- 콘티 파일: ${sbRel} ${existsSync(path.join(ROOT, sbRel)) ? "(있음 — 읽고 고친다)" : "(아직 없음 — 이 경로에 새로 만든다. id 필드도 이 값)"}`,
      engineNow === "craft"
        ? `- 엔진: Craft — 장면 재료(콘티 materials) → EffectCraft · SoundCraft · FilmCraft. 제작 파일 compositions/${project}/craft/, 초안 render.py --draft (produce 스킬)`
        : `- 화면: ${template === "Composed" || !template ? "compositions/" + project + "/scene.js (HyperFrames 합성)" : "템플릿 " + template}. 색 · 배치는 콘티 direction(direct.py)`,
      scene != null ? `- 이번 요청은 **장면 ${scene}만** 고친다. 다른 장면과 sec 합계는 건드리지 않는다.` : "",
    ].filter(Boolean).join("\n"));
    return parts.join("\n\n---\n\n");
  }

  // ---------- 스트림 정규화 (OpenDesign claude-stream.ts 의 축소판) ----------
  function makeParser(emit, textSoFar = () => "") {
    const blocks = new Map(); // index -> {type, name, id, input}
    let partial = false;
    return (line) => {
      let e;
      try { e = JSON.parse(line); } catch { return; }
      if (e.type === "stream_event") {
        partial = true;
        const ev = e.event || {};
        if (ev.type === "content_block_start") {
          const cb = ev.content_block || {};
          blocks.set(ev.index, { type: cb.type, name: cb.name, id: cb.id, input: "" });
          if (cb.type === "tool_use") emit({ type: "tool_start", id: cb.id, name: cb.name });
          // 도구 호출 사이사이의 텍스트 블록은 문단으로 나눈다
          if (cb.type === "text" && textSoFar()) emit({ type: "text", text: "\n\n" });
          if (cb.type === "thinking") emit({ type: "status", label: "생각 중" });
        } else if (ev.type === "content_block_delta") {
          const d = ev.delta || {};
          if (d.type === "text_delta") emit({ type: "text", text: d.text });
          else if (d.type === "thinking_delta" && d.thinking) emit({ type: "thinking", text: d.thinking });
          else if (d.type === "input_json_delta") { const b = blocks.get(ev.index); if (b) b.input += d.partial_json; }
        } else if (ev.type === "content_block_stop") {
          const b = blocks.get(ev.index);
          if (b?.type === "tool_use") {
            let input = {};
            try { input = JSON.parse(b.input || "{}"); } catch { /* 부분 입력 */ }
            emit({ type: "tool_use", id: b.id, name: b.name, input: summarize(b.name, input) });
            if (b.name === "TodoWrite" && Array.isArray(input.todos)) emit({ type: "todos", todos: input.todos.map((t) => ({ content: t.content, status: t.status, activeForm: t.activeForm })) });
          }
          blocks.delete(ev.index);
        }
        return;
      }
      if (e.type === "assistant" && !partial) {
        // --include-partial-messages 를 못 쓰는 빌드: 완성된 메시지에서 꺼낸다
        for (const c of e.message?.content || []) {
          if (c.type === "text") emit({ type: "text", text: c.text });
          if (c.type === "tool_use") emit({ type: "tool_use", id: c.id, name: c.name, input: summarize(c.name, c.input || {}) });
          if (c.type === "tool_use" && c.name === "TodoWrite" && Array.isArray(c.input?.todos)) emit({ type: "todos", todos: c.input.todos });
        }
      } else if (e.type === "user") {
        for (const c of e.message?.content || []) {
          if (c?.type !== "tool_result") continue;
          const text = Array.isArray(c.content) ? c.content.map((x) => x.text || "").join("") : String(c.content ?? "");
          emit({ type: "tool_result", id: c.tool_use_id, error: !!c.is_error, preview: text.slice(0, 400) });
        }
      } else if (e.type === "system" && e.subtype === "permission_denied") {
        emit({ type: "denied" });
      } else if (e.type === "result") {
        emit({ type: "result", ok: e.subtype === "success" && !e.is_error, cost: e.total_cost_usd ?? null,
          durationMs: e.duration_ms ?? null, denials: (e.permission_denials || []).map((d) => summarize(d.tool_name, d.tool_input || {})) });
      }
    };
  }
  function summarize(name, input) {
    if (input.file_path) return path.relative(ROOT, input.file_path) || input.file_path;
    if (input.command) return String(input.command).slice(0, 160);
    if (input.pattern) return String(input.pattern);
    if (input.query) return String(input.query);
    if (input.url) return String(input.url);
    if (input.skill) return String(input.skill);
    return name === "TodoWrite" ? "할 일 갱신" : "";
  }

  // ---------- 실행 ----------
  const seqs = new Map();   // project -> 마지막 이벤트 번호 (턴이 바뀌어도 계속 늘어남 → Last-Event-ID 로 이어 받기)
  const clientsOf = (project) => { let r = runs.get(project); if (!r) { r = { live: false, events: [], clients: new Set() }; runs.set(project, r); } return r.clients; };
  function broadcast(run, ev) {
    const id = (seqs.get(run.project) || 0) + 1; seqs.set(run.project, id);
    run.events.push({ id, ev });
    const data = `id: ${id}\ndata: ${JSON.stringify(ev)}\n\n`;
    for (const c of run.clients) c.write(data);
  }

  // ---------- 공유 기억 · 화면 맥락 (Nimbalyst 구조 참고: 메시지마다 <…SYSTEM_MESSAGE> 로 지금 화면 + 회상한 기억을 붙인다) ----------
  // 답변 언어(설정 language — 화면 언어와 같이 바뀐다)
  const LANG_LINE = { korean: "한국어 (진행 문장 포함, 다른 언어 문장 금지)", english: "English (all user-facing text, including progress lines)", chinese: "简体中文 (all user-facing text, including progress lines)" };
  const cfgLang = () => readSettings().language || "korean";
  const STYLE_RULES = [
    "## 답하는 법 (가장 먼저 지킬 것)",
    "- **사용자에게 보이는 모든 글은 설정한 답변 언어**(FLUMA_CONTEXT 의 '답변 언어', 기본 한국어)로 쓴다. 첫 문장부터 끝까지, 도구 호출 사이의 짧은 진행 문장까지. 다른 언어 문장을 섞지 않는다. 코드 · 파일 경로 · 명령 · 오류 원문만 그대로 둔다. 영상 안의 나레이션 · 자막 언어는 답변 언어와 별개로 콘티(language)를 따른다.",
    "- 오래 걸리는 일은 시작할 때 무엇을 할지 한 줄로 말하고, 끝나면 결과만 짧게.",
    "- 막히면(모듈 없음 · 권한 거부 등) 같은 시도를 되풀이하지 말고, 무엇이 없는지와 사용자가 실행할 명령 한 줄을 답변 언어로 알리고 멈춘다.",
  ].join("\n");
  const MEMORY_RULES = [
    "## Fluma 공유 기억",
    "- 메뉴(홈 · 트렌드 · 캐릭터 · 스튜디오)는 기억을 함께 쓴다. 매 메시지 끝의 <FLUMA_CONTEXT> 에 지금 화면과 관련 기억이 붙는다. 기억은 참고용 — 지금 요청과 다르면 지금 요청을 따른다.",
    "- 사용자가 **오래 갈 취향 · 결정 · 지시 · 제약**을 말하면(예: \"앞으로 2D 위주\", \"우리 브랜드 색은 …\", \"IT 쪽 관심\") 한 번 기억한다:",
    "  `python3 scripts/memory.py remember --type <preference|decision|instruction|constraint|convention|fact|error> --scope <global|trends|character|studio|project:<id>> --menu <지금 메뉴> --title \"짧은 제목\" --body \"맥락이 담긴 두세 문장(왜 · 어디서 · 무엇)\"`",
    "- 한 문장 조각이 아니라 나중에 혼자 읽어도 이해되는 짧은 문단으로. 같은 제목이면 새 기억이 옛 기억을 대체한다. 이번 대화에만 쓸 일 · 파일에 이미 있는 것 · 키 · 비밀번호는 기억하지 않는다.",
    "- 범위: 모든 메뉴에 해당하면 global, 특정 메뉴 이야기면 그 메뉴.",
    "- 더 찾아볼 때: `python3 scripts/memory.py recall --query \"…\" --any-scope`",
    "- 중간 파일은 <FLUMA_CONTEXT> 의 임시 폴더에 쓴다(7일 뒤 지워짐).",
  ].join("\n");
  const MENU_LABEL = { plan: "홈 · 기획 대화", trends: "트렌드", character: "캐릭터", look: "라이브러리", studio: "영상 편집", home: "홈", global: "홈" };
  function menuOf(project, context) {
    if (project === "_workspace" && context?.note === "홈 화면") return "global";
    if (context?.menu) return context.menu;
    if (project === "_trends") return "trends";
    if (project === "_brand") return "brand";
    if (project === "_character") return "character";
    return "studio";
  }
  function memoryCall(args) {
    return new Promise((resolve) => {
      execFile(PY, ["scripts/memory.py", ...args, "--json"], { cwd: ROOT, timeout: 5000, encoding: "utf8" }, (err, out) => {
        if (err) return resolve([]);
        try { resolve(JSON.parse(out || "[]")); } catch { resolve([]); }
      });
    });
  }
  async function buildContext(project, message, context, sessionId) {
    const menu = menuOf(project, context);
    const scope = (menu === "studio" || menu === "plan") && !project.startsWith("_") ? `project:${project}` : menu;
    const [byQuery, pinned] = await Promise.all([
      memoryCall(["recall", "--query", message.slice(0, 400), "--any-scope", "--limit", "5", "--session", sessionId]),
      memoryCall(["top", "--scope", scope, "--limit", "6"]),
    ]);
    const seen = new Set(), mem = [];
    for (const m of [...pinned, ...byQuery]) if (!seen.has(m.id)) { seen.add(m.id); mem.push(m); }
    const tmp = path.join("workspace", "tmp", project.replace(/[^A-Za-z0-9가-힣_.-]/g, "-"));
    const lines = ["<FLUMA_CONTEXT>", `화면: ${MENU_LABEL[menu] || menu}${menu === "studio" ? ` · 프로젝트 ${project}` : ""}`];
    if (context?.selection) lines.push(`선택: ${String(context.selection).slice(0, 600)}`);
    if (context?.note) lines.push(String(context.note).slice(0, 600));
    lines.push(`임시 폴더: ${tmp}/`);
    // 사용자가 올린 사진 · 영상 (public/uploads/<id>/) — 장면에 쓰라고 하면 이것을 쓴다
    try {
      const up = path.join(ROOT, "public", "uploads", project);
      if (!project.startsWith("_") && existsSync(up)) {
        const files = readdirSync(up).filter((n) => /\.(jpe?g|png|webp|gif|mp4|mov|webm|mkv|m4v|mp3|m4a|wav|ogg|aac|flac)$/i.test(n));
        const kind = (n) => /\.(mp4|mov|webm|mkv|m4v)$/i.test(n) ? `uploads/${project}/${n} (영상 · 프레임: K.seq "uploads/${project}/${n.replace(/\.[^.]+$/, "")}")`
          : /\.(mp3|m4a|wav|ogg|aac|flac)$/i.test(n) ? `uploads/${project}/${n} (음악 — 콘티 music.src: "public/uploads/${project}/${n}")` : `uploads/${project}/${n} (사진)`;
        if (files.length) lines.push(`올린 파일: ${files.map(kind).join(" · ")}`);
      }
    } catch { /* 없음 */ }
    if (mem.length) {
      lines.push("<FLUMA_MEMORY>");
      for (const m of mem) lines.push(`- [${m.type}·${m.scope}] ${m.title} — ${String(m.body).replace(/\s+/g, " ").slice(0, 280)} (${m.id})`);
      lines.push("</FLUMA_MEMORY>");
    }
    lines.push(`답변 언어: ${LANG_LINE[cfgLang()] || LANG_LINE.korean}`);
    lines.push("</FLUMA_CONTEXT>");
    return { text: lines.join("\n"), memories: mem.map((m) => ({ id: m.id, title: m.title, scope: m.scope, type: m.type })), tmp };
  }

  const userFrame = (text) => JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text }] } }) + "\n";

  let shuttingDown = false;
  const busy = new Set();   // 턴을 여는 중 · 실행 중 · 마무리 중인 영상 (동시에 두 턴이 뜨지 않게)
  async function start(project, opts) {
    if (busy.has(project) || runs.get(project)?.live) {
      if (opts.auto) return { sessionId: null };
      throw new HttpError(409, "busy", "에이전트가 아직 작업 중입니다");
    }
    busy.add(project);
    try { return await startInner(project, opts); } catch (e) { busy.delete(project); throw e; }
  }
  async function startInner(project, { message, look, template, skill: skillIn, scene, model, context, auto }) {
    let skill = skillIn;
    if (!auto) { clearTimeout(autoTimers.get(project)); autoTimers.delete(project); autoChain.set(project, 0); }   // 사용자가 직접 보내면 예약된 자동 이어가기는 취소 · 연속 횟수 0
    else if (!autoTimers.has(project)) { busy.delete(project); return { sessionId: null }; }   // 그사이 멈췄으면 자동 이어가기 안 함
    else { autoTimers.delete(project); autoChain.set(project, (autoChain.get(project) ?? 0) + 1); }
    // 장면 코멘트는 따로 고른 스킬이 없으면 scene-edit 를 쓴다
    if (scene != null && !skill && existsSync(path.join(ROOT, ".claude", "skills", "scene-edit", "SKILL.md"))) skill = "scene-edit";
    // Claude 세션을 실제로 연 적이 있어야 --resume (같은 대화를 Codex 로만 하다가 Claude 로 바꾸면 새 세션으로 시작)
    let first = false, ctx = null;
    const sess = await mutate(project, async (s) => {
      const claudeUsed = s.claudeUsed ?? (!!s.sessionId && !s.codexThread);
      first = !s.sessionId || !claudeUsed;
      if (!s.sessionId) s.sessionId = randomUUID();
      ctx = await buildContext(project, message, context, s.sessionId);
      s.messages.push({ role: "user", text: message, skill: skill || null, scene: scene ?? null, ts: Date.now(), memories: ctx.memories });
    });
    await fs.mkdir(path.join(ROOT, ctx.tmp), { recursive: true });

    // 설정(workspace/settings.json): 실행 환경(로컬 CLI · API 키) · 모델 · 생각 깊이. open-design 의 실행 환경 설정을 따름
    const cfg = readSettings();
    let rt;
    try { rt = resolveRuntime(cfg); } catch (err) {
      // 키 · 주소가 빠졌으면 실행하지 않고 바로 알린다
      await mutate(project, (s2) => { s2.messages.push({ role: "assistant", text: "", tools: [], files: [], ok: false, error: String(err.message || err), ts: Date.now() }); });
      const r0 = { project, live: false, events: [], clients: clientsOf(project) }; runs.set(project, r0);
      broadcast(r0, { type: "start", user: message, skill: skill || null, scene: scene ?? null, memories: [] });
      broadcast(r0, { type: "end", ok: false, files: [], stopped: false, error: String(err.message || err) });
      busy.delete(project);
      return { sessionId: sess.sessionId };
    }
    const sys = systemPrompt({ project, look, template, skill, scene });
    let bin, args, stdio;
    if (rt.runtime === "codex") {
      // Codex: 시스템 지시는 새 스레드의 첫 메시지 앞에, 이후엔 같은 스레드를 이어간다. 실행 중 덧붙이기(stdin)는 없음
      const thread = sess.codexThread && sess.codexProvider === (rt.provider || "cli") ? sess.codexThread : null;
      const body = `${message}\n\n${ctx.text}`;
      bin = process.env.SF_CODEX_BIN || "codex";
      args = codexArgs({ cwd: ROOT, threadId: thread, model: model || rt.model, effort: rt.effort, codexConfig: rt.codexConfig, prompt: thread ? body : codexPrompt(sys + "\n\n" + "답변 언어: " + (LANG_LINE[cfg.language] || LANG_LINE.korean), body) });
      stdio = ["ignore", "pipe", "pipe"];
    } else {
      bin = process.env.SF_CLAUDE_BIN || "claude";
      args = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        first ? "--session-id" : "--resume", sess.sessionId,
        "--allowedTools", ...TOOLS, "--disallowedTools", ...DENY,
        "--append-system-prompt", sys];
      // 사용자가 설정에서 켠 MCP 서버: 그 서버의 도구를 모두 허용(mcp__<이름>)
      const mcp = mcpRunConfig(createCrafts(ROOT).mcpServers());   // 사용자 MCP + 설치된 Craft 앱(벡터 · 모션 · 이미지 …)
      if (mcp) { args.push("--mcp-config", mcp.file); args.splice(args.indexOf("--disallowedTools"), 0, ...mcp.tools); }
      const m = model || rt.model || process.env.SF_AGENT_MODEL;
      if (m) args.push("--model", m);
      if (rt.effort) args.push("--effort", rt.effort);
      args.push("--settings", JSON.stringify({ language: cfg.language || "korean" }));
      stdio = ["pipe", "pipe", "pipe"];
      await mutate(project, (s) => { s.claudeUsed = true; });
    }

    const before = await snapshot();
    // Claude Code 자체 자동 기억은 끈다 — 기억은 Fluma 공유 기억(workspace/memory) 하나로 (개발자 기억 폴더 오염 방지)
    const st = spawnTarget(bin);   // Windows 의 npm 설치본(codex.cmd 등)은 셸로 실행
    const child = spawn(st.cmd, args, { cwd: ROOT, env: { ...env, CLAUDE_CODE_DISABLE_AUTO_MEMORY: "1", ...rt.env }, stdio, shell: st.shell, detached: process.platform !== "win32" });
    const run = { project, live: true, child, events: [], clients: clientsOf(project), stdinOpen: rt.runtime !== "codex", text: "", tools: [], todos: null, startedAt: Date.now(), runtime: rt.label, skill: skill || null };
    runs.set(project, run);
    broadcast(run, { type: "start", user: message, skill: skill || null, scene: scene ?? null, memories: ctx.memories, at: run.startedAt });
    onState(project, true);

    const onEv = (ev) => {
      if (ev.type === "text") run.text += ev.text;
      if (ev.type === "tool_use") run.tools.push({ name: ev.name, input: ev.input });
      if (ev.type === "todos") run.todos = ev.todos;
      if (ev.type === "tool_result" && ev.error) { const t = run.tools.at(-1); if (t) t.error = true; }
      if (ev.type === "result") { run.result = ev; if (run.stdinOpen && child.stdin) { run.stdinOpen = false; child.stdin.end(); } }
      broadcast(run, ev);
    };
    const parse = rt.runtime === "codex"
      ? makeCodexParser(onEv, { rel: (p) => path.relative(ROOT, p) || p, onThread: (id) => { mutate(project, (s3) => { s3.codexThread = id; s3.codexProvider = rt.provider || "cli"; }).catch(() => {}); } })
      : makeParser(onEv, () => run.text);
    let buf = "";
    child.stdout.on("data", (b) => {
      buf += b.toString();
      let i;
      while ((i = buf.indexOf("\n")) >= 0) { const line = buf.slice(0, i); buf = buf.slice(i + 1); if (line.trim()) parse(line); }
    });
    let stderr = "";
    child.stderr.on("data", (b) => { stderr += b.toString(); });
    if (child.stdin) {
      child.stdin.on("error", () => { run.stdinOpen = false; });
      child.stdin.write(userFrame(`${message}\n\n${ctx.text}`));
    }

    child.on("error", (e) => { stderr += String(e); });
    child.on("close", async (code, signal) => {
      // 마무리(파일 비교 · 기록 저장)가 끝날 때까지 busy 를 유지 → 그사이 새 턴이 끼어들지 않음
      let files = [], ok = false, errorText = null;
      try {
        const after = await snapshot();
        files = diff(before, after);
        lastTurn.set(project, { files });   // 내용은 디스크 스냅샷(.snap)에만 — 메모리에 쌓지 않음
        await persistTurn(project, before, after, files).catch((e) => console.error("[agent] 되돌리기 스냅샷 실패", e));
        ok = !!run.result?.ok && code === 0;
        errorText = ok || run.stopped ? null : (run.result?.error || stderr.trim().split("\n").filter((l) => l.trim() && !/connectors are disabled/.test(l)).slice(-3).join("\n").slice(0, 400) || (signal ? `중지됨 (${signal})` : `exit ${code}`));
        await mutate(project, (s) => {
          s.messages.push({ role: "assistant", text: run.text, tools: run.tools, files, ok, stopped: !!run.stopped || signal === "SIGTERM",
            cost: run.result?.cost ?? null, todos: run.todos, durationMs: Date.now() - run.startedAt, error: errorText, ts: Date.now() });
        });
      } catch (e) { console.error("[agent] 턴 마무리 실패", e); }
      run.live = false;
      busy.delete(project);
      onState(project, false);
      broadcast(run, { type: "end", ok, files, stopped: !!run.stopped || signal === "SIGTERM", error: errorText, durationMs: Date.now() - run.startedAt, cost: run.result?.cost ?? null });
      // 줄 서 있던 말이 있으면 그것부터(사용자 말이 자동 이어가기보다 먼저). 멈춤을 눌렀으면 줄도 비운다
      // 끼어들기(Ctrl+Enter)로 멈춘 경우는 '사용자가 멈춤'이 아니라 줄 맨 앞의 새 말로 바로 넘어간다
      const userStopped = (run.stopped || signal === "SIGTERM") && !run.interrupt;
      const q = queued.get(project);
      if (q?.length && !userStopped) {
        const next = q.shift(); if (!q.length) queued.delete(project);
        setTimeout(() => start(project, next.opts).catch((e) => console.error("[agent] 줄 선 말 보내기 실패", e)), 300);
        return;
      }
      if (userStopped) queued.delete(project);
      // 사용자가 멈춘 게 아닌데 중간에 끊기면(결과 없이 종료) 한 번 자동으로 이어간다 — 같은 세션이라 맥락 유지
      // 밖에서 끈 경우(서버 종료 · 다른 프로세스의 SIGTERM/SIGKILL → 종료 코드 143/137)는 '끊김'이 아니므로 다시 시작하지 않는다
      const killed = shuttingDown || !!signal || code === 143 || code === 137;
      // 에이전트가 질문 · 선택지로 턴을 끝냈으면 사용자 답을 기다린다 — 자동 이어가기가 끼어들어 답을 가로채지 않게
      // (2026-11-03: '훅을 줄여도 될까요?' 직후 자동 이어가기가 와서 에이전트가 혼자 정했다)
      const asked = waitsForUser(run.text);
      // 끊김에 의한 자동 이어가기는 연속 2번까지(자동으로 이어 간 작업이 또 끊겨도 한 번 더) — 사용자가 말하면 다시 0
      const chain = autoChain.get(project) ?? 0;
      if (!ok && !userStopped && !killed && !run.result && !asked && chain < 2) {
        autoTimers.set(project, setTimeout(() => start(project, { message: "(자동 이어가기) 방금 작업이 중간에 끊겼어. 이미 한 일은 다시 하지 말고, 남은 단계부터 이어서 마무리해 줘.", look, template, skill, scene, model, context, auto: true }).catch(() => {}), 1500));
      } else if (ok && !auto && !userStopped && !asked && skill !== "plan") {   // 기획 대화에서는 화면 구성으로 넘어가지 않는다
        // 콘티는 만들었는데 화면 구성(scene.js)이 없으면 한 번 이어서 짜게 한다 — "매번 같은 화면" 방지
        const missing = missingComposition(files);
        if (missing) autoTimers.set(project, setTimeout(() => start(project, missing.craft
          ? { message: `(자동 이어가기) 콘티 ${missing.id}.json 은 있는데 아직 영상(초안)이 없어. produce 스킬 순서대로 음성 → 장면 재료 → 검사 → 초안 렌더(render.py --draft) → 정지 화면 확인까지 마무리해 줘.`, look, template, skill: "produce", scene: null, model, context, auto: true }
          : { message: `(자동 이어가기) 콘티 ${missing.id}.json 은 있는데 화면 구성 compositions/${missing.id}/scene.js 가 없어. compose 스킬 순서대로 디자인 방향(direct.py --write) → scene.js → 정지 화면 확인 → lint(L15 없음)까지 마무리해 줘.`, look, template, skill: "compose", scene: null, model, context, auto: true }).catch(() => {}), 1500));
      }
    });
    return { sessionId: sess.sessionId };
  }

  /** 이번 턴에 쓴 콘티 중 화면 구성이 없는 것(템플릿이 Composed 이거나 비어 있는 HyperFrames 콘티) */
  function missingComposition(files) {
    for (const f of files || []) {
      const m = /^storyboards\/([^/]+)\.json$/.exec(f.path); if (!m || f.kind === "deleted") continue;
      try {
        const sb = JSON.parse(readFileSync(path.join(ROOT, f.path), "utf8"));
        const engine = sb.engine || (CRAFT ? "craft" : "hyperframes");
        if (engine === "craft") {
          // Craft: 제작 파일(craft.json)이 없으면 아직 만들지 않은 것
          if (!existsSync(path.join(ROOT, "compositions", m[1], "craft", "craft.json"))) return { id: m[1], craft: true };
          continue;
        }
        if ((sb.template === "Composed" || !sb.template) && !existsSync(path.join(ROOT, "compositions", m[1], "scene.js"))) return { id: m[1], craft: false };
      } catch { /* 깨진 콘티는 무시 */ }
    }
    return null;
  }

  /** 실행 중인 턴에 지시를 더한다 (OpenDesign run-steering).
   *  지금 끼워 넣을 수 없으면(턴을 여는 중 · 마무리 중 · Codex 처럼 입력 통로가 없음) 다음 차례로 줄 세운다 → "queued" */
  async function say(project, message, opts) {
    if (await steer(project, message)) return "steer";
    const run = runs.get(project);
    const q = queued.get(project) || []; q.push({ message, opts: { ...opts, message } }); queued.set(project, q);
    if (run) broadcast(run, { type: "queued", text: message });
    // 그사이 턴이 끝나 버렸으면 바로 보낸다
    if (!busy.has(project) && !run?.live) { const next = q.shift(); if (!q.length) queued.delete(project); start(project, next.opts).catch(() => {}); return "start"; }
    return "queued";
  }
  async function steer(project, message) {
    const run = runs.get(project);
    if (!run?.live || !run.stdinOpen) return false;
    run.child.stdin.write(userFrame(message));
    broadcast(run, { type: "steer", text: message });
    await mutate(project, (s) => { s.messages.push({ role: "user", text: message, steer: true, ts: Date.now() }); });
    return true;
  }

  /** 끼어들기: 지금 턴을 멈추고 이 말을 바로 다음 턴으로 보낸다(같은 세션이라 맥락은 이어짐).
   *  긴 명령이 도는 동안 추가 지시가 묻히는 문제 — 줄 맨 앞에 세운 뒤 멈춘다 */
  function interrupt(project, message, opts) {
    const run = runs.get(project);
    if (!run?.live) return null;
    const q = queued.get(project) || []; q.unshift({ message, opts: { ...opts, message } }); queued.set(project, q);
    broadcast(run, { type: "queued", text: message });
    run.interrupt = true;
    stop(project);
    return "interrupt";
  }
  /** 줄 서 있던 말 하나를 뺀다(보내기 취소) */
  function unqueue(project, index) {
    const q = queued.get(project);
    if (!q || index < 0 || index >= q.length) return false;
    q.splice(index, 1); if (!q.length) queued.delete(project);
    const run = runs.get(project);
    if (run) broadcast(run, { type: "unqueued", index });
    return true;
  }

  function stop(project) {
    const run = runs.get(project);
    // 턴과 턴 사이(자동 이어가기 대기 1.5초)에 멈추면 예약된 이어가기만 취소
    if (!run?.live) { const had = autoTimers.has(project); clearTimeout(autoTimers.get(project)); autoTimers.delete(project); return had; }
    run.stopped = true;   // claude 는 SIGTERM 을 받아 정상 종료 코드로 끝나기도 한다 → 신호가 아니라 이 표시로 '사용자가 멈춤'을 판단
    clearTimeout(autoTimers.get(project)); autoTimers.delete(project);
    killTree(run.child);   // 프로세스 그룹째 (claude → python · 크롬 자식까지)
    return true;
  }

  /**
   * 마지막 턴이 바꾼 파일을 턴 전 상태로 되돌린다(바이너리 그대로). paths 를 주면 그 파일만.
   * 턴 뒤에 사람이 또 고친 파일은 덮어쓰지 않고 conflicts 로 돌려준다.
   */
  async function revert(project, paths) {
    const dir = path.join(SESS, `${project}.snap`);
    let manifest;
    try { manifest = JSON.parse(await fs.readFile(path.join(dir, "manifest.json"), "utf8")); } catch { return { files: [], conflicts: [] }; }
    const targets = manifest.files.filter((f) => !paths || paths.includes(f.path));
    const done = [], conflicts = [];
    for (const f of targets) {
      const abs = path.resolve(ROOT, f.path);
      if (!abs.startsWith(ROOT + path.sep)) continue;
      const cur = existsSync(abs) ? hash(await fs.readFile(abs)) : null;
      if (cur !== f.after) { conflicts.push({ path: f.path, kind: f.kind }); continue; }
      if (f.kind === "added") await fs.rm(abs, { force: true });
      else { await fs.mkdir(path.dirname(abs), { recursive: true }); await atomicWrite(abs, await fs.readFile(path.join(dir, "blobs", f.before))); }
      done.push({ path: f.path, kind: f.kind });
    }
    if (done.length && !paths) await fs.rm(dir, { recursive: true, force: true });
    return { files: done, conflicts };
  }

  /** 진행 중인 턴의 이벤트 중 lastId 다음 것만 다시 보낸다 (다시 붙어도 중복 없음) */
  function subscribe(project, res, lastId = 0) {
    const clients = clientsOf(project);
    const run = runs.get(project);
    if (run?.live || busy.has(project)) for (const { id, ev } of run?.events || []) if (id > lastId) res.write(`id: ${id}\ndata: ${JSON.stringify(ev)}\n\n`);
    clients.add(res);
    return () => clients.delete(res);
  }

  return {
    history: async (id) => ({ ...(await load(id)), running: busy.has(id) || !!runs.get(id)?.live, queued: (queued.get(id) || []).map((x) => x.message) }),
    running: (id) => busy.has(id) || !!runs.get(id)?.live,
    reset: async (id) => {
      const run = runs.get(id);
      if (run?.live) { stop(id); await new Promise((r) => { const t = setTimeout(r, 6000); run.child.once("close", () => { clearTimeout(t); r(); }); }); }
      await (writeChain.get(id) || Promise.resolve()).catch(() => {});
      await fs.rm(sessFile(id), { force: true }); await fs.rm(`${sessFile(id)}.prev`, { force: true });
      await fs.rm(path.join(SESS, `${id}.snap`), { recursive: true, force: true });
      lastTurn.delete(id);
    },
    /** 서버 종료 때 실행 중인 에이전트를 함께 끈다 */
    shutdown: () => { shuttingDown = true; for (const t of autoTimers.values()) clearTimeout(t); autoTimers.clear(); for (const r of runs.values()) if (r.live) killTree(r.child); },
    /** 지금 일하는 대화들 — 어느 화면에서든 '다른 곳에서 작업 중'을 보이고 멈출 수 있게 */
    active: () => [...new Set([...busy, ...[...runs.values()].filter((r) => r.live).map((r) => r.project)])].map((id) => {
      const r = runs.get(id); const t = r?.live ? r.tools.at(-1) : null;
      return { id, user: r?.live ? r.events.find((e) => e.ev.type === "start")?.ev.user ?? "" : "", startedAt: r?.startedAt ?? Date.now(), tool: t ? { name: t.name, input: t.input } : null, stopping: !!r?.stopped, skill: r?.skill ?? null };
    }),
    start, steer, say, interrupt, unqueue, stop, revert, subscribe,
    queuedOf: (id) => (queued.get(id) || []).map((x) => x.message),
    lastTurnFiles: (id) => lastTurn.get(id)?.files ?? [],
  };
}
