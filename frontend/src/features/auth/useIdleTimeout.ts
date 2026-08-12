import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/useAuth";

const IDLE_WARNING_MS = 9 * 60 * 1000; // warn at 9 minutes idle
const IDLE_LOGOUT_MS = 10 * 60 * 1000; // auto-logout at 10 minutes idle
const WARNING_WINDOW_S = Math.round((IDLE_LOGOUT_MS - IDLE_WARNING_MS) / 1000); // 60s

const ACTIVITY_EVENTS = ["mousemove", "keydown", "click", "touchstart", "scroll"] as const;

// Tracks user activity while a session is live and calls `onExpire` once idle time
// crosses the 10-minute mark. `onExpire` fires exactly once per idle period — the caller
// (SessionGuard) is responsible for actually logging out; this hook only measures time.
export function useIdleTimeout(onExpire: () => void) {
  const { accessToken } = useAuth();
  const [isWarning, setIsWarning] = useState(false);
  const [secondsRemaining, setSecondsRemaining] = useState(WARNING_WINDOW_S);
  const lastActivityRef = useRef(Date.now());
  // Mirrors `isWarning` for the activity listener's closure — once the warning is up,
  // moving the mouse must not silently reset the clock; only an explicit "Continue
  // Session" click (below) should.
  const isWarningRef = useRef(false);
  const hasExpiredRef = useRef(false);
  // Always current without re-subscribing the effect below on every SessionGuard render.
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  const continueSession = useCallback(() => {
    lastActivityRef.current = Date.now();
    isWarningRef.current = false;
    hasExpiredRef.current = false;
    setIsWarning(false);
    setSecondsRemaining(WARNING_WINDOW_S);
  }, []);

  useEffect(() => {
    if (!accessToken) return;
    lastActivityRef.current = Date.now();
    isWarningRef.current = false;
    hasExpiredRef.current = false;
    setIsWarning(false);
    setSecondsRemaining(WARNING_WINDOW_S);

    const onActivity = () => {
      if (isWarningRef.current) return;
      lastActivityRef.current = Date.now();
    };
    ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, onActivity, { passive: true }));

    const interval = window.setInterval(() => {
      const idleMs = Date.now() - lastActivityRef.current;
      if (idleMs >= IDLE_LOGOUT_MS) {
        if (!hasExpiredRef.current) {
          hasExpiredRef.current = true;
          onExpireRef.current();
        }
        return;
      }
      if (idleMs >= IDLE_WARNING_MS) {
        isWarningRef.current = true;
        setIsWarning(true);
        setSecondsRemaining(Math.max(0, Math.ceil((IDLE_LOGOUT_MS - idleMs) / 1000)));
      }
    }, 1000);

    return () => {
      ACTIVITY_EVENTS.forEach((evt) => window.removeEventListener(evt, onActivity));
      window.clearInterval(interval);
    };
  }, [accessToken]);

  return { isWarning, secondsRemaining, continueSession };
}
