import { useEffect, useState } from "react";
import { Badge, StatusBadge } from "@/components/badges/Badge";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import {
  listAllSupportTickets,
  respondToSupportTicket,
  type SupportTicket,
  type TicketStatus,
} from "@/features/support/api";
import { formatISTDateTime } from "@/shared/dateFormat";

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const RESPOND_STATUS_OPTIONS: { value: TicketStatus; label: string }[] = [
  { value: "in_progress", label: "In Progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

function RespondModal({ ticket, onClose, onResponded }: { ticket: SupportTicket; onClose: () => void; onResponded: () => void }) {
  const [response, setResponse] = useState(ticket.staff_response ?? "");
  const [status, setStatus] = useState<TicketStatus>(ticket.status === "open" ? "in_progress" : ticket.status);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!response.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await respondToSupportTicket(ticket.id, response.trim(), status);
      onResponded();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Respond — ${ticket.ticket_code}`}
      description={ticket.subject}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" loading={isSubmitting} disabled={!response.trim()} onClick={onSubmit}>
            Send Response
          </Button>
        </>
      }
    >
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      <div className="space-y-3">
        <p className="rounded-lg bg-background p-3 text-sm text-textSecondary">{ticket.message}</p>
        <TextareaField label="Response" required rows={4} value={response} onChange={(e) => setResponse(e.target.value)} />
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value as TicketStatus)}
          options={RESPOND_STATUS_OPTIONS}
        />
      </div>
    </Modal>
  );
}

// Production stabilization pass — staff-side Support Ticket queue (list/respond),
// reusing the existing SupportTicket model/attachment plumbing (see backend
// support/service.py's list_all_tickets/respond_to_ticket). The customer-facing
// create/list-own flow (SupportPage) is untouched.
export function SupportTicketListPage() {
  const [tickets, setTickets] = useState<SupportTicket[] | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [respondingTo, setRespondingTo] = useState<SupportTicket | null>(null);

  const load = () => {
    listAllSupportTickets({ status: statusFilter || undefined })
      .then(setTickets)
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load tickets."));
  };

  useEffect(load, [statusFilter]);

  return (
    <SimplePageLayout title="Support Tickets">
      <ErrorBanner message={error} />

      <div className="mb-4 max-w-xs">
        <SelectField label="Status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} options={STATUS_FILTER_OPTIONS} />
      </div>

      {tickets === null && (
        <div className="animate-shimmer h-24 rounded-card bg-gradient-to-r from-border via-background to-border bg-[length:200%_100%]" />
      )}
      {tickets !== null && tickets.length === 0 && (
        <EmptyState icon="alert-triangle" title="No support tickets" description="Nothing matches this filter yet." />
      )}
      {tickets !== null && tickets.length > 0 && (
        <div className="overflow-x-auto rounded-card border border-border bg-card shadow-card">
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Ticket</Th>
                <Th>Subject</Th>
                <Th>Priority</Th>
                <Th>Assigned</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th>Action</Th>
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {tickets.map((t) => (
                <TableRow key={t.id}>
                  <Td>{t.ticket_code}</Td>
                  <Td>
                    <div className="max-w-xs truncate">{t.subject}</div>
                    <div className="text-2xs text-textSecondary capitalize">{t.issue_type}</div>
                  </Td>
                  <Td>
                    <Badge tone={t.priority === "high" ? "danger" : t.priority === "medium" ? "warning" : "neutral"}>{t.priority}</Badge>
                  </Td>
                  <Td>{t.assigned_to_name ?? "Unassigned"}</Td>
                  <Td>
                    <StatusBadge status={t.status} />
                  </Td>
                  <Td>{formatISTDateTime(t.created_at)}</Td>
                  <Td>
                    <Button size="sm" variant="secondary" onClick={() => setRespondingTo(t)}>
                      {t.staff_response ? "Update" : "Respond"}
                    </Button>
                  </Td>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {respondingTo && (
        <RespondModal
          ticket={respondingTo}
          onClose={() => setRespondingTo(null)}
          onResponded={load}
        />
      )}
    </SimplePageLayout>
  );
}
