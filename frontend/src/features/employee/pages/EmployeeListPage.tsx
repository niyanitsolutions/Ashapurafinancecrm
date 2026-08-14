import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BUTTON_BASE_CLASSES, BUTTON_SIZE_CLASSES, BUTTON_VARIANT_CLASSES } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Pagination } from "@/components/tables/Pagination";
import {
  activateEmployee,
  deactivateEmployee,
  exportEmployeesCsvUrl,
  listDepartments,
  listDesignations,
  listEmployees,
  resetEmployeePassword,
  type EmployeeListItem,
  type MasterDataItem,
} from "@/features/employee/api";
import { getErrorMessage } from "@/features/employee/errors";
import { StatusBadge } from "@/features/employee/components/StatusBadge";

const PAGE_SIZE = 20;
const STATUS_OPTIONS = ["active", "inactive", "suspended", "on_leave", "resigned"];

export function EmployeeListPage() {
  const [items, setItems] = useState<EmployeeListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [designationId, setDesignationId] = useState("");
  const [status, setStatus] = useState("");
  const [departments, setDepartments] = useState<MasterDataItem[]>([]);
  const [designations, setDesignations] = useState<MasterDataItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<EmployeeListItem | null>(null);

  const load = () => {
    setIsLoading(true);
    setError(null);
    listEmployees({ page, page_size: PAGE_SIZE, search: search || undefined, department_id: departmentId || undefined, designation_id: designationId || undefined, status: status || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, search, departmentId, designationId, status]);
  useEffect(() => {
    listDepartments().then(setDepartments).catch(() => setDepartments([]));
    listDesignations().then(setDesignations).catch(() => setDesignations([]));
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasFilters = Boolean(search || departmentId || designationId || status);

  const clearFilters = () => {
    setSearch("");
    setDepartmentId("");
    setDesignationId("");
    setStatus("");
    setPage(1);
  };

  const toggleActive = async (employee: EmployeeListItem) => {
    setBusyId(employee.id);
    setMessage(null);
    try {
      if (employee.status === "active") {
        await deactivateEmployee(employee.id);
        setMessage(`${employee.display_name} disabled.`);
      } else {
        await activateEmployee(employee.id);
        setMessage(`${employee.display_name} enabled.`);
      }
      load();
    } finally {
      setBusyId(null);
    }
  };

  const handleResetPassword = async () => {
    if (!resetTarget) return;
    setBusyId(resetTarget.id);
    setMessage(null);
    try {
      await resetEmployeePassword(resetTarget.id);
      setMessage(`Password reset for ${resetTarget.display_name}. They'll receive an OTP to set a new one.`);
      setResetTarget(null);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <SimplePageLayout
      title="Employees"
      subtitle="Your team — who they are, what they do, and what they can access."
      actions={
        <>
          <a href={exportEmployeesCsvUrl()} className={`${BUTTON_BASE_CLASSES} ${BUTTON_VARIANT_CLASSES.secondary} ${BUTTON_SIZE_CLASSES.sm}`}>
            Export
          </a>
          <Link to="/employees/new" className={`${BUTTON_BASE_CLASSES} ${BUTTON_VARIANT_CLASSES.primary} ${BUTTON_SIZE_CLASSES.sm}`}>
            + Add Employee
          </Link>
        </>
      }
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search by name, code, email, mobile…"
          value={search}
          onChange={(e) => { setPage(1); setSearch(e.target.value); }}
          className="w-full max-w-xs rounded border border-border px-3 py-2 text-sm"
        />
        <select value={departmentId} onChange={(e) => { setPage(1); setDepartmentId(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={designationId} onChange={(e) => { setPage(1); setDesignationId(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Designations</option>
          {designations.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s} className="capitalize">{s.replace(/_/g, " ")}</option>
          ))}
        </select>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Department</th>
              <th className="px-4 py-3">Designation</th>
              <th className="px-4 py-3">Mobile</th>
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
                  {hasFilters ? (
                    <EmptyState icon="search" title="No employees match your filters" description="Try a different search term, or clear the filters." secondaryAction={{ label: "Clear filters", onClick: clearFilters }} />
                  ) : (
                    <EmptyState icon="employees" title="No employees yet" description="Add your first team member to get started." primaryAction={{ label: "Add Employee", to: "/employees/new" }} />
                  )}
                </td>
              </tr>
            )}
            {items.map((e) => (
              <tr key={e.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">
                  <Link to={`/employees/${e.id}`} className="text-text hover:text-primary font-medium block">{e.display_name}</Link>
                  <span className="text-xs text-text/40">{e.employee_code}</span>
                </td>
                <td className="px-4 py-3">{e.department_name}</td>
                <td className="px-4 py-3">{e.designation_name}</td>
                <td className="px-4 py-3">{e.mobile}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={e.status} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-3 text-xs">
                    <Link to={`/employees/${e.id}`} className="text-primary hover:underline">View</Link>
                    <Link to={`/employees/${e.id}/edit`} className="text-primary hover:underline">Edit</Link>
                    <button type="button" disabled={busyId === e.id} onClick={() => toggleActive(e)} className="text-primary hover:underline disabled:opacity-40">
                      {e.status === "active" ? "Disable" : "Enable"}
                    </button>
                    <button type="button" disabled={busyId === e.id} onClick={() => setResetTarget(e)} className="text-primary hover:underline disabled:opacity-40">
                      Reset Password
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="employees" onPageChange={setPage} />

      <ConfirmDialog
        open={resetTarget !== null}
        title="Reset Password"
        message={resetTarget ? `Reset ${resetTarget.display_name}'s password? They'll receive an OTP to set a new one.` : ""}
        confirmLabel="Reset Password"
        onConfirm={handleResetPassword}
        onClose={() => setResetTarget(null)}
      />
    </SimplePageLayout>
  );
}
