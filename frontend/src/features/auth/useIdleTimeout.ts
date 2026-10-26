import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/useAuth";

import { apiRequest } from "@/shared/api/client";

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
  const lastSentRef = useRef(0);
  const channelRef = useRef<BroadcastChannel | null>(null);
  const sendActivity = useCallback(() => {
    if (document.visibilityState === "hidden") return;
    if (Date.now() - lastSentRef.current < 30000) return;
    lastSentRef.current = Date.now();
    void apiRequest("/auth/activity", { method: "POST" }).catch(() => { /* Server expiry remains authoritative. */ });
  }, []);
  // Mirrors `isWarning` for the activity listener's closure — once the warning is up,
  // moving the mouse must not silently reset the clock; only an explicit "Continue
  // Session" click (below) should.
  const isWarningRef = useRef(false);
  const hasExpiredRef = useRef(false);
  // Always current without re-subscribing the effect below on every SessionGuard render.
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  const resetFromServer = useCallback(() => {
    lastActivityRef.current = Date.now();
    isWarningRef.current = false;
    hasExpiredRef.current = false;
    setIsWarning(false);
    setSecondsRemaining(WARNING_WINDOW_S);
  }, []);
  const continueSession = useCallback(() => {
    sendActivity();
    channelRef.current?.postMessage("activity");
    resetFromServer();
  }, [sendActivity, resetFromServer]);

  useEffect(() => {
    if (!accessToken) return;
    lastActivityRef.current = Date.now();
    isWarningRef.current = false;
    hasExpiredRef.current = false;
    setIsWarning(false);
    setSecondsRemaining(WARNING_WINDOW_S);

    let channel: BroadcastChannel | null = null;
    try {
      const encoded = accessToken.split(".")[1].replaceAll("-", "+").replaceAll("_", "/");
      const sid = (JSON.parse(atob(encoded)) as { sid?: string }).sid;
      if (sid && typeof BroadcastChannel !== "undefined") {
        channel = new BroadcastChannel(`afs-session-activity:${sid}`);
        channelRef.current = channel;
        channel.onmessage = event => {
          if (event.data !== "activity") return;
          lastActivityRef.current = Date.now();
          isWarningRef.current = false;
          hasExpiredRef.current = false;
          setIsWarning(false);
        };
      }
    } catch { /* Authentication checks token validity on the server. */ }
    const onActivity = (event: Event) => {
      if (!event.isTrusted || document.visibilityState === "hidden") return;
      if (isWarningRef.current) return;
      lastActivityRef.current = Date.now();
      sendActivity();
      channel?.postMessage("activity");
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
      channel?.close();
      channelRef.current = null;
    };
  }, [accessToken, sendActivity]);

  return { isWarning, secondsRemaining, continueSession, resetFromServer };
}
