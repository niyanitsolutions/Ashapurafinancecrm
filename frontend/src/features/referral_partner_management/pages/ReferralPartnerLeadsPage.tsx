import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getErrorMessage } from "@/features/customer/errors";
import {
  listOwnLeads,
  updateReferralLead,
  type ReferralLead,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

export function ReferralPartnerLeadsPage() {
  const [items, setItems] = useState<ReferralLead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editingLeadId, setEditingLeadId] = useState<string | null>(null);

  const load = () => {
    setIsLoading(true);
    listOwnLeads({ page, page_size: PAGE_SIZE })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page]);

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
    <div>
      <h1 className="text-xl font-semibold text-text mb-6">My Leads</h1>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <Link className="mb-6 block text-primary underline" to="/referral-portal/add-customer">Create a reviewed Customer referral</Link>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Mobile</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
            {!isLoading && items.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">No leads submitted yet.</td></tr>}
            {items.map((lead) => (
              <tr key={lead.lead_id} className="border-b border-border last:border-0 hover:bg-background align-top">
                <td className="px-4 py-3">{lead.lead_code}</td>
                <td className="px-4 py-3">
                  {editingLeadId === lead.lead_id ? (
                    <EditLeadForm
                      lead={lead}
                      onCancel={() => setEditingLeadId(null)}
                      onSubmit={(payload) =>
                        run(() => updateReferralLead(lead.lead_id, payload), "Lead updated.").finally(() => setEditingLeadId(null))
                      }
                    />
                  ) : (
                    lead.full_name
                  )}
                </td>
                <td className="px-4 py-3">{lead.mobile}</td>
                <td className="px-4 py-3 capitalize">{lead.external_status.replace("_", " ")}</td>
                <td className="px-4 py-3">
                  {lead.editable && editingLeadId !== lead.lead_id && (
                    <button type="button" onClick={() => setEditingLeadId(lead.lead_id)} className="text-primary hover:underline text-xs">
                      Edit
                    </button>
                  )}
                  {!lead.editable && <span className="text-xs text-text/40">Locked — processing started</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} leads)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}

function EditLeadForm({
  lead, onSubmit, onCancel,
}: {
  lead: ReferralLead;
  onSubmit: (payload: { full_name?: string; mobile?: string; email?: string; remarks?: string }) => void;
  onCancel: () => void;
}) {
  const [fullName, setFullName] = useState(lead.full_name);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ full_name: fullName });
      }}
      className="flex items-center gap-2"
    >
      <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="rounded border border-border px-2 py-1 text-sm" />
      <button type="submit" className="text-primary hover:underline text-xs">Save</button>
      <button type="button" onClick={onCancel} className="text-text/50 hover:underline text-xs">Cancel</button>
    </form>
  );
}
