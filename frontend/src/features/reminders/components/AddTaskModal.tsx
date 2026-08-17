import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { listEmployees, type EmployeeListItem } from "@/features/employee/api";
import { createTask } from "@/features/reminders/api";
import { getErrorMessage } from "@/features/leads/errors";
import { istWallClockToUtcISO } from "@/shared/dateFormat";

const ADD_TASK_FORM_ID = "add-task-form";

const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
] as const;

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
  relatedEntityType?: string;
  relatedEntityId?: string;
  entityLabel?: string;
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
      // `dueAt` is a `type="datetime-local"` value ("YYYY-MM-DDTHH:MM") meant as IST
      // wall-clock time regardless of the entering user's own browser timezone — must
      // not be converted via `new Date(dueAt).toISOString()`, which silently interprets
      // it as the *browser's* local time instead.
      const [datePart, timePart] = dueAt.split("T");
      await createTask({
        title, description: description || undefined, assigned_to: assignedTo,
        due_at: istWallClockToUtcISO(datePart, timePart),
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

  const footer = (
    <>
      <Button variant="secondary" size="sm" onClick={onClose}>
        Cancel
      </Button>
      <Button type="submit" form={ADD_TASK_FORM_ID} size="sm" loading={isSubmitting}>
        Add Task
      </Button>
    </>
  );

  return (
    <Modal open onClose={onClose} title="Add Task" description={entityLabel} footer={footer}>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {loadError && <p className="mb-3 text-sm text-danger">{loadError}</p>}

      <form id={ADD_TASK_FORM_ID} onSubmit={onSubmit} className="space-y-1">
        <FormField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
        <SelectField
          label="Assign To"
          value={assignedTo}
          onChange={(e) => setAssignedTo(e.target.value)}
          required
          placeholder={employees === null ? "Loading employees…" : "Select an employee…"}
          options={(employees ?? []).map((emp) => ({ value: emp.id, label: emp.display_name }))}
        />
        <FormField
          label="Due Date & Time"
          type="datetime-local"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          required
        />
        <div className="mb-4">
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
        <TextareaField
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
      </form>
    </Modal>
  );
}
