import { ReactNode } from "react";
import { twMerge } from "tailwind-merge";

interface BadgeProps {
  label: string;
  color?: string;
  className?: string;
  icon?: ReactNode;
}

export const Badge = ({ label, className, icon }: BadgeProps) => {
  return (
    <div
      className={twMerge(
        "flex items-center gap-1 rounded-[4px] border border-ui-controls-border bg-black/40 px-1.5 py-px text-[11px] font-medium",
        className
      )}
    >
      {icon}
      {label}
    </div>
  );
};
