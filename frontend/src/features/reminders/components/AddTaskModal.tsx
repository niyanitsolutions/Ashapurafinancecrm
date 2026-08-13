import { useEffect, useState } from "react";
import { listEmployees, type EmployeeListItem } from "@/features/employee/api";
import { createTask } from "@/features/reminders/api";
import { getErrorMessage } from "@/features/leads/errors";
import { Icon } from "@/theme/icons";

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
] as const;

function OutlineButton({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border text-text text-sm font-medium py-2 px-3.5 transition-colors hover:bg-background disabled:opacity-50"
    >
      {children}
    </button>
  );
}

// Quick "Add Task" action triggerable from a Lead/Customer detail page — reuses the same
// `POST /tasks` endpoint as the standalone Tasks page's own Assign Task form, just
// pre-filling `related_entity_type`/`related_entity_id` so the created task shows up
// linked to the record it was raised from. Employee picker fetches `GET /employees`
// directly (Owner-only, matching this modal's Owner-only call sites) rather than a
// generic assignee-select component, since none exists yet for an unfiltered employee list.
export function AddTaskModal({
  relatedEntityType,
  relatedEntityId,
  entityLabel,
  onClose,
  onCreated,
}: {
  relatedEntityType: string;
  relatedEntityId: string;
  entityLabel: string;
  onClose: () => void;
  onCreated?: () => void;
}) {
  const [employees, setEmployees] = useState<EmployeeListItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]["value"]>("medium");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEmployees({ page: 1, page_size: 100, status: "active" })
      .then((res) => setEmployees(res.data))
      .catch((err) => setLoadError(getErrorMessage(err)));
  }, []);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await createTask({
        title, description: description || undefined, assigned_to: assignedTo, due_at: new Date(dueAt).toISOString(),
        priority, related_entity_type: relatedEntityType, related_entity_id: relatedEntityId,
      });
      onCreated?.();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-md bg-card border border-border rounded-2xl shadow-dropdown p-6">
        <div className="flex items-center gap-2.5 mb-1">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Icon name="tasks" className="h-4 w-4" />
          </span>
          <h2 className="text-lg font-bold text-text">Add Task</h2>
        </div>
        <p className="text-2xs text-textSecondary mb-4 ml-[46px]">{entityLabel}</p>

        {error && <p className="mb-3 text-sm text-danger">{error}</p>}
        {loadError && <p className="mb-3 text-sm text-danger">{loadError}</p>}

        <form onSubmit={onSubmit} className="space-y-3">
          <input
            placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded border border-border px-3 py-2 text-sm" required
          />
          <select
            value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)}
            className="w-full rounded border border-border px-3 py-2 text-sm" required
          >
            <option value="" disabled>
              {employees === null ? "Loading employees…" : "Assign to…"}
            </option>
            {employees?.map((emp) => (
              <option key={emp.id} value={emp.id}>{emp.display_name}</option>
            ))}
          </select>
          <input
            type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)}
            className="w-full rounded border border-border px-3 py-2 text-sm" required
          />
          <div>
            <label className="block text-sm font-medium text-text mb-2">Priority</label>
            <div className="flex gap-2">
              {PRIORITIES.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setPriority(p.value)}
                  className={`flex-1 rounded-xl border py-2 text-sm font-semibold transition-colors ${
                    priority === p.value ? "border-primary bg-primary/10 text-primary" : "border-border text-textSecondary hover:bg-background"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <textarea
            placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded border border-border px-3 py-2 text-sm" rows={2}
          />

          <div className="mt-2 flex justify-end gap-2.5">
            <OutlineButton onClick={onClose}>Cancel</OutlineButton>
            <button
              type="submit"
              disabled={isSubmitting}
              className="hover-lift rounded-lg bg-gradient-to-r from-primary to-primary-dark text-white text-sm font-semibold py-2 px-4 shadow-card disabled:opacity-50"
            >
              {isSubmitting ? "Adding…" : "Add Task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
