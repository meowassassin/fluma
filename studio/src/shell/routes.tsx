import React, { lazy } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./AppShell";
import { RouteError } from "./ErrorBoundary";
import { HomePage } from "../features/home/HomePage";

// 무거운 화면은 나눠 불러 첫 화면을 빠르게 — 첫 화면이 뜬 뒤 쉬는 틈에 전부 미리 받아 둔다(preloadPages)
const loaders = {
  studio: () => import("../features/studio/StudioPage"),
  videos: () => import("../features/videos/VideosPage"),
  trends: () => import("../features/trends/TrendsPage"),
  xray: () => import("../features/trends/XrayPage"),
  settings: () => import("../features/settings/SettingsPage"),
  crafts: () => import("../features/crafts/CraftsPage"),
};
const StudioPage = lazy(() => loaders.studio().then((m) => ({ default: m.StudioPage })));
const VideosPage = lazy(() => loaders.videos().then((m) => ({ default: m.VideosPage })));
const TrendsPage = lazy(() => loaders.trends().then((m) => ({ default: m.TrendsPage })));
const XrayPage = lazy(() => loaders.xray().then((m) => ({ default: m.XrayPage })));
const CraftsPage = lazy(() => loaders.crafts().then((m) => ({ default: m.CraftsPage })));
const CraftViewPage = lazy(() => loaders.crafts().then((m) => ({ default: m.CraftViewPage })));
const SettingsPage = lazy(() => loaders.settings().then((m) => ({ default: m.SettingsPage })));
export function preloadPages() { for (const f of Object.values(loaders)) f().catch(() => {}); }

// 화면 코드를 받는 동안의 Suspense 는 AppShell 의 Outlet 바깥 한 곳에만 둔다 — 화면마다 경계를 두면 이동할 때마다 빈 화면이 깜빡인다
const L = (el: React.ReactNode) => el;

export const router = createBrowserRouter([
  {
    path: "/", element: <AppShell />, errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage />, errorElement: <RouteError /> },
      { path: "videos", element: L(<VideosPage />), errorElement: <RouteError /> },
      { path: "p/:id", element: L(<StudioPage />), errorElement: <RouteError /> },
      { path: "trends", element: L(<TrendsPage />), errorElement: <RouteError /> },
      { path: "trends/x/:vid", element: L(<XrayPage />), errorElement: <RouteError /> },
      { path: "crafts", element: L(<CraftsPage />), errorElement: <RouteError /> },
      { path: "engine/craft/apps/:name", element: L(<CraftViewPage />), errorElement: <RouteError /> },
      { path: "settings", element: <Navigate to="/settings/agent" replace /> },
      { path: "settings/:section", element: L(<SettingsPage />), errorElement: <RouteError /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
], { future: { v7_relativeSplatPath: true, v7_fetcherPersist: true, v7_normalizeFormMethod: true, v7_partialHydration: true, v7_skipActionErrorRevalidation: true } });
