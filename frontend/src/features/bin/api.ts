import { apiRequest, apiRequestRaw, type PaginationMeta } from "@/shared/api/client";

// Centralized Bin — Owner-only. Every endpoint here 403s for a non-Owner server-side;
// the UI additionally hides the affordances (see useListDelete / RequireOwner).

export interface BinEntry {
  id: string;
  resource_key: string;
  module_label: string;
  stage_label: string | null;
  record_code: string | null;
  record_summary: string | null;
  document_id: string;
  deleted_by: string;
  deleted_by_name: string | null;
  deleted_at: string;
  purge_at: string;
}

export interface DeletableResource {
  key: string;
  module_label: string;
}

export function listDeletableResources() {
  return apiRequest<DeletableResource[]>("/bin/resources");
}

export async function listBin(params: { page?: number; page_size?: number; module?: string; search?: string } = {}) {
  const q = new URLSearchParams();
  if (params.page) q.set("page", String(params.page));
  if (params.page_size) q.set("page_size", String(params.page_size));
  if (params.module) q.set("module", params.module);
  if (params.search) q.set("search", params.search);
  const qs = q.toString();
  const envelope = await apiRequestRaw<BinEntry[]>(`/bin${qs ? `?${qs}` : ""}`);
  const pagination: PaginationMeta | null = envelope.meta?.pagination ?? null;
  return { data: envelope.data ?? [], pagination };
}

export function deleteRecord(resourceKey: string, documentId: string) {
  return apiRequest<BinEntry>(`/bin/${resourceKey}/${documentId}`, { method: "DELETE" });
}

export function bulkDeleteRecords(resourceKey: string, documentIds: string[]) {
  return apiRequest<{ deleted: string[]; skipped: { document_id: string; reason: string }[] }>(
    `/bin/${resourceKey}/bulk-delete`,
    { method: "POST", body: JSON.stringify({ document_ids: documentIds }) },
  );
}

export function restoreRecord(binEntryId: string) {
  return apiRequest<BinEntry>(`/bin/${binEntryId}/restore`, { method: "POST" });
}
