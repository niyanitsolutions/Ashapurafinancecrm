import { useId, type SelectHTMLAttributes } from "react";

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
  const generatedId = useId();
  const fieldId = id ?? selectProps.name ?? generatedId;
  const errorId = `${fieldId}-error`;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="block text-sm font-medium text-text mb-1.5">
        {label}
      </label>
      <select
        {...selectProps}
        id={fieldId}
        aria-invalid={error ? true : selectProps["aria-invalid"]}
        aria-describedby={[selectProps["aria-describedby"], error ? errorId : null].filter(Boolean).join(" ") || undefined}
        className={`w-full min-h-10 rounded-[10px] border ${error ? "border-danger" : "border-border"} px-3.5 py-2.5 text-sm bg-card transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary ${selectProps.className ?? ""}`}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && <p id={errorId} className="mt-1.5 text-sm text-danger">{error}</p>}
    </div>
  );
}
