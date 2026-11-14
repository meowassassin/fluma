"use client";

import { useMemo, useState } from "react";
import { PanelView } from "./base-panel";
import { MediaDragOverlay } from "../drag-overlay";
import { DraggableItem } from "../draggable-item";
import { Button } from "../../../components/ui/button";
import { useEditorAdapters } from "../../../EditorProvider";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "../../../components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../../components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../../../components/ui/tooltip";
import { DEFAULT_NEW_ELEMENT_DURATION } from "../../../timeline/creation";
import { mediaTimeFromSeconds, type MediaTime } from "../../../wasm";
import { useEditor } from "../../../editor/use-editor";
import { useFileUpload } from "../../../media/use-file-upload";
import { processMediaAssets } from "../../../media/processing";
import { showMediaUploadToast } from "../../../media/upload-toast";
import { SelectableItem } from "../../../selection/selectable-item";
import { SelectableSurface } from "../../../selection/selectable-surface";
import { useSelection } from "../../../selection/context";
import { useSelectionScope } from "../../../selection/hooks/use-selection-scope";
import { buildElementFromMedia } from "../../../timeline/element-utils";
import {
  type MediaSortKey,
  type MediaSortOrder,
  type MediaViewMode,
  useAssetsPanelStore,
} from "../assets-panel-store";
import { MASKABLE_ELEMENT_TYPES } from "../../../timeline/types";
import type { MediaAsset } from "../../../media/types";
import { cn } from "../../../utils/ui";
import {
  CloudUploadIcon,
  FolderLibraryIcon,
  GridViewIcon,
  LeftToRightListDashIcon,
  Sorting19Icon,
  Image02Icon,
  MusicNote03Icon,
  Video01Icon,
} from "@hugeicons/core-free-icons";
import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import { Search, X, Film, Music, Image as ImageIcon, LayoutGrid, PlusCircle } from "lucide-react";

