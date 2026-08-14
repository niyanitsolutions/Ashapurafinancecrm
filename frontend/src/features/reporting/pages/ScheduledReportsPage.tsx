import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import {
  createScheduledReport,
  deleteScheduledReport,
  listReportDefinitions,
  listScheduledReports,
  updateScheduledReport,
  type ReportDefinition,
  type ScheduledReport,
} from "@/features/reporting/api";

function CreateScheduleModal({
  definitions, onClose, onSaved,
}: {
  definitions: ReportDefinition[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [reportKey, setReportKey] = useState("");
  const [label, setLabel] = useState("");
  const [frequency, setFrequency] = useState("weekly");
  const [recipients, setRecipients] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await createScheduledReport({
        report_key: reportKey, label, frequency,
        recipient_user_ids: recipients.split(",").map((r) => r.trim()).filter(Boolean),
      });
      onSaved("Schedule created.");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Create Schedule"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-schedule-form" size="sm" loading={isSubmitting}>
            Create Schedule
          </Button>
        </>
      }
    >
      <form id="create-schedule-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <SelectField
          label="Report"
          value={reportKey}
          onChange={(e) => setReportKey(e.target.value)}
          placeholder="Select report…"
          required
          options={definitions.map((d) => ({ value: d.key, label: d.label }))}
        />
        <FormField label="Label" value={label} onChange={(e) => setLabel(e.target.value)} required />
        <SelectField
          label="Frequency"
          value={frequency}
          onChange={(e) => setFrequency(e.target.value)}
          options={[
            { value: "daily", label: "Daily" },
            { value: "weekly", label: "Weekly" },
            { value: "monthly", label: "Monthly" },
          ]}
        />
        <FormField
          label="Recipient user IDs (optional)"
          value={recipients}
          onChange={(e) => setRecipients(e.target.value)}
          placeholder="Comma-separated"
        />
      </form>
    </Modal>
  );
}

export function ScheduledReportsPage() {
  const [items, setItems] = useState<ScheduledReport[]>([]);
  const [definitions, setDefinitions] = useState<ReportDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ScheduledReport | null>(null);

  const load = () => {
    setIsLoading(true);
    listScheduledReports()
      .then(setItems)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);
  useEffect(() => {
    listReportDefinitions().then(setDefinitions).catch(() => setDefinitions([]));
  }, []);

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
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

  return (
    <SimplePageLayout
      title="Automated Reports"
      subtitle="Set up a recurring schedule for any report — automatic email delivery is coming soon; for now, your schedule is saved and ready to activate."
      actions={<Button size="sm" onClick={() => setIsCreateOpen(true)}>+ Create Schedule</Button>}
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      {!isLoading && items.length === 0 ? (
        <EmptyState
          icon="reports"
          title="No automated reports yet"
          description="Create a schedule to have a report ready on a recurring basis."
          primaryAction={{ label: "+ Create Schedule", onClick: () => setIsCreateOpen(true) }}
        />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Label</th>
                <th className="px-4 py-3">Report</th>
                <th className="px-4 py-3">Frequency</th>
                <th className="px-4 py-3">Recipients</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
              {!isLoading &&
                items.map((item) => (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                    <td className="px-4 py-3">{item.label}</td>
                    <td className="px-4 py-3">{item.report_key.replace(/_/g, " ")}</td>
                    <td className="px-4 py-3 capitalize">{item.frequency}</td>
                    <td className="px-4 py-3">{item.recipient_user_ids.length}</td>
                    <td className="px-4 py-3">
                      <Button
                        variant={item.is_active ? "secondary" : "ghost"}
                        size="sm"
                        onClick={() => run(() => updateScheduledReport(item.id, { is_active: !item.is_active }), "Schedule updated.")}
                      >
                        {item.is_active ? "Active" : "Inactive"}
                      </Button>
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" onClick={() => setDeleteTarget(item)} className="text-danger hover:underline text-xs">
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {isCreateOpen && (
        <CreateScheduleModal
          definitions={definitions}
          onClose={() => setIsCreateOpen(false)}
          onSaved={(msg) => {
            setIsCreateOpen(false);
            setMessage(msg);
            load();
          }}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete Schedule"
        message={deleteTarget ? `Delete the "${deleteTarget.label}" schedule? This cannot be undone.` : ""}
        confirmLabel="Delete"
        confirmVariant="danger"
        onConfirm={async () => {
          if (!deleteTarget) return;
          await run(() => deleteScheduledReport(deleteTarget.id), "Schedule deleted.");
          setDeleteTarget(null);
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </SimplePageLayout>
  );
}
