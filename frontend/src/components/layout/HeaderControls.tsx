import { useEffect, useRef, useState } from "react";
import { useDashboardFilters, type DashboardFilters, type DashboardRange } from "@/features/dashboard/DashboardFiltersContext";
import { Icon } from "@/theme/icons";

const RANGE_LABELS: Record<DashboardRange, string> = {
  this_week: "This Week", last_week: "Last Week", this_month: "This Month",
  last_month: "Last Month", last_3_months: "Last 3 Months", last_6_months: "Last 6 Months",
  last_1_year: "Last 1 Year", custom: "Custom",
};

function useDismiss(ref: React.RefObject<HTMLDivElement | null>, close: () => void) {
  useEffect(() => {
    const dismiss = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, [close, ref]);
}

const inputClass = "mt-1 block w-full rounded-lg border border-border bg-background px-2 py-2 text-sm";

export function DateScopePill() {
  const { filters, setFilters } = useDashboardFilters();
  const [open, setOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [startDate, setStartDate] = useState(filters.startDate ?? "");
  const [endDate, setEndDate] = useState(filters.endDate ?? "");
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, () => setOpen(false));
  const invalid = Boolean(startDate && endDate && startDate > endDate);

  const choose = (range: DashboardRange) => {
    if (range === "custom") { setCustomOpen(true); return; }
    setFilters({ ...filters, range, startDate: undefined, endDate: undefined });
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => {
          setCustomOpen(filters.range === "custom");
          setStartDate(filters.startDate ?? "");
          setEndDate(filters.endDate ?? "");
          setOpen((value) => !value);
        }}
        className="flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-2xs font-medium text-text hover:bg-card"
        aria-expanded={open}
      >
        <Icon name="calendar" className="h-4 w-4 text-textSecondary" />
        {filters.range === "custom" ? `${filters.startDate} – ${filters.endDate}` : RANGE_LABELS[filters.range]}
        <Icon name="chevron-down" className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute left-0 z-30 mt-2 w-60 rounded-card border border-border bg-card p-2 shadow-dropdown sm:left-auto sm:right-0">
          {(Object.keys(RANGE_LABELS) as DashboardRange[]).map((range) => (
            <button key={range} type="button" onClick={() => choose(range)}
              className={`w-full rounded-lg px-3 py-2 text-left text-sm ${filters.range === range ? "bg-primary/10 font-semibold text-primary" : "text-text hover:bg-background"}`}>
              {RANGE_LABELS[range]}
            </button>
          ))}
          {customOpen && (
            <div className="mt-2 space-y-2 border-t border-border px-2 pt-3">
              <label className="block text-2xs font-medium">Start Date
                <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className={inputClass} />
              </label>
              <label className="block text-2xs font-medium">End Date
                <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className={inputClass} />
              </label>
              {invalid && <p role="alert" className="text-2xs text-danger">Start Date cannot be after End Date.</p>}
              <button type="button" disabled={!startDate || !endDate || invalid}
                onClick={() => { setFilters({ ...filters, range: "custom", startDate, endDate }); setOpen(false); }}
                className="w-full rounded-lg bg-primary px-3 py-2 text-2xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
                Apply custom range
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function FiltersButton() {
  const { filters, setFilters, sources } = useDashboardFilters();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<DashboardFilters>(filters);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, () => setOpen(false));
  const active = Number(Boolean(filters.productCategory)) + Number(Boolean(filters.sourceId));

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => { setDraft(filters); setOpen((value) => !value); }}
        className="flex items-center gap-2 rounded-xl border border-border px-3.5 py-2 text-2xs font-medium text-text hover:bg-background" aria-expanded={open}>
        <Icon name="filter" className="h-4 w-4 text-textSecondary" />Filters{active ? ` (${active})` : ""}
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-72 rounded-card border border-border bg-card p-4 shadow-dropdown">
          <p className="mb-3 text-sm font-semibold text-text">Dashboard filters</p>
          <label className="block text-2xs font-medium text-text">Product
            <select value={draft.productCategory ?? ""}
              onChange={(event) => setDraft({ ...draft, productCategory: (event.target.value || undefined) as DashboardFilters["productCategory"] })}
              className={inputClass}>
              <option value="">All products</option><option value="loan">Loan</option><option value="insurance">Insurance</option>
            </select>
          </label>
          <label className="mt-3 block text-2xs font-medium text-text">Lead Source
            <select value={draft.sourceId ?? ""} onChange={(event) => setDraft({ ...draft, sourceId: event.target.value || undefined })} className={inputClass}>
              <option value="">All sources</option>
              {sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}
            </select>
          </label>
          <div className="mt-4 flex justify-between gap-2">
            <button type="button" onClick={() => {
              const next = { ...filters, productCategory: undefined, sourceId: undefined };
              setDraft(next); setFilters(next); setOpen(false);
            }} className="rounded-lg px-3 py-2 text-sm font-medium text-textSecondary hover:bg-background">Clear</button>
            <button type="button" onClick={() => {
              setFilters({ ...filters, productCategory: draft.productCategory, sourceId: draft.sourceId });
              setOpen(false);
            }} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Apply</button>
          </div>
        </div>
      )}
    </div>
  );
}
