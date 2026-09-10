import { useEffect, useState } from "react";
import { Button } from "@/components/buttons/Button";
import { FormField } from "@/components/forms/FormField";
import { SelectField } from "@/components/forms/SelectField";
import { TextareaField } from "@/components/forms/TextareaField";
import { Modal } from "@/components/overlays/Modal";
import { getErrorMessage } from "@/features/customer/errors";
import {
  createManualInsuranceCase,
  listInsuranceLookupCategories,
  listInsuranceLookupProducts,
  MANUAL_CREATE_STAGES,
  type InsuranceCaseDetail,
  type InsuranceLookupItem,
} from "@/features/insurance_management/api";
import { INSURANCE_RE_ELIGIBILITY_OPTIONS } from "@/features/insurance_management/statusControl";
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
  const [categories, setCategories] = useState<InsuranceLookupItem[]>([]);
  const [products, setProducts] = useState<InsuranceLookupItem[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [productId, setProductId] = useState("");
  const [productsLoading, setProductsLoading] = useState(false);

  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [alternateMobile, setAlternateMobile] = useState("");
  const [email, setEmail] = useState("");
  const [gender, setGender] = useState("");
  const [age, setAge] = useState("");
  const [profession, setProfession] = useState("");
  const [education, setEducation] = useState("");
  const [height, setHeight] = useState("");
  const [weight, setWeight] = useState("");
  const [motherName, setMotherName] = useState("");
  const [fatherName, setFatherName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [designation, setDesignation] = useState("");
  const [annualIncome, setAnnualIncome] = useState("");
  const [nomineeName, setNomineeName] = useState("");
  const [nomineeDob, setNomineeDob] = useState("");
  const [nomineeRelationship, setNomineeRelationship] = useState("");
  const [remarks, setRemarks] = useState("");
  const [stage, setStage] = useState("fresh_lead");
  const [reason, setReason] = useState("");
  const [reChoice, setReChoice] = useState<ReChoice>("");
  const [customDate, setCustomDate] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listInsuranceLookupCategories()
      .then(setCategories)
      .catch((e) => setError(getErrorMessage(e)));
  }, []);

  useEffect(() => {
    setProductId("");
    setProducts([]);
    if (!categoryId) return;
    setProductsLoading(true);
    listInsuranceLookupProducts(categoryId)
      .then(setProducts)
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setProductsLoading(false));
  }, [categoryId]);

  const needsReEligibility = stage === "rejected" || stage === "re_eligible";
  const today = todayISTDateString();
  const customDateInvalid = reChoice === "custom" && Boolean(customDate) && customDate <= today;

  const alternateMobileInvalid = alternateMobile.trim().length > 0 && !/^[6-9]\d{9}$/.test(alternateMobile.trim());

  const canSubmit =
    fullName.trim().length > 0 &&
    /^[6-9]\d{9}$/.test(mobile) &&
    !alternateMobileInvalid &&
    Boolean(categoryId) &&
    Boolean(productId) &&
    Boolean(age) &&
    (!needsReEligibility || (reason.trim().length > 0 && Boolean(reChoice) && (reChoice !== "custom" || (Boolean(customDate) && !customDateInvalid)))) &&
    !submitting;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const trimmed = (v: string) => v.trim() || undefined;
      const num = (v: string) => (v ? Number(v) : undefined);
      const created = await createManualInsuranceCase({
        full_name: fullName.trim(),
        mobile,
        alternate_mobile: trimmed(alternateMobile),
        email: trimmed(email),
        gender: gender || undefined,
        age: num(age),
        profession: trimmed(profession),
        education: trimmed(education),
        height: num(height),
        weight: num(weight),
        mother_name: trimmed(motherName),
        father_name: trimmed(fatherName),
        company_name: trimmed(companyName),
        designation: trimmed(designation),
        annual_income: num(annualIncome),
        nominee_name: trimmed(nomineeName),
        nominee_dob: nomineeDob || undefined,
        nominee_relationship: trimmed(nomineeRelationship),
        remarks: trimmed(remarks),
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
          <div>
            <FormField
              label="Alternate Mobile (optional)"
              name="alternate_mobile"
              maxLength={10}
              value={alternateMobile}
              onChange={(e) => setAlternateMobile(e.target.value)}
            />
            {alternateMobileInvalid && <p className="-mt-3 text-xs text-danger">Enter a valid 10-digit mobile number.</p>}
          </div>
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
        </div>

        <h3 className="pt-2 text-xs font-semibold uppercase tracking-wide text-text/50">Personal Details</h3>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Profession (optional)" name="profession" value={profession} onChange={(e) => setProfession(e.target.value)} />
          <FormField label="Education (optional)" name="education" value={education} onChange={(e) => setEducation(e.target.value)} />
          <FormField label="Height cm (optional)" name="height" type="number" min={0} value={height} onChange={(e) => setHeight(e.target.value)} />
          <FormField label="Weight kg (optional)" name="weight" type="number" min={0} value={weight} onChange={(e) => setWeight(e.target.value)} />
          <FormField label="Mother's Name (optional)" name="mother_name" value={motherName} onChange={(e) => setMotherName(e.target.value)} />
          <FormField label="Father's Name (optional)" name="father_name" value={fatherName} onChange={(e) => setFatherName(e.target.value)} />
        </div>

        <h3 className="pt-2 text-xs font-semibold uppercase tracking-wide text-text/50">Employment Details</h3>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Company Name (optional)" name="company_name" value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
          <FormField label="Designation (optional)" name="designation" value={designation} onChange={(e) => setDesignation(e.target.value)} />
          <FormField label="Annual Income (optional)" name="annual_income" type="number" min={0} value={annualIncome} onChange={(e) => setAnnualIncome(e.target.value)} />
        </div>

        <h3 className="pt-2 text-xs font-semibold uppercase tracking-wide text-text/50">Nominee Details</h3>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <FormField label="Nominee Name (optional)" name="nominee_name" value={nomineeName} onChange={(e) => setNomineeName(e.target.value)} />
          <FormField label="Nominee DOB (optional)" name="nominee_dob" type="date" value={nomineeDob} onChange={(e) => setNomineeDob(e.target.value)} />
          <FormField
            label="Relationship with Nominee (optional)"
            name="nominee_relationship"
            value={nomineeRelationship}
            onChange={(e) => setNomineeRelationship(e.target.value)}
          />
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
            disabled={!categoryId || productsLoading}
            value={productId}
            onChange={(e) => setProductId(e.target.value)}
            placeholder={
              !categoryId ? "Select a category first" : productsLoading ? "Loading products…" : "Select a product"
            }
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
