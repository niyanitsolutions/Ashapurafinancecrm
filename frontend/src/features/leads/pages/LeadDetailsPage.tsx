import { useEffect, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EligibleAssigneeSelect } from "@/components/forms/EligibleAssigneeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { TextareaField } from "@/components/forms/TextareaField";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { usePermissions } from "@/features/access_control/usePermissions";
import { MessagesPanel } from "@/features/communication/components/MessagesPanel";
import { SendMessageModal } from "@/features/communication/components/SendMessageModal";
import { GenerateLinkModal } from "@/features/leads/components/GenerateLinkModal";
import { AddTaskModal } from "@/features/reminders/components/AddTaskModal";
import {
  addNote,
  assignLead,
  getLead,
  getTimeline,
  unassignLead,
  updateLead,
  type LeadDetail,
  type TimelineEntry,
} from "@/features/leads/api";
import { getErrorMessage } from "@/features/leads/errors";
import { Icon, type IconName } from "@/theme/icons";

function HeaderButton({
  icon,
  label,
  onClick,
  disabled,
  title,
  primary,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
  primary?: boolean;
}) {
  return (
    <Button
      variant={primary ? "primary" : "secondary"}
      size="sm"
      onClick={onClick}
      disabled={disabled}
      title={title}
      icon={<Icon name={icon} className="h-4 w-4" />}
    >
      {label}
    </Button>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}

function activityLabel(entry: TimelineEntry): string {
  const employeeName = entry.metadata && typeof entry.metadata.employee_name === "string" ? entry.metadata.employee_name : null;
  if (entry.event_type === "assigned" && employeeName) return `Lead assigned to ${employeeName}`;
  if (entry.event_type === "unassigned") return "Lead unassigned";
  return (entry.event_type ?? "").replace(/_/g, " ");
}

function TimelineItem({ entry }: { entry: TimelineEntry }) {
  const when = new Date(entry.created_at).toLocaleString();
  if (entry.type === "note") {
    return (
      <div className="border-l-2 border-primary/40 pl-3 py-1">
        <div className="text-sm text-text">{entry.text}</div>
        <div className="text-xs text-text/40">{when}</div>
      </div>
    );
  }
  return (
    <div className="border-l-2 border-border pl-3 py-1">
      <div className="text-sm text-text/70 first-letter:capitalize">{activityLabel(entry)}</div>
      <div className="text-xs text-text/40">{when}</div>
    </div>
  );
}

export function LeadDetailsPage() {
  const { can } = usePermissions();
  const canEdit = can("leads:leads", "edit");
  const canAssign = can("leads:leads", "assign");
  const canAddTask = can("reminders:tasks", "create");
  const canSendMessage = can("communication:send", "create");
  const { leadId } = useParams<{ leadId: string }>();
  const location = useLocation();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  // Table row's Edit action navigates here with `state: { startEditing: true }` so it
  // lands directly in edit mode; View navigates with no state, landing read-only — same
  // route either way (no new `/edit` route, per the "no routing changes" brief), just a
  // different entry intent carried the same way LoginPage/ForgotPassword already carry a
  // one-off `location.state.message`.
  const [isEditing, setIsEditing] = useState(() => Boolean((location.state as { startEditing?: boolean } | null)?.startEditing));
  const [remarks, setRemarks] = useState("");
  const [city, setCity] = useState("");
  const [preferredAmount, setPreferredAmount] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [noteText, setNoteText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [isSendMessageOpen, setIsSendMessageOpen] = useState(false);
  const [messagesRefreshKey, setMessagesRefreshKey] = useState(0);

  const resetFormFields = (l: LeadDetail) => {
    setRemarks(l.remarks ?? "");
    setCity(l.city ?? "");
    setPreferredAmount(l.preferred_amount != null ? String(l.preferred_amount) : "");
  };

  const load = () => {
    if (!leadId) return;
    getLead(leadId)
      .then((l) => {
        setLead(l);
        resetFormFields(l);
      })
      .catch((err) => setError(getErrorMessage(err)));
    getTimeline(leadId)
      .then(setTimeline)
      .catch(() => setTimeline([]));
  };

  useEffect(load, [leadId]);

  if (!leadId) return null;

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  if (error && !lead) {
    return (
      <SimplePageLayout title="Lead" backTo="/leads">
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!lead) {
    return (
      <SimplePageLayout title="Lead" backTo="/leads">
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout
      title={`${lead.full_name} (${lead.lead_code})`}
      backTo="/leads"
      actions={
        <div className="flex flex-wrap items-center gap-2.5">
          {isEditing ? (
            <HeaderButton
              icon="x-circle"
              label="Cancel"
              onClick={() => {
                resetFormFields(lead);
                setIsEditing(false);
              }}
            />
          ) : (
            <>
              <HeaderButton icon="print" label="Print" onClick={() => window.print()} />
              <HeaderButton icon="link" label="Generate Link" onClick={() => setIsLinkModalOpen(true)} />
              {canSendMessage && <HeaderButton icon="chat" label="Send Message" onClick={() => setIsSendMessageOpen(true)} />}
              {canAddTask && <HeaderButton icon="tasks" label="Add Task" onClick={() => setIsTaskModalOpen(true)} />}
              {canEdit && <HeaderButton icon="edit" label="Edit" onClick={() => setIsEditing(true)} primary />}
            </>
          )}
        </div>
      }
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 bg-card border border-border rounded-card shadow-card p-6 space-y-4">
          {lead.is_potential_duplicate && (
            <div className="rounded border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
              Possible duplicate — {lead.duplicate_of_lead_ids.length} other lead(s) share this mobile number.
            </div>
          )}

          {isEditing ? (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                await runAction(
                  () =>
                    updateLead(leadId, {
                      remarks,
                      city: city || undefined,
                      preferred_amount: preferredAmount ? Number(preferredAmount) : undefined,
                    }),
                  "Lead updated.",
                );
                setIsEditing(false);
              }}
              className="space-y-3"
            >
              <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
                <FormField label="City" value={city} onChange={(e) => setCity(e.target.value)} />
                <FormField label="Preferred Loan Amount" type="number" min={1} value={preferredAmount} onChange={(e) => setPreferredAmount(e.target.value)} />
              </div>
              <TextareaField label="Remarks" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
              <SubmitButton>Save Changes</SubmitButton>
            </form>
          ) : (
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
              <Field label="Mobile" value={lead.mobile} />
              <Field label="Email" value={lead.email} />
              <Field label="Source" value={lead.source_name} />
              <Field label="Product" value={`${lead.product_name} (${lead.product_category})`} />
              <Field label="City" value={lead.city} />
              <Field label="Preferred Loan Amount" value={lead.preferred_amount != null ? `₹${lead.preferred_amount.toLocaleString("en-IN")}` : null} />
              <Field label="Status" value={lead.status} />
              <Field label="Assigned To" value={lead.assigned_to_name} />
              <div className="col-span-2">
                <Field label="Remarks" value={lead.remarks} />
              </div>
            </div>
          )}
        </div>

        {canAssign && (
          <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3">
            <h3 className="text-sm font-semibold text-text/70">Assignment</h3>
            {lead.assigned_to ? (
              <Button
                variant="secondary"
                size="sm"
                className="w-full"
                onClick={() => runAction(() => unassignLead(leadId), "Lead unassigned.")}
              >
                Unassign ({lead.assigned_to_name})
              </Button>
            ) : (
              <div className="space-y-2">
                <EligibleAssigneeSelect
                  productCategory={lead.product_category}
                  productId={lead.product_id}
                  value={assigneeId}
                  onChange={setAssigneeId}
                />
                <Button
                  size="sm"
                  className="w-full"
                  disabled={!assigneeId}
                  onClick={() => runAction(() => assignLead(leadId, assigneeId), "Lead assigned.")}
                >
                  Assign
                </Button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="mt-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Timeline</h3>

        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!noteText.trim()) return;
            await runAction(() => addNote(leadId, noteText.trim()), "Note added.");
            setNoteText("");
          }}
          className="mb-4 flex items-end gap-3"
        >
          <div className="flex-1">
            <FormField label="Add a note" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
          </div>
          <div className="mb-4">
            <SubmitButton>Add</SubmitButton>
          </div>
        </form>

        <div className="space-y-1">
          {timeline.length === 0 && <p className="text-sm text-text/40">No activity yet.</p>}
          {timeline.map((entry, i) => (
            <TimelineItem key={i} entry={entry} />
          ))}
        </div>
      </div>

      <MessagesPanel entityType="lead" entityId={leadId} refreshKey={messagesRefreshKey} />

      {isLinkModalOpen && <GenerateLinkModal leadId={leadId} leadCode={lead.lead_code} onClose={() => setIsLinkModalOpen(false)} />}
      {isSendMessageOpen && (
        <SendMessageModal
          entityType="lead"
          entityId={leadId}
          entityLabel={`${lead.full_name} (${lead.lead_code})`}
          onClose={() => setIsSendMessageOpen(false)}
          onSent={() => setMessagesRefreshKey((k) => k + 1)}
        />
      )}
      {isTaskModalOpen && (
        <AddTaskModal
          relatedEntityType="lead"
          relatedEntityId={leadId}
          entityLabel={`Lead ${lead.lead_code}`}
          onClose={() => setIsTaskModalOpen(false)}
          onCreated={() => setMessage("Task added.")}
        />
      )}
    </SimplePageLayout>
  );
}
