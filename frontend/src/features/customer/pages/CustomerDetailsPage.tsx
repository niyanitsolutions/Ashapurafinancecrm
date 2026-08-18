import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge } from "@/components/badges/Badge";
import { Button } from "@/components/buttons/Button";
import { EmployeeSelect } from "@/components/forms/EmployeeSelect";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { useAuth } from "@/features/auth/useAuth";
import { usePermissions } from "@/features/access_control/usePermissions";
import { MessagesPanel } from "@/features/communication/components/MessagesPanel";
import { SendMessageModal } from "@/features/communication/components/SendMessageModal";
import { assignApplication, getCustomerStaff, listApplicationsStaff, type ApplicationListItem, type Customer } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import { AddTaskModal } from "@/features/reminders/components/AddTaskModal";
import { Icon, type IconName } from "@/theme/icons";

function HeaderButton({ icon, label, onClick }: { icon: IconName; label: string; onClick: () => void }) {
  return (
    <Button variant="secondary" size="sm" onClick={onClick} icon={<Icon name={icon} className="h-4 w-4" />}>
      {label}
    </Button>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}

// Document Management redesign / Assignment consistency work — a customer can have
// several independent applications (different products, different assigned employees,
// different case statuses); each row here shows its OWN assignment/status, never one
// shared value for the whole customer. `assigned_to_name`/`case_status_label` are
// already kept correct server-side (see CustomerService.assign_application /
// LoanCaseService.assign_case) — this just renders what the API returns.
function ApplicationRow({ app, canReassign, onReassigned }: { app: ApplicationListItem; canReassign: boolean; onReassigned: () => void }) {
  const [isReassigning, setIsReassigning] = useState(false);
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const onSave = async () => {
    if (!employeeId) return;
    setIsSaving(true);
    setError(null);
    try {
      await assignApplication(app.id, employeeId);
      setIsReassigning(false);
      setEmployeeId("");
      onReassigned();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const caseHref = app.case_id ? (app.case_type === "insurance" ? `/insurance-cases/${app.case_id}` : `/loan-cases/${app.case_id}`) : null;

  return (
    <div className="border border-border rounded-lg p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text">{app.product_name}</p>
          <p className="text-xs text-text/50">{app.application_code}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={app.status === "submitted" ? "success" : "warning"}>{app.status === "submitted" ? "Submitted" : "Draft"}</Badge>
          {app.case_status_label && <Badge tone="info">{app.case_status_label}</Badge>}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text/40">Assigned Employee</p>
          {isReassigning ? (
            <div className="mt-1 space-y-2">
              <EmployeeSelect label="" value={employeeId} onChange={setEmployeeId} />
              <div className="flex items-center gap-2">
                <Button size="sm" disabled={!employeeId} loading={isSaving} onClick={onSave}>
                  Save
                </Button>
                <Button variant="secondary" size="sm" onClick={() => { setIsReassigning(false); setError(null); }}>
                  Cancel
                </Button>
              </div>
              {error && <p className="text-xs text-danger">{error}</p>}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-text/80">{app.assigned_to_name ?? "Unassigned"}</p>
              {canReassign && (
                <button type="button" onClick={() => setIsReassigning(true)} className="text-xs font-medium text-primary hover:underline">
                  Reassign
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex items-end justify-end gap-3">
          {caseHref && (
            <Link to={caseHref} className="text-sm font-medium text-primary hover:underline">
              Manage Status →
            </Link>
          )}
          <Link to={`/applications/${app.id}`} className="text-sm font-medium text-primary hover:underline">
            View Application →
          </Link>
        </div>
      </div>
    </div>
  );
}

export function CustomerDetailsPage() {
  const { can } = usePermissions();
  const { role } = useAuth();
  const canAddTask = can("reminders:tasks", "create");
  const canSendMessage = can("communication:send", "create");
  // Reassignment (`POST /applications/{id}/assign`) is Owner-only server-side — this
  // just keeps the Reassign control from being offered to a role that would 403 on it.
  const canReassign = role === "owner";
  const { customerId } = useParams<{ customerId: string }>();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [applications, setApplications] = useState<ApplicationListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [isSendMessageOpen, setIsSendMessageOpen] = useState(false);
  const [messagesRefreshKey, setMessagesRefreshKey] = useState(0);

  const loadApplications = (id: string) => {
    listApplicationsStaff({ customer_id: id, page_size: 100 })
      .then((res) => setApplications(res.data))
      .catch(() => setApplications([]));
  };

  useEffect(() => {
    if (!customerId) return;
    getCustomerStaff(customerId)
      .then(setCustomer)
      .catch((err) => setError(getErrorMessage(err)));
    loadApplications(customerId);
  }, [customerId]);

  if (!customerId) return null;
  if (error && !customer) {
    return (
      <SimplePageLayout title="Customer" backTo="/customers">
        <p className="text-sm text-danger">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!customer) {
    return (
      <SimplePageLayout title="Customer" backTo="/customers">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  return (
    <SimplePageLayout
      title={`${customer.full_name} (${customer.customer_code})`}
      backTo="/customers"
      actions={
        <div className="flex items-center gap-2.5">
          {canSendMessage && <HeaderButton icon="chat" label="Send Message" onClick={() => setIsSendMessageOpen(true)} />}
          {canAddTask && <HeaderButton icon="tasks" label="Add Task" onClick={() => setIsTaskModalOpen(true)} />}
        </div>
      }
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <div className="max-w-2xl bg-card border border-border rounded-card shadow-card p-6 grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        <Field label="Mobile" value={customer.mobile} />
        <Field label="Email" value={customer.email} />
        <Field label="Date of Birth" value={customer.date_of_birth} />
        <Field label="Gender" value={customer.gender} />
        <Field label="PAN" value={customer.pan_number_masked} />
        <Field label="Aadhaar" value={customer.aadhaar_number_masked} />
        <Field label="Status" value={customer.status} />
        <Field label="Source" value={customer.registration_source === "lead" ? "Lead" : "Direct"} />
        {customer.registration_source === "lead" && (
          <>
            <Field label="Lead Source" value={customer.lead_source_name} />
            <Field label="Lead Code" value={customer.lead_code} />
          </>
        )}
        {customer.address && (
          <div className="col-span-2">
            <Field
              label="Address"
              value={[customer.address.line1, customer.address.line2, customer.address.city, customer.address.state, customer.address.pincode]
                .filter(Boolean)
                .join(", ")}
            />
          </div>
        )}
      </div>

      <div className="max-w-2xl mt-6">
        <h2 className="text-sm font-semibold text-text/70 mb-3">Applications</h2>
        {applications === null && <p className="text-sm text-text/50">Loading…</p>}
        {applications !== null && applications.length === 0 && (
          <div className="bg-card border border-border rounded-card shadow-card p-6 text-center text-sm text-text/50">
            No applications yet.
          </div>
        )}
        {applications !== null && applications.length > 0 && (
          <div className="space-y-3">
            {applications.map((app) => (
              <ApplicationRow key={app.id} app={app} canReassign={canReassign} onReassigned={() => loadApplications(customerId)} />
            ))}
          </div>
        )}
      </div>

      <MessagesPanel entityType="customer" entityId={customerId} refreshKey={messagesRefreshKey} />

      {isTaskModalOpen && (
        <AddTaskModal
          relatedEntityType="customer"
          relatedEntityId={customerId}
          entityLabel={`Customer ${customer.customer_code}`}
          onClose={() => setIsTaskModalOpen(false)}
          onCreated={() => setMessage("Task added.")}
        />
      )}
      {isSendMessageOpen && (
        <SendMessageModal
          entityType="customer"
          entityId={customerId}
          entityLabel={`${customer.full_name} (${customer.customer_code})`}
          onClose={() => setIsSendMessageOpen(false)}
          onSent={() => setMessagesRefreshKey((k) => k + 1)}
        />
      )}
    </SimplePageLayout>
  );
}
