import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { ConfirmDialog } from "@/components/overlays/ConfirmDialog";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { usePermissions } from "@/features/access_control/usePermissions";
import { getErrorMessage } from "@/features/customer/errors";
import {
  approveReferralPartner,
  createReferralPartner,
  deactivateReferralPartner,
  listReferralPartners,
  type ReferralPartner,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

function CreatePartnerModal({ onClose, onSaved }: { onClose: () => void; onSaved: (successMessage: string) => void }) {
  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await createReferralPartner({ full_name: fullName, mobile, email: email || undefined, business_name: businessName || undefined });
      onSaved("Referral Partner created and invited.");
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
      title="Create Referral Partner"
      description="Sends a signup invite (OTP) to the given mobile number. They can set a password right away, but can't submit leads until approved."
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-partner-form" size="sm" loading={isSubmitting}>
            Create &amp; Invite
          </Button>
        </>
      }
    >
      <form id="create-partner-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          <FormField label="Mobile" value={mobile} onChange={(e) => setMobile(e.target.value)} required />
          <FormField label="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <FormField label="Business Name (optional)" value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
        </div>
      </form>
    </Modal>
  );
}

export function ReferralPartnerListPage() {
  const { can, isOwner } = usePermissions();
  const canCreate = can("referral_partner_management:partners", "create");
  const [items, setItems] = useState<ReferralPartner[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [approvalStatus, setApprovalStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deactivateTarget, setDeactivateTarget] = useState<ReferralPartner | null>(null);

  const load = () => {
    setIsLoading(true);
    listReferralPartners({ page, page_size: PAGE_SIZE, approval_status: approvalStatus || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, approvalStatus]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
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

  return (
    <SimplePageLayout
      title="Channel Partners"
      subtitle="Manage the partners who refer leads to you, and their approval status."
      actions={canCreate ? <Button size="sm" onClick={() => setIsCreateOpen(true)}>+ Create Referral Partner</Button> : undefined}
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={approvalStatus} onChange={(e) => { setPage(1); setApprovalStatus(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          <option value="pending_approval">Pending Approval</option>
          <option value="active">Active</option>
          <option value="deactivated">Deactivated</option>
        </select>
      </div>

      {!isLoading && items.length === 0 ? (
        <EmptyState
          icon="referral"
          title="No channel partners yet"
          description="Add your first channel partner to start tracking their referred leads and commissions."
          primaryAction={canCreate ? { label: "+ Create Referral Partner", onClick: () => setIsCreateOpen(true) } : undefined}
        />
      ) : (
        <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-text/60">
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Mobile</th>
                <th className="px-4 py-3">Business</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
              {!isLoading &&
                items.map((partner) => (
                  <tr key={partner.id} className="border-b border-border last:border-0 hover:bg-background">
                    <td className="px-4 py-3">{partner.partner_code}</td>
                    <td className="px-4 py-3">{partner.full_name}</td>
                    <td className="px-4 py-3">{partner.mobile}</td>
                    <td className="px-4 py-3">{partner.business_name || "—"}</td>
                    <td className="px-4 py-3 capitalize">{partner.approval_status.replace("_", " ")}</td>
                    <td className="px-4 py-3">
                      {/* Approve/Deactivate stay Owner-only server-side (no matrix-grantable
                          permission exists for them) — gate on isOwner, not a permission check. */}
                      {isOwner && partner.approval_status !== "active" && (
                        <button type="button" onClick={() => run(() => approveReferralPartner(partner.id), "Referral Partner approved.")} className="text-primary hover:underline text-xs mr-3">
                          Approve
                        </button>
                      )}
                      {isOwner && partner.approval_status !== "deactivated" && (
                        <button type="button" onClick={() => setDeactivateTarget(partner)} className="text-danger hover:underline text-xs">
                          Deactivate
                        </button>
                      )}
                      {!isOwner && <span className="text-text/30">—</span>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="partners" onPageChange={setPage} />

      {isCreateOpen && (
        <CreatePartnerModal
          onClose={() => setIsCreateOpen(false)}
          onSaved={(successMessage) => {
            setIsCreateOpen(false);
            setMessage(successMessage);
            load();
          }}
        />
      )}

      <ConfirmDialog
        open={deactivateTarget !== null}
        title="Deactivate Referral Partner"
        message={deactivateTarget ? `Deactivate ${deactivateTarget.full_name}? They will no longer be able to submit leads.` : ""}
        confirmLabel="Deactivate"
        confirmVariant="danger"
        onConfirm={async () => {
          if (!deactivateTarget) return;
          await run(() => deactivateReferralPartner(deactivateTarget.id), "Referral Partner deactivated.");
          setDeactivateTarget(null);
        }}
        onClose={() => setDeactivateTarget(null)}
      />
    </SimplePageLayout>
  );
}
