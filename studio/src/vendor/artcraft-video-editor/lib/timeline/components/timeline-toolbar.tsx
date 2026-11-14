import { useEditor } from "../../editor/use-editor";
import { useElementSelection } from "../hooks/element/use-element-selection";
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "../../components/ui/tooltip";
import { Button } from "../../components/ui/button";
import {
  SplitButton,
  SplitButtonLeft,
  SplitButtonRight,
  SplitButtonSeparator,
} from "../../components/ui/split-button";
import { Slider } from "../../components/ui/slider";
import { TIMELINE_ZOOM_BUTTON_FACTOR } from "./interaction";
import { TIMELINE_ZOOM_MAX } from "../scale";
import { sliderToZoom, zoomToSlider } from "../zoom-utils";
import { ScenesView } from "../../components/editor/scenes-view";
import { type TActionWithOptionalArgs, invokeAction } from "../../actions";
import {
  canToggleSourceAudio,
  getSourceAudioActionLabel,
  isSourceAudioSeparated,
} from "../audio-separation";
import { hasMediaId } from "../element-utils";
import { cn } from "../../utils/ui";
import { useTimelineStore } from "../timeline-store";
import { ScrollArea } from "../../components/ui/scroll-area";
import {
  Bookmark02Icon,
  Delete02Icon,
  SnowIcon,
  ScissorIcon,
  MagnetIcon,
  SearchAddIcon,
  SearchMinusIcon,
  Copy01Icon,
  AlignLeftIcon,
  AlignRightIcon,
  Link02Icon,
  Layers01Icon,
  Chart03Icon,
  Unlink02Icon,
  UndoIcon,
  RedoIcon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { OcRippleIcon } from "../../components/icons";
import { GraphEditorPopover } from "./graph-editor/popover";
import { PopoverTrigger } from "../../components/ui/popover";
import { useGraphEditorController } from "./graph-editor/use-controller";
import { usePanelStore } from "../../editor/panel-store";
import { ChevronDown } from "lucide-react";

export function TimelineToolbar({
  zoomLevel,
  minZoom,
  setZoomLevel,
}: {
  zoomLevel: number;
  minZoom: number;
  setZoomLevel: ({ zoom }: { zoom: number }) => void;
}) {
  const handleZoom = ({ direction }: { direction: "in" | "out" }) => {
    const newZoomLevel =
      direction === "in"
        ? Math.min(TIMELINE_ZOOM_MAX, zoomLevel * TIMELINE_ZOOM_BUTTON_FACTOR)
        : Math.max(minZoom, zoomLevel / TIMELINE_ZOOM_BUTTON_FACTOR);
    setZoomLevel({ zoom: newZoomLevel });
  };

  return (
    <ScrollArea className="scrollbar-hidden">
      <div className="flex h-10 items-center justify-between border-b px-2 py-1 border-ui-panel-border">
        <ToolbarLeftSection />

        <SceneSelector />

        <ToolbarRightSection
          zoomLevel={zoomLevel}
          minZoom={minZoom}
          onZoomChange={(zoom) => setZoomLevel({ zoom })}
          onZoom={handleZoom}
        />
      </div>
    </ScrollArea>
  );
}

function ToolbarLeftSection() {
  const editor = useEditor();
  const mediaAssets = useEditor((currentEditor) =>
    currentEditor.media.getAssets(),
  );
  const { selectedElements } = useElementSelection();
  const graphEditor = useGraphEditorController();
  const isCurrentlyBookmarked = useEditor((e) =>
    e.scenes.isBookmarked({ time: e.playback.getCurrentTime() }),
  );
  const selectedElement =
    selectedElements.length === 1
      ? (editor.timeline.getElementsWithTracks({
          elements: selectedElements,
        })[0] ?? null)
      : null;
  const selectedMediaAsset = (() => {
    if (!selectedElement) {
      return null;
    }

    const { element } = selectedElement;
    if (!hasMediaId(element)) {
      return null;
    }

    return mediaAssets.find((asset) => asset.id === element.mediaId) ?? null;
  })();
  const canToggleSelectedSourceAudio =
    !!selectedElement &&
    canToggleSourceAudio(selectedElement.element, selectedMediaAsset);
  const sourceAudioLabel =
    selectedElement?.element.type === "video"
      ? getSourceAudioActionLabel({
          element: selectedElement.element,
        })
      : "소리 분리";
  const isSelectedSourceAudioSeparated =
    selectedElement?.element.type === "video" &&
    isSourceAudioSeparated({
      element: selectedElement.element,
    });

  const handleAction = ({
    action,
    event,
  }: {
    action: TActionWithOptionalArgs;
    event: React.MouseEvent;
  }) => {
    event.stopPropagation();
    invokeAction(action);
  };

  return (
    <div className="flex items-center gap-1">
      <TooltipProvider delayDuration={400}>
        <ToolbarButton
          icon={<HugeiconsIcon icon={UndoIcon} />}
          tooltip="실행 취소 (Ctrl+Z)"
          onClick={({ event }) => handleAction({ action: "undo", event })}
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={RedoIcon} />}
          tooltip="다시 실행 (Ctrl+Shift+Z)"
          onClick={({ event }) => handleAction({ action: "redo", event })}
        />

        <div className="h-4 w-px bg-border/50 mx-1" />

        <ToolbarButton
          icon={<HugeiconsIcon icon={ScissorIcon} />}
          tooltip="자르기 (S)"
          onClick={({ event }) => handleAction({ action: "split", event })}
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={AlignLeftIcon} />}
          tooltip="왼쪽 잘라내기"
          onClick={({ event }) => handleAction({ action: "split-left", event })}
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={AlignRightIcon} />}
          tooltip="오른쪽 잘라내기"
          onClick={({ event }) =>
            handleAction({ action: "split-right", event })
          }
        />

        <ToolbarButton
          icon={
            <HugeiconsIcon
              icon={isSelectedSourceAudioSeparated ? Unlink02Icon : Link02Icon}
            />
          }
          tooltip={sourceAudioLabel}
          disabled={!canToggleSelectedSourceAudio}
          onClick={({ event }) =>
            handleAction({ action: "toggle-source-audio", event })
          }
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={Copy01Icon} />}
          tooltip="복제"
          onClick={({ event }) =>
            handleAction({ action: "duplicate-selected", event })
          }
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={SnowIcon} />}
          tooltip="정지 화면 (준비 중)"
          disabled={true}
          onClick={({ event: _event }) => {}}
        />

        <ToolbarButton
          icon={<HugeiconsIcon icon={Delete02Icon} />}
          tooltip="삭제"
          onClick={({ event }) =>
            handleAction({ action: "delete-selected", event })
          }
        />

        <div className="bg-border mx-1 h-6 w-px" />

        <Tooltip>
          <ToolbarButton
            icon={<HugeiconsIcon icon={Bookmark02Icon} />}
            isActive={isCurrentlyBookmarked}
            tooltip={isCurrentlyBookmarked ? "북마크 지우기" : "북마크 추가"}
            onClick={({ event }) =>
              handleAction({ action: "toggle-bookmark", event })
            }
          />
        </Tooltip>

        <GraphEditorPopover
          open={graphEditor.open}
          onOpenChange={graphEditor.onOpenChange}
          value={
            graphEditor.state.status === "ready"
              ? graphEditor.state.cubicBezier
              : null
          }
          message={graphEditor.state.message}
          componentOptions={graphEditor.state.componentOptions}
          activeComponentKey={graphEditor.state.activeComponentKey}
          onActiveComponentKeyChange={graphEditor.onActiveComponentKeyChange}
          onPreviewValue={graphEditor.onPreviewValue}
          onCommitValue={graphEditor.onCommitValue}
          onCancelPreview={graphEditor.onCancelPreview}
        >
          <ToolbarButton
            icon={<HugeiconsIcon icon={Chart03Icon} />}
            tooltip={graphEditor.tooltip}
            disabled={!graphEditor.canOpen}
            buttonWrapper={(button) =>
              graphEditor.canOpen ? (
                <PopoverTrigger asChild>{button}</PopoverTrigger>
              ) : (
                button
              )
            }
          />
        </GraphEditorPopover>
      </TooltipProvider>
    </div>
  );
}

