/* 공통 UI 부품. 화면 코드는 여기 부품만 쓴다(직접 스타일 금지 → 일관성).
   접근성: 아이콘만 있는 버튼은 label 필수(aria-label + 툴팁), 대화상자는 초점 가둠(Radix). */
import React, { forwardRef, useEffect, useId, useRef, useState } from "react";
import * as RTooltip from "@radix-ui/react-tooltip";
import * as RDialog from "@radix-ui/react-dialog";
import * as RMenu from "@radix-ui/react-dropdown-menu";
import * as RPopover from "@radix-ui/react-popover";
import { Icon } from "./Icon";
import { t as tr } from "../lib/i18n";

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");
export { cx };

/* ---------- 단축키 표시 ---------- */
export const Kbd: React.FC<{ k: string }> = ({ k }) => (
  <span className="kbd-g">{k.split("+").map((x, i) => <kbd key={i}>{x === "Mod" ? (navigator.platform.includes("Mac") ? "⌘" : "Ctrl") : x}</kbd>)}</span>
);

/* ---------- 툴팁 ---------- */
export const Tip: React.FC<{ label: React.ReactNode; kbd?: string; side?: "top" | "bottom" | "left" | "right"; children: React.ReactElement }> = ({ label, kbd, side = "bottom", children }) => (
  <RTooltip.Root delayDuration={350}>
    <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
    <RTooltip.Portal>
      <RTooltip.Content className="tip" side={side} sideOffset={6} collisionPadding={8}>
        {label}{kbd && <Kbd k={kbd} />}
      </RTooltip.Content>
    </RTooltip.Portal>
  </RTooltip.Root>
);

/* ---------- 버튼 ---------- */
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "agent";
  size?: "sm" | "md" | "lg"; icon?: string; iconRight?: string; loading?: boolean; block?: boolean;
};
export const Button = forwardRef<HTMLButtonElement, BtnProps>(({ variant = "secondary", size = "md", icon, iconRight, loading, block, className, children, disabled, ...rest }, ref) => (
  <button ref={ref} className={cx("btn", `btn-${variant}`, `btn-${size}`, block && "btn-block", loading && "is-loading", className)} disabled={disabled || loading} {...rest}>
    {loading ? <Spinner s={size === "lg" ? 18 : 16} /> : icon && <Icon n={icon} s={size === "sm" ? 15 : 17} />}
    {children != null && <span className="btn-l">{children}</span>}
    {iconRight && <Icon n={iconRight} s={15} />}
  </button>
));
Button.displayName = "Button";

type IBProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { icon: string; label: string; kbd?: string; active?: boolean; size?: "sm" | "md"; tipSide?: "top" | "bottom" | "left" | "right"; tone?: "default" | "danger" };
export const IconButton = forwardRef<HTMLButtonElement, IBProps>(({ icon, label, kbd, active, size = "md", tipSide, tone, className, ...rest }, ref) => (
  <Tip label={label} kbd={kbd} side={tipSide}>
    <button ref={ref} aria-label={label} aria-pressed={active === undefined ? undefined : active} className={cx("ibtn", `ibtn-${size}`, active && "on", tone === "danger" && "danger", className)} {...rest}>
      <Icon n={icon} s={size === "sm" ? 16 : 18} />
    </button>
  </Tip>
));
IconButton.displayName = "IconButton";

/* ---------- 상태 ---------- */
export const Spinner: React.FC<{ s?: number; className?: string }> = ({ s = 14, className }) => <span className={cx("spin", className)} style={{ width: s, height: s }} aria-hidden />;
export const Skeleton: React.FC<{ w?: number | string; h?: number | string; r?: number; className?: string }> = ({ w = "100%", h = 14, r = 6, className }) => (
  <span className={cx("skel", className)} style={{ width: w, height: h, borderRadius: r }} aria-hidden />
);
export const EmptyState: React.FC<{ icon?: string; title: string; body?: React.ReactNode; action?: React.ReactNode; compact?: boolean }> = ({ icon = "info", title, body, action, compact }) => (
  <div className={cx("empty", compact && "compact")}>
    <span className="empty-ic"><Icon n={icon} s={compact ? 16 : 20} /></span>
    <b>{title}</b>{body && <p>{body}</p>}{action}
  </div>
);
export const Tag: React.FC<{ tone?: "default" | "ok" | "warn" | "danger" | "agent" | "select" | "brand"; children: React.ReactNode; title?: string }> = ({ tone = "default", children, title }) => (
  <span className={cx("tag", `tag-${tone}`)} title={title}>{children}</span>
);
export const Dot: React.FC<{ tone: "ok" | "warn" | "danger" | "agent" | "idle"; pulse?: boolean }> = ({ tone, pulse }) => <i className={cx("dot", `dot-${tone}`, pulse && "pulse")} aria-hidden />;

