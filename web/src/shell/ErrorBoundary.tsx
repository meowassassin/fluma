import React from "react";
import { useNavigate, useRouteError } from "react-router-dom";
import { Button, EmptyState } from "../ui/kit";
import { t } from "../lib/i18n";

/** 화면 단위 오류: 앱 전체가 흰 화면이 되지 않게 그 화면만 대신 그린다 */
export const RouteError: React.FC = () => {
  const err = useRouteError() as Error | undefined;
  const nav = useNavigate();
  return (
    <div className="page-error">
      <EmptyState icon="warn" title={t("이 화면을 그리다 문제가 생겼어요")}
        body={<>{t("다른 화면은 그대로 쓸 수 있어요. 같은 문제가 반복되면 아래 내용을 알려 주세요.")}<br /><code className="err-code">{String(err?.message ?? err).slice(0, 300)}</code></>}
        action={<div className="row"><Button onClick={() => location.reload()}>{t("새로고침")}</Button><Button variant="ghost" onClick={() => nav("/")}>{t("홈으로")}</Button></div>} />
    </div>
  );
};

/** 패널 단위 오류 경계 — 한 패널이 깨져도 편집기 나머지는 동작 */
export class PanelBoundary extends React.Component<{ name: string; children: React.ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  componentDidCatch(err: Error) { console.error(`[${this.props.name}]`, err); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="panel-error">
        <EmptyState compact icon="warn" title={t("{name}을(를) 그리지 못했어요", { name: t(this.props.name) })} body={String(this.state.err.message).slice(0, 160)}
          action={<Button size="sm" onClick={() => this.setState({ err: null })}>{t("다시 시도")}</Button>} />
      </div>
    );
  }
}
