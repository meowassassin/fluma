"use client";

import { useState } from "react";
import type { ParamValues } from "../../params";
import type { Effect } from "../types";
import type { EffectElement, VisualElement } from "../../timeline/types";
import { effectsRegistry } from "..";
import { useEditor } from "../../editor/use-editor";
import { useElementPreview } from "../../timeline/hooks/use-element-preview";
import {
  Section,
  SectionContent,
  SectionHeader,
  SectionTitle,
  SectionFields,
} from "../../components/section";
import { PropertyParamField } from "../../panels/properties/components/property-param-field";
import { Button } from "../../components/ui/button";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  Delete02Icon,
  ViewIcon,
  ViewOffSlashIcon,
  MagicWand05Icon,
} from "@hugeicons/core-free-icons";
import { cn } from "../../utils/ui";
import { Separator } from "../../components/ui/separator";
import {
  ProvidedEffectBrowser,
  effectTargetFor,
  useEffectProvider,
} from "../provider";

export function StandaloneEffectTab({
  element,
  trackId,
}: {
  element: EffectElement;
  trackId: string;
}) {
  const { renderElement, previewUpdates, commit } = useElementPreview({
    trackId,
    elementId: element.id,
    fallback: element,
  });

  const effect: Effect = {
    id: element.id,
    type: element.effectType,
    params: element.params,
    enabled: true,
  };

  const previewParam = (key: string) => (value: number | string | boolean) => {
    previewUpdates({
      params: { ...(renderElement as EffectElement).params, [key]: value },
    });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-3.5 h-11 shrink-0 flex items-center">
        <SectionTitle>효과</SectionTitle>
      </div>
      <EffectSection
        effect={effect}
        renderParams={(renderElement as EffectElement).params}
        previewParam={previewParam}
        onCommit={commit}
      />
    </div>
  );
}