/* ---------- 대화상자 ---------- */
export const Dialog: React.FC<{
  open: boolean; onOpenChange: (v: boolean) => void; title: string; desc?: React.ReactNode; children?: React.ReactNode;
  footer?: React.ReactNode; width?: number;
}> = ({ open, onOpenChange, title, desc, children, footer, width = 440 }) => (
  <RDialog.Root open={open} onOpenChange={onOpenChange}>
    <RDialog.Portal>
      <RDialog.Overlay className="scrim" />
      <RDialog.Content className="dialog" style={{ width }} aria-describedby={desc ? undefined : undefined}>
        <RDialog.Title className="dialog-t">{title}</RDialog.Title>
        {desc ? <RDialog.Description className="dialog-d">{desc}</RDialog.Description> : <RDialog.Description className="sr-only">{title}</RDialog.Description>}
        {children}
        {footer && <div className="dialog-f">{footer}</div>}
        <RDialog.Close asChild><button className="dialog-x" aria-label={tr("닫기")}><Icon n="close" s={14} /></button></RDialog.Close>
      </RDialog.Content>
    </RDialog.Portal>
  </RDialog.Root>
);

/** 확인창: await confirm({...}) → true/false. 파괴적 동작은 danger. */
type ConfirmOpts = { title: string; body?: React.ReactNode; ok?: string; cancel?: string; danger?: boolean };
let pushConfirm: ((o: ConfirmOpts & { resolve: (v: boolean) => void }) => void) | null = null;
export const confirmDialog = (o: ConfirmOpts) => new Promise<boolean>((resolve) => (pushConfirm ? pushConfirm({ ...o, resolve }) : resolve(window.confirm(o.title))));
export const ConfirmHost: React.FC = () => {
  const [q, setQ] = useState<(ConfirmOpts & { resolve: (v: boolean) => void }) | null>(null);
  useEffect(() => { pushConfirm = setQ; return () => { pushConfirm = null; }; }, []);
  const close = (v: boolean) => { q?.resolve(v); setQ(null); };
  return (
    <Dialog open={!!q} onOpenChange={(v) => !v && close(false)} title={q?.title ?? ""} desc={q?.body} width={420}
      footer={<><Button variant="ghost" onClick={() => close(false)}>{q?.cancel ?? tr("취소")}</Button>
        <Button variant={q?.danger ? "danger" : "primary"} autoFocus onClick={() => close(true)}>{q?.ok ?? tr("확인")}</Button></>} />
  );
};

/* ---------- 메뉴 · 팝오버 ---------- */
export type MenuItem = { label: string; icon?: string; kbd?: string; danger?: boolean; disabled?: boolean; onSelect: () => void } | "sep";
export const Menu: React.FC<{ trigger: React.ReactElement; items: MenuItem[]; align?: "start" | "end"; side?: "top" | "right" | "bottom" | "left" }> = ({ trigger, items, align = "end", side = "bottom" }) => (
  <RMenu.Root>
    <RMenu.Trigger asChild>{trigger}</RMenu.Trigger>
    <RMenu.Portal>
      <RMenu.Content className="menu" side={side} align={align} sideOffset={6} collisionPadding={8}>
        {items.map((it, i) => it === "sep" ? <RMenu.Separator key={i} className="menu-sep" /> : (
          <RMenu.Item key={i} className={cx("menu-i", it.danger && "danger")} disabled={it.disabled} onSelect={it.onSelect}>
            {it.icon && <Icon n={it.icon} s={14} />}<span className="grow">{it.label}</span>{it.kbd && <Kbd k={it.kbd} />}
          </RMenu.Item>
        ))}
      </RMenu.Content>
    </RMenu.Portal>
  </RMenu.Root>
);
export const Popover: React.FC<{ trigger: React.ReactElement; children: React.ReactNode; open?: boolean; onOpenChange?: (v: boolean) => void; side?: "top" | "bottom" | "left" | "right"; align?: "start" | "center" | "end"; width?: number }> = ({ trigger, children, open, onOpenChange, side = "bottom", align = "start", width = 320 }) => (
  <RPopover.Root open={open} onOpenChange={onOpenChange}>
    <RPopover.Trigger asChild>{trigger}</RPopover.Trigger>
    <RPopover.Portal>
      <RPopover.Content className="pop" side={side} align={align} sideOffset={6} collisionPadding={8} style={{ width }}>{children}</RPopover.Content>
    </RPopover.Portal>
  </RPopover.Root>
);

