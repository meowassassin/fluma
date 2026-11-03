/* 설정 → YouTube: 내 채널 연결(OAuth). 클라이언트 ID · 비밀은 서버가 ~/.shortsforge/youtube.json 에만 두고 화면으로 돌려주지 않는다.
   연결하면 편집기에서 바로 올리고(공식 업로드 API), 올린 영상의 통계를 장면별로 본다 */
import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Tag } from "../../ui/kit";
import { Icon } from "../../ui/Icon";
import { errMsg } from "../../lib/api";
import { qc } from "../../lib/queries";
import { t } from "../../lib/i18n";
import { StatsView, type ChannelVideo } from "../studio/PublishView";

type Yt = { configured: boolean; connected: boolean; redirect: string; channel: { id: string; title: string; thumb?: string; subscribers?: number; videos?: number } | null };
export const useYoutube = () => useQuery<Yt>({ queryKey: ["youtube"], staleTime: 30_000, queryFn: async ({ signal }) => (await fetch("/api/youtube", { signal })).json() });

export const YoutubeSec: React.FC = () => {
  const { data: y } = useYoutube();
  const [id, setId] = useState(""), [secret, setSecret] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    if (q.get("connected")) { toast.success(t("YouTube 채널을 연결했어요")); qc.invalidateQueries({ queryKey: ["youtube"] }); history.replaceState(null, "", location.pathname); }
    if (q.get("error")) { toast.error(t("연결하지 못했어요"), { description: q.get("error") ?? "" }); history.replaceState(null, "", location.pathname); }
  }, []);
  const saveClient = async () => {
    setBusy(true);
    try {
      const r = await fetch("/api/youtube/client", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client_id: id, client_secret: secret }) });
      const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`);
      setSecret(""); qc.setQueryData(["youtube"], j); toast.success(t("클라이언트를 저장했어요 — 이제 '연결'을 누르세요"));
    } catch (e) { toast.error(t("저장하지 못했어요"), { description: errMsg(e) }); } finally { setBusy(false); }
  };
  const connect = () => { location.href = `/api/youtube/auth?back=${encodeURIComponent(`${location.origin}/settings/youtube`)}`; };
  const disconnect = async () => { await fetch("/api/youtube", { method: "DELETE" }); qc.invalidateQueries({ queryKey: ["youtube"] }); toast(t("연결을 끊었어요")); };
  if (!y) return null;
  return (
    <div className="col yt-sec">
      <div className="set-h"><div><h2>{t("YouTube 채널")}</h2><p>{t("연결하면 편집기에서 바로 올리고, 올린 영상의 통계(이탈 곡선 · 유입 경로 · 시청자)를 장면별로 봅니다. 공식 API 만 씁니다.")}</p></div>
        {y.connected ? <Tag tone="ok">{t("연결됨")}</Tag> : y.configured ? <Tag tone="warn">{t("연결 전")}</Tag> : <Tag>{t("설정 필요")}</Tag>}</div>

      {y.connected && y.channel && (
        <div className="yt-ch">
          {y.channel.thumb && <img src={y.channel.thumb} alt="" />}
          <div><b>{y.channel.title}</b><span className="faint small">{t("구독자 {n} · 영상 {v}", { n: (y.channel.subscribers ?? 0).toLocaleString(), v: y.channel.videos ?? 0 })}</span></div>
          <span className="grow" />
          <Button variant="ghost" onClick={disconnect}>{t("연결 끊기")}</Button>
        </div>
      )}
      {y.connected && <ChannelVideos />}

      {!y.connected && (<>
        <ol className="yt-steps">
          <li>{t("Google Cloud 콘솔에서 프로젝트를 만들고 'YouTube Data API v3' 와 'YouTube Analytics API' 를 사용 설정")} <a href="https://console.cloud.google.com/apis/library" target="_blank" rel="noreferrer"><Icon n="external" s={12} /></a></li>
          <li>{t("OAuth 동의 화면: 외부 · 테스트 모드, 테스트 사용자에 내 Google 계정 추가")}</li>
          <li>{t("사용자 인증 정보 → OAuth 클라이언트 ID → 웹 애플리케이션, 승인된 리디렉션 URI 에 아래 주소")} <code className="yt-uri">{y.redirect}</code></li>
          <li>{t("만든 클라이언트 ID · 비밀을 아래에 넣고 저장 → '연결'")}</li>
        </ol>
        <div className="yt-form">
          <label>{t("클라이언트 ID")}<input value={id} onChange={(e) => setId(e.target.value)} placeholder="…apps.googleusercontent.com" autoComplete="off" spellCheck={false} /></label>
          <label>{t("클라이언트 비밀")}<input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder={y.configured ? t("저장됨 — 바꿀 때만 입력") : "GOCSPX-…"} autoComplete="off" /></label>
          <div className="row gap">
            <Button variant="secondary" disabled={!id || !secret} loading={busy} onClick={saveClient}>{t("저장")}</Button>
            <Button variant="primary" icon="link" disabled={!y.configured} onClick={connect}>{t("YouTube 연결")}</Button>
          </div>
          <p className="faint small">{t("Google 검토를 받지 않은 앱으로 올린 영상은 YouTube 정책상 '비공개'로 고정될 수 있어요. 공개하려면 YouTube Studio 에서 바꾸거나 앱 검토를 받으세요.")}</p>
        </div>
      </>)}
    </div>
  );
};

/** 내 채널 영상 — Fluma 밖에서 올린 것도. 누르면 그 영상의 통계(요약 · 이탈 곡선 · 유입 경로 · 일별 · 시청자) */
const ChannelVideos: React.FC = () => {
  const { data: vids, error } = useQuery<ChannelVideo[]>({ queryKey: ["yt-videos"], staleTime: 60_000,
    queryFn: async ({ signal }) => { const r = await fetch("/api/youtube/videos", { signal }); const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`); return j; } });
  const [sel, setSel] = useState<ChannelVideo | null>(null);
  return (
    <div className="col">
      <div className="set-h"><div><h2>{t("내 채널 영상")}</h2><p>{t("누르면 통계를 봅니다. 분석 숫자는 게시 1~2일 뒤부터 채워져요.")}</p></div></div>
      {error && <p className="faint">{errMsg(error)}</p>}
      <div className="yt-vids">{(vids ?? []).map((v) => (
        <button key={v.videoId} className={`yt-vid ${sel?.videoId === v.videoId ? "on" : ""}`} onClick={() => setSel(sel?.videoId === v.videoId ? null : v)}>
          {v.thumb && <img src={v.thumb} alt="" referrerPolicy="no-referrer" />}
          <span><b>{v.title}</b><i>{new Date(v.published).toLocaleDateString()} · {t("조회 {n}", { n: v.views.toLocaleString() })} · {t("좋아요 {n}", { n: v.likes })} · {v.duration}{t("초")}</i></span>
        </button>))}</div>
      {sel && <div className="yt-stats-box"><StatsView key={sel.videoId} src={`/api/youtube/videos/${sel.videoId}/stats`}
        rec={{ videoId: sel.videoId, url: `https://youtube.com/shorts/${sel.videoId}`, uploaded_at: sel.published, privacy: sel.privacy, title: sel.title, file: "" }} /></div>}
    </div>
  );
};
