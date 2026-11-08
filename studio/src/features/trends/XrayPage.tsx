/* 분해도(엑스레이) — 쇼츠 한 편을 편집 요소로 나눠 본다. 영상과 아래 트랙들이 같은 시각으로 움직인다.
   · 레이어 스택: 지금 샷을 원본 → 배경판 → 누끼 세 장의 카드로 펼침(로고의 겹친 카드)
   · 트랙: 샷 · 등장 요소 · 카메라 · 화면 글자 · 대사 · 음악/박 · 효과음 · 음량 — 어디든 누르면 그 시각으로
   누끼 · 배경판은 패턴 참고용이다. 우리 영상에 쓰지 않는다. */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Icon } from "../../ui/Icon";
import { FlumaBounce, FlumaStrain } from "../../ui/BrandIcons";
import { Button, EmptyState, IconButton, Popover, Segmented, Select, Skeleton, Tag, Tip, confirmDialog, cx } from "../../ui/kit";
import { toast } from "sonner";
import { errMsg } from "../../lib/api";
import { useProjects } from "../../lib/queries";
import { fmtViews } from "../../ui/engines";
import { typing } from "../../lib/ui";
import { t as tt } from "../../lib/i18n";
import { dropTrack, dropXray, segmentPreview, stageT, startTrack, startXray, useTracks, useTrendIndex, useXray, useXrayList, type Pt, type Track, type Xray } from "./data";
import { ShortPlayer } from "./ShortPlayer";

const fmt = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;

export const XrayPage: React.FC = () => {
  const { vid = "" } = useParams();
  const nav = useNavigate();
  const { data: idx } = useTrendIndex();
  const item = idx?.items.find((x) => x.id === vid);
  const { data: xl } = useXrayList();
  const run = xl?.running.find((r) => r.id === vid);
  const done = !!xl?.done.includes(vid);
  const { data: x, isLoading } = useXray(vid, done);

  return (
    <div className="page xray">
      <div className="pg-main">
        <header className="page-head">
          <span className="crumb"><Link to="/trends?v=feed">{tt("트렌드")}</Link><Icon n="chevron" s={12} /><b>{tt("분해도")}</b></span>
          <span className="xray-title ellipsis">{item?.title ?? vid}</span>
          {item && <span className="faint mono small">{fmtViews(item.views)}</span>}
          <span className="grow" />
          {x && <>
            <Button size="sm" variant="ghost" icon="undo" onClick={() => startXray(vid)} disabled={!!run}>{tt("다시 분해")}</Button>
            <Button size="sm" variant="ghost" icon="trash" onClick={async () => {
              if (await confirmDialog({ title: tt("받아 둔 영상과 분해 결과를 지울까요?"), body: tt("트렌드 목록의 쇼츠는 그대로 남습니다."), ok: tt("지우기"), danger: true })) { await dropXray(vid); nav("/trends?v=feed"); }
            }}>{tt("지우기")}</Button>
            <ToGraph vid={vid} />
            <Button size="sm" variant="primary" icon="sparkle" onClick={() => nav("/?prefill=" + encodeURIComponent(brief(x, item?.title)))}>{tt("이 구조로 만들기")}</Button>
          </>}
        </header>
        {run ? (
          <div className="xray-wait"><FlumaStrain s={40} /><b>{stageT(run.stage)}</b><div className="xray-bar"><i style={{ width: `${Math.round((run.progress ?? 0) * 100)}%` }} /></div><span className="faint small">{tt("영상을 받아 샷 · 누끼 · 소리를 나누는 중입니다. 1~2분 걸려요.")}</span></div>
        ) : !done ? (
          <EmptyState icon="layers" title={tt("아직 분해하지 않은 쇼츠예요")} body={tt("영상을 저화질로 받아 샷 · 피사체 누끼 · 배경판 · 화면 글자 · 대사 · 박자 · 효과음으로 나눕니다.")}
            action={<Button variant="primary" icon="layers" onClick={() => startXray(vid)}>{tt("분해 시작")}</Button>} />
        ) : isLoading || !x ? <div className="xray-wait"><Skeleton w={320} h={420} r={16} /></div> : <XrayView x={x} />}
      </div>
    </div>
  );
};

