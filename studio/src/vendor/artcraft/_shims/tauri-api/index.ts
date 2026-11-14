// FLUMA SHIM for @storyteller/tauri-api (upstream: frontend/libs/tauri-api @ 84a6a7d).
// Upstream = Tauri `invoke` bindings into the ArtCraft desktop app (generation, billing,
// provider accounts, model catalog). None of the Phase 0 closure or the four target libs
// import it directly; this stub exists so a stray import fails loudly instead of resolving
// to nothing. Extend with exact symbols only when a later phase needs one.
import type { ImageModel } from "@storyteller/model-list";
import { IMAGE_MODELS } from "@storyteller/model-list";

const disabled = (name: string) => new Error(`ArtCraft cloud not used in Fluma: tauri-api.${name}`);

/** Upstream Provider is a string enum of provider accounts; Fluma has none. */
export type Provider = string;

/** Upstream hook hydrates from the backend; Fluma returns the static Fluma list. */
export const useImageModels = (): ImageModel[] => IMAGE_MODELS;
export const useVideoModels = (): never[] => [];

export async function invokeTauri(name: string): Promise<never> {
  throw disabled(name);
}
