/* 첨부 — 홈 첫 입력창과 에이전트 입력창이 같은 코드를 쓴다.
   파일은 이 영상(프로젝트)의 uploads 로 올리고, 보낼 때 정확한 경로를 메시지에 붙인다 */
import React, { useRef, useState } from "react";
import { Icon } from "../../ui/Icon";
import { FlumaBounce } from "../../ui/BrandIcons";
import { IconButton, Menu, cx } from "../../ui/kit";
import { errMsg, uploadFile } from "../../lib/api";
import { qc, qk } from "../../lib/queries";
import { t } from "../../lib/i18n";

export interface Att { key: string; name: string; kind: "video" | "image" | "audio"; status: "up" | "ok" | "err"; rel?: string; seq?: string; thumb?: string; error?: string }

export function useAttachments(sessionId: string) {
  const [atts, setAtts] = useState<Att[]>([]);
  const attach = async (files: File[]) => {
    for (const f of files) {
      const key = `${f.name}-${f.size}-${Date.now()}`;
      setAtts((a) => [...a, { key, name: f.name, kind: f.type.startsWith("video") ? "video" : f.type.startsWith("audio") || /\.(mp3|m4a|wav|ogg|aac|flac)$/i.test(f.name) ? "audio" : "image", status: "up", thumb: f.type.startsWith("image") ? URL.createObjectURL(f) : undefined }]);
      try {
        const r = await uploadFile(sessionId, f) as { files: { name: string; kind: "image" | "video"; rel: string; seq?: string }[] };
        const hit = r.files.find((x) => x.name === f.name) ?? r.files.find((x) => x.name.endsWith(f.name.replace(/[^\w.가-힣-]/g, "_")));
        setAtts((a) => a.map((x) => (x.key === key ? { ...x, status: hit ? "ok" : "err", rel: hit?.rel, seq: hit?.seq, name: hit?.name ?? x.name } : x)));
        qc.invalidateQueries({ queryKey: qk.uploads(sessionId) });
      } catch (e) { setAtts((a) => a.map((x) => (x.key === key ? { ...x, status: "err", error: errMsg(e) } : x))); }
    }
  };
  const uploading = atts.some((a) => a.status === "up");
  const ready = atts.filter((a) => a.status === "ok" && a.rel);
  const remove = (key: string) => setAtts((x) => x.filter((y) => y.key !== key));
  const clear = () => setAtts([]);
  return { atts, attach, remove, clear, uploading, ready };
}

/** 메시지 앞에 붙는 첨부 안내 — 에이전트가 정확한 경로로 쓰게 */
export const attachNote = (ready: Att[]) => {
  return ready.length ? `[첨부 ${ready.length}개 — 이번 요청은 이 파일들로]\n${ready.map((a) => a.kind === "video"
      ? `- ${a.rel} (직접 찍은 영상 · 프레임: K.seq "${a.seq}" — 영상은 프레임으로 푸는 중일 수 있으니 meta.json 이 생긴 뒤에 쓴다)`
      : a.kind === "audio" ? `- ${a.rel} (배경음악 — 콘티 music: { "src": "public/${a.rel}" } · 시작 지점 start · 음량 gain_db)`
      : `- ${a.rel} (사진 · K.image)`).join("\n")}\n` : "";
};

export const AttachChips: React.FC<{ atts: Att[]; onRemove: (key: string) => void }> = ({ atts, onRemove }) => (
  <>
          {atts.map((a) => (
            <span key={a.key} className={cx("att-chip", a.status)} title={a.error ?? a.rel ?? a.name}>
              <span className="att-th">{a.thumb ? <img src={a.thumb} alt="" /> : <Icon n={a.kind === "video" ? "video" : a.kind === "audio" ? "volume" : "image"} s={13} />}</span>
              <span className="ellipsis">{a.name}</span>
              {a.status === "up" ? <FlumaBounce s={12} label={t("올리는 중")} /> : a.status === "err" ? <Icon n="warn" s={12} /> : null}
              <button aria-label={t("첨부 빼기")} onClick={() => onRemove(a.key)}><Icon n="close" s={11} /></button>
            </span>))}
  </>
);

export const AttachMenu: React.FC<{ attach: (f: File[]) => void }> = ({ attach }) => {
  const vidIn = useRef<HTMLInputElement>(null), imgIn = useRef<HTMLInputElement>(null), audIn = useRef<HTMLInputElement>(null);
  return <>
    <Menu side="top" align="start" trigger={<IconButton icon="plus" label={t("첨부")} size="sm" />} items={[
      { label: t("동영상 첨부"), icon: "video", onSelect: () => vidIn.current?.click() },
      { label: t("이미지 첨부"), icon: "image", onSelect: () => imgIn.current?.click() },
      { label: t("음악 첨부"), icon: "volume", onSelect: () => audIn.current?.click() },
    ]} />
            <input ref={vidIn} type="file" multiple accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.m4v" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
            <input ref={imgIn} type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
            <input ref={audIn} type="file" accept="audio/*,.mp3,.m4a,.wav,.ogg,.aac,.flac" hidden onChange={(e) => { const f = [...(e.target.files ?? [])]; e.target.value = ""; if (f.length) attach(f); }} />
  </>;
};
