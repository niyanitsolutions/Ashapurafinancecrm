import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { Pagination } from "@/components/tables/Pagination";
import { getErrorMessage } from "@/features/customer/errors";
import {
  approveCommissionEntry,
  listCommissionEntries,
  settleCommissionEntry,
  type CommissionEntry,
} from "@/features/referral_partner_management/api";

const PAGE_SIZE = 20;

function SettleModal({ entry, onClose, onSaved }: { entry: CommissionEntry; onClose: () => void; onSaved: () => void }) {
  const [paymentReference, setPaymentReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paymentReference.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await settleCommissionEntry(entry.id, paymentReference.trim());
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
      title="Settle Commission"
      description={`${entry.partner_name || entry.partner_id} · ₹${entry.commission_amount.toLocaleString()}`}
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="settle-commission-form" size="sm" loading={isSubmitting} disabled={!paymentReference.trim()}>
            Settle
          </Button>
        </>
      }
    >
      <form id="settle-commission-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <FormField label="Payment Reference" value={paymentReference} onChange={(e) => setPaymentReference(e.target.value)} required autoFocus />
      </form>
    </Modal>
  );
}

export function CommissionLedgerPage() {
  const [items, setItems] = useState<CommissionEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [settleTarget, setSettleTarget] = useState<CommissionEntry | null>(null);

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
    <SimplePageLayout
      title="Commission Ledger"
      subtitle="Pending → Approved → Paid. Settlement is manual — there is no payment gateway integration yet; recording a reference here is the record of payment."
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={status} onChange={(e) => { setPage(1); setStatus(e.target.value); }} className="rounded-xl border border-border px-3.5 py-2.5 text-sm bg-card">
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="paid">Paid</option>
        </select>
      </div>

      {!isLoading && items.length === 0 ? (
        <EmptyState icon="commission" title="No commission entries yet" description="Entries appear here once a referred lead results in a disbursed loan or issued policy." />
      ) : (
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
              {!isLoading &&
                items.map((entry) => (
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
                        <button type="button" onClick={() => setSettleTarget(entry)} className="text-primary hover:underline text-xs">
                          Settle
                        </button>
                      )}
                      {entry.status === "paid" && entry.payment_reference && <span className="text-xs text-text/50">Ref: {entry.payment_reference}</span>}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} totalItems={total} pageSize={PAGE_SIZE} itemLabel="entries" onPageChange={setPage} />

      {settleTarget && (
        <SettleModal
          entry={settleTarget}
          onClose={() => setSettleTarget(null)}
          onSaved={() => {
            setSettleTarget(null);
            setMessage("Commission entry settled.");
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
