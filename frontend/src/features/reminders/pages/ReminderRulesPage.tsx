import { useEffect, useState } from "react";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  activateReminderRule,
  deactivateReminderRule,
  listReminderRules,
  updateReminderRule,
  type ReminderRule,
} from "@/features/reminders/api";

export function ReminderRulesPage() {
  const [rules, setRules] = useState<ReminderRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    setIsLoading(true);
    listReminderRules()
      .then(setRules)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

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
    <SimplePageLayout title="Reminder Rules">
      <p className="mb-4 text-sm text-text/60">
        Timings for the Reminder Engine — never hardcoded. Edit a value and it applies the next time the scheduler runs.
      </p>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      {isLoading ? (
        <p className="text-sm text-text/50">Loading…</p>
      ) : (
        <div className="space-y-4">
          {rules.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              onSave={(payload) => run(() => updateReminderRule(rule.id, payload), "Rule updated.")}
              onToggle={() => run(() => (rule.status === "active" ? deactivateReminderRule(rule.id) : activateReminderRule(rule.id)), "Rule status updated.")}
            />
          ))}
        </div>
      )}
    </SimplePageLayout>
  );
}

function formatOffsets(values: number[] | null): string {
  return (values ?? []).join(", ");
}

function parseOffsets(text: string): number[] {
  return text
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
}

function RuleCard({ rule, onSave, onToggle }: { rule: ReminderRule; onSave: (payload: Record<string, unknown>) => void; onToggle: () => void }) {
  const isReEligibility = rule.rule_type === "re_eligibility";
  const [eligibleAfterDays, setEligibleAfterDays] = useState(rule.eligible_after_days ?? 0);
  const [notifyBeforeDaysText, setNotifyBeforeDaysText] = useState(formatOffsets(rule.notify_before_days));
  const [notifyBeforeMinutesText, setNotifyBeforeMinutesText] = useState(formatOffsets(rule.notify_before_minutes));
  const [escalationRepeatMinutes, setEscalationRepeatMinutes] = useState(rule.escalation_repeat_minutes ?? 0);
  const [escalationMaxRepeats, setEscalationMaxRepeats] = useState(rule.escalation_max_repeats ?? 0);

  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-text">{rule.label}</h3>
          <p className="text-xs text-text/50">{rule.rule_type === "re_eligibility" ? `Case type: ${rule.case_type}` : "Task Due"}</p>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className={`rounded border text-xs font-medium py-1 px-3 ${rule.status === "active" ? "border-success text-success" : "border-text/30 text-text/50"}`}
        >
          {rule.status === "active" ? "Active" : "Inactive"}
        </button>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (isReEligibility) {
            onSave({ eligible_after_days: eligibleAfterDays, notify_before_days: parseOffsets(notifyBeforeDaysText) });
          } else {
            onSave({
              notify_before_minutes: parseOffsets(notifyBeforeMinutesText), escalation_repeat_minutes: escalationRepeatMinutes,
              escalation_max_repeats: escalationMaxRepeats,
            });
          }
        }}
        className="grid grid-cols-3 gap-3"
      >
        {isReEligibility ? (
          <>
            <label className="text-xs text-text/60">
              Eligible After (days)
              <input type="number" value={eligibleAfterDays} onChange={(e) => setEligibleAfterDays(Number(e.target.value))} className="mt-1 w-full rounded border border-border px-3 py-2 text-sm" />
            </label>
            <label className="text-xs text-text/60 col-span-2">
              Notify Before (days) — comma-separated, e.g. "30, 15, 7, 1" for multiple reminders
              <input
                type="text" value={notifyBeforeDaysText} onChange={(e) => setNotifyBeforeDaysText(e.target.value)}
                className="mt-1 w-full rounded border border-border px-3 py-2 text-sm"
              />
            </label>
          </>
        ) : (
          <>
            <label className="text-xs text-text/60">
              Notify Before (minutes) — comma-separated for multiple reminders
              <input
                type="text" value={notifyBeforeMinutesText} onChange={(e) => setNotifyBeforeMinutesText(e.target.value)}
                className="mt-1 w-full rounded border border-border px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs text-text/60">
              Escalation Repeat (minutes)
              <input type="number" value={escalationRepeatMinutes} onChange={(e) => setEscalationRepeatMinutes(Number(e.target.value))} className="mt-1 w-full rounded border border-border px-3 py-2 text-sm" />
            </label>
            <label className="text-xs text-text/60">
              Max Escalations
              <input type="number" value={escalationMaxRepeats} onChange={(e) => setEscalationMaxRepeats(Number(e.target.value))} className="mt-1 w-full rounded border border-border px-3 py-2 text-sm" />
            </label>
          </>
        )}
        <div className="col-span-3">
          <button type="submit" className="rounded bg-primary text-white text-sm font-medium py-2 px-4">Save</button>
        </div>
      </form>
    </div>
  );
}
