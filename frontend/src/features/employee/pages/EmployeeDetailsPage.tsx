import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import {
  activateEmployee,
  confirmEmployeeDocument,
  deactivateEmployee,
  forceLogoutEmployee,
  getEmployee,
  getEmployeeActivitySummary,
  getEmployeeDocumentUploadUrl,
  getEmployeeDocuments,
  getEmployeeLoginHistory,
  getEmployeeSessions,
  resetEmployeePassword,
  type ActivitySummary,
  type EmployeeDetail,
  type EmployeeDocument,
  type LoginHistoryEntry,
  type SessionSummary,
} from "@/features/employee/api";
import { StatusBadge } from "@/features/employee/components/StatusBadge";
import { getErrorMessage } from "@/features/employee/errors";
import { insuranceProductsApi, loanProductsApi } from "@/features/system_settings/api";
import { formatISTDateTime } from "@/shared/dateFormat";

const DOCUMENT_TYPES = [
  { value: "pan", label: "PAN" },
  { value: "aadhaar", label: "Aadhaar" },
  { value: "offer_letter", label: "Offer Letter" },
  { value: "joining_letter", label: "Joining Letter" },
  { value: "experience_certificate", label: "Experience Certificate" },
  { value: "other", label: "Other" },
];

type Tab = "basic" | "employment" | "documents" | "sessions" | "login-history" | "activity";
const TABS: { key: Tab; label: string }[] = [
  { key: "basic", label: "Basic Information" },
  { key: "employment", label: "Employment" },
  { key: "documents", label: "Documents" },
  { key: "sessions", label: "Sessions" },
  { key: "login-history", label: "Login History" },
  { key: "activity", label: "Activity" },
];

