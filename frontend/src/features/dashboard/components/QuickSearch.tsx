import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { search, type SearchResult } from "@/features/dashboard/api";

const sectionNames: Record<string,string> = {customer:"Customers",application:"Applications",lead:"Leads",employee:"Employees"};
function Highlight({ text, query }: { text: string; query: string }) {
  const needle=query.trim().toLowerCase();
  if(!needle) return <>{text}</>;
  const parts=[];let start=0;let next=text.toLowerCase().indexOf(needle);
  while(next>=0){parts.push(<span key={`text-${start}`}>{text.slice(start,next)}</span>);parts.push(<mark key={`match-${next}`} className="rounded bg-primary/15 text-inherit">{text.slice(next,next+needle.length)}</mark>);start=next+needle.length;next=text.toLowerCase().indexOf(needle,start);}
  parts.push(<span key={`tail-${start}`}>{text.slice(start)}</span>);return <>{parts}</>;
}
function secondary(result: SearchResult) {
  const fields=result.type==="customer"?[result.customer_code,result.mobile]:result.type==="application"?[result.customer_name,result.product_name,result.status,result.assigned_to_name || "Unassigned"]:result.type==="employee"?[result.employee_code,result.designation]:[];
  return fields.filter(Boolean).length > (result.type==="application"?1:0) ? fields.filter(Boolean).join(" | ") : result.subtitle || "";
}

export function QuickSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState(-1);
  const [page, setPage] = useState(1);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  useEffect(() => {
    let current = true;
    if (query.trim().length < 2) { setResults([]); setLoading(false); setError(""); setActive(-1); return; }
    setLoading(true); setError(""); setResults([]); setActive(-1);
    const timer = setTimeout(() => {
      search(query.trim(), page).then(r => { if (current) { setResults(r.results); setActive(-1); } })
        .catch(() => { if (current) { setResults([]); setError("Search is unavailable. Please try again."); } })
        .finally(() => { if (current) setLoading(false); });
    },250);
    return () => { current = false; clearTimeout(timer); };
  },[query,page]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown",close); return () => document.removeEventListener("mousedown",close);
  },[]);
  const ordered = ["customer","application","lead","employee"].flatMap(type => results.filter(result => result.type === type));
  const choose = (result: SearchResult) => { setOpen(false); setQuery(""); navigate(result.route); };
  return <div ref={ref} className="relative w-full max-w-md">
    <input role="combobox" aria-label="Search CRM" aria-expanded={open && query.trim().length >= 2} aria-controls="crm-search-results" aria-activedescendant={active >= 0 ? `crm-search-${active}` : undefined}
      type="search" maxLength={120} value={query} placeholder="Search customers, applications, leads..."
      className="w-full rounded-lg border border-border bg-card px-3 py-2 text-sm" onFocus={() => setOpen(true)}
      onChange={e => { setQuery(e.target.value); setPage(1); setOpen(true); }}
      onKeyDown={e => { if (e.key === "Escape") setOpen(false); if (e.key === "ArrowDown") { e.preventDefault(); setActive(i => Math.min(i+1,ordered.length-1)); } if (e.key === "ArrowUp") { e.preventDefault(); setActive(i => Math.max(i-1,0)); } if (e.key === "Enter" && ordered[active]) { e.preventDefault(); choose(ordered[active]); } }} />
    {open && query.trim().length >= 2 && <div className="absolute left-0 right-0 z-50 mt-1 max-h-[65vh] overflow-y-auto rounded-card border border-border bg-card p-2 shadow-card">
      {loading && <p role="status" className="p-2 text-sm">Searching...</p>}{error && <p role="alert" className="p-2 text-sm text-danger">{error}</p>}
      {!loading && !error && results.length === 0 && <p className="p-2 text-sm">No authorized matches. Try another name or ID.</p>}
      <div role="listbox" id="crm-search-results">{ordered.map((result,i) => <div key={`${result.type}-${result.id}`}>
        {(i === 0 || ordered[i-1].type !== result.type) && <p className="px-2 pt-2 text-xs font-semibold uppercase text-textSecondary">{sectionNames[result.type] || "Results"}</p>}
        <button id={`crm-search-${i}`} role="option" aria-selected={i === active} className={`w-full rounded p-2 text-left text-sm ${i === active ? "bg-primary/10" : "hover:bg-background"}`} onClick={() => choose(result)}>
          <span className="block font-medium"><Highlight text={result.label} query={query}/></span><span className="block break-words text-xs text-textSecondary"><Highlight text={secondary(result)} query={query}/></span>
        </button></div>)}</div>
      <div className="mt-2 flex justify-between gap-2"><button className="text-sm text-primary disabled:opacity-40" disabled={page === 1 || loading} onClick={() => setPage(p => p-1)}>Previous</button><span className="text-xs">Page {page}</span><button className="text-sm text-primary disabled:opacity-40" disabled={loading || results.length === 0} onClick={() => setPage(p => p+1)}>Next</button></div>
    </div>}
  </div>;
}
