import { useEffect, useState } from "react";
import { SubmitButton } from "@/components/forms/SubmitButton";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { getErrorMessage } from "@/features/customer/errors";
import {
  activateCommissionRule,
  createCommissionRule,
  deactivateCommissionRule,
  listCommissionRules,
  type CommissionRule,
} from "@/features/referral_partner_management/api";

export function CommissionRulesPage() {
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    setIsLoading(true);
    listCommissionRules()
      .then(setRules)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

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
    <SimplePageLayout title="Commission Rules">
      <p className="mb-4 text-sm text-text/60">
        Commission rates are never hardcoded — configure them here. A rule with no Product set applies to every product category; a rule with no
        Referral Partner ID set is the default for everyone (a partner-specific rule overrides it). Editing a rule's rate never changes commission
        entries already created from it — those keep their own snapshot.
      </p>
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      <div className="mb-6 bg-card border border-border rounded-card shadow-card p-6">
        <h3 className="text-sm font-semibold text-text/70 mb-3">Create Commission Rule</h3>
        <CreateRuleForm onSubmit={(payload) => run(() => createCommissionRule(payload), "Commission rule created.")} />
      </div>

      <div className="space-y-4">
        {isLoading && <p className="text-sm text-text/50">Loading…</p>}
        {!isLoading && rules.length === 0 && <p className="text-sm text-text/50">No commission rules configured yet.</p>}
        {rules.map((rule) => (
          <div key={rule.id} className="bg-card border border-border rounded-card shadow-card p-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-text">{rule.label}</div>
              <div className="text-xs text-text/50 mt-1">
                Product: {rule.product_category || "All"} · Partner: {rule.partner_id || "Default (all partners)"} · Trigger: {rule.trigger_event.replace("_", " ")}
              </div>
              <div className="text-xs text-text/50">
                {rule.calculation_type === "percentage" ? `${rule.rate_or_amount}%` : `₹${rule.rate_or_amount}`} ({rule.calculation_type})
              </div>
            </div>
            <button
              type="button"
              onClick={() => run(() => (rule.status === "active" ? deactivateCommissionRule(rule.id) : activateCommissionRule(rule.id)), "Rule status updated.")}
              className={`rounded border text-xs font-medium py-1 px-3 ${rule.status === "active" ? "border-success text-success" : "border-text/30 text-text/50"}`}
            >
              {rule.status === "active" ? "Active" : "Inactive"}
            </button>
          </div>
        ))}
      </div>
    </SimplePageLayout>
  );
}

function CreateRuleForm({
  onSubmit,
}: {
  onSubmit: (payload: { label: string; product_category?: string; partner_id?: string; calculation_type: string; rate_or_amount: number; trigger_event: string }) => void;
}) {
  const [label, setLabel] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [calculationType, setCalculationType] = useState("percentage");
  const [rateOrAmount, setRateOrAmount] = useState(0);
  const [triggerEvent, setTriggerEvent] = useState("loan_disbursed");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          label, product_category: productCategory || undefined, partner_id: partnerId || undefined,
          calculation_type: calculationType, rate_or_amount: rateOrAmount, trigger_event: triggerEvent,
        });
        setLabel("");
        setProductCategory("");
        setPartnerId("");
        setRateOrAmount(0);
      }}
      className="grid grid-cols-3 gap-3"
    >
      <input placeholder="Label" value={label} onChange={(e) => setLabel(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" required />
      <select value={productCategory} onChange={(e) => setProductCategory(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
        <option value="">All Products</option>
        <option value="loan">Loan</option>
        <option value="insurance">Insurance</option>
      </select>
      <input placeholder="Referral Partner ID (optional — blank = default)" value={partnerId} onChange={(e) => setPartnerId(e.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
      <select value={calculationType} onChange={(e) => setCalculationType(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
        <option value="percentage">Percentage</option>
        <option value="flat">Flat Amount</option>
      </select>
      <input
        type="number" step="0.01" placeholder="Rate / Amount" value={rateOrAmount}
        onChange={(e) => setRateOrAmount(Number(e.target.value))} className="rounded border border-border px-3 py-2 text-sm" required
      />
      <select value={triggerEvent} onChange={(e) => setTriggerEvent(e.target.value)} className="rounded border border-border px-3 py-2 text-sm">
        <option value="loan_disbursed">Loan Disbursed</option>
        <option value="insurance_policy_issued">Insurance Policy Issued</option>
      </select>
      <div className="col-span-3">
        <SubmitButton>Create Rule</SubmitButton>
      </div>
    </form>
  );
}
