import { apiRequest, getAccessToken } from "@/shared/api/client";
interface KycDocument { id: string }
export async function viewPartnerDocument(id: string) {
  const result = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}/partner-portal/documents/${id}`, { headers: { Authorization: `Bearer ${getAccessToken()}` } });
  if (!result.ok) throw new Error("Document access failed. Check your session and permission.");
  const url = URL.createObjectURL(await result.blob());
  const link = document.createElement("a"); link.href = url; link.target = "_blank"; link.rel = "noopener"; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function uploadPartnerDocument(file: File, category: string, part = "file", password = "", agreement = false) {
  const base = agreement ? "/partner-management/agreements" : "/partner-portal/kyc";
  const ticket = await apiRequest<{ticket: string; upload_url: string; upload_headers?: Record<string,string>}>(`${base}/uploads`, { method: "POST", body: JSON.stringify({ category, part, content_type: file.type, size: file.size }) });
  const put = await fetch(ticket.upload_url, { method: "PUT", headers: { "Content-Type": file.type, ...ticket.upload_headers }, body: file });
  if (!put.ok) throw new Error("Private upload failed. Retry the upload.");
  return apiRequest<KycDocument>(`${base}/${agreement ? "confirm" : "uploads/confirm"}`, { method: "POST", body: JSON.stringify({ ticket: ticket.ticket, pdf_password: password || null, consent: true }) });
}

