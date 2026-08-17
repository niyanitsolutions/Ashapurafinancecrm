import { useEffect, useState } from "react";
import { listEntityMessages, type CrmEntityType, type QueueItem } from "@/features/communication/api";
import { getErrorMessage } from "@/shared/api/errors";
import { formatISTDateTime } from "@/shared/dateFormat";

const STATUS_COLOR: Record<string, string> = {
  pending: "text-text/50",
  processing: "text-text/50",
  sent: "text-primary",
  delivered: "text-success",
  failed: "text-danger",
  retrying: "text-warning",
  exhausted: "text-danger",
};

const CHANNEL_LABEL: Record<string, string> = { whatsapp: "WhatsApp", sms: "SMS", email: "Email" };

// Shown on a Lead/Customer detail page — every message ever sent about this specific
// record (Secure Application Link shares, ad-hoc Send Message, and any future bulk
// message that targeted it), traced via entity_type/entity_id. Reused as-is for both
// entity types; the backend applies the same IDOR scoping as sending.
export function MessagesPanel({ entityType, entityId, refreshKey }: { entityType: CrmEntityType; entityId: string; refreshKey: number }) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEntityMessages(entityType, entityId)
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)));
  }, [entityType, entityId, refreshKey]);

  return (
    <div className="mt-6 bg-card border border-border rounded-card shadow-card p-6">
      <h3 className="text-sm font-semibold text-text/70 mb-3">Messages</h3>
      {error && <p className="text-sm text-danger mb-2">{error}</p>}
      {items.length === 0 ? (
        <p className="text-sm text-text/40">No messages yet.</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.id} className="border-l-2 border-border pl-3 py-1">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium text-text">{CHANNEL_LABEL[item.channel] ?? item.channel}</span>
                <span className={`text-xs font-medium capitalize ${STATUS_COLOR[item.status] ?? "text-text/50"}`}>{item.status}</span>
              </div>
              <div className="text-xs text-text/60 truncate max-w-md" title={item.rendered_body}>{item.rendered_body}</div>
              <div className="text-xs text-text/40">{formatISTDateTime(item.created_at)}</div>
              {item.error_detail && <div className="text-xs text-danger">{item.error_detail}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
