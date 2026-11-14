import {
  masksRegistry,
  type MaskDefinitionForRegistration,
  type MaskIconProps,
} from "../../registry";
import { cinematicBarsMaskDefinition } from "./cinematic-bars";
import { diamondMaskDefinition } from "./diamond";
import { ellipseMaskDefinition } from "./ellipse";
import { freeformMaskDefinition } from "../../freeform/definition";
import { heartMaskDefinition } from "./heart";
import { rectangleMaskDefinition } from "./rectangle";
import { splitMaskDefinition } from "./split";
import { starMaskDefinition } from "./star";
import { textMaskDefinition } from "./text";
// fluma: real icons — upstream registers `icon: null`, and HugeiconsIcon throws
// "currentIcon is not iterable" when the Add-mask menu renders (whole editor
// fell into the error boundary).
import {
  CircleIcon,
  DiamondIcon,
  FavouriteIcon,
  Layout2ColumnIcon,
  Layout2RowIcon,
  PenTool01Icon,
  Square01Icon,
  StarIcon,
  TextIcon,
} from "@hugeicons/core-free-icons";

// All 9 built-in mask definitions are registered: split / cinematic-bars,
// 6 closed-shape masks (rectangle, ellipse, heart, diamond, star, text),
// and the freeform pen-tool mask. Host code passes whatever icon
// component it likes via the loose MaskIconProps contract.

function registerDefaultMask({
  definition,
  icon,
}: {
  definition: MaskDefinitionForRegistration;
  icon: MaskIconProps;
}) {
  if (masksRegistry.has(definition.type)) {
    return;
  }

  masksRegistry.registerMask({ definition, icon });
}

// Idempotent — safe to call multiple times (per-definition has() check).
// Icon values are `unknown` placeholders; the host substitutes its own
// icon components when wiring the panel.
export function registerDefaultMasks(): void {
  registerDefaultMask({
    definition: splitMaskDefinition,
    icon: { icon: Layout2ColumnIcon, strokeWidth: 1 },
  });
  registerDefaultMask({
    definition: cinematicBarsMaskDefinition,
    icon: { icon: Layout2RowIcon },
  });
  registerDefaultMask({
    definition: rectangleMaskDefinition,
    icon: { icon: Square01Icon },
  });
  registerDefaultMask({
    definition: ellipseMaskDefinition,
    icon: { icon: CircleIcon },
  });
  registerDefaultMask({
    definition: heartMaskDefinition,
    icon: { icon: FavouriteIcon },
  });
  registerDefaultMask({
    definition: diamondMaskDefinition,
    icon: { icon: DiamondIcon },
  });
  registerDefaultMask({
    definition: starMaskDefinition,
    icon: { icon: StarIcon },
  });
  registerDefaultMask({
    definition: textMaskDefinition,
    icon: { icon: TextIcon },
  });
  registerDefaultMask({
    definition: freeformMaskDefinition,
    icon: { icon: PenTool01Icon },
  });
}

export {
  cinematicBarsMaskDefinition,
  diamondMaskDefinition,
  ellipseMaskDefinition,
  freeformMaskDefinition,
  heartMaskDefinition,
  rectangleMaskDefinition,
  splitMaskDefinition,
  starMaskDefinition,
  textMaskDefinition,
};
