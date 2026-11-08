/* 설정 · MCP — 외부 도구 서버를 붙이면 에이전트가 그 도구를 쓴다(예: 노션 · 깃허브 · 파일 검색).
   비밀 값(env · header)은 ~/.shortsforge/mcp.json(0600)에만 있고 화면에는 이름만 온다. 고칠 때 비워 두면 기존 값 유지 */
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Icon } from "../../ui/Icon";
import { Button, EmptyState, Field, IconButton, Segmented, Switch, Tag, confirmDialog, cx } from "../../ui/kit";
import { qc } from "../../lib/queries";
import { t } from "../../lib/i18n";

interface Mcp { name: string; type: "stdio" | "http"; enabled: boolean; command: string | null; args: string[]; url: string | null; env: string[]; headers: string[];
  lastTest: { at: number; ok: boolean; tools: number; error: string | null } | null }
const KEY = ["mcp"] as const;
const call = async (method: string, url: string, body?: unknown) => {
  const r = await fetch(url, { method, headers: { "content-type": "application/json", "x-fluma-client": "settings" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j?.error?.message || j?.message || `HTTP ${r.status}`);
  return j;
};
/** "KEY=값" 줄들 ↔ 객체 */
const parseKV = (txt: string) => Object.fromEntries(txt.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const i = l.indexOf("="); return i > 0 ? [l.slice(0, i).trim(), l.slice(i + 1)] : [l, ""]; }));
/** 인자: 따옴표로 묶은 것은 하나로 */
const parseArgs = (txt: string) => (txt.match(/"[^"]*"|'[^']*'|\S+/g) ?? []).map((a) => a.replace(/^["']|["']$/g, ""));

export const McpSec: React.FC = () => {
  const { data: list = [], isLoading } = useQuery({ queryKey: KEY, queryFn: () => call("GET", "/api/mcp") as Promise<Mcp[]> });
  const [edit, setEdit] = useState<Mcp | "new" | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [tools, setTools] = useState<Record<string, string[]>>({});
  const test = async (name: string) => {
    setTesting(name);
    try {
      const r = await call("POST", `/api/mcp/${name}/test`);
      if (r.ok) { setTools((o) => ({ ...o, [name]: r.tools })); toast.success(t("{name} 연결됨 · 도구 {n}개", { name, n: r.tools.length })); } else toast.error(t("{name} 연결 실패", { name }), { description: r.error });
    } catch (e) { toast.error(t("시험하지 못했어요"), { description: String(e) }); }
    setTesting(null); qc.invalidateQueries({ queryKey: KEY });
  };
  const toggle = async (m: Mcp, on: boolean) => {
    await call("PUT", `/api/mcp/${m.name}`, { type: m.type, command: m.command, args: m.args, url: m.url, enabled: on,
      env: Object.fromEntries(m.env.map((k) => [k, ""])), headers: Object.fromEntries(m.headers.map((k) => [k, ""])) });
    qc.invalidateQueries({ queryKey: KEY });
  };
  return (
    <>
      <h2 className="pg-sub">{t("MCP 서버")}</h2>
      <p className="faint set-intro">{t("MCP 서버를 붙이면 에이전트가 그 서버의 도구를 씁니다(예: 노션에서 자료 찾기 · 깃허브 이슈 읽기 · 사내 문서 검색). 켜 둔 서버만 다음 메시지부터 쓰입니다.")}{" "}
        {t("토큰 같은 값은 이 컴퓨터의 {file}(나만 읽기)에만 저장되고 에이전트는 이 파일을 직접 읽을 수 없습니다.").split("{file}").map((x, i) => (i ? <React.Fragment key={i}><code>~/.shortsforge/mcp.json</code>{x}</React.Fragment> : x))}</p>
      <div className="mcp-list">
        {isLoading ? null : !list.length && edit !== "new" ? <EmptyState compact icon="link" title={t("붙인 서버가 없어요")} body={t("‘서버 추가’로 명령(npx …) 또는 주소(https://…)를 넣으세요.")} /> : null}
        {list.map((m) => edit !== "new" && (edit as Mcp | null)?.name === m.name ? <McpForm key={m.name} init={m} onDone={() => setEdit(null)} /> : (
          <div key={m.name} className={cx("mcp", !m.enabled && "off")}>
            <div className="mcp-h">
              <b>{m.name}</b><Tag>{m.type === "http" ? t("주소") : t("명령")}</Tag>
              {m.lastTest && (m.lastTest.ok ? <Tag tone="ok">{t("연결됨 · 도구 {n}", { n: m.lastTest.tools })}</Tag> : <Tag tone="danger">{t("연결 실패")}</Tag>)}
              <span className="grow" />
              <Switch on={m.enabled} onChange={(v) => toggle(m, v)} label={t("{name} 켜기", { name: m.name })} />
            </div>
            <code className="mcp-cmd">{m.type === "http" ? m.url : [m.command, ...m.args].join(" ")}</code>
            {(m.env.length > 0 || m.headers.length > 0) && <span className="faint small">{t("{kind}: {names} (값은 숨김)", { kind: m.type === "http" ? t("헤더") : t("환경 변수"), names: (m.type === "http" ? m.headers : m.env).join(", ") })}</span>}
            {m.lastTest && !m.lastTest.ok && m.lastTest.error && <span className="mcp-err">{m.lastTest.error}</span>}
            {tools[m.name] && <div className="mcp-tools">{tools[m.name].slice(0, 30).map((x) => <span key={x}>{x}</span>)}{tools[m.name].length > 30 && <span>+{tools[m.name].length - 30}</span>}</div>}
            <div className="row end">
              <Button size="sm" variant="ghost" icon="play" disabled={testing === m.name} onClick={() => test(m.name)}>{testing === m.name ? t("시험 중…") : t("연결 시험")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setEdit(m)}>{t("고치기")}</Button>
              <IconButton icon="trash" label={t("지우기")} size="sm" tone="danger" onClick={async () => {
                if (!(await confirmDialog({ title: t("{name} 서버를 지울까요?", { name: m.name }), ok: t("지우기"), danger: true }))) return;
                await call("DELETE", `/api/mcp/${m.name}`); qc.invalidateQueries({ queryKey: KEY });
              }} />
            </div>
          </div>))}
        {edit === "new" ? <McpForm onDone={() => setEdit(null)} /> : <div><Button variant="secondary" icon="plus" onClick={() => setEdit("new")}>{t("서버 추가")}</Button></div>}
      </div>
    </>
  );
};

