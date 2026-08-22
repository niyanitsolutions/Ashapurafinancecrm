import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import {
  getConversation,
  listConversations,
  sendStaffMessage,
  type Conversation,
} from "@/features/messaging/api";
import { formatISTDateTime } from "@/shared/dateFormat";

// Production stabilization pass — staff-side "Customer Messages" (see backend
// `messaging` module). List + thread, same shape as every other staff list+detail page
// in this codebase (e.g. Support Tickets).
export function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [thread, setThread] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadList = () => {
    listConversations()
      .then(setConversations)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load conversations."));
  };

  useEffect(loadList, []);

  const loadThread = (id: string) => {
    setSelectedId(id);
    getConversation(id)
      .then(setThread)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load this conversation."));
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [thread?.messages.length]);

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || !selectedId) return;
    setError(null);
    setIsSending(true);
    try {
      const updated = await sendStaffMessage(selectedId, draft.trim());
      setThread(updated);
      setDraft("");
      loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send message.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <SimplePageLayout title="Customer Messages">
      <ErrorBanner message={error} />

      {conversations !== null && conversations.length === 0 && (
        <EmptyState icon="chat" title="No conversations yet" description="Customer messages will show up here." />
      )}

      {conversations !== null && conversations.length > 0 && (
        <div className="flex gap-4" style={{ height: "65vh" }}>
          <div className="w-72 shrink-0 overflow-y-auto rounded-card border border-border bg-card shadow-card">
            {conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => loadThread(c.id)}
                className={`block w-full border-b border-border p-3 text-left hover:bg-background ${selectedId === c.id ? "bg-background" : ""}`}
              >
                <p className="text-sm font-medium text-text truncate">{c.customer_name ?? "Customer"}</p>
                <p className="text-xs text-textSecondary truncate">{c.last_message_preview || "No messages yet"}</p>
                <p className="text-2xs text-textSecondary">{formatISTDateTime(c.last_message_at)}</p>
              </button>
            ))}
          </div>

          <div className="flex flex-1 flex-col rounded-card border border-border bg-card shadow-card">
            {thread === null ? (
              <div className="flex flex-1 items-center justify-center text-sm text-textSecondary">Select a conversation</div>
            ) : (
              <>
                <div className="border-b border-border px-4 py-3">
                  <p className="text-sm font-medium text-text">{thread.customer_name ?? "Customer"}</p>
                </div>
                <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                  {thread.messages.map((m) => (
                    <div key={m.id} className={`flex ${m.sender_role === "staff" ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${
                          m.sender_role === "staff" ? "bg-primary text-white" : "bg-background text-text"
                        }`}
                      >
                        <p className="whitespace-pre-wrap">{m.body}</p>
                        <p className={`mt-1 text-2xs ${m.sender_role === "staff" ? "text-white/70" : "text-text/40"}`}>
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
                    placeholder="Type a reply…"
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
              </>
            )}
          </div>
        </div>
      )}
    </SimplePageLayout>
  );
}
