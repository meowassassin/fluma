"use client";

// fluma: host extension point — extra left-rail panels (e.g. Fluma's
// "파이프라인" panel). Passed to <VideoEditor extraPanels={...}> and shown as
// additional tabs after the built-in ones.
import { createContext, useContext, type ReactNode } from "react";

export interface EditorExtraPanel {
  id: string;
  label: string;
  icon: ReactNode;
  render: () => ReactNode;
}

const ExtraPanelsCtx = createContext<readonly EditorExtraPanel[]>([]);

export function ExtraPanelsScope({
  panels,
  children,
}: {
  panels: readonly EditorExtraPanel[] | undefined;
  children: ReactNode;
}) {
  return (
    <ExtraPanelsCtx.Provider value={panels ?? []}>{children}</ExtraPanelsCtx.Provider>
  );
}

export function useExtraPanels(): readonly EditorExtraPanel[] {
  return useContext(ExtraPanelsCtx);
}
