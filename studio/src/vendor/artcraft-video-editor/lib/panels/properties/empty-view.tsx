import { HugeiconsIcon } from "@hugeicons/react";
import { Settings05Icon } from "@hugeicons/core-free-icons";

export function EmptyView() {
  return (
    <div className="bg-background flex h-full flex-col items-center justify-center gap-3 p-4">
      <HugeiconsIcon
        icon={Settings05Icon}
        className="text-muted-foreground/75 size-10"
        strokeWidth={1}
      />
      <div className="flex flex-col gap-2 text-center">
        <p className="text-base font-medium">선택한 항목이 없습니다</p>
        <p className="text-muted-foreground text-sm text-balance">
          타임라인에서 클립 · 자막 · 이미지를 누르면 여기서 속성을 바꿀 수 있어요
        </p>
      </div>
    </div>
  );
}
