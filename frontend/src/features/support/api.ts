import { apiRequest } from "@/shared/api/client";

export type IssueType = "application" | "documents" | "payment" | "other";
export type TicketPriority = "low" | "medium" | "high";

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";

export interface SupportTicket {
  id: string;
  ticket_code: string;
  customer_id: string;
  issue_type: IssueType;
  priority: TicketPriority;
  subject: string;
  message: string;
  attachment_download_url: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  staff_response: string | null;
  responded_by_name: string | null;
  responded_at: string | null;
  status: TicketStatus;
  created_at: string;
  updated_at: string;
}

export interface CreateSupportTicketInput {
  issue_type: IssueType;
  priority: TicketPriority;
  subject: string;
  message: string;
  attachment_s3_key?: string;
}

export function getSupportAttachmentUploadUrl(fileName: string, contentType?: string) {
  return apiRequest<{ upload_url: string; s3_key: string }>("/support-tickets/attachment-upload-url", {
    method: "POST",
    body: JSON.stringify({ file_name: fileName, content_type: contentType }),
  });
}

export function createSupportTicket(payload: CreateSupportTicketInput) {
  return apiRequest<SupportTicket>("/support-tickets", { method: "POST", body: JSON.stringify(payload) });
}

export function listOwnSupportTickets() {
  return apiRequest<SupportTicket[]>("/support-tickets/me");
}

// ---------------------------------------------------------------- staff resolution workflow

export function listAllSupportTickets(params: { status?: string; search?: string } = {}) {
  const usp = new URLSearchParams();
  if (params.status) usp.set("status", params.status);
  if (params.search) usp.set("search", params.search);
  const qs = usp.toString();
  return apiRequest<SupportTicket[]>(`/support-tickets${qs ? `?${qs}` : ""}`);
}

export function getSupportTicket(ticketId: string) {
  return apiRequest<SupportTicket>(`/support-tickets/${ticketId}`);
}

export function respondToSupportTicket(ticketId: string, staffResponse: string, status?: TicketStatus) {
  return apiRequest<SupportTicket>(`/support-tickets/${ticketId}`, {
    method: "PATCH",
    body: JSON.stringify({ staff_response: staffResponse, status }),
  });
}
