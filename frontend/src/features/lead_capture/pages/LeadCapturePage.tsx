import { useEffect, useState } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  listCaptureFailures,
  listCaptureSources,
  retryCaptureFailure,
  updateCaptureSource,
  type CaptureFailure,
  type CaptureSource,
} from "@/features/lead_capture/api";

const SOURCE_LABELS: Record<string, string> = { website_form: "Website Form", meta_lead_ads: "Meta Lead Ads", manual_api: "Manual API" };

const PAGE_SIZE = 20;

export function LeadCapturePage() {
  const [sources, setSources] = useState<CaptureSource[]>([]);
  const [failures, setFailures] = useState<CaptureFailure[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadSources = () => { listCaptureSources().then(setSources).catch((err) => setError(getErrorMessage(err))); };
  const loadFailures = () => {
    listCaptureFailures({ page, page_size: PAGE_SIZE, status: statusFilter || undefined })
      .then((res) => {
        setFailures(res.data);
        setTotal(res.pagination?.total ?? res.data.length);
      })
      .catch((err) => setError(getErrorMessage(err)));
  };

  useEffect(loadSources, []);
  useEffect(loadFailures, [page, statusFilter]);

  const run = async (action: () => Promise<unknown>, successMessage: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(successMessage);
      loadSources();
      loadFailures();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <SimplePageLayout
      title="Lead Capture Log"
      subtitle="How website, Meta, and other automated channels attribute leads — and any that failed to import. For administrators only."
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div id="source-mapping" className="mb-6 bg-card border border-border rounded-card shadow-card p-6 scroll-mt-20">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Source Mapping</h3>
        <p className="mb-3 text-xs text-text/50">Which Lead Source (Settings) each capture channel attributes its leads to — never hardcoded.</p>
        <div className="space-y-3">
          {sources.map((source) => (
            <SourceRow key={source.key} source={source} onSave={(payload) => run(() => updateCaptureSource(source.key, payload), "Source mapping updated.")} />
          ))}
        </div>
      </div>

      <div id="capture-failures" className="mb-4 flex items-center gap-4 scroll-mt-20">
        <h3 className="text-sm font-semibold text-text/70">Capture Failures</h3>
        <select value={statusFilter} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} className="rounded border border-border px-3 py-2 text-sm">
          <option value="">All Statuses</option>
          <option value="pending">Pending Retry</option>
          <option value="resolved">Resolved</option>
          <option value="exhausted">Exhausted</option>
          <option value="ignored">Ignored</option>
        </select>
      </div>
      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Detail</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Retries</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {failures.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState icon="lead-capture" title="No failed imports" description="Leads that fail to import from your website or Meta Lead Ads — due to missing data or a duplicate — will show up here for review." />
                </td>
              </tr>
            )}
            {failures.map((f) => (
              <tr key={f.id} className="border-b border-border last:border-0 hover:bg-background">
                <td className="px-4 py-3">{SOURCE_LABELS[f.capture_source] || f.capture_source}</td>
                <td className="px-4 py-3 capitalize">{f.failure_reason.replace(/_/g, " ")}</td>
                <td className="px-4 py-3 max-w-xs truncate" title={f.error_detail || ""}>{f.error_detail || "—"}</td>
                <td className="px-4 py-3 capitalize">{f.status}</td>
                <td className="px-4 py-3">{f.retry_count}</td>
                <td className="px-4 py-3">
                  {(f.status === "pending" || f.status === "exhausted") && (
                    <button type="button" onClick={() => run(() => retryCaptureFailure(f.id), "Retry attempted.")} className="text-primary hover:underline text-xs">
                      Retry Now
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-4 text-sm text-text/60">
        <span>Page {page} of {totalPages} ({total} failures)</span>
        <div className="flex gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Previous</button>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded border border-border px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </SimplePageLayout>
  );
}

function SourceRow({ source, onSave }: { source: CaptureSource; onSave: (payload: Record<string, string>) => void }) {
  const [defaultCategory, setDefaultCategory] = useState(source.default_product_category || "");
  const [defaultProductId, setDefaultProductId] = useState(source.default_product_id || "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ default_product_category: defaultCategory, default_product_id: defaultProductId });
      }}
      className="flex flex-wrap items-end gap-3 border-b border-border last:border-0 pb-3 last:pb-0"
    >
      <div className="text-sm text-text min-w-[10rem]">{SOURCE_LABELS[source.key] || source.key}</div>
      <label className="text-xs text-text/60">
        Default Product Category
        <select value={defaultCategory} onChange={(e) => setDefaultCategory(e.target.value)} className="mt-1 block rounded border border-border px-3 py-2 text-sm">
          <option value="">None</option>
          <option value="loan">Loan</option>
          <option value="insurance">Insurance</option>
        </select>
      </label>
      <label className="text-xs text-text/60">
        Default Product ID
        <input value={defaultProductId} onChange={(e) => setDefaultProductId(e.target.value)} className="mt-1 block rounded border border-border px-3 py-2 text-sm w-56" />
      </label>
      <button type="submit" className="text-primary hover:underline text-xs">Save</button>
    </form>
  );
}
