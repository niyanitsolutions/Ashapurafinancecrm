// Pure-bearer auth state (see docs/decisions/DECISIONS.md #008): access token lives only
// in memory (this context), never localStorage — reduces the XSS blast radius. The
// refresh token is persisted to localStorage so a page reload doesn't force a re-login;
// that persistence choice is the accepted tradeoff of not using cookies, documented in
// docs/KNOWN_LIMITATIONS.md.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getProfile, refreshTokens } from "@/features/auth/api";
import { AuthContext, type AuthContextValue, type LogoutReason } from "@/features/auth/authContext";
import {
  apiRequest,
  REFRESH_TOKEN_STORAGE_KEY,
  setAccessToken as setClientAccessToken,
  setSessionExpiredHandler,
} from "@/shared/api/client";

// Re-exported (now defined in shared/api/client.ts, which needs it too — see that
// file's comment) so existing call sites importing it from here don't need to change:
// pages that need the raw token for a one-off call (e.g. SessionsPage's "Logout All
// Other Devices", which must identify — and exclude — the calling session).
export { REFRESH_TOKEN_STORAGE_KEY };

interface AuthState {
  accessToken: string | null;
  role: string | null;
  userId: string | null;
  mustChangePassword: boolean;
}

const EMPTY_STATE: AuthState = { accessToken: null, role: null, userId: null, mustChangePassword: false };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(EMPTY_STATE);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const preLogoutFlushRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (!storedRefreshToken) {
      setIsBootstrapping(false);
      return;
    }

    refreshTokens(storedRefreshToken)
      .then(async (tokens) => {
        setClientAccessToken(tokens.access_token);
        localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, tokens.refresh_token);
        // The refresh response carries no role/user_id/must_change_password (see
        // docs/api/API.md) — resolved via the existing /auth/profile endpoint instead of
        // decoding the JWT client-side.
        const profile = await getProfile();
        setState({
          accessToken: tokens.access_token,
          role: profile.role,
          userId: profile.user_id,
          mustChangePassword: profile.must_change_password,
        });
      })
      .catch(() => {
        localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
      })
      .finally(() => setIsBootstrapping(false));
  }, []);

  const setSession: AuthContextValue["setSession"] = ({ accessToken, refreshToken, role, userId, mustChangePassword }) => {
    setClientAccessToken(accessToken);
    localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
    setState({ accessToken, role, userId, mustChangePassword });
  };

  const clearMustChangePassword = () => {
    setState((prev) => ({ ...prev, mustChangePassword: false }));
  };

  const clearSession = () => {
    setClientAccessToken(null);
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    setState(EMPTY_STATE);
  };

  useEffect(() => {
    // shared/api/client.ts calls this when a 401 survives its own silent
    // refresh-and-retry (refresh token missing/expired/revoked) — clearing state here
    // makes `accessToken` null, which RequireAuth's existing check reactively redirects
    // to /login for, the same way a manual `logout()` already does.
    setSessionExpiredHandler(() => clearSession());
    return () => setSessionExpiredHandler(null);
  }, []);

  const registerPreLogoutFlush: AuthContextValue["registerPreLogoutFlush"] = (flush) => {
    preLogoutFlushRef.current = flush;
  };

  const logout = async (reason: LogoutReason = "manual") => {
    if (preLogoutFlushRef.current) {
      // Best-effort — a failed flush must never block logout itself.
      await preLogoutFlushRef.current().catch(() => undefined);
    }
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (refreshToken) {
      await apiRequest("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken, reason }) }).catch(
        () => undefined,
      );
    }
    clearSession();
  };

  return (
    <AuthContext.Provider
      value={{ ...state, isBootstrapping, setSession, clearMustChangePassword, clearSession, logout, registerPreLogoutFlush }}
    >
      {children}
    </AuthContext.Provider>
  );
}
