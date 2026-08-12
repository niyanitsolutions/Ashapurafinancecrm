import type { ButtonHTMLAttributes } from "react";

// Orange gradient primary button + hover-lift, per the brief's button spec.
interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isSubmitting?: boolean;
}

export function SubmitButton({ isSubmitting, children, disabled, ...rest }: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={disabled || isSubmitting}
      className="hover-lift inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-3 shadow-glass disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
      {...rest}
    >
      {isSubmitting && (
        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-90" d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
      )}
      {isSubmitting ? "Please wait…" : children}
    </button>
  );
}
