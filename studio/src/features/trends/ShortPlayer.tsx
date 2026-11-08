/* 앱 안 쇼츠 재생 — 분해한 쇼츠는 받아 둔 영상(<video>)으로, 아니면 유튜브 임베드(youtube-nocookie)로. 유튜브로 나가지 않는다.
   소리 켜고 끄기는 임베드를 다시 불러오지 않고 IFrame API 메시지로 */
import React, { forwardRef, useEffect, useRef, useState } from "react";
import { t } from "../../lib/i18n";

export interface ShortPlayerProps { vid: string; muted?: boolean; mini?: boolean; local?: boolean; controls?: boolean; autoPlay?: boolean; loop?: boolean; onTime?: (t: number) => void; onBlocked?: () => void }

export const ShortPlayer = forwardRef<HTMLVideoElement, ShortPlayerProps>(({ vid, muted = true, mini, local, controls = true, autoPlay = true, loop = true, onTime, onBlocked }, ref) => {
  const frame = useRef<HTMLIFrameElement>(null);
  const [blocked, setBlocked] = useState(false);
  // 유튜브가 외부 재생을 막은 영상(오류 101 · 150) · 없는 영상(100)은 IFrame API 오류로 알 수 있다
  useEffect(() => {
    if (local) return;
    const on = (e: MessageEvent) => {
      if (!/youtube(-nocookie)?\.com$/.test(new URL(e.origin).hostname) || e.source !== frame.current?.contentWindow) return;
      let d: { event?: string; info?: unknown }; try { d = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch { return; }
      if (d?.event === "onError" && [100, 101, 150, 2, 5].includes(Number(d.info))) { setBlocked(true); onBlocked?.(); }
    };
    window.addEventListener("message", on); return () => window.removeEventListener("message", on);
  }, [vid, local]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const w = frame.current?.contentWindow; if (!w) return;
    w.postMessage(JSON.stringify({ event: "command", func: muted ? "mute" : "unMute", args: [] }), "*");
    if (!muted) w.postMessage(JSON.stringify({ event: "command", func: "setVolume", args: [80] }), "*");
  }, [muted]);
  if (local) {
    return <video ref={ref} className={mini ? "sp mini" : "sp"} src={`/api/public/trends/xray/${vid}/src.mp4`} autoPlay={autoPlay} loop={loop} muted={muted} playsInline controls={controls && !mini}
      onTimeUpdate={onTime ? (e) => onTime(e.currentTarget.currentTime) : undefined} />;
  }
  const q = new URLSearchParams({ autoplay: "1", mute: muted ? "1" : "0", loop: "1", playlist: vid, playsinline: "1", rel: "0", modestbranding: "1",
    controls: mini ? "0" : "1", enablejsapi: "1", origin: window.location.origin });
  if (blocked) return <div className={mini ? "sp sp-blocked mini" : "sp sp-blocked"}><b>{t("유튜브가 외부 재생을 막은 쇼츠예요")}</b>{!mini && <span>{t("‘분해 시작’을 누르면 영상을 받아 앱 안에서 볼 수 있어요.")}</span>}</div>;
  return <iframe ref={frame} className={mini ? "sp mini" : "sp"} title={t("쇼츠 재생")} src={`https://www.youtube-nocookie.com/embed/${vid}?${q}`}
    allow="autoplay; encrypted-media; picture-in-picture" referrerPolicy="strict-origin-when-cross-origin"
    onLoad={(e) => e.currentTarget.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: vid, channel: "widget" }), "*")} />;
});
ShortPlayer.displayName = "ShortPlayer";
