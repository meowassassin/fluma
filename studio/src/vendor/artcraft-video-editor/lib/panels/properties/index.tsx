"use client";

import { ScrollArea } from "../../components/ui/scroll-area";
import { useEditor } from "../../editor/use-editor";
import { useElementSelection } from "../../timeline/hooks/element/use-element-selection";
import { usePropertiesStore } from "./stores/properties-store";
import { getPropertiesConfig } from "./registry";
import { cn } from "../../utils/ui";
import { EmptyView } from "./empty-view";

export function PropertiesPanel() {
  const editor = useEditor();
  useEditor((e) => e.scenes.getActiveSceneOrNull());
  useEditor((e) => e.media.getAssets());
  const { selectedElements } = useElementSelection();
  const { activeTabPerType, setActiveTab } = usePropertiesStore();

  if (selectedElements.length === 0) {
    return (
      <div className="panel bg-background flex h-full flex-col items-center justify-center overflow-hidden rounded-lg border border-ui-panel-border">
        <EmptyView />
      </div>
    );
  }

  if (selectedElements.length > 1) {
    return (
      <div className="panel bg-background flex h-full flex-col items-center justify-center overflow-hidden rounded-lg border border-ui-panel-border">
        <p className="text-muted-foreground text-sm">
          {selectedElements.length}개 항목 선택됨 — 하나만 선택하면 속성을 바꿀 수 있어요
        </p>
      </div>
    );
  }

  const mediaAssets = editor.media.getAssets();

  const elementsWithTracks = editor.timeline.getElementsWithTracks({
    elements: selectedElements,
  });
  const elementWithTrack = elementsWithTracks[0];

  if (!elementWithTrack) return null;

  const { element, track } = elementWithTrack;
  const config = getPropertiesConfig({ element, mediaAssets });
  const visibleTabs = config.tabs;

  const storedTabId = activeTabPerType[element.type];
  const isStoredTabVisible = visibleTabs.some((t) => t.id === storedTabId);
  const activeTabId = isStoredTabVisible ? storedTabId : config.defaultTab;
  const activeTab =
    visibleTabs.find((t) => t.id === activeTabId) ?? visibleTabs[0];

  if (!activeTab) return null;

  // fluma: labelled horizontal tabs (icon + Korean label) instead of an
  // unlabeled icon rail; element name + kind shown on top.
  const KIND_LABELS: Record<string, string> = {
    video: "영상",
    image: "이미지",
    text: "텍스트",
    audio: "오디오",
    sticker: "스티커",
    graphic: "도형",
    effect: "효과",
  };

  return (
    <div className="panel bg-background flex h-full flex-col overflow-hidden rounded-lg border border-ui-panel-border">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-ui-panel-border px-3">
        <span className="shrink-0 rounded bg-accent px-1.5 py-0.5 text-[10.5px] text-muted-foreground">
          {KIND_LABELS[element.type] ?? element.type}
        </span>
        <span className="truncate text-sm font-medium">{element.name}</span>
      </div>
      <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-ui-panel-border px-2 py-1.5 scrollbar-hidden">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab({ elementType: element.type, tabId: tab.id })}
            className={cn(
              "flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-xs [&_svg]:size-3.5",
              tab.id === activeTab.id
                ? "bg-accent text-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>
      <ScrollArea className="min-h-0 flex-1 scrollbar-hidden">
        {activeTab.content({ trackId: track.id })}
      </ScrollArea>
    </div>
  );
}