function SceneSelector() {
  const editor = useEditor();
  const currentScene = editor.scenes.getActiveScene();

  return (
    <div>
      <SplitButton className="border-foreground/10 border">
        <SplitButtonLeft>{currentScene?.isMain && currentScene.name === "Main scene" ? "메인 장면" : currentScene?.name || "장면 없음"}</SplitButtonLeft>
        <SplitButtonSeparator />
        <ScenesView>
          <SplitButtonRight onClick={() => {}}>
            <HugeiconsIcon icon={Layers01Icon} className="size-4" />
          </SplitButtonRight>
        </ScenesView>
      </SplitButton>
    </div>
  );
}

function ToolbarRightSection({
  zoomLevel,
  minZoom,
  onZoomChange,
  onZoom,
}: {
  zoomLevel: number;
  minZoom: number;
  onZoomChange: (zoom: number) => void;
  onZoom: (options: { direction: "in" | "out" }) => void;
}) {
  const snappingEnabled = useTimelineStore((s) => s.snappingEnabled);
  const rippleEditingEnabled = useTimelineStore((s) => s.rippleEditingEnabled);
  const toggleSnapping = useTimelineStore((s) => s.toggleSnapping);
  const toggleRippleEditing = useTimelineStore((s) => s.toggleRippleEditing);

  return (
    <div className="flex items-center gap-1">
      <TooltipProvider delayDuration={500}>
        <ToolbarButton
          icon={<HugeiconsIcon icon={MagnetIcon} />}
          isActive={snappingEnabled}
          tooltip="자석 맞춤"
          onClick={() => toggleSnapping()}
        />

        <ToolbarButton
          icon={<OcRippleIcon size={24} className="scale-110" />}
          isActive={rippleEditingEnabled}
          tooltip="리플 편집 (뒤 클립 당기기)"
          onClick={() => toggleRippleEditing()}
        />
      </TooltipProvider>

      <div className="bg-border mx-1 h-6 w-px" />

      <div className="flex items-center gap-1">
        <Button
          variant="text"
          size="icon"
          onClick={() => onZoom({ direction: "out" })}
        >
          <HugeiconsIcon icon={SearchMinusIcon} />
        </Button>
        <Slider
          className="w-28"
          value={[zoomToSlider({ zoomLevel, minZoom })]}
          onValueChange={(values) =>
            onZoomChange(sliderToZoom({ sliderPosition: values[0], minZoom }))
          }
          min={0}
          max={1}
          step={0.005}
        />
        <Button
          variant="text"
          size="icon"
          onClick={() => onZoom({ direction: "in" })}
        >
          <HugeiconsIcon icon={SearchAddIcon} />
        </Button>
      </div>

      <div className="bg-border mx-1 h-6 w-px" />

      <ToolbarButton
        icon={<ChevronDown className="size-4" />}
        tooltip="타임라인 접기 (Alt+T)"
        onClick={() => usePanelStore.getState().toggleTimelineCollapsed()}
      />
    </div>
  );
}

function ToolbarButton({
  icon,
  tooltip,
  onClick,
  disabled,
  isActive,
  buttonWrapper,
}: {
  icon: React.ReactNode;
  tooltip: string;
  onClick?: ({ event }: { event: React.MouseEvent }) => void;
  disabled?: boolean;
  isActive?: boolean;
  buttonWrapper?: (button: React.ReactElement) => React.ReactElement;
}) {
  const button = (
    <Button
      variant={isActive ? "secondary" : "text"}
      size="icon"
      disabled={disabled}
      onClick={onClick ? (event) => onClick({ event }) : undefined}
      className={cn(
        "rounded-lg",
        disabled ? "cursor-not-allowed opacity-50" : "",
      )}
    >
      {icon}
    </Button>
  );
  const trigger = disabled ? (
    <span className="inline-flex">{button}</span>
  ) : buttonWrapper ? (
    buttonWrapper(button)
  ) : (
    button
  );

  return (
    <Tooltip delayDuration={200}>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  );
}
