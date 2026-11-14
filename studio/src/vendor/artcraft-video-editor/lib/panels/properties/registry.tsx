import type { ReactNode } from "react";
import type {
  EffectElement,
  GraphicElement,
  ImageElement,
  MaskableElement,
  RetimableElement,
  StickerElement,
  TextElement,
  VisualElement,
  VideoElement,
  AudioElement,
  TimelineElement,
} from "../../timeline/types";
import type { MediaAsset } from "../../media/types";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  TextFontIcon,
  ArrowExpandIcon,
  MusicNote03Icon,
  MagicWand05Icon,
  DashboardSpeed02Icon,
} from "@hugeicons/core-free-icons";
import { ElementParamsTab, type ParamGroupSpec } from "./components/element-params-tab";
import { ClipEffectsTab, StandaloneEffectTab } from "../../effects/components/effects-tab";
import { MasksTab } from "../../masks/components/masks-tab";
import { SpeedTab } from "../../speed/components/speed-tab";
import { GraphicTab } from "../../graphics/components/graphic-tab";
import { OcShapesIcon } from "../../components/icons";

// fluma: Korean labels; transform + blending merged into one "배치" tab;
// text params grouped into collapsible sections; effects tab on text too.
const LAYOUT_GROUPS: readonly ParamGroupSpec[] = [
  {
    id: "transform",
    title: "위치 · 크기 · 회전",
    columns: 2,
    keys: [
      "transform.positionX",
      "transform.positionY",
      "transform.scaleX",
      "transform.scaleY",
      "transform.rotate",
    ],
  },
  { id: "blending", title: "투명도 · 혼합", keys: ["opacity", "blendMode"] },
];

const AUDIO_PARAM_KEYS = ["volume", "muted"] as const;

const TEXT_GROUPS: readonly ParamGroupSpec[] = [
  { id: "content", keys: ["content"] },
  {
    id: "font",
    title: "글꼴",
    keys: ["fontFamily", "fontSize", "fontWeight", "color", "textAlign"],
  },
  {
    id: "slant",
    title: "기울임 · 장식",
    keys: ["fontStyle", "skewX", "textDecoration"],
  },
  { id: "spacing", title: "간격", keys: ["letterSpacing", "lineHeight"] },
  {
    id: "stroke",
    title: "외곽선",
    keys: ["stroke.enabled", "stroke.color", "stroke.width"],
  },
  {
    id: "shadow",
    title: "그림자",
    keys: [
      "shadow.enabled",
      "shadow.color",
      "shadow.blur",
      "shadow.offsetX",
      "shadow.offsetY",
    ],
  },
  {
    id: "background",
    title: "배경 상자",
    keys: [
      "background.enabled",
      "background.color",
      "background.cornerRadius",
      "background.paddingX",
      "background.paddingY",
      "background.offsetX",
      "background.offsetY",
    ],
  },
];

export type TabContentProps = {
  trackId: string;
};

export type PropertiesTabDef = {
  id: string;
  label: string;
  icon: ReactNode;
  content: (props: TabContentProps) => ReactNode;
};

export type ElementPropertiesConfig = {
  defaultTab: string;
  tabs: PropertiesTabDef[];
};

function buildTransformTab({
  element,
}: {
  element: VisualElement;
}): PropertiesTabDef {
  return {
    id: "transform",
    label: "배치",
    icon: <HugeiconsIcon icon={ArrowExpandIcon} size={16} />,
    content: ({ trackId }) => (
      <ElementParamsTab
        element={element}
        trackId={trackId}
        groups={LAYOUT_GROUPS}
        sectionKey="transform"
      />
    ),
  };
}

function buildAudioTab({
  element,
}: {
  element: AudioElement | VideoElement;
}): PropertiesTabDef {
  return {
    id: "audio",
    label: "소리",
    icon: <HugeiconsIcon icon={MusicNote03Icon} size={16} />,
    content: ({ trackId }) => (
      <ElementParamsTab
        element={element}
        trackId={trackId}
        paramKeys={AUDIO_PARAM_KEYS}
        sectionKey="audio"
      />
    ),
  };
}

function buildSpeedTab({
  element,
}: {
  element: RetimableElement;
}): PropertiesTabDef {
  return {
    id: "speed",
    label: "속도",
    icon: <HugeiconsIcon icon={DashboardSpeed02Icon} size={16} />,
    content: ({ trackId }) => (
      <SpeedTab element={element} trackId={trackId} />
    ),
  };
}

