/* 게시 · 성과 — 올리기(공식 업로드 API) 와 올린 뒤의 통계. 이탈 곡선을 콘티 장면에 겹쳐 '어느 장면에서 넘겼나'를 본다.
   분석 API 는 보통 1~2일 늦게 채워진다(실시간 숫자는 데이터 API). '시청 vs 스와이프'는 API 에 없어 Studio 링크로 */
import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Tag, cx } from "../../ui/kit";
import { Icon } from "../../ui/Icon";
import { errMsg } from "../../lib/api";
import { t } from "../../lib/i18n";
import type { Storyboard } from "../../lib/types";

type Rec = { videoId: string; url: string; uploaded_at: string; privacy: string; title: string; file: string };
type Info = { connected: boolean; channel: { title: string } | null; record: Rec | null; file: { name: string; draft: boolean; size: number } | null };
type Rep = { cols: string[]; rows: (string | number)[][]; error?: string };
type Stats = { none?: boolean; at: string; record: Rec; summary: Rep; retention: Rep; traffic: Rep; daily: Rep; demo: Rep; duration: number;
  live: { statistics?: Record<string, string>; status?: { privacyStatus?: string; uploadStatus?: string } } | null;
  scenes: { i: number; role: string; caption: string; from: number; to: number; start: number | null; end: number | null; drop: number | null }[] };

const n0 = (v: unknown) => (v == null || v === "" ? "—" : Number(v).toLocaleString());
const sec = (v: unknown) => (v == null ? "—" : `${Math.round(Number(v) * 10) / 10}${t("초")}`);
const pct = (v: unknown) => (v == null ? "—" : `${Math.round(Number(v) * 10) / 10}%`);
const row = (r: Rep) => Object.fromEntries((r.cols || []).map((c, i) => [c, r.rows?.[0]?.[i]]));
const TRAFFIC: Record<string, string> = { SHORTS: "쇼츠 피드", YT_SEARCH: "YouTube 검색", SUBSCRIBER: "구독 피드", BROWSE: "홈 · 탐색", RELATED_VIDEO: "추천 영상", EXT_URL: "외부", NOTIFICATION: "알림", YT_CHANNEL: "채널 페이지", PLAYLIST: "재생목록", NO_LINK_OTHER: "직접 · 기타", HASHTAGS: "해시태그", SOUND_PAGE: "사운드 페이지", YT_OTHER_PAGE: "기타 YouTube" };

export const PublishView: React.FC<{ projectId: string; sb: Storyboard }> = ({ projectId, sb }) => {
  const { data: info, refetch } = useQuery<Info>({ queryKey: ["yt-proj", projectId], refetchInterval: 4000,
    queryFn: async ({ signal }) => (await fetch(`/api/projects/${projectId}/youtube`, { signal })).json() });
  if (!info) return <div className="einfo faint">{t("불러오는 중…")}</div>;
  if (!info.connected) return (
    <div className="einfo"><h3><Icon n="video" s={18} />{t("YouTube 연결이 필요해요")}</h3>
      <p className="faint">{t("연결하면 여기서 바로 올리고, 올린 뒤 장면별 이탈 · 유입 경로 · 시청자 통계를 봅니다.")}</p>
      <div><Link className="btn btn-primary" to="/settings/youtube">{t("설정 → YouTube 에서 연결")}</Link></div></div>);
  return info.record ? <StatsView src={`/api/projects/${projectId}/youtube/stats`} rec={info.record} /> : <UploadForm projectId={projectId} sb={sb} info={info} onDone={() => refetch()} />;
};

