import type { InputHTMLAttributes } from "react";

interface CheckboxFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

// Shared checkbox primitive — replaces the raw `<input type="checkbox" className="accent-primary">`
// hand-rolled per page (GenerateLinkModal, AddTaskModal, GeoFencingPage) with one consistent
// hit target/label pairing.
export function CheckboxField({ label, id, className = "", ...inputProps }: CheckboxFieldProps) {
  const fieldId = id ?? inputProps.name;
  return (
    <label htmlFor={fieldId} className={`flex cursor-pointer items-center gap-2 text-sm text-text ${className}`}>
      <input id={fieldId} type="checkbox" className="h-4 w-4 rounded border-border accent-primary" {...inputProps} />
      {label}
    </label>
  );
}
