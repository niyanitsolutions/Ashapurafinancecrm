import { useEffect, useState } from "react";
import { getErrorMessage } from "@/features/customer/errors";
import { getOwnDashboard, getOwnPartner, type ReferralDashboard, type ReferralPartner } from "@/features/referral_partner_management/api";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-card border border-border rounded-card shadow-card p-4">
      <div className="text-xs text-text/50">{label}</div>
      <div className="text-xl font-semibold text-text mt-1">{value}</div>
    </div>
  );
}

export function ReferralPartnerDashboardPage() {
  const [dashboard, setDashboard] = useState<ReferralDashboard | null>(null);
  const [partner, setPartner] = useState<ReferralPartner | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    getOwnPartner()
      .then(setPartner)
      .catch((err) => setError(getErrorMessage(err)));
    getOwnDashboard()
      .then(setDashboard)
      .catch(() => undefined) // pre-approval, the dashboard has nothing to show yet — the banner below explains why
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) return <p className="text-sm text-text/50">Loading…</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;

  return (
    <div>
      <h1 className="text-xl font-semibold text-text mb-6">Dashboard</h1>

      {partner && partner.approval_status !== "active" && (
        <div className="mb-6 rounded-card border border-warning/40 bg-warning/10 p-4 text-sm text-text">
          {partner.approval_status === "pending_approval"
            ? "Your account is pending Owner approval. You'll be able to submit leads once approved."
            : "Your account has been deactivated. Contact the Owner for details."}
        </div>
      )}
      {!dashboard ? null : (
        <>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <StatCard label="Total Leads" value={dashboard.total_leads} />
        <StatCard label="Approved" value={dashboard.approved_leads} />
        <StatCard label="Rejected" value={dashboard.rejected_leads} />
        <StatCard label="Commission Pending" value={`₹${dashboard.commission_pending.toLocaleString()}`} />
        <StatCard label="Commission Paid" value={`₹${dashboard.commission_paid.toLocaleString()}`} />
        <StatCard label="Balance" value={`₹${dashboard.commission_balance.toLocaleString()}`} />
      </div>

      <div className="bg-card border border-border rounded-card shadow-card overflow-x-auto">
        <div className="px-4 py-3 border-b border-border text-sm font-semibold text-text/70">Recent Leads</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text/60">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Mobile</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {dashboard.recent_leads.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-text/50">No leads submitted yet.</td></tr>}
            {dashboard.recent_leads.map((lead) => (
              <tr key={lead.lead_id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">{lead.full_name}</td>
                <td className="px-4 py-3">{lead.mobile}</td>
                <td className="px-4 py-3 capitalize">{lead.external_status.replace("_", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
        </>
      )}
    </div>
  );
}
