// FLUMA SHIM — replaces upstream `lists/ImageModels.ts` (ArtCraft cloud catalog).
// Fluma does not call ArtCraft cloud/Omni. These entries only describe what the
// host can generate; the actual call goes through each lib's adapter (Phase 2+),
// e.g. Nano Banana via the Antigravity agent runtime.
import { GenerationProvider } from "@storyteller/api-enums";
import { ImageModel } from "../classes/ImageModel.js";
import { ModelCreator } from "../classes/metadata/ModelCreator.js";
import { ModelTag } from "../classes/metadata/ModelTag.js";
import { CommonAspectRatio } from "../classes/properties/CommonAspectRatio.js";
import { CommonResolution } from "../classes/properties/CommonResolution.js";

const ASPECTS = [
  CommonAspectRatio.Auto,
  CommonAspectRatio.Square,
  CommonAspectRatio.TallNineBySixteen,
  CommonAspectRatio.WideSixteenByNine,
  CommonAspectRatio.TallThreeByFour,
  CommonAspectRatio.WideFourByThree,
];

export const IMAGE_MODELS: ImageModel[] = [
  new ImageModel({
    id: "nano_banana_pro",
    tauriId: "nano_banana_pro",
    fullName: "Nano Banana Pro (Antigravity)",
    category: "image",
    creator: ModelCreator.Google,
    // NB: provider is informational only in Fluma — the host adapter decides the route.
    providers: [GenerationProvider.Artcraft],
    selectorName: "Nano Banana",
    selectorDescription: "Antigravity 에이전트로 생성 · 편집",
    selectorBadges: ["Antigravity"],
    maxGenerationCount: 4,
    defaultGenerationCount: 1,
    canEditImages: true,
    canUseImagePrompt: true,
    maxImagePromptCount: 6,
    canChangeAspectRatio: true,
    canChangeResolution: true,
    aspectRatios: ASPECTS,
    defaultAspectRatio: CommonAspectRatio.TallNineBySixteen,
    resolutions: [CommonResolution.OneK, CommonResolution.TwoK],
    tags: [ModelTag.InstructiveEdit, ModelTag.NonMaskedInpainting],
    progressBarTime: 30000,
  }),
  new ImageModel({
    id: "nano_banana",
    tauriId: "nano_banana",
    fullName: "Nano Banana (Antigravity)",
    category: "image",
    creator: ModelCreator.Google,
    providers: [GenerationProvider.Artcraft],
    selectorName: "Nano Banana (빠름)",
    selectorDescription: "빠른 초안용",
    selectorBadges: ["Antigravity"],
    maxGenerationCount: 4,
    defaultGenerationCount: 1,
    canEditImages: true,
    canUseImagePrompt: true,
    maxImagePromptCount: 3,
    canChangeAspectRatio: true,
    aspectRatios: ASPECTS,
    defaultAspectRatio: CommonAspectRatio.TallNineBySixteen,
    tags: [ModelTag.InstructiveEdit, ModelTag.NonMaskedInpainting],
    progressBarTime: 15000,
  }),
];

export const IMAGE_MODELS_BY_ID: Map<string, ImageModel> = new Map(
  IMAGE_MODELS.map((m) => [m.id, m]),
);
