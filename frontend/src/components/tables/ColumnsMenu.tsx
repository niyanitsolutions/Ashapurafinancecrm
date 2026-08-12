import { useEffect, useRef, useState } from "react";
import { Icon } from "@/theme/icons";

export interface ColumnOption {
  key: string;
  label: string;
}

// Real, working column show/hide chooser — purely a client-side display preference (not
// persisted, not sent to the backend), so it's presentation-only and doesn't touch
// filtering/sorting/pagination/data at all. Columns not passed here (e.g. Code, Name,
// Actions) are always shown — this only toggles the optional ones.
export function ColumnsMenu({
  columns,
  visible,
  onToggle,
}: {
  columns: ColumnOption[];
  visible: Set<string>;
  onToggle: (key: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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
        className="flex items-center gap-2 rounded-xl border border-border bg-card px-3.5 py-2.5 text-sm font-medium text-text hover:bg-background transition-colors"
      >
        <Icon name="grid" className="h-4 w-4 text-textSecondary" />
        Columns
      </button>
      {isOpen && (
        <div className="absolute right-0 mt-2 w-52 bg-card border border-border rounded-card shadow-dropdown p-2 z-20 animate-fade-in">
          {columns.map((col) => (
            <label
              key={col.key}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-text hover:bg-background cursor-pointer"
            >
              <input type="checkbox" checked={visible.has(col.key)} onChange={() => onToggle(col.key)} className="accent-primary" />
              {col.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
