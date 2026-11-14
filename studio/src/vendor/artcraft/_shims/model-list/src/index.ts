// FLUMA SHIM for @storyteller/model-list (upstream: frontend/libs/model-list @ 84a6a7d).
// Upstream pulls a live model catalog from ArtCraft cloud via @storyteller/tauri-utils.
// Fluma keeps the upstream model *classes* verbatim (so types stay compatible) and
// swaps the catalog for a small Fluma list. Not exported here (add only if a lib needs it):
// VideoModel, SplatModel, Object3DModel, creator icons, backend listing loader.
export * from "./lib/classes/Model.js";
export * from "./lib/classes/ImageModel.js";
export * from "./lib/classes/properties/CommonAspectRatio.js";
export * from "./lib/classes/properties/CommonResolution.js";
export * from "./lib/classes/properties/CommonQuality.js";
export * from "./lib/classes/metadata/ModelCreator.js";
export * from "./lib/classes/metadata/ModelTag.js";
export * from "./lib/classes/metadata/ModelFamilies.js";
export * from "./lib/classes/metadata/SizeOption.js";
export * from "./lib/legacy/ModelConfig.js";
export * from "./lib/legacy/ModelInfo.js";
export * from "./lib/lists/FlumaImageModels.js";

import type { ReactNode } from "react";
import type { ModelCreator } from "./lib/classes/metadata/ModelCreator.js";

/** Upstream returns brand logos; Fluma shows no third-party brand marks. */
export const getCreatorIcon = (_creator: ModelCreator): ReactNode => null;
export const getCreatorListIcon = (_creator: ModelCreator): ReactNode => null;
