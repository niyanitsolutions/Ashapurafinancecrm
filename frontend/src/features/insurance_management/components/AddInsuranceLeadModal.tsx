import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { listPortalInsuranceCategories, listPortalProducts } from "@/features/customer/api";
import { getErrorMessage } from "@/features/customer/errors";
import {
  createManualInsuranceCase,
  MANUAL_CREATE_STAGES,
  type InsuranceCaseDetail,
} from "@/features/insurance_management/api";
import { INSURANCE_RE_ELIGIBILITY_OPTIONS } from "@/features/insurance_management/statusControl";
import type { NamedMasterData } from "@/features/system_settings/api";
import { todayISTDateString } from "@/shared/dateFormat";

type ReChoice = (typeof INSURANCE_RE_ELIGIBILITY_OPTIONS)[number]["value"] | "";

// Staff "+ Add Insurance Lead" — the walk-in / phoned-in counterpart of a customer
// applying through the portal. Creates one Insurance case (never a Lead). The backend
// walks the case to the chosen initial stage through the real gated transitions.
export function AddInsuranceLeadModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (created: InsuranceCaseDetail) => void;
}) {
  const [categories, setCategories] = useState<NamedMasterData[]>([]);
  const [products, setProducts] = useState<NamedMasterData[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [productId, setProductId] = useState("");

  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [gender, setGender] = useState("");
  const [age, setAge] = useState("");
  const [profession, setProfession] = useState("");
  const [annualIncome, setAnnualIncome] = useState("");
  const [remarks, setRemarks] = useState("");
  const [stage, setStage] = useState("fresh_lead");
  const [reason, setReason] = useState("");
  const [reChoice, setReChoice] = useState<ReChoice>("");
  const [customDate, setCustomDate] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPortalInsuranceCategories().then(setCategories).catch((e) => setError(getErrorMessage(e)));
  }, []);

  useEffect(() => {
    setProductId("");
    setProducts([]);
    if (!categoryId) return;
    listPortalProducts("insurance", { insuranceCategoryId: categoryId })
      .then(setProducts)
      .catch((e) => setError(getErrorMessage(e)));
  }, [categoryId]);

  const needsReEligibility = stage === "rejected" || stage === "re_eligible";
  const today = todayISTDateString();
  const customDateInvalid = reChoice === "custom" && Boolean(customDate) && customDate <= today;

  const canSubmit =
    fullName.trim().length > 0 &&
    /^[6-9]\d{9}$/.test(mobile) &&
    Boolean(categoryId) &&
    Boolean(productId) &&
    Boolean(age) &&
    (!needsReEligibility || (reason.trim().length > 0 && Boolean(reChoice) && (reChoice !== "custom" || (Boolean(customDate) && !customDateInvalid)))) &&
    !submitting;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const created = await createManualInsuranceCase({
        full_name: fullName.trim(),
        mobile,
        email: email.trim() || undefined,
        gender: gender || undefined,
        age: age ? Number(age) : undefined,
        profession: profession.trim() || undefined,
        annual_income: annualIncome ? Number(annualIncome) : undefined,
        remarks: remarks.trim() || undefined,
        insurance_category_id: categoryId,
        product_id: productId,
        stage,
        reason: needsReEligibility ? reason.trim() : undefined,
        re_eligibility: needsReEligibility && reChoice ? reChoice : undefined,
        re_eligible_date: needsReEligibility && reChoice === "custom" ? customDate : undefined,
      });
      onCreated(created);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Add Insurance Lead" size="lg">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) void submit();
        }}
        className="space-y-3"
      >
        {error && <p className="text-sm text-danger">{error}</p>}

        <h3 className="text-xs font-semibold uppercase tracking-wide text-text/50">Customer Details</h3>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Name" name="full_name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          <FormField label="Mobile" name="mobile" required maxLength={10} value={mobile} onChange={(e) => setMobile(e.target.value)} />
          <FormField label="Email (optional)" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <SelectField
            label="Gender"
            name="gender"
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            placeholder="Select"
            options={[
              { value: "male", label: "Male" },
              { value: "female", label: "Female" },
              { value: "other", label: "Other" },
            ]}
          />
          <FormField label="Age" name="age" required type="number" min={18} max={120} value={age} onChange={(e) => setAge(e.target.value)} />
          <FormField label="Profession (optional)" name="profession" value={profession} onChange={(e) => setProfession(e.target.value)} />
          <FormField label="Annual Income (optional)" name="annual_income" type="number" min={0} value={annualIncome} onChange={(e) => setAnnualIncome(e.target.value)} />
        </div>

        <h3 className="pt-2 text-xs font-semibold uppercase tracking-wide text-text/50">Insurance Details</h3>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <SelectField
            label="Insurance Category"
            name="insurance_category_id"
            required
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            placeholder="Select a category"
            options={categories.map((c) => ({ value: c.id, label: c.name }))}
          />
          <SelectField
            label="Insurance Product"
            name="product_id"
            required
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder={categoryId ? "Select a product" : "Select a category first"}
            options={products.map((p) => ({ value: p.id, label: p.name }))}
          />
        </div>
        <TextareaField label="Remarks (optional)" name="remarks" rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} />

        <SelectField
          label="Initial Stage"
          name="stage"
          required
          value={stage}
          onChange={(e) => setStage(e.target.value)}
          options={MANUAL_CREATE_STAGES.map((s) => ({ value: s.value, label: s.label }))}
        />

        {needsReEligibility && (
          <div className="space-y-2 rounded border border-border bg-background/50 p-3">
            <TextareaField
              label="Rejection Reason (mandatory)"
              name="reason"
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
            <div>
              <p className="mb-1 text-sm font-medium text-text">Re-Eligibility</p>
              <div className="space-y-1.5">
                {INSURANCE_RE_ELIGIBILITY_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex cursor-pointer items-center gap-2 text-sm text-text">
                    <input
                      type="radio"
                      name="add-lead-re-eligibility"
                      value={opt.value}
                      checked={reChoice === opt.value}
                      onChange={() => setReChoice(opt.value)}
                      className="accent-primary"
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>
            {reChoice === "custom" && (
              <div>
                <FormField
                  label="Re-Eligible Date"
                  name="re_eligible_date"
                  type="date"
                  value={customDate}
                  min={today}
                  onChange={(e) => setCustomDate(e.target.value)}
                  required
                />
                {customDateInvalid && <p className="mt-1 text-xs text-danger">The Re-Eligible date must be in the future.</p>}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button type="submit" className="flex-1" loading={submitting} disabled={!canSubmit}>
            Create Insurance Lead
          </Button>
          <Button type="button" variant="secondary" className="flex-1" disabled={submitting} onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}
