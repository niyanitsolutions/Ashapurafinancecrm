import { useEffect, useRef, useState } from "react";

const HEARTBEAT_MS = 5000;
// A tab that's stopped heartbeating for this long is assumed closed/crashed — its lock
// is silently reclaimable rather than permanently blocking the application.
const STALE_AFTER_MS = 10000;

interface LockRecord {
  tabId: string;
  ts: number;
}

function lockKey(applicationId: string): string {
  return `afs_app_lock_${applicationId}`;
}

function readLock(applicationId: string): LockRecord | null {
  const raw = localStorage.getItem(lockKey(applicationId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as LockRecord;
  } catch {
    return null;
  }
}

// Warns when the same application is already open (and recently active) in another tab
// — scoped to the application wizard specifically, to avoid conflicting concurrent
// autosaves, not a site-wide mechanism. `status` starts "checking", resolves to "owned"
// (safe to edit) or "conflict" (another live tab holds it — caller shows a confirm
// dialog and calls `takeOver()` if the user wants to proceed anyway).
export function useApplicationTabLock(applicationId: string | undefined) {
  const [status, setStatus] = useState<"checking" | "owned" | "conflict">("checking");
  const [forceTakeOver, setForceTakeOver] = useState(false);
  const tabIdRef = useRef<string>(undefined);
  if (!tabIdRef.current) tabIdRef.current = crypto.randomUUID();

  useEffect(() => {
    if (!applicationId) return;
    const tabId = tabIdRef.current!;
    const key = lockKey(applicationId);

    if (!forceTakeOver) {
      const existing = readLock(applicationId);
      const isLiveElsewhere = existing && existing.tabId !== tabId && Date.now() - existing.ts < STALE_AFTER_MS;
      if (isLiveElsewhere) {
        setStatus("conflict");
        return;
      }
    }

    const writeLock = () => localStorage.setItem(key, JSON.stringify({ tabId, ts: Date.now() } satisfies LockRecord));
    writeLock();
    setStatus("owned");
    const heartbeat = window.setInterval(writeLock, HEARTBEAT_MS);
    return () => {
      window.clearInterval(heartbeat);
      const current = readLock(applicationId);
      if (current?.tabId === tabId) localStorage.removeItem(key);
    };
  }, [applicationId, forceTakeOver]);

  return { status, takeOver: () => setForceTakeOver(true) };
}
