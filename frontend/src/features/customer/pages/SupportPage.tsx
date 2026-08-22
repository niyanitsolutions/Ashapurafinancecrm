import { useEffect, useState } from "react";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { SubmitButton } from "@/components/forms/SubmitButton";
import {
  createSupportTicket,
  getSupportAttachmentUploadUrl,
  listOwnSupportTickets,
  type IssueType,
  type SupportTicket,
  type TicketPriority,
} from "@/features/support/api";
import { getErrorMessage } from "@/features/customer/errors";
import { formatISTDateTime } from "@/shared/dateFormat";
import { Icon } from "@/theme/icons";

const ISSUE_TYPE_OPTIONS: { value: IssueType; label: string }[] = [
  { value: "application", label: "Application" },
  { value: "documents", label: "Documents" },
  { value: "payment", label: "Payment" },
  { value: "other", label: "Other" },
];
const PRIORITY_OPTIONS: { value: TicketPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];
const PRIORITY_STYLE: Record<TicketPriority, string> = {
  low: "text-text/50",
  medium: "text-warning",
  high: "text-danger",
};

// Customer Portal redesign — a real, listable Support Ticket (issue type/priority/
// attachment/history) alongside the existing lightweight Task/Notification side-effect
// to the Relationship Manager, which still fires unchanged on every ticket created.
export function SupportPage() {
  const [issueType, setIssueType] = useState<IssueType>("application");
  const [priority, setPriority] = useState<TicketPriority>("medium");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [tickets, setTickets] = useState<SupportTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadTickets = () => {
    listOwnSupportTickets()
      .then(setTickets)
      .catch(() => setTickets([]));
  };

  useEffect(loadTickets, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setConfirmation(null);
    setIsSubmitting(true);
    try {
      let attachment_s3_key: string | undefined;
      if (attachment) {
        const { upload_url, s3_key } = await getSupportAttachmentUploadUrl(attachment.name, attachment.type);
        await fetch(upload_url, { method: "PUT", body: attachment, headers: { "Content-Type": attachment.type || "application/octet-stream" } });
        attachment_s3_key = s3_key;
      }
      const ticket = await createSupportTicket({ issue_type: issueType, priority, subject, message, attachment_s3_key });
      setConfirmation(`Ticket ${ticket.ticket_code} created — our team (and your Relationship Manager, if assigned) has been notified.`);
      setSubject("");
      setMessage("");
      setAttachment(null);
      loadTickets();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SimplePageLayout title="Support" backTo="/portal">
      <ErrorBanner message={error} />
      {confirmation && <p className="mb-4 text-sm text-success">{confirmation}</p>}

      <form onSubmit={onSubmit} className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 mb-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Raise a Support Ticket</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
          <SelectField
            label="Issue Type"
            value={issueType}
            onChange={(e) => setIssueType(e.target.value as IssueType)}
            options={ISSUE_TYPE_OPTIONS}
          />
          <SelectField
            label="Priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value as TicketPriority)}
            options={PRIORITY_OPTIONS}
          />
          <div className="md:col-span-2">
            <FormField label="Subject" required value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div className="md:col-span-2 mb-4">
            <label className="block text-sm font-medium text-text mb-1">
              Description<span className="text-danger"> *</span>
            </label>
            <textarea
              required
              className="w-full rounded border border-border px-3 py-2 text-sm"
              rows={4}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </div>
          <div className="md:col-span-2 mb-4">
            <label className="block text-sm font-medium text-text mb-1">Attachment (optional)</label>
            <label className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text/70 hover:bg-background cursor-pointer">
              <Icon name="upload" className="h-4 w-4" />
              {attachment ? attachment.name : "Choose a file"}
              <input type="file" className="hidden" onChange={(e) => setAttachment(e.target.files?.[0] ?? null)} />
            </label>
          </div>
        </div>
        <SubmitButton isSubmitting={isSubmitting}>Submit Ticket</SubmitButton>
      </form>

      <div className="max-w-2xl">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Your Tickets</h2>
        {tickets === null && (
          <div className="animate-shimmer h-24 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
        )}
        {tickets !== null && tickets.length === 0 && <p className="text-sm text-text/50">No support tickets yet.</p>}
        {tickets !== null && tickets.length > 0 && (
          <div className="bg-card border border-border rounded-card shadow-card divide-y divide-border">
            {tickets.map((t) => (
              <div key={t.id} className="p-4">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-sm font-medium text-text">{t.subject}</span>
                  <span className={`text-xs font-medium ${PRIORITY_STYLE[t.priority]}`}>{t.priority.toUpperCase()}</span>
                </div>
                <p className="text-xs text-text/50 mb-1">
                  {t.ticket_code} · {t.issue_type} · {t.assigned_to_name ?? "Unassigned"}
                </p>
                <div className="flex items-center justify-between text-xs text-text/40">
                  <span className="capitalize">{t.status.replace(/_/g, " ")}</span>
                  <span>{formatISTDateTime(t.created_at)}</span>
                </div>
                {t.staff_response && (
                  <div className="mt-2 rounded-lg bg-background p-2.5 text-xs text-text/70">
                    <p className="mb-0.5 font-medium text-text/50">
                      Response from {t.responded_by_name ?? "our team"}
                      {t.responded_at ? ` · ${formatISTDateTime(t.responded_at)}` : ""}
                    </p>
                    <p>{t.staff_response}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </SimplePageLayout>
  );
}