function buildMasksTab({
  element,
}: {
  element: MaskableElement;
}): PropertiesTabDef {
  return {
    id: "masks",
    label: "마스크",
    icon: <OcShapesIcon size={16} />,
    content: ({ trackId }) => (
      <MasksTab element={element} trackId={trackId} />
    ),
  };
}

function buildClipEffectsTab({
  element,
}: {
  element: VisualElement;
}): PropertiesTabDef {
  return {
    id: "effects",
    label: "효과",
    icon: <HugeiconsIcon icon={MagicWand05Icon} size={16} />,
    content: ({ trackId }) => (
      <ClipEffectsTab element={element} trackId={trackId} />
    ),
  };
}

function buildTextTab({ element }: { element: TextElement }): PropertiesTabDef {
  return {
    id: "text",
    label: "텍스트",
    icon: <HugeiconsIcon icon={TextFontIcon} size={16} />,
    content: ({ trackId }) => (
      <ElementParamsTab
        element={element}
        trackId={trackId}
        groups={TEXT_GROUPS}
        sectionKey="text"
      />
    ),
  };
}

function buildGraphicTab({
  element,
}: {
  element: GraphicElement;
}): PropertiesTabDef {
  return {
    id: "graphic",
    label: "도형",
    icon: <OcShapesIcon size={16} />,
    content: ({ trackId }) => (
      <GraphicTab element={element} trackId={trackId} />
    ),
  };
}

function buildStandaloneEffectTab({
  element,
}: {
  element: EffectElement;
}): PropertiesTabDef {
  return {
    id: "effects",
    label: "효과",
    icon: <HugeiconsIcon icon={MagicWand05Icon} size={16} />,
    content: ({ trackId }) => (
      <StandaloneEffectTab element={element} trackId={trackId} />
    ),
  };
}

function getTextConfig({
  element,
}: {
  element: TextElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "text",
    tabs: [
      buildTextTab({ element }),
      buildTransformTab({ element }),
    ],
  };
}

function getVideoConfig({
  element,
  mediaAsset,
}: {
  element: VideoElement;
  mediaAsset: MediaAsset | undefined;
}): ElementPropertiesConfig {
  const showAudioTab = mediaAsset?.hasAudio !== false;
  return {
    defaultTab: "transform",
    tabs: [
      buildTransformTab({ element }),
      ...(showAudioTab ? [buildAudioTab({ element })] : []),
      buildSpeedTab({ element }),
      buildMasksTab({ element }),
    ],
  };
}

function getImageConfig({
  element,
}: {
  element: ImageElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "transform",
    tabs: [
      buildTransformTab({ element }),
      buildMasksTab({ element }),
    ],
  };
}

function getStickerConfig({
  element,
}: {
  element: StickerElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "transform",
    tabs: [
      buildTransformTab({ element }),
    ],
  };
}

function getGraphicConfig({
  element,
}: {
  element: GraphicElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "graphic",
    tabs: [
      buildGraphicTab({ element }),
      buildTransformTab({ element }),
      buildMasksTab({ element }),
    ],
  };
}

function getAudioConfig({
  element,
}: {
  element: AudioElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "audio",
    tabs: [buildAudioTab({ element }), buildSpeedTab({ element })],
  };
}

function getEffectConfig({
  element,
}: {
  element: EffectElement;
}): ElementPropertiesConfig {
  return {
    defaultTab: "effects",
    tabs: [buildStandaloneEffectTab({ element })],
  };
}

export function getPropertiesConfig({
  element,
  mediaAssets,
}: {
  element: TimelineElement;
  mediaAssets: MediaAsset[];
}): ElementPropertiesConfig {
  switch (element.type) {
    case "text":
      return getTextConfig({ element });
    case "video": {
      const mediaAsset = mediaAssets.find((a) => a.id === element.mediaId);
      return getVideoConfig({ element, mediaAsset });
    }
    case "image":
      return getImageConfig({ element });
    case "sticker":
      return getStickerConfig({ element });
    case "graphic":
      return getGraphicConfig({ element });
    case "audio":
      return getAudioConfig({ element });
    case "effect":
      return getEffectConfig({ element });
  }
}