export function MediaView() {
  const editor = useEditor();
  const { toast, mediaSource, assetGallery } = useEditorAdapters();
  const mediaFiles = useEditor((e) => e.media.getAssets());
  const activeProject = useEditor((e) => e.project.getActive());

  const {
    mediaViewMode,
    setMediaViewMode,
    highlightMediaId,
    clearHighlight,
    mediaSortBy,
    mediaSortOrder,
    setMediaSort,
  } = useAssetsPanelStore();

  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);

  const processFiles = async ({ files }: { files: File[] }) => {
    if (!files || files.length === 0) return;
    if (!activeProject) {
      toast.error("열린 프로젝트가 없습니다");
      return;
    }

    setIsProcessing(true);
    setProgress(0);
    try {
      await showMediaUploadToast({
        filesCount: files.length,
        toast,
        promise: async () => {
          const processedAssets = await processMediaAssets({
            files,
            toast,
            mediaSource,
            onProgress: ({ progress }) => setProgress(progress),
          });
          for (const asset of processedAssets) {
            await editor.media.addMediaAsset({
              projectId: activeProject.metadata.id,
              asset,
            });
          }
          return {
            uploadedCount: processedAssets.length,
            assetNames: processedAssets.map((asset) => asset.name),
          };
        },
      });
    } catch (error) {
      console.error("Error processing files:", error);
    } finally {
      setIsProcessing(false);
      setProgress(0);
    }
  };

  const { isDragOver, dragProps, openFilePicker, fileInputProps } =
    useFileUpload({
      accept: "image/*,video/*,audio/*",
      multiple: true,
      onFilesSelected: (files) => processFiles({ files }),
    });

  const handleBrowseGallery = async () => {
    if (!assetGallery || !activeProject) return;
    let selections: Awaited<ReturnType<typeof assetGallery.openPicker>>;
    try {
      selections = await assetGallery.openPicker({
        kinds: ["video", "image", "audio"],
      });
    } catch (error) {
      console.error("Gallery picker failed:", error);
      toast.error("Couldn't open the gallery");
      return;
    }
    if (selections.length === 0) return;

    setIsProcessing(true);
    setProgress(0);
    const abort = new AbortController();
    try {
      await showMediaUploadToast({
        filesCount: selections.length,
        toast,
        promise: async () => {
          // Pre-resolved handles: fetch each CDN URL into a File so the
          // lib's downstream consumers (audio, scene-builder, retime)
          // that need a live Blob keep working. processMediaAssets
          // skips uploadLocalFile because `existingHandles` is set.
          //
          // Per-item try/catch so a single CORS/403/network failure
          // doesn't abort the whole batch. Run the fetches in parallel —
          // sequential awaits used to stall the toast progress bar for
          // the full pre-fetch loop.
          const fetched = await Promise.all(
            selections.map(async (selection) => {
              try {
                const resolved = await mediaSource.resolveMedia(
                  selection.handle,
                );
                const response = await fetch(resolved.url, {
                  signal: abort.signal,
                });
                if (!response.ok) {
                  throw new Error(`HTTP ${response.status}`);
                }
                const blob = await response.blob();
                return {
                  file: new File([blob], selection.name, {
                    type: resolved.mime,
                  }),
                  handle: selection.handle,
                  resolved,
                };
              } catch (error) {
                console.error(
                  "Gallery import failed for",
                  selection.name,
                  error,
                );
                toast.error(`Couldn't import ${selection.name}`, {
                  description:
                    error instanceof Error ? error.message : undefined,
                });
                return null;
              }
            }),
          );
          const successes = fetched.filter(
            (entry): entry is NonNullable<typeof entry> => entry !== null,
          );
          if (successes.length === 0) {
            return { uploadedCount: 0, assetNames: [] };
          }
          const processedAssets = await processMediaAssets({
            files: successes.map((entry) => entry.file),
            toast,
            mediaSource,
            existingHandles: successes.map((entry) => entry.handle),
            // Pass the already-resolved ResolvedMedia through so
            // processMediaAssets doesn't re-call resolveMedia (which
            // for the webapp adapter is a GetMediaFileByToken HTTP
            // roundtrip per asset).
            existingResolved: successes.map((entry) => entry.resolved),
            onProgress: ({ progress }) => setProgress(progress),
          });
          for (const asset of processedAssets) {
            await editor.media.addMediaAsset({
              projectId: activeProject.metadata.id,
              asset,
            });
          }
          return {
            uploadedCount: processedAssets.length,
            assetNames: processedAssets.map((asset) => asset.name),
          };
        },
      });
    } catch (error) {
      console.error("Error importing from gallery:", error);
    } finally {
      abort.abort();
      setIsProcessing(false);
      setProgress(0);
    }
  };

  const handleRemove = ({
    event,
    ids,
  }: {
    event: React.MouseEvent;
    ids: string[];
  }) => {
    event.stopPropagation();

    if (!activeProject) return;
    editor.media.removeMediaAssets({
      projectId: activeProject.metadata.id,
      ids,
    });
  };

  const handleSort = ({ key }: { key: MediaSortKey }) => {
    if (mediaSortBy === key) {
      setMediaSort({
        key,
        order: mediaSortOrder === "asc" ? "desc" : "asc",
      });
    } else {
      setMediaSort({ key, order: "asc" });
    }
  };

  const [category, setCategory] = useState<"all" | "video" | "audio" | "image">("all");
  const [searchQuery, setSearchQuery] = useState("");

  const counts = useMemo(() => {
    const nonEphemeral = mediaFiles.filter((m) => !m.ephemeral);
    return {
      all: nonEphemeral.length,
      video: nonEphemeral.filter((m) => m.type === "video").length,
      audio: nonEphemeral.filter((m) => m.type === "audio").length,
      image: nonEphemeral.filter((m) => m.type === "image").length,
    };
  }, [mediaFiles]);

  const filteredMediaItems = useMemo(() => {
    let filtered = mediaFiles.filter((item) => !item.ephemeral);

    if (category !== "all") {
      filtered = filtered.filter((item) => item.type === category);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      filtered = filtered.filter((item) => item.name.toLowerCase().includes(q));
    }

    filtered.sort((a, b) => {
      let valueA: string | number;
      let valueB: string | number;

      switch (mediaSortBy) {
        case "name":
          valueA = a.name.toLowerCase();
          valueB = b.name.toLowerCase();
          break;
        case "type":
          valueA = a.type;
          valueB = b.type;
          break;
        case "duration":
          valueA = a.duration || 0;
          valueB = b.duration || 0;
          break;
        case "size":
          valueA = a.file.size;
          valueB = b.file.size;
          break;
        default:
          return 0;
      }

      if (valueA < valueB) return mediaSortOrder === "asc" ? -1 : 1;
      if (valueA > valueB) return mediaSortOrder === "asc" ? 1 : -1;
      return 0;
    });

    return filtered;
  }, [mediaFiles, category, searchQuery, mediaSortBy, mediaSortOrder]);
  const orderedMediaIds = useMemo(() => {
    return filteredMediaItems.map((item) => item.id);
  }, [filteredMediaItems]);

  return (
    <>
      <input {...fileInputProps} />

      <PanelView
        title="미디어"
        actions={
          <MediaActions
            mediaViewMode={mediaViewMode}
            setMediaViewMode={setMediaViewMode}
            isProcessing={isProcessing}
            sortBy={mediaSortBy}
            sortOrder={mediaSortOrder}
            onSort={handleSort}
            onImport={openFilePicker}
            onBrowseGallery={assetGallery ? handleBrowseGallery : undefined}
          />
        }
        className={cn(isDragOver && "bg-accent/30")}
        contentClassName="h-full flex flex-col"
        {...dragProps}
      >
        {/* 상단 카테고리 필터 & 검색 바 */}
        <div className="flex items-center gap-1.5 p-2 border-b border-border/40 bg-background/50 shrink-0">
          <div className="flex items-center gap-0.5 shrink-0">
            <TooltipProvider delayDuration={100}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant={category === "all" ? "secondary" : "ghost"}
                    onClick={() => setCategory("all")}
                    className="size-7 rounded-md"
                  >
                    <LayoutGrid className="size-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>전체 ({counts.all})</p></TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant={category === "video" ? "secondary" : "ghost"}
                    onClick={() => setCategory("video")}
                    className="size-7 rounded-md"
                  >
                    <Film className="size-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>영상 ({counts.video})</p></TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant={category === "audio" ? "secondary" : "ghost"}
                    onClick={() => setCategory("audio")}
                    className="size-7 rounded-md"
                  >
                    <Music className="size-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>오디오 ({counts.audio})</p></TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon"
                    variant={category === "image" ? "secondary" : "ghost"}
                    onClick={() => setCategory("image")}
                    className="size-7 rounded-md"
                  >
                    <ImageIcon className="size-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom"><p>이미지 ({counts.image})</p></TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <div className="relative flex-1 flex items-center min-w-0">
            <Search className="absolute left-2 size-3 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="검색..."
              className="w-full h-7 pl-7 pr-6 text-xs bg-muted/40 border border-border/40 rounded-md placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring text-foreground"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-1.5 text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            )}
          </div>
        </div>

        {/* 미디어 본문 영역 */}
        <div className="flex-1 overflow-y-auto p-2">
          {isDragOver || mediaFiles.length === 0 ? (
            <MediaDragOverlay
              isVisible={true}
              isProcessing={isProcessing}
              progress={progress}
              onClick={openFilePicker}
            />
          ) : filteredMediaItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
              <p className="text-xs text-muted-foreground mb-2">
                {searchQuery ? `"${searchQuery}" 검색 결과가 없습니다` : "해당 카테고리에 미디어가 없습니다"}
              </p>
              {(searchQuery || category !== "all") && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCategory("all");
                    setSearchQuery("");
                  }}
                  className="h-7 text-xs"
                >
                  필터 초기화
                </Button>
              )}
            </div>
          ) : (
            <SelectableSurface
              ariaLabel="미디어"
              orderedIds={orderedMediaIds}
              revealId={highlightMediaId}
              onRevealComplete={clearHighlight}
            >
              <MediaScopeRegistrar />
              <MediaItemList
                items={filteredMediaItems}
                mode={mediaViewMode}
                onRemove={handleRemove}
              />
              {/* 상시 파일 업로드 드롭존 */}
              <div
                onClick={openFilePicker}
                className="mt-4 mb-2 flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/70 bg-accent/20 p-3.5 text-center cursor-pointer transition-colors hover:border-primary hover:bg-accent/40"
              >
                <HugeiconsIcon icon={CloudUploadIcon} className="size-5 text-muted-foreground" />
                <p className="text-xs font-medium text-foreground">새 미디어 가져오기</p>
                <p className="text-[11px] text-muted-foreground">생성 AI 영상(MP4), 음원, 이미지 파일 끌어다 놓기</p>
              </div>
            </SelectableSurface>
          )}
        </div>
      </PanelView>
    </>
  );
}

