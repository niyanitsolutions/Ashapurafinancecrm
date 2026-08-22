import { apiRequest } from "@/shared/api/client";

export interface ConversationMessage {
  id: string;
  sender_role: "customer" | "staff";
  sender_name: string;
  body: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  customer_id: string;
  customer_name: string | null;
  employee_id: string | null;
  employee_name: string | null;
  last_message_at: string;
  last_message_preview: string;
  messages: ConversationMessage[];
}

// ---------------------------------------------------------------- customer side

export function getOwnConversation() {
  return apiRequest<Conversation>("/conversations/me");
}

export function sendOwnMessage(body: string) {
  return apiRequest<Conversation>("/conversations/me/messages", { method: "POST", body: JSON.stringify({ body }) });
}

// ---------------------------------------------------------------- staff side

export function listConversations() {
  return apiRequest<Conversation[]>("/conversations");
}

export function getConversation(conversationId: string) {
  return apiRequest<Conversation>(`/conversations/${conversationId}`);
}

export function sendStaffMessage(conversationId: string, body: string) {
  return apiRequest<Conversation>(`/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify({ body }) });
}
