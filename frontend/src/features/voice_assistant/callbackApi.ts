import { apiRequest } from "@/shared/api/client";

export type CallbackEntity = "lead" | "loan_case" | "insurance_case";
export interface CallbackRow { id: string; version: number; state: string; due_at: string; requested_local: string; timezone: string; environment: "test" | "production"; entity_type: CallbackEntity; entity_id: string; customer_id: string | null; customer_request: string; provenance: string; source_call_id: string | null; confirmed_at: string | null; blockers: string[]; calls_placed: number; history_count: number }
export interface CallbackRequest { environment: "test" | "production"; entity_type: CallbackEntity; entity_id: string; assigned_to: string; requested_local: string; timezone: string; dst_fold?: number; customer_request: string; idempotency_key: string }
export interface CallbackChange { version: number; action: "confirm" | "cancel" | "reschedule" | "retry_readiness"; reason: string; requested_local?: string; timezone?: string; dst_fold?: number }
export interface CallbackList { items: CallbackRow[]; total: number; capabilities: { create: boolean; edit: boolean; current_employee_id: string | null }; live_dispatch: string }
export interface CallbackEvent { event: string; at: string; request?: string; reason?: string; old_due_at?: string; new_due_at?: string; old_timezone?: string; new_timezone?: string; calls_placed?: number; blockers?: string[] }
const base = "/voice-assistant/callbacks";
export const resolveCallbackOwner = (id: string, version: number, reason: string) => apiRequest<{ id: string; version: number; state: string }>(`${base}/${id}/resolve-owner`, { method: "POST", body: JSON.stringify({ version, action: "cancel", reason }) });
export const getCallbacks = (entity: CallbackEntity, id: string, environment: string, page: number) => apiRequest<CallbackList>(`${base}?${new URLSearchParams({ entity_type: entity, entity_id: id, environment, page: String(page) })}`);
export const createCallback = (data: CallbackRequest) => apiRequest<CallbackRow>(base, { method: "POST", body: JSON.stringify(data) });
export const changeCallback = (row: CallbackRow, data: Omit<CallbackChange, "version">) => apiRequest<CallbackRow>(`${base}/${row.id}/actions`, { method: "POST", body: JSON.stringify({ version: row.version, ...data }) });
export const getCallbackHistory = (id: string, page: number) => apiRequest<{ items: CallbackEvent[]; total: number }>(`${base}/${id}/history?page=${page}`);
export interface CallbackTimePreview { status: "proposed" | "clarification_required"; requested_local: string | null; timezone: string; clarification: string; interpreted_date?: string; requires_confirmation: true; persisted: false }
export const previewCallbackTime = (request: string, timezone: string) => apiRequest<CallbackTimePreview>("/voice-assistant/callbacks/interpret-time", { method: "POST", body: JSON.stringify({ request, timezone }) });
