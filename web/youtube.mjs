// YouTube 연결 · 업로드 · 통계 — 공식 API 만(OAuth 2.0). 토큰은 키와 같이 ~/.shortsforge/youtube.json(0600)에만 두고 화면 · 에이전트로 보내지 않는다.
// 사용자가 Google Cloud 에서 만든 OAuth 클라이언트(웹 애플리케이션, 리디렉션 URI = http://127.0.0.1:4310/api/youtube/callback)를 설정 화면에 넣고 '연결'을 누른다.
import { promises as fs, existsSync, readFileSync, writeFileSync, mkdirSync, renameSync, chmodSync, statSync, createReadStream } from "node:fs";
import path from "node:path";
import os from "node:os";
import { randomUUID } from "node:crypto";

const FILE = path.join(os.homedir(), ".shortsforge", "youtube.json");
const SCOPES = [
  "https://www.googleapis.com/auth/youtube.upload",
  "https://www.googleapis.com/auth/youtube.readonly",
  "https://www.googleapis.com/auth/yt-analytics.readonly",
];
export const REDIRECT = "http://127.0.0.1:4310/api/youtube/callback";

const load = () => { try { return JSON.parse(readFileSync(FILE, "utf8")); } catch { return {}; } };
const save = (d) => {
  mkdirSync(path.dirname(FILE), { recursive: true, mode: 0o700 });
  const tmp = `${FILE}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(d, null, 1), { mode: 0o600 });
  try { chmodSync(tmp, 0o600); } catch { /* 윈도우 */ }
  renameSync(tmp, FILE);
};

export function createYoutube() {
  const states = new Map();          // OAuth state → 돌아갈 화면 주소
  let access = null;                 // { token, until }

  /** 화면에 보낼 상태(비밀 값 없음) */
  const status = () => {
    const d = load();
    const ch = d.channel ? { ...d.channel, thumb: d.channel.thumb ? `/api/youtube/avatar?v=${encodeURIComponent(d.channel.thumb.slice(-12))}` : null } : null;
    return { configured: !!(d.client_id && d.client_secret), connected: !!d.refresh_token, channel: ch, redirect: REDIRECT };
  };
  const setClient = (client_id, client_secret) => {
    const d = load();
    const changed = d.client_id !== client_id;
    save({ ...(changed ? {} : d), client_id: String(client_id || "").trim(), client_secret: String(client_secret || "").trim() });
    access = null;
  };
  const authUrl = (back) => {
    const d = load();
    if (!d.client_id) throw new Error("먼저 OAuth 클라이언트 ID · 비밀을 넣어 주세요");
    const state = randomUUID();
    states.set(state, back);
    const q = new URLSearchParams({ client_id: d.client_id, redirect_uri: REDIRECT, response_type: "code", scope: SCOPES.join(" "),
      access_type: "offline", prompt: "consent", include_granted_scopes: "true", state });
    return `https://accounts.google.com/o/oauth2/v2/auth?${q}`;
  };
  const token = async (body) => {
    const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error_description || j.error || `토큰 요청 실패 ${r.status}`);
    return j;
  };
  /** 콜백: code → 토큰 → 채널 정보까지 저장. 돌아갈 화면 주소를 돌려준다 */
  const callback = async (code, state) => {
    const back = states.get(state); states.delete(state);
    if (!back) throw new Error("연결 요청이 만료됐어요 — 설정에서 다시 연결해 주세요");
    const d = load();
    const j = await token({ code, client_id: d.client_id, client_secret: d.client_secret, redirect_uri: REDIRECT, grant_type: "authorization_code" });
    access = { token: j.access_token, until: Date.now() + (j.expires_in - 60) * 1000 };
    save({ ...d, refresh_token: j.refresh_token || d.refresh_token, connected_at: new Date().toISOString() });
    const ch = await api("https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true");
    const c = ch.items?.[0];
    save({ ...load(), channel: chan(c) });
    return back;
  };
  const chan = (c) => c ? { id: c.id, title: c.snippet?.title, thumb: c.snippet?.thumbnails?.high?.url || c.snippet?.thumbnails?.medium?.url || c.snippet?.thumbnails?.default?.url,
    subscribers: Number(c.statistics?.subscriberCount ?? 0), videos: Number(c.statistics?.videoCount ?? 0) } : null;
  /** 채널 정보 새로 받기(아이콘 · 구독자 · 영상 수) */
  const refreshChannel = async () => {
    const ch = await api("https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true");
    save({ ...load(), channel: chan(ch.items?.[0]) });
    return load().channel;
  };
  /** 채널 아이콘 — 화면이 Google 이미지 서버에 직접 가지 않게(차단 · 리퍼러 문제) 서버가 받아 둔다 */
  const avatar = async (cacheDir) => {
    const d = load(); const url = d.channel?.thumb; if (!url) return null;
    const f = path.join(cacheDir, `yt-avatar-${Buffer.from(url).toString("base64url").slice(-24)}.jpg`);
    if (!existsSync(f)) {
      const r = await fetch(url); if (!r.ok) return null;
      mkdirSync(cacheDir, { recursive: true }); writeFileSync(f, Buffer.from(await r.arrayBuffer()));
    }
    return f;
  };
  const disconnect = async () => {
    const d = load();
    if (d.refresh_token) await fetch(`https://oauth2.googleapis.com/revoke?token=${encodeURIComponent(d.refresh_token)}`, { method: "POST" }).catch(() => {});
    delete d.refresh_token; delete d.channel; delete d.connected_at;
    save(d); access = null;
  };
  const bearer = async () => {
    if (access && access.until > Date.now()) return access.token;
    const d = load();
    if (!d.refresh_token) throw Object.assign(new Error("YouTube 계정이 연결되지 않았어요 — 설정 → YouTube 에서 연결"), { status: 409 });
    const j = await token({ client_id: d.client_id, client_secret: d.client_secret, refresh_token: d.refresh_token, grant_type: "refresh_token" });
    access = { token: j.access_token, until: Date.now() + (j.expires_in - 60) * 1000 };
    return access.token;
  };
  const api = async (url, init = {}) => {
    const r = await fetch(url, { ...init, headers: { ...(init.headers || {}), Authorization: `Bearer ${await bearer()}` } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(j.error?.message || `YouTube API ${r.status}`), { status: r.status });
    return j;
  };

  /** 재개 가능 업로드(공식). 진행률 콜백(0~1) → videoId */
  const upload = async (file, meta, onProgress = () => {}) => {
    const size = statSync(file).size;
    const body = { snippet: { title: meta.title.slice(0, 100), description: meta.description || "", tags: meta.tags || [], categoryId: meta.categoryId || "27", defaultLanguage: meta.language || "ko" },
      status: { privacyStatus: meta.privacy || "private", selfDeclaredMadeForKids: false, containsSyntheticMedia: !!meta.synthetic } };
    const init = await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", {
      method: "POST", headers: { Authorization: `Bearer ${await bearer()}`, "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": String(size) }, body: JSON.stringify(body) });
    if (!init.ok) { const j = await init.json().catch(() => ({})); throw new Error(j.error?.message || `업로드 시작 실패 ${init.status}`); }
    const loc = init.headers.get("location");
    let sent = 0;
    const stream = createReadStream(file);
    stream.on("data", (b) => { sent += b.length; onProgress(sent / size); });
    const r = await fetch(loc, { method: "PUT", headers: { Authorization: `Bearer ${await bearer()}`, "Content-Type": "video/mp4", "Content-Length": String(size) }, body: stream, duplex: "half" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error?.message || `업로드 실패 ${r.status}`);
    return j.id;
  };

  /** 한 영상의 통계 묶음 — 분석 API(약 2일 늦음) + 데이터 API(실시간 숫자) */
  const stats = async (videoId, since) => {
    const today = new Date().toISOString().slice(0, 10);
    const start = (since || today).slice(0, 10);
    const rep = (q) => api(`https://youtubeanalytics.googleapis.com/v2/reports?${new URLSearchParams({ ids: "channel==MINE", startDate: start, endDate: today, filters: `video==${videoId}`, ...q })}`)
      .then((j) => ({ cols: (j.columnHeaders || []).map((c) => c.name), rows: j.rows || [] })).catch((e) => ({ error: String(e.message || e), cols: [], rows: [] }));
    const [summary, retention, traffic, daily, demo, live] = await Promise.all([
      rep({ metrics: "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,dislikes,comments,shares,subscribersGained,subscribersLost" }),
      rep({ dimensions: "elapsedVideoTimeRatio", metrics: "audienceWatchRatio,relativeRetentionPerformance" }),
      rep({ dimensions: "insightTrafficSourceType", metrics: "views,engagedViews", sort: "-views" }),
      rep({ dimensions: "day", metrics: "views,engagedViews,likes,subscribersGained", sort: "day" }),
      rep({ dimensions: "ageGroup,gender", metrics: "viewerPercentage" }),
      api(`https://www.googleapis.com/youtube/v3/videos?part=statistics,status,snippet,contentDetails&id=${encodeURIComponent(videoId)}`).catch((e) => ({ error: String(e.message || e) })),
    ]);
    return { videoId, at: new Date().toISOString(), summary, retention, traffic, daily, demo, live: live.items?.[0] ?? null, liveError: live.error };
  };

  /** 내 채널에 올라간 영상(최신순) — 업로드 재생목록 → 영상 상세(조회 · 좋아요 · 길이 · 공개 범위) */
  const videos = async (max = 50) => {
    const ch = await api("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true");
    const up = ch.items?.[0]?.contentDetails?.relatedPlaylists?.uploads;
    if (!up) return [];
    const pl = await api(`https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults=${Math.min(50, max)}&playlistId=${encodeURIComponent(up)}`);
    const ids = (pl.items || []).map((i) => i.contentDetails?.videoId).filter(Boolean);
    if (!ids.length) return [];
    const v = await api(`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics,contentDetails,status&id=${ids.join(",")}`);
    const sec = (d) => { const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(d || "") || []; return (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0); };
    return (v.items || []).map((x) => ({ videoId: x.id, title: x.snippet?.title, published: x.snippet?.publishedAt, thumb: x.snippet?.thumbnails?.medium?.url,
      duration: sec(x.contentDetails?.duration), privacy: x.status?.privacyStatus, views: Number(x.statistics?.viewCount ?? 0), likes: Number(x.statistics?.likeCount ?? 0), comments: Number(x.statistics?.commentCount ?? 0) }))
      .sort((a, b) => String(b.published).localeCompare(String(a.published)));
  };
  return { status, setClient, authUrl, callback, disconnect, upload, stats, refreshChannel, avatar, videos };
}
