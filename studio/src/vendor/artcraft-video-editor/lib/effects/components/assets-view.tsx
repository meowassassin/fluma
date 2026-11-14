"use client";

// fluma: Effects panel. With a host effect provider (Fluma: Craft apps on the
// server) it lists the provider's catalogue — searchable, grouped, thumbnails —
// and applies the clicked effect to the selected video / image / text element.
// Without a provider it shows the built-in in-browser effects (blur), which can
// be dragged onto the timeline as an effect clip or applied to the selection.
import { useCallback, useEffect, useState } from "react";
import { PanelView } from "../../panels/assets/views/base-panel";
import { DraggableItem } from "../../panels/assets/draggable-item";
import { effectsRegistry, EFFECT_TARGET_ELEMENT_TYPES } from "../";
import { useEditor } from "../../editor/use-editor";
import { buildEffectElement } from "../../timeline/element-utils";
import type { EffectDefinition } from "../types";
import {
  EFFECT_TARGET_LABELS,
  ProvidedEffectBrowser,
  effectTargetFor,
  useEffectProvider,
  type EffectTarget,
} from "../provider";
import { cn } from "../../utils/ui";

function useSelectedSingleElement() {
  const editor = useEditor();
  const selected = useEditor((e) => e.selection.getSelectedElements());
  useEditor((e) => e.scenes.getActiveSceneOrNull());
  if (selected.length !== 1) return null;
  const [withTrack] = editor.timeline.getElementsWithTracks({ elements: selected });
  return withTrack ?? null;
}

export function EffectsView() {
  const provider = useEffectProvider();
  return (
    <PanelView title="효과">
      {provider ? <ProviderEffects /> : <BuiltinEffects />}
    </PanelView>
  );
}

function ProviderEffects() {
  const provider = useEffectProvider()!;
  const selection = useSelectedSingleElement();
  const selectedTarget = effectTargetFor(selection?.element.type);
  const [target, setTarget] = useState<EffectTarget>(selectedTarget ?? "video");

  useEffect(() => {
    if (selectedTarget) setTarget(selectedTarget);
  }, [selectedTarget]);

  const elementId =
    selection && selectedTarget === target ? selection.element.id : null;

  return (
    <div className="flex flex-col gap-2.5 pb-3">
      <div className="flex gap-1 rounded-md bg-accent/50 p-0.5">
        {(Object.keys(EFFECT_TARGET_LABELS) as EffectTarget[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTarget(key)}
            className={cn(
              "h-7 flex-1 rounded text-xs",
              key === target ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {EFFECT_TARGET_LABELS[key]}
          </button>
        ))}
      </div>
      {selection && elementId && (
        <p className="truncate px-0.5 text-xs text-muted-foreground">
          적용 대상: <span className="text-foreground">{selection.element.name}</span>
        </p>
      )}
      <ProvidedEffectBrowser provider={provider} target={target} elementId={elementId} />
    </div>
  );
}

function BuiltinEffects() {
  const effects = effectsRegistry.getAll();
  return (
    <div className="flex flex-col gap-2.5 pb-3">
      <p className="px-0.5 text-xs text-muted-foreground">
        카드를 누르면 선택한 클립 · 자막에 적용되고, 선택한 항목이 없으면 효과 클립으로 추가됩니다. 타임라인으로 끌어 놓아도 됩니다.
      </p>
      <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(92px, 1fr))" }}>
        {effects.map((effect) => (
          <EffectItem key={effect.type} effect={effect} />
        ))}
      </div>
    </div>
  );
}

function EffectItem({ effect }: { effect: EffectDefinition }) {
  const editor = useEditor();
  const selection = useSelectedSingleElement();

  const handleAdd = useCallback(() => {
    if (selection && effectTargetFor(selection.element.type)) {
      editor.timeline.addClipEffect({
        trackId: selection.track.id,
        elementId: selection.element.id,
        effectType: effect.type,
      });
      return;
    }
    const element = buildEffectElement({
      effectType: effect.type,
      startTime: editor.playback.getCurrentTime(),
    });
    editor.timeline.insertElement({
      placement: { mode: "auto", trackType: "effect" },
      element,
    });
  }, [editor, effect.type, selection]);

  // Static thumbnail: a sample frame with a CSS approximation of the effect.
  const preview = (
    <div
      className="size-full rounded-md"
      style={{
        background:
          "radial-gradient(circle at 50% 42%, #fff 0 22%, transparent 23%), linear-gradient(135deg, #3b82f6, #ec4899 55%, #f59e0b)",
        filter: effect.type === "blur" ? "blur(4px)" : undefined,
      }}
    />
  );

  return (
    <DraggableItem
      name={effect.name}
      preview={preview}
      dragData={{
        id: effect.type,
        name: effect.name,
        type: "effect",
        effectType: effect.type,
        targetElementTypes: EFFECT_TARGET_ELEMENT_TYPES,
      }}
      onAddToTimeline={handleAdd}
      aspectRatio={1}
      isRounded
      variant="card"
      containerClassName="w-full"
    />
  );
}
