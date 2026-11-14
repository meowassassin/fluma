import type { ElementType } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  ClosedCaptionIcon,
  Folder03Icon,
  Happy01Icon,
  HeadphonesIcon,
  MagicWand05Icon,
  TextIcon,
  Settings01Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";

export const TAB_KEYS = [
  "media",
  "text",
  "stickers",
  "effects",
  "sounds",
  "captions",
  "settings",
] as const;

export type Tab = (typeof TAB_KEYS)[number];

const createHugeiconsIcon =
  ({ icon }: { icon: IconSvgElement }) =>
  ({ className }: { className?: string }) => (
    <HugeiconsIcon icon={icon} className={className} />
  );

export const tabs = {
  media: {
    icon: createHugeiconsIcon({ icon: Folder03Icon }),
    label: "미디어",
  },
  text: {
    icon: createHugeiconsIcon({ icon: TextIcon }),
    label: "텍스트",
  },
  stickers: {
    icon: createHugeiconsIcon({ icon: Happy01Icon }),
    label: "도형 · 스티커",
  },
  effects: {
    icon: createHugeiconsIcon({ icon: MagicWand05Icon }),
    label: "효과",
  },
  sounds: {
    icon: createHugeiconsIcon({ icon: HeadphonesIcon }),
    label: "효과음",
  },
  captions: {
    icon: createHugeiconsIcon({ icon: ClosedCaptionIcon }),
    label: "자막",
  },
  settings: {
    icon: createHugeiconsIcon({ icon: Settings01Icon }),
    label: "설정",
  },
} satisfies Record<
  Tab,
  { icon: ElementType<{ className?: string }>; label: string }
>;

export type MediaViewMode = "grid" | "list";
export type MediaSortKey = "name" | "type" | "duration" | "size";
export type MediaSortOrder = "asc" | "desc";

// fluma: host-injected panels use their own ids, so the active tab is a
// built-in Tab or any extra panel id.
export type ActiveAssetsTab = Tab | (string & {});

interface AssetsPanelStore {
  activeTab: ActiveAssetsTab;
  setActiveTab: (tab: ActiveAssetsTab) => void;
  highlightMediaId: string | null;
  requestRevealMedia: (mediaId: string) => void;
  clearHighlight: () => void;

  /* Media */
  mediaViewMode: MediaViewMode;
  setMediaViewMode: (mode: MediaViewMode) => void;
  mediaSortBy: MediaSortKey;
  mediaSortOrder: MediaSortOrder;
  setMediaSort: (args: { key: MediaSortKey; order: MediaSortOrder }) => void;
}

export const useAssetsPanelStore = create<AssetsPanelStore>()(
  persist(
    (set) => ({
      activeTab: "media",
      setActiveTab: (tab) => set({ activeTab: tab }),
      highlightMediaId: null,
      requestRevealMedia: (mediaId) =>
        set({ activeTab: "media", highlightMediaId: mediaId }),
      clearHighlight: () => set({ highlightMediaId: null }),
      mediaViewMode: "grid",
      setMediaViewMode: (mode) => set({ mediaViewMode: mode }),
      mediaSortBy: "name",
      mediaSortOrder: "asc",
      setMediaSort: ({ key, order }) =>
        set({ mediaSortBy: key, mediaSortOrder: order }),
    }),
    {
      name: "assets-panel",
      partialize: (state) => ({
        mediaViewMode: state.mediaViewMode,
        mediaSortBy: state.mediaSortBy,
        mediaSortOrder: state.mediaSortOrder,
      }),
    },
  ),
);
