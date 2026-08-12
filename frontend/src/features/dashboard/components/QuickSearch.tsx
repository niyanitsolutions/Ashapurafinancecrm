import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { search, type SearchResult } from "@/features/dashboard/api";

// Searches whatever entities the current user can already see today — Employees only
// (via Module 2's data, permission-gated in the backend). Extends naturally once
// Leads/Customers exist: the backend adds more entity types to the same /search response.
export function QuickSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      return;
    }
    const handle = setTimeout(() => {
      search(trimmed)
        .then((r) => {
          setResults(r.results);
          setIsOpen(true);
        })
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="relative w-full max-w-sm" ref={ref}>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        placeholder="Search employees…"
        className="w-full rounded border border-border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
      {isOpen && results.length > 0 && (
        <div className="absolute left-0 mt-1 w-full bg-card border border-border rounded-card shadow-card py-1 text-sm z-20">
          {results.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              type="button"
              className="w-full text-left px-4 py-2 hover:bg-background"
              onClick={() => {
                setIsOpen(false);
                setQuery("");
                navigate(r.route);
              }}
            >
              <div className="text-text">{r.label}</div>
              {r.subtitle && <div className="text-text/50 text-xs">{r.subtitle}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
