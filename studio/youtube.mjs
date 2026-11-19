// YouTube 연결 · 업로드 · 통계 — 공식 API 만(OAuth 2.0). 채널(계정) 여러 개 · 기본 하나. 토큰은 키와 같이 ~/.shortsforge/youtube.json(0600)에만 두고 화면 · 에이전트로 보내지 않는다.
// 사용자가 Google Cloud 에서 만든 OAuth 클라이언트(웹 애플리케이션, 리디렉션 URI = http://127.0.0.1:4310/api/youtube/callback)를 설정 화면에 넣고 '연결'을 누른다.
import { promises as fs, existsSync, readFileSync, writeFileSync, mkdirSync, renameSync, chmodSync, statSync, createReadStream } from "node:fs";
import path from "node:path";
import os from "node:os";
import { randomUUID } from "node:crypto";

const DEFAULT_FILE = path.join(os.homedir(), ".shortsforge", "youtube.json");
const SCOPES = [
  "https://www.googleapis.com/auth/youtube.upload",
  "https://www.googleapis.com/auth/youtube.readonly",
  "https://www.googleapis.com/auth/yt-analytics.readonly",
];
export const REDIRECT = "http://127.0.0.1:4310/api/youtube/callback";

/** 저장 모양 맞추기 — 예전 한 계정 모양({ refresh_token, channel, connected_at })을 accounts[0] 로 옮긴다.
    새 모양: { client_id, client_secret, accounts: [{ id(채널 id), refresh_token, channel, connected_at }], default } */
export function normalize(raw) {
  const d = raw && typeof raw === "object" && !Array.isArray(raw) ? { ...raw } : {};
  const accounts = (Array.isArray(d.accounts) ? d.accounts : []).filter((a) => a && typeof a === "object" && a.id).map((a) => ({ ...a }));
  if (d.refresh_token) {
    const id = d.channel?.id || "legacy";   // 채널 정보를 받기 전에 끊긴 옛 파일 — 채널을 새로 받으면 진짜 id 로 바뀐다
    if (!accounts.some((a) => a.id === id)) accounts.unshift({ id, refresh_token: d.refresh_token, channel: d.channel ?? null, connected_at: d.connected_at ?? null });
  }
  delete d.refresh_token; delete d.channel; delete d.connected_at;
  const def = accounts.some((a) => a.id === d.default) ? d.default : accounts[0]?.id ?? null;
  return { ...d, accounts, default: def };
}

