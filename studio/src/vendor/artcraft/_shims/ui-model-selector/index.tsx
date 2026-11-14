// FLUMA SHIM for @storyteller/ui-model-selector (upstream: frontend/libs/components/model-selector @ 84a6a7d).
// Upstream hydrates the model list from ArtCraft cloud through @storyteller/tauri-api
// (useImageModels/useVideoModels) and shows provider/billing pickers. Fluma:
// - model list = the static Fluma list from the model-list shim (Nano Banana via Antigravity),
// - store/hook API kept identical (zustand), provider selection hidden,
// - ClassyModelSelector = a plain Fluma-tone PopoverMenu (no provider submenu, no brand icons).
import { useEffect, useMemo } from "react";
import { create } from "zustand";
import { ImageIcon } from "lucide-react";
import { PopoverMenu, type PopoverItem } from "@storyteller/ui-popover";
import { IMAGE_MODELS, IMAGE_MODELS_BY_ID, type ImageModel, type Model } from "@storyteller/model-list";
import { GenerationProvider } from "@storyteller/api-enums";

export enum ModelPage {
  TextToImage = "text-to-image",
  ImageToVideo = "image-to-video",
  Canvas2D = "canvas-2d",
  Stage3D = "stage-3d",
  ImageEditor = "image-editor",
  ImageTo3DWorld = "image-to-3d-world",
  ImageTo3DObject = "image-to-3d-object",
  Angles = "angles",
}

export type ModelList = Omit<PopoverItem, "selected">[];

interface ClassyModelSelectorState {
  selectedModels: { [page in ModelPage]?: Model };
  selectedProviders: { [page in ModelPage]?: { [modelId: string]: GenerationProvider } };
  setSelectedModel: (page: ModelPage, model: Model) => void;
  setSelectedProvider: (page: ModelPage, modelId: string, provider: GenerationProvider) => void;
}

export const useClassyModelSelectorStore = create<ClassyModelSelectorState>((set) => ({
  selectedModels: {},
  selectedProviders: {},
  setSelectedModel: (page, model) => set((s) => ({ selectedModels: { ...s.selectedModels, [page]: model } })),
  setSelectedProvider: (page, modelId, provider) =>
    set((s) => ({
      selectedProviders: { ...s.selectedProviders, [page]: { ...(s.selectedProviders[page] ?? {}), [modelId]: provider } },
    })),
}));

export const getSelectedImageModel = (page: ModelPage): ImageModel | undefined => {
  const m = useClassyModelSelectorStore.getState().selectedModels[page];
  return m?.kind === "image_model" ? (m as ImageModel) : undefined;
};
export const getSelectedProviderForModel = (page: ModelPage, modelId: string): GenerationProvider | undefined =>
  useClassyModelSelectorStore.getState().selectedProviders[page]?.[modelId];

export const useSelectedModel = (page: ModelPage): Model | undefined =>
  useClassyModelSelectorStore((s) => s.selectedModels[page]);
export const useSelectedImageModel = (page: ModelPage): ImageModel | undefined => {
  const m = useSelectedModel(page);
  return m?.kind === "image_model" ? (m as ImageModel) : undefined;
};
export const useSelectedProviderForModel = (page: ModelPage, modelId: string | undefined): GenerationProvider | undefined =>
  useClassyModelSelectorStore((s) => (modelId ? s.selectedProviders[page]?.[modelId] : undefined));

const DEFAULT_MODEL_ID_FOR_PAGE: Partial<Record<ModelPage, string>> = {
  [ModelPage.TextToImage]: "nano_banana_pro",
  [ModelPage.Canvas2D]: "nano_banana_pro",
  [ModelPage.Stage3D]: "nano_banana_pro",
  [ModelPage.ImageEditor]: "nano_banana_pro",
};

export const defaultModelForPage = (models: Model[], page: ModelPage): Model => {
  const id = DEFAULT_MODEL_ID_FOR_PAGE[page];
  if (id) {
    const fromList = models.find((m) => m.id === id || m.tauriId === id);
    if (fromList) return fromList;
    const fromStatic = IMAGE_MODELS_BY_ID.get(id);
    if (fromStatic) return fromStatic;
  }
  return models[0] ?? IMAGE_MODELS[0];
};

const buildItems = (models: Model[]): ModelList =>
  models.map((model) => ({
    label: model.selectorName,
    icon: <ImageIcon className="h-4 w-4" />,
    description: model.selectorDescription,
    modelConfig: model.toLegacyModelConfig(),
    model,
  }));

const useImagePageList = (): ModelList => useMemo(() => buildItems(IMAGE_MODELS), []);
export const useTextToImagePageModelList = useImagePageList;
export const useCanvas2dPageModelList = useImagePageList;
export const useStage3dPageModelList = useImagePageList;
export const useImageEditorPageModelList = useImagePageList;

interface ClassyModelSelectorProps {
  items: Omit<PopoverItem, "selected">[];
  page: ModelPage;
  mode?: "hoverSelect" | "default" | "toggle" | "button";
  panelTitle?: string;
  buttonClassName?: string;
  panelClassName?: string;
  showIconsInList?: boolean;
  triggerLabel?: string;
  /** Upstream: per-model Tauri providers. Ignored in Fluma. */
  providersByModel?: Partial<Record<string, unknown[]>>;
  providerTooltipDelayMs?: number;
  maxListHeight?: number | string;
  variant?: "floating" | "embedded";
  showProviderSelection?: boolean;
}

const sameModel = (a?: Model, b?: Model) => !!a && !!b && a.tauriId === b.tauriId;

export function ClassyModelSelector({
  items,
  page,
  mode = "toggle",
  panelTitle = "모델",
  buttonClassName,
  panelClassName,
  maxListHeight = "60vh",
}: ClassyModelSelectorProps) {
  const selectedModels = useClassyModelSelectorStore((s) => s.selectedModels);
  const setSelectedModel = useClassyModelSelectorStore((s) => s.setSelectedModel);
  const itemModels = items.map((i) => i.model).filter((m): m is Model => m !== undefined);
  const selected = selectedModels[page] ?? (itemModels.length ? defaultModelForPage(itemModels, page) : undefined);

  useEffect(() => {
    if (!selectedModels[page] && itemModels.length) setSelectedModel(page, defaultModelForPage(itemModels, page));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const list = items.map((i) => ({ ...i, selected: sameModel(i.model, selected) }) as PopoverItem);
  return (
    <PopoverMenu
      items={list}
      onSelect={(item) => item.model && setSelectedModel(page, item.model)}
      mode={mode}
      richList
      panelTitle={panelTitle}
      buttonClassName={buttonClassName}
      panelClassName={panelClassName}
      maxListHeight={maxListHeight}
    />
  );
}
