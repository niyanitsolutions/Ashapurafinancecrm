import { useState } from "react";
import { Icon } from "@/theme/icons";
import { revealAdvisorPassword } from "@/features/recruitment/api";
import { getErrorMessage } from "@/shared/api/errors";

// "Password" row — masked by default. The backend never includes the password hash or
// plaintext on the Advisor Details fetch itself (see `AdvisorDetail.has_password`, a
// plain boolean); the eye click makes a SEPARATE, dedicated, edit-permission-gated,
// audited call (`GET /advisors/{id}/password`) that decrypts the real saved value on
// demand. Nothing sensitive is fetched, cached, or rendered until that explicit click,
// and hiding it again clears the revealed value from memory rather than just re-masking
// a value still held in state.
export function AdvisorPassword({ advisorId, hasPassword, canReveal }: { advisorId: string; hasPassword: boolean; canReveal: boolean }) {
  const [state, setState] = useState<"hidden" | "loading" | "revealed" | "error">("hidden");
  const [password, setPassword] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!hasPassword) {
    return <span>Not set</span>;
  }

  const reveal = async () => {
    setState("loading");
    setError(null);
    try {
      const { password: value } = await revealAdvisorPassword(advisorId);
      setPassword(value);
      setState("revealed");
    } catch (err) {
      setError(getErrorMessage(err));
      setState("error");
    }
  };

  const hide = () => {
    setPassword(null);
    setState("hidden");
  };

  return (
        <span className="inline-flex items-center gap-1.5">
          {state === "revealed" ? password : "••••••••"}
          {state === "loading" && <span className="text-xs text-textSecondary">Loading…</span>}
          {canReveal && (
            <button
              type="button"
              onClick={state === "revealed" ? hide : reveal}
              disabled={state === "loading"}
              aria-label={state === "revealed" ? "Hide password" : "Show password"}
              className="text-textSecondary transition-colors hover:text-text disabled:opacity-50"
            >
              <Icon name={state === "revealed" ? "eye-off" : "eye"} className="h-4 w-4" />
            </button>
          )}
          {state === "error" && error && <span className="text-xs text-danger">{error}</span>}
        </span>
  );
}