/* ---------- 입력 ---------- */
/** 한글 입력기 조합 중인지 (Safari 의 keyCode 229 포함) */
export const composing = (e: React.KeyboardEvent) => e.nativeEvent.isComposing || e.keyCode === 229;

export const Field: React.FC<{ label?: React.ReactNode; hint?: React.ReactNode; children: React.ReactNode; inline?: boolean; htmlFor?: string }> = ({ label, hint, children, inline, htmlFor }) => (
  <div className={cx("field", inline && "inline")}>
    {label && <label className="field-l" htmlFor={htmlFor}>{label}</label>}
    {children}
    {hint && <div className="field-h">{hint}</div>}
  </div>
);

/** 글자 입력: 값은 밖에서, 확정(onCommit)은 Enter/blur 에서만 — 치는 중간값을 저장하지 않는다 */
export const TextInput: React.FC<{ value: string; onCommit: (v: string) => void; placeholder?: string; id?: string; mono?: boolean; disabled?: boolean; "aria-label"?: string }> = ({ value, onCommit, placeholder, id, mono, disabled, ...a }) => {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  return <input id={id} className={cx("in", mono && "mono")} value={v} placeholder={placeholder} disabled={disabled} aria-label={a["aria-label"]}
    onChange={(e) => setV(e.target.value)} onBlur={() => v !== value && onCommit(v)}
    onKeyDown={(e) => { if (e.key === "Enter" && !composing(e)) (e.target as HTMLInputElement).blur(); if (e.key === "Escape") { setV(value); (e.target as HTMLInputElement).blur(); } }} />;
};

/** 여러 줄 글자: 같은 확정 규칙. Ctrl/⌘+Enter 로 확정 */
export const TextArea: React.FC<{ value: string; onCommit: (v: string) => void; rows?: number; placeholder?: string; id?: string; "aria-label"?: string }> = ({ value, onCommit, rows = 3, placeholder, id, ...a }) => {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  return <textarea id={id} className="in ta" rows={rows} value={v} placeholder={placeholder} aria-label={a["aria-label"]}
    onChange={(e) => setV(e.target.value)} onBlur={() => v !== value && onCommit(v)}
    onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !composing(e)) (e.target as HTMLTextAreaElement).blur(); if (e.key === "Escape") { setV(value); (e.target as HTMLTextAreaElement).blur(); } }} />;
};

/** 숫자: 앞 글자(X · Y …)를 끌면 값이 바뀐다. 화살표 ±step (Shift ×10). 확정은 Enter/blur */
export const NumberInput: React.FC<{ label: string; value: number; onCommit: (v: number) => void; step?: number; min?: number; max?: number; digits?: number; unit?: string; readOnly?: boolean }> = ({ label, value, onCommit, step = 1, min = -Infinity, max = Infinity, digits = 0, unit, readOnly }) => {
  const fmt = (n: number) => (Number.isFinite(n) ? n.toFixed(digits) : "0");
  const [v, setV] = useState(fmt(value));
  const id = useId();
  useEffect(() => setV(fmt(value)), [value]); // eslint-disable-line react-hooks/exhaustive-deps
  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const commit = (s: string) => { const n = Number(s); if (s.trim() === "" || !Number.isFinite(n)) { setV(fmt(value)); return; } const c = clamp(n); setV(fmt(c)); if (c !== value) onCommit(c); };
  const drag = useRef<{ x: number; v: number } | null>(null);
  return (
    <label className={cx("num-in", readOnly && "ro")} htmlFor={id}>
      <span className="num-l" onPointerDown={(e) => { if (readOnly) return; drag.current = { x: e.clientX, v: value }; (e.target as HTMLElement).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => { const d = drag.current; if (!d) return; const n = clamp(+(d.v + Math.round((e.clientX - d.x) / 3) * step).toFixed(digits)); setV(fmt(n)); }}
        onPointerUp={() => { if (drag.current) { drag.current = null; commit(v); } }} title={readOnly ? undefined : tr("끌어서 바꾸기")}>{label}</span>
      <input id={id} className="num-v mono" inputMode="decimal" value={v} readOnly={readOnly} onChange={(e) => setV(e.target.value)} onBlur={() => commit(v)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit(v);
          if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); const n = clamp(+(Number(v) + (e.key === "ArrowUp" ? 1 : -1) * step * (e.shiftKey ? 10 : 1)).toFixed(digits)); setV(fmt(n)); onCommit(n); }
          if (e.key === "Escape") setV(fmt(value));
        }} />
      {unit && <span className="num-u">{unit}</span>}
    </label>
  );
};

