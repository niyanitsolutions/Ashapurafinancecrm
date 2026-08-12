import { apiRequest } from "@/shared/api/client";

export interface ReportDefinition {
  key: string;
  label: string;
  category: string;
  description: string;
}

export interface ReportColumn {
  key: string;
  label: string;
}

export interface ReportResult {
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  summary: Record<string, unknown> | null;
}

export interface SavedFilter {
  id: string;
  report_key: string;
  label: string;
  filters: Record<string, unknown>;
  created_at: string;
}

export interface ScheduledReport {
  id: string;
  report_key: string;
  label: string;
  filters: Record<string, unknown>;
  frequency: string;
  recipient_user_ids: string[];
  is_active: boolean;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

function toQuery(params: Record<string, string | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") usp.set(key, value);
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export function listReportDefinitions() {
  return apiRequest<ReportDefinition[]>("/reports");
}

export function runReport(reportKey: string, params: { date_from?: string; date_to?: string }) {
  return apiRequest<ReportResult>(`/reports/${reportKey}${toQuery(params)}`);
}

export function exportReportUrl(reportKey: string, params: { date_from?: string; date_to?: string }): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
  return `${base}/reports/${reportKey}/export${toQuery(params)}`;
}

export function createSavedFilter(payload: { report_key: string; label: string; filters: Record<string, unknown> }) {
  return apiRequest<SavedFilter>("/saved-filters", { method: "POST", body: JSON.stringify(payload) });
}

export function listSavedFilters(reportKey?: string) {
  return apiRequest<SavedFilter[]>(`/saved-filters${toQuery({ report_key: reportKey })}`);
}

export function deleteSavedFilter(filterId: string) {
  return apiRequest<null>(`/saved-filters/${filterId}`, { method: "DELETE" });
}

export function createScheduledReport(payload: { report_key: string; label: string; filters?: Record<string, unknown>; frequency: string; recipient_user_ids?: string[] }) {
  return apiRequest<ScheduledReport>("/scheduled-reports", { method: "POST", body: JSON.stringify(payload) });
}

export function listScheduledReports() {
  return apiRequest<ScheduledReport[]>("/scheduled-reports");
}

export function updateScheduledReport(scheduledReportId: string, payload: Record<string, unknown>) {
  return apiRequest<ScheduledReport>(`/scheduled-reports/${scheduledReportId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteScheduledReport(scheduledReportId: string) {
  return apiRequest<null>(`/scheduled-reports/${scheduledReportId}`, { method: "DELETE" });
}
