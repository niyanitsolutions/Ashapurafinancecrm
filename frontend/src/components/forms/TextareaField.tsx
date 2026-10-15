import { useId, type TextareaHTMLAttributes } from "react";

interface TextareaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
}

// Textarea counterpart to FormField/SelectField — same label/error/spacing contract.
export function TextareaField({ label, error, id, ...textareaProps }: TextareaFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? textareaProps.name ?? generatedId;
  const errorId = `${fieldId}-error`;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="mb-1.5 block text-sm font-medium text-text">
        {label}
      </label>
      <textarea
        {...textareaProps}
        id={fieldId}
        aria-invalid={error ? true : textareaProps["aria-invalid"]}
        aria-describedby={[textareaProps["aria-describedby"], error ? errorId : null].filter(Boolean).join(" ") || undefined}
        className={`w-full rounded-[10px] border ${error ? "border-danger" : "border-border"} bg-card px-3.5 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30 ${textareaProps.className ?? ""}`}
      />
      {error && <p id={errorId} className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
}
