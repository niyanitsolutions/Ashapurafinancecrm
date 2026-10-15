import { useId, type InputHTMLAttributes } from "react";

// New shared home for generic form primitives (see docs/UI_UX.md) — populates the
// Foundation-provisioned but previously-empty components/forms/ folder rather than
// reaching into Authentication's own (frozen) copy in features/auth/components/.
interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function FormField({ label, error, id, ...inputProps }: FormFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? inputProps.name ?? generatedId;
  const errorId = `${fieldId}-error`;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="block text-sm font-medium text-text mb-1.5">
        {label}
      </label>
      <input
        {...inputProps}
        id={fieldId}
        aria-invalid={error ? true : inputProps["aria-invalid"]}
        aria-describedby={[inputProps["aria-describedby"], error ? errorId : null].filter(Boolean).join(" ") || undefined}
        className={`w-full min-h-10 rounded-[10px] border ${error ? "border-danger" : "border-border"} bg-card px-3.5 py-2.5 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary ${inputProps.className ?? ""}`}
      />
      {error && <p id={errorId} className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
}