function MediaScopeRegistrar() {
  useSelectionScope();
  return null;
}

function MediaAssetDraggable({
  item,
  preview,
  variant,
  isRounded,
}: {
  item: MediaAsset;
  preview: React.ReactNode;
  variant: "card" | "compact";
  isRounded?: boolean;
}) {
  const editor = useEditor();

  const addElementAtTime = ({
    asset,
    startTime,
  }: {
    asset: MediaAsset;
    startTime: MediaTime;
  }) => {
    const duration =
      asset.duration != null
        ? mediaTimeFromSeconds({ seconds: asset.duration })
        : DEFAULT_NEW_ELEMENT_DURATION;
    const element = buildElementFromMedia({
      mediaId: asset.id,
      mediaType: asset.type,
      name: asset.name,
      duration,
      startTime,
    });
    editor.timeline.insertElement({
      element,
      placement: { mode: "auto" },
    });
  };

  return (
    <DraggableItem
      name={item.name}
      preview={preview}
      dragData={{
        id: item.id,
        type: "media",
        mediaType: item.type,
        name: item.name,
        ...(item.type !== "audio" && {
          targetElementTypes: [...MASKABLE_ELEMENT_TYPES],
        }),
      }}
      shouldShowPlusOnDrag={false}
      onAddToTimeline={({ currentTime }) =>
        addElementAtTime({ asset: item, startTime: currentTime })
      }
      variant={variant}
      isRounded={isRounded}
    />
  );
}

