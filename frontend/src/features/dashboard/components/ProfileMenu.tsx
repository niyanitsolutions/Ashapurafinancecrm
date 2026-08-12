import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/features/auth/useAuth";
import { Icon } from "@/theme/icons";

export function ProfileMenu({ displayName }: { displayName: string }) {
  const { role, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const initials = displayName
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-medium"
      >
        {initials || "?"}
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-card border border-border rounded-card shadow-card py-1 text-sm z-20">
          <div className="px-4 py-2 border-b border-border">
            <div className="font-medium text-text truncate">{displayName}</div>
            <div className="text-text/50 capitalize">{role}</div>
          </div>
          <Link
            to="/profile"
            className="flex items-center gap-2 px-4 py-2 hover:bg-background text-text"
            onClick={() => setIsOpen(false)}
          >
            <Icon name="user" className="h-4 w-4 text-text/50" />
            My Profile
          </Link>
          <Link
            to="/profile/change-password"
            className="flex items-center gap-2 px-4 py-2 hover:bg-background text-text"
            onClick={() => setIsOpen(false)}
          >
            <Icon name="shield-check" className="h-4 w-4 text-text/50" />
            Change Password
          </Link>
          <button
            type="button"
            className="w-full flex items-center gap-2 text-left px-4 py-2 hover:bg-background text-danger"
            onClick={() => {
              setIsOpen(false);
              logout();
            }}
          >
            <Icon name="logout" className="h-4 w-4" />
            Logout
          </button>
        </div>
      )}
    </div>
  );
}