export function EmployeeDetailsPage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [tab, setTab] = useState<Tab>("basic");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"reset-password" | "force-logout" | null>(null);

  const load = () => {
    if (!employeeId) return;
    getEmployee(employeeId).then(setEmployee).catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(load, [employeeId]);

  if (!employeeId) return null;

  const runAction = async (action: () => Promise<unknown>, successMessage: string) => {
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

  if (error && !employee) {
    return (
      <SimplePageLayout title="Employee" backTo="/employees">
        <p className="text-danger text-sm">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!employee) {
    return (
      <SimplePageLayout title="Employee" backTo="/employees">
        <p className="text-text/50 text-sm">Loading…</p>
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout
      title={employee.display_name}
      subtitle={`${employee.employee_code} · ${employee.designation_name}, ${employee.department_name}`}
      backTo="/employees"
      actions={
        <Button size="sm" onClick={() => navigate(`/employees/${employeeId}/edit`)}>
          Edit
        </Button>
      }
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="flex gap-1 border-b border-border mb-4 overflow-x-auto">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${tab === t.key ? "border-primary text-primary" : "border-transparent text-text/60 hover:text-text"}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "basic" && <BasicInfoTab employee={employee} />}
          {tab === "employment" && <EmploymentTab employee={employee} onEdit={() => navigate(`/employees/${employeeId}/edit`)} />}
          {tab === "documents" && <DocumentsTab employeeId={employeeId} />}
          {tab === "sessions" && <SessionsTab employeeId={employeeId} />}
          {tab === "login-history" && <LoginHistoryTab employeeId={employeeId} />}
          {tab === "activity" && <ActivityTab employeeId={employeeId} />}
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3 h-fit">
          <div className="flex items-center gap-2 mb-1">
            <StatusBadge status={employee.status} />
          </div>
          <h3 className="text-sm font-semibold text-text/70">Actions</h3>

          {employee.status === "active" ? (
            <ActionButton onClick={() => runAction(() => deactivateEmployee(employeeId), "Employee deactivated.")}>Deactivate</ActionButton>
          ) : (
            <ActionButton onClick={() => runAction(() => activateEmployee(employeeId), "Employee activated.")}>Activate</ActionButton>
          )}
          <ActionButton onClick={() => setConfirmAction("reset-password")}>Reset Password</ActionButton>
          <ActionButton onClick={() => setConfirmAction("force-logout")}>Force Logout</ActionButton>
        </div>
      </div>

      <ConfirmDialog
        open={confirmAction === "reset-password"}
        title="Reset Password"
        message={`Reset ${employee.display_name}'s password? They'll receive an OTP to set a new one.`}
        confirmLabel="Reset Password"
        onConfirm={async () => {
          await runAction(() => resetEmployeePassword(employeeId), "Password reset OTP sent.");
          setConfirmAction(null);
        }}
        onClose={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === "force-logout"}
        title="Force Logout"
        message={`Revoke every active session for ${employee.display_name}? They'll be signed out everywhere immediately.`}
        confirmLabel="Force Logout"
        confirmVariant="danger"
        onConfirm={async () => {
          await runAction(() => forceLogoutEmployee(employeeId), "All sessions revoked.");
          setConfirmAction(null);
        }}
        onClose={() => setConfirmAction(null)}
      />
    </SimplePageLayout>
  );
}

function BasicInfoTab({ employee }: { employee: EmployeeDetail }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-4">
      <Section title="Contact">
        <Field label="Mobile" value={employee.mobile} />
        <Field label="Alternative mobile" value={employee.alternative_mobile} />
        <Field label="Email" value={employee.email} />
      </Section>
      <Section title="Personal">
        <Field label="Gender" value={employee.gender} />
        <Field label="Date of birth" value={employee.date_of_birth?.slice(0, 10)} />
        <Field label="Blood group" value={employee.blood_group} />
      </Section>
      {employee.emergency_contact && (
        <Section title="Emergency Contact">
          <Field label="Name" value={employee.emergency_contact.name} />
          <Field label="Relationship" value={employee.emergency_contact.relationship} />
          <Field label="Mobile" value={employee.emergency_contact.mobile} />
        </Section>
      )}
      {employee.current_address && (
        <Section title="Current Address">
          <Field label="Address" value={`${employee.current_address.line1}${employee.current_address.line2 ? ", " + employee.current_address.line2 : ""}`} />
          <Field label="City" value={employee.current_address.city} />
          <Field label="State" value={employee.current_address.state} />
          <Field label="Pincode" value={employee.current_address.pincode} />
        </Section>
      )}
      {!employee.emergency_contact && !employee.current_address && (
        <p className="text-xs text-text/40">Emergency contact and address haven't been added yet — edit this employee to fill them in.</p>
      )}
    </div>
  );
}

function EmploymentTab({ employee, onEdit }: { employee: EmployeeDetail; onEdit: () => void }) {
  const [productNames, setProductNames] = useState<string[]>([]);

  useEffect(() => {
    if (employee.product_ids.length === 0) {
      setProductNames([]);
      return;
    }
    Promise.all([loanProductsApi.list(), insuranceProductsApi.list()]).then(([loan, insurance]) => {
      const byId = new Map([...loan, ...insurance].map((p) => [p.id, p.name]));
      setProductNames(employee.product_ids.map((id) => byId.get(id)).filter((name): name is string => Boolean(name)));
    });
  }, [employee.product_ids]);

  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-4">
      <Section title="Organization">
        <Field label="Department" value={employee.department_name} />
        <Field label="Designation" value={employee.designation_name} />
        <Field label="Branch" value={employee.branch_name} />
        <Field label="Employment type" value={employee.employment_type?.replace(/_/g, " ")} />
        <Field label="Joining date" value={employee.joining_date?.slice(0, 10)} />
      </Section>
      {productNames.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text/70 mb-2">Products Handled</h3>
          <div className="flex flex-wrap gap-1.5">
            {productNames.map((name) => (
              <span key={name} className="rounded-full bg-primary/10 text-primary text-xs font-medium px-2.5 py-1">
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
      {employee.bank_details && (
        <Section title="Bank Details">
          <Field label="Account holder" value={employee.bank_details.account_holder_name} />
          <Field label="Bank" value={employee.bank_details.bank_name} />
          <Field label="IFSC" value={employee.bank_details.ifsc_code} />
          <Field label="Account number" value={employee.bank_details.account_number_masked} />
        </Section>
      )}
      <button type="button" onClick={onEdit} className="text-sm text-primary hover:underline">
        Edit employment details
      </button>
    </div>
  );
}

function DocumentsTab({ employeeId }: { employeeId: string }) {
  const [documents, setDocuments] = useState<EmployeeDocument[] | null>(null);
  const [documentType, setDocumentType] = useState("pan");
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const load = () => {
    getEmployeeDocuments(employeeId).then(setDocuments).catch((err) => setError(getErrorMessage(err)));
  };
  useEffect(load, [employeeId]);

  const handleUpload = async (file: File) => {
    setError(null);
    setIsUploading(true);
    try {
      const { upload_url, s3_key } = await getEmployeeDocumentUploadUrl(employeeId, documentType, file.name, file.type);
      await fetch(upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type || "application/octet-stream" } });
      await confirmEmployeeDocument(employeeId, { document_type: documentType, file_name: file.name, s3_key, content_type: file.type });
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-card shadow-card p-6">
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      <div className="flex items-center gap-3 mb-4">
        <select value={documentType} onChange={(e) => setDocumentType(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
          {DOCUMENT_TYPES.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>
        <label className="rounded-lg border border-border text-sm font-medium py-2 px-4 text-text/70 hover:bg-background cursor-pointer">
          {isUploading ? "Uploading…" : "Upload File"}
          <input
            type="file"
            className="hidden"
            disabled={isUploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUpload(file);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {documents === null && <p className="text-sm text-text/40">Loading…</p>}
      {documents !== null && documents.length === 0 && <p className="text-sm text-text/40">No documents uploaded yet.</p>}
      {documents !== null && documents.length > 0 && (
        <ul className="divide-y divide-border">
          {documents.map((d) => (
            <li key={d.id} className="py-2 flex items-center justify-between text-sm">
              <span className="text-text">{d.file_name}</span>
              <span className="text-text/40 capitalize">{d.document_type.replace(/_/g, " ")}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SessionsTab({ employeeId }: { employeeId: string }) {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  useEffect(() => {
    getEmployeeSessions(employeeId).then(setSessions).catch(() => setSessions([]));
  }, [employeeId]);

  return (
    <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text/60">
            <th className="px-4 py-3">Device</th>
            <th className="px-4 py-3">Location</th>
            <th className="px-4 py-3">Login</th>
            <th className="px-4 py-3">Last Activity</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {sessions === null && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
          {sessions !== null && sessions.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">No sessions recorded.</td></tr>}
          {sessions?.map((s) => (
            <tr key={s.id} className="border-b border-border last:border-0">
              <td className="px-4 py-3">{[s.browser, s.operating_system].filter(Boolean).join(" · ") || "—"}</td>
              <td className="px-4 py-3">{[s.city, s.country].filter(Boolean).join(", ") || s.ip_address || "—"}</td>
              <td className="px-4 py-3">{formatISTDateTime(s.login_at)}</td>
              <td className="px-4 py-3">{formatISTDateTime(s.last_activity_at)}</td>
              <td className="px-4 py-3 capitalize">{s.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LoginHistoryTab({ employeeId }: { employeeId: string }) {
  const [history, setHistory] = useState<LoginHistoryEntry[] | null>(null);
  useEffect(() => {
    getEmployeeLoginHistory(employeeId).then(setHistory).catch(() => setHistory([]));
  }, [employeeId]);

  return (
    <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-text/60">
            <th className="px-4 py-3">Event</th>
            <th className="px-4 py-3">IP Address</th>
            <th className="px-4 py-3">When</th>
          </tr>
        </thead>
        <tbody>
          {history === null && <tr><td colSpan={3} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
          {history !== null && history.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-text/50">No login history yet.</td></tr>}
          {history?.map((h, i) => (
            <tr key={i} className="border-b border-border last:border-0">
              <td className="px-4 py-3 capitalize">{h.event_type.replace(/_/g, " ")}</td>
              <td className="px-4 py-3">{h.ip_address || "—"}</td>
              <td className="px-4 py-3">{formatISTDateTime(h.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActivityTab({ employeeId }: { employeeId: string }) {
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  useEffect(() => {
    getEmployeeActivitySummary(employeeId).then(setSummary).catch(() => setSummary(null));
  }, [employeeId]);

  if (!summary) return <p className="text-sm text-text/40">Loading…</p>;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      <StatTile label="Total Logins" value={summary.total_logins} />
      <StatTile label="Failed Logins" value={summary.failed_login_count} />
      <StatTile label="Active Sessions" value={summary.active_session_count} />
      <StatTile label="Last Login" value={summary.last_login_at ? formatISTDateTime(summary.last_login_at) : "—"} />
      <StatTile label="Account Status" value={summary.account_status} />
      <StatTile label="Employment Status" value={summary.employment_status} />
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-4">
      <div className="text-xs text-text/50 mb-1">{label}</div>
      <div className="text-lg font-semibold text-text capitalize">{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-text/70 mb-2">{title}</h3>
      <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">{children}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm capitalize">{value || "—"}</div>
    </div>
  );
}

function ActionButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="w-full text-left text-sm rounded border border-border px-3 py-2 hover:bg-background">
      {children}
    </button>
  );
}
