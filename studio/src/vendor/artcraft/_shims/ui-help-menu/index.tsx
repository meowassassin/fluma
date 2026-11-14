// FLUMA SHIM for @storyteller/ui-help-menu (upstream: frontend/libs/components/help-menu @ 84a6a7d).
// Upstream shows ArtCraft tutorial videos/news (YouTube + ArtCraft-hosted thumbnails).
// Fluma has its own help; this renders nothing.
export type TutorialItem = {
  id: string;
  title: string;
  thumbnailUrl: string;
  videoUrl: string;
  category?: string;
};

export type HelpMenuButtonProps = {
  items?: TutorialItem[];
  panelTitle?: string;
  className?: string;
  onOpenChange?: (open: boolean) => void;
};

export function HelpMenuButton(_props: HelpMenuButtonProps) {
  return null;
}
