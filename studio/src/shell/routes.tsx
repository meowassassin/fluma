import React, { lazy } from "react";
import { createBrowserRouter, Navigate, useParams } from "react-router-dom";
import { AppShell } from "./AppShell";
import { RouteError } from "./ErrorBoundary";
import { HomePage } from "../features/home/HomePage";

// 일반 탐색 화면은 쉬는 틈에 미리 받아 둔다(preloadPages).
// 단, 무거운 영상 편집기(veditor: 1.7MB JS + 3MB WASM)는 초기 네트워크 및 메모리 보호를 위해 실제 진입 시에만 로드한다.
const preloadLoaders = {
  videos: () => import("../features/videos/VideosPage"),
  trends: () => import("../features/trends/TrendsPage"),
  xray: () => import("../features/trends/XrayPage"),
  library: () => import("../features/library/LibraryPage"),
  automation: () => import("../features/automation/AutomationPage"),
  settings: () => import("../features/settings/SettingsPage"),
  crafts: () => import("../features/crafts/CraftsPage"),
};
const loaders = {
  ...preloadLoaders,
  veditor: () => import("../features/veditor/VEditorPage"),
};
const VideosPage = lazy(() => loaders.videos().then((m) => ({ default: m.VideosPage })));
const TrendsPage = lazy(() => loaders.trends().then((m) => ({ default: m.TrendsPage })));
const XrayPage = lazy(() => loaders.xray().then((m) => ({ default: m.XrayPage })));
const LibraryPage = lazy(() => loaders.library().then((m) => ({ default: m.LibraryPage })));
const AutomationPage = lazy(() => loaders.automation().then((m) => ({ default: m.AutomationPage })));
const CraftsPage = lazy(() => loaders.crafts().then((m) => ({ default: m.CraftsPage })));
const CraftViewPage = lazy(() => loaders.crafts().then((m) => ({ default: m.CraftViewPage })));
const VEditorPage = lazy(() => loaders.veditor().then((m) => ({ default: m.VEditorPage })));
const SettingsPage = lazy(() => loaders.settings().then((m) => ({ default: m.SettingsPage })));
export function preloadPages() { for (const f of Object.values(preloadLoaders)) f().catch(() => {}); }
// 숨은 개발용 화면(레일 없음, 미리 받지 않음) — ArtCraft 공용 부품 점검
const ArtcraftDevPage = lazy(() => import("../features/artcraft-dev/ArtcraftDevPage").then((m) => ({ default: m.ArtcraftDevPage })));

// 화면 코드를 받는 동안의 Suspense 는 AppShell 의 Outlet 바깥 한 곳에만 둔다 — 화면마다 경계를 두면 이동할 때마다 빈 화면이 깜빡인다
const L = (el: React.ReactNode) => el;

/** 과거 Craft 편집기 주소(/p/:id)는 단일 통합된 타임라인 영상 편집기(/veditor/:id)로 리다이렉트 */
const StudioRedirect: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/veditor/${id}`} replace />;
};

/** 예전 파이프라인 주소(/pipeline/:id)는 영상 목록에서 그 영상을 펼친 상태로 */
const PipelineRedirect: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/videos?open=${encodeURIComponent(id ?? "")}`} replace />;
};

export const router = createBrowserRouter([
  // 영상 편집기 — 전체 화면(왼쪽 레일 없이, 편집기 머리에 나가기 버튼)
  { path: "/veditor/:id", element: <React.Suspense fallback={null}><VEditorPage /></React.Suspense>, errorElement: <RouteError /> },
  { path: "/dev/artcraft", element: <React.Suspense fallback={null}><ArtcraftDevPage /></React.Suspense>, errorElement: <RouteError /> },
  {
    path: "/", element: <AppShell />, errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage />, errorElement: <RouteError /> },
      { path: "videos", element: L(<VideosPage />), errorElement: <RouteError /> },
      { path: "p/:id", element: <StudioRedirect /> },
      { path: "pipeline", element: <Navigate to="/videos" replace /> },
      { path: "pipeline/:id", element: <PipelineRedirect /> },
      { path: "trends", element: L(<TrendsPage />), errorElement: <RouteError /> },
      { path: "trends/x/:vid", element: L(<XrayPage />), errorElement: <RouteError /> },
      { path: "library", element: L(<LibraryPage />), errorElement: <RouteError /> },
      { path: "automation", element: L(<AutomationPage />), errorElement: <RouteError /> },
      { path: "crafts", element: L(<CraftsPage />), errorElement: <RouteError /> },
      { path: "engine/craft/apps/:name", element: L(<CraftViewPage />), errorElement: <RouteError /> },
      { path: "settings", element: <Navigate to="/settings/agent" replace /> },
      { path: "settings/:section", element: L(<SettingsPage />), errorElement: <RouteError /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
], { future: { v7_relativeSplatPath: true, v7_fetcherPersist: true, v7_normalizeFormMethod: true, v7_partialHydration: true, v7_skipActionErrorRevalidation: true } });
