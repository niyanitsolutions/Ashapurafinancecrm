import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { Modal } from "@/components/overlays/Modal";
import { listNotifications, markNotificationRead, type AppNotification } from "@/features/reminders/api";
import { Icon } from "@/theme/icons";

// Customer-facing popup for an actionable unread rejection — shown once per portal
// session per notification (dismissing/acting on it marks it read via the existing
// mechanism, so it never nags again on a later page load). Mounted once in
// CustomerPortalLayout so it surfaces regardless of which page the customer lands on
// first, matching "the customer logs into the portal... a customer-facing alert/popup
// should be shown." Queued one at a time — if staff rejected more than one document
// since the customer's last visit, closing one reveals the next.
export function DocumentRejectionAlert() {
  const navigate = useNavigate();
  const [queue, setQueue] = useState<AppNotification[] | null>(null);

  useEffect(() => {
    listNotifications({ page: 1, page_size: 10, status: "unread", category: "document" })
      .then((res) => setQueue(res.data.filter((n) => n.notification_type === "document_rejected")))
      .catch(() => setQueue([]));
  }, []);

  const current = queue?.[0] ?? null;

  const dismiss = () => {
    if (!current) return;
    markNotificationRead(current.id).catch(() => undefined);
    setQueue((q) => (q ? q.slice(1) : q));
  };

  const onUpload = () => {
    dismiss();
    navigate("/portal/documents");
  };

  if (!current) return null;

  return (
    <Modal open onClose={dismiss} title="Document Requires Attention" size="sm">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-danger/10 text-danger">
          <Icon name="x-circle" className="h-5 w-5" />
        </span>
        <p className="text-sm text-text">{current.message}</p>
      </div>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button variant="secondary" size="sm" onClick={dismiss}>
          View Later
        </Button>
        <Button size="sm" onClick={onUpload}>
          Upload New Document
        </Button>
      </div>
    </Modal>
  );
}
