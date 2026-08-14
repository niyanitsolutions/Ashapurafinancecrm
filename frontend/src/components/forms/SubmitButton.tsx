import type { ButtonHTMLAttributes } from "react";
import { Button } from "@/components/buttons/Button";

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  isSubmitting?: boolean;
}

// Thin, API-compatible wrapper over the shared Button primitive — every existing call
// site (43 across the app) keeps working unchanged while inheriting Button's consistent
// styling/loading/disabled behavior. New code should reach for Button directly.
export function SubmitButton({ isSubmitting, children, ...rest }: SubmitButtonProps) {
  return (
    <Button type="submit" variant="primary" loading={isSubmitting} {...rest}>
      {children}
    </Button>
  );
}