function MediaItemWithContextMenu({
  item,
  children,
  onRemove,
}: {
  item: MediaAsset;
  children: React.ReactNode;
  onRemove: ({
    event,
    ids,
  }: {
    event: React.MouseEvent;
    ids: string[];
  }) => void;
}) {
  const { isSelected, selectedIds } = useSelection();
  const idsToDelete = isSelected(item.id) ? selectedIds : [item.id];
  const deleteLabel =
    idsToDelete.length > 1 ? `Delete ${idsToDelete.length} items` : "삭제";

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem
          variant="destructive"
          onClick={(event: React.MouseEvent<HTMLDivElement>) =>
            onRemove({ event, ids: idsToDelete })
          }
        >
          {deleteLabel}
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function MediaItemList({
  items,
  mode,
  onRemove,
}: {
  items: MediaAsset[];
  mode: MediaViewMode;
  onRemove: ({
    event,
    ids,
  }: {
    event: React.MouseEvent;
    ids: string[];
  }) => void;
}) {
  const isGrid = mode === "grid";

  return (
    <div
      className={cn(isGrid ? "grid gap-3" : "flex flex-col gap-1.5")}
      style={
        isGrid ? { gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" } : undefined
      }
    >
      {items.map((item) => (
        <MediaItemWithContextMenu item={item} onRemove={onRemove} key={item.id}>
          <SelectableItem className={cn(!isGrid && "w-full")} id={item.id}>
            <MediaAssetDraggable
              item={item}
              preview={
                <MediaPreview
                  item={item}
                  variant={isGrid ? "grid" : "compact"}
                />
              }
              variant={isGrid ? "card" : "compact"}
              isRounded={isGrid ? false : undefined}
            />
          </SelectableItem>
        </MediaItemWithContextMenu>
      ))}
    </div>
  );
}

function formatDuration({ duration }: { duration: number }) {
  const min = Math.floor(duration / 60);
  const sec = Math.floor(duration % 60);
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

function MediaDurationBadge({ duration }: { duration?: number }) {
  if (!duration) return null;

  return (
    <div className="absolute right-1 bottom-1 rounded bg-black/70 px-1 text-xs text-white">
      {formatDuration({ duration })}
    </div>
  );
}

function MediaDurationLabel({ duration }: { duration?: number }) {
  if (!duration) return null;

  return (
    <span className="text-xs opacity-70">{formatDuration({ duration })}</span>
  );
}

function MediaTypePlaceholder({
  icon,
  label,
  duration,
  variant,
}: {
  icon: IconSvgElement;
  label: string;
  duration?: number;
  variant: "muted" | "bordered";
}) {
  const iconClassName = cn("size-6", variant === "bordered" && "mb-1");

  return (
    <div
      className={cn(
        "text-muted-foreground flex size-full flex-col items-center justify-center rounded",
        variant === "muted" ? "bg-muted/30" : "border",
      )}
    >
      <HugeiconsIcon icon={icon} className={iconClassName} />
      <span className="text-xs">{label}</span>
      <MediaDurationLabel duration={duration} />
    </div>
  );
}

function MediaPreview({
  item,
  variant = "grid",
}: {
  item: MediaAsset;
  variant?: "grid" | "compact";
}) {
  const shouldShowDurationBadge = variant === "grid";

  if (item.type === "image") {
    return (
      <div className="relative flex size-full items-center justify-center bg-muted overflow-hidden rounded">
        <img
          src={item.url ?? ""}
          alt={item.name}
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
        />
        <div className="absolute top-1 left-1 rounded bg-black/60 px-1 py-0.2 text-[9px] font-semibold text-sky-300">
          IMG
        </div>
      </div>
    );
  }

  if (item.type === "video") {
    return (
      <div className="relative size-full bg-black/50 overflow-hidden rounded">
        {item.thumbnailUrl ? (
          <img
            src={item.thumbnailUrl}
            alt={item.name}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center text-muted-foreground bg-muted/20">
            <HugeiconsIcon icon={Video01Icon} className="size-6 mb-1 text-primary/80" />
            <span className="text-[11px] font-medium">영상</span>
          </div>
        )}
        <div className="absolute top-1 left-1 rounded bg-black/60 px-1 py-0.2 text-[9px] font-semibold text-emerald-300">
          MP4
        </div>
        {shouldShowDurationBadge && (
          <MediaDurationBadge duration={item.duration} />
        )}
      </div>
    );
  }

  if (item.type === "audio") {
    return (
      <div className="relative flex size-full flex-col items-center justify-center rounded bg-gradient-to-b from-indigo-950/40 via-background to-slate-900 border border-indigo-500/25 p-2 overflow-hidden">
        <div className="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-indigo-500/10 to-transparent pointer-events-none" />
        <HugeiconsIcon icon={MusicNote03Icon} className="size-6 text-indigo-400 mb-1" />
        <span className="text-[10px] font-medium text-foreground/85 truncate max-w-full text-center px-1">
          {item.name.replace(/\.[^/.]+$/, "")}
        </span>
        <div className="absolute top-1 left-1 rounded bg-indigo-950/70 px-1 py-0.2 text-[9px] font-semibold text-indigo-300">
          AUDIO
        </div>
        {shouldShowDurationBadge && (
          <MediaDurationBadge duration={item.duration} />
        )}
      </div>
    );
  }

  return (
    <MediaTypePlaceholder icon={Image02Icon} label="기타" variant="muted" />
  );
}

function MediaActions({
  mediaViewMode,
  setMediaViewMode,
  isProcessing,
  sortBy,
  sortOrder,
  onSort,
  onImport,
  onBrowseGallery,
}: {
  mediaViewMode: MediaViewMode;
  setMediaViewMode: (mode: MediaViewMode) => void;
  isProcessing: boolean;
  sortBy: MediaSortKey;
  sortOrder: MediaSortOrder;
  onSort: ({ key }: { key: MediaSortKey }) => void;
  onImport: () => void;
  // Optional: only rendered when the host wires an AssetGalleryAdapter.
  onBrowseGallery?: () => void;
}) {
  return (
    <div className="flex gap-1.5">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon"
              variant="ghost"
              onClick={() =>
                setMediaViewMode(mediaViewMode === "grid" ? "list" : "grid")
              }
              disabled={isProcessing}
              className="items-center justify-center"
            >
              {mediaViewMode === "grid" ? (
                <HugeiconsIcon icon={LeftToRightListDashIcon} />
              ) : (
                <HugeiconsIcon icon={GridViewIcon} />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>
              {mediaViewMode === "grid"
                ? "목록으로 보기"
                : "격자로 보기"}
            </p>
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <DropdownMenu>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  disabled={isProcessing}
                  className="items-center justify-center"
                >
                  <HugeiconsIcon icon={Sorting19Icon} />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <DropdownMenuContent align="end">
              <SortMenuItem
                label="이름"
                sortKey="name"
                currentSortBy={sortBy}
                currentSortOrder={sortOrder}
                onSort={onSort}
              />
              <SortMenuItem
                label="종류"
                sortKey="type"
                currentSortBy={sortBy}
                currentSortOrder={sortOrder}
                onSort={onSort}
              />
              <SortMenuItem
                label="길이"
                sortKey="duration"
                currentSortBy={sortBy}
                currentSortOrder={sortOrder}
                onSort={onSort}
              />
              <SortMenuItem
                label="파일 크기"
                sortKey="size"
                currentSortBy={sortBy}
                currentSortOrder={sortOrder}
                onSort={onSort}
              />
            </DropdownMenuContent>
          </DropdownMenu>
          <TooltipContent>
            <p>
              Sort by {sortBy} (
              {sortOrder === "asc" ? "ascending" : "descending"})
            </p>
          </TooltipContent>
        </Tooltip>
      {onBrowseGallery ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              onClick={onBrowseGallery}
              disabled={isProcessing}
              className="size-8 rounded-md"
            >
              <HugeiconsIcon icon={FolderLibraryIcon} />
            </Button>
          </TooltipTrigger>
          <TooltipContent><p>갤러리 둘러보기</p></TooltipContent>
        </Tooltip>
      ) : null}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            onClick={onImport}
            disabled={isProcessing}
            className="size-8 rounded-md"
          >
            <HugeiconsIcon icon={CloudUploadIcon} />
          </Button>
        </TooltipTrigger>
        <TooltipContent><p>미디어 가져오기</p></TooltipContent>
      </Tooltip>
      </TooltipProvider>
    </div>
  );
}

function SortMenuItem({
  label,
  sortKey,
  currentSortBy,
  currentSortOrder,
  onSort,
}: {
  label: string;
  sortKey: MediaSortKey;
  currentSortBy: MediaSortKey;
  currentSortOrder: MediaSortOrder;
  onSort: ({ key }: { key: MediaSortKey }) => void;
}) {
  const isActive = currentSortBy === sortKey;
  const arrow = isActive ? (currentSortOrder === "asc" ? "↑" : "↓") : "";

  return (
    <DropdownMenuItem onClick={() => onSort({ key: sortKey })}>
      {label} {arrow}
    </DropdownMenuItem>
  );
}
