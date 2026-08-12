import { useEffect, useState } from "react";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  approveReferralPartner,
  createReferralPartner,
  deactivateReferralPartner,
  listReferralPartners,
  type ReferralPartner,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

export function ReferralPartnerListPage() {
  const [items, setItems] = useState<ReferralPartner[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [approvalStatus, setApprovalStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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
    <SimplePageLayout title="Channel Partners" subtitle="Manage the partners who refer leads to you, and their approval status.">
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Create Referral Partner</h3>
        <p className="mb-3 text-xs text-text/50">
          Sends a signup invite (OTP) to the given mobile number, same as inviting a Customer. The partner can set their password right away, but
          can't submit leads until you approve them below.
        </p>
        <CreatePartnerForm onSubmit={(payload) => run(() => createReferralPartner(payload), "Referral Partner created and invited.")} />
      </div>

      <div className="mb-4 flex items-center gap-4">
        <select value={approvalStatus} onChange={(e) => { setPage(1); setApprovalStatus(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          <option value="pending_approval">Pending Approval</option>
          <option value="active">Active</option>
          <option value="deactivated">Deactivated</option>
        </select>
      </div>

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
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon="referral"
                    title="No channel partners yet"
                    description="Add your first channel partner above to start tracking their referred leads and commissions."
                  />
                </td>
              </tr>
            )}
            {items.map((partner) => (
              <tr key={partner.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{partner.partner_code}</td>
                <td className="px-4 py-3">{partner.full_name}</td>
                <td className="px-4 py-3">{partner.mobile}</td>
                <td className="px-4 py-3">{partner.business_name || "—"}</td>
                <td className="px-4 py-3 capitalize">{partner.approval_status.replace("_", " ")}</td>
                <td className="px-4 py-3">
                  {partner.approval_status !== "active" && (
                    <button type="button" onClick={() => run(() => approveReferralPartner(partner.id), "Referral Partner approved.")} className="text-primary hover:underline text-xs mr-3">
                      Approve
                    </button>
                  )}
                  {partner.approval_status !== "deactivated" && (
                    <button type="button" onClick={() => run(() => deactivateReferralPartner(partner.id), "Referral Partner deactivated.")} className="text-danger hover:underline text-xs">
                      Deactivate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} partners)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}

function CreatePartnerForm({ onSubmit }: { onSubmit: (payload: { full_name: string; mobile: string; email?: string; business_name?: string }) => void }) {
  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [businessName, setBusinessName] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ full_name: fullName, mobile, email: email || undefined, business_name: businessName || undefined });
        setFullName("");
        setMobile("");
        setEmail("");
        setBusinessName("");
      }}
      className="grid grid-cols-2 gap-3"
    >
      <input placeholder="Full Name" value={fullName} onChange={(e) => setFullName(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Mobile" value={mobile} onChange={(e) => setMobile(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <input placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <input placeholder="Business Name (optional)" value={businessName} onChange={(e) => setBusinessName(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <div className="col-span-2">
        <SubmitButton>Create &amp; Invite</SubmitButton>
      </div>
    </form>
  );
}
