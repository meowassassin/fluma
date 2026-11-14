// FLUMA SHIM for @storyteller/ui-promptbox (upstream: frontend/libs/components/promptbox @ 84a6a7d).
// Upstream PromptBox* talk to ArtCraft cloud (uploads, toaster, billing). Fluma keeps:
// - the store types/hooks verbatim (RefImage, Prompt2DStore, usePrompt2DStore, usePrompt3DStore),
// - AspectRatioIcon/AutoIcon (pure SVG, copied verbatim → ./AspectRatioIcon.tsx),
// - PromptBox2D as a minimal Fluma-tone prompt (textarea + generate) calling onGenerateClick.
// Reference-image upload, fullscreen, count picker etc. are left for the host adapter (Phase 2).
import { useState, type ReactNode } from "react";
import { create, type StoreApi, type UseBoundStore } from "zustand";
import type { ImageModel } from "@storyteller/model-list";
import type { GenerationProvider } from "@storyteller/api-enums";
import type { UploadMediaFn } from "@storyteller/api";
import { Button } from "@storyteller/ui-button";

export { AspectRatioIcon, AutoIcon } from "./AspectRatioIcon";

export interface RefImage {
  id: string;
  url: string;
  fullUrl?: string;
  file: File;
  mediaToken: string;
}

type AspectRatio = "wide" | "tall" | "square";
type Resolution = "1k" | "2k" | "4k";

export interface Prompt2DStore {
  prompt: string;
  aspectRatio: AspectRatio;
  resolution: Resolution;
  useSystemPrompt: boolean;
  referenceImages: RefImage[];
  generationCount: number;
  setPrompt: (prompt: string) => void;
  setAspectRatio: (ratio: AspectRatio) => void;
  setResolution: (resolution: Resolution) => void;
  setUseSystemPrompt: (value: boolean) => void;
  setReferenceImages: (images: RefImage[]) => void;
  setGenerationCount: (count: number) => void;
}

export const usePrompt2DStore = create<Prompt2DStore>()((set) => ({
  prompt: "",
  aspectRatio: "wide",
  resolution: "1k",
  useSystemPrompt: true,
  referenceImages: [],
  generationCount: 1,
  setPrompt: (prompt) => set({ prompt }),
  setAspectRatio: (aspectRatio) => set({ aspectRatio }),
  setResolution: (resolution) => set({ resolution }),
  setUseSystemPrompt: (useSystemPrompt) => set({ useSystemPrompt }),
  setReferenceImages: (referenceImages) => set({ referenceImages }),
  setGenerationCount: (generationCount) => set({ generationCount }),
}));
export { usePrompt2DStore as usePromptStore };

export type UploadImageFn = UploadMediaFn;

export interface PromptBox2DProps {
  uploadImage?: UploadImageFn;
  selectedImageModel?: ImageModel;
  selectedProvider?: GenerationProvider;
  EncodeImageBitmapToBase64: (imageBitmap: ImageBitmap) => Promise<string>;
  onGenerateClick: (
    prompt: string,
    options?: { aspectRatio?: string; resolution?: string; images?: RefImage[]; selectedProvider?: GenerationProvider },
  ) => void | Promise<void>;
  isDisabled?: boolean;
  isEnqueueing?: boolean;
  generationCount?: number;
  onGenerationCountChange?: (count: number) => void;
  onAspectRatioChange?: (ratio: AspectRatio) => void;
  onFitPressed?: () => void | Promise<void>;
  usePrompt2DStore: UseBoundStore<StoreApi<Prompt2DStore>>;
  modelSelector?: ReactNode;
}

export const PromptBox2D = ({
  selectedProvider,
  onGenerateClick,
  isDisabled = false,
  isEnqueueing = false,
  usePrompt2DStore: useStore,
  modelSelector,
}: PromptBox2DProps) => {
  const prompt = useStore((s) => s.prompt);
  const setPrompt = useStore((s) => s.setPrompt);
  const aspectRatio = useStore((s) => s.aspectRatio);
  const resolution = useStore((s) => s.resolution);
  const images = useStore((s) => s.referenceImages);
  const [busy, setBusy] = useState(false);
  const disabled = isDisabled || isEnqueueing || busy || !prompt.trim();
  const submit = async () => {
    if (disabled) return;
    setBusy(true);
    try {
      await onGenerateClick(prompt, { aspectRatio, resolution, images, selectedProvider });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="glass flex w-[640px] max-w-full flex-col gap-2 p-3">
      <textarea
        className="promptbox-scrollbar min-h-[56px] w-full resize-none bg-transparent text-sm text-base-fg outline-none placeholder:text-base-fg/50"
        placeholder="무엇을 만들까요?"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
        }}
      />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">{modelSelector}</div>
        <Button variant="primary" disabled={disabled} onClick={() => void submit()}>
          {isEnqueueing || busy ? "생성 중…" : "생성"}
        </Button>
      </div>
    </div>
  );
};