export function createYoutube({ file = DEFAULT_FILE } = {}) {
  const FILE = file;
  const save = (d) => {
    mkdirSync(path.dirname(FILE), { recursive: true, mode: 0o700 });
    const tmp = `${FILE}.${process.pid}.tmp`;
    writeFileSync(tmp, JSON.stringify(d, null, 1), { mode: 0o600 });
    try { chmodSync(tmp, 0o600); } catch { /* 윈도우 */ }
    renameSync(tmp, FILE);
  };
  /** 읽을 때 옛 모양이면 새 모양으로 한 번 고쳐 쓴다(0600 유지) */
  const load = () => {
    let raw;
    try { raw = JSON.parse(readFileSync(FILE, "utf8")); } catch { return normalize({}); }
    const d = normalize(raw);
    if (raw && (raw.refresh_token || raw.channel || !Array.isArray(raw.accounts) || raw.default !== d.default) && existsSync(FILE)) { try { save(d); } catch { /* 읽기 전용이면 메모리에서만 */ } }
    return d;
  };
  const states = new Map();          // OAuth state → 돌아갈 화면 주소
  const access = new Map();          // 계정 id → { token, until }

  const pub = (a) => {
    const c = a.channel || {};
    return { id: a.id, title: c.title || a.id, handle: c.handle || null, subscribers: c.subscribers ?? null, videos: c.videos ?? null, connected_at: a.connected_at ?? null,
      thumb: c.thumb ? `/api/youtube/avatar?id=${encodeURIComponent(a.id)}&v=${encodeURIComponent(String(c.thumb).slice(-12))}` : null };
  };
  /** 화면에 보낼 상태(비밀 값 없음). channel 은 기본 계정 — 예전 화면 호환 */
  const status = () => {
    const d = load();
    const accounts = d.accounts.map(pub);
    return { configured: !!(d.client_id && d.client_secret), connected: accounts.length > 0, accounts, default: d.default,
      channel: accounts.find((a) => a.id === d.default) ?? null, redirect: REDIRECT };
  };
  /** 실제로 쓸 계정 id — 고른 것이 아직 연결돼 있으면 그것, 아니면 기본 */
  const resolve = (id) => { const d = load(); return (id && d.accounts.some((a) => a.id === id)) ? id : d.default; };
  const has = (id) => !!id && load().accounts.some((a) => a.id === id);
  const setClient = (client_id, client_secret) => {
    const d = load();
    const changed = d.client_id !== client_id;   // 다른 클라이언트면 예전 토큰은 못 쓴다 — 계정도 비운다
    save({ ...(changed ? { accounts: [], default: null } : d), client_id: String(client_id || "").trim(), client_secret: String(client_secret || "").trim() });
    access.clear();
  };
  const authUrl = (back) => {
    const d = load();
    if (!d.client_id) throw new Error("먼저 OAuth 클라이언트 ID · 비밀을 넣어 주세요");
    const state = randomUUID();
    states.set(state, back);
    // select_account: 매번 계정(브랜드 채널 포함)을 고르게 — 다른 채널을 더할 수 있다. consent: refresh_token 을 꼭 받게
    const q = new URLSearchParams({ client_id: d.client_id, redirect_uri: REDIRECT, response_type: "code", scope: SCOPES.join(" "),
      access_type: "offline", prompt: "select_account consent", include_granted_scopes: "true", state });
    return `https://accounts.google.com/o/oauth2/v2/auth?${q}`;
  };
  const token = async (body) => {
    const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error_description || j.error || `토큰 요청 실패 ${r.status}`);
    return j;
  };
  const withToken = async (tok, url, init = {}) => {
    const r = await fetch(url, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${tok}` } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(j.error?.message || `YouTube API ${r.status}`), { status: r.status });
    return j;
  };
  const chan = (c) => c ? { id: c.id, title: c.snippet?.title, handle: c.snippet?.customUrl || null, thumb: c.snippet?.thumbnails?.high?.url || c.snippet?.thumbnails?.medium?.url || c.snippet?.thumbnails?.default?.url,
    subscribers: Number(c.statistics?.subscriberCount ?? 0), videos: Number(c.statistics?.videoCount ?? 0) } : null;
  /** 콜백: code → 토큰 → 채널 정보 → 계정 목록에 더한다(같은 채널이면 토큰만 바꿈). 첫 계정은 기본. 돌아갈 화면 주소를 돌려준다 */
  const callback = async (code, state) => {
    const back = states.get(state); states.delete(state);
    if (!back) throw new Error("연결 요청이 만료됐어요 — 설정에서 다시 연결해 주세요");
    const d0 = load();
    const j = await token({ code, client_id: d0.client_id, client_secret: d0.client_secret, redirect_uri: REDIRECT, grant_type: "authorization_code" });
    const ch = await withToken(j.access_token, "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true");
    const c = chan(ch.items?.[0]);
    if (!c?.id) throw new Error("이 Google 계정에는 YouTube 채널이 없어요 — 채널을 만든 뒤 다시 연결해 주세요");
    const d = load();
    const old = d.accounts.find((a) => a.id === c.id);
    const refresh_token = j.refresh_token || old?.refresh_token;
    if (!refresh_token) throw new Error("Google 이 갱신 토큰을 주지 않았어요 — 다시 연결해 주세요");
    const acc = { id: c.id, refresh_token, channel: c, connected_at: new Date().toISOString() };
    const accounts = old ? d.accounts.map((a) => (a.id === c.id ? acc : a)) : [...d.accounts, acc];
    save({ ...d, accounts, default: d.default && accounts.some((a) => a.id === d.default) ? d.default : c.id });
    access.set(c.id, { token: j.access_token, until: Date.now() + (j.expires_in - 60) * 1000 });
    return back;
  };
  const acct = (id) => {
    const d = load();
    const want = id || d.default;
    const a = d.accounts.find((x) => x.id === want);
    if (!a) throw Object.assign(new Error(id && d.accounts.length ? "그 YouTube 계정은 연결돼 있지 않아요 — 설정 → YouTube" : "YouTube 계정이 연결되지 않았어요 — 설정 → YouTube 에서 연결"), { status: 409 });
    return { d, a };
  };
  const bearer = async (id) => {
    const { d, a } = acct(id);
    const c = access.get(a.id);
    if (c && c.until > Date.now()) return c.token;
    const j = await token({ client_id: d.client_id, client_secret: d.client_secret, refresh_token: a.refresh_token, grant_type: "refresh_token" });
    access.set(a.id, { token: j.access_token, until: Date.now() + (j.expires_in - 60) * 1000 });
    return j.access_token;
  };
  const api = async (url, init = {}, id) => withToken(await bearer(id), url, init);
  /** 채널 정보 새로 받기(아이콘 · 구독자 · 영상 수). 옛 파일의 'legacy' id 는 여기서 진짜 채널 id 로 바뀐다 */
  const refreshChannel = async (id) => {
    const { a } = acct(id);
    const tok = await bearer(a.id);
    const c = chan((await withToken(tok, "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true")).items?.[0]);
    if (!c) return null;
    const d = load();
    const dup = c.id !== a.id && d.accounts.some((x) => x.id === c.id);
    const accounts = d.accounts.filter((x) => !(dup && x.id === a.id)).map((x) => (x.id === a.id ? { ...x, id: c.id, channel: c } : x));
    save({ ...d, accounts, default: d.default === a.id ? c.id : d.default });
    if (c.id !== a.id) { access.set(c.id, access.get(a.id)); access.delete(a.id); }
    return c;
  };
  /** 채널 아이콘 — 화면이 Google 이미지 서버에 직접 가지 않게(차단 · 리퍼러 문제) 서버가 받아 둔다 */
  const avatar = async (cacheDir, id) => {
    const d = load(); const a = d.accounts.find((x) => x.id === (id || d.default));
    const url = a?.channel?.thumb; if (!url) return null;
    const f = path.join(cacheDir, `yt-avatar-${Buffer.from(url).toString("base64url").slice(-24)}.jpg`);
    if (!existsSync(f)) {
      const r = await fetch(url); if (!r.ok) return null;
      mkdirSync(cacheDir, { recursive: true }); writeFileSync(f, Buffer.from(await r.arrayBuffer()));
    }
    return f;
  };
  /** 계정 하나 끊기(id 없으면 모두). 기본 계정을 끊으면 남은 첫 계정이 기본 */
  const disconnect = async (id) => {
    const d = load();
    const gone = id ? d.accounts.filter((a) => a.id === id) : d.accounts;
    for (const a of gone) {
      if (a.refresh_token) await fetch(`https://oauth2.googleapis.com/revoke?token=${encodeURIComponent(a.refresh_token)}`, { method: "POST" }).catch(() => {});
      access.delete(a.id);
    }
    const accounts = id ? d.accounts.filter((a) => a.id !== id) : [];
    save({ ...d, accounts, default: accounts.some((a) => a.id === d.default) ? d.default : accounts[0]?.id ?? null });
  };
  const setDefault = (id) => {
    const d = load();
    if (!d.accounts.some((a) => a.id === id)) throw Object.assign(new Error("그 YouTube 계정은 연결돼 있지 않아요"), { status: 404 });
    save({ ...d, default: id });
  };

  /** 재개 가능 업로드(공식). 진행률 콜백(0~1) → videoId */
  const upload = async (file, meta, onProgress = () => {}, account) => {
    const size = statSync(file).size;
    const body = { snippet: { title: meta.title.slice(0, 100), description: meta.description || "", tags: meta.tags || [], categoryId: meta.categoryId || "27", defaultLanguage: meta.language || "ko" },
      status: { privacyStatus: meta.privacy || "private", selfDeclaredMadeForKids: false, containsSyntheticMedia: !!meta.synthetic } };
    const init = await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", {
      method: "POST", headers: { Authorization: `Bearer ${await bearer(account)}`, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": String(size) }, body: JSON.stringify(body) });
    if (!init.ok) { const j = await init.json().catch(() => ({})); throw new Error(j.error?.message || `업로드 시작 실패 ${init.status}`); }
    const loc = init.headers.get("location");
    let sent = 0;
    const stream = createReadStream(file);
    stream.on("data", (b) => { sent += b.length; onProgress(sent / size); });
    const r = await fetch(loc, { method: "PUT", headers: { Authorization: `Bearer ${await bearer(account)}`, "Content-Type": "video/mp4", "Content-Length": String(size) }, body: stream, duplex: "half" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error?.message || `업로드 실패 ${r.status}`);
    return j.id;
  };

  /** 한 영상의 통계 묶음 — 분석 API(약 2일 늦음) + 데이터 API(실시간 숫자) */
  const stats = async (videoId, since, account) => {
    const today = new Date().toISOString().slice(0, 10);
    const start = (since || today).slice(0, 10);
    const rep = (q) => api(`https://youtubeanalytics.googleapis.com/v2/reports?${new URLSearchParams({ ids: "channel==MINE", startDate: start, endDate: today, filters: `video==${videoId}`, ...q })}`, {}, account)
      .then((j) => ({ cols: (j.columnHeaders || []).map((c) => c.name), rows: j.rows || [] })).catch((e) => ({ error: String(e.message || e), cols: [], rows: [] }));
    const [summary, retention, traffic, daily, demo, live] = await Promise.all([
      rep({ metrics: "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,dislikes,comments,shares,subscribersGained,subscribersLost" }),
      rep({ dimensions: "elapsedVideoTimeRatio", metrics: "audienceWatchRatio,relativeRetentionPerformance" }),
      rep({ dimensions: "insightTrafficSourceType", metrics: "views,engagedViews", sort: "-views" }),
      rep({ dimensions: "day", metrics: "views,engagedViews,likes,subscribersGained", sort: "day" }),
      rep({ dimensions: "ageGroup,gender", metrics: "viewerPercentage" }),
      api(`https://www.googleapis.com/youtube/v3/videos?part=statistics,status,snippet,contentDetails&id=${encodeURIComponent(videoId)}`, {}, account).catch((e) => ({ error: String(e.message || e) })),
    ]);
    return { videoId, at: new Date().toISOString(), summary, retention, traffic, daily, demo, live: live.items?.[0] ?? null, liveError: live.error };
  };

  /** 그 계정 채널에 올라간 영상(최신순) — 업로드 재생목록 → 영상 상세(조회 · 좋아요 · 길이 · 공개 범위) */
  const videos = async (max = 50, account) => {
    const ch = await api("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true", {}, account);
    const up = ch.items?.[0]?.contentDetails?.relatedPlaylists?.uploads;
    if (!up) return [];
    const pl = await api(`https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=${Math.min(50, max)}&playlistId=${encodeURIComponent(up)}`, {}, account);
    const ids = (pl.items || []).map((i) => i.contentDetails?.videoId).filter(Boolean);
    if (!ids.length) return [];
    const v = await api(`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails,status&id=${ids.join(",")}`, {}, account);
    const sec = (d) => { const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(d || "") || []; return (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0); };
    return (v.items || []).map((x) => ({ videoId: x.id, title: x.snippet?.title, published: x.snippet?.publishedAt, thumb: x.snippet?.thumbnails?.medium?.url,
      duration: sec(x.contentDetails?.duration), privacy: x.status?.privacyStatus, views: Number(x.statistics?.viewCount ?? 0), likes: Number(x.statistics?.likeCount ?? 0), comments: Number(x.statistics?.commentCount ?? 0) }))
      .sort((a, b) => String(b.published).localeCompare(String(a.published)));
  };
  return { status, resolve, has, setClient, authUrl, callback, disconnect, setDefault, upload, stats, refreshChannel, avatar, videos };
}
