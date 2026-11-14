import { LabelHTMLAttributes, ReactNode } from "react";
import { twMerge } from "tailwind-merge";

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  className?: string;
  children: ReactNode;
  required?: boolean;
}

export const Label = ({
  className,
  children,
  required,
  ...rest
}: LabelProps) => (
  <label
    className={twMerge(
      "text-base-fg/70 mb-1.5 text-xs font-medium" /* fluma: was mono uppercase */,
      className,
    )}
    {...rest}
  >
    {children}
    {required && <span className="ml-0.5 text-red-400">*</span>}
  </label>
);

export default Label;
