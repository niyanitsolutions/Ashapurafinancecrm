import { useState, type InputHTMLAttributes } from "react";
import { Icon } from "@/theme/icons";

// Same visual language as FormField (glass card input), plus a show/hide toggle — kept as
// its own component rather than an opt-in flag on FormField so every other `type="password"`
// call site (ResetPasswordPage, RegisterPage, ...) is untouched.
interface PasswordFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export function PasswordField({ label, error, id, ...inputProps }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  const fieldId = id ?? inputProps.name;

  return (
    <div className="mb-4">
      <label htmlFor={fieldId} className="block text-sm font-medium text-white/80 mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          id={fieldId}
          type={visible ? "text" : "password"}
          className="w-full rounded-lg border border-white/20 bg-white/10 px-3.5 py-2.5 pr-11 text-sm text-white placeholder-white/40 transition-colors focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/60 [&::-ms-reveal]:hidden [&::-ms-clear]:hidden"
          {...inputProps}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          tabIndex={-1}
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute inset-y-0 right-0 flex items-center pr-3 text-white/50 transition-colors hover:text-white/80"
        >
          <Icon name={visible ? "eye-off" : "eye"} className="h-5 w-5" />
        </button>
      </div>
      {error && <p className="mt-1.5 text-sm text-red-300">{error}</p>}
    </div>
  );
}
