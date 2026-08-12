import { apiRequest } from "@/shared/api/client";

export type IssueType = "application" | "documents" | "payment" | "other";
export type TicketPriority = "low" | "medium" | "high";

export interface SupportTicket {
  id: string;
  ticket_code: string;
  issue_type: IssueType;
  priority: TicketPriority;
  subject: string;
  message: string;
  attachment_download_url: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  status: string;
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
