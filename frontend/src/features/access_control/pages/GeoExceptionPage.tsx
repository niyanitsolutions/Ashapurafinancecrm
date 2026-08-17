import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { useEmployeeNameMap } from "@/components/forms/useEmployeeNameMap";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { createGeoException, listGeoExceptions, revokeGeoException, type GeoException } from "@/features/access_control/api";
import { getErrorMessage } from "@/features/access_control/errors";
import { GEO_ACTIVITIES } from "@/features/geo_fencing/api";
import { istWallClockToUtcISO } from "@/shared/dateFormat";

function activityLabel(activity: string | null): string {
  if (!activity) return "All Activities";
  return GEO_ACTIVITIES.find((a) => a.value === activity)?.label ?? activity;
}

// The DB only ever stores "active"/"revoked" (see GeoException's own docstring — same
// lazy-evaluation convention as the sibling TemporaryAccess model: "expired" is never
// stored, only ever computed at read/enforcement time). `end_date`/`end_time` mean IST
// wall-clock (the same business timezone the backend's own `within_daily_window`
// evaluates the exception against — see docs/TIMEZONE.md), regardless of the viewing
// browser's own timezone — so the comparison instant must be built via
// `istWallClockToUtcISO`, not a bare `new Date(end_date)` + `.setHours(...)` (which
// mixes a UTC-parsed date with the *browser's* local hour/minute).
type DisplayStatus = "active" | "expired" | "revoked";

function displayStatus(item: GeoException, now: Date): DisplayStatus {
  if (item.status === "revoked") return "revoked";
  const end = new Date(istWallClockToUtcISO(item.end_date, item.end_time));
  return now > end ? "expired" : "active";
}

const STATUS_BADGE: Record<DisplayStatus, string> = {
  active: "bg-success/10 text-success",
  expired: "bg-text/10 text-text/50",
  revoked: "bg-danger/10 text-danger",
};

function GrantExceptionModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [employeeId, setEmployeeId] = useState("");
  const [activity, setActivity] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("18:00");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await createGeoException({
        employee_id: employeeId,
        activity: activity || undefined,
        start_date: startDate,
        end_date: endDate,
        start_time: startTime,
        end_time: endTime,
        reason,
      });
      onSaved();
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
      title="Grant Geo Exception"
      description="Temporarily bypasses the Geo Fence restriction for this employee — it does not set a new location."
      size="lg"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="geo-exception-form" size="sm" loading={isSubmitting}>
            Grant Exception
          </Button>
        </>
      }
    >
      <form id="geo-exception-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <EmployeeSelect label="Employee" value={employeeId} onChange={setEmployeeId} required activeOnly />
          <SelectField
            label="Activity"
            placeholder="All Activities"
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
            options={GEO_ACTIVITIES.map((a) => ({ value: a.value, label: a.label }))}
          />
          <FormField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
          <FormField label="Start date" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
          <FormField label="End date" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
          <FormField label="Start time (daily)" type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
          <FormField label="End time (daily)" type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
        </div>
      </form>
    </Modal>
  );
}

// Owner-only end to end: the route is wrapped in RequireOwner (frontend) and every
// /geo-exceptions endpoint is gated require_owner (backend) — see
// access_control/dependencies.py. This page never needs its own extra role check.
// Enforced server-side by app/features/geo_fencing/enforcement.py for lead_creation,
// document_collection, and login — see docs/GEO_FENCING.md. A Geo Exception carries no
// location of its own: it's a temporary bypass of whichever Geo Fence(s) would
// otherwise apply to the employee/activity, not a second location to configure.
export function GeoExceptionPage() {
  const employeeNames = useEmployeeNameMap();
  const [items, setItems] = useState<GeoException[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<GeoException | null>(null);

  const load = () => {
    listGeoExceptions({ page, page_size: pageSize })
      .then(({ items: fetched, pagination }) => {
        setItems(fetched);
        setTotal(pagination?.total ?? fetched.length);
        setTotalPages(pagination?.total_pages ?? 1);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [page, pageSize]);

  const onRevoke = async () => {
    if (!revokeTarget) return;
    setError(null);
    await revokeGeoException(revokeTarget.id);
    setRevokeTarget(null);
    load();
  };

  const now = new Date();

  return (
    <SimplePageLayout
      title="Geo Exceptions"
      subtitle="Grant temporary Geo Fence bypasses to individual employees."
      actions={<Button size="sm" onClick={() => setIsModalOpen(true)}>+ Grant Exception</Button>}
    >
      <ErrorBanner message={error} />

      {items.length === 0 ? (
        <EmptyState
          icon="map-pin"
          title="No geo exceptions yet"
          description="Grant a Geo Exception to let an employee bypass a configured Geo Fence for a limited window."
          primaryAction={{ label: "+ Grant Exception", onClick: () => setIsModalOpen(true) }}
        />
      ) : (
        <>
          <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text/60">
                  <th className="px-4 py-3">Employee</th>
                  <th className="px-4 py-3">Activity</th>
                  <th className="px-4 py-3">Reason</th>
                  <th className="px-4 py-3">Start Date</th>
                  <th className="px-4 py-3">End Date</th>
                  <th className="px-4 py-3">Time Window</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const status = displayStatus(item, now);
                  return (
                    <tr key={item.id} className="border-b border-border last:border-0">
                      <td className="px-4 py-3">{employeeNames[item.employee_id] ?? item.employee_id}</td>
                      <td className="px-4 py-3">{activityLabel(item.activity)}</td>
                      <td className="px-4 py-3">{item.reason}</td>
                      <td className="px-4 py-3">{item.start_date}</td>
                      <td className="px-4 py-3">{item.end_date}</td>
                      <td className="px-4 py-3">{item.start_time}–{item.end_time}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-2xs font-medium capitalize ${STATUS_BADGE[status]}`}>
                          {status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {status === "active" && (
                          <button type="button" onClick={() => setRevokeTarget(item)} className="text-danger hover:underline text-xs">
                            Revoke
                          </button>
                        )}
                        {status !== "active" && <span className="text-text/30">—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={total}
            pageSize={pageSize}
            itemLabel="geo exceptions"
            onPageChange={setPage}
            onPageSizeChange={(size) => { setPage(1); setPageSize(size); }}
          />
        </>
      )}

      {isModalOpen && (
        <GrantExceptionModal
          onClose={() => setIsModalOpen(false)}
          onSaved={() => {
            setIsModalOpen(false);
            setPage(1);
            load();
          }}
        />
      )}

      <ConfirmDialog
        open={revokeTarget !== null}
        title="Revoke this Geo Exception?"
        message={
          revokeTarget
            ? `${employeeNames[revokeTarget.employee_id] ?? "This employee"} will no longer be allowed to bypass the ${activityLabel(revokeTarget.activity)} Geo Fence for this exception.`
            : undefined
        }
        confirmLabel="Revoke"
        confirmVariant="danger"
        onConfirm={onRevoke}
        onClose={() => setRevokeTarget(null)}
      />
    </SimplePageLayout>
  );
}
