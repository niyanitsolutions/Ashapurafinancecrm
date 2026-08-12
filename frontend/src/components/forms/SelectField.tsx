import type { SelectHTMLAttributes } from "react";

interface Option {
  value: string;
  label: string;
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  options: Option[];
  placeholder?: string;
}

export function SelectField({ label, error, options, placeholder, id, ...selectProps }: SelectFieldProps) {
  const fieldId = id ?? selectProps.name;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="block text-sm font-medium text-text mb-1.5">
        {label}
      </label>
      <select
        id={fieldId}
        className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
        {...selectProps}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
}
