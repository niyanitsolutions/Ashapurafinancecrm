import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  getUnreadNotificationCount,
  listNotifications,
  markNotificationRead,
  type AppNotification,
} from "@/features/reminders/api";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

// Customer-facing counterpart of the (currently still stubbed) Staff Topbar bell — see
// dashboard/components/NotificationBell.tsx's own docstring. Reuses the exact same
// backend Notification model/endpoints (RemindersService, GET /notifications*) every
// staff notification already goes through; this is a new UI surface, not a new
// notification system. Same "short background poll" precedent LeadListPage/
// NotificationListPage already established — no push transport exists in this project.
const POLL_INTERVAL_MS = 15_000;
const RECENT_LIMIT = 5;

export function CustomerNotificationBell() {
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
        className="relative flex h-9 w-9 items-center justify-center rounded-full text-text/60 hover:bg-background hover:text-text"
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
        <div className="absolute right-0 mt-2 w-80 bg-card border border-border rounded-card shadow-dropdown py-1 text-sm z-30">
          <div className="px-4 py-2 border-b border-border font-medium text-text">Notifications</div>
          {recent.length === 0 ? (
            <div className="px-4 py-6 text-center text-text/50">You're all caught up.</div>
          ) : (
            <ul>
              {recent.map((n) => (
                <li key={n.id} className={n.status === "unread" ? "bg-primary/5" : undefined}>
                  <Link
                    to="/portal/documents"
                    onClick={() => onOpenNotification(n)}
                    className="block px-4 py-2.5 hover:bg-background"
                  >
                    <p className="text-sm font-medium text-text">{n.title}</p>
                    <p className="text-xs text-text/60">{n.message}</p>
                    <p className="text-2xs text-text/40 mt-0.5">{formatISTDateTime(n.created_at)}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/portal/alerts"
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
