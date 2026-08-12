import { useEffect, useState } from "react";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
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

export function ScheduledReportsPage() {
  const [items, setItems] = useState<ScheduledReport[]>([]);
  const [definitions, setDefinitions] = useState<ReportDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Create Schedule</h3>
        <CreateScheduleForm
          definitions={definitions}
          onSubmit={(payload) => run(() => createScheduledReport(payload), "Schedule created.")}
        />
      </div>

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
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState icon="reports" title="No automated reports yet" description="Create a schedule above to have a report ready on a recurring basis." />
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{item.label}</td>
                <td className="px-4 py-3">{item.report_key.replace(/_/g, " ")}</td>
                <td className="px-4 py-3 capitalize">{item.frequency}</td>
                <td className="px-4 py-3">{item.recipient_user_ids.length}</td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => run(() => updateScheduledReport(item.id, { is_active: !item.is_active }), "Schedule updated.")}
                    className={`rounded border text-xs font-medium py-1 px-3 ${item.is_active ? "border-success text-success" : "border-text/30 text-text/50"}`}
                  >
                    {item.is_active ? "Active" : "Inactive"}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <button type="button" onClick={() => run(() => deleteScheduledReport(item.id), "Schedule deleted.")} className="text-danger hover:underline text-xs">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SimplePageLayout>
  );
}

function CreateScheduleForm({
  definitions, onSubmit,
}: {
  definitions: ReportDefinition[];
  onSubmit: (payload: { report_key: string; label: string; frequency: string; recipient_user_ids: string[] }) => void;
}) {
  const [reportKey, setReportKey] = useState("");
  const [label, setLabel] = useState("");
  const [frequency, setFrequency] = useState("weekly");
  const [recipients, setRecipients] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          report_key: reportKey, label, frequency,
          recipient_user_ids: recipients.split(",").map((r) => r.trim()).filter(Boolean),
        });
        setLabel("");
        setRecipients("");
      }}
      className="grid grid-cols-2 gap-3"
    >
      <select value={reportKey} onChange={(e) => setReportKey(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required>
        <option value="" disabled>Select report…</option>
        {definitions.map((d) => (
          <option key={d.key} value={d.key}>{d.label}</option>
        ))}
      </select>
      <input placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <select value={frequency} onChange={(e) => setFrequency(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
      </select>
      <input
        placeholder="Recipient user IDs, comma-separated (optional)" value={recipients} onChange={(e) => setRecipients(e.target.value)}
        className="rounded border border-border px-3 py-2 text-sm"
      />
      <div className="col-span-2">
        <SubmitButton>Create Schedule</SubmitButton>
      </div>
    </form>
  );
}
