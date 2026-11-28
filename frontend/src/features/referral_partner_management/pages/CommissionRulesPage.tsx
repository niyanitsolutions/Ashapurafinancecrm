import { useEffect, useState } from "react";
import { apiRequest } from "@/shared/api/client";
import { listReferralPartners, updateCommissionRule } from "../api";
import { istDateKey } from "@/shared/dateFormat";
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

function CreateRuleModal({ onClose, onSaved, existing }: { onClose: () => void; onSaved: (message: string) => void; existing?: CommissionRule | null }) {
  const [label, setLabel] = useState(existing?.label??"");
  const [productCategory, setProductCategory] = useState(existing?.product_category??"");
  const [partnerId, setPartnerId] = useState(existing?.partner_id??"");
  const [calculationType, setCalculationType] = useState(existing?.calculation_type??"percentage");
  const [rateOrAmount, setRateOrAmount] = useState(String(existing?.rate_or_amount??0));
  const [triggerEvent, setTriggerEvent] = useState(existing?.trigger_event??"loan_disbursed");
  const [products,setProducts]=useState<{id:string;name:string}[]>([]);
  const [partnerSearch,setPartnerSearch]=useState("");
  const [partners,setPartners]=useState<{id:string;full_name:string}[]>([]);
  const [productId,setProductId]=useState(existing?.product_id??"");
  const [effectiveFrom,setEffectiveFrom]=useState(existing?.effective_from?istDateKey(existing.effective_from):"");
  const [effectiveUntil,setEffectiveUntil]=useState(existing?.effective_until?istDateKey(existing.effective_until):"");
  const [terms,setTerms]=useState(existing?.terms??"");
  const [fixedConfirmed,setFixedConfirmed]=useState(existing?.fixed_contract_confirmed??false);
  const [fixedPolicy,setFixedPolicy]=useState(existing?.fixed_event_policy??"");
  const [active,setActive]=useState(existing?.status!=="inactive");
  useEffect(()=>{void apiRequest<{id:string;name:string}[]>("/loan-products").then(setProducts).catch(e=>setError(e.message));},[]);
  useEffect(()=>{let current=true;void listReferralPartners({page_size:100,search:partnerSearch||undefined}).then(r=>{if(current)setPartners(r.data);}).catch(e=>{if(current)setError(e.message);});return()=>{current=false;};},[partnerSearch]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await (existing ? (payload: Parameters<typeof createCommissionRule>[0])=>updateCommissionRule(existing.id,payload) : createCommissionRule)({
        label, product_category: productCategory || null, partner_id: partnerId || null,
        calculation_type: calculationType, rate_or_amount: Number(rateOrAmount), trigger_event: triggerEvent,
        product_id: productId||null, effective_from: effectiveFrom?new Date(effectiveFrom+"T00:00:00+05:30").toISOString():null, effective_until: effectiveUntil?new Date(effectiveUntil+"T00:00:00+05:30").toISOString():null, terms, fixed_contract_confirmed: calculationType==="flat"&&fixedConfirmed, fixed_event_policy: calculationType==="flat"?(fixedPolicy||null):null, status: active?"active":"inactive",
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
      title={existing?"Publish new commission rule version":"Create Commission Rule"}
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-rule-form" size="sm" loading={isSubmitting}>
            {existing?"Publish new version":"Create Rule"}
          </Button>
        </>
      }
    >
      <form id="create-rule-form" onSubmit={onSubmit}>
        <ErrorBanner message={error} />
        <FormField label="Search applicable Partners" value={partnerSearch} onChange={e=>setPartnerSearch(e.target.value)}/>
        <SelectField label="Applicable Partner" value={partnerId} onChange={e=>setPartnerId(e.target.value)} options={[{value:"",label:"All Partners"},...(partnerId&&!partners.some(partner=>partner.id===partnerId)?[{value:partnerId,label:`Selected Partner ${partnerId}`}]:[]),...partners.map(p=>({value:p.id,label:p.full_name}))]}/>
        <SelectField label="Loan Product" value={productId} onChange={e=>{setProductId(e.target.value);if(e.target.value)setProductCategory("loan");}} options={[{value:"",label:"All products in the selected category"},...products.map(p=>({value:p.id,label:p.name}))]}/>
        <p className="text-sm">{triggerEvent==="insurance_policy_issued"?"Calculation basis: confirmed policy premium.":"Calculation basis: actual eligible disbursed amount."} Partner-specific rules take precedence.</p>
        <FormField label="Effective From" required type="date" value={effectiveFrom} onChange={e=>setEffectiveFrom(e.target.value)}/>
        <FormField label="Effective Until (exclusive, optional)" type="date" value={effectiveUntil} onChange={e=>setEffectiveUntil(e.target.value)}/>
        <label className="mb-3 block"><input type="checkbox" checked={active} onChange={e=>setActive(e.target.checked)}/>Rule active</label>
        <FormField label="Commission terms and conditions" value={terms} onChange={e=>setTerms(e.target.value)}/>
        {calculationType==="flat"&&<SelectField label="Confirmed fixed-amount contract basis" value={fixedPolicy} onChange={e=>setFixedPolicy(e.target.value)} options={[{value:"",label:"Select the approved contract basis"},{value:"per_case",label:"Once per Loan Case"},{value:"per_event",label:"Each eligible disbursement event"}]}/>}
        <label className="mb-3 block text-sm"><input type="checkbox" checked={fixedConfirmed} onChange={e=>setFixedConfirmed(e.target.checked)}/>A fixed amount is explicitly supported by the approved commission contract</label>
        <p className="mb-3 text-sm">1. Select Partner and product. 2. Set the actual disbursement rate. 3. Confirm effective dates and terms.</p>
        <FormField label="Rule Name" value={label} onChange={(e) => setLabel(e.target.value)} required />
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
  const [editingRule,setEditingRule]=useState<CommissionRule|null>(null);

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
                {!rules.some(candidate=>candidate.previous_rule_id===rule.id)&&<Button variant="secondary" onClick={()=>setEditingRule(rule)}>Edit new version</Button>}
                <span className="text-xs">Version {rule.rule_version??1}</span>
                <Button
                  disabled={rules.some(candidate=>candidate.previous_rule_id===rule.id)}
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

      {(isCreateOpen||editingRule) && (
        <CreateRuleModal
          existing={editingRule}
          onClose={() => {setIsCreateOpen(false);setEditingRule(null);}}
          onSaved={(msg) => {
            setIsCreateOpen(false);
            setEditingRule(null);
            setMessage(msg);
            load();
          }}
        />
      )}
    </SimplePageLayout>
  );
}
