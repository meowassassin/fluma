"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui/tooltip";
import { Button } from "../../components/ui/button";
import { cn } from "../../utils/ui";
import { TAB_KEYS, tabs, useAssetsPanelStore } from "./assets-panel-store";
import { useExtraPanels } from "./extra-panels";

export function TabBar() {
  const { activeTab, setActiveTab } = useAssetsPanelStore();
  const extraPanels = useExtraPanels();
  // fluma: built-in tabs + host panels share one list
  const items = [
    ...TAB_KEYS.map((key) => {
      const tab = tabs[key];
      const Icon = tab.icon;
      return { id: key as string, label: tab.label, icon: <Icon /> };
    }),
    ...extraPanels.map((panel) => ({ id: panel.id, label: panel.label, icon: panel.icon })),
  ];
  const [showTopFade, setShowTopFade] = useState(false);
  const [showBottomFade, setShowBottomFade] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const checkScrollPosition = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;

    const { scrollTop, scrollHeight, clientHeight } = element;
    setShowTopFade(scrollTop > 0);
    setShowBottomFade(scrollTop < scrollHeight - clientHeight - 1);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    checkScrollPosition();
    element.addEventListener("scroll", checkScrollPosition);

    const resizeObserver = new ResizeObserver(checkScrollPosition);
    resizeObserver.observe(element);

    return () => {
      element.removeEventListener("scroll", checkScrollPosition);
      resizeObserver.disconnect();
    };
  }, [checkScrollPosition]);

  return (
    <div className="relative flex">
      <div
        ref={scrollRef}
        className="scrollbar-hidden relative flex size-full p-1.5 flex-col items-center justify-start gap-1 overflow-y-auto"
      >
        {items.map((item, index) => {
          const isActive = activeTab === item.id;
          return (
            <div key={item.id} className="contents">
              {index === TAB_KEYS.length && (
                <div className="my-1 h-px w-6 shrink-0 bg-border/60" />
              )}
              <Tooltip delayDuration={50}>
                <TooltipTrigger asChild>
                  <Button
                    variant={isActive ? "secondary" : "ghost"}
                    size="icon"
                    aria-label={item.label}
                    className={cn(
                      "shrink-0 h-9 w-9 rounded-lg border-transparent [&_svg]:size-[18px]",
                      isActive
                        ? "text-primary font-semibold shadow-xs"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                    onClick={() => setActiveTab(item.id)}
                  >
                    {item.icon}
                  </Button>
                </TooltipTrigger>
                <TooltipContent
                  side="right"
                  align="center"
                  variant="sidebar"
                  sideOffset={8}
                >
                  <div className="text-foreground text-xs leading-none font-medium">
                    {item.label}
                  </div>
                </TooltipContent>
              </Tooltip>
            </div>
          );
        })}
      </div>

      <FadeOverlay direction="top" show={showTopFade} />
      <FadeOverlay direction="bottom" show={showBottomFade} />
    </div>
  );
}

function FadeOverlay({
  direction,
  show,
}: {
  direction: "top" | "bottom";
  show: boolean;
}) {
  return (
    <div
      className={cn(
        "pointer-events-none absolute right-0 left-0 h-6",
        direction === "top" && show
          ? "from-background top-0 bg-gradient-to-b to-transparent"
          : "from-background bottom-0 bg-gradient-to-t to-transparent",
      )}
    />
  );
}
