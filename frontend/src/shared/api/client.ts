// Typed fetch client wrapping the backend's standard envelope
// ({ success, data, error, meta }) — see backend/app/core/response.py and
// docs/api/API_STANDARDS.md. Every feature's API calls should go through this,
// not raw fetch, so error handling and the base URL stay in one place.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

// Same storage key AuthProvider (features/auth/context.tsx) has always used — defined
// here, not there, so this module (the lower-level one) can read/refresh it itself on a
// 401 without importing back up into features/auth/* and creating a cycle (api.ts
// already imports apiRequest from here). context.tsx re-exports this binding so
// existing `import { REFRESH_TOKEN_STORAGE_KEY } from "@/features/auth/context"` call
// sites (e.g. SessionsPage) keep working unchanged.
export const REFRESH_TOKEN_STORAGE_KEY = "afs_refresh_token";

// Routes a 401 must never trigger a refresh-and-retry for: a wrong password on /login is
// a normal 401 with nothing to refresh, and a 401 from /refresh itself means the refresh
// token is the thing that's invalid — retrying it would recurse forever.
const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh"];

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorDetail | null;
  meta: { pagination?: PaginationMeta } | null;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

let accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

// Added in Module 6A — a plain `<a href>` to a protected download endpoint can't carry
// the Bearer token (this app is pure-Bearer, no cookies — decision 008), so a real
// download needs a manual authenticated fetch + blob. See LeadListPage's export button.
export function getAccessToken(): string | null {
  return accessToken;
}

// AuthProvider registers its own logout/redirect here — this module can't import
// AuthContext (see the REFRESH_TOKEN_STORAGE_KEY comment above for why), so a session
// that can't be silently refreshed is surfaced through this callback instead of a plain
// thrown error a caller might swallow. Left `null` (no-op) until AuthProvider mounts.
let onSessionExpired: (() => void) | null = null;

export function setSessionExpiredHandler(handler: (() => void) | null) {
  onSessionExpired = handler;
}

// De-dupes concurrent 401s (several queries/autosaves firing near the 15-minute access
// token expiry at once) into a single /auth/refresh call instead of a stampede of them.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const storedRefreshToken = localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
    if (!storedRefreshToken) return null;
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: storedRefreshToken }),
      });
      if (!response.ok) return null;
      const body = (await response.json()) as ApiResponse<{ access_token: string; refresh_token: string }>;
      if (!body.success || !body.data) return null;
      accessToken = body.data.access_token;
      localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, body.data.refresh_token);
      return accessToken;
    } catch {
      return null;
    }
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

// Returns the full envelope — needed when a caller wants `meta` (e.g. pagination), not
// just `data`. Added in Module 2 for the Employee List page.
export async function apiRequestRaw<T>(path: string, init: RequestInit = {}, _isRetry = false): Promise<ApiResponse<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...init.headers,
      },
    });
  } catch (err) {
    // fetch() itself throws on a network-level failure (offline, DNS, connection
    // refused, CORS preflight failure) — never on an HTTP error status, which still
    // resolves normally below. Distinguishable code so shared/api/errors.ts can show a
    // "check your connection" message instead of a generic one.
    throw new ApiError("network_error", "Unable to connect to the server. Please check your internet connection.", err);
  }

  // A 15-minute access token expiring mid-session (a long form, a slow typist) must not
  // silently drop every subsequent request/autosave — try one silent refresh-and-retry
  // before giving up. Skipped for retries themselves (one attempt only) and for the two
  // paths where a 401 means something else entirely (see NO_REFRESH_PATHS above).
  if (response.status === 401 && !_isRetry && !NO_REFRESH_PATHS.some((p) => path.startsWith(p))) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequestRaw<T>(path, init, true);
    }
    localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
    accessToken = null;
    onSessionExpired?.();
  }

  let body: ApiResponse<T>;
  try {
    body = (await response.json()) as ApiResponse<T>;
  } catch (err) {
    // A non-JSON error body (an HTML error page from a proxy/gateway in front of the
    // API, a truly malformed response, etc.) — every response from this app's own API
    // is always JSON (see backend/app/core/response.py + main.py's exception handlers),
    // so this only fires for something upstream of the app itself.
    throw new ApiError(`http_${response.status}`, "An unexpected error occurred.", err);
  }

  if (!body.success || body.error) {
    throw new ApiError(body.error?.code ?? `http_${response.status}`, body.error?.message ?? "Request failed", body.error?.details);
  }

  return body;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const body = await apiRequestRaw<T>(path, init);
  return body.data as T;
}
