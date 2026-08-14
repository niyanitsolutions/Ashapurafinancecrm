import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { search, type SearchResult } from "@/features/dashboard/api";

// `/dashboard/search` only covers Employees today (Module 5's own limitation — see
// docs/KNOWN_LIMITATIONS.md). Rather than show a "Search employees…" box on every page
// regardless of relevance (the source of the "search placeholder is unrelated to the
// current page" complaint), only render it where an employee lookup is actually a
// plausible action: the Dashboard itself, and the Administration cluster (Employees/
// Roles/Temporary Access/Geo Exceptions/Lead Capture — same route set navConfig.ts's
// Administration leaf treats as one module). Hidden everywhere else rather than invented
// a Lead/Customer search that doesn't exist on the backend.
const EMPLOYEE_SEARCH_PREFIXES = [
  "/employees",
  "/roles",
  "/temporary-access",
  "/geo-exceptions",
  "/settings/departments",
  "/settings/designations",
  "/lead-capture",
];

export function isEmployeeSearchRelevant(pathname: string): boolean {
  if (pathname === "/") return true;
  return EMPLOYEE_SEARCH_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function QuickSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const relevant = isEmployeeSearchRelevant(location.pathname);

  useEffect(() => {
    const trimmed = query.trim();
    if (!relevant || trimmed.length < 2) {
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
  }, [query, relevant]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (!relevant) return null;

  return (
    <div className="relative w-full max-w-sm" ref={ref}>
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setIsOpen(true)}
        placeholder="Search employees by name, code, mobile…"
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