const UploadForm: React.FC<{ projectId: string; sb: Storyboard; info: Info; onDone: () => void }> = ({ projectId, sb, info, onDone }) => {
  const [title, setTitle] = useState(sb.title ?? "");
  const [desc, setDesc] = useState(""), [tags, setTags] = useState(""), [privacy, setPrivacy] = useState("private"), [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      const r = await fetch(`/api/projects/${projectId}/youtube/upload`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, description: desc, tags: tags.split(/[,\s#]+/).filter(Boolean), privacy }) });
      const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`);
      toast.success(t("업로드를 시작했어요"), { description: t("끝나면 여기서 통계를 볼 수 있어요") });
      onDone();
    } catch (e) { toast.error(t("올리지 못했어요"), { description: errMsg(e) }); } finally { setBusy(false); }
  };
  return (
    <div className="einfo pub">
      <h3><Icon n="upload" s={18} />{t("YouTube 에 올리기")} <span className="faint small">· {info.channel?.title}</span></h3>
      <LinkExisting projectId={projectId} onDone={onDone} />
      {!info.file ? <p className="faint">{t("올릴 영상이 없어요 — 먼저 렌더해 주세요")}</p> : <>
        <p className="faint small">{t("파일")}: {info.file.name}{info.file.draft && <> · <Tag tone="warn">{t("초안")}</Tag> {t("최종 렌더가 없어 초안을 올립니다")}</>}</p>
        <label>{t("제목")}<input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>{t("설명")}<textarea rows={4} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t("출처 · 해시태그(#쇼츠 등 3개 정도)")} /></label>
        <label>{t("태그(쉼표로)")}<input value={tags} onChange={(e) => setTags(e.target.value)} /></label>
        <label>{t("공개 범위")}<select value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
          <option value="private">{t("비공개")}</option><option value="unlisted">{t("일부 공개")}</option><option value="public">{t("공개")}</option></select></label>
        <div><Button variant="primary" icon="upload" loading={busy} disabled={!title.trim()} onClick={go}>{t("올리기")}</Button></div>
      </>}
    </div>
  );
};

/** 통계 대시보드 — 콘티에 연결된 영상(장면별 이탈 포함) 또는 채널의 아무 영상(src 로 받을 주소만 다름) */
export const StatsView: React.FC<{ src: string; rec: Rec }> = ({ src, rec }) => {
  const [fresh, setFresh] = useState(0);
  const { data: s, isFetching, error } = useQuery<Stats>({ queryKey: ["yt-stats", src, fresh], staleTime: 60_000,
    queryFn: async ({ signal }) => { const r = await fetch(`${src}${fresh ? (src.includes("?") ? "&" : "?") + "fresh=1" : ""}`, { signal }); const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`); return j; } });
  const sum = s ? row(s.summary) : {};
  const live = s?.live?.statistics ?? {};
  const worst = useMemo(() => (s?.scenes ?? []).filter((x) => x.drop != null).sort((a, b) => (b.drop ?? 0) - (a.drop ?? 0))[0], [s]);
  const studio = `https://studio.youtube.com/video/${rec.videoId}/analytics/tab-overview/period-default`;
  const empty = s && !s.summary.rows.length;
  return (
    <div className="stats">
      <div className="st-head">
        <div><b>{rec.title}</b><span className="faint small">{new Date(rec.uploaded_at).toLocaleString()} · {s?.live?.status?.privacyStatus ?? rec.privacy}</span></div>
        <span className="grow" />
        <a className="btn btn-ghost" href={rec.url} target="_blank" rel="noreferrer"><Icon n="external" s={13} />{t("영상")}</a>
        <a className="btn btn-ghost" href={studio} target="_blank" rel="noreferrer"><Icon n="external" s={13} />{t("Studio 분석(시청 vs 스와이프)")}</a>
        <Button variant="secondary" icon="history" loading={isFetching} onClick={() => setFresh((x) => x + 1)}>{t("새로 받기")}</Button>
      </div>
      {error && <p className="st-err">{errMsg(error)}</p>}
      <div className="st-cards">
        <Card k={t("조회수(실시간)")} v={n0(live.viewCount)} />
        <Card k={t("좋아요(실시간)")} v={n0(live.likeCount)} />
        <Card k={t("댓글(실시간)")} v={n0(live.commentCount)} />
        <Card k={t("넘기지 않고 본 비율(추정)")} v={sum.views ? pct((Number(sum.engagedViews) / Number(sum.views)) * 100) : "—"} hint={t("참여 조회 ÷ 조회 — Studio 의 '시청 vs 스와이프'에 가까운 값")} strong />
        <Card k={t("참여 조회수")} v={n0(sum.engagedViews)} hint={t("첫 장면을 넘겨서 본 조회")} />
        <Card k={t("평균 시청 비율")} v={pct(sum.averageViewPercentage)} strong />
        <Card k={t("조회수(분석)")} v={n0(sum.views)} hint={t("분석 집계 기준(1~2일 늦음)")} />
        <Card k={t("평균 시청 시간")} v={sec(sum.averageViewDuration)} />
        <Card k={t("총 시청 시간")} v={`${n0(sum.estimatedMinutesWatched)}${t("분")}`} />
        <Card k={t("공유")} v={n0(sum.shares)} />
        <Card k={t("구독 증감")} v={sum.subscribersGained == null ? "—" : `+${n0(sum.subscribersGained)} / −${n0(sum.subscribersLost)}`} />
        <Card k={t("싫어요")} v={n0(sum.dislikes)} />
      </div>
      {empty && <p className="faint small">{t("분석 숫자는 보통 올린 뒤 1~2일 걸려 채워져요. 실시간 숫자는 바로 보입니다.")}</p>}

      <section className="st-sec">
        <h4>{(s?.scenes ?? []).length ? t("장면별 이탈") : t("이탈 곡선")} {worst && <span className="st-worst">{t("가장 많이 넘긴 곳: 장면 {n}", { n: worst.i + 1 })}</span>}</h4>
        <Retention s={s} />
        {!!(s?.scenes ?? []).length && <table className="st-table"><thead><tr><th>{t("장면")}</th><th>{t("자막")}</th><th>{t("시작 → 끝 남은 비율")}</th><th>{t("이 장면에서 넘김")}</th></tr></thead>
          <tbody>{(s?.scenes ?? []).map((x) => (
            <tr key={x.i} className={cx(worst?.i === x.i && "hot")}><td>{x.i + 1}</td><td>{x.caption?.replace(/\n/g, " / ")}</td>
              <td>{x.start == null ? "—" : `${Math.round(x.start * 100)}% → ${Math.round((x.end ?? 0) * 100)}%`}</td>
              <td>{x.drop == null ? "—" : `${Math.round(x.drop * 100)}%p`}</td></tr>))}</tbody></table>}
      </section>

      <div className="st-two">
        <section className="st-sec"><h4>{t("유입 경로")}</h4><Bars rows={(s?.traffic.rows ?? []).map((r) => [t(TRAFFIC[String(r[0])] ?? String(r[0])), Number(r[1])])} /></section>
        <section className="st-sec"><h4>{t("시청자 연령 · 성별")}</h4><Bars unit="%" rows={(s?.demo.rows ?? []).map((r) => [`${String(r[0]).replace("age", "")} · ${r[1] === "female" ? t("여") : r[1] === "male" ? t("남") : t("기타")}`, Number(r[2])])} /></section>
      </div>
      <section className="st-sec"><h4>{t("일별 조회")}</h4><Daily rows={s?.daily.rows ?? []} /></section>
      <p className="faint small">{t("‘시청 vs 스와이프’ 비율은 YouTube 가 API 로 주지 않아 Studio 에서만 볼 수 있어요.")} {s && `${t("받은 시각")} ${new Date(s.at).toLocaleTimeString()}`}</p>
    </div>
  );
};

