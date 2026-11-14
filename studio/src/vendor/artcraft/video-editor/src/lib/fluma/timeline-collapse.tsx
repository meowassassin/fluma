"use client";

// fluma: hide / show the timeline (Alt+T, toolbar button, bar button) so the
// preview gets the full height. Uses react-resizable-panels' collapsible panel
// on the upstream timeline panel (VideoEditor.tsx) — the layout stays upstream.
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ChevronUp } from "lucide-react";
import type { ImperativePanelHandle } from "react-resizable-panels";

interface TimelineCollapseState {
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  toggle: () => void;
}

export const useTimelineCollapse = create<TimelineCollapseState>()(
  persist(
    (set) => ({
      collapsed: false,
      setCollapsed: (collapsed) => set({ collapsed }),
      toggle: () => set((s) => ({ collapsed: !s.collapsed })),
    }),
    { name: "fluma-veditor-timeline-collapsed" },
  ),
);

/** Props for the timeline <ResizablePanel> + Alt+T shortcut. */
export function useTimelineCollapsePanel() {
  const ref = useRef<ImperativePanelHandle>(null);
  const collapsed = useTimelineCollapse((s) => s.collapsed);

  useEffect(() => {
    const panel = ref.current;
    if (!panel) return;
    if (collapsed && !panel.isCollapsed()) panel.collapse();
    if (!collapsed && panel.isCollapsed()) panel.expand();
  }, [collapsed]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyT") {
        e.preventDefault();
        useTimelineCollapse.getState().toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return {
    collapsed,
    panelProps: {
      ref,
      collapsible: true,
      collapsedSize: 0,
      onCollapse: () => useTimelineCollapse.getState().setCollapsed(true),
      onExpand: () => useTimelineCollapse.getState().setCollapsed(false),
    },
  };
}

export function CollapsedTimelineBar() {
  return (
    <div className="mx-3 mb-2 flex h-7 shrink-0 select-none items-center justify-between rounded-md border border-border px-3">
      <span className="text-[11px] text-muted-foreground">타임라인 숨김 (Alt+T)</span>
      <button
        type="button"
        onClick={() => useTimelineCollapse.getState().setCollapsed(false)}
        className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium text-primary-400 hover:bg-accent"
        title="타임라인 펼치기 (Alt+T)"
      >
        <ChevronUp className="size-3.5" />
        <span>타임라인 펼치기</span>
      </button>
    </div>
  );
}
