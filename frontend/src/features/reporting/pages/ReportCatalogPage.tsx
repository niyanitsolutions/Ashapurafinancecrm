import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import { listReportDefinitions, type ReportDefinition } from "@/features/reporting/api";

const CATEGORY_LABELS: Record<string, string> = {
  lead: "Lead Reports",
  loan: "Loan Reports",
  insurance: "Insurance Reports",
  employee: "Employee Reports",
  referral: "Referral Reports",
  dashboard: "Dashboard Analytics",
};

export function ReportCatalogPage() {
  const [definitions, setDefinitions] = useState<ReportDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    listReportDefinitions()
      .then(setDefinitions)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  const byCategory = definitions.reduce<Record<string, ReportDefinition[]>>((acc, d) => {
    (acc[d.category] ??= []).push(d);
    return acc;
  }, {});

  return (
    <SimplePageLayout title="Reports">
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}
      {isLoading && <p className="text-sm text-text/50">Loading…</p>}
      <div className="space-y-6">
        {Object.entries(byCategory).map(([category, reports]) => (
          <div key={category}>
            <h3 className="text-sm font-semibold text-text/70 mb-2">{CATEGORY_LABELS[category] || category}</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {reports.map((report) => (
                <Link
                  key={report.key} to={`/reports/${report.key}`}
                  className="bg-card border border-border rounded-card shadow-card p-4 hover:border-primary transition-colors"
                >
                  <div className="text-sm font-medium text-text">{report.label}</div>
                  <div className="text-xs text-text/50 mt-1">{report.description}</div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}
