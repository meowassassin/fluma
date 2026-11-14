"use client";

// fluma: always-visible "back to videos" button left of the project menu
// (upstream only has "Exit project" inside the menu). Same exit sequence as
// the upstream menu item: flush pending saves, close, navigate.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { Button } from "../components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";
import { useEditor } from "../editor/use-editor";

export function FlumaExitButton({ exitTo }: { exitTo: string }) {
  const [isExiting, setIsExiting] = useState(false);
  const navigate = useNavigate();
  const editor = useEditor();

  const handleExit = async () => {
    if (isExiting) return;
    setIsExiting(true);
    try {
      await editor.project.prepareExit();
      editor.project.closeProject();
    } catch (error) {
      console.error("Failed to prepare project exit:", error);
    } finally {
      navigate(exitTo);
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleExit}
          disabled={isExiting}
          className="size-8 text-muted-foreground hover:text-foreground"
          aria-label="영상 목록으로 나가기"
        >
          <HugeiconsIcon icon={ArrowLeft02Icon} className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">영상 목록으로 나가기</TooltipContent>
    </Tooltip>
  );
}