export function ClipEffectsTab({
  element,
  trackId,
}: {
  element: VisualElement;
  trackId: string;
}) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const editor = useEditor();
  const { renderElement, previewUpdates, commit } = useElementPreview({
    trackId,
    elementId: element.id,
    fallback: element,
  });

  const effects: Effect[] = element.effects ?? [];

  const getRenderParams = ({ effectId }: { effectId: string }): ParamValues => {
    return (
      (renderElement as VisualElement).effects?.find((ef) => ef.id === effectId)
        ?.params ??
      effects.find((ef) => ef.id === effectId)?.params ??
      {}
    );
  };

  const buildPreviewParam =
    (effectId: string) =>
    (key: string) =>
    (value: number | string | boolean) => {
      const updatedEffects = (
        (renderElement as VisualElement).effects ?? []
      ).map((existing) =>
        existing.id !== effectId
          ? existing
          : { ...existing, params: { ...existing.params, [key]: value } },
      );
      previewUpdates({ effects: updatedEffects });
    };

  const handleDragStart = ({ index }: { index: number }) => setDragIndex(index);

  const handleDragOver = ({
    event,
    index,
  }: {
    event: React.DragEvent;
    index: number;
  }) => {
    event.preventDefault();
    if (index !== dropIndex) setDropIndex(index);
  };

  const handleDrop = ({ toIndex }: { toIndex: number }) => {
    if (dragIndex !== null && dragIndex !== toIndex) {
      editor.timeline.reorderClipEffects({
        trackId,
        elementId: element.id,
        fromIndex: dragIndex,
        toIndex,
      });
    }
    setDragIndex(null);
    setDropIndex(null);
  };

  const handleDragEnd = () => {
    setDragIndex(null);
    setDropIndex(null);
  };

  return (
    <div className="flex flex-col h-full">
      <AddEffectArea element={element} trackId={trackId} />
      {effects.length > 0 && (
        <div className="border-b border-white/5 px-3.5 h-10 shrink-0 flex items-center">
          <SectionTitle>적용된 효과 {effects.length}</SectionTitle>
        </div>
      )}
      {effects.length > 0 && (
        <ul className="flex flex-col">
          {effects.map((effect, index) => {
            const resolvedDragIndex = dragIndex ?? -1;
            const isDragging = dragIndex === index;
            const isDropTarget =
              dropIndex === index && dragIndex !== null && dragIndex !== index;
            const showTopDropIndicator =
              isDropTarget && index < resolvedDragIndex;
            const showBottomDropIndicator =
              isDropTarget && index > resolvedDragIndex;

            return (
              <li
                key={effect.id}
                draggable
                onDragStart={() => handleDragStart({ index })}
                onDragOver={(event) => handleDragOver({ event, index })}
                onDrop={() => handleDrop({ toIndex: index })}
                onDragEnd={handleDragEnd}
                className={cn(
                  "group list-none",
                  isDragging && "opacity-40",
                  showTopDropIndicator && "border-t-2 border-primary",
                  showBottomDropIndicator && "border-b-2 border-primary",
                )}
              >
                <EffectSection
                  effect={effect}
                  renderParams={getRenderParams({ effectId: effect.id })}
                  previewParam={buildPreviewParam(effect.id)}
                  onCommit={commit}
                  onToggle={() =>
                    editor.timeline.toggleClipEffect({
                      trackId,
                      elementId: element.id,
                      effectId: effect.id,
                    })
                  }
                  onRemove={() =>
                    editor.timeline.removeClipEffect({
                      trackId,
                      elementId: element.id,
                      effectId: effect.id,
                    })
                  }
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// fluma: add effects right here. With a host effect provider (Craft-backed in
// Fluma) the provider's catalogue is shown and applied server-side; without
// one, the built-in in-browser effects are offered.
function AddEffectArea({
  element,
  trackId,
}: {
  element: VisualElement;
  trackId: string;
}) {
  const editor = useEditor();
  const provider = useEffectProvider();
  const target = effectTargetFor(element.type);

  if (provider && target) {
    return (
      <div className="border-b border-white/5 p-3">
        <ProvidedEffectBrowser
          provider={provider}
          target={target}
          elementId={element.id}
          compact
        />
      </div>
    );
  }

  const builtins = effectsRegistry.getAll();
  return (
    <div className="flex flex-col gap-2 border-b border-white/5 p-3">
      <span className="text-xs text-muted-foreground">효과 추가</span>
      <div className="flex flex-wrap gap-1.5">
        {builtins.map((definition) => (
          <Button
            key={definition.type}
            variant="secondary"
            size="sm"
            className="h-7 gap-1 text-xs"
            onClick={() =>
              editor.timeline.addClipEffect({
                trackId,
                elementId: element.id,
                effectType: definition.type,
              })
            }
          >
            <HugeiconsIcon icon={MagicWand05Icon} className="size-3.5" />
            {definition.name}
          </Button>
        ))}
      </div>
    </div>
  );
}

function EffectSection({
  effect,
  renderParams,
  previewParam,
  onCommit,
  onToggle,
  onRemove,
}: {
  effect: Effect;
  renderParams: ParamValues;
  previewParam: (key: string) => (value: number | string | boolean) => void;
  onCommit: () => void;
  onToggle?: () => void;
  onRemove?: () => void;
}) {
  const definition = effectsRegistry.get(effect.type);

  return (
    <Section
      sectionKey={onToggle ? `clip-effect:${effect.id}` : undefined}
      showTopBorder={false}
    >
      <SectionHeader
        className={cn(onToggle && "cursor-move")}
        trailing={
          onToggle && (
            <div className="flex items-center gap-1">
              <Button
                variant={effect.enabled ? "secondary" : "ghost"}
                size="icon"
                aria-label={`${definition.name} 켜기/끄기`}
                onClick={onToggle}
              >
                <HugeiconsIcon
                  icon={effect.enabled ? ViewIcon : ViewOffSlashIcon}
                />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`${definition.name} 삭제`}
                onClick={onRemove}
              >
                <HugeiconsIcon icon={Delete02Icon} />
              </Button>
            </div>
          )
        }
      >
        <SectionTitle
          className={cn(onToggle && !effect.enabled && "text-muted-foreground")}
        >
          {definition.name}
        </SectionTitle>
      </SectionHeader>
      <SectionContent
        className={cn("p-0", onToggle && !effect.enabled && "opacity-50")}
      >
        <SectionFields>
          {definition.params.map((param) => (
            <div key={param.key} className="flex flex-col gap-3.5">
              <div className="px-4">
                <PropertyParamField
                  param={param}
                  value={renderParams[param.key] ?? param.default}
                  onPreview={previewParam(param.key)}
                  onCommit={onCommit}
                />
              </div>
              <Separator />
            </div>
          ))}
        </SectionFields>
      </SectionContent>
    </Section>
  );
}
