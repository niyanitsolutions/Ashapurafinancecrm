import { useEffect, useState } from "react";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  approveCommissionEntry,
  listCommissionEntries,
  settleCommissionEntry,
  type CommissionEntry,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

export function CommissionLedgerPage() {
  const [items, setItems] = useState<CommissionEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [paymentRefByEntry, setPaymentRefByEntry] = useState<Record<string, string>>({});

  const load = () => {
    setIsLoading(true);
    listCommissionEntries({ page, page_size: PAGE_SIZE, status: status || undefined })
      .then((res) => {
        setItems(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [page, status]);

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
    <SimplePageLayout title="Commission Ledger">
      <p className="mb-4 text-sm text-text/60">
        Pending → Approved → Paid. Settlement is manual — there is no payment gateway integration yet; recording a reference here is the record of
        payment.
      </p>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
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
              <th className="px-4 py-3">Partner</th>
              <th className="px-4 py-3">Case</th>
              <th className="px-4 py-3">Base Amount</th>
              <th className="px-4 py-3">Commission</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">Loading…</td></tr>}
            {!isLoading && items.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-center text-text/50">No commission entries yet.</td></tr>}
            {items.map((entry) => (
              <tr key={entry.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{entry.partner_name || entry.partner_id}</td>
                <td className="px-4 py-3 capitalize">{entry.case_type}</td>
                <td className="px-4 py-3">₹{entry.base_amount.toLocaleString()}</td>
                <td className="px-4 py-3">₹{entry.commission_amount.toLocaleString()}</td>
                <td className="px-4 py-3 capitalize">{entry.status}</td>
                <td className="px-4 py-3">
                  {entry.status === "pending" && (
                    <button type="button" onClick={() => run(() => approveCommissionEntry(entry.id), "Commission entry approved.")} className="text-primary hover:underline text-xs">
                      Approve
                    </button>
                  )}
                  {entry.status === "approved" && (
                    <div className="flex items-center gap-2">
                      <input
                        placeholder="Payment ref." value={paymentRefByEntry[entry.id] || ""}
                        onChange={(e) => setPaymentRefByEntry((prev) => ({ ...prev, [entry.id]: e.target.value }))}
                        className="rounded border border-border px-2 py-1 text-xs w-28"
                      />
                      <button
                        type="button"
                        onClick={() => run(() => settleCommissionEntry(entry.id, paymentRefByEntry[entry.id] || ""), "Commission entry settled.")}
                        className="text-primary hover:underline text-xs"
                      >
                        Settle
                      </button>
                    </div>
                  )}
                  {entry.status === "paid" && entry.payment_reference && <span className="text-xs text-text/50">Ref: {entry.payment_reference}</span>}
                </td>
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
    </SimplePageLayout>
  );
}
