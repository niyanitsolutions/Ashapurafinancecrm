import type { TextareaHTMLAttributes } from "react";

interface TextareaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
}

// Textarea counterpart to FormField/SelectField — same label/error/spacing contract.
export function TextareaField({ label, error, id, ...textareaProps }: TextareaFieldProps) {
  const fieldId = id ?? textareaProps.name;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="mb-1.5 block text-sm font-medium text-text">
        {label}
      </label>
      <textarea
        id={fieldId}
        className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        {...textareaProps}
      />
      {error && <p className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
}
