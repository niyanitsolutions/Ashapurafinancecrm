import { useEffect, useState } from "react";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/features/customer/errors";
import { completeTask, createTask, listTasks, type Task } from "@/features/reminders/api";

const PAGE_SIZE = 20;

export function TaskListPage() {
  const { role } = useAuth();
  const [items, setItems] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    setIsLoading(true);
    listTasks({ page, page_size: PAGE_SIZE, status: status || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleComplete = async (taskId: string) => {
    setError(null);
    setMessage(null);
    try {
      await completeTask(taskId);
      setMessage("Task marked complete.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title="Tasks" subtitle="Follow-up work assigned to your team, with reminders and escalation if something's overdue.">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      {role === "owner" && (
        <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
          <h3 className="text-sm font-semibold text-text/70 mb-3">Assign Task</h3>
          <CreateTaskForm
            onSubmit={async (payload) => {
              setError(null);
              setMessage(null);
              try {
                await createTask(payload);
                setMessage("Task assigned.");
                load();
              } catch (err) {
                setError(getErrorMessage(err));
              }
            }}
          />
        </div>
      )}

      <div className="mb-4 flex items-center gap-4">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
        </select>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Assigned To</th>
              <th className="px-4 py-3">Due</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState icon="tasks" title="No tasks yet" description={role === "owner" ? "Assign your first task to a team member using the form above." : "You'll see tasks here once your manager assigns you one."} />
                </td>
              </tr>
            )}
            {items.map((task) => (
              <tr key={task.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">
                  {task.title}
                  {task.owner_escalated && <span className="ml-2 text-xs text-danger">(escalated)</span>}
                </td>
                <td className="px-4 py-3">{task.assigned_to_name || "—"}</td>
                <td className="px-4 py-3">{new Date(task.due_at).toLocaleString()}</td>
                <td className="px-4 py-3 capitalize">{task.status}</td>
                <td className="px-4 py-3">
                  {task.status === "pending" && (
                    <button type="button" onClick={() => handleComplete(task.id)} className="text-primary hover:underline text-xs">
                      Mark Complete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} tasks)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}

function CreateTaskForm({ onSubmit }: { onSubmit: (payload: { title: string; description?: string; assigned_to: string; due_at: string }) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [dueAt, setDueAt] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ title, description: description || undefined, assigned_to: assignedTo, due_at: new Date(dueAt).toISOString() });
        setTitle("");
        setDescription("");
        setAssignedTo("");
        setDueAt("");
      }}
      className="grid grid-cols-2 gap-3"
    >
      <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Employee ID" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <div className="col-span-2">
        <SubmitButton>Assign Task</SubmitButton>
      </div>
    </form>
  );
}
