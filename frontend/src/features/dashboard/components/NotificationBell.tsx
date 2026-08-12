import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getNotifications, type NotificationsResult } from "@/features/dashboard/api";
import { Icon } from "@/theme/icons";

// Framework-ready: renders the bell + dropdown against a real endpoint, but there's no
// Notification Management module yet, so `available` is always false and the list is
// always empty today (see docs/KNOWN_LIMITATIONS.md).
export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const [result, setResult] = useState<NotificationsResult | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getNotifications()
      .then(setResult)
      .catch(() => setResult(null));
  }, []);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="relative w-9 h-9 rounded-full hover:bg-background flex items-center justify-center text-text/70"
        aria-label="Notifications"
      >
        <Icon name="bell" className="h-5 w-5" />
        {result && result.unread_count > 0 && (
          <span className="absolute top-1 right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] leading-4 text-center font-medium">
            {result.unread_count > 9 ? "9+" : result.unread_count}
          </span>
        )}
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 bg-card border border-border rounded-card shadow-card py-1 text-sm z-20">
          <div className="px-4 py-2 border-b border-border font-medium text-text">Notifications</div>
          {!result || !result.available || result.items.length === 0 ? (
            <div className="px-4 py-6 text-center text-text/50">
              {result?.available === false ? "You're all caught up." : "Nothing new."}
            </div>
          ) : (
            <ul>
              {result.items.map((item, i) => (
                <li key={i} className="px-4 py-2 hover:bg-background text-text">
                  {JSON.stringify(item)}
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
