import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Icon } from "@/theme/icons";
import { useAuth } from "@/features/auth/useAuth";
import {
  assignApplication,
  getApplication,
  listDocuments,
  rejectDocument,
  verifyDocument,
  type ApplicationDetail,
  type ApplicationDocument,
} from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";

const STATUS_BADGE: Record<ApplicationDocument["verification_status"], { label: string; className: string; icon: "check-circle" | "x-circle" | "clock" }> = {
  verified: { label: "Verified", className: "text-success", icon: "check-circle" },
  rejected: { label: "Rejected", className: "text-danger", icon: "x-circle" },
  pending: { label: "Pending Review", className: "text-text/50", icon: "clock" },
};

export function StaffApplicationDetailsPage() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const { role } = useAuth();
  const [application, setApplication] = useState<ApplicationDetail | null>(null);
  const [documents, setDocuments] = useState<ApplicationDocument[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const load = () => {
    if (!applicationId) return;
    getApplication(applicationId)
      .then(setApplication)
      .catch((err) => setError(getErrorMessage(err)));
    listDocuments(applicationId)
      .then(setDocuments)
      .catch(() => setDocuments([]));
  };

  useEffect(load, [applicationId]);  

  if (!applicationId) return null;
  if (error && !application) {
    return (
      <SimplePageLayout title="Application" backTo="/applications">
        <p className="text-sm text-danger">{error}</p>
      </SimplePageLayout>
    );
  }
  if (!application) {
    return (
      <SimplePageLayout title="Application" backTo="/applications">
        <p className="text-sm text-text/50">Loading…</p>
      </SimplePageLayout>
    );
  }

  const onAssign = async () => {
    setError(null);
    setMessage(null);
    try {
      await assignApplication(applicationId, employeeId);
      setMessage("Application assigned.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onVerify = async (documentId: string) => {
    setError(null);
    setMessage(null);
    try {
      await verifyDocument(applicationId, documentId);
      setMessage("Document verified.");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const onReject = async (documentId: string) => {
    if (!rejectReason.trim()) return;
    setError(null);
    setMessage(null);
    try {
      await rejectDocument(applicationId, documentId, rejectReason.trim());
      setMessage("Document rejected.");
      setRejectingId(null);
      setRejectReason("");
      load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title={application.application_code} backTo="/applications">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-6">
          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Details</h2>
            <p className="text-sm text-text/60 mb-2 capitalize">
              {application.product_name} · {application.status}
            </p>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              {Object.entries(application.form_data).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-xs text-text/50 capitalize">{key.replace(/_/g, " ")}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="bg-card border border-border rounded-card shadow-card p-6">
            <h2 className="text-sm font-semibold text-text/70 mb-3">Documents</h2>
            {documents.length === 0 && <p className="text-sm text-text/50">No documents uploaded yet.</p>}
            <ul className="space-y-3">
              {documents.map((d) => {
                const badge = STATUS_BADGE[d.verification_status];
                return (
                  <li key={d.id} className="border border-border rounded-lg p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <span className="text-text/70">{d.document_type_name}: </span>
                        {d.download_url ? (
                          <a href={d.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                            {d.file_name}
                          </a>
                        ) : (
                          d.file_name
                        )}
                      </div>
                      <span className={`flex items-center gap-1 text-xs font-medium ${badge.className}`}>
                        <Icon name={badge.icon} className="h-4 w-4" />
                        {badge.label}
                      </span>
                    </div>
                    {d.verification_status === "rejected" && d.rejection_reason && (
                      <p className="mt-1 text-xs text-danger">Reason: {d.rejection_reason}</p>
                    )}
                    {d.verification_status === "pending" && (
                      <div className="mt-2 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => onVerify(d.id)}
                          className="rounded border border-success text-success text-xs font-medium py-1 px-2.5 hover:bg-success/10"
                        >
                          Verify
                        </button>
                        {rejectingId === d.id ? (
                          <>
                            <input
                              type="text"
                              placeholder="Rejection reason"
                              value={rejectReason}
                              onChange={(e) => setRejectReason(e.target.value)}
                              className="rounded border border-border px-2 py-1 text-xs"
                            />
                            <button
                              type="button"
                              disabled={!rejectReason.trim()}
                              onClick={() => onReject(d.id)}
                              className="rounded border border-danger text-danger text-xs font-medium py-1 px-2.5 disabled:opacity-50"
                            >
                              Confirm Reject
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => { setRejectingId(d.id); setRejectReason(""); }}
                            className="rounded border border-border text-text/60 text-xs font-medium py-1 px-2.5 hover:bg-background"
                          >
                            Reject
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <div className="bg-card border border-border rounded-card shadow-card p-6 space-y-3">
          <h3 className="text-sm font-semibold text-text/70">Assignment</h3>
          <p className="text-sm text-text">{application.assigned_to_name || "Unassigned"}</p>
          {role === "owner" && (
            <>
              <input
                type="text"
                placeholder="Employee ID"
                value={employeeId}
                onChange={(e) => setEmployeeId(e.target.value)}
                className="w-full rounded border border-border px-3 py-2 text-sm"
              />
              <button
                type="button"
                disabled={!employeeId}
                onClick={onAssign}
                className="w-full rounded bg-primary text-white text-sm font-medium py-2 disabled:opacity-50"
              >
                Assign
              </button>
              <p className="text-xs text-text/40">Find the Employee ID from the Employees list.</p>
            </>
          )}
        </div>
      </div>
    </SimplePageLayout>
  );
}
