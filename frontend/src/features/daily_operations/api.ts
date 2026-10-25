import { apiRequest, getAccessToken } from "@/shared/api/client";

export type Area = "follow-ups" | "progress" | "sessions" | "issues";
export const areas: Record<Area, string> = {
  "follow-ups": "Daily Follow-up Data", progress: "Loan Progress Tracking",
  sessions: "Employee Login & Logout", issues: "Inquiry or Issue",
};
export interface Row { id: string; version?: number; [key: string]: unknown }
export interface DailyLookups {
  self_id: string;
  self_name?: string;
  employees: { id: string; name: string }[];
  leads: { id: string; name: string; number: string; code: string }[];
  cases: { id: string; name: string; number: string; code: string; bank: string; status?: string }[];
}
export const getLookups = (search = "") => apiRequest<DailyLookups>(`/daily-operations/lookups?search=${encodeURIComponent(search)}`);
export const deleteRecord = (area: Area, row: Row) => apiRequest(`/daily-operations/${area}/${row.id}`, { method: "DELETE", body: JSON.stringify({ version: row.version ?? 0 }) });
export interface List { items: Row[]; total: number; statuses?: Record<string, number>; metrics?: { approved_amount: number; disbursed_amount: number }; breakdowns?: Record<string, { label: string; count: number }[]> }
export interface RowError { column: string; message: string }
export interface Preview { id: string; policy: string; rows: { row: number; values: Record<string, string>; errors: RowError[]; duplicate?: boolean }[] }
export interface ImportResult { inserted: number; updated: number; skipped: number; rejected: number; errors: { row: number; errors: RowError[] }[] }
export const base = "/daily-operations";
export const listRecords = (area: Area, filters: string) => apiRequest<List>(`${base}/${area}?${filters}`);
export const getRecord = (area: Area, id: string) => apiRequest<Row>(`${base}/${area}/${id}`);
export const saveRecord = (area: Area, values: Record<string, unknown>, id?: string) => apiRequest<Row>(`${base}/${area}${id ? `/${id}` : ""}`, { method: id ? "PATCH" : "POST", body: JSON.stringify(values) });

export async function download(path: string, filename: string) {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}${path}`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { error?: { message?: string } } | null;
    throw new Error(error?.error?.message ?? "Download failed. Please sign in again if your session expired.");
  }
  downloadBlob(await response.blob(), filename);
}
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const followStatuses = ["FOLLOW UP PENDING", "NEXT FOLLOW UP", "DISBURSE", "REJECTED WITH REASON"];
export const issueStatuses = ["OPEN", "IN PROGRESS", "RESOLVED", "REOPENED"];
export const text = (value: unknown) => value === null || value === undefined || value === "" ? "—" : String(value);
export function businessTime(value: unknown) {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
}
