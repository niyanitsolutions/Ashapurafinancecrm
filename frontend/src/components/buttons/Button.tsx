import type { ButtonHTMLAttributes, ReactNode } from "react";

// Single source of truth for button styling — see docs/UI_UX.md. Consolidates what used
// to be independently copy-pasted `bg-gradient-to-r from-primary to-primary-dark ...`
// strings and per-file `OutlineButton` components (GenerateLinkModal, AddTaskModal,
// EmptyState) into one component with a real variant/size contract.
export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

// Exported so non-<button> elements that need identical styling (e.g. EmptyState's
// react-router <Link> actions) can compose the same classes without duplicating them.
export const BUTTON_VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-gradient-to-r from-primary to-primary-dark text-white font-semibold shadow-card hover-lift",
  secondary: "border border-border bg-card text-text font-medium hover:bg-background",
  danger: "border border-danger/25 bg-card text-danger font-medium hover:bg-danger/5",
  ghost: "text-text/70 font-medium hover:bg-background",
};

export const BUTTON_SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "text-sm py-2 px-3.5 gap-1.5",
  md: "text-sm py-2.5 px-5 gap-2",
};

export const BUTTON_BASE_CLASSES =
  "inline-flex items-center justify-center rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0";

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  disabled,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={`${BUTTON_BASE_CLASSES} ${BUTTON_VARIANT_CLASSES[variant]} ${BUTTON_SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading ? "Please wait…" : (
        <>
          {icon}
          {children}
        </>
      )}
    </button>
  );
}
