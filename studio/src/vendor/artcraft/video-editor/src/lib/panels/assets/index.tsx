"use client";

import { Separator } from "../../components/ui/separator";
import { type Tab, useAssetsPanelStore } from "./assets-panel-store";
import { TabBar } from "./tabbar";
import { MediaView } from "./views/assets";
import { SettingsView } from "./views/settings";
import { SoundsView } from "../../sounds/components/assets-view";
import { StickersView } from "../../stickers/components/assets-view";
import { TextView } from "../../text/components/assets-view";
import { EffectsView } from "../../effects/components/assets-view";
// fluma: host panels + Fluma views for the Text / Captions tabs
import { useExtraPanels } from "../../fluma/extra-panels";
import { FlumaTextView } from "../../fluma/text-view";
import { CaptionsView } from "../../fluma/captions-view";

const FLUMA_VIEW_OVERRIDES: Partial<Record<Tab, React.ReactNode>> = {
  text: <FlumaTextView />,
  captions: <CaptionsView />,
};

// Captions tab renders a placeholder; depends on the transcription
// subsystem which is deferred per port scope.
function ComingSoon({ label }: { label: string }) {
  return (
    <div className="text-muted-foreground p-4">{label} view coming soon...</div>
  );
}

export function AssetsPanel() {
  const { activeTab } = useAssetsPanelStore();
  const extra = useExtraPanels().find((panel) => panel.id === activeTab); // fluma

  const viewMap: Record<Tab, React.ReactNode> = {
    media: <MediaView />,
    sounds: <SoundsView />,
    text: FLUMA_VIEW_OVERRIDES.text ?? <TextView />, // fluma: presets
    stickers: <StickersView />,
    effects: <EffectsView />,
    captions: FLUMA_VIEW_OVERRIDES.captions ?? <ComingSoon label="Captions" />, // fluma: caption list
    settings: <SettingsView />,
  };

  return (
    <div className="panel bg-background flex h-full rounded-lg border border-ui-panel-border overflow-hidden">
      <TabBar />
      <Separator orientation="vertical" />
      <div className="min-w-0 flex-1 overflow-hidden">
        {/* fluma: host panels render in the same area as built-in views */}
        {extra ? <div className="h-full overflow-y-auto">{extra.render()}</div> : (viewMap[activeTab as Tab] ?? viewMap.media)}
      </div>
    </div>
  );
}