const McpForm: React.FC<{ init?: Mcp; onDone: () => void }> = ({ init, onDone }) => {
  const [name, setName] = useState(init?.name ?? "");
  const [type, setType] = useState<"stdio" | "http">(init?.type ?? "stdio");
  const [command, setCommand] = useState(init?.command ?? "npx");
  const [args, setArgs] = useState((init?.args ?? []).map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" "));
  const [url, setUrl] = useState(init?.url ?? "");
  const [kv, setKv] = useState(((init?.type === "http" ? init?.headers : init?.env) ?? []).map((k) => `${k}=`).join("\n"));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const pairs = parseKV(kv);
      await call("PUT", `/api/mcp/${name.trim()}`, type === "http" ? { type, url, headers: pairs, enabled: init?.enabled ?? true } : { type, command, args: parseArgs(args), env: pairs, enabled: init?.enabled ?? true });
      qc.invalidateQueries({ queryKey: KEY }); toast.success(t("저장했어요 — ‘연결 시험’으로 확인해 보세요")); onDone();
    } catch (e) { toast.error(t("저장하지 못했어요"), { description: String((e as Error).message) }); }
    setBusy(false);
  };
  return (
    <div className="mcp form">
      <Field label={t("이름")} hint={t("영문 소문자 · 숫자 · - _ — 에이전트에게는 mcp__이름 으로 보입니다")}><input className="in" value={name} disabled={!!init} onChange={(e) => setName(e.target.value.toLowerCase())} placeholder="notion" /></Field>
      <Field label={t("연결 방식")}><Segmented aria-label={t("연결 방식")} size="sm" value={type} onChange={(v) => setType(v as "stdio" | "http")} options={[{ value: "stdio", label: t("명령 실행 (stdio)") }, { value: "http", label: t("주소 (http)") }]} /></Field>
      {type === "stdio" ? <>
        <Field label={t("명령")}><input className="in mono" value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx" /></Field>
        <Field label={t("인자")} hint={t("띄어쓰기로 구분, 공백이 든 값은 따옴표로")}><input className="in mono" value={args} onChange={(e) => setArgs(e.target.value)} placeholder={t("-y @modelcontextprotocol/server-filesystem /home/me/자료")} /></Field>
      </> : <Field label={t("주소")}><input className="in mono" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/mcp" /></Field>}
      <Field label={type === "http" ? t("헤더 (줄마다 이름=값)") : t("환경 변수 (줄마다 이름=값)")} hint={init ? t("값을 비워 두면 저장된 값을 그대로 씁니다") : t("예: Authorization=Bearer … / GITHUB_TOKEN=…")}>
        <textarea className="in ta mono" rows={3} value={kv} onChange={(e) => setKv(e.target.value)} />
      </Field>
      <div className="row end"><Button size="sm" variant="ghost" onClick={onDone}>{t("취소")}</Button><Button size="sm" variant="primary" disabled={busy || !name.trim()} onClick={save}><Icon n="check" s={13} />{t("저장")}</Button></div>
    </div>
  );
};
