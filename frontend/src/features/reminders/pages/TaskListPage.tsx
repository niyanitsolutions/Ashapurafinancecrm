import { useEffect, useState } from "react";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { useAuth } from "@/features/auth/useAuth";
import { getErrorMessage } from "@/features/customer/errors";
import { completeTask, createTask, listTasks, type Task } from "@/features/reminders/api";

const PAGE_SIZE = 20;

const PRIORITY_BADGE: Record<string, string> = {
  high: "bg-danger/10 text-danger",
  medium: "bg-warning/10 text-warning",
  low: "bg-text/10 text-text/60",
};

function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${PRIORITY_BADGE[priority] ?? PRIORITY_BADGE.medium}`}>
      {priority}
    </span>
  );
}

export function TaskListPage() {
  const { role } = useAuth();
  const [items, setItems] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    setIsLoading(true);
    listTasks({ page, page_size: PAGE_SIZE, status: status || undefined, priority: priority || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, status, priority]);

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
        <select value={priority} onChange={(e) => { setPage(1); setPriority(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Assigned To</th>
              <th className="px-4 py-3">Due</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={6}>
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
                <td className="px-4 py-3"><PriorityBadge priority={task.priority} /></td>
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

function CreateTaskForm({
  onSubmit,
}: {
  onSubmit: (payload: { title: string; description?: string; assigned_to: string; due_at: string; priority: string }) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [priority, setPriority] = useState("medium");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ title, description: description || undefined, assigned_to: assignedTo, due_at: new Date(dueAt).toISOString(), priority });
        setTitle("");
        setDescription("");
        setAssignedTo("");
        setDueAt("");
        setPriority("medium");
      }}
      className="grid grid-cols-2 gap-3"
    >
      <input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Employee ID" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
        <option value="low">Low Priority</option>
        <option value="medium">Medium Priority</option>
        <option value="high">High Priority</option>
      </select>
      <input placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} className="rounded border border-border px-3 py-2 text-sm col-span-2" />
      <div className="col-span-2">
        <SubmitButton>Assign Task</SubmitButton>
      </div>
    </form>
  );
}
