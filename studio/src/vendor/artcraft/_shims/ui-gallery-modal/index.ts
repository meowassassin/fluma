// FLUMA SHIM for @storyteller/ui-gallery-modal (upstream: frontend/libs/components/gallery-modal @ 84a6a7d).
// Upstream = ArtCraft cloud media library (lists/uploads via @storyteller/api + Tauri).
// Fluma keeps only the host-agnostic pieces the editors import:
// - GalleryItem type, the window-event drop bus (emit/on/remove), the modal signals,
// - DragGhost (pure UI, copied verbatim).
// The gallery modal itself is NOT provided; Fluma's asset browser emits drops via emitImageDrop().
import { signal } from "@preact/signals-react";

export { DragGhost } from "./DragGhost";
export type { DragGhostState } from "./DragGhost";

export interface GalleryItem {
  id: string;
  label: string;
  thumbnail: string | null;
  thumbnailUrlTemplate?: string;
  fullImage?: string | null;
  createdAt: string;
  mediaClass?: string;
  assetType?: string;
  isUpload?: boolean;
  batchImageToken?: string;
  mediaTokens?: string[];
  imageUrls?: string[];
  promptToken?: string;
  durationMillis?: number;
}

export const galleryModalVisibleDuringDrag = signal(true);
export const galleryReopenAfterDragSignal = signal(false);
export const galleryModalVisibleViewMode = signal(false);
export const galleryModalDraggingUnder = signal(false);
export const galleryDragHidesImmediately = signal(false);
export const galleryModalLightboxMediaId = signal<string | null>(null);
export const galleryModalLightboxVisible = signal(false);
export const galleryModalLightboxImage = signal<any>(null);

export const IMAGE_DROP_EVENT = "gallery-image-drop";
export const FOLDER_DROP_EVENT = "gallery-folder-drop";

export function emitImageDrop(item: GalleryItem, position: { x: number; y: number }) {
  window.dispatchEvent(new CustomEvent(IMAGE_DROP_EVENT, { detail: { item, position } }));
}

export function onImageDrop(callback: (item: GalleryItem, position: { x: number; y: number }) => void) {
  const handler = (e: any) => callback(e.detail.item, e.detail.position);
  window.addEventListener(IMAGE_DROP_EVENT, handler);
  return handler;
}

export function removeImageDropListener(handler: (e: any) => void) {
  window.removeEventListener(IMAGE_DROP_EVENT, handler);
}