const Card: React.FC<{ k: string; v: string; hint?: string; strong?: boolean }> = ({ k, v, hint, strong }) => (
  <div className={cx("st-card", strong && "strong")} title={hint}><span>{k}</span><b>{v}</b></div>
);
const Bars: React.FC<{ rows: [string, number][]; unit?: string }> = ({ rows, unit = "" }) => {
  if (!rows.length) return <p className="faint small">{t("아직 데이터가 없어요")}</p>;
  const max = Math.max(...rows.map((r) => r[1]), 1);
  return <div className="st-bars">{rows.slice(0, 8).map(([k, v]) => <div key={k}><span>{k}</span><i style={{ width: `${(v / max) * 100}%` }} /><b>{Math.round(v * 10) / 10}{unit}</b></div>)}</div>;
};
const Daily: React.FC<{ rows: (string | number)[][] }> = ({ rows }) => {
  if (!rows.length) return <p className="faint small">{t("아직 데이터가 없어요")}</p>;
  const max = Math.max(...rows.map((r) => Number(r[1])), 1), W = 600, H = 90;
  const pts = rows.map((r, i) => `${(i / Math.max(1, rows.length - 1)) * W},${H - (Number(r[1]) / max) * (H - 8)}`).join(" ");
  return <svg viewBox={`0 0 ${W} ${H}`} className="st-daily" preserveAspectRatio="none"><polyline points={pts} fill="none" stroke="var(--brand)" strokeWidth="2" /></svg>;
};
/** 이탈 곡선 + 장면 띠: x = 영상 진행(0~1), y = 남아 있는 시청자 비율. 점선 = 비슷한 길이 영상 대비 순위(0.5 = 보통, 높을수록 좋음) */
const Retention: React.FC<{ s?: Stats }> = ({ s }) => {
  const rows = s?.retention.rows ?? [];
  const W = 640, H = 200, P = 24;
  if (!rows.length) return <p className="faint small">{t("이탈 곡선은 조회가 쌓이면(보통 1~2일 뒤) 나타나요")}</p>;
  const ymax = Math.max(1, ...rows.map((r) => Number(r[1])));
  const X = (x: number) => P + x * (W - 2 * P), Y = (y: number) => H - P - (y / ymax) * (H - 2 * P);
  const line = rows.map((r) => `${X(Number(r[0]))},${Y(Number(r[1]))}`).join(" ");
  const rel = rows.map((r) => `${X(Number(r[0]))},${Y(Math.min(ymax, Number(r[2])))}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="st-ret">
      {(s?.scenes ?? []).map((x) => <g key={x.i}><rect x={X(x.from)} y={P} width={X(x.to) - X(x.from)} height={H - 2 * P} fill={x.i % 2 ? "rgba(255,255,255,.03)" : "rgba(255,255,255,.07)"} />
        <text x={X(x.from) + 4} y={P + 12} fontSize="10" fill="var(--tx-3)">{x.i + 1}</text></g>)}
      {[0.25, 0.5, 0.75, 1].map((g) => <g key={g}><line x1={P} x2={W - P} y1={Y(g)} y2={Y(g)} stroke="var(--line-2)" strokeDasharray="2 4" /><text x={2} y={Y(g) + 3} fontSize="9" fill="var(--tx-4)">{Math.round(g * 100)}%</text></g>)}
      <polyline points={rel} fill="none" stroke="var(--tx-3)" strokeWidth="1" strokeDasharray="4 3" />
      <polyline points={line} fill="none" stroke="var(--brand)" strokeWidth="2.2" />
    </svg>
  );
};

/** 이미 채널에 올린 영상을 이 콘티와 연결 — 그 영상의 이탈 곡선이 이 콘티의 장면에 겹친다 */
const LinkExisting: React.FC<{ projectId: string; onDone: () => void }> = ({ projectId, onDone }) => {
  const [open, setOpen] = useState(false);
  const { data: vids } = useQuery<ChannelVideo[]>({ queryKey: ["yt-videos"], enabled: open, queryFn: async ({ signal }) => (await fetch("/api/youtube/videos", { signal })).json() });
  const link = async (videoId: string) => {
    const r = await fetch(`/api/projects/${projectId}/youtube/link`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ videoId }) });
    const j = await r.json(); if (!r.ok) { toast.error(t("연결하지 못했어요"), { description: j?.error?.message }); return; }
    toast.success(t("이 영상과 연결했어요")); onDone();
  };
  return (
    <div className="pub-link">
      <button className="link-btn" onClick={() => setOpen((v) => !v)}><Icon n="link" s={13} />{t("이미 올린 영상이면 연결하기")}</button>
      {open && <div className="yt-vids">{!vids ? <span className="faint small">{t("불러오는 중…")}</span> : vids.map((v) => (
        <button key={v.videoId} className="yt-vid" onClick={() => link(v.videoId)}>{v.thumb && <img src={v.thumb} alt="" referrerPolicy="no-referrer" />}<span><b>{v.title}</b><i>{new Date(v.published).toLocaleDateString()} · {t("조회 {n}", { n: v.views.toLocaleString() })}</i></span></button>))}</div>}
    </div>
  );
};
export type ChannelVideo = { videoId: string; title: string; published: string; thumb?: string; duration: number; privacy: string; views: number; likes: number; comments: number };
