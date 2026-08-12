// Single source of truth for the password complexity policy on the client side —
// mirrors backend/app/security/password.py's PASSWORD_COMPLEXITY_RULES exactly, so a
// password that passes here never gets rejected by the server for complexity reasons
// (length is still separately enforced by passwordSchema/the input's own maxLength).
export const PASSWORD_RULES: { label: string; test: (password: string) => boolean }[] = [
  { label: "At least 8 characters", test: (p) => p.length >= 8 },
  { label: "An uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { label: "A lowercase letter", test: (p) => /[a-z]/.test(p) },
  { label: "A number", test: (p) => /\d/.test(p) },
  { label: "A special character", test: (p) => /[^\w\s]/.test(p) },
];

export function isPasswordStrong(password: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(password));
}

export function PasswordStrengthChecklist({ password }: { password: string }) {
  return (
    <ul className="mb-4 -mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
      {PASSWORD_RULES.map((rule) => {
        const met = rule.test(password);
        return (
          <li key={rule.label} className={met ? "text-success" : "text-text/40"}>
            {met ? "✓" : "✗"} {rule.label}
          </li>
        );
      })}
    </ul>
  );
}
