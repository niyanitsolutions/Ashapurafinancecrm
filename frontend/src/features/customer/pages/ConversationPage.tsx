import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getOwnConversation, sendOwnMessage, type Conversation } from "@/features/messaging/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

// Production stabilization pass — "Message your RM", a real two-way thread with the
// customer's assigned Relationship Manager (see backend `messaging` module). Distinct
// from the pre-existing, unchanged one-way Communication History feed at
// /portal/notifications (MessagesPage.tsx) — that feed is real, working code and stays
// reachable there; this page is what "Message your RM" now opens.
export function ConversationPage() {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = () => {
    getOwnConversation()
      .then(setConversation)
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, []);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [conversation?.messages.length]);

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.trim()) return;
    setError(null);
    setIsSending(true);
    try {
      const updated = await sendOwnMessage(draft.trim());
      setConversation(updated);
      setDraft("");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <SimplePageLayout title="Message your RM" backTo="/portal">
      <ErrorBanner message={error} />

      <div className="max-w-2xl bg-card border border-border rounded-card shadow-card flex flex-col" style={{ height: "60vh" }}>
        <div className="border-b border-border px-4 py-3">
          <p className="text-sm font-medium text-text">{conversation?.employee_name ?? "Your Relationship Manager"}</p>
          {!conversation?.employee_id && conversation !== null && (
            <p className="text-xs text-text/50">Not yet assigned — our team will still see your message.</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {conversation === null && !error && <p className="text-sm text-text/40">Loading…</p>}
          {conversation !== null && conversation.messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center text-text/40">
              <Icon name="chat" className="h-8 w-8 mb-2" />
              <p className="text-sm">Send a message to start the conversation.</p>
            </div>
          )}
          {conversation?.messages.map((m) => (
            <div key={m.id} className={`flex ${m.sender_role === "customer" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${
                  m.sender_role === "customer" ? "bg-primary text-white" : "bg-background text-text"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.body}</p>
                <p className={`mt-1 text-2xs ${m.sender_role === "customer" ? "text-white/70" : "text-text/40"}`}>
                  {m.sender_role === "staff" ? `${m.sender_name} · ` : ""}
                  {formatISTDateTime(m.created_at)}
                </p>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={onSend} className="flex items-center gap-2 border-t border-border p-3">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message…"
            className="flex-1 rounded-xl border border-border px-3.5 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <button
            type="submit"
            disabled={!draft.trim() || isSending}
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </SimplePageLayout>
  );
}
