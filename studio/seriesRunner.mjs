// Fluma 네이티브 시리즈 양산 — 주제만 주면 편수·주제 목록을 정하고 에이전트로 한 편씩 큐 처리 (n8n 불필요)
import { existsSync, readdirSync } from "node:fs";
import path from "node:path";
import { atomicWrite, readJson } from "./lib.mjs";

const RUNS_FILE = (root) => path.join(root, "data", "workspace", "series-runs.json");

const EPISODE_ANGLES = [
  "숨은 기능 3가지",
  "단축키·꿀팁",
  "초보가 헷갈리는 설정",
  "하나만 바꾸면 체감",
  "비교·정리",
  "속도 올리는 습관",
  "실수 방지",
];

export function newProjectId() {
  const d = new Date();
  const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `${date}-s${Date.now().toString(36).slice(-6)}-01`;
}

function decideEpisodeCount(theme, requested, topics, maxCap = 7) {
  if (topics.length) return Math.min(topics.length, 20);
  const n = Number(requested);
  if (Number.isFinite(n) && n > 0) return Math.min(20, Math.max(1, n));
  const t = String(theme || "").trim();
  const auto = t.length < 12 ? 3 : t.length < 28 ? 5 : 7;
  return Math.min(maxCap, auto);
}

function expandTopics(theme, count, explicit = []) {
  if (explicit.length) return explicit.slice(0, count).map((x) => String(x).trim()).filter(Boolean);
  const base = String(theme || "").trim();
  return Array.from({ length: count }, (_, i) => {
    if (i === 0) return base;
    const ang = EPISODE_ANGLES[i % EPISODE_ANGLES.length];
    return `${base} — ${ang} (${i + 1}편)`;
  });
}

function episodePrompt(run, ep) {
  const preset = run.presetId ? `프리셋 id: ${run.presetId}(라이브러리 presets.json 참고).` : "";
  return [
    `[시리즈 자동 제작] 시리즈 ${run.id} · ${ep.n}/${run.episodes.length}편`,
    `이번 편 주제: ${ep.topic}`,
    `경로: ${run.route || "material"} (material: 실제 자료 + Craft · clip: 퍼온 클립 재편집).`,
    "사용자에게 터미널 명령 시키지 말고, 조사→콘티→produce까지 말로 멈추지 말고 완성 MP4를 media로 보여줘.",
    "선택지(choices)는 정말 막힐 때만. 같은 시리즈 톤·형식을 유지.",
    preset,
  ].filter(Boolean).join("\n");
}

function hasDeliverable(root, projectId) {
  const craft = path.join(root, "data", "compositions", projectId, "craft", "craft.json");
  if (existsSync(craft)) return true;
  const out = path.join(root, "data", "out");
  try {
    return readdirSync(out, { withFileTypes: true }).some((e) => e.isFile() && e.name.startsWith(projectId) && e.name.endsWith(".mp4"));
  } catch {
    return false;
  }
}

export function createSeriesRunner({ ROOT, agent, onChange = () => {} }) {
  const file = RUNS_FILE(ROOT);
  let gate = false;

  async function loadRuns() {
    return (await readJson(file, [])) || [];
  }
  async function saveRuns(runs) {
    await atomicWrite(file, JSON.stringify(runs, null, 2));
  }

  async function publishRun(run) {
    onChange(run);
  }

  function seriesBusy(runs, ignoreProjectId = null) {
    return runs.some((r) => r.status === "running" && r.episodes.some((e) => e.status === "running" && e.projectId !== ignoreProjectId));
  }

  async function advance(run) {
    const runs = await loadRuns();
    const idx = runs.findIndex((r) => r.id === run.id);
    if (idx < 0) return;
    runs[idx] = run;
    if (run.current >= run.episodes.length) {
      run.status = "done";
      run.finishedAt = new Date().toISOString();
    }
    await saveRuns(runs);
    await publishRun(run);
    if (run.status === "running") setTimeout(() => tick(run.id), 2500);
  }

  async function tick(seriesId) {
    if (gate) return;
    const runs = await loadRuns();
    const run = runs.find((r) => r.id === seriesId);
    if (!run || run.status !== "running") return;

    const cur = run.episodes[run.current];
    if (!cur) {
      run.status = "done";
      run.finishedAt = new Date().toISOString();
      await saveRuns(runs);
      await publishRun(run);
      return;
    }

    if (cur.status === "pending") {
      if (seriesBusy(runs) || agent.running(cur.projectId)) return;
      gate = true;
      try {
        cur.status = "running";
        cur.startedAt = new Date().toISOString();
        await saveRuns(runs);
        await publishRun(run);
        await agent.start(cur.projectId, {
          message: episodePrompt(run, cur),
          skill: "plan",
          context: { menu: "plan", seriesId: run.id, episode: cur.n },
        });
      } catch (e) {
        cur.status = "error";
        cur.error = String(e.message || e);
        run.current++;
        await advance(run);
      } finally {
        gate = false;
      }
      return;
    }

    if (cur.status === "running" && !agent.running(cur.projectId)) {
      cur.delivered = hasDeliverable(ROOT, cur.projectId);
      cur.status = cur.delivered ? "done" : "done";
      cur.finishedAt = new Date().toISOString();
      run.current++;
      await advance(run);
    }
  }

  async function onAgentIdle(projectId) {
    const runs = await loadRuns();
    const run = runs.find((r) => r.status === "running" && r.episodes.some((e) => e.projectId === projectId && e.status === "running"));
    if (!run) return;
    setTimeout(() => tick(run.id), 1500);
  }

  async function start(body = {}) {
    const theme = String(body.theme || body.topics?.[0] || "").trim();
    if (!theme) throw new Error("시리즈 주제(theme)가 필요합니다");
    const topics = Array.isArray(body.topics) ? body.topics.map((t) => String(t).trim()).filter(Boolean) : [];
    const maxCap = Math.min(20, Math.max(1, Number(body.maxEpisodes) || 7));
    const count = decideEpisodeCount(theme, body.count, topics, maxCap);
    const episodeTopics = expandTopics(theme, count, topics.length ? topics : []);
    const run = {
      id: `series-${Date.now().toString(36)}`,
      theme,
      presetId: body.presetId || null,
      route: body.route === "clip" ? "clip" : "material",
      autopilot: body.autopilot !== false,
      createdAt: new Date().toISOString(),
      status: "running",
      current: 0,
      episodes: episodeTopics.map((topic, i) => ({
        n: i + 1,
        topic,
        projectId: newProjectId(),
        status: "pending",
      })),
    };
    const runs = await loadRuns();
    runs.unshift(run);
    await saveRuns(runs);
    await publishRun(run);
    setTimeout(() => tick(run.id), 500);
    return run;
  }

  async function stop(seriesId) {
    const runs = await loadRuns();
    const run = runs.find((r) => r.id === seriesId);
    if (!run) return null;
    run.status = "paused";
    run.pausedAt = new Date().toISOString();
    await saveRuns(runs);
    await publishRun(run);
    return run;
  }

  async function list() {
    return (await loadRuns()).slice(0, 30);
  }

  async function get(id) {
    return (await loadRuns()).find((r) => r.id === id) || null;
  }

  setInterval(() => {
    loadRuns().then((runs) => {
      for (const r of runs) if (r.status === "running") tick(r.id);
    }).catch(() => {});
  }, 45_000).unref();

  return { start, stop, list, get, tick, onAgentIdle };
}