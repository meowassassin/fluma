// FLUMA SHIM for @storyteller/ui-pricing-modal (upstream: frontend/libs/components/pricing-modal @ 84a6a7d).
// Upstream = ArtCraft credits/billing UI backed by the cloud. Fluma has no credits:
// the store keeps the same shape (so callers type-check and can still write estimates),
// and CostCalculatorButton renders nothing.
import { create } from "zustand";
import type { ModelPage } from "@storyteller/ui-model-selector";

interface CostBreakdownModalState {
  isOpen: boolean;
  openModal: () => void;
  closeModal: () => void;
  toggleModal: () => void;
  estimatedCreditsByPage: Partial<Record<ModelPage, number | null>>;
  setEstimatedCreditsForPage: (page: ModelPage, credits: number | null) => void;
}

export const useCostBreakdownModalStore = create<CostBreakdownModalState>((set) => ({
  isOpen: false,
  openModal: () => {},
  closeModal: () => set({ isOpen: false }),
  toggleModal: () => {},
  estimatedCreditsByPage: {},
  setEstimatedCreditsForPage: (page, credits) =>
    set((s) => ({ estimatedCreditsByPage: { ...s.estimatedCreditsByPage, [page]: credits } })),
}));

export interface CostCalculatorButtonProps {
  className?: string;
  modelPage?: ModelPage;
}

/** No credits in Fluma — intentionally renders nothing. */
export function CostCalculatorButton(_props: CostCalculatorButtonProps) {
  return null;
}
export default CostCalculatorButton;
