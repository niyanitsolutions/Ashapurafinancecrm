import { createContext } from "react";

interface AuthState {
  accessToken: string | null;
  role: string | null;
  userId: string | null;
  mustChangePassword: boolean;
}

export type LogoutReason = "manual" | "idle_timeout";

export interface AuthContextValue extends AuthState {
  isBootstrapping: boolean;
  setSession: (session: { accessToken: string; refreshToken: string; role: string; userId: string; mustChangePassword: boolean }) => void;
  clearMustChangePassword: () => void;
  clearSession: () => void;
  // Revokes the session server-side (best-effort) then clears it locally — the one
  // logout path every Logout button/idle-timeout auto-logout goes through, so none of
  // them duplicate the revoke-then-clear sequence. `reason` is stamped onto the
  // server-side audit log entry (see AuditEvent.AUTO_LOGOUT).
  logout: (reason?: LogoutReason) => Promise<void>;
  // A page with unsaved local state (e.g. the application wizard's autosave) can
  // register a callback here that `logout()` awaits first, so a manual Logout click or
  // an idle auto-logout can never drop the last few seconds of edits. Pass `null` to
  // unregister when the page unmounts. Only one flush is ever in flight at a time —
  // there's only ever one such page open per tab.
  registerPreLogoutFlush: (flush: (() => Promise<void>) | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