/** 에이전트에게 넘길 구조 요약 (베끼지 않고 리듬 · 배치만) */
function brief(x: Xray, title?: string) {
  const shots = x.shots.map((s) => tt("{a}~{b}초", { a: s.start, b: s.end }) + " " + tt(s.camera?.kind ?? "고정") + (s.subject.area > 0.02 ? " · " + tt("피사체 {p}%", { p: Math.round(s.subject.area * 100) }) : "")).join(" / ");
  return tt("트렌드 쇼츠 “{title}”의 편집 구조를 참고해서(내용 · 그림은 베끼지 말고 리듬 · 배치 · 소리 쓰는 법만) 내 주제로 만들어 줘.", { title: title ?? x.id }) + "\n" +
    tt("구조: {v}", { v: x.recipe.join(" · ") }) + "\n" + tt("샷: {v}", { v: shots }) + "\n" + tt("내 주제: ");
}

const XrayView: React.FC<{ x: Xray }> = ({ x }) => {
  const video = useRef<HTMLVideoElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);
  // 아래 트랙 높이를 재서 위 영역이 남은 높이에 꼭 맞게 (창을 줄여도 트랙이 플레이어를 덮지 않음)
  useEffect(() => {
    const el = root.current, tk = el?.querySelector<HTMLElement>(".tracks"); if (!el || !tk) return;
    const ro = new ResizeObserver(() => el.style.setProperty("--tk-h", `${tk.offsetHeight}px`)); ro.observe(tk); return () => ro.disconnect();
  }, []);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  // 소리: 원본 / 목소리만 / 음악 · 효과음만 (분해 때 나눈 트랙을 영상 시각에 맞춰 재생)
  const [stem, setStem] = useState<"mix" | "vocals" | "music">("mix");
  const audio = useRef<HTMLAudioElement>(null);
  const [picking, setPicking] = useState(false);   // 개체 따라 누끼: 영상에서 개체를 찍는 중
  // 찍은 점: 클릭 = 포함, Shift+클릭 = 빼기(개체에 붙어 같이 잡히는 책상 · 모니터 등). 찍을 때마다 한 프레임 미리보기
  const [pts, setPts] = useState<{ x: number; y: number; neg: boolean }[]>([]);
  const [prev, setPrev] = useState<{ url?: string; busy: boolean; error?: string; t: number } | null>(null);
  const endPick = () => { setPicking(false); setPts([]); setPrev(null); };
  const preview = async (list: typeof pts, at: number) => {
    const pos = list.filter((q) => !q.neg).map((q) => [q.x, q.y] as Pt), neg = list.filter((q) => q.neg).map((q) => [q.x, q.y] as Pt);
    if (!pos.length) { setPrev(null); return; }
    setPrev((p) => ({ ...(p ?? {}), busy: true, t: at }));
    const r = await segmentPreview(x.id, at, pos, neg);
    setPrev({ url: r.url, error: r.error, busy: false, t: at });
  };
  const beginTrack = () => {
    const pos = pts.filter((q) => !q.neg), neg = pts.filter((q) => q.neg);
    if (!pos.length || !prev) return;
    startTrack(x.id, +prev.t.toFixed(2), +pos[0].x.toFixed(4), +pos[0].y.toFixed(4), pos.slice(1).map((q) => [q.x, q.y] as Pt), neg.map((q) => [q.x, q.y] as Pt));
    endPick();
  };
  const [showTrack, setShowTrack] = useState<string | null>(null);
  const { data: tr } = useTracks(x.id);
  const tracks = tr?.tracks ?? [];
  const [over, setOver] = useState<Set<string>>(() => new Set(["text", "subject"]));
  const [spread, setSpread] = useState(true);
  const dur = x.video.duration;
  // 재생 시각을 화면 갱신마다 읽는다 (timeupdate 보다 부드럽게)
  useEffect(() => { let h = 0; const tick = () => {
    const v = video.current; if (v) setT(v.currentTime);
    const au = audio.current;   // 나눈 트랙을 영상에 맞춤(0.12초 넘게 어긋나면 당김)
    if (v && au && au.src) { if (Math.abs(au.currentTime - v.currentTime) > 0.12) au.currentTime = v.currentTime; if (v.paused !== au.paused) { if (v.paused) au.pause(); else au.play().catch(() => {}); } }
    h = requestAnimationFrame(tick); }; h = requestAnimationFrame(tick); return () => cancelAnimationFrame(h); }, []);
  const seek = (s: number) => { const v = video.current; if (v) { v.currentTime = Math.max(0, Math.min(dur - 0.05, s)); } };
  const toggle = () => { const v = video.current; if (!v) return; if (v.paused) v.play(); else v.pause(); };
  const stepShot = (d: 1 | -1) => {
    const v = video.current; if (!v) return; v.pause();
    if (d > 0) { const n = x.shots.find((s) => s.start > v.currentTime + 0.01); if (n) seek(n.start + 0.01); }
    else { const p = [...x.shots].reverse().find((s) => s.start < v.currentTime - 0.3); seek(p ? p.start + 0.01 : 0); }
  };
  // 재생 상태는 영상 이벤트로만 (버튼 아이콘이 실제 상태와 어긋나지 않게)
  useEffect(() => {
    const v = video.current; if (!v) return;
    const on = () => setPlaying(!v.paused);
    v.addEventListener("play", on); v.addEventListener("pause", on); v.addEventListener("ended", on);
    return () => { v.removeEventListener("play", on); v.removeEventListener("pause", on); v.removeEventListener("ended", on); };
  }, []);
  const onFrameClick = (e: React.MouseEvent) => {
    if (!picking) { toggle(); return; }
    const r = e.currentTarget.getBoundingClientRect();
    const px = +((e.clientX - r.left) / r.width).toFixed(4), py = +((e.clientY - r.top) / r.height).toFixed(4);
    video.current?.pause();
    const at = prev?.t ?? t;   // 점은 모두 같은 프레임에 — 처음 찍은 시각
    const next = [...pts, { x: px, y: py, neg: e.shiftKey || e.altKey }];
    setPts(next); preview(next, at);
  };
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (typing(e)) return;
      // 버튼에 포커스가 있을 때 스페이스는 버튼 클릭으로도 들어온다 → 여기서 또 처리하면 멈췄다 바로 다시 재생됨
      if ((e.target as HTMLElement | null)?.closest?.("button, [role=button]")) { if (e.key === " ") e.preventDefault(); if (e.key === " ") toggle(); return; }
      const v = video.current; if (!v) return;
      if (e.key === " ") { e.preventDefault(); toggle(); }
      if (e.key === "Escape") endPick();
      if (e.key === "ArrowRight") seek(v.currentTime + (e.shiftKey ? 1 : 1 / 30));
      if (e.key === "ArrowLeft") seek(v.currentTime - (e.shiftKey ? 1 : 1 / 30));
      if (e.key === "]") stepShot(1);
      if (e.key === "[") stepShot(-1);
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  });
  const shot = x.shots.find((s) => t >= s.start && t < s.end) ?? x.shots[x.shots.length - 1];
  const textNow = x.text.filter((e) => t >= e.start && t < e.end);
  const sayNow = x.speech.find((s) => t >= s.start && t <= s.end);
  const beatNow = !!x.sound.beats?.some((b) => Math.abs(b - t) < 0.06);
  const toggleOv = (k: string) => setOver((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const trk = tracks.find((k) => k.id === showTrack) ?? null;
  const trBox = trk && t >= trk.from && t <= trk.to ? trk.boxes.reduce<Track["boxes"][number] | null>((b, c) => (Math.abs(c[0] - t) < Math.abs((b?.[0] ?? 1e9) - t) ? c : b), null) : null;

  return (
    <div className="xv" ref={root}>
      <div className="xv-top">
        {/* 영상 + 겹쳐 보기 */}
        <section className="xv-player">
          <div ref={frameRef} className={cx("xv-frame", beatNow && over.has("beat") && "beat", picking && "picking")} style={{ aspectRatio: `${x.video.w} / ${x.video.h}` }} onClick={onFrameClick}>
            <ShortPlayer ref={video} vid={x.id} local muted={muted || stem !== "mix"} controls={false} autoPlay={false} loop={false} />
            {x.stems && stem !== "mix" && <audio ref={audio} src={`/api/public/${x.stems[stem]}`} muted={muted} preload="auto" />}
            {trk && <svg className="ov-path" viewBox="0 0 1 1" preserveAspectRatio="none"><polyline points={trk.path.map((p) => `${p[1]},${p[2]}`).join(" ")} /></svg>}
            {trBox && <i className="ov-box track" style={box(trBox.slice(1))}><span>{tt("추적")}</span></i>}
            {picking && prev?.url && <img className="ov-seg" src={prev.url} alt="" />}
            {picking && pts.map((q, i) => <i key={i} className={cx("ov-pt", q.neg && "neg")} style={{ left: `${q.x * 100}%`, top: `${q.y * 100}%` }}>{q.neg ? "−" : "+"}</i>)}
            {picking && <div className="ov-pick">{!pts.length ? tt("따라갈 개체를 누르세요 · Esc 취소") : prev?.busy ? tt("잘라 보는 중…") : prev?.error ? prev.error : tt("맞으면 ‘따라가기’ · 더 넣을 곳 클릭 · 뺄 곳 Shift+클릭")}</div>}
            {!playing && !picking && t < 0.05 && <div className="ov-play"><Icon n="play" s={28} /></div>}
            {over.has("text") && textNow.map((e, k) => <i key={k} className="ov-box text" style={box(e.box)}><span>{tt("글자")} · {tt(e.band)}</span></i>)}
            {over.has("subject") && shot?.subject.bbox && <i className="ov-box subj" style={box(shot.subject.bbox)}><span>{tt("피사체")}{shot.subject.group ? ` ${shot.subject.group}` : ""}</span></i>}
            {over.has("speech") && sayNow && <div className="ov-say">{sayNow.text}</div>}
          </div>
          <div className="xv-ctl">
            <IconButton icon="skipBack" label={tt("이전 샷 ([)")} onClick={() => stepShot(-1)} />
            <IconButton icon={playing ? "pause" : "play"} label={tt("재생 / 멈춤 (Space)")} onClick={toggle} />
            <IconButton icon="skipFwd" label={tt("다음 샷 (])")} onClick={() => stepShot(1)} />
            <span className="mono">{fmt(t)} / {fmt(dur)}</span>
            <IconButton icon={muted ? "mute" : "volume"} label={muted ? tt("소리 켜기") : tt("소리 끄기")} onClick={() => setMuted(!muted)} />
            {x.stems && <Segmented aria-label={tt("들을 소리")} size="sm" value={stem} onChange={(v) => setStem(v as typeof stem)}
              options={[{ value: "mix", label: tt("원본") }, { value: "vocals", label: tt("목소리") }, { value: "music", label: tt("음악 · 효과음") }]} />}
          </div>
          <div className="xv-ctl">
            {[["text", "글자"], ["subject", "피사체"], ["speech", "대사"], ["beat", "박"]].map(([k, l]) => (
              <button key={k} className={cx("ov-t", over.has(k) && "on")} aria-pressed={over.has(k)} onClick={() => toggleOv(k)}>{tt(l)}</button>))}
            <span className="grow" />
            {!picking ? <Button size="sm" variant="secondary" icon="cursor" onClick={() => { video.current?.pause(); setPicking(true); }}>{tt("개체 따라 누끼")}</Button> : <>
              <span className="faint small">{tt("포함 {a} · 빼기 {b}", { a: pts.filter((q) => !q.neg).length, b: pts.filter((q) => q.neg).length })}</span>
              <IconButton icon="undo" label={tt("마지막 점 지우기")} size="sm" disabled={!pts.length} onClick={() => { const n = pts.slice(0, -1); setPts(n); preview(n, prev?.t ?? t); }} />
              <Button size="sm" variant="ghost" onClick={endPick}>{tt("취소")}</Button>
              <Button size="sm" variant="primary" icon="play" disabled={!prev?.url || prev.busy} onClick={beginTrack}>{tt("따라가기")}</Button>
            </>}
          </div>
        </section>

        {/* 지금 샷의 레이어 스택 */}
        <section className="xv-stack" aria-label={tt("지금 샷의 레이어")}>
          <div className="xv-stack-h">
            <b>{tt("샷 {n}", { n: shot.i + 1 })}</b><span className="faint mono">{tt("{a}~{b}초", { a: shot.start, b: shot.end })}</span>
            <Tag tone="select">{tt(shot.camera?.kind ?? "고정")}</Tag>
            {shot.subject.group && <Tag tone="brand">{tt("요소 {g}", { g: shot.subject.group })}</Tag>}
            {!!shot.subject.faces && <Tag tone="warn">{tt("실사 얼굴 {n}", { n: shot.subject.faces })}</Tag>}
            <span className="grow" />
            <Segmented aria-label={tt("레이어 보기")} size="sm" value={spread ? "spread" : "stack"} onChange={(v) => setSpread(v === "spread")} options={[{ value: "spread", label: tt("펼치기") }, { value: "stack", label: tt("겹치기") }]} />
          </div>
          <div className={cx("lstack", spread && "spread")}>
            <figure className="xlc l0"><img src={`/api/public/${shot.frame}`} alt="" /><figcaption>{tt("원본")}</figcaption></figure>
            {shot.subject.bg && <figure className="xlc l1"><img src={`/api/public/${shot.subject.bg}`} alt="" /><figcaption>{tt("배경판")} <span>{tt("(추정)")}</span></figcaption></figure>}
            {shot.subject.cut && <figure className="xlc l2 cut"><img src={`/api/public/${shot.subject.cut}`} alt="" style={shot.subject.bbox ? { left: `${shot.subject.bbox[0] * 100}%`, top: `${shot.subject.bbox[1] * 100}%`, width: `${shot.subject.bbox[2] * 100}%` } : undefined} /><figcaption>{tt("피사체 누끼 · {p}%", { p: Math.round(shot.subject.area * 100) })}</figcaption></figure>}
          </div>
          <div className="xv-pal">{shot.palette.map((p) => <i key={p.hex} style={{ background: p.hex, flex: p.w }} title={p.hex} />)}</div>
          <p className="faint small">{tt("누끼 · 배경판은 구성을 읽기 위한 참고용이에요. 우리 영상에 쓰지 않습니다.")}</p>
        </section>

        {/* 레시피 · 등장 요소 · 대사 */}
        <section className="xv-side">
          <p className="xv-guide">{tt("멈추고 [ ] 로 샷을 넘기며 각 샷이 무엇으로 이루어졌는지 보세요. ‘개체 따라 누끼’로 캐릭터 하나의 움직임을 샷 전체에서 뽑을 수 있어요.")}</p>
          {(tracks.length > 0 || !!tr?.running.length) && <>
            <h4>{tt("따라 뽑은 개체")}</h4>
            {tr?.running.map((r) => <div key={r.jobId} className="trk run"><FlumaStrain s={16} /><span className="grow">{stageT(r.stage)}</span><span className="mono faint">{Math.round((r.progress ?? 0) * 100)}%</span></div>)}
            {tracks.map((k) => (
              <div key={k.id} className={cx("trk", showTrack === k.id && "on")}>
                <video className="trk-v" src={`/api/public/${k.preview}`} autoPlay loop muted playsInline />
                <div className="trk-i">
                  <b className="mono">{tt("{a}~{b}초", { a: k.from.toFixed(1), b: k.to.toFixed(1) })}</b>
                  <span className="faint small">{tt("{n}프레임", { n: k.frames })}{k.motion ? " · " + tt("이동 {p}% · 크기 ×{s}", { p: Math.round(k.motion.travel * 100), s: k.motion.scale }) : ""}</span>
                  <span className="row">
                    <Button size="sm" variant="ghost" icon="play" onClick={() => { setShowTrack(k.id); seek(k.from); video.current?.play(); }}>{tt("구간 재생")}</Button>
                    <Button size="sm" variant="ghost" icon={showTrack === k.id ? "eyeOff" : "eye"} onClick={() => setShowTrack(showTrack === k.id ? null : k.id)}>{tt("궤적")}</Button>
                    <IconButton icon="trash" label={tt("지우기")} size="sm" onClick={() => { if (showTrack === k.id) setShowTrack(null); dropTrack(x.id, k.id); }} />
                  </span>
                </div>
              </div>))}
          </>}
          <h4>{tt("편집 레시피")}</h4>
          <ul className="recipe">{x.recipe.map((r, k) => <li key={k}>{r}</li>)}</ul>
          {x.subjects.length > 0 && <>
            <h4>{tt("등장 요소")} <span className="faint">{tt("누끼 색 분포로 묶음")}</span></h4>
            <div className="subj">{x.subjects.map((g) => (
              <Tip key={g.id} label={tt("샷 {n}", { n: g.shots.map((n) => n + 1).join(", ") })}>
                <button className={cx("subj-c", shot.subject.group === g.id && "on")} onClick={() => seek(x.shots[g.shots[0]].start + 0.01)}>
                  {g.cover ? <img src={`/api/public/${g.cover}`} alt="" /> : <span />}<b>{g.id}</b><em>{g.shots.length}</em>
                </button>
              </Tip>))}</div>
          </>}
          {x.speech.length > 0 && <>
            <h4>{tt("대사")}</h4>
            <div className="script">{x.speech.map((s, k) => (
              <button key={k} className={cx("script-r", t >= s.start && t <= s.end && "on")} onClick={() => seek(s.start)}><span className="mono faint">{s.start.toFixed(1)}</span>{s.text}</button>))}</div>
          </>}
        </section>
      </div>
      <Tracks x={x} t={t} seek={seek} />
    </div>
  );
};

const box = (b: number[]): React.CSSProperties => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${b[2] * 100}%`, height: `${b[3] * 100}%` });

/* ---------- 트랙 ---------- */
const Tracks: React.FC<{ x: Xray; t: number; seek: (s: number) => void }> = ({ x, t, seek }) => {
  const dur = x.video.duration;
  const area = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);   // 트랙 폭(px) — 블럭이 글자를 담을 만큼 넓을 때만 글자를 쓴다
  useEffect(() => { const el = area.current; if (!el) return; const ro = new ResizeObserver(() => setW(el.clientWidth)); ro.observe(el); setW(el.clientWidth); return () => ro.disconnect(); }, []);
  const env = x.sound.envelope ?? [];
  const envPath = useMemo(() => env.length ? "M0,1 " + env.map((v, k) => `L${(k / (env.length - 1)).toFixed(4)},${(1 - v).toFixed(3)}`).join(" ") + " L1,1 Z" : "", [env]);
  const onDown = (e: React.PointerEvent) => {
    const el = area.current; if (!el) return;
    const go = (cx: number) => { const r = el.getBoundingClientRect(); seek(Math.max(0, Math.min(1, (cx - r.left) / r.width)) * dur); };
    go(e.clientX);
    const mv = (ev: PointerEvent) => go(ev.clientX);
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  };
  const step = dur / Math.max(1, w / 70) > 5 ? 10 : 5;   // 눈금 글자끼리 붙지 않게
  const ticks = Array.from({ length: Math.floor(dur / step) + 1 }, (_, k) => k * step);
  const cams = x.shots.filter((s) => s.camera && s.camera.kind !== "고정").map((s) => ({ start: s.start, end: s.end, label: tt(s.camera!.kind), tip: `${tt("샷 {n}", { n: s.i + 1 })} · ${tt(s.camera!.kind)}` }));
  const texts = x.text.map((e) => ({ start: e.start, end: e.end, label: tt(e.band), tip: `${tt("화면 글자")} · ${tt(e.band)} · ${tt("{a}~{b}초", { a: e.start, b: e.end })}` }));
  const says = x.speech.map((s) => ({ start: s.start, end: Math.max(s.end, s.start + 0.2), label: s.text, tip: `${tt("{n}초", { n: s.start.toFixed(1) })} · ${s.text}` }));
  const subs = x.shots.filter((s) => s.subject.group).map((s) => ({ start: s.start, end: s.end, label: s.subject.group!, tip: `${tt("샷 {n}", { n: s.i + 1 })} · ${tt("요소 {g}", { g: s.subject.group! })}`, cls: `g${"ABCDEFGH".indexOf(s.subject.group!) % 6}` }));
  return (
    <div className="tracks" onPointerDown={onDown}>
      <Row label="" cls="ruler">{ticks.map((s) => <span key={s} className={s / dur > 0.97 ? "end" : undefined} style={{ left: pc(s, dur) }}>{s}s</span>)}</Row>
      <Row label={tt("샷")} cls="shots">{x.shots.map((s) => (
        <div key={s.i} className={cx("tk-shot", t >= s.start && t < s.end && "on")} style={{ left: pc(s.start, dur), width: pc(s.end - s.start, dur) }} title={`${tt("샷 {n}", { n: s.i + 1 })} · ${tt("{a}~{b}초", { a: s.start, b: s.end })}`}>
          <img src={`/api/public/${s.frame}`} alt="" />{((s.end - s.start) / dur) * w >= 18 && <span className="mono">{s.i + 1}</span>}
        </div>))}</Row>
      <Lanes label={tt("요소")} items={subs} dur={dur} w={w} kind="chip" />
      <Lanes label={tt("카메라")} items={cams} dur={dur} w={w} kind="cam" />
      <Lanes label={tt("화면 글자")} items={texts} dur={dur} w={w} kind="txt" />
      <Lanes label={tt("대사")} items={says} dur={dur} w={w} kind="say" />
      <Row label={x.sound.bpm ? tt("음악 {bpm}", { bpm: Math.round(x.sound.bpm) }) : tt("음악 · 박")} cls="music">
        {(x.sound.music ?? []).map((m, k) => m ? <i key={k} className="mus" style={{ left: pc(k, dur), width: pc(1, dur) }} /> : null)}
        {(x.sound.beats ?? []).map((b, k) => <b key={k} className="beat" style={{ left: pc(b, dur) }} />)}
      </Row>
      <Row label={tt("효과음")} cls="sfx">{(x.sound.sfx ?? []).map((s, k) => (
        <i key={k} title={`${tt("{n}초", { n: s.t })} · ${tt(s.kind)}`} className={cx("sfx-m", s.kind.startsWith("고음") ? "hi" : s.kind.startsWith("저음") ? "lo" : "mid")} style={{ left: pc(s.t, dur) }} />))}</Row>
      <Row label={tt("음량")} cls="env">{envPath && <svg viewBox="0 0 1 1" preserveAspectRatio="none"><path d={envPath} /></svg>}</Row>
      <div className="tk-area" ref={area} aria-hidden><div className="tk-head" style={{ left: pc(t, dur) }} /></div>
    </div>
  );
};
const pc = (s: number, dur: number) => `${(s / dur) * 100}%`;
const Row: React.FC<{ label: string; cls: string; h?: number; children?: React.ReactNode }> = ({ label, cls, h, children }) => (
  <div className="tk-row" style={h ? { height: h } : undefined}><span className="tk-l">{label}</span><div className={cx("tk", cls)}>{children}</div></div>
);
/** 시간이 겹치는 블럭은 줄을 나눠 쌓는다(최대 3줄). 블럭이 좁으면 글자는 숨기고 마우스를 올리면 보인다 */
const Lanes: React.FC<{ label: string; items: { start: number; end: number; label: string; tip: string; cls?: string }[]; dur: number; w: number; kind: "chip" | "cam" | "txt" | "say" }> = ({ label, items, dur, w, kind }) => {
  const placed = useMemo(() => {
    const ends: number[] = [];
    return [...items].sort((a, b) => a.start - b.start).map((it) => {
      let lane = ends.findIndex((e) => e <= it.start + 0.01);
      if (lane < 0) { lane = Math.min(ends.length, 2); }
      ends[lane] = Math.max(ends[lane] ?? 0, it.end);
      return { ...it, lane };
    });
  }, [items]);
  const lanes = Math.max(1, ...placed.map((p) => p.lane + 1));
  const lh = lanes === 1 ? 26 : 19;
  return (
    <Row label={label} cls={`lanes ${kind}`} h={lanes * lh + 4}>
      {placed.map((p, k) => {
        const px = ((p.end - p.start) / dur) * w;
        return (
          <div key={k} className={cx("tk-blk", kind, p.cls)} title={p.tip}
            style={{ left: pc(p.start, dur), width: pc(p.end - p.start, dur), top: 2 + p.lane * lh, height: lh - 4 }}>
            {px >= (kind === "chip" ? 16 : 44) && <span>{p.label}</span>}
          </div>
        );
      })}
    </Row>
  );
};

/** 이 분해도의 형식(샷 리듬 · 주인공 자리 · 글자 자리 · 카메라)을 내 영상 설계도로. 미리 보고 넣는다 */
const ToGraph: React.FC<{ vid: string }> = ({ vid }) => {
  const { data: projects = [] } = useProjects();
  const nav = useNavigate();
  const [pick, setPick] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const call = async (apply: boolean) => {
    setBusy(true);
    try {
      const r = await fetch(`/api/trends/xray/${vid}/to-graph`, { method: "POST", headers: { "content-type": "application/json", "x-fluma-client": "ui" }, body: JSON.stringify({ project: pick, apply }) });
      const d = await r.json(); if (!r.ok) throw new Error(d?.error?.message ?? tt("실패"));
      if (!apply) setPreview(d.log);
      else { toast.success(tt("설계도에 넣었어요"), { description: tt("편집기에서 S(스케치)로 애니메틱을 보세요. 참고 그림 자리는 최종 렌더 전에 직접 만든 화면으로 바꿔야 합니다.") }); setPreview(null); nav(`/p/${pick}`); }
    } catch (e) { toast.error(tt("옮기지 못했어요"), { description: errMsg(e) }); } finally { setBusy(false); }
  };
  return (
    <Popover trigger={<Button size="sm" variant="secondary" icon="layers">{tt("내 영상 설계도로")}</Button>}>
      <div className="col" style={{ width: 340, gap: 8 }}>
        <b>{tt("형식만 내 영상으로 옮기기")}</b>
        <span className="faint small">{tt("샷 리듬 · 주인공 자리 · 글자 자리 · 카메라 움직임을 내 영상 길이에 맞춰 넣습니다. 원본 그림 · 말 · 글은 옮기지 않고, 참고 그림은 구도 확인용(최종 렌더에서 막힘)입니다.")}</span>
        <Select aria-label={tt("넣을 영상")} value={pick} onChange={(v) => { setPick(v); setPreview(null); }} options={[{ value: "", label: tt("넣을 영상 고르기") }, ...projects.map((p) => ({ value: p.id, label: p.title || p.id }))]} />
        {preview && <pre className="xg-preview">{preview}</pre>}
        <div className="row end">
          <Button size="sm" disabled={!pick} loading={busy && !preview} onClick={() => call(false)}>{tt("미리 보기")}</Button>
          <Button size="sm" variant="primary" disabled={!pick || !preview} loading={busy && !!preview} onClick={() => call(true)}>{tt("넣기")}</Button>
        </div>
      </div>
    </Popover>
  );
};