/** 색: #hex · rgb() · rgba() 모두 받아 #hex 로 정규화 */
export const toHex = (c?: string | null): string | null => {
  if (!c) return null; const s = c.trim();
  if (/^#[0-9a-f]{6}$/i.test(s)) return s.toLowerCase();
  if (/^#[0-9a-f]{3}$/i.test(s)) return ("#" + s.slice(1).split("").map((x) => x + x).join("")).toLowerCase();
  const m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(s);
  if (m) return "#" + [m[1], m[2], m[3]].map((x) => Math.min(255, +x).toString(16).padStart(2, "0")).join("");
  return null;
};
export const ColorInput: React.FC<{ value?: string | null; fallback?: string | null; onCommit: (hex: string) => void; label?: string }> = ({ value, fallback, onCommit, label: labelIn }) => {
  const label = labelIn ?? tr("색");
  const shown = toHex(value) ?? toHex(fallback) ?? "#ffffff";
  const [t, setT] = useState(shown);
  useEffect(() => setT(shown), [shown]);
  return (
    <div className="color-in">
      <input type="color" aria-label={tr("{label} 고르기", { label })} value={shown} onChange={(e) => onCommit(e.target.value)} />
      <input className="in mono" aria-label={tr("{label} 값", { label })} value={t} onChange={(e) => setT(e.target.value)}
        onBlur={() => { const h = toHex(t); if (h) { if (h !== shown) onCommit(h); } else setT(shown); }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
    </div>
  );
};

export const Select: React.FC<{ value: string; onChange: (v: string) => void; options: { value: string; label: string; disabled?: boolean }[]; id?: string; "aria-label"?: string; size?: "sm" | "md" }> = ({ value, onChange, options, id, size = "md", ...a }) => (
  <span className={cx("sel", `sel-${size}`)}>
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-label={a["aria-label"]}>
      {options.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>)}
    </select>
    <Icon n="down" s={12} />
  </span>
);

export const Switch: React.FC<{ on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }> = ({ on, onChange, label, disabled }) => (
  <button role="switch" aria-checked={on} aria-label={label} disabled={disabled} className={cx("switch", on && "on")} onClick={() => onChange(!on)}><i /></button>
);

export const Segmented: React.FC<{ value: string; onChange: (v: string) => void; options: { value: string; label: React.ReactNode; title?: string }[]; size?: "sm" | "md"; "aria-label": string }> = ({ value, onChange, options, size = "md", ...a }) => (
  <div className={cx("seg", `seg-${size}`)} role="radiogroup" aria-label={a["aria-label"]}>
    {options.map((o) => (
      <button key={o.value} role="radio" aria-checked={value === o.value} className={cx(value === o.value && "on")} title={o.title} onClick={() => onChange(o.value)}>{o.label}</button>
    ))}
  </div>
);

/** 접는 구역 — 열림 상태를 기억(localStorage) */
export const Section: React.FC<{ id: string; title: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean; dense?: boolean }> = ({ id, title, right, children, defaultOpen = true, dense }) => {
  const key = `fluma.sect.${id}`;
  const [open, setOpen] = useState(() => { try { const v = localStorage.getItem(key); return v == null ? defaultOpen : v === "1"; } catch { return defaultOpen; } });
  const toggle = () => setOpen((o) => { try { localStorage.setItem(key, o ? "0" : "1"); } catch { /* 저장 안 됨 */ } return !o; });
  return (
    <section className={cx("sect", dense && "dense", open && "open")}>
      <div className="sect-h">
        <button className="sect-t" aria-expanded={open} onClick={toggle}><Icon n={open ? "down" : "chevron"} s={12} />{title}</button>
        {right && <div className="sect-r">{right}</div>}
      </div>
      {open && <div className="sect-b">{children}</div>}
    </section>
  );
};

/** 진행 막대: 값이 없으면 흐르는 막대(진행률 모름) */
export const Progress: React.FC<{ value?: number | null; tone?: "primary" | "agent" | "ok" }> = ({ value, tone = "primary" }) => (
  <div className={cx("prog", `prog-${tone}`, value == null && "indet")} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value == null ? undefined : Math.round(value * 100)}>
    <i style={value == null ? undefined : { width: `${Math.max(2, Math.min(100, value * 100))}%` }} />
  </div>
);

export const Avatar: React.FC<{ src?: string | null; label: string; size?: number }> = ({ src, label, size = 28 }) => (
  src ? <img className="avatar" src={src} alt="" width={size} height={size} /> : <span className="avatar ph" style={{ width: size, height: size }}>{label.slice(0, 1)}</span>
);
