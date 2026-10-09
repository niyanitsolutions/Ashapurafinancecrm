import { apiBlob, apiRequest } from "@/shared/api/client";

export interface BillingCustomer {
  name: string; address: string; city: string; state: string; pincode: string;
  country: string; gstin: string; phone: string; email: string;
}
export interface Item {
  description: string; hsn: string; quantity: string; unit: string; rate: string; gst_rate: string;
}
export interface InvoiceInput {
  customer_id: string | null; customer: BillingCustomer; invoice_date: string; due_date: string;
  place_of_supply: string; terms: string; tax_type: "IGST" | "CGST_SGST"; items: Item[]; version: number;
}
export type Status = "draft" | "issued" | "partially_paid" | "paid" | "cancelled";
export interface Invoice extends InvoiceInput {
  id: string; invoice_number: string; status: Status; subtotal: string; gst_total: string;
  grand_total: string; amount_in_words: string; created_by_name: string; created_at: string;
  cancellation_reason?: string;
}
export interface InvoiceConfig {
  gstin: string; website: string; bank_name: string; branch: string; account_number: string;
  account_holder: string; ifsc: string; prefix: string; starting_number: number; default_gst: string;
  default_terms: string; signatory: string; designation: string; signature_s3_key: string | null;
  show_signature: boolean; qr_type: "none" | "identifier" | "upi"; upi_id: string;
}
export interface Company extends InvoiceConfig {
  name: string; address: Record<string,string>; phone: string; email: string; logo_s3_key: string | null;
}
export interface CustomerOption { id: string; name: string; phone: string; email: string; address: Record<string,string> }
export function money(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  const tail = whole.slice(-3);
  const head = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `₹${head ? head + "," : ""}${tail}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}
export const getInvoice = (id: string) => apiRequest<Invoice>(`/invoices/${id}`);
export const listInvoices = (query: URLSearchParams) => apiRequest<{items: Invoice[]; total: number; total_pages: number}>(`/invoices?${query}`);
export const saveInvoice = (input: InvoiceInput, id?: string) => apiRequest<Invoice>(id ? `/invoices/${id}` : "/invoices", {method: id ? "PUT" : "POST", body: JSON.stringify(input)});
export const duplicateInvoice = (id: string) => apiRequest<Invoice>(`/invoices/${id}/duplicate`, {method: "POST"});
export const setInvoiceStatus = (id: string, status: Status, version: number, reason = "") => apiRequest<Invoice>(`/invoices/${id}/${status === "cancelled" ? "cancel" : "status"}`, {method: "POST", body: JSON.stringify(status === "cancelled" ? {reason, version} : {status, version})});
export const invoicePdf = (id: string, purpose = "preview") => apiBlob(`/invoices/${id}/pdf?purpose=${purpose}`);
export const previewPdf = (input: InvoiceInput) => apiBlob("/invoices/preview/pdf", {method: "POST", body: JSON.stringify(input)});
export const getDefaults = () => apiRequest<Company>("/invoices/defaults");
export const getCustomers = (search: string) => apiRequest<CustomerOption[]>(`/invoices/customers?search=${encodeURIComponent(search)}`);
export const getSettings = () => apiRequest<{config: InvoiceConfig; company: Company; assets: {logo: string | null; signature: string | null}}>("/invoice-settings");
export const saveSettings = (config: InvoiceConfig) => apiRequest<InvoiceConfig>("/invoice-settings", {method: "PUT", body: JSON.stringify(config)});
export function uploadSignature(file: File) {
  const data = new FormData(); data.append("file", file);
  return apiRequest<{s3_key: string; preview_url: string}>("/invoice-settings/signature", {method: "POST", body: data});
}
export function downloadPdf(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
}
