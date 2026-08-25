import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getUnreadNotificationCount, listNotifications, markNotificationRead, type AppNotification } from "@/features/reminders/api";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

// Staff Topbar bell — wired to the same real Notification model/endpoints
// (RemindersService, GET /notifications*) the Customer Portal's own bell already uses
// (CustomerNotificationBell.tsx); this was previously a stub hitting a non-existent
// `/dashboard/notifications` endpoint that always returned empty (see
// docs/KNOWN_LIMITATIONS.md). Fixed as part of the Loan Management redesign so a staff
// member actually sees a notification when a customer uploads an Additional Document
// (requirement 15) — no second notification system, just this UI catching up to the
// one that already existed.
const POLL_INTERVAL_MS = 15_000;
const RECENT_LIMIT = 5;

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [recent, setRecent] = useState<AppNotification[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  const loadCount = () => {
    getUnreadNotificationCount()
      .then(setUnreadCount)
      .catch(() => undefined);
  };

  useEffect(() => {
    loadCount();
    const interval = window.setInterval(loadCount, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    listNotifications({ page: 1, page_size: RECENT_LIMIT })
      .then((res) => setRecent(res.data))
      .catch(() => setRecent([]));
  }, [isOpen]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const onOpenNotification = (n: AppNotification) => {
    if (n.status === "unread") {
      markNotificationRead(n.id)
        .then(() => {
          setUnreadCount((c) => Math.max(0, c - 1));
          setRecent((items) => items.map((i) => (i.id === n.id ? { ...i, status: "read" } : i)));
        })
        .catch(() => undefined);
    }
    setIsOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="relative w-9 h-9 rounded-full hover:bg-background flex items-center justify-center text-text/70"
        aria-label="Notifications"
      >
        <Icon name="bell" className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] leading-4 text-center font-medium">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-card border border-border rounded-card shadow-card py-1 text-sm z-20">
          <div className="px-4 py-2 border-b border-border font-medium text-text">Notifications</div>
          {recent.length === 0 ? (
            <div className="px-4 py-6 text-center text-text/50">You're all caught up.</div>
          ) : (
            <ul>
              {recent.map((n) => (
                <li key={n.id} className={n.status === "unread" ? "bg-primary/5" : undefined}>
                  <Link to="/notifications" onClick={() => onOpenNotification(n)} className="block px-4 py-2.5 hover:bg-background">
                    <p className="text-sm font-medium text-text">{n.title}</p>
                    <p className="text-xs text-text/60">{n.message}</p>
                    <p className="text-2xs text-text/40 mt-0.5">{formatISTDateTime(n.created_at)}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/notifications"
            onClick={() => setIsOpen(false)}
            className="block border-t border-border px-4 py-2 text-center text-primary hover:bg-background"
          >
            View All
          </Link>
        </div>
      )}
    </div>
  );
}
