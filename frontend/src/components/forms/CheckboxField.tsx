import type { InputHTMLAttributes } from "react";

interface CheckboxFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  // When the surrounding UI already states what the checkbox means (e.g. a table
  // column header like "View"/"Create"/"Edit"), repeating that text next to every
  // cell's checkbox is visual noise — but the checkbox still needs an accessible name.
  // `hideLabel` keeps `label` in the DOM for screen readers (sr-only) without
  // rendering it visibly. Defaults to false so every existing call site is unaffected.
  hideLabel?: boolean;
}

// Shared checkbox primitive — replaces the raw `<input type="checkbox" className="accent-primary">`
// hand-rolled per page (GenerateLinkModal, AddTaskModal, GeoFencingPage) with one consistent
// hit target/label pairing.
export function CheckboxField({ label, id, hideLabel = false, className = "", ...inputProps }: CheckboxFieldProps) {
  const fieldId = id ?? inputProps.name;
  return (
    <label htmlFor={fieldId} className={`flex cursor-pointer items-center gap-2 text-sm text-text ${className}`}>
      <input id={fieldId} type="checkbox" className="h-4 w-4 rounded border-border accent-primary" {...inputProps} />
      {hideLabel ? <span className="sr-only">{label}</span> : label}
    </label>
  );
}
