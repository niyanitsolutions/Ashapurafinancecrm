import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  createSavedFilter,
  deleteSavedFilter,
  exportReportUrl,
  listSavedFilters,
  runReport,
  type ReportResult,
  type SavedFilter,
} from "@/features/reporting/api";
import { getAccessToken } from "@/shared/api/client";

// Plain `<a href>` can't carry the Bearer token — same pattern as Leads' CSV export
// (frontend/src/features/leads/pages/LeadListPage.tsx).
async function downloadCsv(url: string, filename: string, setError: (msg: string | null) => void) {
  setError(null);
  try {
    const token = getAccessToken();
    const response = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) throw new Error("Export failed");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objectUrl);
  } catch {
    setError("Couldn't export this report. Please try again.");
  }
}

export function ReportViewerPage() {
  const { reportKey } = useParams<{ reportKey: string }>();
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [result, setResult] = useState<ReportResult | null>(null);
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [newFilterLabel, setNewFilterLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    if (!reportKey) return;
    setIsLoading(true);
    setError(null);
    runReport(reportKey, { date_from: dateFrom || undefined, date_to: dateTo || undefined })
      .then(setResult)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [reportKey]); // eslint-disable-line react-hooks/exhaustive-deps -- explicit "Run" button applies date changes

  useEffect(() => {
    if (!reportKey) return;
    listSavedFilters(reportKey).then(setSavedFilters).catch(() => setSavedFilters([]));
  }, [reportKey]);

  if (!reportKey) return null;

  const applySavedFilter = (filter: SavedFilter) => {
    setDateFrom((filter.filters.date_from as string) ?? "");
    setDateTo((filter.filters.date_to as string) ?? "");
  };

  const saveCurrentFilter = async () => {
    if (!newFilterLabel) return;
    setError(null);
    try {
      await createSavedFilter({ report_key: reportKey, label: newFilterLabel, filters: { date_from: dateFrom || undefined, date_to: dateTo || undefined } });
      setNewFilterLabel("");
      setMessage("Filter saved.");
      listSavedFilters(reportKey).then(setSavedFilters);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const removeSavedFilter = async (filterId: string) => {
    setError(null);
    try {
      await deleteSavedFilter(filterId);
      setSavedFilters((prev) => prev.filter((f) => f.id !== filterId));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <SimplePageLayout title={reportKey.replace(/_/g, " ")}>
      <div className="mb-4">
        <Link to="/reports" className="text-sm text-primary hover:underline">
          ← Back to Reports
        </Link>
      </div>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-4 flex flex-wrap items-end gap-3">
        <label className="text-xs text-text/60">
          From
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="mt-1 block rounded-xl border border-border px-3.5 py-2.5 text-sm" />
        </label>
        <label className="text-xs text-text/60">
          To
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="mt-1 block rounded-xl border border-border px-3.5 py-2.5 text-sm" />
        </label>
        <Button size="sm" onClick={load}>
          Run
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => downloadCsv(exportReportUrl(reportKey, { date_from: dateFrom || undefined, date_to: dateTo || undefined }), `${reportKey}.csv`, setError)}
        >
          Export CSV
        </Button>

        <div className="flex flex-wrap items-end gap-2 sm:ml-auto">
          {savedFilters.length > 0 && (
            <select
              onChange={(e) => {
                const filter = savedFilters.find((f) => f.id === e.target.value);
                if (filter) applySavedFilter(filter);
              }}
              className="rounded-xl border border-border px-3.5 py-2.5 text-sm"
              defaultValue=""
            >
              <option value="" disabled>Load saved filter…</option>
              {savedFilters.map((f) => (
                <option key={f.id} value={f.id}>{f.label}</option>
              ))}
            </select>
          )}
          <input
            placeholder="Save as…" value={newFilterLabel} onChange={(e) => setNewFilterLabel(e.target.value)}
            className="rounded-xl border border-border px-3.5 py-2.5 text-sm w-32"
          />
          <Button variant="ghost" size="sm" onClick={saveCurrentFilter}>
            Save Filter
          </Button>
        </div>
      </div>

      {savedFilters.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          {savedFilters.map((f) => (
            <span key={f.id} className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1 text-xs text-text/70">
              {f.label}
              <button type="button" onClick={() => removeSavedFilter(f.id)} className="text-danger hover:underline">×</button>
            </span>
          ))}
        </div>
      )}

      {isLoading && <p className="text-sm text-text/50">Loading…</p>}
      {!isLoading && result && (
        <>
          {result.summary && (
            <div className="mb-4 flex flex-wrap gap-4">
              {Object.entries(result.summary).map(([key, value]) => (
                <div key={key} className="bg-card border border-border rounded-card shadow-card px-4 py-2">
                  <div className="text-xs text-text/50">{key.replace(/_/g, " ")}</div>
                  <div className="text-sm font-semibold text-text">{String(value)}</div>
                </div>
              ))}
            </div>
          )}
          <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-text/60">
                  {result.columns.map((c) => (
                    <th key={c.key} className="px-4 py-3">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.length === 0 && (
                  <tr>
                    <td colSpan={result.columns.length}>
                      <EmptyState icon="reports" title="No data for this date range" description="Try widening the date range or changing the filters above." />
                    </td>
                  </tr>
                )}
                {result.rows.map((row, i) => (
                  <tr key={i} className="border-b border-border last:border-0 hover:bg-background">
                    {result.columns.map((c) => (
                      <td key={c.key} className="px-4 py-3">{row[c.key] === null || row[c.key] === undefined ? "—" : String(row[c.key])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </SimplePageLayout>
  );
}
