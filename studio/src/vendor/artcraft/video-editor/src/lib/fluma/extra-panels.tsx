"use client";

// fluma: host extension point — extra left-rail panels (e.g. Fluma's
// "파이프라인" panel). Passed to <VideoEditor extraPanels={...}> and shown as
// additional tabs after the built-in ones.
import { createContext, useContext, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";
import { Button } from "../components/ui/button";
import { cn } from "../utils/ui";
import { useAssetsPanelStore } from "../panels/assets/assets-panel-store";


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

// Rail buttons for host panels, rendered after the built-in tabs in
// panels/assets/tabbar.tsx (same look as the built-in buttons).

export function ExtraPanelTabButtons() {
  const panels = useExtraPanels();
  const { activeTab, setActiveTab } = useAssetsPanelStore();
  if (panels.length === 0) return null;
  return (
    <>
      <div className="my-1 h-px w-6 shrink-0 bg-border" />
      {panels.map((panel) => (
        <Tooltip key={panel.id} delayDuration={10}>
          <TooltipTrigger asChild>
            <Button
              variant={activeTab === panel.id ? "secondary" : "ghost"}
              size="icon"
              aria-label={panel.label}
              className={cn(
                "shrink-0",
                "h-8 w-8 rounded-lg border-transparent",
                activeTab !== panel.id && "text-muted-foreground",
              )}
              onClick={() => setActiveTab(panel.id)}
            >
              {panel.icon}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right" align="center" variant="sidebar" sideOffset={8}>
            <div className="text-foreground text-sm leading-none font-medium">{panel.label}</div>
          </TooltipContent>
        </Tooltip>
      ))}
    </>
  );
}
