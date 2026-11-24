/* 연결한 YouTube 채널(계정) — 설정 · 채팅창 · 게시 화면이 같이 쓰는 조회 · 고르기. 토큰은 서버에만 있고 여기엔 이름 · 아이콘만 온다 */
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { qc } from "../../lib/queries";
import type { YtAccount, YtProjectAccount, YtStatus } from "../../lib/types";

export const useYoutube = () => useQuery<YtStatus>({ queryKey: ["youtube"], staleTime: 30_000, queryFn: async ({ signal }) => (await fetch("/api/youtube", { signal })).json() });

/** 이 영상(프로젝트)을 올릴 채널 — 채팅창 · 게시 화면이 같이 쓴다. 작업 공간 대화(_로 시작)는 없음 */
export const useProjectYtAccount = (projectId: string | null | undefined) => useQuery<YtProjectAccount>({
  queryKey: ["yt-account", projectId], enabled: !!projectId && !projectId.startsWith("_"), staleTime: 30_000,
  queryFn: async ({ signal }) => { const r = await fetch(`/api/projects/${projectId}/youtube-account`, { signal }); const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`); return j; } });
export async function setProjectYtAccount(projectId: string, id: string | null) {
  const r = await fetch(`/api/projects/${projectId}/youtube-account`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
  const j = await r.json(); if (!r.ok) throw new Error(j?.error?.message ?? `HTTP ${r.status}`);
  qc.setQueryData(["yt-account", projectId], j); qc.invalidateQueries({ queryKey: ["yt-proj", projectId] });
  return j as YtProjectAccount;
}
/** 채널 아이콘(없으면 첫 글자) */
export const YtAvatar: React.FC<{ a: Pick<YtAccount, "title" | "thumb"> | null | undefined; s?: number }> = ({ a, s = 20 }) =>
  a?.thumb ? <img className="yt-av" src={a.thumb} alt="" width={s} height={s} style={{ width: s, height: s }} />
    : <span className="yt-av yt-av-x" style={{ width: s, height: s, fontSize: Math.round(s * 0.5) }}>{(a?.title ?? "?").slice(0, 1)}</span>;

