import type { InputHTMLAttributes } from "react";

// Restyled for the glassmorphism AuthPageLayout (dark card, not a light one) —
// light-colored label, translucent input surface, white text/caret.
interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function FormField({ label, error, id, ...inputProps }: FormFieldProps) {
  const fieldId = id ?? inputProps.name;
  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="block text-sm font-medium text-white/80 mb-1.5">
        {label}
      </label>
      <input
        id={fieldId}
        className="w-full rounded-lg border border-white/20 bg-white/10 px-3.5 py-2.5 text-sm text-white placeholder-white/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/60"
        {...inputProps}
      />
      {error && <p className="mt-1.5 text-sm text-red-300">{error}</p>}
    </div>
  );
}
