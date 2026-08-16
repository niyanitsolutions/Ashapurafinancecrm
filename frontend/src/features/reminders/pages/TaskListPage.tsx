import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Pagination } from "@/components/tables/Pagination";
import { Table, TableBody, TableHead, TableHeadRow, TableRow, Td, Th } from "@/components/tables/DataTable";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/features/customer/errors";
import { AddTaskModal } from "@/features/reminders/components/AddTaskModal";
import { completeTask, listTasks, type Task } from "@/features/reminders/api";

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
  const { can } = usePermissions();
  const canCreate = can("reminders:tasks", "create");
  const [items, setItems] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

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
  const hasFilters = Boolean(status || priority);

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
    <SimplePageLayout
      title="Tasks"
      subtitle="Follow-up work assigned to your team, with reminders and escalation if something's overdue."
      actions={canCreate ? <Button size="sm" onClick={() => setIsCreateOpen(true)}>+ Assign Task</Button> : undefined}
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="completed">Completed</option>
        </select>
        <select value={priority} onChange={(e) => { setPage(1); setPriority(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {!isLoading && items.length === 0 ? (
        <EmptyState
          icon="tasks"
          title={hasFilters ? "No tasks match your filters" : "No tasks yet"}
          description={
            hasFilters
              ? "Try a different status or priority filter."
              : canCreate
                ? "Assign your first task to a team member."
                : "You'll see tasks here once your manager assigns you one."
          }
          primaryAction={canCreate && !hasFilters ? { label: "+ Assign Task", onClick: () => setIsCreateOpen(true) } : undefined}
        />
      ) : (
        <div className="overflow-x-auto rounded-card border border-border bg-card shadow-card">
          <Table>
            <TableHead>
              <TableHeadRow>
                <Th>Title</Th>
                <Th>Priority</Th>
                <Th>Assigned To</Th>
                <Th>Due</Th>
                <Th>Status</Th>
                <Th />
              </TableHeadRow>
            </TableHead>
            <TableBody>
              {isLoading && (
                <tr>
                  <Td colSpan={6} className="text-center text-text/50 py-6">
                    Loading…
                  </Td>
                </tr>
              )}
              {!isLoading &&
                items.map((task) => (
                  <TableRow key={task.id}>
                    <Td>
                      {task.title}
                      {task.owner_escalated && <span className="ml-2 text-xs text-danger">(escalated)</span>}
                    </Td>
                    <Td>
                      <PriorityBadge priority={task.priority} />
                    </Td>
                    <Td>{task.assigned_to_name || "—"}</Td>
                    <Td>{new Date(task.due_at).toLocaleString()}</Td>
                    <Td className="capitalize">{task.status}</Td>
                    <Td>
                      {task.status === "pending" && (
                        <button type="button" onClick={() => handleComplete(task.id)} className="text-primary hover:underline text-xs">
                          Mark Complete
                        </button>
                      )}
                    </Td>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Pagination
        page={page}
        totalPages={totalPages}
        totalItems={total}
        pageSize={PAGE_SIZE}
        itemLabel="tasks"
        onPageChange={setPage}
      />

      {isCreateOpen && (
        <AddTaskModal
          onClose={() => setIsCreateOpen(false)}
          onCreated={() => {
            setMessage("Task assigned.");
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
