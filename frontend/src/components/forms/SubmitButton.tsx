import type { ButtonHTMLAttributes } from "react";

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isSubmitting?: boolean;
}

export function SubmitButton({ isSubmitting, children, disabled, ...rest }: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={disabled || isSubmitting}
      className="hover-lift rounded-xl bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2.5 px-5 shadow-card disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
      {...rest}
    >
      {isSubmitting ? "Please wait…" : children}
    </button>
  );
}
