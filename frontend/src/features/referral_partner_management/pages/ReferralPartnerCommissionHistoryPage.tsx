import { useEffect, useState } from "react";
import { getErrorMessage } from "@/features/customer/errors";
import { listOwnCommissionEntries, type CommissionEntry } from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

export function ReferralPartnerCommissionHistoryPage() {
  const [items, setItems] = useState<CommissionEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    listOwnCommissionEntries({ page, page_size: PAGE_SIZE, status: status || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [page, status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <h1 className="text-xl font-semibold text-text mb-6">Commission History</h1>
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-4 flex items-center gap-4">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="paid">Paid</option>
        </select>
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Case Type</th>
              <th className="px-4 py-3">Base Amount</th>
              <th className="px-4 py-3">Commission</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Paid Reference</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
            {!isLoading && items.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-text/50">No commission entries yet.</td></tr>}
            {items.map((entry) => (
              <tr key={entry.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3 capitalize">{entry.case_type}</td>
                <td className="px-4 py-3">₹{entry.base_amount.toLocaleString()}</td>
                <td className="px-4 py-3">₹{entry.commission_amount.toLocaleString()}</td>
                <td className="px-4 py-3 capitalize">{entry.status}</td>
                <td className="px-4 py-3">{entry.payment_reference || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} entries)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
}
