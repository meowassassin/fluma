import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import * as RTooltip from "@radix-ui/react-tooltip";
import { Toaster } from "sonner";
import { qc, qk, startEvents } from "./lib/queries";
import { api } from "./lib/api";
import { preloadPages, router } from "./shell/routes";
import { ConfirmHost } from "./ui/kit";
import { useLang } from "./lib/i18n";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/shell.css";
import "./styles/home.css";
import "./styles/studio.css";
import "./styles/agent.css";
import "./styles/pages.css";
import "./styles/trends.css";
import "./styles/brand.css";

startEvents();

// 첫 화면이 뜬 뒤 쉬는 틈에: 다른 화면 코드 · 자주 쓰는 목록을 차례로 미리 받아 둔다
const idle = (f: () => void) => ("requestIdleCallback" in window ? (window as Window & { requestIdleCallback: (f: () => void, o?: { timeout: number }) => void }).requestIdleCallback(f, { timeout: 3000 }) : setTimeout(f, 1500));
idle(() => {
  preloadPages();
  qc.prefetchQuery({ queryKey: qk.projects, queryFn: ({ signal }) => api.projects(signal), staleTime: 10_000 });
  qc.prefetchQuery({ queryKey: qk.settings, queryFn: async ({ signal }) => (await api.settings(signal)).settings });
  setTimeout(() => {
    qc.prefetchQuery({ queryKey: qk.engines, queryFn: ({ signal }) => api.engines(signal), staleTime: 5 * 60_000 });
    qc.prefetchQuery({ queryKey: qk.characters, queryFn: ({ signal }) => api.characters(signal), staleTime: 5 * 60_000 });
    qc.prefetchQuery({ queryKey: qk.skills, queryFn: ({ signal }) => api.skills(signal), staleTime: 5 * 60_000 });
    qc.prefetchQuery({ queryKey: qk.trends, staleTime: 30_000, queryFn: async ({ signal }) => {
      const r = await fetch("/api/public/trends/index.json", { signal }); if (!r.ok) return { requests: [], items: [] };
      const d = await r.json(); return { requests: d.requests ?? [], items: d.items ?? [] };
    } });
  }, 2000);
});

// 언어를 바꾸면 화면 전체를 다시 그린다(t() 가 새 언어로 다시 불리게) — 데이터 캐시 · 주소는 그대로
const LangRoot: React.FC = () => {
  const lang = useLang((s) => s.lang);
  return <React.Fragment key={lang}><RouterProvider router={router} future={{ v7_startTransition: true }} /><ConfirmHost /></React.Fragment>;
};

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <RTooltip.Provider delayDuration={350} skipDelayDuration={200}>
        <LangRoot />
        <Toaster theme="dark" position="bottom-right" closeButton visibleToasts={4} offset={16} />
      </RTooltip.Provider>
    </QueryClientProvider>
  </React.StrictMode>,
);
