import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { ErrorBanner } from "@/components/forms/ErrorBanner";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { EmptyState } from "@/components/layout/EmptyState";
import { SimplePageLayout } from "@/components/layout/SimplePageLayout";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import {
  activateCommissionRule,
  createCommissionRule,
  deactivateCommissionRule,
  listCommissionRules,
  type CommissionRule,
} from "@/features/referral_partner_management/api";

function CreateRuleModal({ onClose, onSaved }: { onClose: () => void; onSaved: (message: string) => void }) {
  const [label, setLabel] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [partnerId, setPartnerId] = useState("");
  const [calculationType, setCalculationType] = useState("percentage");
  const [rateOrAmount, setRateOrAmount] = useState("0");
  const [triggerEvent, setTriggerEvent] = useState("loan_disbursed");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await createCommissionRule({
        label, product_category: productCategory || undefined, partner_id: partnerId || undefined,
        calculation_type: calculationType, rate_or_amount: Number(rateOrAmount), trigger_event: triggerEvent,
      });
      onSaved("Commission rule created.");
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
      title="Create Commission Rule"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-rule-form" size="sm" loading={isSubmitting}>
            Create Rule
          </Button>
        </>
      }
    >
      <form id="create-rule-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <FormField label="Label" value={label} onChange={(e) => setLabel(e.target.value)} required />
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <SelectField
            label="Product"
            value={productCategory}
            onChange={(e) => setProductCategory(e.target.value)}
            placeholder="All Products"
            options={[
              { value: "loan", label: "Loan" },
              { value: "insurance", label: "Insurance" },
            ]}
          />
          <FormField
            label="Referral Partner ID (optional)"
            value={partnerId}
            onChange={(e) => setPartnerId(e.target.value)}
            placeholder="Blank = default for all partners"
          />
          <SelectField
            label="Calculation Type"
            value={calculationType}
            onChange={(e) => setCalculationType(e.target.value)}
            options={[
              { value: "percentage", label: "Percentage" },
              { value: "flat", label: "Flat Amount" },
            ]}
          />
          <FormField label="Rate / Amount" type="number" step="0.01" value={rateOrAmount} onChange={(e) => setRateOrAmount(e.target.value)} required />
        </div>
        <SelectField
          label="Trigger Event"
          value={triggerEvent}
          onChange={(e) => setTriggerEvent(e.target.value)}
          options={[
            { value: "loan_disbursed", label: "Loan Disbursed" },
            { value: "insurance_policy_issued", label: "Insurance Policy Issued" },
          ]}
        />
      </form>
    </Modal>
  );
}

export function CommissionRulesPage() {
  const [rules, setRules] = useState<CommissionRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

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
    <SimplePageLayout
      title="Commission Rules"
      subtitle="Commission rates are never hardcoded — configure them here. A rule with no Product set applies to every product category; a rule with no Referral Partner ID set is the default for everyone. Editing a rule's rate never changes commission entries already created from it."
      actions={<Button size="sm" onClick={() => setIsCreateOpen(true)}>+ Create Commission Rule</Button>}
    >
      {message && <p className="mb-4 text-sm text-success">{message}</p>}
      <ErrorBanner message={error} />

      {!isLoading && rules.length === 0 ? (
        <EmptyState
          icon="commission"
          title="No commission rules configured yet"
          description="Create your first commission rule to define how partners earn on referred leads."
          primaryAction={{ label: "+ Create Commission Rule", onClick: () => setIsCreateOpen(true) }}
        />
      ) : (
        <div className="space-y-4">
          {isLoading && <p className="text-sm text-text/50">Loading…</p>}
          {!isLoading &&
            rules.map((rule) => (
              <div key={rule.id} className="bg-card border border-border rounded-card shadow-card p-4 flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-semibold text-text">{rule.label}</div>
                  <div className="text-xs text-text/50 mt-1">
                    Product: {rule.product_category || "All"} · Partner: {rule.partner_id || "Default (all partners)"} · Trigger: {rule.trigger_event.replace("_", " ")}
                  </div>
                  <div className="text-xs text-text/50">
                    {rule.calculation_type === "percentage" ? `${rule.rate_or_amount}%` : `₹${rule.rate_or_amount}`} ({rule.calculation_type})
                  </div>
                </div>
                <Button
                  variant={rule.status === "active" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => run(() => (rule.status === "active" ? deactivateCommissionRule(rule.id) : activateCommissionRule(rule.id)), "Rule status updated.")}
                >
                  {rule.status === "active" ? "Active" : "Inactive"}
                </Button>
              </div>
            ))}
        </div>
      )}

      {isCreateOpen && (
        <CreateRuleModal
          onClose={() => setIsCreateOpen(false)}
          onSaved={(msg) => {
            setIsCreateOpen(false);
            setMessage(msg);
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
