import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type DashboardRange = "this_week" | "last_week" | "this_month" | "last_month" | "last_3_months" | "last_6_months" | "last_1_year" | "custom";

export interface DashboardFilters {
  range: DashboardRange;
  startDate?: string;
  endDate?: string;
  productCategory?: "loan" | "insurance";
  sourceId?: string;
}

export interface LeadSourceOption { id: string; label: string; }

interface DashboardFiltersValue {
  filters: DashboardFilters;
  setFilters: (filters: DashboardFilters) => void;
  sources: LeadSourceOption[];
  setSources: (sources: LeadSourceOption[]) => void;
}

const DashboardFiltersContext = createContext<DashboardFiltersValue | null>(null);

export function DashboardFiltersProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<DashboardFilters>({ range: "this_month" });
  const [sources, setSources] = useState<LeadSourceOption[]>([]);
  const value = useMemo(() => ({ filters, setFilters, sources, setSources }), [filters, sources]);
  return <DashboardFiltersContext.Provider value={value}>{children}</DashboardFiltersContext.Provider>;
}

export function useDashboardFilters() {
  const context = useContext(DashboardFiltersContext);
  if (!context) throw new Error("Dashboard filters must be used inside DashboardFiltersProvider.");
  return context;
}
