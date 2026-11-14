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
import { CaptionsView } from "../../text/components/captions-view";
import { useExtraPanels } from "./extra-panels";

const VIEWS: Record<Tab, () => React.ReactNode> = {
  media: () => <MediaView />,
  text: () => <TextView />,
  stickers: () => <StickersView />,
  effects: () => <EffectsView />,
  sounds: () => <SoundsView />,
  captions: () => <CaptionsView />,
  settings: () => <SettingsView />,
};

export function AssetsPanel() {
  const { activeTab } = useAssetsPanelStore();
  const extraPanels = useExtraPanels();
  // fluma: host panels render in the same area as built-in views
  const extra = extraPanels.find((panel) => panel.id === activeTab);
  const builtin = VIEWS[activeTab as Tab] ?? VIEWS.media;

  return (
    <div className="panel bg-background flex h-full rounded-lg border border-ui-panel-border overflow-hidden">
      <TabBar />
      <Separator orientation="vertical" />
      <div className="min-w-0 flex-1 overflow-hidden">
        {extra ? <div className="h-full overflow-y-auto">{extra.render()}</div> : builtin()}
      </div>
    </div>
  );
}
